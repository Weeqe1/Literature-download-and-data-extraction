#!/usr/bin/env python3
"""
高级PDF分析器（无外部依赖）
使用纯Python实现PDF文本提取和分析
"""

import os
import re
import json
import csv
from typing import Dict, List, Tuple, Any, Optional
from datetime import datetime

class PurePythonPDFParser:
    """纯Python PDF解析器"""
    
    def __init__(self):
        pass
    
    def extract_text_from_pdf(self, pdf_path: str) -> Tuple[str, int, Dict[str, Any]]:
        """从PDF提取文本"""
        result = {
            "text": "",
            "pages": 0,
            "metadata": {},
            "tables": [],
            "figures": [],
            "extraction_method": "binary_parsing"
        }
        
        try:
            with open(pdf_path, 'rb') as f:
                content = f.read()
            
            # 检查PDF头部
            if not content.startswith(b'%PDF'):
                return "", 0, {"error": "不是有效的PDF文件"}
            
            # 提取PDF版本
            version_match = re.search(rb'%PDF-(\d+\.\d+)', content)
            if version_match:
                result["metadata"]["version"] = version_match.group(1).decode('ascii')
            
            # 提取页数
            pages_match = re.findall(rb'/Type\s*/Page[^s]', content)
            result["pages"] = len(pages_match)
            
            # 使用多种方法提取文本
            text_methods = [
                self._extract_text_streams,
                self._extract_text_objects,
                self._extract_text_encoded,
                self._extract_text_strings,
            ]
            
            all_text = []
            for method in text_methods:
                try:
                    text = method(content)
                    if text and len(text) > 50:
                        all_text.append(text)
                except:
                    continue
            
            # 合并所有提取的文本
            if all_text:
                result["text"] = "\n".join(all_text)
            
            # 提取元数据
            result["metadata"].update(self._extract_metadata(content))
            
            return result["text"], result["pages"], result
            
        except Exception as e:
            return "", 0, {"error": str(e)}
    
    def _extract_text_streams(self, content: bytes) -> str:
        """从流对象中提取文本"""
        text_parts = []
        
        # 查找所有流对象
        stream_pattern = re.compile(rb'stream\r?\n(.*?)\r?\nendstream', re.DOTALL)
        streams = stream_pattern.findall(content)
        
        for stream in streams:
            try:
                # 尝试解压缩（如果是压缩的）
                try:
                    import zlib
                    decompressed = zlib.decompress(stream)
                    stream = decompressed
                except:
                    pass
                
                # 提取文本
                # 查找Tj和TJ操作符
                text_ops = re.findall(rb'\[(.*?)\]\s*TJ', stream)
                for op in text_ops:
                    # 提取字符串
                    strings = re.findall(rb'\(([^)]+)\)', op)
                    for s in strings:
                        try:
                            text_parts.append(s.decode('utf-8', errors='ignore'))
                        except:
                            pass
                
                # 查找Tj操作符
                text_ops = re.findall(rb'\(([^)]+)\)\s*Tj', stream)
                for s in text_ops:
                    try:
                        text_parts.append(s.decode('utf-8', errors='ignore'))
                    except:
                        pass
                
                # 查找BT...ET文本块
                text_blocks = re.findall(rb'BT\s*(.*?)\s*ET', stream, re.DOTALL)
                for block in text_blocks:
                    # 提取文本
                    strings = re.findall(rb'\(([^)]+)\)', block)
                    for s in strings:
                        try:
                            text_parts.append(s.decode('utf-8', errors='ignore'))
                        except:
                            pass
            except:
                continue
        
        return " ".join(text_parts)
    
    def _extract_text_objects(self, content: bytes) -> str:
        """从文本对象中提取文本"""
        text_parts = []
        
        # 查找所有文本对象
        text_pattern = re.compile(rb'BT\s*(.*?)\s*ET', re.DOTALL)
        text_objects = text_pattern.findall(content)
        
        for obj in text_objects:
            # 提取字符串
            strings = re.findall(rb'\(([^)]+)\)', obj)
            for s in strings:
                try:
                    text_parts.append(s.decode('utf-8', errors='ignore'))
                except:
                    pass
            
            # 提取十六进制字符串
            hex_strings = re.findall(rb'<([0-9A-Fa-f]+)>', obj)
            for hex_str in hex_strings:
                try:
                    text = bytes.fromhex(hex_str.decode('ascii')).decode('utf-8', errors='ignore')
                    text_parts.append(text)
                except:
                    pass
        
        return " ".join(text_parts)
    
    def _extract_text_encoded(self, content: bytes) -> str:
        """提取编码的文本"""
        text_parts = []
        
        # 查找编码的字符串
        # 查找Unicode字符串
        unicode_pattern = re.compile(rb'<FEFF([0-9A-Fa-f]+)>')
        unicode_strings = unicode_pattern.findall(content)
        
        for hex_str in unicode_strings:
            try:
                text = bytes.fromhex(hex_str.decode('ascii')).decode('utf-16-be', errors='ignore')
                text_parts.append(text)
            except:
                pass
        
        # 查找其他编码的字符串
        encoded_pattern = re.compile(rb'\(([^)]+)\)')
        encoded_strings = encoded_pattern.findall(content)
        
        for s in encoded_strings:
            try:
                # 尝试多种编码
                for encoding in ['utf-8', 'latin-1', 'ascii']:
                    try:
                        text = s.decode(encoding, errors='ignore')
                        if text.strip() and len(text) > 1:
                            text_parts.append(text)
                            break
                    except:
                        continue
            except:
                pass
        
        return " ".join(text_parts)
    
    def _extract_text_strings(self, content: bytes) -> str:
        """提取字符串对象"""
        text_parts = []
        
        # 查找所有字符串
        string_pattern = re.compile(rb'\(([^)]{3,})\)')
        strings = string_pattern.findall(content)
        
        for s in strings:
            try:
                text = s.decode('utf-8', errors='ignore')
                # 过滤掉非文本内容
                if self._is_valid_text(text):
                    text_parts.append(text)
            except:
                pass
        
        return " ".join(text_parts)
    
    def _is_valid_text(self, text: str) -> bool:
        """检查是否为有效文本"""
        if not text or len(text) < 3:
            return False
        
        # 检查是否包含可打印字符
        printable_count = sum(1 for c in text if c.isprintable() or c.isspace())
        if printable_count / len(text) < 0.7:
            return False
        
        # 检查是否包含太多特殊字符
        special_count = sum(1 for c in text if not c.isalnum() and not c.isspace())
        if special_count / len(text) > 0.5:
            return False
        
        return True
    
    def _extract_metadata(self, content: bytes) -> Dict[str, str]:
        """提取PDF元数据"""
        metadata = {}
        
        # 提取标题
        title_match = re.search(rb'/Title\s*\(([^)]+)\)', content)
        if title_match:
            metadata["title"] = title_match.group(1).decode('utf-8', errors='ignore')
        
        # 提取作者
        author_match = re.search(rb'/Author\s*\(([^)]+)\)', content)
        if author_match:
            metadata["author"] = author_match.group(1).decode('utf-8', errors='ignore')
        
        # 提取主题
        subject_match = re.search(rb'/Subject\s*\(([^)]+)\)', content)
        if subject_match:
            metadata["subject"] = subject_match.group(1).decode('utf-8', errors='ignore')
        
        # 提取关键词
        keywords_match = re.search(rb'/Keywords\s*\(([^)]+)\)', content)
        if keywords_match:
            metadata["keywords"] = keywords_match.group(1).decode('utf-8', errors='ignore')
        
        return metadata

class AdvancedPDFAnalyzer:
    """高级PDF分析器"""
    
    def __init__(self):
        self.parser = PurePythonPDFParser()
        
        # 纳米荧光探针核心关键词
        self.core_keywords = [
            # 英文关键词
            "fluorescent probe", "fluorescent nanoprobe", "fluorescent nanosensor",
            "nano fluorescent probe", "nanoscale fluorescent probe",
            "quantum dot", "upconversion nanoparticle", "polymeric nanoparticle",
            "fluorescent detection", "fluorescent imaging", "fluorescent sensor",
            "fluorescence", "fluorophore", "luminescent", "luminescence",
            
            # 中文关键词
            "荧光探针", "荧光纳米探针", "荧光传感器", "荧光检测", "荧光成像",
            "量子点", "上转换纳米粒子", "聚合物纳米粒子"
        ]
        
        # 材料关键词
        self.material_keywords = [
            "CdSe", "CdTe", "ZnS", "quantum dot", "QD", "QDs",
            "upconversion", "UCNP", "NaYF4", "NaGdF4", "NaErF4",
            "carbon dot", "CD", "graphene quantum dot", "GQD", "CQD",
            "gold nanoparticle", "AuNP", "silver nanoparticle", "AgNP",
            "silica nanoparticle", "SiNP", "polymeric nanoparticle",
            "dye", "fluorophore", "FITC", "rhodamine", "cyanine",
            "rare earth", "lanthanide", "europium", "terbium",
            "perovskite", "AIE", "aggregation-induced emission"
        ]
        
        # 检测/传感关键词
        self.detection_keywords = [
            "detection", "sensing", "imaging", "bioimaging",
            "target", "analyte", "biomarker", "protein",
            "metal ion", "pH", "temperature", "oxygen",
            "immunoassay", "biosensor", "diagnostic", "sensor",
            "monitor", "measure", "quantif"
        ]
        
        # 波长相关关键词
        self.wavelength_keywords = [
            "nm", "wavelength", "excitation", "emission",
            "absorbance", "absorption", "photoluminescence",
            "PL", "UV-Vis", "spectrum", "spectra"
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
            "wavelength_keyword_matches": [],
            "field_availability": {},
            "extracted_values": {},
            "quality_score": 0.0,
            "rating": "UNKNOWN",
            "rating_reason": "",
            "analysis_timestamp": datetime.now().isoformat()
        }
        
        try:
            # 获取文件大小
            result["file_size_kb"] = os.path.getsize(pdf_path) / 1024
            
            # 检查文件头部
            with open(pdf_path, 'rb') as f:
                header = f.read(8)
                if not header.startswith(b'%PDF'):
                    result["rating"] = "INVALID"
                    result["rating_reason"] = "不是有效的PDF文件"
                    return result
            
            result["is_valid_pdf"] = True
            
            # 提取文本
            text, pages, metadata = self.parser.extract_text_from_pdf(pdf_path)
            result["page_count"] = pages
            result["text_length"] = len(text)
            
            if result["text_length"] < 100:
                result["rating"] = "NO_TEXT"
                result["rating_reason"] = "PDF没有可提取的文本内容（可能是扫描版）"
                return result
            
            # 检查核心关键词
            text_lower = text.lower()
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
            
            # 检查波长关键词
            for keyword in self.wavelength_keywords:
                if keyword.lower() in text_lower:
                    result["wavelength_keyword_matches"].append(keyword)
            
            # 判断是否与纳米荧光探针相关
            result["is_nfp_related"] = (
                len(result["core_keyword_matches"]) > 0 or
                (len(result["material_keyword_matches"]) > 0 and len(result["detection_keyword_matches"]) > 0) or
                (len(result["wavelength_keyword_matches"]) > 0 and len(result["detection_keyword_matches"]) > 0)
            )
            
            # 评估字段可用性
            result["field_availability"] = self._evaluate_field_availability(text)
            
            # 提取具体数值
            result["extracted_values"] = self._extract_values(text)
            
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
            r'(?:core material|composition|synthesized from|prepared from).*?([A-Z][a-z]*(?:\s+[A-Z][a-z]*)*)',
            r'([A-Z][a-z]*(?:\s+[A-Z][a-z]*)*)\s+(?:nanoparticle|nanocrystal|quantum dot|QD)',
            r'(?:based on|made from|derived from)\s+([A-Z][a-z]*(?:\s+[A-Z][a-z]*)*)',
        ]
        availability["core_material"] = any(re.search(p, text, re.IGNORECASE) for p in material_patterns)
        
        # 发射波长
        emission_patterns = [
            r'emission.*?(?:peak|maximum|wavelength|λem).*?(\d+)\s*nm',
            r'(?:λem|emission peak|emission maximum).*?(\d+)\s*nm',
            r'(\d+)\s*nm.*?(?:emission|fluorescence)',
            r'emission.*?(\d+)\s*nm',
        ]
        availability["emission_wavelength_nm"] = any(re.search(p, text, re.IGNORECASE) for p in emission_patterns)
        
        # 目标分析物
        target_patterns = [
            r'(?:detect|sense|measure|target|for)\s+([A-Z][a-z]*(?:\s+[A-Z][a-z]*)*(?:\s+[A-Z][a-z]*)*)',
            r'(?:detection of|sensing of|measurement of)\s+([A-Z][a-z]*(?:\s+[A-Z][a-z]*)*)',
            r'(?:target analyte|analyte|target).*?([A-Z][a-z]*(?:\s+[A-Z][a-z]*)*)',
        ]
        availability["target_analyte"] = any(re.search(p, text, re.IGNORECASE) for p in target_patterns)
        
        # 壳层或掺杂剂
        shell_patterns = [
            r'(?:shell|coating|doped with|dopant).*?([A-Z][a-z]*(?:\s+[A-Z][a-z]*)*)',
            r'core.*?shell.*?([A-Z][a-z]*(?:\s+[A-Z][a-z]*)*)',
            r'(?:ZnS|SiO2|polymer)\s+(?:shell|coating)',
        ]
        availability["shell_or_dopant"] = any(re.search(p, text, re.IGNORECASE) for p in shell_patterns)
        
        # 表面配体
        ligand_patterns = [
            r'(?:surface|functionalized|conjugated|modified|capped).*?([A-Z][a-z]*(?:\s+[A-Z][a-z]*)*)',
            r'(?:ligand|modifier|coating).*?([A-Z][a-z]*(?:\s+[A-Z][a-z]*)*)',
            r'(?:PEG|aptamer|antibody|peptide)',
        ]
        availability["surface_ligands_modifiers"] = any(re.search(p, text, re.IGNORECASE) for p in ligand_patterns)
        
        # 尺寸
        size_patterns = [
            r'(?:size|diameter|particle size).*?(\d+(?:\.\d+)?)\s*nm',
            r'(\d+(?:\.\d+)?)\s*nm.*?(?:particle|nanoparticle|diameter)',
            r'(?:TEM|SEM|DLS).*?(\d+(?:\.\d+)?)\s*nm',
        ]
        availability["size_nm"] = any(re.search(p, text, re.IGNORECASE) for p in size_patterns)
        
        # 激发波长
        excitation_patterns = [
            r'(?:excitation|Ex|λex).*?(\d+)\s*nm',
            r'excited.*?(\d+)\s*nm',
            r'(\d+)\s*nm.*?(?:excitation|excited)',
        ]
        availability["excitation_wavelength_nm"] = any(re.search(p, text, re.IGNORECASE) for p in excitation_patterns)
        
        # 量子产率
        qy_patterns = [
            r'(?:quantum yield|QY|ΦF|photoluminescence quantum yield).*?(\d+(?:\.\d+)?)\s*%',
            r'(\d+(?:\.\d+)?)\s*%.*?(?:quantum yield|QY)',
            r'(?:QY of|quantum yield of)\s+(\d+(?:\.\d+)?)\s*%',
        ]
        availability["quantum_yield_percent"] = any(re.search(p, text, re.IGNORECASE) for p in qy_patterns)
        
        # 检测限
        lod_patterns = [
            r'(?:limit of detection|LOD|detection limit|DL).*?(\d+(?:\.\d+)?)\s*(?:nM|μM|pM|ng/mL|μg/mL|M)',
            r'(\d+(?:\.\d+)?)\s*(?:nM|μM|pM|ng/mL|μg/mL|M).*?(?:limit of detection|LOD)',
            r'(?:as low as|down to)\s+(\d+(?:\.\d+)?)\s*(?:nM|μM|pM|ng/mL|μg/mL)',
        ]
        availability["limit_of_detection"] = any(re.search(p, text, re.IGNORECASE) for p in lod_patterns)
        
        # 测试介质
        medium_patterns = [
            r'(?:in|using|dissolved in|prepared in)\s+(PBS|buffer|serum|water|ethanol|methanol|DMF|DMSO)',
            r'(?:medium|solvent|solution).*?(PBS|buffer|serum|water|ethanol|methanol|DMF|DMSO)',
            r'(?:aqueous|organic)\s+(?:solution|medium)',
        ]
        availability["test_solvent_or_medium"] = any(re.search(p, text, re.IGNORECASE) for p in medium_patterns)
        
        # 响应类型
        response_patterns = [
            r'(?:turn-on|turn-off|ratiometric|on-off|off-on|enhancement|quenching)',
            r'(?:increase|decrease|enhance|quench).*?(?:fluorescence|emission|signal)',
            r'fluorescence.*?(?:increase|decrease|enhance|quench)',
        ]
        availability["response_type"] = any(re.search(p, text, re.IGNORECASE) for p in response_patterns)
        
        # 线性范围
        range_patterns = [
            r'(?:linear range|detection range|working range).*?(\d+(?:\.\d+)?)\s*(?:to|-|~|–)\s*(\d+(?:\.\d+)?)',
            r'(\d+(?:\.\d+)?)\s*(?:to|-|~|–)\s*(\d+(?:\.\d+)?).*?(?:linear|range|concentration)',
            r'(?:from|between)\s+(\d+(?:\.\d+)?)\s*(?:to|-|~|–)\s*(\d+(?:\.\d+)?)',
        ]
        availability["linear_range"] = any(re.search(p, text, re.IGNORECASE) for p in range_patterns)
        
        return availability
    
    def _extract_values(self, text: str) -> Dict[str, Any]:
        """提取具体数值"""
        values = {}
        
        # 提取发射波长
        emission_match = re.search(r'(?:emission|λem).*?(\d+)\s*nm', text, re.IGNORECASE)
        if emission_match:
            values["emission_wavelength_nm"] = int(emission_match.group(1))
        
        # 提取激发波长
        excitation_match = re.search(r'(?:excitation|λex).*?(\d+)\s*nm', text, re.IGNORECASE)
        if excitation_match:
            values["excitation_wavelength_nm"] = int(excitation_match.group(1))
        
        # 提取尺寸
        size_match = re.search(r'(?:size|diameter).*?(\d+(?:\.\d+)?)\s*nm', text, re.IGNORECASE)
        if size_match:
            values["size_nm"] = float(size_match.group(1))
        
        # 提取量子产率
        qy_match = re.search(r'(?:quantum yield|QY).*?(\d+(?:\.\d+)?)\s*%', text, re.IGNORECASE)
        if qy_match:
            values["quantum_yield_percent"] = float(qy_match.group(1))
        
        # 提取检测限
        lod_match = re.search(r'(?:LOD|limit of detection).*?(\d+(?:\.\d+)?)\s*(nM|μM|pM|ng/mL|μg/mL)', text, re.IGNORECASE)
        if lod_match:
            values["limit_of_detection"] = f"{lod_match.group(1)} {lod_match.group(2)}"
        
        return values
    
    def _calculate_quality_score(self, result: Dict[str, Any]) -> float:
        """计算质量分数"""
        score = 0.0
        
        # 基础分数：有效PDF
        if result["is_valid_pdf"]:
            score += 10.0
        
        # 有文本内容
        if result["text_length"] > 100:
            score += 10.0
        if result["text_length"] > 1000:
            score += 5.0
        if result["text_length"] > 5000:
            score += 5.0
        
        # 与纳米荧光探针相关
        if result["is_nfp_related"]:
            score += 25.0
        
        # 关键词匹配
        score += min(len(result["core_keyword_matches"]) * 3.0, 15.0)
        score += min(len(result["material_keyword_matches"]) * 2.0, 10.0)
        score += min(len(result["detection_keyword_matches"]) * 2.0, 10.0)
        score += min(len(result["wavelength_keyword_matches"]) * 1.0, 5.0)
        
        # 必需字段可用性
        field_availability = result["field_availability"]
        required_available = sum(1 for f in self.required_fields if field_availability.get(f, False))
        score += (required_available / len(self.required_fields)) * 30.0
        
        # 重要字段可用性
        important_available = sum(1 for f in self.important_fields if field_availability.get(f, False))
        score += (important_available / len(self.important_fields)) * 20.0
        
        # 提取到具体数值加分
        if result["extracted_values"]:
            score += min(len(result["extracted_values"]) * 3.0, 15.0)
        
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
            elif score >= 65:
                return "B", "良好：包含所有必需字段，信息较完整"
            elif score >= 50:
                return "C+", "中等偏上：包含所有必需字段，但其他信息有限"
            else:
                return "C", "中等：包含所有必需字段，但其他信息有限"
        
        elif required_available >= 2:
            if score >= 70:
                return "B-", "良好偏下：缺少1个必需字段，但其他信息较完整"
            elif score >= 55:
                return "C", "中等：缺少部分必需字段，但其他信息较完整"
            else:
                return "D", "较差：缺少部分必需字段，信息有限"
        
        elif required_available >= 1:
            if score >= 60:
                return "C-", "中等偏下：缺少大部分必需字段"
            else:
                return "D", "较差：缺少大部分必需字段"
        
        else:
            return "F", "不合格：缺少所有必需字段，无法提取有效信息"

def main():
    """主函数"""
    print("=" * 80)
    print("高级PDF分析器（无外部依赖）")
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
    analyzer = AdvancedPDFAnalyzer()
    
    # 分析所有PDF
    results = []
    for i, pdf_path in enumerate(pdf_files, 1):
        if i % 50 == 0:
            print(f"\n[{i}/{len(pdf_files)}] 分析进度...")
        
        result = analyzer.analyze_pdf(pdf_path)
        results.append(result)
        
        # 显示前10个文件和所有A/B级文件的详细信息
        if i <= 10 or result["rating"] in ["A", "B", "B-", "C+"]:
            print(f"\n[{i}] {result['file_name']}")
            print(f"  评级: {result['rating']} - {result['rating_reason']}")
            print(f"  分数: {result['quality_score']:.1f}/100")
            print(f"  文本长度: {result['text_length']} 字符")
            if result["is_nfp_related"]:
                print(f"  核心关键词: {', '.join(result['core_keyword_matches'][:5])}")
                if result["extracted_values"]:
                    print(f"  提取的数值: {result['extracted_values']}")
    
    # 保存结果
    output_dir = "/home/weeqe/WSL/DATA-Download_Extraction/outputs/analysis"
    os.makedirs(output_dir, exist_ok=True)
    
    # 保存详细JSON结果
    json_path = os.path.join(output_dir, "pdf_quality_analysis_advanced.json")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n详细分析结果已保存到: {json_path}")
    
    # 创建CSV报告
    csv_path = os.path.join(output_dir, "pdf_quality_report_advanced.csv")
    with open(csv_path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        
        # 写入表头
        headers = [
            "文件名", "文件大小(KB)", "页数", "文本长度", "有效PDF", "NFP相关",
            "核心关键词匹配数", "材料关键词匹配数", "检测关键词匹配数", "波长关键词匹配数",
            "质量分数", "评级", "评级原因",
            "核心材料", "发射波长", "目标分析物", "壳层/掺杂剂", "表面配体",
            "尺寸", "激发波长", "量子产率", "检测限", "测试介质", "响应类型", "线性范围",
            "提取的发射波长", "提取的激发波长", "提取的尺寸", "提取的量子产率", "提取的检测限"
        ]
        writer.writerow(headers)
        
        # 写入数据
        for r in results:
            row = [
                r["file_name"],
                round(r["file_size_kb"], 1),
                r["page_count"],
                r["text_length"],
                "是" if r["is_valid_pdf"] else "否",
                "是" if r["is_nfp_related"] else "否",
                len(r["core_keyword_matches"]),
                len(r["material_keyword_matches"]),
                len(r["detection_keyword_matches"]),
                len(r["wavelength_keyword_matches"]),
                round(r["quality_score"], 1),
                r["rating"],
                r["rating_reason"],
                "✓" if r["field_availability"].get("core_material") else "✗",
                "✓" if r["field_availability"].get("emission_wavelength_nm") else "✗",
                "✓" if r["field_availability"].get("target_analyte") else "✗",
                "✓" if r["field_availability"].get("shell_or_dopant") else "✗",
                "✓" if r["field_availability"].get("surface_ligands_modifiers") else "✗",
                "✓" if r["field_availability"].get("size_nm") else "✗",
                "✓" if r["field_availability"].get("excitation_wavelength_nm") else "✗",
                "✓" if r["field_availability"].get("quantum_yield_percent") else "✗",
                "✓" if r["field_availability"].get("limit_of_detection") else "✗",
                "✓" if r["field_availability"].get("test_solvent_or_medium") else "✗",
                "✓" if r["field_availability"].get("response_type") else "✗",
                "✓" if r["field_availability"].get("linear_range") else "✗",
                r["extracted_values"].get("emission_wavelength_nm", ""),
                r["extracted_values"].get("excitation_wavelength_nm", ""),
                r["extracted_values"].get("size_nm", ""),
                r["extracted_values"].get("quantum_yield_percent", ""),
                r["extracted_values"].get("limit_of_detection", ""),
            ]
            writer.writerow(row)
    
    print(f"CSV报告已保存到: {csv_path}")
    
    # 打印统计摘要
    print("\n" + "=" * 80)
    print("分析统计摘要")
    print("=" * 80)
    
    total = len(results)
    rating_counts = {}
    for r in results:
        rating = r["rating"]
        rating_counts[rating] = rating_counts.get(rating, 0) + 1
    
    print(f"\n总PDF文件数: {total}")
    print("\n评级分布:")
    for rating in ["A", "B", "B-", "C+", "C", "C-", "D", "F", "INVALID", "NO_TEXT", "ERROR"]:
        count = rating_counts.get(rating, 0)
        pct = (count / total * 100) if total > 0 else 0
        if count > 0:
            print(f"  {rating}: {count} 个 ({pct:.1f}%)")
    
    nfp_related = sum(1 for r in results if r["is_nfp_related"])
    valid_pdf = sum(1 for r in results if r["is_valid_pdf"])
    
    print(f"\nNFP相关文件数: {nfp_related}")
    print(f"有效PDF文件数: {valid_pdf}")
    
    # 打印平均分数
    scores = [r["quality_score"] for r in results if r["is_valid_pdf"]]
    avg_score = sum(scores) / len(scores) if scores else 0
    print(f"\n平均质量分数: {avg_score:.1f}/100")
    
    # 打印各字段可用性统计
    print("\n字段可用性统计:")
    field_names = [
        ("core_material", "核心材料"),
        ("emission_wavelength_nm", "发射波长"),
        ("target_analyte", "目标分析物"),
        ("shell_or_dopant", "壳层/掺杂剂"),
        ("surface_ligands_modifiers", "表面配体"),
        ("size_nm", "尺寸"),
        ("excitation_wavelength_nm", "激发波长"),
        ("quantum_yield_percent", "量子产率"),
        ("limit_of_detection", "检测限"),
        ("test_solvent_or_medium", "测试介质"),
        ("response_type", "响应类型"),
        ("linear_range", "线性范围"),
    ]
    
    for field_key, field_name in field_names:
        available = sum(1 for r in results if r["field_availability"].get(field_key, False))
        pct = (available / total * 100) if total > 0 else 0
        print(f"  {field_name}: {available}/{total} ({pct:.1f}%)")
    
    # 打印推荐用于数据提取的文件
    print("\n" + "=" * 80)
    print("推荐用于数据提取的文件 (评级A、B、B-、C+)")
    print("=" * 80)
    
    recommended = [r for r in results if r["rating"] in ["A", "B", "B-", "C+"]]
    if recommended:
        print(f"\n共 {len(recommended)} 个文件推荐用于数据提取:")
        for r in recommended[:30]:
            print(f"  - {r['file_name']} (评级: {r['rating']}, 分数: {r['quality_score']:.1f})")
        if len(recommended) > 30:
            print(f"  ... 还有 {len(recommended) - 30} 个文件")
    else:
        print("\n没有评级为A或B的文件")
    
    # 打印不合格文件
    print("\n" + "=" * 80)
    print("不合格文件 (评级F)")
    print("=" * 80)
    
    failed = [r for r in results if r["rating"] == "F"]
    if failed:
        print(f"\n共 {len(failed)} 个文件不合格:")
        # 按原因分组
        reason_groups = {}
        for r in failed:
            reason = r["rating_reason"]
            if reason not in reason_groups:
                reason_groups[reason] = []
            reason_groups[reason].append(r["file_name"])
        
        for reason, files in reason_groups.items():
            print(f"\n{reason} ({len(files)} 个文件):")
            for f in files[:5]:
                print(f"  - {f}")
            if len(files) > 5:
                print(f"  ... 还有 {len(files) - 5} 个文件")
    else:
        print("\n没有不合格的文件")
    
    print("\n" + "=" * 80)
    print("分析完成！")
    print("=" * 80)

if __name__ == "__main__":
    main()