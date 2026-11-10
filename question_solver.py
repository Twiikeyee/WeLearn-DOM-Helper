# -*- coding: utf-8 -*-
"""
WeLearn Question Parser & Solver Strategy.

Derived from UnipusAI-Helper (c) 2024 YSJohnson (GNU AGPLv3).
Adapted for WeLearn Platform (welearn.sflep.com) by WeLearn-DOM-Helper contributors.
Licensed under GNU AGPLv3.
"""

import logging
import re
import time
from typing import Any, Callable, Dict, List, Optional

from selenium.common.exceptions import (
    NoAlertPresentException,
    NoSuchElementException,
    StaleElementReferenceException,
)
from selenium.webdriver.common.by import By
from ai_client import OpenAICompatibleClient
from tts_engine import TTSEngine
from webdriver_helper import WebDriverHelper
from welearn_config import Config

logger = logging.getLogger("WeLearnBot")


class WeLearnQuestionSolver:
    """Core question solver implementing DOM-first and LLM-fallback strategies."""

    def __init__(
        self,
        config: Config,
        ai_client: Optional[OpenAICompatibleClient] = None,
        tts_engine: Optional[TTSEngine] = None,
        log_callback: Optional[Callable[[str], None]] = None,
    ):
        self.config = config
        self.ai_client = ai_client or OpenAICompatibleClient(config)
        self.tts_engine = tts_engine or TTSEngine(
            engine=config.tts_engine, voice=config.tts_voice, proxy=config.tts_proxy
        )
        self.log_callback = log_callback or (lambda msg: logger.info(msg))

    def log(self, message: str) -> None:
        """Deliver log message to UI queue or logger."""
        if self.log_callback:
            try:
                self.log_callback(message)
            except Exception:
                pass
        else:
            logger.info(message)

    def _fill_text(self, driver, element, text: str) -> None:
        """Dispatch text input according to typing_mode (fast vs simulate)."""
        mode = getattr(self.config, "typing_mode", "fast").lower()
        if mode == "simulate":
            WebDriverHelper.simulate_typing(driver, element, text)
        else:
            WebDriverHelper.fast_fill(driver, element, text)

    def locate_sco_scope(self, driver, scoid: str):
        """Locate the section page container strictly bounded by data-scoid."""
        selectors = [
            f'li[data-scoid="{scoid}"][data-controltype="page"]',
            f'li[data-scoid="{scoid}"]',
            f'[data-scoid="{scoid}"]',
        ]
        for sel in selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, sel)
                for el in elements:
                    if el.is_displayed():
                        return el
                if elements:
                    return elements[0]
            except Exception:
                continue

        fallback_selectors = [
            'li[data-controltype="page"]:not([style*="display: none"])',
            'div.main_page:not([style*="display: none"])',
            'div.part_content',
            'body',
        ]
        for sel in fallback_selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, sel)
                if elements:
                    return elements[0]
            except Exception:
                continue

        return driver

    def fill_sco_questions(self, driver, scoid: str) -> Dict[str, Any]:
        """Fill all questions within the active SCO scope without waiting or submitting."""
        start_time = time.time()
        scope = self.locate_sco_scope(driver, scoid)
        self.log(f"-> 锁定小节作答范围: SCO [{scoid}]")

        # Step 1: Solve Choice Questions (div[data-controltype="choice"])
        choice_count = self._solve_choices(driver, scope)

        # Step 2: Solve Objective Short Fill-in (div[data-controltype="filling"])
        filling_count = self._solve_objective_fillings(driver, scope)

        # Step 3: Solve Subjective Long Fill-in / Open Essay (div[data-controltype="fillinglong"])
        subjective_count = self._solve_subjective_fillings(driver, scope)

        # Step 4: Handle Audio / Record elements
        record_count = self._handle_audio_records(driver, scope)

        elapsed_solving = time.time() - start_time
        is_voice_only = (record_count > 0) and (choice_count + filling_count + subjective_count == 0)
        self.log(
            f"   作答统计: 选择 {choice_count} 道, 填空 {filling_count} 道, "
            f"主观题 {subjective_count} 道, 语音/录音 {record_count} 道 (耗时 {elapsed_solving:.1f} 秒)"
        )
        if is_voice_only:
            self.log(f"   提示: SCO [{scoid}] 为纯语音/口语录音题，若平台限制网页提交将仅累计学习时长。")

        return {
            "scoid": scoid,
            "choice_count": choice_count,
            "filling_count": filling_count,
            "subjective_count": subjective_count,
            "record_count": record_count,
            "elapsed_solving": elapsed_solving,
            "is_voice_only": is_voice_only,
        }

    def solve_sco(
        self,
        driver,
        scoid: str,
        dwell_seconds: Optional[float] = None,
        skip_submit: bool = False,
    ) -> bool:
        """Process all questions within the active SCO scope, dwell, and optionally submit."""
        stats = self.fill_sco_questions(driver, scoid)
        elapsed_solving = stats["elapsed_solving"]
        scope = self.locate_sco_scope(driver, scoid)

        # Step 5: Dynamic dwell time and submission
        self._dwell_and_submit(
            driver,
            scope,
            elapsed_time=elapsed_solving,
            target_dwell_override=dwell_seconds,
            skip_submit=skip_submit,
        )
        return True

    def _solve_choices(self, driver, scope) -> int:
        """Extract and solve choice questions using DOM-native data-solution."""
        try:
            choice_containers = scope.find_elements(By.CSS_SELECTOR, 'div[data-controltype="choice"]')
        except Exception:
            return 0

        solved_count = 0
        for idx, container in enumerate(choice_containers):
            try:
                options = container.find_elements(
                    By.CSS_SELECTOR,
                    'ul[data-itemtype="options"] > li, [data-itemtype="options"] li, li'
                )
                if not options:
                    continue

                solution_selected = False
                for opt in options:
                    sol_attr = opt.get_attribute("data-solution")
                    if sol_attr is not None:
                        opt_text = (opt.text or "").strip().replace("\n", " ")
                        self.log(f"   [选择题 {idx+1}] 命中 DOM 原生答案: {opt_text[:30] or '(选项标签)'}")
                        WebDriverHelper.safe_click(driver, opt)
                        solution_selected = True

                if not solution_selected:
                    for opt in options:
                        inputs = opt.find_elements(By.CSS_SELECTOR, 'input, span, label')
                        for inp in inputs:
                            if inp.get_attribute("data-solution") is not None:
                                self.log(f"   [选择题 {idx+1}] 命中子节点原生答案")
                                WebDriverHelper.safe_click(driver, opt)
                                solution_selected = True
                                break
                        if solution_selected:
                            break

                if not solution_selected and options:
                    self.log(f"   [选择题 {idx+1}] 未发现 data-solution 标记，默认选择第 1 项")
                    WebDriverHelper.safe_click(driver, options[0])

                solved_count += 1
            except Exception as e:
                logger.debug("Error solving choice question %d: %s", idx, e)

        return solved_count

    def _solve_objective_fillings(self, driver, scope) -> int:
        """Extract and solve short fill-in inputs using DOM data-solution or result."""
        try:
            inputs = scope.find_elements(
                By.CSS_SELECTOR,
                'div[data-controltype="filling"] input[data-itemtype="input"], '
                'div[data-controltype="filling"] input[type="text"], '
                'input[data-itemtype="input"]'
            )
        except Exception:
            return 0

        solved_count = 0
        for idx, inp in enumerate(inputs):
            try:
                solution = inp.get_attribute("data-solution")

                if not solution:
                    try:
                        parent = inp.find_element(By.XPATH, "..")
                        results = parent.find_elements(By.CSS_SELECTOR, '[data-itemtype="result"]')
                        if results:
                            solution = (results[0].text or "").strip()
                    except Exception:
                        pass

                if solution:
                    clean_answer = str(solution).split("/")[0].strip()
                    self.log(f"   [客观填空 {idx+1}] 填入 DOM 原生答案: '{clean_answer}'")
                    self._fill_text(driver, inp, clean_answer)
                    solved_count += 1
                else:
                    default_ans = "answer"
                    self._fill_text(driver, inp, default_ans)
                    solved_count += 1
            except Exception as e:
                logger.debug("Error solving filling question %d: %s", idx, e)

        return solved_count

    def _solve_subjective_fillings(self, driver, scope) -> int:
        """Solve subjective open essay / long filling questions (LLM or default template)."""
        try:
            containers = scope.find_elements(
                By.CSS_SELECTOR, 'div[data-controltype="fillinglong"]'
            )
        except Exception:
            return 0

        solved_count = 0
        for idx, container in enumerate(containers):
            try:
                text_areas = container.find_elements(
                    By.CSS_SELECTOR, 'textarea, input[type="text"], [contenteditable="true"]'
                )
                if not text_areas:
                    continue

                target_input = text_areas[0]

                # Check if data-solution is present on textarea or container
                solution = target_input.get_attribute("data-solution") or container.get_attribute("data-solution")
                if solution:
                    clean_ans = str(solution).strip()
                    self.log(f"   [主观题 {idx+1}] 命中 DOM 原生标准答案: {clean_ans[:30]}...")
                    self._fill_text(driver, target_input, clean_ans)
                    solved_count += 1
                    continue

                # Decision: Call LLM vs Use Generic Academic Template
                use_llm = bool(getattr(self.config, "enable_llm_subjective", False)) and self.ai_client.is_available()

                if use_llm:
                    direction = ""
                    context = ""
                    stem = ""

                    try:
                        dir_els = scope.find_elements(By.CSS_SELECTOR, '.direction, [data-itemtype="direction"], .part_title')
                        if dir_els:
                            direction = (dir_els[0].text or "").strip()
                    except Exception:
                        pass

                    try:
                        white_frames = scope.find_elements(By.CSS_SELECTOR, '.white_frame, .passage, .reading_content')
                        if white_frames:
                            context = (white_frames[0].text or "").strip()
                    except Exception:
                        pass

                    try:
                        stem_els = container.find_elements(By.CSS_SELECTOR, 'span[data-itemtype="stem"], [data-itemtype="stem"]')
                        if stem_els:
                            stem = (stem_els[0].text or "").strip()
                        else:
                            stem = (container.text or "").strip()
                    except Exception:
                        stem = (container.text or "").strip()

                    self.log(f"   [主观题 {idx+1}] 已开启 LLM 辅助，正在请求大模型生成答案...")
                    llm_answer = self.ai_client.solve_subjective_question(
                        stem=stem, direction=direction, context=context
                    )
                    self.log(f"   [主观题 {idx+1}] LLM 答复: '{llm_answer[:35]}...'")
                    self._fill_text(driver, target_input, llm_answer)
                else:
                    default_text = getattr(
                        self.config,
                        "subjective_default_text",
                        "From my perspective, this viewpoint is quite reasonable and practical."
                    )
                    self.log(f"   [主观题 {idx+1}] 零 Token 模式：填入标准学术范句")
                    self._fill_text(driver, target_input, default_text)

                solved_count += 1
            except Exception as e:
                logger.debug("Error solving subjective filling question %d: %s", idx, e)

        return solved_count

    def _handle_audio_records(self, driver, scope) -> int:
        """Handle record and audio controls safely."""
        try:
            records = scope.find_elements(
                By.CSS_SELECTOR, '[data-controltype="record"], [data-controltype="myaudio"]'
            )
        except Exception:
            return 0

        handled_count = 0
        for idx, rec in enumerate(records):
            try:
                triggers = rec.find_elements(
                    By.CSS_SELECTOR, 'button, .btn_record, .record_btn, .btn_play, a'
                )
                if triggers:
                    self.log(f"   [录音/音频题 {idx+1}] 触发录音/播放控件")
                    WebDriverHelper.safe_click(driver, triggers[0])
                    time.sleep(0.5)
                    stop_btns = rec.find_elements(By.CSS_SELECTOR, '.btn_stop, .stop_btn')
                    if stop_btns:
                        WebDriverHelper.safe_click(driver, stop_btns[0])
                handled_count += 1
            except Exception as e:
                logger.debug("Error handling audio record %d: %s", idx, e)

        return handled_count

    def _dwell_and_submit(
        self,
        driver,
        scope,
        elapsed_time: float = 0.0,
        target_dwell_override: Optional[float] = None,
        skip_submit: bool = False,
    ) -> None:
        """Dynamic dwell time deduction and SCORM native submission."""
        if target_dwell_override is not None:
            target_dwell = max(0.0, float(target_dwell_override))
        else:
            target_dwell = max(0.0, float(self.config.min_dwell_seconds))

        remaining_wait = max(0.0, float(target_dwell) - float(elapsed_time))

        if target_dwell > 0:
            if remaining_wait > 0.1:
                self.log(
                    f"   需补齐分配时长，等待 {remaining_wait:.1f} 秒 (目标 {target_dwell:.1f}s, 已耗时 {elapsed_time:.1f}s)..."
                )
                time.sleep(remaining_wait)
            else:
                self.log(f"   答题耗时 {elapsed_time:.1f}s 已满足分配时长 ({target_dwell:.1f}s)，无需额外停留。")

        if skip_submit:
            self.log("   [纯挂时长/解耦阶段] 跳过重复点击提交按钮。")
            return

        self.submit_sco_in_scope(driver, scope)

    def submit_sco(self, driver, scoid: str) -> bool:
        """Locate SCO scope and trigger native SCORM submission."""
        scope = self.locate_sco_scope(driver, scoid)
        return self.submit_sco_in_scope(driver, scope)

    def submit_sco_in_scope(self, driver, scope) -> bool:
        """Click submit button inside the given scope and confirm dialogs safely."""
        submit_selectors = [
            '[data-controltype="submit"]',
            'button[data-controltype="submit"]',
            'a[data-controltype="submit"]',
            'input[data-controltype="submit"]',
            '.btn_submit',
            '#btn_submit',
        ]
        submit_btn = None
        for sel in submit_selectors:
            try:
                buttons = scope.find_elements(By.CSS_SELECTOR, sel)
                visible = [b for b in buttons if b.is_displayed()]
                if visible:
                    submit_btn = visible[0]
                    break
                elif buttons:
                    submit_btn = buttons[0]
                    break
            except Exception:
                continue

        if submit_btn:
            self.log("   点击页面提交按钮 [data-controltype='submit']...")
            try:
                # Bypass courseware layui layer confirmEx dialogs
                driver.execute_script("""
                window.confirmEx = function(title, defaultTitle, yesF, noF) {
                    if (yesF) yesF();
                };
                window.CONFIRM_AUTO_CALL = [{title: "", action: true}];
                """)
            except Exception:
                pass

            WebDriverHelper.safe_click(driver, submit_btn)
            time.sleep(0.8)

            try:
                alert = driver.switch_to.alert
                alert_text = alert.text
                alert.accept()
                self.log(f"   已确认提交弹窗: {alert_text}")
            except NoAlertPresentException:
                pass
            except Exception:
                pass

            try:
                confirm_btns = driver.find_elements(
                    By.CSS_SELECTOR, '.btn_confirm, .dialog_ok, .btn_ok, .layui-layer-btn0'
                )
                for cb in confirm_btns:
                    if cb.is_displayed():
                        WebDriverHelper.safe_click(driver, cb)
                        break
            except Exception:
                pass

            time.sleep(0.6)
            self.log("   已完成原生提交，SCORM 状态已同步。")
            return True
        else:
            self.log("   未在当前小节中发现提交按钮（可能为纯阅读、自动保存或受限语音小节）。")
            return False
