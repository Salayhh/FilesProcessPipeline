# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

这是一个文档结构化处理工具集，包含两个主要功能：
1. **MinerU 批量文档解析** - 调用 MinerU API 将 PDF/Word/PPT/图片等文档解析为 Markdown
2. **Kimi 批量文档整理** - 调用 Kimi API 将不良品报告按照模板格式重新整理

## 常用命令

```bash
# 运行完整 Pipeline
python pipeline.py

# 安装依赖
pip install -r requirements.txt

# 单独测试某个 Stage（见各阶段说明）
```

## 环境变量配置

`.env` 文件需配置以下变量：

```env
# MinerU API 配置
MINERU_BASE_URL=https://mineru.net/api/v4
MINERU_API_TOKEN=your_mineru_token_here

# Kimi API 配置
KIMI_API_KEY=sk-your_kimi_api_key_here
KIMI_MODEL=kimi-k2.5
KIMI_BASE_URL=https://api.moonshot.cn/v1
```

## Pipeline 架构

项目采用四阶段 Pipeline 架构：

```
输入文件 (./input)
    ↓
[Stage 1: MinerU 文档解析]
    - 调用 MinerU API 解析 PDF/Word/PPT/图片
    - 输出 Markdown + 图片到 ./mineru_output/
    ↓
[Stage 2: Kimi 文档整理]
    - 调用 Kimi API 按模板重新整理内容
    - 输出整理后的 Markdown 到 ./kimi_output/
    ↓
[Stage 3: 图片处理和链接更新]
    - 移动图片到目标目录
    - 处理 Markdown 内容（添加标题、分隔符）
    - 更新图片链接为服务器 URL
    - 输出最终结果到 ./output/
    ↓
[Stage 4: 归档]
    - 归档中间文件到 ./data/{timestamp}/
    - 重新创建空的输入/输出目录
```

### 使用方法

**运行完整 Pipeline：**
```bash
python pipeline.py
```

**Pipeline 流程：**
1. 将待处理文件放入 `./input/` 目录
2. 运行 `python pipeline.py`
3. 查看 `./output/` 目录获取最终结果

### 目录结构

```
.
├── input/                  # 输入文件目录
├── mineru_output/          # MinerU 解析输出
│   └── {filename}/
│       ├── full.md
│       └── images/
├── kimi_output/            # Kimi 整理输出
│   └── batch_{timestamp}/
│       └── processed_*.md
├── output/                 # 最终输出
├── data/                   # 归档目录
│   └── {timestamp}/
│       ├── input/
│       ├── mineru_output/
│       └── kimi_output/
├── stages/                 # Pipeline 阶段模块
│   ├── __init__.py
│   ├── base_stage.py       # 基础阶段类
│   ├── mineru_stage.py     # Stage 1: MinerU 解析
│   ├── kimi_stage.py       # Stage 2: Kimi 整理
│   ├── image_stage.py      # Stage 3: 图片处理
│   └── archive_stage.py    # Stage 4: 归档
├── config.py               # 统一配置模块
├── pipeline.py             # Pipeline 主程序
└── .env                    # 环境变量配置
```

## 代码架构说明

### 基础架构
- `BaseStage` 抽象基类定义了 `run()` 接口
- 所有 Stage 继承自 `BaseStage`
- `config.py` 集中管理所有配置（环境变量、路径、常量）
- `config.py` 有重复的 `DATA_DIR` 定义（第24行和第27行）

### MinerU 处理器架构
- `MinerUStage` 类封装 API 调用
- 主要流程：申请上传链接 → 上传文件 → 轮询任务状态 → 下载结果
- 支持三种模型：`pipeline`（默认）、`vlm`、`MinerU-HTML`
- 配置项：`MINERU_MODEL_VERSION`, `MINERU_ENABLE_TABLE`, `MINERU_ENABLE_FORMULA`, `MINERU_LANGUAGE`

### Kimi 处理器架构
- 使用 OpenAI SDK 调用 Kimi API
- 通过 `file-extract` purpose 上传文件并抽取内容
- 将文件内容作为 system prompt 进行对话
- 主要任务：将不良品报告按照模板格式重新整理

### 图片处理架构
- 从 MinerU 输出目录收集图片
- 移动图片到目标服务器目录 (`IMAGE_TARGET_DIR`)
- 处理 Markdown 内容：
  - 提取一级标题（不良项目）
  - 将标题添加到二级标题前
  - 在二级标题间添加分隔符 (`+=+=+=`)
  - 更新图片链接为服务器 URL (`IMAGE_BASE_URL`)

### 归档阶段架构
- `ArchiveStage` 将中间目录归档到带时间戳的目录
- 默认归档：`input/`, `kimi_output/`, `mineru_output/`
- 归档后重新创建空的源目录
- 归档位置：`data/{YYYYMMDDHHMMSS}/`

## 模板说明

不良品报告模板包含五个部分：
1. **发生状况 (5W2H)** - 不良现象、车型、零件、日期、地点等
2. **事实把握** - 不良品确认、现生产品品质、发生范围、再现试验
3. **原因调查** - 发生原因、流出原因、why-why分析
4. **改善对策** - 事象对策、再发防止、已出货品处置
5. **水平展开** - 同车型、不同车型、组织内展开

## 开发注意事项

1. API Token 不要硬编码，使用 `.env` 文件管理
2. MinerU API 单次最多处理 200 个文件 (`MINERU_MAX_FILES_PER_BATCH`)
3. Pipeline 执行过程中会创建批次目录，用于区分不同批次的处理结果
4. 图片处理阶段需要确保目标服务器目录可访问
5. 每个阶段都有独立的错误处理，单个文件失败不会影响其他文件的处理
6. `config.py` 中 `DATA_DIR` 定义重复，建议修复
