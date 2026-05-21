import unittest

from services.ai_analysis import build_analysis_context
from services.ai_tools import AIToolContext, classify_intent, run_analysis_tools


FIELD_LABELS = {
    "sequence": "序号",
    "name": "姓名",
    "department": "部门",
    "education": "学历",
    "birth_date": "出生年月",
    "salary": "工资",
    "employment_type": "用工类型",
    "reward_name": "奖励名称",
    "reward_authority_type": "批准机关性质",
}


def build_context(rows, fields=None, table_name="base_info", table_label="人员基本信息"):
    fields = fields or ["sequence", "name", "department", "education"]
    return AIToolContext(table_name, rows, fields, FIELD_LABELS, table_label)


class AIToolCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            {"sequence": 1, "name": "张三", "department": "研发部", "education": "本科", "salary": "12000", "employment_type": "全职"},
            {"sequence": 2, "name": "李四", "department": "研发部", "education": "硕士", "salary": "9800", "employment_type": "兼职"},
            {"sequence": 3, "name": "王五", "department": "综合部", "education": "本科", "salary": "11000", "employment_type": "全职"},
        ]
        self.context = build_context(
            self.rows,
            ["sequence", "name", "department", "education", "salary", "employment_type"],
        )

    def run_tool(self, question, rows=None, fields=None, table_name="base_info", table_label="人员基本信息"):
        rows = rows or self.rows
        fields = fields or self.context.selected_fields
        context = build_context(rows, fields, table_name, table_label)
        return run_analysis_tools(
            table_name,
            rows,
            context.selected_fields,
            FIELD_LABELS,
            question,
            table_label,
            context,
        )

    def test_classify_intent_uses_new_intent_names(self):
        self.assertEqual("conditional_count", classify_intent("研发部有多少人？", self.context))
        self.assertEqual("count_total", classify_intent("当前结果共有多少人？", self.context))
        self.assertEqual("distribution", classify_intent("各部门分别多少人？", self.context))

    def test_total_count_compatibility_wrapper_uses_engine(self):
        result = self.run_tool("当前结果共有多少人？")

        self.assertEqual(["count_total"], result.called_tools)
        self.assertEqual("count_total", result.action_type)
        self.assertEqual(3, result.raw_count)
        self.assertIn("统计结果：3 人", result.context_markdown)
        self.assertIn("structured_pipeline", result.context_markdown)

    def test_conditional_count_filters_matching_rows(self):
        result = self.run_tool("研发部有多少人？")

        self.assertEqual("conditional_count", result.action_type)
        self.assertEqual(2, result.raw_count)
        self.assertIn("部门 = 研发部", result.context_markdown)
        self.assertIn("统计结果：2 人", result.context_markdown)

    def test_distribution_can_filter_by_non_group_field_value(self):
        rows = [
            {"sequence": 1, "name": "张三", "department": "研发部", "education": "本科"},
            {"sequence": 2, "name": "李四", "department": "研发部", "education": "硕士"},
            {"sequence": 3, "name": "王五", "department": "销售部", "education": "本科"},
            {"sequence": 4, "name": "赵六", "department": "销售部", "education": "本科"},
        ]
        result = self.run_tool(
            "各部门的本科学历人员分布是怎样的？",
            rows=rows,
            fields=["sequence", "name", "department", "education"],
        )

        self.assertEqual("distribution", result.action_type)
        self.assertEqual(3, result.raw_count)
        self.assertIn("统计口径：学历 = 本科", result.context_markdown)
        self.assertIn("| 销售部 | 2 | 66.7% |", result.context_markdown)
        self.assertIn("| 研发部 | 1 | 33.3% |", result.context_markdown)

    def test_compare_and_boolean_are_deterministic(self):
        aggregate = self.run_tool("谁的工资最高？")
        boolean = self.run_tool("张三是不是全职？")

        self.assertEqual("compare", aggregate.action_type)
        self.assertEqual(3, aggregate.raw_count)
        self.assertIn("张三", aggregate.context_markdown)
        self.assertIn("12000", aggregate.context_markdown)
        self.assertEqual("compare", boolean.action_type)
        self.assertIn("是。依据", boolean.context_markdown)

    def test_missing_evidence_returns_clarification_not_guess(self):
        result = self.run_tool("张三是不是合同制？")

        self.assertEqual("clarify", result.action_type)
        self.assertIn("请补充要确认的字段或取值", result.context_markdown)

    def test_broad_list_query_is_guarded_and_truncated(self):
        rows = [
            {"sequence": index, "name": f"人员{index}", "department": "研发部", "education": "本科"}
            for index in range(1, 51)
        ]
        result = self.run_tool("列出所有本科人员名单", rows=rows, fields=["sequence", "name", "department", "education"])

        self.assertEqual("list_records", result.action_type)
        self.assertEqual(50, result.raw_count)
        self.assertIn("共匹配 50 条记录", result.context_markdown)
        self.assertIn("仅展示前 20 条", result.context_markdown)
        self.assertNotIn("人员50", result.context_markdown)

    def test_tool_augmented_context_uses_structured_pipeline_result(self):
        result = self.run_tool("各部门分别多少人？")
        compact = build_analysis_context(
            "base_info",
            self.rows,
            self.context.selected_fields,
            FIELD_LABELS,
            "各部门分别多少人？",
            "人员基本信息",
            tool_result=result,
        )

        self.assertIn("## 工具调用结果", compact)
        self.assertIn("structured_pipeline", compact)
        self.assertNotIn("## 明细样本（前 30 行，仅用于举例）", compact)


if __name__ == "__main__":
    unittest.main()
