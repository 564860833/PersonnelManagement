"""Deterministic context builder for AI-assisted personnel analysis."""

import re
from typing import Dict, Iterable, List, Sequence

import pandas as pd

from metadata.constants import TABLE_DATE_FIELDS, get_table_label
from metadata.query_options import GRADE_OPTIONS


FULL_DETAIL_LIMIT = 100
SAMPLE_DETAIL_LIMIT = 30
TOP_VALUE_LIMIT = 10
FOCUS_ROW_LIMIT = 10


def build_analysis_context(
    table_name: str,
    rows: Sequence[dict],
    selected_fields: Sequence[str],
    field_labels: Dict[str, str],
    user_question: str,
    table_label: str = None,
    tool_result=None,
) -> str:
    """Build markdown context whose statistics are computed outside the LLM."""
    rows = list(rows or [])
    selected_fields = [field for field in selected_fields if field]
    field_labels = dict(field_labels or {})
    table_label = table_label or get_table_label(table_name)

    if not selected_fields and rows:
        selected_fields = [field for field in rows[0].keys() if field != "id"]
    selected_fields = _existing_fields(rows, selected_fields)

    if tool_result is not None:
        return _build_tool_augmented_context(
            table_name,
            rows,
            selected_fields,
            field_labels,
            user_question,
            table_label,
            tool_result,
        )

    if not rows or not selected_fields:
        return "\n".join(
            [
                "## 数据范围",
                f"- 当前表：{table_label} ({table_name})",
                "- 当前结果行数：0",
                "- 结论限制：当前没有可分析数据。若用户提问涉及具体人员或统计，请回答“抱歉，根据现有数据无法回答该问题”。",
            ]
        )

    df = pd.DataFrame(rows)
    row_count = len(df)
    normalised = _normalised_frame(df, selected_fields)

    sections = [
        _build_scope_section(table_name, table_label, row_count, selected_fields, field_labels),
        _build_field_reference_section(table_name, selected_fields, field_labels),
        _build_basic_stats_section(normalised, selected_fields, field_labels),
        _build_distribution_section(normalised, table_name, selected_fields, field_labels),
        _build_date_section(normalised, table_name, selected_fields, field_labels),
        _build_focus_section(df, user_question, selected_fields, field_labels),
        _build_detail_section(normalised, row_count, selected_fields, field_labels),
        _build_business_rules_section(selected_fields, user_question, field_labels),
        _build_answer_rules_section(row_count),
    ]

    return "\n\n".join(section for section in sections if section)


def _build_tool_augmented_context(
    table_name: str,
    rows: Sequence[dict],
    selected_fields: Sequence[str],
    field_labels: Dict[str, str],
    user_question: str,
    table_label: str,
    tool_result,
) -> str:
    row_count = len(rows or [])
    sections = [
        _build_compact_scope_section(table_name, table_label, row_count, selected_fields, field_labels),
        _build_field_reference_section(table_name, selected_fields, field_labels) if selected_fields else "",
        _build_business_rules_section(selected_fields, user_question, field_labels),
        _build_compact_answer_rules_section(),
        getattr(tool_result, "context_markdown", ""),
    ]
    return "\n\n".join(section for section in sections if section)


def _build_compact_scope_section(
    table_name: str,
    table_label: str,
    row_count: int,
    selected_fields: Sequence[str],
    field_labels: Dict[str, str],
) -> str:
    selected_labels = "、".join(_label(field, field_labels) for field in selected_fields)
    return "\n".join(
        [
            "## 数据范围",
            f"- 当前表：{table_label} ({table_name})",
            f"- 当前结果行数：{row_count}",
            f"- 选中字段数：{len(selected_fields)}",
            f"- 选中字段：{selected_labels}",
            "- 上下文策略：本轮只提供程序按问题调用工具后的结果，不默认展开全量统计或全量明细。",
        ]
    )


def _existing_fields(rows: Sequence[dict], fields: Sequence[str]) -> List[str]:
    if not rows:
        return list(fields)
    available = set()
    for row in rows[:20]:
        available.update(row.keys())
    return [field for field in fields if field in available]


def _normalised_frame(df: pd.DataFrame, fields: Sequence[str]) -> pd.DataFrame:
    data = {}
    for field in fields:
        data[field] = df[field].map(_normalise_value) if field in df.columns else ""
    return pd.DataFrame(data)


def _normalise_value(value) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    text = re.sub(r"\s+", " ", text)
    return text


def _label(field: str, field_labels: Dict[str, str]) -> str:
    return field_labels.get(field, field)


def _date_fields(table_name: str) -> set:
    return set(TABLE_DATE_FIELDS.get(table_name, []))


def _build_scope_section(
    table_name: str,
    table_label: str,
    row_count: int,
    selected_fields: Sequence[str],
    field_labels: Dict[str, str],
) -> str:
    selected_labels = "、".join(_label(field, field_labels) for field in selected_fields)
    detail_rule = (
        f"当前结果不超过 {FULL_DETAIL_LIMIT} 行，明细数据为全量。"
        if row_count <= FULL_DETAIL_LIMIT
        else f"当前结果超过 {FULL_DETAIL_LIMIT} 行，统计基于全量 {row_count} 行；明细仅提供前 {SAMPLE_DETAIL_LIMIT} 行样本用于举例。"
    )
    return "\n".join(
        [
            "## 数据范围",
            f"- 当前表：{table_label} ({table_name})",
            f"- 当前结果行数：{row_count}",
            f"- 选中字段数：{len(selected_fields)}",
            f"- 选中字段：{selected_labels}",
            "- 统计口径：总数、比例、分布、排行均由程序基于当前表全量结果计算。",
            f"- 明细策略：{detail_rule}",
        ]
    )


def _build_field_reference_section(table_name: str, fields: Sequence[str], labels: Dict[str, str]) -> str:
    rows = []
    date_fields = _date_fields(table_name)
    for field in fields:
        rule = "普通文本字段"
        if field in date_fields:
            rule = "日期/年月字段，按原始导入值展示；排序统计按可识别的年月日计算。"
        if field == "current_grade":
            rule = "职级/等级字段；如需排序，只能参考系统内置职级顺序。"
        if field == "next_promotion":
            rule = "已导入的晋升相关字段；只能解释字段原值，不能自行判断政策资格。"
        rows.append([_label(field, labels), field, rule])

    return "## 字段说明\n" + _markdown_table(["字段", "数据库字段", "规则"], rows)


def _build_basic_stats_section(df: pd.DataFrame, fields: Sequence[str], labels: Dict[str, str]) -> str:
    rows = []
    total = len(df)
    for field in fields:
        series = df[field] if field in df.columns else pd.Series(dtype=str)
        non_empty = int((series != "").sum())
        missing = total - non_empty
        unique_count = int(series[series != ""].nunique())
        rows.append([_label(field, labels), non_empty, missing, unique_count])
    return "## 全量字段统计\n" + _markdown_table(["字段", "非空数", "空值数", "唯一值数"], rows)


def _build_distribution_section(
    df: pd.DataFrame,
    table_name: str,
    fields: Sequence[str],
    labels: Dict[str, str],
) -> str:
    total = len(df)
    if total == 0:
        return ""

    date_fields = _date_fields(table_name)
    chunks = []
    for field in fields:
        if field in date_fields or not _is_categorical_field(df[field], field, total):
            continue
        counts = df[field][df[field] != ""].value_counts().head(TOP_VALUE_LIMIT)
        if counts.empty:
            continue
        rows = []
        for value, count in counts.items():
            percent = f"{count / total:.1%}"
            rows.append([_clip(value, 60), int(count), percent])
        chunks.append(f"### {_label(field, labels)} Top {TOP_VALUE_LIMIT}\n" + _markdown_table(["取值", "人数/条数", "占比"], rows))

    if not chunks:
        return ""
    return "## 全量分类分布\n" + "\n\n".join(chunks)


def _is_categorical_field(series: pd.Series, field: str, total: int) -> bool:
    if field in {"id", "sequence", "name"}:
        return False
    non_empty = series[series != ""]
    if non_empty.empty:
        return False
    unique_count = int(non_empty.nunique())
    lengths = non_empty.map(len)
    if int(lengths.max()) > 120 or float(lengths.mean()) > 36:
        return False
    return unique_count <= 50 or unique_count <= max(10, total * 0.5)


def _build_date_section(
    df: pd.DataFrame,
    table_name: str,
    fields: Sequence[str],
    labels: Dict[str, str],
) -> str:
    rows = []
    date_fields = _date_fields(table_name)
    for field in fields:
        if field not in date_fields:
            continue
        values = [value for value in df[field].tolist() if value]
        if not values:
            rows.append([_label(field, labels), 0, "", ""])
            continue
        earliest = min(values, key=_date_sort_key)
        latest = max(values, key=_date_sort_key)
        rows.append([_label(field, labels), len(values), earliest, latest])
    if not rows:
        return ""
    return "## 全量日期范围\n" + _markdown_table(["字段", "非空数", "最早值", "最晚值"], rows)


def _date_sort_key(value: str):
    text = str(value)
    match = re.search(r"(\d{4})(?:[.\-/年](\d{1,2}))?(?:[.\-/月](\d{1,2}))?", text)
    if not match:
        return (9999, 99, 99, text)
    year = int(match.group(1))
    month = int(match.group(2) or 1)
    day = int(match.group(3) or 1)
    return (year, month, day, text)


def _build_focus_section(
    df: pd.DataFrame,
    question: str,
    selected_fields: Sequence[str],
    labels: Dict[str, str],
) -> str:
    question = question or ""
    parts = []
    used_signatures = set()

    if "name" in df.columns:
        names = sorted(
            {_normalise_value(value) for value in df["name"].tolist() if _normalise_value(value)},
            key=len,
            reverse=True,
        )
        for name in names:
            if name and name in question:
                matches = df[df["name"].map(_normalise_value) == name]
                parts.append(_focus_block(f"姓名匹配：{name}", matches, selected_fields, labels))
                used_signatures.add(("name", name))
                break

    for field in selected_fields:
        if field not in df.columns:
            continue
        values = sorted(
            {_normalise_value(value) for value in df[field].tolist() if _normalise_value(value)},
            key=len,
            reverse=True,
        )
        for value in values:
            if (field, value) in used_signatures or not _value_can_match_question(field, value):
                continue
            if value in question:
                matches = df[df[field].map(_normalise_value) == value]
                parts.append(_focus_block(f"字段取值匹配：{_label(field, labels)} = {value}", matches, selected_fields, labels))
                used_signatures.add((field, value))
                break
        if len(parts) >= 3:
            break

    if not parts:
        return ""
    return "## 本轮问题匹配\n" + "\n\n".join(parts)


def _value_can_match_question(field: str, value: str) -> bool:
    if field in {"id", "sequence"}:
        return False
    if field in {"gender", "relation"}:
        return len(value) >= 1
    return len(value) >= 2


def _focus_block(title: str, matches: pd.DataFrame, selected_fields: Sequence[str], labels: Dict[str, str]) -> str:
    display_fields = _focus_display_fields(matches, selected_fields)
    return "\n".join(
        [
            f"### {title}",
            f"- 全量匹配条数：{len(matches)}",
            _records_to_table(matches.head(FOCUS_ROW_LIMIT).to_dict("records"), display_fields, labels),
        ]
    )


def _focus_display_fields(matches: pd.DataFrame, selected_fields: Sequence[str]) -> List[str]:
    fields = []
    for field in ("sequence", "name"):
        if field in matches.columns and field not in fields:
            fields.append(field)
    for field in selected_fields:
        if field in matches.columns and field not in fields:
            fields.append(field)
    return fields


def _build_detail_section(
    df: pd.DataFrame,
    row_count: int,
    selected_fields: Sequence[str],
    labels: Dict[str, str],
) -> str:
    if row_count <= FULL_DETAIL_LIMIT:
        title = f"## 全量明细（{row_count} 行）"
        detail = df
    else:
        title = f"## 明细样本（前 {SAMPLE_DETAIL_LIMIT} 行，仅用于举例）"
        detail = df.head(SAMPLE_DETAIL_LIMIT)
    return title + "\n" + _records_to_table(detail.to_dict("records"), selected_fields, labels)


def _build_business_rules_section(fields: Sequence[str], question: str, labels: Dict[str, str]) -> str:
    question = question or ""
    lines = []
    grade_label = labels.get("current_grade", "职级/等级")
    if "current_grade" in fields or "职级" in question or "等级" in question:
        grade_order = " > ".join(str(item) for item in GRADE_OPTIONS)
        lines.append(f"- {grade_label}顺序参考：{grade_order}")
    if "next_promotion" in fields or "晋升" in question:
        lines.append("- 晋升相关结论只能依据“距离下次职级晋升时间”等已导入字段；禁止根据任职时间、职级顺序或政策自行推断，不得根据任职时间自行判断是否具备晋升资格。")
    if not lines:
        return ""
    return "## 业务规则限制\n" + "\n".join(lines)


def _build_answer_rules_section(row_count: int) -> str:
    sample_rule = (
        "- 当前已提供全量明细，可以引用明细回答。"
        if row_count <= FULL_DETAIL_LIMIT
        else "- 当前只提供样本明细；涉及总数、比例、分布、排行时必须使用全量统计，不得把样本当全量。"
    )
    return "\n".join(
        [
            "## 回答约束",
            "- 只能根据本上下文回答，不要编造不存在的字段、人员或政策。",
            "- 如果上下文无法支持用户问题，请回答“抱歉，根据现有数据无法回答该问题”。",
            "- 不要生成 SQL，也不要声称已经执行 SQL。",
            sample_rule,
        ]
    )


def _build_compact_answer_rules_section() -> str:
    return "\n".join(
        [
            "## 回答约束",
            "- 每轮工具结果末尾的【内部回答格式】只用于约束回答形态，禁止在答案中复述这些内部规则。",
            "- 只能根据本轮工具调用结果回答，不要编造不存在的字段、人员或政策。",
            "- 涉及总数、比例、分布、排行时，必须使用工具调用结果中的确定性统计。",
            "- 如果工具调用结果无法支持用户问题，请回答“抱歉，根据现有数据无法回答该问题”。",
            "- 不要输出“工具调用结果”“程序检索结果”“最终答案”“根据工具调用结果”等元叙述。",
            "- 不要生成 SQL，也不要声称已经执行 SQL。",
        ]
    )


def _records_to_table(records: Iterable[dict], fields: Sequence[str], labels: Dict[str, str]) -> str:
    records = list(records)
    if not records:
        return "_无匹配明细_"
    headers = [_label(field, labels) for field in fields]
    rows = []
    for record in records:
        rows.append([_normalise_value(record.get(field, "")) for field in fields])
    return _markdown_table(headers, rows)


def _markdown_table(headers: Sequence, rows: Sequence[Sequence]) -> str:
    header_line = "| " + " | ".join(_table_cell(value, 80) for value in headers) + " |"
    separator = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(_table_cell(value, 120) for value in row) + " |" for row in rows]
    return "\n".join([header_line, separator] + body)


def _table_cell(value, max_length: int) -> str:
    text = _clip(_normalise_value(value), max_length)
    text = text.replace("|", "\\|")
    return text


def _clip(value: str, max_length: int) -> str:
    text = str(value)
    if len(text) <= max_length:
        return text
    return text[: max_length - 1] + "…"
