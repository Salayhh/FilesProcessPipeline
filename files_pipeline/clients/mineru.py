"""MinerU HTTP client."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import requests

from files_pipeline.config import Settings


class MinerUAPIError(Exception):
    """Raised when MinerU API calls fail."""


class MinerUClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.mineru_api_token}",
        }

    def request(self, method: str, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        url = f"{self.settings.mineru_base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        try:
            response = requests.request(method, url, headers=self.headers, timeout=30, **kwargs)
        except requests.exceptions.RequestException as exc:
            raise MinerUAPIError(f"MinerU 请求失败: {exc}") from exc

        if response.status_code != 200:
            raise MinerUAPIError(f"MinerU HTTP {response.status_code}: {response.text}")

        data = response.json()
        if data.get("code") != 0:
            raise MinerUAPIError(f"MinerU API {data.get('code')}: {data.get('msg')}")
        return data

    def apply_upload_urls(self, files: list[dict[str, str]]) -> tuple[str, list[str]]:
        payload: dict[str, Any] = {
            "files": files,
            "model_version": self.settings.mineru_model_version,
            "enable_table": self.settings.mineru_enable_table,
            "enable_formula": self.settings.mineru_enable_formula,
            "language": self.settings.mineru_language,
        }
        result = self.request("POST", "/file-urls/batch", json=payload)
        return result["data"]["batch_id"], result["data"]["file_urls"]

    def upload_file(self, file_path: Path, upload_url: str) -> None:
        with file_path.open("rb") as file:
            response = requests.put(upload_url, data=file, timeout=60)
        if response.status_code != 200:
            raise MinerUAPIError(f"上传失败 {file_path.name}: HTTP {response.status_code}")

    def query_batch_results(self, batch_id: str) -> dict[str, Any]:
        result = self.request("GET", f"/extract-results/batch/{batch_id}")
        return result["data"]

    def download_zip(self, zip_url: str) -> bytes:
        try:
            response = requests.get(zip_url, timeout=120)
        except requests.exceptions.RequestException as exc:
            raise MinerUAPIError(f"下载解析结果失败: {exc}") from exc
        if response.status_code != 200:
            raise MinerUAPIError(f"下载解析结果失败: HTTP {response.status_code}")
        return response.content
