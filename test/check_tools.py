#!/usr/bin/env python3
"""
检查可用的PDF解析工具
"""

import sys
import subprocess

def check_command(cmd):
    """检查命令是否可用"""
    try:
        result = subprocess.run(['which', cmd], capture_output=True, text=True)
        return result.returncode == 0
    except:
        return False

def check_python_module(module_name):
    """检查Python模块是否可用"""
    try:
        __import__(module_name)
        return True
    except ImportError:
        return False

def main():
    print("=" * 60)
    print("PDF解析工具检查")
    print("=" * 60)
    
    # 系统命令
    print("\n系统命令:")
    commands = ['pdftotext', 'pdfinfo', 'pdfimages', 'pdftoppm', 'tesseract', 'convert']
    for cmd in commands:
        available = check_command(cmd)
        status = "✓ 可用" if available else "✗ 不可用"
        print(f"  {cmd}: {status}")
    
    # Python模块
    print("\nPython模块:")
    modules = [
        'PyPDF2',
        'pdfplumber', 
        'fitz',  # PyMuPDF
        'pdfminer',
        'camelot',
        'tabula',
        'pytesseract',
        'easyocr',
        'PIL',  # Pillow
        'cv2',  # OpenCV
    ]
    
    available_modules = []
    for module in modules:
        try:
            __import__(module)
            print(f"  {module}: ✓ 已安装")
            available_modules.append(module)
        except ImportError:
            print(f"  {module}: ✗ 未安装")
    
    print("\n" + "=" * 60)
    print("可用的PDF解析方案")
    print("=" * 60)
    
    # 推荐解析方案
    if 'fitz' in available_modules:
        print("\n1. PyMuPDF (fitz) - 推荐")
        print("   - 高性能PDF解析")
        print("   - 支持文本、图像、表格提取")
        print("   - 支持OCR集成")
    
    if 'pdfplumber' in available_modules:
        print("\n2. pdfplumber - 推荐")
        print("   - 优秀的表格提取能力")
        print("   - 保持文本布局")
        print("   - 支持坐标定位")
    
    if 'PyPDF2' in available_modules:
        print("\n3. PyPDF2 - 基础")
        print("   - 基本文本提取")
        print("   - 轻量级")
    
    if 'pdfminer' in available_modules:
        print("\n4. pdfminer - 高级")
        print("   - 精确的文本提取")
        print("   - 支持复杂布局")
    
    if 'pytesseract' in available_modules or 'easyocr' in available_modules:
        print("\n5. OCR方案 - 处理扫描版PDF")
        if 'pytesseract' in available_modules:
            print("   - Tesseract OCR")
        if 'easyocr' in available_modules:
            print("   - EasyOCR")
    
    # 检查特定功能
    print("\n" + "=" * 60)
    print("功能支持检查")
    print("=" * 60)
    
    features = {
        '文本提取': ['PyPDF2', 'pdfplumber', 'fitz', 'pdfminer'],
        '表格提取': ['pdfplumber', 'camelot', 'tabula'],
        '图像提取': ['fitz', 'PyPDF2'],
        'OCR识别': ['pytesseract', 'easyocr'],
        '图像处理': ['PIL', 'cv2'],
    }
    
    for feature, required_modules in features.items():
        available = any(m in available_modules for m in required_modules)
        status = "✓ 支持" if available else "✗ 不支持"
        print(f"  {feature}: {status}")
    
    return available_modules

if __name__ == "__main__":
    available = main()
    print(f"\n总计可用模块: {len(available)}")
    print("可用模块列表:", ", ".join(available) if available else "无")