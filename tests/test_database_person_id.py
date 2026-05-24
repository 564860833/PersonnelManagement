import os
import sqlite3
import tempfile
import unittest

import pandas as pd

from core.database import Database
from services.excel_export import export_table_data


class DatabasePersonIdTests(unittest.TestCase):
    def make_db_path(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        return path

    def open_db(self):
        db = Database(self.make_db_path())
        self.addCleanup(db.close)
        return db

    def test_new_schema_uses_person_id_foreign_keys_and_indexes(self):
        db = self.open_db()

        self.assertEqual(1, db.conn.execute("PRAGMA foreign_keys").fetchone()[0])
        self.assertIn("person_id", db.get_table_columns("rewards"))
        self.assertNotIn("sequence", db.get_table_columns("rewards"))
        self.assertNotIn("name", db.get_table_columns("rewards"))

        fk_rows = db.conn.execute("PRAGMA foreign_key_list(rewards)").fetchall()
        self.assertEqual("base_info", fk_rows[0]["table"])
        self.assertEqual("person_id", fk_rows[0]["from"])
        self.assertEqual("id", fk_rows[0]["to"])

        indexes = {row["name"] for row in db.conn.execute("PRAGMA index_list(base_info)").fetchall()}
        self.assertIn("idx_base_info_sequence_name", indexes)
        self.assertIn("idx_base_info_name_without_sequence", indexes)

    def test_import_and_query_related_rows_by_person_id(self):
        db = self.open_db()

        db.import_excel_data("base_info", [{"sequence": 1, "name": "张三", "current_grade": "一级"}])
        db.import_excel_data("rewards", [{"sequence": "1.0", "name": "张三", "reward_name": "优秀"}])

        results = db.search_personnel(name="张三")
        self.assertEqual(1, len(results["base_info"]))
        self.assertEqual(1, results["total_count"])
        self.assertEqual(1, len(results["rewards"]))
        reward = results["rewards"][0]
        self.assertEqual(results["base_info"][0]["id"], reward["person_id"])
        self.assertEqual(1, reward["sequence"])
        self.assertEqual("张三", reward["name"])
        self.assertEqual("优秀", reward["reward_name"])

    def test_birth_month_search_matches_migrated_legacy_datetime_text(self):
        path = self.make_db_path()
        conn = sqlite3.connect(path)
        conn.executescript(
            """
            CREATE TABLE base_info (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sequence INTEGER,
                name TEXT NOT NULL,
                birth_date TEXT
            );
            INSERT INTO base_info(sequence, name, birth_date) VALUES (1, 'A', '1990-01-01 00:00:00');
            INSERT INTO base_info(sequence, name, birth_date) VALUES (2, 'B', '1990-02-01 00:00:00');
            """
        )
        conn.commit()
        conn.close()

        db = Database(path)
        self.addCleanup(db.close)

        results = db.search_personnel(birth_start="1990.01", birth_end="1990.01")

        self.assertEqual(["A"], [row["name"] for row in results["base_info"]])
        row = results["base_info"][0]
        self.assertEqual("1990-01", row["birth_date"])
        self.assertEqual("1990-01-01 00:00:00", row["birth_date_display"])

    def test_date_migration_preserves_invalid_legacy_display_and_clears_standard(self):
        path = self.make_db_path()
        conn = sqlite3.connect(path)
        conn.executescript(
            """
            CREATE TABLE base_info (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sequence INTEGER,
                name TEXT NOT NULL,
                birth_date TEXT
            );
            INSERT INTO base_info(sequence, name, birth_date) VALUES (1, 'A', 'not-a-date');
            """
        )
        conn.commit()
        conn.close()

        db = Database(path)
        self.addCleanup(db.close)

        row = db.get_all_data("base_info")[0]
        self.assertIsNone(row["birth_date"])
        self.assertEqual("not-a-date", row["birth_date_display"])

    def test_birth_month_search_keeps_existing_month_format(self):
        db = self.open_db()
        db.import_excel_data(
            "base_info",
            [
                {"sequence": 1, "name": "A", "birth_date": "1990.01"},
                {"sequence": 2, "name": "B", "birth_date": "1990.02"},
            ],
        )

        results = db.search_personnel(birth_start="1990.01", birth_end="1990.01")

        self.assertEqual(["A"], [row["name"] for row in results["base_info"]])
        row = results["base_info"][0]
        self.assertEqual("1990-01", row["birth_date"])
        self.assertEqual("1990.01", row["birth_date_display"])

    def test_search_personnel_paginates_base_info_with_total_count(self):
        db = self.open_db()
        db.import_excel_data(
            "base_info",
            [
                {"sequence": 1, "name": "P1"},
                {"sequence": 2, "name": "P2"},
                {"sequence": 3, "name": "P3"},
            ],
        )

        results = db.search_personnel(table_name="base_info", limit=2, offset=1)

        self.assertEqual(3, results["total_count"])
        self.assertEqual(["P2", "P3"], [row["name"] for row in results["base_info"]])

    def test_search_personnel_paginates_related_tables_with_total_count(self):
        db = self.open_db()
        db.import_excel_data(
            "base_info",
            [
                {"sequence": 1, "name": "P1"},
                {"sequence": 2, "name": "P2"},
            ],
        )
        db.import_excel_data(
            "family",
            [
                {"sequence": 1, "name": "P1", "relation": "father", "family_name": "F1"},
                {"sequence": 1, "name": "P1", "relation": "mother", "family_name": "M1"},
                {"sequence": 2, "name": "P2", "relation": "spouse", "family_name": "S2"},
            ],
        )

        results = db.search_personnel(name="P1", table_name="family", limit=1, offset=1)

        self.assertEqual(2, results["total_count"])
        self.assertEqual(1, len(results["family"]))
        self.assertEqual("mother", results["family"][0]["relation"])
        self.assertEqual("P1", results["family"][0]["name"])

    def test_base_info_import_normalizes_birth_date_month(self):
        db = self.open_db()
        db.import_excel_data(
            "base_info",
            [{"sequence": 1, "name": "A", "birth_date": "1990-01-01 00:00:00"}],
        )

        row = db.get_all_data("base_info")[0]
        self.assertEqual("1990-01", row["birth_date"])
        self.assertEqual("1990-01-01 00:00:00", row["birth_date_display"])

    def test_date_placeholder_values_import_as_blank(self):
        db = self.open_db()
        db.import_excel_data(
            "base_info",
            [
                {
                    "sequence": 1,
                    "name": "A",
                    "birth_date": "-",
                    "party_date": "—",
                    "current_legal_position_date": "无",
                }
            ],
        )

        row = db.get_all_data("base_info")[0]
        self.assertIsNone(row["birth_date"])
        self.assertEqual("", row["birth_date_display"])
        self.assertIsNone(row["party_date"])
        self.assertEqual("", row["party_date_display"])
        self.assertIsNone(row["current_legal_position_date"])
        self.assertEqual("", row["current_legal_position_date_display"])

    def test_base_info_import_rejects_duplicate_people_within_batch(self):
        db = self.open_db()

        with self.assertRaisesRegex(ValueError, "重复人员"):
            db.import_excel_data(
                "base_info",
                [
                    {"sequence": 1, "name": "张三", "current_grade": "一级"},
                    {"sequence": "1.0", "name": " 张三 ", "current_grade": "二级"},
                ],
            )

        self.assertEqual([], db.get_all_data("base_info"))

    def test_related_import_rejects_missing_base_person(self):
        db = self.open_db()

        with self.assertRaisesRegex(ValueError, "无法关联到 base_info"):
            db.import_excel_data("family", [{"sequence": 99, "name": "不存在", "relation": "父亲"}])

        self.assertEqual([], db.get_all_data("family"))

    def test_related_import_skips_rows_without_business_fields(self):
        db = self.open_db()
        db.import_excel_data("base_info", [{"sequence": 1, "name": "张三"}])
        person_id = db.get_all_data("base_info")[0]["id"]

        db.import_excel_data("family", [{"sequence": 1, "name": "张三"}])
        db.import_excel_data("rewards", [{"person_id": person_id, "reward_name": "   "}])
        db.import_excel_data("resume", [{"sequence": 1, "name": "张三", "resume_text": "NaN"}])

        self.assertEqual([], db.get_all_data("family"))
        self.assertEqual([], db.get_all_data("rewards"))
        self.assertEqual([], db.get_all_data("resume"))

    def test_related_import_keeps_rows_with_business_fields(self):
        db = self.open_db()
        db.import_excel_data("base_info", [{"sequence": 1, "name": "张三"}])

        db.import_excel_data("family", [{"sequence": 1, "name": "张三", "relation": "父亲"}])
        db.import_excel_data("rewards", [{"sequence": 1, "name": "张三", "reward_name": "优秀"}])
        db.import_excel_data("resume", [{"sequence": 1, "name": "张三", "resume_text": "简历"}])

        self.assertEqual("父亲", db.get_all_data("family")[0]["relation"])
        self.assertEqual("优秀", db.get_all_data("rewards")[0]["reward_name"])
        self.assertEqual("简历", db.get_all_data("resume")[0]["resume_text"])

    def test_migrates_old_related_tables_to_person_id(self):
        path = self.make_db_path()
        conn = sqlite3.connect(path)
        conn.executescript(
            """
            CREATE TABLE base_info (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sequence INTEGER,
                name TEXT NOT NULL
            );
            CREATE TABLE rewards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sequence INTEGER,
                name TEXT NOT NULL,
                reward_name TEXT
            );
            CREATE TABLE family (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sequence INTEGER,
                name TEXT NOT NULL,
                relation TEXT,
                family_name TEXT,
                birth_date TEXT,
                political_status TEXT,
                work_unit TEXT,
                position TEXT
            );
            CREATE TABLE resume (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sequence INTEGER,
                name TEXT NOT NULL,
                resume_text TEXT
            );
            INSERT INTO base_info(sequence, name) VALUES (1, '张三');
            INSERT INTO rewards(sequence, name, reward_name) VALUES (1, '张三', '优秀');
            INSERT INTO family(sequence, name, relation, family_name) VALUES (1, '张三', '父亲', '张父');
            INSERT INTO resume(sequence, name, resume_text) VALUES (1, '张三', '简历');
            """
        )
        conn.commit()
        conn.close()

        db = Database(path)
        self.addCleanup(db.close)

        self.assertIn("person_id", db.get_table_columns("rewards"))
        self.assertNotIn("sequence", db.get_table_columns("rewards"))
        results = db.search_personnel(name="张三")
        self.assertEqual("优秀", results["rewards"][0]["reward_name"])
        self.assertEqual("张父", results["family"][0]["family_name"])
        self.assertEqual("简历", results["resume"][0]["resume_text"])

    def test_migration_rejects_unmatched_related_rows_without_half_migration(self):
        path = self.make_db_path()
        conn = sqlite3.connect(path)
        conn.executescript(
            """
            CREATE TABLE base_info (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sequence INTEGER,
                name TEXT NOT NULL
            );
            CREATE TABLE rewards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sequence INTEGER,
                name TEXT NOT NULL,
                reward_name TEXT
            );
            INSERT INTO base_info(sequence, name) VALUES (1, '张三');
            INSERT INTO rewards(sequence, name, reward_name) VALUES (2, '李四', '优秀');
            """
        )
        conn.commit()
        conn.close()

        with self.assertRaises(sqlite3.IntegrityError):
            Database(path)

        conn = sqlite3.connect(path)
        try:
            columns = [row[1] for row in conn.execute("PRAGMA table_info(rewards)").fetchall()]
            self.assertIn("sequence", columns)
            self.assertNotIn("person_id", columns)
        finally:
            conn.close()

    def test_base_info_import_preserves_matching_person_id(self):
        db = self.open_db()
        db.import_excel_data("base_info", [{"sequence": 1, "name": "张三", "current_grade": "一级"}])
        original_id = db.get_all_data("base_info")[0]["id"]
        db.import_excel_data("rewards", [{"sequence": 1, "name": "张三", "reward_name": "优秀"}])

        db.import_excel_data("base_info", [{"sequence": 1, "name": "张三", "current_grade": "二级"}])

        base_row = db.get_all_data("base_info")[0]
        self.assertEqual(original_id, base_row["id"])
        self.assertEqual("二级", base_row["current_grade"])
        self.assertEqual(original_id, db.search_personnel()["rewards"][0]["person_id"])

    def test_export_hides_internal_person_id(self):
        path = self.make_db_path() + ".xlsx"
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))

        export_table_data(
            [{"id": 1, "person_id": 3, "sequence": 1, "name": "张三", "reward_name": "优秀"}],
            path,
            "rewards",
        )

        columns = list(pd.read_excel(path).columns)
        self.assertNotIn("id", columns)
        self.assertNotIn("person_id", columns)
        self.assertEqual(["sequence", "name", "reward_name"], columns)

    def test_export_uses_date_display_and_hides_display_columns(self):
        path = self.make_db_path() + ".xlsx"
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))

        export_table_data(
            [
                {
                    "sequence": 1,
                    "name": "A",
                    "reward_date": "2024-01",
                    "reward_date_display": "2024.01",
                }
            ],
            path,
            "rewards",
        )

        exported = pd.read_excel(path, dtype=str)
        self.assertEqual(["sequence", "name", "reward_date"], list(exported.columns))
        self.assertEqual("2024.01", exported.iloc[0]["reward_date"])


if __name__ == "__main__":
    unittest.main()
