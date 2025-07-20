# Medical Residency Rotation Scheduler

![Python Version](https://img.shields.io/badge/python-3.9+-blue.svg)

A sophisticated, automated scheduling system for medical residency programs, built using Python and Google's OR-Tools (CP-SAT solver). This project transforms the complex, manual task of assigning annual rotations into a streamlined, optimized, and error-free process.

The system is designed to handle the intricate web of constraints inherent in academic medicine, including PGY-specific graduation requirements, minimum staffing levels for clinical services, and individual resident leave requests. It produces a globally feasible and high-quality 13-block annual schedule, presented through an interactive web interface built with Streamlit.

---

## Features

-   **Constraint-Based Optimization:** Utilizes the powerful CP-SAT solver to find schedules that satisfy all mandatory (hard) constraints.
-   **Schedule Quality Optimization:** Maximizes a configurable objective function to adhere to desirable (soft) constraints, such as ensuring certain rotations are scheduled consecutively.
-   **Modular Architecture:** The backend logic is cleanly separated into modules for configuration, data parsing, model building, and output generation, following best practices in software engineering.
-   **Interactive Web Interface:** A user-friendly Streamlit application allows for easy uploading of input files and clear visualization of the results.
-   **Comprehensive Reporting:** Generates a multi-sheet Excel report with the full schedule, a per-block staffing summary, and PGY-specific views.
-   **Detailed Objective Analysis:** Provides a complete log of which soft constraints were satisfied or violated, along with a normalized quality score for the generated schedule.
-   **Flexible Input Format:** Supports complex pre-assignments, including forcing a resident into one of several rotations (OR condition) and forbidding multiple rotations in a single block.

---

## Project Structure

The project is organized into a modular `scheduler` package and a Streamlit front-end.

```
medical-rotation-scheduling/
|-- scheduler/
|   |-- config.py         # All static parameters and business rules
|   |-- parser.py         # Handles parsing of the input Excel file
|   |-- model.py          # Builds the CP-SAT constraint model
|   |-- writer.py         # Formats and writes the output files
|   |-- main.py           # Orchestrates the entire scheduling workflow
|-- sample_data/
|   |-- real_example_input.xlsx # An example of the input file format
|-- app.py                # The Streamlit user interface
|-- requirements.txt      # Project dependencies
|-- README.md             # This file
```

---

## Installation

To set up the project locally, follow these steps. It is highly recommended to use a virtual environment.

1.  **Clone the Repository**
    ```bash
    git clone [https://github.com/your-username/medical-rotation-scheduling.git](https://github.com/your-username/medical-rotation-scheduling.git)
    cd medical-rotation-scheduling
    ```

2.  **Create and Activate a Virtual Environment**
    ```bash
    # For macOS/Linux
    python3 -m venv myenv
    source myenv/bin/activate

    # For Windows
    python -m venv myenv
    myenv\Scripts\activate
    ```

3.  **Install Dependencies**
    The project's dependencies are listed in the `requirements.txt` file.
    ```bash
    pip install -r requirements.txt
    ```

---

## Usage

The application is run through the Streamlit interface.

1.  **Launch the Application**
    Make sure you are in the root directory of the project (`medical-rotation-scheduling/`) and your virtual environment is activated. Then, run the following command:
    ```bash
    streamlit run app.py
    ```

2.  **Use the Web Interface**
    -   Your web browser will open to the application's main page.
    -   Use the file uploader to select your input Excel file (an example is provided in the `sample_data` directory).
    -   Click the "Run Scheduler" button to start the optimization process.
    -   Once complete, the results will be displayed on the page, and you can download the full schedule and the objective log.

---

## Input File Format

The scheduler requires a single Excel (`.xlsx`) file with a specific structure.

| Column | Type | Description |
| :--- | :--- | :--- |
| `ID` | Text | A unique identifier for each resident. |
| `PGY` | Text | The resident's postgraduate year (e.g., R1, R2, R4_Chiefs). |
| `Leave1Block` | Number | The block number (1-13) for the first leave request. |
| `Leave1Half` | Text | The half of the block for the first leave (e.g., "First Half"). |
| `Leave2Block` | Number | The block number for the second leave request. |
| `Leave2Half` | Text | The half of the block for the second leave. |
| `Block_1`...`Block_13`| Text | Columns for specifying pre-assignments. |

### Specifying Pre-assignments

In the `Block_1` through `Block_13` columns, you can specify three types of pre-assignments:

1.  **Forced Assignment (Single):** To lock a resident into one rotation.
    -   **Example:** `Cardiology`

2.  **Forced Assignment (OR Condition):** To force a resident into one of several possible rotations.
    -   **Example:** `Cardiology, AMAU` (The resident will be assigned to either Cardiology or AMAU).

3.  **Forbidden Assignments:** To prevent a resident from being assigned to one or more rotations.
    -   **Example (Single):** `!MICU`
    -   **Example (Multiple):** `!Cardiology, !MICU`

**Important Note:** A single cell cannot contain both forced and forbidden assignments (e.g., `AMAU, !Cardiology`), as this is a logical contradiction. The application will raise an error if it detects such an entry.

---

## Constraints Overview

The model is governed by a comprehensive set of hard (mandatory) and soft (preferential) constraints. For a complete technical and mathematical description of all constraints, please refer to the `Technical_Report.pdf` document in this repository.

### Hard Constraints
-   **Assignment Rules:** Each resident has exactly one assignment per block.
-   **Graduation Requirements:** PGY-specific rules on the number of blocks required for certain rotations.
-   **Staffing Levels:** Minimum and exact staffing requirements for all key clinical services.
-   **Sequential Rules:** Rules preventing residents from taking certain rotations consecutively.

### Soft Constraints
-   **Penalties:** Discouraging undesirable patterns (e.g., too many consecutive "Medical Teams" blocks for an R1).
-   **Rewards:** Encouraging desirable patterns (e.g., scheduling "MICU" or "Hematology/Oncology" in consecutive blocks).