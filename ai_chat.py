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

    def __init__(self, model_name, system_prompt, user_query, n_ctx):
        super().__init__()
        self.model_name = model_name
        self.system_prompt = system_prompt
        self.user_query = user_query
        self.n_ctx = n_ctx
        self.api_url = "http://127.0.0.1:11434/api/chat"
        self._is_running = True  # 新增：运行状态标志位

    def stop(self):
        """新增：停止运行的方法"""
        self._is_running = False

    def run(self):
        try:
            print(f"DEBUG: 正在请求 Ollama 模型 [{self.model_name}], ctx={self.n_ctx}")

            full_user_content = f"{self.system_prompt}\n\n问题: {self.user_query}"

            payload = {
                "model": self.model_name,
                "messages": [
                    {"role": "system",
                     "content": "You are a helpful HR data assistant. Answer based on the provided data."},
                    {"role": "user", "content": full_user_content}
                ],
                "stream": True,  # 修改为 True，允许流式读取并随时中断
                "options": {
                    "num_ctx": self.n_ctx,
                    "temperature": 0.1,  # 调低温度以减少幻觉，提高准确度
                    "top_p": 0.9
                }
            }

            response = requests.post(self.api_url, json=payload, stream=True, timeout=300)

            if response.status_code == 404:
                self.finished.emit(f"错误: 找不到模型 `{self.model_name}`。")
                return

            response.raise_for_status()

            answer = ""
            # 迭代读取流式返回的内容
            for line in response.iter_lines():
                # 如果外部调用了 stop()，则中断连接
                if not self._is_running:
                    print("DEBUG: 收到停止信号，正在中断与 Ollama 的连接...")
                    response.close()
                    # 不再发送 finished 信号，直接结束
                    return

                if line:
                    data = json.loads(line)
                    answer += data.get('message', {}).get('content', '')

            # 正常完成时发送结果
            if self._is_running:
                self.finished.emit(answer)

        except requests.exceptions.ConnectionError:
            self.finished.emit("错误: 无法连接到本地 Ollama 服务。\n请确认 Ollama 已在后台运行。")
        except Exception as e:
            if not self._is_running:
                # 如果是手动停止引发的异常（如断开连接），则忽略
                pass
            else:
                print(f"AI Error: {e}")
                traceback.print_exc()
                self.finished.emit(f"AI 运行出错: {str(e)}")


class AIChatDialog(QDialog):
    def __init__(self, data_context, parent=None):
        super().__init__(parent)
        self.data_context = data_context
        self.setWindowTitle("智能分析助手 (Ollama 自动识别模型版)")
        self.resize(900, 800)
        self.setup_ui()

    def closeEvent(self, event):
        """重写关闭事件，在关闭对话框时中断 AI 分析"""
        if hasattr(self, 'worker') and self.worker:
            self.worker.stop()
            self.chat_history.append("<p style='color:orange;'><i>(AI 分析已强制中止)</i></p>")

        # 接受关闭事件，正常关闭窗口
        event.accept()

    def get_local_models(self):
        """调用 Ollama API 获取本地已安装的模型列表"""
        try:
            response = requests.get("http://127.0.0.1:11434/api/tags", timeout=3)
            if response.status_code == 200:
                data = response.json()
                # 提取返回数据中的 name 字段作为模型名称
                models = [model['name'] for model in data.get('models', [])]
                return models
        except requests.exceptions.ConnectionError:
            print("未能连接到 Ollama 服务，请检查 Ollama 是否启动。")
        except Exception as e:
            print(f"获取模型列表失败: {e}")
        return []

    def refresh_models(self):
        """刷新下拉框中的模型列表"""
        self.model_combo.clear()
        models = self.get_local_models()
        if models:
            self.model_combo.addItems(models)
            self.status_label.setText(f"就绪 (已识别到 {len(models)} 个本地模型)")
        else:
            self.model_combo.addItem("未检测到模型/服务未启动")
            self.status_label.setText("错误：无法连接 Ollama 或未安装任何模型")

    def setup_ui(self):
        layout = QVBoxLayout()

        # ================== 参数设置区域 ==================
        settings_group = QGroupBox("Ollama 模型设置")
        settings_layout = QHBoxLayout()
        settings_layout.setContentsMargins(10, 5, 10, 5)

        # 1. Ollama 模型下拉选择 (替换了原来的 QLineEdit)
        settings_layout.addWidget(QLabel("选择模型:"))
        self.model_combo = QComboBox()
        self.model_combo.setToolTip("选择你在本地 Ollama 中已加载的模型")
        self.model_combo.setMinimumWidth(180)
        settings_layout.addWidget(self.model_combo)

        # 添加一个刷新按钮，方便热更新模型列表
        self.refresh_btn = QPushButton("刷新列表")
        self.refresh_btn.setToolTip("如果你刚刚导入了新模型，点击此按钮刷新列表")
        self.refresh_btn.clicked.connect(self.refresh_models)
        self.refresh_btn.setAutoDefault(False)
        settings_layout.addWidget(self.refresh_btn)

        settings_layout.addSpacing(20)

        # 2. 上下文长度 (n_ctx)
        settings_layout.addWidget(QLabel("上下文长度:"))
        self.ctx_combo = QComboBox()
        self.ctx_combo.addItems(["2048 (省内存)", "4096 (推荐)", "8192 (长文本)", "16384 (极限)"])
        self.ctx_combo.setCurrentIndex(1)
        settings_layout.addWidget(self.ctx_combo)

        settings_layout.addStretch()
        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)
        # ========================================================

        # 聊天历史
        self.chat_history = QTextEdit()
        self.chat_history.setReadOnly(True)
        layout.addWidget(self.chat_history)

        # 输入区域
        input_layout = QHBoxLayout()
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("请输入您的问题：")
        self.input_field.returnPressed.connect(self.start_inference)

        self.send_btn = QPushButton("发送")
        self.send_btn.clicked.connect(self.start_inference)
        self.send_btn.setAutoDefault(True)  # <--- 新增这行
        self.send_btn.setDefault(True)
        self.send_btn.setStyleSheet("""
            QPushButton { background-color: #2196F3; color: white; border-radius: 4px; padding: 5px 15px; }
            QPushButton:hover { background-color: #1976D2; }
            QPushButton:disabled { background-color: #BDBDBD; }
        """)

        input_layout.addWidget(self.input_field)
        input_layout.addWidget(self.send_btn)
        layout.addLayout(input_layout)

        # 状态栏
        self.status_label = QLabel("正在初始化...")
        self.status_label.setStyleSheet("color: gray; font-size: 12px;")
        layout.addWidget(self.status_label)

        self.setLayout(layout)

        # 界面初始化完成后，自动获取一次模型列表
        self.refresh_models()

    def start_inference(self):
        question = self.input_field.text().strip()
        if not question: return

        # 从下拉菜单获取当前选中的模型
        model_name = self.model_combo.currentText().strip()
        if not model_name or "未检测到模型" in model_name:
            self.chat_history.append(
                "<p style='color:red;'>错误：未选择有效的模型，请确认 Ollama 已启动并安装了模型！</p>")
            return

        ctx_text = self.ctx_combo.currentText().split()[0]
        n_ctx = int(ctx_text)

        self.chat_history.append(
            f"<p style='color:#666; font-size:12px;'><i>(正在调用本地 Ollama [{model_name}], ctx={n_ctx}...)</i></p>")
        self.chat_history.append(f"<b>我:</b> {question}")

        self.input_field.clear()
        self.send_btn.setEnabled(False)
        self.status_label.setText(f"AI 正在思考中... (模型: {model_name})")

        # 优化后的 prompt 结构
        system_prompt = (
            "### 角色\n你是一名专业的人力资源数据分析师。\n\n"
            "### 核心任务\n请仅根据下方提供的【CSV数据】回答用户的【提问】。如果数据中不存在相关信息，请直接回答'抱歉，根据现有数据无法回答该问题'，严禁编造信息。\n\n"
            "### 数据内容\n"
            f"{self.data_context}\n\n"
            "### 输出规则\n"
            "1. 必须使用 Markdown 表格列出多条数据。\n"
            "2. 回复必须简洁、专业，禁止输出与数据无关的内容。\n"
        )

        self.worker = AIWorker(model_name, system_prompt, question, n_ctx)
        self.worker_thread = threading.Thread(target=self.worker.run)

        self.worker_thread.daemon = True
        self.worker.finished.connect(self.handle_response)
        self.worker_thread.start()

    def handle_response(self, response):
        # 1. 直接将原始回复作为最终结论，不再解析 <think> 标签
        final_answer = response.strip()

        # 2. 渲染最终结论 (使用 Markdown)
        try:
            # 确保安装了 markdown 库，config.py 中已列出此依赖
            answer_html = markdown.markdown(final_answer, extensions=['extra', 'tables'])
        except:
            answer_html = final_answer.replace('\n', '<br>')

        # 3. 组合最终样式 (去掉了 thought_html 相关部分)
        styled_html = f"""
        <style>
            p {{ margin-bottom: 8px; line-height: 1.6; }}
            ul {{ margin-bottom: 8px; margin-left: 15px; }}
            li {{ margin-bottom: 4px; }}
            strong {{ color: #003366; }}
            table {{ border-collapse: collapse; width: 100%; margin: 10px 0; }}
            th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
            th {{ background-color: #f2f2f2; }}
        </style>
        <div>
            <div>{answer_html}</div>
        </div>
        """

        # 追加到聊天窗口
        self.chat_history.append(f"<b>AI:</b><br>{styled_html}")
        self.chat_history.append("<hr>")

        # 滚动到底部
        scrollbar = self.chat_history.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

        # 恢复 UI 状态
        self.send_btn.setEnabled(True)
        self.status_label.setText("就绪")
