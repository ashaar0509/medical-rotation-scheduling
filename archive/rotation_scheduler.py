from pathlib import Path
import pandas as pd
from ortools.sat.python import cp_model
import pandas as pd
import numpy as np
import random

# -------------------------
# Config
# -------------------------
INPUT_FILE = "input_run_fresh.csv"
OUTPUT_XLSX = "input_ran_before.xlsx"
BLOCKS = 13

ROTATIONS = [
    "Cardiology", "Endocrine", "Infectious Disease", "AMAU", "Nephrology",
    "Neurology", "CCU", "MICU", "Al Khor", "MOP", "Geriatrics", "Hematology",
    "Oncology", "Al Wakra", "GI", "Pulmonology", "Rheumatology", "ED",
    "Medical Consultation", "Medical Teams", "Senior Rotation",
    "Registrar Rotation"
]

# This is only relevant in half leaves. # In full blocks, this is irrelevant
LEAVE_ALLOWED = {
    "R1": {"Endocrine", "AMAU", "Infectious Disease"}, # Add LEAVE Rotation
    "R2": {"MOP", "Nephrology", "AMAU"},
    "R3": {"GI", "Pulmonology", "AMAU"},
    "R4": {"Medical Consultation"},
}


GRAD_REQ = {
    "R1": {
        ("Medical Teams",): (7, 8),
        ("AMAU",): (1, 2),
        ("Cardiology",): (2,),
        ("Infectious Disease",): (1, 2),
        ("Endocrine",): (1, 2)
    },
    "R2": {
        ("Senior Rotation",): (1,),
        ("CCU",): (2,),
        ("MICU",): (2,),
        ("Nephrology",): (1, 2),
        ("Neurology",): (1,),
        ("Cardiology",): (1,),
        ("Geriatrics",): (1,),
        ("AMAU",): (1,),
        ("Al Khor",): (1,),
        ("MOP",): (1,)
    },
    "R3": {
        ("Senior Rotation",): (2,),
        ("Oncology",): (1,),
        ("Hematology",): (1,),
        ("Al Wakra",): (1,),
        ("GI",): (2,),
        ("Pulmonology",): (2,),
        ("Rheumatology",): (1,),
        ("AMAU",): (1,),
        ("MOP",): (1,),
        ("Cardiology", "ED", "Medical Consultation"): (1,) # Lrave
    },
    "R4": {
        ("Registrar Rotation",): (5, 6),
        ("Medical Consultation",): (2,),
        ("Al Wakra",): (2,),
        ("Al Khor",): (1,),
        ("Hematology", "Oncology"): (1,)
    }
}


PER_BLOCK_MIN = {
    "Cardiology": 11, "AMAU": 11, "CCU": 7, "MICU": 7,
    "Al Khor": 6, "MOP": 6, "Hematology": 5,
    "Oncology": 5, "Al Wakra": 9, "Medical Consultation": 10
}

# exact 20 3-13
ELIGIBILITY = {
    pgy: set(GRAD_REQ[pgy].keys()) for pgy in GRAD_REQ
}

def add_grad_requirements(model, x, residents, pgy_of, grad_req, rmap):
    relaxed_r1 = {
        ("Medical Teams",): (5, 6),
        ("Endocrine",): (1,),
        ("Infectious Disease",): (1,),
        ("Cardiology",): (1,),
        ("AMAU",): (1,),
    }

    for r_idx, res_id in enumerate(residents):
        pgy = pgy_of[res_id]
        row = df[df["ID"] == res_id].iloc[0]
        start_blk = int(row.get("StartBlock", 1)) - 1  # 0-indexed

        reqs = grad_req[pgy]
        if pgy == "R1" and start_blk > 0:
            reqs = relaxed_r1

        for group, counts in reqs.items():
            total = sum(
                x[r_idx, b, rmap[rot]]
                for rot in group
                for b in range(start_blk, BLOCKS)
            )
            if len(counts) == 1:
                model.Add(total >= counts[0])
            elif max(counts) - min(counts) + 1 == len(counts):
                model.Add(total >= min(counts))
                model.Add(total <= max(counts))
            else:
                flags = []
                for v in counts:
                    y = model.NewBoolVar(f"eq_{res_id}_{group}_{v}")
                    model.Add(total == v).OnlyEnforceIf(y)
                    flags.append(y)
                model.Add(sum(flags) == 1)

def add_leave_rules(model, x, res, pgy_of, leaves, rmap):
    for r, res_id in enumerate(res):
        pgy = pgy_of[res_id]
        allowed_idx = [rmap[rn] for rn in LEAVE_ALLOWED[pgy]]
        for blk in leaves[res_id]:
            model.Add(sum(x[r, blk, t] for t in allowed_idx) == 1)


# -------------------------
# Load Data
# -------------------------
df = pd.read_csv(INPUT_FILE)
residents = df["ID"].tolist()
pgy_of = df.set_index("ID")["PGY"].to_dict()

# -------------------------
# All residents start at Block 0 for a fresh run
# -------------------------
# leave_blocks = {rid: [] for rid in residents}
# leave_fraction = {res_id: {b: 1.0 for b in range(BLOCKS)} for res_id in residents}

start_block_of = {rid: 0 for rid in residents}

leave_blocks = {rid: [] for rid in residents}
for _, row in df.iterrows():
    if pd.notna(row["Leave1Block"]):
        leave_blocks[row["ID"]].append(int(row["Leave1Block"]) - 1)
    if pd.notna(row["Leave2Block"]):
        leave_blocks[row["ID"]].append(int(row["Leave2Block"]) - 1)
leave_blocks

# Build leave fraction table: 1.0 (no leave), 0.5 (half), 0.0 (full block leave)
leave_fraction = {res_id: {b: 1.0 for b in range(BLOCKS)} for res_id in residents}

for _, row in df.iterrows():
    rid = row["ID"]
    blk1, half1 = row["Leave1Block"], row["Leave1Half"]
    blk2, half2 = row["Leave2Block"], row["Leave2Half"]

    if pd.notna(blk1) and pd.notna(half1):
        blk = int(blk1) - 1
        leave_fraction[rid][blk] -= 0.5
    if pd.notna(blk2) and pd.notna(half2):
        blk = int(blk2) - 1
        leave_fraction[rid][blk] -= 0.5
