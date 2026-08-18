import os
from dataclasses import dataclass
from urllib.parse import urlparse

from azure.storage.blob import BlobServiceClient, ContentSettings


@dataclass(frozen=True)
class BlobLocation:
    container: str
    blob_name: str

    @property
    def path(self) -> str:
        return f"{self.container}/{self.blob_name}"


@dataclass(frozen=True)
class CorrelatedBlobPath:
    container: str
    correlation_id: str
    process: str
    blob_name: str

    @property
    def path(self) -> str:
        return f"{self.container}/{self.blob_name}"


def parse_blob_path(blob_path: str) -> BlobLocation:
    if not blob_path or not blob_path.strip():
        raise ValueError("blob_path is required.")

    value = blob_path.strip()

    if value.startswith("https://"):
        parsed = urlparse(value)
        parts = parsed.path.strip("/").split("/")
        if len(parts) < 4:
            raise ValueError("Blob URL must include container, process folder, correlation folder, and blob name.")
        return BlobLocation(container=parts[0], blob_name="/".join(parts[1:]))

    parts = value.strip("/").split("/")
    if len(parts) < 4:
        raise ValueError("blob_path must be formatted as '<container>/<process-folder>/<correlation-id>/<blob-name>' or be a full blob URL.")

    return BlobLocation(container=parts[0], blob_name="/".join(parts[1:]))


def build_correlated_output_blob_name(
    input_location: BlobLocation,
    correlation_id: str,
    output_filename: str,
    output_container: str = "output",
) -> CorrelatedBlobPath:
    parts = input_location.blob_name.strip("/").split("/")
    process = parts[0] if parts and parts[0].strip() else ""
    if (
        len(parts) < 3
        or parts[1] != correlation_id
    ):
        raise ValueError(
            "Input blob path must be formatted as "
            f"'<input-container>/<process-folder>/{correlation_id}/<filename>'."
        )

    if not correlation_id.strip():
        raise ValueError("correlation_id is required.")

    safe_filename = output_filename.strip().replace("\\", "/").split("/")[-1]
    if not safe_filename:
        raise ValueError("Output filename is required.")

    return CorrelatedBlobPath(
        container=output_container,
        correlation_id=correlation_id,
        process=process,
        blob_name=f"{process}/{correlation_id}/{safe_filename}",
    )


def get_blob_service_client(
    connection_string: str | None = None,
    account_url: str | None = None,
) -> BlobServiceClient:
    if connection_string:
        return BlobServiceClient.from_connection_string(connection_string)

    if account_url:
        from azure.identity import DefaultAzureCredential

        return BlobServiceClient(account_url=account_url, credential=DefaultAzureCredential())

    connection_string = os.getenv("AzureWebJobsStorage")
    if connection_string:
        return BlobServiceClient.from_connection_string(connection_string)

    account_url = os.getenv("AZURE_STORAGE_ACCOUNT_URL")
    if not account_url:
        raise RuntimeError(
            "Set AzureWebJobsStorage or AZURE_STORAGE_ACCOUNT_URL for blob access."
        )

    from azure.identity import DefaultAzureCredential

    return BlobServiceClient(account_url=account_url, credential=DefaultAzureCredential())


def download_blob_bytes(
    blob_path: str,
    *,
    connection_string: str | None = None,
    account_url: str | None = None,
) -> tuple[BlobLocation, bytes]:
    location = parse_blob_path(blob_path)
    service = get_blob_service_client(connection_string=connection_string, account_url=account_url)
    blob_client = service.get_blob_client(location.container, location.blob_name)
    return location, blob_client.download_blob().readall()


def upload_blob_bytes(
    container: str,
    blob_name: str,
    content: bytes,
    content_type: str,
    *,
    connection_string: str | None = None,
    account_url: str | None = None,
) -> BlobLocation:
    if not container or not container.strip():
        raise ValueError("Output container name is required.")

    service = get_blob_service_client(connection_string=connection_string, account_url=account_url)
    blob_client = service.get_blob_client(container.strip(), blob_name)
    blob_client.upload_blob(
        content,
        overwrite=True,
        content_settings=ContentSettings(content_type=content_type),
    )
    return BlobLocation(container=container.strip(), blob_name=blob_name)
