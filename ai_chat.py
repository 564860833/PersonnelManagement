import sys
import os
import json
import re
import requests
import threading
import traceback
import markdown
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QTextEdit, QLineEdit,
                             QPushButton, QLabel, QHBoxLayout, QComboBox, QGroupBox, QMessageBox)
from PyQt5.QtCore import pyqtSignal, QObject


class AIWorker(QObject):
    """在后台线程运行AI推理，调用本地 Ollama 接口"""
    finished = pyqtSignal(str)

    def __init__(self, model_name, messages, n_ctx):
        super().__init__()
        self.model_name = model_name
        self.messages = messages  # 接收完整的消息列表
        self.n_ctx = n_ctx
        self.api_url = "http://127.0.0.1:11434/api/chat"
        self._is_running = True

    def stop(self):
        self._is_running = False

    def run(self):
        try:
            print(f"DEBUG: 正在请求 Ollama 模型 [{self.model_name}], ctx={self.n_ctx}")

            payload = {
                "model": self.model_name,
                "messages": self.messages,  # 发送包含上下文的消息列表
                "stream": True,
                "options": {
                    "num_ctx": self.n_ctx,
                    "temperature": 0.1,
                    "top_p": 0.9,
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
                print(f"AI Error: {e}")
                traceback.print_exc()
                self.finished.emit(f"AI 运行出错: {str(e)}")


class AIChatDialog(QDialog):
    def __init__(self, data_context, parent=None):
        super().__init__(parent)
        self.data_context = data_context
        # 新增：用于存储多轮对话的消息列表
        self.history_messages = []
        self.setWindowTitle("智能分析助手 (多轮对话版)")
        self.resize(900, 800)
        self.setup_ui()

    def closeEvent(self, event):
        if hasattr(self, 'worker') and self.worker:
            self.worker.stop()
        event.accept()

    def get_local_models(self):
        try:
            response = requests.get("http://127.0.0.1:11434/api/tags", timeout=3)
            if response.status_code == 200:
                data = response.json()
                models = [model['name'] for model in data.get('models', [])]
                return models
        except Exception as e:
            print(f"获取模型列表失败: {e}")
        return []

    def refresh_models(self):
        self.model_combo.clear()
        models = self.get_local_models()
        if models:
            self.model_combo.addItems(models)
            self.status_label.setText(f"就绪 (已识别到 {len(models)} 个本地模型)")
        else:
            self.model_combo.addItem("未检测到模型/服务未启动")
            self.status_label.setText("错误：无法连接 Ollama")

    def setup_ui(self):
        layout = QVBoxLayout()

        settings_group = QGroupBox("Ollama 模型设置")
        settings_layout = QHBoxLayout()

        settings_layout.addWidget(QLabel("选择模型:"))
        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(180)
        settings_layout.addWidget(self.model_combo)

        self.refresh_btn = QPushButton("刷新列表")
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
        self.clear_btn.clicked.connect(self.clear_chat)
        settings_layout.addWidget(self.clear_btn)

        settings_layout.addStretch()
        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)

        self.chat_history = QTextEdit()
        self.chat_history.setReadOnly(True)
        layout.addWidget(self.chat_history)

        input_layout = QHBoxLayout()
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("请输入您的问题...")
        self.input_field.returnPressed.connect(self.start_inference)

        self.send_btn = QPushButton("发送")
        self.send_btn.clicked.connect(self.start_inference)
        self.send_btn.setDefault(True)
        self.send_btn.setStyleSheet("background-color: #2196F3; color: white; padding: 5px 15px;")

        input_layout.addWidget(self.input_field)
        input_layout.addWidget(self.send_btn)
        layout.addLayout(input_layout)

        self.status_label = QLabel("正在初始化...")
        layout.addWidget(self.status_label)

        self.setLayout(layout)
        self.refresh_models()

    def clear_chat(self):
        """清空对话历史"""
        self.history_messages = []
        self.chat_history.clear()
        self.chat_history.append("<p style='color:gray;'><i>对话已清空</i></p>")

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

        # 2. 构造本次请求的消息列表
        # 如果是首轮对话，加入系统提示词和数据上下文
        if not self.history_messages:
            system_content = (
                "### 角色\n你是一名专业的人力资源数据分析师。\n\n"
                "### 核心任务\n请仅根据下方提供的【CSV数据】回答用户的【提问】。如果数据中不存在相关信息，请直接回答'抱歉，根据现有数据无法回答该问题'，严禁编造信息。\n\n"
                "### 数据内容\n"
                f"{self.data_context}\n\n"
                "### 输出规则\n"
                "1. 使用 Markdown 表格列出多条数据。\n"
                "2. 回复简洁、专业，禁止输出与数据无关的内容。\n"
        )
            self.history_messages.append({"role": "system", "content": system_content})

        # 将当前问题加入历史记录
        self.history_messages.append({"role": "user", "content": question})

        # 3. 启动后台线程，传递完整的对话历史
        self.worker = AIWorker(model_name, self.history_messages, n_ctx)
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
        except:
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
