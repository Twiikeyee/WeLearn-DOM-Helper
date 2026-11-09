# -*- coding: utf-8 -*-
"""
Unit tests for WeLearn-DOM-Helper components.
"""

import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from ai_client import OpenAICompatibleClient
from question_solver import WeLearnQuestionSolver
from webdriver_helper import WebDriverHelper
from welearn_api import WeLearnAPI, WeLearnCourse, WeLearnSCO, WeLearnUnit
from welearn_config import Config
from welearn_player import WeLearnFrameContext, WeLearnPlayer


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


if __name__ == "__main__":
    unittest.main()
