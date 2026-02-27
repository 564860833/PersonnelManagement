import os
import subprocess
import logging
import platform

logger = logging.getLogger('OllamaManager')


class LocalOllamaManager:
    def __init__(self):
        self.process = None
        # 获取当前项目根目录
        self.base_dir = os.path.dirname(os.path.abspath(__file__))

        # 定义 ollama.exe 的路径和模型存放路径
        if platform.system() == "Windows":
            self.exe_path = os.path.join(self.base_dir, "bin", "ollama.exe")
        else:
            self.exe_path = os.path.join(self.base_dir, "bin", "ollama")  # Linux/Mac

        self.models_dir = os.path.join(self.base_dir, "models")

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
        """关闭 Ollama 服务"""
        if self.process:
            logger.info("正在关闭内置 Ollama 服务...")
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except Exception as e:
                logger.error(f"关闭 Ollama 服务发生异常: {e}")
                self.process.kill()
            finally:
                self.process = None