"""Deterministic Python executor for structured AI query plans."""

import re
from collections import Counter
from typing import Iterable, List, Sequence, Set, Tuple

from services.ai_catalog import AICatalog
from services.ai_resolver import NEGATIVE_KEYWORDS, POSITIVE_KEYWORDS, SENSITIVE_FIELDS
from services.ai_types import AIAggregate, AIGroupBy, AIQueryFilter, AIQueryPlan, AIQueryResult


DISPLAY_ROW_LIMIT = 20


class AIQueryExecutor:
    def execute(self, plan: AIQueryPlan, catalog: AICatalog) -> AIQueryResult:
        if plan.intent == "unsupported":
            return AIQueryResult(
                intent=plan.intent,
                total_count=len(catalog.rows),
                message="当前问题缺少明确字段、取值或业务规则，无法可靠计算。",
                confidence=plan.confidence,
            )
        if plan.intent == "compare" and "boolean" in plan.metrics:
            return self._execute_boolean(plan, catalog)
        if plan.intent == "field_stats":
            return self._execute_field_stats(plan, catalog)
        if plan.intent == "date_range":
            return self._execute_date_range(plan, catalog)
        if plan.intent == "subjective_assessment":
            return self._execute_subjective_assessment(plan, catalog)

        matched_indices = self._apply_filters(plan.filters, catalog)
        rows = [catalog.rows[index] for index in sorted(matched_indices)]
        evidence = _filter_evidence(plan.filters, catalog)

        if plan.intent == "count_total":
            return AIQueryResult(
                intent=plan.intent,
                matched_count=len(catalog.rows),
                total_count=len(catalog.rows),
                evidence=[f"当前【{catalog.table_label}】查询结果"],
                confidence=plan.confidence,
            )
        if plan.intent == "conditional_count":
            return AIQueryResult(
                intent=plan.intent,
                matched_count=len(rows),
                total_count=len(catalog.rows),
                evidence=evidence,
                confidence=plan.confidence,
            )
        if plan.intent == "distribution":
            return self._execute_distribution(plan, catalog, rows, evidence)
        if plan.intent == "compare":
            return self._execute_aggregate(plan, catalog, rows, evidence)

        display_fields = plan.display_fields or catalog.default_display_fields()
        return AIQueryResult(
            intent="list_records",
            matched_count=len(rows),
            total_count=len(catalog.rows),
            display_rows=[_project_row(row, display_fields) for row in rows[:DISPLAY_ROW_LIMIT]],
            fields=display_fields,
            evidence=evidence,
            truncated=len(rows) > DISPLAY_ROW_LIMIT,
            confidence=plan.confidence,
        )

    def _execute_distribution(
        self,
        plan: AIQueryPlan,
        catalog: AICatalog,
        rows: Sequence[dict],
        evidence: List[str],
    ) -> AIQueryResult:
        if not plan.group_by:
            return AIQueryResult(
                intent=plan.intent,
                matched_count=len(rows),
                total_count=len(catalog.rows),
                evidence=evidence,
                message="缺少分组字段。",
                confidence=plan.confidence,
            )

        counter = Counter()
        for row in rows:
            key_parts = [_group_value(row, group) for group in plan.group_by]
            if not key_parts:
                continue
            counter[tuple(key_parts)] += 1

        total = len(rows)
        groups = []
        for key, count in counter.most_common():
            labels = []
            for group, value in zip(plan.group_by, key):
                labels.append(
                    {
                        "field": group.field,
                        "label": group.label or catalog.label(group.field),
                        "value": value,
                    }
                )
            groups.append(
                {
                    "keys": labels,
                    "count": count,
                    "percent": (count / total) if total else 0,
                }
            )

        return AIQueryResult(
            intent=plan.intent,
            matched_count=total,
            total_count=len(catalog.rows),
            groups=groups,
            evidence=evidence,
            confidence=plan.confidence,
        )

    def _execute_aggregate(
        self,
        plan: AIQueryPlan,
        catalog: AICatalog,
        rows: Sequence[dict],
        evidence: List[str],
    ) -> AIQueryResult:
        if not plan.aggregates:
            return AIQueryResult(
                intent=plan.intent,
                matched_count=len(rows),
                total_count=len(catalog.rows),
                evidence=evidence,
                message="缺少聚合字段。",
                confidence=plan.confidence,
            )
        aggregate = plan.aggregates[0]
        values = [
            (row, _normalise(row.get(aggregate.field, "")))
            for row in rows
            if _normalise(row.get(aggregate.field, ""))
        ]
        if not values:
            return AIQueryResult(
                intent=plan.intent,
                matched_count=0,
                total_count=len(catalog.rows),
                evidence=evidence,
                message=f"字段【{catalog.label(aggregate.field)}】没有可计算数据。",
                confidence=plan.confidence,
            )

        operation = aggregate.operation
        if operation == "average":
            numeric = [(row, raw, number) for row, raw in values for number in [_parse_number(raw)] if number is not None]
            if not numeric:
                return AIQueryResult(intent=plan.intent, total_count=len(catalog.rows), evidence=evidence, message="没有可计算的数值。", confidence=plan.confidence)
            average = sum(item[2] for item in numeric) / len(numeric)
            return AIQueryResult(
                intent=plan.intent,
                matched_count=len(numeric),
                total_count=len(catalog.rows),
                aggregate_value=_format_number(average),
                evidence=evidence + [f"{catalog.label(aggregate.field)} 平均值"],
                confidence=plan.confidence,
            )

        numeric = [(row, raw, number) for row, raw in values for number in [_parse_number(raw)] if number is not None]
        if numeric and operation in {"max", "min"}:
            target = max(item[2] for item in numeric) if operation == "max" else min(item[2] for item in numeric)
            winners = [(row, raw) for row, raw, number in numeric if number == target]
            return _aggregate_result(plan, catalog, aggregate, winners, _format_number(target), len(numeric), evidence)

        if aggregate.field in catalog.date_fields or operation in {"earliest", "latest", "oldest", "youngest"}:
            date_values = [(row, raw, _date_sort_key(raw)) for row, raw in values]
            if operation in {"latest", "youngest", "max"}:
                target_key = max(item[2] for item in date_values)
            else:
                target_key = min(item[2] for item in date_values)
            winners = [(row, raw) for row, raw, key in date_values if key == target_key]
            display_value = winners[0][1] if winners else ""
            return _aggregate_result(plan, catalog, aggregate, winners, display_value, len(date_values), evidence)

        counts = Counter(raw for _, raw in values)
        if operation in {"max", "mode"}:
            target = max(counts.values())
        elif operation == "min":
            target = min(counts.values())
        else:
            return AIQueryResult(intent=plan.intent, total_count=len(catalog.rows), evidence=evidence, message="无法识别聚合方式。", confidence=plan.confidence)
        winners = [value for value, count in counts.items() if count == target]
        return AIQueryResult(
            intent=plan.intent,
            matched_count=len(values),
            total_count=len(catalog.rows),
            aggregate_value=f"{'、'.join(winners)}（{target} 条）",
            evidence=evidence + [f"{catalog.label(aggregate.field)} {operation}"],
            confidence=plan.confidence,
        )

    def _execute_boolean(self, plan: AIQueryPlan, catalog: AICatalog) -> AIQueryResult:
        subject_filters = [item for item in plan.filters if item.field == "name"]
        target_filters = [item for item in plan.filters if item.field != "name"]
        subject_indices = self._apply_filters(subject_filters, catalog)
        if not subject_indices:
            return AIQueryResult(
                intent=plan.intent,
                matched_count=0,
                total_count=len(catalog.rows),
                boolean_value=None,
                evidence=_filter_evidence(plan.filters, catalog),
                message="没有找到要确认的人员。",
                confidence=plan.confidence,
            )

        true_indices = self._apply_filters(target_filters, catalog, base_indices=subject_indices)
        subject_rows = [catalog.rows[index] for index in sorted(subject_indices)]
        display_fields = plan.display_fields or catalog.default_display_fields()
        return AIQueryResult(
            intent=plan.intent,
            matched_count=len(subject_rows),
            total_count=len(catalog.rows),
            boolean_value=bool(true_indices),
            display_rows=[_project_row(row, display_fields) for row in subject_rows[:DISPLAY_ROW_LIMIT]],
            fields=display_fields,
            evidence=_filter_evidence(plan.filters, catalog),
            confidence=plan.confidence,
        )

    def _execute_field_stats(self, plan: AIQueryPlan, catalog: AICatalog) -> AIQueryResult:
        fields = plan.display_fields or catalog.selected_fields[:8]
        groups = []
        total = len(catalog.rows)
        for field in fields:
            values = [_normalise(row.get(field, "")) for row in catalog.rows]
            non_empty = sum(1 for value in values if value)
            groups.append(
                {
                    "keys": [{"field": field, "label": catalog.label(field), "value": "字段统计"}],
                    "count": non_empty,
                    "empty_count": total - non_empty,
                    "unique_count": len(set(value for value in values if value)),
                    "percent": (non_empty / total) if total else 0,
                }
            )
        return AIQueryResult(
            intent=plan.intent,
            matched_count=total,
            total_count=len(catalog.rows),
            groups=groups,
            evidence=[f"统计字段：{'、'.join(catalog.label(field) for field in fields)}"],
            confidence=plan.confidence,
        )

    def _execute_date_range(self, plan: AIQueryPlan, catalog: AICatalog) -> AIQueryResult:
        fields = plan.display_fields or [field for field in catalog.selected_fields if field in catalog.date_fields]
        groups = []
        for field in fields:
            values = [_normalise(row.get(field, "")) for row in catalog.rows]
            values = [value for value in values if value]
            groups.append(
                {
                    "keys": [{"field": field, "label": catalog.label(field), "value": "日期范围"}],
                    "count": len(values),
                    "min": min(values, key=_date_sort_key) if values else "",
                    "max": max(values, key=_date_sort_key) if values else "",
                    "percent": (len(values) / len(catalog.rows)) if catalog.rows else 0,
                }
            )
        return AIQueryResult(
            intent=plan.intent,
            matched_count=len(catalog.rows),
            total_count=len(catalog.rows),
            groups=groups,
            evidence=[f"统计字段：{'、'.join(catalog.label(field) for field in fields)}"] if fields else [],
            confidence=plan.confidence,
        )

    def _execute_subjective_assessment(self, plan: AIQueryPlan, catalog: AICatalog) -> AIQueryResult:
        criteria = [
            item for item in plan.criteria
            if item.get("field") in catalog.selected_fields and item.get("field") not in SENSITIVE_FIELDS
        ]
        if not criteria:
            return AIQueryResult(
                intent=plan.intent,
                total_count=len(catalog.rows),
                message="主观评价需要先确认可执行的评分规则。",
                confidence=plan.confidence,
            )

        display_fields = [
            field for field in (plan.display_fields or catalog.default_display_fields())
            if field not in SENSITIVE_FIELDS
        ]
        excluded_sensitive = [
            catalog.label(field)
            for field in (plan.display_fields or catalog.default_display_fields())
            if field in SENSITIVE_FIELDS
        ]
        scored_rows = []
        for row in catalog.rows:
            score, basis, missing = _score_row(row, criteria, catalog)
            projected = _project_row(row, display_fields)
            projected["__score"] = _format_number(score)
            projected["__score_basis"] = "；".join(basis[:4])
            if missing:
                projected["__missing"] = "、".join(missing[:4])
            scored_rows.append(projected)
        scored_rows.sort(key=lambda item: _parse_number(item.get("__score")) or 0, reverse=True)

        return AIQueryResult(
            intent=plan.intent,
            matched_count=len(scored_rows),
            total_count=len(catalog.rows),
            display_rows=scored_rows[:DISPLAY_ROW_LIMIT],
            fields=display_fields + ["__score", "__score_basis", "__missing"],
            evidence=[_criterion_label(item, catalog) for item in criteria],
            truncated=len(scored_rows) > DISPLAY_ROW_LIMIT,
            sensitive_fields_removed=excluded_sensitive,
            confidence=plan.confidence,
        )

    def _apply_filters(
        self,
        filters: Sequence[AIQueryFilter],
        catalog: AICatalog,
        base_indices: Iterable[int] = None,
    ) -> Set[int]:
        selected = set(base_indices) if base_indices is not None else set(range(len(catalog.rows)))
        for item in filters:
            selected &= self._indices_for_filter(item, catalog, selected)
        return selected

    def _indices_for_filter(self, item: AIQueryFilter, catalog: AICatalog, base_indices: Iterable[int]) -> Set[int]:
        base = set(base_indices)
        if item.field not in catalog.selected_fields:
            return set()
        if item.op == "is_empty":
            return {index for index in base if not _normalise(catalog.rows[index].get(item.field, ""))}
        if item.op == "contains":
            needle = _normalise(item.value)
            return {index for index in base if needle and needle in _normalise(catalog.rows[index].get(item.field, ""))}
        if item.op == "range":
            start, end = _range_bounds(item)
            return {
                index for index in base
                if _value_in_range(_normalise(catalog.rows[index].get(item.field, "")), start, end)
            }
        if item.op == "in":
            indices = set()
            for value in item.values:
                indices |= _indices_for_value(catalog, item.field, value)
            return indices & base
        return _indices_for_value(catalog, item.field, item.value) & base


def _indices_for_value(catalog: AICatalog, field: str, value) -> Set[int]:
    text = _normalise(value)
    indexed = catalog.value_index.get(field, {}).get(text)
    if indexed is not None:
        return set(indexed)
    return {
        index for index, row in enumerate(catalog.rows)
        if _normalise(row.get(field, "")) == text
    }


def _filter_evidence(filters: Sequence[AIQueryFilter], catalog: AICatalog) -> List[str]:
    evidence = []
    for item in filters:
        label = catalog.label(item.field)
        if item.op == "in":
            evidence.append(f"{label} 属于 {'、'.join(str(value) for value in item.values)}")
        elif item.op == "contains":
            evidence.append(f"{label} 包含 {item.value}")
        elif item.op == "range":
            evidence.append(f"{label} 在指定范围内")
        elif item.op == "is_empty":
            evidence.append(f"{label} 为空")
        else:
            evidence.append(f"{label} = {item.value}")
    return evidence


def _aggregate_result(
    plan: AIQueryPlan,
    catalog: AICatalog,
    aggregate: AIAggregate,
    winners: Sequence[Tuple[dict, str]],
    value,
    matched_count: int,
    evidence: List[str],
) -> AIQueryResult:
    display_fields = plan.display_fields or catalog.default_display_fields()
    return AIQueryResult(
        intent=plan.intent,
        matched_count=matched_count,
        total_count=len(catalog.rows),
        aggregate_value=value,
        aggregate_rows=[_project_row(row, display_fields) for row, _ in winners[:DISPLAY_ROW_LIMIT]],
        fields=display_fields,
        evidence=evidence + [f"{catalog.label(aggregate.field)} {aggregate.operation}"],
        confidence=plan.confidence,
    )


def _score_row(row: dict, criteria: Sequence[dict], catalog: AICatalog) -> Tuple[float, List[str], List[str]]:
    weighted = 0.0
    basis = []
    missing = []
    for criterion in criteria:
        field = str(criterion.get("field", ""))
        label = catalog.label(field)
        weight = float(criterion.get("weight", 0) or 0)
        value = _normalise(row.get(field, ""))
        if not value:
            missing.append(label)
            continue
        score = _criterion_score(value, criterion)
        weighted += score * weight / 100
        basis.append(f"{label}={value}")
    return round(weighted, 2), basis, missing


def _criterion_score(value: str, criterion: dict) -> float:
    mapping = criterion.get("mapping")
    if isinstance(mapping, dict):
        for key, score in mapping.items():
            if str(key) in value:
                try:
                    return float(score)
                except (TypeError, ValueError):
                    return 0.0
        return 0.0

    direction = str(criterion.get("direction", ""))
    if direction == "positive_keyword":
        return 100.0 if any(word in value for word in POSITIVE_KEYWORDS) else 50.0
    if direction == "negative_keyword":
        return 100.0 if any(word in value for word in NEGATIVE_KEYWORDS) else 0.0
    if direction == "non_empty":
        return 100.0 if value else 0.0
    if direction == "earlier_is_better":
        year, month, day = _parse_date_parts(value)
        if year is None:
            number = _parse_number(value)
            return max(0.0, min(100.0, 100.0 - number)) if number is not None else 40.0
        ordinal = year * 372 + (month or 1) * 31 + (day or 1)
        # Keep this deterministic without knowing business cutoffs: earlier dates score higher.
        return max(0.0, min(100.0, 100.0 - ((ordinal - 1970 * 372) / 372)))
    return 50.0


def _criterion_label(criterion: dict, catalog: AICatalog) -> str:
    field = str(criterion.get("field", ""))
    weight = criterion.get("weight", "")
    direction = criterion.get("direction") or ("映射评分" if criterion.get("mapping") else "评分")
    return f"{catalog.label(field)}（权重 {weight}，{direction}）"


def _project_row(row: dict, fields: Sequence[str]) -> dict:
    return {field: row.get(field, "") for field in fields if field in row}


def _group_value(row: dict, group: AIGroupBy) -> str:
    raw = _normalise(row.get(group.field, ""))
    if not raw:
        return "未填写"
    if group.date_part:
        year, month, day = _parse_date_parts(raw)
        if group.date_part == "year":
            return f"{year}年" if year else "未识别日期"
        if group.date_part == "month":
            return f"{month:02d}月" if month else "未识别日期"
        if group.date_part == "year_month":
            return f"{year}.{month:02d}" if year and month else "未识别日期"
        if group.date_part == "day":
            return f"{day:02d}日" if day else "未识别日期"
    return raw


def _range_bounds(item: AIQueryFilter):
    if isinstance(item.value, dict):
        return item.value.get("start"), item.value.get("end")
    if item.values:
        start = item.values[0] if len(item.values) > 0 else None
        end = item.values[1] if len(item.values) > 1 else None
        return start, end
    return None, None


def _value_in_range(value: str, start, end) -> bool:
    if not value:
        return False
    number = _parse_number(value)
    start_number = _parse_number(start) if start is not None else None
    end_number = _parse_number(end) if end is not None else None
    if number is not None and (start_number is not None or end_number is not None):
        if start_number is not None and number < start_number:
            return False
        if end_number is not None and number > end_number:
            return False
        return True

    key = _date_sort_key(value)
    if start is not None and key < _date_sort_key(str(start)):
        return False
    if end is not None and key > _date_sort_key(str(end)):
        return False
    return True


def _parse_date_parts(value: str):
    match = re.search(r"(\d{4})(?:[.\-/年](\d{1,2}))?(?:[.\-/月](\d{1,2}))?", str(value))
    if not match:
        return None, None, None
    return int(match.group(1)), int(match.group(2) or 1), int(match.group(3) or 1)


def _date_sort_key(value: str):
    year, month, day = _parse_date_parts(value)
    if year is None:
        return (9999, 99, 99, str(value))
    return (year, month or 1, day or 1, str(value))


def _parse_number(value) -> float:
    if value is None:
        return None
    text = str(value).replace(",", "").strip()
    multiplier = 10000 if "万" in text else 1
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0)) * multiplier
    except ValueError:
        return None


def _format_number(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _normalise(value) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip())
