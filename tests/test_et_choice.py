import unittest
from unittest.mock import MagicMock, patch
from question_solver import WeLearnQuestionSolver
from webdriver_helper import WebDriverHelper
from welearn_config import Config


class TestEtChoice(unittest.TestCase):
    def setUp(self):
        self.messages = []
        self.solver = WeLearnQuestionSolver(Config(min_dwell_seconds=0), log_callback=self.messages.append)
        self.driver = MagicMock()
        self.scope = MagicMock()

    def choice(self, key, selected=()):
        choice = MagicMock()
        choice.is_displayed.return_value = True
        options = [MagicMock() for _ in range(4)]
        choice.find_elements.return_value = options
        state = {'key': list(key), 'value': list(selected)}
        return choice, options, state

    def test_four_angular_choices_read_state_and_click_options(self):
        rows = [self.choice([1]), self.choice([3]), self.choice([2]), self.choice([0])]
        self.scope.find_elements.side_effect = lambda by, selector: [r[0] for r in rows] if selector == 'et-choice' else []
        states = {id(row[0]): row[2] for row in rows}
        def read(driver, choice):
            return dict(states[id(choice)])
        def click(driver, option):
            for _, options, state in rows:
                for index, candidate in enumerate(options):
                    if candidate is option:
                        state['value'] = [index]
                        return True
            return False
        with patch.object(self.solver, '_et_choice_state', side_effect=read), patch.object(WebDriverHelper, 'safe_click', side_effect=click):
            solved, total = self.solver._solve_et_choices(self.driver, self.scope)
        self.assertEqual((solved, total), (4, 4))
        self.assertEqual([r[2]['value'] for r in rows], [[1], [3], [2], [0]])

    def test_missing_key_prevents_partial_clicks(self):
        first = self.choice([1])
        second = self.choice([])
        rows = [first, second]
        self.scope.find_elements.return_value = [r[0] for r in rows]
        with patch.object(self.solver, '_et_choice_state', side_effect=[first[2], None]), patch.object(WebDriverHelper, 'safe_click') as click:
            self.assertEqual(self.solver._solve_et_choices(self.driver, self.scope), (0, 2))
            click.assert_not_called()

    def test_zero_answers_with_submit_is_blocked(self):
        with patch.object(self.solver, 'find_submit_button', return_value=MagicMock()):
            self.assertFalse(self.solver.can_submit_questions({}, self.scope))

    def test_unresolved_choice_blocks_submission(self):
        self.assertFalse(self.solver.can_submit_questions({'choice_count': 3, 'et_choice_unresolved': 1}, self.scope))

    def test_reading_without_submit_remains_allowed(self):
        with patch.object(self.solver, 'find_submit_button', return_value=None):
            self.assertTrue(self.solver.can_submit_questions({}, self.scope))

    def test_selection_failure_is_reported_unresolved(self):
        choice, options, state = self.choice([1])
        self.scope.find_elements.return_value = [choice]
        with patch.object(self.solver, '_et_choice_state', return_value=state), patch.object(WebDriverHelper, 'safe_click', return_value=False):
            self.assertEqual(self.solver._solve_et_choices(self.driver, self.scope), (0, 1))

    def test_no_answers_does_not_click_submit(self):
        stats = {'choice_count': 0, 'filling_count': 0, 'subjective_count': 0, 'record_count': 0, 'elapsed_solving': 0}
        with patch.object(self.solver, 'fill_sco_questions', return_value=stats), \
             patch.object(self.solver, 'locate_sco_scope', return_value=self.scope), \
             patch.object(self.solver, 'find_submit_button', return_value=MagicMock()), \
             patch.object(self.solver, 'submit_sco_in_scope') as submit:
            self.assertFalse(self.solver.solve_sco(self.driver, 'exercise'))
            submit.assert_not_called()

    def test_filled_choice_does_not_toggle_again(self):
        choice, options, state = self.choice([1], [1])
        self.scope.find_elements.return_value = [choice]
        with patch.object(self.solver, '_et_choice_state', return_value=state), patch.object(WebDriverHelper, 'safe_click') as click:
            self.assertEqual(self.solver._solve_et_choices(self.driver, self.scope), (1, 1))
            click.assert_not_called()


if __name__ == '__main__':
    unittest.main()
