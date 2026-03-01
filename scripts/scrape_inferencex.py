#!/usr/bin/env python3
"""
InferenceX 数据采集脚本 - 从 Vercel Blob Storage 采集 LLM 推理性能基准数据

使用 subprocess + curl 作为 HTTP 客户端（避免 Python requests 库在某些环境中
对 Vercel Blob Storage 的 SSL 连接存在挂起问题）。

数据流程:
  1. 从 availability.json 获取可用的模型/日期索引
  2. 为每个模型+序列组合找到匹配的 availability key
  3. 获取最新日期的 e2e 和 interactivity 数据
  4. 展平嵌套结构（{data: [...], gpus: [...]} → flat records）
  5. 保存为标准化的 JSON 文件
"""

import subprocess
import json
import time
import os
import re
import argparse
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Set
import logging

logger = logging.getLogger(__name__)

# ─── 默认模型和序列配置 ───────────────────────────────────────────────────────
DEFAULT_MODELS = [
    "Llama 3.3 70B Instruct",
    "gpt-oss 120B",
    "DeepSeek R1 0528",
    "Kimi K2.5",
    "MiniMax M2.5",
    "Qwen 3.5 397B-A17B",
]

DEFAULT_SEQUENCES = ["1K / 1K", "1K / 8K", "8K / 1K"]

BLOB_STORAGE_BASE_URL = (
    "https://yig6saydz8oscerh.public.blob.vercel-storage.com/historical-data-prod-v9"
)


# ─── 工具函数 ─────────────────────────────────────────────────────────────────

def curl_fetch(url: str, timeout: int = 120) -> Tuple[Optional[str], int]:
    """
    使用 curl 获取 URL 内容（避免 Python requests SSL 挂起问题）

    Returns:
        (response_body, http_status_code)
    """
    try:
        result = subprocess.run(
            ['curl', '-sL', '--max-time', str(timeout),
             '-w', '\n__HTTP_CODE__%{http_code}',
             '-H', 'User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
             '-H', 'Accept: application/json',
             url],
            capture_output=True, text=True, timeout=timeout + 10
        )

        if result.returncode != 0:
            logger.error(f"curl failed with exit code {result.returncode}: {result.stderr}")
            return None, 0

        # 分离响应体和 HTTP 状态码
        output = result.stdout
        if '__HTTP_CODE__' in output:
            parts = output.rsplit('\n__HTTP_CODE__', 1)
            body = parts[0]
            http_code = int(parts[1].strip()) if len(parts) > 1 else 0
        else:
            body = output
            http_code = 200  # 假设成功

        return body, http_code

    except subprocess.TimeoutExpired:
        logger.error(f"curl timeout after {timeout}s for {url}")
        return None, 0
    except Exception as e:
        logger.error(f"curl error for {url}: {e}")
        return None, 0


# ─── 数据采集器 ───────────────────────────────────────────────────────────────

class APIDataCollector:
    """API数据采集器 - 适配新的 Vercel Blob Storage 架构"""

    def __init__(self, base_url: str = BLOB_STORAGE_BASE_URL, timeout: int = 120):
        self.base_url = base_url
        self.timeout = timeout
        self.availability = None  # 缓存 availability 数据

    def fetch_availability(self) -> Dict:
        """获取 availability.json 索引，包含所有可用的模型/日期映射"""
        if self.availability is not None:
            return self.availability

        url = f"{self.base_url}/availability.json"
        logger.info(f"Fetching availability index: {url}")

        body, status = curl_fetch(url, timeout=60)
        if status == 200 and body:
            try:
                self.availability = json.loads(body)
                logger.info(f"Availability index loaded: {len(self.availability)} keys")
                return self.availability
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse availability JSON: {e}")
                return {}
        else:
            logger.error(f"Failed to fetch availability: HTTP {status}")
            return {}

    def normalize_model_name(self, model: str) -> str:
        """标准化模型名称用于匹配 availability key"""
        normalized = model.lower().replace(' ', '-')
        # 处理版本号中的点: 3.3 -> 3_3, 2.5 -> 2_5, 3.5 -> 3_5
        normalized = re.sub(r'(\d+)\.(\d+)', r'\1_\2', normalized)
        return normalized

    def normalize_sequence(self, sequence: str) -> str:
        """标准化序列名称: '1K / 1K' -> '1k_1k'"""
        return sequence.lower().replace(' ', '').replace('/', '_')

    def find_availability_key(self, model: str, sequence: str) -> Optional[str]:
        """
        在 availability.json 中查找匹配的基础 key
        基础 key 是不包含硬件和精度后缀的最短匹配 key
        例如: deepseek-r1-0528-1k_1k (不是 deepseek-r1-0528-1k_1k-fp8-b200_trt)
        """
        availability = self.fetch_availability()
        if not availability:
            return None

        model_id = self.normalize_model_name(model)
        seq_id = self.normalize_sequence(sequence)

        # 策略1: 找以 model_id-seq_id 结尾的 key（最基础的 key）
        candidates = []
        for key in availability.keys():
            key_lower = key.lower()
            # 检查 key 是否以 seq_id 结尾且包含模型名
            if model_id in key_lower and key_lower.endswith(seq_id):
                candidates.append(key)

        if candidates:
            # 选最短的（最基础的 key，没有精度/硬件后缀）
            candidates.sort(key=lambda x: len(x))
            chosen = candidates[0]
            logger.info(f"Found availability key: '{chosen}' for model='{model}', seq='{sequence}'")
            return chosen

        # 策略2: 尝试常见的 key 模式
        possible_keys = [
            f"{model_id}-{seq_id}",
            f"{model_id}-fp8-{seq_id}",
            f"{model_id}-fp4-{seq_id}",
        ]
        for pk in possible_keys:
            if pk in availability:
                logger.info(f"Found availability key (pattern match): '{pk}' for model='{model}', seq='{sequence}'")
                return pk

        # 最后: 列出所有含模型名的 key，帮助调试
        model_keys = [k for k in availability.keys() if model_id in k.lower()]
        if model_keys:
            logger.warning(f"No exact match for model='{model}', seq='{sequence}'. "
                         f"Available keys with this model ({len(model_keys)}): {model_keys[:10]}")
        else:
            logger.warning(f"No availability keys found for model='{model}' (normalized: '{model_id}')")

        return None

    def get_latest_date(self, availability_key: str) -> Optional[str]:
        """获取指定 availability key 的最新日期"""
        availability = self.fetch_availability()
        if not availability or availability_key not in availability:
            return None

        dates = availability[availability_key]
        if not dates:
            return None

        return sorted(dates)[-1]

    def get_all_dates(self, availability_key: str) -> List[str]:
        """获取指定 availability key 的所有可用日期"""
        availability = self.fetch_availability()
        if not availability or availability_key not in availability:
            return []
        return sorted(availability[availability_key])

    def flatten_data(self, raw_data) -> List[Dict]:
        """
        将 API 返回的嵌套数据结构展平为平坦的记录列表。

        新 API 返回格式: [{"data": [...records...], "gpus": [...]}]
        旧 API 返回格式: [...records...] (每个 record 直接含 hwKey, conc 等)
        """
        if not raw_data:
            return []

        flat_records = []

        if isinstance(raw_data, list):
            for item in raw_data:
                if isinstance(item, dict):
                    # 新格式: {"data": [...], "gpus": [...]}
                    if 'data' in item and isinstance(item['data'], list):
                        flat_records.extend(item['data'])
                    # 旧格式: 直接就是 record
                    elif 'hwKey' in item or 'hw' in item:
                        flat_records.append(item)
                    else:
                        # 未知格式，尝试作为记录添加
                        flat_records.append(item)
        elif isinstance(raw_data, dict):
            if 'data' in raw_data and isinstance(raw_data['data'], list):
                flat_records.extend(raw_data['data'])
            else:
                flat_records.append(raw_data)

        return flat_records

    def fetch_data(self, availability_key: str, date: str, data_type: str) -> Tuple[Optional[List], bool, str]:
        """
        获取指定日期和类型的数据，并展平嵌套结构

        Args:
            availability_key: availability.json 中的 key
            date: 日期字符串, 如 '2026-02-25'
            data_type: 'e2e' 或 'interactivity'

        Returns:
            (data, success, url) - data 是展平后的记录列表
        """
        url = f"{self.base_url}/{date}/{availability_key}-{data_type}.json"

        body, status = curl_fetch(url, timeout=self.timeout)

        if status == 200 and body:
            try:
                raw_data = json.loads(body)
                # 展平嵌套结构
                flat_records = self.flatten_data(raw_data)
                if flat_records:
                    return flat_records, True, url
                else:
                    logger.warning(f"No records found after flattening data from {url}")
                    return None, False, url
            except json.JSONDecodeError as e:
                logger.error(f"JSON parse error for {url}: {e}")
                return None, False, url
        else:
            logger.warning(f"HTTP {status} for {url}")
            return None, False, url

    def analyze_data(self, data: List[Dict]) -> Dict:
        """分析数据统计信息"""
        if not data:
            return {
                'record_count': 0,
                'hwkeys': set(),
                'b200_trt_count': 0,
                'has_b200_trt': False,
                'precisions': set(),
            }

        hwkeys = set()
        precisions = set()
        b200_trt_count = 0

        for item in data:
            hwkey = str(item.get('hwKey', ''))
            hwkeys.add(hwkey)
            if 'b200_trt' in hwkey.lower():
                b200_trt_count += 1

            precision = str(item.get('precision', ''))
            if precision:
                precisions.add(precision)

        return {
            'record_count': len(data),
            'hwkeys': hwkeys,
            'b200_trt_count': b200_trt_count,
            'has_b200_trt': b200_trt_count > 0,
            'precisions': precisions,
        }

    def save_json_file(self, data: List[Dict], model: str, sequence: str, data_type: str,
                      output_dir: str, response_index: int = 1,
                      availability_key: str = '', date: str = '', url: str = '') -> str:
        """保存JSON文件"""
        os.makedirs(output_dir, exist_ok=True)

        model_safe = model.replace(' ', '_').replace('.', '_')
        sequence_safe = sequence.replace(' ', '_').replace('/', '___')

        filename = f"{response_index:02d}_{model_safe}_{sequence_safe}_{data_type}.json"
        filepath = os.path.join(output_dir, filename)

        # 分析数据
        analysis = self.analyze_data(data)

        file_data = {
            'metadata': {
                'combination_index': response_index,
                'model': model,
                'sequence': sequence,
                'response_index': response_index,
                'timestamp': datetime.now().isoformat(),
                'request_id': response_index,
                'url': url,
                'availability_key': availability_key,
                'data_date': date,
                'method': 'GET',
                'content_type': 'application/json',
                'data_size': len(json.dumps(data)),
                'data_type': data_type,
                'record_count': analysis['record_count'],
                'b200_trt_count': analysis['b200_trt_count'],
                'hwkeys': sorted(list(analysis['hwkeys'])),
                'precisions': sorted(list(analysis['precisions'])),
            },
            'data': data
        }

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(file_data, f, indent=2, ensure_ascii=False)

        logger.info(f"Saved: {filename} ({analysis['record_count']} records, "
                    f"{analysis['b200_trt_count']} b200_trt, date={date})")
        return filepath

    def collect_all_data(self, models: List[str], sequences: List[str],
                        output_dir: str) -> Dict:
        """采集所有数据"""
        # 首先获取 availability 索引
        print("📥 Fetching availability index...")
        availability = self.fetch_availability()
        if not availability:
            print("❌ Failed to fetch availability index!")
            return {
                'successful_collections': [],
                'failed_collections': [],
                'total_files': 0,
                'total_records': 0,
                'total_b200_trt': 0,
                'model_stats': {},
                'error': 'Failed to fetch availability index'
            }

        print(f"✅ Availability index loaded: {len(availability)} data keys")

        data_types = ["e2e", "interactivity"]
        results = {
            'successful_collections': [],
            'failed_collections': [],
            'total_files': 0,
            'total_records': 0,
            'total_b200_trt': 0,
            'model_stats': {},
            'availability_keys_total': len(availability),
        }

        response_index = 1

        for model in models:
            model_stats = {
                'files': 0,
                'records': 0,
                'b200_trt': 0,
                'hwkeys': set(),
                'successful_combinations': 0,
                'dates_used': set(),
            }

            for sequence in sequences:
                combination_data = {
                    'model': model,
                    'sequence': sequence,
                    'data_types': {},
                    'timestamp': datetime.now().isoformat(),
                }

                # 查找 availability key
                avail_key = self.find_availability_key(model, sequence)
                if not avail_key:
                    print(f"\n❌ No availability key found for {model} + {sequence}")
                    combination_data['data_types'] = {
                        dt: {'success': False, 'error': 'No availability key found'}
                        for dt in data_types
                    }
                    results['failed_collections'].append(combination_data)
                    response_index += 1
                    continue

                # 获取最新日期
                latest_date = self.get_latest_date(avail_key)
                if not latest_date:
                    print(f"\n❌ No dates available for {model} + {sequence} (key: {avail_key})")
                    combination_data['data_types'] = {
                        dt: {'success': False, 'error': 'No dates available'}
                        for dt in data_types
                    }
                    results['failed_collections'].append(combination_data)
                    response_index += 1
                    continue

                combination_data['availability_key'] = avail_key
                combination_data['data_date'] = latest_date
                combination_data['available_dates'] = len(self.get_all_dates(avail_key))

                combination_success = False

                for data_type in data_types:
                    print(f"\n📊 Collecting {model} + {sequence} ({data_type}) [date: {latest_date}]...")

                    data, success, url = self.fetch_data(avail_key, latest_date, data_type)

                    if success and data:
                        try:
                            # 保存文件
                            filepath = self.save_json_file(
                                data, model, sequence, data_type,
                                output_dir, response_index,
                                availability_key=avail_key,
                                date=latest_date, url=url
                            )

                            # 分析数据
                            analysis = self.analyze_data(data)

                            # 更新统计
                            model_stats['files'] += 1
                            model_stats['records'] += analysis['record_count']
                            model_stats['b200_trt'] += analysis['b200_trt_count']
                            model_stats['hwkeys'].update(analysis['hwkeys'])
                            model_stats['dates_used'].add(latest_date)

                            results['total_files'] += 1
                            results['total_records'] += analysis['record_count']
                            results['total_b200_trt'] += analysis['b200_trt_count']

                            combination_data['data_types'][data_type] = {
                                'success': True,
                                'record_count': analysis['record_count'],
                                'b200_trt_count': analysis['b200_trt_count'],
                                'hwkeys': sorted(list(analysis['hwkeys'])),
                                'precisions': sorted(list(analysis['precisions'])),
                                'filepath': filepath,
                                'url': url,
                                'date': latest_date,
                            }

                            combination_success = True
                            print(f"✅ Success: {analysis['record_count']} records, "
                                  f"{analysis['b200_trt_count']} b200_trt, "
                                  f"HW: {sorted(list(analysis['hwkeys']))}")

                        except Exception as e:
                            print(f"❌ Failed to save file: {str(e)}")
                            logger.error(f"Save error: {e}", exc_info=True)
                            combination_data['data_types'][data_type] = {
                                'success': False,
                                'error': str(e)
                            }
                    else:
                        print(f"❌ Failed to fetch data from {url}")
                        combination_data['data_types'][data_type] = {
                            'success': False,
                            'error': f'Failed to fetch data from {url}'
                        }

                    time.sleep(0.3)  # 短暂延迟

                if combination_success:
                    model_stats['successful_combinations'] += 1
                    results['successful_collections'].append(combination_data)
                else:
                    results['failed_collections'].append(combination_data)

                response_index += 1

            # 转换 set 为 list 以便 JSON 序列化
            model_stats['hwkeys'] = sorted(list(model_stats['hwkeys']))
            model_stats['dates_used'] = sorted(list(model_stats['dates_used']))
            results['model_stats'][model] = model_stats

        return results


# ─── 入口函数 ─────────────────────────────────────────────────────────────────

def scrape_api_data(models: List[str], sequences: List[str],
                    output_dir: str = "json_data/raw_json_files",
                    timeout: int = 120) -> Dict:
    """
    使用新 API 方法采集数据的入口函数

    Args:
        models: 模型列表
        sequences: 序列长度列表
        output_dir: 输出目录
        timeout: 请求超时时间（秒）

    Returns:
        采集结果字典
    """
    print("🚀 Starting InferenceX data collection (Vercel Blob Storage API)...")
    print(f"📋 Target: {len(models)} models × {len(sequences)} sequences = {len(models) * len(sequences)} combinations")
    print(f"📁 Output directory: {output_dir}")

    # 确保输出目录存在
    os.makedirs(output_dir, exist_ok=True)

    # 创建采集器
    collector = APIDataCollector(timeout=timeout)

    # 开始采集
    start_time = time.time()
    results = collector.collect_all_data(models, sequences, output_dir)
    elapsed_time = time.time() - start_time

    # 更新统计
    results['elapsed_time'] = elapsed_time
    results['timestamp'] = datetime.now().isoformat()
    results['api_version'] = 'v2-vercel-blob'
    results['base_url'] = collector.base_url

    # 打印结果
    print(f"\n{'='*80}")
    print(f"📈 Collection Statistics:")
    print(f"{'='*80}")
    print(f"Elapsed time: {elapsed_time:.1f} seconds")
    print(f"Total files: {results['total_files']}")
    print(f"Total records: {results['total_records']}")
    print(f"Total b200_trt data: {results['total_b200_trt']}")
    print(f"Successful combinations: {len(results['successful_collections'])}")
    print(f"Failed combinations: {len(results['failed_collections'])}")

    print(f"\n📊 Model Details:")
    for model, stats in results['model_stats'].items():
        print(f"\n🔸 {model}:")
        print(f"  Files: {stats['files']}")
        print(f"  Records: {stats['records']}")
        print(f"  b200_trt: {stats['b200_trt']} ({'✅' if stats['b200_trt'] > 0 else '❌'})")
        print(f"  Hardware: {stats['hwkeys']}")
        print(f"  Dates used: {stats['dates_used']}")

    # 保存总结报告
    summary_file = os.path.join(output_dir, 'api_scraping_summary.json')
    with open(summary_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\n📋 Summary saved: {summary_file}")

    return results


# ─── CLI 入口 ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="InferenceX 推理性能数据采集 (Vercel Blob Storage API)"
    )
    parser.add_argument(
        '--output-dir', '-o',
        default='json_data/raw_json_files',
        help='输出目录 (默认: json_data/raw_json_files)'
    )
    parser.add_argument(
        '--models', '-m',
        default=None,
        help='逗号分隔的模型列表 (默认: 使用内置列表)'
    )
    parser.add_argument(
        '--sequences', '-s',
        default=None,
        help='逗号分隔的序列列表 (默认: "1K / 1K,1K / 8K,8K / 1K")'
    )
    parser.add_argument(
        '--timeout', '-t',
        type=int, default=120,
        help='请求超时时间（秒）(默认: 120)'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='启用详细日志输出'
    )

    args = parser.parse_args()

    # 设置日志
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format='%(asctime)s - %(levelname)s - %(message)s')

    # 解析模型列表
    models = [m.strip() for m in args.models.split(',')] if args.models else DEFAULT_MODELS

    # 解析序列列表
    sequences = [s.strip() for s in args.sequences.split(',')] if args.sequences else DEFAULT_SEQUENCES

    # 执行采集
    results = scrape_api_data(models, sequences, args.output_dir, args.timeout)

    # 退出码
    if results.get('total_files', 0) > 0:
        exit(0)
    else:
        print("❌ No data was collected!")
        exit(1)


if __name__ == "__main__":
    main()
