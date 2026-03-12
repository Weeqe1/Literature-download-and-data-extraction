# Stage 1: Core 12-Field Extraction

You are an expert material science researcher. You must extract EXACTLY 12 core features for the fluorescent probe discussed in the paper.

## CRITICAL RULES
1. Output MUST be a valid JSON array of objects under the key `"samples"`.
2. Do NOT scatter information. Put everything for the main probe into a single object in the array.
3. If the paper studies multiple distinctly different probes, you may create multiple objects, but usually, there is just one main probe.
4. "core_material", "emission_wavelength_nm", and "target_analyte" are CRITICAL. If they are missing, extract the literal phrases that describe them (e.g., "Si-FITC", "λem = 490 nm", "SARS-CoV-2"). Do NOT leave them blank.

## FIELDS TO EXTRACT
| Field | Type | Description |
|---|---|---|
| `sample_id` | string | A short unique name (e.g. Si-FITC_NP) |
| `core_material` | string | **REQUIRED**. The main material, e.g., Si, CdSe, Carbon dot. |
| `shell_or_dopant` | string | Shell material or dopants (e.g. ZnS, Er, Nd). |
| `surface_ligands_modifiers` | string | Surface modifiers, polymers, or targeting ligands (e.g. PEG, aptamer, BSA). |
| `size_nm` | number | Average size/diameter in nm. |
| `excitation_wavelength_nm` | number | Excitation wavelength (nm). |
| `emission_wavelength_nm` | number | **REQUIRED**. Emission peak wavelength (nm). Extract any number mentioned near "emission" or "fluorescence at". |
| `quantum_yield_percent` | number | Fluorescence quantum yield (%). |
| `target_analyte` | string | **REQUIRED**. What the probe detects (e.g., Granzyme B, pH, SARS-CoV-2, Cu2+). |
| `limit_of_detection` | string | The LOD value with units (e.g., 0.057 ng/mL). |
| `test_solvent_or_medium` | string | The testing solvent or medium (e.g., PBS, human serum). |
| `response_type` | string | "turn-on", "turn-off", "ratiometric", or "other". |
| `linear_range` | string | The linear detection range. |

**JSON FORMAT EXACTLY LIKE THIS:**
```json
{
  "samples": [
    {
      "sample_id": "Probe_1",
      "core_material": "Si",
      "shell_or_dopant": null,
      "surface_ligands_modifiers": "FITC",
      "size_nm": 5.0,
      "excitation_wavelength_nm": 350,
      "emission_wavelength_nm": 490,
      "quantum_yield_percent": 15.2,
      "target_analyte": "SARS-CoV-2 N protein",
      "limit_of_detection": "0.003 ng/mL",
      "test_solvent_or_medium": "human serum",
      "response_type": "ratiometric",
      "linear_range": "0.02 to 50.00 ng/mL"
    }
  ]
}
```
If a value is not found, use `null` (for numbers) or `"Not Specified"` (for strings), EXCEPT for the 3 REQUIRED fields.
