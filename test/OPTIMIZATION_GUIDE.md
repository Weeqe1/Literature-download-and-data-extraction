# NFP-PDF-to-DB 优化指南

## 概述

本文档描述了针对低下载成功率（9%）和性能问题的优化方案。

## 主要问题分析

### 原始运行结果
- **总文献数**: 5,245 篇
- **尝试下载**: 2,902 篇
- **成功下载**: 261 篇 (9.0%)
- **失败原因**:
  - `none`: 2,014 篇 (没有找到PDF链接)
  - `unpaywall`: 715 篇 (Unpaywall找到链接但下载失败)
  - `direct`: 151 篇
  - `pmc`: 21 篇
  - `doi_redirect`: 1 篇

## 优化方案

### 1. 增加PDF下载源

我们添加了以下新的PDF下载源：

#### Sci-Hub
- **用途**: 学术研究用途，获取付费论文PDF
- **镜像站点**:
  - https://sci-hub.se
  - https://sci-hub.st
  - https://sci-hub.ru
- **优先级**: 第6级（在标准来源之后）

#### ResearchGate
- **用途**: 从ResearchGate获取作者上传的PDF
- **优先级**: 第7级

#### arXiv
- **用途**: 直接从arXiv获取预印本PDF
- **优先级**: 第4级（在PMC之后）

### 2. 优化配置参数

#### 搜索参数
```yaml
search:
  # 保持高值以获取全部文献
  max_results_per_clause: 2000  # 从1200增加到2000
  max_total: 50000  # 合理上限
```

#### 下载参数
```yaml
runtime:
  # 增加并发和重试
  max_concurrent_downloads: 12  # 从4增加到12
  download_retries: 8  # 从3增加到8
  download_timeout: 120  # 从60增加到120
  
  # 更频繁的检查点
  checkpoint_interval: 25  # 从100减少到25
  
  # 启用增强的PDF下载源
  enhanced_pdf_sources: true
```

#### 质量控制
```yaml
quality:
  enabled: true  # 启用质量过滤
  min_relevance: 0.2  # 提高相关性要求
  min_completeness: 0.3  # 提高完整性要求
  min_overall: 0.25  # 提高综合评分要求
```

### 3. 代码修改

#### harvester.py
- 添加了对增强下载器的支持
- 根据配置自动选择使用标准或增强下载器

#### downloader.py
- 添加了 `_download_from_scihub()` 函数
- 添加了 `_download_from_researchgate()` 函数
- 修改了 `_resolve_pdf_url()` 函数，增加更多PDF来源
- 修改了 `download_file()` 函数，支持特殊来源的下载

#### sources/base.py
- 添加了 Sci-Hub 和 ResearchGate 的速率限制配置

## 使用方法

### 1. 使用优化后的配置文件

```bash
# 复制优化后的配置文件
cp configs/harvest/harvest_config_optimized_v2.yml configs/harvest/harvest_config.yml

# 运行程序
python harvest_literature.py
```

### 2. 配置文件说明

优化后的配置文件 `harvest_config_optimized_v2.yml` 包含：

1. **保持最大搜索范围**: 不减少搜索结果数量
2. **启用质量过滤**: 过滤低质量文献
3. **增强PDF下载**: 支持多个PDF来源
4. **优化性能**: 增加并发和重试次数

### 3. 预期改进

#### 下载成功率
- **原始**: 9.0%
- **预期**: 30-50%（通过Sci-Hub和ResearchGate）

#### 性能改进
- **并发下载**: 从4增加到12，速度提升3倍
- **重试次数**: 从3增加到8，提高成功率
- **超时时间**: 从60秒增加到120秒，处理慢速连接

#### 质量改进
- **相关性过滤**: 过滤不相关文献
- **完整性检查**: 确保必要字段存在
- **综合评分**: 综合评估文献质量

## 监控和调试

### 1. 下载报告

程序会生成详细的下载报告：
```
outputs/literature/download_report.txt
```

报告包含：
- 总任务数
- 成功/失败数量
- 下载来源分布
- 失败原因分布
- 优化建议

### 2. 检查点文件

定期保存的检查点文件：
```
outputs/literature/_checkpoint.xlsx
outputs/literature/_checkpoint_stats.json
```

### 3. 日志输出

详细的日志输出帮助调试：
```
2026-04-12 18:40:44 [INFO] etl_ensemble.harvester: [Download] Using enhanced PDF sources for better coverage...
2026-04-12 18:40:44 [INFO] etl_ensemble.downloader:   [Download] Trying Sci-Hub for 10.1007/s12274-022-4567-8...
```

## 注意事项

### 1. 法律合规
- Sci-Hub 仅用于学术研究用途
- 请遵守当地法律法规
- 尊重版权和知识产权

### 2. 性能考虑
- 增加并发数会消耗更多系统资源
- 建议在空闲时间运行
- 监控磁盘空间使用情况

### 3. 网络要求
- 需要稳定的网络连接
- 可能需要代理访问某些网站
- 注意API速率限制

## 故障排除

### 1. 下载仍然失败
- 检查网络连接
- 验证API密钥是否有效
- 查看日志中的具体错误信息

### 2. 程序运行缓慢
- 减少 `max_concurrent_downloads` 值
- 增加 `requests_per_second` 间隔
- 检查系统资源使用情况

### 3. 质量过滤过于严格
- 降低 `min_relevance`、`min_completeness`、`min_overall` 值
- 临时禁用质量过滤进行测试

## 联系支持

如有问题或建议，请联系：
- 邮箱: wangqi@ahut.edu.cn
- 项目地址: https://github.com/your-repo/nfp-pdf-to-db

---

**最后更新**: 2026-04-12
**版本**: 1.0