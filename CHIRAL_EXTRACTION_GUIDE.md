# 手性纳米荧光探针数据提取指南

## 概述

本指南介绍如何使用修改后的系统提取手性纳米荧光探针的结构化数据，构建机器学习数据集。

## 系统架构

```
文献检索 → PDF下载 → 数据提取 → 数据集构建
    ↓           ↓           ↓           ↓
harvest_config_chiral.yml  PDF文件  run_chiral_extraction.py  build_chiral_dataset.py
```

## 文件说明

### 1. 配置文件

- **configs/harvest/harvest_config_chiral.yml** - 手性纳米荧光探针文献检索配置
  - 包含18种检索关键词组合
  - 覆盖：手性量子点、手性碳点、手性聚合物点等

- **configs/extraction/schema_chiral.yml** - 手性探针数据Schema
  - 定义了60+个字段
  - 包含手性属性、材料组成、光学性能等

- **configs/extraction/stages/stage1_chiral_extraction.md** - 提取提示词
  - 专门针对手性探针设计
  - 包含详细的提取指南和示例

### 2. 提取代码

- **run_chiral_extraction.py** - 手性探针提取入口
  - 使用新的schema_chiral.yml
  - 自动提取手性相关字段
  - 支持多种LLM模型

- **build_chiral_dataset.py** - 数据集构建脚本
  - 处理手性相关字段编码
  - 生成ML-ready数据集

## 使用步骤

### 步骤1：检索手性纳米荧光探针文献

```bash
# 使用手性探针专用配置
cp configs/harvest/harvest_config_chiral.yml configs/harvest/harvest_config.yml

# 运行文献检索
python harvest_literature.py
```

**检索结果将保存在**: `outputs/chiral_literature/`

### 步骤2：下载PDF文件

文献检索完成后，系统会自动下载PDF文件到：
```
outputs/chiral_literature/PDF/
```

### 步骤3：提取手性探针数据

```bash
# 运行手性探针数据提取
python run_chiral_extraction.py \
    --pdf_dir outputs/chiral_literature/PDF \
    --out_dir outputs/chiral_extraction \
    --schema configs/extraction/schema_chiral.yml
```

**提取结果将保存在**: `outputs/chiral_extraction/`

每个PDF会生成一个JSON文件，包含：
- paper_metadata: 论文元数据
- samples: 手性探针样本数组

### 步骤4：构建机器学习数据集

```bash
# 构建ML-ready数据集
python build_chiral_dataset.py \
    outputs/chiral_extraction \
    outputs/chiral_nanoprobes_ml_dataset.csv
```

**数据集将保存在**: `outputs/chiral_nanoprobes_ml_dataset.csv`

## 数据Schema详解

### 手性属性字段（核心新增）

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| chiral_type | enum | 手性类型 | R, S, D, L, (+), (-), racemic |
| chiral_source | string | 手性来源 | L-cysteine, BINOL, chiral polymer |
| chiral_center_count | int | 手性中心数量 | 1, 2 |
| enantioselectivity_factor | float | 对映选择性因子 | 2.5, 10.3 |
| chiral_recognition_mechanism | string | 识别机制 | hydrogen bonding, π-π stacking |
| glum_value | float | 发光不对称因子 | 0.02, -0.015 |
| cpl_wavelength_nm | float | CPL波长 | 520, 650 |

### 探针组成字段

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| core_material | string | 核心材料 | CdTe, Carbon dot, Au, NaYF4 |
| chiral_ligand | string | 手性配体 | L-cysteine, D-penicillamine |
| size_nm | float | 粒径 | 3.5, 50.0 |
| morphology | string | 形貌 | spherical, rod, dot |

### 检测应用字段

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| target_analyte | string | 目标分析物 | D-cysteine, L-alanine, Fe3+ |
| target_enantiomer | enum | 目标对映体 | R, S, D, L, both, achiral |
| analyte_category | enum | 分析物类别 | amino_acid, drug, metal_ion |
| limit_of_detection | string | 检测限 | 0.1 nM, 1.2 μM |
| response_type | enum | 响应类型 | turn-on, turn-off, cpl_on |

## 数据集字段说明

构建的数据集包含以下类型的字段：

### 1. 数值型字段（直接用于ML）
- size_nm: 粒径
- excitation_wavelength_nm: 激发波长
- emission_wavelength_nm: 发射波长
- quantum_yield_percent: 量子产率
- enantioselectivity_factor: 对映选择性因子
- glum_value: 发光不对称因子
- chiral_center_count: 手性中心数量

### 2. One-hot编码字段
- chiral_type_R, chiral_type_S, chiral_type_D, chiral_type_L: 手性类型
- category_amino_acid, category_drug, category_metal_ion: 分析物类别
- response_turn_on, response_turn_off, response_cpl_on: 响应类型

### 3. 分类型字段
- core_material_type: 核心材料类型（quantum_dot, carbon_dot, gold, silver等）
- chiral_source: 手性来源（L-cysteine, BINOL等）

### 4. 文本型字段
- target_analyte: 目标分析物
- selectivity: 选择性描述
- chiral_recognition_mechanism: 识别机制

## 机器学习应用

### 可以构建的预测模型

1. **手性探针材料预测**
   - 输入：目标分析物、检测条件
   - 输出：推荐的核心材料、手性配体

2. **检测性能预测**
   - 输入：探针组成、手性类型
   - 输出：预期的检测限、选择性

3. **光学性能预测**
   - 输入：材料组成、手性修饰
   - 输出：发射波长、量子产率、glum值

4. **对映选择性预测**
   - 输入：探针结构、分析物结构
   - 输出：预期的对映选择性因子

### 特征工程建议

1. **手性相关特征**
   - 手性类型编码
   - 手性中心数量
   - 手性来源分类

2. **材料特征**
   - 核心材料类型
   - 粒径
   - 表面修饰

3. **光学特征**
   - 激发/发射波长
   - Stokes位移
   - 量子产率

4. **应用特征**
   - 分析物类别
   - 响应类型
   - 检测环境

## 注意事项

### 1. 数据质量
- 手性相关字段的提取准确率可能较低
- 建议人工审核高价值数据
- glum值等专业参数可能需要验证

### 2. 字段缺失
- 不是所有探针都包含所有字段
- 手性来源是必需字段
- 对映选择性因子可能为空

### 3. 数据平衡
- 不同手性类型的样本可能不平衡
- 不同材料类型的样本可能不平衡
- 需要在训练时考虑采样策略

## 示例数据

### 示例1：L-半胱氨酸修饰的CdTe量子点

```json
{
  "sample_id": "L-Cys-CdTe_QD",
  "chiral_type": "L",
  "chiral_source": "L-cysteine",
  "chiral_center_count": 1,
  "enantioselectivity_factor": 3.2,
  "core_material": "CdTe",
  "chiral_ligand": "L-cysteine",
  "size_nm": 3.5,
  "emission_wavelength_nm": 540,
  "quantum_yield_percent": 45.0,
  "target_analyte": "D-cysteine",
  "target_enantiomer": "D",
  "analyte_category": "amino_acid",
  "limit_of_detection": "0.5 μM",
  "response_type": "turn-on"
}
```

### 示例2：具有CPL的手性碳点

```json
{
  "sample_id": "CD-L-Trp",
  "chiral_type": "L",
  "chiral_source": "L-tryptophan",
  "glum_value": 0.012,
  "cpl_wavelength_nm": 480,
  "core_material": "Carbon dot",
  "chiral_ligand": "L-tryptophan",
  "size_nm": 4.2,
  "emission_wavelength_nm": 480,
  "target_analyte": "naproxen",
  "target_enantiomer": "S",
  "analyte_category": "drug",
  "response_type": "cpl_on"
}
```

## 故障排除

### 1. 检索不到文献
- 检查API密钥是否正确
- 尝试调整关键词组合
- 检查网络连接

### 2. 提取失败
- 检查PDF是否可读
- 确认LLM模型配置正确
- 查看日志文件获取详细错误

### 3. 数据集为空
- 确认JSON文件存在
- 检查mandatory字段是否满足
- 查看过滤日志

## 联系方式

如有问题，请联系：
- 邮箱: wangqi@ahut.edu.cn

---

**最后更新**: 2026-04-13
**版本**: 1.0