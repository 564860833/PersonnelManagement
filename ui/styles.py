"""Shared UI styles."""

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
            background-color: #2f7d4f;
            color: white;
            font-weight: bold;
            border: 1px solid #2f7d4f;
        }
        QPushButton:hover {
            background-color: #276b43;
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
            background-color: #1f6fb2;
            color: white;
            font-weight: bold;
            border: 1px solid #1f6fb2;
        }
        QPushButton:hover {
            background-color: #185f9a;
        }
    """,
    "accent": """
        QPushButton {
            background-color: #7a4ea3;
            color: white;
            font-weight: bold;
            border: 1px solid #7a4ea3;
        }
        QPushButton:hover {
            background-color: #68438b;
        }
    """,
    "table_enabled": """
        QPushButton {
            background-color: #2f7d4f;
            color: white;
            border: 1px solid #2f7d4f;
            padding: 6px;
        }
        QPushButton:hover {
            background-color: #276b43;
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
    border: 1px solid #74b58b;
    background-color: #fbfffc;
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
    background-color: #edf7f1;
    border-color: #b7d9c4;
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
    background-color: #edf7f1;
    border-color: #74b58b;
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
    background-color: #edf7f1;
    border-color: #74b58b;
}
QPushButton#monthCell[state="selected"] {
    background-color: #2f7d4f;
    border-color: #2f7d4f;
    color: #ffffff;
    font-weight: bold;
}
QPushButton#monthCell[state="range"] {
    background-color: #e8f4ed;
    border-color: #b7d9c4;
    color: #1f5f39;
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
    background-color: #edf7f1;
    border-color: #74b58b;
}
QPushButton#yearCell[state="selected"] {
    background-color: #2f7d4f;
    border-color: #2f7d4f;
    color: #ffffff;
    font-weight: bold;
}
QPushButton#yearCell[state="range"] {
    background-color: #e8f4ed;
    border-color: #b7d9c4;
    color: #1f5f39;
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
    selection-background-color: #dfefff;
}
QHeaderView::section {
    background-color: #f3f4f6;
    color: #222;
    padding: 6px;
    border: 1px solid #d4d7dc;
    font-weight: bold;
}
"""

NO_PERMISSION_LABEL_STYLE = "font-size: 18px; color: #b00020;"


def button_style(kind: str) -> str:
    return BUTTON_BASE + BUTTON_STYLES[kind]
