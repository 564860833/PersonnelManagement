"""Shared UI styles."""

THEME_PRIMARY = "#1E5AA8"
THEME_PRIMARY_HOVER = "#174A8B"
THEME_LIGHT = "#EAF2FB"
THEME_BORDER = "#8BB6E8"

TABLE_ROW_BACKGROUND = "#FFFFFF"
TABLE_ROW_ALTERNATE_BACKGROUND = "#F7F9FC"
TABLE_ROW_HOVER_BACKGROUND = THEME_LIGHT

PAGE_BACKGROUND_STYLE = """
QWidget#queryPage {
    background-color: #F0F2F5;
}
"""

CARD_STYLE = """
QFrame#sectionCard {
    background-color: #FFFFFF;
    border: none;
    border-radius: 8px;
}
"""

BUTTON_BASE = """
QPushButton {
    border-radius: 4px;
    padding: 6px;
}
QPushButton:disabled {
    background-color: #f0f0f0;
    color: #888;
    border: 1px solid #ddd;
}
"""

BUTTON_STYLES = {
    "primary": """
        QPushButton {
            background-color: #1E5AA8;
            color: white;
            font-weight: bold;
            border: 1px solid #1E5AA8;
        }
        QPushButton:hover {
            background-color: #174A8B;
        }
    """,
    "secondary": """
        QPushButton {
            background-color: #f5f5f5;
            color: #333;
            border: 1px solid #c9c9c9;
        }
        QPushButton:hover {
            background-color: #e9e9e9;
        }
    """,
    "info": """
        QPushButton {
            background-color: #1E5AA8;
            color: white;
            font-weight: bold;
            border: 1px solid #1E5AA8;
        }
        QPushButton:hover {
            background-color: #174A8B;
        }
    """,
    "accent": """
        QPushButton {
            background-color: #1E5AA8;
            color: white;
            font-weight: bold;
            border: 1px solid #1E5AA8;
        }
        QPushButton:hover {
            background-color: #174A8B;
        }
    """,
    "table_enabled": """
        QPushButton {
            background-color: #1E5AA8;
            color: white;
            border: 1px solid #1E5AA8;
            padding: 6px;
        }
        QPushButton:hover {
            background-color: #174A8B;
        }
    """,
    "table_disabled": """
        QPushButton {
            background-color: #f0f0f0;
            color: #888;
            border: 1px solid #ddd;
            padding: 6px;
        }
    """,
}

ANALYSIS_FIELD_LABEL_STYLE = "color: #333; font-weight: bold; margin-bottom: 5px;"
COMPACT_BUTTON_STYLE = "padding: 3px;"

QUERY_FORM_CONTROL_STYLE = """
QLabel#queryFormLabel {
    color: #333;
    font-weight: bold;
}
QLineEdit, QComboBox {
    min-height: 30px;
    padding: 4px 8px;
    border: 1px solid #d0d7de;
    border-radius: 5px;
    background-color: #ffffff;
    color: #222;
}
QLineEdit:focus, QComboBox:focus {
    border: 1px solid #8BB6E8;
    background-color: #F7FBFF;
}
QLineEdit:read-only {
    background-color: #f9fafb;
}
QLineEdit#monthRangePicker {
    color: #222;
}
QComboBox::drop-down {
    border: none;
    width: 24px;
}
QWidget#monthPanel {
    background-color: #ffffff;
    border: 1px solid #d8dee4;
    border-radius: 6px;
}
QLabel#monthPanelCaption {
    color: #57606a;
    font-weight: bold;
}
QLabel#monthPanelTitle {
    color: #24292f;
    font-weight: bold;
}
QPushButton#monthYearButton {
    min-height: 0;
    padding: 0 8px;
    border: 1px solid transparent;
    border-radius: 5px;
    background-color: transparent;
    color: #24292f;
    font-weight: bold;
}
QPushButton#monthYearButton:hover {
    background-color: #EAF2FB;
    border-color: #8BB6E8;
}
QPushButton#monthNavButton {
    min-height: 0;
    padding: 0;
    border: 1px solid #d0d7de;
    border-radius: 5px;
    background-color: #f6f8fa;
    color: #24292f;
}
QPushButton#monthNavButton:hover {
    background-color: #EAF2FB;
    border-color: #8BB6E8;
}
QPushButton#monthNavButton:disabled {
    background-color: #f6f8fa;
    color: #c9d1d9;
    border-color: #eaeef2;
}
QPushButton#monthCell {
    min-height: 0;
    padding: 0;
    border: 1px solid #d0d7de;
    border-radius: 5px;
    background-color: #ffffff;
    color: #24292f;
}
QPushButton#monthCell:hover {
    background-color: #EAF2FB;
    border-color: #8BB6E8;
}
QPushButton#monthCell[state="selected"] {
    background-color: #1E5AA8;
    border-color: #1E5AA8;
    color: #ffffff;
    font-weight: bold;
}
QPushButton#monthCell[state="range"] {
    background-color: #EAF2FB;
    border-color: #8BB6E8;
    color: #174A8B;
}
QPushButton#monthCell:disabled {
    background-color: #f6f8fa;
    border-color: #eaeef2;
    color: #c9d1d9;
}
QPushButton#yearCell {
    min-height: 0;
    padding: 0;
    border: 1px solid #d0d7de;
    border-radius: 5px;
    background-color: #ffffff;
    color: #24292f;
}
QPushButton#yearCell:hover {
    background-color: #EAF2FB;
    border-color: #8BB6E8;
}
QPushButton#yearCell[state="selected"] {
    background-color: #1E5AA8;
    border-color: #1E5AA8;
    color: #ffffff;
    font-weight: bold;
}
QPushButton#yearCell[state="range"] {
    background-color: #EAF2FB;
    border-color: #8BB6E8;
    color: #174A8B;
}
QPushButton#yearCell:disabled {
    background-color: #f6f8fa;
    border-color: #eaeef2;
    color: #c9d1d9;
}
"""

RESULT_TABLE_STYLE = """
QTableWidget, QTableView {
    gridline-color: #d8d8d8;
    selection-background-color: #EAF2FB;
    alternate-background-color: #F7F9FC;
    background-color: #FFFFFF;
}
QHeaderView::section {
    background-color: #EAF2FB;
    color: #174A8B;
    padding: 6px;
    border: 1px solid #8BB6E8;
    font-weight: bold;
}
"""

NO_PERMISSION_LABEL_STYLE = "font-size: 18px; color: #b00020;"


def button_style(kind: str) -> str:
    return BUTTON_BASE + BUTTON_STYLES[kind]
