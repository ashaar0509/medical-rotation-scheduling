# scheduler/parser.py

"""
Input Data Parser for the Medical Rotation Scheduling Model.

This module is responsible for reading the primary input Excel file, which
contains resident information, leave requests, and pre-assignments. It parses
this data into a structured format that can be directly used by the model
builder.
"""

import pandas as pd
from typing import Any, Dict, List, Set, Tuple

# Import constants and structured classes from the configuration module
from scheduler.config import (
	NUM_BLOCKS,
	GRADUATION_REQUIREMENTS,
	LEAVE_ELIGIBLE_ROTATIONS,
	ALL_ROTATIONS,
	LEAVE_ROTATION,
	TRANSFER_ROTATION
)

class RotationDataParser:
	"""
	Parses and holds all input data for the scheduling problem.

	This class reads a specified Excel file upon initialization and transforms
	its contents into various Python data structures. These attributes are
	then consumed by the model builder to construct the constraints.
	"""
	def __init__(self, input_file_path: str):
		"""
		Initializes the data parser and triggers the parsing process.

		Args:
			input_file_path: The absolute path to the input Excel data file.
		"""
		# --- Public Attributes ---
		# These attributes store the parsed data and are intended for public
		# access by other components of the scheduler.

		# Core resident and rotation lists
		self.residents: List[str] = []
		self.pgys: List[str] = []

		# Mappings for resident and rotation indices
		self.resident_to_idx: Dict[str, int] = {}
		self.rotation_to_idx: Dict[str, int] = {
			rot: i for i, rot in enumerate(ALL_ROTATIONS)
		}
		self.idx_to_rotation: Dict[int, str] = {
			i: rot for rot, i in self.rotation_to_idx.items()
		}

		# Special index for the LEAVE rotation
		self.leave_idx: int = self.rotation_to_idx[LEAVE_ROTATION]

		# Dictionaries for storing specific constraints and rules
		self.leave_dict: Dict[str, Dict[str, Any]] = {}
		self.forced_assignments: Dict[Tuple[int, int], str] = {}
		self.forbidden_assignments: Dict[Tuple[int, int], str] = {}
		self.eligibility_map: Dict[str, Set[str]] = {}

		# --- Initialization ---
		self._execute_parsing_workflow(input_file_path)

	@property
	def num_residents(self) -> int:
		"""Returns the total number of residents parsed from the input."""
		return len(self.residents)

	def _execute_parsing_workflow(self, file_path: str) -> None:
		"""
		Manages the step-by-step process of data parsing and structuring.
		
		Args:
			file_path: The path to the input Excel file.
		"""
		# 1. Read the raw data from the Excel file into a DataFrame.
		source_df = self._read_source_file(file_path)

		# 2. Parse the DataFrame to populate core data attributes.
		self._parse_dataframe(source_df)
		
		# 3. Build the PGY-to-rotation eligibility map based on grad reqs.
		self._build_eligibility_map()

		# 4. Create the final resident-to-index mapping.
		self.resident_to_idx = {
			res: i for i, res in enumerate(self.residents)
		}

	def _read_source_file(self, file_path: str) -> pd.DataFrame:
		"""
		Reads the source Excel file and prepares it for parsing.

		Args:
			file_path: The path to the input Excel file.
		
		Returns:
			A pandas DataFrame with null values filled for safe processing.
		"""
		# Fill missing values for leave blocks to prevent errors.
		# An empty leave request is equivalent to 0.
		fill_values = {
			"Leave1Block": 0,
			"Leave2Block": 0,
			"Leave1Half": "",
			"Leave2Half": ""
		}
		return pd.read_excel(file_path).fillna(fill_values)

	def _parse_dataframe(self, df: pd.DataFrame) -> None:
		"""
		Iterates through the source DataFrame to populate the main data
		attributes of the class.

		Args:
			df: The pre-processed pandas DataFrame from the input file.
		"""
		self.residents = df["ID"].tolist()
		self.pgys = df["PGY"].tolist()

		for resident_idx, row in enumerate(df.itertuples(index=False)):
			resident_id = row.ID
			
			# Parse leave requests
			self._parse_leave_requests(resident_id, row)

			# Parse pre-determined block assignments (forced/forbidden)
			self._parse_block_assignments(resident_idx, row)

	def _parse_leave_requests(self, resident_id: str, row: Any) -> None:
		"""
		Parses full and half-block leave requests for a single resident.

		Args:
			resident_id: The unique identifier for the resident.
			row: A row from the input DataFrame (as a named tuple).
		"""
		block1 = int(row.Leave1Block)
		block2 = int(row.Leave2Block)
		
		full_leave_blocks, half_leave_blocks = set(), set()

		if block1 and (block1 == block2):
			# If both leave blocks are the same, it's a full-block leave.
			full_leave_blocks.add(block1)
		else:
			# Otherwise, they are treated as separate half-block leaves.
			if block1:
				half_leave_blocks.add(block1)
			if block2:
				half_leave_blocks.add(block2)
		
		self.leave_dict[resident_id] = {
			"pgy": row.PGY,
			"full": full_leave_blocks,
			"half": half_leave_blocks
		}

	def _parse_block_assignments(
		self, resident_idx: int, row: Any
	) -> None:
		"""
		Parses forced and forbidden rotation assignments for a resident.

		Args:
			resident_idx: The 0-based index of the resident.
			row: A row from the input DataFrame.
		"""
		for b in range(1, NUM_BLOCKS + 1):
			column_name = f"Block_{b}"
			assignment_str = str(getattr(row, column_name, "")).strip()

			if not assignment_str or assignment_str.lower() in {"nan", "none"}:
				continue

			# Model blocks are 0-indexed, so we subtract 1.
			assignment_key = (resident_idx, b - 1)
			
			if assignment_str.startswith("!"):
				# A '!' prefix indicates a forbidden assignment.
				forbidden_rotation = assignment_str[1:]
				self.forbidden_assignments[assignment_key] = forbidden_rotation
			else:
				# Otherwise, it is a forced assignment.
				self.forced_assignments[assignment_key] = assignment_str

	def _build_eligibility_map(self) -> None:
		"""
		Constructs a dictionary mapping each PGY level to the set of
		rotations they are eligible to take, based on graduation requirements.
		"""
		eligibility = {}
		for pgy, req_list in GRADUATION_REQUIREMENTS.items():
			# Flatten the list of all rotations mentioned in requirements.
			allowed_rotations = {
				rot for req in req_list for rot in req.rotations
			}
			eligibility[pgy] = allowed_rotations

		# Add special administrative rotations to the eligibility sets.
		for pgy in eligibility:
			eligibility[pgy].add(LEAVE_ROTATION)
			if pgy == "R_NEURO":
				eligibility[pgy].add(TRANSFER_ROTATION)
		
		self.eligibility_map = eligibility