import unittest
from contextlib import redirect_stdout
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

import pipeline as simple_entry
from files_pipeline import cli


class CliTest(unittest.TestCase):
    def test_cli_run_command_calls_pipeline(self):
        with patch("files_pipeline.cli.run_pipeline", return_value=SimpleNamespace(run_id="run-1")) as run_pipeline:
            with redirect_stdout(StringIO()):
                exit_code = cli.main(["run", "--input", "input", "--run-id", "run-1"])

        self.assertEqual(exit_code, 0)
        run_pipeline.assert_called_once()
        self.assertEqual(run_pipeline.call_args.kwargs["input_dir"].as_posix(), "input")
        self.assertEqual(run_pipeline.call_args.kwargs["run_id"], "run-1")

    def test_cli_run_without_input_uses_settings_default(self):
        with patch("files_pipeline.cli.run_pipeline", return_value=SimpleNamespace(run_id="run-1")) as run_pipeline:
            with redirect_stdout(StringIO()):
                exit_code = cli.main(["run", "--run-id", "run-1"])

        self.assertEqual(exit_code, 0)
        run_pipeline.assert_called_once()
        self.assertIsNone(run_pipeline.call_args.kwargs["input_dir"])

    def test_cli_archive_command_calls_archive(self):
        with patch("files_pipeline.cli.archive_run", return_value="/tmp/data/run-1") as archive_run:
            with redirect_stdout(StringIO()):
                exit_code = cli.main(["archive", "--run-id", "run-1"])

        self.assertEqual(exit_code, 0)
        archive_run.assert_called_once_with("run-1")

    def test_simple_pipeline_entry_calls_run_pipeline(self):
        fake_manifest = SimpleNamespace(
            run_id="run-1",
            stages={"render": {"output_files": ["final/0001_doc.md"]}},
        )
        with patch("pipeline.run_pipeline", return_value=fake_manifest) as run_pipeline:
            with redirect_stdout(StringIO()):
                exit_code = simple_entry.main()

        self.assertEqual(exit_code, 0)
        run_pipeline.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
