import os

base_dir = r"D:\Desktop\DATA-Download_Extraction\configs\extraction\stages"

def append_to_file(filename, content):
    filepath = os.path.join(base_dir, filename)
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            existing = f.read()
        if "CRITICAL DIRECTIVE:" not in existing:
            with open(filepath, "a", encoding="utf-8") as f:
                f.write(content)
            print(f"Updated {filename}")
        else:
            print(f"Already updated {filename}")
    else:
        print(f"File not found: {filename}")

s2_content = """

### 🚨 CRITICAL DIRECTIVE: PROBE MATERIAL 🚨
You MUST extract the overall probe material or composition. 
1. If the material (e.g., 'Si-FITC nanoparticles', 'Carbon dots') is mentioned in the abstract or text, you MUST capture it. 
2. If it does not neatly fit 'core_material' or 'shell_material' schemas, force the full name into 'core_material', 'probe_material', or 'chemical_formula'. 
3. NEVER leave the material completely empty or fail to output if the paper describes a specific fluorescent probe. Extract the literal text if you cannot parse it.
"""

s4_content = """

### 🚨 CRITICAL DIRECTIVE: EMISSION WAVELENGTH 🚨
You MUST extract the Emission Wavelength. 
1. Search aggressively for terms like 'λem', 'emission at', 'fluorescence at', or 'centered at xxx nm'. 
2. If the text says "Si fluorescence at λem = 385 nm and FITC fluorescence at λem = 490 nm", extract 385 and 490. 
3. DO NOT leave the emission wavelength blank if any numerical value is provided in the text. Output the literal string if numerical parsing fails.
"""

s6_content = """

### 🚨 CRITICAL DIRECTIVE: TARGET ANALYTE 🚨
You MUST extract the Target Analyte (what the probe is designed to detect).
1. Examples: 'SARS-CoV-2 nucleocapsid protein', 'Cu2+', 'pH', 'Granzyme B'. 
2. Look for phrases like 'detection of', 'immunoassay for', 'sensor for', 'probe for'. 
3. This is an absolute priority. DO NOT leave the target analyte blank. If unsure, extract the most likely target from the title or abstract.
"""

append_to_file("stage2_material.md", s2_content)
append_to_file("stage4_optical.md", s4_content)
append_to_file("stage6_bio.md", s6_content)
