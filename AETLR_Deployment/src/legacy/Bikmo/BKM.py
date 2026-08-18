import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipelines.bikmo import BikmoConfig, run


BASE_DIR = Path(__file__).resolve().parent
INPUT_DIR = BASE_DIR / "Input"
OUTPUT_DIR = BASE_DIR / "Output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def process_local_file(input_path: Path) -> Path:
    result = run(
        input_bytes=input_path.read_bytes(),
        filename=input_path.name,
        config=BikmoConfig(),
    )
    output_path = OUTPUT_DIR / result.output_filename
    output_path.write_bytes(result.output_bytes)
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Bikmo ETL locally.")
    parser.add_argument(
        "input_file",
        nargs="?",
        help="Input .xlsx file. Defaults to all files in Bikmo/Input.",
    )
    args = parser.parse_args()

    start_time = time.perf_counter()
    input_files = [Path(args.input_file)] if args.input_file else sorted(INPUT_DIR.glob("*.xlsx"))

    if not input_files:
        raise SystemExit(f"No local .xlsx files found in {INPUT_DIR}")

    for input_file in input_files:
        output_path = process_local_file(input_file)
        print(f"Finished: {output_path}")

    end_time = time.perf_counter()
    print(f"ETL completed in {end_time - start_time:.2f} seconds")


if __name__ == "__main__":
    main()
