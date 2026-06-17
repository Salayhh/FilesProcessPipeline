import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from files_pipeline.config import Settings


class SettingsTest(unittest.TestCase):
    def test_env_file_overrides_shell_environment(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / ".env").write_text(
                "\n".join(
                    [
                        "MINERU_API_TOKEN=file-mineru",
                        "KIMI_API_KEY=file-kimi",
                        "KIMI_MODEL=from-file",
                        "OUTPUT_FORMAT=txt",
                    ]
                ),
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {
                    "MINERU_API_TOKEN": "shell-mineru",
                    "KIMI_API_KEY": "shell-kimi",
                    "KIMI_MODEL": "from-shell",
                    "OUTPUT_FORMAT": "md",
                },
                clear=True,
            ):
                settings = Settings.from_env(base_dir=temp_path)

            self.assertEqual(settings.mineru_api_token, "file-mineru")
            self.assertEqual(settings.kimi_api_key, "file-kimi")
            self.assertEqual(settings.kimi_model, "from-file")
            self.assertEqual(settings.output_format, "txt")

    def test_mineru_options_are_loaded_from_env(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / ".env").write_text(
                "\n".join(
                    [
                        "MINERU_MODEL_VERSION=vlm",
                        "MINERU_ENABLE_TABLE=false",
                        "MINERU_ENABLE_FORMULA=true",
                        "MINERU_LANGUAGE=en",
                    ]
                ),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {}, clear=True):
                settings = Settings.from_env(base_dir=temp_path)

            self.assertEqual(settings.mineru_model_version, "vlm")
            self.assertFalse(settings.mineru_enable_table)
            self.assertTrue(settings.mineru_enable_formula)
            self.assertEqual(settings.mineru_language, "en")

    def test_missing_required_keys_are_reported(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            with patch.dict(os.environ, {}, clear=True):
                settings = Settings.from_env(base_dir=temp_path, env_file=temp_path / "missing.env")

            self.assertEqual(settings.missing_required_keys(), ["MINERU_API_TOKEN", "KIMI_API_KEY"])

    def test_invalid_output_format_fails_fast(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / ".env").write_text("OUTPUT_FORMAT=html\n", encoding="utf-8")

            with self.assertRaises(ValueError):
                Settings.from_env(base_dir=temp_path)

    def test_invalid_integer_env_fails_fast(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / ".env").write_text("KIMI_TIMEOUT=abc\n", encoding="utf-8")

            with self.assertRaises(ValueError):
                Settings.from_env(base_dir=temp_path)


if __name__ == "__main__":
    unittest.main()
