import inspect
import unittest

from ui.ai_chat import AIChatDialog, clean_ai_response


class AIChatFlowTests(unittest.TestCase):
    def test_start_inference_does_not_short_circuit_tool_answers(self):
        source = inspect.getsource(AIChatDialog.start_inference)

        self.assertNotIn("direct_answer", source)
        self.assertNotIn("round_context", source)
        self.assertIn("AIWorker", source)
        self.assertIn("self.query_engine", inspect.getsource(AIChatDialog.__init__))
        self.assertIn("self.session_state", source)

    def test_clean_count_response_removes_prompt_leakage(self):
        response = (
            "严格输出要求指定一句话、列表、表格或是/否回答，以它为准。\n"
            "最终答案\n"
            "用户的问题是询问有多少条记录属于中央机关作为批准机关的情况。"
            "根据工具调用结果中的count_rows统计，满足条件的条数为2条。"
        )

        cleaned = clean_ai_response(response, "count")

        self.assertEqual("满足条件的条数为2条。", cleaned)
        self.assertNotIn("严格输出要求", cleaned)
        self.assertNotIn("最终答案", cleaned)
        self.assertNotIn("工具调用结果", cleaned)

    def test_clean_boolean_response_keeps_yes_no_shape(self):
        response = "最终答案\n根据工具调用结果可知，是，张三的用工类型为全职。"

        cleaned = clean_ai_response(response, "boolean")

        self.assertTrue(cleaned.startswith("是"))
        self.assertNotIn("最终答案", cleaned)
        self.assertNotIn("工具调用结果", cleaned)

    def test_clean_list_response_keeps_markdown_table(self):
        response = "最终答案\n| 姓名 | 部门 |\n| --- | --- |\n| 张三 | 研发部 |"

        cleaned = clean_ai_response(response, "list")

        self.assertIn("| 姓名 | 部门 |", cleaned)
        self.assertIn("| 张三 | 研发部 |", cleaned)
        self.assertNotIn("最终答案", cleaned)


if __name__ == "__main__":
    unittest.main()
