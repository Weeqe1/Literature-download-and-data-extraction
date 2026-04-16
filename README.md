# 手性纳米荧光探针数据库构建系统
# Chiral Nanoprobe Database Builder

## 概述

本系统用于自动化构建手性纳米荧光探针数据库，支持从科学文献中提取结构化数据，用于机器学习研究。

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置API密钥

编辑 `configs/harvest/harvest_config.yml`，填入您的API密钥：

```yaml
api_keys:
  openalex: "your_api_key"
  wos: "your_api_key"
  semantic_scholar: "your_api_key"
  contact_email: "your_email@example.com"
```

### 3. 运行程序

```bash
python main.py
```

## 项目结构

```
DATA-Download_Extraction/
├── main.py                    # 主入口（交互式工作流程）
├── README.md                  # 项目说明
├── requirements.txt           # Python依赖
│
├── configs/                   # 配置文件
│   ├── harvest/               # 文献检索配置
│   └── extraction/            # 数据提取配置
│
├── scripts/                   # 核心脚本
│   ├── harvest_literature.py  # 文献检索与下载
│   ├── run_chiral_extraction_v2.py # 数据提取
│   ├── build_chiral_dataset.py # 数据集构建
│   ├── quality_control.py     # 质量控制
│   ├── analyze_logs.py        # 日志分析
│   └── logging_config.py      # 日志配置
│
├── etl_ensemble/              # 核心功能模块
│   ├── harvester.py           # 文献收割器
│   ├── downloader.py          # PDF下载器
│   ├── pdf_parser.py          # PDF解析器
│   ├── consensus_engine.py    # 共识引擎
│   ├── llm_multi_client.py    # 多模型客户端
│   └── sources/               # 数据源模块
│
├── docs/                      # 文档
│   ├── PROJECT_STRUCTURE.md   # 项目结构说明
│   ├── CHIRAL_EXTRACTION_GUIDE.md # 手性提取指南
│   └── EXTRACTION_OPTIMIZATION.md # 优化指南
│
├── outputs/                   # 输出目录
│   └── literature/            # 文献下载结果
│       ├── PDF/               # PDF文件
│       └── *.csv              # 元数据
│
└── logs/                      # 日志目录
```   ├── pdf_parser.py                # PDF解析器
│   ├── anti_ban.py                  # 反封锁模块
│   ├── llm_multi_client.py          # 多模型客户端
│   ├── llm_openai_client.py         # OpenAI客户端
│   ├── consensus_engine.py          # 共识引擎
│   ├── pdf_checker.py               # PDF检查器
│   └── sources/                     # 数据源模块
│       ├── openalex.py
│       ├── wos.py
│       ├── semantic_scholar.py
│       ├── pubmed.py
│       ├── arxiv.py
│       └── crossref.py
│
├── configs/                         # 配置文件
│   ├── harvest/
│   │   └── harvest_config.yml       # 文献检索配置
│   └── extraction/
│       ├── llm_backends.yml         # LLM配置
│       ├── schema_chiral.yml        # 数据Schema
│       └── stages/
│           └── stage1_chiral_extraction_v2.md  # 提取提示词
│
├── outputs/                         # 输出目录
│   └── literature/                  # 文献下载输出
│
├── logs/                            # 运行日志
│
├── README.md                        # 本文件
├── PROJECT_STRUCTURE.md             # 项目结构详细说明
├── CHIRAL_EXTRACTION_GUIDE.md       # 数据提取指南
├── EXTRACTION_OPTIMIZATION.md       # 优化说明
├── requirements.txt                 # Python依赖
└── .gitignore                       # Git忽略文件
```

## 工作流程

### 使用 main.py（推荐）

```bash
python main.py
```

程序会显示交互式菜单：

```
请选择要执行的操作：
----------------------------------------
  [1] 文献检索与PDF下载
  [2] 数据提取与数据集构建
  [3] 查看运行状态和统计
  [4] 分析运行日志
  [0] 退出程序
----------------------------------------
```

### 手动运行各个步骤

#### 步骤1：文献检索与下载

```bash
python harvest_literature.py
```

- 从6个学术数据库检索文献
- 自动下载PDF文件
- 结果保存在 `outputs/literature/`

#### 步骤2：数据提取

```bash
python run_chiral_extraction_v2.py \
    --pdf_dir outputs/literature/PDF \
    --out_dir outputs/chiral_extraction \
    --workers 4 \
    --resume
```

参数说明：
- `--pdf_dir`: PDF文件目录
- `--out_dir`: 输出目录
- `--workers`: 并行worker数量
- `--resume`: 启用断点续传

#### 步骤3：构建数据集

```bash
python build_chiral_dataset.py \
    outputs/chiral_extraction \
    outputs/chiral_nanoprobes_ml_dataset.csv
```

## 数据Schema

系统提取46个字段，分为8个类别：

| 类别 | 字段数 | 示例字段 |
|------|--------|----------|
| 论文元数据 | 4 | title, doi, year, journal |
| 手性属性 | 8 | chiral_type, chiral_source, glum_value |
| 探针组成 | 7 | core_material, chiral_ligand, size_nm |
| 光学性能 | 7 | emission_wavelength_nm, quantum_yield_percent |
| 检测应用 | 8 | target_analyte, limit_of_detection |
| 实验条件 | 4 | test_solvent_or_medium, ph_value |
| 合成方法 | 4 | synthesis_method, synthesis_temperature_celsius |
| 应用场景 | 4 | application_type, in_vivo_or_in_vitro |

## 优化特性

### 数据提取优化

- ✅ **断点续传**：支持中断后继续
- ✅ **并行处理**：4-8个worker同时处理
- ✅ **数据验证**：自动验证提取数据质量
- ✅ **LLM重试**：失败自动重试3次
- ✅ **详细日志**：记录每次提取

### Ensemble提取（新增）

系统支持**多模型ensemble提取**，通过多个LLM模型并行处理同一PDF，然后通过共识算法合并结果，显著提高提取准确性和可靠性。

#### 配置方式

在 `configs/extraction/llm_backends.yml` 中配置：

```yaml
ensemble:
  enabled: true  # 启用ensemble模式
  strategy: "majority_vote"  # 共识策略
  min_agreement: 0.6  # 最小共识阈值 (60%)
  max_workers: 4  # 最大并行worker数
  output_format: "consensus"  # 输出格式
```

#### 共识策略

1. **majority_vote** - 多数投票（默认）
   - 每个字段取出现最多的值
   - 需要至少60%模型达成共识

2. **weighted_vote** - 加权投票
   - 根据模型历史准确率加权
   - 权重自动从模型性能日志中学习

3. **confidence_based** - 基于置信度
   - 选择置信度最高的结果
   - 置信度基于字段完整性和一致性

#### 输出格式

- `consensus` - 只输出共识结果（默认）
- `individual` - 保存每个模型的单独结果
- `all` - 保存所有结果（共识 + 单独）

#### 日志记录

Ensemble过程会记录详细的日志到：
- `logs/ensemble_<timestamp>.log` - 主日志
- `outputs/ensemble_comparison/` - 对比报告目录

#### 使用示例

```bash
# 使用ensemble模式运行提取
python run_chiral_extraction_v2.py \
    --pdf_dir outputs/literature/PDF \
    --out_dir outputs/chiral_extraction \
    --workers 4 \
    --resume \
    --ensemble

# 查看ensemble对比报告
python analyze_ensemble_logs.py
```

### 性能对比

| 指标 | 原版 | 优化版 | Ensemble |
|------|------|--------|----------|
| 处理时间（410个PDF） | ~5小时 | ~1.25小时 | ~2小时 |
| API成本 | ~$100 | ~$50 | ~$80 |
| 准确性 | 中等 | 高 | 非常高 |
| 断点续传 | ❌ | ✅ | ✅ |
| 并行处理 | ❌ | ✅ | ✅ |

## 日志分析

查看运行日志：

```bash
python analyze_logs.py
```

或使用main.py中的日志分析功能。

## 故障排查

### 1. 文献检索失败

检查API密钥配置：
```bash
cat configs/harvest/harvest_config.yml
```

### 2. 数据提取失败

检查LLM配置：
```bash
cat configs/extraction/llm_backends.yml
```

### 3. 查看详细日志

```bash
ls -lt logs/
cat logs/harvest_*.log
```

## 文档

- `PROJECT_STRUCTURE.md` - 详细的项目结构说明
- `CHIRAL_EXTRACTION_GUIDE.md` - 数据提取详细指南
- `EXTRACTION_OPTIMIZATION.md` - 优化说明

## 许可证

MIT License

---

**最后更新**: 2026-04-16