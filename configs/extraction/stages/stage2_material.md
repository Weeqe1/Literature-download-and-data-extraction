# Stage 2: Material Composition & Morphology

You are extracting **material and structural information** from a scientific paper about nano fluorescent probes.

## CRITICAL: Sample ID Naming Convention

**IMPORTANT**: Use a CONSISTENT and STANDARDIZED `sample_id` format across ALL samples:

**Format**: `{CoreMaterial}_{ShellMaterial}_{Size}nm` or `{CoreMaterial}_{Modifier}`

**Examples**:
- `CdSe_ZnS_5nm` (for CdSe/ZnS QD with 5nm size)
- `CdTe_gelatin` (for gelatin-coated CdTe)
- `Fe3O4_silica_FITC` (for silica-coated Fe3O4 with FITC dye)
- `AuNC_BSA` (for BSA-protected gold nanoclusters)

**Rules**:
1. Use underscores `_` to separate components, NOT spaces or hyphens
2. Use chemical formulas (CdSe, Fe3O4) NOT full names
3. Keep it SHORT but UNIQUE
4. If multiple sizes of same material exist, include size: `CdSe_ZnS_3nm`, `CdSe_ZnS_5nm`

## Multi-Sample Handling
If the paper describes **multiple distinct probe samples**, return an **array of objects**, one for each sample.

## Fields to Extract (per sample)

| Field | Type | Description |
|-------|------|-------------|
| `sample_id` | string | **REQUIRED** - Use naming convention above |
| `probe_category` | enum | QD, Perovskite, CD, UCNP, AIE-dot, P-dot, MOF, SiO2-dye, Au-NC, Ag-NC, Graphene-QD, MXene, Other |
| `core_material` | string | Core material formula (e.g., CdSe, CsPbBr3) |
| `shell_material` | string | Shell material formula (e.g., ZnS) |
| `shell_layers` | integer | Number of shell layers (0 = no shell) |
| `alloy_composition` | string | Alloy composition (e.g., CdSeS) |
| `dopant_elements` | list | Dopant elements list |
| `dopant_concentration_percent` | number | Dopant concentration (%) |
| `chemical_formula` | string | Complete chemical formula |
| `core_diameter_nm` | number | Core diameter in nm |
| `shell_thickness_nm` | number | Shell thickness in nm |
| `total_diameter_nm` | number | Total particle diameter in nm |
| `length_nm` | number | Length for rod/wire shapes (nm) |
| `aspect_ratio` | number | Aspect ratio |
| `morphology` | enum | spherical, rod, plate, cubic, tetrapod, wire, core-shell, hollow, irregular |
| `crystal_structure` | enum | zinc_blende, wurtzite, cubic_perovskite, orthorhombic, tetragonal, amorphous |
| `size_distribution_std_nm` | number | Size distribution std dev (nm) |
| `polydispersity_index` | number | PDI value |

## Response Format

```json
{
  "samples": [
    {
      "sample_id": "CdSe_ZnS_5nm",
      "probe_category": "QD",
      "core_material": "CdSe",
      "shell_material": "ZnS",
      "total_diameter_nm": 5.2,
      ...
    }
  ]
}
```

Use `null` for fields not found.
