"""In-memory semantic retrieval for AI-assisted personnel analysis."""

import logging
import math
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import requests

from services.ollama_manager import EMBEDDING_MODEL_NAME, ollama_api_url


logger = logging.getLogger("AIRetrieval")

MAX_VALUE_EMBEDDING_ITEMS = 300
MAX_ROW_EMBEDDING_ITEMS = 120

SYNONYM_GROUPS = [
    {"研发部", "开发部", "技术部", "研发部门", "开发部门", "技术开发部"},
    {"资深", "资深员工", "老员工", "老同志", "老资格", "工龄长", "工作年限长", "参加工作早"},
    {"检察官助理", "助理", "检助"},
    {"办公室", "综合办公室", "行政办公室"},
    {"政治部", "政工部", "干部部"},
    {"本科", "学士", "大学本科"},
    {"硕士", "研究生", "硕士研究生"},
    {"博士", "博士研究生"},
]


@dataclass
class RetrievalMatch:
    field_name: str
    field_label: str
    value: str
    score: float
    match_type: str
    row_indices: List[int]
    matched_text: str

    @property
    def row_count(self) -> int:
        return len(self.row_indices)


@dataclass
class RowMatch:
    row_index: int
    score: float
    match_type: str
    text: str


@dataclass
class RetrievalResult:
    field_matches: List[RetrievalMatch]
    row_matches: List[RowMatch]
    embedding_used: bool = False
    degraded: bool = False
    message: str = ""


class OllamaEmbeddingClient:
    def __init__(self, model_name: str = EMBEDDING_MODEL_NAME, timeout: float = 8.0):
        self.model_name = model_name
        self.timeout = timeout

    def embed_texts(self, texts: Sequence[str]) -> Optional[List[List[float]]]:
        clean_texts = [text for text in texts if text]
        if not clean_texts:
            return []

        try:
            response = requests.post(
                ollama_api_url("/api/embed"),
                json={"model": self.model_name, "input": clean_texts},
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
            embeddings = data.get("embeddings")
            if isinstance(embeddings, list) and len(embeddings) == len(clean_texts):
                return embeddings
        except Exception as e:
            logger.debug("Ollama embedding 调用失败，降级到轻量匹配: %s", e)
        return None


class LocalRetrievalIndex:
    """Build a per-dialog in-memory index from already-authorized rows."""

    def __init__(
        self,
        rows: Sequence[dict],
        selected_fields: Sequence[str],
        field_labels: Dict[str, str],
        embedding_client: Optional[OllamaEmbeddingClient] = None,
    ):
        self.rows = list(rows or [])
        self.selected_fields = [field for field in selected_fields if field]
        self.field_labels = dict(field_labels or {})
        self.embedding_client = embedding_client or OllamaEmbeddingClient()
        self.value_entries = self._build_value_entries()
        self.row_entries = self._build_row_entries()
        self.row_text_by_index = {entry["row_index"]: entry["text"] for entry in self.row_entries}
        self._value_embeddings: Optional[List[List[float]]] = None
        self._row_embeddings: Optional[List[List[float]]] = None
        self._embedding_failed = False

    def search(self, question: str, top_k: int = 5, row_limit: int = 10) -> RetrievalResult:
        question = _normalise(question)
        if not question or not self.rows:
            return RetrievalResult([], [], message="无可检索数据")

        value_matches = self._lexical_value_matches(question)
        row_matches = self._lexical_row_matches(question)
        embedding_used = False
        degraded = False
        message = ""

        if len(value_matches) < top_k and not self._embedding_failed:
            embedded_values = self._embedding_value_matches(question)
            if embedded_values is None:
                degraded = True
                message = f"embedding 模型 {EMBEDDING_MODEL_NAME} 不可用，已使用轻量匹配"
            else:
                embedding_used = True
                value_matches = _merge_value_matches(value_matches + embedded_values)

        if len(row_matches) < row_limit and not self._embedding_failed:
            embedded_rows = self._embedding_row_matches(question)
            if embedded_rows is not None:
                embedding_used = True
                row_matches = _merge_row_matches(row_matches + embedded_rows)

        value_matches = _merge_value_matches(value_matches)[:top_k]
        matched_row_indices = []
        for match in value_matches:
            matched_row_indices.extend(match.row_indices)
        row_matches.extend(self._rows_from_indices(matched_row_indices, source="字段取值匹配"))
        row_matches = _merge_row_matches(row_matches)[:row_limit]

        return RetrievalResult(
            field_matches=value_matches,
            row_matches=row_matches,
            embedding_used=embedding_used,
            degraded=degraded or self._embedding_failed,
            message=message,
        )

    def rows_for_matches(self, matches: Iterable[RetrievalMatch], limit: int = 10) -> List[dict]:
        indices = []
        for match in matches:
            indices.extend(match.row_indices)
        unique_indices = []
        seen = set()
        for index in indices:
            if index not in seen:
                seen.add(index)
                unique_indices.append(index)
        return [self.rows[index] for index in unique_indices[:limit] if 0 <= index < len(self.rows)]

    def _build_value_entries(self) -> List[dict]:
        grouped: Dict[Tuple[str, str], List[int]] = {}
        for row_index, row in enumerate(self.rows):
            for field in self.selected_fields:
                value = _normalise(row.get(field, ""))
                if value and _value_can_match(field, value):
                    grouped.setdefault((field, value), []).append(row_index)

        entries = []
        for (field, value), row_indices in grouped.items():
            label = self.field_labels.get(field, field)
            search_terms = [label, field, value] + related_terms(value) + related_terms(label)
            entries.append(
                {
                    "field_name": field,
                    "field_label": label,
                    "value": value,
                    "row_indices": row_indices,
                    "text": " ".join(dict.fromkeys(term for term in search_terms if term)),
                }
            )
        return entries

    def _build_row_entries(self) -> List[dict]:
        entries = []
        display_fields = _display_fields(self.rows, self.selected_fields)
        for row_index, row in enumerate(self.rows):
            parts = []
            for field in display_fields:
                value = _normalise(row.get(field, ""))
                if value:
                    parts.append(f"{self.field_labels.get(field, field)}={value}")
            if parts:
                entries.append({"row_index": row_index, "text": "；".join(parts)})
        return entries

    def _lexical_value_matches(self, question: str) -> List[RetrievalMatch]:
        matches = []
        for entry in self.value_entries:
            score, match_type, matched_text = _lexical_score(question, entry["text"], entry["value"])
            if score >= 0.45:
                matches.append(
                    RetrievalMatch(
                        field_name=entry["field_name"],
                        field_label=entry["field_label"],
                        value=entry["value"],
                        score=score,
                        match_type=match_type,
                        row_indices=list(entry["row_indices"]),
                        matched_text=matched_text,
                    )
                )
        return matches

    def _lexical_row_matches(self, question: str) -> List[RowMatch]:
        matches = []
        for entry in self.row_entries:
            score = SequenceMatcher(None, question, entry["text"]).ratio()
            if question in entry["text"]:
                score = max(score, 0.9)
            if score >= 0.5:
                matches.append(RowMatch(entry["row_index"], score, "行摘要匹配", entry["text"]))
        return sorted(matches, key=lambda item: item.score, reverse=True)

    def _embedding_value_matches(self, question: str) -> Optional[List[RetrievalMatch]]:
        entries = self.value_entries[:MAX_VALUE_EMBEDDING_ITEMS]
        if not entries:
            return []
        embeddings = self._get_value_embeddings(entries)
        if embeddings is None:
            self._embedding_failed = True
            return None
        question_embedding = self._embed_question(question)
        if question_embedding is None:
            self._embedding_failed = True
            return None

        matches = []
        for entry, embedding in zip(entries, embeddings):
            score = cosine_similarity(question_embedding, embedding)
            if score >= 0.62:
                matches.append(
                    RetrievalMatch(
                        field_name=entry["field_name"],
                        field_label=entry["field_label"],
                        value=entry["value"],
                        score=score,
                        match_type="语义向量匹配",
                        row_indices=list(entry["row_indices"]),
                        matched_text=entry["text"],
                    )
                )
        return sorted(matches, key=lambda item: item.score, reverse=True)

    def _embedding_row_matches(self, question: str) -> Optional[List[RowMatch]]:
        entries = self.row_entries[:MAX_ROW_EMBEDDING_ITEMS]
        if not entries:
            return []
        embeddings = self._get_row_embeddings(entries)
        if embeddings is None:
            return None
        question_embedding = self._embed_question(question)
        if question_embedding is None:
            return None

        matches = []
        for entry, embedding in zip(entries, embeddings):
            score = cosine_similarity(question_embedding, embedding)
            if score >= 0.58:
                matches.append(RowMatch(entry["row_index"], score, "行摘要语义匹配", entry["text"]))
        return sorted(matches, key=lambda item: item.score, reverse=True)

    def _get_value_embeddings(self, entries: Sequence[dict]) -> Optional[List[List[float]]]:
        if self._value_embeddings is None:
            self._value_embeddings = self.embedding_client.embed_texts([entry["text"] for entry in entries])
        return self._value_embeddings

    def _get_row_embeddings(self, entries: Sequence[dict]) -> Optional[List[List[float]]]:
        if self._row_embeddings is None:
            self._row_embeddings = self.embedding_client.embed_texts([entry["text"] for entry in entries])
        return self._row_embeddings

    def _embed_question(self, question: str) -> Optional[List[float]]:
        embeddings = self.embedding_client.embed_texts([question])
        if not embeddings:
            return None
        return embeddings[0]

    def _rows_from_indices(self, indices: Iterable[int], source: str) -> List[RowMatch]:
        matches = []
        for index in indices:
            if 0 <= index < len(self.rows):
                text = self.row_text_by_index.get(index, "")
                matches.append(RowMatch(index, 0.88, source, text))
        return matches


def related_terms(text: str) -> List[str]:
    text = _normalise(text)
    if not text:
        return []
    terms = []
    for group in SYNONYM_GROUPS:
        if any(term and (term in text or text in term) for term in group):
            terms.extend(sorted(group))
    return [term for term in dict.fromkeys(terms) if term != text]


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if not left_norm or not right_norm:
        return 0.0
    return dot / (left_norm * right_norm)


def _lexical_score(question: str, text: str, value: str) -> Tuple[float, str, str]:
    if value and value in question:
        return 1.0, "精确取值匹配", value

    for term in related_terms(value) + related_terms(text):
        if term and term in question:
            return 0.86, "同义词匹配", term

    text_parts = [part for part in re.split(r"[\s=；、,，/]+", text) if part]
    for part in text_parts:
        if len(part) >= 2 and part in question:
            return 0.78, "字段文本匹配", part

    ratio = max(SequenceMatcher(None, question, text).ratio(), SequenceMatcher(None, question, value).ratio())
    if ratio >= 0.52:
        return ratio, "模糊匹配", value
    return 0.0, "", ""


def _merge_value_matches(matches: Sequence[RetrievalMatch]) -> List[RetrievalMatch]:
    best: Dict[Tuple[str, str], RetrievalMatch] = {}
    for match in matches:
        key = (match.field_name, match.value)
        if key not in best or match.score > best[key].score:
            best[key] = match
    return sorted(best.values(), key=lambda item: item.score, reverse=True)


def _merge_row_matches(matches: Sequence[RowMatch]) -> List[RowMatch]:
    best: Dict[int, RowMatch] = {}
    for match in matches:
        if match.row_index not in best or match.score > best[match.row_index].score:
            best[match.row_index] = match
    return sorted(best.values(), key=lambda item: item.score, reverse=True)


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
    return fields


def _value_can_match(field: str, value: str) -> bool:
    if field in {"id", "sequence"}:
        return False
    if field in {"gender", "relation"}:
        return len(value) >= 1
    return len(value) >= 2


def _normalise(value) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return re.sub(r"\s+", " ", text)
