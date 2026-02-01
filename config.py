import os
import logging
import sys
from pathlib import Path
from PyQt5.QtGui import QFont
from datetime import datetime


class Config:
    """应用程序配置类"""

    def __init__(self):
        # 基本配置
        self.APP_NAME = "人员信息管理系统"
        self.APP_VERSION = "1.0"

        # 日志格式定义
        self.LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

        # 数据库配置
        self.DB_NAME = "personnel_system.db"
        self.DB_PATH = self.get_db_path()

        # 日志配置
        self.LOG_LEVEL = logging.INFO
        self.LOG_FILE = self.get_log_path()

        # 创建必要目录和日志文件
        self.create_app_directories()
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
        self.REQUIRED_SHEETS = {
            'base_info': '人员基本信息',
            'rewards': '人员奖惩信息',
            'family': '人员家庭成员信息',
            'resume': '人员简历信息'
        }

        # 必需安装的Python依赖包
        self.REQUIRED_PACKAGES = [
            'pandas',  # 用于Excel数据处理
            'openpyxl',  # 处理Excel文件（特别是合并单元格）
        ]

    def get_db_path(self) -> str:
        """获取数据库文件路径 - 使用相对路径"""
        return "personnel_system.db"  # 直接放在程序目录

    def get_log_path(self) -> str:
        """获取日志文件路径 - 使用相对路径"""
        return "application.log"  # 直接放在程序目录

    def ensure_log_file_exists(self):
        """确保日志文件存在"""
        if not os.path.exists(self.LOG_FILE):
            try:
                with open(self.LOG_FILE, 'w', encoding='utf-8') as f:
                    f.write(f"{datetime.now()} - 日志文件创建\n")
            except Exception as e:
                print(f"无法创建日志文件: {e}")

    def get_app_data_dir(self) -> str:
        """获取应用程序数据存储目录"""
        # 跨平台应用数据目录
        if os.name == 'nt':  # Windows
            app_data = os.getenv('APPDATA')
            app_dir = os.path.join(app_data, self.APP_NAME)  # 直接使用APP_NAME
        else:  # macOS/Linux
            home_dir = os.path.expanduser('~')
            app_dir = os.path.join(home_dir, '.config', self.APP_NAME)  # 直接使用APP_NAME

        return app_dir

    def create_app_directories(self):
        """创建应用程序所需的目录结构"""
        app_dir = self.get_app_data_dir()
        for path in [app_dir, os.path.join(app_dir, 'backups')]:
            Path(path).mkdir(parents=True, exist_ok=True)

    def get_backup_dir(self) -> str:
        """获取备份目录"""
        return os.path.join(self.get_app_data_dir(), 'backups')

    def get_backup_filename(self) -> str:
        """生成自动备份文件名"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"backup_{timestamp}.db"

    def configure_logging(self):
        """配置日志系统，确保使用UTF-8编码"""
        root_logger = logging.getLogger()
        root_logger.setLevel(self.LOG_LEVEL)

        # 移除默认处理器（如果有）
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

        # 创建文件处理器并设置UTF-8编码
        formatter = logging.Formatter(self.LOG_FORMAT)
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
logger = logging.getLogger('Config')
logger.info(f"应用程序配置已加载: {config.APP_NAME} v{config.APP_VERSION}")

# 检查依赖包
if not config.check_dependencies():
    logger.critical("缺少必要的依赖包，应用程序可能无法正常运行！")