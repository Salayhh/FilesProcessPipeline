# AGENTS.md instructions for /Users/mitozuki/workspace/FilesProcessPipeline

本项目是一个 Python 文档结构化处理 Pipeline，用于把 PDF、Word、PPT、图片、HTML 等输入文件依次经过 MinerU 解析、Kimi 整理、图片链接处理和归档，最终生成结构化 Markdown 或文本结果。

请使用中文与用户沟通。用户使用 macOS 26.5，习惯把环境变量放在 `.env` 文件内。

## 项目结构

```text
.
├── pipeline.py              # Pipeline 主协调器
├── config.py                # 统一配置、环境变量和路径定义
├── stages/                  # 各阶段实现
│   ├── base_stage.py        # Stage 抽象基类，目前不是所有 Stage 都继承它
│   ├── mineru_stage.py      # Stage 1: MinerU 文档解析
│   ├── kimi_stage.py        # Stage 2: Kimi 文档整理
│   ├── image_stage.py       # Stage 3: 图片处理和链接更新
│   └── archive_stage.py     # Stage 4: 中间文件归档
├── tests/                   # 单元测试
├── README.md                # 用户文档
├── CLAUDE.md                # 旧项目说明，可能有过期内容
└── pipeline_demo.html       # 演示页面
```

运行时会自动创建或使用这些目录：

```text
input/                       # 输入文件
mineru_output/               # MinerU 解析输出
kimi_output/                 # Kimi 整理输出
output/                      # 最终输出
data/{timestamp}/            # 归档后的 input、mineru_output、kimi_output
```

## 运行方式

完整运行：

```bash
python3 pipeline.py
```

完整运行会调用外部 API，并且最后会执行归档：`input/`、`mineru_output/`、`kimi_output/` 会被移动到 `data/{timestamp}/`，随后重新创建为空目录。除非用户明确要求运行完整流程，否则不要随意执行 `python3 pipeline.py`。

单元测试：

```bash
python3 -m unittest discover -s tests
```

当前测试不依赖外部 API，适合在修改后优先运行。

## 环境变量

环境变量从 `.env` 加载，`config.py` 使用 `load_dotenv(override=True)`，因此 `.env` 会覆盖系统环境变量。

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
IMAGE_TARGET_DIR=/path/to/pic
OUTPUT_FORMAT=md
```

如果 `IMAGE_BASE_URL` 或 `IMAGE_TARGET_DIR` 为空，图片移动和图片链接更新会跳过，但 Markdown 内容处理仍会执行。

## Pipeline 设计

`DocumentPipeline` 位于 `pipeline.py`，顺序执行四个阶段：

1. `MinerUStage.run(input_dir, output_dir)`：收集支持格式文件，申请上传 URL，上传文件，轮询解析结果，下载并解压结果到 `mineru_output/`，返回本次产出的 Markdown 路径。
2. `KimiStage.run(input_files, output_dir)`：只读取传入的 MinerU Markdown，调用 Kimi API 按不良报告模板整理，写入 `kimi_output/batch_{YYYYMMDD_HHMMSS}/processed_*.md`。
3. `ImageStage.run(kimi_output_files, mineru_output_dir, final_output_dir)`：处理 Markdown 标题结构，按配置移动图片并更新链接，写入 `output/`。
4. `ArchiveStage.run(files_to_keep=...)`：移动 `input/`、`kimi_output/`、`mineru_output/` 到 `data/{YYYYMMDDHHMMSS}/` 并重建空目录；Kimi 失败的原始输入文件会复制回 `input/`。

各 Stage 的 `run()` 应返回统计字典，至少包含 `success` 和 `failed`。修改或新增 Stage 时，保持这个约定，避免破坏 `DocumentPipeline._print_summary()`。

## 开发规则

- 先理解现有流程和副作用，再写代码；不确定或存在歧义时，主动询问用户澄清。
- 优先使用简单、低复杂度的 Python 实现，避免引入不必要的框架或抽象。
- 配置、路径、常量优先放在 `config.py` 的 `Config` 中，不要在业务代码里硬编码 API Token、目录或模型参数。
- 修改现有代码时，只改与任务相关的部分，不动无关代码或注释。
- 保持当前模块边界：Pipeline 负责编排，Stage 负责单阶段处理，`Config` 负责配置。
- 文件读写默认使用 UTF-8；需要兼容历史文档时，可参考 `KimiStage._read_file_content()` 的编码兜底方式。
- 支持文件类型应通过 `Config.SUPPORTED_EXTENSIONS` 维护。
- 输出格式通过 `OUTPUT_FORMAT` 控制，当前约定为 `md` 或 `txt`。
- 当前文件收集使用小写扩展名模式，例如 `*.pdf`；如果要支持 `.PDF`，需要修改收集逻辑并补测试。

## 测试和验证

- 优先对单个 Stage 或纯函数做小范围验证，避免直接跑完整 pipeline。
- 修改通用行为后运行 `python3 -m unittest discover -s tests`。
- 完整 pipeline 依赖 MinerU/Kimi 网络 API 和真实 Token，且会归档输入和中间目录；运行前必须确认 `.env`、`input/` 内容和用户意图。
- 调试图片处理时，可以只构造 Kimi 输出 Markdown 和 MinerU 图片目录，调用 `ImageStage.run()`，避免触发外部 API。
- 调试归档逻辑时注意它会移动目录；不要用真实重要输入目录做随意测试。

## 已知注意事项

- `CLAUDE.md` 中部分描述已经过期，例如 Kimi 文件抽取、BaseStage 继承关系、MinerU 默认模型等；以代码和 README 为准。
- `MinerUStage` 和 `KimiStage` 会访问外部服务；网络失败、Token 错误和 API 限流都应作为正常失败路径处理。
- `MinerUStage._extract_zip_safely()` 已有路径穿越保护，修改解压逻辑时必须保留安全校验。
- `ImageStage` 会使用正则处理 Markdown 标题和图片链接，修改时要准备覆盖标题格式、无图片、无三级标题、多个文档同名图片等边界情况。
- `ImageStage` 当前主要识别 `不良项目：` 全角冒号和 `![](images/xxx)` 图片链接形式；扩展格式时要同步更新测试和 README。
