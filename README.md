# InferenceX Data Scraper v3

从 [SemiAnalysis InferenceX](https://inferencex.semianalysis.com/) 平台自动采集 LLM 推理性能基准数据，转换为结构化 CSV 并输出。

## ✨ 功能特性

- 🔄 **全自动采集** — 使用新的 InferenceX API v1 (`/api/v1/benchmarks`) 获取最新数据
- 📊 **指标丰富** — 包含 TTFT, ITL, TPOT, E2E Latency, Throughput per GPU 等 20+ 项核心指标
- 📉 **展平结构** — 自动将嵌套的 `metrics` 字典展平为 CSV 列
- 🛠️ **一键执行** — 提供全自动化脚本，完成从下载到 CSV 生成的全流程
- 🛡️ **稳定性** — 使用 `subprocess + curl` 绕过 Python SSL 挂起问题，支持大并发数据包

## 📋 工作流程

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│ 1. API 采集      │ ──▶ │ 2. JSON → CSV   │ ──▶ │ 3. 输出结果      │
│  (API v1 REST)  │     │  (指标字典展平)   │     │ (benchmarks.csv)│
└─────────────────┘     └─────────────────┘     └─────────────────┘
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

# 步骤 2: 将 JSON 转换为综合 CSV
python3 scripts/convert_to_csv.py --input-dir json_data/raw_json_files --output-dir json_data

# 步骤 3: 归档/重命名最终数据 (可选)
python3 scripts/merge_csv.py --input-dir json_data --output json_data/inference_max_merged.csv
```

### 自定义选项

```bash
# 指定模型列表
python3 scripts/run_pipeline.py --models "llama70b,dsr1,qwen3.5"

# 采集历史特定日期的数据
python3 scripts/run_pipeline.py --date 2025-10-29

# 指定自定义序列长度
python3 scripts/run_pipeline.py --sequences "1K / 1K,1K / 8K,8K / 1K"
```

## 📁 目录结构

```
inferencex-scraper/
├── README.md                      # 本说明文件
├── SKILL.md                       # Claude Code Skill 描述文件
└── scripts/
    ├── scrape_inferencex.py       # 步骤 1: API 数据采集 (支持 API v1)
    ├── convert_to_csv.py          # 步骤 2: JSON → CSV 转换 (指标展平)
    ├── merge_csv.py               # 步骤 3: 最终文件处理与兼容性层
    └── run_pipeline.py            # 一键全流程编排脚本
```

## 📊 采集模型支持 (部分列举)

| 模型 ID | 对应模型名称 |
|---------|-------------|
| `llama70b` | Llama-3.3-70B-Instruct-FP8 |
| `dsr1` | DeepSeek-R1-0528 |
| `kimik2.5` | Kimi-K2.5 |
| `minimaxm2.5` | MiniMax-M2.5 |
| `qwen3.5` | Qwen-3.5-397B-A17B |
| `glm5` | GLM-5 |

## 📄 输出数据说明

### 核心指标列 (扁平化后)

| 列名 | 说明 |
|------|------|
| `metrics_p99_ttft` | 首字延迟 (Time to First Token) P99 |
| `metrics_mean_itl` | 平均词间延迟 (Inter-Token Latency) |
| `metrics_tput_per_gpu` | 每 GPU 总吞吐量 (tokens/s) |
| `metrics_p99_e2el` | 端到端总延迟 (End-to-End Latency) P99 |
| `metrics_p99_tpot` | 每输出字延迟 (Time Per Output Token) P99 |

### 技术背景

InferenceX 在 v3 版本后弃用了原有的 Vercel Blob Storage 静态 JSON 文件存储方式，转而使用更加集成的 API 接口。新接口一个 API 请求即可返回对应模型在该日期的 **全量指标数据**（不再区分 e2e 和 interactivity 两个文件），大大提高了采集效率。

## 🤖 作为 Claude Code Skill 使用

通过 Claude Code 的命令行环境，你可以直接呼唤：

> "采集最新的 InferenceX 跑分数据并整理成 CSV"
> "帮我看看 DeepSeek R1 在 H200 上的最新表现"

## 📜 License

MIT
