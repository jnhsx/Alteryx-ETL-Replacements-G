import os
import json
from datetime import datetime, timezone

import azure.functions as func
from azure.identity import ManagedIdentityCredential, DefaultAzureCredential, CredentialUnavailableError
from azure.storage.blob import BlobServiceClient

# Configure Application Insights monitoring
from azure.monitor.opentelemetry import configure_azure_monitor

connection_string = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
if connection_string:
    configure_azure_monitor(connection_string=connection_string)

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

@app.route(route="health", methods=["GET"])
def health(req: func.HttpRequest) -> func.HttpResponse:
    return func.HttpResponse("ok", status_code=200)

@app.route(route="diag", methods=["GET"])
def diag(req: func.HttpRequest) -> func.HttpResponse:
    """Diagnostic endpoint — no Azure SDK calls, confirms host loads."""
    keys = [
        "AzureWebJobsStorage__accountName",
        "AzureWebJobsStorage__credential",
        "AzureWebJobsStorage__blobServiceUri",
        "IDENTITY_ENDPOINT",
        "BIKMO_OUTPUT_CONTAINER",
        "WEBSITE_SITE_NAME",
        "FUNCTIONS_WORKER_RUNTIME",
        "FUNCTIONS_EXTENSION_VERSION",
    ]
    safe_redact = {"IDENTITY_HEADER", "SECRET", "KEY", "PASSWORD"}
    payload = {k: (os.getenv(k) or "") if not any(r in k for r in safe_redact) else "<redacted>" for k in keys}

    # Check whether SDK packages are importable
    for pkg, sym in [("azure.identity", "ManagedIdentityCredential"), ("azure.storage.blob", "BlobServiceClient")]:
        try:
            mod = __import__(pkg, fromlist=[sym])
            payload[f"import_{pkg.replace('.','_')}"] = "ok"
        except Exception as e:
            payload[f"import_{pkg.replace('.','_')}"] = f"FAILED: {e}"

    return func.HttpResponse(json.dumps(payload), status_code=200, mimetype="application/json")

@app.route(route="blob-smoke", methods=["GET", "POST"])
def blob_smoke(req: func.HttpRequest) -> func.HttpResponse:
    account_name = os.getenv("BIKMO_OUTPUT_CONTAINER")
    if not account_name:
        return func.HttpResponse(
            "Missing BIKMO_OUTPUT_CONTAINER app setting.",
            status_code=500
        )

    input_container = os.getenv("INPUT_CONTAINER", "input")
    output_container = os.getenv("OUTPUT_CONTAINER", "output")
    managed_identity_client_id = os.getenv("AZURE_CLIENT_ID") or os.getenv("MANAGED_IDENTITY_CLIENT_ID")
    identity_endpoint = os.getenv("IDENTITY_ENDPOINT")
    identity_header_present = bool(os.getenv("IDENTITY_HEADER"))

    account_url = f"https://{account_name}.blob.core.windows.net"

    try:
        # In App Service, prefer managed identity. If a user-assigned client ID is set but invalid,
        # fall back to system-assigned identity so blob-smoke still works.
        if identity_endpoint:
            if managed_identity_client_id:
                try:
                    credential = ManagedIdentityCredential(client_id=managed_identity_client_id)
                    _ = credential.get_token("https://storage.azure.com/.default")
                except CredentialUnavailableError:
                    credential = ManagedIdentityCredential()
            else:
                credential = ManagedIdentityCredential()
        else:
            credential = DefaultAzureCredential()

        blob_service = BlobServiceClient(account_url=account_url, credential=credential)

        blob_name = f"smoke-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.txt"
        payload = f"Blob smoke test at {datetime.now(timezone.utc).isoformat()}".encode("utf-8")

        src_blob = blob_service.get_blob_client(container=input_container, blob=blob_name)
        dst_blob = blob_service.get_blob_client(container=output_container, blob=blob_name)

        # 1) Create file in input container
        src_blob.upload_blob(payload, overwrite=True)

        # 2) Copy content to output container
        copied = src_blob.download_blob().readall()
        dst_blob.upload_blob(copied, overwrite=True)

    except Exception as exc:
        return func.HttpResponse(
            json.dumps({
                "ok": False,
                "error": type(exc).__name__,
                "detail": str(exc),
                "storage_account": account_name,
                "input_container": input_container,
                "output_container": output_container,
                "identity_endpoint_present": bool(identity_endpoint),
                "identity_header_present": identity_header_present,
                "managed_identity_client_id_present": bool(managed_identity_client_id),
            }),
            status_code=500,
            mimetype="application/json"
        )

    return func.HttpResponse(
        json.dumps({
            "ok": True,
            "storage_account": account_name,
            "input_container": input_container,
            "output_container": output_container,
            "blob_name": blob_name
        }),
        status_code=200,
        mimetype="application/json"
    )