# 项目结构说明

## 概述

手性纳米荧光探针数据库构建系统，实现了从文献检索、PDF下载到结构化数据提取的完整流水线。

## 目录结构

```
DATA-Download_Extraction/
├── main.py                    # 主入口，交互式工作流程
├── README.md                  # 项目说明文档
├── requirements.txt           # Python依赖
├── .gitignore                 # Git忽略文件
│
├── configs/                   # 配置文件目录
│   ├── harvest/               # 文献检索配置
│   │   └── harvest_config.yml # 主配置文件
│   └── extraction/            # 信息提取配置
│       ├── llm_backends.yml   # LLM后端配置
│       ├── schema_chiral.yml  # 数据Schema定义
│       └── stages/            # 提取阶段配置
│           └── stage1_chiral_extraction_v2.md
│
├── scripts/                   # 脚本目录
│   ├── harvest_literature.py  # 文献下载入口
│   ├── run_chiral_extraction_v2.py # 数据提取
│   ├── build_chiral_dataset.py # 数据集构建
│   ├── analyze_logs.py        # 日志分析
│   ├── quality_control.py     # 质量控制
│   └── logging_config.py      # 日志配置
│
├── etl_ensemble/              # 核心模块目录
│   ├── __init__.py            # 包初始化
│   ├── harvester.py           # 文献收割器
│   ├── downloader.py          # PDF下载器
│   ├── pdf_parser.py          # PDF解析器
│   ├── consensus_engine.py    # 共识引擎
│   ├── llm_multi_client.py    # 多模型客户端
│   ├── llm_openai_client.py   # OpenAI客户端
│   ├── pdf_checker.py         # PDF检查器
│   ├── anti_ban.py            # 反封锁模块
│   └── sources/               # 数据源模块
│       ├── __init__.py
│       ├── base.py            # 基础工具
│       ├── openalex.py        # OpenAlex API
│       ├── wos.py             # Web of Science
│       ├── semantic_scholar.py # Semantic Scholar
│       ├── pubmed.py          # PubMed
│       ├── arxiv.py           # arXiv
│       └── crossref.py        # Crossref
│
├── docs/                      # 文档目录
│   ├── PROJECT_STRUCTURE.md   # 项目结构说明（本文件）
│   ├── CHIRAL_EXTRACTION_GUIDE.md # 手性提取指南
│   └── EXTRACTION_OPTIMIZATION.md # 提取优化指南
│
├── outputs/                   # 输出目录
│   └── literature/            # 文献数据输出
│       ├── PDF/               # 下载的PDF文件
│       ├── nano_fluorescent_probes.csv # 元数据CSV
│       └── _checkpoint.csv    # 检查点文件
│
└── logs/                      # 日志目录
```

## 核心模块说明

### 1. 入口文件

- **main.py** - 主入口，提供交互式工作流程菜单
  - 文献检索与PDF下载
  - 数据提取与数据集构建
  - 运行状态查看
  - 日志分析

- **scripts/harvest_literature.py** - 文献下载入口
  - 从多个学术数据库检索文献
  - 自动去重和合并结果
  - 通过Unpaywall获取开放获取PDF

- **scripts/run_chiral_extraction_v2.py** - 数据提取入口
  - 使用多个大语言模型并行提取
  - 支持断点续传和并行处理
  - 数据验证和质量检查

- **scripts/build_chiral_dataset.py** - 数据集构建
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

## 使用方法

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置API密钥

编辑 `configs/harvest/harvest_config.yml` 和 `configs/extraction/llm_backends.yml`

### 3. 运行系统

```bash
python3 main.py
```

然后按照交互式菜单选择操作：
1. 文献检索与PDF下载
2. 数据提取与数据集构建
3. 查看运行状态和统计
4. 分析运行日志

### 4. 单独运行各模块

```bash
# 文献下载
python3 scripts/harvest_literature.py

# 数据提取
python3 scripts/run_chiral_extraction_v2.py --pdf_dir outputs/literature/PDF --out_dir outputs/chiral_extraction

# 数据集构建
python3 scripts/build_chiral_dataset.py outputs/chiral_extraction outputs/chiral_nanoprobes_ml_dataset.csv
```

## 输出文件说明

### 1. 文献下载输出 (outputs/literature/)

- `nano_fluorescent_probes.csv` - 元数据CSV文件
- `PDF/` - 下载的PDF文件目录
- `_checkpoint.csv` - 检查点文件

### 2. 数据提取输出 (outputs/chiral_extraction/)

- `{pdf_name}.json` - 每个PDF的提取结果
- 包含paper_metadata和samples数组

### 3. 数据集输出

- `outputs/chiral_nanoprobes_ml_dataset.csv` - ML-ready数据集

## 注意事项

1. **API密钥**：请妥善保管API密钥，不要提交到版本控制
2. **磁盘空间**：PDF下载会占用大量磁盘空间
3. **网络连接**：需要稳定的网络连接访问学术数据库
4. **速率限制**：注意各API的速率限制，避免被封锁
5. **版权合规**：仅用于学术研究，尊重版权

---

**最后更新**：2026-04-16
**版本**：2.0