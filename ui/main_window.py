import logging
import os

from PyQt5.QtCore import Qt, QThread
from PyQt5.QtWidgets import (
    QMainWindow, QTabWidget, QAction, QFileDialog,
    QMessageBox, QStatusBar, QDialog, QLabel, QProgressDialog
)
from core.database import Database
from services.excel_export import export_table_data
from services.excel_import import import_prepared_records, prepare_import_preview
from config import config
from ui.change_password import ChangePasswordDialog
from ui.confirm_dialog import confirm_danger
from ui.user_management import AddUserDialog, UserManagementDialog
from ui.log_viewer import LogViewer
from ui.styles import NO_PERMISSION_LABEL_STYLE
from ui.toast import show_toast
from ui.worker import Worker, WorkerResultHandler
from metadata.constants import ADMIN_PERMISSIONS, DEFAULT_PERMISSIONS, TABLE_LABELS, normalize_permissions

logger = logging.getLogger('MainWindow')


class MainWindow(QMainWindow):
    def __init__(self, db, username, permissions):
        super().__init__()
        self.db = db
        self.username = username
        self.query_tab = None  # 添加这一行
        self.last_import_dir = ""
        self.last_export_dir = ""
        self._last_tab_index = -1
        self._background_tasks = []

        # 确保权限字典不为空
        self.permissions = normalize_permissions(permissions or DEFAULT_PERMISSIONS.copy())

        # 添加 is_admin 属性
        self.is_admin = self.db.is_admin(username)


        # 管理员自动拥有所有权限
        if self.is_admin:
            self.permissions = normalize_permissions(ADMIN_PERMISSIONS.copy())
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
            self.tab_widget.currentChanged.connect(self.on_tab_changed)
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

            self.tab_widget.tabBar().setVisible(self.tab_widget.count() > 1)

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

    def _modern_progress_dialog_factory(self, title: str, message: str, icon_kind: str):
        """创建现代加载弹窗工厂，供特定后台任务覆盖默认进度框。"""
        def factory(parent, _task_title):
            from ui.loading_dialog import ModernLoadingDialog

            return ModernLoadingDialog(
                parent,
                title=title,
                message=message,
                icon_kind=icon_kind,
            )

        return factory

    def run_background_task(
        self,
        title: str,
        task_fn,
        on_success=None,
        on_error=None,
        progress_dialog_factory=None,
    ):
        """在线程中执行耗时任务，并显示忙碌进度框。"""
        if progress_dialog_factory is not None:
            progress = progress_dialog_factory(self, title)
        else:
            progress = QProgressDialog(title, "", 0, 0, self)
            progress.setWindowTitle("请稍候")
            progress.setWindowModality(Qt.WindowModal)
            progress.setCancelButton(None)
            progress.setMinimumDuration(0)
            progress.setAutoClose(False)
            progress.setAutoReset(False)
        progress.show()

        thread = QThread(self)
        worker = Worker(task_fn)
        worker.moveToThread(thread)

        task_ref = {
            "thread": thread,
            "worker": worker,
            "progress": progress,
        }

        def default_error(message: str):
            QMessageBox.critical(self, "操作失败", message)

        def cleanup():
            progress.close()
            progress.deleteLater()
            handler.deleteLater()
            if task_ref in self._background_tasks:
                self._background_tasks.remove(task_ref)

        handler = WorkerResultHandler(
            on_success=on_success,
            on_error=on_error or default_error,
            on_done=cleanup,
            parent=self,
        )
        task_ref["handler"] = handler
        self._background_tasks.append(task_ref)

        thread.started.connect(worker.run)
        worker.finished.connect(handler.handle_finished)
        worker.failed.connect(handler.handle_failed)
        worker.done.connect(handler.handle_done)
        worker.done.connect(worker.deleteLater)
        worker.done.connect(thread.quit)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    # =================== 新增导出数据方法 ===================
    def export_data(self, table_name: str):
        """导出指定表的数据到Excel文件"""
        try:
            # 检查当前查询标签页是否有查询结果
            if not hasattr(self, 'query_tab') or self.query_tab is None:
                self.set_status("导出失败：请先执行查询操作")
                QMessageBox.warning(self, "导出失败", "请先执行查询操作")
                return

            query_conditions_getter = getattr(self.query_tab, "get_last_query_conditions", None)
            query_conditions = query_conditions_getter() if callable(query_conditions_getter) else None
            if query_conditions is None:
                self.set_status("导出失败：请先执行查询操作")
                QMessageBox.warning(self, "导出失败", "请先执行查询操作")
                return

            count_result = self.db.search_personnel(
                table_name=table_name,
                limit=1,
                offset=0,
                **query_conditions,
            )
            total_count = int(count_result.get("total_count", 0))
            if total_count <= 0:
                self.set_status(f"导出失败：{TABLE_LABELS.get(table_name, table_name)}没有可导出的数据")
                QMessageBox.warning(self, "导出失败", "没有可导出的数据")
                return

            chinese_name = TABLE_LABELS.get(table_name, table_name)
            default_file_name = f"{chinese_name}.xlsx"
            last_dialog_dir = self.get_dialog_dir(self.last_export_dir)
            default_save_path = (
                os.path.join(last_dialog_dir, default_file_name)
                if last_dialog_dir else default_file_name
            )

            # 选择保存位置
            file_path, _ = QFileDialog.getSaveFileName(
                self, f"保存{chinese_name}",
                default_save_path,
                "Excel文件 (*.xlsx)"
            )

            if not file_path:
                return  # 用户取消了保存
            self.last_export_dir = self.get_selected_dir(file_path)

            export_query_conditions = dict(query_conditions)

            def export_task():
                export_db = Database(config.DB_PATH)
                try:
                    results_dict = export_db.search_personnel(
                        table_name=table_name,
                        **export_query_conditions,
                    )
                    export_data = [dict(row) for row in results_dict.get(table_name, [])]
                    assessment_years = export_db.get_assessment_years()
                    return export_table_data(export_data, file_path, table_name, assessment_years)
                finally:
                    export_db.close()

            def handle_export_success(exported_count):
                self.set_status(f"导出成功：{chinese_name}，{exported_count} 条，保存到 {file_path}")
                show_toast(self, f"{chinese_name}导出成功，共 {exported_count} 条")
                logger.info(f"成功导出{table_name}数据到: {file_path}")

            def handle_export_error(message: str):
                logger.error(f"导出{table_name}失败: {message}")
                self.set_status(f"导出失败：{chinese_name}")
                QMessageBox.critical(
                    self, "导出失败",
                    f"导出{chinese_name}时发生错误:\n{message}"
                )

            self.run_background_task(
                "正在导出数据",
                export_task,
                handle_export_success,
                handle_export_error,
                progress_dialog_factory=self._modern_progress_dialog_factory(
                    "正在导出数据",
                    f"正在生成{chinese_name} Excel 文件，请稍候...",
                    "export",
                ),
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
        if confirm_danger(self, "确认清空日志", "确定要清空所有日志记录吗？", "清空日志"):
            try:
                with open(config.LOG_FILE, 'w') as f:
                    f.write("")
                self.set_status("日志文件已清空")
                show_toast(self, "日志文件已清空")
                logger.info("用户清空了日志文件")
            except Exception as e:
                logger.error(f"清空日志文件失败: {e}")
                self.set_status("清空日志文件失败")
                QMessageBox.critical(self, "错误", f"清空日志文件失败: {e}")

    def clear_query_cache(self):
        """清空查询页缓存，避免数据变更后继续显示旧结果。"""
        if self.query_tab is not None and hasattr(self.query_tab, 'clear_results'):
            self.query_tab.clear_results()

    def on_tab_changed(self, index: int):
        """切换主选项卡时保留查询条件。"""
        if self.query_tab is None:
            self._last_tab_index = index
            return

        query_index = self.tab_widget.indexOf(self.query_tab)
        if self._last_tab_index == query_index and hasattr(self.query_tab, 'save_query_state'):
            self.query_tab.save_query_state()

        if index == query_index and hasattr(self.query_tab, 'restore_query_state'):
            self.query_tab.restore_query_state()

        self._last_tab_index = index

    def get_dialog_dir(self, path: str) -> str:
        """获取文件选择框可用的初始目录。"""
        if path and os.path.isdir(path):
            return path
        return ""

    def get_selected_dir(self, file_path: str) -> str:
        """获取用户选择文件所在目录。"""
        return os.path.dirname(file_path) if file_path else ""

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

        if table_name == "base_info":
            message_box.setText(f"本次导入的{table_label}中有 {len(duplicate_keys)} 条记录与数据库已有人员重复。")
            message_box.setInformativeText(
                "重复判断规则：序号和姓名都相同。\n\n"
                f"{sample_text}\n\n"
                "选择“更新并新增”后，系统会更新匹配人员的基本信息，新增 Excel 中的新人员，"
                "并保留数据库中未出现在 Excel 的人员。"
            )
            confirm_button = message_box.addButton("更新并新增", QMessageBox.AcceptRole)
            confirm_mode = 'merge'
        else:
            message_box.setText(f"本次导入的{table_label}中有 {len(duplicate_keys)} 条重复明细。")
            message_box.setInformativeText(
                "重复判断规则：同一人员且明细内容完全相同。\n\n"
                f"{sample_text}\n\n"
                "选择“跳过重复并追加新增明细”后，系统只插入新增明细，重复明细不会再次写入。"
            )
            confirm_button = message_box.addButton("跳过重复并追加新增明细", QMessageBox.AcceptRole)
            confirm_mode = 'append_unique'

        message_box.addButton("取消", QMessageBox.RejectRole)
        message_box.setDefaultButton(confirm_button)
        message_box.exec_()

        clicked_button = message_box.clickedButton()
        if clicked_button == confirm_button:
            return confirm_mode
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
            self.get_dialog_dir(self.last_import_dir), "Excel Files (*.xlsx *.xls)"
        )
        if not file_path:
            return
        self.last_import_dir = self.get_selected_dir(file_path)

        table_label = TABLE_LABELS[table_name]

        def preview_task():
            return prepare_import_preview(file_path, config.DB_PATH, table_name)

        def handle_preview_success(preview_result):
            if not preview_result.get("success"):
                message = preview_result.get("message", "读取文件失败")
                QMessageBox.critical(self, "导入失败", message)
                self.set_status(f"导入失败：{table_label}，{message}")
                return

            duplicate_keys = preview_result.get("duplicate_keys", [])
            import_mode = self.confirm_import_mode(table_name, duplicate_keys)
            if import_mode == 'cancel':
                self.set_status(f"导入已取消：{table_label}")
                return

            mode_labels = {
                'append': "导入",
                'merge': "更新并新增",
                'append_unique': "跳过重复并追加新增明细",
            }
            mode_label = mode_labels.get(import_mode, "导入")

            def import_task():
                return import_prepared_records(
                    config.DB_PATH,
                    table_name,
                    preview_result.get("records", []),
                    preview_result.get("assessment_years"),
                )

            def handle_import_success(import_result):
                message = import_result.get("message", "导入完成")
                if not import_result.get("success"):
                    QMessageBox.critical(self, "导入失败", message)
                    self.set_status(f"导入失败：{table_label}，{message}")
                    return

                self.clear_query_cache()
                self.set_status(f"{mode_label}成功：{table_label}，{message}")
                show_toast(self, f"{mode_label}成功：{table_label}，{message}")

            def handle_import_error(message: str):
                QMessageBox.critical(self, "导入失败", message)
                self.set_status(f"导入失败：{table_label}，{message}")

            self.run_background_task(
                "正在导入数据",
                import_task,
                handle_import_success,
                handle_import_error,
                progress_dialog_factory=self._modern_progress_dialog_factory(
                    "正在导入数据",
                    f"正在{mode_label}{table_label}，请稍候...",
                    "import",
                ),
            )

        def handle_preview_error(message: str):
            logger.error(f"读取{table_name}导入文件失败: {message}")
            QMessageBox.critical(
                self,
                "导入出错",
                f"读取{table_label}导入文件时发生错误：{message}\n请查看日志获取详细信息"
            )
            self.set_status(f"导入异常：{table_label}，请查看日志")

        self.run_background_task(
            "正在读取数据",
            preview_task,
            handle_preview_success,
            handle_preview_error,
            progress_dialog_factory=self._modern_progress_dialog_factory(
                "正在读取数据",
                f"正在解析{table_label}导入文件，请稍候...",
                "import",
            ),
        )

    def on_clear_database(self):
        """清空数据库前提示确认"""
        if confirm_danger(self, "确认清空数据库", "确认要清空数据库吗？", "清空数据库"):
            self.clear_database()

    def clear_database(self):
        """实际执行数据库清空操作（移除内部的确认对话框）"""
        if self.db.clear_business_data():
            self.clear_query_cache()
            self.set_status("数据库已清空，查询结果已清除")
            show_toast(self, "数据库已清空，查询结果已清除")
            return

        self.set_status("清空数据库失败，请查看日志")
        QMessageBox.critical(self, "错误", "清空数据库失败，请查看日志")

    def on_change_password(self):
        """弹出修改密码对话框"""
        dlg = ChangePasswordDialog(self.db, self.username)
        if dlg.exec_() == QDialog.Accepted:
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
        if self.query_tab is not None and hasattr(self.query_tab, 'close_ai_dialog'):
            self.query_tab.close_ai_dialog()
        if hasattr(self.db, 'close'):
            self.db.close()
        event.accept()
