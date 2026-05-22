import os
import sqlite3
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QHeaderView

from metadata.constants import TABLE_LABELS
from ui.user_management import CenteredIconDelegate, UserManagementDialog


class FakeUserDb:
    def __init__(self, permissions):
        self.permissions = permissions
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("CREATE TABLE users (username TEXT)")
        self.conn.executemany(
            "INSERT INTO users (username) VALUES (?)",
            [("admin",), ("analyst",)],
        )
        self.conn.commit()

    def get_user_permissions(self, username):
        return self.permissions[username]


class UserManagementDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_dialog(self):
        permissions = {
            "analyst": {
                "base_info": True,
                "rewards": False,
                "family": True,
                "resume": False,
            }
        }
        dialog = UserManagementDialog(FakeUserDb(permissions))
        self.addCleanup(dialog.deleteLater)
        return dialog

    def permission_col(self, table_name):
        return 1 + list(TABLE_LABELS.keys()).index(table_name)

    def test_permission_cells_use_icons_instead_of_check_text(self):
        dialog = self.make_dialog()

        granted_item = dialog.user_table.item(0, self.permission_col("base_info"))
        denied_item = dialog.user_table.item(0, self.permission_col("rewards"))

        self.assertEqual("", granted_item.text())
        self.assertFalse(granted_item.icon().isNull())
        self.assertEqual("有权限", granted_item.toolTip())

        self.assertEqual("", denied_item.text())
        self.assertFalse(denied_item.icon().isNull())
        self.assertEqual("无权限", denied_item.toolTip())

    def test_permission_columns_use_centered_icon_delegate(self):
        dialog = self.make_dialog()

        for table_name in TABLE_LABELS:
            col = self.permission_col(table_name)
            self.assertIsInstance(dialog.user_table.itemDelegateForColumn(col), CenteredIconDelegate)
        self.assertEqual(24, dialog.user_table.iconSize().width())
        self.assertEqual(24, dialog.user_table.iconSize().height())

    def test_family_permission_column_is_wider_for_full_header(self):
        dialog = self.make_dialog()
        family_col = self.permission_col("family")
        rewards_col = self.permission_col("rewards")

        self.assertEqual(QHeaderView.Interactive, dialog.user_table.horizontalHeader().sectionResizeMode(family_col))
        self.assertGreater(dialog.user_table.columnWidth(family_col), dialog.user_table.columnWidth(rewards_col))
        self.assertGreaterEqual(dialog.user_table.columnWidth(family_col), 210)


if __name__ == "__main__":
    unittest.main()
