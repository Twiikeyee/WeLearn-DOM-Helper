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
        """Dispatch text input according to typing_mode (fast vs simulate) and sync jQuery values."""
        mode = getattr(self.config, "typing_mode", "fast").lower()
        is_readonly = bool(element.get_attribute("readonly") or element.get_attribute("data-alwaysreadonly"))
        if mode == "simulate" and not is_readonly:
            WebDriverHelper.simulate_typing(driver, element, text)
        else:
            WebDriverHelper.fast_fill(driver, element, text)

        # Sync WeLearn jQuery values and myresult display if present
        try:
            driver.execute_script(
                """
                var el = arguments[0];
                var val = arguments[1];
                var $ = window.jQuery || window.$;
                if ($) {
                    var $parent = $(el).closest('[data-controltype]');
                    if ($parent.length > 0 && typeof $parent.values === 'function') {
                        $parent.values(val);
                    }
                    var $myres = $parent.find('[data-itemtype="myresult"]');
                    if ($myres.length > 0) {
                        $myres.text(val);
                    }
                }
                """,
                element,
                str(text),
            )
        except Exception:
            pass

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
        et_solved, et_total = self._solve_et_choices(driver, scope)
        choice_count += et_solved
        tof_solved, tof_total = self._solve_et_tof(driver, scope)

        # Step 2: Solve Banked Cloze / ChooseBox (.ChooseBox, [data-choosebox])
        choosebox_count = self._solve_choosebox_fillings(driver, scope)

        # Step 3: Solve Objective Short Fill-in (div[data-controltype="filling"])
        filling_count = self._solve_objective_fillings(driver, scope) + choosebox_count
        blank_solved, blank_total = self._solve_et_blanks(driver, scope)
        filling_count += blank_solved

        # Step 4: Solve Subjective Long Fill-in / Open Essay (div[data-controltype="fillinglong"])
        subjective_count = self._solve_subjective_fillings(driver, scope)

        # Step 5: Handle Audio / Record elements
        record_count = self._handle_audio_records(driver, scope)

        elapsed_solving = time.time() - start_time
        is_voice_only = (record_count > 0) and (choice_count + tof_solved + filling_count + subjective_count == 0)
        self.log(
            f"   作答统计: 选择 {choice_count} 道, 判断 {tof_solved} 道, 填空 {filling_count} 道, "
            f"主观题 {subjective_count} 道, 语音/录音 {record_count} 道 (耗时 {elapsed_solving:.1f} 秒)"
        )
        if is_voice_only:
            self.log(f"   提示: SCO [{scoid}] 为纯语音/口语录音题，若平台限制网页提交将仅累计学习时长。")

        return {
            "scoid": scoid,
            "choice_count": choice_count,
            "et_choice_total": et_total,
            "et_choice_unresolved": et_total - et_solved,
            "tof_count": tof_solved,
            "et_tof_unresolved": tof_total - tof_solved,
            "et_blank_unresolved": blank_total - blank_solved,
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

        # Do not submit a question page when parsing failed or only some ET choices were filled.
        if not skip_submit and not self.can_submit_questions(stats, scope):
            return False

        # Step 5: Dynamic dwell time and submission
        self._dwell_and_submit(
            driver,
            scope,
            elapsed_time=elapsed_solving,
            target_dwell_override=dwell_seconds,
            skip_submit=skip_submit,
        )
        return True

    @staticmethod
    def _et_choice_state(driver, element):
        """Read the Angular component state after it removes the original key attribute."""
        return driver.execute_script("""
            var element = arguments[0];
            if (!window.angular) return null;
            var wrapped = window.angular.element(element);
            var ctrl = wrapped.controller('etChoice');
            if (!ctrl) {
                var scope = wrapped.isolateScope && wrapped.isolateScope();
                ctrl = scope && scope.choice;
            }
            if (!ctrl || !ctrl.hasKey || !Array.isArray(ctrl.key) || !Array.isArray(ctrl.value)) return null;
            return {key: ctrl.key.slice(), value: ctrl.value.slice()};
        """, element)

    def _solve_et_choices(self, driver, scope):
        """Solve Angular et-choice controls using their component's native answer key."""
        try:
            choices = [el for el in scope.find_elements(By.CSS_SELECTOR, 'et-choice') if el.is_displayed()]
        except Exception as e:
            logger.debug("Error finding et-choice questions: %s", e)
            self.log("   无法检查课件题目，已停止自动提交。")
            return 0, 1
        if not choices:
            return 0, 0

        # First validate every key so a missing answer does not lead to a partial submission.
        plan = []
        for number, choice in enumerate(choices, 1):
            try:
                options = choice.find_elements(By.CSS_SELECTOR, 'ol > li, ul > li')
                if not options:
                    options = choice.find_elements(By.CSS_SELECTOR, ':scope > .wrapper > span')
                state = self._et_choice_state(driver, choice)
                if not isinstance(state, dict):
                    raise ValueError("页面组件没有提供答案")
                key, selected = state.get('key'), state.get('value')
                if (not isinstance(key, list) or not key or not isinstance(selected, list)
                        or any(type(i) is not int or i < 0 or i >= len(options) for i in key + selected)
                        or len(set(key)) != len(key)):
                    raise ValueError("答案格式与选项不匹配")
                plan.append((number, choice, options, set(key), set(selected)))
            except Exception as e:
                self.log(f"   [选择题 {number}] 无法读取课件组件答案: {e}；已停止自动提交。")
                return 0, len(choices)

        solved = 0
        for number, choice, options, key, selected in plan:
            try:
                # Normal option clicks preserve the courseware's own Angular events.
                for index in sorted(selected - key):
                    if not WebDriverHelper.safe_click(driver, options[index]):
                        raise RuntimeError("取消选项失败")
                for index in sorted(key - selected):
                    if not WebDriverHelper.safe_click(driver, options[index]):
                        raise RuntimeError("点击选项失败")
                state = self._et_choice_state(driver, choice)
                if not isinstance(state, dict) or set(state.get('value', [])) != key:
                    raise RuntimeError("页面未确认选中状态")
                self.log(f"   [选择题 {number}] 已按课件组件答案选中 {', '.join(chr(65 + i) for i in sorted(key))}")
                solved += 1
            except Exception as e:
                self.log(f"   [选择题 {number}] 作答失败: {e}；已停止自动提交。")
        return solved, len(choices)

    @staticmethod
    def _et_component_state(driver, element, component, alias):
        return driver.execute_script("""
            var element = arguments[0], component = arguments[1], alias = arguments[2];
            if (!window.angular) return null;
            var wrapped = window.angular.element(element);
            var ctrl = wrapped.controller(component);
            if (!ctrl) {
                var scope = wrapped.isolateScope && wrapped.isolateScope();
                ctrl = scope && scope[alias];
            }
            if (!ctrl || !ctrl.hasKey || !Array.isArray(ctrl.key)) return null;
            return {key: ctrl.key.slice(), value: Array.isArray(ctrl.value) ? ctrl.value.slice() : ctrl.value};
        """, element, component, alias)

    def _solve_et_tof(self, driver, scope):
        try:
            questions = [el for el in scope.find_elements(By.CSS_SELECTOR, 'et-tof') if el.is_displayed()]
        except Exception as e:
            logger.debug("Error finding et-tof questions: %s", e)
            self.log("   无法检查课件题目，已停止自动提交。")
            return 0, 1
        plan = []
        for number, question in enumerate(questions, 1):
            try:
                state = self._et_component_state(driver, question, 'etTof', 'tof')
                options = question.find_elements(By.CSS_SELECTOR, 'span.controls > span')
                if (not isinstance(state, dict) or len(options) != 2
                        or not isinstance(state.get('key'), list) or len(state['key']) != 1
                        or state['key'][0] not in ('t', 'f')
                        or not isinstance(state.get('value'), list)):
                    raise ValueError("判断题答案或选项不可用")
                plan.append((number, question, options, state['key'][0], state['value']))
            except Exception as e:
                self.log(f"   [判断题 {number}] 无法读取课件组件答案: {e}；已停止自动提交。")
                return 0, len(questions)
        solved = 0
        for number, question, options, key, selected in plan:
            try:
                if selected != [key] and not WebDriverHelper.safe_click(driver, options[0 if key == 't' else 1]):
                    raise RuntimeError("点击选项失败")
                state = self._et_component_state(driver, question, 'etTof', 'tof')
                if not isinstance(state, dict) or state.get('value') != [key]:
                    raise RuntimeError("页面未确认选中状态")
                self.log(f"   [判断题 {number}] 已按课件组件答案选中 {key.upper()}")
                solved += 1
            except Exception as e:
                self.log(f"   [判断题 {number}] 作答失败: {e}；已停止自动提交。")
        return solved, len(questions)

    @staticmethod
    def _commit_et_blank(driver, input_element, answer):
        """Write and commit via Angular ngModel, including its debounced textarea model."""
        return driver.execute_script("""
            var el = arguments[0], value = arguments[1];
            if (!window.angular) return false;
            var wrapped = window.angular.element(el);
            var model = wrapped.controller('ngModel');
            var scope = wrapped.scope();
            if (!scope && wrapped.injector()) scope = wrapped.injector().get('$rootScope');
            if (!model || !scope) return false;
            var commit = function() {
                model.$setViewValue(value);
                model.$commitViewValue();
                model.$render();
            };
            if (scope.$root.$$phase) commit(); else scope.$apply(commit);
            return true;
        """, input_element, answer)

    def _solve_et_blanks(self, driver, scope):
        try:
            questions = [el for el in scope.find_elements(By.CSS_SELECTOR, 'et-blank') if el.is_displayed()]
        except Exception as e:
            logger.debug("Error finding et-blank questions: %s", e)
            self.log("   无法检查课件题目，已停止自动提交。")
            return 0, 1
        plan = []
        for number, question in enumerate(questions, 1):
            try:
                state = self._et_component_state(driver, question, 'etBlank', 'blank')
                fields = question.find_elements(By.CSS_SELECTOR, 'textarea.blank, input.blank, [contenteditable].blank')
                fields = [field for field in fields if field.is_displayed() and field.is_enabled()]
                keys = state.get('key') if isinstance(state, dict) else None
                if not fields or not isinstance(keys, list):
                    raise ValueError("未找到可编辑输入框或组件答案")
                answer = next((key.strip() for key in keys if isinstance(key, str) and key.strip()), None)
                if not answer:
                    raise ValueError("组件没有提供参考答案")
                plan.append((number, question, fields[0], answer))
            except Exception as e:
                self.log(f"   [问答题 {number}] 无法读取课件组件答案: {e}；已停止自动提交。")
                return 0, len(questions)
        solved = 0
        for number, question, field, answer in plan:
            try:
                if not self._commit_et_blank(driver, field, answer):
                    raise RuntimeError("无法同步 Angular 输入状态")
                state = self._et_component_state(driver, question, 'etBlank', 'blank')
                if not isinstance(state, dict) or state.get('value') != answer:
                    raise RuntimeError("页面未确认填写状态")
                self.log(f"   [问答题 {number}] 已填入课件组件中的参考答案")
                solved += 1
            except Exception as e:
                self.log(f"   [问答题 {number}] 作答失败: {e}；已停止自动提交。")
        return solved, len(questions)

    def can_submit_questions(self, stats, scope):
        if any(stats.get(k, 0) for k in ('et_choice_unresolved', 'et_tof_unresolved', 'et_blank_unresolved')):
            self.log("   课件题目未全部完成，已停止自动提交。")
            return False
        answered = sum(stats.get(k, 0) for k in ('choice_count', 'tof_count', 'filling_count', 'subjective_count', 'record_count'))
        if answered == 0 and self.find_submit_button(scope):
            self.log("   检测到提交按钮但未识别到题目，已停止自动提交，请检查课件结构。")
            return False
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

    def _solve_choosebox_fillings(self, driver, scope) -> int:
        """Extract and solve banked cloze (选词填空) within ChooseBox containers."""
        try:
            script = """
            var scope = arguments[0];
            var $ = window.jQuery || window.$;
            if (!$) return [];

            var $scope = $(scope);
            var $boxes = $scope.find('.ChooseBox, [data-choosebox]');
            if ($boxes.length === 0) {
                var $hasMyRes = $scope.find('div[data-controltype="filling"]').filter(function() {
                    return $(this).find('[data-itemtype="myresult"]').length > 0 ||
                           $(this).find('input[data-alwaysreadonly]').length > 0;
                });
                if ($hasMyRes.length > 0) {
                    $boxes = $scope;
                }
            }
            if ($boxes.length === 0) return [];

            var results = [];
            // Clear unsubmitChecked in answer sheet
            $scope.find('.ChooseSheet_cell li').removeClass('unsubmitChecked');

            $boxes.find('div[data-controltype="filling"]').each(function() {
                var $t = $(this);
                // Mark this element so ordinary fill doesn't overwrite it
                $t.attr('data-processed-by-helper', 'true');
                $t.find('input').attr('data-processed-by-helper', 'true');

                var sol = $t.find('[data-solution]').attr('data-solution') ||
                          $t.attr('data-solution');
                if (!sol) {
                    var $res = $t.find('[data-itemtype="result"]');
                    if ($res.length > 0) sol = $res.text();
                }

                if (sol) {
                    sol = $.trim(sol.split('/')[0]);

                    // 1. Invoke WeLearn's jQuery plugin values() method
                    if (typeof $t.values === 'function') {
                        $t.values(sol);
                    }

                    // 2. Set input value and dispatch events
                    var $inp = $t.find('input');
                    if ($inp.length > 0) {
                        $inp.val(sol).trigger('change').trigger('input');
                    }

                    // 3. Set visible myresult text
                    var $myres = $t.find('[data-itemtype="myresult"]');
                    if ($myres.length > 0) {
                        $myres.text(sol);
                    }

                    // 4. Mark corresponding word in AnswerSheet
                    $scope.find('.ChooseSheet_cell li').each(function() {
                        var txt = $.trim($(this).text()).toLowerCase();
                        if (txt === sol.toLowerCase()) {
                            $(this).addClass('unsubmitChecked');
                        }
                    });

                    results.push(sol);
                }
            });
            return results;
            """
            solved_answers = driver.execute_script(script, scope)
            if solved_answers:
                for idx, ans in enumerate(solved_answers):
                    self.log(f"   [选词填空 {idx+1}] 命中并填入 DOM 原生答案: '{ans}'")
                return len(solved_answers)
        except Exception as e:
            logger.debug("Error solving choosebox fillings: %s", e)
        return 0

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
                # Skip if already processed by ChooseBox solver or readonly
                if inp.get_attribute("data-processed-by-helper") or inp.get_attribute("data-alwaysreadonly"):
                    continue
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

    @staticmethod
    def find_submit_button(scope):
        # Prefer known courseware controls, then match visible button labels.
        submit_selectors = (
            '[data-controltype="submit"]', 'et-button[action="item.submit()"] button',
            '.cmd_submit', '.btn_submit', '#btn_submit',
        )
        submit_btn = None
        for sel in submit_selectors:
            try:
                buttons = scope.find_elements(By.CSS_SELECTOR, sel)
                visible = [button for button in buttons if button.is_displayed()]
                if visible:
                    submit_btn = visible[0]
                    break
                if buttons:
                    submit_btn = buttons[0]
                    break
            except Exception:
                continue

        if not submit_btn:
            try:
                candidates = scope.find_elements(
                    By.CSS_SELECTOR, 'button, input[type="submit"], input[type="button"], a, [role="button"], div, span'
                )
                for button in candidates:
                    if not button.is_displayed() or not button.is_enabled():
                        continue
                    labels = (button.text, button.get_attribute("value"),
                              button.get_attribute("aria-label"), button.get_attribute("title"))
                    if any(re.sub(r"\s+", " ", str(label or "")).strip().casefold()
                           in {"submit", "提交", "提交答案"} for label in labels):
                        submit_btn = button
                        break
            except Exception as e:
                logger.debug("Error finding submit button by label: %s", e)

        return submit_btn

    def submit_sco_in_scope(self, driver, scope) -> bool:
        """Click submit button inside the given scope and confirm dialogs safely."""
        try:
            # Prepare submit buttons: unhide, unlock re-submission & auto-confirm LayUI
            driver.execute_script("""
            var sc = arguments[0];
            var $ = window.jQuery || window.$;
            if ($) {
                var $sc = $(sc);
                var $btns = $sc.find('[data-controltype="submit"], [data-controltype="mirrorcmd"], .cmd_submit');
                $btns.each(function() {
                    $(this).removeAttr('data-submitted');
                    $(this).attr('data-submittednotlock', '');
                    $(this).attr('data-ignoresubmitcheck', '');
                    $(this).show();
                });
            }
            window.confirmEx = function(title, defaultTitle, yesF, noF) {
                if (yesF) yesF();
            };
            window.CONFIRM_AUTO_CALL = [{title: "", action: true}];
            """, scope)
        except Exception:
            pass

        submit_btn = self.find_submit_button(scope)

        if submit_btn:
            self.log("   点击当前小节的提交按钮...")
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
            self.log("   已点击提交按钮，请在平台检查完成状态。")
            return True
        else:
            self.log("   未在当前小节中发现提交按钮（可能为纯阅读、自动保存或受限语音小节）。")
            return False
