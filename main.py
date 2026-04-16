#!/usr/bin/env python3
"""
main.py - 手性纳米荧光探针数据库构建系统主入口

提供交互式工作流程，支持：
1. 文献检索与下载
2. 数据提取与数据集构建
3. 运行状态查看
"""

import os
import sys
import logging
from datetime import datetime
from pathlib import Path

# 添加scripts目录和项目根目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scripts'))
sys.path.insert(0, os.path.dirname(__file__))

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def print_banner():
    """打印程序横幅"""
    print("\n" + "=" * 60)
    print("   手性纳米荧光探针数据库构建系统")
    print("   Chiral Nanoprobe Database Builder")
    print("=" * 60)
    print()


def print_menu():
    """打印主菜单"""
    print("\n请选择要执行的操作：")
    print("-" * 40)
    print("  [1] 文献检索与PDF下载")
    print("  [2] 数据提取与数据集构建")
    print("  [3] 查看运行状态和统计")
    print("  [4] 分析运行日志")
    print("  [0] 退出程序")
    print("-" * 40)


def run_harvest():
    """运行文献检索和下载"""
    print("\n" + "=" * 50)
    print("  文献检索与PDF下载")
    print("=" * 50)
    
    # 检查配置文件
    config_path = "configs/harvest/harvest_config.yml"
    if not os.path.exists(config_path):
        print(f"\n错误：配置文件不存在: {config_path}")
        print("请先配置API密钥和搜索参数。")
        return
    
    print(f"\n使用配置文件: {config_path}")
    print("\n开始文献检索...")
    print("提示：此过程可能需要较长时间，请耐心等待。")
    print("      日志将自动保存到 logs/ 目录。")
    
    confirm = input("\n是否继续？(y/n): ").strip().lower()
    if confirm != 'y':
        print("已取消。")
        return
    
    # 导入并运行harvest_literature
    try:
        from harvest_literature import main as harvest_main
        harvest_main()
    except Exception as e:
        logger.error(f"文献检索失败: {e}")
        print(f"\n错误: {e}")
    
    print("\n文献检索完成！")
    print("结果保存在: outputs/literature/")


def run_extraction():
    """运行数据提取和数据集构建"""
    print("\n" + "=" * 50)
    print("  数据提取与数据集构建")
    print("=" * 50)
    
    # 检查PDF目录
    pdf_dir = "outputs/literature/PDF"
    if not os.path.exists(pdf_dir):
        print(f"\n错误：PDF目录不存在: {pdf_dir}")
        print("请先运行文献检索下载PDF文件。")
        return
    
    # 统计PDF文件数量
    pdf_files = list(Path(pdf_dir).glob("*.pdf"))
    print(f"\n找到 {len(pdf_files)} 个PDF文件")
    
    if len(pdf_files) == 0:
        print("没有找到PDF文件，请先运行文献检索。")
        return
    
    # 显示提取选项
    print("\n提取选项：")
    print("  [1] 完整提取（推荐，包含数据集构建）")
    print("  [2] 仅数据提取")
    print("  [3] 仅数据集构建")
    print("  [0] 返回主菜单")
    
    choice = input("\n请选择: ").strip()
    
    if choice == '1':
        run_full_extraction()
    elif choice == '2':
        run_data_extraction_only()
    elif choice == '3':
        run_dataset_building_only()
    elif choice == '0':
        return
    else:
        print("无效选择")


def run_full_extraction():
    """完整提取流程"""
    print("\n开始完整提取流程...")
    
    # 步骤1：数据提取
    print("\n[步骤1/2] 从PDF提取数据...")
    try:
        from run_chiral_extraction_v2 import main as extraction_main
        
        # 修改sys.argv以传递参数
        original_argv = sys.argv.copy()
        sys.argv = [
            'run_chiral_extraction_v2.py',
            '--pdf_dir', 'outputs/literature/PDF',
            '--out_dir', 'outputs/chiral_extraction',
            '--workers', '4',
            '--resume'
        ]
        
        extraction_main()
        sys.argv = original_argv
        
    except Exception as e:
        logger.error(f"数据提取失败: {e}")
        print(f"\n数据提取错误: {e}")
        return
    
    # 步骤2：构建数据集
    print("\n[步骤2/2] 构建机器学习数据集...")
    try:
        from build_chiral_dataset import build_chiral_dataset
        
        build_chiral_dataset(
            json_dir='outputs/chiral_extraction',
            out_path='outputs/chiral_nanoprobes_ml_dataset.csv'
        )
        
    except Exception as e:
        logger.error(f"数据集构建失败: {e}")
        print(f"\n数据集构建错误: {e}")
        return
    
    print("\n完整提取流程完成！")
    print("提取结果: outputs/chiral_extraction/")
    print("数据集: outputs/chiral_nanoprobes_ml_dataset.csv")


def run_data_extraction_only():
    """仅运行数据提取"""
    print("\n开始数据提取...")
    
    try:
        from run_chiral_extraction_v2 import main as extraction_main
        
        original_argv = sys.argv.copy()
        sys.argv = [
            'run_chiral_extraction_v2.py',
            '--pdf_dir', 'outputs/literature/PDF',
            '--out_dir', 'outputs/chiral_extraction',
            '--workers', '4',
            '--resume'
        ]
        
        extraction_main()
        sys.argv = original_argv
        
        print("\n数据提取完成！")
        print("结果保存在: outputs/chiral_extraction/")
        
    except Exception as e:
        logger.error(f"数据提取失败: {e}")
        print(f"\n错误: {e}")


def run_dataset_building_only():
    """仅运行数据集构建"""
    extraction_dir = 'outputs/chiral_extraction'
    
    if not os.path.exists(extraction_dir):
        print(f"\n错误：提取结果目录不存在: {extraction_dir}")
        print("请先运行数据提取。")
        return
    
    print("\n开始构建数据集...")
    
    try:
        from build_chiral_dataset import build_chiral_dataset
        
        build_chiral_dataset(
            json_dir=extraction_dir,
            out_path='outputs/chiral_nanoprobes_ml_dataset.csv'
        )
        
        print("\n数据集构建完成！")
        print("数据集保存在: outputs/chiral_nanoprobes_ml_dataset.csv")
        
    except Exception as e:
        logger.error(f"数据集构建失败: {e}")
        print(f"\n错误: {e}")


def show_status():
    """显示运行状态和统计"""
    print("\n" + "=" * 50)
    print("  运行状态与统计")
    print("=" * 50)
    
    # 1. 文献下载状态
    print("\n【文献下载状态】")
    literature_dir = "outputs/literature"
    if os.path.exists(literature_dir):
        # 检查CSV文件
        csv_files = list(Path(literature_dir).glob("*.csv"))
        print(f"  CSV文件数: {len(csv_files)}")
        
        # 检查PDF文件
        pdf_dir = os.path.join(literature_dir, "PDF")
        if os.path.exists(pdf_dir):
            pdf_files = list(Path(pdf_dir).glob("*.pdf"))
            print(f"  PDF文件数: {len(pdf_files)}")
        else:
            print("  PDF目录不存在")
        
        # 检查检查点
        checkpoint_path = os.path.join(literature_dir, "_checkpoint.csv")
        if os.path.exists(checkpoint_path):
            print(f"  检查点: 存在")
        else:
            print(f"  检查点: 不存在")
    else:
        print("  文献目录不存在")
    
    # 2. 数据提取状态
    print("\n【数据提取状态】")
    extraction_dir = "outputs/chiral_extraction"
    if os.path.exists(extraction_dir):
        json_files = list(Path(extraction_dir).glob("*.json"))
        print(f"  提取结果数: {len(json_files)}")
        
        # 检查检查点
        checkpoint_path = os.path.join(extraction_dir, "checkpoint.json")
        if os.path.exists(checkpoint_path):
            import json
            with open(checkpoint_path, 'r') as f:
                checkpoint = json.load(f)
            print(f"  已处理: {len(checkpoint.get('processed', []))}")
            print(f"  失败: {len(checkpoint.get('failed', []))}")
        else:
            print(f"  检查点: 不存在")
    else:
        print("  提取目录不存在")
    
    # 3. 数据集状态
    print("\n【数据集状态】")
    dataset_path = "outputs/chiral_nanoprobes_ml_dataset.csv"
    if os.path.exists(dataset_path):
        import csv
        with open(dataset_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            rows = list(reader)
            print(f"  数据集文件: 存在")
            print(f"  总行数: {len(rows) - 1}")  # 减去表头
            print(f"  特征数: {len(rows[0]) if rows else 0}")
    else:
        print("  数据集: 不存在")
    
    # 4. 日志状态
    print("\n【日志状态】")
    logs_dir = "logs"
    if os.path.exists(logs_dir):
        log_files = list(Path(logs_dir).glob("*.log"))
        print(f"  日志文件数: {len(log_files)}")
        if log_files:
            latest = max(log_files, key=lambda x: x.stat().st_mtime)
            print(f"  最新日志: {latest.name}")
    else:
        print("  日志目录不存在")


def analyze_logs():
    """分析运行日志"""
    print("\n" + "=" * 50)
    print("  日志分析")
    print("=" * 50)
    
    logs_dir = "logs"
    if not os.path.exists(logs_dir):
        print("\n日志目录不存在。")
        return
    
    log_files = list(Path(logs_dir).glob("*.log"))
    if not log_files:
        print("\n没有找到日志文件。")
        return
    
    # 列出日志文件
    print("\n可用的日志文件：")
    for i, log_file in enumerate(sorted(log_files, reverse=True), 1):
        mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
        print(f"  [{i}] {log_file.name} ({mtime.strftime('%Y-%m-%d %H:%M')})")
    
    print(f"  [0] 返回主菜单")
    
    choice = input("\n请选择要分析的日志 (序号): ").strip()
    
    if choice == '0':
        return
    
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(log_files):
            selected_log = sorted(log_files, reverse=True)[idx]
            print(f"\n分析日志: {selected_log.name}")
            
            # 调用analyze_logs.py
            from analyze_logs import parse_log_file, print_comparison_report
            
            stats = parse_log_file(str(selected_log))
            
            # 打印简要统计
            print(f"\n运行时长: {stats.get('duration', 'N/A')}")
            print(f"下载成功: {stats.get('download_success', 0)}")
            print(f"下载失败: {stats.get('download_failed', 0)}")
            
            if stats.get('download_total', 0) > 0:
                success_rate = stats['download_success'] / stats['download_total'] * 100
                print(f"成功率: {success_rate:.1f}%")
            
            print(f"\n详细信息请查看日志文件。")
        else:
            print("无效选择")
    except ValueError:
        print("请输入有效的数字")


def main():
    """主函数"""
    print_banner()
    
    while True:
        print_menu()
        choice = input("请输入选择 (0-4): ").strip()
        
        if choice == '1':
            run_harvest()
        elif choice == '2':
            run_extraction()
        elif choice == '3':
            show_status()
        elif choice == '4':
            analyze_logs()
        elif choice == '0':
            print("\n感谢使用，再见！")
            break
        else:
            print("\n无效选择，请重新输入。")
        
        input("\n按回车键继续...")


if __name__ == "__main__":
    main()