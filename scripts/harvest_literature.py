"""Harvester entry point - delegates to etl_ensemble.harvester."""
import os
import logging
from datetime import datetime
from logging_config import setup_logging
from etl_ensemble.harvester import LiteratureHarvester, load_config


def main():
    # 创建logs目录（在项目根目录下）
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)  # 向上一级到项目根目录
    log_dir = os.path.join(project_root, "logs")
    os.makedirs(log_dir, exist_ok=True)
    
    # 生成带有时间戳的日志文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"harvest_{timestamp}.log")
    
    # 设置日志（同时输出到控制台和文件）
    setup_logging(log_file=log_file)
    
    logger = logging.getLogger(__name__)
    logger.info("=" * 60)
    logger.info("Starting literature harvest pipeline")
    logger.info("Log file: %s", log_file)
    logger.info("=" * 60)
    
    cfg = load_config()
    harvester = LiteratureHarvester(config=cfg)
    harvester.run()
    
    logger.info("=" * 60)
    logger.info("Literature harvest completed")
    logger.info("Log saved to: %s", log_file)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
