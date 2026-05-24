import logging
from PyQt5.QtGui import QFont
from datetime import datetime
from pathlib import Path
from app_paths import data_path
from metadata.constants import TABLE_LABELS

logger = logging.getLogger('Config')


class Config:
    """应用程序配置类"""

    def __init__(self):
        # 基本配置
        self.APP_NAME = "人员信息管理系统"
        self.APP_VERSION = "2.0"

        # 日志格式定义
        self.LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

        # 数据库配置
        self.DB_NAME = "personnel_system.db"
        self.DB_PATH = self.get_db_path()

        # 日志配置
        self.LOG_LEVEL = logging.INFO
        self.LOG_FILE = self.get_log_path()

        # 创建必要日志文件
        self.ensure_log_file_exists()
        self.configure_logging()

        # 用户界面配置
        self.MAIN_WINDOW_SIZE = (1280, 720)
        self.FONT_NAME = "Microsoft YaHei"
        self.FONT_SIZE = 10

        # 安全配置
        self.MAX_LOGIN_ATTEMPTS = 5
        self.SESSION_TIMEOUT = 1800  # 30分钟无操作自动登出（秒）

        # 数据导入配置
        self.REQUIRED_SHEETS = TABLE_LABELS.copy()

        # 必需安装的Python依赖包
        self.REQUIRED_PACKAGES = [
            'pandas',  # 用于Excel数据处理
            'openpyxl',  # 处理Excel文件（特别是合并单元格）
            'requests',  # 【新增】用于调用本地 Ollama API
            'markdown',  # 【新增】用于渲染 AI 返回的 Markdown 文本
        ]

    def get_db_path(self) -> str:
        """获取数据库文件路径 - 使用 exe 同级隐藏 data 目录。"""
        return str(data_path("personnel_system.db"))

    def get_log_path(self) -> str:
        """获取日志文件路径 - 使用 exe 同级隐藏 data 目录。"""
        return str(data_path("application.log"))

    def ensure_log_file_exists(self):
        """确保日志文件存在。"""
        log_path = Path(self.LOG_FILE)
        if not log_path.exists():
            try:
                log_path.parent.mkdir(parents=True, exist_ok=True)
                with log_path.open('w', encoding='utf-8') as f:
                    f.write(f"{datetime.now()} - 日志文件创建\n")
            except Exception as e:
                logger.error(f"无法创建日志文件: {e}")

    def configure_logging(self):
        """配置日志系统，确保使用UTF-8编码"""
        root_logger = logging.getLogger()
        root_logger.setLevel(self.LOG_LEVEL)

        # 移除默认处理器（如果有）
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

        # 创建文件处理器并设置UTF-8编码
        formatter = logging.Formatter(self.LOG_FORMAT)
        Path(self.LOG_FILE).parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(self.LOG_FILE, encoding='utf-8')
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

        # 添加控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    def font(self):
        """获取配置的字体对象"""
        return QFont(self.FONT_NAME, self.FONT_SIZE)

    def check_dependencies(self) -> bool:
        """检查所有必需的依赖包是否已安装"""
        try:
            import importlib
            missing = []
            for package in self.REQUIRED_PACKAGES:
                try:
                    importlib.import_module(package)
                except ImportError:
                    missing.append(package)

            if missing:
                logger.error(f"缺少必要的依赖包: {', '.join(missing)}")
                return False
            return True
        except Exception as e:
            logger.error(f"检查依赖包失败: {e}")
            return False



# 全局配置实例
config = Config()

APP_NAME = config.APP_NAME
APP_VERSION = config.APP_VERSION
logger.info(f"应用程序配置已加载: {config.APP_NAME} v{config.APP_VERSION}")

# 检查依赖包
if not config.check_dependencies():
    logger.critical("缺少必要的依赖包，应用程序可能无法正常运行！")
