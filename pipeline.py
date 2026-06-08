"""
文档预处理 Pipeline 主协调器
集成 MinerU 解析、Kimi 整理、图片处理三个阶段
"""
import sys
from pathlib import Path
from typing import List
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
            'stage_times': {},
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
        print(f"  - Kimi Model: {self.config.KIMI_MODEL}")
        print(f"  - Output Format: {self.config.OUTPUT_FORMAT}")

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

            t1_start = datetime.now()
            mineru_result = self.mineru_stage.run(
                input_dir=self.config.INPUT_DIR,
                output_dir=self.config.MINERU_OUTPUT_DIR
            )
            self.stats['stage_times']['mineru'] = (datetime.now() - t1_start).total_seconds()

            self.stats['mineru_success'] = mineru_result.get('success', 0)
            self.stats['mineru_failed'] = mineru_result.get('failed', 0)

            if self.stats['mineru_success'] == 0:
                raise PipelineError("MinerU Parsing Stage has no successful files, Pipeline aborted")

            # Stage 2: Kimi Document Processing
            print("\n" + "=" * 60)
            print("Stage 2: Kimi Document Processing")
            print("=" * 60)

            # Use only Markdown files produced by this run.
            mineru_md_files = [Path(p) for p in mineru_result.get('output_files', [])]

            t2_start = datetime.now()
            kimi_result = self.kimi_stage.run(
                input_files=mineru_md_files,
                output_dir=self.config.KIMI_OUTPUT_DIR
            )
            self.stats['stage_times']['kimi'] = (datetime.now() - t2_start).total_seconds()

            self.stats['kimi_success'] = kimi_result.get('success', 0)
            self.stats['kimi_failed'] = kimi_result.get('failed', 0)

            if self.stats['kimi_success'] == 0:
                raise PipelineError("Kimi Organizing Stage has no successful files, Pipeline aborted")

            # Stage 3: Image Processing and Link Update
            print("\n" + "=" * 60)
            print("Stage 3: Image Processing and Link Update")
            print("=" * 60)

            # Use only Kimi files produced by this run.
            kimi_output_files = [Path(p) for p in kimi_result.get('output_files', [])]

            t3_start = datetime.now()
            image_result = self.image_stage.run(
                kimi_output_files=kimi_output_files,
                mineru_output_dir=self.config.MINERU_OUTPUT_DIR,
                final_output_dir=self.config.OUTPUT_DIR
            )
            self.stats['stage_times']['image'] = (datetime.now() - t3_start).total_seconds()

            self.stats['image_success'] = image_result.get('success', 0)
            self.stats['image_failed'] = image_result.get('failed', 0)

            if self.stats['image_success'] == 0:
                raise PipelineError("Image Processing Stage has no successful files, Pipeline aborted")

            # Stage 4: Archive intermediate files
            print("\n" + "=" * 60)
            print("Stage 4: Archive Intermediate Files")
            print("=" * 60)

            t4_start = datetime.now()
            archive_result = self.archive_stage.run()
            self.stats['stage_times']['archive'] = (datetime.now() - t4_start).total_seconds()

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
        total_duration = "N/A"
        if self.stats['start_time'] and self.stats['end_time']:
            delta = self.stats['end_time'] - self.stats['start_time']
            total_duration = f"{delta.total_seconds():.1f} s"

        # 各阶段用时
        st = self.stats.get('stage_times', {})

        # Token 统计（基于 Kimi 成功处理的文件数）
        kimi_success = self.stats['kimi_success']
        token_stats = self.kimi_stage.token_stats if hasattr(self.kimi_stage, 'token_stats') else {}

        print("\n" + "=" * 60)
        print("Pipeline Execution Summary")
        print("=" * 60)
        print(f"Total Files: {self.stats['total_files']}")
        print()
        print("Stage 1 - MinerU Parsing:")
        print(f"  Success: {self.stats['mineru_success']}, Failed: {self.stats['mineru_failed']}")
        print(f"  Duration: {st.get('mineru', 0):.1f} s")
        print("Stage 2 - Kimi Processing:")
        print(f"  Success: {self.stats['kimi_success']}, Failed: {self.stats['kimi_failed']}")
        print(f"  Duration: {st.get('kimi', 0):.1f} s")
        print("Stage 3 - Image Processing:")
        print(f"  Success: {self.stats['image_success']}, Failed: {self.stats['image_failed']}")
        print(f"  Duration: {st.get('image', 0):.1f} s")
        print("Stage 4 - Archive:")
        archive_success = self.stats.get('archive_success', 0)
        archive_failed = self.stats.get('archive_failed', 0)
        print(f"  Success: {archive_success}, Failed: {archive_failed}")
        print(f"  Duration: {st.get('archive', 0):.1f} s")
        print()
        if kimi_success > 0 and token_stats:
            avg_in = token_stats.get('total_prompt_tokens', 0) / kimi_success
            avg_out = token_stats.get('total_completion_tokens', 0) / kimi_success
            avg_total = token_stats.get('total_tokens', 0) / kimi_success
            print("Avg Token Usage per Document (Kimi Stage):")
            print(f"  Input:    {avg_in:,.0f}")
            print(f"  Output:   {avg_out:,.0f}")
            print(f"  Total:    {avg_total:,.0f}")
            print()
        print(f"Total Duration: {total_duration}")
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
