import sys
import threading
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QTextEdit, QLineEdit,
                             QPushButton, QLabel, QHBoxLayout)
from PyQt5.QtCore import pyqtSignal, QObject

# 尝试导入，防止未安装报错
try:
    from llama_cpp import Llama

    HAS_LLAMA = True
except ImportError:
    HAS_LLAMA = False


class AIWorker(QObject):
    """在后台线程运行AI推理，防止界面卡死"""
    finished = pyqtSignal(str)

    def __init__(self, model_path, system_prompt, user_query):
        super().__init__()
        self.model_path = model_path
        self.system_prompt = system_prompt
        self.user_query = user_query

    def run(self):
        if not HAS_LLAMA:
            self.finished.emit("错误: 未检测到 llama-cpp-python 库。")
            return

        try:
            # 加载模型 (n_ctx是上下文长度，根据数据量调整)
            # n_threads 设置为 CPU 核心数 - 1
            llm = Llama(model_path=self.model_path, n_ctx=2048, n_threads=4, verbose=False)

            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": self.user_query}
            ]

            # 开始推理
            output = llm.create_chat_completion(messages=messages, temperature=0.7)
            response = output['choices'][0]['message']['content']
            self.finished.emit(response)
        except Exception as e:
            self.finished.emit(f"AI 运行出错: {str(e)}")


class AIChatDialog(QDialog):
    def __init__(self, data_context, parent=None):
        super().__init__(parent)
        self.data_context = data_context  # 这是从查询结果传来的数据字符串
        self.model_path = "models/qwen1_5-1_8b-chat-q4_k_m.gguf"  # 模型路径
        self.setWindowTitle("智能数据助手 (离线版)")
        self.resize(600, 500)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()

        self.chat_history = QTextEdit()
        self.chat_history.setReadOnly(True)
        layout.addWidget(self.chat_history)

        input_layout = QHBoxLayout()
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("请输入您的问题，例如：'帮我总结一下这些人的学历情况'...")
        self.send_btn = QPushButton("发送")
        self.send_btn.clicked.connect(self.start_inference)

        input_layout.addWidget(self.input_field)
        input_layout.addWidget(self.send_btn)
        layout.addWidget(input_layout)

        self.status_label = QLabel("就绪 (模型运行于本地 CPU)")
        layout.addWidget(self.status_label)

        self.setLayout(layout)

    def start_inference(self):
        question = self.input_field.text().strip()
        if not question:
            return

        self.chat_history.append(f"<b>我:</b> {question}")
        self.input_field.clear()
        self.send_btn.setEnabled(False)
        self.status_label.setText("AI 正在思考中... (可能需要几秒到几十秒)")

        # 构建提示词 (Prompt Engineering)
        system_prompt = (
            "你是一个人事管理助手。以下是当前查询到的员工数据 JSON 格式："
            f"{self.data_context}\n\n"
            "请根据以上数据回答用户问题。如果数据中没有答案，请直接说不知道。不要编造数据。"
        )

        # 启动后台线程
        self.worker = AIWorker(self.model_path, system_prompt, question)
        self.worker_thread = threading.Thread(target=self.worker.run)
        self.worker.finished.connect(self.handle_response)
        self.worker_thread.start()

    def handle_response(self, response):
        self.chat_history.append(f"<b>AI:</b> {response}")
        self.send_btn.setEnabled(True)
        self.status_label.setText("就绪")