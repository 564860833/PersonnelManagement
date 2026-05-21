"""User-facing answer rendering for deterministic AI query results."""

from typing import Sequence

from services.ai_catalog import AICatalog
from services.ai_types import AIQueryPlan, AIQueryResult


class AIAnswerer:
    def render(self, plan: AIQueryPlan, result: AIQueryResult, catalog: AICatalog) -> str:
        if plan.intent == "unsupported":
            return f"抱歉，{result.message or '当前问题缺少明确字段、取值或业务规则，无法可靠计算。'}"
        if plan.intent in {"count_total", "conditional_count"}:
            return self._count_answer(plan, result, catalog)
        if plan.intent == "distribution":
            return self._distribution_answer(plan, result, catalog)
        if plan.intent == "compare":
            if "boolean" in plan.metrics or result.boolean_value is not None:
                return self._boolean_answer(result)
            return self._aggregate_answer(plan, result, catalog)
        if plan.intent == "field_stats":
            return self._field_stats_answer(result, catalog)
        if plan.intent == "date_range":
            return self._date_range_answer(result, catalog)
        if plan.intent == "subjective_assessment":
            return self._subjective_answer(plan, result, catalog)
        return self._list_answer(result, catalog)

    def _count_answer(self, plan: AIQueryPlan, result: AIQueryResult, catalog: AICatalog) -> str:
        unit = _unit(catalog)
        scope = "；".join(result.evidence) if result.evidence else f"当前【{catalog.table_label}】查询结果"
        lines = [
            f"统计结果：{result.matched_count} {unit}",
            f"统计口径：{scope}",
            f"数据范围：{result.scope or f'当前查询结果，共 {result.total_count} 条'}",
        ]
        if plan.intent == "conditional_count":
            lines.append(f"匹配依据：{'；'.join(result.evidence) if result.evidence else '未识别到明确条件'}")
        return _with_warnings(lines, result)

    def _distribution_answer(self, plan: AIQueryPlan, result: AIQueryResult, catalog: AICatalog) -> str:
        if result.message:
            return f"抱歉，{result.message}"
        if not result.groups:
            return _with_warnings(["没有可统计的分布数据。", f"数据范围：{result.scope}"], result)

        group_labels = [group.label or catalog.label(group.field) for group in plan.group_by]
        headers = group_labels + ["数量", "占比"]
        rows = []
        for item in result.groups:
            values = [part["value"] for part in item["keys"]]
            rows.append(values + [item["count"], f"{item['percent']:.1%}"])

        top = result.groups[0]
        top_label = " / ".join(part["value"] for part in top["keys"])
        lines = [
            f"共匹配 {result.matched_count} 条记录，分布如下：",
            _markdown_table(headers, rows),
            f"数量最多的是 {top_label}，共 {top['count']} 条。",
            f"统计口径：{'；'.join(result.evidence) if result.evidence else '按当前结果分组统计'}",
            f"数据范围：{result.scope}",
        ]
        return _with_warnings(lines, result)

    def _aggregate_answer(self, plan: AIQueryPlan, result: AIQueryResult, catalog: AICatalog) -> str:
        if result.message:
            return f"抱歉，{result.message}"
        if not plan.aggregates:
            return "抱歉，缺少可计算字段。"
        aggregate = plan.aggregates[0]
        operation = _operation_label(aggregate.operation)
        field_label = catalog.label(aggregate.field)
        names = _names_from_rows(result.aggregate_rows)
        subject = names or "匹配对象"
        if aggregate.operation == "average":
            lead = f"{field_label}的平均值为 {result.aggregate_value}，参与统计 {result.matched_count} 条。"
        else:
            lead = f"{field_label}{operation}的是 {subject}，结果为 {result.aggregate_value}。"
        return _with_warnings(
            [
                lead,
                f"统计口径：{'；'.join(result.evidence) if result.evidence else field_label}",
                f"数据范围：{result.scope}",
            ],
            result,
        )

    def _boolean_answer(self, result: AIQueryResult) -> str:
        if result.boolean_value is None:
            return "抱歉，根据现有数据无法回答该问题。"
        prefix = "是" if result.boolean_value else "否"
        evidence = "；".join(result.evidence) if result.evidence else "当前数据匹配结果"
        return _with_warnings([f"{prefix}。依据：{evidence}。", f"数据范围：{result.scope}"], result)

    def _field_stats_answer(self, result: AIQueryResult, catalog: AICatalog) -> str:
        if not result.groups:
            return "当前没有可汇总的字段数据。"
        rows = []
        for item in result.groups:
            key = item["keys"][0]
            rows.append([key["label"], item["count"], item.get("empty_count", 0), item.get("unique_count", 0), f"{item['percent']:.1%}"])
        lines = [
            f"当前【{catalog.table_label}】共 {result.total_count} 条记录，字段完整性如下：",
            _markdown_table(["字段", "非空数", "空值数", "唯一值数", "非空占比"], rows),
            f"数据范围：{result.scope}",
        ]
        return _with_warnings(lines, result)

    def _date_range_answer(self, result: AIQueryResult, catalog: AICatalog) -> str:
        if not result.groups:
            return "当前没有可统计的日期字段。"
        rows = []
        for item in result.groups:
            key = item["keys"][0]
            rows.append([key["label"], item["count"], item.get("min", ""), item.get("max", "")])
        lines = [
            f"当前【{catalog.table_label}】日期范围如下：",
            _markdown_table(["字段", "非空数", "最早值", "最晚值"], rows),
            f"数据范围：{result.scope}",
        ]
        return _with_warnings(lines, result)

    def _subjective_answer(self, plan: AIQueryPlan, result: AIQueryResult, catalog: AICatalog) -> str:
        if result.message:
            return result.message
        headers = [_field_label(field, catalog) for field in result.fields]
        rows = [[row.get(field, "") for field in result.fields] for row in result.display_rows]
        lines = [
            "这是基于已确认规则的辅助分析，不代表最终人事结论。",
            f"评分口径：{'；'.join(result.evidence)}",
            f"共计算 {result.matched_count} 条记录，以下按辅助评分展示：",
            _markdown_table(headers, rows),
            f"数据范围：{result.scope}",
        ]
        if result.sensitive_fields_removed:
            lines.append(f"已排除敏感字段：{'、'.join(result.sensitive_fields_removed)}")
        return _with_warnings(lines, result)

    def _list_answer(self, result: AIQueryResult, catalog: AICatalog) -> str:
        if result.matched_count == 0:
            return _with_warnings(["没有找到匹配的明细。", f"数据范围：{result.scope}"], result)
        headers = [_field_label(field, catalog) for field in result.fields]
        rows = [[row.get(field, "") for field in result.fields] for row in result.display_rows]
        lead = f"共匹配 {result.matched_count} 条记录"
        if result.truncated:
            lead += f"，以下仅展示前 {len(result.display_rows)} 条"
        lead += "："
        lines = [
            lead,
            _markdown_table(headers, rows),
            f"匹配依据：{'；'.join(result.evidence) if result.evidence else '当前查询结果'}",
            f"数据范围：{result.scope}",
        ]
        return _with_warnings(lines, result)


def _with_warnings(lines: Sequence[str], result: AIQueryResult) -> str:
    output = [line for line in lines if line]
    if result.warnings:
        output.append("提示：" + "；".join(result.warnings))
    return "\n\n".join(output)


def _unit(catalog: AICatalog) -> str:
    return "人" if catalog.table_name == "base_info" else "条记录"


def _field_label(field: str, catalog: AICatalog) -> str:
    return {
        "__score": "辅助评分",
        "__score_basis": "主要依据",
        "__missing": "缺失信息",
    }.get(field, catalog.label(field))


def _operation_label(operation: str) -> str:
    return {
        "max": "最高",
        "min": "最低",
        "oldest": "最老",
        "youngest": "最年轻",
        "earliest": "最早",
        "latest": "最晚",
        "mode": "最多",
    }.get(operation, operation)


def _names_from_rows(rows: Sequence[dict]) -> str:
    names = []
    for row in rows:
        name = str(row.get("name", "")).strip()
        if name and name not in names:
            names.append(name)
    return "、".join(names)


def _markdown_table(headers: Sequence, rows: Sequence[Sequence]) -> str:
    header_line = "| " + " | ".join(_table_cell(value) for value in headers) + " |"
    separator = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(_table_cell(value) for value in row) + " |" for row in rows]
    return "\n".join([header_line, separator] + body)


def _table_cell(value) -> str:
    return str(value).replace("|", "\\|")
