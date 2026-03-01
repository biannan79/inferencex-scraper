#!/usr/bin/env python3
"""
InferenceX 一键全流程脚本 - 采集 → 转换 → 合并

依次执行：
  1. scrape_inferencex.py — 从 Vercel Blob Storage 采集 JSON 数据
  2. convert_to_csv.py   — 将 JSON 按类型转换为 E2E 和 Interactivity CSV
  3. merge_csv.py         — 合并两个 CSV 为最终的 merged.csv
"""

import os
import sys
import time
import argparse
from datetime import datetime

# 确保能导入同目录下的模块
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from scrape_inferencex import scrape_api_data, DEFAULT_MODELS, DEFAULT_SEQUENCES
from convert_to_csv import process_json_files_by_type, convert_files_to_csv
from merge_csv import read_csv_file, join_csv_files, define_output_columns, save_joined_csv


def run_pipeline(models=None, sequences=None, output_base='json_data',
                 scrape_only=False, convert_only=False, timeout=120):
    """
    执行完整的数据采集和处理管道

    Args:
        models: 模型列表（None 则使用默认）
        sequences: 序列列表（None 则使用默认）
        output_base: 输出根目录
        scrape_only: 仅执行采集步骤
        convert_only: 仅执行转换和合并步骤
        timeout: 请求超时时间
    """
    models = models or DEFAULT_MODELS
    sequences = sequences or DEFAULT_SEQUENCES

    raw_dir = os.path.join(output_base, 'raw_json_files')
    e2e_csv = os.path.join(output_base, 'inference_max_e2e.csv')
    inter_csv = os.path.join(output_base, 'inference_max_interactivity.csv')
    merged_csv = os.path.join(output_base, 'inference_max_merged.csv')

    pipeline_start = time.time()
    print("=" * 80)
    print(f"🚀 InferenceX Data Pipeline - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    print(f"📋 Models: {len(models)}")
    print(f"📋 Sequences: {len(sequences)}")
    print(f"📁 Output base: {output_base}")
    print()

    # ─── 步骤 1: 数据采集 ───────────────────────────────────────────────────
    if not convert_only:
        print("━" * 80)
        print("📥 STEP 1/3: Data Collection")
        print("━" * 80)

        step_start = time.time()
        scrape_results = scrape_api_data(models, sequences, raw_dir, timeout)
        step_elapsed = time.time() - step_start

        total_files = scrape_results.get('total_files', 0)
        total_records = scrape_results.get('total_records', 0)

        print(f"\n⏱️  Step 1 took {step_elapsed:.1f}s — {total_files} files, {total_records} records")

        if total_files == 0:
            print("❌ No data collected, aborting pipeline!")
            return False

        if scrape_only:
            print(f"\n🏁 Scrape-only mode — pipeline complete ({step_elapsed:.1f}s)")
            return True

    # ─── 步骤 2: JSON → CSV 转换 ─────────────────────────────────────────────
    print("\n" + "━" * 80)
    print("📄 STEP 2/3: JSON → CSV Conversion")
    print("━" * 80)

    step_start = time.time()

    interactivity_files, e2e_files = process_json_files_by_type(raw_dir)

    interactivity_result = None
    if interactivity_files:
        interactivity_result = convert_files_to_csv(interactivity_files, 'interactivity', inter_csv)

    e2e_result = None
    if e2e_files:
        e2e_result = convert_files_to_csv(e2e_files, 'e2e', e2e_csv)

    step_elapsed = time.time() - step_start

    if not interactivity_result and not e2e_result:
        print("❌ No data was converted, aborting pipeline!")
        return False

    inter_records = interactivity_result['total_records'] if interactivity_result else 0
    e2e_records = e2e_result['total_records'] if e2e_result else 0
    print(f"\n⏱️  Step 2 took {step_elapsed:.1f}s — E2E: {e2e_records} records, Inter: {inter_records} records")

    # ─── 步骤 3: CSV 合并 ─────────────────────────────────────────────────────
    print("\n" + "━" * 80)
    print("🔗 STEP 3/3: CSV Merge (E2E + Interactivity)")
    print("━" * 80)

    step_start = time.time()

    if not os.path.exists(e2e_csv) or not os.path.exists(inter_csv):
        print("❌ One or both CSV files missing, skipping merge")
        return False

    e2e_data = read_csv_file(e2e_csv)
    interactivity_data = read_csv_file(inter_csv)

    key_fields = ['model_name', 'sequence_length', 'conc', 'hwKey', 'precision', 'tp']
    joined_data, stats = join_csv_files(e2e_data, interactivity_data, key_fields)

    if joined_data:
        base_columns = e2e_data[0].keys() if e2e_data else []
        output_columns = define_output_columns(base_columns)
        save_joined_csv(joined_data, output_columns, merged_csv)

    step_elapsed = time.time() - step_start
    print(f"\n⏱️  Step 3 took {step_elapsed:.1f}s — {len(joined_data)} merged records")

    # ─── 总结 ────────────────────────────────────────────────────────────────
    total_elapsed = time.time() - pipeline_start
    print("\n" + "=" * 80)
    print(f"🎉 Pipeline Complete! Total time: {total_elapsed:.1f}s")
    print("=" * 80)
    print(f"📄 E2E CSV:          {e2e_csv}")
    print(f"📄 Interactivity CSV: {inter_csv}")
    print(f"📄 Merged CSV:       {merged_csv}")

    if os.path.exists(merged_csv):
        file_size = os.path.getsize(merged_csv)
        print(f"📊 Merged size:      {file_size:,} bytes ({file_size/1024/1024:.2f} MB)")

    print(f"📈 Total records:    {len(joined_data):,}")

    return True


def main():
    parser = argparse.ArgumentParser(
        description='InferenceX 一键数据采集与处理管道'
    )
    parser.add_argument(
        '--output-base', '-o',
        default='json_data',
        help='输出根目录 (默认: json_data)'
    )
    parser.add_argument(
        '--models', '-m',
        default=None,
        help='逗号分隔的模型列表'
    )
    parser.add_argument(
        '--sequences', '-s',
        default=None,
        help='逗号分隔的序列列表'
    )
    parser.add_argument(
        '--scrape-only',
        action='store_true',
        help='仅执行采集步骤'
    )
    parser.add_argument(
        '--convert-only',
        action='store_true',
        help='仅执行转换和合并步骤（跳过采集）'
    )
    parser.add_argument(
        '--timeout', '-t',
        type=int, default=120,
        help='请求超时时间（秒）'
    )

    args = parser.parse_args()

    models = [m.strip() for m in args.models.split(',')] if args.models else None
    sequences = [s.strip() for s in args.sequences.split(',')] if args.sequences else None

    success = run_pipeline(
        models=models,
        sequences=sequences,
        output_base=args.output_base,
        scrape_only=args.scrape_only,
        convert_only=args.convert_only,
        timeout=args.timeout,
    )

    exit(0 if success else 1)


if __name__ == "__main__":
    main()
