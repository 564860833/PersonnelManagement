"""Direct Ollama chat helper for the AI assistant."""

import json
from typing import Any, Dict, List, Optional, Sequence

import requests

from services.ollama_manager import ollama_api_url


SYSTEM_PROMPT = (
    "你是人员信息管理系统的AI分析助手。"
    "你只能根据用户筛选后的表格数据回答问题，不要推测未提供的内容。"
)
MAX_HISTORY_MESSAGES = 20
ALLOWED_HISTORY_ROLES = {"user", "assistant"}
CONTEXT_ERROR_PATTERNS = (
    "context length",
    "context window",
    "context limit",
    "context_length",
    "maximum context",
    "exceeds context",
    "too many tokens",
    "prompt is too long",
)


def build_messages(
    question: str,
    analysis_payload: dict,
    history_messages: Optional[Sequence[Dict[str, str]]] = None,
) -> List[Dict[str, str]]:
    data = {
        "tables": _tables_for_prompt(analysis_payload.get("tables") or {}),
    }
    user_prompt = "\n".join(
        [
            "筛选后的数据如下：",
            _to_json(data),
            "",
            "请仅根据以上筛选后的数据回答用户问题，不要补充未提供的字段或推测不存在的信息。",
            "如果数据不足以回答，请直接说明不足。",
            "",
            "用户问题：",
            str(question),
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

    answer_content = _post_chat(
        model_name,
        build_messages(question, analysis_payload, history_messages),
        n_ctx,
        timeout,
    )
    return str(answer_content).strip()


def is_context_length_error(error: Exception) -> bool:
    error_text = "\n".join(_error_texts(error)).lower()
    return any(pattern in error_text for pattern in CONTEXT_ERROR_PATTERNS)


def _post_chat(model_name: str, messages: List[Dict[str, str]], n_ctx: int, timeout: float) -> str:
    response = requests.post(
        ollama_api_url("/api/chat"),
        json={
            "model": model_name,
            "messages": messages,
            "stream": False,
            "options": {"num_ctx": n_ctx},
        },
        timeout=timeout,
    )
    response.raise_for_status()
    return str(response.json().get("message", {}).get("content", "")).strip()


def _error_texts(error: Exception) -> List[str]:
    texts = [str(error)]
    response = getattr(error, "response", None)
    if response is None:
        return texts

    for attr_name in ("text", "content"):
        value = getattr(response, attr_name, None)
        if isinstance(value, bytes):
            texts.append(value.decode("utf-8", errors="replace"))
        elif value:
            texts.append(str(value))

    try:
        texts.append(_to_json(response.json()))
    except Exception:
        pass
    return texts


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


def _tables_for_prompt(tables: Dict[str, dict]) -> List[dict]:
    prompt_tables = []
    for table_name, table in tables.items():
        field_labels = dict(table.get("field_labels") or {})
        selected_fields = list(field_labels.keys())
        prompt_tables.append(
            {
                "table_name": table.get("table_name") or table_name,
                "table_label": table.get("table_label") or table_name,
                "fields": _field_descriptions(selected_fields, field_labels),
                "rows": _project_rows(table.get("rows") or [], selected_fields),
            }
        )
    return prompt_tables


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
