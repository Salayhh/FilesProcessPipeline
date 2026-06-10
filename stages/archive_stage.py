"""
归档阶段 - 在Pipeline运行完成后归档中间文件
"""
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from config import Config


class ArchiveStage:
    """归档阶段处理器"""

    def __init__(self):
        self.timestamp = None
        self.data_dir = Config.DATA_DIR
        self.archive_dir = None

    def run(
        self,
        dirs_to_archive: Optional[List[Path]] = None,
        files_to_keep: Optional[List[Path]] = None,
    ) -> dict:
        """
        执行归档操作

        Args:
            dirs_to_archive: 要归档的目录列表，默认归档 input, kimi_output, mineru_output
            files_to_keep: 归档后需要保留在 INPUT_DIR 中的文件相对路径列表

        Returns:
            dict: 归档结果统计
        """
        if dirs_to_archive is None:
            dirs_to_archive = [
                Config.INPUT_DIR,
                Config.KIMI_OUTPUT_DIR,
                Config.MINERU_OUTPUT_DIR,
            ]

        self.timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        self.archive_dir = self.data_dir / self.timestamp

        print("\n" + "=" * 60)
        print("归档阶段: 归档中间文件")
        print("=" * 60)
        print(f"归档目标目录: {self.archive_dir}")
        print(f"归档时间戳: {self.timestamp}")
        print("-" * 60)

        # 创建归档目录
        self.archive_dir.mkdir(parents=True, exist_ok=True)

        result = {
            'success': 0,
            'failed': 0,
            'archived_dirs': [],
            'errors': []
        }

        for src_dir in dirs_to_archive:
            if not src_dir.exists():
                print(f"[SKIP] 目录不存在: {src_dir}")
                continue

            # 计算目标子目录名称
            dir_name = src_dir.name
            dest_dir = self.archive_dir / dir_name

            try:
                # 移动整个目录到归档目录
                shutil.move(str(src_dir), str(dest_dir))
                # 重新创建空的源文件夹
                src_dir.mkdir(parents=True, exist_ok=True)
                print(f"[OK] {dir_name} -> {dest_dir}")
                result['success'] += 1
                result['archived_dirs'].append({
                    'source': str(src_dir),
                    'destination': str(dest_dir),
                    'name': dir_name
                })
            except Exception as e:
                error_msg = f"归档失败 {dir_name}: {e}"
                print(f"[ERROR] {error_msg}")
                result['failed'] += 1
                result['errors'].append(error_msg)

        # 将指定文件从归档目录复制回 INPUT_DIR
        if files_to_keep and Config.INPUT_DIR in dirs_to_archive:
            archived_input = self.archive_dir / Config.INPUT_DIR.name
            kept_count = 0
            for rel_path in files_to_keep:
                src = archived_input / rel_path
                dst = Config.INPUT_DIR / rel_path
                if src.exists():
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(src), str(dst))
                    kept_count += 1
                    print(f"[KEEP] 保留文件: {rel_path}")
            if kept_count:
                print(f"[KEEP] 共保留 {kept_count} 个失败文件在 input/ 中")

        # 输出归档摘要
        print("-" * 60)
        print("归档摘要:")
        print(f"  成功: {result['success']} 个目录")
        print(f"  失败: {result['failed']} 个目录")
        print(f"  归档位置: {self.archive_dir}")
        print("=" * 60)

        return result
