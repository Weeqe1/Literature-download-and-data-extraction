# Stage 2: Material Composition & Morphology

You are extracting **material and structural information** from a scientific paper about nano fluorescent probes.

## Task
Extract ONLY the following fields. Return a JSON object with these exact keys.

## Fields to Extract

| Field | Type | Description |
|-------|------|-------------|
| `probe_category` | enum | Type: QD, Perovskite, CD, UCNP, AIE-dot, P-dot, MOF, SiO2-dye, Au-NC, Ag-NC, Graphene-QD, MXene, Other |
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

Return ONLY valid JSON with the above keys. Use `null` for fields not found.
