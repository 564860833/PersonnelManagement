import html
import logging
import threading

import markdown
from PyQt5.QtCore import QObject, Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from services.ai_context import next_context_length, recommend_context_length
from services.ai_direct import ask_model, is_context_length_error
from services.ollama_manager import APP_OLLAMA_HOST, fetch_ollama_models
from ui.styles import DIALOG_BASE_STYLE, DIALOG_BUTTON_STYLE

logger = logging.getLogger("AIChat")

MODEL_PLACEHOLDER = "未检测到可用模型"

AI_CHAT_STYLE = """
QFrame#aiHeaderPanel,
QFrame#aiInputPanel {
    background-color: #FFFFFF;
    border: 1px solid #E5EAF0;
    border-radius: 8px;
}
QLabel#aiDialogTitle {
    color: #174A8B;
    font-size: 20px;
    font-weight: bold;
}
QLabel#aiContextLabel,
QLabel#aiFooterStatus {
    color: #57606A;
}
QLabel#aiModelStatus {
    padding: 4px 10px;
    border-radius: 5px;
    font-weight: bold;
}
QLabel#aiModelStatus[state="ready"] {
    color: #174A8B;
    background-color: #EAF2FB;
    border: 1px solid #8BB6E8;
}
QLabel#aiModelStatus[state="warning"] {
    color: #8F1D16;
    background-color: #FFF1F0;
    border: 1px solid #F3B5AD;
}
QLabel#aiModelStatus[state="busy"] {
    color: #174A8B;
    background-color: #F7FBFF;
    border: 1px solid #8BB6E8;
}
QTextEdit#aiHistory {
    background-color: #FFFFFF;
    border: 1px solid #E5EAF0;
    border-radius: 8px;
    padding: 12px;
}
QLineEdit#aiQuestionInput {
    min-height: 38px;
}
"""

ANALYSIS_DOCUMENT_STYLE = """
body {
    font-family: "Microsoft YaHei", "Microsoft YaHei UI", sans-serif;
    color: #24292F;
    font-size: 14px;
}
.message {
    margin: 0 0 18px 0;
}
p {
    margin: 0 0 9px 0;
}
ul, ol {
    margin: 6px 0 9px 22px;
}
li {
    margin-bottom: 4px;
}
hr {
    border: 0;
    border-top: 1px solid #E5EAF0;
    margin: 12px 0;
}
"""


class AIWorker(QObject):
    """在后台线程调用本地 Ollama 模型。"""

    finished = pyqtSignal(object)
    failed = pyqtSignal(str)
    context_changed = pyqtSignal(int)

    def __init__(
        self,
        question,
        analysis_payload,
        model_name,
        n_ctx,
        history_messages=None,
        max_n_ctx=None,
    ):
        super().__init__()
        self.question = question
        self.analysis_payload = analysis_payload
        self.model_name = model_name
        self.n_ctx = n_ctx
        self.max_n_ctx = max_n_ctx or n_ctx
        self.history_messages = [dict(message) for message in history_messages or []]
        self._is_running = True

    def stop(self):
        self._is_running = False

    def run(self):
        try:
            logger.debug("正在调用 Ollama 模型，model=%s, ctx=%s", self.model_name, self.n_ctx)
            answer = self._ask_with_context_retry()
            if self._is_running:
                self.finished.emit(answer or "模型没有返回内容。")
        except Exception as e:
            if self._is_running:
                logger.exception("AI 模型调用出错")
                self.failed.emit(str(e))

    def _ask_with_context_retry(self):
        while True:
            try:
                return self._ask_with_context(self.n_ctx)
            except Exception as e:
                if not is_context_length_error(e):
                    raise

                retry_n_ctx = next_context_length(self.n_ctx, self.max_n_ctx)
                if not retry_n_ctx:
                    raise

                logger.info(
                    "AI 上下文不足，准备自动升档重试: model=%s, ctx=%s -> %s",
                    self.model_name,
                    self.n_ctx,
                    retry_n_ctx,
                )
                self.n_ctx = retry_n_ctx
                self.context_changed.emit(retry_n_ctx)

    def _ask_with_context(self, n_ctx):
        return ask_model(
            self.question,
            self.analysis_payload,
            self.model_name,
            n_ctx,
            history_messages=self.history_messages,
        )


def render_message_html(role: str, content: str, is_error: bool = False) -> str:
    if is_error:
        body_html = html.escape(str(content)).replace("\n", "<br>")
        return render_bubble_html(
            body_html,
            align="left",
            avatar="🤖",
            avatar_background="#FFF1F0",
            avatar_color="#8F1D16",
            background="#FFF1F0",
            border="#F3B5AD",
            text_color="#8F1D16",
            corner="left",
        )
    elif role == "user":
        body_html = html.escape(str(content)).replace("\n", "<br>")
        return render_bubble_html(
            body_html,
            align="right",
            avatar="👤",
            avatar_background="#EAF2FB",
            avatar_color="#174A8B",
            background="#2563EB",
            border="#2563EB",
            text_color="#FFFFFF",
            corner="right",
        )
    else:
        body_html = render_markdown_html(content)
        return render_bubble_html(
            body_html,
            align="left",
            avatar="🤖",
            avatar_background="#EAF2FB",
            avatar_color="#174A8B",
            background="#F6F8FA",
            border="#E5E7EB",
            text_color="#24292F",
            corner="left",
        )


def render_bubble_html(
    body_html: str,
    align: str,
    avatar: str,
    avatar_background: str,
    avatar_color: str,
    background: str,
    border: str,
    text_color: str,
    corner: str = "left",
) -> str:
    title_align = "right" if align == "right" else "left"
    tail_radius = (
        "border-top-left-radius: 4px;"
        if corner == "left"
        else "border-top-right-radius: 4px;"
    )
    avatar_cell = f"""
        <td width="32" valign="top" align="center" style="border: none; padding: 0;">
            <div style="width: 28px; height: 28px; line-height: 28px; text-align: center; border-radius: 14px; background-color: {avatar_background}; color: {avatar_color}; font-size: 15px;">{avatar}</div>
        </td>
    """
    gap_cell = '<td width="8" style="border: none; padding: 0;"></td>'
    bubble_cell = f"""
        <td valign="top" align="{title_align}" style="border: none; padding: 0;">
            <table cellspacing="0" cellpadding="0" style="border: none; margin: 0;">
                <tr>
                    <td align="{title_align}" style="border: none; padding: 0;">
                        <div style="background-color: {background}; color: {text_color}; border: 1px solid {border}; border-radius: 12px; {tail_radius} padding: 10px 14px; text-align: left;">
                            {body_html}
                        </div>
                    </td>
                </tr>
            </table>
        </td>
    """
    spacer_cell = '<td width="24%" style="border: none; padding: 0;"></td>'
    if align == "right":
        message_cells = f"{bubble_cell}{gap_cell}{avatar_cell}"
        leading_spacer = spacer_cell
        trailing_spacer = ""
    else:
        message_cells = f"{avatar_cell}{gap_cell}{bubble_cell}"
        leading_spacer = ""
        trailing_spacer = spacer_cell

    return f"""
    <div class="message">
        <table width="100%" cellspacing="0" cellpadding="0" style="border: none; margin: 0;">
            <tr>
                {leading_spacer}
                <td width="76%" align="{title_align}" style="border: none; padding: 0;">
                    <table cellspacing="0" cellpadding="0" align="{title_align}" style="border: none; margin: 0;">
                        <tr>
                            {message_cells}
                        </tr>
                    </table>
                </td>
                {trailing_spacer}
            </tr>
        </table>
    </div>
    """


def render_markdown_html(content: str) -> str:
    try:
        rendered = markdown.markdown(str(content), extensions=["extra", "tables"])
        return style_markdown_tables(rendered)
    except Exception as e:
        logger.error("Markdown 渲染失败: %s", e)
        return html.escape(str(content)).replace("\n", "<br>")


def style_markdown_tables(rendered_html: str) -> str:
    return (
        str(rendered_html)
        .replace(
            "<table>",
            '<table style="border-collapse: collapse; width: 100%; margin: 8px 0;">',
        )
        .replace(
            "<th>",
            '<th style="border: 1px solid #D0D7DE; padding: 7px 9px; background-color: #EAF2FB; color: #174A8B; font-weight: bold;">',
        )
        .replace(
            "<td>",
            '<td style="border: 1px solid #D0D7DE; padding: 7px 9px;">',
        )
    )


class AIChatDialog(QDialog):
    def __init__(self, analysis_payload, parent=None):
        super().__init__(parent)
        self.analysis_payload = analysis_payload
        self.history_messages = []
        self.current_context_recommendation = None
        self.is_inference_running = False
        self.worker = None
        self.worker_thread = None
        self.setWindowTitle("智能分析助手")
        self.resize(960, 760)
        self.setup_ui()

    def closeEvent(self, event):
        if self.worker:
            self.worker.stop()
        event.accept()

    def refresh_models(self):
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        available, models = fetch_ollama_models(timeout=3)
        if models:
            self.model_combo.addItems(models)
            self.set_model_status("ready", f"已连接，{len(models)} 个模型")
            self.status_label.setText(f"就绪，端口 {APP_OLLAMA_HOST}")
        else:
            self.model_combo.addItem(MODEL_PLACEHOLDER)
            if available:
                self.set_model_status("warning", "未检测到模型")
                self.status_label.setText(f"Ollama 已连接，但未检测到可用模型 ({APP_OLLAMA_HOST})")
            else:
                self.set_model_status("warning", "服务未连接")
                self.status_label.setText(f"无法连接专用 Ollama ({APP_OLLAMA_HOST})")
        self.model_combo.blockSignals(False)
        self.refresh_context_recommendation()
        self.update_action_state()

    def refresh_context_recommendation(self, model_name=None):
        if model_name is None:
            model_name = self.selected_model_name()
        elif not self.is_valid_model_name(model_name):
            model_name = ""

        self.current_context_recommendation = recommend_context_length(model_name)
        self.update_context_label(self.current_context_recommendation.n_ctx)
        return self.current_context_recommendation

    def update_context_label(self, n_ctx):
        if self.current_context_recommendation:
            self.ctx_label.setText(f"{int(n_ctx)}（{self.current_context_recommendation.reason}）")
        else:
            self.ctx_label.setText(str(n_ctx))

        try:
            is_running = self.is_inference_running
        except (AttributeError, RuntimeError):
            is_running = False

        if is_running:
            self.status_label.setText(f"上下文已自动升档到 {int(n_ctx)}，正在重试分析...")

    def setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        self.setStyleSheet(DIALOG_BASE_STYLE + DIALOG_BUTTON_STYLE + AI_CHAT_STYLE)

        header_panel = QFrame()
        header_panel.setObjectName("aiHeaderPanel")
        header_layout = QVBoxLayout(header_panel)
        header_layout.setContentsMargins(16, 14, 16, 14)
        header_layout.setSpacing(10)

        title_row = QHBoxLayout()
        title_row.setSpacing(10)
        title_label = QLabel("智能分析")
        title_label.setObjectName("aiDialogTitle")
        self.model_status_label = QLabel("正在初始化")
        self.model_status_label.setObjectName("aiModelStatus")
        self.model_status_label.setProperty("state", "busy")
        title_row.addWidget(title_label)
        title_row.addStretch()
        title_row.addWidget(self.model_status_label, 0, Qt.AlignRight)
        header_layout.addLayout(title_row)

        settings_layout = QHBoxLayout()
        settings_layout.setSpacing(8)
        settings_layout.addWidget(QLabel("模型"))
        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(220)
        self.model_combo.currentTextChanged.connect(self.refresh_context_recommendation)
        settings_layout.addWidget(self.model_combo)

        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.setObjectName("secondaryButton")
        self.refresh_btn.clicked.connect(self.refresh_models)
        settings_layout.addWidget(self.refresh_btn)

        settings_layout.addSpacing(14)
        settings_layout.addWidget(QLabel("上下文"))
        self.ctx_label = QLabel("自动检测中...")
        self.ctx_label.setObjectName("aiContextLabel")
        settings_layout.addWidget(self.ctx_label, 1)

        self.clear_btn = QPushButton("清空对话")
        self.clear_btn.setObjectName("secondaryButton")
        self.clear_btn.clicked.connect(self.clear_chat)
        settings_layout.addWidget(self.clear_btn)
        header_layout.addLayout(settings_layout)
        layout.addWidget(header_panel)

        self.chat_history = QTextEdit()
        self.chat_history.setObjectName("aiHistory")
        self.chat_history.setReadOnly(True)
        self.chat_history.document().setDefaultStyleSheet(ANALYSIS_DOCUMENT_STYLE)
        layout.addWidget(self.chat_history, 1)

        input_panel = QFrame()
        input_panel.setObjectName("aiInputPanel")
        input_layout = QVBoxLayout(input_panel)
        input_layout.setContentsMargins(14, 12, 14, 12)
        input_layout.setSpacing(8)

        question_row = QHBoxLayout()
        question_row.setSpacing(8)
        self.input_field = QLineEdit()
        self.input_field.setObjectName("aiQuestionInput")
        self.input_field.setPlaceholderText("输入要分析的问题")
        self.input_field.returnPressed.connect(self.start_inference)

        self.send_btn = QPushButton("发送")
        self.send_btn.setObjectName("primaryButton")
        self.send_btn.setMinimumWidth(92)
        self.send_btn.clicked.connect(self.start_inference)
        self.send_btn.setDefault(True)

        question_row.addWidget(self.input_field, 1)
        question_row.addWidget(self.send_btn)
        input_layout.addLayout(question_row)

        self.status_label = QLabel("正在初始化...")
        self.status_label.setObjectName("aiFooterStatus")
        self.status_label.setWordWrap(True)
        input_layout.addWidget(self.status_label)
        layout.addWidget(input_panel)

        self.setLayout(layout)
        self.refresh_models()

    def clear_chat(self):
        """清空对话历史。"""
        self.history_messages = []
        self.chat_history.clear()
        self.status_label.setText("对话已清空，可继续提问。")

    def start_inference(self):
        question = self.input_field.text().strip()
        if not question:
            return

        model_name = self.selected_model_name()
        if not model_name:
            self.status_label.setText("未选择可用模型，无法发送分析请求。")
            self.update_action_state()
            return

        if self.is_inference_running:
            return

        recommendation = self.current_context_recommendation or self.refresh_context_recommendation(model_name)
        n_ctx = recommendation.n_ctx

        self.append_message("user", question)
        self.input_field.clear()
        self.is_inference_running = True
        self.set_model_status("busy", "分析中")
        self.status_label.setText("AI 正在选择数据列并分析...")
        self.update_action_state()

        history_snapshot = [dict(message) for message in self.history_messages]
        self.history_messages.append({"role": "user", "content": question})

        self.worker = AIWorker(
            question,
            self.analysis_payload,
            model_name,
            n_ctx,
            history_snapshot,
            recommendation.max_n_ctx,
        )
        self.worker_thread = threading.Thread(target=self.worker.run)
        self.worker_thread.daemon = True
        self.worker.context_changed.connect(self.update_context_label)
        self.worker.finished.connect(self.handle_response)
        self.worker.failed.connect(self.handle_error)
        self.worker_thread.start()

    def handle_response(self, response):
        final_answer = str(response).strip()
        self.history_messages.append({"role": "assistant", "content": final_answer})
        self.append_message("assistant", final_answer)
        self.finish_inference("就绪")

    def handle_error(self, message):
        error_text = str(message).strip() or "未知错误"
        self.append_message("assistant", f"AI 运行出错: {error_text}", is_error=True)
        self.finish_inference(f"分析失败：{error_text}")

    def append_message(self, role: str, content: str, is_error: bool = False):
        self.chat_history.append(render_message_html(role, content, is_error=is_error))
        self.chat_history.verticalScrollBar().setValue(self.chat_history.verticalScrollBar().maximum())

    def finish_inference(self, status_text: str):
        self.is_inference_running = False
        self.worker = None
        self.set_model_status("ready" if self.selected_model_name() else "warning", self.model_ready_text())
        self.status_label.setText(status_text)
        self.update_action_state()

    def update_action_state(self):
        has_model = bool(self.selected_model_name())
        self.send_btn.setEnabled(has_model and not self.is_inference_running)
        self.input_field.setEnabled(not self.is_inference_running)
        self.model_combo.setEnabled(not self.is_inference_running)
        self.refresh_btn.setEnabled(not self.is_inference_running)
        self.clear_btn.setEnabled(not self.is_inference_running)

    def selected_model_name(self) -> str:
        model_name = self.model_combo.currentText().strip()
        return model_name if self.is_valid_model_name(model_name) else ""

    def is_valid_model_name(self, model_name: str) -> bool:
        model_name = (model_name or "").strip()
        return bool(model_name and model_name != MODEL_PLACEHOLDER and not model_name.startswith("未检测到"))

    def set_model_status(self, state: str, text: str):
        self.model_status_label.setText(text)
        self.model_status_label.setProperty("state", state)
        self.refresh_widget_style(self.model_status_label)

    def model_ready_text(self) -> str:
        if self.selected_model_name():
            return "已连接"
        return "未检测到模型"

    def refresh_widget_style(self, widget):
        if not hasattr(widget, "style"):
            return
        style = widget.style()
        style.unpolish(widget)
        style.polish(widget)
