import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QDialog, QHeaderView

from metadata.constants import TABLE_LABELS
from ui.change_password import ChangePasswordDialog
from ui.login import LoginDialog
from ui.user_management import AddUserDialog, CenteredIconDelegate, EditPermissionsDialog, UserManagementDialog


class FakeUserDb:
    def __init__(self, permissions):
        self.permissions = permissions

    def get_user_permissions(self, username):
        return self.permissions[username]

    def get_all_users(self):
        return ["analyst"]


class FakeEditUserDb(FakeUserDb):
    def __init__(self, permissions):
        super().__init__(permissions)
        self.set_permission_calls = []

    def set_user_permissions(self, username, permissions):
        self.set_permission_calls.append((username, permissions))


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


class FakeLoginDb:
    def __init__(self, password):
        self.password = password
        self.get_password_calls = []

    def get_password(self, username):
        self.get_password_calls.append(username)
        return self.password


class FakeChangePasswordDb:
    def __init__(self, stored_password="oldpw", change_success=True):
        self.stored_password = stored_password
        self.change_success = change_success
        self.get_password_calls = []
        self.change_password_calls = []

    def get_password(self, username):
        self.get_password_calls.append(username)
        return self.stored_password

    def change_password(self, username, new_password):
        self.change_password_calls.append((username, new_password))
        return self.change_success


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

    def test_password_with_surrounding_whitespace_is_rejected_before_db_lookup(self):
        cases = [
            (" pw", " pw"),
            ("pw ", "pw "),
            ("pw", "pw "),
        ]
        for password, confirm in cases:
            with self.subTest(password=password, confirm=confirm):
                db = FakeAddUserDb()
                dialog = self.make_dialog(db)
                dialog.username_input.setText("analyst")
                dialog.password_input.setText(password)
                dialog.confirm_input.setText(confirm)

                with patch("ui.user_management.QMessageBox.warning") as warning:
                    dialog.on_ok()

                warning.assert_called_once()
                self.assertEqual([], db.get_password_calls)
                self.assertEqual([], db.add_user_calls)
                self.assertEqual([], db.set_permission_calls)

    def test_related_permission_checkbox_forces_base_info(self):
        db = FakeAddUserDb()
        dialog = self.make_dialog(db)

        dialog.permission_checks["family"].setChecked(True)
        self.assertTrue(dialog.permission_checks["base_info"].isChecked())

        dialog.permission_checks["base_info"].setChecked(False)
        self.assertFalse(dialog.permission_checks["base_info"].isChecked())
        self.assertFalse(dialog.permission_checks["family"].isChecked())


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

    def test_permission_cells_normalize_related_permissions(self):
        dialog = UserManagementDialog(
            FakeUserDb(
                {
                    "analyst": {
                        "base_info": False,
                        "rewards": False,
                        "family": True,
                        "resume": False,
                    }
                }
            )
        )
        self.addCleanup(dialog.deleteLater)

        base_info_item = dialog.user_table.item(0, self.permission_col("base_info"))
        family_item = dialog.user_table.item(0, self.permission_col("family"))

        self.assertEqual("有权限", base_info_item.toolTip())
        self.assertEqual("有权限", family_item.toolTip())

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

    def test_edit_permissions_dialog_normalizes_initial_and_saved_permissions(self):
        db = FakeEditUserDb(
            {
                "analyst": {
                    "base_info": False,
                    "rewards": True,
                    "family": False,
                    "resume": False,
                }
            }
        )
        dialog = EditPermissionsDialog(
            db,
            "analyst",
            {
                "base_info": False,
                "rewards": True,
                "family": False,
                "resume": False,
            },
        )
        self.addCleanup(dialog.deleteLater)

        self.assertTrue(dialog.permission_checks["base_info"].isChecked())
        self.assertTrue(dialog.permission_checks["rewards"].isChecked())

        dialog.save_permissions()

        self.assertEqual(
            [
                (
                    "analyst",
                    {
                        "base_info": True,
                        "rewards": True,
                        "family": False,
                        "resume": False,
                    },
                )
            ],
            db.set_permission_calls,
        )


class LoginDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_dialog(self, db):
        dialog = LoginDialog(db)
        self.addCleanup(dialog.deleteLater)
        return dialog

    def test_login_accepts_password_with_surrounding_whitespace(self):
        db = FakeLoginDb("pw")
        dialog = self.make_dialog(db)
        dialog.username_edit.setText("analyst")
        dialog.password_edit.setText(" pw ")

        dialog.authenticate()

        self.assertEqual(["analyst"], db.get_password_calls)
        self.assertEqual(QDialog.Accepted, dialog.result())


class ChangePasswordDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_dialog(self, db):
        dialog = ChangePasswordDialog(db, "analyst")
        self.addCleanup(dialog.deleteLater)
        return dialog

    def test_new_password_with_surrounding_whitespace_is_rejected_before_db_lookup(self):
        cases = [
            ("new ", "new "),
            (" new", " new"),
            ("new", "new "),
        ]
        for new_password, confirm in cases:
            with self.subTest(new_password=new_password, confirm=confirm):
                db = FakeChangePasswordDb()
                dialog = self.make_dialog(db)
                dialog.old_edit.setText("oldpw")
                dialog.new_edit.setText(new_password)
                dialog.confirm_edit.setText(confirm)

                with patch("ui.change_password.QMessageBox.warning") as warning:
                    dialog.on_ok()

                warning.assert_called_once()
                self.assertEqual([], db.get_password_calls)
                self.assertEqual([], db.change_password_calls)


if __name__ == "__main__":
    unittest.main()
