import os
import time
import chardet
import logging
from PyQt5.QtWidgets import (QDialog, QTextEdit, QPushButton, QVBoxLayout,
                             QHBoxLayout, QLabel, QFileDialog, QApplication,
                             QComboBox, QMainWindow)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QTextCursor


class LogViewer(QDialog):
    def __init__(self, log_file_path=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("日志查看器")
        self.setMinimumSize(800, 600)

        self.log_file_path = log_file_path
        self.last_position = 0
        self.file_modified = 0
        self.file_size = 0
        self.encoding = "utf-8"  # 默认编码
        self.encoding_cache = {}  # 文件路径到编码的映射缓存

        self.setup_ui()

        # 设置定时器实时更新日志
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_logs)
        self.timer.start(1000)  # 每秒检查一次

        # 如果提供了日志文件路径，初始加载日志
        if self.log_file_path and os.path.exists(self.log_file_path):
            self.load_initial_logs()

    def setup_ui(self):
        layout = QVBoxLayout()

        # 路径显示
        path_layout = QHBoxLayout()
        path_layout.addWidget(QLabel("日志文件:"))
        self.path_label = QLabel(self.log_file_path or "未选择日志文件")
        path_layout.addWidget(self.path_label, 1)

        # 文件选择按钮
        self.select_btn = QPushButton("选择日志文件")
        self.select_btn.clicked.connect(self.select_log_file)
        path_layout.addWidget(self.select_btn)

        layout.addLayout(path_layout)

        # 编码选择
        encoding_layout = QHBoxLayout()
        encoding_layout.addWidget(QLabel("文件编码:"))

        self.encoding_combo = QComboBox()
        self.encoding_combo.addItems([
            "自动检测",
            "UTF-8",
            "GBK",
            "GB2312",
            "BIG5",
            "ISO-8859-1",
            "Windows-1252"
        ])
        self.encoding_combo.setCurrentText("自动检测")
        encoding_layout.addWidget(self.encoding_combo)

        self.reload_btn = QPushButton("重新加载")
        self.reload_btn.clicked.connect(self.reload_logs)
        encoding_layout.addWidget(self.reload_btn)

        layout.addLayout(encoding_layout)

        # 日志显示区域
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 10))  # 等宽字体适合显示日志
        self.log_text.setLineWrapMode(QTextEdit.NoWrap)  # 禁用自动换行
        layout.addWidget(self.log_text, 1)

        # 按钮区域
        btn_layout = QHBoxLayout()

        # 顶部按钮
        self.top_btn = QPushButton("顶部")
        self.top_btn.clicked.connect(self.go_to_top)
        btn_layout.addWidget(self.top_btn)

        # 底部按钮
        self.bottom_btn = QPushButton("底部")
        self.bottom_btn.clicked.connect(self.go_to_bottom)
        btn_layout.addWidget(self.bottom_btn)


        # 关闭按钮
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

        self.setLayout(layout)

    def detect_encoding(self, file_path):
        """检测文件编码，使用缓存提高性能"""
        # 如果已缓存编码，直接返回
        if file_path in self.encoding_cache:
            return self.encoding_cache[file_path]

        # 自动检测文件编码
        try:
            with open(file_path, 'rb') as f:
                raw_data = f.read(4096)  # 读取文件前4KB用于检测编码
                result = chardet.detect(raw_data)

            # 如果检测置信度足够高，使用检测到的编码
            if result['confidence'] > 0.7:
                encoding = result['encoding'].lower()
                # 修正常见编码名称
                if encoding == 'gb2312':
                    encoding = 'gbk'
                self.encoding_cache[file_path] = encoding
                return encoding

            # 默认使用UTF-8
            return 'utf-8'
        except Exception:
            return 'utf-8'

    def get_file_encoding(self):
        """获取当前使用的文件编码"""
        selected_encoding = self.encoding_combo.currentText()
        if selected_encoding == "自动检测":
            if self.log_file_path:
                return self.detect_encoding(self.log_file_path)
            return 'utf-8'
        return selected_encoding.lower()

    def read_file_content(self, file_path, start=0, length=None):
        """读取文件内容，使用检测到的编码"""
        encoding = self.get_file_encoding()

        # 常见的编码映射
        encoding_map = {
            'gb2312': 'gbk',
            'gb18030': 'gbk',
            'big5': 'cp950',
        }

        # 应用映射
        final_encoding = encoding_map.get(encoding.lower(), encoding)

        try:
            # 尝试读取
            with open(file_path, 'r', encoding=final_encoding, errors='replace') as f:
                if start > 0:
                    f.seek(start)
                content = f.read(length) if length else f.read()
            return content
        except UnicodeDecodeError:
            # 尝试其他可能的编码
            for alt_encoding in ['utf-8', 'gbk', 'cp936', 'latin1']:
                try:
                    with open(file_path, 'r', encoding=alt_encoding, errors='replace') as f:
                        if start > 0:
                            f.seek(start)
                        content = f.read(length) if length else f.read()
                    return content
                except:
                    continue
            return "无法解码文件内容"
        except Exception as e:
            return f"读取文件失败: {str(e)}"

    def select_log_file(self):
        """选择日志文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择日志文件", "", "日志文件 (*.log *.txt);;所有文件 (*.*)"
        )
        if file_path:
            self.log_file_path = file_path
            self.path_label.setText(file_path)
            self.last_position = 0
            self.reload_logs()

    def reload_logs(self):
        """重新加载日志文件"""
        if self.log_file_path and os.path.exists(self.log_file_path):
            self.last_position = 0
            self.load_initial_logs()

    def load_initial_logs(self):
        """加载初始日志内容"""
        if not self.log_file_path or not os.path.exists(self.log_file_path):
            return

        try:
            # 获取文件状态和大小
            stat = os.stat(self.log_file_path)
            self.file_modified = stat.st_mtime
            self.file_size = stat.st_size

            # 读取文件内容
            content = self.read_file_content(self.log_file_path)
            self.log_text.setPlainText(content)
            self.last_position = self.file_size

            # 滚动到底部
            self.go_to_bottom()
        except Exception as e:
            self.log_text.append(f"加载日志失败: {str(e)}")

    def update_logs(self):
        """更新日志内容（增量更新）"""
        if not self.log_file_path or not os.path.exists(self.log_file_path):
            return

        try:
            # 检查文件是否被修改
            stat = os.stat(self.log_file_path)
            if stat.st_mtime <= self.file_modified and stat.st_size == self.file_size:
                return  # 文件未修改

            # 更新文件状态
            self.file_modified = stat.st_mtime
            new_size = stat.st_size

            # 文件被截断的情况（例如日志轮转）
            if new_size < self.last_position:
                # 如果文件变小，重新加载整个文件
                self.reload_logs()
                return

            # 读取新增内容
            if new_size > self.last_position:
                # 计算要读取的大小
                read_size = new_size - self.last_position

                # 读取新增内容
                new_content = self.read_file_content(
                    self.log_file_path,
                    start=self.last_position,
                    length=read_size
                )

                # 添加到日志显示区域
                if new_content.strip():
                    self.log_text.append(new_content)

                # 如果当前在底部，自动滚动
                scrollbar = self.log_text.verticalScrollBar()
                auto_scroll = scrollbar.value() == scrollbar.maximum()

                # 更新最后位置
                self.last_position = new_size

                # 如果设置了自动滚动，滚动到底部
                if auto_scroll:
                    self.go_to_bottom()

            self.file_size = new_size
        except Exception as e:
            self.log_text.append(f"更新日志失败: {str(e)}")

    def go_to_top(self):
        """滚动到日志顶部"""
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.Start)
        self.log_text.setTextCursor(cursor)

    def go_to_bottom(self):
        """滚动到日志底部"""
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.log_text.setTextCursor(cursor)
        self.log_text.ensureCursorVisible()


    def closeEvent(self, event):
        """关闭时停止定时器"""
        self.timer.stop()
        super().closeEvent(event)


# 测试代码
if __name__ == "__main__":
    import sys

    # 启动日志查看器
    app = QApplication(sys.argv)
    viewer = LogViewer()
    viewer.exec_()
    sys.exit(app.exec_())