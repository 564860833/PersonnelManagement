"""Question classification and first-pass QueryPlan generation."""

import re
from typing import Optional

from services.ai_catalog import AICatalog
from services.ai_types import AIQueryPlan


BOOLEAN_WORDS = ("是不是", "是否", "能否", "能不能", "可否", "可以吗", "有没有", "是否为")
COUNT_WORDS = ("几个", "几个人", "多少", "多少人", "几人", "几名", "人数", "总人数", "总数", "共有", "有多少")
AGGREGATE_WORDS = ("最高", "最低", "最老", "最年轻", "平均", "最多", "最少", "最早", "最晚", "最大", "最小")
DISTRIBUTION_WORDS = ("分别", "分布", "各", "每", "按", "排行", "占比", "比例", "统计")
LIST_WORDS = ("查", "查询", "查看", "哪些", "谁", "人员", "情况", "名单", "列出", "明细", "详情")
FIELD_STATS_WORDS = ("空值", "缺失", "完整", "完整性", "非空", "唯一", "字段统计")
DATE_RANGE_WORDS = ("日期范围", "时间范围", "年月范围", "最早时间", "最晚时间")
SUBJECTIVE_WORDS = (
    "更适合",
    "适合晋升",
    "应该晋升",
    "值得培养",
    "重点培养",
    "表现更好",
    "发展潜力",
    "风险更高",
    "适合调岗",
    "更优秀",
    "推荐",
)
UNSUPPORTED_JUDGEMENT_WORDS = (
    "人品",
    "不可靠",
    "品德",
    "能力差",
    "必须淘汰",
    "一定有风险",
    "谁不行",
)


def parse_intent(question: str, catalog: AICatalog) -> AIQueryPlan:
    """Create a coarse plan. Field/value resolution happens in ai_resolver."""
    q = _normalise(question)
    if not q:
        return AIQueryPlan(
            intent="unsupported",
            confidence=0.0,
            missing_slots=["question"],
            clarification_prompt="请先输入需要分析的问题。",
        )

    if not catalog.rows or not catalog.selected_fields:
        return AIQueryPlan(
            intent="unsupported",
            confidence=1.0,
            target="person",
        )

    if _contains_any(q, UNSUPPORTED_JUDGEMENT_WORDS):
        return AIQueryPlan(
            intent="unsupported",
            confidence=0.9,
            risk_level="high",
            allow_direct_answer=False,
            clarification_prompt="这个问题涉及高风险主观判断，当前数据不能支持可靠结论。",
        )

    if "优秀" in q and not catalog.match_values(q, limit=3):
        return AIQueryPlan(
            intent="subjective_assessment",
            metrics=["score"],
            confidence=0.78,
            risk_level="medium",
            allow_direct_answer=False,
            requires_user_confirmation=True,
            assessment_goal="performance",
            missing_slots=["assessment_criteria"],
            clarification_options=[
                "按考核结果和奖惩情况评价工作表现",
                "按任职时间、职级信息和晋升字段评价晋升关注度",
                "按惩戒、影响期、异常备注评价风险关注度",
                "自定义字段和权重",
            ],
        )

    if _contains_any(q, SUBJECTIVE_WORDS):
        return AIQueryPlan(
            intent="subjective_assessment",
            metrics=["score"],
            confidence=0.82,
            risk_level="high",
            allow_direct_answer=False,
            requires_user_confirmation=True,
            assessment_goal=_assessment_goal(q),
            missing_slots=["assessment_criteria"],
            clarification_options=[
                "按考核结果和奖惩情况评价工作表现",
                "按任职时间、职级信息和晋升字段评价晋升关注度",
                "按惩戒、影响期、异常备注评价风险关注度",
                "自定义字段和权重",
            ],
        )

    if _contains_any(q, FIELD_STATS_WORDS):
        return AIQueryPlan(intent="field_stats", metrics=["non_empty", "empty", "unique"], confidence=0.86)

    if _contains_any(q, DATE_RANGE_WORDS) or ("范围" in q and _contains_any(q, ("日期", "时间", "年月"))):
        return AIQueryPlan(intent="date_range", metrics=["min", "max"], confidence=0.86)

    if _contains_any(q, BOOLEAN_WORDS):
        return AIQueryPlan(intent="compare", metrics=["boolean"], confidence=0.82)

    if _contains_any(q, AGGREGATE_WORDS):
        if _looks_like_range_request(q):
            return AIQueryPlan(intent="date_range", metrics=["min", "max"], confidence=0.78)
        return AIQueryPlan(intent="compare", metrics=["aggregate"], confidence=0.84)

    if _contains_any(q, COUNT_WORDS) and _is_total_count_question(q, catalog):
        return AIQueryPlan(intent="count_total", metrics=["count"], confidence=0.88)

    if _contains_any(q, DISTRIBUTION_WORDS):
        return AIQueryPlan(intent="distribution", metrics=["count", "ratio"], confidence=0.86)

    if _contains_any(q, COUNT_WORDS):
        return AIQueryPlan(intent="conditional_count", metrics=["count"], confidence=0.86)

    if _contains_any(q, LIST_WORDS):
        return AIQueryPlan(intent="list_records", confidence=0.78)

    return AIQueryPlan(intent="list_records", confidence=0.5)


def classify_question(question: str, catalog: Optional[AICatalog] = None) -> str:
    if catalog is None:
        q = _normalise(question)
        if _contains_any(q, SUBJECTIVE_WORDS):
            return "subjective_assessment"
        if _contains_any(q, FIELD_STATS_WORDS):
            return "field_stats"
        if _contains_any(q, DATE_RANGE_WORDS):
            return "date_range"
        if _contains_any(q, DISTRIBUTION_WORDS):
            return "distribution"
        if _contains_any(q, COUNT_WORDS):
            return "conditional_count"
        return "list_records"
    return parse_intent(question, catalog).intent


def _is_total_count_question(question: str, catalog: AICatalog) -> bool:
    q = _normalise(question)
    explicit_scope = any(
        text in q
        for text in (
            "当前结果",
            "当前查询结果",
            "当前表",
            "表里总共",
            "表中总共",
            "总共有",
            "一共有",
            "共有多少人",
            "总人数",
            "总数",
        )
    )
    if not explicit_scope:
        return False
    return not bool(catalog.match_values(q, limit=3))


def _looks_like_range_request(question: str) -> bool:
    return "范围" in question and not any(word in question for word in ("谁", "哪个", "哪位"))


def _assessment_goal(question: str) -> str:
    if "晋升" in question:
        return "promotion"
    if any(word in question for word in ("培养", "潜力")):
        return "development"
    if "风险" in question:
        return "risk"
    if "调岗" in question:
        return "transfer"
    return "performance"


def _contains_any(question: str, words) -> bool:
    return any(word in question for word in words)


def _normalise(value) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip())
