import logging
import os
import tempfile
import unittest
from logging.handlers import RotatingFileHandler
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

import config
import ui.log_viewer
from ui.log_viewer import LogViewer
from ui.main_window import MainWindow


class FakeRootLogger:
    def __init__(self):
        self.handlers = []
        self.level = None

    def setLevel(self, level):
        self.level = level

    def removeHandler(self, handler):
        self.handlers.remove(handler)

    def addHandler(self, handler):
        self.handlers.append(handler)


class LoggingSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_config_uses_rotating_file_handler(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cfg = config.Config.__new__(config.Config)
            cfg.LOG_LEVEL = logging.INFO
            cfg.LOG_FORMAT = "%(message)s"
            cfg.LOG_FILE = str(Path(temp_dir) / "application.log")
            cfg.LOG_MAX_BYTES = 1024
            cfg.LOG_BACKUP_COUNT = 3
            root_logger = FakeRootLogger()

            with patch("config.logging.getLogger", return_value=root_logger):
                cfg.configure_logging()

            rotating_handlers = [
                handler for handler in root_logger.handlers
                if isinstance(handler, RotatingFileHandler)
            ]
            self.assertEqual(logging.INFO, root_logger.level)
            self.assertEqual(1, len(rotating_handlers))
            self.assertEqual(cfg.LOG_FILE, rotating_handlers[0].baseFilename)
            self.assertEqual(1024, rotating_handlers[0].maxBytes)
            self.assertEqual(3, rotating_handlers[0].backupCount)

            for handler in root_logger.handlers:
                handler.close()

    def test_non_admin_cannot_view_log(self):
        window = MainWindow.__new__(MainWindow)
        window.is_admin = False

        with patch("ui.main_window.QMessageBox.warning") as warning, \
                patch("ui.main_window.LogViewer") as log_viewer:
            MainWindow.on_view_log(window)

        warning.assert_called_once()
        log_viewer.assert_not_called()

    def test_non_admin_cannot_clear_log(self):
        window = MainWindow.__new__(MainWindow)
        window.is_admin = False

        with patch("ui.main_window.QMessageBox.warning") as warning, \
                patch("ui.main_window.confirm_danger") as confirm:
            MainWindow.on_clear_log(window)

        warning.assert_called_once()
        confirm.assert_not_called()

    def test_admin_view_log_opens_log_viewer_with_main_window_parent(self):
        window = MainWindow.__new__(MainWindow)
        window.is_admin = True

        with patch("ui.main_window.config.LOG_FILE", "D:/tmp/application.log"), \
                patch("ui.main_window.LogViewer") as log_viewer_class:
            log_viewer = log_viewer_class.return_value
            MainWindow.on_view_log(window)

        log_viewer_class.assert_called_once_with("D:/tmp/application.log", window)
        log_viewer.exec_.assert_called_once()

    def test_log_viewer_initial_load_reads_tail_for_large_logs(self):
        with tempfile.TemporaryDirectory() as temp_dir, \
                patch.object(ui.log_viewer, "INITIAL_LOG_TAIL_BYTES", 40):
            path = Path(temp_dir) / "application.log"
            path.write_text(
                "old line 1\nold line 2\nold line 3\nrecent line 1\nrecent line 2\n",
                encoding="utf-8",
            )
            viewer = LogViewer()
            self.addCleanup(viewer.deleteLater)

            content, _start = viewer.read_initial_file_content(path, path.stat().st_size)

        self.assertIn("已省略前", content)
        self.assertNotIn("old line 1", content)
        self.assertIn("recent line 1", content)
        self.assertIn("recent line 2", content)


if __name__ == "__main__":
    unittest.main()
