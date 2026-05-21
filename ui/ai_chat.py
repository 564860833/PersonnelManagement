import logging
import re
import threading
import markdown
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QTextEdit, QLineEdit,
                             QPushButton, QLabel, QHBoxLayout, QComboBox, QGroupBox, QMessageBox)
from PyQt5.QtCore import pyqtSignal, QObject
from services.ai_engine import AIQueryEngine
from services.ai_types import AIAnswer, AIConversationState
from services.ollama_manager import APP_OLLAMA_HOST, ensure_ollama_ready, fetch_ollama_models
from ui.styles import DIALOG_BASE_STYLE, DIALOG_BUTTON_STYLE

logger = logging.getLogger('AIChat')


META_LINE_PATTERNS = (
    r"^(?:#+\s*)?(?:最终答案|最终回答|答案|回答|结论)\s*[:：]?\s*$",
    r"^(?:#+\s*)?(?:严格输出要求|内部回答格式|工具调用结果|程序检索结果|动作模式)\s*[:：]?.*$",
)

META_PHRASE_PATTERNS = (
    r"严格输出要求[^。！？\n]*[。！？]?",
    r"内部回答格式[^。！？\n]*[。！？]?",
    r"用户的问题是[^。！？\n]*[。！？]?",
    r"根据(?:上述|本轮|当前)?(?:的)?(?:工具调用结果|程序检索结果)[^，。！？\n]*(?:，|。|显示|可知|统计)?",
    r"工具调用结果中的?[A-Za-z_]+统计[，,]?",
    r"程序检索结果显示[，,]?",
    r"最终答案[:：]?",
)


def clean_ai_response(response: str, action_type: str = "") -> str:
    """Remove internal prompt leakage and keep the user-facing answer concise."""
    original = (response or "").strip()
    if not original:
        return ""

    lines = []
    for raw_line in original.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw_line.strip()
        if not line:
            lines.append("")
            continue
        if any(re.search(pattern, line, flags=re.IGNORECASE) for pattern in META_LINE_PATTERNS):
            continue
        lines.append(raw_line.rstrip())

    cleaned = "\n".join(lines).strip()
    for pattern in META_PHRASE_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(?:count_rows|semantic_search|list_rows|distribution|aggregate|boolean_check)\b", "", cleaned)
    cleaned = _normalise_answer_spacing(cleaned)

    if action_type in {"count", "aggregate", "boolean"}:
        compact = _compact_business_answer(cleaned, action_type)
        if compact:
            cleaned = compact

    return cleaned.strip() or original


def _compact_business_answer(text: str, action_type: str) -> str:
    without_tables = "\n".join(
        line for line in text.splitlines()
        if not line.lstrip().startswith("|") and not re.match(r"^\s*-{3,}\s*$", line)
    )
    sentences = _answer_sentences(without_tables)
    if not sentences:
        return _normalise_answer_spacing(without_tables)

    if action_type == "boolean":
        for sentence in sentences:
            if sentence.startswith(("是", "否", "抱歉")):
                return sentence
        for sentence in sentences:
            if re.search(r"(?:^|[，,。])(?:是|否)(?:[，,。]|$)", sentence):
                return sentence

    if action_type == "count":
        for sentence in sentences:
            if re.search(r"\d+\s*(?:条记录|条|人|个|名|项|次)", sentence):
                return sentence

    if action_type == "aggregate":
        for sentence in sentences:
            if any(word in sentence for word in ("最高", "最低", "最早", "最晚", "平均", "最多", "最少", "数值", "结果")):
                return sentence

    return sentences[0]


def _answer_sentences(text: str) -> list:
    text = _normalise_answer_spacing(text)
    if not text:
        return []
    parts = re.findall(r"[^。！？\n]+[。！？]?", text)
    return [part.strip() for part in parts if part.strip()]


def _normalise_answer_spacing(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text or "")
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"^[，,。；;：:\s]+", "", text.strip())
    return text


class AIWorker(QObject):
    """在后台线程运行结构化 AI 查询管线。"""
    finished = pyqtSignal(object)

    def __init__(self, engine, question, analysis_payload, session_state, model_name, n_ctx):
        super().__init__()
        self.engine = engine
        self.question = question
        self.analysis_payload = analysis_payload
        self.session_state = session_state
        self.model_name = model_name
        self.n_ctx = n_ctx
        self._is_running = True

    def stop(self):
        self._is_running = False

    def run(self):
        try:
            logger.debug("正在运行 AI 查询管线，model=%s, ctx=%s", self.model_name, self.n_ctx)
            answer = self.engine.answer(
                self.question,
                self.analysis_payload,
                self.session_state,
                model_name=self.model_name,
                n_ctx=self.n_ctx,
            )
            if self._is_running:
                self.finished.emit(answer)
        except Exception as e:
            if self._is_running:
                logger.exception("AI 查询管线运行出错")
                self.finished.emit(f"AI 运行出错: {str(e)}")


class AIChatDialog(QDialog):
    def __init__(self, analysis_payload, parent=None):
        super().__init__(parent)
        self.analysis_payload = analysis_payload
        # 轻量历史只用于显示和摘要；待澄清计划由 session_state 显式保存。
        self.history_messages = []
        self.query_engine = AIQueryEngine()
        self.session_state = AIConversationState()
        self._pending_action_type = ""
        self.setWindowTitle("智能分析助手 (多轮对话版)")
        self.resize(900, 800)
        self.setup_ui()

    def closeEvent(self, event):
        if hasattr(self, 'worker') and self.worker:
            self.worker.stop()
        event.accept()

    def get_local_models(self):
        available, models = fetch_ollama_models(timeout=3)
        return models if available else []

    def refresh_models(self):
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
                if not status.embedding_model_available:
                    detail += "，语义检索降级"
                self.status_label.setText(f"就绪 ({detail})")
        else:
            self.model_combo.addItem("未检测到可用模型")
            if status.local_model_names and status.service_available:
                self.status_label.setText(f"专用 Ollama 端口 {APP_OLLAMA_HOST} 已占用，但未加载程序目录 models")
            elif status.local_model_names:
                self.status_label.setText(f"检测到程序目录 models，但无法启动或连接专用 Ollama ({APP_OLLAMA_HOST})")
            else:
                self.status_label.setText("未检测到模型；请确认程序目录 models")

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
        settings_layout.addWidget(self.model_combo)

        self.refresh_btn = QPushButton("刷新列表")
        self.refresh_btn.setObjectName("secondaryButton")
        self.refresh_btn.clicked.connect(self.refresh_models)
        settings_layout.addWidget(self.refresh_btn)

        settings_layout.addSpacing(20)
        settings_layout.addWidget(QLabel("上下文长度:"))
        self.ctx_combo = QComboBox()
        self.ctx_combo.addItems(["2048", "4096", "8192", "16384"])
        self.ctx_combo.setCurrentIndex(1)
        settings_layout.addWidget(self.ctx_combo)

        # 新增：清空对话按钮
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
        """清空对话历史"""
        self.history_messages = []
        self.session_state = AIConversationState()
        self.chat_history.clear()
        self.chat_history.append("<p style='color:gray;'><i>对话已清空</i></p>")

    def start_inference(self):
        question = self.input_field.text().strip()
        if not question: return

        model_name = self.model_combo.currentText().strip()
        if not model_name or "未检测到模型" in model_name:
            model_name = ""

        ctx_text = self.ctx_combo.currentText().split()[0]
        n_ctx = int(ctx_text)

        # 1. 更新 UI 显示
        self.chat_history.append(f"<b>我:</b> {question}")
        self.input_field.clear()
        self.send_btn.setEnabled(False)
        self.status_label.setText("AI 正在解析和计算...")

        # 长期历史只保存原始问题和最终摘要；澄清状态由 AIConversationState 单独管理。
        self.history_messages.append({"role": "user", "content": question})

        self.worker = AIWorker(
            self.query_engine,
            question,
            self.analysis_payload,
            self.session_state,
            model_name,
            n_ctx,
        )
        self.worker_thread = threading.Thread(target=self.worker.run)
        self.worker_thread.daemon = True
        self.worker.finished.connect(self.handle_response)
        self.worker_thread.start()

    def handle_response(self, response):
        if isinstance(response, AIAnswer):
            self.session_state = response.session_state
            final_answer = response.text.strip()
            action_type = response.intent
            if response.clarification_required:
                self.status_label.setText("等待澄清")
            else:
                self.status_label.setText("就绪")
        else:
            action_type = getattr(self, "_pending_action_type", "")
            final_answer = clean_ai_response(str(response), action_type)
            self._pending_action_type = ""
            self.status_label.setText("就绪")

        # 4. 将 AI 的回复存入历史记录，实现多轮记忆
        self.history_messages.append({"role": "assistant", "content": final_answer})

        # 渲染 Markdown
        try:
            answer_html = markdown.markdown(final_answer, extensions=['extra', 'tables'])
        except Exception as e:
            logger.error(f"Markdown 渲染失败: {e}")
            answer_html = final_answer.replace('\n', '<br>')

        styled_html = f"""
        <style>
            table {{ border-collapse: collapse; width: 100%; margin: 10px 0; }}
            th, td {{ border: 1px solid #ddd; padding: 8px; }}
            th {{ background-color: #f2f2f2; }}
        </style>
        <div>{answer_html}</div>
        """

        self.chat_history.append(f"<b>AI:</b><br>{styled_html}<hr>")

        # 自动滚动
        self.chat_history.verticalScrollBar().setValue(self.chat_history.verticalScrollBar().maximum())
        self.send_btn.setEnabled(True)
        if action_type and action_type != "unsupported" and not isinstance(response, AIAnswer):
            self.status_label.setText("就绪")
