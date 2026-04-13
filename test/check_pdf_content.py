#!/usr/bin/env python3
"""
检查PDF文件内容
"""

import os

def check_pdf_content(pdf_path):
    """检查PDF文件内容"""
    try:
        with open(pdf_path, 'rb') as f:
            content = f.read()
            
        # 检查PDF头部
        if not content.startswith(b'%PDF'):
            return "不是有效的PDF文件"
        
        # 检查是否包含文本对象
        text_patterns = [
            b'/Type /Page',
            b'/Contents',
            b'BT',  # Begin text
            b'ET',  # End text
            b'Tj',  # Show text
            b'TJ',  # Show text with positioning
        ]
        
        text_found = False
        for pattern in text_patterns:
            if pattern in content:
                text_found = True
                break
        
        if not text_found:
            return "PDF可能不包含文本对象（可能是扫描版）"
        
        # 尝试提取一些文本
        import re
        
        # 查找文本对象
        text_objects = re.findall(rb'BT\s.*?ET', content, re.DOTALL)
        if text_objects:
            # 尝试提取文本
            extracted_text = []
            for obj in text_objects[:5]:  # 只检查前5个
                # 查找Tj或TJ操作
                tj_matches = re.findall(rb'\(([^)]+)\)\s*Tj', obj)
                if tj_matches:
                    for match in tj_matches:
                        try:
                            text = match.decode('utf-8', errors='ignore')
                            if text.strip():
                                extracted_text.append(text)
                        except:
                            pass
            
            if extracted_text:
                return f"找到文本: {' '.join(extracted_text[:3])}..."
        
        return "PDF结构正常，但无法直接提取文本"
        
    except Exception as e:
        return f"检查失败: {str(e)}"

def main():
    pdf_dir = "/home/weeqe/WSL/DATA-Download_Extraction/outputs/literature/PDF"
    
    # 检查几个文件
    test_files = [
        "2005_crossref_Preparation, characterization and application of f_10.1007_s10895-005-2823-9.pdf",
        "2006_arXiv_On-command enhancement of single molecule fluorescence using a gold nanoparticle as an optical nano-antenna.pdf",
        "2008_Biosensors & bioelectronics_Quantum dots encapsulated with amphiphilic alginate as bioprobe for fast screening anti-dengue virus agents.pdf",
    ]
    
    for filename in test_files:
        pdf_path = os.path.join(pdf_dir, filename)
        if os.path.exists(pdf_path):
            print(f"\n检查: {filename}")
            result = check_pdf_content(pdf_path)
            print(f"结果: {result}")

if __name__ == "__main__":
    main()