# 日志文件说明

## 概述

本目录用于保存 `harvest_literature.py` 运行时的日志文件。每次运行程序时，会自动生成一个带有时间戳的日志文件。

## 日志文件命名规则

```
harvest_YYYYMMDD_HHMMSS.log
```

例如：
- `harvest_20260416_123456.log` - 2026年4月16日12点34分56秒的运行日志
- `harvest_20260415_211615.log` - 2026年4月15日21点16分15秒的运行日志

## 日志内容

日志文件包含以下信息：

### 1. 程序启动信息
```
============================================================
Starting literature harvest pipeline
Log file: /path/to/logs/harvest_20260416_123456.log
============================================================
```

### 2. 配置加载信息
```
2026-04-16 12:34:56 [INFO] etl_ensemble.harvester: [Config] Loaded configuration from configs/harvest/harvest_config.yml
```

### 3. 搜索进度
```
2026-04-16 12:34:56 [INFO] etl_ensemble.harvester: [Split] derived 10 clauses from keywords.
2026-04-16 12:34:56 [INFO] etl_ensemble.harvester: [Clause 1] "chiral fluorescent nanoprobe"
2026-04-16 12:34:56 [INFO] etl_ensemble.harvester: [openalex] querying (title-only): "chiral fluorescent nanoprobe"
2026-04-16 12:34:57 [INFO] etl_ensemble.harvester: [openalex] returned 5 items, kept 5 after clause match
```

### 4. 下载进度
```
2026-04-16 12:35:00 [INFO] etl_ensemble.harvester: [Download] attempting to download OA PDFs and assembling table...
2026-04-16 12:35:00 [INFO] etl_ensemble.downloader:   [Resume] Loaded 1073 DOIs from checkpoint
2026-04-16 12:35:00 [INFO] etl_ensemble.downloader:   [Download] 850 works to process (of 1946 total)
```

### 5. 反封锁警告
```
2026-04-16 12:35:30 [WARNING] etl_ensemble.anti_ban: [AntiBan] Forbidden (403) on direct
2026-04-16 12:35:35 [WARNING] etl_ensemble.anti_ban: [AntiBan] Source 'direct' banned for 300s after 5 failures
```

### 6. 完成信息
```
============================================================
Literature harvest completed
Log saved to: /path/to/logs/harvest_20260416_123456.log
============================================================
```

## 日志级别

- **INFO**: 正常运行信息
- **WARNING**: 警告信息（如反封锁触发、速率限制等）
- **ERROR**: 错误信息（如下载失败、API错误等）
- **DEBUG**: 调试信息（如需要，可修改日志级别）

## 使用方法

### 1. 查看最新日志

```bash
# 查看最新的日志文件
ls -lt logs/ | head -5

# 查看最新日志的内容
tail -f logs/harvest_*.log | head -100
```

### 2. 分析运行状态

```bash
# 统计下载成功数
grep -c "succeeded" logs/harvest_*.log

# 查看所有警告
grep "WARNING" logs/harvest_*.log

# 查看所有错误
grep "ERROR" logs/harvest_*.log

# 查看反封锁触发次数
grep -c "banned" logs/harvest_*.log
```

### 3. 比较多次运行

```bash
# 比较两次运行的下载成功率
grep "succeeded" logs/harvest_20260415_*.log
grep "succeeded" logs/harvest_20260416_*.log
```

## 日志文件管理

### 1. 清理旧日志

```bash
# 删除30天前的日志
find logs/ -name "*.log" -mtime +30 -delete

# 删除所有日志（谨慎使用）
rm -f logs/*.log
```

### 2. 压缩日志

```bash
# 压缩单个日志
gzip logs/harvest_20260415_211615.log

# 批量压缩
gzip logs/*.log
```

### 3. 日志轮转

建议定期清理或压缩旧日志，避免占用过多磁盘空间。

## 注意事项

1. **磁盘空间**: 日志文件可能较大，特别是长时间运行时
2. **编码格式**: 日志文件使用UTF-8编码
3. **并发写入**: 同一时间只能运行一个harvest程序，避免日志混乱
4. **日志级别**: 默认为INFO级别，可在logging_config.py中修改

## 故障排查

如果日志文件没有生成，检查：

1. logs目录是否存在且有写入权限
2. 磁盘空间是否充足
3. 程序是否正常启动

---

**最后更新**: 2026-04-16
**维护者**: Hermes Agent