#!/usr/bin/env python3
"""
测试main.py的基本功能
"""

import sys
import os

# 添加路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scripts'))
sys.path.insert(0, os.path.dirname(__file__))

def test_imports():
    """测试导入是否正常"""
    print("测试导入...")
    
    try:
        from scripts import harvest_literature
        print("✓ harvest_literature 导入成功")
    except ImportError as e:
        print(f"✗ harvest_literature 导入失败: {e}")
    
    try:
        from scripts import run_chiral_extraction_v2
        print("✓ run_chiral_extraction_v2 导入成功")
    except ImportError as e:
        print(f"✗ run_chiral_extraction_v2 导入失败: {e}")
    
    try:
        from scripts import build_chiral_dataset
        print("✓ build_chiral_dataset 导入成功")
    except ImportError as e:
        print(f"✗ build_chiral_dataset 导入失败: {e}")
    
    try:
        from etl_ensemble import harvester
        print("✓ etl_ensemble.harvester 导入成功")
    except ImportError as e:
        print(f"✗ etl_ensemble.harvester 导入失败: {e}")

def test_file_structure():
    """测试文件结构"""
    print("\n测试文件结构...")
    
    required_files = [
        'main.py',
        'scripts/harvest_literature.py',
        'scripts/run_chiral_extraction_v2.py',
        'scripts/build_chiral_dataset.py',
        'etl_ensemble/__init__.py',
        'etl_ensemble/harvester.py',
        'configs/harvest/harvest_config.yml',
        'requirements.txt'
    ]
    
    for file_path in required_files:
        if os.path.exists(file_path):
            print(f"✓ {file_path} 存在")
        else:
            print(f"✗ {file_path} 不存在")

if __name__ == "__main__":
    print("=" * 50)
    print("项目结构测试")
    print("=" * 50)
    
    test_file_structure()
    test_imports()
    
    print("\n" + "=" * 50)
    print("测试完成")
    print("=" * 50)