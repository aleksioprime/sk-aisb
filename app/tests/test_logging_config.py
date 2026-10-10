"""Тесты настройки файлового журнала UMKA."""

import logging
import tempfile
import unittest
from pathlib import Path

from sorter.logging_config import configure_logging


class LoggingConfigTests(unittest.TestCase):
    """Проверки создания UTF-8-журнала и защиты от дублирования handlers."""

    def test_writes_log_file_and_replaces_old_handlers(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "logs" / "umka.log"
            self.assertTrue(configure_logging(path, verbose=True, backup_count=3))
            first_count = len(logging.getLogger().handlers)
            self.assertTrue(configure_logging(path, verbose=True, backup_count=3))
            self.assertEqual(len(logging.getLogger().handlers), first_count)

            logging.getLogger("test").info("Проверка журнала")
            for handler in logging.getLogger().handlers:
                handler.flush()
            self.assertIn("Проверка журнала", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
