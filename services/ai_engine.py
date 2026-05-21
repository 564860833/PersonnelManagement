"""High-level AI query engine: plan, clarify, execute, and answer."""

import copy
from typing import Optional

from services.ai_answerer import AIAnswerer
from services.ai_catalog import AICatalog
from services.ai_executor import AIQueryExecutor
from services.ai_guard import validate_result
from services.ai_planner import AIPlanner
from services.ai_state import (
    make_idle_state,
    make_pending_state,
    merge_clarification,
    should_start_new_question,
    state_for_catalog,
)
from services.ai_types import AIAnswer, AIConversationState


class AIQueryEngine:
    def __init__(
        self,
        planner: Optional[AIPlanner] = None,
        executor: Optional[AIQueryExecutor] = None,
        answerer: Optional[AIAnswerer] = None,
    ):
        self.planner = planner
        self.executor = executor or AIQueryExecutor()
        self.answerer = answerer or AIAnswerer()

    def answer(
        self,
        question: str,
        analysis_payload: dict,
        session_state: Optional[AIConversationState] = None,
        model_name: Optional[str] = None,
        n_ctx: int = 4096,
    ) -> AIAnswer:
        catalog = AICatalog.from_payload(analysis_payload)
        state = state_for_catalog(session_state, catalog)
        planner = self.planner or AIPlanner(
            model_name=_normal_model_name(model_name),
            n_ctx=n_ctx,
            use_model_planning=True,
        )

        if state.mode == "awaiting_clarification" and state.pending_plan:
            if should_start_new_question(question, catalog):
                state.reset_pending()
                plan = planner.plan(question, catalog)
                original_question = question
            else:
                merge_planner = AIPlanner(use_model_planning=False)
                plan = merge_clarification(state, question, catalog, planner=merge_planner)
                original_question = state.original_question or question
        else:
            plan = planner.plan(question, catalog)
            original_question = question

        if plan.needs_clarification():
            pending_state = make_pending_state(plan, original_question, catalog)
            prompt = plan.clarification_prompt or pending_state.clarification_prompt
            return AIAnswer(
                text=prompt,
                intent="clarify",
                plan=copy.deepcopy(plan),
                query_result=None,
                session_state=pending_state,
                clarification_required=True,
            )

        result = self.executor.execute(plan, catalog)
        result = validate_result(result, plan, catalog)
        text = self.answerer.render(plan, result, catalog)
        next_state = make_idle_state(_summary_for_state(text))
        return AIAnswer(
            text=text,
            intent=plan.intent,
            plan=copy.deepcopy(plan),
            query_result=result,
            session_state=next_state,
            clarification_required=False,
        )


def _normal_model_name(model_name: Optional[str]) -> Optional[str]:
    model_name = (model_name or "").strip()
    if not model_name or "未检测到模型" in model_name:
        return None
    return model_name


def _summary_for_state(text: str) -> str:
    text = (text or "").strip().replace("\n", " ")
    return text[:160]
