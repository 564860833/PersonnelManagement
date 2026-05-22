"""Direct Ollama chat helper for the AI assistant."""

import json
import re
from typing import Any, Dict, List, Optional, Sequence

import requests

from services.ollama_manager import ollama_api_url


SYSTEM_PROMPT = "你是人员信息管理系统的 AI 助手。用户会提供当前查询表的数据，你可以结合这些数据回答用户问题。"
SELECTION_SYSTEM_PROMPT = "你是人员信息管理系统的数据字段选择助手。你只能根据 schema 选择本轮问题需要的数据表和字段。"
SELECTION_FAILURE_MESSAGE = "我没能从问题中判断需要哪些表和字段。请把问题说得更具体一些，例如说明要分析职级、奖惩、家庭成员还是简历经历。"
MAX_HISTORY_MESSAGES = 20
ALLOWED_HISTORY_ROLES = {"user", "assistant"}
IDENTITY_FIELDS = ("sequence", "name")


def build_schema_selection_messages(
    question: str,
    analysis_payload: dict,
    history_messages: Optional[Sequence[Dict[str, str]]] = None,
) -> List[Dict[str, str]]:
    schemas = dict(analysis_payload.get("schemas") or {})
    schema_prompt = {
        "schemas": schemas,
        "response_format": {
            "tables": [
                {
                    "table_name": "只能使用 schema 中真实存在的表名",
                    "columns": ["只能使用该表 schema 中真实存在的列名"],
                }
            ]
        },
    }

    user_prompt = "\n".join(
        [
            "可用数据表 schema 如下，schema 只用于选择字段，不包含任何行数据：",
            _to_json(schema_prompt),
            "",
            "请只返回 JSON，不要输出解释、Markdown 或额外文字。",
            "如果无法判断需要哪些字段，请返回 {\"tables\": []}。",
            "",
            "用户问题：",
            question,
        ]
    )
    messages = [{"role": "system", "content": SELECTION_SYSTEM_PROMPT}]
    messages.extend(_sanitize_history_messages(history_messages))
    messages.append({"role": "user", "content": user_prompt})
    return messages


def build_messages(
    question: str,
    analysis_payload: dict,
    history_messages: Optional[Sequence[Dict[str, str]]] = None,
) -> List[Dict[str, str]]:
    data = {
        "筛选后的数据": _tables_for_prompt(analysis_payload.get("tables") or {}),
    }
    user_prompt = "\n".join(
        [
            "筛选后的数据如下：",
            _to_json(data),
            "",
            "只能基于“筛选后的数据”回答。即使 schema 中存在其他字段，如果本轮筛选后的数据没有提供，也不能假设或引用。",
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

    selection_content = _post_chat(
        model_name,
        build_schema_selection_messages(question, analysis_payload, history_messages),
        n_ctx,
        timeout,
    )
    selected_payload = _filter_payload_by_selection(
        analysis_payload,
        _parse_selection_response(selection_content),
    )
    if not selected_payload.get("tables"):
        return SELECTION_FAILURE_MESSAGE

    answer_content = _post_chat(
        model_name,
        build_messages(question, selected_payload, history_messages),
        n_ctx,
        timeout,
    )
    return str(answer_content).strip()


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


def _parse_selection_response(content: str) -> Dict[str, Any]:
    candidate = str(content or "").strip()
    fence_match = re.search(r"```(?:json)?\s*(.*?)```", candidate, re.IGNORECASE | re.DOTALL)
    if fence_match:
        candidate = fence_match.group(1).strip()

    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start < 0 or end <= start:
            return {"tables": []}
        try:
            parsed = json.loads(candidate[start:end + 1])
        except json.JSONDecodeError:
            return {"tables": []}

    if not isinstance(parsed, dict):
        return {"tables": []}
    tables = parsed.get("tables")
    if not isinstance(tables, list):
        return {"tables": []}
    return {"tables": tables}


def _filter_payload_by_selection(analysis_payload: dict, selection: Dict[str, Any]) -> dict:
    schemas = dict(analysis_payload.get("schemas") or {})
    source_tables = dict(analysis_payload.get("tables") or {})
    filtered_tables = {}

    for table_selection in selection.get("tables") or []:
        if not isinstance(table_selection, dict):
            continue

        table_name = str(table_selection.get("table_name", "")).strip()
        if table_name not in schemas or table_name not in source_tables:
            continue

        valid_columns = _schema_column_names(schemas[table_name])
        explicit_columns = _valid_selected_columns(table_selection.get("columns"), valid_columns)
        if not explicit_columns:
            continue

        selected_columns = _with_identity_fields(explicit_columns, valid_columns)
        source_table = dict(source_tables.get(table_name) or {})
        field_labels = dict(source_table.get("field_labels") or {})
        selected_labels = {field: field_labels.get(field, field) for field in selected_columns}
        rows = list(source_table.get("rows") or [])

        filtered_tables[table_name] = {
            "table_name": table_name,
            "table_label": source_table.get("table_label") or schemas[table_name].get("table_label", table_name),
            "field_labels": selected_labels,
            "rows": _project_rows(rows, selected_columns),
        }

    return {"tables": filtered_tables}


def _schema_column_names(schema: dict) -> List[str]:
    names = []
    for column in schema.get("columns") or []:
        if not isinstance(column, dict):
            continue
        name = str(column.get("name", "")).strip()
        if name and name not in names:
            names.append(name)
    return names


def _valid_selected_columns(columns: Any, valid_columns: Sequence[str]) -> List[str]:
    if not isinstance(columns, list):
        return []

    valid_column_set = set(valid_columns)
    selected = []
    for column in columns:
        if isinstance(column, dict):
            column_name = str(column.get("name", "")).strip()
        else:
            column_name = str(column).strip()
        if column_name in valid_column_set and column_name not in selected:
            selected.append(column_name)
    return selected


def _with_identity_fields(columns: Sequence[str], valid_columns: Sequence[str]) -> List[str]:
    selected = []
    for field in IDENTITY_FIELDS:
        if field in valid_columns and field not in selected:
            selected.append(field)
    for field in columns:
        if field not in selected:
            selected.append(field)
    return selected


def _tables_for_prompt(tables: Dict[str, dict]) -> List[dict]:
    prompt_tables = []
    for table_name, table in tables.items():
        field_labels = dict(table.get("field_labels") or {})
        prompt_tables.append(
            {
                "table_name": table.get("table_name") or table_name,
                "table_label": table.get("table_label") or table_name,
                "fields": _field_descriptions(list(field_labels.keys()), field_labels),
                "rows": list(table.get("rows") or []),
            }
        )
    return prompt_tables


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
