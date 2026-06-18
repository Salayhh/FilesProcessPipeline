"""MinerU HTTP client."""

from __future__ import annotations

from pathlib import Path
import time
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
        attempts = self.settings.mineru_upload_max_retries + 1
        last_error = ""
        for attempt in range(1, attempts + 1):
            try:
                with file_path.open("rb") as file:
                    response = requests.put(upload_url, data=file, timeout=self.settings.mineru_upload_timeout)
                if response.status_code == 200:
                    return
                if not self._is_retryable_upload_status(response.status_code):
                    raise MinerUAPIError(f"上传失败 {file_path.name}: HTTP {response.status_code}")
                last_error = f"HTTP {response.status_code}"
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
                last_error = str(exc)
            except requests.exceptions.RequestException as exc:
                last_error = str(exc)
                raise MinerUAPIError(f"上传失败 {file_path.name}: {last_error}") from exc

            if attempt < attempts:
                delay = self.settings.mineru_upload_retry_delay
                print(f"[MinerU] 上传重试: {file_path.name}, attempt={attempt + 1}/{attempts}, 上次错误: {last_error}", flush=True)
                if delay > 0:
                    time.sleep(delay)

        raise MinerUAPIError(f"上传失败 {file_path.name}: {last_error}")

    def _is_retryable_upload_status(self, status_code: int) -> bool:
        return status_code >= 500 or status_code in {408, 429}

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
