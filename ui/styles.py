"""Shared UI styles."""

THEME_PRIMARY = "#1E5AA8"
THEME_PRIMARY_HOVER = "#174A8B"
THEME_LIGHT = "#EAF2FB"
THEME_BORDER = "#8BB6E8"

TABLE_ROW_BACKGROUND = "#FFFFFF"
TABLE_ROW_ALTERNATE_BACKGROUND = "#F7F9FC"

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

SCROLLBAR_STYLE = """
QScrollBar:vertical {
    width: 8px;
    margin: 0;
    border: none;
    background: transparent;
}
QScrollBar:horizontal {
    height: 8px;
    margin: 0;
    border: none;
    background: transparent;
}
QScrollBar::handle:vertical,
QScrollBar::handle:horizontal {
    background-color: rgba(30, 90, 168, 70);
    border: none;
    border-radius: 4px;
}
QScrollBar::handle:vertical {
    min-height: 28px;
}
QScrollBar::handle:horizontal {
    min-width: 28px;
}
QScrollBar::handle:vertical:hover,
QScrollBar::handle:horizontal:hover {
    background-color: rgba(30, 90, 168, 110);
}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical,
QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal {
    width: 0;
    height: 0;
    border: none;
    background: transparent;
}
QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical,
QScrollBar::add-page:horizontal,
QScrollBar::sub-page:horizontal {
    background: transparent;
}
"""

DIALOG_BASE_STYLE = """
QDialog {
    background-color: #F0F2F5;
    color: #24292f;
}
QFrame#dialogPanel,
QFrame#loginCard {
    background-color: #FFFFFF;
    border: none;
    border-radius: 8px;
}
QLabel#dialogTitle {
    color: #174A8B;
    font-size: 16px;
    font-weight: bold;
}
QLabel#dialogSubtitle {
    color: #57606a;
}
QLabel#fieldLabel {
    color: #333333;
    font-weight: bold;
}
QLineEdit,
QComboBox,
QTextEdit {
    min-height: 32px;
    padding: 4px 8px;
    border: 1px solid #d0d7de;
    border-radius: 5px;
    background-color: #ffffff;
    color: #24292f;
}
QLineEdit:focus,
QComboBox:focus,
QTextEdit:focus {
    border: 1px solid #8BB6E8;
    background-color: #F7FBFF;
}
QComboBox::drop-down {
    border: none;
    width: 24px;
}
QGroupBox {
    margin-top: 14px;
    padding: 14px 10px 10px 10px;
    border: 1px solid #e5eaf0;
    border-radius: 8px;
    background-color: #ffffff;
    color: #174A8B;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
}
QScrollArea {
    border: 1px solid #e5eaf0;
    border-radius: 6px;
    background-color: #ffffff;
}
QScrollArea > QWidget > QWidget {
    background-color: #ffffff;
}
QCheckBox {
    spacing: 8px;
    color: #24292f;
}
QTableWidget,
QTableView {
    gridline-color: #d8d8d8;
    selection-background-color: #D8E9F9;
    selection-color: #174A8B;
    alternate-background-color: #F7F9FC;
    background-color: #FFFFFF;
    border: 1px solid #d8dee4;
    border-radius: 6px;
}
QTableWidget::item:selected,
QTableView::item:selected {
    background-color: #D8E9F9;
    color: #174A8B;
}
QHeaderView::section {
    background-color: #EAF2FB;
    color: #174A8B;
    padding: 6px;
    border: 1px solid #8BB6E8;
    font-weight: bold;
}
""" + SCROLLBAR_STYLE

DIALOG_BUTTON_STYLE = """
QPushButton {
    min-height: 32px;
    padding: 4px 14px;
    border: 1px solid #c9d1d9;
    border-radius: 5px;
    background-color: #ffffff;
    color: #24292f;
}
QPushButton:hover {
    background-color: #f6f8fa;
}
QPushButton#primaryButton {
    background-color: #1E5AA8;
    border-color: #1E5AA8;
    color: #ffffff;
    font-weight: bold;
}
QPushButton#primaryButton:hover {
    background-color: #174A8B;
}
QPushButton#secondaryButton {
    background-color: #ffffff;
    border-color: #c9d1d9;
    color: #24292f;
}
QPushButton#secondaryButton:hover {
    background-color: #EAF2FB;
    border-color: #8BB6E8;
    color: #174A8B;
}
QPushButton#dangerButton {
    background-color: #B42318;
    border-color: #B42318;
    color: #ffffff;
    font-weight: bold;
}
QPushButton#dangerButton:hover {
    background-color: #8F1D16;
}
QPushButton:disabled {
    background-color: #f6f8fa;
    border-color: #eaeef2;
    color: #8c959f;
}
"""

DANGER_CONFIRM_STYLE = DIALOG_BASE_STYLE + DIALOG_BUTTON_STYLE + """
QFrame#dangerConfirmPanel {
    background-color: #FFFFFF;
    border: none;
    border-radius: 8px;
}
QLabel#dangerTitle {
    color: #8F1D16;
    font-size: 16px;
    font-weight: bold;
}
QLabel#dangerMessage {
    color: #3f4752;
    line-height: 1.4;
}
QLabel#dangerHint {
    color: #8F1D16;
    background-color: #FFF1F0;
    border: 1px solid #F3B5AD;
    border-radius: 5px;
    padding: 8px;
}
"""

LOGIN_DIALOG_STYLE = DIALOG_BASE_STYLE + DIALOG_BUTTON_STYLE + """
QDialog#loginDialog {
    background-color: #F0F2F5;
}
QLabel#loginTitle {
    color: #174A8B;
    font-size: 20px;
    font-weight: bold;
}
QLabel#loginSubtitle {
    color: #57606a;
    font-size: 12px;
}
QFrame#loginDivider {
    background-color: #EAF2FB;
    min-height: 1px;
    max-height: 1px;
    border: none;
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

COMPACT_BUTTON_STYLE = "padding: 3px;"

PAGINATION_BUTTON_STYLE = """
QPushButton#pageNavButton,
QPushButton#pageNumberButton,
QPushButton#pageEllipsis {
    min-width: 32px;
    max-width: 32px;
    min-height: 32px;
    max-height: 32px;
    padding: 0;
    border: 1px solid #d0d7de;
    border-radius: 5px;
    background-color: #ffffff;
    color: #24292f;
    font-weight: normal;
}
QPushButton#pageNavButton:hover,
QPushButton#pageNumberButton:hover {
    background-color: #EAF2FB;
    border-color: #8BB6E8;
    color: #174A8B;
}
QPushButton#pageNumberButton[active="true"] {
    background-color: #1E5AA8;
    border-color: #1E5AA8;
    color: #ffffff;
    font-weight: bold;
}
QPushButton#pageNavButton:disabled,
QPushButton#pageNumberButton:disabled {
    background-color: #f6f8fa;
    border-color: #eaeef2;
    color: #c9d1d9;
}
QPushButton#pageEllipsis {
    border-color: transparent;
    background-color: transparent;
    color: #6e7781;
}
"""

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
    border: 1px solid #E5EAF0;
    border-radius: 8px;
}
QFrame#monthPanelDivider {
    background-color: #E5EAF0;
    border: none;
    min-height: 1px;
    max-height: 1px;
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
    border: 1px solid transparent;
    border-radius: 5px;
    background-color: transparent;
    color: #57606a;
    font-weight: bold;
}
QPushButton#monthNavButton:hover {
    background-color: #EAF2FB;
    border-color: #8BB6E8;
    color: #174A8B;
}
QPushButton#monthNavButton:disabled {
    background-color: transparent;
    color: #c9d1d9;
    border-color: transparent;
}
QPushButton#monthCell {
    min-height: 36px;
    max-height: 36px;
    padding: 0;
    font-size: 13px;
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
    min-height: 36px;
    max-height: 36px;
    padding: 0;
    font-size: 13px;
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
    selection-background-color: #D8E9F9;
    selection-color: #174A8B;
    alternate-background-color: #F7F9FC;
    background-color: #FFFFFF;
}
QTableWidget::item:selected, QTableView::item:selected {
    background-color: #D8E9F9;
    color: #174A8B;
}
QHeaderView::section {
    background-color: #EAF2FB;
    color: #174A8B;
    padding: 6px;
    border: 1px solid #8BB6E8;
    font-weight: bold;
}
""" + SCROLLBAR_STYLE

NO_PERMISSION_LABEL_STYLE = "font-size: 18px; color: #b00020;"


def button_style(kind: str) -> str:
    return BUTTON_BASE + BUTTON_STYLES[kind]
