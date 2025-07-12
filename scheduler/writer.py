from typing import Any
import pandas as pd
from ortools.sat.python import cp_model
from scheduler.config import idx_to_rotation, BLOCKS

def extract_solution(solver: cp_model.CpSolver, x, residents) -> list[Any]:
	solution = []
	for r, res_id in enumerate(residents):
		row = [res_id]
		for b in range(BLOCKS):
			rot_id = solver.Value(x[r, b])
			row.append(idx_to_rotation[rot_id])
		solution.append(row)
	return solution

def write_output(solution, output_path, pgys):
	columns = ["Resident"] + [f"Block_{i+1}" for i in range(BLOCKS)]
	df = pd.DataFrame(solution, columns=columns)

	# Sheet 1: Summary
	blocks = columns[1:]
	melted = df.melt(id_vars=["Resident"], value_vars=blocks,
					 var_name="Block", value_name="Rotation")
	count_df = (
		melted.groupby(["Rotation", "Block"])
		.size()
		.unstack(fill_value=0)
		.sort_index()
	)
	count_df.index.name = None
	count_df.columns.name = None
	count_df = count_df[blocks]

	# Split by PGY for R1–R4 sheets
	df["PGY"] = pgys
	r1 = df[df["PGY"] == "R1"].drop(columns="PGY")
	r2 = df[df["PGY"] == "R2"].drop(columns="PGY")
	r3 = df[df["PGY"] == "R3"].drop(columns="PGY")
	r4 = df[df["PGY"] == "R4"].drop(columns="PGY")
	r4_neuro = df[df["PGY"] == "R4_NEURO"].drop(columns="PGY")
 

	with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
		count_df.to_excel(writer, sheet_name="Summary")
		df.drop(columns="PGY").to_excel(writer, sheet_name="FullSchedule", index=False)
		r1.to_excel(writer, sheet_name="R1", index=False)
		r2.to_excel(writer, sheet_name="R2", index=False)
		r3.to_excel(writer, sheet_name="R3", index=False)
		r4.to_excel(writer, sheet_name="R4", index=False)
		r4_neuro.to_excel(writer, sheet_name="R4_NEURO", index=False)

def solve_and_export(model, x, residents, output_path, pgys):
	solver = cp_model.CpSolver()
	status = solver.Solve(model)


	if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
		solution = extract_solution(solver, x, residents)
		write_output(solution, output_path, pgys)
		return True, solver
	else:
		return False, None

