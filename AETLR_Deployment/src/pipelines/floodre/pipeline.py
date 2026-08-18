from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
import re

import pandas as pd

from shared.pipeline import PipelineResult


CSV_CONTENT_TYPE = "text/csv; charset=utf-8-sig"

EXPECTED_COLUMNS = {
    "INSURER_REFERENCE",
    "FRID",
    "TOTAL_PREMIUM_PAYABLE",
}


@dataclass(frozen=True)
class FloodReConfig:
    selected_month: str = ""
    version: str = ""


def run(input_bytes: bytes, filename: str, config: FloodReConfig) -> PipelineResult:
    if not input_bytes:
        raise ValueError("FloodRe input blob is empty.")

    report_date = parse_report_date(config.selected_month) if config.selected_month.strip() else pd.Timestamp.today()
    report_month = config.selected_month.strip() or report_date.strftime("%B")
    df = extract(input_bytes)
    output_df, invalid_rows = transform(df, report_date, report_month, config.version)

    safe_month = safe_path_segment(report_date.strftime("%Y-%m-%d"))
    safe_version = safe_path_segment(config.version)
    output_filename = f"FloodRe Output {safe_month} v{safe_version}.csv"
    output_bytes = dataframe_to_csv_bytes(output_df)

    invalid_row_count = len(invalid_rows)

    return PipelineResult(
        output_bytes=output_bytes,
        output_filename=output_filename,
        content_type=CSV_CONTENT_TYPE,
        row_count=len(output_df),
        warnings=[f"Dropped {invalid_row_count} invalid rows."] if invalid_row_count else [],
    )


def extract(input_bytes: bytes) -> pd.DataFrame:
    merlin = load_clean_sheet(input_bytes, "Merlin")
    magic = load_clean_sheet(input_bytes, "Magic")
    return pd.concat([merlin, magic], ignore_index=True)


def load_clean_sheet(input_bytes: bytes, sheet_name: str) -> pd.DataFrame:
    raw = pd.read_excel(BytesIO(input_bytes), sheet_name=sheet_name, header=None, dtype=object)

    header_row_idx = None
    for i, row in raw.iterrows():
        values = set(str(v).strip() for v in row.values if pd.notna(v))
        if EXPECTED_COLUMNS.issubset(values):
            header_row_idx = i
            break

    if header_row_idx is None:
        raise ValueError(f"Header not found in sheet: {sheet_name}")

    df = raw.iloc[header_row_idx + 1 :].copy()
    df.columns = raw.iloc[header_row_idx]
    return df.dropna(how="all")


def transform(
    df: pd.DataFrame,
    report_date: pd.Timestamp,
    report_month: str,
    report_version: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = df.copy()
    valid_mask = df.apply(is_valid_row, axis=1)
    invalid_rows = df[~valid_mask].copy()
    df = df[valid_mask].copy()

    df["INSURER_REFERENCE"] = (
        df["INSURER_REFERENCE"].astype(str) + "-" + df["FRID"].astype(str)
    )
    df["NUMBER_OF_BEDROOMS"] = df["NUMBER_OF_BEDROOMS"].replace("6+", "6")

    uppercase_fields = [
        "PROPERTY_TYPE",
        "PROPERTY_USE",
        "CONSTRUCTION_WALL",
        "CONSTRUCTION_ROOF",
    ]
    for col in uppercase_fields:
        if col in df.columns:
            df[col] = df[col].astype(str).str.upper()

    df["BUILD_BACK_BETTER_ELIGIBLE"] = "Y"
    df["BUILD_BACK_BETTER_SUM_INSURED"] = 10000
    df["BUILD_BACK_BETTER_CLAIM_VALUE_TRIGGER"] = 0

    df["TOTAL_PREMIUM_PAYABLE"] = pd.to_numeric(
        df["TOTAL_PREMIUM_PAYABLE"],
        errors="coerce",
    ).fillna(0)

    line_count = len(df)
    total_premium_payment = df["TOTAL_PREMIUM_PAYABLE"].sum()

    df["DATE"] = report_date.strftime("%Y-%m-%d")
    df["MONTH"] = report_month
    df["VERSION"] = report_version
    df["TYPE"] = 1
    df["LINE_COUNT"] = line_count
    df["TOTAL_PREMIUM_PAYMENT"] = total_premium_payment
    df["INSURER_ID"] = "TAJ1468"
    df["INSURER_NAME"] = "HISCOX LTD"
    df["INSURER_FCA_NUMBER"] = "113849"

    rating_date_columns = [
        "BUILDING_TRANSACTION_RATING_DATE",
        "CONTENTS_TRANSACTION_RATING_DATE",
    ]
    for col in rating_date_columns:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce", dayfirst=True).dt.strftime("%d/%m/%Y")

    return df, invalid_rows


def is_valid_row(row: pd.Series) -> bool:
    required_fields = [
        "INSURER_REFERENCE",
        "FRID",
        "TOTAL_PREMIUM_PAYABLE",
    ]

    for field in required_fields:
        if pd.isna(row.get(field)) or str(row.get(field)).strip() == "":
            return False

    bedrooms = str(row.get("NUMBER_OF_BEDROOMS", "")).strip()
    if bedrooms != "6+" and not bedrooms.isdigit():
        return False

    try:
        float(row["TOTAL_PREMIUM_PAYABLE"])
    except (TypeError, ValueError):
        return False

    ref = str(row["INSURER_REFERENCE"])
    return re.match(r"^[A-Za-z0-9\-]+$", ref) is not None


def parse_report_date(selected_month: str) -> pd.Timestamp:
    value = selected_month.strip()
    for date_format in ("%Y-%m-%d", "%b-%y"):
        try:
            return pd.Timestamp(datetime.strptime(value, date_format))
        except ValueError:
            pass

    raise ValueError(
        f"Invalid selected_month '{selected_month}'. Expected format: YYYY-MM-DD or Jan-26."
    )


def dataframe_to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")


def safe_path_segment(value: str) -> str:
    return value.strip().replace("/", "-").replace("\\", "-")
