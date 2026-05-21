import unittest

from services.ai_engine import AIQueryEngine
from services.ai_types import AIConversationState


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
    "current_position": "现任职务",
    "current_grade": "职级/等级",
    "current_grade_date": "任现职级/等级时间",
    "next_promotion": "距离下次职级晋升时间",
    "rewards": "奖惩",
    "gender": "性别",
    "resume_text": "简历信息",
}


def payload(rows=None, fields=None):
    rows = rows or [
        {
            "sequence": 1,
            "name": "张三",
            "department": "研发部",
            "education": "本科",
            "birth_date": "1980.01",
            "salary": "12000",
            "employment_type": "全职",
        },
        {
            "sequence": 2,
            "name": "李四",
            "department": "研发部",
            "education": "硕士",
            "birth_date": "1990.05",
            "salary": "9800",
            "employment_type": "兼职",
        },
        {
            "sequence": 3,
            "name": "王五",
            "department": "综合部",
            "education": "本科",
            "birth_date": "1980.05",
            "salary": "11000",
            "employment_type": "全职",
        },
    ]
    fields = fields or ["sequence", "name", "department", "education", "birth_date", "salary", "employment_type"]
    return {
        "table_name": "base_info",
        "table_label": "人员基本信息",
        "rows": rows,
        "selected_fields": fields,
        "field_labels": {field: FIELD_LABELS[field] for field in fields},
    }


def rewards_payload():
    rows = [
        {"sequence": 1, "name": "张三", "reward_name": "记三等功", "reward_authority_type": "中央机关"},
        {"sequence": 2, "name": "李四", "reward_name": "三等功", "reward_authority_type": "地方机关"},
        {"sequence": 3, "name": "王五", "reward_name": "一等功", "reward_authority_type": "中央机关"},
        {"sequence": 4, "name": "赵六", "reward_name": "通报表扬", "reward_authority_type": "地方机关"},
    ]
    fields = ["sequence", "name", "reward_name", "reward_authority_type"]
    return {
        "table_name": "rewards",
        "table_label": "人员奖惩信息",
        "rows": rows,
        "selected_fields": fields,
        "field_labels": {field: FIELD_LABELS[field] for field in fields},
    }


class AIQueryEngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = AIQueryEngine()

    def test_clarification_reply_merges_group_by_month(self):
        first = self.engine.answer("统计本科人员", payload(), AIConversationState())

        self.assertTrue(first.clarification_required)
        self.assertEqual("awaiting_clarification", first.session_state.mode)
        self.assertIn("group_by", first.session_state.missing_slots)

        second = self.engine.answer("按月份", payload(), first.session_state)

        self.assertFalse(second.clarification_required)
        self.assertEqual("distribution", second.intent)
        self.assertEqual("month", second.plan.group_by[0].date_part)
        self.assertEqual(2, second.query_result.matched_count)
        self.assertIn("01月", second.text)
        self.assertIn("05月", second.text)

    def test_clarification_reply_fills_education_filter_value(self):
        first = self.engine.answer("学历有多少人？", payload(), AIConversationState())

        self.assertTrue(first.clarification_required)
        self.assertIn("filter_value:education", first.session_state.missing_slots)

        second = self.engine.answer("本科", payload(), first.session_state)

        self.assertFalse(second.clarification_required)
        self.assertEqual("conditional_count", second.intent)
        self.assertEqual(2, second.query_result.matched_count)
        self.assertIn("2 人", second.text)

    def test_new_question_cancels_pending_plan(self):
        first = self.engine.answer("统计本科人员", payload(), AIConversationState())

        second = self.engine.answer("不是，我想查研发部有多少人", payload(), first.session_state)

        self.assertFalse(second.clarification_required)
        self.assertEqual("conditional_count", second.intent)
        self.assertEqual(2, second.query_result.matched_count)
        self.assertEqual("idle", second.session_state.mode)
        self.assertIn("部门 = 研发部", second.text)

    def test_pending_plan_invalidates_when_catalog_signature_changes(self):
        first = self.engine.answer("统计本科人员", payload(), AIConversationState())
        changed_payload = payload(fields=["sequence", "name", "department", "education"])

        second = self.engine.answer("按月份", changed_payload, first.session_state)

        self.assertTrue(second.clarification_required)
        self.assertEqual("awaiting_clarification", second.session_state.mode)
        self.assertEqual("按月份", second.session_state.original_question)

    def test_ambiguous_standard_requires_clarification(self):
        answer = self.engine.answer("优秀的人有哪些？", payload(), AIConversationState())

        self.assertTrue(answer.clarification_required)
        self.assertEqual("clarify", answer.intent)
        self.assertEqual("subjective_assessment", answer.plan.intent)
        self.assertIn("评价标准", answer.text)

    def test_regression_count_list_distribution_aggregate_boolean(self):
        count = self.engine.answer("研发部有多少人？", payload(), AIConversationState())
        listing = self.engine.answer("开发部的人有哪些？", payload(), AIConversationState())
        distribution = self.engine.answer("各部门分别多少人？", payload(), AIConversationState())
        aggregate = self.engine.answer("谁的工资最高？", payload(), AIConversationState())
        boolean = self.engine.answer("张三是不是全职？", payload(), AIConversationState())

        self.assertEqual(2, count.query_result.matched_count)
        self.assertEqual(2, listing.query_result.matched_count)
        self.assertEqual("distribution", distribution.intent)
        self.assertIn("研发部", distribution.text)
        self.assertEqual("12000", aggregate.query_result.aggregate_value)
        self.assertIn("张三", aggregate.text)
        self.assertTrue(boolean.query_result.boolean_value)
        self.assertTrue(boolean.text.startswith("是"))

    def test_count_short_reward_value_filters_before_counting(self):
        answer = self.engine.answer("几个三等功", rewards_payload(), AIConversationState())

        self.assertFalse(answer.clarification_required)
        self.assertEqual("conditional_count", answer.intent)
        self.assertEqual(2, answer.query_result.matched_count)
        self.assertIn("奖励名称 属于", answer.text)
        self.assertIn("2 条记录", answer.text)

    def test_total_count_uses_explicit_total_intent(self):
        answer = self.engine.answer("当前结果共有多少人？", payload(), AIConversationState())

        self.assertFalse(answer.clarification_required)
        self.assertEqual("count_total", answer.intent)
        self.assertEqual(3, answer.query_result.matched_count)
        self.assertIn("统计结果：3 人", answer.text)

    def test_ambiguous_value_match_requires_field_clarification(self):
        rows = [
            {"sequence": 1, "name": "张三", "current_position": "办公室主任", "current_grade": "一级主任科员", "resume_text": "曾任部门主任"},
            {"sequence": 2, "name": "李四", "current_position": "检察官", "current_grade": "一级检察官", "resume_text": ""},
        ]
        fields = ["sequence", "name", "current_position", "current_grade", "resume_text"]
        answer = self.engine.answer("几个主任？", payload(rows, fields), AIConversationState())

        self.assertTrue(answer.clarification_required)
        self.assertEqual("clarify", answer.intent)
        self.assertIn("多个字段", answer.text)
        self.assertIn("现任职务", answer.text)

    def test_missing_selected_field_does_not_guess_condition(self):
        rows = [{"sequence": 1, "name": "张三", "department": "研发部"}]
        fields = ["sequence", "name", "department"]
        answer = self.engine.answer("几个三等功？", payload(rows, fields), AIConversationState())

        self.assertTrue(answer.clarification_required)
        self.assertEqual("clarify", answer.intent)
        self.assertIn("没有匹配到", answer.text)

    def test_subjective_assessment_scores_after_user_confirms_rule(self):
        rows = [
            {"sequence": 1, "name": "张三", "next_promotion": "2025.01", "current_grade_date": "2020.01", "rewards": "三等功", "gender": "男"},
            {"sequence": 2, "name": "李四", "next_promotion": "2028.01", "current_grade_date": "2023.01", "rewards": "", "gender": "女"},
        ]
        fields = ["sequence", "name", "next_promotion", "current_grade_date", "rewards", "gender"]
        first = self.engine.answer("谁更适合晋升？", payload(rows, fields), AIConversationState())
        second = self.engine.answer("2", payload(rows, fields), first.session_state)

        self.assertTrue(first.clarification_required)
        self.assertFalse(second.clarification_required)
        self.assertEqual("subjective_assessment", second.intent)
        self.assertIn("辅助评分", second.text)
        self.assertNotIn("| 性别 |", second.text)
        self.assertIn("性别", second.text)

    def test_large_list_result_is_guarded_and_truncated(self):
        rows = [
            {"sequence": index, "name": f"人员{index}", "department": "研发部", "education": "本科"}
            for index in range(1, 51)
        ]
        fields = ["sequence", "name", "department", "education"]
        answer = self.engine.answer("本科人员名单", payload(rows, fields), AIConversationState())

        self.assertEqual("list_records", answer.intent)
        self.assertEqual(50, answer.query_result.matched_count)
        self.assertTrue(answer.query_result.truncated)
        self.assertIn("仅展示前 20 条", answer.text)
        self.assertNotIn("人员50", answer.text)


if __name__ == "__main__":
    unittest.main()
