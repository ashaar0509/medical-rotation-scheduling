# Technical Report: Medical Residency Rotation Scheduler

**Author:** Abdullah Shaar  
**Institution:** Hamad Bin Khalifa University (HBKU)  
**Repository:** [github.com/ashaar0509/medical-rotation-scheduling](https://github.com/ashaar0509/medical-rotation-scheduling)

---

## Table of Contents

1. [Problem Description](#1-problem-description)
2. [System Architecture](#2-system-architecture)
3. [Mathematical Model](#3-mathematical-model)
   - 3.1 [Sets and Indices](#31-sets-and-indices)
   - 3.2 [Decision Variables](#32-decision-variables)
   - 3.3 [Hard Constraints](#33-hard-constraints)
   - 3.4 [Soft Constraints and Objective Function](#34-soft-constraints-and-objective-function)
4. [Input Data Specification](#4-input-data-specification)
5. [Solver and Implementation](#5-solver-and-implementation)
6. [Output and Reporting](#6-output-and-reporting)
7. [Configuration Reference](#7-configuration-reference)
8. [Limitations and Future Work](#8-limitations-and-future-work)

---

## 1. Problem Description

Medical residency programmes require each trainee (resident) to rotate through a set of clinical services over the course of a training year. At Hamad Medical Corporation, the training year is divided into **13 scheduling blocks**, and the programme accommodates approximately **60–80 residents** spanning six postgraduate year (PGY) levels: R1, R2, R3, R4, R4_Chiefs, and R_NEURO.

The manual scheduling process is labour-intensive, error-prone, and typically requires days of iteration by the programme director. The core difficulty is that the decision space is extremely large (each resident can take one of ~22 rotations per block), while simultaneously satisfying a large set of interdependent constraints:

- Each PGY level has **graduation requirements** specifying how many blocks must be spent on specific rotations.
- Each clinical service needs a **minimum number of residents** in every block to maintain patient care.
- Residents may have approved **leave requests** (full or half-block) that restrict their availability.
- Certain rotations have **sequential rules** — some should not be consecutive; others benefit from being consecutive.
- **Pre-assignments** from earlier planning decisions may already fix certain resident–block combinations.

This system encodes all of these rules into a **Constraint Programming (CP)** model and solves it using Google OR-Tools' **CP-SAT solver**, which is a highly optimised, complete SAT/CP hybrid solver capable of handling problems of this scale.

---

## 2. System Architecture

The project follows a modular pipeline architecture:

```
Input Excel File
      │
      ▼
┌─────────────────┐
│  parser.py      │  Reads and validates the Excel file.
│  RotationData   │  Builds eligibility maps, leave dictionaries,
│  Parser         │  and forced/forbidden assignment dicts.
└────────┬────────┘
         │  parsed_data
         ▼
┌─────────────────┐
│  model.py       │  Creates CP-SAT decision variables.
│  ScheduleModel  │  Adds hard constraints to the model.
│  Builder        │  Registers soft constraints and builds
└────────┬────────┘  the objective function.
         │  model + soft_constraints_map
         ▼
┌─────────────────┐
│  OR-Tools       │  CP-SAT solver (Google).
│  CpSolver       │  Finds a feasible + optimised assignment.
└────────┬────────┘
         │  solver (with variable values)
         ▼
┌─────────────────┐
│  writer.py      │  Extracts the schedule from solver values.
│  SolutionWriter │  Analyses soft constraint outcomes.
│                 │  Computes quality scores.
└────────┬────────┘  Writes multi-sheet Excel report.
         │
         ▼
  Output Excel File
  + Constraint Log CSV
```

The web interface (`app.py`) and command-line entry point (`scheduler/main.py`) both call into this pipeline through `RotationScheduler`, which wires the components together.

---

## 3. Mathematical Model

### 3.1 Sets and Indices

| Symbol | Description |
|:---|:---|
| R | Set of all residents, indexed by r = 0 … |R|−1 |
| B | Set of scheduling blocks, B = {0, 1, …, 12} (13 blocks total) |
| Ω | Set of all rotations (22 clinical + LEAVE + TRANSFER = 24 total) |
| P | Set of PGY levels: {R1, R2, R3, R4, R4_Chiefs, R_NEURO} |
| pgy(r) | PGY level of resident r |
| G(p) | List of graduation requirements for PGY level p |
| L_full(r) | Set of full-leave block numbers for resident r |
| L_half(r) | Set of half-leave block numbers for resident r |

### 3.2 Decision Variables

**Primary variable:**

```
x[r, b] ∈ {0, 1, …, |Ω|−1}    for all r ∈ R, b ∈ B
```

`x[r, b]` is an integer whose value is the index of the rotation assigned to resident `r` in block `b`. The domain of `x[r, b]` is restricted at construction time to only the rotations eligible for `pgy(r)` in block `b` (accounting for leave).

**Indicator variables:**

```
y[r, b, ω] ∈ {0, 1}    for all r ∈ R, b ∈ B, ω ∈ Ω
```

`y[r, b, ω] = 1` if and only if `x[r, b] = index(ω)`. These are linked to `x` by:

```
y[r, b, ω] = 1  ⟺  x[r, b] = index(ω)
```

And the uniqueness constraint ensures exactly one indicator is active per resident per block:

```
∑_{ω ∈ Ω} y[r, b, ω] = 1    for all r ∈ R, b ∈ B
```

### 3.3 Hard Constraints

All hard constraints must be satisfied for a solution to be considered feasible. If any hard constraint cannot be met, the solver reports INFEASIBLE.

---

#### H1 — Domain Restriction (Leave Enforcement)

For a full-leave block:
```
x[r, b] = index(LEAVE)    if (b+1) ∈ L_full(r)
```

For a half-leave block, the eligible rotation set is intersected with `LEAVE_ELIGIBLE_ROTATIONS[pgy(r)]`, restricting the domain accordingly.

---

#### H2 — Graduation Requirements

For each PGY level `p` and each requirement `g ∈ G(p)` with rotation group `Rotg`, minimum `ming`, and maximum `maxg`:

```
ming ≤ ∑_{b ∈ B} ∑_{ω ∈ Rotg} y[r, b, ω] ≤ maxg    for all r where pgy(r) = p
```

**Special case:** R3 residents with a full-block leave are exempt from the elective group constraint {Cardiology, ED, Medical Consultation}.

---

#### H3 — Exact Staffing for Administrative Rotations

In every block `b`:
```
∑_{r ∈ R} y[r, b, "Senior Rotation"]    = 10
∑_{r ∈ R} y[r, b, "Registrar Rotation"] = 20
∑_{r ∈ R} y[r, b, "Medical Teams"]      = 20    (blocks 4–13 only)
```

---

#### H4 — Minimum Staffing for Clinical Rotations

For each rotation `ω` with minimum staffing requirement `min_staff(ω)`:
```
∑_{r ∈ R} y[r, b, ω] ≥ min_staff(ω)    for all b ∈ B
```

Rotations and their minimums:

| Rotation | Minimum per block |
|:---|:---:|
| Cardiology | 11 |
| AMAU | 11 |
| CCU | 7 |
| MICU | 7 |
| Al Khor | 6 |
| MOP | 6 |
| Hematology | 5 |
| Oncology | 5 |
| Al Wakra | 9 |
| Medical Consultation | 10 |
| Medical Teams | 20 |

---

#### H5 — Weighted 2nd On-Call Coverage

Residents on half-leave blocks are available for only half a block (3 units), while full-availability residents contribute 6 units. The total weighted 2nd on-call coverage (GI + Rheumatology + Pulmonology) must reach at least 60 units per block:

```
∑_{r ∈ R \ R_NEURO} ∑_{ω ∈ 2ndOnCall} w(r, b) · y[r, b, ω] ≥ 60    for all b ∈ B
```

where `w(r, b) = 3` if `(b+1) ∈ L_half(r)`, else `6`.

---

#### H6 — Floater Coverage

Nephrology and Endocrine serve as floater rotations providing additional on-call coverage. At least 10 non-NEURO residents must be on a floater rotation in each block:

```
∑_{r ∈ R \ R_NEURO} ∑_{ω ∈ Floater} y[r, b, ω] ≥ 10    for all b ∈ B
```

---

#### H7 — PGY-Specific Start-of-Year Rules

```
x[r, 0] = index("Medical Teams")     for all r where pgy(r) = "R1"
x[r, 0] ≠ index("Senior Rotation")   for all r where pgy(r) = "R2"
∑_{r ∈ R} y[r, 1, "Medical Teams"]  ≥ 25
```

All R1 residents begin the year on Medical Teams (orientation period). R2 residents may not start the year as Senior Residents. At least 25 residents must be on Medical Teams in Block 2.

---

#### H8 — Consecutive Rotation Limits

**R1:** No more than 5 Medical Teams blocks in any consecutive 6-block window:
```
∑_{b = start}^{start+5} y[r, b, "Medical Teams"] ≤ 5    for all start ∈ {0, …, 7}, r where pgy(r) = "R1"
```

**R2 and R3:** Cannot do Senior Rotation in two consecutive blocks:
```
y[r, b, "Senior Rotation"] + y[r, b+1, "Senior Rotation"] ≤ 1    for all b ∈ {0, …, 11}, r where pgy(r) ∈ {R2, R3}
```

---

#### H9 — Batch Integrity for MICU and CCU

MICU and CCU are 2-block rotations that must not straddle scheduling batch boundaries at blocks 2, 4, 6, 8, 10 (zero-indexed: 1, 3, 5, 7, 9):

```
y[r, b, ω] + y[r, b+1, ω] ≤ 1    for b ∈ {1, 3, 5, 7, 9}, ω ∈ {MICU, CCU}, all r ∈ R
```

---

#### H10 — R_NEURO Fixed Template

Neurology residents follow a fixed partial schedule:
```
x[r, 0] = x[r, 1] = x[r, 2] = index("Medical Teams")
x[r, 11] = x[r, 12] = index("TRANSFER")
    for all r where pgy(r) = "R_NEURO"
```

---

#### H11 — Pre-Assignments

**Forced (single or OR):** resident `r` in block `b` must take one of the rotations in list `F(r, b)`:
```
x[r, b] ∈ {index(ω) : ω ∈ F(r, b)}
```

**Forbidden:** resident `r` in block `b` must not take rotation `ω`:
```
x[r, b] ≠ index(ω)    for all ω ∈ Forbidden(r, b)
```

### 3.4 Soft Constraints and Objective Function

Soft constraints are encoded as auxiliary Boolean variables and added to a weighted objective function that the solver maximises. Each soft constraint variable `s` is True when the pattern is active, and contributes `weight(s)` to the objective. Positive weights are rewards; negative weights are penalties.

```
Maximise:  ∑_s  weight(s) · s
```

The **Normalised Quality Score** is:

```
Q = raw_score / max_possible_score
```

where `max_possible_score = ∑_{s : weight(s) > 0} weight(s)`.

---

**S1 — Consecutive MICU (R2, +2)**  
Rewards R2 residents who complete both required MICU blocks consecutively (better for learning continuity):
```
s_{r,b} = y[r, b, "MICU"] ∧ y[r, b+1, "MICU"]    weight = +2
```

**S2 — Consecutive CCU (R2, +2)**  
Same rationale for CCU:
```
s_{r,b} = y[r, b, "CCU"] ∧ y[r, b+1, "CCU"]    weight = +2
```

**S3 — Consecutive Hematology/Oncology (any eligible PGY, +2)**  
Hematology and Oncology are closely related sub-specialties. Scheduling them consecutively (in either order) supports thematic learning:
```
s_{r,b} = (y[r,b,"Hematology"] ∧ y[r,b+1,"Oncology"]) ∨ (y[r,b,"Oncology"] ∧ y[r,b+1,"Hematology"])
weight = +2
```

**S4 — 4 Consecutive Medical Teams for R1 (penalty, −1)**  
R1 residents need variety. Being stuck on Medical Teams for 4+ consecutive blocks in a window is undesirable:
```
s_{r,start} = (∑_{b=start}^{start+3} y[r, b, "Medical Teams"] == 4)    weight = −1
```

**S5 — Consecutive Cardiology for R1 (penalty, −1)**  
R1 residents doing Cardiology twice in a row is suboptimal for exposure breadth:
```
s_{r,b} = y[r, b, "Cardiology"] ∧ y[r, b+1, "Cardiology"]    weight = −1
```

**S6 — Consecutive Senior Rotation for R3 (penalty, −2)**  
R3 residents should space their Senior Rotation blocks to maximise teaching impact:
```
s_{r,b} = y[r, b, "Senior Rotation"] ∧ y[r, b+1, "Senior Rotation"]    weight = −2
```

**S7 — Senior Rotation with 1-block gap for R3 (penalty, −1)**  
Even a 1-block gap between two Senior Rotation assignments is considered too close:
```
s_{r,b} = y[r, b, "Senior Rotation"] ∧ y[r, b+2, "Senior Rotation"]    weight = −1
```

**S8 — 6 Consecutive Registrar Rotation for R4 (penalty, −2)**  
R4 and R4_Chiefs residents should not be in Registrar Rotation for 6 or more consecutive blocks:
```
s_{r,start} = (∑_{b=start}^{start+5} y[r, b, "Registrar Rotation"] == 6)    weight = −2
```

---

## 4. Input Data Specification

The scheduler reads a single Excel (`.xlsx`) file. Each row corresponds to one resident.

| Column | Type | Required | Description |
|:---|:---|:---:|:---|
| `ID` | String | Yes | Unique resident identifier. |
| `PGY` | String | Yes | One of: R1, R2, R3, R4, R4_Chiefs, R_NEURO. |
| `Leave1Block` | Integer (1–13) | No | Block number of first leave request. |
| `Leave1Half` | String | No | `First Half` or `Second Half`. |
| `Leave2Block` | Integer (1–13) | No | Block number of second leave request. |
| `Leave2Half` | String | No | `First Half` or `Second Half`. |
| `Block_1` … `Block_13` | String | No | Pre-assignment specification (see below). |

**Pre-assignment parsing rules:**

- A plain rotation name → forced single assignment.
- Comma-separated rotation names (no `!`) → forced OR assignment (resident takes exactly one).
- `!RotationName` entries → forbidden assignment (one or more, comma-separated).
- A cell containing both forced and forbidden entries raises a `ValueError`.

---

## 5. Solver and Implementation

**Solver:** Google OR-Tools CP-SAT  
**Language:** Python 3.11  
**Environment:** Conda (`environment.yml` — name: `med-rotation-scheduler`)  
**Key libraries:** `ortools`, `pandas`, `openpyxl`, `streamlit`, `ipywidgets`, `matplotlib`, `seaborn`

The CP-SAT solver is a **complete** solver, meaning:
- If a feasible solution exists, it will find one.
- If no feasible solution exists, it will prove infeasibility (reporting `INFEASIBLE`).
- It explores the search space using SAT-based techniques combined with constraint propagation and linear relaxations.

In practice, the model solves in **seconds to a few minutes** depending on the number of residents, the tightness of staffing constraints, and the number of pre-assignments.

The `soft_constraints_map` in `ScheduleModelBuilder` stores entries as `(BoolVar, weight)` tuples. This design ensures the `SolutionWriter` can recover exact weights for reporting without re-inferring them from description strings — a common source of subtle bugs.

---

## 6. Output and Reporting

The Excel output (`output_schedule.xlsx`) contains the following sheets:

| Sheet | Contents |
|:---|:---|
| `FullSchedule` | All residents and their assignment for each of the 13 blocks. |
| `Summary` | Rotation × block staffing matrix (count of residents per rotation per block). |
| `ObjectiveLog` | Every soft constraint with its status (Active/Inactive) and score contribution. |
| `R1`, `R2`, … | Schedule filtered to each PGY level for easy distribution. |

In addition, the Streamlit interface allows downloading the constraint log as a `.csv` file, and displays:

- The **Normalised Quality Score** (0%–100%+) as a headline metric.
- The **Raw Score** for direct comparison across runs.
- Expandable lists of satisfied and unsatisfied soft constraints.

---

## 7. Configuration Reference

All tuneable parameters are in `scheduler/config.py`.

| Parameter | Type | Description |
|:---|:---|:---|
| `NUM_BLOCKS` | int | Number of scheduling blocks per year (default: 13). |
| `CLINICAL_ROTATIONS` | list | All clinical rotation names. |
| `GRADUATION_REQUIREMENTS` | dict | Per-PGY `PGYRequirement` lists. |
| `LEAVE_ELIGIBLE_ROTATIONS` | dict | Rotations allowed during a half-leave block, per PGY. |
| `PER_BLOCK_MINIMUM_STAFFING` | dict | Minimum resident count per rotation per block. |
| `COVERAGE_GROUPS` | dict | Rotation groupings for weighted on-call coverage rules. |
| `REWARD_WEIGHT` | int | Base weight for soft rewards (default: +1). |
| `PENALTY_WEIGHT` | int | Base weight for soft penalties (default: −1). |

To add a new rotation, add its name to `CLINICAL_ROTATIONS`, add any graduation requirement entries to `GRADUATION_REQUIREMENTS`, and (optionally) add a minimum staffing entry to `PER_BLOCK_MINIMUM_STAFFING`.

---

## 8. Limitations and Future Work

**Current limitations:**

- The model is configured for a specific programme structure (HMC Internal Medicine). Adapting it to another programme requires updating `config.py`.
- The solver's wall-clock time is not bounded; for very large or tightly constrained inputs, the solve can take several minutes.
- There is currently no support for partial-year scheduling (e.g. scheduling blocks 7–13 while fixing 1–6).

**Potential future enhancements:**

- **Time limit configuration** — expose a solver time limit in the UI so users can trade solution quality for speed.
- **Resident preference input** — allow residents to express rotation preferences, encoded as additional soft constraints.
- **Infeasibility diagnosis** — when the solver returns `INFEASIBLE`, automatically identify which constraints are in conflict.
- **Schedule diffing** — compare two generated schedules side-by-side to assess the impact of changing constraints.
- **REST API** — expose the scheduler as a web service endpoint, decoupled from the Streamlit UI.
