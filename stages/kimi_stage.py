"""
Pipeline Stage 2: Kimi 文档整理
调用 Kimi API 将不良品报告按照模板格式重新整理
"""
import re
import time
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime

from openai import OpenAI

from config import Config


class KimiStage:
    """Kimi 文档整理阶段"""

    def __init__(self):
        self.config = Config
        self.client = None
        self.template_structure = self._load_template_structure()
        self.token_stats = {'total_prompt_tokens': 0, 'total_completion_tokens': 0, 'total_tokens': 0}

    def _create_client(self) -> OpenAI:
        """创建 Kimi API 客户端"""
        return OpenAI(
            api_key=self.config.KIMI_API_KEY,
            base_url=self.config.KIMI_BASE_URL
        )

    def _load_template_structure(self) -> str:
        """加载模板结构定义"""
        return """
不良报告-硬件类模板结构：

# 不良项目：Y年M月某车型XX不良

## 第一部分：发生状况 (5W2H)

1. 不良现象/客户投诉事象（What）
2. 车型/机种（What）
3. 零件名称/零件号（What）
4. 不良重要度的等级（What）
5. 发生日期（When）
6. 发生地点（Where）
7. 发生件数/不良率（How many）
8. 责任部门/供应商（Who）
9. 初期处置/止血措施（How）

## 第二部分：事实把握（现场·现物·现实）

### 1、不良品确认结果
1.1 确认结果描述
1.2 正常状态
1.3 有问题的状态

### 2、现生产品的品质状况
2.1 工艺设计和保证方法
2.2 现生产品的品质确认结果

### 3、发生对象范围和证据
3.1 5M变化点调查
3.2 根据批次追溯结果或其他辅助手段明确发生范围

### 4、不良现象再现试验结果
4.1 试验项目一
4.2 试验项目二

### 5、要因分析
<table><tr><td>分类</td><td>相关工序/作业</td><td>规定</td><td>事实</td><td>问题点</td></tr><tr><td>发生</td><td></td><td></td><td></td><td></td></tr><tr><td>流出</td><td></td><td></td><td></td><td></td></tr></table>

## 第三部分：原因调查

### 1、不良原因分析
1.1 发生原因
1.2 流出原因

### 2、对于原因引起的问题现象的再现性确认结果
2.1 再现试验结果
2.2 正常状态/有问题的状态

### 3、why-why分析（深层原因分析）

## 第四部分：改善对策（事象对策·再发防止对策）

### 1、事象对策
1.1 针对不良发生原因的对策
1.2 针对不良流出的对策

### 2、再发防止对策
2.1 针对不良发生
2.2 针对不良流出

### 3、已出货品的处置对策

### 4、在库品的处置对策

### 5、对策实施后的效果

### 6、对策PPA

## 第五部分：水平展开
1. 同车型的水平展开
2. 不同车型的水平展开
3. 组织内的水平展开
4. 上下游组织的水平展开
"""

    def _read_file_content(self, file_path: Path) -> str:
        """读取文件内容，支持多种编码"""
        try:
            return file_path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            try:
                return file_path.read_text(encoding='gbk')
            except UnicodeDecodeError:
                return file_path.read_text(encoding='utf-8', errors='ignore')

    def _call_kimi_api(self, source_content: str, file_name: str = "") -> Dict:
        """调用 Kimi API 处理文件内容

        Returns:
            Dict: 包含 'content'、'prompt_tokens'、'completion_tokens'、'total_tokens'
        """
        system_prompt = f"""你是一个专业的文档整理助手。你的任务是将输入的不良品分析报告按照指定的模板格式重新整理。

请严格按照以下模板结构输出：

{self.template_structure}

重要说明：
1. 请保持原文中的具体数据、日期、数量等信息的准确性
2. 如果原文中某些字段没有明确信息，跳过即可，**禁止编造、联想、扩充内容**
3. 尽可能保留原文的内容，非必要情况下不要改写、概况
4. 输出格式必须是标准的Markdown格式,**内容是中文**
5. 必须保留原文中的markdown图片链接(类似：![](xxx.png/jpg)格式)，在重新整理时，尽量将图片链接保持在原有上下文的位置
6. 一级标题不良项目的车型一般是类似3QC、3LN、3GJ等三位数字英文混合的代号，在车型/机种/文件名处可以找到
"""

        # 在 user prompt 中加入文件名信息
        file_name_hint = f"""原始文件名：{file_name}
提示：文件名中可能包含机型信息（如3QC、3LN等三位代号），请仔细分析。

---

""" if file_name else ""

        user_prompt = f"""请将以下不良品分析报告按照模板格式重新整理：

{file_name_hint}{source_content}

---

请直接输出按照模板结构整理后的文档。"""

        try:
            response = self.client.chat.completions.create(
                model=self.config.KIMI_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=1,
            )

            # 提取 Token 使用量
            usage = response.usage
            return {
                'content': response.choices[0].message.content,
                'prompt_tokens': usage.prompt_tokens if usage else 0,
                'completion_tokens': usage.completion_tokens if usage else 0,
                'total_tokens': usage.total_tokens if usage else 0
            }
        except Exception as e:
            raise Exception(f"Kimi API调用失败: {str(e)}")

    def _process_single_file(self, file_path: Path, output_dir: Path) -> Dict:
        """处理单个文件"""
        print(f"  正在读取文件: {file_path.name}")

        try:
            # 读取文件内容
            content = self._read_file_content(file_path)

            if not content.strip():
                return {
                    'file': file_path.name,
                    'status': 'failed',
                    'error': '文件内容为空'
                }

            # 调用 Kimi API
            print(f"  正在调用 Kimi API 处理...")
            result = self._call_kimi_api(content, file_path.name)

            # 更新 Token 统计
            self.token_stats['total_prompt_tokens'] += result['prompt_tokens']
            self.token_stats['total_completion_tokens'] += result['completion_tokens']
            self.token_stats['total_tokens'] += result['total_tokens']

            print(f"  Token 使用量: 输入={result['prompt_tokens']}, 输出={result['completion_tokens']}, 总计={result['total_tokens']}")

            # 保存输出文件
            output_filename = f"processed_{file_path.stem}.md"
            output_path = output_dir / output_filename
            output_path.write_text(result['content'], encoding='utf-8')

            print(f"  完成: {output_filename}")

            return {
                'file': file_path.name,
                'status': 'success',
                'output': output_filename
            }

        except Exception as e:
            error_msg = str(e)
            print(f"  错误: {error_msg}")
            return {
                'file': file_path.name,
                'status': 'failed',
                'error': error_msg
            }

    def run(self, input_files: List[Path], output_dir: Path = None) -> Dict:
        """
        执行 Kimi 处理阶段

        Args:
            input_files: 输入文件列表（Markdown 文件路径）
            output_dir: 输出目录，默认使用配置中的 KIMI_OUTPUT_DIR

        Returns:
            Dict: 处理统计信息 {'success': int, 'failed': int}
        """
        output_dir = Path(output_dir) if output_dir else self.config.KIMI_OUTPUT_DIR
        output_dir.mkdir(parents=True, exist_ok=True)

        # 创建批次目录
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        batch_output_dir = output_dir / f"batch_{timestamp}"
        batch_output_dir.mkdir(parents=True, exist_ok=True)

        # 过滤出 Markdown 文件
        md_files = [f for f in input_files if f.suffix.lower() == '.md']

        if not md_files:
            print(f"警告: 没有找到 Markdown 文件")
            return {'success': 0, 'failed': 0}

        print(f"\nKimi 批量文档整理")
        print(f"=" * 60)
        print(f"输入文件数: {len(md_files)}")
        print(f"输出目录: {batch_output_dir}")
        print(f"模型: {self.config.KIMI_MODEL}")
        print(f"=" * 60)

        # 初始化客户端
        try:
            self.client = self._create_client()
            print("✓ Kimi 客户端初始化成功")
        except Exception as e:
            print(f"✗ Kimi 客户端初始化失败: {e}")
            return {'success': 0, 'failed': len(md_files)}

        # 处理文件
        results = []
        for i, file_path in enumerate(md_files, 1):
            print(f"\n[{i}/{len(md_files)}] 处理文件: {file_path.name}")

            result = self._process_single_file(file_path, batch_output_dir)
            results.append(result)

            # 添加延迟避免 API 限流
            if i < len(md_files):
                time.sleep(1)

        # 统计结果
        success_count = sum(1 for r in results if r['status'] == 'success')
        failed_count = sum(1 for r in results if r['status'] == 'failed')

        print(f"\n{'='*60}")
        print(f"Kimi 处理完成: 成功 {success_count}, 失败 {failed_count}")
        print(f"Token 使用量统计:")
        print(f"  - 输入 (Prompt): {self.token_stats['total_prompt_tokens']:,} tokens")
        print(f"  - 输出 (Completion): {self.token_stats['total_completion_tokens']:,} tokens")
        print(f"  - 总计: {self.token_stats['total_tokens']:,} tokens")
        print(f"结果保存在: {batch_output_dir}")
        print(f"{'='*60}")

        return {
            'success': success_count,
            'failed': failed_count
        }
