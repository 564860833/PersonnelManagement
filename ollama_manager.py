import os
import sys
import subprocess
import logging
import platform

logger = logging.getLogger('OllamaManager')


class LocalOllamaManager:
    def __init__(self):
        self.process = None

        # 判断是否为 PyInstaller 打包后的环境
        if getattr(sys, 'frozen', False):
            # 外部路径：指向 exe 文件所在的真实同级目录
            external_base_dir = os.path.dirname(sys.executable)
        else:
            # 源码运行环境
            external_base_dir = os.path.dirname(os.path.abspath(__file__))

        # 定义 ollama 的路径 (现在使用外部路径 external_base_dir)
        if platform.system() == "Windows":
            self.exe_path = os.path.join(external_base_dir, "bin", "ollama.exe")
        else:
            self.exe_path = os.path.join(external_base_dir, "bin", "ollama")

        # 定义模型存放路径 (同样使用外部路径)
        self.models_dir = os.path.join(external_base_dir, "models")

    def start(self):
        """静默启动内部打包的 Ollama 服务"""
        if not os.path.exists(self.exe_path):
            logger.error(f"未找到内置的 Ollama 程序: {self.exe_path}")
            return False

        # 确保模型目录存在
        os.makedirs(self.models_dir, exist_ok=True)

        # 设置环境变量，重定向模型存储路径，实现绿色便携化
        env = os.environ.copy()
        env["OLLAMA_MODELS"] = self.models_dir
        # env["OLLAMA_HOST"] = "127.0.0.1:11434" # 默认端口

        try:
            # 静默启动参数
            creationflags = 0
            if platform.system() == "Windows":
                # 防止在 Windows 下弹出黑框 CMD 窗口
                creationflags = subprocess.CREATE_NO_WINDOW

            logger.info("正在后台启动内置 Ollama 服务...")
            self.process = subprocess.Popen(
                [self.exe_path, "serve"],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags
            )
            logger.info("内置 Ollama 服务启动成功！")
            return True
        except Exception as e:
            logger.error(f"启动 Ollama 失败: {e}")
            return False

    def stop(self):
        """关闭 Ollama 服务及其所有子进程"""
        if self.process:
            logger.info("正在关闭内置 Ollama 服务及其子进程...")
            try:
                if platform.system() == "Windows":
                    # 【修改点 1】：把 call 改为 Popen
                    subprocess.Popen(
                        ['taskkill', '/F', '/T', '/PID', str(self.process.pid)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        creationflags=subprocess.CREATE_NO_WINDOW # 避免闪黑框
                    )
                else:
                    # Mac/Linux 逻辑
                    self.process.terminate()
            except Exception as e:
                logger.error(f"关闭 Ollama 进程树时发生异常: {e}")
            finally:
                self.process = None

        # 终极保险：万一进程树没杀干净，按名字再补一刀
        if platform.system() == "Windows":
            try:
                # 【修改点 2】：把 call 改为 Popen
                subprocess.Popen(
                    ['taskkill', '/F', '/IM', 'ollama.exe'],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW # 避免闪黑框
                )
            except:
                pass
