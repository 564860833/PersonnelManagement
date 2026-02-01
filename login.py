from PyQt5.QtWidgets import (QDialog, QLabel, QLineEdit, QPushButton,
                             QVBoxLayout, QMessageBox, QHBoxLayout, QFrame, QApplication)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QPixmap, QIcon
from database import Database
import config

class LoginDialog(QDialog):
    def __init__(self, db: Database):
        super().__init__()
        self.db = db
        # 移除帮助按钮
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setup_ui()
        self.center_on_screen()


    def center_on_screen(self):
        screen_geo = QApplication.desktop().availableGeometry()
        x = (screen_geo.width() - self.width()) // 2
        y = (screen_geo.height() - self.height()) // 2
        self.move(x, y)

    def setup_ui(self):
        self.setWindowTitle("系统登录")
        self.setFixedSize(400, 300)

        main_layout = QVBoxLayout()
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # 标题
        self.add_header(main_layout)

        # 分隔线
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        main_layout.addWidget(separator)
        main_layout.addSpacing(10)

        # 表单
        self.add_form_layout(main_layout)
        self.add_button_layout(main_layout)

        self.setLayout(main_layout)

    def add_header(self, layout):
        title_label = QLabel(config.APP_NAME)
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)

        version_label = QLabel(f"版本 {config.APP_VERSION}")
        version_font = QFont()
        version_font.setPointSize(10)
        version_label.setFont(version_font)
        version_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(version_label)
        layout.addSpacing(10)

    def add_form_layout(self, layout):
        username_layout = QHBoxLayout()
        username_layout.addWidget(QLabel("用户名:"))
        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("请输入用户名")
        self.username_edit.setMinimumWidth(200)
        self.username_edit.setFocus()
        username_layout.addWidget(self.username_edit)

        password_layout = QHBoxLayout()
        password_layout.addWidget(QLabel("密   码:"))
        self.password_edit = QLineEdit()
        self.password_edit.setPlaceholderText("请输入密码")
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.password_edit.setMinimumWidth(200)
        password_layout.addWidget(self.password_edit)

        layout.addLayout(username_layout)
        layout.addLayout(password_layout)
        layout.addSpacing(10)

    def add_button_layout(self, layout):
        btn_layout = QHBoxLayout()
        btn_layout.setAlignment(Qt.AlignCenter)

        self.login_btn = QPushButton("登录")
        self.login_btn.setMinimumWidth(100)
        self.login_btn.setDefault(True)
        self.login_btn.clicked.connect(self.authenticate)

        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setMinimumWidth(100)
        self.cancel_btn.clicked.connect(self.reject)

        btn_layout.addWidget(self.login_btn)
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)

    def showEvent(self, event):
        super().showEvent(event)
        self.center_on_screen()

    def authenticate(self):
        username = self.username_edit.text().strip()
        password = self.password_edit.text().strip()

        if not username:
            QMessageBox.warning(self, "输入错误", "用户名不能为空")
            self.username_edit.setFocus()
            return
        if not password:
            QMessageBox.warning(self, "输入错误", "密码不能为空")
            self.password_edit.setFocus()
            return

        # 从数据库验证
        try:
            stored = self.db.get_password(username)
        except Exception as e:
            QMessageBox.critical(self, "数据库错误", f"无法读取用户信息: {e}")
            return

        if stored is None:
            QMessageBox.warning(self, "错误", "用户不存在")
            self.username_edit.selectAll()
            self.username_edit.setFocus()
            return

        if password != stored:
            QMessageBox.warning(self, "错误", "用户名或密码错误")
            self.password_edit.selectAll()
            self.password_edit.setFocus()
            return

        # 验证通过
        self.accept()

    def get_username(self) -> str:
        return self.username_edit.text().strip()