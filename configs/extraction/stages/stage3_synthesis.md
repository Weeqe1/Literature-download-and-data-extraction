# Stage 3: Synthesis Parameters

You are extracting **synthesis and reaction parameters** from a scientific paper about nano fluorescent probes.

## CRITICAL: Sample ID Consistency

**Use the EXACT SAME `sample_id` as defined in Stage 2 (Material stage).**

**Format reminder**: `{CoreMaterial}_{ShellMaterial}_{Size}nm` or `{CoreMaterial}_{Modifier}`
- Examples: `CdSe_ZnS_5nm`, `Fe3O4_silica_FITC`, `CdTe_gelatin`

If the same synthesis procedure applies to multiple samples, create one entry for each sample with their respective `sample_id`.

## Fields to Extract (per sample)

| Field | Type | Description |
|-------|------|-------------|
| `sample_id` | string | **REQUIRED** - MUST match Stage 2 exactly |
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

```json
{
  "samples": [
    {
      "sample_id": "CdSe_ZnS_5nm",
      "synthesis_method": "hot_injection",
      "reaction_temperature_C": 280,
      "reaction_time_min": 30,
      ...
    }
  ]
}
```

Use `null` for fields not found.
