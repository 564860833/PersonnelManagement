from datetime import datetime
import re
import logging

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QTableWidget,
    QTableWidgetItem, QComboBox, QGroupBox,
    QMessageBox, QHeaderView, QDialog,
    QVBoxLayout, QCheckBox, QDialogButtonBox,
    QScrollArea, QAbstractItemView, QGridLayout, QFrame
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QIntValidator
from database import Database

logger = logging.getLogger('QueryTab')


# 职级对话框类
class GradeSelectionDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("选择职级/等级")
        self.setMinimumSize(400, 500)
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
        self.all_check.stateChanged.connect(self.on_all_selected)
        scroll_layout.addWidget(self.all_check)

        # 所有职级选项
        self.grade_checks = []
        grade_options = [
            "副厅", "正处", "副处", "二级高级检察官", "三级高级检察官",
            "四级高级检察官", "一级检察官", "二级检察官", "三级检察官",
            "五级检察官助理", "四级检察官助理", "三级检察官助理",
            "二级检察官助理", "一级检察官助理", "试用期人员",
            "二级科员", "一级科员", "四级主任科员", "三级主任科员",
            "二级主任科员", "一级主任科员", "四级调研员", "三级调研员",
            "二级调研员", "一级警长", "二级警长", "三级高级警长"
        ]

        # 添加复选框
        for grade in grade_options:
            check = QCheckBox(grade)
            check.stateChanged.connect(self.on_grade_selected)
            self.grade_checks.append(check)
            scroll_layout.addWidget(check)

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
        self.current_results = []  # 保存当前基础信息查询结果
        self.current_results_dict = {}  # 保存完整查询结果
        # 职位名称映射表（简洁名称 → 完整名称列表）
        self.position_mapping = {
            "副厅": ["检察长"],
            "正县": ["常务副检察长"],
            "副县": ["副检察长", "纪检监察组组长", "政治部主任",
                     "检委会专职委员", "副县级领导"],
            "正科": ["办公室主任", "人事科科长", "机关党委专职副书记",
                     "宣教科科长", "第一检察部主任", "第二检察部主任",
                     "第三检察部主任", "第四检察部主任", "第五检察部主任",
                     "第六检察部主任", "综合业务部主任", "检务督查室主任",
                     "技术科科长", "法警支队队长", "法警支队教导员",
                     "计财科科长"],
            "副科": ["办公室副主任", "人事科副科长", "宣教科副科长",
                     "第一检察部副主任", "第二检察部副主任", "第三检察部副主任",
                     "第四检察部副主任", "第五检察部副主任", "第六检察部副主任",
                     "综合业务部副主任", "控申办负责人", "未检办负责人",
                     "行检办负责人", "检务督查室副主任", "技术科副科长",
                     "法警支队副队长", "计财科副科长"],
            "副科级以上": ["副科级及以上职位"],
            "其他": ["二级高级检察官", "三级高级检察官", "四级高级检察官",
                     "员额检察官", "检察官助理", "科员", "法警", "工勤",
                     "聘用制书记员", "试用期人员"]
        }

        self.setup_ui()
        logger.info("查询标签页已初始化")
        logger.info(
            f"用户权限: base_info={self.permissions['base_info']}, rewards={self.permissions['rewards']}, family={self.permissions['family']}, resume={self.permissions['resume']}")

    def setup_ui(self):
        """设置用户界面 - 优化版"""
        main_layout = QVBoxLayout()
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(15, 15, 15, 15)

        # 查询条件组 - 使用更美观的网格布局
        condition_group = QGroupBox("查询条件")
        grid_layout = QGridLayout()
        grid_layout.setHorizontalSpacing(15)
        grid_layout.setVerticalSpacing(10)
        grid_layout.setContentsMargins(10, 15, 10, 15)  # 增加内边距

        # 添加一个空列作为左侧控件和右侧控件的分隔
        grid_layout.setColumnMinimumWidth(2, 30)  # 设置第2列为分隔列，最小宽度30像素

        # ======== 第一行：姓名 + 出生年月 ========
        row = 0

        # 姓名 - 左对齐
        grid_layout.addWidget(QLabel("姓名:"), row, 0, Qt.AlignRight)
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("输入姓名")
        self.name_input.setMinimumWidth(150)
        grid_layout.addWidget(self.name_input, row, 1)  # 不再跨列

        # 添加分隔标签
        grid_layout.addWidget(QLabel(""), row, 2)  # 空标签作为分隔

        # 出生年月标签 - 右对齐（向右移动到第3列）
        grid_layout.addWidget(QLabel("出生年月范围:"), row, 3, Qt.AlignRight)

        # 起始年月（向右移动到第4列）
        birth_start_layout = QHBoxLayout()
        birth_start_layout.addWidget(QLabel("从"))
        self.birth_start_year = QLineEdit()
        self.birth_start_year.setPlaceholderText("输入年份")
        self.birth_start_year.setValidator(QIntValidator(1900, 2100, self))
        self.birth_start_year.setFixedWidth(200)
        self.birth_start_month = QComboBox()
        self.birth_start_month.addItem("不限")
        self.birth_start_month.addItems([f"{month:02d}" for month in range(1, 13)])
        self.birth_start_month.setFixedWidth(200)
        birth_start_layout.addWidget(self.birth_start_year)
        birth_start_layout.addWidget(QLabel("年"))
        birth_start_layout.addWidget(self.birth_start_month)
        birth_start_layout.addWidget(QLabel("月"))
        grid_layout.addLayout(birth_start_layout, row, 4)

        # 结束年月（向右移动到第5列）
        birth_end_layout = QHBoxLayout()
        birth_end_layout.addWidget(QLabel("至"))
        self.birth_end_year = QLineEdit()
        self.birth_end_year.setPlaceholderText("输入年份")
        self.birth_end_year.setValidator(QIntValidator(1900, 2100, self))
        self.birth_end_year.setFixedWidth(200)
        self.birth_end_month = QComboBox()
        self.birth_end_month.addItem("不限")
        self.birth_end_month.addItems([f"{month:02d}" for month in range(1, 13)])
        self.birth_end_month.setFixedWidth(200)
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
        for level in ["副厅", "正县", "副县", "正科", "副科", "副科级以上", "其他"]:
            self.position_combo.addItem(level, level)
        self.position_combo.setMinimumWidth(120)
        grid_layout.addWidget(self.position_combo, row, 1)

        # 分隔列
        grid_layout.addWidget(QLabel(""), row, 2)  # 空标签作为分隔

        # 职级/等级 - 右对齐（向右移动到第3列）
        grid_layout.addWidget(QLabel("职级/等级:"), row, 3, Qt.AlignRight)
        self.grade_display = QLineEdit()
        self.grade_display.setReadOnly(True)
        self.grade_display.setPlaceholderText("点击选择")
        self.grade_display.setMinimumWidth(150)
        grid_layout.addWidget(self.grade_display, row, 4)  # 移动到第4列

        self.select_grades_btn = QPushButton("选择...")
        self.select_grades_btn.setFixedWidth(80)
        self.select_grades_btn.setStyleSheet("padding: 3px;")
        self.select_grades_btn.clicked.connect(self.select_grades)
        grid_layout.addWidget(self.select_grades_btn, row, 5)  # 移动到第5列

        # ======== 第三行：学历学位 ========
        row += 1

        # 全日制学历学位 - 左对齐
        grid_layout.addWidget(QLabel("全日制学历学位:"), row, 0, Qt.AlignRight)
        self.education_combo = QComboBox()
        self.education_combo.addItem("不限", "")
        for level in ["博士", "硕士", "学士", "专科", "本科及以上"]:
            self.education_combo.addItem(level, level)
        self.education_combo.setMinimumWidth(120)
        grid_layout.addWidget(self.education_combo, row, 1)

        # 分隔列
        grid_layout.addWidget(QLabel(""), row, 2)  # 空标签作为分隔

        # 在职学历学位 - 右对齐（向右移动到第3列）
        grid_layout.addWidget(QLabel("在职学历学位:"), row, 3, Qt.AlignRight)
        self.parttime_combo = QComboBox()
        self.parttime_combo.addItem("不限", "")
        for level in ["博士", "硕士", "学士", "专科", "本科及以上"]:
            self.parttime_combo.addItem(level, level)
        self.parttime_combo.setMinimumWidth(120)
        grid_layout.addWidget(self.parttime_combo, row, 4)  # 移动到第4列

        # ======== 第四行：按钮 ========
        row += 1
        button_layout = QHBoxLayout()
        button_layout.setSpacing(15)

        # 使用更美观的按钮样式
        self.query_btn = QPushButton("查询")
        self.query_btn.setFixedWidth(100)
        self.query_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                border-radius: 4px;
                padding: 6px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        self.query_btn.clicked.connect(self.execute_query)

        self.clear_btn = QPushButton("清空条件")
        self.clear_btn.setFixedWidth(100)
        self.clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #f1f1f1;
                color: #333;
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 6px;
            }
            QPushButton:hover {
                background-color: #e6e6e6;
            }
        """)
        self.clear_btn.clicked.connect(self.clear_conditions)

        self.view_all_btn = QPushButton("查看全部")
        self.view_all_btn.setFixedWidth(100)
        self.view_all_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                font-weight: bold;
                border-radius: 4px;
                padding: 6px;
            }
            QPushButton:hover {
                background-color: #0b7dda;
            }
        """)
        self.view_all_btn.clicked.connect(self.view_all_data)

        button_layout.addStretch()
        button_layout.addWidget(self.query_btn)
        button_layout.addWidget(self.clear_btn)
        button_layout.addWidget(self.view_all_btn)
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
        self.base_info_btn = QPushButton("人员基本信息")
        self.rewards_btn = QPushButton("人员奖惩信息")
        self.family_btn = QPushButton("人员家庭成员信息")
        self.resume_btn = QPushButton("人员简历信息")

        # 根据权限设置按钮可用状态
        self.base_info_btn.setEnabled(self.permissions.get('base_info', False))
        self.rewards_btn.setEnabled(self.permissions.get('rewards', False))
        self.family_btn.setEnabled(self.permissions.get('family', False))
        self.resume_btn.setEnabled(self.permissions.get('resume', False))

        # 设置按钮样式
        for btn, table in [(self.base_info_btn, "base_info"),
                           (self.rewards_btn, "rewards"),
                           (self.family_btn, "family"),
                           (self.resume_btn, "resume")]:
            btn.setMinimumHeight(40)
            btn.setFont(QFont("Microsoft YaHei", 10))
            if self.permissions.get(table, False):
                btn.setStyleSheet("background-color: #4CAF50; color: white;")
            else:
                btn.setStyleSheet("background-color: #f0f0f0; color: #888;")
                btn.setToolTip("您没有此表格的查看权限")
            btn.clicked.connect(lambda _, t=table: self.show_table_data(t))
            button_layout.addWidget(btn)
        result_layout.addLayout(button_layout)

        # 结果表 - 关键修改：禁用行选择功能
        self.result_table = QTableWidget()
        self.result_table.setEditTriggers(QTableWidget.NoEditTriggers)
        # 禁用排序功能，防止数据错乱
        self.result_table.setSortingEnabled(False)
        # 禁用行选择功能 - 新增
        self.result_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.result_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        result_layout.addWidget(self.result_table)

        result_group.setLayout(result_layout)
        main_layout.addWidget(result_group)
        self.setLayout(main_layout)

    def get_education_keywords(self, level: str) -> list:
        """将界面选项映射到数据库关键词"""
        mapping = {
            "博士": ["博士"],
            "硕士": ["硕士"],
            "学士": ["学士", "本科"],
            "专科": ["专科", "大专"],
            "本科及以上": ["本科", "硕士", "博士", "学士"]
        }
        return mapping.get(level, [])

    def select_grades(self):
        """弹出职级选择对话框"""
        dlg = GradeSelectionDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            selected = dlg.selected_grades()
            if selected:
                self.grade_display.setText(", ".join(selected))
            else:
                self.grade_display.clear()

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

    def view_all_data(self):
        """查看全部数据"""
        try:
            # 直接查询所有数据，不使用任何条件
            results_dict = self.db.search_personnel()
            self.current_results_dict = results_dict
            self.current_results = results_dict.get('base_info', [])

            # 显示基础信息表
            self.setup_table_headers('base_info')
            self.display_results(self.current_results, 'base_info')

            # 启用按钮（仅当有查询结果时）
            has_results = len(self.current_results) > 0
            self.base_info_btn.setEnabled(has_results and self.permissions.get('base_info', False))
            self.rewards_btn.setEnabled(has_results and self.permissions.get('rewards', False))
            self.family_btn.setEnabled(has_results and self.permissions.get('family', False))
            self.resume_btn.setEnabled(has_results and self.permissions.get('resume', False))

            QMessageBox.information(self, "查询完成", f"共找到 {len(self.current_results)} 条记录")
        except Exception as e:
            logger.error(f"查看全部数据失败: {e}")
            QMessageBox.critical(self, "查询错误", f"查看全部数据时发生错误: {e}")

    def execute_query(self):
        """执行数据库查询操作"""
        try:
            # 收集所有查询条件
            name = self.name_input.text().strip() or None

            # 获取现任职务条件
            selected_level = self.position_combo.currentData()
            position = None
            if selected_level:
                # 特殊处理"副科级以上"级别
                if selected_level == "副科级以上":
                    # 合并所有副科级及以上的职位
                    position = []
                    for level in ["副科", "正科", "副县", "正县", "副厅"]:
                        position.extend(self.position_mapping[level])
                else:
                    # 使用映射表获取实际职位列表
                    position = self.position_mapping.get(selected_level, [])

            # 获取职级/等级条件 - 使用 grade_display
            grades = []
            grade_text = self.grade_display.text().strip()
            if grade_text:
                grades = [g.strip() for g in grade_text.split(",") if g.strip()]

            # 处理出生年月范围条件（格式为yyyy.MM）
            birth_start = None
            birth_end = None

            # 获取起始年月
            start_year = self.birth_start_year.text().strip()
            start_month = self.birth_start_month.currentText().strip()  # 去掉可能的空格
            if start_year and start_month:  # 年份和月份都填写
                birth_start = f"{start_year}.{start_month}"
            elif start_year:  # 只填写了年份
                # 处理为年份范围（从该年1月到12月）
                birth_start = f"{start_year}.01"
                # 如果结束年月没有设置，自动设置为该年12月
                if not birth_end and not self.birth_end_year.text().strip():
                    birth_end = f"{start_year}.12"

            # 获取结束年月
            end_year = self.birth_end_year.text().strip()
            end_month = self.birth_end_month.currentText().strip()  # 去掉可能的空格
            if end_year and end_month:  # 年份和月份都填写
                birth_end = f"{end_year}.{end_month}"
            elif end_year:  # 只填写了年份
                # 处理为年份范围（从该年1月到12月）
                birth_end = f"{end_year}.12"
                # 如果开始年月没有设置，自动设置为该年1月
                if not birth_start and not self.birth_start_year.text().strip():
                    birth_start = f"{end_year}.01"

            # 处理学历条件
            education_keywords = []
            if self.education_combo.currentData():
                selected_level = self.education_combo.currentData()
                education_keywords = self.get_education_keywords(selected_level)

            # 处理在职学历学位条件 - 不再使用列表，直接使用字符串
            parttime_keywords = []
            if self.parttime_combo.currentData():
                selected_level = self.parttime_combo.currentData()
                parttime_keywords = self.get_education_keywords(selected_level)

            # 调用数据库接口
            results_dict = self.db.search_personnel(
                name=name,
                grades=grades if grades else None,
                position=position,
                birth_start=birth_start,
                birth_end=birth_end,
                education=education_keywords,  # 传入关键词列表
                parttime_education=parttime_keywords  # 传入关键词列表
            )

            self.current_results_dict = results_dict
            self.current_results = results_dict.get('base_info', [])

            # 显示基础信息表
            self.setup_table_headers('base_info')
            self.display_results(self.current_results, 'base_info')

            # 启用按钮（仅当有查询结果时）
            has_results = len(self.current_results) > 0
            self.base_info_btn.setEnabled(has_results and self.permissions.get('base_info', False))
            self.rewards_btn.setEnabled(has_results and self.permissions.get('rewards', False))
            self.family_btn.setEnabled(has_results and self.permissions.get('family', False))
            self.resume_btn.setEnabled(has_results and self.permissions.get('resume', False))

            QMessageBox.information(self, "查询完成", f"找到 {len(self.current_results)} 条记录")

        except Exception as e:
            logger.error(f"查询执行失败: {e}")
            QMessageBox.critical(self, "查询错误", f"执行查询时发生错误: {e}")

    def show_table_data(self, table_name: str):
        """显示指定表的数据"""
        # 检查用户是否有权限查看此表
        if not self.permissions.get(table_name, False):
            QMessageBox.warning(self, "权限不足", "您没有查看此表格的权限")
            return

        # 直接显示该表的所有数据
        data = self.current_results_dict.get(table_name, [])

        # 如果没有数据，显示空表格
        if not data:
            self.result_table.setRowCount(0)
            self.result_table.setColumnCount(0)
            return

        # 设置表头
        self.setup_table_headers(table_name)

        # 显示数据
        self.display_results(data, table_name)

    def get_table_name(self, table_name: str) -> str:
        """获取表的中文名称"""
        table_names = {
            'base_info': '人员基本信息',
            'rewards': '人员奖惩信息',
            'family': '人员家庭成员信息',
            'resume': '人员简历信息'
        }
        return table_names.get(table_name, table_name)


    def setup_table_headers(self, table_name: str):
        """根据表名设置表头"""
        if table_name == 'base_info':
            self.setup_base_info_table()
        elif table_name == 'rewards':
            self.setup_rewards_table()
        elif table_name == 'family':
            self.setup_family_table()
        elif table_name == 'resume':
            self.setup_resume_table()

    def setup_base_info_table(self):
        """设置基础信息表的列头 - 动态显示年份"""
        # 获取实际年份配置
        assessment_years = self.db.get_assessment_years() or []

        # 生成年度考核表头
        assessment_headers = [f"{year}年年度考核结果" for year in assessment_years]

        headers = [
            "序号", "姓名","距离下次职级晋升时间", "现任职务", "任现职务时间",
            "职级/等级", "任现职级/等级时间",
            "前一职务", "前一职务任职时间", "前二职务", "前二职务任职时间",
            "现任法律职务", "现任法律职务任职时间", "前一法律职务",
            "前一法律职务任职时间", "入额时间", "进入检察机关时间", "性别",
            "出生年月", "民族", "籍贯出生地", "参加工作时间", "入党时间",
            "全日制学历学位", "全日制毕业院校及专业", "在职学历学位",
            "在职毕业院校及专业", "奖惩"
        ]

        # 添加年度考核列
        headers.extend(assessment_headers)
        headers.append("备注")

        self.result_table.setColumnCount(len(headers))
        self.result_table.setHorizontalHeaderLabels(headers)

    def setup_rewards_table(self):
        """设置奖惩信息表的列头"""
        headers = [
            "序号", "姓名", "奖励名称", "奖励批准日期", "奖励批准单位", "批准机关性质",
            "惩戒名称", "惩处批准日期", "惩戒批准单位", "惩戒批准机关性质", "影响期"
        ]
        self.result_table.setColumnCount(len(headers))
        self.result_table.setHorizontalHeaderLabels(headers)

    def setup_family_table(self):
        """设置家庭成员信息表的列头"""
        headers = [
            "序号", "姓名", "称谓", "家庭成员姓名", "出生日期", "政治面貌",
            "家庭成员工作单位", "职务"
        ]
        self.result_table.setColumnCount(len(headers))
        self.result_table.setHorizontalHeaderLabels(headers)

    def setup_resume_table(self):
        """设置简历信息表的列头"""
        headers = ["序号", "姓名", "简历信息"]
        self.result_table.setColumnCount(len(headers))
        self.result_table.setHorizontalHeaderLabels(headers)

        # 关键修改：设置各列的宽度调整策略
        # 序号列 - 根据内容调整
        self.result_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)

        # 姓名列 - 根据内容调整，但设置最小宽度
        self.result_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.result_table.horizontalHeader().setMinimumSectionSize(80)  # 设置最小宽度

        # 简历信息列 - 可拉伸模式，优先使用剩余空间
        self.result_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)

        # 设置表格属性，允许文本换行和自动调整行高
        self.result_table.setWordWrap(True)  # 启用文本换行
        self.result_table.setTextElideMode(Qt.ElideNone)  # 禁用省略号截断

    def display_results(self, data, table_name: str):
        """在表格中显示查询结果"""
        # 如果没有数据，清空表格并返回
        if not data:
            self.result_table.setRowCount(0)
            return

        # 根据表类型创建不同的字段映射
        if table_name == 'base_info':
            field_mapping = {
                "序号": "sequence",
                "姓名": "name",
                "距离下次职级晋升时间": "next_promotion",
                "现任职务": "current_position",
                "任现职务时间": "current_position_date",
                "职级/等级": "current_grade",
                "任现职级/等级时间": "current_grade_date",
                "前一职务": "previous_position1",
                "前一职务任职时间": "previous_position1_date",
                "前二职务": "previous_position2",
                "前二职务任职时间": "previous_position2_date",
                "现任法律职务": "current_legal_position",
                "现任法律职务任职时间": "current_legal_position_date",
                "前一法律职务": "previous_legal_position",
                "前一法律职务任职时间": "previous_legal_position_date",
                "入额时间": "admission_date",
                "进入检察机关时间": "entry_date",
                "性别": "gender",
                "出生年月": "birth_date",
                "民族": "ethnicity",
                "籍贯出生地": "hometown",
                "参加工作时间": "work_start_date",
                "入党时间": "party_date",
                "全日制学历学位": "fulltime_education",
                "全日制毕业院校及专业": "fulltime_school",
                "在职学历学位": "parttime_education",
                "在职毕业院校及专业": "parttime_school",
                "奖惩": "rewards",
                "备注": "remarks",
            }
            # 添加年度考核字段映射
            assessment_years = self.db.get_assessment_years() or []
            for idx, year in enumerate(assessment_years):
                field_mapping[f"{year}年年度考核结果"] = f"assessment_{idx}"
        elif table_name == 'rewards':
            field_mapping = {
                "序号": "sequence",
                "姓名": "name",
                "奖励名称": "reward_name",
                "奖励批准日期": "reward_date",
                "奖励批准单位": "reward_unit",
                "批准机关性质": "reward_authority_type",
                "惩戒名称": "punishment_name",
                "惩处批准日期": "punishment_date",
                "惩戒批准单位": "punishment_unit",
                "惩戒批准机关性质": "punishment_authority_type",
                "影响期": "impact_period",
            }
        elif table_name == 'family':
            field_mapping = {
                "序号": "sequence",
                "姓名": "name",
                "称谓": "relation",
                "家庭成员姓名": "family_name",
                "出生日期": "birth_date",
                "政治面貌": "political_status",
                "家庭成员工作单位": "work_unit",
                "职务": "position",
            }
        elif table_name == 'resume':
            field_mapping = {
                "序号": "sequence",
                "姓名": "name",
                "简历信息": "resume_text",
            }


        # 获取表格列数
        col_count = self.result_table.columnCount()

        # 设置行数
        self.result_table.setRowCount(len(data))

        # 获取列头信息用于数据映射
        headers = []
        for i in range(col_count):
            headers.append(self.result_table.horizontalHeaderItem(i).text())

        # 对所有表中的日期字段进行格式转换
        for record in data:
            # 日期格式转换
            if table_name in ['base_info', 'rewards', 'family']:
                # 定义各表的日期字段
                date_fields = {
                    'base_info': [
                        'birth_date', 'work_start_date', 'party_date',
                        'current_position_date', 'current_grade_date',
                        'previous_position1_date', 'previous_position2_date',
                        'current_legal_position_date', 'previous_legal_position_date',
                        'admission_date', 'entry_date', 'next_promotion'
                    ],
                    'rewards': [
                        'reward_date', 'punishment_date'
                    ],
                    'family': [
                        'birth_date'
                    ]
                }

                for field in date_fields.get(table_name, []):
                    if field in record and record[field]:
                        value = str(record[field])
                        # 转换格式：YYYY-MM-DD → YYYY.MM
                        if re.match(r'^\d{4}-\d{2}-\d{2}$', value):
                            record[field] = value[:7].replace('-', '.')
                        # 处理浮点数格式（如1996.01）
                        elif re.match(r'^\d{4}\.\d{2}$', value):
                            record[field] = value
                        # 处理整数格式（如199601）
                        elif re.match(r'^\d{6}$', value):
                            record[field] = f"{value[:4]}.{value[4:6]}"

        # 填充数据
        for row_idx, row_data in enumerate(data):
            for col_idx, header in enumerate(headers):
                field_name = field_mapping.get(header, header.lower())
                value = row_data.get(field_name, '')
                if value is None:
                    value = ''

                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignCenter)

                # 关键修改1: 启用文本自动换行
                item.setFlags(item.flags() | Qt.TextWordWrap)

                # 关键修改2: 对于简历信息表启用富文本显示
                if table_name == 'resume' and field_name == 'resume_text':
                    item.setToolTip(value)  # 添加完整内容作为提示

                self.result_table.setItem(row_idx, col_idx, item)

        # 关键修改3: 自动调整行高以显示完整内容
        self.result_table.resizeRowsToContents()

        # 关键修改4: 对于简历信息表特殊处理列宽
        if table_name == 'resume':
            # 简历列设置为可拉伸
            self.result_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)

        # 调整列宽
        self.result_table.resizeColumnsToContents()
        self.result_table.scrollToTop()