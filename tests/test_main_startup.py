import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import main


class FakeApp:
    def __init__(self):
        self.exec_called = False
        self.quit_called = False

    def setWindowIcon(self, _icon):
        pass

    def windowIcon(self):
        return None

    def setFont(self, _font):
        pass

    def exec_(self):
        self.exec_called = True
        return 0

    def quit(self):
        self.quit_called = True


class FakeDatabase:
    def __init__(self):
        self.closed = False

    def get_password(self, _username):
        return "pw"

    def get_user_permissions(self, _username):
        return {
            "base_info": True,
            "rewards": False,
            "family": False,
            "resume": False,
        }

    def is_admin(self, _username):
        return False

    def close(self):
        self.closed = True


class FakeLoginDialog:
    Accepted = 1

    def __init__(self, _db):
        pass

    def setWindowIcon(self, _icon):
        pass

    def exec_(self):
        return self.Accepted

    def get_username(self):
        return "analyst"


class MainStartupTests(unittest.TestCase):
    def test_database_check_failure_closes_db_and_returns_nonzero_without_event_loop(self):
        app = FakeApp()
        db = FakeDatabase()

        with (
            patch("main.create_application", return_value=app),
            patch("main.Database", return_value=db),
            patch("main.check_database_connection", return_value=False),
            patch("main.QMessageBox.critical") as critical,
        ):
            exit_code = main.main()

        self.assertEqual(1, exit_code)
        self.assertTrue(db.closed)
        self.assertTrue(app.quit_called)
        self.assertFalse(app.exec_called)
        critical.assert_called_once()

    def test_main_window_creation_failure_closes_db_and_returns_nonzero_without_event_loop(self):
        app = FakeApp()
        db = FakeDatabase()

        with (
            patch("main.create_application", return_value=app),
            patch("main.Database", return_value=db),
            patch("main.check_database_connection", return_value=True),
            patch("main.LoginDialog", FakeLoginDialog),
            patch("main.MainWindow", side_effect=RuntimeError("boom")),
            patch("main.QMessageBox.critical") as critical,
        ):
            exit_code = main.main()

        self.assertEqual(1, exit_code)
        self.assertTrue(db.closed)
        self.assertTrue(app.quit_called)
        self.assertFalse(app.exec_called)
        critical.assert_called_once()


if __name__ == "__main__":
    unittest.main()
