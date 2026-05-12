"""
文档预处理 Pipeline 主协调器
集成 MinerU 解析、Kimi 整理、图片处理三个阶段
"""
import sys
import time
from pathlib import Path
from typing import List, Optional
from datetime import datetime

from config import Config
from stages.mineru_stage import MinerUStage
from stages.kimi_stage import KimiStage
from stages.image_stage import ImageStage
from stages.archive_stage import ArchiveStage


class PipelineError(Exception):
    """Pipeline 执行错误"""
    pass


class DocumentPipeline:
    """文档预处理 Pipeline"""

    def __init__(self):
        self.config = Config
        self.mineru_stage = MinerUStage()
        self.kimi_stage = KimiStage()
        self.image_stage = ImageStage()
        self.archive_stage = ArchiveStage()

        # 执行统计
        self.stats = {
            'start_time': None,
            'end_time': None,
            'total_files': 0,
            'mineru_success': 0,
            'mineru_failed': 0,
            'kimi_success': 0,
            'kimi_failed': 0,
            'image_success': 0,
            'image_failed': 0,
        }

    def validate(self) -> bool:
        """验证配置和环境"""
        print("=" * 60)
        print("Pipeline Environment Validation")
        print("=" * 60)

        # Check Required Configuration
        missing = self.config.validate()
        if missing:
            print(f"[ERROR] Missing required config: {', '.join(missing)}")
            print("Please check .env file")
            return False

        print("[OK] Config validation passed")

        # Create Required Directories
        self.config.ensure_directories()
        print("[OK] Directory structure ready")

        # Check Input Directory for Files
        input_files = self._collect_input_files()
        if not input_files:
            print(f"[ERROR] Input directory is empty: {self.config.INPUT_DIR}")
            print("Please place files in the input directory")
            return False

        print(f"[OK] Found {len(input_files)} files to process")
        self.stats['total_files'] = len(input_files)

        return True

    def _collect_input_files(self) -> List[Path]:
        """收集输入文件"""
        files = []
        for ext in self.config.SUPPORTED_EXTENSIONS:
            files.extend(self.config.INPUT_DIR.rglob(f"*{ext}"))
        return sorted(files)

    def run(self) -> bool:
        """执行完整 Pipeline"""
        self.stats['start_time'] = datetime.now()

        try:
            # Stage 1: MinerU Document Parsing
            print("\n" + "=" * 60)
            print("Stage 1: MinerU Document Parsing")
            print("=" * 60)

            mineru_result = self.mineru_stage.run(
                input_dir=self.config.INPUT_DIR,
                output_dir=self.config.MINERU_OUTPUT_DIR
            )

            self.stats['mineru_success'] = mineru_result.get('success', 0)
            self.stats['mineru_failed'] = mineru_result.get('failed', 0)

            if self.stats['mineru_success'] == 0:
                raise PipelineError("MinerU Parsing Stage has no successful files, Pipeline aborted")

            # Stage 2: Kimi Document Processing
            print("\n" + "=" * 60)
            print("Stage 2: Kimi Document Processing")
            print("=" * 60)

            # Get MinerU Output markdown files
            mineru_md_files = list(self.config.MINERU_OUTPUT_DIR.rglob("*.md"))

            kimi_result = self.kimi_stage.run(
                input_files=mineru_md_files,
                output_dir=self.config.KIMI_OUTPUT_DIR
            )

            self.stats['kimi_success'] = kimi_result.get('success', 0)
            self.stats['kimi_failed'] = kimi_result.get('failed', 0)

            if self.stats['kimi_success'] == 0:
                raise PipelineError("Kimi Organizing Stage has no successful files, Pipeline aborted")

            # Stage 3: Image Processing and Link Update
            print("\n" + "=" * 60)
            print("Stage 3: Image Processing and Link Update")
            print("=" * 60)

            # Get Kimi Output files to process
            kimi_output_files = list(self.config.KIMI_OUTPUT_DIR.rglob("*.md"))

            image_result = self.image_stage.run(
                kimi_output_files=kimi_output_files,
                mineru_output_dir=self.config.MINERU_OUTPUT_DIR,
                final_output_dir=self.config.OUTPUT_DIR
            )

            self.stats['image_success'] = image_result.get('success', 0)
            self.stats['image_failed'] = image_result.get('failed', 0)

            # Stage 4: Archive intermediate files
            print("\n" + "=" * 60)
            print("Stage 4: Archive Intermediate Files")
            print("=" * 60)

            archive_result = self.archive_stage.run()

            self.stats['archive_success'] = archive_result.get('success', 0)
            self.stats['archive_failed'] = archive_result.get('failed', 0)

            self.stats['end_time'] = datetime.now()
            self._print_summary()

            return True

        except PipelineError as e:
            print(f"\n[ERROR] Pipeline error: {e}")
            self.stats['end_time'] = datetime.now()
            self._print_summary()
            return False
        except Exception as e:
            print(f"\n[ERROR] Unexpected pipeline error: {e}")
            import traceback
            traceback.print_exc()
            self.stats['end_time'] = datetime.now()
            self._print_summary()
            return False

    def _print_summary(self):
        """打印执行摘要"""
        duration = "N/A"
        if self.stats['start_time'] and self.stats['end_time']:
            delta = self.stats['end_time'] - self.stats['start_time']
            duration = f"{delta.total_seconds():.1f} s"

        print("\n" + "=" * 60)
        print("Pipeline Execution Summary")
        print("=" * 60)
        print(f"Total Duration: {duration}")
        print(f"Total Files: {self.stats['total_files']}")
        print()
        print("Stage 1 - MinerU Parsing:")
        print(f"  Success: {self.stats['mineru_success']}, Failed: {self.stats['mineru_failed']}")
        print("Stage 2 - Kimi Processing:")
        print(f"  Success: {self.stats['kimi_success']}, Failed: {self.stats['kimi_failed']}")
        print("Stage 3 - Image Processing:")
        print(f"  Success: {self.stats['image_success']}, Failed: {self.stats['image_failed']}")
        print("Stage 4 - Archive:")
        archive_success = self.stats.get('archive_success', 0)
        archive_failed = self.stats.get('archive_failed', 0)
        print(f"  Success: {archive_success}, Failed: {archive_failed}")
        print("=" * 60)


def main():
    """主入口"""
    pipeline = DocumentPipeline()

    # Validate Environment
    if not pipeline.validate():
        sys.exit(1)

    # Execute Pipeline
    success = pipeline.run()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
