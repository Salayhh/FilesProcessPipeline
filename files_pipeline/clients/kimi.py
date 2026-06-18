"""Kimi client using the OpenAI-compatible SDK."""

from __future__ import annotations

from threading import Lock

from openai import OpenAI

from files_pipeline.config import Settings
from files_pipeline.models import KimiCompletion, TokenUsage


class KimiClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._client: OpenAI | None = None
        self._client_lock = Lock()
        self.template = self._load_template()

    def _load_template(self) -> str:
        if not self.settings.kimi_template_path:
            raise ValueError("未配置 Kimi 模板路径")
        return self.settings.kimi_template_path.read_text(encoding="utf-8")

    @property
    def client(self) -> OpenAI:
        if self._client is None:
            with self._client_lock:
                if self._client is None:
                    self._client = OpenAI(
                        api_key=self.settings.kimi_api_key,
                        base_url=self.settings.kimi_base_url,
                        timeout=self.settings.kimi_timeout,
                        max_retries=0,
                    )
        return self._client

    def complete(self, source_content: str, file_name: str) -> KimiCompletion:
        system_prompt = f"""你是一个专业的文档整理助手。你的任务是将输入的不良品分析报告按照指定的模板格式重新整理。

请严格按照以下模板结构输出：

{self.template}

重要说明：
1. 请保持原文中的具体数据、日期、数量等信息的准确性
2. 如果模板的某些标题或分点在原文中没有明确信息，写：（原文未提及）/（原文未明确提及）即可，禁止编造、联想、扩充内容
3. 尽可能保留原文的内容，非必要情况下不要改写、概括
4. 输出格式必须是标准的Markdown格式，内容是中文
5. 必须保留原文中所有的markdown图片链接，按照模板整理时，尽量将图片链接保持在原有上下文的位置
6. 一级标题不良项目的车型一般是类似3QC、3LN、3GJ等三位数字英文混合的代号，在车型/机种/文件名处可以找到
7. 严格按照模板的分级标题和分点输出，不要擅自改动、加粗标题和分点
"""
        file_name_hint = f"""原始文件名：{file_name}
提示：文件名中可能包含机型信息（如3QC、3LN等三位代号），请仔细分析。

---

"""
        user_prompt = f"""请将以下不良品分析报告按照模板格式重新整理：

{file_name_hint}{source_content}

---

请直接输出按照模板结构整理后的文档。
"""
        response = self.client.chat.completions.create(
            model=self.settings.kimi_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=1,
        )
        usage = response.usage
        token_usage = TokenUsage(
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            total_tokens=usage.total_tokens if usage else 0,
        )
        return KimiCompletion(content=response.choices[0].message.content, token_usage=token_usage)
