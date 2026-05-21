"""Resolve natural-language fields, values, ambiguity, and scoring rules."""

import copy
import re
from typing import Dict, Iterable, List, Optional, Sequence, Set

from services.ai_catalog import AICatalog, AIValueCandidate
from services.ai_intent import (
    AGGREGATE_WORDS,
    BOOLEAN_WORDS,
    COUNT_WORDS,
    DISTRIBUTION_WORDS,
    LIST_WORDS,
)
from services.ai_types import AIAggregate, AIGroupBy, AIQueryFilter, AIQueryPlan


SENSITIVE_FIELDS = {
    "gender",
    "ethnicity",
    "hometown",
    "birth_date",
    "political_status",
    "family_name",
    "relation",
}
POSITIVE_KEYWORDS = ("优秀", "嘉奖", "记功", "三等功", "二等功", "一等功", "表彰", "先进")
NEGATIVE_KEYWORDS = ("处分", "惩戒", "警告", "记过", "影响期", "异常", "问责")


def resolve_plan(question: str, plan: AIQueryPlan, catalog: AICatalog) -> AIQueryPlan:
    plan = copy.deepcopy(plan)
    q = _normalise(question)

    if plan.intent == "count_total":
        plan.filters = []
        plan.metrics = plan.metrics or ["count"]
        return plan

    if plan.intent == "conditional_count":
        _resolve_value_filters(plan, q, catalog, require_condition=True)
        plan.metrics = plan.metrics or ["count"]
        return plan

    if plan.intent == "list_records":
        _resolve_value_filters(plan, q, catalog, require_condition=False)
        return plan

    if plan.intent == "distribution":
        plan.group_by = plan.group_by or parse_group_by(q, catalog)
        excluded = {item.field for item in plan.group_by if _field_is_group_only(q, item, catalog)}
        _resolve_value_filters(plan, q, catalog, excluded_fields=excluded, require_condition=False)
        if not plan.group_by and "group_by" not in plan.missing_slots:
            plan.missing_slots.append("group_by")
        return plan

    if plan.intent == "field_stats":
        plan.display_fields = _fields_for_field_stats(q, catalog)
        return plan

    if plan.intent == "date_range":
        plan.display_fields = _fields_for_date_range(q, catalog)
        if not plan.display_fields and "date_field" not in plan.missing_slots:
            plan.missing_slots.append("date_field")
        return plan

    if plan.intent == "compare":
        if "boolean" in plan.metrics:
            _resolve_boolean_filters(plan, q, catalog)
        else:
            plan.metrics = ["aggregate"]
            plan.aggregates = plan.aggregates or parse_aggregates(q, catalog)
            excluded = {item.field for item in plan.aggregates}
            _resolve_value_filters(plan, q, catalog, excluded_fields=excluded, require_condition=False)
            if not plan.aggregates and "aggregate_field" not in plan.missing_slots:
                plan.missing_slots.append("aggregate_field")
        return plan

    if plan.intent == "subjective_assessment":
        plan.allow_direct_answer = False
        plan.requires_user_confirmation = not bool(plan.criteria)
        if not plan.criteria and "assessment_criteria" not in plan.missing_slots:
            plan.missing_slots.append("assessment_criteria")
        return plan

    return plan


def parse_group_by(question: str, catalog: AICatalog) -> List[AIGroupBy]:
    q = _normalise(question)
    if any(word in q for word in ("按年月", "按日期", "按时间")):
        field = catalog.first_date_field(q)
        if field:
            return [AIGroupBy(field=field, date_part="year_month", label="年月")]
    if any(word in q for word in ("按月份", "按月", "每月", "月份")):
        field = catalog.first_date_field(q)
        if field:
            return [AIGroupBy(field=field, date_part="month", label="月份")]
    if any(word in q for word in ("按年份", "按年度", "每年", "年份", "年度")):
        field = catalog.first_date_field(q)
        if field:
            return [AIGroupBy(field=field, date_part="year", label="年份")]

    grouped_fields = []
    for field in catalog.selected_fields:
        if field in {"id", "sequence", "name"}:
            continue
        for term in catalog.field_aliases.get(field, []):
            patterns = (f"各{term}", f"每{term}", f"按{term}", f"按照{term}", f"{term}分布", f"{term}分别")
            if term and any(pattern in q for pattern in patterns):
                grouped_fields.append(field)
                break

    if not grouped_fields and any(word in q for word in DISTRIBUTION_WORDS):
        mentioned = [
            item.field
            for item in catalog.fields_mentioned(q, include_date_part=True)
            if item.field not in {"id", "sequence", "name"}
        ]
        grouped_fields.extend(mentioned[:1])

    groups = []
    for field in dict.fromkeys(grouped_fields):
        if field in catalog.date_fields:
            groups.append(AIGroupBy(field=field, date_part="year_month", label="年月"))
        else:
            groups.append(AIGroupBy(field=field, label=catalog.label(field)))
    return groups[:2]


def parse_aggregates(question: str, catalog: AICatalog) -> List[AIAggregate]:
    operation = _resolve_aggregate_operation(question)
    if not operation:
        return []
    mentioned = [
        item.field
        for item in catalog.fields_mentioned(question, include_date_part=True)
        if item.field not in {"id", "sequence", "name"}
    ]
    field = mentioned[0] if mentioned else ""
    if not field and operation in {"oldest", "youngest"}:
        for preferred in ("birth_date", "work_start_date", "entry_date"):
            if preferred in catalog.selected_fields:
                field = preferred
                break
        field = field or catalog.first_date_field(question)
    if not field:
        return []
    return [AIAggregate(field=field, operation=operation, label=catalog.label(field))]


def criteria_from_reply(reply: str, catalog: AICatalog, goal: str = "") -> List[Dict[str, object]]:
    q = _normalise(reply)
    if q in {"1", "一"} or any(word in q for word in ("工作表现", "考核", "奖惩")):
        return _performance_criteria(catalog)
    if q in {"2", "二"} or any(word in q for word in ("晋升", "任职", "职级")) or goal == "promotion":
        return _promotion_criteria(catalog)
    if q in {"3", "三"} or any(word in q for word in ("风险", "惩戒", "影响期")):
        return _risk_criteria(catalog)
    if any(word in q for word in ("培养", "潜力", "发展")) or goal == "development":
        return _development_criteria(catalog)
    return []


def clarification_prompt(plan: AIQueryPlan, catalog: AICatalog) -> str:
    slots = set(plan.missing_slots)
    for slot in plan.missing_slots:
        if slot.startswith("filter_value:"):
            field = slot.split(":", 1)[1]
            values = "、".join(catalog.values_for_field(field)[:6])
            suffix = f"例如：{values}。" if values else ""
            return f"你要按哪个【{catalog.label(field)}】取值筛选？{suffix}"
        if slot.startswith("ambiguous_filter:"):
            labels = plan.clarification_options or []
            if labels:
                return f"这个条件匹配到多个字段：{'、'.join(labels)}。请说明要按哪个字段统计。"
            return "这个条件匹配到多个字段，请说明要按哪个字段统计。"
    if "assessment_criteria" in slots:
        options = plan.clarification_options or [
            "按考核结果和奖惩情况评价工作表现",
            "按任职时间、职级信息和晋升字段评价晋升关注度",
            "按惩戒、影响期、异常备注评价风险关注度",
            "自定义字段和权重",
        ]
        return "这个问题属于主观评价，不能仅凭 AI 直接判断。请先确认评价标准：\n" + "\n".join(
            f"{index}. {option}" for index, option in enumerate(options, 1)
        )
    if "group_by" in slots:
        examples = ["按部门", "按职级"]
        if catalog.date_fields:
            examples.append("按月份")
        return f"要按哪个字段统计分布？可以回答“{'、'.join(examples)}”。"
    if "boolean_target" in slots:
        return "请补充要确认的字段或取值，例如“全职”“本科”或具体部门。"
    if "subject" in slots:
        return "请补充要确认的人员姓名。"
    if "aggregate_field" in slots:
        return "请补充要计算的字段，例如工资、出生年月或奖励日期。"
    if "date_field" in slots:
        return "当前选中字段中没有可识别的日期字段，请先选择日期或年月相关字段。"
    if "filter" in slots:
        return "当前选中字段中没有匹配到这个条件，请确认是否选择了相关字段。"
    if "question" in slots:
        return "请先输入需要分析的问题。"
    return "请补充一个更明确的筛选或统计条件。"


def group_by_from_reply(reply: str, catalog: AICatalog) -> Optional[AIGroupBy]:
    groups = parse_group_by(reply, catalog)
    if groups:
        return groups[0]
    fields = catalog.fields_mentioned(reply, include_date_part=True)
    if not fields:
        return None
    field = fields[0].field
    if field in catalog.date_fields:
        return AIGroupBy(field=field, date_part="year_month", label="年月")
    return AIGroupBy(field=field, label=catalog.label(field))


def add_filter_from_reply(
    plan: AIQueryPlan,
    reply: str,
    catalog: AICatalog,
    allowed_field: str = "",
    excluded_field: str = "",
) -> bool:
    allowed = [allowed_field] if allowed_field else None
    excluded = [excluded_field] if excluded_field else None
    matches = catalog.match_values(reply, allowed_fields=allowed, excluded_fields=excluded, limit=6)
    if not matches and allowed_field:
        matches = _contains_candidates_for_field(catalog, reply, allowed_field)
    if not matches:
        return False
    by_field: Dict[str, List[AIValueCandidate]] = {}
    for match in matches:
        by_field.setdefault(match.field, []).append(match)
    for field, items in by_field.items():
        values = [item.value for item in _preferred_value_candidates(items, catalog)]
        plan.filters = [item for item in plan.filters if item.field != field]
        if len(values) == 1:
            plan.filters.append(AIQueryFilter(field=field, op="eq", value=values[0], confidence=items[0].score, source=items[0].reason))
        elif values:
            plan.filters.append(AIQueryFilter(field=field, op="in", values=values, confidence=items[0].score, source="澄清多取值匹配"))
    return True


def _resolve_value_filters(
    plan: AIQueryPlan,
    question: str,
    catalog: AICatalog,
    excluded_fields: Optional[Iterable[str]] = None,
    require_condition: bool = False,
) -> None:
    excluded = set(excluded_fields or set())
    candidates = catalog.match_values(question, excluded_fields=excluded, limit=16)
    if not candidates:
        mentioned = [item.field for item in catalog.fields_mentioned(question) if item.field not in excluded]
        if require_condition and mentioned:
            slot = f"filter_value:{mentioned[0]}"
            if slot not in plan.missing_slots:
                plan.missing_slots.append(slot)
        elif require_condition and "filter" not in plan.missing_slots:
            plan.missing_slots.append("filter")
        return

    by_field: Dict[str, List[AIValueCandidate]] = {}
    for item in candidates:
        by_field.setdefault(item.field, []).append(item)

    explicit_fields = {item.field for item in catalog.fields_mentioned(question) if item.field not in excluded}
    candidate_scores = {field: max(item.score for item in items) for field, items in by_field.items()}
    best_score = max(candidate_scores.values())
    close_fields = [
        field
        for field, score in candidate_scores.items()
        if score >= max(0.78, best_score - 0.08)
    ]
    value_fields = [field for field in close_fields if field not in {"name"}]

    if explicit_fields and any(field in close_fields for field in explicit_fields):
        selected_fields = [field for field in close_fields if field in explicit_fields]
    elif len(value_fields) > 1:
        term = _best_question_term(question, catalog)
        labels = [catalog.label(field) for field in value_fields[:4]]
        slot = f"ambiguous_filter:{term or '条件'}"
        if slot not in plan.missing_slots:
            plan.missing_slots.append(slot)
        plan.clarification_options = labels
        return
    else:
        selected_fields = [close_fields[0]]

    for field in selected_fields:
        items = by_field.get(field, [])
        preferred = _preferred_value_candidates(items, catalog)
        if not preferred:
            continue
        plan.filters = [item for item in plan.filters if item.field != field]
        if len(preferred) == 1:
            item = preferred[0]
            plan.filters.append(
                AIQueryFilter(
                    field=field,
                    op="eq",
                    value=item.value,
                    confidence=item.score,
                    source=item.reason,
                    keyword=_best_question_term(question, catalog),
                )
            )
        else:
            plan.filters.append(
                AIQueryFilter(
                    field=field,
                    op="in",
                    values=[item.value for item in preferred],
                    confidence=max(item.score for item in preferred),
                    source="同字段多取值匹配",
                    keyword=_best_question_term(question, catalog),
                )
            )


def _resolve_boolean_filters(plan: AIQueryPlan, question: str, catalog: AICatalog) -> None:
    if not any(item.field == "name" for item in plan.filters):
        add_filter_from_reply(plan, question, catalog, allowed_field="name")
    if not any(item.field != "name" for item in plan.filters):
        add_filter_from_reply(plan, question, catalog, excluded_field="name")


def _preferred_value_candidates(items: Sequence[AIValueCandidate], catalog: Optional[AICatalog] = None) -> List[AIValueCandidate]:
    if not items:
        return []
    exact = [item for item in items if item.score >= 0.94]
    if exact:
        return [
            item
            for item in items
            if item.score >= 0.94
            or (
                item.reason.startswith("问题关键词匹配取值")
                and (catalog is None or _is_actual_field_value(catalog, item.field, item.value))
            )
        ]
    best_score = max(item.score for item in items)
    return [item for item in items if item.score >= max(0.78, best_score - 0.08)]


def _contains_candidates_for_field(catalog: AICatalog, reply: str, field: str) -> List[AIValueCandidate]:
    q = _normalise(reply)
    matches = []
    for value, indices in catalog.value_index.get(field, {}).items():
        if q and (q in value or value in q):
            matches.append(AIValueCandidate(field, catalog.label(field), value, list(indices), 0.84, "澄清文本匹配取值"))
    return matches


def _is_actual_field_value(catalog: AICatalog, field: str, value: str) -> bool:
    target = _normalise(value)
    return any(_normalise(row.get(field, "")) == target for row in catalog.rows)


def _field_is_group_only(question: str, group: AIGroupBy, catalog: AICatalog) -> bool:
    return any(
        pattern.format(term=term) in question
        for term in catalog.field_aliases.get(group.field, [])
        for pattern in ("各{term}", "每{term}", "按{term}", "按照{term}", "{term}分布", "{term}分别")
    )


def _fields_for_field_stats(question: str, catalog: AICatalog) -> List[str]:
    mentioned = [item.field for item in catalog.fields_mentioned(question, include_date_part=True)]
    return mentioned or catalog.selected_fields[:8]


def _fields_for_date_range(question: str, catalog: AICatalog) -> List[str]:
    mentioned = [item.field for item in catalog.fields_mentioned(question, include_date_part=True) if item.field in catalog.date_fields]
    if mentioned:
        return mentioned
    return [field for field in catalog.selected_fields if field in catalog.date_fields][:4]


def _resolve_aggregate_operation(question: str) -> str:
    q = _normalise(question)
    if "平均" in q:
        return "average"
    if any(word in q for word in ("最老", "年龄最大")):
        return "oldest"
    if any(word in q for word in ("最年轻", "年龄最小")):
        return "youngest"
    if "最早" in q:
        return "earliest"
    if any(word in q for word in ("最晚", "最近")):
        return "latest"
    if any(word in q for word in ("最多", "最大", "最高")):
        return "max"
    if any(word in q for word in ("最少", "最小", "最低")):
        return "min"
    return ""


def _performance_criteria(catalog: AICatalog) -> List[Dict[str, object]]:
    criteria = []
    for field in catalog.selected_fields:
        label = catalog.label(field)
        if field.startswith("assessment_") or "考核" in label:
            criteria.append({"field": field, "weight": 50, "mapping": {"优秀": 100, "称职": 80, "基本称职": 50, "不称职": 0}})
            break
    _append_if_available(criteria, catalog, ("rewards", "reward_name"), 30, "positive_keyword")
    _append_if_available(criteria, catalog, ("punishment_name", "impact_period"), 20, "negative_keyword")
    return _normalise_weights(criteria)


def _promotion_criteria(catalog: AICatalog) -> List[Dict[str, object]]:
    criteria = []
    _append_if_available(criteria, catalog, ("next_promotion",), 35, "earlier_is_better")
    _append_if_available(criteria, catalog, ("current_grade_date",), 25, "earlier_is_better")
    for field in catalog.selected_fields:
        label = catalog.label(field)
        if field.startswith("assessment_") or "考核" in label:
            criteria.append({"field": field, "weight": 20, "mapping": {"优秀": 100, "称职": 80, "基本称职": 50, "不称职": 0}})
            break
    _append_if_available(criteria, catalog, ("rewards", "reward_name"), 20, "positive_keyword")
    return _normalise_weights(criteria)


def _risk_criteria(catalog: AICatalog) -> List[Dict[str, object]]:
    criteria = []
    _append_if_available(criteria, catalog, ("punishment_name",), 45, "negative_keyword")
    _append_if_available(criteria, catalog, ("impact_period",), 35, "non_empty")
    _append_if_available(criteria, catalog, ("remarks",), 20, "negative_keyword")
    return _normalise_weights(criteria)


def _development_criteria(catalog: AICatalog) -> List[Dict[str, object]]:
    criteria = _performance_criteria(catalog)
    _append_if_available(criteria, catalog, ("current_grade_date", "current_position_date"), 20, "earlier_is_better")
    return _normalise_weights(criteria)


def _append_if_available(criteria: List[Dict[str, object]], catalog: AICatalog, fields: Sequence[str], weight: int, direction: str) -> None:
    for field in fields:
        if field in catalog.selected_fields and field not in SENSITIVE_FIELDS:
            criteria.append({"field": field, "weight": weight, "direction": direction})
            return


def _normalise_weights(criteria: List[Dict[str, object]]) -> List[Dict[str, object]]:
    filtered = [item for item in criteria if item.get("field") not in SENSITIVE_FIELDS]
    total = sum(float(item.get("weight", 0) or 0) for item in filtered)
    if not filtered or total <= 0:
        return []
    for item in filtered:
        item["weight"] = round(float(item.get("weight", 0) or 0) * 100 / total, 2)
    return filtered


def _best_question_term(question: str, catalog: AICatalog) -> str:
    text = _normalise(question)
    removable = sorted(
        set(
            COUNT_WORDS
            + BOOLEAN_WORDS
            + AGGREGATE_WORDS
            + DISTRIBUTION_WORDS
            + LIST_WORDS
            + tuple(alias for aliases in catalog.field_aliases.values() for alias in aliases)
            + ("当前", "现在", "查询结果", "记录", "条记录", "人员", "人", "条", "个", "的", "吗", "呢", "是", "为", "有", "？", "?", "，", ",", "。")
        ),
        key=len,
        reverse=True,
    )
    for word in removable:
        if word:
            text = text.replace(word, " ")
    terms = [part for part in re.split(r"[\s,，。；;:：?？!！]+", text) if len(part) >= 2]
    return terms[0] if terms else ""


def _normalise(value) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip())
