import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from ui.loading_dialog import ModernLoadingDialog
from ui.main_window import MainWindow


class MainWindowProgressDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_window_stub(self):
        window = MainWindow.__new__(MainWindow)
        window.last_export_dir = ""
        window.last_import_dir = ""
        window.permissions = {"base_info": True}
        window.query_tab = type(
            "QueryTabStub",
            (),
            {"current_results_dict": {"base_info": [{"sequence": 1, "name": "张三"}]}},
        )()
        window.clear_query_cache = lambda: None
        return window

    def make_dialog_from_factory(self, factory, task_title=""):
        dialog = factory(None, task_title)
        self.addCleanup(dialog.deleteLater)
        return dialog

    def test_modern_loading_dialog_constructs_each_icon_kind(self):
        for icon_kind in ("ai", "import", "export"):
            with self.subTest(icon_kind=icon_kind):
                dialog = ModernLoadingDialog(
                    title="测试标题",
                    message="测试说明",
                    icon_kind=icon_kind,
                )
                self.addCleanup(dialog.deleteLater)
                dialog.show()
                self.app.processEvents()

                self.assertEqual(icon_kind, dialog.icon_kind)
                self.assertEqual("测试标题", dialog.windowTitle())
                dialog.close()

    def test_export_data_uses_modern_export_progress_dialog(self):
        window = self.make_window_stub()
        calls = []

        def run_background_task(title, task_fn, on_success=None, on_error=None, progress_dialog_factory=None):
            calls.append((title, progress_dialog_factory))

        window.run_background_task = run_background_task

        with patch("ui.main_window.QFileDialog.getSaveFileName", return_value=("D:/tmp/base_info.xlsx", "")):
            MainWindow.export_data(window, "base_info")

        self.assertEqual(1, len(calls))
        title, factory = calls[0]
        self.assertEqual("正在导出数据", title)
        dialog = self.make_dialog_from_factory(factory, title)
        self.assertEqual("正在导出数据", dialog.windowTitle())
        self.assertEqual("export", dialog.icon_kind)

    def test_import_data_preview_uses_modern_import_progress_dialog(self):
        window = self.make_window_stub()
        calls = []

        def run_background_task(title, task_fn, on_success=None, on_error=None, progress_dialog_factory=None):
            calls.append((title, progress_dialog_factory))

        window.run_background_task = run_background_task

        with patch("ui.main_window.QFileDialog.getOpenFileName", return_value=("D:/tmp/base_info.xlsx", "")):
            MainWindow.import_data(window, "base_info")

        self.assertEqual(1, len(calls))
        title, factory = calls[0]
        self.assertEqual("正在读取数据", title)
        dialog = self.make_dialog_from_factory(factory, title)
        self.assertEqual("正在读取数据", dialog.windowTitle())
        self.assertEqual("import", dialog.icon_kind)

    def test_import_data_write_uses_modern_import_progress_dialog(self):
        window = self.make_window_stub()
        calls = []

        def run_background_task(title, task_fn, on_success=None, on_error=None, progress_dialog_factory=None):
            calls.append((title, progress_dialog_factory))
            if len(calls) == 1:
                on_success(
                    {
                        "success": True,
                        "records": [{"sequence": 1, "name": "张三"}],
                        "assessment_years": [],
                        "duplicate_keys": [],
                    }
                )

        window.run_background_task = run_background_task

        with patch("ui.main_window.QFileDialog.getOpenFileName", return_value=("D:/tmp/base_info.xlsx", "")):
            MainWindow.import_data(window, "base_info")

        self.assertEqual(2, len(calls))
        title, factory = calls[1]
        self.assertEqual("正在导入数据", title)
        dialog = self.make_dialog_from_factory(factory, title)
        self.assertEqual("正在导入数据", dialog.windowTitle())
        self.assertEqual("import", dialog.icon_kind)


if __name__ == "__main__":
    unittest.main()
