# -*- coding: utf-8 -*-
"""
Unit tests for WeLearn-DOM-Helper components.
"""

import json
import os
import queue
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from ai_client import OpenAICompatibleClient
from question_solver import WeLearnQuestionSolver
from webdriver_helper import WebDriverHelper
from welearn_api import WeLearnAPI, WeLearnCourse, WeLearnSCO, WeLearnUnit
from welearn_bot import DurationPlanner, WeLearnBot
from welearn_config import Config
from welearn_player import WeLearnFrameContext, WeLearnPlayer
import config_editor


class TestConfig(unittest.TestCase):
    def test_default_config(self):
        cfg = Config()
        self.assertEqual(cfg.browser, "edge")
        self.assertEqual(cfg.min_dwell_seconds, 0)
        self.assertEqual(cfg.typing_mode, "fast")
        self.assertFalse(cfg.enable_llm_subjective)
        self.assertTrue(len(cfg.subjective_default_text) > 0)

    def test_save_and_load_config(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            temp_path = f.name

        try:
            cfg = Config(
                username="test_user",
                password="test_password",
                typing_mode="simulate",
                min_dwell_seconds=3,
                enable_llm_subjective=True,
                api_key="sk-testkey123",
            )
            cfg.save_json(temp_path)

            loaded = Config.from_json(temp_path)
            self.assertEqual(loaded.username, "test_user")
            self.assertEqual(loaded.password, "test_password")
            self.assertEqual(loaded.typing_mode, "simulate")
            self.assertEqual(loaded.min_dwell_seconds, 3)
            self.assertTrue(loaded.enable_llm_subjective)
            self.assertEqual(loaded.api_key, "sk-testkey123")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)


class TestWeLearnAPI(unittest.TestCase):
    def test_get_course_ids_regex(self):
        mock_html = '''
        <html>
        <script>
            var user_info = {"uid": 1234567, "classid": "cls-987654321"};
        </script>
        </html>
        '''
        mock_driver = MagicMock()
        mock_driver.current_url = "https://welearn.sflep.com/student/course_info.aspx?cid=4395"
        mock_driver.page_source = mock_html

        uid, classid = WeLearnAPI.get_course_ids(mock_driver, "4395")
        self.assertEqual(uid, "1234567")
        self.assertEqual(classid, "cls-987654321")

    def test_course_dataclass(self):
        course = WeLearnCourse(cid="4395", name="英语综合教程 1", progress="25%")
        self.assertEqual(course.cid, "4395")
        self.assertEqual(course.name, "英语综合教程 1")
        self.assertEqual(course.progress, "25%")

    def test_normalize_cdn_addr(self):
        raw = "//centercourseware.sflep.com/Course/unit_01/main8.html?m-1-1-8|B1U1 > Task 3"
        self.assertEqual(
            WeLearnAPI.normalize_cdn_addr(raw),
            "https://centercourseware.sflep.com/Course/unit_01/main8.html?m-1-1-8",
        )


class TestWeLearnPlayer(unittest.TestCase):
    def test_is_shell_page(self):
        mock_driver = MagicMock()
        mock_driver.current_url = "https://welearn.sflep.com/student/StudyCourse.aspx?cid=4395&classid=123&sco=m-1-1-1"
        self.assertTrue(WeLearnPlayer.is_shell_page(mock_driver))

        mock_driver.current_url = "https://welearn.sflep.com/2019/student/index.aspx"
        self.assertFalse(WeLearnPlayer.is_shell_page(mock_driver))

    def test_get_current_scoid(self):
        mock_driver = MagicMock()
        mock_driver.current_url = "https://welearn.sflep.com/student/StudyCourse.aspx?cid=4395&classid=123&sco=m-1-1-1"
        self.assertEqual(WeLearnPlayer.get_current_scoid(mock_driver), "m-1-1-1")

    def test_frame_context_manager(self):
        mock_driver = MagicMock()
        mock_frame = MagicMock()
        with patch.object(WeLearnPlayer, "find_content_frame", return_value=mock_frame):
            with WeLearnFrameContext(mock_driver) as ctx:
                self.assertTrue(ctx.entered)
                mock_driver.switch_to.frame.assert_called_with(mock_frame)
            mock_driver.switch_to.default_content.assert_called()


class TestQuestionSolver(unittest.TestCase):
    def setUp(self):
        self.cfg = Config(min_dwell_seconds=0, typing_mode="fast", enable_llm_subjective=False)
        self.mock_ai = MagicMock(spec=OpenAICompatibleClient)
        self.mock_ai.is_available.return_value = True
        self.mock_ai.solve_subjective_question.return_value = "Generated subjective answer"
        self.solver = WeLearnQuestionSolver(config=self.cfg, ai_client=self.mock_ai)

    def test_solve_choices_dom_native(self):
        mock_driver = MagicMock()
        mock_scope = MagicMock()

        mock_container = MagicMock()
        mock_opt1 = MagicMock()
        mock_opt1.get_attribute.return_value = None

        mock_opt2 = MagicMock()
        mock_opt2.get_attribute.side_effect = lambda attr: "" if attr == "data-solution" else None
        mock_opt2.text = "Option B"

        mock_container.find_elements.return_value = [mock_opt1, mock_opt2]
        mock_scope.find_elements.return_value = [mock_container]

        with patch.object(WebDriverHelper, "safe_click") as mock_click:
            count = self.solver._solve_choices(mock_driver, mock_scope)
            self.assertEqual(count, 1)
            mock_click.assert_called_with(mock_driver, mock_opt2)

    def test_solve_objective_fillings_fast_fill(self):
        mock_driver = MagicMock()
        mock_scope = MagicMock()

        mock_inp = MagicMock()
        mock_inp.get_attribute.side_effect = lambda attr: "eighteen/18" if attr == "data-solution" else None
        mock_scope.find_elements.return_value = [mock_inp]

        with patch.object(WebDriverHelper, "fast_fill") as mock_fast:
            count = self.solver._solve_objective_fillings(mock_driver, mock_scope)
            self.assertEqual(count, 1)
            mock_fast.assert_called_with(mock_driver, mock_inp, "eighteen")

    def test_solve_subjective_zero_token_mode(self):
        mock_driver = MagicMock()
        mock_scope = MagicMock()

        mock_container = MagicMock()
        mock_textarea = MagicMock()
        mock_textarea.get_attribute.return_value = None
        mock_container.get_attribute.return_value = None
        mock_container.find_elements.return_value = [mock_textarea]

        mock_scope.find_elements.return_value = [mock_container]

        with patch.object(WebDriverHelper, "fast_fill") as mock_fast:
            # When enable_llm_subjective is False, it should NOT call AI client!
            count = self.solver._solve_subjective_fillings(mock_driver, mock_scope)
            self.assertEqual(count, 1)
            self.mock_ai.solve_subjective_question.assert_not_called()
            mock_fast.assert_called_with(mock_driver, mock_textarea, self.cfg.subjective_default_text)

    def test_solve_subjective_llm_mode(self):
        mock_driver = MagicMock()
        mock_scope = MagicMock()

        self.solver.config.enable_llm_subjective = True

        mock_container = MagicMock()
        mock_textarea = MagicMock()
        mock_textarea.get_attribute.return_value = None
        mock_container.get_attribute.return_value = None
        mock_container.find_elements.return_value = [mock_textarea]

        mock_scope.find_elements.return_value = [mock_container]

        with patch.object(WebDriverHelper, "fast_fill") as mock_fast:
            count = self.solver._solve_subjective_fillings(mock_driver, mock_scope)
            self.assertEqual(count, 1)
            self.mock_ai.solve_subjective_question.assert_called()
            mock_fast.assert_called_with(mock_driver, mock_textarea, "Generated subjective answer")


class TestConfigEditor(unittest.TestCase):
    def test_default_config_types(self):
        d = config_editor.DEFAULT_CONFIG
        self.assertIsInstance(d["enable_llm_subjective"], bool)
        self.assertFalse(d["enable_llm_subjective"])
        self.assertIsInstance(d["headless"], bool)
        self.assertIsInstance(d["debug_mode"], bool)
        self.assertIsInstance(d["min_dwell_seconds"], int)
        self.assertEqual(d["concurrency_mode"], "serial")
        self.assertEqual(d["target_total_seconds"], 0)
        self.assertEqual(d["max_concurrent_tabs"], 3)


class TestDurationPlanner(unittest.TestCase):
    def test_parse_learntime(self):
        self.assertEqual(DurationPlanner.parse_learntime_seconds("00:05:12"), 312)
        self.assertEqual(DurationPlanner.parse_learntime_seconds("01:00:00"), 3600)
        self.assertEqual(DurationPlanner.parse_learntime_seconds("03:20"), 200)
        self.assertEqual(DurationPlanner.parse_learntime_seconds("45"), 45)
        self.assertEqual(DurationPlanner.parse_learntime_seconds(""), 0)

    def test_plan_dwell_allocations_deducts_learned_and_matches_sum(self):
        tabs = [
            {"scoid": "m-1-1-1", "learntime": "00:01:00"},  # 60s
            {"scoid": "m-1-1-2", "learntime": "00:00:40"},  # 40s
            {"scoid": "m-1-1-3", "learntime": "00:00:00"},  # 0s
            {"scoid": "m-1-1-4", "learntime": "00:00:20"},  # 20s
        ]
        # Already learned = 120s. Target = 300s -> Net needed = 180s
        allocs, summary = DurationPlanner.plan_dwell_allocations(
            selected_tabs=tabs, target_total_seconds=300, min_dwell_seconds=0
        )
        self.assertEqual(len(allocs), 4)
        self.assertEqual(summary["already_learned_seconds"], 120)
        self.assertEqual(summary["net_needed_seconds"], 180)
        self.assertEqual(sum(allocs), 180)
        self.assertTrue(all(a > 0 for a in allocs))

    def test_plan_dwell_allocations_already_satisfied(self):
        tabs = [
            {"scoid": "m-1-1-1", "learntime": "00:10:00"},
            {"scoid": "m-1-1-2", "learntime": "00:10:00"},
        ]
        allocs, summary = DurationPlanner.plan_dwell_allocations(
            selected_tabs=tabs, target_total_seconds=600, min_dwell_seconds=0
        )
        self.assertEqual(summary["net_needed_seconds"], 0)
        self.assertEqual(allocs, [0, 0])


class TestConcurrencyModes(unittest.TestCase):
    def _make_mock_driver(self):
        driver = MagicMock()
        driver.current_window_handle = "tab_1"
        handles = ["tab_1"]

        def open_new_tab(kind="tab"):
            new_h = f"tab_{len(handles) + 1}"
            handles.append(new_h)
            driver.current_window_handle = new_h

        def switch_win(h):
            driver.current_window_handle = h

        def close_win():
            if driver.current_window_handle in handles and len(handles) > 1:
                handles.remove(driver.current_window_handle)
                driver.current_window_handle = handles[0]

        driver.switch_to.new_window.side_effect = open_new_tab
        driver.switch_to.window.side_effect = switch_win
        driver.close.side_effect = close_win
        type(driver).window_handles = property(lambda self_d: list(handles))
        return driver

    def test_pipeline_mode_preserves_submission_order(self):
        cfg = Config(
            concurrency_mode="pipeline",
            target_total_seconds=2,
            max_concurrent_tabs=3,
            min_dwell_seconds=0,
        )
        log_q = queue.Queue()
        bot = WeLearnBot(cfg, log_q)
        bot.driver = self._make_mock_driver()

        submitted_order = []
        filled_order = []

        def fake_fill(drv, scoid):
            filled_order.append(scoid)
            return {
                "scoid": scoid,
                "choice_count": 1,
                "filling_count": 0,
                "subjective_count": 0,
                "record_count": 0,
                "elapsed_solving": 0.05,
                "is_voice_only": False,
            }

        def fake_submit(drv, scoid):
            submitted_order.append(scoid)
            return True

        bot.solver.fill_sco_questions = MagicMock(side_effect=fake_fill)
        bot.solver.submit_sco = MagicMock(side_effect=fake_submit)

        tabs = [
            {"scoid": "m-1-1-1", "l1_title": "Sec 1", "learntime": "00:00:00", "status": "not_started"},
            {"scoid": "m-1-1-2", "l1_title": "Sec 2", "learntime": "00:00:00", "status": "not_started"},
            {"scoid": "m-1-1-3", "l1_title": "Sec 3", "learntime": "00:00:00", "status": "not_started"},
        ]

        with patch.object(WeLearnPlayer, "navigate_to_sco", return_value=True), patch.object(
            WeLearnFrameContext, "enter", return_value=True
        ):
            bot.process_selected_tabs(tabs)

        # Must launch and submit strictly in 1 -> 2 -> 3 order
        self.assertEqual(filled_order, ["m-1-1-1", "m-1-1-2", "m-1-1-3"])
        self.assertEqual(submitted_order, ["m-1-1-1", "m-1-1-2", "m-1-1-3"])
        self.assertTrue(all(t["status"] == "done" for t in tabs))

    def test_decoupled_mode_single_submit_and_concurrent_dwell(self):
        cfg = Config(
            concurrency_mode="decoupled",
            target_total_seconds=2,
            max_concurrent_tabs=2,
            min_dwell_seconds=0,
        )
        log_q = queue.Queue()
        bot = WeLearnBot(cfg, log_q)
        bot.driver = self._make_mock_driver()

        solve_calls = []

        def fake_solve(drv, scoid, dwell_seconds=None, skip_submit=False):
            solve_calls.append(scoid)
            return True

        bot.solver.solve_sco = MagicMock(side_effect=fake_solve)

        tabs = [
            {"scoid": "m-1-1-1", "l1_title": "Sec 1", "learntime": "00:00:00", "status": "not_started"},
            {"scoid": "m-1-1-2", "l1_title": "Sec 2", "learntime": "00:00:00", "status": "done"},
        ]

        with patch.object(WeLearnPlayer, "navigate_to_sco", return_value=True), patch.object(
            WeLearnFrameContext, "enter", return_value=True
        ):
            bot.process_selected_tabs(tabs)

        # Only undone task m-1-1-1 is solved in Phase 1; done task m-1-1-2 only dwells in Phase 2
        self.assertEqual(solve_calls, ["m-1-1-1"])
        self.assertTrue(all(t["status"] == "done" for t in tabs))


if __name__ == "__main__":
    unittest.main()
