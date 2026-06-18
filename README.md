# 文档结构化处理 Pipeline v2

这是一个 Python 文档结构化处理 Pipeline，用于把 PDF、Word、PPT、图片、HTML 等输入文件依次经过 MinerU 解析、Kimi 整理、Markdown/图片渲染，最终生成结构化 Markdown 或文本结果。

v2 的核心变化：

- 默认完整流程不再归档或移动 `input/`。
- 每次运行都会创建独立的 `runs/{run_id}/` 目录。
- 图片默认复制到本次运行的 `assets/`，不破坏 MinerU 原始输出。
- 根目录 `pipeline.py` 是日常简易入口；`files_pipeline.cli` 提供高级子命令。

## 快速开始

### 1. 安装依赖

```bash
python3 -m pip install -r requirements.txt
```

依赖包括：

- `requests`：调用 MinerU API 和下载解析结果
- `openai`：以 OpenAI SDK 兼容方式调用 Kimi API
- `python-dotenv`：读取 `.env`

### 2. 配置环境变量

复制 `.env.example` 为 `.env`，并填写 API Token：

```bash
cp .env.example .env
```

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
MINERU_MODEL_VERSION=pipeline
MINERU_ENABLE_TABLE=true
MINERU_ENABLE_FORMULA=false
MINERU_LANGUAGE=ch
MINERU_UPLOAD_TIMEOUT=60
MINERU_UPLOAD_MAX_RETRIES=2
MINERU_UPLOAD_RETRY_DELAY=10
KIMI_TIMEOUT=300
KIMI_MAX_RETRIES=2
KIMI_RETRY_DELAY=5
KIMI_CONCURRENCY=4
ASSETS_DIR=/your/custom/assets/root
IMAGE_BASE_URL=http://your-server/pic
OUTPUT_FORMAT=md
```

`.env` 会覆盖系统环境变量。`OUTPUT_FORMAT` 只允许 `md` 或 `txt`。`KIMI_CONCURRENCY` 控制 Kimi 阶段并发处理文件数，必须是大于等于 1 的整数。`ASSETS_DIR` 留空时图片写入 `runs/{run_id}/assets/`，填写后图片写入 `ASSETS_DIR/{run_id}/`。

### 3. 准备输入文件

将待处理文件放入 `input/`：

```bash
mkdir -p input
cp your-document.pdf input/
```

支持格式：

- PDF：`.pdf`
- Word：`.doc`、`.docx`
- PowerPoint：`.ppt`、`.pptx`
- 图片：`.png`、`.jpg`、`.jpeg`、`.jp2`、`.webp`、`.gif`、`.bmp`
- HTML：`.html`、`.htm`

文件扩展名按大小写不敏感处理，例如 `.PDF` 可以被收集。

### 4. 日常运行

```bash
python3 pipeline.py
```

默认行为：

1. 从 `input/` 读取文件并复制快照到 `runs/{run_id}/source/`
2. 调用 MinerU，写入 `runs/{run_id}/mineru/{source_id}/`
3. 调用 Kimi，写入 `runs/{run_id}/kimi/{source_id}.md`
4. 复制图片到 `runs/{run_id}/assets/{source_id}/`
5. 写入最终结果到 `runs/{run_id}/final/{source_id}.{md|txt}`
6. 写入运行记录 `runs/{run_id}/manifest.json`

完整运行会调用外部 API，但不会移动或清空 `input/`。

## 高级 CLI

完整运行：

```bash
python3 -m files_pipeline.cli run --input input
```

单阶段调试：

```bash
python3 -m files_pipeline.cli parse --input input --run-id demo
python3 -m files_pipeline.cli organize --run-id demo
python3 -m files_pipeline.cli render --run-id demo
```

显式归档：

```bash
python3 -m files_pipeline.cli archive --run-id demo
```

归档只会把 `runs/{run_id}/` 移动到 `data/{run_id}/`，不会处理 `input/`。

查看和补跑失败文件：

```bash
python3 -m files_pipeline.cli failed --run-id demo
python3 -m files_pipeline.cli retry-failed --run-id demo
```

`retry-failed` 会读取原 run 的 `manifest.json` 和 `source/` 快照，只补跑未完成文件缺失的阶段，并把结果写回同一个 `runs/{run_id}/`。

## 目录结构

```text
.
├── input/                         # 输入文件
├── runs/
│   └── {run_id}/
│       ├── source/                # 本次输入快照
│       ├── mineru/{source_id}/    # MinerU 解压结果
│       ├── kimi/{source_id}.md    # Kimi 整理结果
│       ├── assets/{source_id}/    # 复制后的图片
│       ├── final/{source_id}.md   # 最终输出
│       └── manifest.json          # 阶段状态、路径、错误、token 统计
├── data/                          # 显式 archive 命令的目标
├── files_pipeline/
│   ├── clients/                   # MinerU/Kimi API adapter
│   ├── stages/                    # MinerU、Kimi、Render 三阶段
│   ├── prompts/                   # Kimi 模板
│   ├── config.py
│   ├── models.py
│   ├── pipeline.py
│   └── cli.py
├── tests/
├── pipeline.py                    # 简易运行入口
├── .env.example
└── README.md
```

## 运行产物

`manifest.json` 会记录：

- `run_id`
- 每个文档的 `source_id`、原始路径、阶段输出路径、状态和错误
- 每个 stage 的成功/失败数量
- Kimi token 统计

不会记录 API Token。

`source_id` 格式为 `{序号}_{安全文件名}`，例如：

```text
0001_3QC_report
0002_3QC_report
```

序号用于避免同名文件冲突。

## 图片策略

Render 阶段会从 MinerU 输出目录复制图片：

```text
runs/{run_id}/mineru/{source_id}/images/*
-> runs/{run_id}/assets/{source_id}/*
```

如果配置了 `ASSETS_DIR`，图片会复制到：

```text
{ASSETS_DIR}/{run_id}/{source_id}/*
```

默认最终 Markdown 使用相对链接：

```md
![现象](../assets/{source_id}/image.png)
```

配置 `ASSETS_DIR` 但未配置 `IMAGE_BASE_URL` 时，最终 Markdown 会使用从 `runs/{run_id}/final/` 指向该图片目录的相对链接。

如果配置了 `IMAGE_BASE_URL`，最终 Markdown 使用绝对链接：

```md
![现象](http://your-server/pic/{run_id}/{source_id}/image.png)
```

当前识别 `![](images/xxx)`、`![alt](images/xxx)` 和 `![alt](./images/xxx)`。

## 测试

默认单元测试不调用外部 API：

```bash
python3 -m unittest discover -s tests
```

当前覆盖：

- 配置加载、`.env` override、非法配置
- MinerU zip 安全解压、Markdown 规范化、大小写扩展名、mock 解析流程
- Kimi 空文件、重试、失败记录、token 统计
- Render 标题处理、图片复制、相对/绝对链接
- Pipeline 编排、失败 manifest、部分成功状态、失败补跑、默认不归档
- 简易入口和高级 CLI 参数分发

完整 Pipeline 依赖 MinerU/Kimi 网络 API 和真实 Token，不建议作为普通测试命令。

## 故障排查

### 缺少配置

`python3 pipeline.py` 启动时会验证：

- `MINERU_API_TOKEN`
- `KIMI_API_KEY`

缺少任一配置会直接退出。

### 未找到输入文件

确认文件位于 `input/` 下，且扩展名在支持列表内。

### 图片链接未更新

确认 MinerU 输出中存在：

```text
runs/{run_id}/mineru/{source_id}/images/
```

如果没有配置 `IMAGE_BASE_URL`，链接会被改成相对路径，不会变成图床 URL。

### 单阶段调试

优先使用高级 CLI 的 `parse`、`organize`、`render` 子命令，不要为了调试单个阶段反复跑完整流程。
