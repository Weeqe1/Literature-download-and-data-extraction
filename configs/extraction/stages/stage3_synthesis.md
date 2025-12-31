# Stage 3: Synthesis Parameters

You are extracting **synthesis and reaction parameters** from a scientific paper about nano fluorescent probes.

## IMPORTANT: Multi-Sample Handling
If the paper describes **multiple distinct probe samples** with different synthesis conditions, return an **array of objects**, one for each sample. Use the same `sample_id` as in Stage 2.

## Task
Extract the following fields for EACH distinct probe sample.

## Fields to Extract (per sample)

| Field | Type | Description |
|-------|------|-------------|
| `sample_id` | string | **REQUIRED** - Match the sample_id from Stage 2 |
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

Return a JSON object with a `samples` array:
```json
{
  "samples": [
    {
      "sample_id": "CdSe/ZnS-520",
      "synthesis_method": "hot_injection",
      "reaction_temperature_C": 280,
      ...
    }
  ]
}
```

If all samples share the same synthesis parameters, you may return a single object. Use `null` for fields not found.
