from typing import Any
import pandas as pd
from ortools.sat.python import cp_model
from scheduler.config import idx_to_rotation, BLOCKS # type: ignore

def extract_solution(solver: cp_model.CpSolver, x, residents) -> list[Any]:
	solution = []
	for r, res_id in enumerate(residents):
		row = [res_id]
		for b in range(BLOCKS):
			rot_id = solver.Value(x[r, b])
			row.append(idx_to_rotation[rot_id])
		solution.append(row)
	return solution

def write_output(solution, output_path) -> None:
	columns = ["Resident"] + [f"Block_{i+1}" for i in range(BLOCKS)]
	df = pd.DataFrame(solution, columns=columns)
	df.to_excel(output_path, index=False)

def solve_and_export(model, x, residents, output_path) -> bool:
	solver = cp_model.CpSolver()
	status = solver.Solve(model)

	if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
		solution = extract_solution(solver, x, residents)
		write_output(solution, output_path)
		return True
	else:
		return False
