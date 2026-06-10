import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from config import Config
from stages.kimi_stage import KimiStage


class KimiStageTest(unittest.TestCase):
    def test_run_processes_markdown_file_without_calling_real_api(self):
        stage = KimiStage()

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_file = temp_path / "3QC_report.md"
            ignored_file = temp_path / "ignored.txt"
            output_dir = temp_path / "kimi_output"

            input_file.write_text("原始内容\n![](images/a.png)\n", encoding="utf-8")
            ignored_file.write_text("不是 Markdown 文件", encoding="utf-8")

            api_result = {
                "content": "# 不良项目：2026年3QC不良\n\n整理后的内容",
                "prompt_tokens": 10,
                "completion_tokens": 20,
                "total_tokens": 30,
            }

            with patch.object(stage, "_create_client", return_value=object()) as create_client:
                with patch.object(stage, "_call_kimi_api", return_value=api_result) as call_kimi_api:
                    result = stage.run([input_file, ignored_file], output_dir)

            self.assertEqual(result["success"], 1)
            self.assertEqual(result["failed"], 0)
            self.assertEqual(result["failed_files"], [])
            self.assertEqual(len(result["output_files"]), 1)

            create_client.assert_called_once_with()
            call_kimi_api.assert_called_once_with("原始内容\n![](images/a.png)\n", "3QC_report.md")

            output_path = Path(result["output_files"][0])
            self.assertEqual(output_path.name, "processed_3QC_report.md")
            self.assertEqual(output_path.parent, Path(result["output_dir"]))
            self.assertEqual(output_path.read_text(encoding="utf-8"), api_result["content"])

            self.assertEqual(stage.token_stats["total_prompt_tokens"], 10)
            self.assertEqual(stage.token_stats["total_completion_tokens"], 20)
            self.assertEqual(stage.token_stats["total_tokens"], 30)


@unittest.skipUnless(
    os.getenv("RUN_KIMI_API_TEST") == "1" and bool(Config.KIMI_API_KEY),
    "设置 RUN_KIMI_API_TEST=1 且配置 KIMI_API_KEY 后才运行真实 Kimi API 测试",
)
class KimiStageRealAPITest(unittest.TestCase):
    def test_run_processes_markdown_file_with_real_kimi_api(self):
        stage = KimiStage()

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_file = temp_path / "3QC_real_api_test.md"
            output_dir = temp_path / "kimi_output"

            input_file.write_text(
                "\n".join(
                    [
                        "# 3QC 后盖划伤不良报告",
                        "",
                        "车型/机种：3QC",
                        "不良现象：后盖表面有划伤。",
                        "发生日期：2026年6月10日",
                        "发生件数：1件",
                    ]
                ),
                encoding="utf-8",
            )

            result = stage.run([input_file], output_dir)

            self.assertEqual(result["success"], 1)
            self.assertEqual(result["failed"], 0)
            self.assertEqual(len(result["output_files"]), 1)

            output_path = Path(result["output_files"][0])
            self.assertTrue(output_path.exists())
            output_content = output_path.read_text(encoding="utf-8")
            self.assertIn("# 不良项目：", output_content)
            self.assertGreater(len(output_content.strip()), 0)
            self.assertGreater(stage.token_stats["total_tokens"], 0)


if __name__ == "__main__":
    unittest.main()
