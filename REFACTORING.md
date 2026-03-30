# Refactoring Log - NFP-PDF-to-DB

Date: 2026-03-30

## Summary

全面重构优化了项目的代码结构、日志系统、模块化程度和测试覆盖。

## Changes

### P0 - 模块拆分 (Critical)

**`harvest_literature.py` 拆分**

原文件约 1500 行，包含所有逻辑。现已拆分为：

| 新模块 | 职责 | 原代码行数 |
|--------|------|-----------|
| `etl_ensemble/sources/base.py` | 通用工具：sanitize_filename, doi_normalize, normalize_text, parse_clause_units, split_keywords_into_clauses, match_work_against_clause, rate_limit 等 | ~300 行 |
| `etl_ensemble/sources/openalex.py` | OpenAlex API 搜索，含预算追踪、重试、预过滤 | ~200 行 |
| `etl_ensemble/sources/wos.py` | Web of Science 搜索 | ~100 行 |
| `etl_ensemble/sources/semantic_scholar.py` | Semantic Scholar 搜索，含速率限制 | ~150 行 |
| `etl_ensemble/sources/pubmed.py` | PubMed esearch+efetch 搜索 | ~100 行 |
| `etl_ensemble/sources/arxiv.py` | arXiv Atom API 搜索 | ~60 行 |
| `etl_ensemble/sources/crossref.py` | Crossref 搜索 + DOI 查找 + Unpaywall | ~200 行 |
| `etl_ensemble/harvester.py` | LiteratureHarvester 类，编排搜索、合并、去重、下载 | ~350 行 |
| `etl_ensemble/downloader.py` | PDF 下载：并发、checkpoint、磁盘监控 | ~250 行 |
| `etl_ensemble/pdf_checker.py` | PDF 完整性校验和清理 | ~120 行 |
| `harvest_literature.py` | 薄入口层，仅 15 行 | ~15 行 |

**向后兼容**：`harvest_literature.py` 保留 `main()` 函数，可直接运行。

### P1 - Logging 系统

- 新增 `logging_config.py`：统一日志配置（格式、级别、文件输出）
- 所有模块替换 `print()` 为 `logger.info/warning/error()`
- 影响文件：
  - `run_staged_extraction.py`
  - `quality_control.py`
  - `build_clean_dataset.py`
  - `etl_ensemble/llm_multi_client.py`
  - `etl_ensemble/llm_openai_client.py`
  - `etl_ensemble/focused_reextractor.py`
  - `etl_ensemble/human_review_manager.py`

### P1 - 修复 `llm_openai_client.py` 模块级副作用

**Before**: 模块导入时即执行配置加载、修改环境变量、可能抛出 RuntimeError

**After**: 
- 配置加载延迟到 `LLMClient.__init__`
- 提供 `load_config()` 函数供显式调用
- 导入不再产生副作用

### P1 - 全局状态清理

`LiteratureHarvester` 类封装了原先的全局状态：
- `_config` → `self.config`
- `SESSION` → `self.session`
- `_OPENALEX_BUDGET_EXHAUSTED` → 模块级（openalex.py 内）
- `_LAST_SOURCE_STATS` → `etl_ensemble/sources/base.py` 模块级

### P2 - 依赖清理

从 `requirements.txt` 移除：
- `aiohttp>=3.9`（未实际使用）

### P2 - 单元测试

新增 `tests/` 目录，包含：

| 测试文件 | 覆盖模块 | 测试数 |
|---------|---------|--------|
| `test_base.py` | sources/base.py | ~30 |
| `test_consensus.py` | consensus_engine.py | ~15 |
| `test_dataset.py` | build_clean_dataset.py | ~15 |
| `test_quality.py` | quality_control.py | ~8 |
| `test_pdf_parser.py` | pdf_parser.py | ~10 |

运行：`pytest tests/ -v`

### P3 - 完善 `human_review_manager.py`

扩展为完整的审核管理模块：
- `save_review_case()` - 保存审核案例
- `load_pending_reviews()` - 加载待审核案例
- `mark_reviewed()` - 标记已审核
- `get_review_stats()` - 审核统计
- `export_review_report()` - 导出审核报告

## New File Structure

```
DATA-Download_Extraction/
├── harvest_literature.py          # 薄入口 (15 行)
├── run_staged_extraction.py       # LLM 提取主流程 (logging 已替换)
├── quality_control.py             # 质量控制 (logging 已替换)
├── build_clean_dataset.py         # 数据集构建 (logging 已替换)
├── logging_config.py              # [NEW] 日志配置
├── requirements.txt               # [UPDATED] 移除 aiohttp
├── REFACTORING.md                 # [NEW] 本文件
├── configs/
│   ├── harvest/harvest_config.yml
│   └── extraction/
│       ├── llm_backends.yml
│       ├── schema.yml
│       ├── patterns.yml
│       └── stages/
├── etl_ensemble/
│   ├── __init__.py                # [UPDATED]
│   ├── harvester.py               # [NEW] LiteratureHarvester 类
│   ├── downloader.py              # [NEW] PDF 下载模块
│   ├── pdf_checker.py             # [NEW] PDF 校验模块
│   ├── sources/                   # [NEW] 数据源模块
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── openalex.py
│   │   ├── wos.py
│   │   ├── semantic_scholar.py
│   │   ├── pubmed.py
│   │   ├── arxiv.py
│   │   └── crossref.py
│   ├── pdf_parser.py
│   ├── llm_openai_client.py       # [UPDATED] 延迟加载
│   ├── llm_multi_client.py        # [UPDATED] logging
│   ├── consensus_engine.py
│   ├── focused_reextractor.py     # [UPDATED] logging
│   └── human_review_manager.py    # [UPDATED] 扩展功能
├── tests/                         # [NEW] 单元测试
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_base.py
│   ├── test_consensus.py
│   ├── test_dataset.py
│   ├── test_quality.py
│   └── test_pdf_parser.py
└── outputs/
```

## Migration Notes

- **无破坏性变更**：所有原有入口点保持兼容
- `harvest_literature.py` 的 `main()` 函数仍然可用
- `run_staged_extraction.py` 和 `build_clean_dataset.py` 的接口不变
- 配置文件格式不变
