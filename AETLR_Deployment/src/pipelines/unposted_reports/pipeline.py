from dataclasses import dataclass
from datetime import datetime, timedelta
from io import BytesIO

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
    "Effective End Date",
    "Premium",
    "Commission",
    "Tax",
    "Section Number",
    "Profit Centre",
    "Currency",
    "Country for taxation",
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
    "Action",
    "Comments",
    "Date",
    "Start Time",
    "End Time",
    "Time Taken",
    "Processed By",
    "Team that deals",
]


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
    primary_team = TEAM_ORDER[0]
    team_files: list[PipelineArtifact] = []
    primary_bytes = b""
    primary_filename = ""

    for team in TEAM_ORDER:
        team_df = merged_df[merged_df["Control"] == team].copy()
        workbook_bytes = build_team_workbook(team_df, team)
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
        primary_bytes = build_team_workbook(merged_df, primary_team)
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
    df_merged = df_merged.rename(columns={"Effective End date": "Effective End Date"})

    for col in OUTPUT_COLUMNS:
        if col not in df_merged.columns:
            df_merged[col] = None

    agency_lookup = build_agency_lookup(df_agencies)
    df_merged["Control"] = df_merged["I-90 Broker ID"].map(agency_lookup)
    df_merged["Control"] = df_merged["Control"].apply(normalize_team_name)
    df_merged["Control"] = df_merged["Control"].fillna("PSC")

    broker_ids = df_merged["I-90 Broker ID"].apply(extract_broker_id)
    df_merged["Broker ID"] = broker_ids
    df_merged["Broker ID Number"] = broker_ids
    df_merged["Case ID"] = df_merged["Policy"].astype(str) + df_merged["Event #"].astype(str)

    df_merged["Effective"] = pd.to_datetime(df_merged["Effective"], errors="coerce", dayfirst=True)
    df_merged["Processing Date"] = pd.to_datetime(df_merged["Processing Date"], errors="coerce", dayfirst=True)
    df_merged["Post Delay Date"] = pd.to_datetime(df_merged["Post Delay Date"], errors="coerce", dayfirst=True)
    df_merged["Time Taken"] = (df_merged["Processing Date"] - df_merged["Effective"]).dt.days

    return df_merged[OUTPUT_COLUMNS]


def validate_agency_columns(df_agencies: pd.DataFrame) -> None:
    required = ["Agency no", "Team"]
    missing = [col for col in required if col not in df_agencies.columns]
    if missing:
        raise ValueError(f"agencyList.xlsx is missing required columns: {', '.join(missing)}")


def build_agency_lookup(df_agencies: pd.DataFrame) -> dict[object, object]:
    agencies = df_agencies[["Agency no", "Team"]].dropna(subset=["Agency no"]).copy()
    agencies = agencies.drop_duplicates(subset=["Agency no"], keep="first")
    agencies["Team"] = agencies["Team"].apply(normalize_team_name)
    return agencies.set_index("Agency no")["Team"].dropna().to_dict()


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


def build_team_workbook(df_team: pd.DataFrame, team_name: str) -> bytes:
    output = BytesIO()
    team_df = df_team.copy()

    if "Processing Date" in team_df.columns:
        team_df["Processing Date"] = pd.to_datetime(team_df["Processing Date"], errors="coerce")
    if "Post Delay Date" in team_df.columns:
        team_df["Post Delay Date"] = pd.to_datetime(team_df["Post Delay Date"], errors="coerce")

    today = pd.Timestamp.today().normalize()
    yesterday = today - pd.Timedelta(days=1)

    post_delay_df = team_df[
        team_df["Post Delay Date"].notna() & (team_df["Post Delay Date"] > yesterday)
    ].copy()
    today_cases_df = team_df[team_df["Processing Date"].dt.normalize() == today].copy()
    team_sheet_df = team_df.copy()

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
    last7 = str(i90_id)[-7:]
    return int(last7.lstrip("0") or "0")


def safe_path_segment(value: str) -> str:
    return value.strip().replace("/", "-").replace("\\", "-")
