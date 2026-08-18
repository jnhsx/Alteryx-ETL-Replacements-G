import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipelines.floodre import FloodReConfig, run


BASE_DIR = Path(__file__).resolve().parent
INPUT_DIR = BASE_DIR / "Input"
OUTPUT_DIR = BASE_DIR / "Output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def process_local_file(input_path: Path, version: str) -> list[Path]:
    result = run(
        input_bytes=input_path.read_bytes(),
        filename=input_path.name,
        config=FloodReConfig(version=version),
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
    parser = argparse.ArgumentParser(description="Run FloodRe ETL locally.")
    parser.add_argument(
        "input_file",
        nargs="?",
        help="Input .xlsx file. Defaults to the first .xlsx file in FloodRe/Input.",
    )
    parser.add_argument("--version", required=True)
    args = parser.parse_args()

    start_time = time.perf_counter()
    input_path = Path(args.input_file) if args.input_file else next(INPUT_DIR.glob("*.xlsx"))
    output_paths = process_local_file(input_path, args.version)

    print("FloodRe transformation completed successfully.")
    for output_path in output_paths:
        print(f"Output written to: {output_path}")
    print(f"ETL completed in {time.perf_counter() - start_time:.2f} seconds")


if __name__ == "__main__":
    main()
