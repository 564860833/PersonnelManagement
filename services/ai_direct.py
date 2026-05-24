"""Direct Ollama chat helper for the AI assistant."""

import json
from typing import Any, Callable, Dict, List, Optional, Sequence

import requests

from services.ollama_manager import ollama_api_url


SYSTEM_PROMPT = """# 角色设定
你是专业的“人员信息管理系统”数据分析助手。你的任务是客观、精准地分析用户提供的结构化表格数据，并解答疑问。

# 核心纪律（必须严格遵守）
1. 事实至上：仅允许基于下方提供的 JSON 格式“当前筛选数据”回答问题。绝不可编造数据、不可推测未提供的内容。
2. 边界控制：若当前数据无法完整回答问题，必须明确回复“根据当前提供的数据不足以得出结论”，禁止凭空补全。
3. 冲突处理：历史消息仅作为对话语境参考。若历史消息内容与当前提供的数据发生冲突，必须绝对以“当前提供的数据”为准。

# 输出规范
1. 结构化呈现：优先使用 Markdown 列表（- 或 1.）来梳理逻辑。
2. 表格展示：当涉及多个人员比对、统计或多个属性列举时，必须使用 Markdown 表格进行展示。
3. 简明严谨：直接输出分析结果，无需多余的寒暄与废话。"""
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
    return _build_messages_from_analysis_data_json(
        question,
        build_analysis_data_json(analysis_payload),
        history_messages,
    )


def build_analysis_data_json(analysis_payload: dict) -> str:
    data = {
        "tables": _tables_for_prompt((analysis_payload or {}).get("tables") or {}),
    }
    return _to_json(data)


def _build_messages_from_analysis_data_json(
    question: str,
    analysis_data_json: str,
    history_messages: Optional[Sequence[Dict[str, str]]] = None,
) -> List[Dict[str, str]]:
    user_prompt = (
        "以下是本次分析依赖的当前筛选数据：\n"
        "<data>\n"
        f"{analysis_data_json}\n"
        "</data>\n\n"
        "请基于上述数据，回答以下问题：\n"
        "<question>\n"
        f"{question}\n"
        "</question>"
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
    analysis_data_json: Optional[str] = None,
) -> str:
    model_name = (model_name or "").strip()
    if not model_name:
        raise ValueError("未选择可用模型。")

    messages = (
        build_messages(question, analysis_payload, history_messages)
        if analysis_data_json is None
        else _build_messages_from_analysis_data_json(question, analysis_data_json, history_messages)
    )
    answer_content = _post_chat(model_name, messages, n_ctx, timeout)
    return str(answer_content).strip()


def ask_model_stream(
    question: str,
    analysis_payload: dict,
    model_name: str,
    n_ctx: int = 4096,
    timeout: float = 120.0,
    history_messages: Optional[Sequence[Dict[str, str]]] = None,
    on_delta: Optional[Callable[[str], None]] = None,
    analysis_data_json: Optional[str] = None,
) -> str:
    model_name = (model_name or "").strip()
    if not model_name:
        raise ValueError("未选择可用模型。")

    messages = (
        build_messages(question, analysis_payload, history_messages)
        if analysis_data_json is None
        else _build_messages_from_analysis_data_json(question, analysis_data_json, history_messages)
    )
    return _post_chat_stream(model_name, messages, n_ctx, timeout, on_delta=on_delta)


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


def _post_chat_stream(
    model_name: str,
    messages: List[Dict[str, str]],
    n_ctx: int,
    timeout: float,
    on_delta: Optional[Callable[[str], None]] = None,
) -> str:
    response = requests.post(
        ollama_api_url("/api/chat"),
        json={
            "model": model_name,
            "messages": messages,
            "stream": True,
            "options": {"num_ctx": n_ctx},
        },
        timeout=timeout,
        stream=True,
    )
    try:
        response.raise_for_status()
        chunks = []
        for line in response.iter_lines(decode_unicode=True):
            if not line:
                continue
            data = _parse_stream_line(line)
            if data.get("error"):
                raise RuntimeError(str(data.get("error")))

            delta = _stream_delta_content(data)
            if delta:
                chunks.append(delta)
                if on_delta is not None:
                    on_delta(delta)

            if data.get("done"):
                break
        return "".join(chunks).strip()
    finally:
        response.close()


def _parse_stream_line(line: str) -> dict:
    try:
        data = json.loads(line)
    except (TypeError, json.JSONDecodeError) as e:
        raise RuntimeError(f"Invalid Ollama stream response: {line}") from e
    if not isinstance(data, dict):
        raise RuntimeError(f"Invalid Ollama stream response: {line}")
    return data


def _stream_delta_content(data: dict) -> str:
    message = data.get("message")
    if isinstance(message, dict):
        return str(message.get("content") or "")
    if "response" in data:
        return str(data.get("response") or "")
    return ""


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
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
