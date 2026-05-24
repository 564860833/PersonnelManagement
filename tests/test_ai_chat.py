import inspect
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QPoint, Qt
from PyQt5.QtWidgets import QApplication, QComboBox, QWidget

from services.ai_context import ContextRecommendation, HardwareSnapshot
from services.ai_direct import ask_model, ask_model_stream, build_analysis_data_json, build_messages
from ui.ai_chat import (
    AI_CHAT_STYLE,
    AIChatDialog,
    AIWorker,
    AI_CHAT_WINDOW_HEIGHT_RATIO,
    AI_CHAT_WINDOW_WIDTH_RATIO,
    CORE_FIELDS,
    CoreFieldSelectionDialog,
    FieldSelectionPage,
    MODEL_PLACEHOLDER,
    NAV_SIDEBAR_MIN_WIDTH,
    TABLE_NAV_BUTTON_MIN_WIDTH,
    TableNavItem,
    TableEnableSwitch,
    core_fields_for_table,
    estimate_payload_tokens,
    filter_analysis_payload_by_columns,
    group_columns_for_table,
    render_message_html,
    save_table_core_fields,
)
from ui.main_window import MainWindow
from ui.query import QueryTab, build_ai_analysis_payload


FIELD_LABELS = {
    "sequence": "序号",
    "name": "姓名",
    "department": "部门",
    "current_grade": "职级/等级",
}


def payload():
    return {
        "schemas": {
            "base_info": {
                "table_name": "base_info",
                "table_label": "人员基本信息",
                "columns": [
                    {"name": "sequence", "label": "序号"},
                    {"name": "name", "label": "姓名"},
                    {"name": "department", "label": "部门"},
                    {"name": "current_grade", "label": "职级/等级"},
                ],
            },
            "rewards": {
                "table_name": "rewards",
                "table_label": "人员奖惩信息",
                "columns": [
                    {"name": "sequence", "label": "序号"},
                    {"name": "name", "label": "姓名"},
                    {"name": "reward_name", "label": "奖励名称"},
                ],
            },
        },
        "tables": {
            "base_info": {
                "table_name": "base_info",
                "table_label": "人员基本信息",
                "field_labels": FIELD_LABELS,
                "rows": [
                    {"sequence": 1, "name": "张三", "department": "研发部", "current_grade": "一级"},
                    {"sequence": 2, "name": "李四", "department": "综合部", "current_grade": "二级"},
                ],
            },
            "rewards": {
                "table_name": "rewards",
                "table_label": "人员奖惩信息",
                "field_labels": {
                    "sequence": "序号",
                    "name": "姓名",
                    "reward_name": "奖励名称",
                },
                "rows": [],
            },
        },
    }


class FakeResponse:
    def __init__(self, content):
        self.content = content

    def raise_for_status(self):
        return None

    def json(self):
        return {"message": {"content": self.content}}


class FakeStreamingResponse:
    def __init__(self, lines):
        self.lines = list(lines)
        self.closed = False

    def raise_for_status(self):
        return None

    def iter_lines(self, decode_unicode=False):
        for line in self.lines:
            if decode_unicode or isinstance(line, str):
                yield line
            else:
                yield line.encode("utf-8")

    def close(self):
        self.closed = True


class FakeOllamaStatus:
    def __init__(self, service_available, message=""):
        self.service_available = service_available
        self.message = message


class FakeSignal:
    def __init__(self):
        self.callbacks = []

    def connect(self, callback):
        self.callbacks.append(callback)


class FakeDialog:
    def __init__(self):
        self.destroyed = FakeSignal()
        self.closed = False
        self.title = ""
        self.shown = False
        self.is_inference_running = False
        self.sync_started = False
        self.sync_deferred = False
        self.applied_payload = None
        self.sync_error = None

    def close(self):
        self.closed = True

    def setWindowTitle(self, title):
        self.title = title

    def show(self):
        self.shown = True

    def begin_payload_sync(self):
        self.sync_started = True

    def mark_payload_sync_deferred(self):
        self.sync_deferred = True

    def apply_analysis_payload(self, analysis_payload):
        self.applied_payload = analysis_payload

    def fail_payload_sync(self, message):
        self.sync_error = message


class FakeDb:
    def get_assessment_years(self):
        return []


class FakeWidget:
    def __init__(self):
        self.enabled = None

    def setEnabled(self, enabled):
        self.enabled = enabled


class FakeButton(FakeWidget):
    def __init__(self, text=""):
        super().__init__()
        self.text_value = text
        self.tooltip = ""
        self.checked = False

    def setText(self, text):
        self.text_value = text

    def text(self):
        return self.text_value

    def setToolTip(self, text):
        self.tooltip = text

    def setChecked(self, checked):
        self.checked = checked


class FakeLineEdit(FakeWidget):
    def __init__(self, text=""):
        super().__init__()
        self._text = text
        self.clear_called = False

    def text(self):
        return self._text

    def clear(self):
        self.clear_called = True
        self._text = ""


class FakeCombo(FakeWidget):
    def __init__(self, text=""):
        super().__init__()
        self._text = text
        self.items = []
        self.signals_blocked = False

    def currentText(self):
        return self._text

    def clear(self):
        self.items = []
        self._text = ""

    def addItem(self, text):
        self.items.append(str(text))
        if not self._text:
            self._text = str(text)

    def findText(self, text):
        try:
            return self.items.index(str(text))
        except ValueError:
            return -1

    def setCurrentIndex(self, index):
        self._text = self.items[index]

    def setCurrentText(self, text):
        self._text = str(text)

    def blockSignals(self, blocked):
        previous = self.signals_blocked
        self.signals_blocked = blocked
        return previous

    def count(self):
        return len(self.items)

    def itemText(self, index):
        return self.items[index]


class FakeLabel:
    def __init__(self):
        self.text = ""
        self.properties = {}

    def setText(self, text):
        self.text = text

    def setProperty(self, key, value):
        self.properties[key] = value


class FakeScrollBar:
    def __init__(self):
        self.value = None

    def maximum(self):
        return 100

    def setValue(self, value):
        self.value = value


class FakeHistory:
    def __init__(self):
        self.items = []
        self.scroll_bar = FakeScrollBar()

    def clear(self):
        self.items = []

    def append(self, html):
        self.items.append(html)

    def verticalScrollBar(self):
        return self.scroll_bar


class FakeCheck:
    def __init__(self, checked=True):
        self._checked = checked
        self.enabled = None

    def isChecked(self):
        return self._checked

    def setChecked(self, checked):
        self._checked = checked

    def setEnabled(self, enabled):
        self.enabled = enabled


class FakeTimer:
    def __init__(self):
        self.started = False
        self.stopped = False
        self.interval = None
        self.timeout = FakeSignal()

    def setSingleShot(self, value):
        return None

    def setInterval(self, value):
        self.interval = value

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True


class TestAIChatDialogBehavior(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self._config_dir = tempfile.TemporaryDirectory()
        self.core_config_path = Path(self._config_dir.name) / "ai_core_fields.json"
        self._core_config_patch = patch("ui.ai_chat.AI_CORE_FIELDS_CONFIG_FILE", self.core_config_path)
        self._core_config_patch.start()

    def tearDown(self):
        self._core_config_patch.stop()
        self._config_dir.cleanup()

    def make_dialog(self):
        dialog = AIChatDialog.__new__(AIChatDialog)
        dialog.analysis_payload = payload()
        dialog.history_messages = []
        dialog.current_context_recommendation = ContextRecommendation(
            n_ctx=4096,
            reason="test",
            hardware=HardwareSnapshot(),
            max_n_ctx=4096,
        )
        dialog.current_context_n_ctx = 4096
        dialog.context_options = [2048, 4096]
        dialog.is_inference_running = False
        dialog.worker = None
        dialog.worker_thread = None
        dialog.column_checks = {}
        dialog.table_pages = {}
        dialog.table_nav_buttons = {}
        dialog.table_nav_items = {}
        dialog.enabled_tables = {}
        dialog._selected_payload_cache_key = None
        dialog._selected_payload_cache = None
        dialog._selected_data_json_cache_key = None
        dialog._selected_data_json_cache_value = None
        dialog._payload_token_cache_key = None
        dialog._payload_token_cache_value = None
        dialog._chat_display_messages = []
        dialog._streaming_message_index = None
        dialog._stream_render_pending = False
        dialog._pressure_refresh_pending = False
        dialog.pressure_timer = type(
            "FakeTimer",
            (),
            {
                "started": False,
                "interval": None,
                "setSingleShot": lambda self, value: None,
                "setInterval": lambda self, value: setattr(self, "interval", value),
                "timeout": type("FakeSignal", (), {"connect": lambda self, fn: None})(),
                "start": lambda self: setattr(self, "started", True),
            },
        )()
        dialog.stream_render_timer = FakeTimer()
        dialog.pressure_bar = FakeWidget()
        dialog.pressure_bar.setValue = lambda value: setattr(dialog.pressure_bar, "value", value)
        dialog.pressure_bar.setProperty = lambda key, value: dialog.pressure_bar.properties.__setitem__(key, value)
        dialog.pressure_bar.properties = {}
        dialog.pressure_bar.style = lambda: type(
            "FakeStyle",
            (),
            {"unpolish": lambda self, widget: None, "polish": lambda self, widget: None},
        )()
        dialog.pressure_value_label = FakeLabel()
        dialog.pressure_hint_label = FakeLabel()
        dialog.context_combo = FakeCombo()
        dialog.context_reason_label = FakeLabel()
        dialog.column_summary_label = FakeLabel()
        dialog.status_label = FakeLabel()
        dialog.model_status_label = FakeLabel()
        dialog.model_combo = FakeCombo("qwen2:latest")
        dialog.input_field = FakeLineEdit("按部门汇总")
        dialog.send_btn = FakeButton()
        dialog.refresh_btn = FakeButton()
        dialog.clear_btn = FakeButton()
        dialog.chat_history = FakeHistory()
        dialog.chat_nav_btn = FakeButton()
        dialog.workspace_stack = type(
            "Stack",
            (),
            {
                "current": None,
                "setCurrentWidget": lambda self, widget: setattr(self, "current", widget),
                "currentWidget": lambda self: self.current,
            },
        )()
        return dialog

    def build_page(self, dialog):
        page = FieldSelectionPage(
            "base_info",
            "人员基本信息",
            2,
            [
                {"name": "sequence", "label": "序号"},
                {"name": "name", "label": "姓名"},
                {"name": "department", "label": "部门"},
                {"name": "current_grade", "label": "职级/等级"},
            ],
            parent=None,
        )
        page.selection_changed.connect(lambda table_name: None)
        page.return_requested.connect(lambda: None)
        dialog.table_pages = {"base_info": page}
        dialog.table_nav_buttons = {"base_info": FakeButton()}
        dialog.table_nav_items = {}
        dialog.column_checks = {"base_info": page.checkboxes}
        dialog.enabled_tables = {"base_info": True}
        return page

    def get_group(self, page, label):
        for block in page.group_blocks:
            if block.group_label == label:
                return block
        self.fail(f"未找到字段分组: {label}")

    def test_group_columns_for_table_groups_assessment_and_unknown_fields(self):
        groups = group_columns_for_table(
            "base_info",
            [
                {"name": "sequence", "label": "序号"},
                {"name": "assessment_0", "label": "2021年年度考核结果"},
                {"name": "department", "label": "部门"},
            ],
        )

        group_fields = {
            group["label"]: [column["name"] for column in group["columns"]]
            for group in groups
        }
        self.assertEqual(["sequence"], group_fields["基础身份信息"])
        self.assertEqual(["assessment_0"], group_fields["学历与考核奖惩"])
        self.assertEqual(["department"], group_fields["其他字段"])

    def test_core_fields_fall_back_to_static_defaults_without_config(self):
        fields = core_fields_for_table(
            "base_info",
            ["sequence", "name", "department", "current_grade", "assessment_0"],
        )

        self.assertIn("current_grade", CORE_FIELDS["base_info"])
        self.assertEqual({"sequence", "name", "current_grade", "assessment_0"}, fields)

    def test_core_fields_ignore_invalid_stored_config(self):
        self.core_config_path.write_text(
            json.dumps({"base_info": ["missing_field"]}, ensure_ascii=False),
            encoding="utf-8",
        )

        fields = core_fields_for_table(
            "base_info",
            ["sequence", "name", "department", "current_grade"],
        )

        self.assertEqual({"sequence", "name", "current_grade"}, fields)

    def test_saved_core_fields_are_loaded_and_applied_by_new_page(self):
        available = ["sequence", "name", "department", "current_grade"]
        saved = save_table_core_fields("base_info", ["department", "missing_field"], available)

        page = self.build_page(self.make_dialog())

        self.assertEqual({"sequence", "name", "department"}, saved)
        self.assertTrue(page.checkboxes["sequence"].isChecked())
        self.assertTrue(page.checkboxes["name"].isChecked())
        self.assertTrue(page.checkboxes["department"].isChecked())
        self.assertFalse(page.checkboxes["current_grade"].isChecked())

        page.set_all_fields(False)
        page.set_core_fields()

        self.assertTrue(page.checkboxes["department"].isChecked())
        self.assertFalse(page.checkboxes["current_grade"].isChecked())
        stored = json.loads(self.core_config_path.read_text(encoding="utf-8"))
        self.assertEqual(["sequence", "name", "department"], stored["base_info"])

    def test_core_field_dialog_saves_and_restores_defaults(self):
        page = self.build_page(self.make_dialog())

        dialog = page.create_core_field_dialog()
        self.assertIsInstance(dialog, CoreFieldSelectionDialog)
        self.assertIsNone(page.core_config_btn.menu())
        self.assertIn("department", dialog.core_field_checks)
        self.assertFalse(dialog.core_field_checks["sequence"].isEnabled())

        dialog.core_field_checks["department"].setChecked(True)
        dialog.core_field_checks["current_grade"].setChecked(False)
        dialog.choose_save()
        self.assertEqual(CoreFieldSelectionDialog.SAVE_ACTION, dialog.action)
        page.save_core_fields_from_dialog(dialog)

        self.assertTrue(page.checkboxes["department"].isChecked())
        self.assertFalse(page.checkboxes["current_grade"].isChecked())

        restore_dialog = page.create_core_field_dialog()
        restore_dialog.choose_restore_default()
        self.assertEqual(CoreFieldSelectionDialog.RESTORE_DEFAULT_ACTION, restore_dialog.action)
        page.restore_default_core_fields()

        self.assertFalse(page.checkboxes["department"].isChecked())
        self.assertTrue(page.checkboxes["current_grade"].isChecked())
        stored = json.loads(self.core_config_path.read_text(encoding="utf-8"))
        self.assertNotIn("base_info", stored)

    def test_core_segment_buttons_share_layout_but_keep_independent_actions(self):
        page = self.build_page(self.make_dialog())

        self.assertEqual(0, page.core_button_group_layout.spacing())
        self.assertIs(page.core_button_group_layout.itemAt(0).widget(), page.core_btn)
        self.assertIs(page.core_button_group_layout.itemAt(1).widget(), page.core_config_btn)
        self.assertEqual("🔍", page.core_config_btn.text())
        self.assertEqual(page.core_btn.height(), page.core_config_btn.height())
        self.assertEqual(32, page.core_btn.maximumHeight())
        self.assertEqual(32, page.core_config_btn.maximumHeight())
        self.assertEqual("人员基本信息（2行）", page.title_label.text())
        self.assertEqual(page.field_header_layout.count(), 5)
        self.assertEqual(0, page.field_header_layout.indexOf(page.title_label))
        self.assertEqual(1, page.field_header_layout.indexOf(page.badge_label))
        self.assertEqual(2, page.field_header_layout.indexOf(page.core_button_group))
        self.assertEqual(3, page.field_header_layout.indexOf(page.all_btn))
        self.assertEqual(4, page.field_header_layout.indexOf(page.reset_btn))
        self.assertIsNotNone(page.return_btn)
        self.assertEqual("完成选择并返回对话", page.return_btn.text())
        self.assertEqual(2, page.field_footer_layout.count())
        self.assertEqual(1, page.field_footer_layout.indexOf(page.return_btn))
        self.assertFalse(hasattr(page, "meta_label"))

        page.set_all_fields(True)
        page.checkboxes["current_grade"].setChecked(False)
        page.core_btn.click()

        self.assertFalse(page.checkboxes["department"].isChecked())
        self.assertTrue(page.checkboxes["current_grade"].isChecked())

        opened = []
        page.open_core_field_dialog = lambda: opened.append(True)
        page.core_config_btn.click()

        self.assertEqual([True], opened)

    def test_field_page_uses_group_blocks_and_global_actions(self):
        page = FieldSelectionPage(
            "base_info",
            "人员基本信息",
            2,
            [
                {"name": "sequence", "label": "序号"},
                {"name": "name", "label": "姓名"},
                {"name": "department", "label": "部门"},
                {"name": "current_grade", "label": "职级/等级"},
            ],
        )

        self.assertIn("已选 3/4 列", page.badge_label.text())
        self.assertEqual(4, len(page.checkboxes))
        self.assertEqual(["基础身份信息", "行政职务履历", "其他字段"], [block.group_label for block in page.group_blocks])
        self.assertGreater(self.get_group(page, "基础身份信息").fields_layout.count(), 0)
        self.assertTrue(page.checkboxes["sequence"].isChecked())

        page.set_all_fields(False)
        self.assertTrue(page.checkboxes["sequence"].isChecked())
        self.assertTrue(page.checkboxes["name"].isChecked())
        self.assertFalse(page.checkboxes["department"].isChecked())
        self.assertFalse(page.checkboxes["current_grade"].isChecked())

        page.set_core_fields()
        self.assertFalse(page.checkboxes["department"].isChecked())
        self.assertTrue(page.checkboxes["current_grade"].isChecked())

        page.set_all_fields(True)
        self.assertTrue(page.checkboxes["department"].isChecked())

        page.reset_fields()
        self.assertFalse(page.checkboxes["department"].isChecked())
        self.assertFalse(page.checkboxes["current_grade"].isChecked())
        self.assertTrue(page.checkboxes["sequence"].isChecked())
        self.assertTrue(page.checkboxes["name"].isChecked())

    def test_group_actions_only_affect_their_own_fields(self):
        page = FieldSelectionPage(
            "base_info",
            "人员基本信息",
            2,
            [
                {"name": "sequence", "label": "序号"},
                {"name": "name", "label": "姓名"},
                {"name": "department", "label": "部门"},
                {"name": "current_grade", "label": "职级/等级"},
            ],
        )
        other_group = self.get_group(page, "其他字段")
        role_group = self.get_group(page, "行政职务履历")

        page.set_all_fields(False)
        other_group.set_all_fields(True)

        self.assertTrue(page.checkboxes["department"].isChecked())
        self.assertFalse(page.checkboxes["current_grade"].isChecked())
        self.assertIn("已选 1/1", other_group.badge_label.text())

        other_group.reset_fields()
        self.assertFalse(page.checkboxes["department"].isChecked())
        role_group.set_all_fields(True)
        self.assertTrue(page.checkboxes["current_grade"].isChecked())
        self.assertFalse(page.checkboxes["department"].isChecked())

        role_group.reset_fields()
        self.assertFalse(page.checkboxes["current_grade"].isChecked())
        self.assertFalse(page.checkboxes["department"].isChecked())

    def test_refresh_context_pressure_estimates_and_sets_state(self):
        dialog = self.make_dialog()
        self.build_page(dialog)

        dialog.refresh_context_pressure()

        self.assertGreater(dialog.pressure_bar.value, 0)
        self.assertIn("tokens", dialog.pressure_value_label.text)
        self.assertIn(dialog.pressure_bar.properties["state"], {"safe", "warn", "danger"})

    def test_schedule_context_pressure_refresh_uses_timer(self):
        dialog = self.make_dialog()

        dialog.schedule_context_pressure_refresh()

        self.assertTrue(dialog.pressure_timer.started)
        self.assertTrue(dialog._pressure_refresh_pending)

    def test_table_enable_switch_entire_rect_is_clickable(self):
        switch = TableEnableSwitch()

        self.assertTrue(switch.hitButton(QPoint(2, 12)))
        self.assertTrue(switch.hitButton(QPoint(21, 12)))
        self.assertTrue(switch.hitButton(QPoint(40, 12)))
        self.assertFalse(switch.hitButton(QPoint(43, 12)))

    def test_navigation_switches_workspace_pages(self):
        dialog = self.make_dialog()
        dialog.table_pages = {
            "base_info": type(
                "Page",
                (),
                {
                    "selected_count": lambda self: 3,
                    "total_count": lambda self: 4,
                    "refresh_badge": lambda self: None,
                    "reflow_fields": lambda self: None,
                    "table_label": "人员基本信息",
                    "row_count": 2,
                },
            )(),
        }
        dialog.table_nav_buttons = {"base_info": FakeButton()}
        dialog.chat_page = object()

        dialog.refresh_table_navigation()
        AIChatDialog.switch_to_table(dialog, "base_info")
        self.assertIs(dialog.workspace_stack.current, dialog.table_pages["base_info"])
        self.assertEqual("人员基本信息\n已选 3/4", dialog.table_nav_buttons["base_info"].text())
        self.assertIn("2 行", dialog.table_nav_buttons["base_info"].tooltip)

        AIChatDialog.switch_to_chat(dialog)
        self.assertIs(dialog.workspace_stack.current, dialog.chat_page)

    def test_table_nav_item_switch_toggles_without_navigation_click(self):
        with patch("ui.ai_chat.fetch_ollama_models", return_value=(True, ["qwen2:latest"])):
            dialog = AIChatDialog(payload())
        try:
            item = dialog.table_nav_items["base_info"]
            self.assertIsInstance(item, TableNavItem)
            self.assertIs(dialog.table_nav_buttons["base_info"], item.nav_button)
            self.assertTrue(item.enable_switch.isChecked())
            self.assertGreaterEqual(dialog.sidebar_panel.minimumWidth(), NAV_SIDEBAR_MIN_WIDTH)
            self.assertGreaterEqual(item.minimumWidth(), TABLE_NAV_BUTTON_MIN_WIDTH + item.enable_switch.width())
            self.assertGreaterEqual(item.nav_button.minimumWidth(), TABLE_NAV_BUTTON_MIN_WIDTH)
            self.assertEqual(item.enable_switch.sizePolicy().Fixed, item.enable_switch.sizePolicy().horizontalPolicy())
            self.assertFalse(dialog.column_summary_label.wordWrap())

            dialog.switch_to_chat()
            current_page = dialog.workspace_stack.currentWidget()
            item.enable_switch.click()
            self.app.processEvents()

            self.assertFalse(dialog.enabled_tables["base_info"])
            self.assertIs(dialog.workspace_stack.currentWidget(), current_page)
            self.assertFalse(item.nav_button.isEnabled())
        finally:
            dialog.close()

    def test_ai_dialog_default_geometry_scales_to_parent_and_centers(self):
        reference = QWidget()
        reference.setGeometry(100, 80, 1600, 1000)
        with patch("ui.ai_chat.fetch_ollama_models", return_value=(True, ["qwen2:latest"])):
            dialog = AIChatDialog(payload(), reference_widget=reference)
        try:
            self.assertIsNone(dialog.parentWidget())
            self.assertEqual(int(1600 * AI_CHAT_WINDOW_WIDTH_RATIO), dialog.width())
            self.assertEqual(int(1000 * AI_CHAT_WINDOW_HEIGHT_RATIO), dialog.height())

            dialog._center_on_reference_geometry()
            self.assertEqual(reference.geometry().center(), dialog.frameGeometry().center())
        finally:
            dialog.close()
            reference.close()

    def test_ai_dialog_window_flags_include_independent_window_controls(self):
        with patch("ui.ai_chat.fetch_ollama_models", return_value=(True, ["qwen2:latest"])):
            dialog = AIChatDialog(payload())
        try:
            flags = dialog.windowFlags()
            self.assertTrue(bool(flags & Qt.Window))
            self.assertTrue(bool(flags & Qt.WindowMinimizeButtonHint))
            self.assertTrue(bool(flags & Qt.WindowMaximizeButtonHint))
            self.assertTrue(bool(flags & Qt.WindowCloseButtonHint))
            self.assertFalse(bool(flags & Qt.WindowContextHelpButtonHint))
            self.assertIsNone(dialog.parentWidget())
        finally:
            dialog.close()

    def test_disabled_table_is_removed_from_selected_payload_until_reenabled(self):
        dialog = self.make_dialog()
        page = self.build_page(dialog)
        page.checkboxes["department"].setChecked(True)
        dialog.enabled_tables = {"base_info": False, "rewards": True}

        disabled_payload = dialog.selected_analysis_payload()

        self.assertNotIn("base_info", disabled_payload["tables"])
        self.assertIn("rewards", disabled_payload["tables"])

        dialog.enabled_tables["base_info"] = True
        enabled_payload = dialog.selected_analysis_payload()

        self.assertIn("base_info", enabled_payload["tables"])
        self.assertIn("department", enabled_payload["tables"]["base_info"]["field_labels"])

    def test_disabling_current_table_returns_to_chat_and_blocks_navigation(self):
        dialog = self.make_dialog()
        page = self.build_page(dialog)
        dialog.chat_page = object()
        dialog.workspace_stack.setCurrentWidget(page)

        dialog.on_table_enabled_changed("base_info", False)

        self.assertIs(dialog.workspace_stack.currentWidget(), dialog.chat_page)
        self.assertFalse(dialog.enabled_tables["base_info"])
        self.assertFalse(dialog.table_nav_buttons["base_info"].enabled)

        dialog.switch_to_table("base_info")

        self.assertIs(dialog.workspace_stack.currentWidget(), dialog.chat_page)

    def test_all_disabled_tables_disable_send_and_show_empty_summary(self):
        dialog = self.make_dialog()
        self.build_page(dialog)
        dialog.enabled_tables = {"base_info": False, "rewards": False}

        dialog.refresh_column_summary()

        self.assertEqual("将发送0个表/0列", dialog.column_summary_label.text)
        self.assertFalse(dialog.send_btn.enabled)

    def test_summary_and_action_state_do_not_build_full_payload(self):
        dialog = self.make_dialog()
        page = self.build_page(dialog)
        page.checkboxes["department"].setChecked(True)

        with patch("ui.ai_chat.filter_analysis_payload_by_columns", side_effect=AssertionError("full payload built")):
            dialog.refresh_column_summary()
            dialog.update_action_state()

        self.assertEqual("将发送2个表/6列", dialog.column_summary_label.text)
        self.assertTrue(dialog.send_btn.enabled)

    def test_empty_selected_rows_disable_send(self):
        dialog = self.make_dialog()
        dialog.analysis_payload["tables"]["base_info"]["rows"] = []
        self.build_page(dialog)

        dialog.update_action_state()

        self.assertFalse(dialog.send_btn.enabled)

    def test_selected_analysis_payload_uses_cache_until_selection_changes(self):
        dialog = self.make_dialog()
        page = self.build_page(dialog)

        with patch(
            "ui.ai_chat.filter_analysis_payload_by_columns",
            wraps=filter_analysis_payload_by_columns,
        ) as payload_filter:
            first_payload = dialog.selected_analysis_payload()
            second_payload = dialog.selected_analysis_payload()

            self.assertIs(first_payload, second_payload)
            self.assertEqual(1, payload_filter.call_count)

            page.checkboxes["department"].setChecked(True)
            dialog.on_table_selection_changed("base_info")
            updated_payload = dialog.selected_analysis_payload()

            self.assertIsNot(updated_payload, first_payload)
            self.assertEqual(2, payload_filter.call_count)
            self.assertIn("department", updated_payload["tables"]["base_info"]["field_labels"])

    def test_selected_analysis_data_json_reuses_cache_until_selection_changes(self):
        dialog = self.make_dialog()
        page = self.build_page(dialog)

        with patch("ui.ai_chat.build_analysis_data_json", wraps=build_analysis_data_json) as build_json:
            first_json = dialog.selected_analysis_data_json()
            second_json = dialog.selected_analysis_data_json()

            self.assertEqual(first_json, second_json)
            self.assertEqual(1, build_json.call_count)

            page.checkboxes["department"].setChecked(True)
            dialog.on_table_selection_changed("base_info")
            updated_json = dialog.selected_analysis_data_json()

            self.assertNotEqual(first_json, updated_json)
            self.assertEqual(2, build_json.call_count)

    def test_context_pressure_reuses_token_estimate_for_same_selection(self):
        dialog = self.make_dialog()
        self.build_page(dialog)

        with patch("ui.ai_chat.estimate_payload_tokens", wraps=estimate_payload_tokens) as estimate:
            dialog.refresh_context_pressure()
            dialog.refresh_context_pressure()

            self.assertEqual(1, estimate.call_count)

            dialog.on_table_enabled_changed("base_info", False)
            dialog.refresh_context_pressure()

            self.assertEqual(2, estimate.call_count)

    def test_sidebar_nav_buttons_share_capsule_style(self):
        dialog = self.make_dialog()

        chat_button = AIChatDialog.create_nav_button(dialog, "当前对话", "聊天与提问")
        table_button = AIChatDialog.create_nav_button(dialog, "人员基本信息")

        self.assertEqual("aiNavButton", chat_button.objectName())
        self.assertEqual("aiNavButton", table_button.objectName())
        nav_style = AI_CHAT_STYLE.split("QPushButton#aiNavButton {", 1)[1].split("}", 1)[0]
        self.assertIn("border: 1px solid #E5EAF0;", nav_style)
        self.assertIn("background-color: #FBFDFF;", nav_style)
        self.assertNotIn("QPushButton#aiTableNavButton", AI_CHAT_STYLE)

    def test_model_status_is_left_aligned_and_context_combo_has_options(self):
        with patch("ui.ai_chat.fetch_ollama_models", return_value=(True, ["qwen2:latest"])):
            dialog = AIChatDialog(payload())
        try:
            self.assertIs(dialog.settings_header_layout.itemAt(0).widget(), dialog.model_status_label)
            self.assertIsInstance(dialog.context_combo, QComboBox)
            self.assertIn(dialog.current_context_n_ctx, dialog.context_options)
            self.assertEqual(str(dialog.current_context_n_ctx), dialog.context_combo.currentText())
            self.assertNotIn("▾", dialog.context_combo.currentText())
            self.assertGreater(dialog.context_combo.count(), 0)
            self.assertTrue(dialog.context_reason_label.wordWrap())
        finally:
            dialog.close()

    def test_apply_analysis_payload_refreshes_rows_and_preserves_chat_selection(self):
        with patch("ui.ai_chat.fetch_ollama_models", return_value=(True, ["qwen2:latest"])):
            dialog = AIChatDialog(payload())
        try:
            dialog.history_messages = [{"role": "user", "content": "按部门汇总"}]
            dialog.table_pages["base_info"].checkboxes["department"].setChecked(True)
            dialog.table_pages["base_info"].checkboxes["current_grade"].setChecked(True)
            dialog.enabled_tables["rewards"] = False

            updated_payload = payload()
            updated_payload["schemas"]["base_info"]["columns"] = [
                {"name": "sequence", "label": "序号"},
                {"name": "name", "label": "姓名"},
                {"name": "department", "label": "部门"},
            ]
            updated_payload["tables"]["base_info"]["field_labels"] = {
                "sequence": "序号",
                "name": "姓名",
                "department": "部门",
            }
            updated_payload["tables"]["base_info"]["rows"] = [
                {"sequence": 3, "name": "王五", "department": "研发部"},
            ]

            dialog.begin_payload_sync()
            self.assertFalse(dialog.send_btn.isEnabled())

            dialog.apply_analysis_payload(updated_payload)

            self.assertEqual([{"role": "user", "content": "按部门汇总"}], dialog.history_messages)
            self.assertEqual(1, dialog.table_pages["base_info"].row_count)
            self.assertTrue(dialog.column_checks["base_info"]["department"].isChecked())
            self.assertNotIn("current_grade", dialog.column_checks["base_info"])
            self.assertFalse(dialog.enabled_tables["rewards"])
            self.assertIn("后续问题将基于最新查询结果", dialog.status_label.text())
        finally:
            dialog.close()

    def test_selecting_context_updates_pressure_denominator(self):
        dialog = self.make_dialog()
        self.build_page(dialog)
        dialog.context_combo = FakeCombo()
        dialog.context_reason_label = FakeLabel()
        dialog.context_options = [2048, 4096, 8192]

        AIChatDialog.set_context_n_ctx(dialog, 8192)
        dialog.refresh_context_pressure()

        self.assertEqual(8192, dialog.current_context_n_ctx)
        self.assertEqual("8192", dialog.context_combo.currentText())
        self.assertIn("8.2k", dialog.pressure_value_label.text)

    def test_switching_to_field_page_reflows_tags_without_window_resize(self):
        with patch("ui.ai_chat.fetch_ollama_models", return_value=(True, ["qwen2:latest"])):
            dialog = AIChatDialog(payload())
        try:
            dialog.show()
            self.app.processEvents()
            dialog.switch_to_table("base_info")
            self.app.processEvents()
            self.app.processEvents()

            page = dialog.table_pages["base_info"]
            geometries = [check.geometry() for check in page.checkboxes.values()]
            self.assertGreater(len({(geometry.x(), geometry.y()) for geometry in geometries}), 1)
            self.assertLess(max(geometry.width() for geometry in geometries), 240)
        finally:
            dialog.close()

    def test_refresh_column_summary_updates_badges_and_nav(self):
        dialog = self.make_dialog()
        page = self.build_page(dialog)
        page.checkboxes["department"].setChecked(True)

        dialog.refresh_column_summary()

        self.assertIn("将发送2个表/6列", dialog.column_summary_label.text)
        self.assertIn("已选 4/4 列", page.badge_label.text())
        self.assertIn("已选 1/1", self.get_group(page, "其他字段").badge_label.text())
        self.assertIn("已选 4/4", dialog.table_nav_buttons["base_info"].text())

    def test_global_controls_disable_during_inference(self):
        dialog = self.make_dialog()
        page = self.build_page(dialog)
        dialog.is_inference_running = True

        dialog.update_action_state()

        self.assertFalse(dialog.send_btn.enabled)
        self.assertFalse(dialog.input_field.enabled)
        self.assertFalse(dialog.model_combo.enabled)
        self.assertFalse(dialog.refresh_btn.enabled)
        self.assertFalse(dialog.clear_btn.enabled)
        self.assertFalse(dialog.chat_nav_btn.enabled)
        self.assertFalse(dialog.table_nav_buttons["base_info"].enabled)
        self.assertFalse(page.core_btn.isEnabled())
        self.assertFalse(page.core_config_btn.isEnabled())
        self.assertFalse(page.all_btn.isEnabled())
        self.assertFalse(page.reset_btn.isEnabled())
        self.assertFalse(page.group_blocks[0].all_btn.isEnabled())
        self.assertFalse(page.group_blocks[0].reset_btn.isEnabled())

    def test_global_controls_disable_during_payload_sync(self):
        dialog = self.make_dialog()
        page = self.build_page(dialog)
        dialog.is_payload_syncing = True

        dialog.update_action_state()

        self.assertFalse(dialog.send_btn.enabled)
        self.assertFalse(dialog.input_field.enabled)
        self.assertFalse(dialog.model_combo.enabled)
        self.assertFalse(dialog.refresh_btn.enabled)
        self.assertFalse(dialog.clear_btn.enabled)
        self.assertFalse(dialog.chat_nav_btn.enabled)
        self.assertFalse(dialog.table_nav_buttons["base_info"].enabled)
        self.assertFalse(page.core_btn.isEnabled())
        self.assertFalse(page.core_config_btn.isEnabled())
        self.assertFalse(page.all_btn.isEnabled())
        self.assertFalse(page.reset_btn.isEnabled())

    def make_ai_payload_query_tab(self, permissions=None):
        tab = QueryTab.__new__(QueryTab)
        tab.permissions = permissions or {
            "base_info": True,
            "rewards": False,
            "family": False,
            "resume": False,
        }
        tab._last_query_conditions = {}
        tab._ai_payload_cache = {}
        return tab

    def make_payload_db(self):
        class FakePayloadDb:
            def __init__(self):
                self.search_calls = []
                self.closed_count = 0

            def get_assessment_years(self):
                return []

            def search_personnel(self, **kwargs):
                self.search_calls.append(dict(kwargs))
                table_name = kwargs["table_name"]
                return {
                    table_name: [
                        {
                            "sequence": len(self.search_calls),
                            "name": "P",
                        }
                    ],
                    "total_count": 1,
                }

            def close(self):
                self.closed_count += 1

        return FakePayloadDb()

    def test_ai_payload_cache_reuses_same_query_permissions_and_db_signature(self):
        tab = self.make_ai_payload_query_tab()
        db = self.make_payload_db()
        signature = (("db", True, 10, 100), ("db-wal", False, 0, 0), ("db-shm", False, 0, 0))

        with patch("ui.query.Database", return_value=db), \
                patch.object(QueryTab, "_ai_database_signature", return_value=signature):
            first = QueryTab.build_full_ai_analysis_payload(tab, {})
            second = QueryTab.build_full_ai_analysis_payload(tab, {})

        self.assertIs(first, second)
        self.assertEqual(1, len(db.search_calls))
        self.assertEqual(1, db.closed_count)

    def test_ai_payload_cache_rebuilds_when_query_conditions_change(self):
        tab = self.make_ai_payload_query_tab()
        db = self.make_payload_db()
        signature = (("db", True, 10, 100), ("db-wal", False, 0, 0), ("db-shm", False, 0, 0))

        with patch("ui.query.Database", return_value=db), \
                patch.object(QueryTab, "_ai_database_signature", return_value=signature):
            first = QueryTab.build_full_ai_analysis_payload(tab, {})
            second = QueryTab.build_full_ai_analysis_payload(tab, {"name": "P"})

        self.assertIsNot(first, second)
        self.assertEqual(2, len(db.search_calls))

    def test_ai_payload_cache_rebuilds_when_permissions_change(self):
        tab = self.make_ai_payload_query_tab()
        db = self.make_payload_db()
        signature = (("db", True, 10, 100), ("db-wal", False, 0, 0), ("db-shm", False, 0, 0))

        with patch("ui.query.Database", return_value=db), \
                patch.object(QueryTab, "_ai_database_signature", return_value=signature):
            first = QueryTab.build_full_ai_analysis_payload(tab, {})
            tab.permissions = {
                "base_info": True,
                "rewards": False,
                "family": True,
                "resume": False,
            }
            second = QueryTab.build_full_ai_analysis_payload(tab, {})

        self.assertIsNot(first, second)
        self.assertEqual(3, len(db.search_calls))
        self.assertEqual("family", db.search_calls[-1]["table_name"])

    def test_ai_payload_cache_rebuilds_when_database_signature_changes(self):
        tab = self.make_ai_payload_query_tab()
        db = self.make_payload_db()
        first_signature = (("db", True, 10, 100), ("db-wal", False, 0, 0), ("db-shm", False, 0, 0))
        second_signature = (("db", True, 20, 200), ("db-wal", False, 0, 0), ("db-shm", False, 0, 0))

        with patch("ui.query.Database", return_value=db), \
                patch.object(
                    QueryTab,
                    "_ai_database_signature",
                    side_effect=[first_signature, first_signature, second_signature, second_signature],
                ):
            first = QueryTab.build_full_ai_analysis_payload(tab, {})
            second = QueryTab.build_full_ai_analysis_payload(tab, {})

        self.assertIsNot(first, second)
        self.assertEqual(2, len(db.search_calls))

    def test_ai_payload_cache_skips_store_when_database_changes_during_build(self):
        tab = self.make_ai_payload_query_tab()
        db = self.make_payload_db()
        first_signature = (("db", True, 10, 100), ("db-wal", False, 0, 0), ("db-shm", False, 0, 0))
        second_signature = (("db", True, 20, 200), ("db-wal", False, 0, 0), ("db-shm", False, 0, 0))

        with patch("ui.query.Database", return_value=db), \
                patch.object(
                    QueryTab,
                    "_ai_database_signature",
                    side_effect=[first_signature, second_signature, second_signature, second_signature],
                ):
            first = QueryTab.build_full_ai_analysis_payload(tab, {})
            second = QueryTab.build_full_ai_analysis_payload(tab, {})

        self.assertIsNot(first, second)
        self.assertEqual(2, len(db.search_calls))

    def test_clear_results_invalidates_ai_payload_cache(self):
        tab = self.make_ai_payload_query_tab()
        tab.current_total_counts = {}
        tab.current_results = []
        tab.current_results_dict = {}
        tab.current_table_name = "base_info"
        tab.current_page = 1
        tab.ai_dialog = None
        tab._pending_ai_sync_conditions = None
        tab._ai_sync_generation = 0
        tab.update_pagination_controls = lambda *_args: None
        tab.update_table_buttons = lambda *_args: None

        class FakeModel:
            def clear(self):
                pass

        tab.result_model = FakeModel()
        db = self.make_payload_db()
        signature = (("db", True, 10, 100), ("db-wal", False, 0, 0), ("db-shm", False, 0, 0))

        with patch("ui.query.Database", return_value=db), \
                patch.object(QueryTab, "_ai_database_signature", return_value=signature):
            QueryTab.build_full_ai_analysis_payload(tab, {})
            QueryTab.clear_results(tab)
            QueryTab.build_full_ai_analysis_payload(tab, {})

        self.assertEqual(2, len(db.search_calls))


class AIChatDirectModelTests(unittest.TestCase):
    def test_chat_dialog_uses_direct_model_and_column_selection(self):
        source = "\n".join(
            [
                inspect.getsource(AIChatDialog),
                inspect.getsource(AIWorker),
                inspect.getsource(AIChatDialog.start_inference),
                inspect.getsource(AIChatDialog.refresh_models),
            ]
        )

        self.assertIn("AIWorker", source)
        self.assertIn("ask_model_stream", source)
        self.assertIn("recommend_context_length", source)
        self.assertIn("selected_analysis_payload", source)
        self.assertIn("selected_analysis_data_json", source)
        self.assertIn("build_analysis_data_json", source)
        self.assertIn("filter_analysis_payload_by_columns", source)
        self.assertNotIn("build_schema_selection_messages", source)
        self.assertNotIn("AIQueryEngine", source)

    def test_ai_worker_passes_auto_context_to_direct_model(self):
        history = [{"role": "user", "content": "上一轮问题"}]
        worker = AIWorker("继续分析", payload(), "qwen2:latest", 8192, history, analysis_data_json='{"tables":[]}')
        deltas = []
        worker.delta.connect(deltas.append)

        with patch("ui.ai_chat.ask_model_stream", return_value="OK") as ask:
            worker.run()

        ask.assert_called_once()
        args = ask.call_args.args
        kwargs = ask.call_args.kwargs
        self.assertEqual("继续分析", args[0])
        self.assertEqual("qwen2:latest", args[2])
        self.assertEqual(8192, args[3])
        self.assertEqual(history, kwargs["history_messages"])
        self.assertEqual('{"tables":[]}', kwargs["analysis_data_json"])
        self.assertEqual([], deltas)

    def test_ai_worker_emits_streaming_delta_and_final_answer(self):
        worker = AIWorker("继续分析", payload(), "qwen2:latest", 8192, analysis_data_json='{"tables":[]}')
        deltas = []
        finished = []
        worker.delta.connect(deltas.append)
        worker.finished.connect(finished.append)

        def fake_stream(*args, **kwargs):
            kwargs["on_delta"]("A")
            kwargs["on_delta"]("B")
            return "AB"

        with patch("ui.ai_chat.ask_model_stream", side_effect=fake_stream):
            worker.run()

        self.assertEqual(["A", "B"], deltas)
        self.assertEqual(["AB"], finished)

    def test_ai_worker_context_errors_fail_without_auto_retry(self):
        worker = AIWorker("继续分析", payload(), "qwen2:latest", 2048)
        failures = []
        finished = []
        worker.failed.connect(failures.append)
        worker.finished.connect(finished.append)

        with patch(
            "ui.ai_chat.ask_model_stream",
            side_effect=RuntimeError("context length exceeded"),
        ) as ask, patch("ui.ai_chat.logger.exception"):
            worker.run()

        ask.assert_called_once()
        self.assertEqual([], finished)
        self.assertEqual(["上下文不足，请在左下角选择更大的上下文后重试"], failures)

    def test_ai_worker_does_not_retry_non_context_errors(self):
        worker = AIWorker("继续分析", payload(), "qwen2:latest", 2048)

        with patch("ui.ai_chat.ask_model_stream", side_effect=RuntimeError("network failed")) as ask, \
                patch("ui.ai_chat.logger.exception"):
            worker.run()

        ask.assert_called_once()

    def test_ai_worker_emits_failed_for_model_errors(self):
        worker = AIWorker("继续分析", payload(), "qwen2:latest", 2048)
        failures = []
        finished = []
        worker.failed.connect(failures.append)
        worker.finished.connect(finished.append)

        with patch("ui.ai_chat.ask_model_stream", side_effect=RuntimeError("network failed")), \
                patch("ui.ai_chat.logger.exception"):
            worker.run()

        self.assertEqual(["network failed"], failures)
        self.assertEqual([], finished)

    def test_stream_delta_updates_single_assistant_message_and_final_response(self):
        dialog = self.make_chat_dialog_stub()
        dialog.history_messages = [{"role": "user", "content": "上一轮问题"}]
        dialog._pending_history_length = 1
        dialog.history_messages.append({"role": "user", "content": "本轮问题"})
        dialog.is_inference_running = True
        AIChatDialog.append_message(dialog, "user", "本轮问题")

        AIChatDialog.handle_stream_delta(dialog, "A")
        AIChatDialog.handle_stream_delta(dialog, "B")

        self.assertTrue(dialog.stream_render_timer.started)
        self.assertEqual(2, len(dialog.chat_history.items))
        self.assertIn("A", dialog._chat_display_messages[1]["content"])
        self.assertIn("AB", dialog._chat_display_messages[1]["content"])

        AIChatDialog.handle_response(dialog, "AB")

        self.assertEqual(2, len(dialog.chat_history.items))
        self.assertIn("AB", dialog.chat_history.items[-1])
        self.assertEqual(
            [
                {"role": "user", "content": "上一轮问题"},
                {"role": "user", "content": "本轮问题"},
                {"role": "assistant", "content": "AB"},
            ],
            dialog.history_messages,
        )
        self.assertFalse(dialog._stream_render_pending)

    def test_user_message_renders_as_right_blue_bubble(self):
        rendered = render_message_html("user", "<script>alert(1)</script>")

        self.assertIn('width="76%" align="right"', rendered)
        self.assertIn("background-color: #2563EB", rendered)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", rendered)
        self.assertNotIn("<script>alert(1)</script>", rendered)

    def test_ai_message_renders_as_left_bubble_with_markdown_table(self):
        rendered = render_message_html(
            "assistant",
            "| 部门 | 人数 |\n| --- | --- |\n| 研发部 | 2 |",
        )

        self.assertIn('width="76%" align="left"', rendered)
        self.assertIn("background-color: #F6F8FA", rendered)
        self.assertIn('<table style="border-collapse: collapse; width: 100%; margin: 8px 0;">', rendered)

    def test_ai_message_escapes_raw_html_but_keeps_markdown(self):
        rendered = render_message_html(
            "assistant",
            "<script>alert(1)</script>\n**bold**",
        )

        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", rendered)
        self.assertNotIn("<script>alert(1)</script>", rendered)
        self.assertIn("<strong>bold</strong>", rendered)

    def test_error_message_renders_as_left_red_bubble(self):
        rendered = render_message_html("assistant", "network failed", is_error=True)

        self.assertIn('width="76%" align="left"', rendered)
        self.assertIn("background-color: #FFF1F0", rendered)
        self.assertIn("network failed", rendered)

    def test_context_combo_updates_with_selected_context_and_reason(self):
        dialog = AIChatDialog.__new__(AIChatDialog)
        dialog.current_context_recommendation = ContextRecommendation(
            n_ctx=2048,
            reason="15.6GB 内存 / 4GB 显存",
            hardware=HardwareSnapshot(),
            max_n_ctx=8192,
        )
        dialog.current_context_n_ctx = 2048
        dialog.context_options = [2048, 4096, 8192]
        dialog.context_combo = FakeCombo()
        dialog.context_reason_label = FakeLabel()

        AIChatDialog.set_context_n_ctx(dialog, 4096)

        self.assertEqual("4096", dialog.context_combo.currentText())
        self.assertEqual(["2048", "4096", "8192"], dialog.context_combo.items)
        self.assertEqual("（15.6GB 内存 / 4GB 显存）", dialog.context_reason_label.text)

    def make_query_tab_stub(self):
        tab = QueryTab.__new__(QueryTab)
        tab.db = FakeDb()
        tab.permissions = {"base_info": True, "rewards": False, "family": False, "resume": False}
        tab.ai_dialog = None
        tab._last_query_conditions = {}
        tab.window = lambda: object()
        return tab

    def test_open_ai_chat_opens_dialog_without_progress_when_ollama_ready(self):
        tab = self.make_query_tab_stub()

        with patch.object(QueryTab, "open_ai_dialog") as open_dialog, \
                patch.object(QueryTab, "start_ollama_then_open_ai") as start_then_open, \
                patch.object(QueryTab, "build_full_ai_analysis_payload", return_value=payload()) as build_payload, \
                patch("ui.query.ensure_ollama_ready", return_value=FakeOllamaStatus(True)) as ensure_ready:
            QueryTab.open_ai_chat(tab)

        build_payload.assert_called_once_with({})
        ensure_ready.assert_called_once_with(start_if_needed=True)
        open_dialog.assert_called_once()
        start_then_open.assert_not_called()

    def test_open_ai_chat_warns_when_combined_ollama_start_fails(self):
        tab = self.make_query_tab_stub()

        with patch.object(QueryTab, "open_ai_dialog") as open_dialog, \
                patch.object(QueryTab, "start_ollama_then_open_ai") as start_then_open, \
                patch.object(QueryTab, "build_full_ai_analysis_payload", return_value=payload()) as build_payload, \
                patch("ui.query.ensure_ollama_ready", return_value=FakeOllamaStatus(False)) as ensure_ready, \
                patch("ui.query.QMessageBox.warning") as warning:
            QueryTab.open_ai_chat(tab)

        build_payload.assert_called_once_with({})
        ensure_ready.assert_called_once_with(start_if_needed=True)
        open_dialog.assert_not_called()
        start_then_open.assert_not_called()
        warning.assert_called_once()

    def test_open_ai_chat_uses_background_task_for_full_payload(self):
        tab = self.make_query_tab_stub()
        calls = {}

        class FakeMainWindow:
            def run_background_task(
                self,
                title,
                task_fn,
                on_success=None,
                on_error=None,
                progress_dialog_factory=None,
            ):
                calls["title"] = title
                calls["progress_dialog_factory"] = progress_dialog_factory
                calls["result"] = task_fn()
                on_success(calls["result"])

        tab.window = lambda: FakeMainWindow()

        with patch.object(QueryTab, "handle_ai_runtime_result") as handle_runtime, \
                patch.object(QueryTab, "build_full_ai_analysis_payload", return_value=payload()) as build_payload, \
                patch("ui.query.ensure_ollama_ready", return_value=FakeOllamaStatus(True)) as ensure_ready:
            QueryTab.open_ai_chat(tab)

        self.assertEqual("正在准备 AI 分析环境，请稍候...", calls["title"])
        self.assertTrue(callable(calls["progress_dialog_factory"]))
        build_payload.assert_called_once_with({})
        ensure_ready.assert_called_once_with(start_if_needed=True)
        handle_runtime.assert_called_once()
        runtime_result = handle_runtime.call_args.args[0]
        self.assertEqual(payload(), runtime_result["analysis_payload"])
        self.assertTrue(runtime_result["ollama_status"].service_available)

    def test_open_ai_chat_requires_query_rows_before_ollama_check(self):
        tab = self.make_query_tab_stub()
        tab._last_query_conditions = None

        with patch.object(QueryTab, "open_ai_dialog") as open_dialog, \
                patch.object(QueryTab, "start_ollama_then_open_ai") as start_then_open, \
                patch("ui.query.ensure_ollama_ready") as ensure_ready, \
                patch("ui.query.QMessageBox.warning") as warning:
            QueryTab.open_ai_chat(tab)

        ensure_ready.assert_not_called()
        open_dialog.assert_not_called()
        start_then_open.assert_not_called()
        warning.assert_called_once()

    def test_prepare_ai_chat_runtime_skips_ollama_when_payload_has_no_rows(self):
        tab = self.make_query_tab_stub()
        empty_payload = payload()
        for table in empty_payload["tables"].values():
            table["rows"] = []

        with patch.object(QueryTab, "build_full_ai_analysis_payload", return_value=empty_payload) as build_payload, \
                patch("ui.query.ensure_ollama_ready") as ensure_ready:
            result = QueryTab.prepare_ai_chat_runtime(tab, {})

        build_payload.assert_called_once_with({})
        ensure_ready.assert_not_called()
        self.assertEqual(empty_payload, result["analysis_payload"])
        self.assertIsNone(result["ollama_status"])

    def test_sync_open_ai_dialog_rebuilds_payload_with_latest_conditions(self):
        tab = self.make_query_tab_stub()
        dialog = FakeDialog()
        tab.ai_dialog = dialog
        tab._ai_sync_generation = 0
        new_payload = payload()

        def run_sync(task_fn, on_success=None, on_error=None):
            on_success(task_fn())

        tab._run_ai_sync_worker = run_sync

        with patch.object(QueryTab, "build_full_ai_analysis_payload", return_value=new_payload) as build_payload:
            synced = QueryTab.sync_open_ai_dialog(tab, {"name": "张三"})

        self.assertTrue(synced)
        self.assertTrue(dialog.sync_started)
        self.assertIs(dialog.applied_payload, new_payload)
        build_payload.assert_called_once_with({"name": "张三"})

    def test_sync_open_ai_dialog_defers_while_inference_running(self):
        tab = self.make_query_tab_stub()
        dialog = FakeDialog()
        dialog.is_inference_running = True
        tab.ai_dialog = dialog
        tab._pending_ai_sync_conditions = None

        with patch.object(QueryTab, "_run_ai_sync_worker") as run_worker:
            synced = QueryTab.sync_open_ai_dialog(tab, {"department": "研发部"})

        self.assertFalse(synced)
        self.assertTrue(dialog.sync_deferred)
        self.assertEqual({"department": "研发部"}, tab._pending_ai_sync_conditions)
        run_worker.assert_not_called()

    def test_sync_open_ai_dialog_ignores_stale_background_result(self):
        tab = self.make_query_tab_stub()
        dialog = FakeDialog()
        tab.ai_dialog = dialog
        tab._ai_sync_generation = 0
        callbacks = []

        def run_sync(task_fn, on_success=None, on_error=None):
            callbacks.append((task_fn, on_success))

        tab._run_ai_sync_worker = run_sync

        QueryTab.sync_open_ai_dialog(tab, {"name": "first"})
        QueryTab.sync_open_ai_dialog(tab, {"name": "second"})

        callbacks[0][1]({"stale": True})
        self.assertIsNone(dialog.applied_payload)

        callbacks[1][1]({"fresh": True})
        self.assertEqual({"fresh": True}, dialog.applied_payload)

    def test_query_tab_page_navigation_requeries_current_table(self):
        class FakePagedDb:
            def __init__(self):
                self.calls = []

            def search_personnel(self, **kwargs):
                self.calls.append(kwargs)
                table_name = kwargs["table_name"]
                return {
                    table_name: [{"marker": kwargs["offset"]}],
                    "total_count": 120,
                }

        db = FakePagedDb()
        tab = QueryTab.__new__(QueryTab)
        tab.db = db
        tab.page_size = 50
        tab.current_table_name = "family"
        tab.current_page = 1
        tab.current_results_dict = {"family": [{"marker": 0}]}
        tab.current_total_counts = {"base_info": 1, "family": 120}
        tab.current_results = []
        tab._last_query_conditions = {"name": "P1"}
        tab.display_current_page = lambda: None
        tab.update_table_buttons = lambda has_results: None

        QueryTab.go_to_page(tab, 3)

        self.assertEqual(3, tab.current_page)
        self.assertEqual({"marker": 100}, tab.current_results_dict["family"][0])
        self.assertEqual(
            {
                "table_name": "family",
                "limit": 50,
                "offset": 100,
                "name": "P1",
            },
            db.calls[0],
        )

    def test_start_ollama_then_open_ai_uses_main_window_progress(self):
        tab = self.make_query_tab_stub()
        calls = {}

        class FakeMainWindow:
            def run_background_task(
                self,
                title,
                task_fn,
                on_success=None,
                on_error=None,
                progress_dialog_factory=None,
            ):
                calls["title"] = title
                calls["progress_dialog_factory"] = progress_dialog_factory
                calls["result"] = task_fn()
                on_success(calls["result"])

        tab.window = lambda: FakeMainWindow()

        with patch.object(QueryTab, "open_ai_dialog") as open_dialog, \
                patch("ui.query.ensure_ollama_ready", return_value=FakeOllamaStatus(True)) as ensure_ready:
            QueryTab.start_ollama_then_open_ai(tab, payload())

        self.assertTrue(callable(calls["progress_dialog_factory"]))
        self.assertIn("ModernLoadingDialog", inspect.getsource(calls["progress_dialog_factory"]))
        ensure_ready.assert_called_once_with(start_if_needed=True)
        open_dialog.assert_called_once()

    def test_main_window_background_task_keeps_default_progress_dialog_path(self):
        source = inspect.getsource(MainWindow.run_background_task)

        self.assertIn("progress_dialog_factory=None", source)
        self.assertIn("QProgressDialog", source)
        self.assertIn("progress_dialog_factory(self, title)", source)

    def test_handle_ollama_started_for_ai_warns_when_start_failed(self):
        tab = self.make_query_tab_stub()

        with patch.object(QueryTab, "open_ai_dialog") as open_dialog, \
                patch("ui.query.QMessageBox.warning") as warning:
            QueryTab.handle_ollama_started_for_ai(tab, FakeOllamaStatus(False, "启动失败"), payload())

        open_dialog.assert_not_called()
        warning.assert_called_once()

    def test_open_ai_dialog_creates_independent_window_with_reference_widget(self):
        tab = self.make_query_tab_stub()
        analysis_payload = payload()
        created_dialog = FakeDialog()

        with patch("ui.ai_chat.AIChatDialog", return_value=created_dialog) as dialog_class:
            QueryTab.open_ai_dialog(tab, analysis_payload)

        dialog_class.assert_called_once_with(analysis_payload, reference_widget=tab)
        self.assertIs(tab.ai_dialog, created_dialog)
        self.assertEqual("智能分析 - 查询结果", created_dialog.title)
        self.assertTrue(created_dialog.shown)
        self.assertEqual(1, len(created_dialog.destroyed.callbacks))

    def test_close_ai_dialog_closes_current_window_and_clears_reference(self):
        tab = self.make_query_tab_stub()
        existing_dialog = FakeDialog()
        tab.ai_dialog = existing_dialog

        QueryTab.close_ai_dialog(tab)

        self.assertTrue(existing_dialog.closed)
        self.assertIsNone(tab.ai_dialog)

    def test_build_ai_analysis_payload_keeps_permitted_schema_with_empty_rows(self):
        results = {
            "base_info": [{"sequence": 1, "name": "张三"}],
            "family": [],
        }
        permissions = {
            "base_info": True,
            "rewards": False,
            "family": True,
            "resume": True,
        }

        analysis_payload = build_ai_analysis_payload(results, permissions)

        self.assertEqual({"base_info", "family", "resume"}, set(analysis_payload["schemas"].keys()))
        self.assertEqual({"base_info", "family", "resume"}, set(analysis_payload["tables"].keys()))
        self.assertNotIn("rewards", analysis_payload["schemas"])
        self.assertEqual([], analysis_payload["tables"]["family"]["rows"])
        self.assertEqual([], analysis_payload["tables"]["resume"]["rows"])
        self.assertIn({"name": "resume_text", "label": "简历信息"}, analysis_payload["schemas"]["resume"]["columns"])
        self.assertEqual("张三", analysis_payload["tables"]["base_info"]["rows"][0]["name"])

    def test_build_ai_analysis_payload_hides_internal_ids(self):
        results = {
            "rewards": [
                {
                    "id": 1,
                    "person_id": 2,
                    "sequence": 1,
                    "name": "寮犱笁",
                    "reward_name": "浼樼",
                }
            ]
        }
        permissions = {
            "base_info": False,
            "rewards": True,
            "family": False,
            "resume": False,
        }

        analysis_payload = build_ai_analysis_payload(results, permissions)

        row = analysis_payload["tables"]["rewards"]["rows"][0]
        self.assertEqual({"sequence": 1, "name": "寮犱笁", "reward_name": "浼樼"}, row)

    def test_filter_analysis_payload_by_columns_projects_schemas_labels_and_rows(self):
        filtered = filter_analysis_payload_by_columns(
            payload(),
            {
                "base_info": ["department"],
                "rewards": ["reward_name"],
            },
        )

        self.assertEqual({"base_info", "rewards"}, set(filtered["tables"].keys()))
        self.assertEqual(
            ["sequence", "name", "department"],
            list(filtered["tables"]["base_info"]["field_labels"].keys()),
        )
        self.assertEqual(
            ["sequence", "name", "reward_name"],
            list(filtered["tables"]["rewards"]["field_labels"].keys()),
        )
        self.assertEqual(
            {"sequence": 1, "name": "张三", "department": "研发部"},
            filtered["tables"]["base_info"]["rows"][0],
        )
        self.assertNotIn("current_grade", filtered["tables"]["base_info"]["rows"][0])
        self.assertEqual(
            ["sequence", "name", "department"],
            [column["name"] for column in filtered["schemas"]["base_info"]["columns"]],
        )

    def test_build_messages_uses_filtered_data_and_history(self):
        filtered_payload = filter_analysis_payload_by_columns(payload(), {"base_info": ["department"]})
        history = [
            {"role": "user", "content": "上一轮问题"},
            {"role": "assistant", "content": "上一轮回答"},
            {"role": "system", "content": "这条不应进入历史。"},
        ]

        messages = build_messages("张三在哪个部门？", filtered_payload, history)
        all_text = "\n".join(message["content"] for message in messages)

        self.assertEqual({"role": "user", "content": "上一轮问题"}, messages[1])
        self.assertEqual({"role": "assistant", "content": "上一轮回答"}, messages[2])
        self.assertIn('"department":"研发部"', all_text)
        self.assertNotIn("这条不应进入历史", all_text)
        self.assertNotIn("current_grade", all_text)
        self.assertIn("历史消息仅作为对话语境参考", messages[0]["content"])
        self.assertIn("必须绝对以“当前提供的数据”为准", messages[0]["content"])
        self.assertIn("<data>", messages[-1]["content"])
        self.assertIn("</data>", messages[-1]["content"])
        self.assertIn("<question>", messages[-1]["content"])
        self.assertIn("</question>", messages[-1]["content"])
        self.assertNotIn("筛选后的数据如下", messages[-1]["content"])
        self.assertNotIn("\n  ", messages[-1]["content"])

    def test_history_keeps_recent_ten_rounds_as_twenty_messages(self):
        history = []
        for index in range(12):
            history.append({"role": "user", "content": f"问题{index}"})
            history.append({"role": "assistant", "content": f"回答{index}"})

        messages = build_messages("继续分析", {"tables": {}}, history)
        retained_history = messages[1:-1]

        self.assertEqual(20, len(retained_history))
        self.assertEqual({"role": "user", "content": "问题2"}, retained_history[0])
        self.assertEqual({"role": "assistant", "content": "回答11"}, retained_history[-1])

    def test_ask_model_posts_selected_payload_directly_once(self):
        filtered = filter_analysis_payload_by_columns(payload(), {"base_info": ["department"]})

        with patch("services.ai_direct.requests.post", return_value=FakeResponse("正式分析结果")) as post:
            answer = ask_model("按部门分析", filtered, "qwen2:latest", n_ctx=8192, timeout=5)

        self.assertEqual("正式分析结果", answer)
        post.assert_called_once()
        body = post.call_args.kwargs["json"]
        prompt_text = "\n".join(message["content"] for message in body["messages"])
        self.assertEqual("qwen2:latest", body["model"])
        self.assertEqual({"num_ctx": 8192}, body["options"])
        self.assertIn('"sequence":1', prompt_text)
        self.assertIn('"name":"张三"', prompt_text)
        self.assertIn('"department":"研发部"', prompt_text)
        self.assertNotIn("current_grade", prompt_text)
        self.assertNotIn("一级", prompt_text)

    def test_ask_model_posts_dialog_history_once(self):
        history = [
            {"role": "user", "content": "上一轮问题"},
            {"role": "assistant", "content": "上一轮回答"},
        ]

        with patch("services.ai_direct.requests.post", return_value=FakeResponse("已结合历史回答。")) as post:
            answer = ask_model(
                "继续分析",
                payload(),
                "qwen2:latest",
                timeout=5,
                history_messages=history,
            )

        self.assertEqual("已结合历史回答。", answer)
        messages = post.call_args.kwargs["json"]["messages"]
        self.assertEqual(history[0], messages[1])
        self.assertEqual(history[1], messages[2])

    def test_ask_model_requires_model_name(self):
        with self.assertRaises(ValueError):
            ask_model("问题", payload(), "", n_ctx=4096)

    def make_chat_dialog_stub(self, model_name="qwen2:latest", question="按部门汇总"):
        dialog = AIChatDialog.__new__(AIChatDialog)
        dialog.analysis_payload = payload()
        dialog.input_field = FakeLineEdit(question)
        dialog.model_combo = FakeCombo(model_name)
        dialog.status_label = FakeLabel()
        dialog.model_status_label = FakeLabel()
        dialog.send_btn = FakeButton()
        dialog.refresh_btn = FakeButton()
        dialog.clear_btn = FakeButton()
        dialog.chat_history = FakeHistory()
        dialog.history_messages = []
        dialog.is_inference_running = False
        dialog.worker = None
        dialog.current_context_recommendation = ContextRecommendation(
            n_ctx=4096,
            reason="test",
            hardware=HardwareSnapshot(),
            max_n_ctx=4096,
        )
        dialog.current_context_n_ctx = 4096
        dialog.context_options = [2048, 4096]
        dialog._selected_payload_cache_key = None
        dialog._selected_payload_cache = None
        dialog._selected_data_json_cache_key = None
        dialog._selected_data_json_cache_value = None
        dialog._payload_token_cache_key = None
        dialog._payload_token_cache_value = None
        dialog._chat_display_messages = []
        dialog._streaming_message_index = None
        dialog._stream_render_pending = False
        dialog.stream_render_timer = FakeTimer()
        dialog.enabled_tables = {}
        dialog.column_checks = {
            "base_info": {
                "sequence": FakeCheck(True),
                "name": FakeCheck(True),
                "department": FakeCheck(True),
                "current_grade": FakeCheck(False),
            }
        }
        return dialog

    def test_start_inference_without_model_does_not_create_worker(self):
        dialog = self.make_chat_dialog_stub(model_name=MODEL_PLACEHOLDER)

        AIChatDialog.start_inference(dialog)

        self.assertIsNone(dialog.worker)
        self.assertFalse(dialog.input_field.clear_called)
        self.assertFalse(dialog.send_btn.enabled)
        self.assertTrue(dialog.input_field.enabled)

    def test_start_inference_uses_user_selected_context(self):
        dialog = self.make_chat_dialog_stub()
        dialog.current_context_n_ctx = 8192

        class FakeThread:
            def __init__(self, *_args):
                self.started = FakeSignal()
                self.finished = FakeSignal()
                self.start_called = False
                self.quit_called = False

            def quit(self):
                self.quit_called = True

            def start(self):
                self.start_called = True

            def deleteLater(self):
                pass

        with patch("ui.ai_chat.QThread", FakeThread), \
                patch.object(AIWorker, "moveToThread", lambda *_args: None):
            AIChatDialog.start_inference(dialog)

        self.assertIsNotNone(dialog.worker)
        self.assertEqual(8192, dialog.worker.n_ctx)
        self.assertIsNotNone(dialog.worker.analysis_data_json)
        self.assertTrue(dialog.worker_thread.start_called)

    def test_handle_error_does_not_store_error_as_assistant_history(self):
        dialog = self.make_chat_dialog_stub()
        dialog.history_messages = [{"role": "user", "content": "上一轮问题"}]
        dialog.is_inference_running = True
        dialog._pending_history_length = 1

        AIChatDialog.handle_error(dialog, "network failed")

        self.assertEqual([{"role": "user", "content": "上一轮问题"}], dialog.history_messages)
        self.assertIn("network failed", dialog.chat_history.items[-1])
        self.assertTrue(dialog.send_btn.enabled)

    def test_handle_error_rolls_back_unfinished_user_turn(self):
        dialog = self.make_chat_dialog_stub()
        dialog.history_messages = [
            {"role": "user", "content": "上一轮问题"},
            {"role": "assistant", "content": "上一轮回答"},
        ]
        dialog.is_inference_running = True
        dialog._pending_history_length = 2

        AIChatDialog.handle_error(dialog, "network failed")

        self.assertEqual(
            [
                {"role": "user", "content": "上一轮问题"},
                {"role": "assistant", "content": "上一轮回答"},
            ],
            dialog.history_messages,
        )
        self.assertIsNone(dialog._pending_history_length)

    def test_stream_error_discards_partial_and_rolls_back_history(self):
        dialog = self.make_chat_dialog_stub()
        dialog.history_messages = [{"role": "user", "content": "上一轮问题"}]
        dialog._pending_history_length = 1
        dialog.history_messages.append({"role": "user", "content": "本轮问题"})
        dialog.is_inference_running = True
        AIChatDialog.append_message(dialog, "user", "本轮问题")
        AIChatDialog.handle_stream_delta(dialog, "partial")

        AIChatDialog.handle_error(dialog, "network failed")

        self.assertEqual([{"role": "user", "content": "上一轮问题"}], dialog.history_messages)
        rendered = "\n".join(dialog.chat_history.items)
        self.assertNotIn("partial", rendered)
        self.assertIn("network failed", rendered)
        self.assertIn("本轮问题", rendered)
        self.assertTrue(dialog.send_btn.enabled)

    def test_ask_model_accepts_pre_serialized_data_json(self):
        serialized = '{"tables":[{"table_name":"base_info","table_label":"人员基本信息","fields":[],"rows":[]}]}'

        with patch("services.ai_direct.build_analysis_data_json", side_effect=AssertionError("should reuse")), \
                patch("services.ai_direct.requests.post", return_value=FakeResponse("正式分析结果")) as post:
            answer = ask_model(
                "按部门分析",
                payload(),
                "qwen2:latest",
                n_ctx=8192,
                timeout=5,
                analysis_data_json=serialized,
            )

        self.assertEqual("正式分析结果", answer)
        prompt_text = "\n".join(message["content"] for message in post.call_args.kwargs["json"]["messages"])
        self.assertIn(serialized, prompt_text)

    def test_ask_model_stream_posts_streaming_payload_and_emits_deltas(self):
        lines = [
            json.dumps({"message": {"content": "A"}, "done": False}, ensure_ascii=False),
            json.dumps({"message": {"content": "B"}, "done": False}, ensure_ascii=False),
            json.dumps({"done": True}, ensure_ascii=False),
        ]
        response = FakeStreamingResponse(lines)
        deltas = []

        with patch("services.ai_direct.requests.post", return_value=response) as post:
            answer = ask_model_stream(
                "按部门分析",
                payload(),
                "qwen2:latest",
                n_ctx=8192,
                timeout=5,
                on_delta=deltas.append,
                analysis_data_json='{"tables":[]}',
            )

        self.assertEqual("AB", answer)
        self.assertEqual(["A", "B"], deltas)
        body = post.call_args.kwargs["json"]
        self.assertEqual("qwen2:latest", body["model"])
        self.assertTrue(body["stream"])
        self.assertEqual({"num_ctx": 8192}, body["options"])
        self.assertTrue(post.call_args.kwargs["stream"])
        self.assertTrue(response.closed)

    def test_ask_model_stream_raises_chunk_error(self):
        response = FakeStreamingResponse([json.dumps({"error": "boom"}, ensure_ascii=False)])

        with patch("services.ai_direct.requests.post", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "boom"):
                ask_model_stream("按部门分析", payload(), "qwen2:latest", timeout=5)

        self.assertTrue(response.closed)


if __name__ == "__main__":
    unittest.main()
