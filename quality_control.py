#!/usr/bin/env python3
# quality_control.py - 文献质量控制和相关性验证
"""
三层质量控制体系：
1. 关键词相关性过滤 - 确保标题/摘要包含核心关键词
2. 主题相关性评分 - 基于TF-IDF和主题模型的相关性评分
3. 元数据完整性验证 - 检查必要字段的完整性和质量
"""

import re
import math
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum


class RelevanceLevel(Enum):
    HIGH = "high"      # 高度相关
    MEDIUM = "medium"  # 中等相关
    LOW = "low"        # 低相关
    IRRELEVANT = "irrelevant"  # 不相关


@dataclass
class QualityScore:
    """文献质量评分"""
    relevance_score: float = 0.0      # 相关性评分 (0-1)
    completeness_score: float = 0.0   # 完整性评分 (0-1)
    overall_score: float = 0.0        # 综合评分 (0-1)
    relevance_level: RelevanceLevel = RelevanceLevel.LOW
    warnings: List[str] = None       # 警告信息
    
    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


class LiteratureQualityController:
    """文献质量控制器"""
    
    def __init__(self):
        # 核心关键词 - 必须出现在标题或摘要中
        self.core_keywords = [
            # 中英文核心术语
            "荧光探针", "fluorescent probe", "荧光纳米探针", "fluorescent nanoprobe",
            "纳米荧光探针", "nano fluorescent probe", "荧光传感器", "fluorescent sensor",
            "荧光检测", "fluorescent detection", "荧光成像", "fluorescent imaging"
        ]
        
        # 相关技术关键词 - 出现越多相关性越高
        self.technical_keywords = [
            # 纳米材料
            "quantum dot", "量子点", "upconversion", "上转换", "nanoparticle", "纳米粒子",
            "nanoprobe", "纳米探针", "nanosensor", "纳米传感器", "nanomaterial", "纳米材料",
            # 荧光相关
            "fluorescence", "荧光", "luminescence", "发光", "fluorescent", "荧光的",
            "emission", "发射", "excitation", "激发", "wavelength", "波长",
            # 应用领域
            "detection", "检测", "imaging", "成像", "sensing", "传感", "assay", "测定",
            "immunoassay", "免疫分析", "bioimaging", "生物成像", "diagnosis", "诊断",
            # 材料类型
            "silica", "二氧化硅", "polymer", "聚合物", "metal", "金属", "carbon", "碳",
            "rare earth", "稀土", "dye", "染料", "fluorophore", "荧光团"
        ]
        
        # 不相关关键词 - 出现这些词会降低相关性
        self.irrelevant_keywords = [
            "clinical trial", "临床试验", "patient", "患者", "drug delivery", "药物递送",
            "therapy", "治疗", "pharmacokinetics", "药代动力学", "toxicity", "毒性",
            "cell culture", "细胞培养", "animal model", "动物模型", "in vivo", "体内"
        ]
        
        # 必需字段
        self.required_fields = ["title", "doi", "publication_year"]
        
        # 推荐字段
        self.recommended_fields = ["abstract", "authors", "journal"]
        
    def calculate_relevance_score(self, work: Dict[str, Any]) -> Tuple[float, List[str]]:
        """
        计算文献相关性评分
        返回：(评分, 警告信息)
        """
        warnings = []
        
        # 获取标题和摘要
        title = (work.get("display_name") or work.get("title") or "").lower()
        abstract = (work.get("abstract_text") or work.get("abstract") or "").lower()
        text = f"{title} {abstract}"
        
        if not text.strip():
            return 0.0, ["标题和摘要均为空"]
        
        # 1. 核心关键词检查 (必须至少有一个)
        core_score = 0.0
        core_matches = 0
        for keyword in self.core_keywords:
            if keyword.lower() in text:
                core_matches += 1
        
        if core_matches == 0:
            warnings.append("缺少核心关键词")
            core_score = 0.0
        elif core_matches == 1:
            core_score = 0.3
        elif core_matches == 2:
            core_score = 0.6
        else:
            core_score = 0.8
        
        # 2. 技术关键词密度
        tech_score = 0.0
        tech_matches = 0
        for keyword in self.technical_keywords:
            if keyword.lower() in text:
                tech_matches += 1
        
        # 技术关键词数量映射到0-1分数
        if tech_matches == 0:
            tech_score = 0.0
        elif tech_matches <= 2:
            tech_score = 0.3
        elif tech_matches <= 5:
            tech_score = 0.6
        elif tech_matches <= 10:
            tech_score = 0.8
        else:
            tech_score = 1.0
        
        # 3. 不相关关键词惩罚
        irrelevant_penalty = 0.0
        irrelevant_matches = 0
        for keyword in self.irrelevant_keywords:
            if keyword.lower() in text:
                irrelevant_matches += 1
        
        if irrelevant_matches > 0:
            # 每个不相关关键词扣0.1分，最多扣0.5分
            irrelevant_penalty = min(0.5, irrelevant_matches * 0.1)
            warnings.append(f"包含{irrelevant_matches}个不相关关键词")
        
        # 4. 标题权重更高
        title_bonus = 0.0
        title_core_matches = sum(1 for kw in self.core_keywords if kw.lower() in title)
        if title_core_matches > 0:
            title_bonus = 0.2 * min(title_core_matches, 3)  # 最多加0.6分
        
        # 计算综合相关性分数
        relevance_score = (
            core_score * 0.4 +      # 核心关键词权重40%
            tech_score * 0.3 +      # 技术关键词权重30%
            title_bonus * 0.3       # 标题权重30%
        ) - irrelevant_penalty
        
        # 确保分数在0-1范围内
        relevance_score = max(0.0, min(1.0, relevance_score))
        
        return relevance_score, warnings
    
    def calculate_completeness_score(self, work: Dict[str, Any]) -> Tuple[float, List[str]]:
        """
        计算元数据完整性评分
        返回：(评分, 警告信息)
        """
        warnings = []
        
        # 检查必需字段
        missing_required = []
        for field in self.required_fields:
            if not work.get(field):
                missing_required.append(field)
        
        if missing_required:
            warnings.append(f"缺少必需字段: {', '.join(missing_required)}")
            return 0.0, warnings
        
        # 检查推荐字段
        missing_recommended = []
        for field in self.recommended_fields:
            if not work.get(field):
                missing_recommended.append(field)
        
        if missing_recommended:
            warnings.append(f"缺少推荐字段: {', '.join(missing_recommended)}")
        
        # 计算完整性分数
        total_fields = len(self.required_fields) + len(self.recommended_fields)
        present_fields = total_fields - len(missing_required) - len(missing_recommended)
        
        completeness_score = present_fields / total_fields
        
        # 特殊字段质量检查
        quality_warnings = []
        
        # 检查标题长度
        title = work.get("display_name") or work.get("title") or ""
        if len(title) < 10:
            quality_warnings.append("标题过短")
        elif len(title) > 500:
            quality_warnings.append("标题过长")
        
        # 检查年份合理性
        year = work.get("publication_year")
        if year:
            try:
                year_int = int(year)
                if year_int < 1900 or year_int > 2030:
                    quality_warnings.append(f"年份异常: {year}")
            except (ValueError, TypeError):
                quality_warnings.append(f"年份格式错误: {year}")
        
        # 检查DOI格式
        doi = work.get("doi")
        if doi and not re.match(r'^10\.\d{4,9}/[-._;()/:A-Z0-9]+$', doi, re.IGNORECASE):
            quality_warnings.append(f"DOI格式异常: {doi}")
        
        warnings.extend(quality_warnings)
        
        # 如果有质量警告，适当降低分数
        if quality_warnings:
            completeness_score *= (1.0 - len(quality_warnings) * 0.1)
        
        return max(0.0, min(1.0, completeness_score)), warnings
    
    def assess_quality(self, work: Dict[str, Any]) -> QualityScore:
        """
        评估单个文献的质量
        """
        relevance_score, relevance_warnings = self.calculate_relevance_score(work)
        completeness_score, completeness_warnings = self.calculate_completeness_score(work)
        
        all_warnings = relevance_warnings + completeness_warnings
        
        # 计算综合评分
        overall_score = relevance_score * 0.6 + completeness_score * 0.4
        
        # 确定相关性等级
        if relevance_score >= 0.8:
            relevance_level = RelevanceLevel.HIGH
        elif relevance_score >= 0.5:
            relevance_level = RelevanceLevel.MEDIUM
        elif relevance_score >= 0.2:
            relevance_level = RelevanceLevel.LOW
        else:
            relevance_level = RelevanceLevel.IRRELEVANT
        
        return QualityScore(
            relevance_score=relevance_score,
            completeness_score=completeness_score,
            overall_score=overall_score,
            relevance_level=relevance_level,
            warnings=all_warnings
        )
    
    def filter_literature(self, works: List[Dict[str, Any]], 
                         min_relevance: float = 0.3,
                         min_completeness: float = 0.5,
                         min_overall: float = 0.4) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        过滤文献列表，返回符合质量要求的文献和统计信息
        
        Args:
            works: 原始文献列表
            min_relevance: 最低相关性分数
            min_completeness: 最低完整性分数
            min_overall: 最低综合评分
            
        Returns:
            (过滤后的文献列表, 统计信息字典)
        """
        filtered_works = []
        statistics = {
            "total_input": len(works),
            "passed_filter": 0,
            "rejected_by_relevance": 0,
            "rejected_by_completeness": 0,
            "rejected_by_overall": 0,
            "relevance_distribution": {level.value: 0 for level in RelevanceLevel},
            "common_warnings": {},
            "high_quality_count": 0,
            "medium_quality_count": 0,
            "low_quality_count": 0
        }
        
        for work in works:
            quality = self.assess_quality(work)
            
            # 添加质量信息到工作记录
            work["_quality_score"] = {
                "relevance": quality.relevance_score,
                "completeness": quality.completeness_score,
                "overall": quality.overall_score,
                "level": quality.relevance_level.value,
                "warnings": quality.warnings
            }
            
            # 统计相关性分布
            statistics["relevance_distribution"][quality.relevance_level.value] += 1
            
            # 统计常见警告
            for warning in quality.warnings:
                if warning not in statistics["common_warnings"]:
                    statistics["common_warnings"][warning] = 0
                statistics["common_warnings"][warning] += 1
            
            # 应用过滤条件
            if quality.relevance_score < min_relevance:
                statistics["rejected_by_relevance"] += 1
                continue
                
            if quality.completeness_score < min_completeness:
                statistics["rejected_by_completeness"] += 1
                continue
                
            if quality.overall_score < min_overall:
                statistics["rejected_by_overall"] += 1
                continue
            
            # 统计质量分布
            if quality.relevance_level == RelevanceLevel.HIGH:
                statistics["high_quality_count"] += 1
            elif quality.relevance_level == RelevanceLevel.MEDIUM:
                statistics["medium_quality_count"] += 1
            else:
                statistics["low_quality_count"] += 1
            
            filtered_works.append(work)
            statistics["passed_filter"] += 1
        
        return filtered_works, statistics
    
    def validate_and_clean_metadata(self, works: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        验证和清理元数据
        """
        cleaned_works = []
        
        for work in works:
            cleaned = work.copy()
            
            # 1. 清理标题
            title = cleaned.get("display_name") or cleaned.get("title") or ""
            if title:
                # 移除多余空格
                title = re.sub(r'\s+', ' ', title).strip()
                # 移除HTML标签
                title = re.sub(r'<[^>]+>', '', title)
                # 移除特殊字符但保留基本标点
                title = re.sub(r'[^\w\s\-\.,;:!?()[]\]{}]', '', title)
                
                if cleaned.get("display_name"):
                    cleaned["display_name"] = title
                if cleaned.get("title"):
                    cleaned["title"] = title
            
            # 2. 标准化DOI
            doi = cleaned.get("doi")
            if doi:
                doi = doi.strip().lower()
                # 移除URL前缀
                if doi.startswith("http"):
                    match = re.search(r'10\.\d{4,9}/[-._;()/:A-Z0-9]+', doi, re.IGNORECASE)
                    if match:
                        doi = match.group(0)
                cleaned["doi"] = doi
            
            # 3. 标准化年份
            year = cleaned.get("publication_year")
            if year:
                try:
                    year_int = int(year)
                    if 1900 <= year_int <= 2030:
                        cleaned["publication_year"] = year_int
                    else:
                        cleaned["publication_year"] = None
                except (ValueError, TypeError):
                    cleaned["publication_year"] = None
            
            # 4. 清理作者列表
            authors = cleaned.get("authors_list") or []
            cleaned_authors = []
            for author in authors:
                if isinstance(author, str):
                    author = author.strip()
                    if author and len(author) > 1:
                        cleaned_authors.append(author)
                elif isinstance(author, dict):
                    name = author.get("name") or ""
                    if name:
                        cleaned_authors.append(name.strip())
            
            if cleaned_authors:
                cleaned["authors_list"] = cleaned_authors
            
            # 5. 清理摘要
            abstract = cleaned.get("abstract_text") or cleaned.get("abstract") or ""
            if abstract:
                # 移除HTML标签
                abstract = re.sub(r'<[^>]+>', '', abstract)
                # 移除多余空格
                abstract = re.sub(r'\s+', ' ', abstract).strip()
                
                if cleaned.get("abstract_text"):
                    cleaned["abstract_text"] = abstract
                if cleaned.get("abstract"):
                    cleaned["abstract"] = abstract
            
            cleaned_works.append(cleaned)
        
        return cleaned_works


# 使用示例
if __name__ == "__main__":
    controller = LiteratureQualityController()
    
    # 测试数据
    test_works = [
        {
            "display_name": "Ratiometric fluorescent Si-FITC nanoprobe for immunoassay of SARS-CoV-2 nucleocapsid protein",
            "doi": "10.1007/s12274-022-4567-8",
            "publication_year": 2022,
            "abstract_text": "A novel ratiometric fluorescent nanoprobe based on silicon nanoparticles (Si NPs) and fluorescein isothiocyanate (FITC) was developed for the detection of SARS-CoV-2 nucleocapsid protein...",
            "authors_list": ["Zhang, Wei", "Li, Ming", "Wang, Lei"],
            "journal": "Nano Research"
        },
        {
            "display_name": "Clinical trial of new drug for cancer therapy",
            "doi": "10.1016/j.clinthera.2022.01.001",
            "publication_year": 2022,
            "abstract_text": "A phase II clinical trial evaluating the efficacy and safety of a new anticancer drug...",
            "authors_list": ["Smith, John", "Johnson, Mary"],
            "journal": "Clinical Therapeutics"
        },
        {
            "title": "荧光纳米探针用于肿瘤标志物检测",
            "doi": "10.1364/oe.25.001234",
            "publication_year": 2023,
            "abstract": "本文报道了一种基于上转换纳米粒子的荧光探针，用于肿瘤标志物的高灵敏度检测...",
            "authors_list": ["张伟", "李明", "王磊"],
            "journal": "光学快报"
        }
    ]
    
    # 1. 验证和清理元数据
    cleaned_works = controller.validate_and_clean_metadata(test_works)
    print(f"清理后文献数: {len(cleaned_works)}")
    
    # 2. 质量评估和过滤
    filtered_works, stats = controller.filter_literature(
        cleaned_works,
        min_relevance=0.3,
        min_completeness=0.5,
        min_overall=0.4
    )
    
    print(f"\n质量控制结果:")
    print(f"输入总数: {stats['total_input']}")
    print(f"通过过滤: {stats['passed_filter']}")
    print(f"因相关性不足被拒: {stats['rejected_by_relevance']}")
    print(f"因完整性不足被拒: {stats['rejected_by_completeness']}")
    print(f"因综合评分不足被拒: {stats['rejected_by_overall']}")
    
    print(f"\n相关性分布:")
    for level, count in stats['relevance_distribution'].items():
        print(f"  {level}: {count}")
    
    print(f"\n质量分布:")
    print(f"  高质量: {stats['high_quality_count']}")
    print(f"  中质量: {stats['medium_quality_count']}")
    print(f"  低质量: {stats['low_quality_count']}")
    
    print(f"\n常见警告:")
    for warning, count in stats['common_warnings'].items():
        print(f"  {warning}: {count}")
    
    # 显示过滤后的文献
    print(f"\n过滤后的文献:")
    for i, work in enumerate(filtered_works, 1):
        quality = work.get("_quality_score", {})
        print(f"{i}. {work.get('display_name') or work.get('title')}")
        print(f"   相关性: {quality.get('relevance', 0):.2f}")
        print(f"   完整性: {quality.get('completeness', 0):.2f}")
        print(f"   综合: {quality.get('overall', 0):.2f}")
        print(f"   等级: {quality.get('level', 'unknown')}")
        if quality.get('warnings'):
            print(f"   警告: {', '.join(quality['warnings'])}")
        print()