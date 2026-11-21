import unittest
from unittest.mock import MagicMock

from question_solver import WeLearnQuestionSolver


class SubmitButtonTests(unittest.TestCase):
    @staticmethod
    def element(text='', displayed=True, value=None):
        element = MagicMock()
        element.text = text
        element.is_displayed.return_value = displayed
        element.is_enabled.return_value = True
        element.get_attribute.side_effect = lambda name: value if name == 'value' else None
        return element

    def test_finds_visible_submit_text(self):
        hidden = self.element('Submit', displayed=False)
        visible = self.element(' Submit ')
        scope = MagicMock()
        scope.find_elements.side_effect = lambda by, sel: [hidden, visible] if sel.startswith('button, input') else []
        self.assertIs(WeLearnQuestionSolver.find_submit_button(scope), visible)

    def test_finds_submit_input_value(self):
        button = self.element(value='Submit')
        scope = MagicMock()
        scope.find_elements.side_effect = lambda by, sel: [button] if sel.startswith('button, input') else []
        self.assertIs(WeLearnQuestionSolver.find_submit_button(scope), button)

    def test_retains_existing_selector_priority(self):
        button = self.element('Original')
        scope = MagicMock()
        scope.find_elements.side_effect = lambda by, sel: [button] if sel == '[data-controltype="submit"]' else []
        self.assertIs(WeLearnQuestionSolver.find_submit_button(scope), button)

    def test_prefers_interactive_button_over_div_wrapper(self):
        wrapper_div = self.element('Submit')
        button = self.element('Submit')
        scope = MagicMock()
        def find(by, sel):
            if sel.startswith('button, input'):
                return [button]
            if sel == 'div, span':
                return [wrapper_div]
            return []
        scope.find_elements.side_effect = find
        self.assertIs(WeLearnQuestionSolver.find_submit_button(scope), button)


if __name__ == '__main__':
    unittest.main()
