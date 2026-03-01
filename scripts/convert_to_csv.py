#!/usr/bin/env python3
"""
JSON → CSV 转换脚本 - 将采集到的 InferenceX 原始 JSON 文件按 E2E 和 Interactivity 两类
分别转换为 CSV 文件。

核心功能:
  1. 自动识别 JSON 文件类型（根据 URL 中的 e2e.json 或 interactivity.json）
  2. 扫描所有记录字段，自动展平嵌套字典（如 costh: {y: 1.2, roof: true} → costh_y, costh_roof）
  3. 输出两个分离的 CSV 文件
"""

import json
import os
import glob
import csv
import re
import argparse
from datetime import datetime


def normalize_sequence_format(sequence_str):
    """将序列格式标准化为 1k-1k, 1k-8k 等格式"""
    normalized = sequence_str.replace(' ', '').lower()
    normalized = normalized.replace('/', '-')
    return normalized


def categorize_json_file(filepath):
    """根据URL判断JSON文件类型"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        url = data.get('metadata', {}).get('url', '')

        if 'interactivity.json' in url:
            return 'interactivity'
        elif 'e2e.json' in url:
            return 'e2e'
        else:
            # 也尝试通过文件名判断
            basename = os.path.basename(filepath).lower()
            if 'interactivity' in basename:
                return 'interactivity'
            elif 'e2e' in basename:
                return 'e2e'
            print(f"⚠️  Warning: Unknown file type for {filepath}")
            return None

    except Exception as e:
        print(f"Error categorizing {filepath}: {e}")
        return None


def extract_all_fields(json_files):
    """提取所有可能的字段名"""
    all_fields = set()
    all_nested_fields = {}

    for filepath in json_files:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            data_points = data.get('data', [])
            for point in data_points:
                if isinstance(point, dict):
                    for key, value in point.items():
                        if isinstance(value, dict):
                            for nested_key in value.keys():
                                all_nested_fields[key] = all_nested_fields.get(key, set())
                                all_nested_fields[key].add(nested_key)
                        else:
                            all_fields.add(key)
        except Exception as e:
            print(f"Error extracting fields from {filepath}: {e}")

    # 将嵌套字段转换为扁平字段名
    flat_fields = set(all_fields)
    for parent_key, nested_keys in all_nested_fields.items():
        for nested_key in nested_keys:
            flat_fields.add(f"{parent_key}_{nested_key}")

    return sorted(list(flat_fields))


def flatten_data_point(data_point):
    """将嵌套的数据点扁平化"""
    flattened = {}

    for key, value in data_point.items():
        if isinstance(value, dict):
            for nested_key, nested_value in value.items():
                flattened[f"{key}_{nested_key}"] = nested_value
        else:
            flattened[key] = value

    return flattened


def process_json_files_by_type(directory):
    """按类型处理JSON文件"""
    # 查找所有JSON文件（排除报告文件）
    json_files = glob.glob(os.path.join(directory, '*.json'))
    json_files = [f for f in json_files if not any(x in os.path.basename(f).lower()
                                               for x in ['readme', 'summary', 'cleanup', 'report'])]

    print(f"📊 Found {len(json_files)} JSON files to process")

    if not json_files:
        print("❌ No JSON files found!")
        return None, None

    # 按类型分类文件
    interactivity_files = []
    e2e_files = []

    print("🔍 Categorizing files by type...")
    for filepath in json_files:
        file_type = categorize_json_file(filepath)
        if file_type == 'interactivity':
            interactivity_files.append(filepath)
        elif file_type == 'e2e':
            e2e_files.append(filepath)

    print(f"📋 Interactivity files: {len(interactivity_files)}")
    print(f"📋 E2E files: {len(e2e_files)}")

    if len(interactivity_files) != len(e2e_files):
        print(f"⚠️  Warning: Different number of files - Interactivity: {len(interactivity_files)}, E2E: {len(e2e_files)}")

    return interactivity_files, e2e_files


def convert_files_to_csv(files, file_type, output_file):
    """将指定类型的文件转换为CSV"""
    if not files:
        print(f"❌ No {file_type} files to process")
        return None

    print(f"\n🔄 Processing {file_type} files...")

    # 提取所有可能的字段
    print("🔍 Analyzing data structure...")
    all_fields = extract_all_fields(files)
    print(f"📋 Found {len(all_fields)} unique data fields for {file_type}")

    # 定义CSV列的顺序
    csv_columns = ['model_name', 'sequence_length'] + all_fields

    # 准备CSV数据
    csv_data = []
    total_records = 0

    for i, filepath in enumerate(files):
        filename = os.path.basename(filepath)
        print(f"  📄 Processing {i+1}/{len(files)}: {filename}")

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                json_data = json.load(f)

            # 提取元数据
            metadata = json_data.get('metadata', {})
            model_name = metadata.get('model', 'Unknown')
            sequence_length = normalize_sequence_format(metadata.get('sequence', 'Unknown'))

            # 处理数据点
            data_points = json_data.get('data', [])
            file_records = 0

            for data_point in data_points:
                if isinstance(data_point, dict):
                    # 扁平化数据点
                    flattened_point = flatten_data_point(data_point)

                    # 创建CSV行
                    csv_row = {}

                    # 添加模型和序列列
                    csv_row['model_name'] = model_name
                    csv_row['sequence_length'] = sequence_length

                    # 添加所有数据字段
                    for field in all_fields:
                        csv_row[field] = flattened_point.get(field, '')

                    csv_data.append(csv_row)
                    file_records += 1

            total_records += file_records
            print(f"    ✅ Extracted {file_records} data points")

        except Exception as e:
            print(f"    ❌ Error processing {filename}: {e}")

    print(f"📊 Total {file_type} records extracted: {total_records}")

    # 保存CSV文件
    if save_csv_file(csv_columns, csv_data, output_file):
        return {
            'columns': csv_columns,
            'data': csv_data,
            'total_records': total_records,
            'file_count': len(files)
        }
    else:
        return None


def save_csv_file(csv_columns, csv_data, output_file):
    """保存CSV文件"""
    try:
        os.makedirs(os.path.dirname(output_file) if os.path.dirname(output_file) else '.', exist_ok=True)
        with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=csv_columns)
            writer.writeheader()
            writer.writerows(csv_data)

        print(f"✅ CSV file saved: {output_file}")
        return True

    except Exception as e:
        print(f"❌ Error saving CSV file: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description='将 InferenceX JSON 数据转换为分类 CSV 文件'
    )
    parser.add_argument(
        '--input-dir', '-i',
        default='json_data/raw_json_files',
        help='输入 JSON 文件目录 (默认: json_data/raw_json_files)'
    )
    parser.add_argument(
        '--output-dir', '-o',
        default='json_data',
        help='输出 CSV 文件目录 (默认: json_data)'
    )

    args = parser.parse_args()

    input_directory = args.input_dir
    interactivity_output = os.path.join(args.output_dir, 'inference_max_interactivity.csv')
    e2e_output = os.path.join(args.output_dir, 'inference_max_e2e.csv')

    if not os.path.exists(input_directory):
        print(f"❌ Input directory {input_directory} does not exist")
        return

    print("🚀 Starting separated JSON to CSV conversion...")

    # 按类型分类文件
    interactivity_files, e2e_files = process_json_files_by_type(input_directory)

    if not interactivity_files and not e2e_files:
        print("❌ No valid files found")
        return

    # 转换 interactivity 文件
    interactivity_result = None
    if interactivity_files:
        print(f"\n📊 Converting Interactivity files...")
        interactivity_result = convert_files_to_csv(interactivity_files, 'interactivity', interactivity_output)

    # 转换 e2e 文件
    e2e_result = None
    if e2e_files:
        print(f"\n📊 Converting E2E files...")
        e2e_result = convert_files_to_csv(e2e_files, 'e2e', e2e_output)

    if not interactivity_result and not e2e_result:
        print("❌ No data was converted")
        return

    # 显示转换结果
    print(f"\n🎉 Separated conversion completed successfully!")

    if interactivity_result:
        file_size = os.path.getsize(interactivity_output)
        print(f"📄 Interactivity CSV: {interactivity_output}")
        print(f"📊 Size: {file_size:,} bytes ({file_size/1024/1024:.2f} MB)")
        print(f"📈 Records: {interactivity_result['total_records']:,}")

    if e2e_result:
        file_size = os.path.getsize(e2e_output)
        print(f"📄 E2E CSV: {e2e_output}")
        print(f"📊 Size: {file_size:,} bytes ({file_size/1024/1024:.2f} MB)")
        print(f"📈 Records: {e2e_result['total_records']:,}")

    total_records = (interactivity_result['total_records'] if interactivity_result else 0) + \
                   (e2e_result['total_records'] if e2e_result else 0)
    print(f"📊 Total records across both files: {total_records:,}")


if __name__ == "__main__":
    main()
