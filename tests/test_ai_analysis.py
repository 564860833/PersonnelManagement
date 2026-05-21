import unittest

from services.ai_analysis import build_analysis_context


FIELD_LABELS = {
    "sequence": "序号",
    "name": "姓名",
    "current_grade": "职级/等级",
    "birth_date": "出生年月",
    "next_promotion": "距离下次职级晋升时间",
}


class AIAnalysisContextTests(unittest.TestCase):
    def test_small_data_includes_full_details(self):
        rows = [
            {"sequence": 1, "name": "张三", "current_grade": "一级", "birth_date": "1980.01"},
            {"sequence": 2, "name": "李四", "current_grade": "二级", "birth_date": "1990.05"},
        ]

        context = build_analysis_context(
            "base_info",
            rows,
            ["sequence", "name", "current_grade", "birth_date"],
            FIELD_LABELS,
            "共有多少人？",
            "人员基本信息",
        )

        self.assertIn("当前结果行数：2", context)
        self.assertIn("## 全量明细（2 行）", context)
        self.assertIn("张三", context)
        self.assertIn("李四", context)

    def test_large_data_uses_full_stats_and_30_row_sample(self):
        rows = [
            {
                "sequence": index,
                "name": f"人员{index}",
                "current_grade": "一级" if index % 2 else "二级",
                "birth_date": "1980.01",
            }
            for index in range(1, 121)
        ]

        context = build_analysis_context(
            "base_info",
            rows,
            ["sequence", "name", "current_grade", "birth_date"],
            FIELD_LABELS,
            "统计职级分布",
            "人员基本信息",
        )

        self.assertIn("统计基于全量 120 行", context)
        self.assertIn("## 明细样本（前 30 行，仅用于举例）", context)
        self.assertIn("总数、比例、分布、排行均由程序基于当前表全量结果计算", context)
        self.assertNotIn("## 全量明细（120 行）", context)

    def test_distribution_missing_and_date_range_are_computed(self):
        rows = [
            {"sequence": 1, "name": "张三", "current_grade": "一级", "birth_date": "1980.01"},
            {"sequence": 2, "name": "李四", "current_grade": "一级", "birth_date": "1990.05"},
            {"sequence": 3, "name": "王五", "current_grade": "", "birth_date": ""},
        ]

        context = build_analysis_context(
            "base_info",
            rows,
            ["current_grade", "birth_date"],
            FIELD_LABELS,
            "分析职级和出生年月",
            "人员基本信息",
        )

        self.assertIn("职级/等级", context)
        self.assertIn("空值数", context)
        self.assertIn("一级", context)
        self.assertIn("66.7%", context)
        self.assertIn("1980.01", context)
        self.assertIn("1990.05", context)

    def test_question_name_focus_adds_matching_rows(self):
        rows = [
            {"sequence": 1, "name": "张三", "current_grade": "一级", "birth_date": "1980.01"},
            {"sequence": 2, "name": "李四", "current_grade": "二级", "birth_date": "1990.05"},
        ]

        context = build_analysis_context(
            "base_info",
            rows,
            ["current_grade", "birth_date"],
            FIELD_LABELS,
            "张三的情况是什么？",
            "人员基本信息",
        )

        self.assertIn("姓名匹配：张三", context)
        self.assertIn("全量匹配条数：1", context)

    def test_next_promotion_is_explanation_only(self):
        rows = [
            {
                "sequence": 1,
                "name": "张三",
                "current_grade": "一级",
                "next_promotion": "2026.06",
            }
        ]

        context = build_analysis_context(
            "base_info",
            rows,
            ["name", "current_grade", "next_promotion"],
            FIELD_LABELS,
            "张三是否可以晋升？",
            "人员基本信息",
        )

        self.assertIn("只能解释字段原值", context)
        self.assertIn("禁止根据任职时间", context)
        self.assertIn("不得根据任职时间", context)

if __name__ == "__main__":
    unittest.main()
