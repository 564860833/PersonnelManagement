import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services import ollama_manager


class FakeProcess:
    def poll(self):
        return None

    def terminate(self):
        return None

    def wait(self, timeout=None):
        return None


class OllamaManagerTests(unittest.TestCase):
    def tearDown(self):
        ollama_manager._started_process = None

    def test_api_url_uses_app_dedicated_host(self):
        with patch.dict("os.environ", {"OLLAMA_HOST": "http://192.168.1.10:11434"}):
            self.assertEqual(
                f"http://{ollama_manager.APP_OLLAMA_HOST}/api/tags",
                ollama_manager.ollama_api_url("/api/tags"),
            )

    def test_find_ollama_executable_prefers_app_local_runtime(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            app_dir = Path(temp_dir)
            local_ollama = app_dir / "ollama" / "ollama.exe"
            local_ollama.parent.mkdir()
            local_ollama.write_text("", encoding="utf-8")

            with patch.object(ollama_manager, "get_application_dir", return_value=app_dir), \
                    patch("services.ollama_manager.shutil.which", return_value=None):
                self.assertEqual(str(local_ollama), ollama_manager.find_ollama_executable())

    def test_start_ollama_serve_sets_dedicated_env(self):
        captured = {}

        def fake_popen(command, **kwargs):
            captured["command"] = command
            captured["env"] = kwargs["env"]
            return FakeProcess()

        with tempfile.TemporaryDirectory() as temp_dir, \
                patch("services.ollama_manager.subprocess.Popen", side_effect=fake_popen):
            models_dir = Path(temp_dir) / "models"
            models_dir.mkdir()

            self.assertTrue(ollama_manager.start_ollama_serve("ollama.exe", models_dir))
            self.assertEqual(["ollama.exe", "serve"], captured["command"])
            self.assertEqual(ollama_manager.APP_OLLAMA_HOST, captured["env"]["OLLAMA_HOST"])
            self.assertEqual(str(models_dir), captured["env"]["OLLAMA_MODELS"])


if __name__ == "__main__":
    unittest.main()
