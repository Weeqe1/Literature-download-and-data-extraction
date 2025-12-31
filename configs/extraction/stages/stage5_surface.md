# Stage 5: Surface Chemistry & Stability

You are extracting **surface chemistry and stability metrics** from a scientific paper about nano fluorescent probes.

## Task
Extract ONLY the following fields. Return a JSON object with these exact keys.

## Fields to Extract

| Field | Type | Description |
|-------|------|-------------|
| `surface_ligand` | string | Surface ligand name |
| `ligand_type` | enum | carboxylic_acid, amine, thiol, phosphine, polymer, silica, PEG, peptide, antibody |
| `ligand_chain_length` | integer | Ligand carbon chain length |
| `ligand_molecular_weight` | number | Ligand molecular weight (Da) |
| `surface_charge_type` | enum | positive, negative, neutral, zwitterionic |
| `zeta_potential_mV` | number | Zeta potential (mV) |
| `hydrodynamic_diameter_nm` | number | Hydrodynamic diameter (nm) |
| `surface_coverage_per_nm2` | number | Ligand coverage density (/nm²) |
| `passivation_strategy` | enum | oleic_acid, thiol, silica_coating, polymer_encapsulation, halide, none |
| `photostability_half_life_min` | number | Photostability half-life (min) |
| `photobleaching_rate_per_hour` | number | Photobleaching rate (%/h) |
| `thermal_stability_max_C` | number | Thermal stability max temp (°C) |
| `ph_stability_min` | number | pH stability lower limit |
| `ph_stability_max` | number | pH stability upper limit |
| `colloidal_stability_days` | number | Colloidal stability (days) |
| `air_stability_hours` | number | Air stability (hours) |
| `storage_temperature_C` | number | Storage temperature (°C) |

## Response Format

Return ONLY valid JSON with the above keys. Use `null` for fields not found.
