from PyQt5.QtCore import QLineF, QPointF, QRectF, Qt, QTimer
from PyQt5.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PyQt5.QtWidgets import (
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ui.styles import THEME_BORDER, THEME_LIGHT, THEME_PRIMARY, THEME_PRIMARY_HOVER


class LoadingRing(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._angle = 0
        self.setFixedSize(56, 56)
        self._timer = QTimer(self)
        self._timer.setInterval(28)
        self._timer.timeout.connect(self._tick)

    def _tick(self):
        self._angle = (self._angle + 10) % 360
        self.update()

    def showEvent(self, event):
        if not self._timer.isActive():
            self._timer.start()
        super().showEvent(event)

    def hideEvent(self, event):
        self._timer.stop()
        super().hideEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = QRectF(9, 9, self.width() - 18, self.height() - 18)
        base_pen = QPen(QColor(THEME_LIGHT), 5)
        base_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(base_pen)
        painter.drawEllipse(rect)

        active_pen = QPen(QColor(THEME_PRIMARY), 5)
        active_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(active_pen)
        painter.drawArc(rect, self._angle * 16, -115 * 16)


class AiChipIcon(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(64, 64)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        size = min(self.width(), self.height())
        chip_size = size * 0.54
        chip_rect = QRectF(
            (self.width() - chip_size) / 2,
            (self.height() - chip_size) / 2,
            chip_size,
            chip_size,
        )
        pin_pen = QPen(QColor(THEME_BORDER), max(2, int(size * 0.045)))
        pin_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pin_pen)

        pin_length = size * 0.12
        for ratio in (0.2, 0.5, 0.8):
            x = chip_rect.left() + chip_rect.width() * ratio
            y = chip_rect.top() + chip_rect.height() * ratio
            painter.drawLine(QLineF(chip_rect.left() - pin_length, y, chip_rect.left(), y))
            painter.drawLine(QLineF(chip_rect.right(), y, chip_rect.right() + pin_length, y))
            painter.drawLine(QLineF(x, chip_rect.top() - pin_length, x, chip_rect.top()))
            painter.drawLine(QLineF(x, chip_rect.bottom(), x, chip_rect.bottom() + pin_length))

        painter.setPen(QPen(QColor(THEME_PRIMARY), max(2, int(size * 0.04))))
        painter.setBrush(QColor(THEME_LIGHT))
        painter.drawRoundedRect(chip_rect, 9, 9)

        painter.setPen(QColor(THEME_PRIMARY_HOVER))
        font = QFont()
        font.setBold(True)
        font.setPixelSize(int(size * 0.28))
        painter.setFont(font)
        painter.drawText(chip_rect, Qt.AlignCenter, "AI")


class FileTransferIcon(QWidget):
    def __init__(self, icon_kind="import", parent=None):
        super().__init__(parent)
        self.icon_kind = icon_kind
        self.setFixedSize(64, 64)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        file_rect = QRectF(15, 10, 34, 42)
        fold = QPolygonF([
            QPointF(file_rect.right() - 10, file_rect.top()),
            QPointF(file_rect.right(), file_rect.top() + 10),
            QPointF(file_rect.right() - 10, file_rect.top() + 10),
        ])

        painter.setPen(QPen(QColor(THEME_PRIMARY), 2))
        painter.setBrush(QColor(THEME_LIGHT))
        painter.drawRoundedRect(file_rect, 7, 7)
        painter.setBrush(QColor("#D8E9F9"))
        painter.drawPolygon(fold)

        painter.setPen(QPen(QColor(THEME_BORDER), 2, Qt.SolidLine, Qt.RoundCap))
        for y in (25, 32, 39):
            painter.drawLine(QLineF(23, y, 41, y))

        is_export = self.icon_kind == "export"
        arrow_start = QPointF(32, 54 if is_export else 10)
        arrow_end = QPointF(32, 42 if is_export else 24)
        head = QPolygonF(
            [
                QPointF(32, arrow_end.y()),
                QPointF(25, arrow_end.y() + (7 if is_export else -7)),
                QPointF(39, arrow_end.y() + (7 if is_export else -7)),
            ]
        )

        painter.setPen(QPen(QColor(THEME_PRIMARY_HOVER), 3, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(QLineF(arrow_start, arrow_end))
        painter.setBrush(QColor(THEME_PRIMARY_HOVER))
        painter.setPen(Qt.NoPen)
        painter.drawPolygon(head)


class ModernLoadingDialog(QDialog):
    def __init__(
        self,
        parent=None,
        title="Starting Ollama",
        message="Connecting to the local AI service...",
        icon_kind="ai",
    ):
        super().__init__(parent)
        self.icon_kind = icon_kind
        self.setWindowTitle(title)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setWindowModality(Qt.WindowModal)
        self.setModal(True)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumWidth(560)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(24, 24, 24, 24)

        panel = QFrame(self)
        panel.setObjectName("loadingPanel")
        panel.setMinimumWidth(512)
        panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        shadow = QGraphicsDropShadowEffect(panel)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(15, 23, 42, 45))
        panel.setGraphicsEffect(shadow)

        row = QHBoxLayout(panel)
        row.setContentsMargins(32, 30, 32, 30)
        row.setSpacing(20)

        title_label = QLabel(title)
        title_label.setObjectName("loadingTitle")
        message_label = QLabel(message)
        message_label.setObjectName("loadingMessage")
        message_label.setWordWrap(True)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(6)
        text_layout.addWidget(title_label)
        text_layout.addWidget(message_label)

        row.addWidget(self._create_icon(panel, icon_kind), 0, Qt.AlignTop)
        row.addLayout(text_layout, 1)
        row.addWidget(LoadingRing(panel), 0, Qt.AlignVCenter)
        outer_layout.addWidget(panel)

        self.setStyleSheet(
            """
            QFrame#loadingPanel {
                background-color: #FFFFFF;
                border: 1px solid #E5EAF0;
                border-radius: 8px;
            }
            QLabel#loadingTitle {
                color: #174A8B;
                font-size: 20px;
                font-weight: bold;
            }
            QLabel#loadingMessage {
                color: #57606A;
                font-size: 15px;
            }
            """
        )

    def _create_icon(self, parent, icon_kind):
        if icon_kind == "ai":
            return AiChipIcon(parent)
        if icon_kind in ("import", "export"):
            return FileTransferIcon(icon_kind, parent)
        return AiChipIcon(parent)

    def reject(self):
        return

    def showEvent(self, event):
        super().showEvent(event)
        self._center_on_parent()

    def _center_on_parent(self):
        parent = self.parentWidget()
        if parent is None:
            return
        parent_geometry = parent.frameGeometry()
        dialog_geometry = self.frameGeometry()
        dialog_geometry.moveCenter(parent_geometry.center())
        self.move(dialog_geometry.topLeft())
