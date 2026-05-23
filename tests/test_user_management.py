import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QHeaderView

from metadata.constants import TABLE_LABELS
from ui.user_management import AddUserDialog, CenteredIconDelegate, UserManagementDialog


class FakeUserDb:
    def __init__(self, permissions):
        self.permissions = permissions

    def get_user_permissions(self, username):
        return self.permissions[username]

    def get_all_users(self):
        return ["analyst"]


class FakeAddUserDb:
    def __init__(self, add_success=True):
        self.add_success = add_success
        self.add_user_calls = []
        self.get_password_calls = []
        self.set_permission_calls = []

    def is_reserved_admin_username(self, username):
        return isinstance(username, str) and username.casefold() == "admin"

    def get_password(self, username):
        self.get_password_calls.append(username)
        return None

    def add_user(self, username, password):
        self.add_user_calls.append((username, password))
        return self.add_success

    def set_user_permissions(self, username, permissions):
        self.set_permission_calls.append((username, permissions))


class AddUserDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_dialog(self, db):
        dialog = AddUserDialog(db)
        self.addCleanup(dialog.deleteLater)
        return dialog

    def fill_required_fields(self, dialog, username="analyst"):
        dialog.username_input.setText(username)
        dialog.password_input.setText("pw")
        dialog.confirm_input.setText("pw")

    def test_reserved_admin_variant_is_rejected_before_user_write(self):
        db = FakeAddUserDb()
        dialog = self.make_dialog(db)
        self.fill_required_fields(dialog, "Admin")

        with patch("ui.user_management.QMessageBox.warning") as warning:
            dialog.on_ok()

        warning.assert_called_once()
        self.assertEqual([], db.get_password_calls)
        self.assertEqual([], db.add_user_calls)
        self.assertEqual([], db.set_permission_calls)

    def test_add_user_failure_does_not_write_permissions(self):
        db = FakeAddUserDb(add_success=False)
        dialog = self.make_dialog(db)
        self.fill_required_fields(dialog)

        with patch("ui.user_management.QMessageBox.critical") as critical:
            dialog.on_ok()

        critical.assert_called_once()
        self.assertEqual([("analyst", "pw")], db.add_user_calls)
        self.assertEqual([], db.set_permission_calls)


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
