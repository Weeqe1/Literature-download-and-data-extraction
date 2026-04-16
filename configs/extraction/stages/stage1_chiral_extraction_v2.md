# Stage 1: Chiral Nano Fluorescent Probe Extraction (Optimized)

## Task
Extract structured data about chiral fluorescent nanoprobes from the scientific paper. Output ONLY valid JSON — no explanations, no markdown, no commentary.

## CRITICAL RULES
1. Output MUST be a valid JSON object with a `"samples"` array
2. Group all data for one probe into a single object
3. If multiple different probes exist, create separate objects with distinct `sample_id`
4. **REQUIRED fields** must never be null: `core_material`, `chiral_source`, `emission_wavelength_nm`, `target_analyte`

## PRIORITY FIELDS

### MUST EXTRACT (Required)
| Field | Description | Example |
|-------|-------------|---------|
| `chiral_type` | Chirality: R/S/D/L/(+)/(-)/racemic | `"L"` |
| `chiral_source` | Source of chirality | `"L-cysteine"`, `"BINOL"` |
| `core_material` | Core material | `"CdTe"`, `"Carbon dot"` |
| `emission_wavelength_nm` | Emission peak (nm) | `540` |
| `target_analyte` | What is detected | `"D-cysteine"` |

### SHOULD EXTRACT (Important)
| Field | Description | Example |
|-------|-------------|---------|
| `chiral_ligand` | Chiral surface ligand | `"L-cysteine"` |
| `size_nm` | Particle size (nm) | `3.5` |
| `quantum_yield_percent` | Quantum yield (%) | `45.0` |
| `limit_of_detection` | LOD with units | `"0.1 nM"` |
| `response_type` | turn-on/turn-off/ratiometric/cpl_on | `"turn-on"` |
| `enantioselectivity_factor` | EF value | `3.2` |

### NICE TO HAVE (Optional)
- `excitation_wavelength_nm`, `stokes_shift_nm`, `fluorescence_lifetime_ns`
- `shell_or_dopant`, `achiral_ligands`, `morphology`
- `test_solvent_or_medium`, `ph_value`
- `glum_value`, `cpl_wavelength_nm` (for CPL probes)
- `synthesis_method`, `chiral_modification_method`

## OUTPUT FORMAT

```json
{
  "samples": [
    {
      "sample_id": "L-Cys-CdTe_QD",
      "chiral_type": "L",
      "chiral_source": "L-cysteine",
      "chiral_ligand": "L-cysteine",
      "core_material": "CdTe",
      "size_nm": 3.5,
      "excitation_wavelength_nm": 365,
      "emission_wavelength_nm": 540,
      "quantum_yield_percent": 45.0,
      "target_analyte": "D-cysteine",
      "target_enantiomer": "D",
      "limit_of_detection": "0.5 μM",
      "response_type": "turn-on",
      "enantioselectivity_factor": 3.2
    }
  ]
}
```

## EXTRACTION GUIDELINES

### How to identify chirality:
- Look for: R/S, D/L, (+)/(-), L-/D- prefixes
- Look for: "enantiomer", "chiral", "enantioselective"
- Look for: chiral molecules as ligands (cysteine, BINOL, etc.)

### How to extract enantioselectivity:
- Look for: "EF =", "enantioselectivity factor", "selectivity ratio"
- Look for: comparison between R and S responses

### How to extract CPL data:
- Look for: "glum", "dissymmetry factor", "CPL"
- Note: glum can be positive or negative

### Common chiral ligands:
- Amino acids: L-cysteine, D-penicillamine, L-arginine, L-histidine
- Small molecules: BINOL, tartaric acid, camphor
- Polymers: chiral polyacetylene, chiral polysaccharide

### Common nanomaterials:
- Quantum dots: CdSe, CdTe, CdS, ZnS, InP
- Carbon dots: C-dots, graphene QDs
- Metal: Au, Ag nanoparticles
- Upconversion: NaYF4, NaGdF4
- Polymer dots: Pdots

## EXAMPLE

Input paper mentions: "L-cysteine capped CdTe quantum dots with emission at 540 nm for selective detection of D-cysteine with LOD of 0.5 μM and EF of 3.2"

Output:
```json
{
  "samples": [{
    "sample_id": "L-Cys-CdTe",
    "chiral_type": "L",
    "chiral_source": "L-cysteine",
    "chiral_ligand": "L-cysteine",
    "core_material": "CdTe",
    "emission_wavelength_nm": 540,
    "target_analyte": "D-cysteine",
    "target_enantiomer": "D",
    "limit_of_detection": "0.5 μM",
    "enantioselectivity_factor": 3.2,
    "response_type": "turn-on"
  }]
}
```

---

## Paper Content