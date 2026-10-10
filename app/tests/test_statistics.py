"""Тесты сохранения и миграции JSON-статистики."""

import json
import tempfile
import unittest
from pathlib import Path

from sorter.statistics import StatisticsStore


class StatisticsStoreTests(unittest.TestCase):
    """Проверки потокобезопасного обновления статистики."""

    def test_records_sort_and_feedback_without_deadlock(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "stats.json"
            store = StatisticsStore(path)
            store.record_sort("paper", 0.05)
            store.record_feedback("yes")
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(saved["total_items"], 1)
            self.assertEqual(saved["by_type"]["paper"], 1)
            self.assertEqual(saved["feedback"]["correct"], 1)

    def test_migrates_old_dm3_format(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "stats.json"
            path.write_text(
                json.dumps({"items": 7, "weight_kg": 1.2, "correct": 3, "incorrect": 1}),
                encoding="utf-8",
            )
            snapshot = StatisticsStore(path).snapshot()
            self.assertEqual(snapshot["total_items"], 7)
            self.assertEqual(snapshot["feedback"]["incorrect"], 1)


if __name__ == "__main__":
    unittest.main()
