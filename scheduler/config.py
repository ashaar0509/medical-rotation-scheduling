# scheduler/config.py

"""
Configuration File for the Medical Rotation Scheduling Model.

This module centralizes all static parameters, business rules, and constants
used by the scheduling application. Modifying these values will directly
impact the model's constraints and objectives.
"""

import os
from dataclasses import dataclass
from typing import Dict, List, Set, Tuple

# ============================================================================
# I. FILE SYSTEM CONFIGURATION
# ============================================================================
# Defines the directory and file names for input and output operations.

# The root directory of the application.
# Assumes this config file is in '.../project_root/scheduler/'
APP_DIR: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Input data directory.
SAMPLE_DATA_DIR: str = os.path.join(APP_DIR, "sample_data")

# Default input and output filenames.
INPUT_FILE: str = "real_example_input.xlsx"
OUTPUT_SCHEDULE_FILE: str = "output_schedule.xlsx"
OUTPUT_DISTRIBUTION_FILE: str = "rotation_distribution.xlsx"


# ============================================================================
# II. CORE MODEL PARAMETERS
# ============================================================================
# Foundational parameters that define the schedule's dimensions.

# The total number of scheduling periods (blocks) in a year.
NUM_BLOCKS: int = 13


# ============================================================================
# III. ROTATION DEFINITIONS
# ============================================================================
# Defines all possible clinical and non-clinical rotations.

# Base list of all clinical rotations offered.
CLINICAL_ROTATIONS: List[str] = [
	"Cardiology", "Endocrine", "Infectious Disease", "AMAU", "Nephrology",
	"Neurology", "CCU", "MICU", "Al Khor", "MOP", "Geriatrics", "Hematology",
	"Oncology", "Al Wakra", "GI", "Pulmonology", "Rheumatology", "ED",
	"Medical Consultation", "Medical Teams", "Senior Rotation",
	"Registrar Rotation",
]

# Special non-clinical or administrative rotation types.
LEAVE_ROTATION: str = "LEAVE"
TRANSFER_ROTATION: str = "TRANSFER"  # Specific to R_NEURO residents

# A comprehensive list of every possible assignment.
ALL_ROTATIONS: List[str] = (
	CLINICAL_ROTATIONS + [LEAVE_ROTATION, TRANSFER_ROTATION]
)


# ============================================================================
# IV. RESIDENT AND ROTATION RULES
# ============================================================================
# Defines rules governing resident eligibility and rotation constraints.

@dataclass(frozen=True)
class PGYRequirement:
	"""
	A structured representation of graduation requirements for a PGY level.
	
	Attributes:
		rotations: A tuple of rotation names that form a requirement group.
		min_blocks: The minimum number of blocks required in this group.
		max_blocks: The maximum number of blocks allowed in this group.
	"""
	rotations: Tuple[str, ...]
	min_blocks: int
	max_blocks: int

# --- PGY-Specific Graduation Requirements ---
# Defines the number of blocks each PGY level must complete for various
# rotation groups. This is a primary driver of the schedule.
GRADUATION_REQUIREMENTS: Dict[str, List[PGYRequirement]] = {
	"R1": [
		PGYRequirement(("Medical Teams",), 4, 7),
		PGYRequirement(("AMAU",), 1, 2),
		PGYRequirement(("Cardiology",), 2, 2),
		PGYRequirement(("Infectious Disease",), 1, 2),
		PGYRequirement(("Endocrine",), 1, 2),
	],
	"R2": [
		PGYRequirement(("Senior Rotation",), 1, 2),
		PGYRequirement(("CCU",), 2, 2),
		PGYRequirement(("MICU",), 2, 2),
		PGYRequirement(("Nephrology",), 1, 2),
		PGYRequirement(("Neurology",), 1, 1),
		PGYRequirement(("Cardiology",), 1, 1),
		PGYRequirement(("Geriatrics",), 1, 1),
		PGYRequirement(("AMAU",), 1, 2),
		PGYRequirement(("Al Khor",), 0, 1),
		PGYRequirement(("MOP",), 1, 1),
	],
	"R3": [
		PGYRequirement(("Senior Rotation",), 2, 2),
		PGYRequirement(("Oncology",), 1, 1),
		PGYRequirement(("Hematology",), 1, 1),
		PGYRequirement(("Al Wakra",), 1, 1),
		PGYRequirement(("GI",), 2, 2),
		PGYRequirement(("Pulmonology",), 2, 2),
		PGYRequirement(("Rheumatology",), 1, 1),
		PGYRequirement(("MOP",), 1, 1),
		PGYRequirement(("AMAU",), 1, 1),
		PGYRequirement(("Cardiology", "ED", "Medical Consultation"), 1, 1),
	],
	"R4": [
		PGYRequirement(("Registrar Rotation",), 5, 6),
		PGYRequirement(("Medical Consultation",), 3, 5),
		PGYRequirement(("Al Wakra",), 1, 2),
		PGYRequirement(("Al Khor",), 1, 2),
		PGYRequirement(("Hematology", "Oncology"), 1, 2),
	],
	"R4_Chiefs": [
		PGYRequirement(("Registrar Rotation",), 5, 7),
		PGYRequirement(("Medical Consultation",), 6, 8),
	],
	"R_NEURO": [
		PGYRequirement(("Medical Teams",), 3, 3),
		PGYRequirement(("AMAU",), 3, 4),
		PGYRequirement(("MICU",), 1, 1),
		PGYRequirement(("Rheumatology",), 1, 1),
		PGYRequirement(("ED",), 2, 2),
		PGYRequirement(("TRANSFER",), 2, 2),
	],
}

# --- Leave Eligibility ---
# Specifies which rotations a resident can be on during a half-block of leave.
LEAVE_ELIGIBLE_ROTATIONS: Dict[str, Set[str]] = {
	"R1": {"Endocrine", "AMAU", "Infectious Disease"},
	"R2": {"MOP", "Nephrology", "AMAU"},
	"R3": {"GI", "Pulmonology", "AMAU"},
	"R4": {"Medical Consultation"},
	"R_NEURO": {"AMAU"},
}


# ============================================================================
# V. STAFFING AND COVERAGE REQUIREMENTS
# ============================================================================
# Defines the minimum number of residents required for specific rotations
# in every block to ensure adequate service coverage.

# --- Per-Block Minimum Staffing ---
# Unweighted count of residents required per block for key rotations.
PER_BLOCK_MINIMUM_STAFFING: Dict[str, int] = {
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

# --- On-Call Group Definitions ---
# These groups are used for complex coverage rules (e.g., weighted sums).
COVERAGE_GROUPS: Dict[str, Set[str]] = {
	"Floater": {"Nephrology", "Endocrine"},
	"2ndOnCall": {"GI", "Rheumatology", "Pulmonology"},
}


# ============================================================================
# VI. OPTIMIZATION OBJECTIVE WEIGHTS
# ============================================================================
# Defines the weights for soft constraints in the objective function.
# These values control the trade-offs the solver makes.
# Positive values indicate rewards; negative values indicate penalties.

# Standard weight for a preferred assignment (reward).
REWARD_WEIGHT: int = 1

# Standard weight for an undesirable assignment (penalty).
PENALTY_WEIGHT: int = -1