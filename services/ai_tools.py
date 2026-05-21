"""Program-side tool routing for AI-assisted personnel analysis."""

import re
from collections import Counter
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

import pandas as pd

from metadata.constants import TABLE_DATE_FIELDS, get_table_label
from services.ai_retrieval import LocalRetrievalIndex, RetrievalResult


TOP_VALUE_LIMIT = 10
TOOL_ROW_LIMIT = 20


@dataclass
class AnalysisToolResult:
    direct_answer: str
    context_markdown: str
    called_tools: List[str]
    retrieval_degraded: bool = False
    retrieval_message: str = ""


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
        self.selected_fields = [field for field in selected_fields if field]
        self.field_labels = dict(field_labels or {})
        self.selected_fields = _existing_fields(self.rows, self.selected_fields)
        self.retrieval_index = retrieval_index or LocalRetrievalIndex(
            self.rows,
            self.selected_fields,
            self.field_labels,
        )


def run_analysis_tools(
    table_name: str,
    rows: Sequence[dict],
    selected_fields: Sequence[str],
    field_labels: Dict[str, str],
    user_question: str,
    table_label: str = None,
    tool_context: Optional[AIToolContext] = None,
) -> AnalysisToolResult:
    context = tool_context or AIToolContext(table_name, rows, selected_fields, field_labels, table_label)
    question = _normalise(user_question)

    if not context.rows or not context.selected_fields:
        return AnalysisToolResult(
            direct_answer="",
            context_markdown="- 当前没有可分析数据。",
            called_tools=[],
        )

    called_tools = []
    sections = []
    direct_answer = ""
    retrieval_result = None

    if _is_total_count_question(question):
        called_tools.append("count_rows")
        section = _tool_count_rows(context)
        sections.append(section)
        unit = "人" if table_name == "base_info" else "条记录"
        direct_answer = f"当前【{context.table_label}】表的当前查询结果共有 **{len(context.rows)} {unit}**。"

    distribution_fields = _fields_for_distribution(question, context)
    if distribution_fields:
        distribution_filter = _build_distribution_filter(question, context, distribution_fields)
        called_tools.append("distribution")
        sections.append(_tool_distribution(context, distribution_fields, distribution_filter))
        if not direct_answer and _is_simple_distribution_question(question):
            direct_answer = sections[-1]

    date_fields = _fields_for_date_range(question, context)
    if date_fields:
        called_tools.append("date_range")
        sections.append(_tool_date_range(context, date_fields))

    stats_fields = _fields_for_field_stats(question, context)
    if stats_fields:
        called_tools.append("field_stats")
        sections.append(_tool_field_stats(context, stats_fields))

    if _should_semantic_search(question, context, bool(distribution_fields)) and not _distribution_only(question, bool(distribution_fields)):
        called_tools.append("semantic_search")
        retrieval_result = context.retrieval_index.search(question)
        sections.append(_tool_semantic_search(context, retrieval_result))
        if retrieval_result.field_matches or retrieval_result.row_matches:
            called_tools.append("list_rows")
            sections.append(_tool_list_rows(context, retrieval_result))

    if not called_tools:
        called_tools.append("semantic_search")
        retrieval_result = context.retrieval_index.search(question)
        sections.append(_tool_semantic_search(context, retrieval_result))
        if retrieval_result.field_matches or retrieval_result.row_matches:
            called_tools.append("list_rows")
            sections.append(_tool_list_rows(context, retrieval_result))

    retrieval_degraded = bool(retrieval_result and retrieval_result.degraded)
    retrieval_message = retrieval_result.message if retrieval_result else ""
    tool_header = "## 工具调用结果\n" + f"- 已调用工具：{', '.join(dict.fromkeys(called_tools))}"
    if retrieval_degraded:
        tool_header += f"\n- 语义检索状态：降级（{retrieval_message or 'embedding 不可用'}）"
    elif retrieval_result and retrieval_result.embedding_used:
        tool_header += "\n- 语义检索状态：已使用本地 embedding"

    return AnalysisToolResult(
        direct_answer=direct_answer,
        context_markdown=tool_header + "\n\n" + "\n\n".join(section for section in sections if section),
        called_tools=list(dict.fromkeys(called_tools)),
        retrieval_degraded=retrieval_degraded,
        retrieval_message=retrieval_message,
    )


def _tool_count_rows(context: AIToolContext) -> str:
    unit = "人" if context.table_name == "base_info" else "条记录"
    return "### count_rows\n" + _markdown_table(["指标", "值"], [["当前结果总数", f"{len(context.rows)} {unit}"]])


def _tool_distribution(context: AIToolContext, fields: Sequence[str], distribution_filter=None) -> str:
    rows = []
    source_rows = distribution_filter["rows"] if distribution_filter else context.rows
    total = len(source_rows)
    if total == 0:
        return "### distribution\n_过滤后没有可统计的数据_"

    for field in fields:
        counts = Counter(_normalise(row.get(field, "")) for row in source_rows)
        counts.pop("", None)
        for value, count in counts.most_common(TOP_VALUE_LIMIT):
            rows.append([_label(field, context), value, count, f"{count / total:.1%}"])
    if not rows:
        return "### distribution\n_没有可统计的分类取值_"

    lines = ["### distribution"]
    if distribution_filter:
        lines.append(f"- 过滤条件：{distribution_filter['summary']}")
        lines.append(f"- 过滤后总数：{total} 条")
    lines.append(_markdown_table(["字段", "取值", "人数/条数", "占比"], rows))
    return "\n".join(lines)


def _tool_date_range(context: AIToolContext, fields: Sequence[str]) -> str:
    rows = []
    for field in fields:
        values = [_normalise(row.get(field, "")) for row in context.rows]
        values = [value for value in values if value]
        if values:
            rows.append([_label(field, context), len(values), min(values, key=_date_sort_key), max(values, key=_date_sort_key)])
        else:
            rows.append([_label(field, context), 0, "", ""])
    return "### date_range\n" + _markdown_table(["字段", "非空数", "最早值", "最晚值"], rows)


def _tool_field_stats(context: AIToolContext, fields: Sequence[str]) -> str:
    rows = []
    total = len(context.rows)
    for field in fields:
        values = [_normalise(row.get(field, "")) for row in context.rows]
        non_empty = sum(1 for value in values if value)
        rows.append([_label(field, context), non_empty, total - non_empty, len(set(value for value in values if value))])
    return "### field_stats\n" + _markdown_table(["字段", "非空数", "空值数", "唯一值数"], rows)


def _tool_semantic_search(context: AIToolContext, result: RetrievalResult) -> str:
    if not result.field_matches and not result.row_matches:
        return "### semantic_search\n_没有检索到与问题直接相关的字段取值或人员明细_"

    rows = []
    for match in result.field_matches:
        rows.append([
            match.field_label,
            match.value,
            f"{match.score:.2f}",
            match.match_type,
            match.row_count,
            match.matched_text,
        ])
    if not rows:
        return "### semantic_search\n_未命中字段取值，仅命中行摘要，见 list_rows_"
    return "### semantic_search\n" + _markdown_table(["来源字段", "原始取值", "相似度", "匹配方式", "匹配行数", "匹配依据"], rows)


def _tool_list_rows(context: AIToolContext, result: RetrievalResult) -> str:
    matched_indices = _matched_indices(result)
    total_matches = len(matched_indices)
    rows = [context.rows[index] for index in matched_indices[:TOOL_ROW_LIMIT] if 0 <= index < len(context.rows)]
    if not rows:
        return "### list_rows\n_无匹配明细_"

    fields = _display_fields(rows, context.selected_fields)
    table_rows = []
    for row in rows[:TOOL_ROW_LIMIT]:
        table_rows.append([_normalise(row.get(field, "")) for field in fields])

    lines = ["### list_rows", f"- 匹配总数：{total_matches} 条"]
    if total_matches > len(table_rows):
        lines.append(
            f"- 数据被截断：为了防止上下文过载，以下仅展示前 {len(table_rows)} 条匹配明细；"
            "完整名单请通过界面筛选功能查看。"
        )
    lines.append(_markdown_table([_label(field, context) for field in fields], table_rows))
    return "\n".join(lines)


def _fields_for_distribution(question: str, context: AIToolContext) -> List[str]:
    if not _is_distribution_question(question):
        return []
    fields = _fields_mentioned(question, context)
    grouped_fields = [
        field for field in fields
        if _field_used_as_distribution_group(question, field, context)
    ]
    if grouped_fields:
        return [field for field in grouped_fields if field not in _date_fields(context.table_name)]
    if fields:
        return [field for field in fields if field not in _date_fields(context.table_name)]
    return [
        field for field in context.selected_fields
        if field not in {"id", "sequence", "name"} and field not in _date_fields(context.table_name)
    ][:2]


def _field_used_as_distribution_group(question: str, field: str, context: AIToolContext) -> bool:
    for term in _field_terms(field, context):
        patterns = (f"各{term}", f"每{term}", f"按{term}", f"{term}分布", f"{term}分别", f"{term}排行", f"{term}占比")
        if any(pattern in question for pattern in patterns):
            return True
    return False


def _build_distribution_filter(question: str, context: AIToolContext, distribution_fields: Sequence[str]):
    result = context.retrieval_index.search(question, top_k=8, row_limit=0)
    usable_matches = [
        match for match in result.field_matches
        if match.field_name not in distribution_fields
        and match.field_name not in {"id", "sequence", "name"}
        and match.match_type in {"精确取值匹配", "同义词匹配", "语义向量匹配"}
    ]
    if not usable_matches:
        return None

    indices_by_field: Dict[str, set] = {}
    summaries = []
    for match in usable_matches:
        indices_by_field.setdefault(match.field_name, set()).update(match.row_indices)
        summaries.append(f"{match.field_label} = {match.value}（{match.match_type}，匹配 {match.row_count} 条）")

    selected_indices = None
    for indices in indices_by_field.values():
        selected_indices = set(indices) if selected_indices is None else selected_indices & set(indices)
    selected_indices = selected_indices or set()

    return {
        "rows": [context.rows[index] for index in sorted(selected_indices) if 0 <= index < len(context.rows)],
        "summary": "；".join(dict.fromkeys(summaries)),
    }


def _fields_for_date_range(question: str, context: AIToolContext) -> List[str]:
    if not any(word in question for word in ("日期", "时间", "年月", "最早", "最晚", "范围")):
        return []
    date_fields = _date_fields(context.table_name)
    fields = [field for field in _fields_mentioned(question, context) if field in date_fields]
    return fields or [field for field in context.selected_fields if field in date_fields][:2]


def _fields_for_field_stats(question: str, context: AIToolContext) -> List[str]:
    if not any(word in question for word in ("空值", "缺失", "完整", "非空", "唯一", "字段统计")):
        return []
    return _fields_mentioned(question, context) or context.selected_fields[:5]


def _fields_mentioned(question: str, context: AIToolContext) -> List[str]:
    fields = []
    for field in context.selected_fields:
        if any(term and term in question for term in _field_terms(field, context)):
            fields.append(field)
    return fields


def _field_terms(field: str, context: AIToolContext) -> List[str]:
    label = _label(field, context)
    return [field, label] + [part for part in re.split(r"[/、\s]+", label) if part]


def _should_semantic_search(question: str, context: AIToolContext, has_distribution: bool) -> bool:
    if has_distribution and not any(word in question for word in ("的", "哪些", "谁", "情况", "名单", "人员")):
        return False
    if any(_normalise(row.get("name", "")) and _normalise(row.get("name", "")) in question for row in context.rows):
        return True
    return any(word in question for word in ("查", "查询", "查看", "哪些", "谁", "人员", "情况", "名单", "部门", "岗位", "资深", "老员工", "开发", "研发"))


def _matched_indices(result: RetrievalResult) -> List[int]:
    indices = []
    if result.field_matches:
        for match in result.field_matches:
            indices.extend(match.row_indices)
    else:
        indices.extend(match.row_index for match in result.row_matches)

    unique_indices = []
    seen = set()
    for index in indices:
        if index not in seen:
            seen.add(index)
            unique_indices.append(index)
    return unique_indices


def _is_total_count_question(question: str) -> bool:
    if not question:
        return False
    if _is_distribution_question(question):
        return False
    count_words = ("几个人", "多少人", "几人", "几名", "人数", "总人数", "总数", "共有", "有多少")
    return any(word in question for word in count_words)


def _is_distribution_question(question: str) -> bool:
    return any(word in question for word in ("分别", "分布", "各", "每", "按", "排行", "占比", "比例", "统计"))


def _is_simple_distribution_question(question: str) -> bool:
    return _is_distribution_question(question) and not any(word in question for word in ("分析", "为什么", "建议", "趋势"))


def _distribution_only(question: str, has_distribution: bool) -> bool:
    if not has_distribution or not _is_simple_distribution_question(question):
        return False
    return not any(word in question for word in ("名单", "哪些", "谁", "列出", "明细", "详情"))


def _existing_fields(rows: Sequence[dict], fields: Sequence[str]) -> List[str]:
    if not rows:
        return list(fields)
    available = set()
    for row in rows[:20]:
        available.update(row.keys())
    return [field for field in fields if field in available]


def _display_fields(rows: Sequence[dict], selected_fields: Sequence[str]) -> List[str]:
    available = set()
    for row in rows[:20]:
        available.update(row.keys())
    fields = []
    for field in ("sequence", "name"):
        if field in available and field not in fields:
            fields.append(field)
    for field in selected_fields:
        if field in available and field not in fields:
            fields.append(field)
    return fields[:8]


def _date_fields(table_name: str) -> set:
    return set(TABLE_DATE_FIELDS.get(table_name, []))


def _date_sort_key(value: str):
    text = str(value)
    match = re.search(r"(\d{4})(?:[.\-/年](\d{1,2}))?(?:[.\-/月](\d{1,2}))?", text)
    if not match:
        return (9999, 99, 99, text)
    return (int(match.group(1)), int(match.group(2) or 1), int(match.group(3) or 1), text)


def _label(field: str, context: AIToolContext) -> str:
    return context.field_labels.get(field, field)


def _normalise(value) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    return re.sub(r"\s+", " ", text)


def _markdown_table(headers: Sequence, rows: Sequence[Sequence]) -> str:
    header_line = "| " + " | ".join(_table_cell(value, 80) for value in headers) + " |"
    separator = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(_table_cell(value, 120) for value in row) + " |" for row in rows]
    return "\n".join([header_line, separator] + body)


def _table_cell(value, max_length: int) -> str:
    text = _normalise(value)
    if len(text) > max_length:
        text = text[: max_length - 1] + "…"
    return text.replace("|", "\\|")
