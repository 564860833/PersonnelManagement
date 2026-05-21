"""Compatibility wrapper for the structured AI analysis pipeline."""

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from metadata.constants import get_table_label
from services.ai_catalog import AICatalog
from services.ai_engine import AIQueryEngine
from services.ai_intent import classify_question
from services.ai_retrieval import LocalRetrievalIndex
from services.ai_types import AIConversationState


@dataclass
class AnalysisToolResult:
    context_markdown: str
    called_tools: List[str]
    retrieval_degraded: bool = False
    retrieval_message: str = ""
    action_type: str = "list_records"
    raw_count: int = 0
    display_count: int = 0
    output_instruction: str = ""


class AIToolContext:
    def __init__(
        self,
        table_name: str,
        rows: Sequence[dict],
        selected_fields: Sequence[str],
        field_labels: Dict[str, str],
        table_label: Optional[str] = None,
        retrieval_index: Optional[LocalRetrievalIndex] = None,
    ):
        self.table_name = table_name
        self.table_label = table_label or get_table_label(table_name)
        self.rows = list(rows or [])
        self.field_labels = dict(field_labels or {})
        self.selected_fields = _existing_fields(self.rows, [field for field in selected_fields if field])
        # Kept for callers that still construct AIToolContext with a retrieval index.
        self.retrieval_index = retrieval_index


def classify_intent(question: str, context: Optional[AIToolContext] = None) -> str:
    """Return the new QueryPlan intent name for compatibility callers."""
    if context is None:
        return classify_question(question)
    catalog = _catalog_from_context(context)
    return classify_question(question, catalog)


def run_analysis_tools(
    table_name: str,
    rows: Sequence[dict],
    selected_fields: Sequence[str],
    field_labels: Dict[str, str],
    user_question: str,
    table_label: str = None,
    tool_context: Optional[AIToolContext] = None,
) -> AnalysisToolResult:
    """Execute the new AIQueryEngine pipeline and expose the old result shape."""
    context = tool_context or AIToolContext(table_name, rows, selected_fields, field_labels, table_label)
    payload = {
        "table_name": context.table_name,
        "table_label": context.table_label,
        "rows": context.rows,
        "selected_fields": context.selected_fields,
        "field_labels": context.field_labels,
    }
    answer = AIQueryEngine().answer(user_question, payload, AIConversationState(), model_name="")
    result = answer.query_result
    action_type = answer.intent
    raw_count = result.matched_count if result is not None else 0
    display_count = _display_count(result)
    called_tools = [action_type] if action_type else []

    return AnalysisToolResult(
        context_markdown=_context_markdown(action_type, called_tools, answer.text),
        called_tools=called_tools,
        retrieval_degraded=False,
        retrieval_message="",
        action_type=action_type,
        raw_count=raw_count,
        display_count=display_count,
        output_instruction="结构化 AI 分析管线已完成，回答必须仅基于上述结果。",
    )


def _catalog_from_context(context: AIToolContext) -> AICatalog:
    return AICatalog(
        context.table_name,
        context.rows,
        context.selected_fields,
        context.field_labels,
        context.table_label,
    )


def _context_markdown(action_type: str, called_tools: Sequence[str], answer_text: str) -> str:
    return "\n".join(
        [
            "## 工具调用结果",
            f"- 动作模式：{action_type}",
            f"- 已调用工具：{', '.join(called_tools) if called_tools else '无'}",
            "",
            "### structured_pipeline",
            answer_text,
        ]
    )


def _display_count(result) -> int:
    if result is None:
        return 0
    return len(result.display_rows) or len(result.groups) or (1 if result.matched_count else 0)


def _existing_fields(rows: Sequence[dict], fields: Sequence[str]) -> List[str]:
    if not rows:
        return list(fields)
    available = set()
    for row in rows[:30]:
        available.update(row.keys())
    return [field for field in fields if field in available]
