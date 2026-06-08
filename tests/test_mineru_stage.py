import tempfile
import unittest
import zipfile
from pathlib import Path

from stages.mineru_stage import MinerUAPIError, MinerUStage


class MinerUStageTest(unittest.TestCase):
    def test_extract_zip_safely_rejects_path_traversal(self):
        stage = MinerUStage()

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            zip_path = temp_path / "bad.zip"
            extract_dir = temp_path / "extract"
            extract_dir.mkdir()

            with zipfile.ZipFile(zip_path, "w") as zip_file:
                zip_file.writestr("../evil.md", "bad")

            with self.assertRaises(MinerUAPIError):
                stage._extract_zip_safely(zip_path, extract_dir)


if __name__ == "__main__":
    unittest.main()
