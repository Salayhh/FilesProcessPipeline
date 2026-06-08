import tempfile
import unittest
from pathlib import Path

from stages.image_stage import ImageStage


class ImageStageTest(unittest.TestCase):
    def test_images_are_moved_into_document_subfolders(self):
        stage = ImageStage()

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            mineru_output_dir = temp_path / "mineru_output"
            kimi_output_dir = temp_path / "kimi_output"
            final_output_dir = temp_path / "output"
            image_target_dir = temp_path / "pic"

            for doc_name, image_content in [("doc_a", b"a"), ("doc_b", b"b")]:
                images_dir = mineru_output_dir / doc_name / "images"
                images_dir.mkdir(parents=True)
                (images_dir / "image.png").write_bytes(image_content)

            kimi_output_dir.mkdir()
            doc_a = kimi_output_dir / "processed_doc_a.md"
            doc_b = kimi_output_dir / "processed_doc_b.md"
            doc_a.write_text("# 不良项目：A\n\n## 第一部分：发生状况\n![](images/image.png)\n", encoding="utf-8")
            doc_b.write_text("# 不良项目：B\n\n## 第一部分：发生状况\n![](images/image.png)\n", encoding="utf-8")

            old_base_url = stage.config.IMAGE_BASE_URL
            old_target_dir = stage.config.IMAGE_TARGET_DIR
            stage.config.IMAGE_BASE_URL = "http://server/pic"
            stage.config.IMAGE_TARGET_DIR = image_target_dir
            try:
                result = stage.run(
                    kimi_output_files=[doc_a, doc_b],
                    mineru_output_dir=mineru_output_dir,
                    final_output_dir=final_output_dir,
                )
            finally:
                stage.config.IMAGE_BASE_URL = old_base_url
                stage.config.IMAGE_TARGET_DIR = old_target_dir

            self.assertEqual(result["success"], 2)
            self.assertEqual(result["images_moved"], 2)

            batch_dirs = list(image_target_dir.iterdir())
            self.assertEqual(len(batch_dirs), 1)
            batch_dir = batch_dirs[0]
            self.assertEqual((batch_dir / "doc_a" / "image.png").read_bytes(), b"a")
            self.assertEqual((batch_dir / "doc_b" / "image.png").read_bytes(), b"b")

            output_a = (final_output_dir / "processed_doc_a.md").read_text(encoding="utf-8")
            output_b = (final_output_dir / "processed_doc_b.md").read_text(encoding="utf-8")
            self.assertIn("/doc_a/image.png", output_a)
            self.assertIn("/doc_b/image.png", output_b)


if __name__ == "__main__":
    unittest.main()
