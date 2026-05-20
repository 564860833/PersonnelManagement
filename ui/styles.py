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
