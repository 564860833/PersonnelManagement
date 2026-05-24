import os
import tempfile
import unittest

import pandas as pd

from core.database import Database
from services.excel_import import import_prepared_records, prepare_import_preview


class ExcelImportRelatedRowsTests(unittest.TestCase):
    def make_temp_path(self, suffix):
        fd, path = tempfile.mkstemp(suffix=suffix)
        os.close(fd)
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        return path

    def create_db_with_person(self):
        db_path = self.make_temp_path(".db")
        db = Database(db_path)
        db.import_excel_data("base_info", [{"sequence": 1, "name": "张三"}])
        db.close()
        return db_path

    def write_excel(self, rows, columns):
        file_path = self.make_temp_path(".xlsx")
        pd.DataFrame(rows, columns=columns).to_excel(file_path, index=False)
        return file_path

    def test_preview_rejects_related_file_with_only_empty_detail_rows(self):
        db_path = self.create_db_with_person()
        excel_path = self.write_excel(
            [{"sequence": 1, "name": "张三", "relation": None, "family_name": None}],
            ["sequence", "name", "relation", "family_name"],
        )

        result = prepare_import_preview(excel_path, db_path, "family")

        self.assertFalse(result["success"])
        self.assertIn("未找到有效明细记录", result["message"])
        self.assertEqual([], result["records"])

    def test_preview_keeps_only_valid_related_detail_rows(self):
        db_path = self.create_db_with_person()
        excel_path = self.write_excel(
            [
                {"sequence": 1, "name": "张三", "relation": None, "family_name": None},
                {"sequence": 1, "name": "张三", "relation": "父亲", "family_name": "张父"},
            ],
            ["sequence", "name", "relation", "family_name"],
        )

        result = prepare_import_preview(excel_path, db_path, "family")

        self.assertTrue(result["success"])
        self.assertEqual(1, len(result["records"]))
        self.assertEqual("父亲", result["records"][0]["relation"])
        self.assertEqual("张父", result["records"][0]["family_name"])

    def test_import_prepared_records_rejects_empty_related_rows_before_overwrite_clear(self):
        db_path = self.create_db_with_person()
        db = Database(db_path)
        db.import_excel_data("family", [{"sequence": 1, "name": "张三", "relation": "父亲"}])
        db.close()

        result = import_prepared_records(
            db_path,
            "family",
            [{"sequence": 1, "name": "张三"}],
            overwrite=True,
        )

        self.assertFalse(result["success"])
        self.assertIn("未找到有效明细记录", result["message"])

        db = Database(db_path)
        try:
            rows = db.get_all_data("family")
            self.assertEqual(1, len(rows))
            self.assertEqual("父亲", rows[0]["relation"])
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
