"""Тесты JSONL-журнала отдельных событий сортировки."""

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from sorter.event_journal import EventJournal


class EventJournalTests(unittest.TestCase):
    """Проверки формата, ежедневной ротации и срока хранения."""

    def test_rotates_on_next_day_and_keeps_json_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            journal = EventJournal(path, retention_days=30)
            journal._append(
                {"event": "sort", "event_id": "one"},
                now=datetime.fromisoformat("2026-08-27T23:59:00+03:00"),
            )
            journal._append(
                {"event": "feedback", "event_id": "one", "answer": "yes"},
                now=datetime.fromisoformat("2026-08-28T00:01:00+03:00"),
            )

            archive = Path(directory) / "events.2026-08-27.jsonl"
            self.assertTrue(archive.is_file())
            self.assertEqual(json.loads(archive.read_text(encoding="utf-8"))["event"], "sort")
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["event"], "feedback")

    def test_removes_archives_outside_retention_period(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            expired = Path(directory) / "events.2026-07-01.jsonl"
            recent = Path(directory) / "events.2026-08-27.jsonl"
            expired.write_text("{}\n", encoding="utf-8")
            recent.write_text("{}\n", encoding="utf-8")

            journal = EventJournal(path, retention_days=30)
            journal._append(
                {"event": "sort", "event_id": "two"},
                now=datetime.fromisoformat("2026-08-28T10:00:00+03:00"),
            )

            self.assertFalse(expired.exists())
            self.assertTrue(recent.exists())


if __name__ == "__main__":
    unittest.main()
