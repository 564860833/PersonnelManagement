import sys
import os
import threading
import traceback
import markdown
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QTextEdit, QLineEdit,
                             QPushButton, QLabel, QHBoxLayout, QComboBox, QSpinBox, QGroupBox)
from PyQt5.QtCore import pyqtSignal, QObject, Qt
from PyQt5.QtGui import QIntValidator

# 尝试导入，防止未安装报错
try:
    from llama_cpp import Llama

    HAS_LLAMA = True
except ImportError:
    HAS_LLAMA = False


def get_base_path():
    """获取程序运行的基础路径"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))


class AIWorker(QObject):
    """在后台线程运行AI推理"""
    finished = pyqtSignal(str)

    # 【修改1】构造函数增加 n_ctx 和 n_threads 参数
    def __init__(self, model_path, system_prompt, user_query, n_ctx, n_threads):
        super().__init__()
        self.model_path = model_path
        self.system_prompt = system_prompt
        self.user_query = user_query
        self.n_ctx = n_ctx  # 保存参数
        self.n_threads = n_threads  # 保存参数

    def run(self):
        if not HAS_LLAMA:
            self.finished.emit("错误: 未检测到 llama-cpp-python 库。")
            return

        if not os.path.exists(self.model_path):
            self.finished.emit(f"错误: 找不到模型文件。\n预期路径: {self.model_path}")
            return

        try:
            print(f"DEBUG: 加载模型 params: ctx={self.n_ctx}, threads={self.n_threads}")

            # 【修改2】使用传入的参数初始化模型
            llm = Llama(
                model_path=self.model_path,
                n_ctx=self.n_ctx,  # 使用用户选择的上下文长度
                n_threads=self.n_threads,  # 使用用户选择的线程数
                n_batch=1024,  # 保持较大的批处理以加速读取
                n_gpu_layers=0,  # 强制 CPU
                verbose=True
            )

            # 组合 Prompt (极简模式)
            # 注意：我们将 system_prompt (实际上包含了数据) 和 user_query 分开
            # 这里对 Prompt 结构做一点微调以适应新参数带来的能力
            full_user_content = f"{self.system_prompt}\n\n问题: {self.user_query}"

            messages = [
                {"role": "system",
                 "content": "You are a helpful HR data assistant. Answer based on the provided data."},
                {"role": "user", "content": full_user_content}
            ]

            print("DEBUG: 模型加载成功，开始推理...")

            output = llm.create_chat_completion(
                messages=messages,
                temperature=0.7,
                max_tokens=1024  # 允许生成较长的回答
            )
            response = output['choices'][0]['message']['content']
            self.finished.emit(response)

        except Exception as e:
            print(f"AI Error: {e}")
            traceback.print_exc()
            self.finished.emit(f"AI 运行出错: {str(e)}\n(可能是内存不足或参数设置过高)")


class AIChatDialog(QDialog):
    def __init__(self, data_context, parent=None):
        super().__init__(parent)
        self.data_context = data_context

        # 自动模型路径逻辑
        base_path = get_base_path()
        models_dir = os.path.join(base_path, "models")
        self.model_path = ""
        if os.path.exists(models_dir):
            gguf_files = [f for f in os.listdir(models_dir) if f.endswith('.gguf')]
            if gguf_files:
                gguf_files.sort()
                self.model_path = os.path.join(models_dir, gguf_files[0])
            else:
                self.model_path = os.path.join(models_dir, "未找到模型文件")
        else:
            self.model_path = os.path.join(base_path, "models文件夹缺失")

        self.setWindowTitle("智能分析助手 (参数可调版)")
        self.resize(900, 800)  # 稍微加大窗口
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()

        # ================== 【新增】参数设置区域 ==================
        settings_group = QGroupBox("模型参数设置")
        settings_layout = QHBoxLayout()
        settings_layout.setContentsMargins(10, 5, 10, 5)

        # 1. 上下文长度 (n_ctx)
        settings_layout.addWidget(QLabel("上下文长度 (记忆容量):"))
        self.ctx_combo = QComboBox()
        # 提供常用选项，越大越能处理长数据，但吃内存
        self.ctx_combo.addItems(["2048 (省内存)", "4096 (推荐)", "8192 (长文本)", "16384 (极限)"])
        self.ctx_combo.setCurrentIndex(1)  # 默认选 4096
        self.ctx_combo.setToolTip("决定AI能'记住'多少数据。\n数据量大时请根据运行内存大小调节，否则会报错或截断。")
        settings_layout.addWidget(self.ctx_combo)

        settings_layout.addSpacing(20)  # 间距

        # 2. 线程数 (n_threads)
        settings_layout.addWidget(QLabel("线程数 (CPU核心):"))
        self.thread_spin = QSpinBox()
        self.thread_spin.setRange(1, 32)

        # 智能设置默认线程数：物理核心数
        # 注：os.cpu_count() 获取的是逻辑核心数，对于支持超线程的 CPU，物理核心通常是其一半
        logical_cores = os.cpu_count() if os.cpu_count() else 4
        default_threads = max(1, logical_cores // 2)

        self.thread_spin.setValue(default_threads)
        self.thread_spin.setToolTip("决定 AI 思考的速度。\n默认已设为物理核心数（最佳推理性能）。")
        settings_layout.addWidget(self.thread_spin)

        settings_layout.addStretch()  # 弹簧，把控件顶到左边
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
        self.input_field.returnPressed.connect(self.start_inference)  # 回车发送

        self.send_btn = QPushButton("发送")
        self.send_btn.clicked.connect(self.start_inference)
        # 美化发送按钮
        self.send_btn.setStyleSheet("""
            QPushButton { background-color: #2196F3; color: white; border-radius: 4px; padding: 5px 15px; }
            QPushButton:hover { background-color: #1976D2; }
            QPushButton:disabled { background-color: #BDBDBD; }
        """)

        input_layout.addWidget(self.input_field)
        input_layout.addWidget(self.send_btn)
        layout.addLayout(input_layout)

        # 状态栏
        status_text = "就绪"
        if not HAS_LLAMA:
            status_text = "错误：缺失 llama-cpp-python 库"
        elif not os.path.exists(self.model_path):
            status_text = "错误：未找到模型文件"

        self.status_label = QLabel(status_text)
        self.status_label.setStyleSheet("color: gray; font-size: 12px;")
        layout.addWidget(self.status_label)

        self.setLayout(layout)

    def start_inference(self):
        question = self.input_field.text().strip()
        if not question: return

        # 获取用户选择的参数
        ctx_text = self.ctx_combo.currentText().split()[0]  # 提取 "4096"
        n_ctx = int(ctx_text)
        n_threads = self.thread_spin.value()

        self.chat_history.append(
            f"<p style='color:#666; font-size:12px;'><i>(正在使用参数: ctx={n_ctx}, threads={n_threads}...)</i></p>")
        self.chat_history.append(f"<b>我:</b> {question}")

        self.input_field.clear()
        self.send_btn.setEnabled(False)
        self.status_label.setText(f"AI 正在思考中 (Context: {n_ctx}, Threads: {n_threads})... 请耐心等待")

        # 构建 Prompt
        # 这里使用极简指令
        system_prompt = (
            "Role: HR Data Analyst.\n"
            "Task: Answer based on the CSV data below.\n"
            "Rules: Concise, Markdown format, No Hallucinations.\n"
            f"Data:\n{self.data_context}"
        )

        # 启动线程，传入参数
        self.worker = AIWorker(self.model_path, system_prompt, question, n_ctx, n_threads)
        self.worker_thread = threading.Thread(target=self.worker.run)
        self.worker.finished.connect(self.handle_response)
        self.worker_thread.start()

    def handle_response(self, response):
        # 渲染 Markdown
        try:
            html_content = markdown.markdown(response, extensions=['extra'])
        except:
            html_content = response.replace('\n', '<br>')

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
        <div>{html_content}</div>
        """

        self.chat_history.append(f"<b>AI:</b><br>{styled_html}")
        self.chat_history.append("<hr>")

        # 滚动到底部
        scrollbar = self.chat_history.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

        self.send_btn.setEnabled(True)
        self.status_label.setText("就绪")
