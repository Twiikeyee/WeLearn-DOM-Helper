import unittest
from unittest.mock import MagicMock, patch
from question_solver import WeLearnQuestionSolver
from webdriver_helper import WebDriverHelper
from welearn_config import Config


class TestAngularExerciseTypes(unittest.TestCase):
    def setUp(self):
        self.solver = WeLearnQuestionSolver(Config(), log_callback=lambda _: None)
        self.driver = MagicMock()
        self.scope = MagicMock()

    @staticmethod
    def question(option_count):
        q = MagicMock()
        q.is_displayed.return_value = True
        options = [MagicMock() for _ in range(option_count)]
        for option in options:
            option.is_displayed.return_value = True
            option.is_enabled.return_value = True
        q.find_elements.return_value = options
        return q, options

    def test_tof_three_questions_click_native_controls(self):
        rows = [self.question(2) for _ in range(3)]
        states = {id(q): {'key': [key], 'value': []} for (q, _), key in zip(rows, ['t', 'f', 't'])}
        self.scope.find_elements.return_value = [q for q, _ in rows]
        def state(driver, question, component, alias):
            self.assertEqual((component, alias), ('etTof', 'tof'))
            return states[id(question)].copy()
        def click(driver, option):
            for q, options in rows:
                for i, item in enumerate(options):
                    if item is option:
                        states[id(q)]['value'] = [['t', 'f'][i]]
                        return True
            return False
        with patch.object(self.solver, '_et_component_state', side_effect=state), patch.object(WebDriverHelper, 'safe_click', side_effect=click):
            self.assertEqual(self.solver._solve_et_tof(self.driver, self.scope), (3, 3))

    def test_tof_without_key_does_not_click(self):
        q, _ = self.question(2)
        self.scope.find_elements.return_value = [q]
        with patch.object(self.solver, '_et_component_state', return_value=None), patch.object(WebDriverHelper, 'safe_click') as click:
            self.assertEqual(self.solver._solve_et_tof(self.driver, self.scope), (0, 1))
            click.assert_not_called()

    def test_blank_five_answers_commit_and_verify(self):
        rows = [self.question(1) for _ in range(5)]
        states = {id(q): {'key': [f'Answer {i}'], 'value': ''} for i, (q, _) in enumerate(rows)}
        self.scope.find_elements.return_value = [q for q, _ in rows]
        def state(driver, q, component, alias):
            self.assertEqual((component, alias), ('etBlank', 'blank'))
            return states[id(q)].copy()
        def commit(driver, field, answer):
            for q, fields in rows:
                if fields[0] is field:
                    states[id(q)]['value'] = answer
                    return True
            return False
        with patch.object(self.solver, '_et_component_state', side_effect=state), patch.object(self.solver, '_commit_et_blank', side_effect=commit):
            self.assertEqual(self.solver._solve_et_blanks(self.driver, self.scope), (5, 5))

    def test_blank_missing_reference_fails_without_filling(self):
        q, _ = self.question(1)
        self.scope.find_elements.return_value = [q]
        with patch.object(self.solver, '_et_component_state', return_value={'key': [], 'value': ''}), patch.object(self.solver, '_commit_et_blank') as commit:
            self.assertEqual(self.solver._solve_et_blanks(self.driver, self.scope), (0, 1))
            commit.assert_not_called()

    def test_unresolved_types_block_even_if_other_questions_succeeded(self):
        for key in ('et_tof_unresolved', 'et_blank_unresolved'):
            with self.subTest(type=key):
                self.assertFalse(self.solver.can_submit_questions({'choice_count': 1, key: 1}, self.scope))

    def test_tof_counts_as_answered(self):
        self.assertTrue(self.solver.can_submit_questions({'tof_count': 3}, self.scope))


if __name__ == '__main__':
    unittest.main()
