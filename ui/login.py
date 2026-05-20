from PyQt5.QtWidgets import (QDialog, QLabel, QLineEdit, QPushButton,
                             QVBoxLayout, QMessageBox, QHBoxLayout, QFrame, QApplication)
from PyQt5.QtCore import Qt
from core.database import Database
from ui.styles import LOGIN_DIALOG_STYLE
import config

class LoginDialog(QDialog):
    def __init__(self, db: Database):
        super().__init__()
        self.db = db
        self.setObjectName("loginDialog")
        # 移除帮助按钮
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setup_ui()
        self.center_on_screen()


    def center_on_screen(self):
        screen_geo = QApplication.primaryScreen().availableGeometry()
        x = (screen_geo.width() - self.width()) // 2
        y = (screen_geo.height() - self.height()) // 2
        self.move(x, y)

    def setup_ui(self):
        self.setWindowTitle("系统登录")
        self.setFixedSize(420, 390)
        self.setStyleSheet(LOGIN_DIALOG_STYLE)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(24, 24, 24, 24)
        main_layout.setAlignment(Qt.AlignCenter)

        card = QFrame()
        card.setObjectName("loginCard")
        card.setFixedWidth(360)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(36, 28, 36, 28)
        card_layout.setSpacing(12)

        # 标题
        self.add_header(card_layout)

        # 分隔线
        separator = QFrame()
        separator.setObjectName("loginDivider")
        card_layout.addWidget(separator)

        # 表单
        self.add_form_layout(card_layout)
        self.add_button_layout(card_layout)

        main_layout.addWidget(card)
        self.setLayout(main_layout)

    def add_header(self, layout):
        title_label = QLabel(config.APP_NAME)
        title_label.setObjectName("loginTitle")
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)

        version_label = QLabel(f"版本 {config.APP_VERSION}")
        version_label.setObjectName("loginSubtitle")
        version_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(version_label)
        layout.addSpacing(2)

    def add_form_layout(self, layout):
        username_group = QVBoxLayout()
        username_group.setContentsMargins(0, 0, 0, 0)
        username_group.setSpacing(6)
        self.username_label = QLabel("用户名")
        self.username_label.setObjectName("fieldLabel")
        username_group.addWidget(self.username_label)
        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("请输入用户名")
        self.username_edit.setMinimumHeight(36)
        self.username_edit.setFocus()
        username_group.addWidget(self.username_edit)
        layout.addLayout(username_group)
        layout.addSpacing(12)

        password_group = QVBoxLayout()
        password_group.setContentsMargins(0, 0, 0, 0)
        password_group.setSpacing(6)
        self.password_label = QLabel("密码")
        self.password_label.setObjectName("fieldLabel")
        password_group.addWidget(self.password_label)
        self.password_edit = QLineEdit()
        self.password_edit.setPlaceholderText("请输入密码")
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.password_edit.setMinimumHeight(36)
        password_group.addWidget(self.password_edit)
        layout.addLayout(password_group)
        layout.addSpacing(22)

    def add_button_layout(self, layout):
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.login_btn = QPushButton("登录")
        self.login_btn.setObjectName("primaryButton")
        self.login_btn.setDefault(True)
        self.login_btn.clicked.connect(self.authenticate)

        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setObjectName("secondaryButton")
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
