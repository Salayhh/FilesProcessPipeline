"""
Pipeline Stage 3: 图片处理和链接更新
将不良报告文件夹内的图片移动到指定目录，并处理 markdown 文件内容
"""
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any

from config import Config


class ImageStage:
    """图片处理和链接更新阶段"""

    def __init__(self):
        self.config = Config
        self.stats = {'success': 0, 'failed': 0, 'images_moved': 0}

    def _extract_bad_item_title(self, content: str) -> Optional[str]:
        """提取一级标题 # 不良项目：后的内容

        支持两种格式：
        1. 标准格式：# 不良项目：xxx
        2. 无井号格式：不良项目：xxx（Kimi 有时会漏掉 #）
        """
        # 首先尝试标准格式（带 #）
        pattern_with_hash = r'^#\s*不良项目：\s*(.+)$'
        match = re.search(pattern_with_hash, content, re.MULTILINE)
        if match:
            title = match.group(1).strip()
            return f"[{title}]"

        # 如果没有找到，尝试无井号格式（行首直接是"不良项目："）
        # 确保这不是一个段落中的文字，而是标题行（前面有空行或行首）
        pattern_without_hash = r'(?:^|\n\s*\n)\s*不良项目：\s*(.+?)(?=\n|$)'
        match = re.search(pattern_without_hash, content)
        if match:
            title = match.group(1).strip()
            # 提取第一行（防止有多行内容）
            title = title.split('\n')[0].strip()
            if title:
                return f"[{title}]"

        return None

    def _process_markdown_content(self, content: str, bad_item_title: str) -> str:
        """处理 Markdown 内容：
        1. 在二级标题前拼接一级标题
        2. 第二个二级标题起前面添加分隔符
        3. 第二个二级标题起，如果有下属三级标题，将拼接后的标题拼接到三级标题上并删除该二级标题
        """
        lines = content.split('\n')

        h2_pattern = re.compile(r'^(##\s*)(第[一二三四五六七八九十]+)(部分|章|节)?(\s*[:：]?\s*)(.*)$')
        h3_pattern = re.compile(r'^(###\s+)(.*)$')

        # 找到所有二级标题位置
        h2_positions = []
        for i, line in enumerate(lines):
            if h2_pattern.match(line):
                h2_positions.append(i)

        # 预计算每个二级标题是否有下属三级标题
        h2_has_h3 = {}
        for idx, pos in enumerate(h2_positions):
            next_h2 = h2_positions[idx + 1] if idx + 1 < len(h2_positions) else len(lines)
            has_h3 = False
            for j in range(pos + 1, next_h2):
                if h3_pattern.match(lines[j]):
                    has_h3 = True
                    break
            h2_has_h3[pos] = has_h3

        result_lines = []
        h2_count = 0

        for i, line in enumerate(lines):
            h2_match = h2_pattern.match(line)
            if h2_match:
                h2_count += 1

                prefix = h2_match.group(1)
                num_part = h2_match.group(2)
                suffix = h2_match.group(3) if h2_match.group(3) else ""
                separator = h2_match.group(4)
                rest = h2_match.group(5)
                new_heading = f"{prefix}{bad_item_title}{num_part}{suffix}{separator}{rest}"

                if h2_count >= 2:
                    # 第二个及之后，先添加分隔符
                    if result_lines and result_lines[-1].strip() != '':
                        result_lines.append('')
                    result_lines.append(self.config.SECTION_SEPARATOR)
                    result_lines.append('')

                    if h2_has_h3.get(i, False):
                        # 有三级标题：构造前缀拼接到下属三级标题，删除该二级标题
                        h2_content = new_heading.lstrip('#').strip()
                        rest_after_title = h2_content[len(bad_item_title):]
                        prefix_text = f"{bad_item_title[:-1]}({rest_after_title})]"

                        next_h2 = h2_positions[h2_count] if h2_count < len(h2_positions) else len(lines)
                        for j in range(i + 1, next_h2):
                            h3_match = h3_pattern.match(lines[j])
                            if h3_match:
                                h3_content = h3_match.group(2)
                                lines[j] = f"### {prefix_text}{h3_content}"
                        continue
                    else:
                        # 没有三级标题，保留二级标题
                        result_lines.append(new_heading)
                else:
                    # 第一个二级标题，正常保留
                    result_lines.append(new_heading)
                continue

            result_lines.append(line)

        return '\n'.join(result_lines)

    def _move_images(self, mineru_output_dir: Path, target_folder: Path) -> int:
        """移动图片文件到目标目录"""
        moved_count = 0

        # 遍历所有子目录查找 images 文件夹
        for images_dir in mineru_output_dir.rglob("images"):
            if images_dir.is_dir():
                for image_file in images_dir.iterdir():
                    if image_file.is_file():
                        target_path = target_folder / image_file.name
                        try:
                            shutil.move(str(image_file), str(target_path))
                            moved_count += 1
                            print(f"  移动图片: {image_file.name}")
                        except Exception as e:
                            print(f"  移动图片失败 {image_file.name}: {e}")

        return moved_count

    def _process_single_file(
        self,
        md_file: Path,
        mineru_output_dir: Path,
        target_folder_name: str,
        final_output_dir: Path
    ) -> Dict:
        """处理单个 Markdown 文件"""
        try:
            # 读取文件内容
            content = md_file.read_text(encoding='utf-8')

            # 提取不良项目标题
            bad_item_title = self._extract_bad_item_title(content)

            if bad_item_title:
                print(f"  提取到不良项目标题: {bad_item_title}")
                # 处理 Markdown 内容
                content = self._process_markdown_content(content, bad_item_title)
            else:
                print(f"  未找到不良项目标题，跳过内容处理")

            # 更新图片链接（仅在配置了图片服务器时）
            if target_folder_name and self.config.IMAGE_BASE_URL:
                pattern = r'!\[\]\(\s*images/(.*?)\s*\)'
                replacement = f'![]({self.config.IMAGE_BASE_URL}/{target_folder_name}/\\1)'
                content = re.sub(pattern, replacement, content)

            # 保存最终文件，根据 OUTPUT_FORMAT 决定扩展名
            output_ext = self.config.OUTPUT_FORMAT
            output_filename = md_file.stem + f".{output_ext}"
            output_file = final_output_dir / output_filename
            output_file.write_text(content, encoding='utf-8')

            print(f"  完成: {md_file.name} -> {output_file}")

            return {
                'file': md_file.name,
                'status': 'success',
                'output': str(output_file)
            }

        except Exception as e:
            error_msg = str(e)
            print(f"  错误处理 {md_file.name}: {error_msg}")
            return {
                'file': md_file.name,
                'status': 'failed',
                'error': error_msg
            }

    def run(
        self,
        kimi_output_files: List[Path],
        mineru_output_dir: Path,
        final_output_dir: Path,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行图片处理和链接更新阶段

        Args:
            kimi_output_files: Kimi 输出的 Markdown 文件列表
            mineru_output_dir: MinerU 输出目录（用于查找图片）
            final_output_dir: 最终输出目录

        Returns:
            Dict: 处理统计信息
        """
        print(f"\n图片处理和链接更新")
        print(f"=" * 60)

        if not kimi_output_files:
            print("警告: 没有需要处理的 Kimi 输出文件")
            return {'success': 0, 'failed': 0, 'images_moved': 0}

        final_output_dir.mkdir(parents=True, exist_ok=True)

        # 判断是否启用图片处理
        enable_image_processing = bool(
            self.config.IMAGE_BASE_URL and self.config.IMAGE_TARGET_DIR
        )

        if enable_image_processing:
            # 创建图片目标文件夹
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
            target_folder_name = timestamp
            target_folder = self.config.IMAGE_TARGET_DIR / target_folder_name
            target_folder.mkdir(parents=True, exist_ok=True)
        else:
            target_folder_name = None
            target_folder = None

        print(f"输入文件数: {len(kimi_output_files)}")
        if enable_image_processing:
            print(f"图片目标目录: {target_folder}")
        else:
            print("图片处理: 已禁用（IMAGE_BASE_URL 或 IMAGE_TARGET_DIR 未配置）")
        print(f"最终输出目录: {final_output_dir}")
        print(f"=" * 60)

        # 移动图片
        print("\n[步骤1/2] 移动图片文件...")
        if enable_image_processing:
            images_moved = self._move_images(mineru_output_dir, target_folder)
        else:
            images_moved = 0
            print("  跳过图片移动")
        self.stats['images_moved'] = images_moved
        print(f"✓ 移动了 {images_moved} 个图片文件")

        # 处理 Markdown 文件
        print("\n[步骤2/2] 处理 Markdown 文件...")
        results = []
        for i, md_file in enumerate(kimi_output_files, 1):
            print(f"\n[{i}/{len(kimi_output_files)}] 处理: {md_file.name}")
            result = self._process_single_file(
                md_file,
                mineru_output_dir,
                target_folder_name,
                final_output_dir
            )
            results.append(result)

        # 统计结果
        success_count = sum(1 for r in results if r['status'] == 'success')
        failed_count = sum(1 for r in results if r['status'] == 'failed')

        self.stats['success'] = success_count
        self.stats['failed'] = failed_count

        print(f"\n{'='*60}")
        print(f"图片处理完成: 成功 {success_count}, 失败 {failed_count}")
        print(f"移动图片数: {images_moved}")
        print(f"结果保存在: {final_output_dir}")
        print(f"{'='*60}")

        return self.stats
