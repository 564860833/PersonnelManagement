import inspect
import unittest
from unittest.mock import patch

from services.ai_direct import ask_model, build_messages
from ui.ai_chat import AIChatDialog, AIWorker


FIELD_LABELS = {
    "sequence": "序号",
    "name": "姓名",
    "department": "部门",
}


def payload():
    return {
        "table_name": "base_info",
        "table_label": "人员基本信息",
        "rows": [
            {"sequence": 1, "name": "张三", "department": "研发部"},
            {"sequence": 2, "name": "李四", "department": "综合部"},
        ],
        "selected_fields": ["sequence", "name", "department"],
        "field_labels": FIELD_LABELS,
    }


class FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {"message": {"content": "已收到表数据。"}}


class AIChatDirectModelTests(unittest.TestCase):
    def test_chat_dialog_no_longer_uses_structured_pipeline(self):
        source = "\n".join(
            [
                inspect.getsource(AIChatDialog),
                inspect.getsource(AIWorker),
                inspect.getsource(AIChatDialog.start_inference),
            ]
        )

        self.assertIn("AIWorker", source)
        self.assertIn("ask_model", source)
        self.assertNotIn("AIQueryEngine", source)
        self.assertNotIn("AIConversationState", source)
        self.assertNotIn("session_state", source)
        self.assertNotIn("clean_ai_response", source)

    def test_build_messages_imports_current_table_data(self):
        messages = build_messages("张三在哪个部门？", payload())
        all_text = "\n".join(message["content"] for message in messages)

        self.assertEqual("system", messages[0]["role"])
        self.assertEqual("user", messages[1]["role"])
        self.assertIn("人员基本信息 (base_info)", all_text)
        self.assertIn('"field": "name"', all_text)
        self.assertIn('"label": "姓名"', all_text)
        self.assertIn('"name": "张三"', all_text)
        self.assertIn('"name": "李四"', all_text)
        self.assertIn("张三在哪个部门？", all_text)
        for old_pipeline_text in ("规则", "统计口径", "工具调用", "QueryPlan"):
            self.assertNotIn(old_pipeline_text, all_text)

    def test_build_messages_includes_recent_dialog_history(self):
        history = [
            {"role": "user", "content": "张三在哪个部门？"},
            {"role": "assistant", "content": "张三在研发部。"},
            {"role": "system", "content": "这条不应进入历史。"},
            {"role": "assistant", "content": "  "},
        ]

        messages = build_messages("那他叫什么名字？", payload(), history)

        self.assertEqual("system", messages[0]["role"])
        self.assertEqual({"role": "user", "content": "张三在哪个部门？"}, messages[1])
        self.assertEqual({"role": "assistant", "content": "张三在研发部。"}, messages[2])
        self.assertEqual("user", messages[-1]["role"])
        self.assertIn("那他叫什么名字？", messages[-1]["content"])
        self.assertIn('"name": "张三"', messages[-1]["content"])
        self.assertNotIn("这条不应进入历史", "\n".join(message["content"] for message in messages))

    def test_build_messages_keeps_only_last_ten_rounds(self):
        history = []
        for index in range(12):
            history.append({"role": "user", "content": f"问题{index}"})
            history.append({"role": "assistant", "content": f"回答{index}"})

        messages = build_messages("继续分析", payload(), history)
        retained_history = messages[1:-1]

        self.assertEqual(20, len(retained_history))
        self.assertEqual({"role": "user", "content": "问题2"}, retained_history[0])
        self.assertEqual({"role": "assistant", "content": "回答11"}, retained_history[-1])

    def test_ask_model_posts_to_ollama_chat(self):
        with patch("services.ai_direct.requests.post", return_value=FakeResponse()) as post:
            answer = ask_model("当前表有谁？", payload(), "qwen2:latest", n_ctx=8192, timeout=5)

        self.assertEqual("已收到表数据。", answer)
        post.assert_called_once()
        url = post.call_args.args[0]
        body = post.call_args.kwargs["json"]
        self.assertTrue(url.endswith("/api/chat"))
        self.assertEqual("qwen2:latest", body["model"])
        self.assertFalse(body["stream"])
        self.assertEqual({"num_ctx": 8192}, body["options"])
        self.assertEqual("当前表有谁？", body["messages"][1]["content"].split("用户问题：\n", 1)[1])

    def test_ask_model_posts_dialog_history_to_ollama_chat(self):
        history = [
            {"role": "user", "content": "张三在哪个部门？"},
            {"role": "assistant", "content": "张三在研发部。"},
        ]

        with patch("services.ai_direct.requests.post", return_value=FakeResponse()) as post:
            answer = ask_model(
                "那他叫什么名字？",
                payload(),
                "qwen2:latest",
                timeout=5,
                history_messages=history,
            )

        self.assertEqual("已收到表数据。", answer)
        body = post.call_args.kwargs["json"]
        self.assertEqual(history[0], body["messages"][1])
        self.assertEqual(history[1], body["messages"][2])
        self.assertIn('"name": "张三"', body["messages"][-1]["content"])
        self.assertEqual("那他叫什么名字？", body["messages"][-1]["content"].split("用户问题：\n", 1)[1])

    def test_ask_model_requires_model_name(self):
        with self.assertRaises(ValueError):
            ask_model("问题", payload(), "", n_ctx=4096)


if __name__ == "__main__":
    unittest.main()
