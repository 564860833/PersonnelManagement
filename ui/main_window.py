import logging

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QMainWindow, QTabWidget, QAction, QFileDialog,
    QMessageBox, QStatusBar, QDialog, QLabel
)
from services.excel_export import export_table_data
from services.excel_import import import_specific_table, prepare_import_records
from config import config
from ui.change_password import ChangePasswordDialog
from ui.user_management import AddUserDialog, UserManagementDialog
from ui.log_viewer import LogViewer
from ui.styles import NO_PERMISSION_LABEL_STYLE
from metadata.constants import ADMIN_PERMISSIONS, DEFAULT_PERMISSIONS, TABLE_LABELS

logger = logging.getLogger('MainWindow')


class MainWindow(QMainWindow):
    def __init__(self, db, username, permissions):
        super().__init__()
        self.db = db
        self.username = username
        self.query_tab = None  # 添加这一行


        # 确保权限字典不为空
        self.permissions = permissions or DEFAULT_PERMISSIONS.copy()

        # 添加 is_admin 属性
        self.is_admin = self.db.is_admin(username)


        # 管理员自动拥有所有权限
        if self.is_admin:
            self.permissions = ADMIN_PERMISSIONS.copy()
            logger.info(f"管理员账号 {username} 获得所有权限")

        self.init_ui()
        logger.info(f"主窗口已创建，当前用户: {self.username}")
        logger.info(
            f"用户权限: base_info={self.permissions['base_info']}, rewards={self.permissions['rewards']}, family={self.permissions['family']}, resume={self.permissions['resume']}")

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
                from ui.query import QueryTab
                self.query_tab = QueryTab(self.db, self.permissions)
                self.tab_widget.addTab(self.query_tab, "综合查询")
            else:
                # 如果没有任何权限，显示提示信息
                if not any(self.permissions.values()):
                    no_permission_label = QLabel("您没有任何数据查看权限，请联系管理员")
                    no_permission_label.setAlignment(Qt.AlignCenter)
                    no_permission_label.setStyleSheet(NO_PERMISSION_LABEL_STYLE)
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

        for table_name, label in TABLE_LABELS.items():
            if self.permissions.get(table_name):
                import_action = QAction(f"导入{label}", self)
                import_action.triggered.connect(lambda _, t=table_name: self.import_data(t))
                file_menu.addAction(import_action)

        # 清空数据库菜单项（仅管理员可见）
        if self.is_admin:
            file_menu.addSeparator()
            clear_action = QAction("清空数据库", self)
            clear_action.triggered.connect(self.on_clear_database)
            file_menu.addAction(clear_action)

        # =================== 新增导出菜单 ===================
        export_menu = menubar.addMenu("导出")

        for table_name, label in TABLE_LABELS.items():
            if self.permissions.get(table_name):
                export_action = QAction(f"导出{label}", self)
                export_action.triggered.connect(lambda _, t=table_name: self.export_data(t))
                export_menu.addAction(export_action)

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

    def set_status(self, message: str, timeout: int = 8000):
        """统一更新主窗口状态栏。"""
        if hasattr(self, 'status_bar'):
            self.status_bar.showMessage(message, timeout)

    # =================== 新增导出数据方法 ===================
    def export_data(self, table_name: str):
        """导出指定表的数据到Excel文件"""
        try:
            # 检查当前查询标签页是否有查询结果
            if not hasattr(self, 'query_tab') or self.query_tab is None:
                self.set_status("导出失败：请先执行查询操作")
                QMessageBox.warning(self, "导出失败", "请先执行查询操作")
                return

            # 从查询标签页获取结果数据
            data = self.query_tab.current_results_dict.get(table_name, [])

            if not data:
                self.set_status(f"导出失败：{TABLE_LABELS.get(table_name, table_name)}没有可导出的数据")
                QMessageBox.warning(self, "导出失败", "没有可导出的数据")
                return

            chinese_name = TABLE_LABELS.get(table_name, table_name)

            # 选择保存位置
            file_path, _ = QFileDialog.getSaveFileName(
                self, f"保存{chinese_name}",
                f"{chinese_name}.xlsx",
                "Excel文件 (*.xlsx)"
            )

            if not file_path:
                return  # 用户取消了保存

            try:
                exported_count = export_table_data(data, file_path, table_name)

                # 显示成功消息
                QMessageBox.information(
                    self, "导出成功",
                    f"{chinese_name}已成功导出到:\n{file_path}\n\n共导出{exported_count}条记录"
                )
                self.set_status(f"导出成功：{chinese_name}，{exported_count} 条，保存到 {file_path}")
                logger.info(f"成功导出{table_name}数据到: {file_path}")

            except Exception as e:
                logger.error(f"导出{table_name}失败: {e}")
                self.set_status(f"导出失败：{chinese_name}")
                QMessageBox.critical(
                    self, "导出失败",
                    f"导出{chinese_name}时发生错误:\n{str(e)}"
                )

        except Exception as e:
            logger.error(f"导出过程中发生未预期错误: {e}")
            self.set_status("导出失败：发生未预期错误")
            QMessageBox.critical(
                self, "严重错误",
                f"导出过程中发生严重错误:\n{str(e)}"
            )
    # ============== 新增：日志相关方法 ==============
    def on_view_log(self):
        """打开日志查看器"""
        try:
            log_viewer = LogViewer(config.LOG_FILE)
            log_viewer.exec_()  # 修改这里：由 show() 改为 exec_()
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
                self.set_status("日志文件已清空")
                logger.info("用户清空了日志文件")
            except Exception as e:
                logger.error(f"清空日志文件失败: {e}")
                self.set_status("清空日志文件失败")
                QMessageBox.critical(self, "错误", f"清空日志文件失败: {e}")

    def clear_query_cache(self):
        """清空查询页缓存，避免数据变更后继续显示旧结果。"""
        if self.query_tab is not None and hasattr(self.query_tab, 'clear_results'):
            self.query_tab.clear_results()

    def confirm_import_mode(self, table_name: str, duplicate_keys: list) -> str:
        """当本次导入记录与数据库已有记录重复时，确认导入方式。"""
        if not duplicate_keys:
            return 'append'

        table_label = TABLE_LABELS.get(table_name, table_name)
        sample_keys = []
        for sequence, name in duplicate_keys[:5]:
            sequence_label = sequence or "空"
            sample_keys.append(f"序号 {sequence_label}，姓名 {name}")

        sample_text = "\n".join(sample_keys)
        if len(duplicate_keys) > 5:
            sample_text += f"\n等 {len(duplicate_keys)} 条重复记录"

        message_box = QMessageBox(self)
        message_box.setIcon(QMessageBox.Question)
        message_box.setWindowTitle("检测到重复数据")
        message_box.setText(f"本次导入的{table_label}中有 {len(duplicate_keys)} 条记录与数据库已有数据重复。")
        message_box.setInformativeText(
            "重复判断规则：序号和姓名都相同。\n\n"
            f"{sample_text}\n\n"
            "继续追加会产生重复记录；覆盖当前表会先清空该表再导入本次文件。"
        )

        append_button = message_box.addButton("追加导入", QMessageBox.AcceptRole)
        overwrite_button = message_box.addButton("覆盖当前表", QMessageBox.DestructiveRole)
        message_box.addButton("取消", QMessageBox.RejectRole)
        message_box.setDefaultButton(append_button)
        message_box.exec_()

        clicked_button = message_box.clickedButton()
        if clicked_button == overwrite_button:
            return 'overwrite'
        if clicked_button == append_button:
            return 'append'
        return 'cancel'


    def import_data(self, table_name: str):
        """导入指定表的数据"""
        logger.info(f"尝试导入表: {table_name}")
        logger.info(f"当前用户权限: {self.permissions}")

        if table_name not in TABLE_LABELS:
            QMessageBox.critical(self, "错误", f"无效的表名: {table_name}")
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self, f"选择{TABLE_LABELS[table_name]}数据文件",
            "", "Excel Files (*.xlsx *.xls)"
        )
        if not file_path:
            return

        try:
            preview_success, preview_message, preview_records = prepare_import_records(file_path, self.db, table_name)
            if not preview_success:
                QMessageBox.critical(self, "导入失败", preview_message)
                self.set_status(f"导入失败：{TABLE_LABELS[table_name]}，{preview_message}")
                return

            duplicate_keys = self.db.find_duplicate_person_keys(table_name, preview_records)
            import_mode = self.confirm_import_mode(table_name, duplicate_keys)
            if import_mode == 'cancel':
                self.set_status(f"导入已取消：{TABLE_LABELS[table_name]}")
                return

            if import_mode == 'overwrite':
                if not self.db.clear_table_data(table_name):
                    QMessageBox.critical(self, "导入失败", f"清空{TABLE_LABELS[table_name]}失败，请查看日志")
                    self.set_status(f"覆盖导入失败：清空{TABLE_LABELS[table_name]}失败")
                    return
                self.clear_query_cache()

            # 调用新的导入函数
            success, message = import_specific_table(file_path, self.db, table_name)
            if success:
                self.clear_query_cache()
                mode_label = "覆盖导入" if import_mode == 'overwrite' else "追加导入"
                QMessageBox.information(self, "导入成功", message)
                self.set_status(f"{mode_label}成功：{TABLE_LABELS[table_name]}，{message}")
            else:
                QMessageBox.critical(self, "导入失败", message)
                self.set_status(f"导入失败：{TABLE_LABELS[table_name]}，{message}")
        except Exception as e:
            logger.exception(f"导入{table_name}过程中发生异常")
            QMessageBox.critical(
                self, "导入出错",
                f"导入{TABLE_LABELS[table_name]}时发生错误：{e}\n请查看日志获取详细信息"
            )
            self.set_status(f"导入异常：{TABLE_LABELS[table_name]}，请查看日志")

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
        if self.db.clear_business_data():
            self.clear_query_cache()
            QMessageBox.information(self, "提示", "数据库已清空。")
            self.set_status("数据库已清空，查询结果已清除")
            return

        self.set_status("清空数据库失败，请查看日志")
        QMessageBox.critical(self, "错误", "清空数据库失败，请查看日志")

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
