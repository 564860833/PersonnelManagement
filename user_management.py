from PyQt5.QtWidgets import (QDialog, QLabel, QLineEdit, QPushButton, QVBoxLayout,
                             QHBoxLayout, QMessageBox, QGroupBox, QCheckBox,
                             QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView)
from PyQt5.QtCore import Qt
import logging
import sqlite3

logger = logging.getLogger('UserMgr')


class AddUserDialog(QDialog):
    def __init__(self, db):
        super().__init__()
        self.db = db
        self.setWindowTitle("添加用户账号")
        self.setFixedSize(400, 400)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()

        # 用户名输入
        username_layout = QHBoxLayout()
        username_layout.addWidget(QLabel("用户名:"))
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("输入用户名")
        username_layout.addWidget(self.username_input)
        layout.addLayout(username_layout)

        # 密码输入
        password_layout = QHBoxLayout()
        password_layout.addWidget(QLabel("密码:"))
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("输入密码")
        self.password_input.setEchoMode(QLineEdit.Password)
        password_layout.addWidget(self.password_input)
        layout.addLayout(password_layout)

        # 确认密码
        confirm_layout = QHBoxLayout()
        confirm_layout.addWidget(QLabel("确认密码:"))
        self.confirm_input = QLineEdit()
        self.confirm_input.setPlaceholderText("再次输入密码")
        self.confirm_input.setEchoMode(QLineEdit.Password)
        confirm_layout.addWidget(self.confirm_input)
        layout.addLayout(confirm_layout)

        # 权限设置组
        permissions_group = QGroupBox("表格访问权限")
        permissions_layout = QVBoxLayout()

        self.base_check = QCheckBox("人员基本信息表")
        self.rewards_check = QCheckBox("人员奖惩信息表")
        self.family_check = QCheckBox("人员家庭成员信息表")
        self.resume_check = QCheckBox("人员简历信息表")

        permissions_layout.addWidget(self.base_check)
        permissions_layout.addWidget(self.rewards_check)
        permissions_layout.addWidget(self.family_check)
        permissions_layout.addWidget(self.resume_check)
        permissions_group.setLayout(permissions_layout)
        layout.addWidget(permissions_group)

        # 按钮布局
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        ok_btn = QPushButton("确定")
        ok_btn.clicked.connect(self.on_ok)
        cancel_btn = QPushButton("取消")
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
                'base_info': int(self.base_check.isChecked()),
                'rewards': int(self.rewards_check.isChecked()),
                'family': int(self.family_check.isChecked()),
                'resume': int(self.resume_check.isChecked())
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
        self.setFixedSize(850, 400)
        self.setup_ui()
        self.load_users()

    def setup_ui(self):
        layout = QVBoxLayout()

        # 用户列表
        self.user_table = QTableWidget()
        self.user_table.setColumnCount(5)  # 用户名 + 4个权限
        self.user_table.setHorizontalHeaderLabels(["用户名", "基本信息表", "奖惩信息表", "家庭成员信息表", "简历信息表"])
        self.user_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.user_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.user_table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.user_table)

        # 按钮区域
        btn_layout = QHBoxLayout()

        # 修改权限按钮
        self.edit_btn = QPushButton("修改权限")
        self.edit_btn.clicked.connect(self.edit_permissions)
        btn_layout.addWidget(self.edit_btn)

        # 删除用户按钮
        self.delete_btn = QPushButton("删除用户")
        self.delete_btn.clicked.connect(self.delete_user)
        btn_layout.addWidget(self.delete_btn)

        # 关闭按钮
        self.close_btn = QPushButton("关闭")
        self.close_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.close_btn)

        layout.addLayout(btn_layout)
        self.setLayout(layout)

    def load_users(self):
        """从数据库加载所有用户（除了admin）"""
        try:
            # 获取所有用户（排除admin）
            cursor = self.db.conn.cursor()
            cursor.execute("SELECT username FROM users WHERE username != 'admin'")
            users = [row[0] for row in cursor.fetchall()]

            self.user_table.setRowCount(len(users))

            for row, username in enumerate(users):
                # 获取用户权限
                permissions = self.db.get_user_permissions(username)

                # 填充表格
                self.user_table.setItem(row, 0, QTableWidgetItem(username))
                self.user_table.setItem(row, 1, QTableWidgetItem("✓" if permissions['base_info'] else "✗"))
                self.user_table.setItem(row, 2, QTableWidgetItem("✓" if permissions['rewards'] else "✗"))
                self.user_table.setItem(row, 3, QTableWidgetItem("✓" if permissions['family'] else "✗"))
                self.user_table.setItem(row, 4, QTableWidgetItem("✓" if permissions['resume'] else "✗"))

                # 设置居中
                for col in range(1, 5):
                    item = self.user_table.item(row, col)
                    item.setTextAlignment(Qt.AlignCenter)

        except sqlite3.Error as e:
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

        # 确认删除
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除用户 {username} 吗？此操作不可恢复！",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
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
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()

        # 权限设置组
        permissions_group = QGroupBox("表格访问权限")
        permissions_layout = QVBoxLayout()

        self.base_check = QCheckBox("人员基本信息表")
        self.base_check.setChecked(self.permissions['base_info'])

        self.rewards_check = QCheckBox("人员奖惩信息表")
        self.rewards_check.setChecked(self.permissions['rewards'])

        self.family_check = QCheckBox("人员家庭成员信息表")
        self.family_check.setChecked(self.permissions['family'])

        self.resume_check = QCheckBox("人员简历信息表")
        self.resume_check.setChecked(self.permissions['resume'])

        permissions_layout.addWidget(self.base_check)
        permissions_layout.addWidget(self.rewards_check)
        permissions_layout.addWidget(self.family_check)
        permissions_layout.addWidget(self.resume_check)
        permissions_group.setLayout(permissions_layout)
        layout.addWidget(permissions_group)

        # 按钮
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        save_btn = QPushButton("保存")
        save_btn.clicked.connect(self.save_permissions)
        button_layout.addWidget(save_btn)

        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        layout.addLayout(button_layout)
        self.setLayout(layout)

    def save_permissions(self):
        """保存权限设置"""
        permissions = {
            'base_info': self.base_check.isChecked(),
            'rewards': self.rewards_check.isChecked(),
            'family': self.family_check.isChecked(),
            'resume': self.resume_check.isChecked()
        }

        try:
            self.db.set_user_permissions(self.username, permissions)
            self.accept()
        except Exception as e:
            logger.error(f"保存权限失败: {e}")
            QMessageBox.critical(self, "错误", f"保存权限时出错: {e}")