## Reads JSON body and extracts required fields

import json
import logging
from datetime import datetime, timezone

import azure.functions as func

from pipelines.unposted_reports import UnpostedReportsConfig, run
from shared.blob_io import build_correlated_output_blob_name, download_blob_bytes, upload_blob_bytes
from shared.request_validation import get_required_request_fields
from shared.storage import get_storage_credentials


def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        payload = _read_payload(req)
        params = get_required_request_fields(
            payload,
            req,
            [
                "correlation_id",
                "blob_path_al",
                "blob_path_hh",
                "blob_path_pi",
                "storage_account",
            ],
        )
        correlation_id = params["correlation_id"]
        agency_list_blob_path = params["blob_path_al"]
        hh_blob_path = params["blob_path_hh"]
        pi_blob_path = params["blob_path_pi"]
        storage_connection_string, storage_account_url = get_storage_credentials(params["storage_account"])

        agency_location, agency_list_bytes = download_blob_bytes(
            agency_list_blob_path,
            connection_string=storage_connection_string,
            account_url=storage_account_url,
        )
        hh_location, hh_bytes = download_blob_bytes(
            hh_blob_path,
            connection_string=storage_connection_string,
            account_url=storage_account_url,
        )
        pi_location, pi_bytes = download_blob_bytes(
            pi_blob_path,
            connection_string=storage_connection_string,
            account_url=storage_account_url,
        )
        output_blob = build_correlated_output_blob_name(
            pi_location,
            correlation_id=correlation_id,
            output_filename="output.xlsx",
        )

        for location in [hh_location, agency_location]:
            comparison_blob = build_correlated_output_blob_name(
                location,
                correlation_id=correlation_id,
                output_filename="output.xlsx",
            )
            if (
                comparison_blob.correlation_id != output_blob.correlation_id
                or comparison_blob.process != output_blob.process
            ):
                raise ValueError("All Unposted Reports input blobs must use the same process folder and correlation id.")

        result = run(
            hh_bytes=hh_bytes,
            pi_bytes=pi_bytes,
            agency_list_bytes=agency_list_bytes,
            config=UnpostedReportsConfig(),
        )

        primary_output_blob = build_correlated_output_blob_name(
            pi_location,
            correlation_id=correlation_id,
            output_filename=result.output_filename,
        )
        primary_location = upload_blob_bytes(
            container=primary_output_blob.container,
            blob_name=primary_output_blob.blob_name,
            content=result.output_bytes,
            content_type=result.content_type,
            connection_string=storage_connection_string,
            account_url=storage_account_url,
        )

        uploaded_blob_paths = [primary_location.path]
        for artifact in result.artifacts:
            artifact_output_blob = build_correlated_output_blob_name(
                pi_location,
                correlation_id=correlation_id,
                output_filename=artifact.output_filename,
            )
            artifact_location = upload_blob_bytes(
                container=artifact_output_blob.container,
                blob_name=artifact_output_blob.blob_name,
                content=artifact.output_bytes,
                content_type=artifact.content_type,
                connection_string=storage_connection_string,
                account_url=storage_account_url,
            )
            uploaded_blob_paths.append(artifact_location.path)

        team_blob_paths = {
            "output_apc_blob_path": primary_location.path,
            "output_psc_blob_path": None,
            "output_schemes_blob_path": None,
        }
        for uploaded_path in uploaded_blob_paths:
            normalized = uploaded_path.lower()
            if "psc" in normalized:
                team_blob_paths["output_psc_blob_path"] = uploaded_path
            elif "schemes" in normalized:
                team_blob_paths["output_schemes_blob_path"] = uploaded_path

        response = {
            "status": "success",
            "timestamp": _utc_timestamp(),
            "input_blob_paths": {
                "agency_list": agency_location.path,
                "hh": hh_location.path,
                "pi": pi_location.path,
            },
            **team_blob_paths,
            "correlation_id": primary_output_blob.correlation_id,
            "row_count": result.row_count,
            "warnings": result.warnings,
        }
        return _json_response(response, status_code=200)

    except ValueError as exc:
        logging.exception("Unposted Reports request validation failed.")
        return _json_response({"status": "error", "message": str(exc)}, status_code=400)
    except Exception as exc:
        logging.exception("Unposted Reports function failed.")
        return _json_response({"status": "error", "message": str(exc)}, status_code=500)


def _read_payload(req: func.HttpRequest) -> dict:
    try:
        return req.get_json()
    except ValueError:
        return {}


def _get_required(payload: dict, req: func.HttpRequest, name: str) -> str:
    value = payload.get(name) or req.params.get(name)
    if value is None or str(value).strip() == "":
        raise ValueError(f"{name} is required.")
    return str(value).strip()


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_response(body: dict, status_code: int) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps(body),
        status_code=status_code,
        mimetype="application/json",
    )
