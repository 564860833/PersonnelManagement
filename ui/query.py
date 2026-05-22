import re
import logging

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QTableView,
    QComboBox, QFrame, QGraphicsDropShadowEffect,
    QMessageBox, QHeaderView, QDialog,
    QVBoxLayout, QCheckBox, QDialogButtonBox,
    QScrollArea, QAbstractItemView, QGridLayout, QSizePolicy, QStackedWidget
)
from PyQt5.QtCore import Qt, QSignalBlocker, pyqtSignal
from PyQt5.QtGui import QColor, QFont
from core.database import Database
from metadata.constants import (
    TABLE_LABELS,
    get_table_field_items,
    get_table_field_labels,
    get_table_label,
)
from metadata.query_options import (
    EDUCATION_KEYWORDS,
    EDUCATION_LEVELS,
    GRADE_OPTIONS,
    POSITION_GROUPS,
    POSITION_LEVELS,
    POSITION_MAPPING,
)
from ui.styles import (
    CARD_STYLE,
    DIALOG_BASE_STYLE,
    DIALOG_BUTTON_STYLE,
    PAGE_BACKGROUND_STYLE,
    PAGINATION_BUTTON_STYLE,
    QUERY_FORM_CONTROL_STYLE,
    RESULT_TABLE_STYLE,
    button_style,
)
from ui.table_model import ResultTableModel
from services.ollama_manager import ensure_ollama_ready

logger = logging.getLogger('QueryTab')


def build_ai_analysis_payload(results_dict: dict, permissions: dict, assessment_years=None) -> dict:
    """构建 AI 分析 payload：schema 用于选列，rows 仅供第二阶段分析。"""
    payload = {
        "schemas": {},
        "tables": {},
    }
    allowed_tables = [
        table_name
        for table_name in TABLE_LABELS.keys()
        if (permissions or {}).get(table_name)
    ]

    for table_name in allowed_tables:
        field_labels = get_table_field_labels(table_name, assessment_years or [])
        rows = [dict(row) for row in (results_dict or {}).get(table_name, [])]
        payload["schemas"][table_name] = {
            "table_name": table_name,
            "table_label": get_table_label(table_name),
            "columns": [
                {"name": field_name, "label": label}
                for field_name, label in field_labels.items()
            ],
        }
        payload["tables"][table_name] = {
            "table_name": table_name,
            "table_label": get_table_label(table_name),
            "field_labels": dict(field_labels),
            "rows": rows,
        }

    return payload


def has_analysis_rows(analysis_payload: dict) -> bool:
    """Return True when at least one permitted table has query rows for AI analysis."""
    for table_payload in (analysis_payload.get("tables") or {}).values():
        if not isinstance(table_payload, dict):
            continue
        if table_payload.get("rows"):
            return True
    return False


def _month_sort_key(value: str):
    """把 yyyy.MM 转为可比较的月份序号。"""
    year, month = value.split(".")
    return int(year) * 12 + int(month)


class MonthRangeDialog(QDialog):
    """双面板年月范围选择弹窗。"""

    MIN_YEAR = 1900
    MAX_YEAR = 2100

    def __init__(self, parent=None, start=None, end=None):
        super().__init__(parent)
        self.setWindowTitle("选择出生年月范围")
        self.setMinimumWidth(760)
        self._selected_start = self.normalize_month(start)
        self._selected_end = self.normalize_month(end)
        if self._selected_start and self._selected_end:
            if _month_sort_key(self._selected_start) > _month_sort_key(self._selected_end):
                self._selected_end = None
        self.setup_ui()
        self.update_panels()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(16, 16, 16, 16)

        start_year, end_year = self.initial_panel_years()
        panel_layout = QHBoxLayout()
        panel_layout.setSpacing(14)

        self.start_panel = MonthPanel("起始年月", start_year, self.MIN_YEAR, self.MAX_YEAR)
        self.end_panel = MonthPanel("结束年月", end_year, self.MIN_YEAR, self.MAX_YEAR)
        self.start_panel.monthSelected.connect(self.on_start_selected)
        self.start_panel.yearSelected.connect(self.on_start_year_selected)
        self.end_panel.monthSelected.connect(self.on_end_selected)
        self.end_panel.yearSelected.connect(self.on_end_year_selected)
        panel_layout.addWidget(self.start_panel)
        panel_layout.addWidget(self.end_panel)
        layout.addLayout(panel_layout)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        clear_btn = button_box.addButton("清空", QDialogButtonBox.ResetRole)
        clear_btn.setObjectName("secondaryButton")
        clear_btn.clicked.connect(self.clear_and_accept)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        self.ok_button = button_box.button(QDialogButtonBox.Ok)
        self.ok_button.setObjectName("primaryButton")
        self.ok_button.setText("确认")
        self.cancel_button = button_box.button(QDialogButtonBox.Cancel)
        if self.cancel_button is not None:
            self.cancel_button.setObjectName("secondaryButton")
            self.cancel_button.setText("取消")
        layout.addWidget(button_box)

        self.setStyleSheet(DIALOG_BASE_STYLE + DIALOG_BUTTON_STYLE + QUERY_FORM_CONTROL_STYLE)
        self.start_panel.apply_cell_metrics()
        self.end_panel.apply_cell_metrics()

    def initial_panel_years(self):
        start_year = self.year_part(self._selected_start)
        end_year = self.year_part(self._selected_end)
        if start_year and end_year:
            return start_year, end_year
        if start_year:
            return start_year, min(start_year + 1, self.MAX_YEAR)
        if end_year:
            return max(end_year - 1, self.MIN_YEAR), end_year
        return 1990, 1999

    def selected_range(self):
        return self._selected_start, self._selected_end

    def clear_and_accept(self):
        self._selected_start = None
        self._selected_end = None
        super().accept()

    def on_start_selected(self, value):
        self._selected_start = value
        if self._selected_end and _month_sort_key(value) > _month_sort_key(self._selected_end):
            self._selected_end = None
        start_year = self.year_part(value)
        if self.end_panel.year < start_year:
            self.end_panel.set_year(start_year)
        self.update_panels()

    def on_start_year_selected(self, year):
        self.on_start_selected(f"{year}.01")

    def on_end_selected(self, value):
        if self._selected_start and _month_sort_key(value) < _month_sort_key(self._selected_start):
            return
        self._selected_end = value
        self.update_panels()

    def on_end_year_selected(self, year):
        self.on_end_selected(f"{year}.12")

    def update_panels(self):
        self.start_panel.set_selection(self._selected_start, self._selected_end)
        self.end_panel.set_selection(
            self._selected_start,
            self._selected_end,
            disabled_before=self._selected_start,
        )
        self.ok_button.setEnabled(bool(self._selected_start or self._selected_end))

    def accept(self):
        if not (self._selected_start or self._selected_end):
            return
        if (
            self._selected_start
            and self._selected_end
            and _month_sort_key(self._selected_start) > _month_sort_key(self._selected_end)
        ):
            QMessageBox.warning(self, "年月范围错误", "起始年月不能晚于结束年月。")
            return
        super().accept()

    def normalize_month(self, value):
        if not value:
            return None
        value = str(value).replace("-", ".")
        match = re.match(r"^\d{4}\.(0[1-9]|1[0-2])$", value)
        return value if match else None

    def year_part(self, value):
        return int(value.split(".")[0]) if value else None


class MonthPanel(QFrame):
    """单侧年份月份面板。"""

    YEAR_PAGE_SIZE = 12
    MONTH_CELL_WIDTH = 72
    YEAR_CELL_HEIGHT = 38
    MONTH_CELL_HEIGHT = YEAR_CELL_HEIGHT
    MONTH_GRID_SPACING = 10
    MONTH_GRID_VERTICAL_SPACING = 8
    MONTH_GRID_COLUMNS = 3
    monthSelected = pyqtSignal(str)
    yearSelected = pyqtSignal(int)

    def __init__(self, title, year, min_year, max_year, parent=None):
        super().__init__(parent)
        self.title = title
        self.year = year
        self.min_year = min_year
        self.max_year = max_year
        self.year_page_start = self.year_grid_start(year)
        self.view_mode = "month"
        self._start = None
        self._end = None
        self._disabled_before = None
        self.month_buttons = {}
        self.year_buttons = {}
        self.setup_ui()
        self.refresh()

    def setup_ui(self):
        self.setObjectName("monthPanel")
        self.setAttribute(Qt.WA_StyledBackground, True)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(14)
        shadow.setOffset(0, 2)
        shadow.setColor(QColor(0, 0, 0, 24))
        self.setGraphicsEffect(shadow)
        self.content_width = (
            self.MONTH_GRID_COLUMNS * self.MONTH_CELL_WIDTH
            + (self.MONTH_GRID_COLUMNS - 1) * self.MONTH_GRID_SPACING
        )
        self.grid_height = (
            4 * self.MONTH_CELL_HEIGHT
            + 3 * self.MONTH_GRID_VERTICAL_SPACING
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        caption = QLabel(self.title)
        caption.setObjectName("monthPanelCaption")
        layout.addWidget(caption, 0, Qt.AlignHCenter)

        self.header_widget = QWidget()
        self.header_widget.setObjectName("monthPanelHeader")
        self.header_widget.setFixedWidth(self.content_width)
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(6)
        self.prev_button = QPushButton("<")
        self.prev_button.setObjectName("monthNavButton")
        self.prev_button.setFixedSize(34, 32)
        self.prev_button.clicked.connect(lambda: self.shift_page(-1))
        self.year_button = QPushButton()
        self.year_button.setObjectName("monthYearButton")
        self.year_button.setCursor(Qt.PointingHandCursor)
        self.year_button.clicked.connect(self.toggle_year_view)
        self.next_button = QPushButton(">")
        self.next_button.setObjectName("monthNavButton")
        self.next_button.setFixedSize(34, 32)
        self.next_button.clicked.connect(lambda: self.shift_page(1))
        header_layout.addWidget(self.prev_button)
        header_layout.addWidget(self.year_button, 1)
        header_layout.addWidget(self.next_button)
        self.header_widget.setLayout(header_layout)
        layout.addWidget(self.header_widget, 0, Qt.AlignHCenter)

        self.month_container = QWidget()
        self.month_container.setObjectName("monthGridContainer")
        self.month_container.setFixedSize(self.content_width, self.grid_height)
        month_container_layout = QVBoxLayout(self.month_container)
        month_container_layout.setContentsMargins(0, 0, 0, 0)
        month_grid = QGridLayout()
        month_grid.setHorizontalSpacing(self.MONTH_GRID_SPACING)
        month_grid.setVerticalSpacing(self.MONTH_GRID_VERTICAL_SPACING)
        for month in range(1, 13):
            button = QPushButton(f"{month:02d}")
            button.setObjectName("monthCell")
            button.setFixedSize(self.MONTH_CELL_WIDTH, self.MONTH_CELL_HEIGHT)
            button.clicked.connect(lambda _, m=month: self.monthSelected.emit(self.month_value(m)))
            self.month_buttons[month] = button
            month_grid.addWidget(button, (month - 1) // 3, (month - 1) % 3)
        month_container_layout.addLayout(month_grid)

        self.year_container = QWidget()
        self.year_container.setObjectName("yearGridContainer")
        self.year_container.setFixedSize(self.content_width, self.grid_height)
        year_container_layout = QVBoxLayout(self.year_container)
        year_container_layout.setContentsMargins(0, 0, 0, 0)
        year_grid = QGridLayout()
        year_grid.setHorizontalSpacing(self.MONTH_GRID_SPACING)
        year_grid.setVerticalSpacing(self.MONTH_GRID_VERTICAL_SPACING)
        for index in range(self.YEAR_PAGE_SIZE):
            button = QPushButton()
            button.setObjectName("yearCell")
            button.setFixedSize(self.MONTH_CELL_WIDTH, self.YEAR_CELL_HEIGHT)
            button.clicked.connect(lambda _, i=index: self.select_year_from_grid(i))
            self.year_buttons[index] = button
            year_grid.addWidget(button, index // 3, index % 3)
        year_container_layout.addLayout(year_grid)

        self.grid_stack = QStackedWidget()
        self.grid_stack.setObjectName("monthGridStack")
        self.grid_stack.setFixedSize(self.content_width, self.grid_height)
        self.grid_stack.addWidget(self.month_container)
        self.grid_stack.addWidget(self.year_container)
        layout.addWidget(self.grid_stack, 0, Qt.AlignHCenter)

        layout.addStretch()

    def apply_cell_metrics(self):
        self.header_widget.setFixedWidth(self.content_width)
        self.grid_stack.setFixedSize(self.content_width, self.grid_height)
        self.month_container.setFixedSize(self.content_width, self.grid_height)
        self.year_container.setFixedSize(self.content_width, self.grid_height)
        self.prev_button.setFixedSize(34, 32)
        self.next_button.setFixedSize(34, 32)
        for button in self.month_buttons.values():
            button.setFixedSize(self.MONTH_CELL_WIDTH, self.MONTH_CELL_HEIGHT)
        for button in self.year_buttons.values():
            button.setFixedSize(self.MONTH_CELL_WIDTH, self.YEAR_CELL_HEIGHT)

    def set_year(self, year):
        self.year = max(self.min_year, min(self.max_year, year))
        self.year_page_start = self.year_grid_start(self.year)
        self.refresh()

    def shift_page(self, delta):
        if self.view_mode == "year":
            self.set_year_page_start(self.year_page_start + delta * self.YEAR_PAGE_SIZE)
            return
        self.set_year(self.year + delta)

    def toggle_year_view(self):
        if self.view_mode == "year":
            self.view_mode = "month"
        else:
            self.view_mode = "year"
            self.year_page_start = self.year_grid_start(self.year)
        self.refresh()

    def select_year_from_grid(self, index):
        year = self.year_page_start + index
        if year < self.min_year or year > self.max_year:
            return
        self.year = year
        self.view_mode = "month"
        self.yearSelected.emit(year)
        self.refresh()

    def set_year_page_start(self, year):
        max_start = self.year_grid_start(self.max_year)
        self.year_page_start = max(self.min_year, min(max_start, year))
        self.refresh()

    def set_selection(self, start, end, disabled_before=None):
        self._start = start
        self._end = end
        self._disabled_before = disabled_before
        self.refresh()

    def refresh(self):
        self.grid_stack.setCurrentWidget(
            self.year_container if self.view_mode == "year" else self.month_container
        )
        if self.view_mode == "year":
            page_end = min(self.year_page_start + self.YEAR_PAGE_SIZE - 1, self.max_year)
            self.year_button.setText(f"{self.year_page_start} - {page_end}")
            self.prev_button.setEnabled(self.year_page_start > self.min_year)
            self.next_button.setEnabled(self.year_page_start + self.YEAR_PAGE_SIZE - 1 < self.max_year)
            self.refresh_year_buttons()
            return

        self.year_button.setText(f"{self.year}")
        self.prev_button.setEnabled(self.year > self.min_year)
        self.next_button.setEnabled(self.year < self.max_year)
        for month, button in self.month_buttons.items():
            value = self.month_value(month)
            disabled = self.is_disabled(value)
            button.setEnabled(not disabled)
            button.setToolTip("结束年月不能早于起始年月" if disabled else "")
            button.setProperty("state", self.month_state(value))
            self.refresh_style(button)

    def refresh_year_buttons(self):
        for index, button in self.year_buttons.items():
            year = self.year_page_start + index
            disabled = year < self.min_year or year > self.max_year or self.is_year_disabled(year)
            button.setText(str(year))
            button.setEnabled(not disabled)
            button.setVisible(self.min_year <= year <= self.max_year)
            button.setToolTip("结束年份不能早于起始年月" if disabled else "")
            button.setProperty("state", self.year_state(year))
            self.refresh_style(button)

    def is_disabled(self, value):
        return bool(
            self._disabled_before
            and _month_sort_key(value) < _month_sort_key(self._disabled_before)
        )

    def is_year_disabled(self, year):
        return bool(
            self._disabled_before
            and _month_sort_key(f"{year}.12") < _month_sort_key(self._disabled_before)
        )

    def month_state(self, value):
        if value == self._start or value == self._end:
            return "selected"
        if self._start and self._end:
            value_key = _month_sort_key(value)
            if _month_sort_key(self._start) < value_key < _month_sort_key(self._end):
                return "range"
        return ""

    def year_state(self, year):
        year_start = f"{year}.01"
        year_end = f"{year}.12"
        if self._start and self.year_from_month(self._start) == year:
            return "selected"
        if self._end and self.year_from_month(self._end) == year:
            return "selected"
        if self._start and self._end:
            if _month_sort_key(self._start) < _month_sort_key(year_start):
                if _month_sort_key(year_end) < _month_sort_key(self._end):
                    return "range"
        return ""

    def month_value(self, month):
        return f"{self.year}.{month:02d}"

    def year_grid_start(self, year):
        return max(self.min_year, year - ((year - self.min_year) % self.YEAR_PAGE_SIZE))

    def year_from_month(self, value):
        return int(value.split(".")[0])

    def refresh_style(self, button):
        button.style().unpolish(button)
        button.style().polish(button)


class MonthRangePicker(QLineEdit):
    """只读的年月范围输入框，点击后弹出选择面板。"""

    rangeChanged = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._start = None
        self._end = None
        self.setObjectName("monthRangePicker")
        self.setReadOnly(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setPlaceholderText("选择出生年月范围")
        self.setToolTip("点击选择出生年月范围")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.open_picker()
            event.accept()
            return
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.open_picker()
            event.accept()
            return
        if event.key() in (Qt.Key_Backspace, Qt.Key_Delete):
            self.clear()
            event.accept()
            return
        super().keyPressEvent(event)

    def open_picker(self):
        dialog = MonthRangeDialog(self, self._start, self._end)
        if dialog.exec_() == QDialog.Accepted:
            self.set_range(*dialog.selected_range())

    def set_range(self, start, end):
        start = self.normalize_month(start)
        end = self.normalize_month(end)
        if self._start == start and self._end == end:
            return
        self._start = start
        self._end = end
        self.update_display()
        self.rangeChanged.emit()

    def get_range(self):
        return self._start, self._end

    def clear(self):
        self.set_range(None, None)

    def update_display(self):
        if self._start and self._end:
            self.setText(f"{self.format_month(self._start)} 至 {self.format_month(self._end)}")
        elif self._start:
            self.setText(f"从 {self.format_month(self._start)}")
        elif self._end:
            self.setText(f"至 {self.format_month(self._end)}")
        else:
            QLineEdit.clear(self)

    def normalize_month(self, value):
        if not value:
            return None
        value = str(value).replace("-", ".")
        match = re.match(r"^\d{4}\.(0[1-9]|1[0-2])$", value)
        return value if match else None

    def format_month(self, value):
        return value.replace(".", "-")


# 职级对话框类
class GradeSelectionDialog(QDialog):
    def __init__(self, parent=None, selected_grades=None):
        super().__init__(parent)
        self.setWindowTitle("选择职级/等级")
        self.setMinimumSize(400, 500)
        self.initial_grades = set(selected_grades or [])
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        self.setStyleSheet(DIALOG_BASE_STYLE + DIALOG_BUTTON_STYLE)

        # 滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        scroll_layout = QVBoxLayout(content)

        # 添加"全部"选项
        self.all_check = QCheckBox("全部")
        scroll_layout.addWidget(self.all_check)

        self.grade_checks = []

        # 添加复选框
        for grade in GRADE_OPTIONS:
            check = QCheckBox(grade)
            check.setChecked(grade in self.initial_grades)
            check.stateChanged.connect(self.on_grade_selected)
            self.grade_checks.append(check)
            scroll_layout.addWidget(check)

        if self.grade_checks and all(check.isChecked() for check in self.grade_checks):
            self.all_check.setChecked(True)
        self.all_check.stateChanged.connect(self.on_all_selected)

        scroll.setWidget(content)
        layout.addWidget(scroll)

        # 按钮
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        ok_button = button_box.button(QDialogButtonBox.Ok)
        cancel_button = button_box.button(QDialogButtonBox.Cancel)
        if ok_button is not None:
            ok_button.setObjectName("primaryButton")
        if cancel_button is not None:
            cancel_button.setObjectName("secondaryButton")
        layout.addWidget(button_box)

        self.setLayout(layout)

    def on_all_selected(self, state):
        """当'全部'被选中/取消时，更新所有职级选项"""
        # 暂时断开信号连接，避免递归
        for check in self.grade_checks:
            check.stateChanged.disconnect(self.on_grade_selected)

        # 设置所有职级选项的状态
        for check in self.grade_checks:
            check.setChecked(state == Qt.Checked)

        # 重新连接信号
        for check in self.grade_checks:
            check.stateChanged.connect(self.on_grade_selected)

    def on_grade_selected(self):
        """当单个职级被选择时，更新'全部'状态"""
        # 检查是否所有职级都被选中
        all_selected = all(check.isChecked() for check in self.grade_checks)

        # 暂时断开信号连接，避免递归
        self.all_check.stateChanged.disconnect(self.on_all_selected)
        self.all_check.setChecked(all_selected)
        self.all_check.stateChanged.connect(self.on_all_selected)

    def selected_grades(self):
        """返回选中的职级列表"""
        if self.all_check.isChecked():
            # 如果选中了"全部"，返回所有职级
            return [check.text() for check in self.grade_checks]
        else:
            # 否则返回选中的职级
            return [check.text() for check in self.grade_checks if check.isChecked()]


class QueryTab(QWidget):
    def __init__(self, db: Database, permissions: dict):
        """查询标签页初始化

        参数:
        - db: Database实例
        - permissions: 用户权限字典
        """
        super().__init__()
        self.db = db
        self.permissions = permissions
        self.ai_dialog = None  # 【新增】初始化 AI 对话框引用
        self.current_results = []  # 保存当前基础信息查询结果
        self.current_results_dict = {}  # 保存完整查询结果
        self.current_table_name = 'base_info'
        self._query_state = {}
        self._restoring_query_state = False
        self.page_size = 50
        self.current_page = 1
        self.result_model = None

        self.setup_ui()
        self.bind_query_state_events()
        self.save_query_state()
        logger.info("查询标签页已初始化")
        logger.info(
            f"用户权限: base_info={self.permissions['base_info']}, rewards={self.permissions['rewards']}, family={self.permissions['family']}, resume={self.permissions['resume']}")

    def setup_ui(self):
        """设置用户界面 - 优化版"""
        self.setObjectName("queryPage")
        self.setStyleSheet(PAGE_BACKGROUND_STYLE)

        main_layout = QVBoxLayout()
        main_layout.setSpacing(16)
        main_layout.setContentsMargins(16, 16, 16, 16)

        # 条件区 - 三列顶部标签表单
        condition_group, condition_layout = self.create_card()
        grid_layout = QGridLayout()
        grid_layout.setHorizontalSpacing(18)
        grid_layout.setVerticalSpacing(12)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        for column in range(3):
            grid_layout.setColumnStretch(column, 1)

        def apply_field_metrics(widget):
            widget.setMinimumHeight(34)
            widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            return widget

        def create_form_item(label_text, control):
            container = QWidget()
            layout = QVBoxLayout(container)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(5)
            label = QLabel(label_text)
            label.setObjectName("queryFormLabel")
            layout.addWidget(label)
            layout.addWidget(control)
            return container

        def add_form_item(row, column, label_text, control):
            grid_layout.addWidget(create_form_item(label_text, control), row, column)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("输入姓名")
        apply_field_metrics(self.name_input)

        self.birth_range_picker = MonthRangePicker()
        apply_field_metrics(self.birth_range_picker)

        self.position_combo = QComboBox()
        self.position_combo.addItem("不限", "")
        for level in POSITION_LEVELS:
            self.position_combo.addItem(level, level)
        apply_field_metrics(self.position_combo)

        grade_widget = QWidget()
        grade_layout = QHBoxLayout(grade_widget)
        grade_layout.setContentsMargins(0, 0, 0, 0)
        grade_layout.setSpacing(8)
        self.grade_display = QLineEdit()
        self.grade_display.setReadOnly(True)
        self.grade_display.setPlaceholderText("点击选择")
        apply_field_metrics(self.grade_display)
        self.select_grades_btn = QPushButton("选择...")
        self.select_grades_btn.setFixedWidth(84)
        self.select_grades_btn.setMinimumHeight(34)
        self.select_grades_btn.setStyleSheet(button_style("secondary"))
        self.select_grades_btn.clicked.connect(self.select_grades)
        grade_layout.addWidget(self.grade_display, 1)
        grade_layout.addWidget(self.select_grades_btn)
        grade_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.education_combo = QComboBox()
        self.education_combo.addItem("不限", "")
        for level in EDUCATION_LEVELS:
            self.education_combo.addItem(level, level)
        apply_field_metrics(self.education_combo)

        self.parttime_combo = QComboBox()
        self.parttime_combo.addItem("不限", "")
        for level in EDUCATION_LEVELS:
            self.parttime_combo.addItem(level, level)
        apply_field_metrics(self.parttime_combo)

        add_form_item(0, 0, "姓名", self.name_input)
        add_form_item(0, 1, "出生年月范围", self.birth_range_picker)
        add_form_item(0, 2, "现任职务", self.position_combo)
        add_form_item(1, 0, "职级/等级", grade_widget)
        add_form_item(1, 1, "全日制学历学位", self.education_combo)
        add_form_item(1, 2, "在职学历学位", self.parttime_combo)

        # ======== 按钮行 ========
        button_layout = QHBoxLayout()
        button_layout.setSpacing(15)
        button_layout.setContentsMargins(0, 8, 0, 0)

        # 使用更美观的按钮样式
        self.query_btn = QPushButton("查询")
        self.query_btn.setFixedWidth(100)
        self.query_btn.setStyleSheet(button_style("primary"))
        self.query_btn.clicked.connect(self.execute_query)

        self.clear_btn = QPushButton("清空条件")
        self.clear_btn.setFixedWidth(100)
        self.clear_btn.setStyleSheet(button_style("secondary"))
        self.clear_btn.clicked.connect(self.clear_conditions)

        self.view_all_btn = QPushButton("查看全部")
        self.view_all_btn.setFixedWidth(100)
        self.view_all_btn.setStyleSheet(button_style("info"))
        self.view_all_btn.clicked.connect(self.view_all_data)

        # ======== 【新增】AI 分析按钮开始 ========
        self.ai_btn = QPushButton("AI 智能分析")
        self.ai_btn.setFixedWidth(120)  # 稍微宽一点
        self.ai_btn.setStyleSheet(button_style("accent"))
        # 绑定点击事件 (open_ai_chat 方法需要你在后面定义)
        self.ai_btn.clicked.connect(self.open_ai_chat)
        # ======== 【新增】AI 分析按钮结束 ========

        button_layout.addStretch()
        button_layout.addWidget(self.query_btn)
        button_layout.addWidget(self.clear_btn)
        button_layout.addWidget(self.view_all_btn)
        # ======== 【新增】把 AI 按钮加进布局 ========
        button_layout.addWidget(self.ai_btn)
        # ==========================================
        button_layout.addStretch()

        grid_layout.addLayout(button_layout, 2, 0, 1, 3)

        condition_layout.addLayout(grid_layout)
        main_layout.addWidget(condition_group)

        # 结果区域
        result_group, result_layout = self.create_card()

        # 查看按钮
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 0, 0, 0)
        self.table_buttons = {}

        # 根据统一表配置生成查看按钮
        for table, label in TABLE_LABELS.items():
            btn = QPushButton(label)
            self.table_buttons[table] = btn
            setattr(self, f"{table}_btn", btn)
            btn.setMinimumHeight(40)
            btn.setFont(QFont("Microsoft YaHei", 10))
            if self.permissions.get(table, False):
                btn.setEnabled(True)
                btn.setStyleSheet(button_style("table_enabled"))
            else:
                btn.setEnabled(False)
                btn.setStyleSheet(button_style("table_disabled"))
                btn.setToolTip("您没有此表格的查看权限")
            btn.clicked.connect(lambda _, t=table: self.show_table_data(t))
            button_layout.addWidget(btn)
        result_layout.addLayout(button_layout)

        # 结果表
        self.result_model = ResultTableModel(self)
        self.result_table = QTableView()
        self.result_table.setModel(self.result_model)
        self.result_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        # 禁用排序功能，防止数据错乱
        self.result_table.setSortingEnabled(False)
        # 单击后选中整行，避免鼠标经过时频繁改变高亮行
        self.result_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.result_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.result_table.setStyleSheet(RESULT_TABLE_STYLE)
        self.result_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        result_layout.addWidget(self.result_table)

        pagination_layout = QHBoxLayout()
        pagination_layout.setContentsMargins(0, 6, 0, 0)
        pagination_layout.setSpacing(8)

        self.pagination_summary_label = QLabel("共 0 条")
        self.pagination_summary_label.setStyleSheet("color: #57606a;")

        self.prev_page_btn = QPushButton("<")
        self.prev_page_btn.setObjectName("pageNavButton")
        self.prev_page_btn.setToolTip("上一页")
        self.prev_page_btn.setStyleSheet(PAGINATION_BUTTON_STYLE)
        self.prev_page_btn.clicked.connect(self.previous_page)

        self.page_buttons_layout = QHBoxLayout()
        self.page_buttons_layout.setContentsMargins(0, 0, 0, 0)
        self.page_buttons_layout.setSpacing(6)

        self.next_page_btn = QPushButton(">")
        self.next_page_btn.setObjectName("pageNavButton")
        self.next_page_btn.setToolTip("下一页")
        self.next_page_btn.setStyleSheet(PAGINATION_BUTTON_STYLE)
        self.next_page_btn.clicked.connect(self.next_page)

        pagination_layout.addStretch()
        pagination_layout.addWidget(self.pagination_summary_label)
        pagination_layout.addWidget(self.prev_page_btn)
        pagination_layout.addLayout(self.page_buttons_layout)
        pagination_layout.addWidget(self.next_page_btn)
        pagination_layout.addStretch()
        result_layout.addLayout(pagination_layout)
        self.update_pagination_controls(0, 0)

        result_group.setLayout(result_layout)
        main_layout.addWidget(result_group)
        self.setLayout(main_layout)

    def create_card(self):
        """Create a borderless white card section."""
        card = QFrame()
        card.setObjectName("sectionCard")
        card.setStyleSheet(CARD_STYLE + QUERY_FORM_CONTROL_STYLE)
        self.apply_card_shadow(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        return card, layout

    def apply_card_shadow(self, widget: QWidget):
        shadow = QGraphicsDropShadowEffect(widget)
        shadow.setBlurRadius(14)
        shadow.setOffset(0, 2)
        shadow.setColor(QColor(0, 0, 0, 28))
        widget.setGraphicsEffect(shadow)

    def query_state_widgets(self):
        """返回需要保留输入状态的查询控件。"""
        return [
            self.name_input,
            self.grade_display,
            self.position_combo,
            self.birth_range_picker,
            self.education_combo,
            self.parttime_combo,
        ]

    def bind_query_state_events(self):
        """让查询条件变化时自动写入内存状态。"""
        for widget in self.query_state_widgets():
            if isinstance(widget, MonthRangePicker):
                widget.rangeChanged.connect(self.save_query_state)
            elif isinstance(widget, QLineEdit):
                widget.textChanged.connect(self.save_query_state)
            elif isinstance(widget, QComboBox):
                widget.currentIndexChanged.connect(self.save_query_state)

    def get_query_state(self) -> dict:
        """读取当前查询条件输入状态。"""
        birth_start, birth_end = self.birth_range_picker.get_range()
        return {
            "name": self.name_input.text(),
            "grades": self.grade_display.text(),
            "position": self.position_combo.currentData() or "",
            "birth_start": birth_start,
            "birth_end": birth_end,
            "education": self.education_combo.currentData() or "",
            "parttime_education": self.parttime_combo.currentData() or "",
        }

    def save_query_state(self, *_):
        """保存查询条件，供切换选项卡后恢复。"""
        if self._restoring_query_state:
            return
        self._query_state = self.get_query_state()

    def set_combo_by_data(self, combo: QComboBox, value):
        index = combo.findData(value)
        combo.setCurrentIndex(index if index >= 0 else 0)

    def restore_query_state(self):
        """恢复最近一次保存的查询条件。"""
        if not self._query_state:
            return

        self._restoring_query_state = True
        blockers = [QSignalBlocker(widget) for widget in self.query_state_widgets()]
        try:
            self.name_input.setText(self._query_state.get("name", ""))
            self.grade_display.setText(self._query_state.get("grades", ""))
            self.set_combo_by_data(self.position_combo, self._query_state.get("position", ""))
            self.birth_range_picker.set_range(
                self._query_state.get("birth_start"),
                self._query_state.get("birth_end"),
            )
            self.set_combo_by_data(self.education_combo, self._query_state.get("education", ""))
            self.set_combo_by_data(self.parttime_combo, self._query_state.get("parttime_education", ""))
        finally:
            del blockers
            self._restoring_query_state = False
        self.save_query_state()

    def hideEvent(self, event):
        self.save_query_state()
        super().hideEvent(event)

    def showEvent(self, event):
        self.restore_query_state()
        super().showEvent(event)

    def get_education_keywords(self, level: str) -> list:
        """将界面选项映射到数据库关键词"""
        return EDUCATION_KEYWORDS.get(level, [])

    def select_grades(self):
        """弹出职级选择对话框"""
        dlg = GradeSelectionDialog(self, self.get_selected_grades())
        if dlg.exec_() == QDialog.Accepted:
            selected = dlg.selected_grades()
            if selected:
                self.grade_display.setText(", ".join(selected))
            else:
                self.grade_display.clear()
            self.save_query_state()

    def clear_conditions(self):
        """清空查询条件"""
        # 清空姓名输入
        self.name_input.clear()

        # 清空职级选择
        self.grade_display.clear()

        # 清空现任职务输入
        self.position_combo.setCurrentIndex(0)

        # 清空出生年月范围
        self.birth_range_picker.clear()

        # 重置学历下拉框
        self.education_combo.setCurrentIndex(0)
        self.parttime_combo.setCurrentIndex(0)
        self.save_query_state()

    def update_table_buttons(self, has_results: bool):
        """按查询结果和权限刷新表切换按钮状态。"""
        for table_name, button in self.table_buttons.items():
            button.setEnabled(has_results and self.permissions.get(table_name, False))

    def get_selected_position(self):
        """获取现任职务查询条件。"""
        selected_level = self.position_combo.currentData()
        if not selected_level:
            return None

        group_levels = POSITION_GROUPS.get(selected_level)
        if group_levels:
            position = []
            for level in group_levels:
                position.extend(POSITION_MAPPING.get(level, []))
            return position

        return POSITION_MAPPING.get(selected_level, [])

    def get_selected_grades(self):
        """获取职级/等级查询条件。"""
        grade_text = self.grade_display.text().strip()
        if not grade_text:
            return []
        return [grade.strip() for grade in grade_text.split(",") if grade.strip()]

    def get_birth_range(self):
        """获取出生年月范围条件，格式为 yyyy.MM。"""
        return self.birth_range_picker.get_range()

    def collect_query_conditions(self):
        """收集界面上的所有查询条件。"""
        birth_start, birth_end = self.get_birth_range()
        education_keywords = []
        parttime_keywords = []

        if self.education_combo.currentData():
            education_keywords = self.get_education_keywords(self.education_combo.currentData())

        if self.parttime_combo.currentData():
            parttime_keywords = self.get_education_keywords(self.parttime_combo.currentData())

        return {
            "name": self.name_input.text().strip() or None,
            "grades": self.get_selected_grades() or None,
            "position": self.get_selected_position(),
            "birth_start": birth_start,
            "birth_end": birth_end,
            "education": education_keywords,
            "parttime_education": parttime_keywords,
        }

    def refresh_query_results(self, results_dict):
        """刷新当前查询结果和表格显示。"""
        self.current_results_dict = results_dict
        self.current_results = results_dict.get('base_info', [])
        self.current_table_name = 'base_info'
        self.current_page = 1
        self.display_current_page()
        self.update_table_buttons(len(self.current_results) > 0)

    def clear_results(self):
        """清空当前查询缓存和结果表格。"""
        self.current_results_dict = {}
        self.current_results = []
        self.current_table_name = 'base_info'
        self.current_page = 1
        self.result_model.clear()
        self.update_pagination_controls(0, 0)
        self.update_table_buttons(False)

        if self.ai_dialog is not None:
            self.ai_dialog.close()
            self.ai_dialog = None

    def show_status_message(self, message: str, timeout: int = 6000):
        """在主窗口状态栏显示查询反馈。"""
        main_window = self.window()
        status_bar = getattr(main_window, 'status_bar', None)
        if status_bar is not None:
            status_bar.showMessage(message, timeout)
        else:
            logger.info(message)

    def view_all_data(self):
        """查看全部数据"""
        try:
            # 直接查询所有数据，不使用任何条件
            results_dict = self.db.search_personnel()
            self.refresh_query_results(results_dict)

            self.show_status_message(f"查看全部完成：共找到 {len(self.current_results)} 条基础信息记录")
        except Exception as e:
            logger.error(f"查看全部数据失败: {e}")
            QMessageBox.critical(self, "查询错误", f"查看全部数据时发生错误: {e}")

    def execute_query(self):
        """执行数据库查询操作"""
        try:
            results_dict = self.db.search_personnel(**self.collect_query_conditions())
            self.refresh_query_results(results_dict)

            self.show_status_message(f"查询完成：找到 {len(self.current_results)} 条基础信息记录")

        except Exception as e:
            logger.error(f"查询执行失败: {e}")
            QMessageBox.critical(self, "查询错误", f"执行查询时发生错误: {e}")

    def get_full_field_mapping(self, table_name: str) -> dict:
        """
        获取指定表的所有字段映射（数据库字段名 -> 中文表头名）
        用于确保 AI 能读取到所有列，且能理解列的含义
        """
        assessment_years = self.db.get_assessment_years() or []
        return get_table_field_labels(table_name, assessment_years)

    def open_ai_chat(self):
        """
        启动 AI 分析对话框。
        """
        try:
            assessment_years = self.db.get_assessment_years() or []
            analysis_payload = build_ai_analysis_payload(
                self.current_results_dict,
                self.permissions,
                assessment_years,
            )

            if not analysis_payload["schemas"]:
                QMessageBox.warning(self, "提示", "当前用户没有可用于 AI 分析的数据表权限。")
                return

            if not has_analysis_rows(analysis_payload):
                QMessageBox.warning(self, "提示", "请先查询或查看全部后再使用 AI 分析。")
                return

            try:
                status = ensure_ollama_ready(start_if_needed=False)
                if status.service_available:
                    self.open_ai_dialog(analysis_payload)
                else:
                    self.start_ollama_then_open_ai(analysis_payload)

            except Exception as e:
                logger.exception("AI Dialog Error")
                QMessageBox.critical(self, "组件错误", f"无法打开 AI 窗口：\n{e}")

        except Exception as e:
            logger.exception("AI Logic Error")
            QMessageBox.critical(self, "错误", f"AI分析准备阶段出错：\n{str(e)}")

    def start_ollama_then_open_ai(self, analysis_payload):
        """启动专用 Ollama 服务，完成后再打开 AI 分析窗口。"""
        main_window = self.window()

        def task():
            return ensure_ollama_ready(start_if_needed=True)

        def on_success(status):
            self.handle_ollama_started_for_ai(status, analysis_payload)

        def on_error(message):
            QMessageBox.critical(self, "Ollama 启动失败", message)

        if hasattr(main_window, "run_background_task"):
            from ui.loading_dialog import ModernLoadingDialog

            def progress_dialog_factory(parent, _title):
                return ModernLoadingDialog(
                    parent,
                    title="正在启动 Ollama",
                    message="正在连接本地 AI 服务，请稍候...",
                )

            main_window.run_background_task(
                "正在启动 Ollama，请稍候...",
                task,
                on_success=on_success,
                on_error=on_error,
                progress_dialog_factory=progress_dialog_factory,
            )
            return

        on_success(task())

    def handle_ollama_started_for_ai(self, status, analysis_payload):
        """根据 Ollama 启动结果打开 AI 分析窗口或提示错误。"""
        if getattr(status, "service_available", False):
            self.open_ai_dialog(analysis_payload)
            return

        message = getattr(status, "message", "Ollama 未能启动或连接。")
        QMessageBox.warning(self, "Ollama 启动提示", message)

    def open_ai_dialog(self, analysis_payload):
        """创建并显示 AI 分析窗口。"""
        if hasattr(self, 'ai_dialog') and self.ai_dialog is not None:
            self.ai_dialog.close()

        from ui.ai_chat import AIChatDialog
        self.ai_dialog = AIChatDialog(analysis_payload, self)
        self.ai_dialog.setWindowTitle("智能分析 - 查询结果")
        self.ai_dialog.show()

    def show_table_data(self, table_name: str):
        """显示指定表的数据"""
        # 检查用户是否有权限查看此表
        if not self.permissions.get(table_name, False):
            QMessageBox.warning(self, "权限不足", "您没有查看此表格的权限")
            return

        self.current_table_name = table_name
        self.current_page = 1
        self.display_current_page()

    def get_table_name(self, table_name: str) -> str:
        """获取表的中文名称"""
        return get_table_label(table_name)

    def get_table_columns(self, table_name: str):
        """获取当前表的字段和表头。"""
        assessment_years = self.db.get_assessment_years() or []
        items = get_table_field_items(table_name, assessment_years)
        fields = [field_name for field_name, _ in items]
        headers = [label for _, label in items]
        return fields, headers

    def apply_table_view_layout(self, table_name: str):
        """按表类型设置列宽和换行策略。"""
        header = self.result_table.horizontalHeader()
        if table_name != 'resume':
            self.result_table.setWordWrap(True)
            self.result_table.setTextElideMode(Qt.ElideNone)
            header.setSectionResizeMode(QHeaderView.ResizeToContents)
            return

        self.result_table.setWordWrap(True)
        self.result_table.setTextElideMode(Qt.ElideNone)
        if self.result_model.columnCount() >= 1:
            header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        if self.result_model.columnCount() >= 2:
            header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
            header.setMinimumSectionSize(80)
        if self.result_model.columnCount() >= 3:
            header.setSectionResizeMode(2, QHeaderView.Stretch)

    def display_current_page(self):
        """显示当前表当前页数据。"""
        data = self.current_results_dict.get(self.current_table_name, [])
        total_rows = len(data)
        total_pages = self.get_total_pages(total_rows)

        if total_rows == 0:
            self.current_page = 1
            fields, headers = self.get_table_columns(self.current_table_name)
            self.result_model.set_data([], self.current_table_name, fields, headers, 0)
            self.apply_table_view_layout(self.current_table_name)
            self.update_pagination_controls(total_rows, total_pages)
            return

        self.current_page = max(1, min(self.current_page, total_pages))
        start_index = (self.current_page - 1) * self.page_size
        end_index = start_index + self.page_size
        fields, headers = self.get_table_columns(self.current_table_name)
        self.result_model.set_data(
            data[start_index:end_index],
            self.current_table_name,
            fields,
            headers,
            start_index,
        )
        self.apply_table_view_layout(self.current_table_name)
        self.result_table.resizeRowsToContents()
        self.result_table.scrollToTop()
        self.update_pagination_controls(total_rows, total_pages)

    def get_total_pages(self, total_rows: int) -> int:
        if total_rows <= 0:
            return 0
        return (total_rows + self.page_size - 1) // self.page_size

    def get_visible_page_items(self, total_pages: int):
        if total_pages <= 7:
            return list(range(1, total_pages + 1))

        if self.current_page <= 4:
            return [1, 2, 3, 4, 5, "...", total_pages]

        if self.current_page >= total_pages - 3:
            return [1, "..."] + list(range(total_pages - 4, total_pages + 1))

        return [
            1,
            "...",
            self.current_page - 1,
            self.current_page,
            self.current_page + 1,
            "...",
            total_pages,
        ]

    def clear_page_buttons(self):
        while self.page_buttons_layout.count():
            item = self.page_buttons_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def create_page_button(self, page_item):
        if page_item == "...":
            button = QPushButton("...")
            button.setObjectName("pageEllipsis")
            button.setEnabled(False)
            button.setStyleSheet(PAGINATION_BUTTON_STYLE)
            return button

        button = QPushButton(str(page_item))
        button.setObjectName("pageNumberButton")
        button.setProperty("active", "true" if page_item == self.current_page else "false")
        button.setToolTip(f"第 {page_item} 页")
        button.setStyleSheet(PAGINATION_BUTTON_STYLE)
        button.clicked.connect(lambda _, page=page_item: self.go_to_page(page))
        return button

    def refresh_page_buttons(self, total_pages: int):
        self.clear_page_buttons()
        for page_item in self.get_visible_page_items(total_pages):
            self.page_buttons_layout.addWidget(self.create_page_button(page_item))

    def update_pagination_controls(self, total_rows: int, total_pages: int):
        if total_pages == 0:
            self.pagination_summary_label.setText("共 0 条")
            self.prev_page_btn.setEnabled(False)
            self.next_page_btn.setEnabled(False)
            self.clear_page_buttons()
            return

        self.current_page = max(1, min(self.current_page, total_pages))
        self.pagination_summary_label.setText(f"共 {total_rows} 条，每页 {self.page_size} 条")
        self.prev_page_btn.setEnabled(self.current_page > 1)
        self.next_page_btn.setEnabled(self.current_page < total_pages)
        self.refresh_page_buttons(total_pages)

    def previous_page(self):
        self.go_to_page(self.current_page - 1)

    def next_page(self):
        self.go_to_page(self.current_page + 1)

    def go_to_page(self, page: int):
        total_rows = len(self.current_results_dict.get(self.current_table_name, []))
        total_pages = self.get_total_pages(total_rows)
        if total_pages == 0:
            return
        target_page = max(1, min(page, total_pages))
        if target_page == self.current_page:
            return
        self.current_page = target_page
        self.display_current_page()
