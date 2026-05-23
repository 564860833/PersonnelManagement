from PyQt5.QtWidgets import (QDialog, QLabel, QLineEdit, QPushButton, QVBoxLayout,
                             QHBoxLayout, QMessageBox, QGroupBox, QCheckBox,
                             QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
                             QApplication, QStyle, QStyledItemDelegate, QStyleOptionViewItem)
from PyQt5.QtCore import QLineF, QRect, QRectF, QSize, Qt
from PyQt5.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
import logging
from metadata.constants import TABLE_LABELS
from ui.confirm_dialog import confirm_danger
from ui.styles import DIALOG_BASE_STYLE, DIALOG_BUTTON_STYLE, RESULT_TABLE_STYLE

logger = logging.getLogger('UserMgr')


def _permission_icon(enabled: bool) -> QIcon:
    pixmap = QPixmap(24, 24)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor("#16A34A" if enabled else "#DC2626"))
    painter.drawEllipse(QRectF(2, 2, 20, 20))

    pen = QPen(QColor("#FFFFFF"), 2.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    painter.setPen(pen)
    if enabled:
        painter.drawLine(QLineF(7.2, 12.2, 10.5, 15.5))
        painter.drawLine(QLineF(10.5, 15.5, 16.8, 8.8))
    else:
        painter.drawLine(QLineF(8.2, 8.2, 15.8, 15.8))
        painter.drawLine(QLineF(15.8, 8.2, 8.2, 15.8))
    painter.end()

    return QIcon(pixmap)


def _permission_item(enabled: bool) -> QTableWidgetItem:
    item = QTableWidgetItem()
    item.setIcon(_permission_icon(enabled))
    item.setToolTip("有权限" if enabled else "无权限")
    item.setTextAlignment(Qt.AlignCenter)
    return item


class CenteredIconDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        icon = index.data(Qt.DecorationRole)
        text = index.data(Qt.DisplayRole)
        if isinstance(icon, QIcon) and not icon.isNull() and not text:
            opt = QStyleOptionViewItem(option)
            self.initStyleOption(opt, index)
            opt.text = ""
            opt.icon = QIcon()

            style = opt.widget.style() if opt.widget is not None else QApplication.style()
            style.drawControl(QStyle.CE_ItemViewItem, opt, painter, opt.widget)

            icon_size = QSize(24, 24)
            icon_rect = QRect(
                option.rect.x() + (option.rect.width() - icon_size.width()) // 2,
                option.rect.y() + (option.rect.height() - icon_size.height()) // 2,
                icon_size.width(),
                icon_size.height(),
            )
            icon.paint(painter, icon_rect, Qt.AlignCenter)
            return

        super().paint(painter, option, index)


class AddUserDialog(QDialog):
    def __init__(self, db):
        super().__init__()
        self.db = db
        self.setWindowTitle("添加用户账号")
        self.setMinimumSize(420, 480)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        self.setStyleSheet(DIALOG_BASE_STYLE + DIALOG_BUTTON_STYLE)

        # 用户名输入
        username_layout = QHBoxLayout()
        username_label = QLabel("用户名")
        username_label.setObjectName("fieldLabel")
        username_label.setMinimumWidth(88)
        username_layout.addWidget(username_label)
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("输入用户名")
        username_layout.addWidget(self.username_input)
        layout.addLayout(username_layout)

        # 密码输入
        password_layout = QHBoxLayout()
        password_label = QLabel("密码")
        password_label.setObjectName("fieldLabel")
        password_label.setMinimumWidth(88)
        password_layout.addWidget(password_label)
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("输入密码")
        self.password_input.setEchoMode(QLineEdit.Password)
        password_layout.addWidget(self.password_input)
        layout.addLayout(password_layout)

        # 确认密码
        confirm_layout = QHBoxLayout()
        confirm_label = QLabel("确认密码")
        confirm_label.setObjectName("fieldLabel")
        confirm_label.setMinimumWidth(88)
        confirm_layout.addWidget(confirm_label)
        self.confirm_input = QLineEdit()
        self.confirm_input.setPlaceholderText("再次输入密码")
        self.confirm_input.setEchoMode(QLineEdit.Password)
        confirm_layout.addWidget(self.confirm_input)
        layout.addLayout(confirm_layout)

        # 权限设置组
        permissions_group = QGroupBox("表格访问权限")
        permissions_layout = QVBoxLayout()

        self.permission_checks = {}
        for table_name, label in TABLE_LABELS.items():
            check = QCheckBox(f"{label}表")
            self.permission_checks[table_name] = check
            permissions_layout.addWidget(check)
        permissions_group.setLayout(permissions_layout)
        layout.addWidget(permissions_group)

        # 按钮布局
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        ok_btn = QPushButton("确定")
        ok_btn.setObjectName("primaryButton")
        ok_btn.clicked.connect(self.on_ok)
        cancel_btn = QPushButton("取消")
        cancel_btn.setObjectName("secondaryButton")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(ok_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)

        self.setLayout(layout)

    def on_ok(self):
        username = self.username_input.text().strip()
        password = self.password_input.text()
        confirm = self.confirm_input.text()

        if not username:
            QMessageBox.warning(self, "输入错误", "用户名不能为空")
            return

        if not password:
            QMessageBox.warning(self, "输入错误", "密码不能为空")
            return

        if password != confirm:
            QMessageBox.warning(self, "输入错误", "两次输入的密码不一致")
            return

        # 检查用户名是否已存在
        if self.db.get_password(username) is not None:
            QMessageBox.warning(self, "用户已存在", "该用户名已被使用，请使用其他用户名")
            return

        # 添加用户到数据库
        try:
            self.db.add_user(username, password)

            # 设置权限
            permissions = {
                table_name: int(check.isChecked())
                for table_name, check in self.permission_checks.items()
            }
            self.db.set_user_permissions(username, permissions)

            QMessageBox.information(self, "成功", f"用户 {username} 添加成功")
            self.accept()
        except Exception as e:
            logger.error(f"添加用户失败: {e}")
            QMessageBox.critical(self, "错误", f"添加用户时发生错误: {e}")


class UserManagementDialog(QDialog):
    def __init__(self, db):
        super().__init__()
        self.db = db
        self.setWindowTitle("用户账号管理")
        self.setMinimumSize(980, 480)
        self.setup_ui()
        self.load_users()

    def setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        self.setStyleSheet(DIALOG_BASE_STYLE + DIALOG_BUTTON_STYLE)

        # 用户列表
        self.user_table = QTableWidget()
        self.user_table.setColumnCount(len(TABLE_LABELS) + 1)
        self.user_table.setIconSize(QSize(24, 24))
        self.user_table.setHorizontalHeaderLabels(["用户名"] + [f"{label}表" for label in TABLE_LABELS.values()])
        self.configure_user_table_columns()
        self.user_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.user_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.user_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.user_table.setAlternatingRowColors(True)
        self.user_table.setStyleSheet(RESULT_TABLE_STYLE)
        layout.addWidget(self.user_table)

        # 按钮区域
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        # 修改权限按钮
        self.edit_btn = QPushButton("修改权限")
        self.edit_btn.setObjectName("primaryButton")
        self.edit_btn.clicked.connect(self.edit_permissions)
        btn_layout.addWidget(self.edit_btn)

        # 删除用户按钮
        self.delete_btn = QPushButton("删除用户")
        self.delete_btn.setObjectName("dangerButton")
        self.delete_btn.clicked.connect(self.delete_user)
        btn_layout.addWidget(self.delete_btn)

        # 关闭按钮
        self.close_btn = QPushButton("关闭")
        self.close_btn.setObjectName("secondaryButton")
        self.close_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.close_btn)

        layout.addLayout(btn_layout)
        self.setLayout(layout)

    def configure_user_table_columns(self):
        header = self.user_table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignCenter)
        header.setStretchLastSection(False)

        self.user_table.setColumnWidth(0, 160)
        header.setSectionResizeMode(0, QHeaderView.Interactive)

        self.permission_icon_delegate = CenteredIconDelegate(self.user_table)
        for col, table_name in enumerate(TABLE_LABELS, start=1):
            width = 210 if table_name == "family" else 170
            self.user_table.setColumnWidth(col, width)
            header.setSectionResizeMode(col, QHeaderView.Interactive)
            self.user_table.setItemDelegateForColumn(col, self.permission_icon_delegate)

    def load_users(self):
        """从数据库加载所有用户（除了admin）"""
        try:
            users = self.db.get_all_users()

            self.user_table.setRowCount(len(users))

            for row, username in enumerate(users):
                # 获取用户权限
                permissions = self.db.get_user_permissions(username)

                # 填充表格
                self.user_table.setItem(row, 0, QTableWidgetItem(username))
                for col, table_name in enumerate(TABLE_LABELS, start=1):
                    self.user_table.setItem(row, col, _permission_item(permissions[table_name]))

                # 设置居中
                for col in range(1, len(TABLE_LABELS) + 1):
                    item = self.user_table.item(row, col)
                    item.setTextAlignment(Qt.AlignCenter)

        except Exception as e:
            logger.error(f"加载用户列表失败: {e}")
            QMessageBox.critical(self, "错误", f"加载用户列表失败: {e}")

    def edit_permissions(self):
        """修改选中用户的权限"""
        selected_rows = self.user_table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.warning(self, "未选择", "请先选择一个用户")
            return

        selected_row = selected_rows[0].row()
        username = self.user_table.item(selected_row, 0).text()

        # 获取当前权限
        permissions = self.db.get_user_permissions(username)

        # 创建权限编辑对话框
        dlg = EditPermissionsDialog(self.db, username, permissions)
        if dlg.exec_() == QDialog.Accepted:
            self.load_users()  # 刷新列表
            QMessageBox.information(self, "成功", f"用户 {username} 的权限已更新")

    def delete_user(self):
        """删除选中用户"""
        selected_rows = self.user_table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.warning(self, "未选择", "请先选择一个用户")
            return

        selected_row = selected_rows[0].row()
        username = self.user_table.item(selected_row, 0).text()

        if confirm_danger(self, "确认删除用户", f"确定要删除用户 {username} 吗？", "删除用户"):
            try:
                # 删除用户
                if self.db.delete_user(username):
                    self.load_users()  # 刷新列表
                    QMessageBox.information(self, "成功", f"用户 {username} 已删除")
                else:
                    QMessageBox.warning(self, "失败", "删除用户失败")
            except Exception as e:
                logger.error(f"删除用户失败: {e}")
                QMessageBox.critical(self, "错误", f"删除用户时出错: {e}")


class EditPermissionsDialog(QDialog):
    def __init__(self, db, username, permissions):
        super().__init__()
        self.db = db
        self.username = username
        self.permissions = permissions
        self.setWindowTitle(f"编辑权限 - {username}")
        self.setMinimumSize(420, 420)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        self.setStyleSheet(DIALOG_BASE_STYLE + DIALOG_BUTTON_STYLE)

        # 权限设置组
        permissions_group = QGroupBox("表格访问权限")
        permissions_layout = QVBoxLayout()

        self.permission_checks = {}
        for table_name, label in TABLE_LABELS.items():
            check = QCheckBox(f"{label}表")
            check.setChecked(self.permissions[table_name])
            self.permission_checks[table_name] = check
            permissions_layout.addWidget(check)
        permissions_group.setLayout(permissions_layout)
        layout.addWidget(permissions_group)

        # 按钮
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        save_btn = QPushButton("保存")
        save_btn.setObjectName("primaryButton")
        save_btn.clicked.connect(self.save_permissions)
        button_layout.addWidget(save_btn)

        cancel_btn = QPushButton("取消")
        cancel_btn.setObjectName("secondaryButton")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        layout.addLayout(button_layout)
        self.setLayout(layout)

    def save_permissions(self):
        """保存权限设置"""
        permissions = {
            table_name: check.isChecked()
            for table_name, check in self.permission_checks.items()
        }

        try:
            self.db.set_user_permissions(self.username, permissions)
            self.accept()
        except Exception as e:
            logger.error(f"保存权限失败: {e}")
            QMessageBox.critical(self, "错误", f"保存权限时出错: {e}")
