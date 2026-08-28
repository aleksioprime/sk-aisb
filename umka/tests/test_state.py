"""Тесты общего состояния, публикуемого через веб-интерфейс."""

import unittest

from sorter.models import SortRequest
from sorter.state import StateStore


class StateStoreTests(unittest.TestCase):
    """Проверки связи событий сортировки с обратной связью."""

    def test_feedback_is_accepted_only_once_for_current_event(self):
        stats = {"total_items": 0, "estimated_weight_kg": 0, "by_type": {}, "feedback": {}}
        state = StateStore(stats, "console")
        event_id = state.begin_sort(SortRequest("paper", "section_1", "paper", 0.9))
        self.assertTrue(state.accept_feedback("yes", event_id))
        self.assertFalse(state.accept_feedback("no", event_id))
        self.assertFalse(state.accept_feedback("yes", "another-event"))


if __name__ == "__main__":
    unittest.main()
