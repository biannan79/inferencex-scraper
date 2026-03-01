# InferenceX Data Scraper

从 [SemiAnalysis InferenceX](https://inferencex.semianalysis.com/) 平台自动采集 LLM 推理性能基准数据，转换为结构化 CSV 并合并输出。

## ✨ 功能特性

- 🔄 **全自动采集** — 从 Vercel Blob Storage API 获取最新推理性能基准数据
- 📊 **智能展平** — 自动处理嵌套 JSON 结构（`{data: [...], gpus: [...]}` → flat records）
- 🔗 **数据合并** — 基于复合键 JOIN E2E 与 Interactivity 两类指标
- 🛡️ **SSL 兼容** — 使用 `subprocess + curl` 绕过 Python requests 的 SSL 挂起问题
- 📦 **零依赖** — 仅使用 Python 标准库 + `curl`，无需额外 `pip install`

## 📋 工作流程

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│ 1. API 采集      │ ──▶ │ 2. JSON → CSV   │ ──▶ │ 3. CSV 合并      │ ──▶ │ 4. 输出结果      │
│  (curl + JSON)  │     │  (展平嵌套结构)   │     │ (E2E + Inter)   │     │ (merged.csv)    │
└─────────────────┘     └─────────────────┘     └─────────────────┘     └─────────────────┘
```

## 🚀 快速开始

### 一键执行全流程

```bash
python3 scripts/run_pipeline.py --output-base json_data
```

### 分步执行

```bash
# 步骤 1: 从 API 采集原始 JSON 数据
python3 scripts/scrape_inferencex.py --output-dir json_data/raw_json_files

# 步骤 2: 将 JSON 按类型转换为 E2E 和 Interactivity CSV
python3 scripts/convert_to_csv.py --input-dir json_data/raw_json_files --output-dir json_data

# 步骤 3: 合并两个 CSV 为最终数据集
python3 scripts/merge_csv.py --input-dir json_data --output-dir json_data
```

### 自定义参数

```bash
# 自定义模型列表（逗号分隔）
python3 scripts/run_pipeline.py --models "DeepSeek R1 0528,Kimi K2.5,Llama 3.3 70B Instruct"

# 自定义序列长度
python3 scripts/run_pipeline.py --sequences "1K / 1K,1K / 8K"

# 仅采集不做转换/合并
python3 scripts/run_pipeline.py --scrape-only

# 仅转换合并（已有 JSON 的情况下）
python3 scripts/run_pipeline.py --convert-only

# 指定请求超时时间
python3 scripts/run_pipeline.py --timeout 180
```

## 📁 目录结构

```
inferencex-scraper/
├── README.md                      # 本说明文件
├── SKILL.md                       # Claude Code Skill 描述文件
└── scripts/
    ├── scrape_inferencex.py       # 步骤 1: API 数据采集
    ├── convert_to_csv.py          # 步骤 2: JSON → CSV 转换
    ├── merge_csv.py               # 步骤 3: CSV 合并
    └── run_pipeline.py            # 一键全流程脚本
```

## 📊 默认采集的模型

| 模型名称 | 说明 |
|---------|------|
| Llama 3.3 70B Instruct | Meta Llama 3.3 70B 指令微调版 |
| gpt-oss 120B | 开源 GPT 120B 参数模型 |
| DeepSeek R1 0528 | DeepSeek R1 推理模型 |
| Kimi K2.5 | 月之暗面 Kimi K2.5 |
| MiniMax M2.5 | MiniMax M2.5 模型 |
| Qwen 3.5 397B-A17B | 通义千问 3.5 MoE 模型 |

每个模型采集 3 种序列长度配置：`1K/1K`、`1K/8K`、`8K/1K`，每种配置采集 `e2e` 和 `interactivity` 两类数据。

## 📄 输出文件说明

### 原始 JSON

存放于 `json_data/raw_json_files/`，命名格式：
```
{序号}_{模型名}_{序列}_{类型}.json
例如: 01_DeepSeek_R1_0528_1K_____1K_e2e.json
```

### CSV 文件

| 文件 | 说明 | 列数 |
|------|------|------|
| `inference_max_e2e.csv` | E2E 端到端性能数据 | ~40-60 |
| `inference_max_interactivity.csv` | 交互性能数据 | ~40-60 |
| `inference_max_merged.csv` | 合并数据集（最终输出） | ~80+ |

### 合并 CSV 核心列说明

| 维度 | 核心列 | 说明 |
|------|--------|------|
| **基础信息** | `model_name`, `sequence_length`, `date`, `framework`, `image` | 模型/环境/版本 |
| **硬件拓扑** | `hw`, `hwKey`, `tp`, `ep`, `dp_attention`, `is_multinode` | GPU 硬件与并行配置 |
| **并发设置** | `conc`, `isl`, `osl` | 并发数与序列长度 |
| **延迟指标** | `mean_ttft`, `p99_tpot`, `mean_e2el`, `mean_itl` 等 | 首字/词间/端到端延迟统计 |
| **吞吐指标** | `tput_per_gpu`, `input_tput_per_gpu`, `output_tput_per_gpu` | 每 GPU 吞吐量 |
| **成本分析** | `costh_y`, `costn_y`, `costr_y` 及 `_roof`/`Output` 变体 | 多口径成本推算 |
| **图表坐标** | `e2e_x`, `e2e_y`, `inter_x`, `inter_y` | 前端可视化坐标 |

### 关于空白字段

部分记录的某些列为空白，这是 **正常现象**，不是代码 Bug：

- API 返回的数据字段是 **动态长度** 的 — 不同硬件/并发压力下测量的指标集不完全相同
- 例如低并发测试可能包含完整的 50+ 个字段，而高并发极限压测场景下 API 只返回核心吞吐量 + 成本
- CSV 展平时以 **所有记录中出现过的字段的并集** 作为列头，缺失的字段留空

## 🔧 技术细节

### 数据源

- **API 入口**: Vercel Blob Storage (`yig6saydz8oscerh.public.blob.vercel-storage.com`)
- **索引文件**: `availability.json` — 包含所有可用的模型/序列 key 及其日期列表
- **数据文件**: `/{date}/{availability-key}-{e2e|interactivity}.json`

### 关键设计决策

1. **`subprocess + curl`** 替代 `requests` — 解决 Vercel Blob Storage 在部分 Linux 环境下的 SSL 握手挂起问题
2. **自动展平嵌套 JSON** — `{costh: {y: 1.2, roof: true}}` → `costh_y: 1.2`, `costh_roof: true`
3. **基于复合键的 CSV JOIN** — 使用 `model_name + sequence_length + conc + hwKey + precision + tp` 六个键字段精准匹配
4. **无外部依赖** — 仅使用 Python 标准库（`json`, `csv`, `subprocess`, `re`, `os`, `glob`, `logging`, `argparse`）+ 系统 `curl`

### 数据流拓扑

```
Vercel Blob Storage
       │
       ▼
availability.json ──── 发现可用的 model/sequence/date 组合
       │
       ▼
/{date}/{key}-e2e.json ─────────┐
/{date}/{key}-interactivity.json │
       │                        │
       ▼                        ▼
  raw_json_files/          raw_json_files/
  *_e2e.json               *_interactivity.json
       │                        │
       ▼                        ▼
  展平嵌套 + 提取所有字段    展平嵌套 + 提取所有字段
       │                        │
       ▼                        ▼
  inference_max_e2e.csv    inference_max_interactivity.csv
       │                        │
       └────── JOIN ON ─────────┘
         (6-field composite key)
                 │
                 ▼
      inference_max_merged.csv
```

## 🤖 作为 Claude Code Skill 使用

本工具同时是一个 Claude Code Skill，可以通过自然语言调用：

> "帮我采集最新的 InferenceX 推理性能数据"
> "更新 InferenceX 基准数据并生成合并 CSV"
> "只采集 DeepSeek R1 和 Kimi K2.5 的数据"

Claude Code 会自动读取 `SKILL.md` 中的工作流说明并执行相应步骤。

## ❓ 常见问题

### Q: curl 超时怎么办？
A: Vercel Blob Storage 响应较慢，默认超时已设为 120 秒。可通过 `--timeout 180` 增大。

### Q: 如何添加新模型？
A: 通过 `--models` 参数指定，或修改 `scrape_inferencex.py` 中的 `DEFAULT_MODELS` 列表。新模型必须在 `availability.json` 中存在对应的 key。

### Q: 为什么某些模型采集失败？
A: 常见原因：
1. 模型名称在 `availability.json` 中的格式与传入的不一致（如 "Kimi K2.5" vs "Kimi K2.5 1T"）
2. 该模型+序列组合确实没有数据

### Q: 数据会覆盖吗？
A: 每次运行会覆盖 `raw_json_files/` 和 CSV 文件。如需保留历史版本，请使用主 pipeline 的版本归档功能。

## 📜 License

MIT
