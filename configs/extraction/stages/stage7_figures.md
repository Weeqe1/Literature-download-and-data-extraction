# Stage 7: Figure Analysis (Multimodal)

You are analyzing **figures and spectra images** from a scientific paper about nano fluorescent probes.

## CRITICAL: Sample ID Consistency

**Use the EXACT SAME `sample_id` as defined in Stage 2 (Material stage).**

**Format reminder**: `{CoreMaterial}_{ShellMaterial}_{Size}nm` or `{CoreMaterial}_{Modifier}`
- Examples: `CdSe_ZnS_5nm`, `Fe3O4_silica_FITC`, `CdTe_gelatin`

## Task
Examine the provided images and extract quantitative data visible in figures, charts, and spectra.

## Key Data to Extract from Images

| Data Type | Fields | What to Look For |
|-----------|--------|------------------|
| **PL Spectra** | emission_peak_nm, emission_fwhm_nm | Peak wavelength, peak width |
| **UV-Vis Spectra** | absorption_peak_nm, absorption_onset_nm | Absorption edge, peak position |
| **TEM Images** | core_diameter_nm, total_diameter_nm | Scale bar, particle measurements |
| **Size Distribution** | size_distribution_std_nm, polydispersity_index | Histogram data |
| **Stability Curves** | photostability_half_life_min | Time-dependent intensity |
| **Cell Viability** | cell_viability_percent, cytotoxicity_IC50_ug_mL | Bar charts, IC50 curves |

## Response Format

```json
{
  "samples": [
    {
      "sample_id": "CdSe_ZnS_5nm",
      "emission_peak_nm": 520,
      "emission_fwhm_nm": 28,
      "core_diameter_nm": 3.5,
      "_data_source": "Figure 2a (PL spectrum)"
    }
  ],
  "figures_analyzed": [
    {"figure_id": "Fig2a", "type": "PL_spectrum", "description": "PL spectra showing emission at 520nm"}
  ]
}
```

## Important Notes
- **Use SAME sample_id as Stage 2** - this is critical for data merging
- Read numerical values directly from axis labels and data points
- Note the source figure for each extracted value in `_data_source`
- If multiple samples are shown in one figure, extract data for each separately
- Use `null` for values that cannot be reliably read from images
