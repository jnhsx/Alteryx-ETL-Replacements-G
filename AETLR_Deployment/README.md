## Alteryx ETL Replacements

Python replacements for Alteryx-style reporting workflows. The project is being migrated from the Alteryz platform, was tested in local desktop scripts, and is being migrated to Azure Functions so it can be run as a service.

## Requirements

- Python 3.10+
- pip
- Azure Functions Core Tools for local function testing
- Azure Storage access via either `AzureWebJobsStorage` or `AZURE_STORAGE_ACCOUNT_URL`

## Dependencies

```powershell
pip install -r requirements.txt
```

## Current Azure Function Pattern

The migrated workflows are Bikmo, BDX Tracker, Unposted Reports, and FloodRe.

The Azure Functions accept request parameters and read input files from Azure Blob Storage. Each process has its own required fields:

| Process | Required request fields |
|---|---|
| Bikmo | `correlation_id`, `blob_path`, `storage_account` |
| BDX Tracker | `correlation_id`, `blob_path`, `selected_month`, `storage_account` |
| FloodRe | `correlation_id`, `blob_path`, `version`, `storage_account` |
| Unposted Reports | `correlation_id`, `blob_path_pi`, `blob_path_hh`, `blob_path_al`, `storage_account` |

The function returns the output blob path.

Input blobs should be stored under a correlation-id folder:

```text
input/<process>/<correlation-id>/<filename>.<extension>
```

Outputs are written back under the same correlation id:

```text
output/<process>/<correlation-id>/output.xlsx
```

BDX Tracker also writes:

```text
output/bdx-tracker/<correlation-id>/not_received.html
```

FloodRe writes `output.csv`. Invalid FloodRe rows are not exported; the response warnings only include the invalid row count.

Example request body:

```json
{
  "correlation_id": "8f8f0a",
  "blob_path": "input/bikmo/8f8f0a/report.xlsx"
}
```

Example response:

```json
{
  "status": "success",
  "timestamp": "2026-05-19T10:15:30.000000+00:00",
  "input_blob_path": "input/bikmo/8f8f0a/report.xlsx",
  "output_blob_path": "output/bikmo/8f8f0a/output.xlsx",
  "correlation_id": "8f8f0a",
  "output_filename": "output.xlsx",
  "row_count": 123,
  "warnings": []
}
```

## Structure

```text
functions/
  bikmo_http/          HTTP handler used by function_app.py
  bdx_tracker_http/    HTTP handler used by function_app.py
  floodre_http/        HTTP handler used by function_app.py
  unposted_reports_http/ HTTP handler used by function_app.py
legacy/
  Bikmo/              Local-only wrappers and old process folders
  BDX Tracker/        Local-only wrappers and old process folders
  FloodRe/            Local-only wrappers and old process folders
  Unposted Reports/   Local-only wrappers and old process folders
pipelines/
  bikmo/              Pure Bikmo ETL logic
  bdx_tracker/        Pure BDX Tracker ETL logic
  floodre/            Pure FloodRe ETL logic
  unposted_reports/   Pure Unposted Reports ETL logic
shared/
  blob_io.py          Azure Blob download/upload helpers
  pipeline.py         Common pipeline result object
```

Function wrappers should stay thin: read request parameters, download the blob, call the pipeline, upload the result, and return the output blob path.

Pipelines should stay Azure-agnostic: accept bytes and config, validate/transform data, and return output bytes.

The `legacy/` folder is for local wrappers and old process assets only. It is excluded from Azure Function deployment by `.funcignore`.

## Run Bikmo Locally

The legacy local wrappers live under `legacy/` and delegate to the new pipeline code:

```powershell
python legacy\Bikmo\BKM.py legacy\Bikmo\Input\test.xlsx
```

Or process all `.xlsx` files in `legacy/Bikmo/Input`:

```powershell
python legacy\Bikmo\BKM.py
```

## Run BDX Tracker Locally

```powershell
python "legacy\BDX Tracker\BDX.py" "legacy\BDX Tracker\Input\Bdx tracker 2026.xlsm" --selected-month Jan-26
```

The local run writes both artifacts to `legacy/BDX Tracker/Output`:

- `BDX Management ...xlsx`
- `BDX Email ...html`

## Run FloodRe Locally

```powershell
python legacy\FloodRe\FLR.py "legacy\FloodRe\Input\202206 - FloodRe Policy.xlsx" --version 3
```

FloodRe returns the primary output CSV. If invalid rows are dropped, the response warning includes only the invalid row count.

## Run Azure Functions Locally

Copy `local.settings.sample.json` to `local.settings.json` and set storage values.

Start the function host:

```powershell
func start
```

Call the Bikmo endpoint:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:7071/api/bikmo" `
  -ContentType "application/json" `
  -Body '{"correlation_id":"8f8f0a","blob_path":"input/bikmo/8f8f0a/report.xlsx","storage_account":"nonsensitive"}'
```

Call the BDX Tracker endpoint:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:7071/api/bdx-tracker" `
  -ContentType "application/json" `
  -Body '{"correlation_id":"8f8f0a","blob_path":"input/bdx-tracker/8f8f0a/bdx_tracker.xlsm","selected_month":"Jan-26","storage_account":"nonsensitive"}'
```

BDX Tracker returns `output_blob_path` for the primary Excel workbook and `not_received_blob_path` for the email HTML.

## Run Unposted Reports Locally

Unposted Reports uses three Excel input files:

- `HH.xlsx`
- `PI.xlsx`
- `agencyList.xlsx`

For local testing, the wrapper defaults to the files in `legacy/Unposted Reports/Input`:

```powershell
python "legacy\Unposted Reports\UNP.py"
```

Or provide explicit file paths:

```powershell
python "legacy\Unposted Reports\UNP.py" `
  --hh-file "C:\Temp\HH.xlsx" `
  --pi-file "C:\Temp\PI.xlsx" `
  --agency-list-file "C:\Temp\agencyList.xlsx"
```

Call the Unposted Reports endpoint:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:7071/api/unposted-reports" `
  -ContentType "application/json" `
  -Body '{"correlation_id":"8f8f0a","blob_path_al":"input/unposted-reports/8f8f0a/blob_al.xlsx","blob_path_hh":"input/unposted-reports/8f8f0a/blob_hh.xlsx","blob_path_pi":"input/unposted-reports/8f8f0a/blob_pi.xlsx","storage_account":"nonsensitive"}'
```

Call the FloodRe endpoint:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:7071/api/floodre" `
  -ContentType "application/json" `
  -Body '{"correlation_id":"8f8f0a","blob_path":"input/floodre/8f8f0a/floodre.xlsx","version":"3","storage_account":"nonsensitive"}'
```
