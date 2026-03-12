import re
import sys

path = r'D:\Desktop\DATA-Download_Extraction\run_staged_extraction.py'
with open(path, 'r', encoding='utf-8') as f:
    code = f.read()

new_stages = '''STAGES = [
    {"id": 1, "name": "core_extraction", "file": "stage1_core_extraction.md", "desc": "Core 12-Field Extraction", "multimodal": False}
]'''

code = re.sub(r'STAGES = \[\s*\{.*?\}\s*\]', new_stages, code, flags=re.DOTALL)

new_schema_fields = '''FULL_SCHEMA_FIELDS = [
    "sample_id",
    "core_material",
    "shell_or_dopant",
    "surface_ligands_modifiers",
    "size_nm",
    "excitation_wavelength_nm",
    "emission_wavelength_nm",
    "quantum_yield_percent",
    "target_analyte",
    "limit_of_detection",
    "test_solvent_or_medium",
    "response_type",
    "linear_range"
]'''

code = re.sub(r'FULL_SCHEMA_FIELDS = \[.*?\]', new_schema_fields, code, flags=re.DOTALL)

with open(path, 'w', encoding='utf-8') as f:
    f.write(code)
print("Updated run_staged_extraction.py with new STAGES and FULL_SCHEMA_FIELDS.")