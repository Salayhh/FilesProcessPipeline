"""
Pipeline 配置管理模块
集中管理所有配置参数和环境变量
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()


class Config:
    """统一配置类"""

    # 基础路径配置
    BASE_DIR = Path(__file__).parent
    INPUT_DIR = BASE_DIR / "input"
    MINERU_OUTPUT_DIR = BASE_DIR / "mineru_output"
    KIMI_OUTPUT_DIR = BASE_DIR / "kimi_output"
    OUTPUT_DIR = BASE_DIR / "output"

    # 数据归档目录
    DATA_DIR = BASE_DIR / "data"

    # 数据归档目录
    DATA_DIR = BASE_DIR / "data"

    # MinerU API 配置
    MINERU_BASE_URL = os.getenv("MINERU_BASE_URL", "https://mineru.net/api/v4")
    MINERU_API_TOKEN = os.getenv("MINERU_API_TOKEN")

    # MinerU 处理配置
    MINERU_MODEL_VERSION = "vlm"  # 可选: "pipeline", "vlm", "MinerU-HTML"
    MINERU_ENABLE_TABLE = True
    MINERU_ENABLE_FORMULA = False
    MINERU_LANGUAGE = "ch"
    MINERU_MAX_FILES_PER_BATCH = 200
    MINERU_POLL_INTERVAL = 10  # 秒

    # Kimi API 配置
    KIMI_API_KEY = os.getenv("KIMI_API_KEY")
    KIMI_MODEL = os.getenv("KIMI_MODEL", "kimi-k2.6")
    KIMI_BASE_URL = os.getenv("KIMI_BASE_URL", "https://api.moonshot.cn/v1")

    # 图片&文档处理配置
    IMAGE_BASE_URL = "http://172.16.75.37:60128/pic"
    IMAGE_TARGET_DIR = Path("D:/工作/信息数据系/文件服务器/pic")
    SECTION_SEPARATOR = "+=+=+="

    # 支持的文件扩展名
    SUPPORTED_EXTENSIONS = {
        '.pdf', '.doc', '.docx', '.ppt', '.pptx',
        '.png', '.jpg', '.jpeg', '.jp2', '.webp', '.gif', '.bmp',
        '.html', '.htm'
    }

    @classmethod
    def validate(cls) -> list:
        """验证配置是否完整，返回缺失的配置项列表"""
        missing = []

        if not cls.MINERU_API_TOKEN:
            missing.append("MINERU_API_TOKEN")
        if not cls.KIMI_API_KEY:
            missing.append("KIMI_API_KEY")

        return missing

    @classmethod
    def ensure_directories(cls):
        """确保所有必要的目录存在"""
        dirs = [
            cls.INPUT_DIR,
            cls.MINERU_OUTPUT_DIR,
            cls.KIMI_OUTPUT_DIR,
            cls.OUTPUT_DIR,
            cls.IMAGE_TARGET_DIR,
            cls.DATA_DIR,
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)
