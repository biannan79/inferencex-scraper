---
name: InferenceX Data Scraper
description: 从 SemiAnalysis InferenceX 平台自动采集 LLM 推理性能基准数据，转换为结构化 CSV 并合并输出
---

# InferenceX Data Scraper Skill

从 SemiAnalysis InferenceX (原 InferenceMAX) 平台的 Vercel Blob Storage API 自动采集 LLM 推理性能基准数据（End-to-End 延迟、吞吐量、成本、硬件配置等），将嵌套 JSON 展平为结构化 CSV，并合并 E2E 与 Interactivity 两类指标。

## 工作流程概述

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│ 1. API 采集      │ ──▶ │ 2. JSON → CSV   │ ──▶ │ 3. CSV 合并      │ ──▶ │ 4. 输出结果      │
│  (curl + JSON)  │     │  (展平嵌套结构)   │     │ (E2E + Inter)   │     │ (merged.csv)    │
└─────────────────┘     └─────────────────┘     └─────────────────┘     └─────────────────┘
```

## 详细步骤

### 步骤 1: 执行数据采集

从 Vercel Blob Storage 采集最新的 InferenceX 推理性能基准数据。

**默认采集的模型列表**（可自定义）：
- Llama 3.3 70B Instruct
- gpt-oss 120B
- DeepSeek R1 0528
- Kimi K2.5
- MiniMax M2.5
- Qwen 3.5 397B-A17B

**每个模型采集 3 种序列长度**：
- 1K / 1K (短输入短输出)
- 1K / 8K (短输入长输出)
- 8K / 1K (长输入短输出)

**每个组合采集 2 种数据类型**：
- `e2e` — End-to-End 端到端性能指标
- `interactivity` — 交互式推理指标

// turbo
运行采集脚本：
```bash
cd /root/semi-bench && python3 /root/.gemini/antigravity/skills/inferencex-scraper/scripts/scrape_inferencex.py --output-dir json_data/raw_json_files
```

脚本会自动：
1. 从 `availability.json` 索引发现所有可用的模型/日期数据
2. 匹配模型名称到对应的 availability key
3. 获取每个模型最新日期的数据
4. 展平嵌套的 JSON 结构（`{data: [...], gpus: [...]}` → flat records）
5. 保存为标准化的 JSON 文件

### 步骤 2: 转换 JSON 为分类 CSV

将采集到的原始 JSON 文件按 E2E 和 Interactivity 两类分别转换为 CSV 文件。

// turbo
```bash
cd /root/semi-bench && python3 /root/.gemini/antigravity/skills/inferencex-scraper/scripts/convert_to_csv.py --input-dir json_data/raw_json_files --output-dir json_data
```

此步骤会：
1. 自动识别 JSON 文件类型（根据 URL 中的 `e2e.json` 或 `interactivity.json`）
2. 扫描所有记录字段并自动展平嵌套字典（如 `costh: {y: 1.2, roof: true}` → `costh_y`, `costh_roof`）
3. 输出两个 CSV：
   - `inference_max_e2e.csv` — E2E 端到端性能数据
   - `inference_max_interactivity.csv` — 交互性能数据

### 步骤 3: 合并 E2E 与 Interactivity CSV

将两个 CSV 基于复合键 JOIN 合并为一个完整的数据集。

// turbo
```bash
cd /root/semi-bench && python3 /root/.gemini/antigravity/skills/inferencex-scraper/scripts/merge_csv.py --input-dir json_data --output-dir json_data
```

此步骤会：
1. 以 `model_name + sequence_length + conc + hwKey + precision + tp` 为复合键进行匹配
2. 将 E2E 的坐标值重命名为 `e2e_x`, `e2e_y`
3. 将 Interactivity 的坐标值重命名为 `inter_x`, `inter_y`
4. 输出合并后的 `inference_max_merged.csv`

### 步骤 4: 一键执行全流程

如果想一次性完成采集、转换和合并全流程：

// turbo
```bash
cd /root/semi-bench && python3 /root/.gemini/antigravity/skills/inferencex-scraper/scripts/run_pipeline.py --output-base json_data
```

可选参数：
```bash
# 自定义模型（逗号分隔）
--models "Llama 3.3 70B Instruct,DeepSeek R1 0528"

# 自定义序列（逗号分隔）
--sequences "1K / 1K,1K / 8K"

# 指定输出根目录
--output-base /path/to/output

# 仅采集不做转换/合并
--scrape-only

# 仅转换合并（已有 JSON 的情况下）
--convert-only
```

## 依赖要求

- Python 3.8+
- `curl` 命令行工具（避免 Python requests 对 Vercel 的 SSL 挂起问题）
- 标准库：`json`, `csv`, `subprocess`, `re`, `os`, `glob`, `logging`, `argparse`

**无需额外 pip 安装。**

## 输出文件说明

### 原始 JSON 文件
存放于 `json_data/raw_json_files/`，命名格式：
```
{序号}_{模型名}_{序列}_{类型}.json
例如: 01_DeepSeek_R1_0528_1K_____1K_e2e.json
```

每个 JSON 文件包含：
- `metadata` — 采集元数据（模型名、序列长度、URL、日期等）
- `data` — 性能记录列表

### CSV 文件
存放于 `json_data/`：
- `inference_max_e2e.csv` — E2E 端到端性能（约 40-60 列）
- `inference_max_interactivity.csv` — 交互性能（约 40-60 列）
- `inference_max_merged.csv` — 合并数据集（约 80+ 列）

### 合并 CSV 的核心列说明

| 维度 | 核心列 | 说明 |
|------|--------|------|
| 基础信息 | `model_name`, `sequence_length`, `date`, `framework`, `image` | 模型/环境/版本 |
| 硬件 | `hw`, `hwKey`, `tp`, `ep`, `dp_attention`, `is_multinode` | GPU 硬件与并行拓扑 |
| 并发 | `conc`, `isl`, `osl` | 并发数与序列长度 |
| 延迟 | `mean_ttft`, `p99_tpot`, `mean_e2el`, `mean_itl` 等 | 首字/词间/端到端延迟统计 |
| 吞吐 | `tput_per_gpu`, `input_tput_per_gpu`, `output_tput_per_gpu` | 每 GPU 吞吐量 |
| 成本 | `costh_y`, `costn_y`, `costr_y` 及其 `_roof`/`Output` 变体 | 多口径成本分析 |
| 图表坐标 | `e2e_x`, `e2e_y`, `inter_x`, `inter_y` | 前端可视化坐标 |

### 关于空白字段

部分记录的某些列是空白的，这是**正常现象**，不是代码 Bug：
- API 返回的数据字段是**动态长度**的——不同硬件/并发压力下测量的指标集不完全相同
- 例如低并发测试可能包含完整的 50+ 个字段，而高并发极限压测场景下 API 只返回核心吞吐量+成本
- CSV 展平时会以**所有记录中出现过的字段的并集**作为列头，缺失的字段留空

## 数据源技术细节

- **API 入口**: Vercel Blob Storage (`yig6saydz8oscerh.public.blob.vercel-storage.com`)
- **索引文件**: `availability.json` — 包含所有可用的模型/序列 key 及其对应的日期列表
- **数据文件**: `/{date}/{availability-key}-{e2e|interactivity}.json`
- **HTTP 客户端**: 使用 `subprocess + curl` 而非 Python `requests`（避免 SSL 挂起问题）

## 文件结构

```
inferencex-scraper/
├── SKILL.md                    # 本说明文件
└── scripts/
    ├── scrape_inferencex.py    # 步骤 1: API 数据采集
    ├── convert_to_csv.py       # 步骤 2: JSON → CSV 转换
    ├── merge_csv.py            # 步骤 3: CSV 合并
    └── run_pipeline.py         # 一键全流程脚本
```

## 常见问题

### Q: curl 超时怎么办？
A: Vercel Blob Storage 响应较慢，默认超时已设为 120 秒。如仍超时，可在脚本中调整 `--timeout` 参数。

### Q: 如何添加新模型？
A: 运行 `run_pipeline.py` 时通过 `--models` 参数指定，或在脚本内修改 `DEFAULT_MODELS` 列表。新模型必须在 `availability.json` 中存在对应的 key。

### Q: 为什么某些模型采集失败？
A: 常见原因：(1) 模型名称在 availability.json 中的格式与传入的不一致（如 "Kimi K2.5" vs "Kimi K2.5 1T"），脚本已做模糊匹配但可能不完全；(2) 该模型+序列组合确实没有数据。

### Q: 每次运行会覆盖之前的数据吗？
A: 会覆盖 `json_data/raw_json_files/` 中的文件以及 CSV 文件。如需保留历史版本，请使用主 pipeline（`inference_max_pipeline.py`）的版本归档功能（配置 `max_versions`）。
