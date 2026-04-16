"""Centralized logging configuration for the NFP-PDF-to-DB project.

Import and call `setup_logging()` early in the entry point to configure
all loggers with a consistent format. Individual modules should use:
    import logging
    logger = logging.getLogger(__name__)
"""

import logging
import sys
import os
from datetime import datetime


def setup_logging(level: int = logging.INFO, log_file: str = None) -> None:
    """Configure root logger with console and optional file handlers.

    Args:
        level: Logging level (default: INFO).
        log_file: Optional path to a log file.
    """
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    date_fmt = "%Y-%m-%d %H:%M:%S"

    handlers: list = [logging.StreamHandler(sys.stdout)]
    if log_file:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    logging.basicConfig(
        level=level,
        format=fmt,
        datefmt=date_fmt,
        handlers=handlers,
    )

    # Quiet noisy third-party loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)


def get_ensemble_logger(name: str = "ensemble", log_dir: str = "logs") -> logging.Logger:
    """Get a logger specifically configured for ensemble operations.
    
    Args:
        name: Logger name (default: "ensemble")
        log_dir: Directory for log files (default: "logs")
    
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    
    # 避免重复添加handler
    if not logger.handlers:
        # 创建logs目录
        os.makedirs(log_dir, exist_ok=True)
        
        # 生成带时间戳的日志文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = os.path.join(log_dir, f"ensemble_{timestamp}.log")
        
        # 文件handler
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.INFO)
        
        # 控制台handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        
        # 格式
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        logger.setLevel(logging.INFO)
        
        # 记录初始信息
        logger.info("=" * 60)
        logger.info("Ensemble日志系统初始化")
        logger.info("日志文件: %s", log_file)
        logger.info("=" * 60)
    
    return logger


def log_ensemble_comparison(comparison_report: dict, logger: logging.Logger = None) -> None:
    """Log ensemble comparison results.
    
    Args:
        comparison_report: Dictionary containing comparison results
        logger: Logger instance (creates new one if None)
    """
    if logger is None:
        logger = get_ensemble_logger()
    
    logger.info("=" * 50)
    logger.info("Ensemble对比报告")
    logger.info("=" * 50)
    
    # 记录PDF信息
    if "pdf" in comparison_report:
        logger.info("PDF文件: %s", comparison_report["pdf"])
    
    # 记录成功/失败统计
    if "success_count" in comparison_report:
        logger.info("成功模型数: %d", comparison_report["success_count"])
    if "failed_count" in comparison_report:
        logger.info("失败模型数: %d", comparison_report["failed_count"])
    
    # 记录共识统计
    if "consensus_stats" in comparison_report:
        stats = comparison_report["consensus_stats"]
        logger.info("共识字段数: %d", stats.get("consensus_fields", 0))
        logger.info("总字段数: %d", stats.get("total_fields", 0))
        logger.info("共识比例: %.1f%%", stats.get("consensus_ratio", 0) * 100)
    
    # 记录模型性能
    if "model_performance" in comparison_report:
        logger.info("模型性能:")
        for model_id, perf in comparison_report["model_performance"].items():
            logger.info("  %s: 准确率=%.1f%%, 耗时=%.2fs", 
                       model_id, perf.get("accuracy", 0) * 100, perf.get("duration", 0))
    
    logger.info("=" * 50)
