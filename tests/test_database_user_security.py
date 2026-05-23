import os
import tempfile
import unittest

from core.database import Database


class DatabaseUserSecurityTests(unittest.TestCase):
    def make_db_path(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        return path

    def open_db(self):
        db = Database(self.make_db_path())
        self.addCleanup(db.close)
        return db

    def test_exact_admin_can_be_created_and_updated_by_change_password(self):
        db = self.open_db()

        self.assertTrue(db.change_password("admin", "first"))
        self.assertEqual("first", db.get_password("admin"))
        self.assertTrue(db.is_admin("admin"))

        self.assertTrue(db.change_password("admin", "second"))
        self.assertEqual("second", db.get_password("admin"))

    def test_reserved_admin_variants_cannot_be_added(self):
        db = self.open_db()

        for username in ("Admin", "ADMIN"):
            with self.subTest(username=username):
                self.assertFalse(db.add_user(username, "pw"))
                self.assertIsNone(db.get_password(username))

    def test_change_password_does_not_create_missing_admin_variant(self):
        db = self.open_db()

        self.assertFalse(db.change_password("Admin", "pw"))
        self.assertIsNone(db.get_password("Admin"))

    def test_existing_admin_variant_is_a_regular_user(self):
        db = self.open_db()
        db.conn.execute(
            "INSERT INTO users (username, password) VALUES (?, ?)",
            ("Admin", "old"),
        )
        db.conn.commit()

        self.assertFalse(db.is_admin("Admin"))
        self.assertFalse(db.is_admin("ADMIN"))
        self.assertIn("Admin", db.get_all_users())
        self.assertTrue(db.change_password("Admin", "new"))
        self.assertEqual("new", db.get_password("Admin"))


if __name__ == "__main__":
    unittest.main()
