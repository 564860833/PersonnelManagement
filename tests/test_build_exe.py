import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import build_exe


class BuildExeTests(unittest.TestCase):
    def test_clean_old_builds_preserves_dist_ai_assets(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            build_dir = root / "build"
            pycache_dir = root / "__pycache__"
            dist_dir = root / "dist"
            app_dist_dir = dist_dir / build_exe.APP_NAME
            dist_models_dir = dist_dir / "models"
            dist_ollama_dir = dist_dir / "ollama"

            build_dir.mkdir()
            pycache_dir.mkdir()
            app_dist_dir.mkdir(parents=True)
            dist_models_dir.mkdir(parents=True)
            dist_ollama_dir.mkdir(parents=True)
            (dist_models_dir / "keep.bin").write_text("model", encoding="utf-8")
            (dist_ollama_dir / "ollama.exe").write_text("", encoding="utf-8")

            with patch.object(build_exe, "PROJECT_ROOT", root), \
                    patch.object(build_exe, "DIST_DIR", dist_dir), \
                    patch.object(build_exe, "APP_DIST_DIR", app_dist_dir), \
                    patch("builtins.print"):
                build_exe.clean_old_builds()

            self.assertFalse(build_dir.exists())
            self.assertFalse(pycache_dir.exists())
            self.assertFalse(app_dist_dir.exists())
            self.assertTrue((dist_models_dir / "keep.bin").is_file())
            self.assertTrue((dist_ollama_dir / "ollama.exe").is_file())

    def test_create_ai_package_copies_models_and_ollama_into_dedicated_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            models_dir = root / "models"
            ollama_dir = root / "ollama"
            models_dir.mkdir()
            (models_dir / "blobs").mkdir()
            (models_dir / "manifests").mkdir()
            ollama_dir.mkdir()
            (ollama_dir / "ollama.exe").write_text("", encoding="utf-8")

            dist_dir = root / "dist"
            with patch.object(build_exe, "PROJECT_ROOT", root), \
                    patch.object(build_exe, "DIST_DIR", dist_dir), \
                    patch("builtins.print"):
                self.assertTrue(build_exe.create_ai_package())

            final_dir = dist_dir / build_exe.AI_PACKAGE_NAME
            self.assertTrue((final_dir / "models").is_dir())
            self.assertTrue((final_dir / "ollama" / "ollama.exe").is_file())
            self.assertTrue((final_dir / "README.txt").is_file())


if __name__ == "__main__":
    unittest.main()
