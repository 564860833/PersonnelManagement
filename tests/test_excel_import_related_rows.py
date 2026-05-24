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

    def test_preview_rejects_invalid_base_info_date(self):
        db_path = self.make_temp_path(".db")
        db = Database(db_path)
        db.close()
        excel_path = self.write_excel(
            [{"sequence": 1, "name": "A", "birth_date": "not-a-date"}],
            ["sequence", "name", "birth_date"],
        )

        result = prepare_import_preview(excel_path, db_path, "base_info")

        self.assertFalse(result["success"])
        self.assertIn("出生年月", result["message"])
        self.assertNotIn("birth_date", result["message"])
        self.assertIn("格式无效", result["message"])

    def test_preview_rejects_duplicate_base_info_rows(self):
        db_path = self.make_temp_path(".db")
        db = Database(db_path)
        db.close()
        excel_path = self.write_excel(
            [
                {"sequence": 1, "name": "张三", "current_grade": "一级"},
                {"sequence": "1.0", "name": " 张三 ", "current_grade": "二级"},
            ],
            ["sequence", "name", "current_grade"],
        )

        result = prepare_import_preview(excel_path, db_path, "base_info")

        self.assertFalse(result["success"])
        self.assertIn("重复人员", result["message"])
        self.assertIn("第 1 行", result["message"])
        self.assertIn("第 2 行", result["message"])
        self.assertEqual([], result["records"])

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

    def test_import_prepared_records_rejects_empty_related_rows_without_changes(self):
        db_path = self.create_db_with_person()
        db = Database(db_path)
        db.import_excel_data("family", [{"sequence": 1, "name": "张三", "relation": "父亲"}])
        db.close()

        result = import_prepared_records(
            db_path,
            "family",
            [{"sequence": 1, "name": "张三"}],
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

    def test_import_prepared_records_rejects_duplicate_base_info_before_config_changes(self):
        db_path = self.make_temp_path(".db")
        assessment_years = [2020, 2021, 2022, 2023, 2024]
        db = Database(db_path)
        db.import_excel_data("base_info", [{"sequence": 1, "name": "张三", "current_grade": "原始"}])
        db.set_assessment_years(assessment_years)
        db.close()

        result = import_prepared_records(
            db_path,
            "base_info",
            [
                {"sequence": 1, "name": "张三", "current_grade": "一级"},
                {"sequence": 1, "name": "张三", "current_grade": "二级"},
            ],
            assessment_years=assessment_years,
        )

        self.assertFalse(result["success"])
        self.assertIn("重复人员", result["message"])

        db = Database(db_path)
        try:
            self.assertEqual(assessment_years, db.get_assessment_years())
            rows = db.get_all_data("base_info")
            self.assertEqual(1, len(rows))
            self.assertEqual("张三", rows[0]["name"])
            self.assertEqual("原始", rows[0]["current_grade"])
        finally:
            db.close()

    def test_related_import_skips_existing_duplicate_and_appends_new_detail(self):
        db_path = self.create_db_with_person()
        db = Database(db_path)
        db.import_excel_data("family", [{"sequence": 1, "name": "张三", "relation": "父亲", "family_name": "张父"}])
        db.close()

        result = import_prepared_records(
            db_path,
            "family",
            [
                {"sequence": 1, "name": "张三", "relation": "父亲", "family_name": "张父"},
                {"sequence": 1, "name": "张三", "relation": "母亲", "family_name": "张母"},
            ],
        )

        self.assertTrue(result["success"])
        self.assertIn("成功导入人员家庭成员信息 1 条记录", result["message"])
        self.assertIn("已跳过 1 条重复明细", result["message"])

        db = Database(db_path)
        try:
            rows = sorted(
                (row["relation"], row["family_name"])
                for row in db.get_all_data("family")
            )
            self.assertEqual([("母亲", "张母"), ("父亲", "张父")], rows)
        finally:
            db.close()

    def test_related_import_skips_duplicate_rows_within_batch(self):
        db_path = self.create_db_with_person()

        result = import_prepared_records(
            db_path,
            "family",
            [
                {"sequence": 1, "name": "张三", "relation": "父亲", "family_name": "张父"},
                {"sequence": "1.0", "name": "张三", "relation": "父亲", "family_name": "张父"},
            ],
        )

        self.assertTrue(result["success"])
        self.assertIn("成功导入人员家庭成员信息 1 条记录", result["message"])
        self.assertIn("已跳过 1 条重复明细", result["message"])

        db = Database(db_path)
        try:
            rows = db.get_all_data("family")
            self.assertEqual(1, len(rows))
            self.assertEqual("父亲", rows[0]["relation"])
            self.assertEqual("张父", rows[0]["family_name"])
        finally:
            db.close()

    def test_related_import_reports_all_duplicate_rows_without_inserting(self):
        db_path = self.create_db_with_person()
        db = Database(db_path)
        db.import_excel_data("family", [{"sequence": 1, "name": "张三", "relation": "父亲", "family_name": "张父"}])
        db.close()

        result = import_prepared_records(
            db_path,
            "family",
            [{"sequence": 1, "name": "张三", "relation": "父亲", "family_name": "张父"}],
        )

        self.assertTrue(result["success"])
        self.assertIn("未新增记录", result["message"])
        self.assertIn("已跳过 1 条重复明细", result["message"])

        db = Database(db_path)
        try:
            rows = db.get_all_data("family")
            self.assertEqual(1, len(rows))
            self.assertEqual("父亲", rows[0]["relation"])
        finally:
            db.close()

    def test_base_info_duplicate_with_database_updates_and_adds(self):
        db_path = self.make_temp_path(".db")
        db = Database(db_path)
        db.import_excel_data(
            "base_info",
            [
                {"sequence": 1, "name": "张三", "current_grade": "原始"},
                {"sequence": 2, "name": "李四", "current_grade": "保留"},
            ],
        )
        db.close()

        result = import_prepared_records(
            db_path,
            "base_info",
            [
                {"sequence": 1, "name": "张三", "current_grade": "更新"},
                {"sequence": 3, "name": "王五", "current_grade": "新增"},
            ],
        )

        self.assertTrue(result["success"])

        db = Database(db_path)
        try:
            rows = {row["name"]: row for row in db.get_all_data("base_info")}
            self.assertEqual({"张三", "李四", "王五"}, set(rows))
            self.assertEqual("更新", rows["张三"]["current_grade"])
            self.assertEqual("保留", rows["李四"]["current_grade"])
            self.assertEqual("新增", rows["王五"]["current_grade"])
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
