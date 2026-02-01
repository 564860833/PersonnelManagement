import os
import logging
import sys
from pathlib import Path
import pandas as pd

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QMainWindow, QTabWidget, QAction, QFileDialog,
    QMessageBox, QStatusBar, QDialog, QLabel
)
from PyQt5.QtGui import QIcon
from excel_import import import_specific_table
from config import config
from change_password import ChangePasswordDialog
from user_management import AddUserDialog, UserManagementDialog  # 新增导入
from log_viewer import LogViewer

logger = logging.getLogger('MainWindow')


class MainWindow(QMainWindow):
    def resource_path(relative_path):
        """
        获取资源绝对路径 - 兼容PyInstaller打包模式和开发模式
        专门处理Windows 7 32位系统的路径问题

        参数:
            relative_path: 资源的相对路径

        返回:
            资源的绝对路径
        """
        try:
            # 1. PyInstaller创建临时文件夹时会设置_MEIPASS属性
            base_path = sys._MEIPASS
        except AttributeError:
            # 2. 非PyInstaller环境: 使用当前脚本所在目录
            base_path = os.path.abspath(".")

        # 3. Windows 7兼容处理: 修复短路径问题
        full_path = os.path.join(base_path, relative_path)

        # 4. 日志记录用于调试
        logging.debug(f"资源查找: 相对路径='{relative_path}', 完整路径='{full_path}'")

        # 5. 路径标准化处理 (Windows 7关键!)
        normalized_path = os.path.normpath(full_path)

        # 6. 检查文件是否存在 (开发环境调试)
        if not os.path.exists(normalized_path):
            logging.warning(f"资源文件不存在: {normalized_path}")

            # 尝试回退方案: 在程序目录查找
            fallback_path = os.path.join(os.getcwd(), relative_path)
            if os.path.exists(fallback_path):
                logging.info(f"使用回退路径: {fallback_path}")
                return fallback_path

        return normalized_path

    def __init__(self, db, username, permissions):
        super().__init__()
        self.db = db
        self.username = username
        self.query_tab = None  # 添加这一行


        # 确保权限字典不为空
        self.permissions = permissions or {
            'base_info': False,
            'rewards': False,
            'family': False,
            'resume': False
        }

        # 添加 is_admin 属性
        self.is_admin = self.db.is_admin(username)

        # 确保存在默认用户
        self.ensure_default_user()

        # 管理员自动拥有所有权限
        if self.is_admin:
            self.permissions = {
                'base_info': True,
                'rewards': True,
                'family': True,
                'resume': True
            }
            logger.info(f"管理员账号 {username} 获得所有权限")

        self.init_ui()
        logger.info(f"主窗口已创建，当前用户: {self.username}")
        logger.info(
            f"用户权限: base_info={self.permissions['base_info']}, rewards={self.permissions['rewards']}, family={self.permissions['family']}, resume={self.permissions['resume']}")

    def ensure_default_user(self):
        """如果 users 表中没有 admin，自动插入默认账号"""
        try:
            stored = self.db.get_password('admin')
            if stored is None:
                self.db.change_password('admin', '111111')
                logger.info("默认用户 admin 已创建，初始密码 111111")
        except Exception as e:
            logger.error(f"创建默认用户失败: {e}")

    def init_ui(self):
        """初始化用户界面"""
        try:
            # 设置窗口标题与大小
            self.setWindowTitle(f"人员信息管理系统 - {self.username}")
            self.resize(*config.MAIN_WINDOW_SIZE)

            # 菜单栏
            self.create_menubar()

            # 状态栏
            self.status_bar = QStatusBar()
            self.setStatusBar(self.status_bar)
            self.status_bar.showMessage(f"欢迎回来，{self.username}！")

            # 选项卡
            self.tab_widget = QTabWidget()
            self.setCentralWidget(self.tab_widget)

            # 根据权限添加查询标签页
            if self.permissions.get('base_info'):
                from query import QueryTab
                self.query_tab = QueryTab(self.db, self.permissions)
                self.tab_widget.addTab(self.query_tab, "综合查询")
            else:
                # 如果没有任何权限，显示提示信息
                if not any(self.permissions.values()):
                    no_permission_label = QLabel("您没有任何数据查看权限，请联系管理员")
                    no_permission_label.setAlignment(Qt.AlignCenter)
                    no_permission_label.setStyleSheet("font-size: 18px; color: red;")
                    self.tab_widget.addTab(no_permission_label, "提示")

            self.show()

            # 添加权限日志输出
            logger.info("用户权限状态:")
            logger.info(f"base_info: {self.permissions.get('base_info', False)}")
            logger.info(f"rewards: {self.permissions.get('rewards', False)}")
            logger.info(f"family: {self.permissions.get('family', False)}")
            logger.info(f"resume: {self.permissions.get('resume', False)}")

        except Exception as e:
            logger.exception("主窗口初始化失败")
            QMessageBox.critical(self, "致命错误", f"主窗口初始化失败: {str(e)}")

    def create_menubar(self):
        """创建菜单栏：文件和账户"""
        menubar = self.menuBar()

        # 文件菜单
        file_menu = menubar.addMenu("文件")

        # 根据权限添加导入菜单项 (统一使用lambda表达式)
        if self.permissions.get('base_info'):
            import_base_action = QAction("导入人员基本信息", self)
            import_base_action.triggered.connect(lambda: self.import_data('base_info'))
            file_menu.addAction(import_base_action)

        if self.permissions.get('rewards'):
            import_rewards_action = QAction("导入人员奖惩信息", self)
            import_rewards_action.triggered.connect(lambda: self.import_data('rewards'))
            file_menu.addAction(import_rewards_action)

        if self.permissions.get('family'):
            import_family_action = QAction("导入人员家庭成员信息", self)
            import_family_action.triggered.connect(lambda: self.import_data('family'))
            file_menu.addAction(import_family_action)

        if self.permissions.get('resume'):
            import_resume_action = QAction("导入人员简历信息", self)
            import_resume_action.triggered.connect(lambda: self.import_data('resume'))
            file_menu.addAction(import_resume_action)

        # 清空数据库菜单项（仅管理员可见）
        if self.is_admin:
            file_menu.addSeparator()
            clear_action = QAction("清空数据库", self)
            clear_action.triggered.connect(self.on_clear_database)
            file_menu.addAction(clear_action)

        # =================== 新增导出菜单 ===================
        export_menu = menubar.addMenu("导出")

        # 添加导出选项
        if self.permissions.get('base_info'):
            export_base_action = QAction("导出人员基本信息", self)
            export_base_action.triggered.connect(lambda: self.export_data('base_info'))
            export_menu.addAction(export_base_action)

        if self.permissions.get('rewards'):
            export_rewards_action = QAction("导出人员奖惩信息", self)
            export_rewards_action.triggered.connect(lambda: self.export_data('rewards'))
            export_menu.addAction(export_rewards_action)

        if self.permissions.get('family'):
            export_family_action = QAction("导出人员家庭成员信息", self)
            export_family_action.triggered.connect(lambda: self.export_data('family'))
            export_menu.addAction(export_family_action)

        if self.permissions.get('resume'):
            export_resume_action = QAction("导出人员简历信息", self)
            export_resume_action.triggered.connect(lambda: self.export_data('resume'))
            export_menu.addAction(export_resume_action)

        # 账户菜单
        account_menu = menubar.addMenu("账户")

        # 管理员专属功能
        if self.is_admin:
            # 添加账号
            add_user_action = QAction("添加账号", self)
            add_user_action.triggered.connect(self.on_add_user)
            account_menu.addAction(add_user_action)

            # 管理账号
            manage_users_action = QAction("管理账号", self)
            manage_users_action.triggered.connect(self.on_manage_users)
            account_menu.addAction(manage_users_action)

            account_menu.addSeparator()  # 添加分隔线

        # 修改密码（所有用户可见）
        change_pwd_action = QAction("修改密码", self)
        change_pwd_action.triggered.connect(self.on_change_password)
        account_menu.addAction(change_pwd_action)

        # =================== 日志菜单 ===================
        if self.is_admin:  # 检查当前用户是否是管理员
            log_menu = menubar.addMenu("日志")

            # 查看日志
            view_log_action = QAction("查看系统日志", self)
            view_log_action.triggered.connect(self.on_view_log)
            log_menu.addAction(view_log_action)

            # 清空日志
            clear_log_action = QAction("清空日志文件", self)
            clear_log_action.triggered.connect(self.on_clear_log)
            log_menu.addAction(clear_log_action)

    # =================== 新增导出数据方法 ===================
    def export_data(self, table_name: str):
        """导出指定表的数据到Excel文件"""
        try:
            # 检查当前查询标签页是否有查询结果
            if not hasattr(self, 'query_tab') or self.query_tab is None:
                QMessageBox.warning(self, "导出失败", "请先执行查询操作")
                return

            # 从查询标签页获取结果数据
            data = self.query_tab.current_results_dict.get(table_name, [])

            if not data:
                QMessageBox.warning(self, "导出失败", "没有可导出的数据")
                return

            # 获取表的中文名称
            table_name_mapping = {
                'base_info': '人员基本信息',
                'rewards': '人员奖惩信息',
                'family': '人员家庭成员信息',
                'resume': '人员简历信息'
            }
            chinese_name = table_name_mapping.get(table_name, table_name)

            # 选择保存位置
            file_path, _ = QFileDialog.getSaveFileName(
                self, f"保存{chinese_name}",
                f"{chinese_name}.xlsx",
                "Excel文件 (*.xlsx)"
            )

            if not file_path:
                return  # 用户取消了保存

            try:
                # 将数据转换为DataFrame
                import pandas as pd
                df = pd.DataFrame(data)

                # 移除id列
                if 'id' in df.columns:
                    df = df.drop(columns=['id'])

                # 保存到Excel
                df.to_excel(file_path, index=False)

                # 显示成功消息
                QMessageBox.information(
                    self, "导出成功",
                    f"{chinese_name}已成功导出到:\n{file_path}\n\n共导出{len(data)}条记录"
                )
                logger.info(f"成功导出{table_name}数据到: {file_path}")

            except Exception as e:
                logger.error(f"导出{table_name}失败: {e}")
                QMessageBox.critical(
                    self, "导出失败",
                    f"导出{chinese_name}时发生错误:\n{str(e)}"
                )

        except Exception as e:
            logger.error(f"导出过程中发生未预期错误: {e}")
            QMessageBox.critical(
                self, "严重错误",
                f"导出过程中发生严重错误:\n{str(e)}"
            )
    # ============== 新增：日志相关方法 ==============
    def on_view_log(self):
        """打开日志查看器"""
        try:
            log_viewer = LogViewer(config.LOG_FILE)
            log_viewer.show()
        except Exception as e:
            logger.error(f"打开日志查看器失败: {e}")
            QMessageBox.critical(self, "错误", f"无法打开日志文件: {e}")

    def on_clear_log(self):
        """清空日志文件"""
        reply = QMessageBox.question(
            self, "确认清空",
            "确定要清空所有日志记录吗？此操作不可恢复！",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            try:
                with open(config.LOG_FILE, 'w') as f:
                    f.write("")
                QMessageBox.information(self, "成功", "日志文件已清空")
                logger.info("用户清空了日志文件")
            except Exception as e:
                logger.error(f"清空日志文件失败: {e}")
                QMessageBox.critical(self, "错误", f"清空日志文件失败: {e}")

    def on_view_log(self):
        """打开日志查看器"""
        viewer = LogViewer(config.LOG_FILE)
        viewer.exec_()


    def import_data(self, table_name: str):
        """导入指定表的数据"""
        logger.info(f"尝试导入表: {table_name}")
        logger.info(f"当前用户权限: {self.permissions}")

        # 表名到中文的映射
        table_name_mapping = {
            'base_info': '人员基本信息',
            'rewards': '人员奖惩信息',
            'family': '人员家庭成员信息',
            'resume': '人员简历信息'
        }

        if table_name not in table_name_mapping:
            QMessageBox.critical(self, "错误", f"无效的表名: {table_name}")
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self, f"选择{table_name_mapping[table_name]}数据文件",
            "", "Excel Files (*.xlsx *.xls)"
        )
        if not file_path:
            return

        try:
            # 调用新的导入函数
            success, message = import_specific_table(file_path, self.db, table_name)
            if success:
                QMessageBox.information(self, "导入成功", message)
                self.status_bar.showMessage(f"{table_name_mapping[table_name]}导入成功")
            else:
                QMessageBox.critical(self, "导入失败", message)
                self.status_bar.showMessage(f"{table_name_mapping[table_name]}导入失败")
        except Exception as e:
            logger.exception(f"导入{table_name}过程中发生异常")
            QMessageBox.critical(
                self, "导入出错",
                f"导入{table_name_mapping[table_name]}时发生错误：{e}\n请查看日志获取详细信息"
            )
            self.status_bar.showMessage(f"{table_name_mapping[table_name]}导入异常")

    def on_clear_database(self):
        """清空数据库前提示确认"""
        reply = QMessageBox.question(
            self, "确认清空", "确认要清空数据库吗？此操作无法撤销。",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.clear_database()

    def clear_database(self):
        """实际执行数据库清空操作（移除内部的确认对话框）"""
        try:
            # 清空所有业务表
            tables = ['base_info', 'rewards', 'family', 'resume']
            cursor = self.db.conn.cursor()
            for tbl in tables:
                cursor.execute(f"DELETE FROM {tbl}")

            # 清空年度考核配置
            cursor.execute("DELETE FROM system_config WHERE config_key='assessment_years'")

            self.db.conn.commit()
            QMessageBox.information(self, "提示", "数据库已清空。")
            self.status_bar.showMessage("数据库已清空")
        except Exception as e:
            logger.error(f"清空数据库失败: {e}")
            QMessageBox.critical(self, "错误", f"清空数据库失败: {e}")

    def on_change_password(self):
        """弹出修改密码对话框"""
        dlg = ChangePasswordDialog(self.db, self.username)
        if dlg.exec_() == QDialog.Accepted:
            QMessageBox.information(self, "提示", "密码修改成功，请重新登录")
            self.close()

    def on_add_user(self):
        """弹出添加用户对话框"""
        dlg = AddUserDialog(self.db)
        dlg.exec_()

    def on_manage_users(self):
        """弹出用户管理对话框"""
        dlg = UserManagementDialog(self.db)
        dlg.exec_()

    def closeEvent(self, event):
        """关闭时确保数据库连接关闭"""
        logger.info(f"用户 {self.username} 退出系统")
        if hasattr(self.db, 'close'):
            self.db.close()
        event.accept()