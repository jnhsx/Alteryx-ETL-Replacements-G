import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipelines.unposted_reports import UnpostedReportsConfig, run


BASE_DIR = Path(__file__).resolve().parent
INPUT_DIR = BASE_DIR / "Input"
OUTPUT_DIR = BASE_DIR / "Output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_HH_FILE = INPUT_DIR / "HH.xlsx"
DEFAULT_PI_FILE = INPUT_DIR / "PI.xlsx"
DEFAULT_AGENCY_LIST_FILE = INPUT_DIR / "agencyList.xlsx"


def process_local_files(
    hh_file: Path,
    pi_file: Path,
    agency_list_file: Path,
) -> list[Path]:
    result = run(
        hh_bytes=hh_file.read_bytes(),
        pi_bytes=pi_file.read_bytes(),
        agency_list_bytes=agency_list_file.read_bytes(),
        config=UnpostedReportsConfig(),
    )

    output_paths: list[Path] = []
    for artifact in [result] + list(result.artifacts):
        output_path = OUTPUT_DIR / artifact.output_filename
        output_path.write_bytes(artifact.output_bytes)
        output_paths.append(output_path)
    return output_paths


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Unposted Reports ETL locally.")
    parser.add_argument("--hh-file", default=str(DEFAULT_HH_FILE))
    parser.add_argument("--pi-file", default=str(DEFAULT_PI_FILE))
    parser.add_argument("--agency-list-file", default=str(DEFAULT_AGENCY_LIST_FILE))
    args = parser.parse_args()

    start_time = time.perf_counter()
    output_paths = process_local_files(
        hh_file=Path(args.hh_file),
        pi_file=Path(args.pi_file),
        agency_list_file=Path(args.agency_list_file),
    )

    print("Unposted Reports transformation completed successfully.")
    print("Output written to:")
    for output_path in output_paths:
        print(f"- {output_path}")
    print(f"ETL completed in {time.perf_counter() - start_time:.2f} seconds")


if __name__ == "__main__":
    main()
