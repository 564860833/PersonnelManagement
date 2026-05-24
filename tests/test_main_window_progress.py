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

        class DbStub:
            def search_personnel(self, **kwargs):
                table_name = kwargs.get("table_name", "base_info")
                return {table_name: [{"sequence": 1, "name": "张三"}], "total_count": 1}

        class QueryTabStub:
            current_results_dict = {"base_info": [{"sequence": 1, "name": "张三"}]}

            def get_last_query_conditions(self):
                return {}

        window.db = DbStub()
        window.query_tab = QueryTabStub()
        window.clear_query_cache = lambda: None
        return window

    def make_dialog_from_factory(self, factory, task_title=""):
        dialog = factory(None, task_title)
        self.addCleanup(dialog.deleteLater)
        return dialog

    class FakeMessageBox:
        Question = object()
        AcceptRole = object()
        RejectRole = object()
        instances = []

        def __init__(self, parent):
            self.parent = parent
            self.icon = None
            self.window_title = None
            self.text = None
            self.informative_text = None
            self.buttons = []
            self.default_button = None
            self.clicked_button = None
            self.__class__.instances.append(self)

        def setIcon(self, icon):
            self.icon = icon

        def setWindowTitle(self, title):
            self.window_title = title

        def setText(self, text):
            self.text = text

        def setInformativeText(self, text):
            self.informative_text = text

        def addButton(self, text, role):
            button = {"text": text, "role": role}
            self.buttons.append(button)
            return button

        def setDefaultButton(self, button):
            self.default_button = button

        def exec_(self):
            self.clicked_button = self.default_button

        def clickedButton(self):
            return self.clicked_button

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

    def test_export_data_reads_full_rows_from_database_connection(self):
        window = self.make_window_stub()
        calls = {}

        def run_background_task(title, task_fn, on_success=None, on_error=None, progress_dialog_factory=None):
            calls["title"] = title
            calls["task_fn"] = task_fn
            calls["on_success"] = on_success
            calls["progress_dialog_factory"] = progress_dialog_factory

        window.run_background_task = run_background_task

        class FakeExportDb:
            def __init__(self):
                self.closed = False

            def search_personnel(self, **kwargs):
                return {
                    "base_info": [
                        {"sequence": 1, "name": "张三"},
                        {"sequence": 2, "name": "李四"},
                    ],
                    "total_count": 2,
                }

            def get_assessment_years(self):
                return [2020, 2021, 2022, 2023, 2024]

            def close(self):
                self.closed = True

        fake_db = FakeExportDb()

        with (
            patch("ui.main_window.QFileDialog.getSaveFileName", return_value=("D:/tmp/base_info.xlsx", "")),
            patch("ui.main_window.Database", return_value=fake_db),
            patch("ui.main_window.export_table_data", return_value=2) as export_mock,
        ):
            MainWindow.export_data(window, "base_info")
            exported_count = calls["task_fn"]()

        self.assertEqual("正在导出数据", calls["title"])
        self.assertTrue(calls["progress_dialog_factory"] is not None)
        export_mock.assert_called_once_with(
            [{"sequence": 1, "name": "张三"}, {"sequence": 2, "name": "李四"}],
            "D:/tmp/base_info.xlsx",
            "base_info",
            [2020, 2021, 2022, 2023, 2024],
        )
        self.assertEqual(2, exported_count)
        self.assertTrue(fake_db.closed)

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

    def test_confirm_import_mode_base_info_uses_update_and_add_button(self):
        window = self.make_window_stub()
        self.FakeMessageBox.instances = []

        with patch("ui.main_window.QMessageBox", self.FakeMessageBox):
            mode = MainWindow.confirm_import_mode(window, "base_info", [("1", "张三")])

        box = self.FakeMessageBox.instances[-1]
        self.assertEqual("merge", mode)
        self.assertEqual(["更新并新增", "取消"], [button["text"] for button in box.buttons])

    def test_confirm_import_mode_related_uses_skip_duplicate_button(self):
        window = self.make_window_stub()
        self.FakeMessageBox.instances = []

        with patch("ui.main_window.QMessageBox", self.FakeMessageBox):
            mode = MainWindow.confirm_import_mode(window, "family", [("1", "张三")])

        box = self.FakeMessageBox.instances[-1]
        self.assertEqual("append_unique", mode)
        self.assertEqual(["跳过重复并追加新增明细", "取消"], [button["text"] for button in box.buttons])

    def test_import_data_base_info_duplicate_uses_merge_mode(self):
        window = self.make_window_stub()
        calls = []

        def run_background_task(title, task_fn, on_success=None, on_error=None, progress_dialog_factory=None):
            calls.append(title)
            if title == "正在读取数据":
                on_success(
                    {
                        "success": True,
                        "records": [{"sequence": 1, "name": "张三"}],
                        "assessment_years": [],
                        "duplicate_keys": [("1", "张三")],
                    }
                )
            else:
                task_fn()

        window.run_background_task = run_background_task

        with (
            patch("ui.main_window.QFileDialog.getOpenFileName", return_value=("D:/tmp/base_info.xlsx", "")),
            patch.object(MainWindow, "confirm_import_mode", return_value="merge"),
            patch("ui.main_window.import_prepared_records", return_value={"success": True, "message": "ok"}) as import_mock,
        ):
            MainWindow.import_data(window, "base_info")

        self.assertEqual(["正在读取数据", "正在导入数据"], calls)
        self.assertTrue(import_mock.called)
        self.assertEqual({}, import_mock.call_args.kwargs)

    def test_import_data_related_duplicate_uses_skip_unique_mode(self):
        window = self.make_window_stub()
        calls = []

        def run_background_task(title, task_fn, on_success=None, on_error=None, progress_dialog_factory=None):
            calls.append(title)
            if title == "正在读取数据":
                on_success(
                    {
                        "success": True,
                        "records": [{"sequence": 1, "name": "张三", "relation": "父亲"}],
                        "assessment_years": [],
                        "duplicate_keys": [("1", "张三")],
                    }
                )
            else:
                task_fn()

        window.run_background_task = run_background_task

        with (
            patch("ui.main_window.QFileDialog.getOpenFileName", return_value=("D:/tmp/family.xlsx", "")),
            patch.object(MainWindow, "confirm_import_mode", return_value="append_unique"),
            patch("ui.main_window.import_prepared_records", return_value={"success": True, "message": "ok"}) as import_mock,
        ):
            MainWindow.import_data(window, "family")

        self.assertEqual(["正在读取数据", "正在导入数据"], calls)
        self.assertTrue(import_mock.called)
        self.assertEqual({}, import_mock.call_args.kwargs)


if __name__ == "__main__":
    unittest.main()
