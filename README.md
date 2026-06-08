# 文档结构化处理 Pipeline

这是一个文档预处理 Pipeline，整合 MinerU 文档解析、Kimi 文档整理、图片处理和归档四个阶段，将 PDF/Word/PPT/图片等文档自动转换为结构化 Markdown 文档。

## 快速开始

### 1. 配置环境变量

复制 `.env.example` 为 `.env`，并填写你的 API Token：

```bash
cp .env.example .env
# 编辑 .env 文件，填入你的 API Token
```

`.env` 文件内容：

```env
# MinerU API 配置
MINERU_BASE_URL=https://mineru.net/api/v4
MINERU_API_TOKEN=your_mineru_token_here

# Kimi API 配置
KIMI_API_KEY=sk-your_kimi_api_key_here
KIMI_MODEL=kimi-k2.5
KIMI_BASE_URL=https://api.moonshot.cn/v1
KIMI_TIMEOUT=300
KIMI_MAX_RETRIES=2
KIMI_RETRY_DELAY=5

# 图片处理配置（可选，留空则跳过图片移动和链接更新，不影响文档结构化功能）
IMAGE_BASE_URL=http://your-server/pic
IMAGE_TARGET_DIR=/path/to/pic
```

### 2. 准备输入文件

将待处理的文档放入 `./input/` 目录：

```bash
mkdir -p input
cp your-document.pdf input/
```

> **提示**：程序首次运行时会自动创建 `input/`、`mineru_output/`、`kimi_output/`、`output/`、`data/` 等必要目录，无需手动创建。

支持的文件格式：
- PDF (`.pdf`)
- Word (`.doc`, `.docx`)
- PowerPoint (`.ppt`, `.pptx`)
- 图片 (`.png`, `.jpg`, `.jpeg`, `.webp`, `.gif`, `.bmp`)
- HTML (`.html`, `.htm`)

### 3. 运行 Pipeline

```bash
python pipeline.py
```

Pipeline 会依次执行四个阶段：
1. **Stage 1**: MinerU 文档解析 - 将输入文件解析为 Markdown
2. **Stage 2**: Kimi 文档整理 - 按照模板格式重新整理内容
3. **Stage 3**: 图片处理和链接更新 - 移动图片并更新链接
4. **Stage 4**: 归档中间文件 - 将中间文件归档到时间戳目录

### 4. 查看结果

最终结果保存在 `./output/` 目录：

```bash
ls output/
```

## 目录结构

```
.
├─── input/                      # 输入文件目录
├─── mineru_output/              # 阶段1: MinerU 解析输出
├─── kimi_output/                # 阶段2: Kimi 处理输出
├─── output/                     # 阶段3: 最终输出
├─── data/                       # 阶段4: 归档目录
│   └─── {timestamp}/
│       ├─── input/
│       ├─── mineru_output/
│       └─── kimi_output/
├─── stages/                     # Pipeline 阶段模块
│   ├─── __init__.py
│   ├─── base_stage.py           # Stage 基类
│   ├─── mineru_stage.py         # 阶段1: MinerU 文档解析
│   ├─── kimi_stage.py           # 阶段2: Kimi 文档处理
│   ├─── image_stage.py          # 阶段3: 图片处理
│   └─── archive_stage.py        # 阶段4: 归档
├─── config.py                   # 统一配置模块
├─── pipeline.py                 # Pipeline 主程序
├─── CLAUDE.md                   # 项目文档
├─── README.md                   # 用户文档
└─── .env                        # 环境变量配置（用户创建）
```

## 执行流程

```
输入文件 (./input)
    ↓
[阶段1: MinerU 文档解析]
    - 调用 MinerU API 解析 PDF/Word/PPT/图片
    - 输出 Markdown + 图片到 ./mineru_output/
    ↓
[阶段2: Kimi 文档处理]
    - 调用 Kimi API 按模板重新整理内容
    - 输出处理后的 Markdown 到 ./kimi_output/
    ↓
[阶段3: 图片处理和链接更新]
    - 移动图片到目标目录
    - 处理 Markdown 内容：
      - 提取"不良项目"标题拼接到二级标题
      - 第二个二级标题起前面添加分隔符 +=+=+=
      - 第二个二级标题起，将拼接后的标题拼接到下属三级标题上并删除该二级标题
        （若该二级标题下没有三级标题，则保留原样）
    - 更新图片链接
    - 输出最终结果到 ./output/
    ↓
[阶段4: 归档中间文件]
    - 归档 input/, kimi_output/, mineru_output/ 到 data/{timestamp}/
    - 重新创建空的源目录
```

## 配置说明

### MinerU 配置

在 `config.py` 中可以修改 MinerU 的配置：

```python
# MinerU 处理配置
MINERU_MODEL_VERSION = "vlm"  # 可选: "pipeline", "vlm", "MinerU-HTML"
MINERU_ENABLE_TABLE = True    # 是否开启表格识别
MINERU_ENABLE_FORMULA = False # 是否开启公式识别
MINERU_LANGUAGE = "ch"        # 文档语言
```

### Kimi 配置

在 `.env` 中可以配置 Kimi API 的超时和重试：

```env
KIMI_TIMEOUT=300
KIMI_MAX_RETRIES=2
KIMI_RETRY_DELAY=5
```

- `KIMI_TIMEOUT`：单次 Kimi API 调用超时时间，默认 300 秒
- `KIMI_MAX_RETRIES`：单个文档处理失败后的重试次数，默认 2 次
- `KIMI_RETRY_DELAY`：每次重试前等待秒数，默认 5 秒

默认配置下，每个文档最多会尝试 3 次：首次调用 + 2 次重试。

### 图片处理配置

在 `.env` 中配置图片服务器（可选）：

```env
# 图片处理配置（留空则跳过图片移动和链接更新）
IMAGE_BASE_URL=http://your-server/pic
IMAGE_TARGET_DIR=/path/to/pic
```

- `IMAGE_BASE_URL`：图片服务器访问 URL 前缀
- `IMAGE_TARGET_DIR`：图片文件物理存放路径

若两者任一留空，Pipeline 将跳过图片移动和链接更新步骤，仅保留 Markdown 内容处理。

## 故障排查

### 常见问题

1. **导入错误**
   ```bash
   # 确保在虚拟环境中安装了依赖
   pip install -r requirements.txt
   ```

2. **API Token 错误**
   - 检查 `.env` 文件是否存在
   - 确认 API Token 是否正确

3. **目录权限错误**
   - 确保程序有权限读写输入输出目录

### 调试模式

可以单独运行某个 stage 进行调试：

```python
# 测试 MinerU Stage
from stages.mineru_stage import MinerUStage

stage = MinerUStage()
result = stage.run(
    input_dir=Path("./input"),
    output_dir=Path("./test_output")
)
print(result)
```

## 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情
