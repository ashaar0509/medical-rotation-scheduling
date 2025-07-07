# -------------------------------
# Global Constants and Parameters
# -------------------------------

BLOCKS = 13

# -------------------------------
# Rotation Definitions
# -------------------------------
ROTATIONS = [
    "Cardiology", "Endocrine", "Infectious Disease", "AMAU", "Nephrology",
    "Neurology", "CCU", "MICU", "Al Khor", "MOP", "Geriatrics", "Hematology",
    "Oncology", "Al Wakra", "GI", "Pulmonology", "Rheumatology", "ED",
    "Medical Consultation", "Medical Teams", "Senior Rotation",
    "Registrar Rotation",
]

LEAVE_ROTATION = "LEAVE"
ROTATIONS.append(LEAVE_ROTATION)

# -------------------------------
# Leave-Eligible Rotations by PGY
# -------------------------------
LEAVE_ALLOWED = {
    "R1": {"Endocrine", "AMAU", "Infectious Disease"},
    "R2": {"MOP", "Nephrology", "AMAU"},
    "R3": {"GI", "Pulmonology", "AMAU"},
    "R4": {"Medical Consultation"},
}

# -------------------------------
# Graduation Requirements by PGY
# -------------------------------
GRAD_REQ = {
    "R1": {
        ("Medical Teams",): (4, 5, 6, 7),
        ("AMAU",): (1, 2),
        ("Cardiology",): (2,),
        ("Infectious Disease",): (1, 2),
        ("Endocrine",): (1, 2),
    },
    "R2": {
        ("Senior Rotation",): (1,2),
        ("CCU",): (2,),
        ("MICU",): (2,),
        ("Nephrology",): (1, 2),
        ("Neurology",): (1,),
        ("Cardiology",): (1,),
        ("Geriatrics",): (1,),
        ("AMAU",): (1, 2),
        ("Al Khor",): (0, 1),
        ("MOP",): (1,),
    },
    "R3": {
        ("Senior Rotation",): (2,),
        ("Oncology",): (1,),
        ("Hematology",): (1,),
        ("Al Wakra",): (1,),
        ("GI",): (2,),
        ("Pulmonology",): (2,),
        ("Rheumatology",): (1,),
        ("MOP",): (1,),
        ("AMAU",): (1,),
        ("Cardiology", "ED", "Medical Consultation"): (1,),
    },
    "R4": {
        ("Registrar Rotation",): (5, 6),
        ("Medical Consultation",): (3, 4, 5,),
        ("Al Wakra",): (1, 2),
        ("Al Khor",): (1, 2),
        ("Hematology", "Oncology"): (1, 2),
    },
    "R4_Chiefs": {
        ("Registrar Rotation", ): (5, 6, 7),
        ("Medical Consultation",): (6, 7, 8),
    }
}

# -------------------------------
# Per-block Minimum Requirements
# -------------------------------
PER_BLOCK_MIN = {
    "Cardiology": 11,
    "AMAU": 11,
    "CCU": 7,
    "MICU": 7,
    "Al Khor": 6,
    "MOP": 6,
    "Hematology": 5,
    "Oncology": 5,
    "Al Wakra": 9,
    "Medical Consultation": 10,
    "Medical Teams": 20,
}


# -------------------------------
# Eligibility Matrix
# -------------------------------
ELIGIBILITY = {
    pgy: {rot for group in GRAD_REQ[pgy] for rot in group}
    for pgy in GRAD_REQ
}
for pgy in ELIGIBILITY:
    ELIGIBILITY[pgy].add(LEAVE_ROTATION)

# -------------------------------
# Rotation Group Definitions
# -------------------------------
group_defs = {
    "Floater": {"Nephrology", "Endocrine"},
    "2ndOnCall": {"GI", "Rheumatology", "Pulmonology"},
}

rotation_to_idx = {rot: i for i, rot in enumerate(ROTATIONS)}
idx_to_rotation = {i: rot for rot, i in rotation_to_idx.items()}
LEAVE_IDX = rotation_to_idx[LEAVE_ROTATION]