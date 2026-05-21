"""Schema and permission validation for AI QueryPlan objects."""

import copy
from typing import Iterable

from services.ai_catalog import AICatalog
from services.ai_types import AIQueryPlan, LEGACY_INTENT_ALIASES, VALID_INTENTS


ALLOWED_OPERATORS = {"eq", "contains", "in", "range", "is_empty"}
MAX_LIMIT = 50


def validate_plan(plan: AIQueryPlan, catalog: AICatalog) -> AIQueryPlan:
    """Drop unauthorized plan parts and mark missing slots instead of guessing."""
    plan = copy.deepcopy(plan)
    plan.intent = LEGACY_INTENT_ALIASES.get(plan.intent, plan.intent)
    if plan.intent not in VALID_INTENTS:
        plan.intent = "unsupported"

    plan.filters = [
        item
        for item in plan.filters
        if item.field in catalog.selected_fields and item.op in ALLOWED_OPERATORS
    ]
    plan.group_by = [item for item in plan.group_by if item.field in catalog.selected_fields]
    plan.aggregates = [item for item in plan.aggregates if item.field in catalog.selected_fields]
    plan.sort = [item for item in plan.sort if item.field in catalog.selected_fields]
    plan.display_fields = [field for field in plan.display_fields if field in catalog.selected_fields]
    plan.metrics = list(dict.fromkeys(str(item) for item in plan.metrics if item))

    if plan.limit is None:
        plan.limit = 20
    else:
        try:
            plan.limit = max(1, min(int(plan.limit), MAX_LIMIT))
        except (TypeError, ValueError):
            plan.limit = 20

    missing = list(dict.fromkeys(plan.missing_slots))
    if plan.intent == "distribution" and not plan.group_by:
        missing.append("group_by")
    if plan.intent == "compare" and "aggregate" in plan.metrics and not plan.aggregates:
        missing.append("aggregate_field")
    if plan.intent == "compare" and "boolean" in plan.metrics:
        has_subject = any(item.field == "name" for item in plan.filters)
        has_target = any(item.field != "name" for item in plan.filters)
        if not has_subject:
            missing.append("subject")
        if not has_target:
            missing.append("boolean_target")
    if plan.intent == "subjective_assessment" and not plan.criteria:
        missing.append("assessment_criteria")

    plan.missing_slots = list(dict.fromkeys(_valid_missing_slots(missing)))
    if plan.missing_slots:
        plan.confidence = min(plan.confidence or 0.5, 0.64)
    if not plan.display_fields:
        plan.display_fields = catalog.default_display_fields()
    return plan


def _valid_missing_slots(slots: Iterable[str]):
    for slot in slots:
        if slot:
            yield str(slot)
