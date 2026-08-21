## Reads JSON body and extracts required fields

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import azure.functions as func

from pipelines.floodre import FloodReConfig, run
from shared.blob_io import build_correlated_output_blob_name, download_blob_bytes, upload_blob_bytes
from shared.request_validation import get_required_request_fields
from shared.storage import get_storage_credentials


def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        payload = _read_payload(req)
        params = get_required_request_fields(
            payload,
            req,
            ["blob_path", "correlation_id", "version", "input_type", "storage_account"],
        )
        blob_path = params["blob_path"]
        correlation_id = params["correlation_id"]
        version = params["version"]
        input_type = params["input_type"]
        storage_connection_string, storage_account_url = get_storage_credentials(params["storage_account"])

        input_location, input_bytes = download_blob_bytes(
            blob_path,
            connection_string=storage_connection_string,
            account_url=storage_account_url,
        )
        result = run(
            input_bytes=input_bytes,
            filename=Path(input_location.blob_name).name,
            config=FloodReConfig(version=version, input_type=input_type),
        )

        for warning in result.warnings:
            logging.warning("FloodRe validation warning: %s", warning)

        primary_output_blob = build_correlated_output_blob_name(
            input_location,
            correlation_id=correlation_id,
            output_filename="output.csv",
        )
        primary_location = upload_blob_bytes(
            container=primary_output_blob.container,
            blob_name=primary_output_blob.blob_name,
            content=result.output_bytes,
            content_type=result.content_type,
            connection_string=storage_connection_string,
            account_url=storage_account_url,
        )

        response = {
            "status": "success",
            "timestamp": _utc_timestamp(),
            "input_blob_path": input_location.path,
            "output_blob_path": primary_location.path,
            "correlation_id": primary_output_blob.correlation_id,
            "output_filename": "output.csv",
            "row_count": result.row_count,
            "warnings": result.warnings,
        }
        return _json_response(response, status_code=200)

    except ValueError as exc:
        logging.exception("FloodRe request validation failed.")
        return _json_response({"status": "error", "message": str(exc)}, status_code=400)
    except Exception as exc:
        logging.exception("FloodRe function failed.")
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
