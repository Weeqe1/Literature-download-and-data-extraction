# Stage 4: Optical Properties

You are extracting **optical and photophysical properties** from a scientific paper about nano fluorescent probes. This is the MOST IMPORTANT stage for machine learning applications.

## Task
Extract ONLY the following fields. Return a JSON object with these exact keys.

## Fields to Extract

| Field | Type | Unit | Description |
|-------|------|------|-------------|
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
- Look for values in figures, tables, and experimental sections

## Response Format

Return ONLY valid JSON with the above keys. Use `null` for fields not found.
