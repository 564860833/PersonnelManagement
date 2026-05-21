from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from ui.styles import DANGER_CONFIRM_STYLE


class DangerConfirmDialog(QDialog):
    """Shared confirmation dialog for destructive actions."""

    def __init__(self, parent, title: str, message: str, confirm_text: str):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumSize(380, 220)
        self.setStyleSheet(DANGER_CONFIRM_STYLE)
        self.setup_ui(title, message, confirm_text)

    def setup_ui(self, title: str, message: str, confirm_text: str):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(16, 16, 16, 16)

        panel = QFrame()
        panel.setObjectName("dangerConfirmPanel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(20, 18, 20, 18)
        panel_layout.setSpacing(12)

        title_label = QLabel(title)
        title_label.setObjectName("dangerTitle")
        panel_layout.addWidget(title_label)

        message_label = QLabel(message)
        message_label.setObjectName("dangerMessage")
        message_label.setWordWrap(True)
        panel_layout.addWidget(message_label)

        self.hint_label = QLabel("此操作不可恢复，请确认后再继续。")
        self.hint_label.setObjectName("dangerHint")
        self.hint_label.setWordWrap(False)
        self.hint_label.setMinimumWidth(self.hint_label.sizeHint().width())
        panel_layout.addWidget(self.hint_label)

        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        button_layout.addStretch()

        self.cancel_button = QPushButton("取消")
        self.cancel_button.setObjectName("secondaryButton")
        self.cancel_button.setDefault(True)
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)

        self.confirm_button = QPushButton(confirm_text)
        self.confirm_button.setObjectName("dangerButton")
        self.confirm_button.setAutoDefault(False)
        self.confirm_button.clicked.connect(self.accept)
        button_layout.addWidget(self.confirm_button)

        panel_layout.addLayout(button_layout)
        root_layout.addWidget(panel)

    def showEvent(self, event):
        super().showEvent(event)
        self.cancel_button.setFocus(Qt.OtherFocusReason)


def confirm_danger(parent, title: str, message: str, confirm_text: str) -> bool:
    dialog = DangerConfirmDialog(parent, title, message, confirm_text)
    return dialog.exec_() == QDialog.Accepted
