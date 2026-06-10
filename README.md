# 文档结构化处理 Pipeline

这是一个 Python 文档结构化处理 Pipeline，用于将 PDF、Word、PPT、图片、HTML 等输入文件依次经过 MinerU 解析、Kimi 整理、图片链接处理和归档，最终生成结构化 Markdown 或文本结果。

完整流程会调用外部 API，并在结束时归档 `input/`、`mineru_output/`、`kimi_output/`。运行前请确认 `.env` 和 `input/` 中的文件无误。

## 快速开始

### 1. 安装依赖

建议在虚拟环境中安装：

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

必填配置：

```env
MINERU_BASE_URL=https://mineru.net/api/v4
MINERU_API_TOKEN=your_mineru_token_here
KIMI_API_KEY=sk-your_kimi_api_key_here
KIMI_MODEL=kimi-k2.5
KIMI_BASE_URL=https://api.moonshot.cn/v1
```

可选配置：

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

### 3. 准备输入文件

将待处理文件放入 `input/`：

```bash
mkdir -p input
cp your-document.pdf input/
```

程序运行时会自动创建 `input/`、`mineru_output/`、`kimi_output/`、`output/`、`data/` 等目录。

支持的文件格式由 `Config.SUPPORTED_EXTENSIONS` 控制，当前包括：

- PDF：`.pdf`
- Word：`.doc`、`.docx`
- PowerPoint：`.ppt`、`.pptx`
- 图片：`.png`、`.jpg`、`.jpeg`、`.jp2`、`.webp`、`.gif`、`.bmp`
- HTML：`.html`、`.htm`

注意：当前文件收集按小写扩展名匹配，类似 `.PDF` 这种大写扩展名不会被处理。

### 4. 运行 Pipeline

```bash
python3 pipeline.py
```

执行顺序：

1. `MinerUStage`：上传并解析输入文件，下载解析结果到 `mineru_output/`
2. `KimiStage`：读取本次 MinerU 产出的 Markdown，按不良报告模板整理到 `kimi_output/batch_{timestamp}/`
3. `ImageStage`：处理标题结构、可选移动图片并更新链接，写入 `output/`
4. `ArchiveStage`：归档中间目录到 `data/{YYYYMMDDHHMMSS}/`，并重新创建空目录

最终文件保存在 `output/`。默认文件名保留 Kimi 输出前缀，例如 `processed_xxx.md`。

## 目录结构

```text
.
├── input/                  # 输入文件目录
├── mineru_output/          # MinerU 解析输出
│   └── {filename}/
│       ├── {filename}.md   # full.md 会被重命名
│       └── images/
├── kimi_output/            # Kimi 整理输出
│   └── batch_{timestamp}/
│       └── processed_*.md
├── output/                 # 最终输出
├── data/                   # 归档目录
│   └── {YYYYMMDDHHMMSS}/
│       ├── input/
│       ├── mineru_output/
│       └── kimi_output/
├── stages/
│   ├── base_stage.py
│   ├── mineru_stage.py
│   ├── kimi_stage.py
│   ├── image_stage.py
│   └── archive_stage.py
├── tests/
├── config.py
├── pipeline.py
├── .env.example
└── README.md
```

## 配置说明

### MinerU

代码内默认配置：

```python
MINERU_MODEL_VERSION = "vlm"
MINERU_ENABLE_TABLE = True
MINERU_ENABLE_FORMULA = False
MINERU_LANGUAGE = "ch"
MINERU_MAX_FILES_PER_BATCH = 200
MINERU_POLL_INTERVAL = 10
```

可通过 `.env` 控制的保护参数：

- `MINERU_MAX_POLL_TIME`：单个批次最大轮询秒数，代码默认 `3600`
- `MINERU_MAX_QUERY_ERRORS`：连续查询失败上限，代码默认 `10`

MinerU 解析结果下载后会安全解压，防止 zip 路径穿越；如果压缩包内存在 `full.md`，会重命名为 `{原文件名}.md`。

### Kimi

可通过 `.env` 配置：

- `KIMI_MODEL`：默认 `kimi-k2.5`
- `KIMI_BASE_URL`：默认 `https://api.moonshot.cn/v1`
- `KIMI_TIMEOUT`：未配置时代码默认 `600` 秒，`.env.example` 示例值为 `300`
- `KIMI_MAX_RETRIES`：失败重试次数，代码默认 `2`
- `KIMI_RETRY_DELAY`：重试等待秒数，未配置时代码默认 `10`

默认最大尝试次数为 `首次调用 + KIMI_MAX_RETRIES`。Kimi 阶段会统计 prompt、completion 和 total token。

### 图片和输出格式

```env
IMAGE_BASE_URL=http://your-server/pic
IMAGE_TARGET_DIR=/path/to/pic
OUTPUT_FORMAT=md
```

- `IMAGE_BASE_URL` 和 `IMAGE_TARGET_DIR` 必须同时配置，才会移动图片并更新链接
- 任一为空时，图片移动和图片链接更新会跳过，但 Markdown 标题结构处理仍会执行
- 图片会移动到 `{IMAGE_TARGET_DIR}/{timestamp}/{document_name}/`
- 链接会更新为 `{IMAGE_BASE_URL}/{timestamp}/{document_name}/{image_name}`
- `OUTPUT_FORMAT` 当前约定为 `md` 或 `txt`

图片链接更新当前匹配 `![](images/xxx)` 形式。

## 阶段行为

### Stage 1: MinerU 文档解析

- 从 `input/` 递归收集支持格式文件
- 单批最多处理 `MINERU_MAX_FILES_PER_BATCH` 个文件，超出后只取排序后的前 200 个
- 申请批量上传 URL，逐个上传文件
- 轮询解析状态，直到完成、失败、超时或连续查询错误达到上限
- 下载成功结果并返回本次实际产出的 Markdown 路径

### Stage 2: Kimi 文档整理

- 只处理 Stage 1 本次返回的 Markdown 文件，不扫描历史输出
- 每次运行创建 `kimi_output/batch_{YYYYMMDD_HHMMSS}/`
- 输出文件名为 `processed_{原Markdown文件名}.md`
- 如果单个文档处理失败，会记录到 `failed_files`

### Stage 3: 图片处理和链接更新

- 从 Kimi 输出文件名反推 MinerU 输出目录，例如 `processed_doc.md` 对应 `mineru_output/doc/`
- 提取一级标题 `# 不良项目：...` 或独立行 `不良项目：...`
- 将不良项目标题拼接到二级标题
- 从第二个二级标题起插入分隔符 `+=+=+=`
- 第二个及之后的二级标题如果有下属三级标题，会把二级标题信息拼接到三级标题上，并删除该二级标题
- 根据 `OUTPUT_FORMAT` 写入最终文件

### Stage 4: 归档

- 默认归档 `input/`、`kimi_output/`、`mineru_output/`
- 归档位置为 `data/{YYYYMMDDHHMMSS}/`
- 归档后重新创建空的源目录
- Kimi 失败的原始输入文件会从归档目录复制回 `input/`，便于下次重跑

## 测试

当前单元测试不调用外部 API，可以直接运行：

```bash
python3 -m unittest discover -s tests
```

已覆盖：

- MinerU zip 安全解压拒绝路径穿越
- 图片按文档子目录移动，并生成对应文档链接

完整 Pipeline 依赖 MinerU/Kimi 网络 API 和真实 Token，且会归档输入和中间目录；不要把 `python3 pipeline.py` 当作普通单元测试命令。

## 故障排查

### 缺少配置

`pipeline.py` 启动时会验证：

- `MINERU_API_TOKEN`
- `KIMI_API_KEY`

缺少任一配置会直接退出。

### 未找到输入文件

确认文件位于 `input/` 下，且扩展名为当前支持的小写格式。

### 图片没有移动或链接未更新

确认 `.env` 同时配置了：

```env
IMAGE_BASE_URL=...
IMAGE_TARGET_DIR=...
```

并确认 MinerU 输出目录中存在 `mineru_output/{document_name}/images/`。

### API 调用失败

检查 Token、网络、API 限流和模型配置。MinerU 与 Kimi 的网络错误属于正常失败路径，优先通过单个 Stage 或小样本文件排查。
