---
name: InferenceX Data Scraper
description: 从 SemiAnalysis InferenceX 平台自动采集 LLM 推理性能基准数据，转换为结构化 CSV。
---

# InferenceX Data Scraper Skill (v3)

从 SemiAnalysis InferenceX (原 InferenceMAX) 平台的 API v1 自动采集 LLM 推理性能基准数据（TTFT、ITL、E2E 延迟、吞吐量、硬件配置等），并将 API 返回的综合 JSON 指标展平为结构化 CSV。

## 工作流程

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│ 1. API 采集      │ ──▶ │ 2. JSON → CSV   │ ──▶ │ 3. 输出结果      │
│  (API v1 REST)  │     │  (全指标展平)    │     │ (merged.csv)    │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

## 详细指令

### 1. 执行全流程采集 (推荐)

一键完成所有模型的最新数据采集与处理。

// turbo
```bash
cd /root/semi-bench && python3 /root/.gemini/antigravity/skills/inferencex-scraper/scripts/run_pipeline.py --output-base json_data
```

### 2. 自定义参数调用

可以根据需要指定特定的模型或日期。

**指定模型 ID**:
- `llama70b`, `dsr1`, `kimik2.5`, `minimaxm2.5`, `qwen3.5`, `glm5`

**指定序列长度**:
- "1K / 1K", "1K / 8K", "8K / 1K"

**示例: 采集 DeepSeek R1 的历史数据**
// turbo
```bash
cd /root/semi-bench && python3 /root/.gemini/antigravity/skills/inferencex-scraper/scripts/run_pipeline.py --models "dsr1" --date "2026-03-07"
```

## 默认采集配置

- **目标 API**: `https://inferencex.semianalysis.com/api/v1`
- **默认模型**: Llama 3.3 70B, DeepSeek R1, Kimi K2.5, MiniMax M2.5, Qwen 3.5, GLM-5
- **默认序列**: 1024/1024, 1024/8192, 8192/1024

## 脚本组件说明

1. **`scrape_inferencex.py`**: 利用 `/api/v1/availability` 和 `/api/v1/benchmarks` 接口获取数据。使用 `curl` 保证连接稳定性。
2. **`convert_to_csv.py`**: 将 `metrics` 下的所有嵌套字段（如 `p99_ttft`）提取并映射为 CSV 的扁平列。
3. **`merge_csv.py`**: 最终产出文件处理，并提供旧版 E2E/Interactivity 数据的向后兼容支持。
4. **`run_pipeline.py`**: 全流程调度。

## 依赖
- Python 3.8+
- 系统 `curl` 工具

## 输出位置
- 原始 JSON: `{output-base}/raw_json_files/`
- 最终 CSV: `{output-base}/inference_max_merged.csv`
