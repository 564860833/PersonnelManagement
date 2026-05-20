import re
import logging

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QTableView,
    QComboBox, QGroupBox,
    QMessageBox, QHeaderView, QDialog,
    QVBoxLayout, QCheckBox, QDialogButtonBox,
    QScrollArea, QAbstractItemView, QGridLayout
)
from PyQt5.QtCore import Qt, QSignalBlocker
from PyQt5.QtGui import QFont, QIntValidator
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
    ANALYSIS_FIELD_LABEL_STYLE,
    COMPACT_BUTTON_STYLE,
    RESULT_TABLE_STYLE,
    button_style,
)
from ui.table_model import ResultTableModel

logger = logging.getLogger('QueryTab')


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


class ColumnSelectionDialog(QDialog):
    """用于选择要发送给 AI 分析的列的对话框"""

    def __init__(self, columns, parent=None):
        super().__init__(parent)
        self.setWindowTitle("选择分析字段")
        self.setMinimumSize(300, 450)
        self.columns = columns
        self.checkboxes = []
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()

        # 提示标签
        label = QLabel("请选择需要让 AI 分析的数据列（默认全选）：")
        label.setStyleSheet(ANALYSIS_FIELD_LABEL_STYLE)
        layout.addWidget(label)

        # 滚动区域 (防止列太多超出屏幕)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        scroll_layout = QVBoxLayout(content)

        # 全选/全不选按钮
        btn_layout = QHBoxLayout()
        select_all_btn = QPushButton("全选")
        deselect_all_btn = QPushButton("全不选")
        select_all_btn.clicked.connect(self.select_all)
        deselect_all_btn.clicked.connect(self.deselect_all)
        btn_layout.addWidget(select_all_btn)
        btn_layout.addWidget(deselect_all_btn)
        scroll_layout.addLayout(btn_layout)

        # 添加列复选框
        for col in self.columns:
            cb = QCheckBox(col)
            cb.setChecked(True)  # 默认全部选中
            self.checkboxes.append(cb)
            scroll_layout.addWidget(cb)

        scroll_layout.addStretch()  # 将复选框顶上去

        scroll.setWidget(content)
        layout.addWidget(scroll)

        # 底部确定/取消按钮
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.setLayout(layout)

    def select_all(self):
        for cb in self.checkboxes:
            cb.setChecked(True)

    def deselect_all(self):
        for cb in self.checkboxes:
            cb.setChecked(False)

    def get_selected_columns(self):
        """返回被选中的中文列名列表"""
        return [cb.text() for cb in self.checkboxes if cb.isChecked()]


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
        main_layout = QVBoxLayout()
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(12, 12, 12, 12)

        # 查询条件组 - 使用更美观的网格布局
        condition_group = QGroupBox("查询条件")
        grid_layout = QGridLayout()
        grid_layout.setHorizontalSpacing(10)
        grid_layout.setVerticalSpacing(8)
        grid_layout.setContentsMargins(10, 12, 10, 10)  # 增加内边距

        # 添加一个空列作为左侧控件和右侧控件的分隔
        grid_layout.setColumnMinimumWidth(2, 16)  # 设置第2列为分隔列

        # ======== 第一行：姓名 + 出生年月 ========
        row = 0

        # 姓名 - 左对齐
        grid_layout.addWidget(QLabel("姓名:"), row, 0, Qt.AlignRight)
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("输入姓名")
        self.name_input.setMinimumWidth(130)
        grid_layout.addWidget(self.name_input, row, 1)  # 不再跨列

        # 添加分隔标签
        grid_layout.addWidget(QLabel(""), row, 2)  # 空标签作为分隔

        # 出生年月标签 - 右对齐（向右移动到第3列）
        grid_layout.addWidget(QLabel("出生年月范围:"), row, 3, Qt.AlignRight)

        # 起始年月（向右移动到第4列）
        birth_start_layout = QHBoxLayout()
        birth_start_layout.setSpacing(4)
        birth_start_layout.addWidget(QLabel("从"))
        self.birth_start_year = QLineEdit()
        self.birth_start_year.setPlaceholderText("年份")
        self.birth_start_year.setValidator(QIntValidator(1900, 2100, self))
        self.birth_start_year.setFixedWidth(86)
        self.birth_start_month = QComboBox()
        self.birth_start_month.addItem("不限")
        self.birth_start_month.addItems([f"{month:02d}" for month in range(1, 13)])
        self.birth_start_month.setFixedWidth(72)
        birth_start_layout.addWidget(self.birth_start_year)
        birth_start_layout.addWidget(QLabel("年"))
        birth_start_layout.addWidget(self.birth_start_month)
        birth_start_layout.addWidget(QLabel("月"))
        grid_layout.addLayout(birth_start_layout, row, 4)

        # 结束年月（向右移动到第5列）
        birth_end_layout = QHBoxLayout()
        birth_end_layout.setSpacing(4)
        birth_end_layout.addWidget(QLabel("至"))
        self.birth_end_year = QLineEdit()
        self.birth_end_year.setPlaceholderText("年份")
        self.birth_end_year.setValidator(QIntValidator(1900, 2100, self))
        self.birth_end_year.setFixedWidth(86)
        self.birth_end_month = QComboBox()
        self.birth_end_month.addItem("不限")
        self.birth_end_month.addItems([f"{month:02d}" for month in range(1, 13)])
        self.birth_end_month.setFixedWidth(72)
        birth_end_layout.addWidget(self.birth_end_year)
        birth_end_layout.addWidget(QLabel("年"))
        birth_end_layout.addWidget(self.birth_end_month)
        birth_end_layout.addWidget(QLabel("月"))
        grid_layout.addLayout(birth_end_layout, row, 5)

        # ======== 第二行：现任职务 + 职级/等级 ========
        row += 1

        # 现任职务 - 左对齐
        grid_layout.addWidget(QLabel("现任职务:"), row, 0, Qt.AlignRight)
        self.position_combo = QComboBox()
        self.position_combo.addItem("不限", "")
        for level in POSITION_LEVELS:
            self.position_combo.addItem(level, level)
        self.position_combo.setMinimumWidth(110)
        grid_layout.addWidget(self.position_combo, row, 1)

        # 分隔列
        grid_layout.addWidget(QLabel(""), row, 2)  # 空标签作为分隔

        # 职级/等级 - 右对齐（向右移动到第3列）
        grid_layout.addWidget(QLabel("职级/等级:"), row, 3, Qt.AlignRight)
        self.grade_display = QLineEdit()
        self.grade_display.setReadOnly(True)
        self.grade_display.setPlaceholderText("点击选择")
        self.grade_display.setMinimumWidth(140)
        grid_layout.addWidget(self.grade_display, row, 4)  # 移动到第4列

        self.select_grades_btn = QPushButton("选择...")
        self.select_grades_btn.setFixedWidth(80)
        self.select_grades_btn.setStyleSheet(COMPACT_BUTTON_STYLE)
        self.select_grades_btn.clicked.connect(self.select_grades)
        grid_layout.addWidget(self.select_grades_btn, row, 5)  # 移动到第5列

        # ======== 第三行：学历学位 ========
        row += 1

        # 全日制学历学位 - 左对齐
        grid_layout.addWidget(QLabel("全日制学历学位:"), row, 0, Qt.AlignRight)
        self.education_combo = QComboBox()
        self.education_combo.addItem("不限", "")
        for level in EDUCATION_LEVELS:
            self.education_combo.addItem(level, level)
        self.education_combo.setMinimumWidth(110)
        grid_layout.addWidget(self.education_combo, row, 1)

        # 分隔列
        grid_layout.addWidget(QLabel(""), row, 2)  # 空标签作为分隔

        # 在职学历学位 - 右对齐（向右移动到第3列）
        grid_layout.addWidget(QLabel("在职学历学位:"), row, 3, Qt.AlignRight)
        self.parttime_combo = QComboBox()
        self.parttime_combo.addItem("不限", "")
        for level in EDUCATION_LEVELS:
            self.parttime_combo.addItem(level, level)
        self.parttime_combo.setMinimumWidth(110)
        grid_layout.addWidget(self.parttime_combo, row, 4)  # 移动到第4列

        # ======== 第四行：按钮 ========
        row += 1
        button_layout = QHBoxLayout()
        button_layout.setSpacing(15)

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

        # 按钮行跨所有列（从第0列到第5列）
        grid_layout.addLayout(button_layout, row, 0, 1, 6)

        condition_group.setLayout(grid_layout)
        main_layout.addWidget(condition_group)

        # 查询结果区域
        result_group = QGroupBox("查询结果")
        result_layout = QVBoxLayout()

        # 查看按钮
        button_layout = QHBoxLayout()
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
        # 禁用行选择功能
        self.result_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.result_table.setStyleSheet(RESULT_TABLE_STYLE)
        self.result_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        result_layout.addWidget(self.result_table)

        pagination_layout = QHBoxLayout()
        self.prev_page_btn = QPushButton("上一页")
        self.prev_page_btn.setFixedWidth(90)
        self.prev_page_btn.setStyleSheet(COMPACT_BUTTON_STYLE)
        self.prev_page_btn.clicked.connect(self.previous_page)
        self.page_info_label = QLabel("第 0 / 0 页，共 0 条")
        self.page_info_label.setAlignment(Qt.AlignCenter)
        self.next_page_btn = QPushButton("下一页")
        self.next_page_btn.setFixedWidth(90)
        self.next_page_btn.setStyleSheet(COMPACT_BUTTON_STYLE)
        self.next_page_btn.clicked.connect(self.next_page)

        pagination_layout.addStretch()
        pagination_layout.addWidget(self.prev_page_btn)
        pagination_layout.addWidget(self.page_info_label)
        pagination_layout.addWidget(self.next_page_btn)
        pagination_layout.addStretch()
        result_layout.addLayout(pagination_layout)
        self.update_pagination_controls(0, 0)

        result_group.setLayout(result_layout)
        main_layout.addWidget(result_group)
        self.setLayout(main_layout)

    def query_state_widgets(self):
        """返回需要保留输入状态的查询控件。"""
        return [
            self.name_input,
            self.grade_display,
            self.position_combo,
            self.birth_start_year,
            self.birth_start_month,
            self.birth_end_year,
            self.birth_end_month,
            self.education_combo,
            self.parttime_combo,
        ]

    def bind_query_state_events(self):
        """让查询条件变化时自动写入内存状态。"""
        for widget in self.query_state_widgets():
            if isinstance(widget, QLineEdit):
                widget.textChanged.connect(self.save_query_state)
            elif isinstance(widget, QComboBox):
                widget.currentIndexChanged.connect(self.save_query_state)

    def get_query_state(self) -> dict:
        """读取当前查询条件输入状态。"""
        return {
            "name": self.name_input.text(),
            "grades": self.grade_display.text(),
            "position": self.position_combo.currentData() or "",
            "birth_start_year": self.birth_start_year.text(),
            "birth_start_month": self.birth_start_month.currentText(),
            "birth_end_year": self.birth_end_year.text(),
            "birth_end_month": self.birth_end_month.currentText(),
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

    def set_combo_by_text(self, combo: QComboBox, text: str):
        index = combo.findText(text)
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
            self.birth_start_year.setText(self._query_state.get("birth_start_year", ""))
            self.set_combo_by_text(self.birth_start_month, self._query_state.get("birth_start_month", "不限"))
            self.birth_end_year.setText(self._query_state.get("birth_end_year", ""))
            self.set_combo_by_text(self.birth_end_month, self._query_state.get("birth_end_month", "不限"))
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

        # 清空年份输入框
        self.birth_start_year.clear()
        self.birth_end_year.clear()

        # 重置月份为空值
        self.birth_start_month.setCurrentIndex(0)  # 设置为空值
        self.birth_end_month.setCurrentIndex(0)  # 设置为空值

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
        birth_start = None
        birth_end = None

        start_year = self.birth_start_year.text().strip()
        start_month = self.birth_start_month.currentText().strip()
        if start_month == "不限":
            start_month = None

        if start_year and start_month:
            birth_start = f"{start_year}.{start_month}"
        elif start_year:
            birth_start = f"{start_year}.01"
            if not self.birth_end_year.text().strip():
                birth_end = f"{start_year}.12"

        end_year = self.birth_end_year.text().strip()
        end_month = self.birth_end_month.currentText().strip()
        if end_month == "不限":
            end_month = None

        if end_year and end_month:
            birth_end = f"{end_year}.{end_month}"
        elif end_year:
            birth_end = f"{end_year}.12"
            if not birth_start and not self.birth_start_year.text().strip():
                birth_start = f"{end_year}.01"

        return birth_start, birth_end

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
        启动 AI 分析对话框 (增加了列选择功能 + 性能优化版)
        """
        try:
            # 1. 获取当前筛选后的数据
            current_data = self.current_results_dict.get(self.current_table_name, [])
            if not current_data:
                QMessageBox.warning(self, "提示", f"当前【{self.get_table_name(self.current_table_name)}】没有数据。")
                return

            # 2. 获取该表的所有字段映射 (English Key -> Chinese Header)
            full_mapping = self.get_full_field_mapping(self.current_table_name)

            # 如果映射为空（异常情况），则直接使用数据库字段名
            if not full_mapping and current_data:
                full_mapping = {k: k for k in current_data[0].keys()}

            # ================== 【新增】弹出列选择对话框 ==================
            # 提取所有中文表头作为选项
            all_chinese_headers = list(full_mapping.values())

            # 实例化并显示对话框
            dialog = ColumnSelectionDialog(all_chinese_headers, self)
            if dialog.exec_() != QDialog.Accepted:
                return  # 用户点击了取消，直接退出

            selected_headers = dialog.get_selected_columns()
            if not selected_headers:
                QMessageBox.warning(self, "提示", "您必须至少选择一列才能进行分析。")
                return

            # 根据用户的选择过滤 mapping：只保留勾选了的字段
            filtered_mapping = {k: v for k, v in full_mapping.items() if v in selected_headers}
            # ==============================================================

            # 3. 构建 CSV 数据 (Token 密度最大化)
            csv_lines = []

            # 3.1 生成表头 (使用过滤后的 mapping)
            available_keys = []
            if current_data:
                sample_row = current_data[0]
                # 这里改为遍历 filtered_mapping
                for db_key in filtered_mapping.keys():
                    if db_key in sample_row:
                        available_keys.append(db_key)

            # 对应的中文表头列表
            headers = [filtered_mapping[k] for k in available_keys]
            csv_lines.append(",".join(headers))

            # 3.2 智能数据截断与格式化
            limit_rows = 100
            process_data = current_data[:limit_rows]

            for person in process_data:
                row_values = []
                for key in available_keys:
                    val = person.get(key)
                    # 处理空值
                    if val is None: val = ""
                    val = str(val).strip()

                    # 去除换行符和多余空格，替换英文逗号
                    val = re.sub(r'\s+', ' ', val)
                    val = val.replace(',', '，')

                    row_values.append(val)

                csv_lines.append(",".join(row_values))

            # 4. 组合最终文本
            context_str = "\n".join(csv_lines)
            total_count = len(current_data)

            note = ""
            if total_count > limit_rows:
                note = f"\n(注：当前表格共 {total_count} 人，为保证 AI 运行速度，仅截取前 {limit_rows} 人进行分析。)"

            # 明确告诉 AI 这是一个 CSV 数据
            final_data_context = (
                f"Data({self.get_table_name(self.current_table_name)}):\n"
                f"```csv\n{context_str}\n```"
                f"{note}"
            )

            # 5. 打开窗口
            try:
                if hasattr(self, 'ai_dialog') and self.ai_dialog is not None:
                    self.ai_dialog.close()

                from ui.ai_chat import AIChatDialog
                self.ai_dialog = AIChatDialog(final_data_context, self)
                self.ai_dialog.setWindowTitle(f"智能分析 - {self.get_table_name(self.current_table_name)}")
                self.ai_dialog.show()

            except Exception as e:
                logger.exception("AI Dialog Error")
                QMessageBox.critical(self, "组件错误", f"无法打开 AI 窗口：\n{e}")

        except Exception as e:
            logger.exception("AI Logic Error")
            QMessageBox.critical(self, "错误", f"AI分析准备阶段出错：\n{str(e)}")

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

    def update_pagination_controls(self, total_rows: int, total_pages: int):
        if total_pages == 0:
            self.page_info_label.setText("第 0 / 0 页，共 0 条")
            self.prev_page_btn.setEnabled(False)
            self.next_page_btn.setEnabled(False)
            return

        self.page_info_label.setText(f"第 {self.current_page} / {total_pages} 页，共 {total_rows} 条")
        self.prev_page_btn.setEnabled(self.current_page > 1)
        self.next_page_btn.setEnabled(self.current_page < total_pages)

    def previous_page(self):
        if self.current_page <= 1:
            return
        self.current_page -= 1
        self.display_current_page()

    def next_page(self):
        total_rows = len(self.current_results_dict.get(self.current_table_name, []))
        if self.current_page >= self.get_total_pages(total_rows):
            return
        self.current_page += 1
        self.display_current_page()
