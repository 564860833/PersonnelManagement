"""Direct Ollama chat helper for the AI assistant."""

import json
from typing import Dict, List, Optional, Sequence

import requests

from services.ollama_manager import ollama_api_url


SYSTEM_PROMPT = "你是人员信息管理系统的 AI 助手。用户会提供当前查询表的数据，你可以结合这些数据回答用户问题。"
MAX_HISTORY_MESSAGES = 20
ALLOWED_HISTORY_ROLES = {"user", "assistant"}


def build_messages(
    question: str,
    analysis_payload: dict,
    history_messages: Optional[Sequence[Dict[str, str]]] = None,
) -> List[Dict[str, str]]:
    table_name = analysis_payload.get("table_name", "")
    table_label = analysis_payload.get("table_label", table_name)
    selected_fields = list(analysis_payload.get("selected_fields") or [])
    field_labels = dict(analysis_payload.get("field_labels") or {})
    rows = list(analysis_payload.get("rows") or [])

    fields = _field_descriptions(selected_fields, field_labels)
    projected_rows = _project_rows(rows, selected_fields)
    data = {
        "当前表名": f"{table_label} ({table_name})" if table_name else table_label,
        "字段说明": fields,
        "完整表数据": projected_rows,
    }

    user_prompt = "\n".join(
        [
            "当前查询表数据如下：",
            _to_json(data),
            "",
            "用户问题：",
            question,
        ]
    )
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(_sanitize_history_messages(history_messages))
    messages.append({"role": "user", "content": user_prompt})
    return messages


def ask_model(
    question: str,
    analysis_payload: dict,
    model_name: str,
    n_ctx: int = 4096,
    timeout: float = 120.0,
    history_messages: Optional[Sequence[Dict[str, str]]] = None,
) -> str:
    model_name = (model_name or "").strip()
    if not model_name:
        raise ValueError("未选择可用模型。")

    response = requests.post(
        ollama_api_url("/api/chat"),
        json={
            "model": model_name,
            "messages": build_messages(question, analysis_payload, history_messages),
            "stream": False,
            "options": {"num_ctx": n_ctx},
        },
        timeout=timeout,
    )
    response.raise_for_status()
    content = response.json().get("message", {}).get("content", "")
    return str(content).strip()


def _sanitize_history_messages(
    history_messages: Optional[Sequence[Dict[str, str]]],
) -> List[Dict[str, str]]:
    sanitized = []
    for message in history_messages or []:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role", "")).strip()
        raw_content = message.get("content", "")
        if raw_content is None:
            continue
        content = str(raw_content).strip()
        if role not in ALLOWED_HISTORY_ROLES or not content:
            continue
        sanitized.append({"role": role, "content": content})
    return sanitized[-MAX_HISTORY_MESSAGES:]


def _field_descriptions(selected_fields: Sequence[str], field_labels: Dict[str, str]) -> List[dict]:
    return [
        {"field": field, "label": field_labels.get(field, field)}
        for field in selected_fields
    ]


def _project_rows(rows: Sequence[dict], selected_fields: Sequence[str]) -> List[dict]:
    if not selected_fields:
        return [dict(row) for row in rows]
    return [
        {field: row.get(field, "") for field in selected_fields}
        for row in rows
    ]


def _to_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)
