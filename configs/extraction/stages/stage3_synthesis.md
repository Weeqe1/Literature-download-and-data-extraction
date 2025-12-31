# Stage 3: Synthesis Parameters

You are extracting **synthesis and reaction parameters** from a scientific paper about nano fluorescent probes.

## Task
Extract ONLY the following fields. Return a JSON object with these exact keys.

## Fields to Extract

| Field | Type | Description |
|-------|------|-------------|
| `synthesis_method` | enum | hot_injection, heat_up, solvothermal, hydrothermal, microwave, sonochemical, electrochemical, laser_ablation, pyrolysis, coprecipitation, sol-gel |
| `reaction_temperature_C` | number | Reaction temperature (°C) |
| `nucleation_temperature_C` | number | Nucleation temperature (°C) |
| `growth_temperature_C` | number | Growth temperature (°C) |
| `reaction_time_min` | number | Reaction time in minutes |
| `heating_rate_C_per_min` | number | Heating rate (°C/min) |
| `cooling_method` | enum | natural, ice_bath, water_bath, air_quench |
| `precursor_cation` | string | Cation precursor |
| `precursor_anion` | string | Anion precursor |
| `precursor_molar_ratio` | string | Molar ratio (e.g., "Cd:Se=1:2") |
| `solvent` | string | Solvent name |
| `coordinating_ligand` | string | Coordinating ligand |
| `reaction_atmosphere` | enum | N2, Ar, air, vacuum |
| `pH_value` | number | pH value |
| `injection_rate_mL_per_min` | number | Injection rate (mL/min) |

## Response Format

Return ONLY valid JSON with the above keys. Use `null` for fields not found.
