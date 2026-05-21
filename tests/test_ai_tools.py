import unittest

from services.ai_analysis import build_analysis_context
from services.ai_retrieval import LocalRetrievalIndex
from services.ai_tools import AIToolContext, run_analysis_tools


FIELD_LABELS = {
    "sequence": "序号",
    "name": "姓名",
    "department": "部门",
    "seniority": "资历",
    "education": "学历",
    "birth_date": "出生年月",
}


class FailingEmbeddingClient:
    def embed_texts(self, texts):
        return None


def build_context(rows):
    retrieval = LocalRetrievalIndex(
        rows,
        ["sequence", "name", "department", "seniority", "birth_date"],
        FIELD_LABELS,
        embedding_client=FailingEmbeddingClient(),
    )
    return AIToolContext(
        "base_info",
        rows,
        ["sequence", "name", "department", "seniority", "birth_date"],
        FIELD_LABELS,
        "人员基本信息",
        retrieval_index=retrieval,
    )


class AIToolRoutingTests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            {"sequence": 1, "name": "张三", "department": "研发部", "seniority": "资深", "birth_date": "1980.01"},
            {"sequence": 2, "name": "李四", "department": "研发部", "seniority": "普通", "birth_date": "1990.05"},
            {"sequence": 3, "name": "王五", "department": "综合部", "seniority": "普通", "birth_date": ""},
        ]
        self.context = build_context(self.rows)

    def test_development_department_matches_research_department(self):
        result = run_analysis_tools(
            "base_info",
            self.rows,
            self.context.selected_fields,
            FIELD_LABELS,
            "开发部的人有哪些？",
            "人员基本信息",
            self.context,
        )

        self.assertIn("semantic_search", result.called_tools)
        self.assertIn("list_rows", result.called_tools)
        self.assertIn("研发部", result.context_markdown)
        self.assertIn("张三", result.context_markdown)
        self.assertIn("李四", result.context_markdown)

    def test_old_employee_matches_senior_value(self):
        result = run_analysis_tools(
            "base_info",
            self.rows,
            self.context.selected_fields,
            FIELD_LABELS,
            "有哪些老员工？",
            "人员基本信息",
            self.context,
        )

        self.assertIn("资深", result.context_markdown)
        self.assertIn("张三", result.context_markdown)
        self.assertIn("同义词匹配", result.context_markdown)

    def test_distribution_question_only_calls_distribution(self):
        result = run_analysis_tools(
            "base_info",
            self.rows,
            self.context.selected_fields,
            FIELD_LABELS,
            "各部门分别多少人？",
            "人员基本信息",
            self.context,
        )

        self.assertEqual(["distribution"], result.called_tools)
        self.assertIn("研发部", result.context_markdown)
        self.assertIn("66.7%", result.context_markdown)
        self.assertNotIn("### list_rows", result.context_markdown)
        self.assertNotIn("## 全量明细", result.context_markdown)

    def test_distribution_can_filter_by_non_group_field_value(self):
        rows = [
            {"sequence": 1, "name": "张三", "department": "研发部", "education": "本科"},
            {"sequence": 2, "name": "李四", "department": "研发部", "education": "硕士"},
            {"sequence": 3, "name": "王五", "department": "销售部", "education": "本科"},
            {"sequence": 4, "name": "赵六", "department": "销售部", "education": "本科"},
        ]
        retrieval = LocalRetrievalIndex(
            rows,
            ["sequence", "name", "department", "education"],
            FIELD_LABELS,
            embedding_client=FailingEmbeddingClient(),
        )
        context = AIToolContext(
            "base_info",
            rows,
            ["sequence", "name", "department", "education"],
            FIELD_LABELS,
            "人员基本信息",
            retrieval_index=retrieval,
        )

        result = run_analysis_tools(
            "base_info",
            rows,
            context.selected_fields,
            FIELD_LABELS,
            "各部门的本科学历人员分布是怎样的？",
            "人员基本信息",
            context,
        )

        self.assertEqual(["distribution"], result.called_tools)
        self.assertIn("过滤条件：学历 = 本科", result.context_markdown)
        self.assertIn("过滤后总数：3 条", result.context_markdown)
        self.assertIn("| 部门 | 研发部 | 1 | 33.3% |", result.context_markdown)
        self.assertIn("| 部门 | 销售部 | 2 | 66.7% |", result.context_markdown)

    def test_total_count_question_gets_direct_tool_answer(self):
        result = run_analysis_tools(
            "base_info",
            self.rows,
            self.context.selected_fields,
            FIELD_LABELS,
            "共有多少人？",
            "人员基本信息",
            self.context,
        )

        self.assertEqual(["count_rows"], result.called_tools)
        self.assertIn("共有 **3 人**", result.direct_answer)

    def test_name_question_prefers_exact_name_match(self):
        result = run_analysis_tools(
            "base_info",
            self.rows,
            self.context.selected_fields,
            FIELD_LABELS,
            "张三的情况是什么？",
            "人员基本信息",
            self.context,
        )

        self.assertIn("张三", result.context_markdown)
        self.assertIn("精确取值匹配", result.context_markdown)
        self.assertIn("list_rows", result.called_tools)

    def test_embedding_failure_degrades_to_lightweight_matching(self):
        result = run_analysis_tools(
            "base_info",
            self.rows,
            self.context.selected_fields,
            FIELD_LABELS,
            "开发部的人有哪些？",
            "人员基本信息",
            self.context,
        )

        self.assertTrue(result.retrieval_degraded)
        self.assertIn("语义检索状态：降级", result.context_markdown)
        self.assertIn("研发部", result.context_markdown)

    def test_field_stats_and_date_range_are_deterministic(self):
        stats = run_analysis_tools(
            "base_info",
            self.rows,
            self.context.selected_fields,
            FIELD_LABELS,
            "出生年月范围和空值情况",
            "人员基本信息",
            self.context,
        )

        self.assertIn("date_range", stats.called_tools)
        self.assertIn("field_stats", stats.called_tools)
        self.assertIn("1980.01", stats.context_markdown)
        self.assertIn("1990.05", stats.context_markdown)
        self.assertIn("空值数", stats.context_markdown)

    def test_tool_augmented_context_stays_compact_for_large_data(self):
        rows = [
            {"sequence": index, "name": f"人员{index}", "department": "研发部", "seniority": "普通"}
            for index in range(1, 121)
        ]
        context = build_context(rows)
        tool_result = run_analysis_tools(
            "base_info",
            rows,
            context.selected_fields,
            FIELD_LABELS,
            "各部门分别多少人？",
            "人员基本信息",
            context,
        )
        compact = build_analysis_context(
            "base_info",
            rows,
            context.selected_fields,
            FIELD_LABELS,
            "各部门分别多少人？",
            "人员基本信息",
            tool_result=tool_result,
        )

        self.assertIn("## 工具调用结果", compact)
        self.assertIn("上下文策略：本轮只提供程序按问题调用工具后的结果", compact)
        self.assertNotIn("## 明细样本（前 30 行，仅用于举例）", compact)
        self.assertNotIn("人员120", compact)

    def test_broad_list_query_includes_total_and_truncation_lock(self):
        rows = [
            {"sequence": index, "name": f"人员{index}", "department": "研发部", "seniority": "资深"}
            for index in range(1, 51)
        ]
        context = build_context(rows)

        result = run_analysis_tools(
            "base_info",
            rows,
            context.selected_fields,
            FIELD_LABELS,
            "列出所有老员工的名单和职级",
            "人员基本信息",
            context,
        )

        self.assertIn("匹配总数：50 条", result.context_markdown)
        self.assertIn("数据被截断", result.context_markdown)
        self.assertIn("前 20 条匹配明细", result.context_markdown)
        self.assertIn("界面筛选功能查看", result.context_markdown)
        self.assertNotIn("人员50", result.context_markdown)

    def test_exact_name_after_first_200_rows_triggers_search(self):
        rows = [
            {"sequence": index, "name": f"人员{index}", "department": "综合部", "seniority": "普通"}
            for index in range(1, 251)
        ]
        rows[229]["name"] = "王五"
        rows[229]["department"] = "研发部"
        context = build_context(rows)

        result = run_analysis_tools(
            "base_info",
            rows,
            context.selected_fields,
            FIELD_LABELS,
            "帮我查一下王五的情况",
            "人员基本信息",
            context,
        )

        self.assertIn("semantic_search", result.called_tools)
        self.assertIn("王五", result.context_markdown)
        self.assertIn("研发部", result.context_markdown)


if __name__ == "__main__":
    unittest.main()
