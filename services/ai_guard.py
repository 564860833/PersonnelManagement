"""Post-execution validation, truncation, and safety boundaries."""

import copy
from typing import List

from services.ai_catalog import AICatalog
from services.ai_resolver import SENSITIVE_FIELDS
from services.ai_types import AIQueryPlan, AIQueryResult


DISPLAY_ROW_LIMIT = 20


def validate_result(result: AIQueryResult, plan: AIQueryPlan, catalog: AICatalog) -> AIQueryResult:
    guarded = copy.deepcopy(result)
    guarded.scope = guarded.scope or f"当前【{catalog.table_label}】查询结果，共 {len(catalog.rows)} 条"
    guarded.confidence = min(float(guarded.confidence or 1.0), float(plan.confidence or 1.0))

    if guarded.matched_count == 0 and plan.intent not in {"count_total", "field_stats", "date_range"}:
        guarded.warnings.append("没有匹配到符合条件的记录。")

    if guarded.confidence < 0.65:
        guarded.warnings.append("匹配置信度较低，结果仅供参考。")

    if len(guarded.display_rows) > DISPLAY_ROW_LIMIT:
        guarded.display_rows = guarded.display_rows[:DISPLAY_ROW_LIMIT]
        guarded.truncated = True
        guarded.warnings.append(f"匹配记录较多，以下仅展示前 {DISPLAY_ROW_LIMIT} 条，完整名单请通过界面筛选查看。")
    elif guarded.matched_count > len(guarded.display_rows) >= DISPLAY_ROW_LIMIT:
        guarded.truncated = True
        guarded.warnings.append(f"匹配记录较多，以下仅展示前 {len(guarded.display_rows)} 条，完整名单请通过界面筛选查看。")

    if plan.intent == "subjective_assessment":
        _remove_sensitive_subjective_fields(guarded, catalog)

    guarded.warnings = list(dict.fromkeys(item for item in guarded.warnings if item))
    guarded.sensitive_fields_removed = list(dict.fromkeys(guarded.sensitive_fields_removed))
    return guarded


def _remove_sensitive_subjective_fields(result: AIQueryResult, catalog: AICatalog) -> None:
    sensitive = {field for field in result.fields if field in SENSITIVE_FIELDS}
    if not sensitive:
        return
    result.fields = [field for field in result.fields if field not in sensitive]
    for row in result.display_rows:
        for field in sensitive:
            row.pop(field, None)
    result.sensitive_fields_removed.extend(catalog.label(field) for field in sorted(sensitive))
