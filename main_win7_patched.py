import sys
import os

# ============ 最早期修复 - 必须在所有导入之前 ============
print("应用最早期 Windows 7 兼容性修复...")

# 1. 设置关键环境变量
os.environ.update({
    'PYTHONLEGACYWINDOWSSTDIO': '1',
    'PYTHONIOENCODING': 'utf-8',
    'PYTHONDONTWRITEBYTECODE': '1',
    'PYINSTALLER_WIN7_COMPAT': '1'
})

# 2. 创建pyexpat替代模块（在任何XML相关导入之前）
class UltraCompatExpat:
    def ParserCreate(self, encoding=None):
        class MockParser:
            def __init__(self):
                self.StartElementHandler = None
                self.EndElementHandler = None
                self.CharacterDataHandler = None
            def Parse(self, data, isfinal=1): return True
            def ParseFile(self, file): return True
        return MockParser()

# 立即注入替代模块
sys.modules['pyexpat'] = UltraCompatExpat()
sys.modules['xml.parsers.expat'] = UltraCompatExpat()

print("✓ pyexpat 替代模块已注入")

# 3. Windows 7 特殊处理
if sys.platform == "win32":
    try:
        win_version = sys.getwindowsversion()
        if win_version.major == 6 and win_version.minor == 1:
            print("✓ 检测到 Windows 7，应用特殊兼容处理")

            # 设置Qt兼容模式
            os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "0"
            os.environ["QT_SCALE_FACTOR"] = "1"
            os.environ["QT_OPENGL"] = "software"
    except:
        pass

# ============ 现在安全导入其他模块 ============
try:
    import logging
    from PyQt5.QtGui import QIcon
    from PyQt5.QtWidgets import QApplication, QMessageBox

    # 导入应用模块
    from config import config
    from database import Database
    from login import LoginDialog
    from main_window import MainWindow

except ImportError as e:
    print(f"导入模块失败: {e}")
    input("按任意键退出...")
    sys.exit(1)

# 全局主窗口引用
global_main_window = None
logger = logging.getLogger('Main')

def resource_path(relative_path):
    """获取资源绝对路径"""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

def create_safe_application():
    """创建兼容的Qt应用程序"""
    try:
        app = QApplication(sys.argv)
        app.setApplicationName(config.APP_NAME)
        app.setApplicationVersion(config.APP_VERSION)

        # 设置图标
        try:
            icon_path = resource_path('app_icon.ico')
            if os.path.exists(icon_path):
                app_icon = QIcon(icon_path)
                app.setWindowIcon(app_icon)
        except:
            pass

        return app
    except Exception as e:
        logger.error(f"创建应用程序失败: {e}")
        raise

def main():
    """应用程序主入口"""
    try:
        # 创建Qt应用程序
        app = create_safe_application()

        # 设置字体
        try:
            app.setFont(config.font())
        except:
            pass

        logger.info("应用程序启动")

        # 初始化数据库
        db = Database()

        # 确保管理员账号存在
        if db.get_password('admin') is None:
            db.change_password('admin', '123456')
            logger.info("管理员账号已创建: admin/123456")

        # 登录
        login_dialog = LoginDialog(db)

        if login_dialog.exec_() == LoginDialog.Accepted:
            username = login_dialog.get_username()
            logger.info(f"用户 {username} 登录成功")

            # 获取权限
            permissions = db.get_user_permissions(username)
            if username.lower() == 'admin':
                permissions = {
                    'base_info': True,
                    'rewards': True,
                    'family': True,
                    'resume': True
                }

            # 创建主窗口
            global global_main_window
            global_main_window = MainWindow(db, username, permissions)
            global_main_window.showMaximized()

            return app.exec_()
        else:
            db.close()
            return 0

    except Exception as e:
        logger.exception("应用程序异常")
        try:
            QMessageBox.critical(None, "错误", f"程序出现异常: {str(e)}")
        except:
            print(f"程序异常: {e}")
        return 1

if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except Exception as e:
        print(f"程序异常退出: {e}")
        sys.exit(1)
