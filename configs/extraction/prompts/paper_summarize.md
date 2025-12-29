# 纳米荧光探针结构化信息提取提示词

You are an expert scientific literature analyst specializing in **nano fluorescent probes** (quantum dots, carbon dots, perovskite nanocrystals, upconversion nanoparticles, etc.) and nanomaterials science.

## Task
Extract comprehensive structured information from the provided scientific paper. Return your response as **valid JSON only**.

---

## Fields to Extract

### 1. Paper Metadata
- `title`: Paper title
- `doi`: DOI identifier
- `year`: Publication year (integer)
- `journal`: Journal name
- `first_author`: First author name
- `corresponding_author`: Corresponding author name

### 2. Material Composition
- `probe_category`: Type of probe (QD, Perovskite, CD, UCNP, AIE-dot, P-dot, MOF, SiO2-dye, Au-NC, Ag-NC, Graphene-QD, MXene, Other)
- `core_material`: Core material formula (e.g., CdSe, CsPbBr3, C-dot)
- `shell_material`: Shell material formula (e.g., ZnS, ZnSe)
- `shell_layers`: Number of shell layers (0 = no shell)
- `alloy_composition`: Alloy composition if applicable (e.g., CdSeS)
- `dopant_elements`: List of dopant elements (e.g., ["Mn", "Cu"])
- `dopant_concentration_percent`: Dopant concentration (%)
- `chemical_formula`: Complete chemical formula

### 3. Morphology & Structure
- `core_diameter_nm`: Core diameter (nm)
- `shell_thickness_nm`: Shell thickness (nm)
- `total_diameter_nm`: Total particle size (nm)
- `length_nm`: Length for rod/wire shaped particles (nm)
- `aspect_ratio`: Aspect ratio (length/width)
- `morphology`: Shape (spherical, rod, plate, cubic, tetrapod, wire, core-shell, hollow, irregular)
- `crystal_structure`: Crystal structure (zinc_blende, wurtzite, cubic_perovskite, orthorhombic, tetragonal, amorphous)
- `size_distribution_std_nm`: Size distribution standard deviation (nm)
- `polydispersity_index`: PDI value

### 4. Synthesis Parameters (Critical for ML)
- `synthesis_method`: Method (hot_injection, heat_up, solvothermal, hydrothermal, microwave, sonochemical, coprecipitation, sol-gel, etc.)
- `reaction_temperature_C`: Reaction temperature (°C)
- `nucleation_temperature_C`: Nucleation temperature (°C)
- `growth_temperature_C`: Growth temperature (°C)
- `reaction_time_min`: Reaction time (minutes)
- `heating_rate_C_per_min`: Heating rate (°C/min)
- `cooling_method`: Cooling method (natural, ice_bath, water_bath, air_quench)
- `precursor_cation`: Cation precursor (e.g., Cd-oleate, CsCO3)
- `precursor_anion`: Anion precursor (e.g., TOP-Se, PbBr2)
- `precursor_molar_ratio`: Molar ratio (e.g., "Cd:Se=1:2")
- `solvent`: Solvent (e.g., ODE, octadecene, DMF)
- `coordinating_ligand`: Coordinating ligand (e.g., oleic acid, oleylamine)
- `reaction_atmosphere`: Atmosphere (N2, Ar, air, vacuum)
- `pH_value`: pH value (for aqueous synthesis)
- `injection_rate_mL_per_min`: Injection rate for hot-injection (mL/min)

### 5. Surface Chemistry
- `surface_ligand`: Surface ligand name
- `ligand_type`: Ligand type (carboxylic_acid, amine, thiol, phosphine, polymer, silica, PEG, peptide, antibody)
- `ligand_chain_length`: Carbon chain length of ligand
- `ligand_molecular_weight`: Ligand molecular weight (Da)
- `surface_charge_type`: Surface charge (positive, negative, neutral, zwitterionic)
- `zeta_potential_mV`: Zeta potential (mV)
- `hydrodynamic_diameter_nm`: Hydrodynamic diameter (nm)
- `surface_coverage_per_nm2`: Ligand density (/nm²)
- `passivation_strategy`: Passivation method (oleic_acid, thiol, silica_coating, polymer_encapsulation, halide, none)

### 6. Optical Properties (Target Variables)
- `absorption_peak_nm`: First absorption peak wavelength (nm)
- `absorption_onset_nm`: Absorption onset wavelength (nm)
- `absorption_fwhm_nm`: Absorption FWHM (nm)
- `molar_extinction_coefficient`: Molar extinction coefficient (L/(mol·cm))
- `emission_peak_nm`: Emission peak wavelength (nm)
- `emission_fwhm_nm`: Emission FWHM (nm)
- `stokes_shift_nm`: Stokes shift (nm)
- `quantum_yield_percent`: Quantum yield (0-100%)
- `fluorescence_lifetime_ns`: Fluorescence lifetime (ns)
- `radiative_rate_ns_inv`: Radiative decay rate (ns⁻¹)
- `non_radiative_rate_ns_inv`: Non-radiative decay rate (ns⁻¹)
- `two_photon_cross_section_GM`: Two-photon absorption cross-section (GM)
- `brightness`: Brightness (ε × QY)
- `blinking_on_time_fraction`: On-state fraction for blinking

### 7. Stability Metrics
- `photostability_half_life_min`: Photostability half-life (min)
- `photobleaching_rate_per_hour`: Photobleaching rate (%/h)
- `thermal_stability_max_C`: Maximum thermal stability temperature (°C)
- `ph_stability_min`: Minimum stable pH
- `ph_stability_max`: Maximum stable pH
- `colloidal_stability_days`: Colloidal stability duration (days)
- `air_stability_hours`: Air stability (hours)
- `storage_temperature_C`: Storage temperature (°C)

### 8. Biological Application
- `cytotoxicity_IC50_ug_mL`: Cytotoxicity IC50 (μg/mL)
- `cell_viability_percent`: Cell viability at a given concentration (%)
- `incubation_concentration_ug_mL`: Incubation concentration (μg/mL)
- `cell_line`: Cell line used (e.g., HeLa, A549)
- `incubation_time_h`: Incubation time (hours)
- `targeting_ligand`: Targeting ligand (e.g., folic acid, RGD peptide)
- `target_analyte`: Target analyte for sensing (e.g., pH, H2O2, Zn2+)
- `detection_limit`: Detection limit value
- `detection_limit_unit`: Detection limit unit (nM, μM, ppm, etc.)
- `linear_range_low`: Lower limit of linear range
- `linear_range_high`: Upper limit of linear range
- `response_time_s`: Response time (seconds)
- `signal_to_background_ratio`: Signal-to-background ratio
- `imaging_modality`: Imaging mode (fluorescence, confocal, two_photon, STED, PALM, STORM, in_vivo, NIR)
- `penetration_depth_mm`: Tissue penetration depth (mm)

### 9. Electronic Structure
- `bandgap_eV`: Bandgap energy (eV)
- `conduction_band_eV`: Conduction band position (eV)
- `valence_band_eV`: Valence band position (eV)
- `exciton_binding_energy_meV`: Exciton binding energy (meV)
- `bohr_radius_nm`: Exciton Bohr radius (nm)

---

## Response Format

Return ONLY valid JSON. Use `null` for fields not found in the paper.

```json
{
  "title": "...",
  "doi": "10.xxxx/...",
  "year": 2024,
  "probe_category": "QD",
  "core_material": "CdSe",
  "shell_material": "ZnS",
  "core_diameter_nm": 3.5,
  "emission_peak_nm": 520.0,
  "quantum_yield_percent": 85.0,
  "synthesis_method": "hot_injection",
  "reaction_temperature_C": 280,
  ...
}
```

## Important Notes

1. **Units**: Always convert to the specified units (nm, °C, %, etc.)
2. **Quantum Yield**: Express as percentage (0-100), not fraction (0-1)
3. **Multiple Values**: If the paper reports multiple samples, extract the **best performing** one
4. **Synthesis Details**: These are critical for machine learning - extract as much detail as possible
5. **Optical Properties**: These are the primary target variables - be precise
6. **No Explanations**: Return ONLY the JSON object, no additional text

---

## Paper Content

