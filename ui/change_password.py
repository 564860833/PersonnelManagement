# change_password.py

from PyQt5.QtWidgets import (QDialog, QLabel, QLineEdit, QPushButton,
                             QVBoxLayout, QHBoxLayout, QMessageBox)
from PyQt5.QtCore import Qt
from ui.styles import DIALOG_BASE_STYLE, DIALOG_BUTTON_STYLE
import logging

logger = logging.getLogger('ChangePwd')

class ChangePasswordDialog(QDialog):
    def __init__(self, db, username):
        super().__init__()
        self.db = db
        self.username = username
        self.setWindowTitle("修改密码")
        self.setup_ui()
        self.setMinimumSize(380, 250)

    def setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        self.setStyleSheet(DIALOG_BASE_STYLE + DIALOG_BUTTON_STYLE)

        # 旧密码
        old_layout = QHBoxLayout()
        old_label = QLabel("旧密码")
        old_label.setObjectName("fieldLabel")
        old_label.setMinimumWidth(88)
        old_layout.addWidget(old_label)
        self.old_edit = QLineEdit()
        self.old_edit.setEchoMode(QLineEdit.Password)
        old_layout.addWidget(self.old_edit)
        layout.addLayout(old_layout)

        # 新密码
        new_layout = QHBoxLayout()
        new_label = QLabel("新密码")
        new_label.setObjectName("fieldLabel")
        new_label.setMinimumWidth(88)
        new_layout.addWidget(new_label)
        self.new_edit = QLineEdit()
        self.new_edit.setEchoMode(QLineEdit.Password)
        new_layout.addWidget(self.new_edit)
        layout.addLayout(new_layout)

        # 确认新密码
        confirm_layout = QHBoxLayout()
        confirm_label = QLabel("确认密码")
        confirm_label.setObjectName("fieldLabel")
        confirm_label.setMinimumWidth(88)
        confirm_layout.addWidget(confirm_label)
        self.confirm_edit = QLineEdit()
        self.confirm_edit.setEchoMode(QLineEdit.Password)
        confirm_layout.addWidget(self.confirm_edit)
        layout.addLayout(confirm_layout)

        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.setAlignment(Qt.AlignCenter)
        ok_btn = QPushButton("确定")
        ok_btn.setObjectName("primaryButton")
        ok_btn.clicked.connect(self.on_ok)
        cancel_btn = QPushButton("取消")
        cancel_btn.setObjectName("secondaryButton")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        self.setLayout(layout)

    def on_ok(self):
        old = self.old_edit.text().strip()
        new = self.new_edit.text().strip()
        confirm = self.confirm_edit.text().strip()

        if not old or not new:
            QMessageBox.warning(self, "输入错误", "旧密码和新密码均不能为空")
            return
        if new != confirm:
            QMessageBox.warning(self, "输入错误", "两次输入的新密码不一致")
            return

        # 验证旧密码
        stored = self.db.get_password(self.username)
        if stored is None or stored != old:
            QMessageBox.critical(self, "错误", "旧密码不正确")
            return

        # 更新
        if self.db.change_password(self.username, new):
            QMessageBox.information(self, "成功", "密码修改成功，请重新登录")
            self.accept()
        else:
            QMessageBox.critical(self, "失败", "修改密码时发生错误")
