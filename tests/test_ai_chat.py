import inspect
import json
import unittest
from unittest.mock import patch

from services.ai_context import ContextRecommendation, HardwareSnapshot
from services.ai_direct import (
    SELECTION_FAILURE_MESSAGE,
    ask_model,
    build_messages,
    build_schema_selection_messages,
)
from ui.ai_chat import AIChatDialog, AIWorker, MODEL_PLACEHOLDER, render_message_html
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


class FakeOllamaStatus:
    def __init__(self, service_available, message=""):
        self.service_available = service_available
        self.message = message


class FakeDb:
    def get_assessment_years(self):
        return []


class FakeWidget:
    def __init__(self):
        self.enabled = None

    def setEnabled(self, enabled):
        self.enabled = enabled


class FakeButton(FakeWidget):
    pass


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
    def __init__(self, text):
        super().__init__()
        self._text = text

    def currentText(self):
        return self._text


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

    def append(self, html):
        self.items.append(html)

    def verticalScrollBar(self):
        return self.scroll_bar


class AIChatDirectModelTests(unittest.TestCase):
    def test_chat_dialog_no_longer_uses_structured_pipeline(self):
        source = "\n".join(
            [
                inspect.getsource(AIChatDialog),
                inspect.getsource(AIWorker),
                inspect.getsource(AIChatDialog.start_inference),
                inspect.getsource(AIChatDialog.refresh_models),
            ]
        )

        self.assertIn("AIWorker", source)
        self.assertIn("ask_model", source)
        self.assertIn("recommend_context_length", source)
        self.assertIn("ctx_label", source)
        self.assertNotIn("ctx_combo", source)
        self.assertNotIn("startup_progress", source)
        self.assertNotIn("OllamaStartupWorker", source)
        self.assertNotIn("ensure_ollama_ready(start_if_needed=True)", source)
        self.assertNotIn("AIQueryEngine", source)
        self.assertNotIn("AIConversationState", source)
        self.assertNotIn("session_state", source)
        self.assertNotIn("clean_ai_response", source)

    def test_ai_worker_passes_auto_context_to_direct_model(self):
        history = [{"role": "user", "content": "上一轮问题"}]
        worker = AIWorker("继续分析", payload(), "qwen2:latest", 8192, history)

        with patch("ui.ai_chat.ask_model", return_value="OK") as ask:
            worker.run()

        ask.assert_called_once()
        args = ask.call_args.args
        kwargs = ask.call_args.kwargs
        self.assertEqual("继续分析", args[0])
        self.assertEqual("qwen2:latest", args[2])
        self.assertEqual(8192, args[3])
        self.assertEqual(history, kwargs["history_messages"])

    def test_ai_worker_retries_context_errors_by_steps_until_device_limit(self):
        worker = AIWorker("继续分析", payload(), "qwen2:latest", 2048, max_n_ctx=32768)
        changed_contexts = []
        worker.context_changed.connect(changed_contexts.append)

        with patch(
            "ui.ai_chat.ask_model",
            side_effect=[
                RuntimeError("context length exceeded"),
                RuntimeError("context length exceeded"),
                RuntimeError("context length exceeded"),
                RuntimeError("context length exceeded"),
                "OK",
            ],
        ) as ask:
            worker.run()

        self.assertEqual(5, ask.call_count)
        self.assertEqual(2048, ask.call_args_list[0].args[3])
        self.assertEqual(4096, ask.call_args_list[1].args[3])
        self.assertEqual(8192, ask.call_args_list[2].args[3])
        self.assertEqual(16384, ask.call_args_list[3].args[3])
        self.assertEqual(32768, ask.call_args_list[4].args[3])
        self.assertEqual([4096, 8192, 16384, 32768], changed_contexts)

    def test_ai_worker_does_not_retry_beyond_device_limit(self):
        worker = AIWorker("继续分析", payload(), "qwen2:latest", 4096, max_n_ctx=4096)

        with patch("ui.ai_chat.ask_model", side_effect=RuntimeError("context length exceeded")) as ask, \
                patch("ui.ai_chat.logger.exception"):
            worker.run()

        ask.assert_called_once()

    def test_ai_worker_stops_after_reaching_device_limit(self):
        worker = AIWorker("继续分析", payload(), "qwen2:latest", 2048, max_n_ctx=32768)

        with patch("ui.ai_chat.ask_model", side_effect=RuntimeError("context length exceeded")) as ask, \
                patch("ui.ai_chat.logger.exception"):
            worker.run()

        self.assertEqual(5, ask.call_count)
        self.assertEqual(2048, ask.call_args_list[0].args[3])
        self.assertEqual(4096, ask.call_args_list[1].args[3])
        self.assertEqual(8192, ask.call_args_list[2].args[3])
        self.assertEqual(16384, ask.call_args_list[3].args[3])
        self.assertEqual(32768, ask.call_args_list[4].args[3])

    def test_ai_worker_does_not_retry_non_context_errors(self):
        worker = AIWorker("继续分析", payload(), "qwen2:latest", 2048, max_n_ctx=16384)

        with patch("ui.ai_chat.ask_model", side_effect=RuntimeError("network failed")) as ask, \
                patch("ui.ai_chat.logger.exception"):
            worker.run()

        ask.assert_called_once()

    def test_ai_worker_emits_failed_for_model_errors(self):
        worker = AIWorker("继续分析", payload(), "qwen2:latest", 2048, max_n_ctx=16384)
        failures = []
        finished = []
        worker.failed.connect(failures.append)
        worker.finished.connect(finished.append)

        with patch("ui.ai_chat.ask_model", side_effect=RuntimeError("network failed")), \
                patch("ui.ai_chat.logger.exception"):
            worker.run()

        self.assertEqual(["network failed"], failures)
        self.assertEqual([], finished)

    def test_user_message_renders_as_right_blue_bubble(self):
        rendered = render_message_html("user", "<script>alert(1)</script>")

        self.assertIn('table width="100%"', rendered)
        self.assertIn('width="24%"', rendered)
        self.assertIn('width="76%" align="right"', rendered)
        self.assertIn("background-color: #1E5AA8", rendered)
        self.assertIn("color: #FFFFFF", rendered)
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
        self.assertIn('<th style="border: 1px solid #D0D7DE;', rendered)
        self.assertIn('<td style="border: 1px solid #D0D7DE;', rendered)

    def test_error_message_renders_as_left_red_bubble(self):
        rendered = render_message_html("assistant", "network failed", is_error=True)

        self.assertIn('width="76%" align="left"', rendered)
        self.assertIn("background-color: #FFF1F0", rendered)
        self.assertIn("color: #8F1D16", rendered)
        self.assertIn("network failed", rendered)

    def test_context_label_updates_with_retry_context_and_same_reason(self):
        dialog = AIChatDialog.__new__(AIChatDialog)
        dialog.current_context_recommendation = ContextRecommendation(
            n_ctx=2048,
            reason="15.6GB 内存 / 4GB 显存",
            hardware=HardwareSnapshot(),
            max_n_ctx=8192,
        )

        class FakeLabel:
            def __init__(self):
                self.text = ""

            def setText(self, text):
                self.text = text

        dialog.ctx_label = FakeLabel()
        AIChatDialog.update_context_label(dialog, 4096)

        self.assertEqual("4096（15.6GB 内存 / 4GB 显存）", dialog.ctx_label.text)

    def make_query_tab_stub(self):
        tab = QueryTab.__new__(QueryTab)
        tab.db = FakeDb()
        tab.current_results_dict = {"base_info": [{"sequence": 1, "name": "张三"}]}
        tab.permissions = {"base_info": True, "rewards": False, "family": False, "resume": False}
        tab.ai_dialog = None
        return tab

    def test_open_ai_chat_opens_dialog_without_progress_when_ollama_ready(self):
        tab = self.make_query_tab_stub()

        with patch.object(QueryTab, "open_ai_dialog") as open_dialog, \
                patch.object(QueryTab, "start_ollama_then_open_ai") as start_then_open, \
                patch("ui.query.ensure_ollama_ready", return_value=FakeOllamaStatus(True)) as ensure_ready:
            QueryTab.open_ai_chat(tab)

        ensure_ready.assert_called_once_with(start_if_needed=False)
        open_dialog.assert_called_once()
        start_then_open.assert_not_called()

    def test_open_ai_chat_uses_progress_task_when_ollama_not_ready(self):
        tab = self.make_query_tab_stub()

        with patch.object(QueryTab, "open_ai_dialog") as open_dialog, \
                patch.object(QueryTab, "start_ollama_then_open_ai") as start_then_open, \
                patch("ui.query.ensure_ollama_ready", return_value=FakeOllamaStatus(False)):
            QueryTab.open_ai_chat(tab)

        open_dialog.assert_not_called()
        start_then_open.assert_called_once()

    def test_open_ai_chat_requires_query_rows_before_ollama_check(self):
        tab = self.make_query_tab_stub()
        tab.current_results_dict = {}

        with patch.object(QueryTab, "open_ai_dialog") as open_dialog, \
                patch.object(QueryTab, "start_ollama_then_open_ai") as start_then_open, \
                patch("ui.query.ensure_ollama_ready") as ensure_ready, \
                patch("ui.query.QMessageBox.warning") as warning:
            QueryTab.open_ai_chat(tab)

        ensure_ready.assert_not_called()
        open_dialog.assert_not_called()
        start_then_open.assert_not_called()
        warning.assert_called_once()
        self.assertIn("请先查询或查看全部", warning.call_args.args[2])

    def make_chat_dialog_stub(self, model_name="qwen2:latest", question="按部门汇总"):
        dialog = AIChatDialog.__new__(AIChatDialog)
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
        return dialog

    def test_start_inference_without_model_does_not_create_worker(self):
        dialog = self.make_chat_dialog_stub(model_name=MODEL_PLACEHOLDER)

        AIChatDialog.start_inference(dialog)

        self.assertIsNone(dialog.worker)
        self.assertFalse(dialog.input_field.clear_called)
        self.assertEqual("未选择可用模型，无法发送分析请求。", dialog.status_label.text)
        self.assertFalse(dialog.send_btn.enabled)
        self.assertTrue(dialog.input_field.enabled)

    def test_handle_error_does_not_store_error_as_assistant_history(self):
        dialog = self.make_chat_dialog_stub()
        dialog.history_messages = [{"role": "user", "content": "上一轮问题"}]
        dialog.is_inference_running = True

        AIChatDialog.handle_error(dialog, "network failed")

        self.assertEqual([{"role": "user", "content": "上一轮问题"}], dialog.history_messages)
        self.assertIn("network failed", dialog.chat_history.items[-1])
        self.assertEqual("分析失败：network failed", dialog.status_label.text)
        self.assertTrue(dialog.send_btn.enabled)

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

        self.assertEqual("正在启动 Ollama，请稍候...", calls["title"])
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

    def test_schema_selection_messages_do_not_include_table_rows(self):
        messages = build_schema_selection_messages("按部门分析人员情况", payload())
        all_text = "\n".join(message["content"] for message in messages)

        self.assertEqual("system", messages[0]["role"])
        self.assertEqual("user", messages[-1]["role"])
        self.assertIn('"schemas"', all_text)
        self.assertIn('"table_name": "base_info"', all_text)
        self.assertIn('"name": "department"', all_text)
        self.assertNotIn('"rows"', all_text)
        self.assertNotIn("张三", all_text)
        self.assertNotIn("研发部", all_text)

    def test_build_messages_uses_filtered_data_and_history(self):
        filtered_payload = {
            "tables": {
                "base_info": {
                    "table_name": "base_info",
                    "table_label": "人员基本信息",
                    "field_labels": {
                        "sequence": "序号",
                        "name": "姓名",
                        "department": "部门",
                    },
                    "rows": [{"sequence": 1, "name": "张三", "department": "研发部"}],
                }
            }
        }
        history = [
            {"role": "user", "content": "上一轮问题"},
            {"role": "assistant", "content": "上一轮回答"},
            {"role": "system", "content": "这条不应进入历史。"},
        ]

        messages = build_messages("张三在哪个部门？", filtered_payload, history)
        all_text = "\n".join(message["content"] for message in messages)

        self.assertEqual({"role": "user", "content": "上一轮问题"}, messages[1])
        self.assertEqual({"role": "assistant", "content": "上一轮回答"}, messages[2])
        self.assertIn("筛选后的数据", all_text)
        self.assertIn("只能基于“筛选后的数据”回答", all_text)
        self.assertIn('"department": "研发部"', all_text)
        self.assertNotIn("这条不应进入历史", all_text)
        self.assertNotIn("current_grade", all_text)

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

    def test_ask_model_uses_two_stage_filtered_analysis(self):
        selection = json.dumps(
            {
                "tables": [
                    {"table_name": "base_info", "columns": ["department"]},
                    {"table_name": "rewards", "columns": ["reward_name"]},
                ]
            },
            ensure_ascii=False,
        )

        with patch(
            "services.ai_direct.requests.post",
            side_effect=[FakeResponse(selection), FakeResponse("正式分析结果")],
        ) as post:
            answer = ask_model("按部门和奖励分析人员情况", payload(), "qwen2:latest", n_ctx=8192, timeout=5)

        self.assertEqual("正式分析结果", answer)
        self.assertEqual(2, post.call_count)

        first_body = post.call_args_list[0].kwargs["json"]
        first_text = "\n".join(message["content"] for message in first_body["messages"])
        self.assertIn('"schemas"', first_text)
        self.assertNotIn('"rows"', first_text)
        self.assertNotIn("张三", first_text)
        self.assertNotIn("研发部", first_text)

        second_body = post.call_args_list[1].kwargs["json"]
        second_text = "\n".join(message["content"] for message in second_body["messages"])
        self.assertEqual("qwen2:latest", second_body["model"])
        self.assertEqual({"num_ctx": 8192}, second_body["options"])
        self.assertIn('"sequence": 1', second_text)
        self.assertIn('"name": "张三"', second_text)
        self.assertIn('"department": "研发部"', second_text)
        self.assertIn('"table_name": "rewards"', second_text)
        self.assertIn('"rows": []', second_text)
        self.assertNotIn("current_grade", second_text)
        self.assertNotIn("一级", second_text)

    def test_ask_model_drops_invalid_tables_and_columns(self):
        selection = json.dumps(
            {
                "tables": [
                    {"table_name": "unknown", "columns": ["name"]},
                    {"table_name": "base_info", "columns": ["not_real"]},
                ]
            },
            ensure_ascii=False,
        )

        with patch("services.ai_direct.requests.post", return_value=FakeResponse(selection)) as post:
            answer = ask_model("分析不存在的字段", payload(), "qwen2:latest", timeout=5)

        self.assertEqual(SELECTION_FAILURE_MESSAGE, answer)
        post.assert_called_once()

    def test_ask_model_posts_dialog_history_to_both_stages(self):
        selection = json.dumps(
            {"tables": [{"table_name": "base_info", "columns": ["department"]}]},
            ensure_ascii=False,
        )
        history = [
            {"role": "user", "content": "上一轮问题"},
            {"role": "assistant", "content": "上一轮回答"},
        ]

        with patch(
            "services.ai_direct.requests.post",
            side_effect=[FakeResponse(selection), FakeResponse("已结合历史回答。")],
        ) as post:
            answer = ask_model(
                "继续分析",
                payload(),
                "qwen2:latest",
                timeout=5,
                history_messages=history,
            )

        self.assertEqual("已结合历史回答。", answer)
        first_messages = post.call_args_list[0].kwargs["json"]["messages"]
        second_messages = post.call_args_list[1].kwargs["json"]["messages"]
        self.assertEqual(history[0], first_messages[1])
        self.assertEqual(history[1], first_messages[2])
        self.assertEqual(history[0], second_messages[1])
        self.assertEqual(history[1], second_messages[2])

    def test_ask_model_requires_model_name(self):
        with self.assertRaises(ValueError):
            ask_model("问题", payload(), "", n_ctx=4096)


if __name__ == "__main__":
    unittest.main()
