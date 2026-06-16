# AGENTS.md instructions for /Users/mitozuki/workspace/FilesProcessPipeline

本项目是一个 Python 文档结构化处理 Pipeline，用于把 PDF、Word、PPT、图片、HTML 等输入文件依次经过 MinerU 解析、Kimi 整理、Markdown/图片渲染，最终生成结构化 Markdown 或文本结果。

请使用中文与用户沟通。用户使用 macOS 26.5，习惯把环境变量放在 `.env` 文件内。

## 项目结构

```text
.
├── pipeline.py                    # 日常简易入口
├── files_pipeline/                # v2 核心包
│   ├── config.py                  # Settings.from_env()，统一配置
│   ├── models.py                  # RunContext、DocumentRecord、StageResult、RunManifest
│   ├── pipeline.py                # 核心编排 API
│   ├── cli.py                     # 高级 CLI 子命令
│   ├── markdown.py                # Markdown 标题和图片链接处理
│   ├── assets.py                  # 图片复制
│   ├── clients/
│   │   ├── mineru.py              # MinerU API adapter
│   │   └── kimi.py                # Kimi API adapter
│   ├── stages/
│   │   ├── mineru.py              # Stage 1: MinerU 文档解析
│   │   ├── kimi.py                # Stage 2: Kimi 文档整理
│   │   └── render.py              # Stage 3: Markdown/Image 渲染
│   └── prompts/
│       └── kimi_bad_report_template.md
├── tests/                         # 单元测试
└── README.md                      # 用户文档
```

运行时会自动创建或使用这些目录：

```text
input/                             # 输入文件
runs/{run_id}/source/              # 本次输入快照
runs/{run_id}/mineru/{source_id}/  # MinerU 解析输出
runs/{run_id}/kimi/                # Kimi 整理输出
runs/{run_id}/assets/{source_id}/  # 复制后的图片
runs/{run_id}/final/               # 最终输出
runs/{run_id}/manifest.json        # 运行记录
data/{run_id}/                     # 显式 archive 命令的归档目标
```

## 运行方式

日常完整运行：

```bash
python3 pipeline.py
```

高级 CLI：

```bash
python3 -m files_pipeline.cli run --input input
python3 -m files_pipeline.cli parse --input input --run-id demo
python3 -m files_pipeline.cli organize --run-id demo
python3 -m files_pipeline.cli render --run-id demo
python3 -m files_pipeline.cli archive --run-id demo
```

完整运行会调用外部 API，但默认不会归档或移动 `input/`。只有显式执行 `archive` 命令时，才会把 `runs/{run_id}/` 移动到 `data/{run_id}/`。

单元测试：

```bash
python3 -m unittest discover -s tests
```

当前测试不依赖外部 API，适合在修改后优先运行。

## 环境变量

环境变量从 `.env` 加载，`Settings.from_env()` 使用 `load_dotenv(override=True)`，因此 `.env` 会覆盖系统环境变量。

必填：

```env
MINERU_BASE_URL=https://mineru.net/api/v4
MINERU_API_TOKEN=your_mineru_token_here
KIMI_API_KEY=sk-your_kimi_api_key_here
KIMI_MODEL=kimi-k2.5
KIMI_BASE_URL=https://api.moonshot.cn/v1
```

可选：

```env
MINERU_MAX_POLL_TIME=3600
MINERU_MAX_QUERY_ERRORS=10
KIMI_TIMEOUT=300
KIMI_MAX_RETRIES=2
KIMI_RETRY_DELAY=5
IMAGE_BASE_URL=http://your-server/pic
OUTPUT_FORMAT=md
```

如果 `IMAGE_BASE_URL` 为空，最终 Markdown 使用 `../assets/{source_id}/...` 相对链接。配置后使用 `{IMAGE_BASE_URL}/{run_id}/{source_id}/...` 绝对链接。

## Pipeline 设计

核心编排位于 `files_pipeline/pipeline.py`，顺序执行三阶段：

1. `MinerUStage.run(context, documents)`：读取 `DocumentRecord.source_path`，调用 MinerU API，下载并安全解压结果到 `runs/{run_id}/mineru/{source_id}/`，写回 `mineru_markdown_path`。
2. `KimiStage.run(context, documents)`：读取 `mineru_markdown_path`，调用 Kimi API 按模板整理，写入 `runs/{run_id}/kimi/{source_id}.md`，累计 token。
3. `RenderStage.run(context, documents)`：处理 Markdown 标题结构，复制图片到 `assets/`，更新图片链接，写入 `runs/{run_id}/final/{source_id}.{md|txt}`。

各 Stage 返回 `StageResult`，不要再使用裸 dict 作为 stage 契约。

## 开发规则

- 先理解现有流程和副作用，再写代码；不确定或存在歧义时，主动询问用户澄清。
- 优先使用简单、低复杂度的 Python 实现，避免引入不必要的框架或抽象。
- 配置、路径、常量优先放在 `files_pipeline/config.py` 的 `Settings` 中，不要在业务代码里硬编码 API Token、目录或模型参数。
- 修改现有代码时，只改与任务相关的部分，不动无关代码或注释。
- 保持当前模块边界：Pipeline 负责编排，Stage 负责单阶段处理，Client 负责外部 API，`Settings` 负责配置。
- 文件读写默认使用 UTF-8；需要兼容历史文档时，使用 `files_pipeline.stages.kimi.read_text_with_fallback()` 的编码兜底方式。
- 支持文件类型通过 `SUPPORTED_EXTENSIONS` 维护。
- 输出格式通过 `OUTPUT_FORMAT` 控制，当前只允许 `md` 或 `txt`。
- 输入文件收集已支持大小写扩展名，例如 `.PDF`。

## 测试和验证

- 优先对单个 Stage 或纯函数做小范围验证，避免直接跑完整 pipeline。
- 修改通用行为后运行 `python3 -m unittest discover -s tests`。
- 完整 pipeline 依赖 MinerU/Kimi 网络 API 和真实 Token；运行前必须确认 `.env`、`input/` 内容和用户意图。
- 调试图片处理时，可以只构造 `runs/{run_id}/kimi/` 和 `runs/{run_id}/mineru/{source_id}/images/`，调用 `RenderStage.run()`。
- 调试归档逻辑时注意它会移动 `runs/{run_id}/`；不要对重要 run 目录随意执行 archive。

## 已知注意事项

- `pipeline.py` 是简易入口，不承载业务逻辑；核心逻辑在 `files_pipeline/pipeline.py`。
- `MinerUStage` 和 `KimiStage` 会访问外部服务；网络失败、Token 错误和 API 限流都应作为正常失败路径处理。
- `MinerUStage.extract_zip_safely()` 已有路径穿越保护，修改解压逻辑时必须保留安全校验。
- `RenderStage` 会使用正则处理 Markdown 标题和图片链接，修改时要准备覆盖标题格式、无图片、无三级标题、多个文档同名图片等边界情况。
- `manifest.json` 不应写入 API Token 或完整环境变量。
