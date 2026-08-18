from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import pandas as pd

from shared.pipeline import PipelineResult


BIKMO_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@dataclass(frozen=True)
class BikmoConfig:
    selected_month: str = ""
    version: str = ""


RENAME_COLUMNS = {
    "Insured Name": "Client Name",
    "Period Start Date": "Policy Start Date",
    "Annual Premium": "old Annual Premium",
    "Period End Date": "Policy End Date",
    "Reason Description": "Cancellation reason",
    "Date": "Cancellation Processing Date",
}

NUMERIC_COLUMNS = [
    "old Annual Premium",
    "Transaction Premium",
    "Transaction Commision",
    "Transaction Tax",
]

FINAL_COLUMNS = [
    "Policy",
    "Broker Reference",
    "Client Name",
    "Policy Start Date",
    "Policy End Date",
    "Annual Premium",
    "Cancellation Effective",
    "Cancellation Processing Date",
    "Cancellation return Premium",
    "Commission",
    "Tax",
    "Cancellation reason",
]

REQUIRED_INPUT_COLUMNS = [
    "Policy",
    "Broker Reference",
    "Client Name",
    "Policy Start Date",
    "Policy End Date",
    "old Annual Premium",
    "Effective date",
    "Transaction Premium",
    "Transaction Commision",
    "Transaction Tax",
    "Cancellation reason",
    "Cancellation Processing Date",
]


def run(input_bytes: bytes, filename: str, config: BikmoConfig) -> PipelineResult:
    if not input_bytes:
        raise ValueError("Bikmo input blob is empty.")

    source_name = Path(filename).name
    df = pd.read_excel(BytesIO(input_bytes), sheet_name="report")
    output_df, start_date, end_date = transform(df)

    output_filename = build_output_filename(source_name, start_date, end_date, config)
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        output_df.to_excel(writer, index=False, sheet_name="Data")

    return PipelineResult(
        output_bytes=output.getvalue(),
        output_filename=output_filename,
        content_type=BIKMO_CONTENT_TYPE,
        row_count=len(output_df),
    )


def transform(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Timestamp | None, pd.Timestamp | None]:
    df = df.rename(columns=RENAME_COLUMNS).copy()
    validate_required_columns(df)

    for col in NUMERIC_COLUMNS:
        df[col] = pd.to_numeric(df[col].replace("", 0), errors="coerce").fillna(0)

    df["Annual Premium"] = df["old Annual Premium"].apply(format_currency)
    df["Cancellation Effective"] = pd.to_datetime(
        df["Effective date"], errors="coerce"
    ).dt.strftime("%Y-%m-%d")
    df["Cancellation return Premium"] = df["Transaction Premium"].apply(format_currency)
    df["Commission"] = df["Transaction Commision"].apply(format_currency)
    df["Tax"] = df["Transaction Tax"].apply(format_currency)

    start_dates = pd.to_datetime(df["Policy Start Date"], errors="coerce")
    end_dates = pd.to_datetime(df["Policy End Date"], errors="coerce")

    output_df = df[FINAL_COLUMNS].copy().astype(str)
    return output_df, start_dates.min(), end_dates.max()


def validate_required_columns(df: pd.DataFrame) -> None:
    missing_columns = sorted(col for col in REQUIRED_INPUT_COLUMNS if col not in df.columns)
    if missing_columns:
        missing = ", ".join(missing_columns)
        raise ValueError(f"Bikmo input is missing required columns: {missing}")


def format_currency(value: object) -> str:
    try:
        return f"£{float(value):,.2f}"
    except (TypeError, ValueError):
        return "£0.00"


def build_output_filename(
    source_name: str,
    start_date: pd.Timestamp | None,
    end_date: pd.Timestamp | None,
    config: BikmoConfig,
) -> str:
    if pd.isna(start_date) or pd.isna(end_date):
        date_label = "unknown dates"
    else:
        date_label = f"{start_date:%d.%m.%y} to {end_date:%d.%m.%y}"

    source_stem = Path(source_name).stem
    suffix_parts = []
    if config.selected_month.strip():
        suffix_parts.append(config.selected_month.strip().replace("/", "-").replace("\\", "-"))
    if str(config.version).strip():
        safe_version = str(config.version).strip().replace("/", "-").replace("\\", "-")
        suffix_parts.append(f"v{safe_version}")

    suffix = f" {' '.join(suffix_parts)}" if suffix_parts else ""
    return f"Bikmo Report {date_label}{suffix} ({source_stem}).xlsx"
