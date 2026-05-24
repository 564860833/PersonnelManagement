import html
import json
import logging
import math
import threading
from pathlib import Path

import markdown
from PyQt5.QtCore import QPoint, QRect, QSize, QObject, QTimer, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QPainter
from PyQt5.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from services.ai_context import recommend_context_length
from services.ai_direct import ask_model, is_context_length_error
from services.ollama_manager import APP_OLLAMA_HOST, fetch_ollama_models
from ui.styles import DIALOG_BASE_STYLE, DIALOG_BUTTON_STYLE

logger = logging.getLogger("AIChat")

IDENTITY_FIELDS = ("sequence", "name")
LONG_TEXT_FIELDS = {"resume_text"}
CORE_FIELDS = {
    "base_info": {
        "sequence",
        "name",
        "current_position",
        "current_grade",
        "birth_date",
        "fulltime_education",
        "parttime_education",
        "rewards",
        "remarks",
    },
    "rewards": {
        "sequence",
        "name",
        "reward_name",
        "reward_date",
        "punishment_name",
        "punishment_date",
        "impact_period",
    },
    "family": {
        "sequence",
        "name",
        "relation",
        "family_name",
        "work_unit",
        "position",
    },
    "resume": {
        "sequence",
        "name",
    },
}
FIELD_GROUPS = {
    "base_info": (
        (
            "基础身份信息",
            (
                "sequence",
                "name",
                "gender",
                "birth_date",
                "ethnicity",
                "hometown",
                "work_start_date",
                "party_date",
                "remarks",
            ),
        ),
        (
            "行政职务履历",
            (
                "current_position",
                "current_position_date",
                "current_grade",
                "current_grade_date",
                "next_promotion",
                "previous_position1",
                "previous_position1_date",
                "previous_position2",
                "previous_position2_date",
            ),
        ),
        (
            "检察/法律职务",
            (
                "entry_date",
                "admission_date",
                "current_legal_position",
                "current_legal_position_date",
                "previous_legal_position",
                "previous_legal_position_date",
            ),
        ),
        (
            "学历与考核奖惩",
            (
                "fulltime_education",
                "fulltime_school",
                "parttime_education",
                "parttime_school",
                "rewards",
                "assessment_*",
            ),
        ),
    ),
    "rewards": (
        ("基础身份信息", ("sequence", "name")),
        ("奖励信息", ("reward_name", "reward_date", "reward_unit", "reward_authority_type")),
        (
            "惩戒信息",
            (
                "punishment_name",
                "punishment_date",
                "punishment_unit",
                "punishment_authority_type",
                "impact_period",
            ),
        ),
    ),
    "family": (
        ("基础身份信息", ("sequence", "name")),
        ("家庭成员关系", ("relation", "family_name", "birth_date", "political_status")),
        ("任职工作信息", ("work_unit", "position")),
    ),
    "resume": (
        ("基础身份信息", ("sequence", "name")),
        ("简历内容", ("resume_text",)),
    ),
}
OTHER_FIELD_GROUP_LABEL = "其他字段"

AI_CORE_FIELDS_CONFIG_FILE = Path("ai_core_fields.json")
MODEL_PLACEHOLDER = "未检测到可用模型"
NAV_SIDEBAR_WIDTH = 360
NAV_SIDEBAR_MIN_WIDTH = 360
TABLE_NAV_BUTTON_MIN_WIDTH = 284
CONTEXT_PRESSURE_REFRESH_DELAY_MS = 200
CONTEXT_BUFFER_RATIO = 0.25
CJK_TOKEN_WEIGHT = 1.8
ASCII_TOKEN_WEIGHT = 0.3
WHITESPACE_TOKEN_WEIGHT = 0.05
MANUAL_CONTEXT_OPTIONS = (2048, 4096, 8192, 16384, 32768)
AI_CHAT_WINDOW_WIDTH_RATIO = 0.68
AI_CHAT_WINDOW_HEIGHT_RATIO = 0.70

AI_CHAT_STYLE = """
QSplitter::handle {
    background-color: #E5EAF0;
}
QSplitter::handle:hover {
    background-color: #8BB6E8;
}
QFrame#aiSidebarPanel,
QFrame#aiHeaderPanel,
QFrame#aiColumnPanel,
QFrame#aiInputPanel,
QFrame#aiSidebarSection,
QFrame#aiFieldPageHeader,
QFrame#aiFieldPageFooter {
    background-color: #FFFFFF;
    border: 1px solid #E5EAF0;
    border-radius: 8px;
}
QFrame#aiSidebarPanel {
    padding: 0;
}
QFrame#aiSidebarHeader,
QFrame#aiSidebarFooter {
    background-color: transparent;
}
QWidget#aiNavBody,
QWidget#aiFieldScrollContent {
    background-color: transparent;
}
QLabel#aiDialogTitle {
    color: #174A8B;
    font-size: 20px;
    font-weight: bold;
}
QLabel#aiSidebarSubtitle,
QLabel#aiSectionTitle,
QLabel#aiWorkspaceTitle,
QLabel#aiFieldPageTitle {
    color: #174A8B;
    font-weight: bold;
}
QLabel#aiSidebarTitle {
    color: #174A8B;
    font-size: 17px;
    font-weight: bold;
}
QLabel#aiSidebarSubtitle {
    color: #57606A;
    font-size: 12px;
}
QLabel#aiSectionMeta {
    color: #57606A;
}
QLabel#aiContextLabel,
QLabel#aiColumnSummary,
QLabel#aiFooterStatus {
    color: #57606A;
}
QComboBox#aiContextCombo {
    min-width: 96px;
}
QLabel#aiTableTitle {
    color: #174A8B;
    font-weight: bold;
}
QPushButton#aiNavButton {
    text-align: left;
    padding: 10px 12px;
    border: 1px solid #E5EAF0;
    border-radius: 8px;
    background-color: #FBFDFF;
    color: #24292F;
    font-weight: bold;
}
QPushButton#aiNavButton:hover {
    background-color: #F7FBFF;
    border-color: #CFE1F4;
}
QPushButton#aiNavButton:checked {
    color: #174A8B;
    background-color: #EAF2FB;
    border-color: #8BB6E8;
}
QPushButton#aiNavButton:disabled {
    color: #8C959F;
    background-color: #F6F8FA;
    border-color: #EAEEF2;
}
QFrame#aiTableNavItem {
    background-color: transparent;
    border: none;
}
QLabel#aiNavSummary,
QLabel#aiColumnSummary,
QLabel#aiFieldPageMeta,
QLabel#aiFieldPageBadge,
QLabel#aiPressureValue,
QLabel#aiPressureHint {
    color: #57606A;
}
QLabel#aiFieldPageBadge,
QLabel#aiNavSummary,
QLabel#aiColumnSummary {
    padding: 3px 9px;
    border-radius: 999px;
    background-color: #EAF2FB;
    border: 1px solid #8BB6E8;
    color: #174A8B;
    font-weight: bold;
}
QScrollArea#aiColumnScroll {
    border: none;
    background-color: transparent;
}
QWidget#aiColumnContent {
    background-color: transparent;
}
QFrame#aiFieldScrollWrap {
    background-color: transparent;
}
QFrame#aiFieldGroupBlock {
    background-color: #FFFFFF;
    border: 1px solid #E5EAF0;
    border-radius: 8px;
}
QFrame#aiFieldGroupHeader {
    background-color: #F7FBFF;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
}
QLabel#aiFieldGroupTitle {
    color: #174A8B;
    font-weight: bold;
}
QLabel#aiFieldGroupBadge {
    padding: 3px 8px;
    border-radius: 999px;
    background-color: #FFFFFF;
    border: 1px solid #8BB6E8;
    color: #174A8B;
    font-weight: bold;
}
QLabel#aiPressureValue {
    color: #174A8B;
    font-weight: bold;
}
QLabel#aiPressureHint {
    font-size: 12px;
}
QPushButton#aiFieldTag {
    text-align: left;
    padding: 8px 12px;
    border-radius: 999px;
    border: 1px solid #D0D7DE;
    background-color: #FFFFFF;
    color: #24292F;
}
QPushButton#aiFieldTag:hover {
    border-color: #8BB6E8;
    background-color: #F7FBFF;
}
QPushButton#aiFieldTag:checked {
    border-color: #174A8B;
    background-color: #EAF2FB;
    color: #174A8B;
    font-weight: bold;
}
QPushButton#aiFieldTag:disabled {
    border-color: #D0D7DE;
    background-color: #F6F8FA;
    color: #57606A;
}
QFrame#aiCoreButtonGroup {
    background-color: transparent;
    border: none;
}
QPushButton#aiCoreSegmentLeft {
    min-height: 32px;
    max-height: 32px;
    padding: 4px 14px;
    border: 1px solid #C9D1D9;
    border-top-left-radius: 5px;
    border-bottom-left-radius: 5px;
    border-top-right-radius: 0;
    border-bottom-right-radius: 0;
    background-color: #FFFFFF;
    color: #24292F;
}
QPushButton#aiCoreSegmentLeft:hover {
    background-color: #EAF2FB;
    border-color: #8BB6E8;
    color: #174A8B;
}
QPushButton#aiCoreSegmentLeft:disabled {
    background-color: #F6F8FA;
    border-color: #EAEEF2;
    color: #8C959F;
}
QToolButton#aiCoreSegmentRight {
    min-height: 32px;
    max-height: 32px;
    padding: 4px 12px;
    border: 1px solid #C9D1D9;
    border-left: none;
    border-top-left-radius: 0;
    border-bottom-left-radius: 0;
    border-top-right-radius: 5px;
    border-bottom-right-radius: 5px;
    background-color: #FFFFFF;
    color: #174A8B;
    font-weight: bold;
}
QToolButton#aiCoreSegmentRight:hover {
    background-color: #EAF2FB;
    border-color: #8BB6E8;
    border-left: none;
}
QToolButton#aiCoreSegmentRight:disabled {
    color: #8C959F;
    background-color: #F6F8FA;
    border-color: #EAEEF2;
    border-left: none;
}
QFrame#aiCoreFilterPanel {
    background-color: #FFFFFF;
    border: none;
    border-radius: 8px;
}
QLabel#aiCoreFilterTitle {
    color: #174A8B;
    font-size: 16px;
    font-weight: bold;
}
QLabel#aiCoreFilterMeta {
    color: #57606A;
}
QFrame#aiCoreFilterGroup {
    background-color: #FFFFFF;
    border: 1px solid #E5EAF0;
    border-radius: 8px;
}
QLabel#aiCoreFilterGroupTitle {
    color: #174A8B;
    font-weight: bold;
}
QCheckBox#aiCoreFieldDialogCheck {
    color: #24292F;
    padding: 4px 6px;
}
QCheckBox#aiCoreFieldDialogCheck:disabled {
    color: #57606A;
}
QLabel#aiModelStatus {
    padding: 4px 10px;
    border-radius: 5px;
    font-weight: bold;
}
QLabel#aiModelStatus[state="ready"] {
    color: #174A8B;
    background-color: #EAF2FB;
    border: 1px solid #8BB6E8;
}
QLabel#aiModelStatus[state="warning"] {
    color: #8F1D16;
    background-color: #FFF1F0;
    border: 1px solid #F3B5AD;
}
QLabel#aiModelStatus[state="busy"] {
    color: #174A8B;
    background-color: #F7FBFF;
    border: 1px solid #8BB6E8;
}
QTextEdit#aiHistory {
    background-color: #FFFFFF;
    border: 1px solid #E5EAF0;
    border-radius: 8px;
    padding: 12px;
}
QProgressBar#aiContextPressureBar {
    min-height: 12px;
    max-height: 12px;
    border: 1px solid #D0D7DE;
    border-radius: 6px;
    background-color: #F6F8FA;
}
QProgressBar#aiContextPressureBar::chunk {
    border-radius: 6px;
}
QProgressBar#aiContextPressureBar[state="safe"]::chunk {
    background-color: #2DA44E;
}
QProgressBar#aiContextPressureBar[state="warn"]::chunk {
    background-color: #D97706;
}
QProgressBar#aiContextPressureBar[state="danger"]::chunk {
    background-color: #DC2626;
}
QLineEdit#aiQuestionInput {
    min-height: 38px;
}
"""

ANALYSIS_DOCUMENT_STYLE = """
body {
    font-family: "Microsoft YaHei", "Microsoft YaHei UI", sans-serif;
    color: #24292F;
    font-size: 14px;
}
.message {
    margin: 0 0 18px 0;
}
p {
    margin: 0 0 9px 0;
}
ul, ol {
    margin: 6px 0 9px 22px;
}
li {
    margin-bottom: 4px;
}
hr {
    border: 0;
    border-top: 1px solid #E5EAF0;
    margin: 12px 0;
}
"""


class AIWorker(QObject):
    """在后台线程调用本地 Ollama 模型。"""

    finished = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(
        self,
        question,
        analysis_payload,
        model_name,
        n_ctx,
        history_messages=None,
    ):
        super().__init__()
        self.question = question
        self.analysis_payload = analysis_payload
        self.model_name = model_name
        self.n_ctx = n_ctx
        self.history_messages = [dict(message) for message in history_messages or []]
        self._is_running = True

    def stop(self):
        self._is_running = False

    def run(self):
        try:
            logger.debug("正在调用 Ollama 模型，model=%s, ctx=%s", self.model_name, self.n_ctx)
            answer = self._ask_with_context(self.n_ctx)
            if self._is_running:
                self.finished.emit(answer or "模型没有返回内容。")
        except Exception as e:
            if self._is_running:
                logger.exception("AI 模型调用出错")
                if is_context_length_error(e):
                    self.failed.emit("上下文不足，请在左下角选择更大的上下文后重试")
                else:
                    self.failed.emit(str(e))

    def _ask_with_context(self, n_ctx):
        return ask_model(
            self.question,
            self.analysis_payload,
            self.model_name,
            n_ctx,
            history_messages=self.history_messages,
        )


def render_message_html(role: str, content: str, is_error: bool = False) -> str:
    if is_error:
        body_html = html.escape(str(content)).replace("\n", "<br>")
        return render_bubble_html(
            body_html,
            align="left",
            avatar="🤖",
            avatar_background="#FFF1F0",
            avatar_color="#8F1D16",
            background="#FFF1F0",
            border="#F3B5AD",
            text_color="#8F1D16",
            corner="left",
        )
    elif role == "user":
        body_html = html.escape(str(content)).replace("\n", "<br>")
        return render_bubble_html(
            body_html,
            align="right",
            avatar="👤",
            avatar_background="#EAF2FB",
            avatar_color="#174A8B",
            background="#2563EB",
            border="#2563EB",
            text_color="#FFFFFF",
            corner="right",
        )
    else:
        body_html = render_markdown_html(content)
        return render_bubble_html(
            body_html,
            align="left",
            avatar="🤖",
            avatar_background="#EAF2FB",
            avatar_color="#174A8B",
            background="#F6F8FA",
            border="#E5E7EB",
            text_color="#24292F",
            corner="left",
        )


def render_bubble_html(
    body_html: str,
    align: str,
    avatar: str,
    avatar_background: str,
    avatar_color: str,
    background: str,
    border: str,
    text_color: str,
    corner: str = "left",
) -> str:
    title_align = "right" if align == "right" else "left"
    tail_radius = (
        "border-top-left-radius: 4px;"
        if corner == "left"
        else "border-top-right-radius: 4px;"
    )
    avatar_cell = f"""
        <td width="32" valign="top" align="center" style="border: none; padding: 0;">
            <div style="width: 28px; height: 28px; line-height: 28px; text-align: center; border-radius: 14px; background-color: {avatar_background}; color: {avatar_color}; font-size: 15px;">{avatar}</div>
        </td>
    """
    gap_cell = '<td width="8" style="border: none; padding: 0;"></td>'
    bubble_cell = f"""
        <td valign="top" align="{title_align}" style="border: none; padding: 0;">
            <table cellspacing="0" cellpadding="0" style="border: none; margin: 0;">
                <tr>
                    <td align="{title_align}" style="border: none; padding: 0;">
                        <div style="background-color: {background}; color: {text_color}; border: 1px solid {border}; border-radius: 12px; {tail_radius} padding: 10px 14px; text-align: left;">
                            {body_html}
                        </div>
                    </td>
                </tr>
            </table>
        </td>
    """
    spacer_cell = '<td width="24%" style="border: none; padding: 0;"></td>'
    if align == "right":
        message_cells = f"{bubble_cell}{gap_cell}{avatar_cell}"
        leading_spacer = spacer_cell
        trailing_spacer = ""
    else:
        message_cells = f"{avatar_cell}{gap_cell}{bubble_cell}"
        leading_spacer = ""
        trailing_spacer = spacer_cell

    return f"""
    <div class="message">
        <table width="100%" cellspacing="0" cellpadding="0" style="border: none; margin: 0;">
            <tr>
                {leading_spacer}
                <td width="76%" align="{title_align}" style="border: none; padding: 0;">
                    <table cellspacing="0" cellpadding="0" align="{title_align}" style="border: none; margin: 0;">
                        <tr>
                            {message_cells}
                        </tr>
                    </table>
                </td>
                {trailing_spacer}
            </tr>
        </table>
    </div>
    """


def render_markdown_html(content: str) -> str:
    try:
        safe_content = html.escape(str(content))
        rendered = markdown.markdown(safe_content, extensions=["extra", "tables"])
        return style_markdown_tables(rendered)
    except Exception as e:
        logger.error("Markdown 渲染失败: %s", e)
        return html.escape(str(content)).replace("\n", "<br>")


def style_markdown_tables(rendered_html: str) -> str:
    return (
        str(rendered_html)
        .replace(
            "<table>",
            '<table style="border-collapse: collapse; width: 100%; margin: 8px 0;">',
        )
        .replace(
            "<th>",
            '<th style="border: 1px solid #D0D7DE; padding: 7px 9px; background-color: #EAF2FB; color: #174A8B; font-weight: bold;">',
        )
        .replace(
            "<td>",
            '<td style="border: 1px solid #D0D7DE; padding: 7px 9px;">',
        )
    )


def default_column_checked(table_name: str, field_name: str) -> bool:
    if field_name in IDENTITY_FIELDS:
        return True
    if field_name in LONG_TEXT_FIELDS:
        return False
    if field_name.startswith("assessment_"):
        return True
    return field_name in CORE_FIELDS.get(table_name, set())


def reset_column_checked(field_name: str) -> bool:
    return field_name in IDENTITY_FIELDS


def _available_field_names(available_fields) -> list:
    names = []
    seen = set()
    for item in available_fields or []:
        raw_name = item.get("name") if isinstance(item, dict) else item
        field_name = str(raw_name or "").strip()
        if not field_name or field_name in seen:
            continue
        names.append(field_name)
        seen.add(field_name)
    return names


def default_core_fields_for_table(table_name: str, available_fields=None) -> set:
    if available_fields is None:
        return set(CORE_FIELDS.get(table_name, set())) | set(IDENTITY_FIELDS)

    return {
        field_name
        for field_name in _available_field_names(available_fields)
        if default_column_checked(table_name, field_name)
    }


def _core_fields_config_path(config_path=None) -> Path:
    return Path(config_path) if config_path is not None else Path(AI_CORE_FIELDS_CONFIG_FILE)


def load_core_field_overrides(config_path=None) -> dict:
    path = _core_fields_config_path(config_path)
    try:
        if not path.exists():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("读取 AI 核心字段配置失败，已回退默认配置: %s", e)
        return {}

    if not isinstance(data, dict):
        return {}

    overrides = {}
    for table_name, fields in data.items():
        if not isinstance(fields, (list, tuple, set)):
            continue
        cleaned = []
        seen = set()
        for field in fields:
            field_name = str(field or "").strip()
            if not field_name or field_name in seen:
                continue
            cleaned.append(field_name)
            seen.add(field_name)
        if cleaned:
            overrides[str(table_name)] = cleaned
    return overrides


def save_core_field_overrides(overrides: dict, config_path=None) -> bool:
    path = _core_fields_config_path(config_path)
    serializable = {}
    for table_name, fields in (overrides or {}).items():
        cleaned = []
        seen = set()
        for field in fields or []:
            field_name = str(field or "").strip()
            if not field_name or field_name in seen:
                continue
            cleaned.append(field_name)
            seen.add(field_name)
        if cleaned:
            serializable[str(table_name)] = cleaned

    try:
        if path.parent and not path.parent.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(serializable, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return True
    except Exception as e:
        logger.error("保存 AI 核心字段配置失败: %s", e)
        return False


def normalize_core_field_selection(table_name: str, selected_fields, available_fields) -> list:
    field_order = _available_field_names(available_fields)
    available_set = set(field_order)
    selected_set = {
        str(field or "").strip()
        for field in selected_fields or []
        if str(field or "").strip()
    }
    selected_set.update(field for field in IDENTITY_FIELDS if field in available_set)
    return [field for field in field_order if field in selected_set]


def core_fields_for_table(table_name: str, available_fields, config_path=None) -> set:
    field_order = _available_field_names(available_fields)
    if not field_order:
        return set()

    overrides = load_core_field_overrides(config_path)
    if table_name in overrides:
        raw_fields = overrides.get(table_name) or []
        raw_selected = {
            str(field or "").strip()
            for field in raw_fields
            if str(field or "").strip()
        }
        has_valid_field = any(field in raw_selected for field in field_order)
        if has_valid_field:
            return set(normalize_core_field_selection(table_name, raw_fields, field_order))

    return default_core_fields_for_table(table_name, field_order)


def save_table_core_fields(table_name: str, selected_fields, available_fields, config_path=None) -> set:
    normalized = normalize_core_field_selection(table_name, selected_fields, available_fields)
    overrides = load_core_field_overrides(config_path)
    overrides[table_name] = normalized
    save_core_field_overrides(overrides, config_path)
    return set(normalized)


def restore_default_core_fields_for_table(table_name: str, available_fields, config_path=None) -> set:
    overrides = load_core_field_overrides(config_path)
    if table_name in overrides:
        overrides.pop(table_name, None)
        save_core_field_overrides(overrides, config_path)
    return default_core_fields_for_table(table_name, available_fields)


def _field_matches_group(field_name: str, patterns) -> bool:
    for pattern in patterns or ():
        pattern = str(pattern or "").strip()
        if not pattern:
            continue
        if pattern.endswith("*") and field_name.startswith(pattern[:-1]):
            return True
        if field_name == pattern:
            return True
    return False


def group_columns_for_table(table_name: str, columns) -> list:
    valid_columns = []
    for column in columns or []:
        if not isinstance(column, dict):
            continue
        field_name = str(column.get("name", "")).strip()
        if not field_name:
            continue
        valid_columns.append(column)

    assigned = set()
    groups = []
    for group_label, patterns in FIELD_GROUPS.get(table_name, ()):
        group_columns = []
        for column in valid_columns:
            field_name = str(column.get("name", "")).strip()
            if field_name in assigned:
                continue
            if _field_matches_group(field_name, patterns):
                group_columns.append(column)
                assigned.add(field_name)
        if group_columns:
            groups.append({"label": group_label, "columns": group_columns})

    other_columns = [
        column
        for column in valid_columns
        if str(column.get("name", "")).strip() not in assigned
    ]
    if other_columns:
        groups.append({"label": OTHER_FIELD_GROUP_LABEL, "columns": other_columns})
    return groups


def filter_analysis_payload_by_columns(analysis_payload: dict, column_selection: dict) -> dict:
    schemas = dict((analysis_payload or {}).get("schemas") or {})
    source_tables = dict((analysis_payload or {}).get("tables") or {})
    filtered_schemas = {}
    filtered_tables = {}

    for table_name, source_table in source_tables.items():
        schema = dict(schemas.get(table_name) or {})
        schema_columns = list(schema.get("columns") or [])
        valid_fields = [
            str(column.get("name", "")).strip()
            for column in schema_columns
            if isinstance(column, dict) and str(column.get("name", "")).strip()
        ]
        selected = []
        selected_set = set(column_selection.get(table_name) or [])
        for field in valid_fields:
            if field in selected_set or field in IDENTITY_FIELDS:
                selected.append(field)

        if not selected:
            continue

        field_labels = dict(source_table.get("field_labels") or {})
        selected_labels = {field: field_labels.get(field, field) for field in selected}
        filtered_schemas[table_name] = {
            "table_name": schema.get("table_name") or table_name,
            "table_label": schema.get("table_label") or source_table.get("table_label") or table_name,
            "columns": [
                column
                for column in schema_columns
                if isinstance(column, dict) and column.get("name") in selected
            ],
        }
        filtered_tables[table_name] = {
            "table_name": source_table.get("table_name") or table_name,
            "table_label": source_table.get("table_label") or schema.get("table_label") or table_name,
            "field_labels": selected_labels,
            "rows": [
                {field: row.get(field, "") for field in selected}
                for row in list(source_table.get("rows") or [])
            ],
        }

    return {
        "schemas": filtered_schemas,
        "tables": filtered_tables,
    }


def _is_cjk_char(char: str) -> bool:
    codepoint = ord(char)
    return (
        0x3400 <= codepoint <= 0x4DBF
        or 0x4E00 <= codepoint <= 0x9FFF
        or 0xF900 <= codepoint <= 0xFAFF
    )


def estimate_text_tokens(text: str) -> int:
    total = 0.0
    for char in str(text or ""):
        if char.isspace():
            total += WHITESPACE_TOKEN_WEIGHT
        elif _is_cjk_char(char):
            total += CJK_TOKEN_WEIGHT
        else:
            total += ASCII_TOKEN_WEIGHT
    return max(1, math.ceil(total))


def estimate_payload_tokens(analysis_payload: dict) -> int:
    payload_text = json.dumps(analysis_payload or {}, ensure_ascii=False, separators=(",", ":"), default=str)
    raw_tokens = estimate_text_tokens(payload_text)
    return max(1, math.ceil(raw_tokens * (1 + CONTEXT_BUFFER_RATIO)))


def format_token_count(token_count: int) -> str:
    token_count = max(0, int(token_count or 0))
    if token_count >= 1000:
        return f"{token_count / 1000:.1f}k"
    return str(token_count)


def _safe_instance_value(obj, name: str, default=None):
    try:
        instance_dict = object.__getattribute__(obj, "__dict__")
    except Exception:
        return default
    return instance_dict.get(name, default)


class FlowLayout(QLayout):
    def __init__(self, parent=None, margin=0, h_spacing=8, v_spacing=8):
        super().__init__(parent)
        self._items = []
        self._h_spacing = int(h_spacing)
        self._v_spacing = int(v_spacing)
        self.setContentsMargins(margin, margin, margin, margin)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientations(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self):
        parent = self.parentWidget()
        if parent is not None and parent.width() > 0:
            width = parent.width()
            return QSize(width, self.heightForWidth(width))
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect, test_only=False):
        margins = self.contentsMargins()
        effective = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())
        x = effective.x()
        y = effective.y()
        line_height = 0

        for item in self._items:
            widget = item.widget()
            if widget is not None and not widget.isVisible():
                continue
            item_size = item.sizeHint()
            next_x = x + item_size.width() + self._h_spacing
            if next_x - self._h_spacing > effective.right() and line_height > 0:
                x = effective.x()
                y = y + line_height + self._v_spacing
                next_x = x + item_size.width() + self._h_spacing
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), item_size))
            x = next_x
            line_height = max(line_height, item_size.height())

        return y + line_height - rect.y() + margins.bottom()


class FieldGroupBlock(QFrame):
    selection_changed = pyqtSignal(str)

    def __init__(self, table_name: str, group_label: str, columns, core_fields=None, parent=None):
        super().__init__(parent)
        self.table_name = table_name
        self.group_label = group_label
        self._columns = [column for column in columns if isinstance(column, dict)]
        self.core_fields = (
            set(core_fields)
            if core_fields is not None
            else default_core_fields_for_table(table_name, self._columns)
        )
        self.checkboxes = {}
        self.action_buttons = {}
        self.setObjectName("aiFieldGroupBlock")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QFrame()
        header.setObjectName("aiFieldGroupHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 10, 12, 10)
        header_layout.setSpacing(8)

        self.title_label = QLabel(group_label)
        self.title_label.setObjectName("aiFieldGroupTitle")
        header_layout.addWidget(self.title_label, 1)

        self.badge_label = QLabel("已选 0/0")
        self.badge_label.setObjectName("aiFieldGroupBadge")
        header_layout.addWidget(self.badge_label, 0, Qt.AlignVCenter)

        self.all_btn = QPushButton("全选")
        self.all_btn.setObjectName("secondaryButton")
        self.reset_btn = QPushButton("重置")
        self.reset_btn.setObjectName("secondaryButton")
        self.action_buttons = {
            "all": self.all_btn,
            "reset": self.reset_btn,
        }
        header_layout.addWidget(self.all_btn)
        header_layout.addWidget(self.reset_btn)
        layout.addWidget(header)

        body = QWidget()
        body.setObjectName("aiFieldScrollContent")
        body_layout = FlowLayout(margin=12, h_spacing=8, v_spacing=8)
        body.setLayout(body_layout)
        self.fields_wrap = body
        self.fields_layout = body_layout

        for column in self._columns:
            field_name = str(column.get("name", "")).strip()
            if not field_name:
                continue
            check = self.create_field_tag(column)
            self.checkboxes[field_name] = check
            body_layout.addWidget(check)

        layout.addWidget(body)

        self.all_btn.clicked.connect(lambda: self.set_all_fields(True))
        self.reset_btn.clicked.connect(self.reset_fields)
        self.refresh_badge()

    def create_field_tag(self, column):
        field_name = str(column.get("name", "")).strip()
        label = str(column.get("label") or field_name)
        check = QPushButton(label)
        check.setObjectName("aiFieldTag")
        check.setCheckable(True)
        check.setToolTip(field_name)
        check.setChecked(field_name in self.core_fields)
        check.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        if field_name in IDENTITY_FIELDS:
            check.setChecked(True)
            check.setEnabled(False)
            check.setToolTip(f"{field_name}（身份字段，必须发送）")
        check.toggled.connect(self._handle_selection_changed)
        return check

    def _handle_selection_changed(self, *_):
        self.refresh_badge()
        self.selection_changed.emit(self.table_name)

    def _apply_state(self, field_state_fn):
        for field_name, check in self.checkboxes.items():
            target_state = bool(field_state_fn(field_name, check))
            if field_name in IDENTITY_FIELDS:
                target_state = True
            previous = check.blockSignals(True)
            try:
                check.setChecked(target_state)
            finally:
                check.blockSignals(previous)
        self.refresh_badge()
        self.selection_changed.emit(self.table_name)

    def set_all_fields(self, checked: bool):
        self._apply_state(lambda field_name, _check: True if field_name in IDENTITY_FIELDS else bool(checked))

    def reset_fields(self):
        self._apply_state(
            lambda field_name, _check: reset_column_checked(field_name)
        )

    def selected_fields(self):
        selected = []
        for field_name, check in self.checkboxes.items():
            if check.isChecked() or field_name in IDENTITY_FIELDS:
                selected.append(field_name)
        return selected

    def selected_count(self):
        return len(self.selected_fields())

    def total_count(self):
        return len(self.checkboxes)

    def refresh_badge(self):
        self.badge_label.setText(f"已选 {self.selected_count()}/{self.total_count() or 0}")

    def reflow_fields(self, width=None):
        fields_layout = _safe_instance_value(self, "fields_layout")
        fields_wrap = _safe_instance_value(self, "fields_wrap")
        if fields_layout is None or fields_wrap is None:
            return
        effective_width = int(width or fields_wrap.width() or self.width() or 1)
        effective_width = max(1, effective_width)
        content_height = fields_layout.heightForWidth(effective_width)
        fields_wrap.setMinimumHeight(content_height)
        fields_layout.invalidate()
        fields_layout.setGeometry(QRect(0, 0, effective_width, max(content_height, fields_wrap.height())))
        fields_wrap.updateGeometry()
        fields_wrap.update()


class CoreFieldSelectionDialog(QDialog):
    SAVE_ACTION = "save"
    RESTORE_DEFAULT_ACTION = "restore_default"

    def __init__(
        self,
        table_name: str,
        table_label: str,
        columns,
        core_fields,
        parent=None,
    ):
        super().__init__(parent)
        self.table_name = table_name
        self.table_label = table_label
        self._columns = [column for column in columns if isinstance(column, dict)]
        self.core_fields = set(core_fields or ())
        self.core_field_checks = {}
        self.action = None
        self.setWindowTitle("核心字段筛选")
        self.setModal(True)
        self.resize(560, 620)
        self.setStyleSheet(DIALOG_BASE_STYLE + DIALOG_BUTTON_STYLE + AI_CHAT_STYLE)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        panel = QFrame()
        panel.setObjectName("aiCoreFilterPanel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(16, 14, 16, 14)
        panel_layout.setSpacing(12)

        title_label = QLabel("核心字段筛选")
        title_label.setObjectName("aiCoreFilterTitle")
        meta_label = QLabel(self.table_label)
        meta_label.setObjectName("aiCoreFilterMeta")
        panel_layout.addWidget(title_label)
        panel_layout.addWidget(meta_label)

        scroll = QScrollArea()
        scroll.setObjectName("aiColumnScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content = QWidget()
        content.setObjectName("aiFieldScrollContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(10)

        for group in group_columns_for_table(self.table_name, self._columns):
            group_block = self.create_group_block(group)
            content_layout.addWidget(group_block)
        content_layout.addStretch()

        scroll.setWidget(content)
        panel_layout.addWidget(scroll, 1)

        button_row = QHBoxLayout()
        button_row.setSpacing(8)
        self.restore_btn = QPushButton("恢复默认核心字段")
        self.restore_btn.setObjectName("secondaryButton")
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setObjectName("secondaryButton")
        self.save_btn = QPushButton("保存并应用")
        self.save_btn.setObjectName("primaryButton")
        self.restore_btn.clicked.connect(self.choose_restore_default)
        self.cancel_btn.clicked.connect(self.reject)
        self.save_btn.clicked.connect(self.choose_save)
        button_row.addWidget(self.restore_btn)
        button_row.addStretch()
        button_row.addWidget(self.cancel_btn)
        button_row.addWidget(self.save_btn)
        panel_layout.addLayout(button_row)

        layout.addWidget(panel)

    def create_group_block(self, group):
        block = QFrame()
        block.setObjectName("aiCoreFilterGroup")
        block_layout = QVBoxLayout(block)
        block_layout.setContentsMargins(12, 10, 12, 10)
        block_layout.setSpacing(8)

        title_label = QLabel(group["label"])
        title_label.setObjectName("aiCoreFilterGroupTitle")
        block_layout.addWidget(title_label)

        for column in group["columns"]:
            self.add_field_check(block_layout, column)
        return block

    def add_field_check(self, layout, column):
        field_name = str(column.get("name", "")).strip()
        if not field_name:
            return

        label = str(column.get("label") or field_name)
        check = QCheckBox(label)
        check.setObjectName("aiCoreFieldDialogCheck")
        check.setToolTip(field_name)
        check.setChecked(field_name in self.core_fields or field_name in IDENTITY_FIELDS)
        if field_name in IDENTITY_FIELDS:
            check.setEnabled(False)
            check.setToolTip(f"{field_name}（身份字段，始终作为核心字段发送）")
        layout.addWidget(check)
        self.core_field_checks[field_name] = check

    def selected_fields(self):
        return [
            field_name
            for field_name, check in self.core_field_checks.items()
            if check.isChecked() or field_name in IDENTITY_FIELDS
        ]

    def choose_save(self):
        self.action = self.SAVE_ACTION
        self.accept()

    def choose_restore_default(self):
        self.action = self.RESTORE_DEFAULT_ACTION
        self.accept()


class FieldSelectionPage(QFrame):
    selection_changed = pyqtSignal(str)
    return_requested = pyqtSignal()

    def __init__(self, table_name: str, table_label: str, row_count: int, columns, parent=None):
        super().__init__(parent)
        self.table_name = table_name
        self.table_label = table_label
        self.row_count = int(row_count)
        self._columns = [column for column in columns if isinstance(column, dict)]
        self.field_names = _available_field_names(self._columns)
        self.core_fields = core_fields_for_table(table_name, self.field_names)
        self.checkboxes = {}
        self.group_blocks = []
        self.action_buttons = {}
        self.core_field_checks = {}
        self.setObjectName("aiFieldSelectionPage")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        header = QFrame()
        header.setObjectName("aiFieldPageHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 12, 16, 12)
        header_layout.setSpacing(8)
        self.field_header_layout = header_layout

        self.title_label = QLabel(f"{table_label}（{self.row_count}行）")
        self.title_label.setObjectName("aiFieldPageTitle")
        self.title_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        header_layout.addWidget(self.title_label, 1, Qt.AlignVCenter)

        self.badge_label = QLabel("已选 0/0 列")
        self.badge_label.setObjectName("aiFieldPageBadge")
        header_layout.addWidget(self.badge_label, 0, Qt.AlignVCenter)

        self.core_btn = QPushButton("核心字段")
        self.core_btn.setObjectName("aiCoreSegmentLeft")
        self.core_btn.setFixedHeight(32)
        self.core_config_btn = QToolButton()
        self.core_config_btn.setObjectName("aiCoreSegmentRight")
        self.core_config_btn.setText("🔍")
        self.core_config_btn.setToolTip("配置本表核心字段")
        self.core_config_btn.setAutoRaise(False)
        self.core_config_btn.setFixedHeight(32)
        self.core_button_group = QFrame()
        self.core_button_group.setObjectName("aiCoreButtonGroup")
        self.core_button_group_layout = QHBoxLayout(self.core_button_group)
        self.core_button_group_layout.setContentsMargins(0, 0, 0, 0)
        self.core_button_group_layout.setSpacing(0)
        self.core_button_group_layout.addWidget(self.core_btn)
        self.core_button_group_layout.addWidget(self.core_config_btn)
        self.all_btn = QPushButton("全选")
        self.all_btn.setObjectName("secondaryButton")
        self.reset_btn = QPushButton("重置")
        self.reset_btn.setObjectName("secondaryButton")
        self.action_buttons = {
            "core": self.core_btn,
            "core_config": self.core_config_btn,
            "all": self.all_btn,
            "reset": self.reset_btn,
        }
        header_layout.addWidget(self.core_button_group, 0, Qt.AlignVCenter)
        header_layout.addWidget(self.all_btn, 0, Qt.AlignVCenter)
        header_layout.addWidget(self.reset_btn, 0, Qt.AlignVCenter)
        layout.addWidget(header)

        field_scroll = QScrollArea()
        field_scroll.setObjectName("aiColumnScroll")
        field_scroll.setWidgetResizable(True)
        field_scroll.setFrameShape(QFrame.NoFrame)
        field_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.field_scroll = field_scroll
        groups_wrap = QWidget()
        groups_wrap.setObjectName("aiFieldScrollContent")
        groups_layout = QVBoxLayout(groups_wrap)
        groups_layout.setContentsMargins(0, 0, 0, 0)
        groups_layout.setSpacing(10)
        self.groups_wrap = groups_wrap
        self.groups_layout = groups_layout

        for group in group_columns_for_table(table_name, self._columns):
            block = FieldGroupBlock(
                table_name=table_name,
                group_label=group["label"],
                columns=group["columns"],
                core_fields=self.core_fields,
                parent=self,
            )
            block.selection_changed.connect(self._handle_selection_changed)
            self.group_blocks.append(block)
            self.checkboxes.update(block.checkboxes)
            for action_name, button in block.action_buttons.items():
                self.action_buttons[f"{group['label']}:{action_name}"] = button
            groups_layout.addWidget(block)
        groups_layout.addStretch()

        field_scroll.setWidget(groups_wrap)
        layout.addWidget(field_scroll, 1)

        footer = QFrame()
        footer.setObjectName("aiFieldPageFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        footer_layout.setSpacing(8)
        self.field_footer_layout = footer_layout
        footer_layout.addStretch()
        self.return_btn = QPushButton("完成选择并返回对话")
        self.return_btn.setObjectName("primaryButton")
        self.return_btn.clicked.connect(lambda _checked=False: self.return_requested.emit())
        footer_layout.addWidget(self.return_btn, 0, Qt.AlignRight | Qt.AlignBottom)
        layout.addWidget(footer)

        self.core_btn.clicked.connect(self.set_core_fields)
        self.core_config_btn.clicked.connect(lambda _checked=False: self.open_core_field_dialog())
        self.all_btn.clicked.connect(lambda: self.set_all_fields(True))
        self.reset_btn.clicked.connect(self.reset_fields)
        self.refresh_badge()
        QTimer.singleShot(0, self.reflow_fields)

    def _handle_selection_changed(self, *_):
        self.refresh_badge()
        self.selection_changed.emit(self.table_name)

    def _apply_state(self, field_state_fn):
        for field_name, check in self.checkboxes.items():
            target_state = bool(field_state_fn(field_name, check))
            if field_name in IDENTITY_FIELDS:
                target_state = True
            previous = check.blockSignals(True)
            try:
                check.setChecked(target_state)
            finally:
                check.blockSignals(previous)
        self.refresh_badge()
        self.selection_changed.emit(self.table_name)

    def set_all_fields(self, checked: bool):
        self._apply_state(lambda field_name, _check: True if field_name in IDENTITY_FIELDS else bool(checked))

    def create_core_field_dialog(self):
        self.core_fields = core_fields_for_table(self.table_name, self.field_names)
        dialog = CoreFieldSelectionDialog(
            self.table_name,
            self.table_label,
            self._columns,
            self.core_fields,
            parent=self,
        )
        self.core_field_checks = dialog.core_field_checks
        return dialog

    def open_core_field_dialog(self):
        dialog = self.create_core_field_dialog()
        try:
            if dialog.exec_() != QDialog.Accepted:
                return

            if dialog.action == CoreFieldSelectionDialog.SAVE_ACTION:
                self.save_core_fields_from_dialog(dialog)
            elif dialog.action == CoreFieldSelectionDialog.RESTORE_DEFAULT_ACTION:
                self.restore_default_core_fields()
        finally:
            self.core_field_checks = {}
            dialog.deleteLater()

    def save_core_fields_from_dialog(self, dialog):
        selected_fields = dialog.selected_fields()
        saved_fields = save_table_core_fields(self.table_name, selected_fields, self.field_names)
        self._apply_core_fields(saved_fields)

    def restore_default_core_fields(self):
        default_fields = restore_default_core_fields_for_table(self.table_name, self.field_names)
        self._apply_core_fields(default_fields)

    def _apply_core_fields(self, core_fields):
        self.core_fields = set(core_fields or ())
        for block in _safe_instance_value(self, "group_blocks", []):
            block.core_fields = set(self.core_fields)
        self._sync_core_field_checks()
        self._apply_state(lambda field_name, _check: field_name in self.core_fields)

    def _sync_core_field_checks(self):
        for field_name, check in _safe_instance_value(self, "core_field_checks", {}).items():
            previous = check.blockSignals(True)
            try:
                check.setChecked(field_name in self.core_fields or field_name in IDENTITY_FIELDS)
            finally:
                check.blockSignals(previous)

    def set_core_fields(self):
        self._apply_core_fields(core_fields_for_table(self.table_name, self.field_names))

    def reset_fields(self):
        self._apply_state(
            lambda field_name, _check: reset_column_checked(field_name)
        )

    def selected_fields(self):
        selected = []
        for field_name, check in self.checkboxes.items():
            if check.isChecked() or field_name in IDENTITY_FIELDS:
                selected.append(field_name)
        return selected

    def selected_count(self):
        return len(self.selected_fields())

    def total_count(self):
        return len(self.checkboxes)

    def refresh_badge(self):
        self.badge_label.setText(f"已选 {self.selected_count()}/{self.total_count() or 0} 列")
        for block in _safe_instance_value(self, "group_blocks", []):
            block.refresh_badge()

    def reflow_fields(self):
        group_blocks = _safe_instance_value(self, "group_blocks", [])
        if not group_blocks:
            return
        width = self.width()
        field_scroll = _safe_instance_value(self, "field_scroll")
        if field_scroll is not None and field_scroll.viewport() is not None:
            width = max(width, field_scroll.viewport().width())
        width = max(1, int(width))
        block_width = max(1, width - 4)
        for block in group_blocks:
            block.reflow_fields(block_width)
        groups_wrap = _safe_instance_value(self, "groups_wrap")
        if groups_wrap is not None:
            groups_wrap.updateGeometry()
            groups_wrap.update()

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self.reflow_fields)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self.reflow_fields)


class TableEnableSwitch(QCheckBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(42, 24)
        self.setToolTip("发送此表给 AI")

    def sizeHint(self):
        return QSize(42, 24)

    def hitButton(self, pos):
        return self.rect().contains(pos)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)

        checked = self.isChecked()
        enabled = self.isEnabled()
        if checked and enabled:
            track_color = QColor("#1E5AA8")
            knob_color = QColor("#FFFFFF")
        elif checked:
            track_color = QColor("#BBD4F0")
            knob_color = QColor("#F6F8FA")
        elif enabled:
            track_color = QColor("#D8DEE4")
            knob_color = QColor("#FFFFFF")
        else:
            track_color = QColor("#EAEEF2")
            knob_color = QColor("#F6F8FA")

        track_rect = self.rect().adjusted(2, 4, -2, -4)
        radius = track_rect.height() / 2
        painter.setBrush(track_color)
        painter.drawRoundedRect(track_rect, radius, radius)

        knob_size = track_rect.height() - 4
        knob_x = (
            track_rect.right() - knob_size - 2
            if checked
            else track_rect.left() + 2
        )
        knob_rect = QRect(knob_x, track_rect.top() + 2, knob_size, knob_size)
        painter.setBrush(knob_color)
        painter.drawEllipse(knob_rect)


class TableNavItem(QFrame):
    toggled = pyqtSignal(str, bool)

    def __init__(self, table_name: str, nav_button: QPushButton, parent=None):
        super().__init__(parent)
        self.table_name = table_name
        self.nav_button = nav_button
        self.setObjectName("aiTableNavItem")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.setMinimumWidth(TABLE_NAV_BUTTON_MIN_WIDTH + 50)
        self.nav_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.nav_button.setMinimumWidth(TABLE_NAV_BUTTON_MIN_WIDTH)
        self.enable_switch = TableEnableSwitch(self)
        self.enable_switch.setChecked(True)
        self.enable_switch.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.enable_switch.toggled.connect(self._emit_toggled)

        layout.addWidget(self.nav_button, 1)
        layout.addWidget(self.enable_switch, 0, Qt.AlignVCenter)

    def _emit_toggled(self, enabled: bool):
        self.toggled.emit(self.table_name, bool(enabled))

    def set_table_enabled(self, enabled: bool):
        previous = self.enable_switch.blockSignals(True)
        try:
            self.enable_switch.setChecked(bool(enabled))
        finally:
            self.enable_switch.blockSignals(previous)
        self.nav_button.setEnabled(bool(enabled))
        self.enable_switch.setToolTip("发送此表给 AI" if enabled else "不发送此表给 AI")

    def set_controls_enabled(self, controls_enabled: bool, table_enabled: bool):
        self.nav_button.setEnabled(bool(controls_enabled and table_enabled))
        self.enable_switch.setEnabled(bool(controls_enabled))


class AIChatDialog(QDialog):
    payload_sync_resume_requested = pyqtSignal()

    def __init__(self, analysis_payload, parent=None, reference_widget=None):
        super().__init__(None)
        self.reference_widget = reference_widget or parent
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self._configure_window_flags()
        self.analysis_payload = analysis_payload
        self.history_messages = []
        self.current_context_recommendation = None
        self.is_inference_running = False
        self.is_payload_syncing = False
        self.is_payload_sync_deferred = False
        self.worker = None
        self.worker_thread = None
        self._pending_history_length = None
        self.current_context_n_ctx = None
        self.context_options = []
        self.column_checks = {}
        self.table_pages = {}
        self.table_nav_buttons = {}
        self.table_nav_items = {}
        self.enabled_tables = {}
        self._selected_payload_cache_key = None
        self._selected_payload_cache = None
        self._payload_token_cache_key = None
        self._payload_token_cache_value = None
        self._pressure_refresh_scheduled = False
        self._pressure_refresh_pending = False
        self.pressure_timer = QTimer(self)
        self.pressure_timer.setSingleShot(True)
        self.pressure_timer.setInterval(CONTEXT_PRESSURE_REFRESH_DELAY_MS)
        self.pressure_timer.timeout.connect(self._apply_pending_pressure_refresh)
        self.setWindowTitle("智能分析助手")
        self.setup_ui()
        self._apply_default_geometry()

    def _configure_window_flags(self):
        self.setWindowFlag(Qt.Window, True)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setWindowFlag(Qt.WindowSystemMenuHint, True)
        self.setWindowFlag(Qt.WindowMinimizeButtonHint, True)
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, True)
        self.setWindowFlag(Qt.WindowCloseButtonHint, True)

    def closeEvent(self, event):
        if self.worker:
            self.worker.stop()
        event.accept()

    def showEvent(self, event):
        super().showEvent(event)
        self._center_on_reference_geometry()

    def _reference_geometry(self):
        reference_widget = getattr(self, "reference_widget", None)
        if reference_widget is not None:
            reference_window = reference_widget.window()
            if reference_window is not None:
                geometry = reference_window.geometry()
                if geometry.isValid() and geometry.width() > 0 and geometry.height() > 0:
                    return geometry

        screen = QApplication.primaryScreen()
        if screen is not None:
            return screen.availableGeometry()
        return None

    def _preferred_geometry_size(self, reference_geometry):
        width = max(1, int(reference_geometry.width() * AI_CHAT_WINDOW_WIDTH_RATIO))
        height = max(1, int(reference_geometry.height() * AI_CHAT_WINDOW_HEIGHT_RATIO))
        return width, height

    def _apply_default_geometry(self):
        reference_geometry = self._reference_geometry()
        if reference_geometry is None:
            self.resize(1280, 760)
            return
        width, height = self._preferred_geometry_size(reference_geometry)
        self.resize(width, height)

    def _center_on_reference_geometry(self):
        reference_geometry = self._reference_geometry()
        if reference_geometry is None:
            return
        dialog_geometry = self.frameGeometry()
        dialog_geometry.moveCenter(reference_geometry.center())
        self.move(dialog_geometry.topLeft())

    def refresh_models(self):
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        available, models = fetch_ollama_models(timeout=3)
        if models:
            self.model_combo.addItems(models)
            self.set_model_status("ready", f"已连接，{len(models)} 个模型")
            self.status_label.setText(f"就绪，端口 {APP_OLLAMA_HOST}")
        else:
            self.model_combo.addItem(MODEL_PLACEHOLDER)
            if available:
                self.set_model_status("warning", "未检测到模型")
                self.status_label.setText(f"Ollama 已连接，但未检测到可用模型 ({APP_OLLAMA_HOST})")
            else:
                self.set_model_status("warning", "服务未连接")
                self.status_label.setText(f"无法连接专用 Ollama ({APP_OLLAMA_HOST})")
        self.model_combo.blockSignals(False)
        self.refresh_context_recommendation()
        self.update_action_state()

    def refresh_context_recommendation(self, model_name=None):
        if model_name is None:
            model_name = self.selected_model_name()
        elif not self.is_valid_model_name(model_name):
            model_name = ""

        previous_n_ctx = _safe_instance_value(self, "current_context_n_ctx")
        self.current_context_recommendation = recommend_context_length(model_name)
        self.context_options = self.available_context_options(self.current_context_recommendation)
        if previous_n_ctx in self.context_options:
            selected_n_ctx = previous_n_ctx
        elif previous_n_ctx is None:
            selected_n_ctx = self.current_context_recommendation.n_ctx
        else:
            selected_n_ctx = max(self.context_options or [self.current_context_recommendation.n_ctx])
        self.set_context_n_ctx(selected_n_ctx)
        if _safe_instance_value(self, "pressure_timer") is not None:
            self.schedule_context_pressure_refresh()
        return self.current_context_recommendation

    def available_context_options(self, recommendation=None):
        recommendation = recommendation or self.current_context_recommendation
        if recommendation is None:
            return list(MANUAL_CONTEXT_OPTIONS)
        max_n_ctx = max(1, int(getattr(recommendation, "max_n_ctx", None) or recommendation.n_ctx or 4096))
        recommended_n_ctx = max(1, int(getattr(recommendation, "n_ctx", 4096) or 4096))
        options = [value for value in MANUAL_CONTEXT_OPTIONS if value <= max_n_ctx]
        if recommended_n_ctx <= max_n_ctx:
            options.append(recommended_n_ctx)
        if not options:
            options.append(recommended_n_ctx)
        return sorted(set(options))

    def set_context_n_ctx(self, n_ctx):
        self.current_context_n_ctx = int(n_ctx) if n_ctx else self.current_context_n_ctx
        self.refresh_context_controls()
        if _safe_instance_value(self, "pressure_timer") is not None:
            self.schedule_context_pressure_refresh()

    def refresh_context_controls(self):
        context_combo = _safe_instance_value(self, "context_combo")
        context_reason_label = _safe_instance_value(self, "context_reason_label")
        if context_combo is not None:
            selected_text = str(int(self.current_context_n_ctx or 0))
            blocked = context_combo.blockSignals(True) if hasattr(context_combo, "blockSignals") else None
            try:
                if hasattr(context_combo, "clear"):
                    context_combo.clear()
                for option in self.context_options or self.available_context_options():
                    context_combo.addItem(str(int(option)))
                if hasattr(context_combo, "findText") and hasattr(context_combo, "setCurrentIndex"):
                    index = context_combo.findText(selected_text)
                    if index >= 0:
                        context_combo.setCurrentIndex(index)
                elif hasattr(context_combo, "setCurrentText"):
                    context_combo.setCurrentText(selected_text)
            finally:
                if hasattr(context_combo, "blockSignals"):
                    context_combo.blockSignals(blocked)
        if context_reason_label is not None:
            if self.current_context_recommendation:
                context_reason_label.setText(f"（{self.current_context_recommendation.reason}）")
            else:
                context_reason_label.setText("")

    def on_context_combo_changed(self, value):
        try:
            n_ctx = int(str(value).strip())
        except (TypeError, ValueError):
            return
        if n_ctx == int(self.current_context_n_ctx or 0):
            return
        self.set_context_n_ctx(n_ctx)

    def schedule_context_pressure_refresh(self):
        pressure_timer = _safe_instance_value(self, "pressure_timer")
        if pressure_timer is None:
            return
        self._pressure_refresh_pending = True
        pressure_timer.start()

    def _apply_pending_pressure_refresh(self):
        if not self._pressure_refresh_pending:
            return
        self._pressure_refresh_pending = False
        self.refresh_context_pressure()

    def refresh_context_pressure(self):
        pressure_bar = _safe_instance_value(self, "pressure_bar")
        if pressure_bar is None:
            return

        selected_payload = self.selected_analysis_payload()
        selection_key = self._selected_payload_cache_key
        if selection_key == self._payload_token_cache_key and self._payload_token_cache_value is not None:
            estimated_tokens = self._payload_token_cache_value
        else:
            estimated_tokens = estimate_payload_tokens(selected_payload)
            self._payload_token_cache_key = selection_key
            self._payload_token_cache_value = estimated_tokens
        context_limit = max(
            1,
            int(
                _safe_instance_value(self, "current_context_n_ctx", None)
                or getattr(_safe_instance_value(self, "current_context_recommendation"), "n_ctx", 4096)
                or 4096
            ),
        )
        ratio = min(1.0, estimated_tokens / context_limit)
        percent = int(round(ratio * 100))

        pressure_bar.setValue(percent)
        if ratio < 0.5:
            state = "safe"
            hint = "余量充足"
        elif ratio < 0.8:
            state = "warn"
            hint = "接近上限"
        else:
            state = "danger"
            hint = "请减少字段"

        pressure_bar.setProperty("state", state)
        self.refresh_widget_style(pressure_bar)
        self.pressure_value_label.setText(f"{format_token_count(estimated_tokens)} / {format_token_count(context_limit)} tokens")
        self.pressure_hint_label.setText(hint)

    def on_table_selection_changed(self, table_name: str):
        page = _safe_instance_value(self, "table_pages", {}).get(table_name)
        if page:
            page.refresh_badge()
        self.invalidate_selection_caches()
        self.refresh_column_summary()

    def setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        self.setStyleSheet(DIALOG_BASE_STYLE + DIALOG_BUTTON_STYLE + AI_CHAT_STYLE)

        root_splitter = QSplitter(Qt.Horizontal)
        root_splitter.setChildrenCollapsible(False)
        root_splitter.setHandleWidth(8)
        self.root_splitter = root_splitter

        sidebar_panel = QFrame()
        sidebar_panel.setObjectName("aiSidebarPanel")
        sidebar_panel.setMinimumWidth(NAV_SIDEBAR_MIN_WIDTH)
        sidebar_panel.setMaximumWidth(360)
        self.sidebar_panel = sidebar_panel
        sidebar_layout = QVBoxLayout(sidebar_panel)
        sidebar_layout.setContentsMargins(12, 12, 12, 12)
        sidebar_layout.setSpacing(12)

        sidebar_header = QFrame()
        sidebar_header.setObjectName("aiSidebarHeader")
        sidebar_header_layout = QVBoxLayout(sidebar_header)
        sidebar_header_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_header_layout.setSpacing(3)
        self.sidebar_title_label = QLabel("智能分析")
        self.sidebar_title_label.setObjectName("aiSidebarTitle")
        self.sidebar_title_label.setWordWrap(False)
        self.sidebar_subtitle_label = QLabel("当前对话与数据表")
        self.sidebar_subtitle_label.setObjectName("aiSidebarSubtitle")
        self.sidebar_subtitle_label.setWordWrap(False)
        sidebar_header_layout.addWidget(self.sidebar_title_label)
        sidebar_header_layout.addWidget(self.sidebar_subtitle_label)
        sidebar_layout.addWidget(sidebar_header)

        self.nav_button_group = QButtonGroup(self)
        self.nav_button_group.setExclusive(True)

        self.chat_nav_btn = self.create_nav_button("当前对话", "聊天与提问")
        self.chat_nav_btn.clicked.connect(lambda _checked=False: self.switch_to_chat())
        self.nav_button_group.addButton(self.chat_nav_btn)
        sidebar_layout.addWidget(self.chat_nav_btn)

        table_header = QHBoxLayout()
        table_header.setSpacing(8)
        table_title = QLabel("数据表")
        table_title.setObjectName("aiSectionTitle")
        table_title.setWordWrap(False)
        self.table_title_label = table_title
        self.column_summary_label = QLabel()
        self.column_summary_label.setObjectName("aiColumnSummary")
        self.column_summary_label.setWordWrap(False)
        self.column_summary_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        table_header.addWidget(table_title)
        table_header.addStretch()
        table_header.addWidget(self.column_summary_label)
        sidebar_layout.addLayout(table_header)

        nav_scroll = QScrollArea()
        nav_scroll.setObjectName("aiColumnScroll")
        nav_scroll.setWidgetResizable(True)
        nav_scroll.setFrameShape(QFrame.NoFrame)
        nav_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        nav_body = QWidget()
        nav_body.setObjectName("aiNavBody")
        self.table_nav_layout = QVBoxLayout(nav_body)
        self.table_nav_layout.setContentsMargins(0, 0, 0, 0)
        self.table_nav_layout.setSpacing(8)
        self.table_nav_layout.addStretch()
        nav_scroll.setWidget(nav_body)
        sidebar_layout.addWidget(nav_scroll, 1)

        self.sidebar_footer = self.create_global_controls_panel()
        sidebar_layout.addWidget(self.sidebar_footer, 0)

        main_panel = QFrame()
        main_panel_layout = QVBoxLayout(main_panel)
        main_panel_layout.setContentsMargins(0, 0, 0, 0)
        main_panel_layout.setSpacing(0)

        self.workspace_stack = QStackedWidget()
        self.chat_page = self.create_chat_page()
        self.workspace_stack.addWidget(self.chat_page)
        main_panel_layout.addWidget(self.workspace_stack, 1)

        root_splitter.addWidget(sidebar_panel)
        root_splitter.addWidget(main_panel)
        root_splitter.setStretchFactor(0, 0)
        root_splitter.setStretchFactor(1, 1)
        root_splitter.setSizes([NAV_SIDEBAR_WIDTH, 980])

        layout.addWidget(root_splitter, 1)

        self.setLayout(layout)
        self.build_field_pages()
        self.chat_nav_btn.setChecked(True)
        self.refresh_models()
        self.refresh_context_pressure()

    def create_nav_button(self, title: str, subtitle: str = ""):
        button = QPushButton(title if not subtitle else f"{title}\n{subtitle}")
        button.setObjectName("aiNavButton")
        button.setCheckable(True)
        button.setMinimumHeight(50)
        button.setMinimumWidth(TABLE_NAV_BUTTON_MIN_WIDTH)
        button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        button.setCursor(Qt.PointingHandCursor)
        return button

    def create_table_nav_item(self, table_name: str, table_label: str):
        nav_button = self.create_nav_button(table_label)
        nav_item = TableNavItem(table_name, nav_button)
        nav_item.toggled.connect(self.on_table_enabled_changed)
        nav_button.clicked.connect(lambda _checked=False, name=table_name: self.switch_to_table(name))
        return nav_item

    def create_global_controls_panel(self):
        settings_panel = QFrame()
        settings_panel.setObjectName("aiSidebarSection")
        settings_layout = QVBoxLayout(settings_panel)
        settings_layout.setContentsMargins(12, 12, 12, 12)
        settings_layout.setSpacing(8)

        settings_header = QHBoxLayout()
        settings_header.setSpacing(8)
        self.settings_header_layout = settings_header
        self.model_status_label = QLabel("正在初始化")
        self.model_status_label.setObjectName("aiModelStatus")
        self.model_status_label.setProperty("state", "busy")
        settings_header.addWidget(self.model_status_label)
        settings_header.addStretch()
        settings_layout.addLayout(settings_header)

        self.model_combo = QComboBox()
        self.model_combo.currentTextChanged.connect(self.refresh_context_recommendation)
        settings_layout.addWidget(self.model_combo)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.setObjectName("secondaryButton")
        self.refresh_btn.clicked.connect(self.refresh_models)
        self.clear_btn = QPushButton("清空对话")
        self.clear_btn.setObjectName("secondaryButton")
        self.clear_btn.clicked.connect(self.clear_chat)
        action_row.addWidget(self.refresh_btn)
        action_row.addWidget(self.clear_btn)
        settings_layout.addLayout(action_row)

        pressure_row = QHBoxLayout()
        pressure_row.setSpacing(8)
        pressure_label = QLabel("上下文压力")
        pressure_label.setObjectName("aiSectionTitle")
        pressure_row.addWidget(pressure_label)
        pressure_row.addStretch()
        self.context_combo = QComboBox()
        self.context_combo.setObjectName("aiContextCombo")
        self.context_combo.setToolTip("选择上下文大小")
        self.context_combo.currentTextChanged.connect(self.on_context_combo_changed)
        pressure_row.addWidget(self.context_combo, 0, Qt.AlignVCenter)
        settings_layout.addLayout(pressure_row)

        self.context_reason_label = QLabel("")
        self.context_reason_label.setObjectName("aiContextLabel")
        self.context_reason_label.setWordWrap(True)
        settings_layout.addWidget(self.context_reason_label)

        self.pressure_bar = QProgressBar()
        self.pressure_bar.setObjectName("aiContextPressureBar")
        self.pressure_bar.setRange(0, 100)
        self.pressure_bar.setValue(0)
        self.pressure_bar.setTextVisible(False)
        self.pressure_bar.setProperty("state", "safe")
        settings_layout.addWidget(self.pressure_bar)

        pressure_meta_row = QHBoxLayout()
        pressure_meta_row.setSpacing(8)
        self.pressure_value_label = QLabel("0 / 0 tokens")
        self.pressure_value_label.setObjectName("aiPressureValue")
        self.pressure_hint_label = QLabel("余量充足")
        self.pressure_hint_label.setObjectName("aiPressureHint")
        pressure_meta_row.addWidget(self.pressure_value_label)
        pressure_meta_row.addStretch()
        pressure_meta_row.addWidget(self.pressure_hint_label)
        settings_layout.addLayout(pressure_meta_row)
        return settings_panel

    def create_chat_page(self):
        chat_page = QWidget()
        chat_layout = QVBoxLayout(chat_page)
        chat_layout.setContentsMargins(0, 0, 0, 0)
        chat_layout.setSpacing(10)

        self.chat_history = QTextEdit()
        self.chat_history.setObjectName("aiHistory")
        self.chat_history.setReadOnly(True)
        self.chat_history.document().setDefaultStyleSheet(ANALYSIS_DOCUMENT_STYLE)
        chat_layout.addWidget(self.chat_history, 1)

        input_panel = QFrame()
        input_panel.setObjectName("aiInputPanel")
        input_layout = QVBoxLayout(input_panel)
        input_layout.setContentsMargins(14, 12, 14, 12)
        input_layout.setSpacing(8)

        question_row = QHBoxLayout()
        question_row.setSpacing(8)
        self.input_field = QLineEdit()
        self.input_field.setObjectName("aiQuestionInput")
        self.input_field.setPlaceholderText("输入要分析的问题")
        self.input_field.returnPressed.connect(self.start_inference)

        self.send_btn = QPushButton("发送")
        self.send_btn.setObjectName("primaryButton")
        self.send_btn.setMinimumWidth(92)
        self.send_btn.clicked.connect(self.start_inference)
        self.send_btn.setDefault(True)

        question_row.addWidget(self.input_field, 1)
        question_row.addWidget(self.send_btn)
        input_layout.addLayout(question_row)

        self.status_label = QLabel("正在初始化...")
        self.status_label.setObjectName("aiFooterStatus")
        self.status_label.setWordWrap(True)
        input_layout.addWidget(self.status_label)
        chat_layout.addWidget(input_panel)
        return chat_page

    def build_field_pages(self, selected_columns=None, enabled_tables=None):
        schemas = dict((self.analysis_payload or {}).get("schemas") or {})
        tables = dict((self.analysis_payload or {}).get("tables") or {})
        self.column_checks = {}
        self.enabled_tables = {}

        insert_index = max(0, self.table_nav_layout.count() - 1)
        for table_name, schema in schemas.items():
            table = dict(tables.get(table_name) or {})
            columns = [column for column in schema.get("columns") or [] if isinstance(column, dict)]
            table_label = schema.get("table_label") or table.get("table_label") or table_name
            row_count = len(table.get("rows") or [])
            page = FieldSelectionPage(
                table_name=table_name,
                table_label=table_label,
                row_count=row_count,
                columns=columns,
                parent=self,
            )
            page.selection_changed.connect(self.on_table_selection_changed)
            page.return_requested.connect(self.switch_to_chat)
            if selected_columns and table_name in selected_columns:
                selected_fields = set(selected_columns.get(table_name) or [])
                for field_name, check in page.checkboxes.items():
                    previous = check.blockSignals(True)
                    try:
                        check.setChecked(field_name in selected_fields or field_name in IDENTITY_FIELDS)
                    finally:
                        check.blockSignals(previous)
            self.table_pages[table_name] = page
            self.column_checks[table_name] = page.checkboxes
            table_enabled = True
            if enabled_tables is not None and table_name in enabled_tables:
                table_enabled = bool(enabled_tables.get(table_name))
            self.enabled_tables[table_name] = table_enabled
            self.workspace_stack.addWidget(page)

            nav_item = self.create_table_nav_item(table_name, table_label)
            nav_button = nav_item.nav_button
            self.table_nav_items[table_name] = nav_item
            self.table_nav_buttons[table_name] = nav_button
            self.nav_button_group.addButton(nav_button)
            nav_item.set_table_enabled(table_enabled)
            self.table_nav_layout.insertWidget(insert_index, nav_item)
            insert_index += 1

        self.refresh_table_navigation()
        self.refresh_column_summary()
        self.schedule_context_pressure_refresh()

    def snapshot_field_selection(self) -> dict:
        selection = {}
        for table_name, page in _safe_instance_value(self, "table_pages", {}).items():
            table_selection = []
            for field_name, check in page.checkboxes.items():
                if check.isChecked() or field_name in IDENTITY_FIELDS:
                    table_selection.append(field_name)
            selection[table_name] = table_selection
        return selection

    def current_field_table_name(self):
        stack = _safe_instance_value(self, "workspace_stack")
        if stack is None or not hasattr(stack, "currentWidget"):
            return None
        try:
            current_widget = stack.currentWidget()
        except RuntimeError:
            return None
        for table_name, page in _safe_instance_value(self, "table_pages", {}).items():
            if current_widget is page:
                return table_name
        return None

    def clear_field_pages(self):
        stack = _safe_instance_value(self, "workspace_stack")
        nav_layout = _safe_instance_value(self, "table_nav_layout")
        nav_group = _safe_instance_value(self, "nav_button_group")

        for page in list(_safe_instance_value(self, "table_pages", {}).values()):
            if stack is not None and hasattr(stack, "removeWidget"):
                stack.removeWidget(page)
            if hasattr(page, "deleteLater"):
                page.deleteLater()

        for table_name, nav_button in list(_safe_instance_value(self, "table_nav_buttons", {}).items()):
            if nav_group is not None and hasattr(nav_group, "removeButton"):
                nav_group.removeButton(nav_button)

        for nav_item in list(_safe_instance_value(self, "table_nav_items", {}).values()):
            if nav_layout is not None and hasattr(nav_layout, "removeWidget"):
                nav_layout.removeWidget(nav_item)
            if hasattr(nav_item, "deleteLater"):
                nav_item.deleteLater()

        self.column_checks = {}
        self.table_pages = {}
        self.table_nav_buttons = {}
        self.table_nav_items = {}
        self.enabled_tables = {}

    def begin_payload_sync(self):
        self.is_payload_syncing = True
        self.is_payload_sync_deferred = False
        status_label = _safe_instance_value(self, "status_label")
        if status_label is not None:
            status_label.setText("主窗口查询结果已更新，正在同步...")
        self.update_action_state()

    def mark_payload_sync_deferred(self):
        self.is_payload_sync_deferred = True
        status_label = _safe_instance_value(self, "status_label")
        if status_label is not None:
            status_label.setText("主窗口查询结果已更新，当前分析结束后同步。")
        self.update_action_state()

    def apply_analysis_payload(self, analysis_payload):
        selected_columns = self.snapshot_field_selection()
        enabled_tables = dict(_safe_instance_value(self, "enabled_tables", {}) or {})
        current_table_name = self.current_field_table_name()

        self.analysis_payload = analysis_payload or {"schemas": {}, "tables": {}}
        self.clear_field_pages()
        self.invalidate_selection_caches()
        self.is_payload_syncing = False
        self.is_payload_sync_deferred = False
        self.build_field_pages(selected_columns=selected_columns, enabled_tables=enabled_tables)

        if current_table_name in _safe_instance_value(self, "table_pages", {}) and self.is_table_enabled(current_table_name):
            self.switch_to_table(current_table_name)
        else:
            self.switch_to_chat()

        self.refresh_context_pressure()
        status_label = _safe_instance_value(self, "status_label")
        if status_label is not None:
            status_label.setText("数据已同步，后续问题将基于最新查询结果。")
        self.update_action_state()

    def fail_payload_sync(self, message):
        self.is_payload_syncing = False
        self.is_payload_sync_deferred = False
        status_label = _safe_instance_value(self, "status_label")
        if status_label is not None:
            detail = str(message).strip()
            suffix = f"：{detail}" if detail else ""
            status_label.setText(f"同步失败，当前 AI 窗口仍使用上一次数据{suffix}")
        self.update_action_state()

    def switch_to_chat(self):
        stack = _safe_instance_value(self, "workspace_stack")
        chat_page = _safe_instance_value(self, "chat_page")
        if stack is not None and chat_page is not None:
            stack.setCurrentWidget(chat_page)
        chat_nav_btn = _safe_instance_value(self, "chat_nav_btn")
        if chat_nav_btn is not None:
            chat_nav_btn.setChecked(True)

    def switch_to_table(self, table_name: str):
        if not self.is_table_enabled(table_name):
            return

        page = _safe_instance_value(self, "table_pages", {}).get(table_name)
        stack = _safe_instance_value(self, "workspace_stack")
        if stack is not None and page is not None:
            stack.setCurrentWidget(page)
            QTimer.singleShot(0, page.reflow_fields)
        nav_button = _safe_instance_value(self, "table_nav_buttons", {}).get(table_name)
        if nav_button is not None:
            nav_button.setChecked(True)

    def is_table_enabled(self, table_name: str) -> bool:
        return bool(_safe_instance_value(self, "enabled_tables", {}).get(table_name, True))

    def on_table_enabled_changed(self, table_name: str, enabled: bool):
        if table_name not in _safe_instance_value(self, "table_pages", {}):
            return

        self.enabled_tables[table_name] = bool(enabled)
        self.invalidate_selection_caches()
        if not enabled and self.is_current_table_page(table_name):
            self.switch_to_chat()
        self.refresh_column_summary()

    def is_current_table_page(self, table_name: str) -> bool:
        stack = _safe_instance_value(self, "workspace_stack")
        page = _safe_instance_value(self, "table_pages", {}).get(table_name)
        if stack is None or page is None or not hasattr(stack, "currentWidget"):
            return False
        try:
            return stack.currentWidget() is page
        except RuntimeError:
            return False

    def refresh_table_navigation(self):
        busy = bool(_safe_instance_value(self, "is_inference_running", False) or _safe_instance_value(self, "is_payload_syncing", False))
        for table_name, page in _safe_instance_value(self, "table_pages", {}).items():
            nav_button = _safe_instance_value(self, "table_nav_buttons", {}).get(table_name)
            nav_item = _safe_instance_value(self, "table_nav_items", {}).get(table_name)
            if page is None:
                continue
            page.refresh_badge()
            if nav_button is not None:
                selected_count = page.selected_count()
                total_count = page.total_count()
                nav_button.setText(f"{page.table_label}\n已选 {selected_count}/{total_count}")
                nav_button.setToolTip(f"{page.table_label} · {page.row_count} 行 · 已选 {selected_count}/{total_count}")
                nav_button.setEnabled(self.is_table_enabled(table_name) and not busy)
            if nav_item is not None:
                nav_item.set_table_enabled(self.is_table_enabled(table_name))
                nav_item.set_controls_enabled(not busy, self.is_table_enabled(table_name))

    def selected_column_map(self) -> dict:
        schemas = dict((self.analysis_payload or {}).get("schemas") or {})
        selection = {}
        for table_name, schema in schemas.items():
            if not self.is_table_enabled(table_name):
                continue
            checks = self.column_checks.get(table_name) or {}
            selected = []
            if checks:
                for field_name, check in checks.items():
                    if check.isChecked() or field_name in IDENTITY_FIELDS:
                        selected.append(field_name)
            else:
                for column in schema.get("columns") or []:
                    if not isinstance(column, dict):
                        continue
                    field_name = str(column.get("name", "")).strip()
                    if field_name in IDENTITY_FIELDS:
                        selected.append(field_name)
            if selected:
                selection[table_name] = selected
        return selection

    def selected_payload_cache_key(self, selection=None):
        selection = selection if selection is not None else self.selected_column_map()
        return tuple(
            (table_name, tuple(fields))
            for table_name, fields in selection.items()
        )

    def invalidate_selection_caches(self):
        self._selected_payload_cache_key = None
        self._selected_payload_cache = None
        self._payload_token_cache_key = None
        self._payload_token_cache_value = None

    def selected_payload_stats(self) -> tuple:
        tables = dict((self.analysis_payload or {}).get("tables") or {})
        selection = self.selected_column_map()
        table_count = 0
        column_count = 0
        row_count = 0
        for table_name, selected_fields in selection.items():
            if not selected_fields:
                continue
            table = dict(tables.get(table_name) or {})
            rows = table.get("rows") or []
            table_count += 1
            column_count += len(selected_fields)
            row_count += len(rows) if hasattr(rows, "__len__") else sum(1 for _ in rows)
        return table_count, column_count, row_count

    def enabled_analysis_payload(self) -> dict:
        payload = self.analysis_payload or {}
        schemas = dict(payload.get("schemas") or {})
        tables = dict(payload.get("tables") or {})
        return {
            "schemas": {
                table_name: schema
                for table_name, schema in schemas.items()
                if self.is_table_enabled(table_name)
            },
            "tables": {
                table_name: table
                for table_name, table in tables.items()
                if self.is_table_enabled(table_name)
            },
        }

    def selected_analysis_payload(self) -> dict:
        selection = self.selected_column_map()
        cache_key = self.selected_payload_cache_key(selection)
        if cache_key != self._selected_payload_cache_key or self._selected_payload_cache is None:
            self._selected_payload_cache = filter_analysis_payload_by_columns(
                self.enabled_analysis_payload(),
                selection,
            )
            self._selected_payload_cache_key = cache_key
        return self._selected_payload_cache

    def has_selected_analysis_payload(self) -> bool:
        table_count, column_count, row_count = self.selected_payload_stats()
        return table_count > 0 and column_count > 0 and row_count > 0

    def refresh_column_summary(self):
        column_summary_label = _safe_instance_value(self, "column_summary_label")
        if column_summary_label is None:
            return
        table_count, column_count, _row_count = self.selected_payload_stats()
        column_summary_label.setText(f"将发送{table_count}个表/{column_count}列")
        self.refresh_table_navigation()
        if _safe_instance_value(self, "send_btn") is not None:
            self.update_action_state()
        self.schedule_context_pressure_refresh()

    def clear_chat(self):
        """清空对话历史。"""
        self.history_messages = []
        self._pending_history_length = None
        self.chat_history.clear()
        self.status_label.setText("对话已清空，可继续提问。")

    def start_inference(self):
        question = self.input_field.text().strip()
        if not question:
            return

        model_name = self.selected_model_name()
        if not model_name:
            self.status_label.setText("未选择可用模型，无法发送分析请求。")
            self.update_action_state()
            return

        if self.is_inference_running or _safe_instance_value(self, "is_payload_syncing", False):
            return

        if not self.has_selected_analysis_payload():
            self.status_label.setText("请至少选择一个可分析字段后再发送。")
            self.update_action_state()
            return

        selected_payload = self.selected_analysis_payload()

        if self.current_context_recommendation is None:
            self.refresh_context_recommendation(model_name)
        n_ctx = int(self.current_context_n_ctx or 4096)

        self.append_message("user", question)
        self.input_field.clear()
        self.is_inference_running = True
        self.set_model_status("busy", "分析中")
        self.status_label.setText("AI 正在基于已选择的数据字段分析...")
        self.update_action_state()

        history_snapshot = [dict(message) for message in self.history_messages]
        self._pending_history_length = len(self.history_messages)
        self.history_messages.append({"role": "user", "content": question})

        self.worker = AIWorker(
            question,
            selected_payload,
            model_name,
            n_ctx,
            history_snapshot,
        )
        self.worker_thread = threading.Thread(target=self.worker.run)
        self.worker_thread.daemon = True
        self.worker.finished.connect(self.handle_response)
        self.worker.failed.connect(self.handle_error)
        self.worker_thread.start()

    def handle_response(self, response):
        final_answer = str(response).strip()
        self.history_messages.append({"role": "assistant", "content": final_answer})
        self.append_message("assistant", final_answer)
        self._pending_history_length = None
        self.finish_inference("就绪")

    def handle_error(self, message):
        error_text = str(message).strip() or "未知错误"
        self.append_message("assistant", f"AI 运行出错: {error_text}", is_error=True)
        pending_length = getattr(self, "_pending_history_length", None)
        if isinstance(pending_length, int) and pending_length >= 0:
            self.history_messages = self.history_messages[:pending_length]
        self._pending_history_length = None
        self.finish_inference(f"分析失败：{error_text}")

    def append_message(self, role: str, content: str, is_error: bool = False):
        self.chat_history.append(render_message_html(role, content, is_error=is_error))
        self.chat_history.verticalScrollBar().setValue(self.chat_history.verticalScrollBar().maximum())

    def finish_inference(self, status_text: str):
        self.is_inference_running = False
        self.worker = None
        self.set_model_status("ready" if self.selected_model_name() else "warning", self.model_ready_text())
        if _safe_instance_value(self, "is_payload_sync_deferred", False):
            self.is_payload_sync_deferred = False
            self.status_label.setText("主窗口查询结果已更新，正在同步...")
            self.update_action_state()
            try:
                self.payload_sync_resume_requested.emit()
            except RuntimeError:
                logger.debug("AI payload sync resume signal could not be emitted", exc_info=True)
            return
        self.status_label.setText(status_text)
        self.update_action_state()

    def update_action_state(self):
        has_model = bool(self.selected_model_name())
        has_selected_payload = self.has_selected_analysis_payload()
        busy = bool(_safe_instance_value(self, "is_inference_running", False) or _safe_instance_value(self, "is_payload_syncing", False))
        send_btn = _safe_instance_value(self, "send_btn")
        input_field = _safe_instance_value(self, "input_field")
        model_combo = _safe_instance_value(self, "model_combo")
        refresh_btn = _safe_instance_value(self, "refresh_btn")
        clear_btn = _safe_instance_value(self, "clear_btn")
        if send_btn is not None:
            send_btn.setEnabled(has_model and has_selected_payload and not busy)
        if input_field is not None:
            input_field.setEnabled(not busy)
        if model_combo is not None:
            model_combo.setEnabled(not busy)
        if refresh_btn is not None:
            refresh_btn.setEnabled(not busy)
        if clear_btn is not None:
            clear_btn.setEnabled(not busy)
        if _safe_instance_value(self, "chat_nav_btn") is not None:
            _safe_instance_value(self, "chat_nav_btn").setEnabled(not busy)
        for table_name, nav_button in _safe_instance_value(self, "table_nav_buttons", {}).items():
            nav_button.setEnabled(not busy and self.is_table_enabled(table_name))
        for table_name, nav_item in _safe_instance_value(self, "table_nav_items", {}).items():
            nav_item.set_controls_enabled(not busy, self.is_table_enabled(table_name))
        for page in _safe_instance_value(self, "table_pages", {}).values():
            for field_name, check in page.checkboxes.items():
                check.setEnabled(field_name not in IDENTITY_FIELDS and not busy)
            for button in page.action_buttons.values():
                button.setEnabled(not busy)

    def selected_model_name(self) -> str:
        model_name = self.model_combo.currentText().strip()
        return model_name if self.is_valid_model_name(model_name) else ""

    def is_valid_model_name(self, model_name: str) -> bool:
        model_name = (model_name or "").strip()
        return bool(model_name and model_name != MODEL_PLACEHOLDER and not model_name.startswith("未检测到"))

    def set_model_status(self, state: str, text: str):
        self.model_status_label.setText(text)
        self.model_status_label.setProperty("state", state)
        self.refresh_widget_style(self.model_status_label)

    def model_ready_text(self) -> str:
        if self.selected_model_name():
            return "已连接"
        return "未检测到模型"

    def refresh_widget_style(self, widget):
        if not hasattr(widget, "style"):
            return
        style = widget.style()
        style.unpolish(widget)
        style.polish(widget)
