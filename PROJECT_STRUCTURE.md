# 项目结构说明

## 目录结构

```
DATA-Download_Extraction/
├── main.py                          # 主入口（交互式工作流程）
├── README.md                        # 项目说明
├── requirements.txt                 # Python依赖
├── PROJECT_STRUCTURE.md             # 本文件
│
├── configs/                         # 配置文件
│   ├── harvest/
│   │   └── harvest_config.yml       # 文献检索配置
│   └── extraction/
│       ├── llm_backends.yml         # LLM配置（含ensemble配置）
│       ├── schema_chiral.yml        # 数据Schema
│       └── stages/
│           └── stage1_chiral_extraction_v2.md  # 提取提示词
│
├── scripts/                         # 核心脚本
│   ├── harvest_literature.py        # 文献检索与下载
│   ├── run_chiral_extraction_v2.py  # 数据提取（支持ensemble）
│   ├── build_chiral_dataset.py      # 数据集构建
│   ├── logging_config.py            # 日志配置
│   └── analyze_logs.py              # 日志分析
│
├── etl_ensemble/                    # 核心功能模块
│   ├── harvester.py                 # 文献收割器
│   ├── downloader.py                # PDF下载器
│   ├── pdf_parser.py                # PDF解析器
│   ├── consensus_engine.py          # 共识引擎
│   ├── llm_multi_client.py          # 多模型客户端
│   └── sources/                     # 数据源模块
│
├── outputs/                         # 输出目录
│   ├── literature/                  # 文献下载结果
│   │   ├── PDF/                     # PDF文件
│   │   └── *.csv                    # 元数据
│   ├── chiral_extraction/           # 数据提取结果
│   └── ensemble_comparison/         # Ensemble对比报告
│
└── logs/                            # 日志目录
    ├── main_*.log                   # 主程序日志
    ├── harvest_*.log                # 文献检索日志
    └── ensemble_*.log               # Ensemble日志
```

## 核心模块说明

### 1. 文献检索模块

- **harvest_literature.py**: 主入口，协调文献检索和下载
- **etl_ensemble/harvester.py**: 文献收割器，支持多数据源
- **etl_ensemble/downloader.py**: PDF下载器，支持断点续传

### 2. 数据提取模块

- **run_chiral_extraction_v2.py**: 数据提取主脚本
- **etl_ensemble/pdf_parser.py**: PDF解析器
- **etl_ensemble/llm_multi_client.py**: 多模型客户端
- **etl_ensemble/consensus_engine.py**: Ensemble共识引擎

### 3. 数据集构建模块

- **build_chiral_dataset.py**: 构建机器学习数据集

### 4. 日志和分析模块

- **scripts/logging_config.py**: 统一日志配置
- **scripts/analyze_logs.py**: 日志分析工具

## Ensemble功能

### 配置文件

`configs/extraction/llm_backends.yml` 包含ensemble配置：

```yaml
ensemble:
  enabled: true
  strategy: "majority_vote"  # 共识策略
  min_agreement: 0.6         # 最小共识阈值
  max_workers: 4             # 最大并行worker数
  output_format: "consensus" # 输出格式
```

### 共识策略

1. **majority_vote**: 多数投票
2. **weighted_vote**: 加权投票
3. **confidence_based**: 基于置信度

### 输出文件

- `outputs/ensemble_comparison/comparison_*..json`: 对比报告
- `logs/ensemble_*.log`: Ensemble日志

## 工作流程

### 1. 文献检索

```bash
python main.py
# 选择 [1] 文献检索与PDF下载
```

### 2. 数据提取（Ensemble模式）

```bash
python run_chiral_extraction_v2.py \
    --pdf_dir outputs/literature/PDF \
    --out_dir outputs/chiral_extraction \
    --workers 4 \
    --resume \
    --ensemble
```

### 3. 查看Ensemble对比

```bash
python main.py
# 选择 [5] Ensemble对比分析
```

## 日志系统

### 日志文件

- `logs/main_*.log`: 主程序日志
- `logs/harvest_*.log`: 文献检索日志
- `logs/ensemble_*.log`: Ensemble操作日志

### 日志查看

```bash
# 查看最新日志
ls -lt logs/

# 分析日志
python analyze_logs.py
```

## 配置说明

### harvest_config.yml

- API密钥配置
- 搜索关键词和参数
- 输出设置
- 运行时参数

### llm_backends.yml

- LLM模型配置
- Ensemble参数
- 共识策略设置

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

### 3. Ensemble问题

查看Ensemble日志：
```bash
cat logs/ensemble_*.log
```

## 更新日志

### 2026-04-16
- 添加Ensemble提取功能
- 添加多模型共识引擎
- 添加Ensemble对比分析功能
- 更新日志系统支持Ensemble日志

---

**最后更新**: 2026-04-16
