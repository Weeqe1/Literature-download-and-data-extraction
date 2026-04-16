#!/usr/bin/env python3
"""测试日志文件输出功能"""

import os
import sys
import logging
from datetime import datetime

# 创建logs目录
log_dir = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(log_dir, exist_ok=True)

# 生成带有时间戳的日志文件名
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_file = os.path.join(log_dir, f"test_{timestamp}.log")

# 设置日志（同时输出到控制台和文件）
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_file, encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

logger.info("=" * 60)
logger.info("日志测试开始")
logger.info("日志文件: %s", log_file)
logger.info("=" * 60)

logger.info("这是一条测试日志")
logger.warning("这是一条警告日志")
logger.error("这是一条错误日志")

logger.info("=" * 60)
logger.info("日志测试完成")
logger.info("=" * 60)

print(f"\n日志文件已创建: {log_file}")
print("请检查日志文件是否存在且内容正确。")
