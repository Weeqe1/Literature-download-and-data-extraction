# Stage 6: Biological Application

You are extracting **biological and sensing application data** from a scientific paper about nano fluorescent probes.

## Task
Extract ONLY the following fields. Return a JSON object with these exact keys.

## Fields to Extract

| Field | Type | Description |
|-------|------|-------------|
| `cytotoxicity_IC50_ug_mL` | number | Cytotoxicity IC50 (μg/mL) |
| `cell_viability_percent` | number | Cell viability (%) |
| `incubation_concentration_ug_mL` | number | Incubation concentration (μg/mL) |
| `cell_line` | string | Cell line (e.g., HeLa, A549, MCF-7) |
| `incubation_time_h` | number | Incubation time (hours) |
| `targeting_ligand` | string | Targeting ligand (e.g., folic acid, RGD) |
| `target_analyte` | string | Detection target (e.g., pH, H2O2, Zn2+, glucose) |
| `detection_limit` | number | Detection limit value |
| `detection_limit_unit` | string | Detection limit unit (nM, μM, ppm) |
| `linear_range_low` | number | Linear range lower limit |
| `linear_range_high` | number | Linear range upper limit |
| `response_time_s` | number | Response time (seconds) |
| `signal_to_background_ratio` | number | Signal-to-background ratio (SBR) |
| `imaging_modality` | enum | fluorescence, confocal, two_photon, STED, PALM, STORM, in_vivo, NIR |
| `penetration_depth_mm` | number | Tissue penetration depth (mm) |
| `conduction_band_eV` | number | Conduction band position (eV) |
| `valence_band_eV` | number | Valence band position (eV) |
| `exciton_binding_energy_meV` | number | Exciton binding energy (meV) |
| `bohr_radius_nm` | number | Exciton Bohr radius (nm) |

## Response Format

Return ONLY valid JSON with the above keys. Use `null` for fields not found.
