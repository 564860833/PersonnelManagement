from PyQt5.QtCore import QEasingCurve, QEvent, QPropertyAnimation, QTimer, Qt
from PyQt5.QtWidgets import QApplication, QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel


TOAST_STYLES = {
    "success": """
        QFrame {
            background-color: #1E5AA8;
            border: 1px solid #174A8B;
            border-radius: 8px;
        }
        QLabel {
            color: white;
            font-weight: 500;
        }
    """,
    "info": """
        QFrame {
            background-color: #1E5AA8;
            border: 1px solid #174A8B;
            border-radius: 8px;
        }
        QLabel {
            color: white;
            font-weight: 500;
        }
    """,
}


class ToastWidget(QFrame):
    def __init__(self, parent):
        super().__init__(parent)
        self._target = parent
        self._margin = 18
        self._duration = 2500
        self._text_safe_padding = 10
        self._message = ""

        self.setObjectName("ToastWidget")
        self.setFocusPolicy(Qt.NoFocus)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.hide()

        self.label = QLabel(self)
        self.label.setFont(self._target.font())
        self.label.setWordWrap(False)
        self.label.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.addWidget(self.label)

        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        self.opacity_effect.setOpacity(1.0)

        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.fade_out)

        self.fade_animation = QPropertyAnimation(self.opacity_effect, b"opacity", self)
        self.fade_animation.setDuration(220)
        self.fade_animation.setEasingCurve(QEasingCurve.OutCubic)
        self.fade_animation.finished.connect(self.finish_fade)

        self._target.installEventFilter(self)

    def show_message(self, message: str, duration: int = 2500, kind: str = "success"):
        self._duration = duration
        self.fade_animation.stop()
        self.hide_timer.stop()
        self.opacity_effect.setOpacity(1.0)
        self.setStyleSheet(TOAST_STYLES.get(kind, TOAST_STYLES["success"]))
        self._message = message
        self.setToolTip(message)
        self.reposition()
        self.show()
        self.raise_()
        self.hide_timer.start(self._duration)

    def reposition(self):
        if self._target is None:
            return

        available_width = max(220, self._target.width() - self._margin * 2)
        max_width = min(720, available_width)
        label_width = max_width - 32 - self._text_safe_padding
        display_text, display_width = self.fit_message_to_two_lines(label_width)
        self.label.setText(display_text)
        self.label.setFixedWidth(min(label_width, display_width + self._text_safe_padding))

        self.setMaximumWidth(max_width)
        self.adjustSize()

        status_bar_height = 0
        status_bar = getattr(self._target, "status_bar", None)
        if status_bar is not None and status_bar.isVisible():
            status_bar_height = status_bar.height()

        x = self._margin
        y = max(self._margin, self._target.height() - status_bar_height - self.height() - self._margin)
        self.move(x, y)

    def fit_message_to_two_lines(self, label_width: int):
        metrics = self.label.fontMetrics()
        text_width = metrics.horizontalAdvance(self._message)
        if text_width <= label_width:
            return self._message, text_width

        safe_line_width = max(1, label_width - self._text_safe_padding)
        first_line_length = self.find_fit_length(self._message, safe_line_width)
        if first_line_length <= 0:
            return metrics.elidedText(self._message, Qt.ElideRight, safe_line_width), label_width

        first_line = self._message[:first_line_length].rstrip()
        second_line = self._message[first_line_length:].lstrip()
        if metrics.horizontalAdvance(second_line) > safe_line_width:
            second_line = metrics.elidedText(second_line, Qt.ElideRight, safe_line_width)

        return f"{first_line}\n{second_line}", label_width

    def find_fit_length(self, text: str, max_width: int) -> int:
        metrics = self.label.fontMetrics()
        low = 0
        high = len(text)
        best = 0

        while low <= high:
            mid = (low + high) // 2
            if metrics.horizontalAdvance(text[:mid]) <= max_width:
                best = mid
                low = mid + 1
            else:
                high = mid - 1

        return best

    def fade_out(self):
        self.fade_animation.stop()
        self.fade_animation.setStartValue(self.opacity_effect.opacity())
        self.fade_animation.setEndValue(0.0)
        self.fade_animation.start()

    def finish_fade(self):
        if self.opacity_effect.opacity() <= 0.05:
            self.hide()

    def eventFilter(self, watched, event):
        if watched == self._target and event.type() in (
            QEvent.Resize,
            QEvent.Move,
            QEvent.Show,
            QEvent.WindowStateChange,
            QEvent.LayoutRequest,
        ):
            self.reposition()
        return super().eventFilter(watched, event)


def show_toast(parent, message: str, duration: int = 2500, kind: str = "success"):
    target = parent.window() if parent is not None else QApplication.activeWindow()
    if target is None:
        return None

    toast = getattr(target, "_toast_widget", None)
    if toast is None:
        toast = ToastWidget(target)
        target._toast_widget = toast

    toast.show_message(message, duration, kind)
    return toast
