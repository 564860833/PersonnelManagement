import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import build_exe


class BuildExeTests(unittest.TestCase):
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
