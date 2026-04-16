#!/usr/bin/env python3
"""
搜索结果一致性测试脚本
比较多次运行的搜索结果差异
"""

import os
import csv
import hashlib
from datetime import datetime
from typing import Dict, Set, List, Tuple


def load_dois_from_csv(csv_path: str) -> Set[str]:
    """从CSV文件加载所有DOI"""
    dois = set()
    if not os.path.exists(csv_path):
        return dois
    
    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            doi = row.get('doi', '').strip()
            if doi and doi != 'nan' and doi != '':
                dois.add(doi.lower())
    return dois


def load_titles_from_csv(csv_path: str) -> Set[str]:
    """从CSV文件加载所有标题（用于无DOI文献的匹配）"""
    titles = set()
    if not os.path.exists(csv_path):
        return titles
    
    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            title = row.get('title', '').strip()
            if title:
                # 标准化标题（小写，去除空格）
                normalized = ' '.join(title.lower().split())
                titles.add(normalized)
    return titles


def compare_results(file1: str, file2: str) -> Dict:
    """比较两个CSV文件的结果"""
    
    # 加载DOI
    dois1 = load_dois_from_csv(file1)
    dois2 = load_dois_from_csv(file2)
    
    # 加载标题
    titles1 = load_titles_from_csv(file1)
    titles2 = load_titles_from_csv(file2)
    
    # 计算交集和差集
    common_dois = dois1 & dois2
    only_in_1_dois = dois1 - dois2
    only_in_2_dois = dois2 - dois1
    
    common_titles = titles1 & titles2
    only_in_1_titles = titles1 - titles2
    only_in_2_titles = titles2 - titles1
    
    return {
        'file1': file1,
        'file2': file2,
        'file1_total': len(dois1) if dois1 else len(titles1),
        'file2_total': len(dois2) if dois2 else len(titles2),
        'common_dois': len(common_dois),
        'only_in_1_dois': len(only_in_1_dois),
        'only_in_2_dois': len(only_in_2_dois),
        'common_titles': len(common_titles),
        'only_in_1_titles': len(only_in_1_titles),
        'only_in_2_titles': len(only_in_2_titles),
        'overlap_rate': len(common_dois) / max(len(dois1), len(dois2), 1) * 100,
        'examples_only_in_1': list(only_in_1_dois)[:5] if only_in_1_dois else list(only_in_1_titles)[:5],
        'examples_only_in_2': list(only_in_2_dois)[:5] if only_in_2_dois else list(only_in_2_titles)[:5],
    }


def find_checkpoint_files(outputs_dir: str = 'outputs/literature') -> List[str]:
    """查找所有的检查点文件（来自不同运行）"""
    checkpoint_files = []
    
    # 查找checkpoint文件
    for f in os.listdir(outputs_dir):
        if 'checkpoint' in f.lower() and f.endswith('.csv'):
            checkpoint_files.append(os.path.join(outputs_dir, f))
    
    # 查找主数据文件
    for f in os.listdir(outputs_dir):
        if f.startswith('nano_fluorescent_probes') and f.endswith('.csv') and '_check' not in f:
            checkpoint_files.append(os.path.join(outputs_dir, f))
    
    return sorted(set(checkpoint_files))


def print_comparison_report(comparison: Dict):
    """打印比较报告"""
    print("\n" + "=" * 70)
    print("搜索结果一致性分析报告")
    print("=" * 70)
    
    print(f"\n文件1: {os.path.basename(comparison['file1'])}")
    print(f"  总记录数: {comparison['file1_total']}")
    
    print(f"\n文件2: {os.path.basename(comparison['file2'])}")
    print(f"  总记录数: {comparison['file2_total']}")
    
    print(f"\n【DOI匹配分析】")
    print(f"  共同DOI数: {comparison['common_dois']}")
    print(f"  仅在文件1中: {comparison['only_in_1_dois']}")
    print(f"  仅在文件2中: {comparison['only_in_2_dois']}")
    print(f"  重叠率: {comparison['overlap_rate']:.1f}%")
    
    if comparison['examples_only_in_1']:
        print(f"\n  仅在文件1中的示例DOI:")
        for doi in comparison['examples_only_in_1']:
            print(f"    - {doi}")
    
    if comparison['examples_only_in_2']:
        print(f"\n  仅在文件2中的示例DOI:")
        for doi in comparison['examples_only_in_2']:
            print(f"    - {doi}")
    
    # 判断一致性
    print(f"\n【一致性评估】")
    if comparison['overlap_rate'] >= 95:
        print(f"  ✅ 高度一致（重叠率 {comparison['overlap_rate']:.1f}%）")
        print(f"  说明：两次运行结果基本相同")
    elif comparison['overlap_rate'] >= 80:
        print(f"  ⚠️ 较为一致（重叠率 {comparison['overlap_rate']:.1f}%）")
        print(f"  说明：存在部分差异，可能是新文献或API波动")
    else:
        print(f"  ❌ 差异较大（重叠率 {comparison['overlap_rate']:.1f}%）")
        print(f"  说明：结果差异显著，需要检查配置或网络")
    
    print("\n" + "=" * 70)


def main():
    import sys
    
    outputs_dir = 'outputs/literature'
    
    # 查找可用的CSV文件
    csv_files = []
    for f in os.listdir(outputs_dir):
        if f.endswith('.csv') and '_check' not in f:
            csv_files.append(os.path.join(outputs_dir, f))
    
    if len(csv_files) < 2:
        print("需要至少两个CSV文件才能进行比较")
        print(f"当前找到的文件: {csv_files}")
        print("\n提示：多次运行 harvest_literature.py 后，可以比较不同运行的结果")
        return
    
    print("找到以下CSV文件：")
    for i, f in enumerate(sorted(csv_files), 1):
        print(f"  {i}. {os.path.basename(f)}")
    
    # 如果有两个文件，直接比较
    if len(csv_files) == 2:
        comparison = compare_results(csv_files[0], csv_files[1])
        print_comparison_report(comparison)
    else:
        # 多个文件，比较最新的两个
        csv_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
        print(f"\n比较最新的两个文件：")
        print(f"  1. {os.path.basename(csv_files[0])}")
        print(f"  2. {os.path.basename(csv_files[1])}")
        
        comparison = compare_results(csv_files[0], csv_files[1])
        print_comparison_report(comparison)


if __name__ == "__main__":
    main()