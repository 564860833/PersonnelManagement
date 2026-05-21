"""Conversation state and clarification merge logic for AI queries."""

import copy
import re
from typing import Optional

from services.ai_catalog import AICatalog
from services.ai_planner import AIPlanner, clarification_prompt
from services.ai_resolver import add_filter_from_reply as resolver_add_filter_from_reply
from services.ai_resolver import criteria_from_reply, group_by_from_reply
from services.ai_types import AIAggregate, AIConversationState, AIGroupBy, AIQueryFilter, AIQueryPlan


NEW_QUESTION_PREFIXES = ("不是", "不对", "不用", "重新", "换成", "改成", "我想查", "帮我查")
NEW_QUESTION_INTENT_WORDS = (
    "多少",
    "几",
    "哪些",
    "谁",
    "分布",
    "统计",
    "是不是",
    "是否",
    "最高",
    "最低",
    "平均",
)


def state_for_catalog(state: Optional[AIConversationState], catalog: AICatalog) -> AIConversationState:
    state = copy.deepcopy(state) if state is not None else AIConversationState()
    if state.mode == "awaiting_clarification" and state.catalog_signature != catalog.signature:
        state.reset_pending()
    return state


def make_pending_state(plan: AIQueryPlan, question: str, catalog: AICatalog) -> AIConversationState:
    return AIConversationState(
        mode="awaiting_clarification",
        pending_plan=copy.deepcopy(plan),
        original_question=question,
        missing_slots=list(plan.missing_slots),
        clarification_prompt=plan.clarification_prompt or clarification_prompt(plan, catalog),
        catalog_signature=catalog.signature,
    )


def make_idle_state(summary: str = "") -> AIConversationState:
    return AIConversationState(mode="idle", last_answer_summary=summary)


def should_start_new_question(reply: str, catalog: AICatalog) -> bool:
    q = _normalise(reply)
    if not q:
        return False
    has_prefix = q.startswith(NEW_QUESTION_PREFIXES)
    has_intent = any(word in q for word in NEW_QUESTION_INTENT_WORDS)
    has_value = bool(catalog.match_values(q, limit=3))
    has_field = bool(catalog.fields_mentioned(q, include_date_part=True))
    return bool((has_prefix and has_intent and (has_value or has_field)) or (len(q) >= 10 and has_intent and (has_value or has_field)))


def merge_clarification(
    state: AIConversationState,
    user_reply: str,
    catalog: AICatalog,
    planner: Optional[AIPlanner] = None,
) -> AIQueryPlan:
    planner = planner or AIPlanner(use_model_planning=False)
    if not state.pending_plan:
        return planner.plan(user_reply, catalog)

    plan = copy.deepcopy(state.pending_plan)
    reply_plan = planner.plan(user_reply, catalog)
    q = _normalise(user_reply)
    remaining = []

    for slot in plan.missing_slots:
        if slot == "group_by":
            if reply_plan.group_by:
                plan.group_by = reply_plan.group_by
                continue
            group = group_by_from_reply(q, catalog) or _group_by_from_short_reply(q, catalog)
            if group:
                plan.group_by = [group]
                continue
            remaining.append(slot)
            continue

        if slot.startswith("filter_value:"):
            field = slot.split(":", 1)[1]
            if resolver_add_filter_from_reply(plan, q, catalog, allowed_field=field):
                continue
            remaining.append(slot)
            continue

        if slot.startswith("ambiguous_filter:"):
            fields = catalog.fields_mentioned(q, include_date_part=True)
            if fields and resolver_add_filter_from_reply(plan, state.original_question, catalog, allowed_field=fields[0].field):
                continue
            remaining.append(slot)
            continue

        if slot == "filter":
            if resolver_add_filter_from_reply(plan, f"{state.original_question} {q}", catalog):
                continue
            remaining.append(slot)
            continue

        if slot == "boolean_target":
            if resolver_add_filter_from_reply(plan, q, catalog, excluded_field="name"):
                continue
            remaining.append(slot)
            continue

        if slot == "subject":
            if resolver_add_filter_from_reply(plan, q, catalog, allowed_field="name"):
                continue
            remaining.append(slot)
            continue

        if slot == "aggregate_field":
            if reply_plan.aggregates:
                plan.aggregates = reply_plan.aggregates
                continue
            fields = catalog.fields_mentioned(q, include_date_part=True)
            if fields:
                field = fields[0].field
                operation = plan.aggregates[0].operation if plan.aggregates else "max"
                plan.aggregates = [AIAggregate(field=field, operation=operation, label=catalog.label(field))]
                continue
            remaining.append(slot)
            continue

        if slot == "assessment_criteria":
            criteria = criteria_from_reply(q, catalog, goal=plan.assessment_goal)
            if criteria:
                plan.criteria = criteria
                plan.requires_user_confirmation = False
                plan.allow_direct_answer = False
                continue
            remaining.append(slot)
            continue

        remaining.append(slot)

    plan.missing_slots = remaining
    plan.clarification_prompt = ""
    if not remaining:
        plan.confidence = max(plan.confidence or 0.0, 0.86)
    return planner.validate_plan(plan, catalog)


def _add_filter_from_reply(
    plan: AIQueryPlan,
    reply: str,
    catalog: AICatalog,
    allowed_field: str = "",
    excluded_field: str = "",
) -> bool:
    allowed = [allowed_field] if allowed_field else None
    excluded = [excluded_field] if excluded_field else None
    matches = catalog.match_values(reply, allowed_fields=allowed, excluded_fields=excluded, limit=4)
    if not matches:
        return False
    by_field = {}
    for match in matches:
        by_field.setdefault(match.field, []).append(match)
    for field, items in by_field.items():
        values = [item.value for item in items if item.score >= max(0.78, items[0].score - 0.08)]
        plan.filters = [item for item in plan.filters if item.field != field]
        if len(values) == 1:
            plan.filters.append(AIQueryFilter(field=field, op="eq", value=values[0], confidence=items[0].score, source=items[0].reason))
        else:
            plan.filters.append(AIQueryFilter(field=field, op="in", values=values, confidence=items[0].score, source="澄清多取值匹配"))
    return True


def _group_by_from_short_reply(reply: str, catalog: AICatalog):
    if any(word in reply for word in ("月份", "按月", "每月")):
        field = catalog.first_date_field(reply)
        if field:
            return AIGroupBy(field=field, date_part="month", label="月份")
    if any(word in reply for word in ("年份", "年度", "每年")):
        field = catalog.first_date_field(reply)
        if field:
            return AIGroupBy(field=field, date_part="year", label="年份")
    fields = catalog.fields_mentioned(reply, include_date_part=True)
    if fields:
        field = fields[0].field
        if field in catalog.date_fields:
            return AIGroupBy(field=field, date_part="year_month", label="年月")
        return AIGroupBy(field=field, label=catalog.label(field))
    return None


def _normalise(value) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip())
