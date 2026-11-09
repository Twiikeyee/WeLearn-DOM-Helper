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
        """Deliver log message to UI queue and logger."""
        logger.info(message)
        if self.log_callback:
            try:
                self.log_callback(message)
            except Exception:
                pass

    def locate_sco_scope(self, driver, scoid: str):
        """Locate the section page container strictly bounded by data-scoid."""
        # 1. Exact match: li[data-scoid="{scoid}"] or [data-scoid="{scoid}"]
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

        # 2. Fallback: currently active or visible page container
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

    def solve_sco(self, driver, scoid: str) -> bool:
        """Process all questions within the active SCO scope and submit."""
        scope = self.locate_sco_scope(driver, scoid)
        self.log(f"-> 锁定小节作答范围: SCO [{scoid}]")

        questions_answered = 0

        # Step 1: Solve Choice Questions (div[data-controltype="choice"])
        choice_count = self._solve_choices(driver, scope)
        questions_answered += choice_count

        # Step 2: Solve Objective Short Fill-in (div[data-controltype="filling"])
        filling_count = self._solve_objective_fillings(driver, scope)
        questions_answered += filling_count

        # Step 3: Solve Subjective Long Fill-in / Open Essay (div[data-controltype="fillinglong"])
        subjective_count = self._solve_subjective_fillings(driver, scope)
        questions_answered += subjective_count

        # Step 4: Handle Audio / Record elements ([data-controltype="record"], [data-controltype="myaudio"])
        record_count = self._handle_audio_records(driver, scope)
        questions_answered += record_count

        total_found = choice_count + filling_count + subjective_count + record_count
        self.log(
            f"   作答统计: 选择题 {choice_count} 道, 填空题 {filling_count} 道, "
            f"主观题 {subjective_count} 道, 音频题 {record_count} 道 (共处理 {total_found} 项)"
        )

        # Step 5: Dwell time and Submission
        self._dwell_and_submit(driver, scope)
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
                # Find options within container
                options = container.find_elements(
                    By.CSS_SELECTOR,
                    'ul[data-itemtype="options"] > li, [data-itemtype="options"] li, li'
                )
                if not options:
                    continue

                solution_selected = False
                for opt in options:
                    # Check if option has data-solution attribute (DOM native answer!)
                    sol_attr = opt.get_attribute("data-solution")
                    if sol_attr is not None:
                        opt_text = (opt.text or "").strip().replace("\n", " ")
                        self.log(f"   [选择题 {idx+1}] 命中 DOM 原生标准答案: {opt_text[:30] or '(选项标签)'}")
                        WebDriverHelper.safe_click(driver, opt)
                        WebDriverHelper.human_like_delay(0.2)
                        solution_selected = True

                # If no direct li has data-solution, check child input/radio/span
                if not solution_selected:
                    for opt in options:
                        inputs = opt.find_elements(By.CSS_SELECTOR, 'input, span, label')
                        for inp in inputs:
                            if inp.get_attribute("data-solution") is not None:
                                self.log(f"   [选择题 {idx+1}] 命中子节点原生答案")
                                WebDriverHelper.safe_click(driver, opt)
                                WebDriverHelper.human_like_delay(0.2)
                                solution_selected = True
                                break
                        if solution_selected:
                            break

                # Fallback: if no data-solution is present at all, select first option
                if not solution_selected and options:
                    self.log(f"   [选择题 {idx+1}] 未发现 data-solution 属性，默认选择第 1 项")
                    WebDriverHelper.safe_click(driver, options[0])
                    WebDriverHelper.human_like_delay(0.2)

                solved_count += 1
            except Exception as e:
                logger.debug("Error solving choice question %d: %s", idx, e)

        return solved_count

    def _solve_objective_fillings(self, driver, scope) -> int:
        """Extract and solve short fill-in inputs using DOM data-solution or result."""
        try:
            # Inputs under div[data-controltype="filling"] or with data-itemtype="input"
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
                # 1. Check data-solution on the input itself
                solution = inp.get_attribute("data-solution")

                # 2. Check sibling or descendant [data-itemtype="result"]
                if not solution:
                    try:
                        parent = inp.find_element(By.XPATH, "..")
                        results = parent.find_elements(By.CSS_SELECTOR, '[data-itemtype="result"]')
                        if results:
                            solution = (results[0].text or "").strip()
                    except Exception:
                        pass

                if solution:
                    # Clean solution: handle multiple accepted answers split by "/"
                    # e.g. "eighteen/18" -> "eighteen"
                    clean_answer = str(solution).split("/")[0].strip()
                    self.log(f"   [客观填空 {idx+1}] 填入 DOM 原生答案: '{clean_answer}'")
                    WebDriverHelper.simulate_typing(driver, inp, clean_answer)
                    WebDriverHelper.human_like_delay(0.2)
                    solved_count += 1
                else:
                    # Fallback to LLM if no native solution found
                    stem_text = ""
                    try:
                        parent = inp.find_element(By.XPATH, "../..")
                        stem_text = (parent.text or "").strip()
                    except Exception:
                        pass
                    if stem_text and self.ai_client.is_available():
                        ans = self.ai_client.solve_subjective_question(stem=stem_text)
                        WebDriverHelper.simulate_typing(driver, inp, ans)
                        WebDriverHelper.human_like_delay(0.2)
                        solved_count += 1
            except Exception as e:
                logger.debug("Error solving filling question %d: %s", idx, e)

        return solved_count

    def _solve_subjective_fillings(self, driver, scope) -> int:
        """Extract and solve subjective open essay / long filling questions using LLM."""
        try:
            containers = scope.find_elements(
                By.CSS_SELECTOR, 'div[data-controltype="fillinglong"]'
            )
        except Exception:
            return 0

        solved_count = 0
        for idx, container in enumerate(containers):
            try:
                # Find input or textarea
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
                    WebDriverHelper.simulate_typing(driver, target_input, clean_ans)
                    WebDriverHelper.human_like_delay(0.2)
                    solved_count += 1
                    continue

                # Extract context for LLM
                direction = ""
                context = ""
                stem = ""

                # Direction / Instructions
                try:
                    dir_els = scope.find_elements(By.CSS_SELECTOR, '.direction, [data-itemtype="direction"], .part_title')
                    if dir_els:
                        direction = (dir_els[0].text or "").strip()
                except Exception:
                    pass

                # Background text / Passage (.white_frame, .passage, .article, etc.)
                try:
                    white_frames = scope.find_elements(By.CSS_SELECTOR, '.white_frame, .passage, .reading_content')
                    if white_frames:
                        context = (white_frames[0].text or "").strip()
                except Exception:
                    pass

                # Stem
                try:
                    stem_els = container.find_elements(By.CSS_SELECTOR, 'span[data-itemtype="stem"], [data-itemtype="stem"]')
                    if stem_els:
                        stem = (stem_els[0].text or "").strip()
                    else:
                        stem = (container.text or "").strip()
                except Exception:
                    stem = (container.text or "").strip()

                self.log(f"   [主观题 {idx+1}] 无固定答案，调用 LLM 综合上下文生成回答...")
                llm_answer = self.ai_client.solve_subjective_question(
                    stem=stem, direction=direction, context=context
                )
                self.log(f"   [主观题 {idx+1}] LLM 答复: '{llm_answer[:40]}...'")
                WebDriverHelper.simulate_typing(driver, target_input, llm_answer)
                WebDriverHelper.human_like_delay(0.3)
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
                # Look for record button or trigger
                triggers = rec.find_elements(
                    By.CSS_SELECTOR, 'button, .btn_record, .record_btn, .btn_play, a'
                )
                if triggers:
                    self.log(f"   [录音/音频题 {idx+1}] 触发录音/播放控件")
                    WebDriverHelper.safe_click(driver, triggers[0])
                    time.sleep(1.0)
                    # If there is a stop button, click it after short pause
                    stop_btns = rec.find_elements(By.CSS_SELECTOR, '.btn_stop, .stop_btn')
                    if stop_btns:
                        WebDriverHelper.safe_click(driver, stop_btns[0])
                handled_count += 1
            except Exception as e:
                logger.debug("Error handling audio record %d: %s", idx, e)

        return handled_count

    def _dwell_and_submit(self, driver, scope) -> None:
        """Keep human-like dwell time and submit to trigger native SCORM sync."""
        dwell_seconds = max(1, int(self.config.min_dwell_seconds))
        self.log(f"   保持真实作答停留时间 ({dwell_seconds} 秒)...")
        time.sleep(dwell_seconds)

        # Locate submit button
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
            WebDriverHelper.safe_click(driver, submit_btn)
            time.sleep(1.0)

            # Accept browser alert if popup appears ("Are you sure to submit?")
            try:
                alert = driver.switch_to.alert
                alert_text = alert.text
                alert.accept()
                self.log(f"   确认提交弹窗: {alert_text}")
            except NoAlertPresentException:
                pass
            except Exception:
                pass

            # Also check for DOM confirmation dialogs (e.g. .dialog_ok, .confirm_btn)
            try:
                confirm_btns = driver.find_elements(By.CSS_SELECTOR, '.btn_confirm, .dialog_ok, .btn_ok')
                for cb in confirm_btns:
                    if cb.is_displayed():
                        WebDriverHelper.safe_click(driver, cb)
                        break
            except Exception:
                pass

            time.sleep(1.5)
            self.log("   已完成页面提交，SCORM 状态已原生上报。")
        else:
            self.log("   未在当前小节中发现提交按钮（可能为纯阅读或自动保存小节）。")
