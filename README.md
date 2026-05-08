# Medical Residency Rotation Scheduler

![Python](https://img.shields.io/badge/python-3.11-blue.svg)
![OR-Tools](https://img.shields.io/badge/solver-OR--Tools%20CP--SAT-orange.svg)
![Streamlit](https://img.shields.io/badge/UI-Streamlit-red.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

An automated scheduling system for medical residency programs, built with Python and Google's **OR-Tools CP-SAT solver**. It transforms the complex, manual task of assigning annual rotations into an optimised, constraint-satisfying, reproducible process — and presents the results through an interactive Streamlit web interface.

---

## Overview

Scheduling medical rotations is one of the hardest planning problems in academic medicine. Programme directors must simultaneously satisfy:

- **Graduation requirements** — each PGY level must complete specific rotations for a fixed number of blocks.
- **Staffing minimums** — every clinical service must have enough residents in every block.
- **Leave requests** — residents may have full or half-block leave in specific periods.
- **Sequential rules** — some rotations cannot be taken back-to-back; others are better when consecutive.
- **Pre-assignments** — certain residents may already be committed to specific rotations in specific blocks.

This system encodes all of those rules as a **Constraint Programming (CP-SAT)** model and solves the 13-block annual schedule globally and simultaneously, rather than block-by-block. It supports up to six PGY levels (R1, R2, R3, R4, R4_Chiefs, R_NEURO) and 22 clinical rotations.

For a full mathematical description of the model, see [docs/TECHNICAL_REPORT.md](docs/TECHNICAL_REPORT.md).

---

## Features

- **Constraint-based optimisation** — uses CP-SAT to satisfy all hard (mandatory) constraints.
- **Objective-driven quality** — maximises a weighted score of soft (preferential) constraints.
- **Flexible pre-assignments** — supports forced single, forced OR, and forbidden rotation pre-assignments per block.
- **Interactive web interface** — upload an Excel file, run the solver, and view results in-browser via Streamlit.
- **Multi-sheet Excel output** — full schedule, per-PGY views, staffing summary, and objective log.
- **Transparent scoring** — every soft constraint is logged with its satisfaction status and score contribution.
- **Modular architecture** — cleanly separated `config`, `parser`, `model`, `writer`, and `main` modules.

---

## Project Structure

```
medical-rotation-scheduling/
├── scheduler/
│   ├── __init__.py       # Package marker
│   ├── config.py         # All static parameters, rotation lists, and business rules
│   ├── parser.py         # Reads and validates the input Excel file
│   ├── model.py          # Builds the CP-SAT constraint model
│   ├── writer.py         # Extracts the solution and writes the Excel report
│   └── main.py           # Orchestrates the pipeline; standalone entry point
├── sample_data/
│   ├── hmc_im_residency_sample_input.xlsx      # Full working example (default input)
│   ├── hmc_im_equal_distribution_sample.xlsx   # Equal resident distribution variant
│   └── hmc_im_preassignment_sample.xlsx        # Example with pre-assigned blocks
├── notebooks/
│   └── rotation_scheduler.ipynb  # Interactive end-to-end walkthrough notebook
├── docs/
│   └── TECHNICAL_REPORT.md       # Full mathematical and architectural description
├── app.py                # Streamlit web interface
├── environment.yml       # Conda environment definition
└── README.md             # This file
```

---

## Installation

**1. Clone the repository**
```bash
git clone https://github.com/ashaar0509/medical-rotation-scheduling.git
cd medical-rotation-scheduling
```

**2. Create and activate the conda environment**
```bash
conda env create -f environment.yml
conda activate med-rotation-scheduler
```

---

## Usage

The scheduler runs the same pipeline regardless of how it is invoked. Pick whichever mode suits your workflow.

### Option 1 — Streamlit Web App

```bash
streamlit run app.py
```

Your browser will open to the app. Upload your input file, click **Run Scheduler**, then review and download results.

### Option 2 — Command Line

```bash
# Use the default sample input
python -m scheduler.main

# Specify your own input and output paths
python -m scheduler.main --input path/to/your_input.xlsx --output path/to/schedule.xlsx

# See all options
python -m scheduler.main --help
```

A formatted summary is printed to the terminal on completion. The Excel workbook is written to the output path.

### Option 3 — Jupyter Notebook

```bash
conda activate med-rotation-scheduler
jupyter notebook notebooks/rotation_scheduler.ipynb
```

The notebook walks through the full pipeline interactively — from configuration inspection to results visualisation and export.

---

## Input File Format

The scheduler requires a single `.xlsx` file. Each row represents one resident.

| Column | Type | Description |
|:---|:---|:---|
| `ID` | Text | Unique identifier for each resident (e.g. `R1_001`). |
| `PGY` | Text | Postgraduate year level: `R1`, `R2`, `R3`, `R4`, `R4_Chiefs`, or `R_NEURO`. |
| `Leave1Block` | Number | Block number (1–13) for the first leave period. Leave blank if none. |
| `Leave1Half` | Text | Which half of the block: `First Half` or `Second Half`. |
| `Leave2Block` | Number | Block number (1–13) for the second leave period. Leave blank if none. |
| `Leave2Half` | Text | Which half: `First Half` or `Second Half`. |
| `Block_1` … `Block_13` | Text | Optional pre-assignments for each block (see below). |

> **Full-block leave:** Set both `Leave1Block` and `Leave2Block` to the same block number. The resident will be forced onto `LEAVE` for that entire block.

### Pre-assignment Syntax

In any `Block_N` column you can specify three types of constraint:

| Type | Syntax | Example | Effect |
|:---|:---|:---|:---|
| Forced (single) | Rotation name | `Cardiology` | Resident must do Cardiology in that block. |
| Forced (OR) | Comma-separated names | `Cardiology, AMAU` | Resident must do one of Cardiology or AMAU. |
| Forbidden | `!` prefix | `!MICU` or `!Cardiology, !MICU` | Resident cannot be assigned those rotations. |

> **Note:** A cell cannot contain both forced and forbidden entries (e.g. `AMAU, !Cardiology`). This is logically contradictory and will raise a parsing error.

---

## Constraints Overview

The model enforces two categories of constraints. For the complete mathematical formulation, see [docs/TECHNICAL_REPORT.md](docs/TECHNICAL_REPORT.md).

### Hard Constraints (must be satisfied)

| Category | Description |
|:---|:---|
| Unique assignment | Each resident is assigned exactly one rotation per block. |
| Graduation requirements | Each PGY level must meet rotation-specific block count ranges. |
| Staffing minimums | Clinical services have minimum (and some exact) per-block headcounts. |
| Leave enforcement | Full-leave blocks are fixed to LEAVE; half-leave restricts eligible rotations. |
| Sequential rules | R1s cannot have >5 consecutive Medical Teams. R2/R3s cannot repeat Senior Rotation back-to-back. |
| Batch integrity | MICU and CCU cannot straddle scheduling batch boundaries. |
| R_NEURO template | Neurology residents have a fixed partial template (Blocks 1–3 and 12–13). |
| Pre-assignments | Forced and forbidden block assignments from the input file. |

### Soft Constraints (optimised)

| Constraint | PGY | Weight |
|:---|:---|:---|
| Consecutive MICU blocks | R2 | +2 |
| Consecutive CCU blocks | R2 | +2 |
| Consecutive Hematology/Oncology blocks | Any eligible | +2 |
| 4+ consecutive Medical Teams | R1 | −1 |
| Consecutive Cardiology | R1 | −1 |
| Consecutive Senior Rotation | R3 | −2 |
| Senior Rotation with only 1-block gap | R3 | −1 |
| 6 consecutive Registrar Rotation | R4 / R4_Chiefs | −2 |

The **Normalized Schedule Quality Score** displayed after a run is `raw_score / max_possible_score`, where `max_possible_score` is the theoretical maximum if every reward fires and no penalty fires.

---

## Output

The generated Excel workbook contains the following sheets:

| Sheet | Contents |
|:---|:---|
| `FullSchedule` | All residents × 13 blocks. |
| `Summary` | Rotation × block staffing counts. |
| `ObjectiveLog` | Each soft constraint with its status and score contribution. |
| `R1`, `R2`, … | Schedule filtered to each PGY level. |

---

## Configuration

All tuneable parameters live in `scheduler/config.py`. Key sections:

- **`GRADUATION_REQUIREMENTS`** — per-PGY rotation block count ranges.
- **`PER_BLOCK_MINIMUM_STAFFING`** — minimum headcount per rotation per block.
- **`LEAVE_ELIGIBLE_ROTATIONS`** — rotations allowed during a half-leave block.
- **`COVERAGE_GROUPS`** — rotation groupings for weighted on-call coverage.
- **`REWARD_WEIGHT` / `PENALTY_WEIGHT`** — base weights for the objective function.

---

## Technical Notes

The CP-SAT solver is a complete, sound solver — it guarantees that any solution it returns satisfies **all** hard constraints. If no feasible solution exists (e.g. due to conflicting pre-assignments or over-constrained staffing), the app will report this clearly rather than returning a broken schedule.

Solve time depends on the number of residents and the tightness of constraints, typically ranging from a few seconds to a few minutes.

---

## License

MIT License. See `LICENSE` for details.
