# Stage 4: Optical Properties

You are extracting **optical and photophysical properties** from a scientific paper about nano fluorescent probes. This is the MOST IMPORTANT stage for machine learning applications.

## IMPORTANT: Multi-Sample Handling
If the paper describes **multiple distinct probe samples** with different optical properties, return an **array of objects**, one for each sample. Use the same `sample_id` from previous stages.

## Task
Extract the following fields for EACH distinct probe sample.

## Fields to Extract (per sample)

| Field | Type | Unit | Description |
|-------|------|------|-------------|
| `sample_id` | string | - | **REQUIRED** - Match sample_id from previous stages |
| `absorption_peak_nm` | number | nm | Absorption peak wavelength |
| `absorption_onset_nm` | number | nm | Absorption onset wavelength |
| `absorption_fwhm_nm` | number | nm | Absorption FWHM |
| `molar_extinction_coefficient` | number | L/(mol·cm) | Molar extinction coefficient |
| `emission_peak_nm` | number | nm | Emission/PL peak wavelength |
| `emission_fwhm_nm` | number | nm | Emission FWHM |
| `stokes_shift_nm` | number | nm | Stokes shift |
| `quantum_yield_percent` | number | % | Quantum yield (0-100) |
| `fluorescence_lifetime_ns` | number | ns | Fluorescence lifetime |
| `radiative_rate_ns_inv` | number | ns⁻¹ | Radiative rate |
| `non_radiative_rate_ns_inv` | number | ns⁻¹ | Non-radiative rate |
| `two_photon_cross_section_GM` | number | GM | Two-photon cross section |
| `brightness` | number | - | Brightness (ε × QY) |
| `blinking_on_time_fraction` | number | - | Blinking on-time fraction |
| `bandgap_eV` | number | eV | Bandgap energy |

## Important Notes
- Quantum yield should be in percentage (0-100), not fraction (0-1)
- If QY is given as fraction (e.g., 0.85), convert to percentage (85%)
- Different samples often have different emission peaks - extract each separately

## Response Format

Return a JSON object with a `samples` array:
```json
{
  "samples": [
    {
      "sample_id": "CdSe/ZnS-520",
      "emission_peak_nm": 520,
      "quantum_yield_percent": 65,
      "fluorescence_lifetime_ns": 22.5,
      ...
    },
    {
      "sample_id": "CdSe/ZnS-580",
      "emission_peak_nm": 580,
      "quantum_yield_percent": 72,
      "fluorescence_lifetime_ns": 28.1,
      ...
    }
  ]
}
```

Use `null` for fields not found.
