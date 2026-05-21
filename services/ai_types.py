"""Shared structured types for the AI query pipeline."""

from dataclasses import dataclass, field as dataclass_field
from typing import Any, Dict, List, Optional


VALID_INTENTS = {
    "count_total",
    "conditional_count",
    "list_records",
    "distribution",
    "field_stats",
    "date_range",
    "compare",
    "subjective_assessment",
    "unsupported",
    "clarify",
}

LEGACY_INTENT_ALIASES = {
    "count": "conditional_count",
    "list": "list_records",
    "aggregate": "compare",
    "boolean": "compare",
    "summary": "field_stats",
}


@dataclass
class AIQueryFilter:
    field: str = ""
    op: str = "eq"
    value: Any = ""
    values: List[Any] = dataclass_field(default_factory=list)
    confidence: float = 1.0
    source: str = "rule"
    keyword: str = ""


@dataclass
class AIGroupBy:
    field: str
    date_part: str = ""
    label: str = ""


@dataclass
class AIAggregate:
    field: str
    operation: str
    label: str = ""


@dataclass
class AISort:
    field: str
    direction: str = "asc"


@dataclass
class AIQueryPlan:
    intent: str = "list_records"
    target: str = "person"
    filters: List[AIQueryFilter] = dataclass_field(default_factory=list)
    group_by: List[AIGroupBy] = dataclass_field(default_factory=list)
    aggregates: List[AIAggregate] = dataclass_field(default_factory=list)
    sort: List[AISort] = dataclass_field(default_factory=list)
    limit: Optional[int] = None
    display_fields: List[str] = dataclass_field(default_factory=list)
    metrics: List[str] = dataclass_field(default_factory=list)
    criteria: List[Dict[str, Any]] = dataclass_field(default_factory=list)
    assessment_goal: str = ""
    risk_level: str = "low"
    allow_direct_answer: bool = True
    requires_user_confirmation: bool = False
    clarification_options: List[str] = dataclass_field(default_factory=list)
    confidence: float = 0.0
    missing_slots: List[str] = dataclass_field(default_factory=list)
    clarification_prompt: str = ""
    source: str = "rule"

    def needs_clarification(self) -> bool:
        return bool(self.missing_slots)


@dataclass
class AIQueryResult:
    intent: str
    matched_count: int = 0
    total_count: int = 0
    display_rows: List[Dict[str, Any]] = dataclass_field(default_factory=list)
    groups: List[Dict[str, Any]] = dataclass_field(default_factory=list)
    aggregate_value: Any = None
    aggregate_rows: List[Dict[str, Any]] = dataclass_field(default_factory=list)
    boolean_value: Optional[bool] = None
    evidence: List[str] = dataclass_field(default_factory=list)
    fields: List[str] = dataclass_field(default_factory=list)
    message: str = ""
    scope: str = ""
    warnings: List[str] = dataclass_field(default_factory=list)
    truncated: bool = False
    sensitive_fields_removed: List[str] = dataclass_field(default_factory=list)
    confidence: float = 1.0


@dataclass
class AIConversationState:
    mode: str = "idle"
    pending_plan: Optional[AIQueryPlan] = None
    original_question: str = ""
    missing_slots: List[str] = dataclass_field(default_factory=list)
    clarification_prompt: str = ""
    catalog_signature: str = ""
    last_answer_summary: str = ""

    def reset_pending(self) -> None:
        self.mode = "idle"
        self.pending_plan = None
        self.original_question = ""
        self.missing_slots = []
        self.clarification_prompt = ""
        self.catalog_signature = ""


@dataclass
class AIAnswer:
    text: str
    intent: str = "unsupported"
    plan: Optional[AIQueryPlan] = None
    query_result: Optional[AIQueryResult] = None
    session_state: AIConversationState = dataclass_field(default_factory=AIConversationState)
    clarification_required: bool = False
    retrieval_degraded: bool = False
