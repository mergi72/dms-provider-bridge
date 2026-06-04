# dms-provider-bridge

[![CI](https://github.com/mergi72/dms-provider-bridge/actions/workflows/ci.yml/badge.svg)](https://github.com/mergi72/dms-provider-bridge/actions/workflows/ci.yml)

`dms-provider-bridge` is a base bridge service skeleton for integrating multiple DMS providers (eDoCat, Alfresco, FSO, ...).

## Quick Start

```bash
python -m venv .venv312
.venv312\\Scripts\\activate
pip install -e .
python -m uvicorn dms_provider_bridge.app.server:app --host 127.0.0.1 --port 8765
```

## VS Code (Windows)

The workspace is preconfigured to use the `.venv312` interpreter in `.vscode/settings.json`.

## Tests

Install test dependencies:

```bash
python -m pip install -e .[dev]
```

Quick run (PowerShell):

```powershell
.\scripts\run-tests.ps1 unit
.\scripts\run-tests.ps1 integration
.\scripts\run-tests.ps1 all
```

Quick run (Bash, for example Git Bash/WSL):

```bash
./scripts/run-tests.sh unit
./scripts/run-tests.sh integration
./scripts/run-tests.sh all
```

Note: both scripts look for the interpreter in this order: `.venv312`, `.venv`, and finally system `python`/`python3` from PATH.

## Clean Release ZIP (No Cache)

For release packaging, use Git archive so only tracked files are included:

```powershell
.\scripts\build-release-zip.ps1
```

This workflow automatically excludes local artifacts such as `__pycache__/`, `*.pyc`, `.venv/`, and runtime logs.

If you want to clean the local workspace before that, run:

```powershell
.\scripts\clean-artifacts.ps1
```

## Safe Testing (ENV)

For local smoke testing, avoid hardcoded passwords in shell history. Put them into environment variables and build payloads from them.

PowerShell:

```powershell
$env:BRIDGE_USER = "user@domain"
$env:BRIDGE_PASSWORD = "secret"

$body = @{
  path = "edocat:/deals"
  auth = @{
    mode = "credentials"
    username = $env:BRIDGE_USER
    password = $env:BRIDGE_PASSWORD
  }
} | ConvertTo-Json -Depth 10

Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8765/bridge/wfx/list -ContentType "application/json" -Body $body
```

Bash:

```bash
export BRIDGE_USER='user@domain'
export BRIDGE_PASSWORD='secret'

curl -sS http://127.0.0.1:8765/bridge/wfx/list \
  -H 'Content-Type: application/json' \
  -d "{\"path\":\"edocat:/deals\",\"auth\":{\"mode\":\"credentials\",\"username\":\"$BRIDGE_USER\",\"password\":\"$BRIDGE_PASSWORD\"}}"
```

## WFX Bridge API (for C# plugin)

Remote path format:

- `edocat:/folder/file.txt`
- `alfresco:/folder/file.txt`

Endpoints:

- `GET /bridge/wfx/providers` (provider discovery for root listing in the WFX plugin)

- `POST /bridge/wfx/list`
- `POST /bridge/wfx/stat`
- `POST /bridge/wfx/mkdir`
- `POST /bridge/wfx/delete`
- `POST /bridge/wfx/move`
- `POST /bridge/wfx/copy`
- `POST /bridge/wfx/download`
- `POST /bridge/wfx/download-raw`
- `POST /bridge/wfx/upload`
- `POST /bridge/wfx/upload-raw`
- `POST /bridge/wfx/upload-stream` (alias for `upload-raw`)
- `POST /bridge/wfx/resolve-share-url`
- `POST /bridge/wfx/browse-share-url`
- `POST /bridge/wfx/browse-share-url-validate`

Authentication (`auth`) is required for every call:

The bridge uses one incoming authentication model for all providers. Provider specific upstream HTTP authentication is resolved inside the provider implementation.

- `credentials`:
  `{ "auth": { "mode": "credentials", "credential_id": "edocat-prod" } }`
  or
  `{ "auth": { "mode": "credentials", "username": "user", "password": "secret" } }`

  `credential_id` is read from Windows Credential Manager. For regular credentials, use a generic credential with `UserName` and a secret in the credential blob; if the blob contains JSON, the bridge can also read `username`, `password`, `token`, and optional `base_url`.
- `winuser`:
  `{ "auth": { "mode": "winuser", "win_user": "DOMAIN\\user" } }`

Example request:

`{ "path": "edocat:/", "auth": { "mode": "winuser", "win_user": "DOMAIN\\user" } }`

Response uses a unified shape:

- `ok` (`true/false`)
- `error_code` (`0` = OK)
- `message` (error text)
- `data` (operation payload)
- `metadata.provider` (active provider)
- `metadata.upstream_auth_scheme` (for example `basic`, `ticket`)
- `metadata.upstream_endpoint` (actual upstream endpoint for the provider)

Execution mode notes:

- If the bridge obtains usable upstream credentials or ticket, operations run in `live` mode.
- If credentials or ticket are not available, the bridge returns a safe `preview` result (including exact endpoint) so the WFX layer can see what would be called.

Transfer operations:

- `download`: `{ "path": "alfresco:/contracts/sample.txt", "auth": { ... } }`
- `upload`: `{ "destination": "alfresco:/contracts", "file_name": "upload.txt", "content_base64": "...", "overwrite": true, "auth": { ... } }`
  - Intended only for small test payloads (`upload.inline.maxBytes`, default `4194304` = 4 MB).
  - For larger files use `upload-raw` / `upload-stream`.
- `upload-raw` / `upload-stream`: multipart form-data with fields `destination`, `file_name`, `overwrite`, `auth_json`, and binary field `file`

Raw upload limits:

- Config key: `upload.raw.maxBytes` in `config/default.json` (can be overridden in `config/user.json`)
- Default: `536870912` (512 MB)
- Stream chunk size key: `upload.raw.chunkBytes` (clamped to 1-4 MB, default `1048576` = 1 MB)
- Bridge rejects larger payloads before provider upload and logs `bytes`, `max_bytes`, and `duration_ms`

Alfresco upload transport:

- Raw upload writes incoming multipart file to a temporary file in chunks (1-4 MB policy).
- Bridge then forwards this file to Alfresco as `multipart/form-data` using streamed file chunks.
- Large uploads avoid `content_base64` in the transfer path.

eDoCat Share URL to bridge path conversion:

- `resolve-share-url`: `{ "share_url": "https://.../documentlibrary#/Team%20Documents/Upload?page=1", "provider": "alfresco" }`
- Response returns `data.path` in `alfresco:/...` format, usable for `list/stat/copy/...`.

One-shot browse via Share URL:

- `browse-share-url`: `{ "share_url": "https://.../documentlibrary#/Team%20Documents/Upload?page=1", "provider": "alfresco", "operation": "list|stat|download|copy|move|mkdir|delete|upload", "execute": true, "auth": { ... }, "provider_path_override": "/optional/manual/path", "destination_share_url": "https://...", "destination_path_override": "/target/path", "file_name": "upload.txt", "content_base64": "...", "overwrite": true }`
- `browse-share-url` is the canonical endpoint; for dry-run validation, use the same endpoint with `execute=false`.
- Response includes `data.resolved` (URL resolution result), `data.path_source` (`share_url` or `provider_path_override`), and `data.result` (selected operation result).
- For `copy|move`, `destination_path_override` or `destination_share_url` is additionally required; response contains `data.destination`.
- For `upload`, `file_name` is required; target can be provided via `destination_path_override` or `destination_share_url`, otherwise the path resolved from `share_url` is used.
- OpenAPI operationId: `bridgeResolveShareUrl`, `bridgeBrowseShareUrl` (canonical), deprecated alias: `bridgeBrowseShareUrlValidateDeprecated`.
- If `execute=false`, the endpoint performs no action and returns dry-run validation with the same logic as `browse-share-url-validate`.

Lightweight validation without operation execution:

- `browse-share-url-validate`: same inputs as `browse-share-url`, but without `auth` and without `content_base64`.
- Endpoint returns computed `source` and `destination` paths and payload validation errors without calling provider operations.
- Internally this is an alias to `browse-share-url` with `execute=false` (single shared implementation path).
- In OpenAPI this endpoint is marked as deprecated; preferred endpoint is `browse-share-url` with `execute=false`.

`download` payload notes:

- `/bridge/wfx/download` always returns JSON contract (`ok`, `error_code`, `data`).
- `/bridge/wfx/download-raw` returns raw file bytes (`Content-Disposition` + `Content-Type`).
- In `live` mode, JSON `download` includes `data.content_base64`, `data.mime_type`, and `data.size`.
- In `preview` mode, those fields are `null` and target endpoint is provided in `data.message`.

FSO security notes:

- FSO provider supports local path restrictions via `allowedRoots` in `config/fso.json`.
- Operations outside these roots are blocked (`ProviderOperationError`).
- For local environments, set your own absolute paths (Windows example):

```json
{
  "key": "fso",
  "fso": {
    "allowedRoots": [
      "C:/MyDocuments"
    ]
  }
}
```

Alfresco performance notes:

- The client contains in-memory cache for doc library resolution, child lookup, and path resolution.
- Repeated calls for the same Alfresco path are significantly faster than the first cold lookup.

## Runbook

Restart local server:

```powershell
$conn = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 8765 -ErrorAction SilentlyContinue | Where-Object { $_.State -eq 'Listen' }
if ($conn) { Stop-Process -Id $conn.OwningProcess -Force }
.\.venv312\Scripts\python.exe -m uvicorn dms_provider_bridge.app.server:app --app-dir src --host 127.0.0.1 --port 8765
```

Health check:

```powershell
Invoke-RestMethod -Method Get -Uri http://127.0.0.1:8765/health | ConvertTo-Json -Depth 10
```

Diagnostics when the same file keeps appearing (typically "welcome.pdf"):

- Verify you are calling `POST /bridge/wfx/list` (not legacy `GET /listing`).
- Verify provider format is `provider=edocat`, not `provider=edocat:`.
- Verify payload sends correct provider-prefixed `path` (`edocat:/...` or `alfresco:/...`) and `auth`.
- For Alfresco, first call may be slower; repeated call should be faster (warm cache).

## Structure

Project is split into:

- `app/` API layer
- `services/` business logic
- `providers/` provider implementations
- `clients/` API clients
- `models/` data models
- `core/` configuration, logging, and core utilities

## License

The project is licensed under the MIT License. Full text is available in `LICENSE`.

