"""Rule-first planner for the structured AI analysis pipeline."""

import json
import logging
import re
from typing import Optional

import requests

from services.ai_catalog import AICatalog
from services.ai_intent import parse_intent
from services.ai_resolver import clarification_prompt, resolve_plan
from services.ai_schema import validate_plan
from services.ai_types import (
    AIAggregate,
    AIGroupBy,
    AIQueryFilter,
    AIQueryPlan,
    LEGACY_INTENT_ALIASES,
)
from services.ollama_manager import ollama_api_url


logger = logging.getLogger("AIPlanner")


class AIPlanner:
    def __init__(
        self,
        model_name: Optional[str] = None,
        n_ctx: int = 4096,
        use_model_planning: bool = True,
        timeout: float = 20.0,
    ):
        self.model_name = model_name
        self.n_ctx = n_ctx
        self.use_model_planning = use_model_planning
        self.timeout = timeout

    def plan(self, question: str, catalog: AICatalog) -> AIQueryPlan:
        rule_plan = self._rule_plan(question, catalog)
        if (
            self.use_model_planning
            and self.model_name
            and rule_plan.confidence < 0.55
            and not rule_plan.needs_clarification()
        ):
            model_plan = self._model_plan(question, catalog)
            if model_plan:
                model_plan = self._finalise(model_plan, question, catalog)
                if model_plan.confidence >= rule_plan.confidence:
                    return model_plan
        return rule_plan

    def validate_plan(self, plan: AIQueryPlan, catalog: AICatalog) -> AIQueryPlan:
        return validate_plan(plan, catalog)

    def _rule_plan(self, question: str, catalog: AICatalog) -> AIQueryPlan:
        return self._finalise(parse_intent(question, catalog), question, catalog)

    def _finalise(self, plan: AIQueryPlan, question: str, catalog: AICatalog) -> AIQueryPlan:
        resolved = resolve_plan(question, plan, catalog)
        validated = validate_plan(resolved, catalog)
        validated.clarification_prompt = validated.clarification_prompt or clarification_prompt(validated, catalog)
        return validated

    def _model_plan(self, question: str, catalog: AICatalog) -> Optional[AIQueryPlan]:
        try:
            fields = [{"field": field, "label": catalog.label(field)} for field in catalog.selected_fields]
            prompt = (
                "你只输出 JSON，不要解释。把用户的人事数据问题改写为结构化 QueryPlan。\n"
                "只能使用给定字段名，不能编造字段。intent 必须是 "
                "count_total/conditional_count/list_records/distribution/field_stats/date_range/"
                "compare/subjective_assessment/unsupported/clarify 之一。\n"
                "JSON 字段：intent, filters, group_by, aggregates, metrics, criteria, confidence, missing_slots。\n"
                "filters 使用 field/op/value/values；compare 极值使用 aggregates 的 field/operation。\n"
                f"可用字段：{json.dumps(fields, ensure_ascii=False)}\n"
                f"用户问题：{question}"
            )
            response = requests.post(
                ollama_api_url("/api/chat"),
                json={
                    "model": self.model_name,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "options": {"num_ctx": self.n_ctx, "temperature": 0.0},
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            content = response.json().get("message", {}).get("content", "")
            data = _extract_json_object(content)
            if not isinstance(data, dict):
                return None
            return _plan_from_model_json(data)
        except Exception as exc:
            logger.debug("模型规划失败，使用规则规划: %s", exc)
            return None


def _plan_from_model_json(data: dict) -> AIQueryPlan:
    filters = []
    for item in data.get("filters") or []:
        if isinstance(item, dict):
            filters.append(
                AIQueryFilter(
                    field=str(item.get("field", "")),
                    op=str(item.get("op") or item.get("operator") or "eq"),
                    value=item.get("value", ""),
                    values=list(item.get("values") or []),
                    confidence=float(item.get("confidence", 0.6) or 0.6),
                    source="model",
                    keyword=str(item.get("keyword", "")),
                )
            )

    group_by = []
    for item in data.get("group_by") or []:
        if isinstance(item, str):
            group_by.append(AIGroupBy(field=item))
        elif isinstance(item, dict):
            group_by.append(
                AIGroupBy(
                    field=str(item.get("field", "")),
                    date_part=str(item.get("date_part", "")),
                    label=str(item.get("label", "")),
                )
            )

    aggregates = []
    for item in data.get("aggregates") or []:
        if isinstance(item, dict):
            aggregates.append(
                AIAggregate(
                    field=str(item.get("field", "")),
                    operation=str(item.get("operation", "")),
                    label=str(item.get("label", "")),
                )
            )

    intent = str(data.get("intent", "unsupported"))
    intent = LEGACY_INTENT_ALIASES.get(intent, intent)
    return AIQueryPlan(
        intent=intent,
        target=str(data.get("target", "person") or "person"),
        filters=filters,
        group_by=group_by,
        aggregates=aggregates,
        metrics=[str(item) for item in data.get("metrics") or []],
        criteria=[item for item in data.get("criteria") or [] if isinstance(item, dict)],
        confidence=float(data.get("confidence", 0.5) or 0.5),
        missing_slots=[str(item) for item in data.get("missing_slots") or []],
        risk_level=str(data.get("risk_level", "low") or "low"),
        allow_direct_answer=bool(data.get("allow_direct_answer", True)),
        requires_user_confirmation=bool(data.get("requires_user_confirmation", False)),
        source="model",
    )


def _extract_json_object(text: str):
    text = (text or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, flags=re.S)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
