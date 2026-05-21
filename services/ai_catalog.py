"""Catalog of fields, aliases, values, and row scope for AI planning."""

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence

from metadata.constants import COLUMN_LABEL_ALIASES, TABLE_DATE_FIELDS, get_table_label
from metadata.query_options import EDUCATION_KEYWORDS, POSITION_GROUPS, POSITION_MAPPING
from services.ai_retrieval import related_terms


@dataclass
class AIValueCandidate:
    field: str
    label: str
    value: str
    row_indices: List[int]
    score: float
    reason: str


@dataclass
class AIFieldCandidate:
    field: str
    label: str
    score: float
    reason: str


class AICatalog:
    """Authoritative data scope available to the AI assistant."""

    def __init__(
        self,
        table_name: str,
        rows: Sequence[dict],
        selected_fields: Sequence[str],
        field_labels: Dict[str, str],
        table_label: Optional[str] = None,
    ):
        self.table_name = table_name
        self.table_label = table_label or get_table_label(table_name)
        self.rows = list(rows or [])
        self.field_labels = dict(field_labels or {})
        self.selected_fields = self._existing_fields(selected_fields)
        self.date_fields = set(TABLE_DATE_FIELDS.get(table_name, [])) & set(self.selected_fields)
        self.field_aliases = self._build_field_aliases()
        self.value_index = self._build_value_index()
        self.signature = self._build_signature()

    @classmethod
    def from_payload(cls, payload: dict) -> "AICatalog":
        return cls(
            table_name=payload.get("table_name", ""),
            table_label=payload.get("table_label"),
            rows=payload.get("rows") or [],
            selected_fields=payload.get("selected_fields") or [],
            field_labels=payload.get("field_labels") or {},
        )

    def label(self, field: str) -> str:
        return self.field_labels.get(field, field)

    def is_available_field(self, field: str) -> bool:
        return field in self.selected_fields

    def fields_mentioned(self, text: str, include_date_part: bool = False) -> List[AIFieldCandidate]:
        q = _normalise(text)
        matches: List[AIFieldCandidate] = []
        for field in self.selected_fields:
            best_score = 0.0
            best_reason = ""
            for alias in self.field_aliases.get(field, []):
                if not alias:
                    continue
                if alias == q:
                    score = 1.0
                elif alias in q:
                    score = 0.86
                else:
                    score = 0.0
                if score > best_score:
                    best_score = score
                    best_reason = f"字段别名：{alias}"
            if best_score:
                matches.append(AIFieldCandidate(field, self.label(field), best_score, best_reason))

        if include_date_part and any(word in q for word in ("月份", "年月", "日期", "时间", "年份", "年度")):
            date_field = self.first_date_field(q)
            if date_field and not any(item.field == date_field for item in matches):
                matches.append(AIFieldCandidate(date_field, self.label(date_field), 0.72, "日期粒度提示"))

        return sorted(matches, key=lambda item: item.score, reverse=True)

    def first_date_field(self, text: str = "") -> str:
        mentioned = [item.field for item in self.fields_mentioned(text) if item.field in self.date_fields]
        if mentioned:
            return mentioned[0]
        for preferred in (
            "reward_date",
            "punishment_date",
            "birth_date",
            "work_start_date",
            "entry_date",
            "current_position_date",
            "current_grade_date",
        ):
            if preferred in self.date_fields:
                return preferred
        return next(iter(self.date_fields), "")

    def match_values(
        self,
        text: str,
        allowed_fields: Optional[Iterable[str]] = None,
        excluded_fields: Optional[Iterable[str]] = None,
        limit: int = 8,
    ) -> List[AIValueCandidate]:
        q = _normalise(text)
        if not q:
            return []

        allowed = set(allowed_fields) if allowed_fields else set(self.selected_fields)
        excluded = set(excluded_fields or set())
        candidates: List[AIValueCandidate] = []
        for field, values in self.value_index.items():
            if field not in allowed or field in excluded:
                continue
            for value, row_indices in values.items():
                score, reason = _value_score(q, value, self.field_aliases.get(field, []))
                if score:
                    candidates.append(
                        AIValueCandidate(
                            field=field,
                            label=self.label(field),
                            value=value,
                            row_indices=list(row_indices),
                            score=score,
                            reason=reason,
                        )
                    )

        candidates.sort(key=lambda item: (item.score, len(item.row_indices), len(item.value)), reverse=True)
        return _dedupe_candidates(candidates)[:limit]

    def values_for_field(self, field: str) -> List[str]:
        return list(self.value_index.get(field, {}).keys())

    def default_display_fields(self) -> List[str]:
        fields = []
        for field in ("sequence", "name"):
            if field in self.selected_fields:
                fields.append(field)
        for field in self.selected_fields:
            if field not in fields:
                fields.append(field)
        return fields[:8]

    def _existing_fields(self, selected_fields: Sequence[str]) -> List[str]:
        selected = [field for field in selected_fields if field]
        if not self.rows:
            return selected
        available = set()
        for row in self.rows[:30]:
            available.update(row.keys())
        return [field for field in selected if field in available]

    def _build_field_aliases(self) -> Dict[str, List[str]]:
        aliases: Dict[str, List[str]] = {}
        for field in self.selected_fields:
            label = self.label(field)
            terms = [field, label]
            terms.extend(part for part in re.split(r"[/、\s]+", label) if part)
            for alias, alias_field in COLUMN_LABEL_ALIASES.items():
                if alias_field == field:
                    terms.append(alias)

            lower = field.lower()
            if "department" in lower or "部门" in label or "科室" in label:
                terms.extend(["部门", "科室", "单位", "处室"])
            if "position" in lower or "职务" in label or "岗位" in label or "职位" in label:
                terms.extend(["岗位", "职位", "职务", "职务层次"])
            if "education" in lower or "学历" in label or "学位" in label:
                terms.extend(["学历", "学位", "学历学位", "文化程度"])
            if "grade" in lower or "职级" in label or "等级" in label:
                terms.extend(["职级", "等级", "级别"])
            if "salary" in lower or "工资" in label or "薪资" in label:
                terms.extend(["工资", "薪资", "收入", "薪酬"])
            if "name" == lower or label == "姓名":
                terms.extend(["姓名", "名字", "人员"])
            if field in self.date_fields or "日期" in label or "时间" in label or "年月" in label:
                terms.extend(["日期", "时间", "年月", "月份", "年份"])
            if "seniority" in lower or "资历" in label:
                terms.extend(["资历", "老员工", "资深"])
            aliases[field] = list(dict.fromkeys(_normalise(term) for term in terms if _normalise(term)))
        return aliases

    def _build_value_index(self) -> Dict[str, Dict[str, List[int]]]:
        value_index: Dict[str, Dict[str, List[int]]] = {}
        for row_index, row in enumerate(self.rows):
            for field in self.selected_fields:
                value = _normalise(row.get(field, ""))
                if not _value_can_match(field, value):
                    continue
                value_index.setdefault(field, {}).setdefault(value, []).append(row_index)

        self._add_business_concepts(value_index)
        return value_index

    def _add_business_concepts(self, value_index: Dict[str, Dict[str, List[int]]]) -> None:
        for field in self.selected_fields:
            label = self.label(field)
            lower = field.lower()
            values = value_index.get(field, {})

            if "education" in lower or "学历" in label or "学位" in label:
                for concept, keywords in EDUCATION_KEYWORDS.items():
                    indices = [
                        index
                        for value, row_indices in values.items()
                        if any(keyword in value for keyword in keywords)
                        for index in row_indices
                    ]
                    if indices:
                        values.setdefault(concept, sorted(set(indices)))

            if "position" in lower or "职务" in label or "岗位" in label:
                for concept, positions in POSITION_MAPPING.items():
                    indices = [
                        index
                        for value, row_indices in values.items()
                        if any(position in value for position in positions)
                        for index in row_indices
                    ]
                    if indices:
                        values.setdefault(concept, sorted(set(indices)))
                for concept, groups in POSITION_GROUPS.items():
                    indices = [
                        index
                        for group in groups
                        for index in values.get(group, [])
                    ]
                    if indices:
                        values.setdefault(concept, sorted(set(indices)))

    def _build_signature(self) -> str:
        sampled_rows = []
        if self.rows:
            sample = self.rows[:10] + self.rows[-10:]
            for row in sample:
                sampled_rows.append({field: _normalise(row.get(field, "")) for field in self.selected_fields})
        payload = {
            "table": self.table_name,
            "fields": self.selected_fields,
            "count": len(self.rows),
            "sample": sampled_rows,
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


def _dedupe_candidates(candidates: Sequence[AIValueCandidate]) -> List[AIValueCandidate]:
    best: Dict[tuple, AIValueCandidate] = {}
    for item in candidates:
        key = (item.field, item.value)
        if key not in best or item.score > best[key].score:
            best[key] = item
    return list(best.values())


def _value_score(question: str, value: str, field_aliases: Sequence[str]) -> tuple:
    if not value:
        return 0.0, ""
    if value == question:
        return 1.0, "取值完全匹配"
    if value in question:
        return 0.96, "取值出现在问题中"
    if len(value) >= 2 and question in value:
        return 0.82, "问题文本包含在取值中"

    for term in _question_value_terms(question, field_aliases):
        if len(term) >= 2 and (term in value or value in term):
            return 0.84, f"问题关键词匹配取值：{term}"

    for term in related_terms(value):
        if term and term in question:
            return 0.88, f"同义词匹配：{term}"

    for alias in field_aliases:
        if alias and alias in question and value in question:
            return 0.9, f"字段 {alias} 的取值匹配"
    return 0.0, ""


def _value_can_match(field: str, value: str) -> bool:
    if not value or field == "id":
        return False
    if field == "sequence":
        return False
    if field in {"gender", "relation"}:
        return len(value) >= 1
    return len(value) >= 2


def _question_value_terms(question: str, field_aliases: Sequence[str]) -> List[str]:
    text = _normalise(question)
    removable_words = sorted(
        set(
            field_aliases
            + [
                "表里",
                "表中",
                "当前",
                "现在",
                "查询结果",
                "记录",
                "条记录",
                "人员",
                "人",
                "条",
                "个",
                "几个",
                "几个人",
                "多少",
                "多少人",
                "几人",
                "几名",
                "人数",
                "总人数",
                "总数",
                "共有",
                "有多少",
                "有",
                "叫",
                "名叫",
                "姓名",
                "的",
                "吗",
                "呢",
                "是",
                "为",
                "？",
                "?",
                "，",
                ",",
                "。",
            ]
        ),
        key=len,
        reverse=True,
    )
    for word in removable_words:
        if word:
            text = text.replace(word, " ")
    return [part for part in re.split(r"[\s,，。；;:：?？!！]+", text) if len(part) >= 2]


def _normalise(value) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip())
