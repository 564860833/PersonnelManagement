import logging
import threading

import markdown
from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtWidgets import (
    QComboBox,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from services.ai_context import next_context_length, recommend_context_length
from services.ai_direct import ask_model, is_context_length_error
from services.ollama_manager import APP_OLLAMA_HOST, ensure_ollama_ready, fetch_ollama_models
from ui.styles import DIALOG_BASE_STYLE, DIALOG_BUTTON_STYLE

logger = logging.getLogger("AIChat")


class AIWorker(QObject):
    """在后台线程调用本地 Ollama 模型。"""

    finished = pyqtSignal(object)
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
                self.finished.emit(f"AI 运行出错: {str(e)}")

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


class AIChatDialog(QDialog):
    def __init__(self, analysis_payload, parent=None):
        super().__init__(parent)
        self.analysis_payload = analysis_payload
        self.history_messages = []
        self.current_context_recommendation = None
        self.setWindowTitle("智能分析助手")
        self.resize(900, 800)
        self.setup_ui()

    def closeEvent(self, event):
        if hasattr(self, "worker") and self.worker:
            self.worker.stop()
        event.accept()

    def get_local_models(self):
        available, models = fetch_ollama_models(timeout=3)
        return models if available else []

    def refresh_models(self):
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        status = ensure_ollama_ready(start_if_needed=True)
        models = status.service_models
        if models:
            self.model_combo.addItems(models)
            if status.warning and status.local_model_names:
                self.status_label.setText(f"专用 Ollama 端口 {APP_OLLAMA_HOST} 已占用，但未加载程序目录 models")
            else:
                detail = f"已识别到 {len(models)} 个模型"
                if status.local_models_dir:
                    detail += "，使用程序目录 models"
                detail += f"，端口 {APP_OLLAMA_HOST}"
                self.status_label.setText(f"就绪 ({detail})")
        else:
            self.model_combo.addItem("未检测到可用模型")
            if status.local_model_names and status.service_available:
                self.status_label.setText(f"专用 Ollama 端口 {APP_OLLAMA_HOST} 已占用，但未加载程序目录 models")
            elif status.local_model_names:
                self.status_label.setText(f"检测到程序目录 models，但无法启动或连接专用 Ollama ({APP_OLLAMA_HOST})")
            else:
                self.status_label.setText("未检测到模型；请确认程序目录 models")
        self.model_combo.blockSignals(False)
        self.refresh_context_recommendation()

    def refresh_context_recommendation(self, model_name=None):
        if model_name is None:
            model_name = self.model_combo.currentText().strip()
        if not model_name or "未检测到模型" in model_name:
            model_name = ""

        self.current_context_recommendation = recommend_context_length(model_name)
        self.update_context_label(self.current_context_recommendation.n_ctx)
        return self.current_context_recommendation

    def update_context_label(self, n_ctx):
        if self.current_context_recommendation:
            self.ctx_label.setText(f"{int(n_ctx)}（{self.current_context_recommendation.reason}）")
        else:
            self.ctx_label.setText(str(n_ctx))

    def setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        self.setStyleSheet(DIALOG_BASE_STYLE + DIALOG_BUTTON_STYLE)

        settings_group = QGroupBox("Ollama 模型设置")
        settings_layout = QHBoxLayout()
        settings_layout.setSpacing(8)

        settings_layout.addWidget(QLabel("选择模型:"))
        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(180)
        self.model_combo.currentTextChanged.connect(self.refresh_context_recommendation)
        settings_layout.addWidget(self.model_combo)

        self.refresh_btn = QPushButton("刷新列表")
        self.refresh_btn.setObjectName("secondaryButton")
        self.refresh_btn.clicked.connect(self.refresh_models)
        settings_layout.addWidget(self.refresh_btn)

        settings_layout.addSpacing(20)
        settings_layout.addWidget(QLabel("上下文长度:"))
        self.ctx_label = QLabel("自动检测中...")
        self.ctx_label.setObjectName("dialogSubtitle")
        settings_layout.addWidget(self.ctx_label)

        self.clear_btn = QPushButton("清空对话")
        self.clear_btn.setObjectName("secondaryButton")
        self.clear_btn.clicked.connect(self.clear_chat)
        settings_layout.addWidget(self.clear_btn)

        settings_layout.addStretch()
        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)

        self.chat_history = QTextEdit()
        self.chat_history.setReadOnly(True)
        layout.addWidget(self.chat_history)

        input_layout = QHBoxLayout()
        input_layout.setSpacing(8)
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("请输入您的问题...")
        self.input_field.returnPressed.connect(self.start_inference)

        self.send_btn = QPushButton("发送")
        self.send_btn.setObjectName("primaryButton")
        self.send_btn.clicked.connect(self.start_inference)
        self.send_btn.setDefault(True)

        input_layout.addWidget(self.input_field)
        input_layout.addWidget(self.send_btn)
        layout.addLayout(input_layout)

        self.status_label = QLabel("正在初始化...")
        self.status_label.setObjectName("dialogSubtitle")
        layout.addWidget(self.status_label)

        self.setLayout(layout)
        self.refresh_models()

    def clear_chat(self):
        """清空对话历史。"""
        self.history_messages = []
        self.chat_history.clear()
        self.chat_history.append("<p style='color:gray;'><i>对话已清空</i></p>")

    def start_inference(self):
        question = self.input_field.text().strip()
        if not question:
            return

        model_name = self.model_combo.currentText().strip()
        if not model_name or "未检测到模型" in model_name:
            model_name = ""

        recommendation = self.current_context_recommendation or self.refresh_context_recommendation()
        n_ctx = recommendation.n_ctx

        self.chat_history.append(f"<b>我:</b> {question}")
        self.input_field.clear()
        self.send_btn.setEnabled(False)
        self.status_label.setText("AI 正在选择数据列并分析...")
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
        self.worker_thread.start()

    def handle_response(self, response):
        final_answer = str(response).strip()
        self.status_label.setText("就绪")
        self.history_messages.append({"role": "assistant", "content": final_answer})

        try:
            answer_html = markdown.markdown(final_answer, extensions=["extra", "tables"])
        except Exception as e:
            logger.error("Markdown 渲染失败: %s", e)
            answer_html = final_answer.replace("\n", "<br>")

        styled_html = f"""
        <style>
            table {{ border-collapse: collapse; width: 100%; margin: 10px 0; }}
            th, td {{ border: 1px solid #ddd; padding: 8px; }}
            th {{ background-color: #f2f2f2; }}
        </style>
        <div>{answer_html}</div>
        """

        self.chat_history.append(f"<b>AI:</b><br>{styled_html}<hr>")
        self.chat_history.verticalScrollBar().setValue(self.chat_history.verticalScrollBar().maximum())
        self.send_btn.setEnabled(True)
