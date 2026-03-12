import re

path = r'D:\Desktop\DATA-Download_Extraction\run_staged_extraction.py'
with open(path, 'r', encoding='utf-8') as f:
    code = f.read()

# Replace STAGES array
old_stages = '''STAGES = [
    {"id": 1, "name": "metadata", "file": "stage1_metadata.md", "desc": "论文元数据", "multimodal": False},
    {"id": 2, "name": "material", "file": "stage2_material.md", "desc": "材料与结构", "multimodal": False},
    {"id": 3, "name": "synthesis", "file": "stage3_synthesis.md", "desc": "合成参数", "multimodal": False},
    {"id": 4, "name": "optical", "file": "stage4_optical.md", "desc": "光学性能", "multimodal": False},
    {"id": 5, "name": "surface", "file": "stage5_surface.md", "desc": "表面与稳定性", "multimodal": False},
    {"id": 6, "name": "bio", "file": "stage6_bio.md", "desc": "生物应用", "multimodal": False},
    {"id": 7, "name": "figures", "file": "stage7_figures.md", "desc": "图片分析", "multimodal": True},
]'''

new_stages = '''STAGES = [
    {"id": 1, "name": "core_extraction", "file": "stage1_core_extraction.md", "desc": "Core 12-Field Extraction", "multimodal": False}
]'''

code = code.replace(old_stages, new_stages)

# Replace FULL_SCHEMA_FIELDS array
old_schema_fields = '''FULL_SCHEMA_FIELDS = [
    # 样品标识
    "sample_id",
    # 材料与结构 (Stage 2)
    "probe_category", "core_material", "shell_material", "shell_layers", 
    "alloy_composition", "dopant_elements", "dopant_concentration_percent", "chemical_formula",
    "core_diameter_nm", "shell_thickness_nm", "total_diameter_nm", "length_nm", 
    "aspect_ratio", "morphology", "crystal_structure",
    # 合成参数 (Stage 3)
    "synthesis_method", "precursors_core", "precursors_shell", "solvents",
    "reaction_temperature_c", "reaction_time_h", "purification_method",
    # 光学性能 (Stage 4)
    "absorption_peak_nm", "absorption_onset_nm", "absorption_fwhm_nm", 
    "molar_extinction_coefficient", "excitation_wavelength_nm", "emission_peak_nm", 
    "emission_fwhm_nm", "stokes_shift_nm", "fluorescence_lifetime_ns",
    "quantum_yield_percent", "quantum_yield_reference", "brightness",
    "two_photon_absorption_cross_section_gm", "upconversion_emission",
    "photobleaching_rate", "photoluminescence_mechanism",
    # 表面与稳定性 (Stage 5)
    "surface_ligands_modifiers", "zeta_potential_mv", "hydrodynamic_diameter_nm",
    "solubility_solvents", "buffer_stability", "ph_stability_range", 
    "thermal_stability", "storage_shelf_life",
    # 生物应用与传感 (Stage 6)
    "application_type", "target_analyte", "detection_mechanism", "response_type",
    "limit_of_detection", "linear_range", "selectivity_interferences",
    "response_time_s", "reversibility", "in_vitro_cell_lines",
    "cytotoxicity_ic50", "cellular_uptake_mechanism", "intracellular_localization",
    "in_vivo_animal_model", "administration_route", "biodistribution_organs",
    "clearance_pathway", "blood_half_life_h",
    # 图片分析额外字段 (Stage 7)
    "figure_derived_size_nm", "figure_derived_morphology", "figure_derived_emission_peak_nm"
]'''

new_schema_fields = '''FULL_SCHEMA_FIELDS = [
    "sample_id", "core_material", "shell_or_dopant", "surface_ligands_modifiers", 
    "size_nm", "excitation_wavelength_nm", "emission_wavelength_nm", "quantum_yield_percent", 
    "target_analyte", "limit_of_detection", "test_solvent_or_medium", "response_type", "linear_range"
]'''

code = code.replace(old_schema_fields, new_schema_fields)

# Also update the stages_to_run default array:
code = code.replace("stages_to_process = stages_to_run or [1, 2, 3, 4, 5, 6, 7]  # Default: all 7 stages", "stages_to_process = stages_to_run or [1]")

with open(path, 'w', encoding='utf-8') as f:
    f.write(code)

print("Safely replaced STAGES and FULL_SCHEMA_FIELDS.")