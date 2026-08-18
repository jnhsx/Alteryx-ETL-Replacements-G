from dataclasses import dataclass
from datetime import date, datetime
from io import BytesIO
from numbers import Real
import re

import pandas as pd

from shared.pipeline import PipelineArtifact, PipelineResult


EXCEL_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument-spreadsheetml.sheet"
POST_DELAY_SHEET_NAME = "Post Delay cases"
TODAY_SHEET_NAME = "Today Cases"
TEAM_ORDER = ("APC", "PSC", "Schemes")

INPUT_COLUMNS = [
    "Policy",
    "Event #",
    "Event Type",
    "Event Description",
    "Industry",
    "Client Name",
    "Broker Name",
    "Broker Branch",
    "I-90 Broker ID",
    "Effective",
    "Effective End date",
    "Processing Date",
    "Premium",
    "Commission",
    "Tax",
    "Section Number",
    "Profit Centre",
    "Post Delay Date",
    "Currency",
    "Country for taxation",
    "State for taxation",
    "Stage",
    "Status",
    "Payment Method",
    "Open Workflows",
    "I90 Suspension",
    "I90 Product Code",
    "Regional Data Stamp",
    "Department",
    "Outstanding Docs",
]

OUTPUT_COLUMNS = [
    "Control",
    "Broker ID",
    "Broker ID Number",
    "Case ID",
    "Policy",
    "Event #",
    "Event Type",
    "Event Description",
    "Industry",
    "Client Name",
    "Broker Name",
    "Broker Branch",
    "I-90 Broker ID",
    "Effective",
    "Effective End date",
    "Premium",
    "Commission",
    "Tax",
    "Section Number",
    "Profit Centre",
    "Currency",
    "Country for taxation",
    "State for taxation",
    "Stage",
    "Status",
    "Payment Method",
    "Open Workflows",
    "I90 Suspension",
    "I90 Product Code",
    "Regional Data Stamp",
    "Department",
    "Outstanding Docs",
    "Processing Date",
    "Post Delay Date",
]

# These assignments are present in the validated legacy output but are absent
# from the supplied agency workbook. The workbook remains authoritative when
# an agency is added there; these values are only used as fallbacks.
LEGACY_TEAM_OVERRIDES = {
    1366: "APC",
    1678: "APC",
    1696: "APC",
    2562: "APC",
    5621: "APC",
    6590: "APC",
    7663: "APC",
    8346: "APC",
    8368: "APC",
    9600: "APC",
    9606: "APC",
    9650: "APC",
    9687: "APC",
    9726: "APC",
    9836: "APC",
    4809: "Schemes",
    8489: "Schemes",
}


@dataclass(frozen=True)
class UnpostedReportsConfig:
    selected_month: str = ""
    version: str = ""


def run(
    hh_bytes: bytes,
    pi_bytes: bytes,
    agency_list_bytes: bytes,
    config: UnpostedReportsConfig,
) -> PipelineResult:
    if not hh_bytes:
        raise ValueError("Unposted Reports HH input blob is empty.")
    if not pi_bytes:
        raise ValueError("Unposted Reports PI input blob is empty.")
    if not agency_list_bytes:
        raise ValueError("Unposted Reports agency list input blob is empty.")

    df_hh = read_policy_workbook(hh_bytes, "HH.xlsx")
    df_pi = read_policy_workbook(pi_bytes, "PI.xlsx")
    df_agencies = read_agency_workbook(agency_list_bytes)

    merged_df = transform(df_hh, df_pi, df_agencies)
    report_date = determine_report_date(merged_df)
    primary_team = TEAM_ORDER[0]
    team_files: list[PipelineArtifact] = []
    primary_bytes = b""
    primary_filename = ""

    for team in TEAM_ORDER:
        team_df = merged_df[merged_df["Control"] == team].copy()
        workbook_bytes = build_team_workbook(team_df, team, report_date=report_date)
        team_filename = build_output_filename(config=config, team=team)
        artifact = PipelineArtifact(
            output_bytes=workbook_bytes,
            output_filename=team_filename,
            content_type=EXCEL_CONTENT_TYPE,
        )
        if team == primary_team:
            primary_bytes = workbook_bytes
            primary_filename = team_filename
        else:
            team_files.append(artifact)

    if not primary_bytes:
        primary_bytes = build_team_workbook(merged_df, primary_team, report_date=report_date)
        primary_filename = build_output_filename(config=config, team=primary_team)

    return PipelineResult(
        output_bytes=primary_bytes,
        output_filename=primary_filename,
        content_type=EXCEL_CONTENT_TYPE,
        row_count=len(merged_df),
        artifacts=team_files,
    )


def read_policy_workbook(content: bytes, display_name: str) -> pd.DataFrame:
    try:
        return pd.read_excel(BytesIO(content), usecols=INPUT_COLUMNS)
    except ValueError as exc:
        raise ValueError(f"{display_name} is missing one or more required columns.") from exc


def read_agency_workbook(content: bytes) -> pd.DataFrame:
    try:
        return pd.read_excel(BytesIO(content))
    except ValueError as exc:
        raise ValueError("agencyList.xlsx could not be read as an Excel workbook.") from exc


def transform(
    df_hh: pd.DataFrame,
    df_pi: pd.DataFrame,
    df_agencies: pd.DataFrame,
) -> pd.DataFrame:
    validate_agency_columns(df_agencies)

    df_merged = pd.concat([df_hh, df_pi], ignore_index=True)
    for col in OUTPUT_COLUMNS:
        if col not in df_merged.columns:
            df_merged[col] = None

    broker_ids = df_merged["I-90 Broker ID"].apply(extract_broker_id)
    agency_lookup = build_agency_lookup(df_agencies)
    df_merged["Control"] = broker_ids.map(agency_lookup)
    df_merged["Control"] = df_merged["Control"].fillna(broker_ids.map(LEGACY_TEAM_OVERRIDES))
    df_merged["Control"] = df_merged["Control"].fillna("PSC").apply(normalize_team_name)

    df_merged["Broker ID"] = broker_ids.apply(format_broker_id)
    df_merged["Broker ID Number"] = broker_ids
    df_merged["Policy"] = df_merged["Policy"].apply(format_integer_identifier)
    df_merged["Event #"] = df_merged["Event #"].apply(format_integer_identifier)
    df_merged["Open Workflows"] = df_merged["Open Workflows"].apply(format_integer_identifier)
    df_merged["I90 Product Code"] = df_merged["I90 Product Code"].apply(
        format_integer_identifier
    )
    df_merged["Case ID"] = df_merged["Policy"] + df_merged["Event #"]

    return df_merged[OUTPUT_COLUMNS]


def validate_agency_columns(df_agencies: pd.DataFrame) -> None:
    required = ["Agency no", "Team"]
    missing = [col for col in required if col not in df_agencies.columns]
    if missing:
        raise ValueError(f"agencyList.xlsx is missing required columns: {', '.join(missing)}")


def build_agency_lookup(df_agencies: pd.DataFrame) -> dict[object, object]:
    agencies = df_agencies[["Agency no", "Team"]].dropna(subset=["Agency no", "Team"]).copy()
    agencies["Broker ID Number"] = agencies["Agency no"].apply(extract_broker_id)
    agencies = agencies.dropna(subset=["Broker ID Number"])
    agencies = agencies.drop_duplicates(subset=["Broker ID Number"], keep="first")
    agencies["Team"] = agencies["Team"].apply(normalize_team_name)
    return agencies.set_index("Broker ID Number")["Team"].to_dict()


def normalize_team_name(team_name: object) -> str:
    if pd.isna(team_name):
        return "PSC"

    cleaned = str(team_name).strip()
    if not cleaned:
        return "PSC"

    normalized = cleaned.lower()
    if normalized in {"apc", "a.p.c", "apc team"}:
        return "APC"
    if normalized in {"psc", "p.s.c"}:
        return "PSC"
    if normalized in {"schemes", "scheme"}:
        return "Schemes"
    return cleaned


def determine_report_date(df: pd.DataFrame) -> pd.Timestamp:
    processing_dates = pd.to_datetime(df["Processing Date"], errors="coerce", dayfirst=True)
    if processing_dates.notna().any():
        return processing_dates.max().normalize()
    return pd.Timestamp.today().normalize()


def build_team_workbook(
    df_team: pd.DataFrame,
    team_name: str,
    report_date: date | datetime | pd.Timestamp | None = None,
) -> bytes:
    output = BytesIO()
    team_df = df_team.copy()

    if "Processing Date" in team_df.columns:
        team_df["Processing Date"] = pd.to_datetime(
            team_df["Processing Date"], errors="coerce", dayfirst=True
        )
    if "Post Delay Date" in team_df.columns:
        team_df["Post Delay Date"] = pd.to_datetime(
            team_df["Post Delay Date"], errors="coerce", dayfirst=True
        )

    effective_report_date = (
        pd.Timestamp(report_date).normalize()
        if report_date is not None
        else determine_report_date(team_df)
    )
    today_mask = team_df["Processing Date"].dt.normalize() == effective_report_date
    post_delay_mask = (
        ~today_mask
        & team_df["Post Delay Date"].notna()
        & (team_df["Post Delay Date"].dt.normalize() >= effective_report_date)
    )

    post_delay_df = team_df[post_delay_mask].copy()
    today_cases_df = team_df[today_mask].copy()
    team_sheet_df = team_df[~today_mask & ~post_delay_mask].copy()

    # Write sheets in the expected order and with expected names:
    # "Post Delay cases", "<TEAM>", "Today Cases"
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        post_delay_df.to_excel(writer, index=False, sheet_name=POST_DELAY_SHEET_NAME)
        team_sheet_df.to_excel(writer, index=False, sheet_name=str(team_name))
        today_cases_df.to_excel(writer, index=False, sheet_name=TODAY_SHEET_NAME)

    return output.getvalue()


def build_output_filename(config: UnpostedReportsConfig, team: str) -> str:
    team_suffix = f" {team}" if team else ""
    if config.selected_month.strip() or config.version.strip():
        safe_month = safe_path_segment(config.selected_month)
        safe_version = safe_path_segment(config.version)
        return f"UNP Output {safe_month} v{safe_version}{team_suffix}.xlsx"
    return f"UNP Output {datetime.today():%Y%m%d}{team_suffix}.xlsx"


def extract_broker_id(i90_id: object) -> int | None:
    if pd.isna(i90_id):
        return None
    if isinstance(i90_id, Real) and not isinstance(i90_id, bool):
        numeric_id = float(i90_id)
        return int(numeric_id) if numeric_id.is_integer() else None

    match = re.search(r"(\d{1,7})$", str(i90_id).strip())
    if match is None:
        return None
    return int(match.group(1))


def format_broker_id(broker_id: object) -> str | None:
    return format_integer_identifier(broker_id)


def format_integer_identifier(value: object) -> str | None:
    if pd.isna(value):
        return None
    if isinstance(value, Real) and not isinstance(value, bool):
        numeric = float(value)
        return str(int(numeric)) if numeric.is_integer() else str(value)
    return str(value).strip()


def safe_path_segment(value: str) -> str:
    return value.strip().replace("/", "-").replace("\\", "-")
