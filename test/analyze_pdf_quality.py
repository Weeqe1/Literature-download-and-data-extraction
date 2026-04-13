#!/usr/bin/env python3
"""
PDF质量分析脚本
分析所有PDF文件，评估其是否符合数据提取要求
"""

import os
import sys
import json
import pandas as pd
from pathlib import Path
from typing import Dict, List, Tuple, Any
import re
from datetime import datetime

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from etl_ensemble.pdf_parser import parse_pdf, truncate_text

class PDFQualityAnalyzer:
    """PDF质量分析器"""
    
    def __init__(self):
        # 纳米荧光探针核心关键词
        self.core_keywords = [
            # 英文关键词
            "fluorescent probe", "fluorescent nanoprobe", "fluorescent nanosensor",
            "nano fluorescent probe", "nanoscale fluorescent probe",
            "quantum dot", "upconversion nanoparticle", "polymeric nanoparticle",
            "fluorescent detection", "fluorescent imaging", "fluorescent sensor",
            "fluorescence", "fluorophore", "luminescent",
            
            # 中文关键词
            "荧光探针", "荧光纳米探针", "荧光传感器", "荧光检测", "荧光成像",
            "量子点", "上转换纳米粒子", "聚合物纳米粒子"
        ]
        
        # 材料关键词
        self.material_keywords = [
            "CdSe", "CdTe", "ZnS", "quantum dot", "QD",
            "upconversion", "UCNP", "NaYF4", "NaGdF4",
            "carbon dot", "CD", "graphene quantum dot", "GQD",
            "gold nanoparticle", "AuNP", "silver nanoparticle", "AgNP",
            "silica nanoparticle", "SiNP", "polymeric nanoparticle",
            "dye", "fluorophore", "FITC", "rhodamine", "cyanine",
            "rare earth", "lanthanide", "europium", "terbium"
        ]
        
        # 检测/传感关键词
        self.detection_keywords = [
            "detection", "sensing", "imaging", "bioimaging",
            "target", "analyte", "biomarker", "protein",
            "metal ion", "pH", "temperature", "oxygen",
            "immunoassay", "biosensor", "diagnostic"
        ]
        
        # schema中定义的关键字段
        self.required_fields = [
            "core_material", "emission_wavelength_nm", "target_analyte"
        ]
        
        self.important_fields = [
            "shell_or_dopant", "surface_ligands_modifiers", "size_nm",
            "excitation_wavelength_nm", "quantum_yield_percent",
            "limit_of_detection", "test_solvent_or_medium",
            "response_type", "linear_range"
        ]
        
    def analyze_pdf(self, pdf_path: str) -> Dict[str, Any]:
        """分析单个PDF文件"""
        result = {
            "file_path": pdf_path,
            "file_name": os.path.basename(pdf_path),
            "file_size_kb": 0,
            "page_count": 0,
            "text_length": 0,
            "is_valid_pdf": False,
            "is_nfp_related": False,
            "core_keyword_matches": [],
            "material_keyword_matches": [],
            "detection_keyword_matches": [],
            "field_availability": {},
            "quality_score": 0.0,
            "rating": "UNKNOWN",
            "rating_reason": "",
            "analysis_timestamp": datetime.now().isoformat()
        }
        
        try:
            # 获取文件大小
            result["file_size_kb"] = os.path.getsize(pdf_path) / 1024
            
            # 解析PDF
            pdf_data = parse_pdf(pdf_path)
            
            # 检查是否为有效PDF
            if "error" in pdf_data:
                result["rating"] = "INVALID"
                result["rating_reason"] = f"PDF解析错误: {pdf_data['error']}"
                return result
            
            result["is_valid_pdf"] = True
            result["page_count"] = pdf_data.get("metadata", {}).get("page_count", 0)
            
            # 获取文本内容
            full_text = pdf_data.get("text", "")
            result["text_length"] = len(full_text)
            
            if not full_text.strip():
                result["rating"] = "NO_TEXT"
                result["rating_reason"] = "PDF没有可提取的文本内容"
                return result
            
            # 检查核心关键词
            text_lower = full_text.lower()
            for keyword in self.core_keywords:
                if keyword.lower() in text_lower:
                    result["core_keyword_matches"].append(keyword)
            
            # 检查材料关键词
            for keyword in self.material_keywords:
                if keyword.lower() in text_lower:
                    result["material_keyword_matches"].append(keyword)
            
            # 检查检测关键词
            for keyword in self.detection_keywords:
                if keyword.lower() in text_lower:
                    result["detection_keyword_matches"].append(keyword)
            
            # 判断是否与纳米荧光探针相关
            result["is_nfp_related"] = (
                len(result["core_keyword_matches"]) > 0 or
                (len(result["material_keyword_matches"]) > 0 and len(result["detection_keyword_matches"]) > 0)
            )
            
            # 评估字段可用性
            result["field_availability"] = self._evaluate_field_availability(full_text)
            
            # 计算质量分数
            result["quality_score"] = self._calculate_quality_score(result)
            
            # 确定评级
            result["rating"], result["rating_reason"] = self._determine_rating(result)
            
        except Exception as e:
            result["rating"] = "ERROR"
            result["rating_reason"] = f"分析过程出错: {str(e)}"
        
        return result
    
    def _evaluate_field_availability(self, text: str) -> Dict[str, bool]:
        """评估字段可用性"""
        availability = {}
        text_lower = text.lower()
        
        # 核心材料
        material_patterns = [
            r'core.*?(?:material|composition).*?([A-Z][a-z]*(?:\s+[A-Z][a-z]*)*)',
            r'([A-Z][a-z]*(?:\s+[A-Z][a-z]*)*)\s+(?:nanoparticle|nanocrystal|quantum dot)',
            r'synthesized\s+(?:from|using)\s+([A-Z][a-z]*(?:\s+[A-Z][a-z]*)*)',
        ]
        availability["core_material"] = any(re.search(p, text, re.IGNORECASE) for p in material_patterns)
        
        # 发射波长
        emission_patterns = [
            r'emission.*?(?:peak|maximum|wavelength).*?(\d+)\s*nm',
            r'λem.*?(\d+)\s*nm',
            r'emission.*?(\d+)\s*nm',
        ]
        availability["emission_wavelength_nm"] = any(re.search(p, text, re.IGNORECASE) for p in emission_patterns)
        
        # 目标分析物
        target_patterns = [
            r'(?:detect|sense|measure|target).*?([A-Z][a-z]*(?:\s+[A-Z][a-z]*)*(?:\s+[A-Z][a-z]*)*)',
            r'(?:for|targeting)\s+([A-Z][a-z]*(?:\s+[A-Z][a-z]*)*)\s+(?:detection|sensing)',
        ]
        availability["target_analyte"] = any(re.search(p, text, re.IGNORECASE) for p in target_patterns)
        
        # 壳层或掺杂剂
        shell_patterns = [
            r'shell.*?([A-Z][a-z]*(?:\s+[A-Z][a-z]*)*)',
            r'dopant.*?([A-Z][a-z]*(?:\s+[A-Z][a-z]*)*)',
            r'core.*?shell.*?([A-Z][a-z]*(?:\s+[A-Z][a-z]*)*)',
        ]
        availability["shell_or_dopant"] = any(re.search(p, text, re.IGNORECASE) for p in shell_patterns)
        
        # 表面配体
        ligand_patterns = [
            r'surface.*?(?:ligand|modifier|coating).*?([A-Z][a-z]*(?:\s+[A-Z][a-z]*)*)',
            r'functionalized.*?([A-Z][a-z]*(?:\s+[A-Z][a-z]*)*)',
            r'conjugated.*?([A-Z][a-z]*(?:\s+[A-Z][a-z]*)*)',
        ]
        availability["surface_ligands_modifiers"] = any(re.search(p, text, re.IGNORECASE) for p in ligand_patterns)
        
        # 尺寸
        size_patterns = [
            r'(?:size|diameter).*?(\d+(?:\.\d+)?)\s*nm',
            r'(\d+(?:\.\d+)?)\s*nm.*?(?:particle|nanoparticle)',
            r'TEM.*?(\d+(?:\.\d+)?)\s*nm',
        ]
        availability["size_nm"] = any(re.search(p, text, re.IGNORECASE) for p in size_patterns)
        
        # 激发波长
        excitation_patterns = [
            r'(?:excitation|Ex|λex).*?(\d+)\s*nm',
            r'excited.*?(\d+)\s*nm',
        ]
        availability["excitation_wavelength_nm"] = any(re.search(p, text, re.IGNORECASE) for p in excitation_patterns)
        
        # 量子产率
        qy_patterns = [
            r'(?:quantum yield|QY|ΦF).*?(\d+(?:\.\d+)?)\s*%',
            r'(\d+(?:\.\d+)?)\s*%.*?(?:quantum yield|QY)',
        ]
        availability["quantum_yield_percent"] = any(re.search(p, text, re.IGNORECASE) for p in qy_patterns)
        
        # 检测限
        lod_patterns = [
            r'(?:limit of detection|LOD|detection limit).*?(\d+(?:\.\d+)?)\s*(?:nM|μM|pM|ng/mL|μg/mL)',
            r'(\d+(?:\.\d+)?)\s*(?:nM|μM|pM|ng/mL|μg/mL).*?(?:limit of detection|LOD)',
        ]
        availability["limit_of_detection"] = any(re.search(p, text, re.IGNORECASE) for p in lod_patterns)
        
        # 测试介质
        medium_patterns = [
            r'(?:in|using|dissolved in)\s+(PBS|buffer|serum|water|ethanol|methanol|DMF)',
            r'(?:medium|solvent).*?(PBS|buffer|serum|water|ethanol|methanol|DMF)',
        ]
        availability["test_solvent_or_medium"] = any(re.search(p, text, re.IGNORECASE) for p in medium_patterns)
        
        # 响应类型
        response_patterns = [
            r'(?:turn-on|turn-off|ratiometric|on-off|off-on)',
            r'(?:increase|decrease).*?fluorescence',
            r'fluorescence.*?(?:increase|decrease)',
        ]
        availability["response_type"] = any(re.search(p, text, re.IGNORECASE) for p in response_patterns)
        
        # 线性范围
        range_patterns = [
            r'(?:linear range|detection range).*?(\d+(?:\.\d+)?)\s*(?:to|-|~)\s*(\d+(?:\.\d+)?)',
            r'(\d+(?:\.\d+)?)\s*(?:to|-|~)\s*(\d+(?:\.\d+)?).*?(?:linear|range)',
        ]
        availability["linear_range"] = any(re.search(p, text, re.IGNORECASE) for p in range_patterns)
        
        return availability
    
    def _calculate_quality_score(self, result: Dict[str, Any]) -> float:
        """计算质量分数"""
        score = 0.0
        
        # 基础分数：有效PDF
        if result["is_valid_pdf"]:
            score += 10.0
        
        # 有文本内容
        if result["text_length"] > 100:
            score += 10.0
        
        # 与纳米荧光探针相关
        if result["is_nfp_related"]:
            score += 30.0
        
        # 核心关键词匹配
        score += min(len(result["core_keyword_matches"]) * 5.0, 20.0)
        
        # 材料关键词匹配
        score += min(len(result["material_keyword_matches"]) * 2.0, 10.0)
        
        # 检测关键词匹配
        score += min(len(result["detection_keyword_matches"]) * 2.0, 10.0)
        
        # 必需字段可用性
        field_availability = result["field_availability"]
        required_available = sum(1 for f in self.required_fields if field_availability.get(f, False))
        score += (required_available / len(self.required_fields)) * 30.0
        
        # 重要字段可用性
        important_available = sum(1 for f in self.important_fields if field_availability.get(f, False))
        score += (important_available / len(self.important_fields)) * 20.0
        
        return min(score, 100.0)
    
    def _determine_rating(self, result: Dict[str, Any]) -> Tuple[str, str]:
        """确定评级"""
        score = result["quality_score"]
        is_nfp_related = result["is_nfp_related"]
        field_availability = result["field_availability"]
        
        # 检查必需字段
        required_available = sum(1 for f in self.required_fields if field_availability.get(f, False))
        
        if not result["is_valid_pdf"]:
            return "F", "无效PDF文件"
        
        if result["text_length"] < 100:
            return "F", "文本内容过少"
        
        if not is_nfp_related:
            return "F", "与纳米荧光探针主题无关"
        
        if required_available == len(self.required_fields):
            if score >= 80:
                return "A", "优秀：包含所有必需字段，信息完整"
            elif score >= 60:
                return "B", "良好：包含所有必需字段，信息较完整"
            else:
                return "C", "中等：包含所有必需字段，但其他信息有限"
        
        elif required_available >= 2:
            if score >= 60:
                return "C", "中等：缺少部分必需字段，但其他信息较完整"
            else:
                return "D", "较差：缺少部分必需字段，信息有限"
        
        elif required_available >= 1:
            return "D", "较差：缺少大部分必需字段"
        
        else:
            return "F", "不合格：缺少所有必需字段，无法提取有效信息"

def main():
    """主函数"""
    print("=" * 80)
    print("PDF质量分析工具")
    print("=" * 80)
    
    # PDF目录
    pdf_dir = "/home/weeqe/WSL/DATA-Download_Extraction/outputs/literature/PDF"
    
    if not os.path.exists(pdf_dir):
        print(f"错误：PDF目录不存在: {pdf_dir}")
        return
    
    # 获取所有PDF文件
    pdf_files = []
    for root, dirs, files in os.walk(pdf_dir):
        for file in files:
            if file.lower().endswith('.pdf'):
                pdf_files.append(os.path.join(root, file))
    
    print(f"找到 {len(pdf_files)} 个PDF文件")
    
    # 创建分析器
    analyzer = PDFQualityAnalyzer()
    
    # 分析所有PDF
    results = []
    for i, pdf_path in enumerate(pdf_files, 1):
        print(f"\n[{i}/{len(pdf_files)}] 分析: {os.path.basename(pdf_path)}")
        result = analyzer.analyze_pdf(pdf_path)
        results.append(result)
        print(f"  评级: {result['rating']} - {result['rating_reason']}")
        print(f"  分数: {result['quality_score']:.1f}/100")
    
    # 保存结果
    output_dir = "/home/weeqe/WSL/DATA-Download_Extraction/outputs/analysis"
    os.makedirs(output_dir, exist_ok=True)
    
    # 保存详细JSON结果
    json_path = os.path.join(output_dir, "pdf_quality_analysis.json")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n详细分析结果已保存到: {json_path}")
    
    # 创建DataFrame并保存为Excel
    df_data = []
    for r in results:
        row = {
            "文件名": r["file_name"],
            "文件大小(KB)": round(r["file_size_kb"], 1),
            "页数": r["page_count"],
            "文本长度": r["text_length"],
            "有效PDF": "是" if r["is_valid_pdf"] else "否",
            "NFP相关": "是" if r["is_nfp_related"] else "否",
            "核心关键词匹配数": len(r["core_keyword_matches"]),
            "材料关键词匹配数": len(r["material_keyword_matches"]),
            "检测关键词匹配数": len(r["detection_keyword_matches"]),
            "质量分数": round(r["quality_score"], 1),
            "评级": r["rating"],
            "评级原因": r["rating_reason"],
            "核心材料": "✓" if r["field_availability"].get("core_material") else "✗",
            "发射波长": "✓" if r["field_availability"].get("emission_wavelength_nm") else "✗",
            "目标分析物": "✓" if r["field_availability"].get("target_analyte") else "✗",
            "壳层/掺杂剂": "✓" if r["field_availability"].get("shell_or_dopant") else "✗",
            "表面配体": "✓" if r["field_availability"].get("surface_ligands_modifiers") else "✗",
            "尺寸": "✓" if r["field_availability"].get("size_nm") else "✗",
            "激发波长": "✓" if r["field_availability"].get("excitation_wavelength_nm") else "✗",
            "量子产率": "✓" if r["field_availability"].get("quantum_yield_percent") else "✗",
            "检测限": "✓" if r["field_availability"].get("limit_of_detection") else "✗",
            "测试介质": "✓" if r["field_availability"].get("test_solvent_or_medium") else "✗",
            "响应类型": "✓" if r["field_availability"].get("response_type") else "✗",
            "线性范围": "✓" if r["field_availability"].get("linear_range") else "✗",
        }
        df_data.append(row)
    
    df = pd.DataFrame(df_data)
    
    # 保存为Excel
    excel_path = os.path.join(output_dir, "pdf_quality_report.xlsx")
    df.to_excel(excel_path, index=False, sheet_name="PDF质量分析")
    print(f"Excel报告已保存到: {excel_path}")
    
    # 打印统计摘要
    print("\n" + "=" * 80)
    print("分析统计摘要")
    print("=" * 80)
    
    total = len(results)
    rating_counts = df["评级"].value_counts()
    
    print(f"\n总PDF文件数: {total}")
    print("\n评级分布:")
    for rating in ["A", "B", "C", "D", "F"]:
        count = rating_counts.get(rating, 0)
        pct = (count / total * 100) if total > 0 else 0
        print(f"  {rating}: {count} 个 ({pct:.1f}%)")
    
    print(f"\nNFP相关文件数: {df['NFP相关'].value_counts().get('是', 0)}")
    print(f"有效PDF文件数: {df['有效PDF'].value_counts().get('是', 0)}")
    
    # 打印平均分数
    avg_score = df["质量分数"].mean()
    print(f"\n平均质量分数: {avg_score:.1f}/100")
    
    # 打印各字段可用性统计
    print("\n字段可用性统计:")
    field_cols = ["核心材料", "发射波长", "目标分析物", "壳层/掺杂剂", "表面配体", 
                  "尺寸", "激发波长", "量子产率", "检测限", "测试介质", "响应类型", "线性范围"]
    for col in field_cols:
        available = df[col].value_counts().get("✓", 0)
        pct = (available / total * 100) if total > 0 else 0
        print(f"  {col}: {available}/{total} ({pct:.1f}%)")
    
    # 打印推荐用于数据提取的文件
    print("\n" + "=" * 80)
    print("推荐用于数据提取的文件 (评级A和B)")
    print("=" * 80)
    
    recommended = df[df["评级"].isin(["A", "B"])]
    if len(recommended) > 0:
        print(f"\n共 {len(recommended)} 个文件推荐用于数据提取:")
        for _, row in recommended.head(20).iterrows():
            print(f"  - {row['文件名']} (评级: {row['评级']}, 分数: {row['质量分数']})")
        if len(recommended) > 20:
            print(f"  ... 还有 {len(recommended) - 20} 个文件")
    else:
        print("\n没有评级为A或B的文件")
    
    # 打印不合格文件
    print("\n" + "=" * 80)
    print("不合格文件 (评级F)")
    print("=" * 80)
    
    failed = df[df["评级"] == "F"]
    if len(failed) > 0:
        print(f"\n共 {len(failed)} 个文件不合格:")
        for _, row in failed.head(20).iterrows():
            print(f"  - {row['文件名']} - {row['评级原因']}")
        if len(failed) > 20:
            print(f"  ... 还有 {len(failed) - 20} 个文件")
    else:
        print("\n没有不合格的文件")
    
    print("\n" + "=" * 80)
    print("分析完成！")
    print("=" * 80)

if __name__ == "__main__":
    main()