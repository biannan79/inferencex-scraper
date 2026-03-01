#!/usr/bin/env python3
"""
CSV 合并脚本 - 将 E2E 和 Interactivity 两个 CSV 文件基于复合键 JOIN 合并

Join 键: model_name, sequence_length, conc, hwKey, precision, tp
合并后新增列: e2e_x, e2e_y, inter_x, inter_y
"""

import csv
import os
import argparse
from collections import defaultdict
from datetime import datetime


def read_csv_file(filepath):
    """读取CSV文件并返回字典数据"""
    data = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                data.append(row)
        return data
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return []


def create_key_index(data, key_fields):
    """基于指定键字段创建索引"""
    index = defaultdict(list)

    for row in data:
        key_parts = []
        for field in key_fields:
            key_parts.append(row.get(field, ''))

        key = '|'.join(key_parts)
        index[key].append(row)

    return index


def join_csv_files(e2e_data, interactivity_data, key_fields):
    """执行基于多键的join操作"""
    print(f"🔄 Creating index for E2E data...")
    e2e_index = create_key_index(e2e_data, key_fields)

    print(f"🔄 Creating index for Interactivity data...")
    interactivity_index = create_key_index(interactivity_data, key_fields)

    print(f"📊 E2E unique keys: {len(e2e_index)}")
    print(f"📊 Interactivity unique keys: {len(interactivity_index)}")

    # 执行join操作
    joined_data = []
    matched_keys = 0
    e2e_only_keys = 0
    inter_only_keys = 0

    # 首先处理E2E数据作为基础
    for key, e2e_rows in e2e_index.items():
        if key in interactivity_index:
            # 找到匹配的记录
            inter_rows = interactivity_index[key]

            for e2e_row in e2e_rows:
                for inter_row in inter_rows:
                    # 创建合并后的行
                    joined_row = e2e_row.copy()

                    # 重命名E2E的x和y字段
                    if 'x' in e2e_row:
                        joined_row['e2e_x'] = e2e_row['x']
                        del joined_row['x']

                    if 'y' in e2e_row:
                        joined_row['e2e_y'] = e2e_row['y']
                        del joined_row['y']

                    # 添加Interactivity的x和y字段
                    if 'x' in inter_row:
                        joined_row['inter_x'] = inter_row['x']

                    if 'y' in inter_row:
                        joined_row['inter_y'] = inter_row['y']

                    joined_data.append(joined_row)

            matched_keys += 1
        else:
            # E2E独有的记录
            for e2e_row in e2e_rows:
                joined_row = e2e_row.copy()

                if 'x' in e2e_row:
                    joined_row['e2e_x'] = e2e_row['x']
                    del joined_row['x']

                if 'y' in e2e_row:
                    joined_row['e2e_y'] = e2e_row['y']
                    del joined_row['y']

                joined_row['inter_x'] = ''
                joined_row['inter_y'] = ''

                joined_data.append(joined_row)

            e2e_only_keys += 1

    # 处理Interactivity独有的记录
    for key, inter_rows in interactivity_index.items():
        if key not in e2e_index:
            for inter_row in inter_rows:
                joined_row = {}

                for field in inter_row:
                    if field in ['x', 'y']:
                        continue
                    joined_row[field] = inter_row[field]

                joined_row['e2e_x'] = ''
                joined_row['e2e_y'] = ''

                if 'x' in inter_row:
                    joined_row['inter_x'] = inter_row['x']

                if 'y' in inter_row:
                    joined_row['inter_y'] = inter_row['y']

                joined_data.append(joined_row)

            inter_only_keys += 1

    print(f"✅ Matched keys: {matched_keys}")
    print(f"⚠️  E2E only keys: {e2e_only_keys}")
    print(f"⚠️  Interactivity only keys: {inter_only_keys}")
    print(f"📊 Total joined records: {len(joined_data)}")

    return joined_data, {
        'matched_keys': matched_keys,
        'e2e_only_keys': e2e_only_keys,
        'inter_only_keys': inter_only_keys,
        'total_records': len(joined_data)
    }


def define_output_columns(base_columns):
    """定义输出列的顺序"""
    exclude_columns = ['x', 'y']
    base_cols = [col for col in base_columns if col not in exclude_columns]

    new_columns = ['e2e_x', 'e2e_y', 'inter_x', 'inter_y']

    return base_cols + new_columns


def save_joined_csv(data, columns, output_file):
    """保存合并后的CSV文件"""
    try:
        os.makedirs(os.path.dirname(output_file) if os.path.dirname(output_file) else '.', exist_ok=True)
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=columns)
            writer.writeheader()
            writer.writerows(data)

        print(f"✅ Joined CSV saved: {output_file}")
        return True
    except Exception as e:
        print(f"❌ Error saving joined CSV: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description='合并 InferenceX E2E 和 Interactivity CSV 文件'
    )
    parser.add_argument(
        '--input-dir', '-i',
        default='json_data',
        help='输入 CSV 文件目录 (默认: json_data)'
    )
    parser.add_argument(
        '--output-dir', '-o',
        default='json_data',
        help='输出合并 CSV 文件目录 (默认: json_data)'
    )

    args = parser.parse_args()

    e2e_file = os.path.join(args.input_dir, 'inference_max_e2e.csv')
    interactivity_file = os.path.join(args.input_dir, 'inference_max_interactivity.csv')
    output_file = os.path.join(args.output_dir, 'inference_max_merged.csv')

    # 定义join的键字段
    key_fields = ['model_name', 'sequence_length', 'conc', 'hwKey', 'precision', 'tp']

    print("🚀 Starting CSV file merge operation...")

    # 检查输入文件
    if not os.path.exists(e2e_file):
        print(f"❌ E2E file not found: {e2e_file}")
        return

    if not os.path.exists(interactivity_file):
        print(f"❌ Interactivity file not found: {interactivity_file}")
        return

    # 读取CSV文件
    print(f"📖 Reading E2E file: {e2e_file}")
    e2e_data = read_csv_file(e2e_file)
    print(f"   Loaded {len(e2e_data)} records")

    print(f"📖 Reading Interactivity file: {interactivity_file}")
    interactivity_data = read_csv_file(interactivity_file)
    print(f"   Loaded {len(interactivity_data)} records")

    # 执行join操作
    print(f"\n🔄 Joining files on keys: {', '.join(key_fields)}")
    joined_data, stats = join_csv_files(e2e_data, interactivity_data, key_fields)

    if not joined_data:
        print("❌ No data to save")
        return

    # 定义输出列
    base_columns = e2e_data[0].keys() if e2e_data else []
    output_columns = define_output_columns(base_columns)

    print(f"📋 Output columns: {len(output_columns)}")

    # 保存合并后的文件
    if save_joined_csv(joined_data, output_columns, output_file):
        file_size = os.path.getsize(output_file)
        print(f"\n🎉 CSV merge completed successfully!")
        print(f"📄 Output file: {output_file}")
        print(f"📊 File size: {file_size:,} bytes ({file_size/1024/1024:.2f} MB)")
        print(f"📈 Total records: {len(joined_data):,}")
        print(f"📋 Columns: {len(output_columns)}")

        total_keys = stats['matched_keys'] + stats['e2e_only_keys'] + stats['inter_only_keys']
        if total_keys > 0:
            print(f"📊 Match rate: {(stats['matched_keys'] / total_keys * 100):.1f}%")


if __name__ == "__main__":
    main()
