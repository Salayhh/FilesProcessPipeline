"""
Pipeline Stage 1: MinerU 文档解析
负责调用 MinerU API 将 PDF/Word/PPT/图片等文档解析为 Markdown
"""
import os
import time
import zipfile
from pathlib import Path
from typing import List, Dict, Tuple
import requests

from config import Config


class MinerUAPIError(Exception):
    """MinerU API 错误"""
    pass


class MinerUStage:
    """MinerU 文档解析阶段"""

    def __init__(self):
        self.config = Config
        self.token = self.config.MINERU_API_TOKEN
        self.base_url = self.config.MINERU_BASE_URL
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}"
        }
        self.stats = {'success': 0, 'failed': 0}

    def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict:
        """发送 HTTP 请求"""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"

        try:
            response = requests.request(
                method, url, headers=self.headers, timeout=30, **kwargs
            )

            if response.status_code != 200:
                raise MinerUAPIError(f"HTTP {response.status_code}: {response.text}")

            data = response.json()

            if data.get("code") != 0:
                raise MinerUAPIError(f"API Error {data.get('code')}: {data.get('msg')}")

            return data

        except requests.exceptions.RequestException as e:
            raise MinerUAPIError(f"Request failed: {str(e)}")

    def _apply_upload_urls(self, files: List[Dict], **options) -> Tuple[str, List[str]]:
        """申请批量文件上传链接"""
        endpoint = "/file-urls/batch"

        data = {
            "files": files,
            "model_version": self.config.MINERU_MODEL_VERSION
        }

        for key in ["enable_formula", "enable_table", "language", "callback", "seed", "extra_formats"]:
            if key in options:
                data[key] = options[key]

        result = self._make_request("POST", endpoint, json=data)

        batch_id = result["data"]["batch_id"]
        file_urls = result["data"]["file_urls"]

        return batch_id, file_urls

    def _upload_file(self, file_path: str, upload_url: str) -> bool:
        """上传单个文件"""
        try:
            with open(file_path, 'rb') as f:
                response = requests.put(upload_url, data=f, timeout=60)

            if response.status_code == 200:
                print(f"  ✓ 上传成功: {Path(file_path).name}")
                return True
            else:
                print(f"  ✗ 上传失败: {Path(file_path).name} (HTTP {response.status_code})")
                return False

        except Exception as e:
            print(f"  ✗ 上传异常: {Path(file_path).name} ({str(e)})")
            return False

    def _query_batch_results(self, batch_id: str) -> Dict:
        """批量查询解析结果"""
        endpoint = f"/extract-results/batch/{batch_id}"
        result = self._make_request("GET", endpoint)
        return result["data"]

    def _download_result(self, zip_url: str, output_dir: Path, file_name: str) -> bool:
        """下载并解压解析结果"""
        try:
            base_name = Path(file_name).stem
            extract_dir = output_dir / base_name
            extract_dir.mkdir(parents=True, exist_ok=True)

            print(f"  正在下载: {file_name} 的解析结果...")
            response = requests.get(zip_url, timeout=120)

            if response.status_code != 200:
                print(f"  ✗ 下载失败: HTTP {response.status_code}")
                return False

            zip_path = extract_dir / "result.zip"
            with open(zip_path, 'wb') as f:
                f.write(response.content)

            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)

            zip_path.unlink()

            # 重命名 full.md 为与文件夹同名的文件
            full_md_path = extract_dir / "full.md"
            if full_md_path.exists():
                new_md_path = extract_dir / f"{base_name}.md"
                full_md_path.rename(new_md_path)
                print(f"  ✓ 已重命名: full.md -> {base_name}.md")

            print(f"  ✓ 下载完成: {extract_dir}")
            return True

        except Exception as e:
            print(f"  ✗ 下载异常: {str(e)}")
            return False

    def _collect_files(self, input_dir: Path) -> List[Path]:
        """收集输入文件"""
        files = []
        for ext in self.config.SUPPORTED_EXTENSIONS:
            files.extend(input_dir.rglob(f"*{ext}"))
        return sorted(files)

    def run(self, input_dir: Path = None, output_dir: Path = None) -> Dict:
        """
        执行 MinerU 处理阶段

        Args:
            input_dir: 输入目录，默认使用配置中的 INPUT_DIR
            output_dir: 输出目录，默认使用配置中的 MINERU_OUTPUT_DIR

        Returns:
            Dict: 处理统计信息 {'success': int, 'failed': int}
        """
        input_dir = Path(input_dir) if input_dir else self.config.INPUT_DIR
        output_dir = Path(output_dir) if output_dir else self.config.MINERU_OUTPUT_DIR

        output_dir.mkdir(parents=True, exist_ok=True)

        # 收集文件
        files = self._collect_files(input_dir)
        if not files:
            print(f"警告: 在 {input_dir} 中未找到支持的文件")
            return {'success': 0, 'failed': 0}

        if len(files) > self.config.MINERU_MAX_FILES_PER_BATCH:
            print(f"警告: 文件数量超过 {self.config.MINERU_MAX_FILES_PER_BATCH}，只处理前 {self.config.MINERU_MAX_FILES_PER_BATCH} 个")
            files = files[:self.config.MINERU_MAX_FILES_PER_BATCH]

        print(f"\nMinerU 批量文件解析")
        print(f"=" * 60)
        print(f"输入目录: {input_dir}")
        print(f"输出目录: {output_dir}")
        print(f"文件数量: {len(files)}")
        print(f"模型版本: {self.config.MINERU_MODEL_VERSION}")
        print(f"=" * 60)

        # 步骤1: 申请上传链接
        print("\n[步骤1/4] 申请文件上传链接...")
        file_infos = [{"name": f.name} for f in files]

        try:
            options = {
                "enable_table": self.config.MINERU_ENABLE_TABLE,
                "enable_formula": self.config.MINERU_ENABLE_FORMULA,
                "language": self.config.MINERU_LANGUAGE
            }
            batch_id, upload_urls = self._apply_upload_urls(file_infos, **options)
            print(f"✓ 申请成功: batch_id={batch_id}")
        except MinerUAPIError as e:
            print(f"✗ 申请失败: {e}")
            return {'success': 0, 'failed': len(files)}

        # 步骤2: 上传文件
        print("\n[步骤2/4] 上传文件...")
        upload_success = []
        for fp, url in zip(files, upload_urls):
            success = self._upload_file(str(fp), url)
            upload_success.append(success)

        if not any(upload_success):
            print("✗ 所有文件上传失败")
            return {'success': 0, 'failed': len(files)}

        # 步骤3: 等待解析完成
        print("\n[步骤3/4] 等待解析完成...")
        print("提示: 根据文件大小和数量，这可能需要几分钟到几十分钟")

        completed_files = {}
        failed_files = {}

        while True:
            try:
                data = self._query_batch_results(batch_id)
                results = data.get("extract_result", [])

                all_done = True
                for r in results:
                    state = r.get("state", "")
                    file_name = r.get("file_name", "")

                    if state == "done":
                        if file_name not in completed_files:
                            completed_files[file_name] = r
                            print(f"  ✓ 完成: {file_name}")
                    elif state == "failed":
                        if file_name not in failed_files:
                            failed_files[file_name] = r
                            print(f"  ✗ 失败: {file_name} - {r.get('err_msg', '')}")
                    else:
                        all_done = False

                if all_done and len(results) == len(files):
                    print(f"\n✓ 所有任务处理完成")
                    break

                total = len(files)
                done = len(completed_files)
                failed = len(failed_files)
                progress = (done + failed) / total * 100 if total > 0 else 0
                print(f"  进度: {done}/{total} 完成, {failed}/{total} 失败 ({progress:.1f}%)")

                time.sleep(self.config.MINERU_POLL_INTERVAL)

            except MinerUAPIError as e:
                print(f"  ✗ 查询失败: {e}")
                time.sleep(self.config.MINERU_POLL_INTERVAL)
                continue

        # 步骤4: 下载结果
        print("\n[步骤4/4] 下载解析结果...")

        download_count = 0
        for file_name, result in completed_files.items():
            zip_url = result.get("full_zip_url", "")
            if zip_url:
                if self._download_result(zip_url, output_dir, file_name):
                    download_count += 1

        print(f"\n{'='*60}")
        print(f"MinerU 处理完成: 成功 {download_count}, 失败 {len(failed_files)}")
        print(f"结果保存在: {output_dir}")
        print(f"{'='*60}")

        return {
            'success': download_count,
            'failed': len(failed_files)
        }
