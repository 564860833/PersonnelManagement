import json
import logging
import requests
import threading
import markdown
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QTextEdit, QLineEdit,
                             QPushButton, QLabel, QHBoxLayout, QComboBox, QGroupBox, QMessageBox)
from PyQt5.QtCore import pyqtSignal, QObject
from services.ai_analysis import build_analysis_context
from services.ai_tools import AIToolContext, run_analysis_tools
from services.ollama_manager import APP_OLLAMA_HOST, ensure_ollama_ready, fetch_ollama_models, ollama_api_url
from ui.styles import DIALOG_BASE_STYLE, DIALOG_BUTTON_STYLE

logger = logging.getLogger('AIChat')


class AIWorker(QObject):
    """在后台线程运行AI推理，调用本地 Ollama 接口"""
    finished = pyqtSignal(str)

    def __init__(self, model_name, messages, n_ctx):
        super().__init__()
        self.model_name = model_name
        self.messages = messages  # 接收完整的消息列表
        self.n_ctx = n_ctx
        self.api_url = ollama_api_url("/api/chat")
        self._is_running = True

    def stop(self):
        self._is_running = False

    def run(self):
        try:
            logger.debug(f"正在请求 Ollama 模型 [{self.model_name}], ctx={self.n_ctx}")

            payload = {
                "model": self.model_name,
                "messages": self.messages,  # 发送包含上下文的消息列表
                "stream": True,
                "options": {
                    "num_ctx": self.n_ctx,
                    "temperature": 0.1,
                    "top_p": 0.9,
                    "seed": 42,
                }
            }

            response = requests.post(self.api_url, json=payload, stream=True, timeout=300)

            if response.status_code == 404:
                self.finished.emit(f"错误: 找不到模型 `{self.model_name}`。")
                return

            response.raise_for_status()

            answer = ""
            for line in response.iter_lines():
                if not self._is_running:
                    response.close()
                    return

                if line:
                    data = json.loads(line)
                    answer += data.get('message', {}).get('content', '')

            if self._is_running:
                self.finished.emit(answer)

        except requests.exceptions.ConnectionError:
            self.finished.emit("错误: 无法连接到本地 Ollama 服务。\n请确认 Ollama 已在后台运行。")
        except Exception as e:
            if self._is_running:
                logger.exception("AI 运行出错")
                self.finished.emit(f"AI 运行出错: {str(e)}")


class AIChatDialog(QDialog):
    def __init__(self, analysis_payload, parent=None):
        super().__init__(parent)
        self.analysis_payload = analysis_payload
        # 新增：用于存储多轮对话的消息列表
        self.history_messages = []
        self.tool_context = AIToolContext(
            table_name=self.analysis_payload["table_name"],
            rows=self.analysis_payload["rows"],
            selected_fields=self.analysis_payload["selected_fields"],
            field_labels=self.analysis_payload["field_labels"],
            table_label=self.analysis_payload.get("table_label"),
        )
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
        self.chat_history.clear()
        self.chat_history.append("<p style='color:gray;'><i>对话已清空</i></p>")

    def build_round_context(self, question):
        tool_result = run_analysis_tools(
            table_name=self.analysis_payload["table_name"],
            rows=self.analysis_payload["rows"],
            selected_fields=self.analysis_payload["selected_fields"],
            field_labels=self.analysis_payload["field_labels"],
            user_question=question,
            table_label=self.analysis_payload.get("table_label"),
            tool_context=self.tool_context,
        )
        return build_analysis_context(
            table_name=self.analysis_payload["table_name"],
            rows=self.analysis_payload["rows"],
            selected_fields=self.analysis_payload["selected_fields"],
            field_labels=self.analysis_payload["field_labels"],
            user_question=question,
            table_label=self.analysis_payload.get("table_label"),
            tool_result=tool_result,
        )

    def prepare_round(self, question):
        tool_result = run_analysis_tools(
            table_name=self.analysis_payload["table_name"],
            rows=self.analysis_payload["rows"],
            selected_fields=self.analysis_payload["selected_fields"],
            field_labels=self.analysis_payload["field_labels"],
            table_label=self.analysis_payload.get("table_label"),
            user_question=question,
            tool_context=self.tool_context,
        )
        round_context = build_analysis_context(
            table_name=self.analysis_payload["table_name"],
            rows=self.analysis_payload["rows"],
            selected_fields=self.analysis_payload["selected_fields"],
            field_labels=self.analysis_payload["field_labels"],
            user_question=question,
            table_label=self.analysis_payload.get("table_label"),
            tool_result=tool_result,
        )
        return tool_result, round_context

    def system_prompt(self):
        return (
            "### 角色\n"
            "你是一名专业的人力资源数据分析师。\n\n"
            "### 可信数据规则\n"
            "1. 只能根据每轮用户消息中提供的【工具调用结果】和【匹配明细】回答。\n"
            "2. 涉及总数、比例、分布、排行时，必须使用工具调用结果中的确定性统计，不能自行估算。\n"
            "3. 如果只提供匹配明细，明细只能用于解释该问题，不能当作全量数据。\n"
            "4. 如果上下文无法支持用户问题，请回答“抱歉，根据现有数据无法回答该问题”。\n"
            "5. 不要生成 SQL，不要声称已经执行 SQL，不要编造不存在的字段、人员或政策。\n"
            "6. 晋升相关结论只能解释已导入字段，不得根据任职时间或职级顺序自行判断政策资格。\n\n"
            "7. 如果工具结果提示“数据被截断”或“仅展示前 X 条”，必须先说明匹配总数，"
            "再列出样本，并建议用户通过界面筛选功能查看完整名单。\n\n"
            "### 输出规则\n"
            "1. 多条数据优先使用 Markdown 表格。\n"
            "2. 回复要简洁、专业，最后只做必要总结。\n"
        )

    def start_inference(self):
        question = self.input_field.text().strip()
        if not question: return

        model_name = self.model_combo.currentText().strip()
        if not model_name or "未检测到模型" in model_name:
            self.chat_history.append("<p style='color:red;'>错误：未选择有效模型</p>")
            return

        ctx_text = self.ctx_combo.currentText().split()[0]
        n_ctx = int(ctx_text)

        # 1. 更新 UI 显示
        self.chat_history.append(f"<b>我:</b> {question}")
        self.input_field.clear()
        self.send_btn.setEnabled(False)
        self.status_label.setText("AI 正在思考中...")

        if not self.history_messages:
            self.history_messages.append({"role": "system", "content": self.system_prompt()})

        try:
            tool_result, round_context = self.prepare_round(question)
        except Exception as e:
            logger.exception("AI 分析上下文生成失败")
            self.chat_history.append(f"<p style='color:red;'>AI 分析准备失败：{str(e)}</p>")
            self.send_btn.setEnabled(True)
            self.status_label.setText("就绪")
            return

        if tool_result.retrieval_degraded:
            self.status_label.setText("AI 正在思考中...（语义检索降级）")

        if tool_result.direct_answer:
            self.history_messages.append({"role": "user", "content": question})
            self.handle_response(tool_result.direct_answer)
            return

        enriched_question = (
            "### 用户问题\n"
            f"{question}\n\n"
            "### 程序计算结果\n"
            f"{round_context}"
        )
        request_messages = self.history_messages + [{"role": "user", "content": enriched_question}]

        # 长期历史只保存原始问题，避免把大段统计上下文在多轮对话中重复累积。
        self.history_messages.append({"role": "user", "content": question})

        # 3. 启动后台线程，传递本轮请求消息
        self.worker = AIWorker(model_name, request_messages, n_ctx)
        self.worker_thread = threading.Thread(target=self.worker.run)
        self.worker_thread.daemon = True
        self.worker.finished.connect(self.handle_response)
        self.worker_thread.start()

    def handle_response(self, response):
        final_answer = response.strip()

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
        self.status_label.setText("就绪")
