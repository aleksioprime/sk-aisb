"""Тесты переходов автомата сортировки без камеры и GPIO."""

import unittest

from sorter.controller import SortingController
from sorter.models import Detection


def detected(name="paper", confidence=0.9):
    """Создать тестовую детекцию с достаточной площадью рамки."""
    return Detection(name, confidence, 5000, (0, 0, 100, 50))


class SortingControllerTests(unittest.TestCase):
    """Проверки стабилизации, блокировки повторов и восстановления."""

    def setUp(self):
        self.controller = SortingController(
            stable_frames=3,
            clear_frames=2,
            class_to_section={"paper": "section_1", "plastic": "section_2"},
            class_to_type={"paper": "paper", "plastic": "plastic_aluminum"},
        )

    def test_requires_stable_class(self):
        self.assertIsNone(self.controller.observe(detected()))
        self.assertIsNone(self.controller.observe(detected()))
        request = self.controller.observe(detected())
        self.assertEqual(request.section, "section_1")
        self.assertEqual(self.controller.state, self.controller.SORTING)

    def test_class_change_resets_streak(self):
        self.controller.observe(detected("paper"))
        self.controller.observe(detected("paper"))
        self.assertIsNone(self.controller.observe(detected("plastic")))
        self.assertEqual(self.controller.candidate_count, 1)

    def test_same_object_is_not_sorted_twice(self):
        for _ in range(3):
            request = self.controller.observe(detected())
        self.assertIsNotNone(request)
        self.controller.sorting_finished()
        for _ in range(10):
            self.assertIsNone(self.controller.observe(detected()))
        self.assertEqual(self.controller.state, self.controller.WAITING_FOR_REMOVAL)

    def test_unlocks_only_after_consecutive_clear_frames(self):
        for _ in range(3):
            self.controller.observe(detected())
        self.controller.sorting_finished()
        self.controller.observe(None)
        self.controller.observe(detected())
        self.controller.observe(None)
        self.assertEqual(self.controller.state, self.controller.WAITING_FOR_REMOVAL)
        self.controller.observe(None)
        self.assertEqual(self.controller.state, self.controller.IDLE)

    def test_hardware_failure_returns_to_idle(self):
        for _ in range(3):
            self.controller.observe(detected())
        self.controller.sorting_failed()
        self.assertEqual(self.controller.state, self.controller.IDLE)


if __name__ == "__main__":
    unittest.main()
