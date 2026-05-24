import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app_paths


class AppPathsTests(unittest.TestCase):
    def test_runtime_path_uses_project_root_in_development(self):
        with patch.object(app_paths.sys, "frozen", False, create=True):
            self.assertEqual(app_paths.project_root() / "application.log", app_paths.runtime_path("application.log"))

    def test_data_dir_uses_project_root_data_in_development(self):
        with patch.object(app_paths.sys, "frozen", False, create=True):
            self.assertEqual(app_paths.project_root() / "data", app_paths.data_dir())

    def test_application_dir_uses_executable_parent_when_frozen(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            exe_path = Path(temp_dir) / "人员信息管理系统.exe"
            with patch.object(app_paths.sys, "frozen", True, create=True), \
                    patch.object(app_paths.sys, "executable", str(exe_path)):
                self.assertEqual(Path(temp_dir), app_paths.application_dir())

    def test_data_path_uses_executable_sibling_data_dir_when_frozen(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            exe_path = Path(temp_dir) / "app.exe"
            expected_path = Path(temp_dir) / "data" / "personnel_system.db"
            with patch.object(app_paths.sys, "frozen", True, create=True), \
                    patch.object(app_paths.sys, "executable", str(exe_path)):
                self.assertEqual(expected_path, app_paths.data_path("personnel_system.db"))
                self.assertTrue((Path(temp_dir) / "data").is_dir())

    def test_resource_path_prefers_pyinstaller_meipass(self):
        with tempfile.TemporaryDirectory() as temp_dir, \
                patch.object(app_paths.sys, "_MEIPASS", temp_dir, create=True):
            self.assertEqual(Path(temp_dir) / "app_icon.ico", app_paths.resource_path("app_icon.ico"))

    def test_data_path_moves_legacy_runtime_files_into_data_dir(self):
        for file_name in ("personnel_system.db", "application.log"):
            with self.subTest(file_name=file_name), tempfile.TemporaryDirectory() as temp_dir:
                app_dir = Path(temp_dir)
                exe_path = app_dir / "app.exe"
                legacy_path = app_dir / file_name
                legacy_path.write_text("legacy content", encoding="utf-8")

                with patch.object(app_paths.sys, "frozen", True, create=True), \
                        patch.object(app_paths.sys, "executable", str(exe_path)):
                    target_path = app_paths.data_path(file_name)

                self.assertEqual(app_dir / "data" / file_name, target_path)
                self.assertFalse(legacy_path.exists())
                self.assertEqual("legacy content", target_path.read_text(encoding="utf-8"))

    def test_data_path_preserves_existing_data_file_and_backs_up_legacy_file(self):
        for file_name in ("personnel_system.db", "application.log"):
            with self.subTest(file_name=file_name), tempfile.TemporaryDirectory() as temp_dir:
                app_dir = Path(temp_dir)
                exe_path = app_dir / "app.exe"
                data_dir = app_dir / "data"
                data_dir.mkdir()
                target_path = data_dir / file_name
                target_path.write_text("current content", encoding="utf-8")
                legacy_path = app_dir / file_name
                legacy_path.write_text("legacy content", encoding="utf-8")

                with patch.object(app_paths.sys, "frozen", True, create=True), \
                        patch.object(app_paths.sys, "executable", str(exe_path)):
                    resolved_path = app_paths.data_path(file_name)

                backups = list((data_dir / "legacy").glob(f"{file_name}.*.bak"))
                self.assertEqual(target_path, resolved_path)
                self.assertEqual("current content", target_path.read_text(encoding="utf-8"))
                self.assertFalse(legacy_path.exists())
                self.assertEqual(1, len(backups))
                self.assertEqual("legacy content", backups[0].read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
