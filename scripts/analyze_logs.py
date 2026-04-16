#!/usr/bin/env python3
"""
日志分析脚本 - 分析harvest_literature.py的运行日志
用法: python analyze_logs.py [log_file]
"""

import os
import re
import sys
from datetime import datetime
from pathlib import Path
from collections import Counter


def parse_log_file(log_file: str) -> dict:
    """解析日志文件，提取关键信息"""
    
    stats = {
        'file': log_file,
        'start_time': None,
        'end_time': None,
        'duration': None,
        'total_clauses': 0,
        'total_works_merged': 0,
        'total_dois_filled': 0,
        'download_total': 0,
        'download_success': 0,
        'download_failed': 0,
        'download_success_rate': 0.0,
        'download_sources': {},
        'warnings': [],
        'errors': [],
        'bans': [],
        'rate_limits': [],
    }
    
    if not os.path.exists(log_file):
        stats['errors'].append(f"Log file not found: {log_file}")
        return stats
    
    with open(log_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    for line in lines:
        # 提取时间戳
        time_match = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
        if time_match:
            timestamp = datetime.strptime(time_match.group(1), '%Y-%m-%d %H:%M:%S')
            if stats['start_time'] is None:
                stats['start_time'] = timestamp
            stats['end_time'] = timestamp
        
        # 提取子句数量
        if '[Split] derived' in line and 'clauses' in line:
            match = re.search(r'derived (\d+) clauses', line)
            if match:
                stats['total_clauses'] = int(match.group(1))
        
        # 提取合并后的总数
        if '[Merge] merged total:' in line:
            match = re.search(r'merged total: (\d+)', line)
            if match:
                stats['total_works_merged'] = int(match.group(1))
        
        # 提取DOI填充数量
        if '[Fill] trying to find missing DOIs for' in line:
            match = re.search(r'for (\d+) items', line)
            if match:
                stats['total_dois_filled'] = int(match.group(1))
        
        # 提取下载统计
        if '[Download]' in line and 'works to process' in line:
            match = re.search(r'(\d+) works to process', line)
            if match:
                stats['download_total'] = int(match.group(1))
        
        if '[Download] Complete:' in line:
            match = re.search(r'(\d+) succeeded, (\d+) failed', line)
            if match:
                stats['download_success'] = int(match.group(1))
                stats['download_failed'] = int(match.group(2))
        
        if 'Download:' in line and 'succeeded' in line and '%' in line:
            match = re.search(r'(\d+)/(\d+) succeeded \((\d+\.?\d*)%\)', line)
            if match:
                stats['download_success'] = int(match.group(1))
                stats['download_total'] = int(match.group(2))
                stats['download_success_rate'] = float(match.group(3))
        
        # 提取下载来源统计
        if '[Stats] Download:' in line and 'Sources:' in line:
            sources_part = line.split('Sources:')[1].strip()
            for source_match in re.finditer(r'(\w+)=(\d+)', sources_part):
                source_name = source_match.group(1)
                source_count = int(source_match.group(2))
                stats['download_sources'][source_name] = source_count
        
        # 提取警告
        if '[WARNING]' in line:
            stats['warnings'].append(line.strip())
        
        # 提取错误
        if '[ERROR]' in line:
            stats['errors'].append(line.strip())
        
        # 提取封禁信息
        if 'banned for' in line:
            stats['bans'].append(line.strip())
        
        # 提取速率限制信息
        if 'rate limited' in line or '429' in line:
            stats['rate_limits'].append(line.strip())
    
    # 计算运行时长
    if stats['start_time'] and stats['end_time']:
        duration = stats['end_time'] - stats['start_time']
        stats['duration'] = str(duration)
    
    # 计算成功率
    if stats['download_total'] > 0 and stats['download_success_rate'] == 0:
        stats['download_success_rate'] = (stats['download_success'] / stats['download_total']) * 100
    
    return stats


def print_stats(stats: dict):
    """打印统计信息"""
    print("\n" + "=" * 70)
    print("日志分析报告")
    print("=" * 70)
    
    print(f"\n日志文件: {stats['file']}")
    
    if stats['start_time']:
        print(f"开始时间: {stats['start_time'].strftime('%Y-%m-%d %H:%M:%S')}")
    if stats['end_time']:
        print(f"结束时间: {stats['end_time'].strftime('%Y-%m-%d %H:%M:%S')}")
    if stats['duration']:
        print(f"运行时长: {stats['duration']}")
    
    print(f"\n【文献检索统计】")
    print(f"  搜索子句数: {stats['total_clauses']}")
    print(f"  合并后总数: {stats['total_works_merged']}")
    print(f"  DOI填充数: {stats['total_dois_filled']}")
    
    print(f"\n【下载统计】")
    print(f"  需下载总数: {stats['download_total']}")
    print(f"  成功下载: {stats['download_success']}")
    print(f"  下载失败: {stats['download_failed']}")
    print(f"  成功率: {stats['download_success_rate']:.1f}%")
    
    if stats['download_sources']:
        print(f"\n【下载来源分布】")
        for source, count in sorted(stats['download_sources'].items(), key=lambda x: -x[1]):
            print(f"  {source}: {count}")
    
    print(f"\n【问题统计】")
    print(f"  警告数量: {len(stats['warnings'])}")
    print(f"  错误数量: {len(stats['errors'])}")
    print(f"  封禁次数: {len(stats['bans'])}")
    print(f"  速率限制: {len(stats['rate_limits'])}")
    
    # 显示最常见的警告
    if stats['warnings']:
        print(f"\n【最常见的警告】(前5个)")
        warning_types = Counter()
        for w in stats['warnings']:
            if 'Forbidden (403)' in w:
                warning_types['403 Forbidden'] += 1
            elif 'banned' in w:
                warning_types['Source banned'] += 1
            elif 'rate limited' in w:
                warning_types['Rate limited'] += 1
            elif 'Timeout' in w:
                warning_types['Timeout'] += 1
            else:
                warning_types['Other'] += 1
        
        for wtype, count in warning_types.most_common(5):
            print(f"  {wtype}: {count}")
    
    # 显示错误
    if stats['errors']:
        print(f"\n【错误详情】(前5个)")
        for error in stats['errors'][:5]:
            print(f"  {error[:100]}...")
    
    print("\n" + "=" * 70)


def find_latest_log(log_dir: str = 'logs') -> str:
    """查找最新的日志文件"""
    if not os.path.exists(log_dir):
        return None
    
    log_files = [f for f in os.listdir(log_dir) if f.startswith('harvest_') and f.endswith('.log')]
    if not log_files:
        return None
    
    log_files.sort(reverse=True)
    return os.path.join(log_dir, log_files[0])


def main():
    # 确定日志文件
    if len(sys.argv) > 1:
        log_file = sys.argv[1]
    else:
        log_file = find_latest_log()
        if not log_file:
            print("错误: 未找到日志文件")
            print("用法: python analyze_logs.py [log_file]")
            sys.exit(1)
        print(f"使用最新日志文件: {log_file}")
    
    # 解析并打印统计
    stats = parse_log_file(log_file)
    print_stats(stats)


if __name__ == "__main__":
    main()