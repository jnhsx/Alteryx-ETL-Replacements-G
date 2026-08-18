import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipelines.bdx_tracker import BdxTrackerConfig, run


BASE_DIR = Path(__file__).resolve().parent
INPUT_FILE = BASE_DIR / "Input" / "Bdx tracker 2026.xlsm"
OUTPUT_DIR = BASE_DIR / "Output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def process_local_file(input_path: Path, selected_month: str) -> list[Path]:
    result = run(
        input_bytes=input_path.read_bytes(),
        filename=input_path.name,
        config=BdxTrackerConfig(selected_month=selected_month),
    )

    output_paths = []
    primary_output = OUTPUT_DIR / result.output_filename
    primary_output.write_bytes(result.output_bytes)
    output_paths.append(primary_output)

    for artifact in result.artifacts:
        artifact_output = OUTPUT_DIR / artifact.output_filename
        artifact_output.write_bytes(artifact.output_bytes)
        output_paths.append(artifact_output)

    return output_paths


def main() -> None:
    parser = argparse.ArgumentParser(description="Run BDX Tracker ETL locally.")
    parser.add_argument(
        "input_file",
        nargs="?",
        default=str(INPUT_FILE),
        help="Input .xlsm or .xlsx file.",
    )
    parser.add_argument("--selected-month", required=True, help="Month column to process, e.g. Jan-26.")
    args = parser.parse_args()

    start_time = time.perf_counter()
    output_paths = process_local_file(Path(args.input_file), args.selected_month)

    print("BDX Tracker transformation completed successfully.")
    for output_path in output_paths:
        print(f"Output written to: {output_path}")

    end_time = time.perf_counter()
    print(f"ETL completed in {end_time - start_time:.2f} seconds")


if __name__ == "__main__":
    main()
