# 测试文件夹 (test)

本文件夹用于存放测试代码、分析脚本和临时输出文件，以保持项目根目录的整洁。

## 文件夹结构

```
test/
├── analysis/                    # 分析结果输出目录
│   ├── pdf_quality_analysis.json
│   ├── pdf_quality_report.csv
│   └── ...
├── advanced_pdf_analyzer.py     # 高级PDF分析器
├── analyze_pdf_final.py         # PDF分析脚本（最终版）
├── analyze_pdf_quality.py       # PDF质量分析脚本
├── analyze_pdf_quality_pypdf2.py # PDF质量分析（PyPDF2版本）
├── analyze_pdf_quality_simple.py # 简单PDF质量分析
├── analyze_pdf_with_strings.py  # 使用strings的PDF分析
├── check_pdf_content.py         # 检查PDF内容
├── check_tools.py               # 检查可用工具
├── anti_ban.py                  # 反封锁模块
├── downloader_enhanced.py       # 增强的下载器
├── harvest_config_optimized.yml # 优化后的配置文件
├── harvest_config_optimized_v2.yml # 优化后的配置文件v2
├── patterns.yml                 # 模式匹配配置
├── stages/                      # 提取阶段配置
│   ├── stage1_core_extraction.md
│   └── stage2_figure_analysis.md
├── OPTIMIZATION_GUIDE.md        # 优化指南
├── ANTI_BAN_GUIDE.md            # 反封锁指南
└── PDF_QUALITY_FINAL_REPORT.md  # PDF质量分析最终报告
```

## 文件说明

### 分析脚本

1. **advanced_pdf_analyzer.py** - 高级PDF分析器
   - 使用纯Python实现，不依赖外部库
   - 支持多种文本提取方法
   - 可以提取PDF中的数值信息

2. **analyze_pdf_final.py** - PDF分析脚本（最终版）
   - 使用系统命令（file、strings）分析PDF
   - 生成详细的CSV报告

3. **analyze_pdf_quality.py** - PDF质量分析脚本
   - 基础版本的PDF分析脚本
   - 需要pdfplumber或PyMuPDF库

4. **analyze_pdf_quality_pypdf2.py** - PDF质量分析（PyPDF2版本）
   - 使用PyPDF2库的PDF分析脚本

5. **analyze_pdf_quality_simple.py** - 简单PDF质量分析
   - 简化版本的PDF分析脚本
   - 使用csv模块生成报告

6. **analyze_pdf_with_strings.py** - 使用strings的PDF分析
   - 使用strings命令提取PDF文本
   - 适合处理可提取文本的PDF

7. **check_pdf_content.py** - 检查PDF内容
   - 检查PDF文件是否有效
   - 分析PDF内部结构

8. **check_tools.py** - 检查可用工具
   - 检查系统中可用的PDF解析工具
   - 检查Python模块是否安装

### 核心模块

9. **anti_ban.py** - 反封锁模块
   - User-Agent轮换
   - 智能延迟
   - 代理支持

10. **downloader_enhanced.py** - 增强的下载器
    - 支持更多PDF下载源
    - 包括Sci-Hub、ResearchGate等

### 配置文件

11. **harvest_config_optimized.yml** - 优化后的配置文件
    - 针对低下载成功率的优化配置

12. **harvest_config_optimized_v2.yml** - 优化后的配置文件v2
    - 保持搜索结果数量，提高准确性

13. **patterns.yml** - 模式匹配配置
    - 字段别名和单位转换规则

14. **stages/** - 提取阶段配置
    - Stage 1: 核心12字段提取
    - Stage 2: 多模态图表分析

### 文档

15. **OPTIMIZATION_GUIDE.md** - 优化指南
    - 详细的优化方案说明
    - 使用方法和注意事项

16. **ANTI_BAN_GUIDE.md** - 反封锁指南
    - 反封锁机制详细说明
    - 配置参数和最佳实践

17. **PDF_QUALITY_FINAL_REPORT.md** - PDF质量分析最终报告
    - 所有PDF文件的质量分析结果
    - 推荐用于数据提取的文件列表

## 使用方法

### 运行PDF分析

```bash
# 进入test目录
cd test

# 运行高级PDF分析器
python3 advanced_pdf_analyzer.py

# 运行简单PDF分析
python3 analyze_pdf_with_strings.py

# 检查可用工具
python3 check_tools.py
```

### 查看分析结果

分析结果保存在 `test/analysis/` 目录下：
- `pdf_quality_analysis.json` - 详细JSON结果
- `pdf_quality_report.csv` - CSV格式报告

### 使用优化配置

如果需要使用优化后的配置，可以复制到configs目录：

```bash
# 复制优化配置
cp test/harvest_config_optimized_v2.yml configs/harvest/harvest_config.yml
```

## 注意事项

1. **测试文件**：本文件夹中的文件主要用于测试和分析，不建议在生产环境中使用
2. **依赖问题**：部分脚本可能需要额外的Python库，但核心分析器不依赖外部库
3. **输出文件**：分析结果会保存在 `test/analysis/` 目录下
4. **配置文件**：优化后的配置文件仅供参考，使用前请仔细评估

## 后续工作

1. **完成PDF分析**：继续分析剩余的PDF文件
2. **安装高级工具**：安装PyPDF2、pdfplumber等库以提升分析能力
3. **实现OCR功能**：处理扫描版PDF
4. **优化数值提取**：添加验证和过滤逻辑

---

**最后更新**：2026-04-13
**维护者**：Hermes Agent