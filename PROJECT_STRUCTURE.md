# 项目结构说明

## 概述

NFP-PDF-to-DB 是一个纳米荧光探针文献数据自动化提取系统，实现了从文献检索、PDF下载到结构化数据提取的完整流水线。

## 目录结构

```
DATA-Download_Extraction/
├── .git/                          # Git版本控制
├── .gitignore                     # Git忽略文件
├── README.md                      # 项目说明文档
├── PROJECT_STRUCTURE.md           # 项目结构说明（本文件）
│
├── configs/                       # 配置文件目录
│   ├── harvest/                   # 文献检索配置
│   │   └── harvest_config.yml     # 主配置文件
│   └── extraction/                # 信息提取配置
│       ├── llm_backends.yml       # LLM后端配置
│       ├── schema.yml             # 数据Schema定义
│       └── stages/                # 提取阶段配置
│           ├── stage1_core_extraction.md
│           └── stage2_figure_analysis.md
│
├── etl_ensemble/                  # 核心模块目录
│   ├── __init__.py                # 包初始化
│   ├── harvester.py               # 文献收割器
│   ├── downloader.py              # PDF下载器
│   ├── pdf_parser.py              # PDF解析器
│   ├── consensus_engine.py        # 共识引擎
│   ├── llm_multi_client.py        # 多模型客户端
│   ├── llm_openai_client.py       # OpenAI客户端
│   ├── focused_reextractor.py     # 聚焦重提取
│   ├── human_review_manager.py    # 人工审核管理
│   ├── model_accuracy.py          # 模型准确度评估
│   ├── pdf_checker.py             # PDF检查器
│   └── sources/                   # 数据源模块
│       ├── __init__.py
│       ├── base.py                # 基础工具
│       ├── openalex.py            # OpenAlex API
│       ├── wos.py                 # Web of Science
│       ├── semantic_scholar.py    # Semantic Scholar
│       ├── pubmed.py              # PubMed
│       ├── arxiv.py               # arXiv
│       └── crossref.py            # Crossref
│
├── outputs/                       # 输出目录
│   └── literature/                # 文献数据输出
│       ├── PDF/                   # 下载的PDF文件
│       ├── nano_fluorescent_probes.xlsx  # 元数据Excel
│       ├── _checkpoint.xlsx       # 检查点文件
│       ├── filtered_out_audit.xlsx # 过滤审计
│       ├── duplicates/            # 重复文件备份
│       └── invalid_backup/        # 无效文件备份
│
├── test/                          # 测试和分析目录
│   ├── README.md                  # 测试目录说明
│   ├── analysis/                  # 分析结果输出
│   ├── advanced_pdf_analyzer.py   # 高级PDF分析器
│   ├── analyze_pdf_final.py       # PDF分析脚本
│   ├── analyze_pdf_quality.py     # PDF质量分析
│   ├── analyze_pdf_quality_pypdf2.py # PyPDF2版本
│   ├── analyze_pdf_quality_simple.py # 简单版本
│   ├── analyze_pdf_with_strings.py # strings版本
│   ├── check_pdf_content.py       # PDF内容检查
│   ├── check_tools.py             # 工具检查
│   ├── anti_ban.py                # 反封锁模块
│   ├── downloader_enhanced.py     # 增强下载器
│   ├── harvest_config_optimized.yml # 优化配置
│   ├── harvest_config_optimized_v2.yml # 优化配置v2
│   ├── patterns.yml               # 模式配置
│   ├── stages/                    # 阶段配置
│   ├── OPTIMIZATION_GUIDE.md      # 优化指南
│   ├── ANTI_BAN_GUIDE.md          # 反封锁指南
│   └── PDF_QUALITY_FINAL_REPORT.md # 质量分析报告
│
├── build_clean_dataset.py         # 数据集构建
├── harvest_literature.py          # 文献收割入口
├── logging_config.py              # 日志配置
├── quality_control.py             # 质量控制
├── run_staged_extraction.py       # 分阶段提取
└── requirements.txt               # Python依赖
```

## 核心模块说明

### 1. 入口文件

- **harvest_literature.py** - 文献收割入口
  - 从多个学术数据库检索文献
  - 自动去重和合并结果
  - 通过Unpaywall获取开放获取PDF

- **run_staged_extraction.py** - 信息提取入口
  - 使用多个大语言模型并行提取
  - 支持OpenAI GPT、Google Gemini、DeepSeek、Grok
  - 分阶段提取：核心字段和图表分析

- **quality_control.py** - 质量控制模块
  - 三层质量控制：关键词、主题、元数据
  - 过滤低质量文献

- **build_clean_dataset.py** - 数据集构建
  - 从提取结果构建ML-ready数据集
  - 数据清洗和特征工程

### 2. 核心模块 (etl_ensemble/)

- **harvester.py** - 文献收割器
  - 协调多个数据源的搜索
  - 合并和去重结果
  - 填充缺失的DOI

- **downloader.py** - PDF下载器
  - 并发下载支持
  - 检查点保存
  - 磁盘空间监控

- **pdf_parser.py** - PDF解析器
  - 使用pdfplumber和PyMuPDF
  - 提取文本、表格、图像
  - 支持OCR集成

- **consensus_engine.py** - 共识引擎
  - 比较多个模型的输出
  - 使用字段特定的容差
  - 支持源权重和模型权重

- **llm_multi_client.py** - 多模型客户端
  - 统一调用多个LLM后端
  - 支持OpenAI、Gemini、DeepSeek、Grok
  - 自动回退机制

### 3. 数据源模块 (etl_ensemble/sources/)

- **openalex.py** - OpenAlex API
- **wos.py** - Web of Science
- **semantic_scholar.py** - Semantic Scholar
- **pubmed.py** - PubMed
- **arxiv.py** - arXiv
- **crossref.py** - Crossref + Unpaywall

## 配置文件说明

### 1. 文献检索配置 (configs/harvest/harvest_config.yml)

```yaml
api_keys:
  openalex: "your_api_key"
  wos: "your_api_key"
  semantic_scholar: "your_api_key"
  contact_email: "your_email@example.com"

search:
  keywords: |
    ("nano fluorescent probe") OR 
    ("nanoscale fluorescent probe") OR ...
  sources_order: [openalex, wos, semantic_scholar, pubmed, arxiv, crossref]
  year_from: 2000
  year_to: 2028
  max_results_per_clause: 2000
  max_total: 50000

runtime:
  incremental: true
  requests_per_second: 0.3
  max_concurrent_downloads: 4
  download_retries: 3

quality:
  enabled: true
  min_relevance: 0.3
  min_completeness: 0.5
  min_overall: 0.4
```

### 2. LLM后端配置 (configs/extraction/llm_backends.yml)

```yaml
models:
  - id: xiaomi_mimo_omni
    provider: openai
    model_name: mimo-v2-flash
    api_key_env: sk-cyn...nsyj
    base_url: https://api.xiaomimimo.com/v1
    enabled: true
  - id: openai_chatgpt
    provider: openai
    model_name: gpt-3.5-turbo-0125
    api_key_env: sk-pro...Tx8A
    enabled: false
```

### 3. 数据Schema (configs/extraction/schema.yml)

```yaml
version: 3.0.0

paper_meta:
  - {name: title, type: str, desc: "Paper Title"}
  - {name: doi, type: str, desc: "DOI"}
  - {name: year, type: int, desc: "Year of Publication"}

probe_features:
  - {name: core_material, type: str, desc: "Core material/composition"}
  - {name: shell_or_dopant, type: str, desc: "Shell material or dopant"}
  - {name: surface_ligands_modifiers, type: str, desc: "Surface ligands"}
  - {name: size_nm, type: float, unit: nm, desc: "Average size"}
  - {name: excitation_wavelength_nm, type: float, unit: nm, desc: "Excitation wavelength"}
  - {name: emission_wavelength_nm, type: float, unit: nm, desc: "Emission wavelength"}
  - {name: quantum_yield_percent, type: float, unit: "%", desc: "Quantum yield"}
  - {name: target_analyte, type: str, desc: "Target analyte"}
  - {name: limit_of_detection, type: str, desc: "Limit of Detection"}
  - {name: test_solvent_or_medium, type: str, desc: "Testing medium"}
  - {name: response_type, type: enum, enum: [turn-on, turn-off, ratiometric, other]}
  - {name: linear_range, type: str, desc: "Linear detection range"}
```

## 使用方法

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置API密钥

编辑 `configs/harvest/harvest_config.yml` 和 `configs/extraction/llm_backends.yml`

### 3. 运行文献收割

```bash
python harvest_literature.py
```

### 4. 运行信息提取

```bash
python run_staged_extraction.py --pdf_dir outputs/literature/PDF --out_dir outputs/extraction
```

### 5. 构建数据集

```bash
python build_clean_dataset.py outputs/extraction outputs/nfp_ml_ready_dataset.csv
```

## 测试和分析

测试和分析相关的文件都存放在 `test/` 目录下：

```bash
cd test

# 检查可用工具
python3 check_tools.py

# 运行PDF分析
python3 advanced_pdf_analyzer.py

# 查看分析结果
ls analysis/
```

## 输出文件说明

### 1. 文献收割输出 (outputs/literature/)

- `nano_fluorescent_probes.xlsx` - 元数据Excel文件
- `PDF/` - 下载的PDF文件目录
- `_checkpoint.xlsx` - 检查点文件
- `filtered_out_audit.xlsx` - 过滤审计文件

### 2. 信息提取输出 (outputs/extraction/)

- `{pdf_name}.json` - 每个PDF的提取结果
- 包含paper_metadata和samples数组

### 3. 数据集输出

- `nfp_ml_ready_dataset.csv` - ML-ready数据集

## 注意事项

1. **API密钥**：请妥善保管API密钥，不要提交到版本控制
2. **磁盘空间**：PDF下载会占用大量磁盘空间
3. **网络连接**：需要稳定的网络连接访问学术数据库
4. **速率限制**：注意各API的速率限制，避免被封锁
5. **版权合规**：仅用于学术研究，尊重版权

## 联系方式

- 邮箱: wangqi@ahut.edu.cn
- 项目地址: https://github.com/your-repo/nfp-pdf-to-db

---

**最后更新**：2026-04-13
**版本**：1.0