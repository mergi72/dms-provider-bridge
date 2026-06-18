# dms-provider-bridge

[![CI](https://github.com/mergi72/dms-provider-bridge/actions/workflows/ci.yml/badge.svg)](https://github.com/mergi72/dms-provider-bridge/actions/workflows/ci.yml)
[![Status](https://img.shields.io/badge/Status-Beta-yellowgreen)](https://github.com/mergi72/dms-provider-bridge)
[![Bridge Version](https://img.shields.io/badge/Bridge-v0.7.9--beta-blue)](https://github.com/mergi72/dms-provider-bridge/releases/tag/v0.7.9-beta)
[![Bridge Setup](https://img.shields.io/badge/Setup-v0.5.0--beta-blueviolet)](https://github.com/mergi72/dms-provider-bridge/releases/tag/v0.5.0-beta)

Current development branch: `develop`  
Stable release branch: `main`

`dms-provider-bridge` is a base bridge service skeleton for integrating multiple DMS providers such as Alfresco and other document repositories.

Current release mapping:

- Bridge repository latest changelog version: `0.7.9-beta`
- Latest bridge-only release: `v0.7.9-beta`

## Configuration Model

Short version:

```text
Connection is the mount users open.
Driver is how the bridge talks to a DMS type.
Provider ABC is the shared contract underneath.
```

The bridge configuration follows a simple VFS-style model:

- `Provider ABC` is the common bridge contract. It can be changed and configured, but only when you know exactly what you are doing.
- `Driver` describes one DMS type, for example Alfresco, eDoCat, WebDAV or another backend.
- `Connection` is the named mount exposed to clients and Total Commander, for example `alfresco:/` or `company-dms:/`.

Bridge Configurator is available at [http://127.0.0.1:8765/config](http://127.0.0.1:8765/config).

The bridge now has two clearly separated responsibilities:

- Bridge runtime handles WFX/API operations such as list, upload, download, copy and move.
- Bridge Configurator handles configuration authoring, validation, runtime audit and connection tests.

The configurator currently runs inside the same local FastAPI process as the bridge, but it should be treated as an admin/configuration layer rather than as provider runtime logic.

Runtime naming:

- WFX endpoints expose `connections`; old runtime `providers` naming is not used in the 0.7 beta API.
- Runtime connection names are connection keys/mounts from connection config.
- Driver modules such as `alfresco.py` and `edocat.py` remain the concrete DMS implementations behind those connections.
- Runtime discovery treats those modules as driver factories.
- `dms_provider_bridge.drivers` is a compatibility package that currently exposes the existing `providers` modules without moving files.

Compatibility aliases:

- New request payloads should use `connection` or `connection_name` for the user-visible mount.
- Existing request payloads that still send `provider` or `provider_name` remain accepted as legacy aliases for `connection`.
- Responses and logs may include both `connection` and `provider` keys during the 0.7 beta series. `connection` is the preferred key; `provider` is kept for compatibility with existing tools and logs.
- When both names are supplied, they must point to the same value. A mismatch is treated as a validation/configuration error.

Current UI rules:

- `provider.json` is shown as the Provider ABC contract.
- `driver.json` and `connection.json` are templates and are shown as readonly.
- Concrete driver and connection files can be created and saved from the UI.
- Connection saves validate required driver and mount fields before writing JSON.
- The template files are never overwritten by `Save`.

Configuration checks:

- `Test` on a connection first performs a runtime-only check. It loads the connection, resolves its driver and shows the effective mount, base URL, auth mode and list endpoint. This check does not call the remote DMS.
- `Live List Root` is optional. It accepts the same auth JSON shape as Swagger requests, for example inline `username` and `password`, uses it for one request, and never writes it to config.
- `Audit` checks that every connection JSON is visible as a WFX connection and that runtime driver/mount values match the connection definition.
- Machine templates define the shape of config. User-specific or environment-specific values should be stored in local config files, not in the templates.

The 0.7 configuration/runtime model is intentionally split by responsibility:

```text
Provider ABC  read-only common VFS contract
Driver        concrete DMS/API implementation settings
Connection    named mount exposed to clients as connection:/path
```

## Runtime Modes

Bridge can be run in two different Windows runtime models. Keep them separate:

- TC user mode:
  - Intended for Total Commander / TC-WFX interactive usage.
  - Runs under the logged-in Windows user, for example from a user startup task.
  - Can access that user's Windows Credential Manager entries.
  - This is the right model for `credential_id` values created by the TC-WFX plugin.
- Service mode:
  - Intended for server-style local bridge usage.
  - Runs as the `DMSProviderBridge` Windows Service via NSSM.
  - Current `v0.5.0-beta` installer installs this service as `LocalSystem`.
  - `LocalSystem` cannot see credentials stored in an interactive user's Windows Credential Manager.

Current setup release `v0.5.0-beta` is the Service mode installer. TC user mode remains a separate runtime model for scenarios where user-scoped credentials are required.

## Connection Operations

The bridge supports file operations inside one connection and between different connections:

- Copy within the same connection uses the driver-native copy operation when available.
- Copy between connections, for example `edocat:/...` to `alfresco:/...`, is handled as download plus upload.
- Move between connections is handled as download, upload, then delete from the source connection.
- Large connection-to-connection transfers use a temporary file fallback when the payload exceeds the inline upload limit.

Connection-to-connection copy/move can use separate credentials for each side:

```json
{
  "source": "edocat:/source/file.txt",
  "destination": "alfresco:/target/file.txt",
  "auth": {
    "mode": "credentials",
    "credential_id": "fallback-credential"
  },
  "source_auth": {
    "mode": "credentials",
    "credential_id": "edocat-credential"
  },
  "destination_auth": {
    "mode": "credentials",
    "credential_id": "alfresco-credential"
  }
}
```

`source_auth` and `destination_auth` are optional. When omitted, the bridge falls back to `auth` for backward compatibility.

## Related Projects

- `tc-wfx-plugin`
- `dms-provider-installer`

## Quick Start

```bash
python -m venv .venv312
.venv312\\Scripts\\activate
pip install -e .
python -m uvicorn dms_provider_bridge.app.server:app --host 127.0.0.1 --port 8765
```

Verify bridge:

- Health: [http://127.0.0.1:8765/health](http://127.0.0.1:8765/health)
- Swagger UI: [http://127.0.0.1:8765/docs](http://127.0.0.1:8765/docs)
- Config UI: [http://127.0.0.1:8765/config](http://127.0.0.1:8765/config)
- OpenAPI: [http://127.0.0.1:8765/openapi.json](http://127.0.0.1:8765/openapi.json)

The Swagger UI is the fastest way to:

- test provider connectivity
- test credentials
- browse providers
- validate request payloads before integrating clients

Standalone executable quick run:

```powershell
.\dist\dms-provider-bridge.exe
```

## Testing the Bridge

Use these endpoints first when diagnosing install/config/auth problems:

- Swagger UI: [http://127.0.0.1:8765/docs](http://127.0.0.1:8765/docs)
- OpenAPI: [http://127.0.0.1:8765/openapi.json](http://127.0.0.1:8765/openapi.json)
- Health: [http://127.0.0.1:8765/health](http://127.0.0.1:8765/health)

Most recent bridge issues were diagnosable directly through Swagger UI without adding debug code, including credential resolution, LocalSystem visibility, root path handling, and provider config problems.

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

## Build bridge.exe (Windows)

For a release executable build (PyInstaller onefile), run:

```powershell
.\scripts\build-bridge.ps1
```

Output:

- `dist/dms-provider-bridge.exe`

Alternative build (onedir layout) is still available:

```powershell
.\scripts\build-bridge-exe.ps1
```

Quick health check:

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8765/health
```

## Safe Testing (ENV)

For local smoke testing, avoid hardcoded passwords in shell history. Put them into environment variables and build payloads from them.

PowerShell:

```powershell
$env:BRIDGE_USER = "user@domain"
$env:BRIDGE_PASSWORD = "secret"

$body = @{
  path = "alfresco:/"
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
  -d "{\"path\":\"alfresco:/\",\"auth\":{\"mode\":\"credentials\",\"username\":\"$BRIDGE_USER\",\"password\":\"$BRIDGE_PASSWORD\"}}"
```

## WFX Bridge API (for C# plugin)

## Config Layers

Configuration is loaded from two fixed Windows scopes:

- Machine config: `%ProgramData%\DMS Provider\config`
- User config: `%APPDATA%\DMS Provider\config`

The machine config is authoritative. For each config file, the bridge loads the machine JSON first, then merges the matching user `*.local.json` only if the machine JSON exists.

- Bridge/system config: `bridge.json`
- Driver config (`alfresco`, `sharepoint`, ...): `drivers/<driver>.json`
- Connection config (`company-dms`, `alfresco`, ...): `connections/<connection>.json`
- User overrides: `bridge.local.json`, `drivers/<driver>.local.json`, `connections/<connection>.local.json`

User `*.local.json` values override existing machine keys and may add missing keys. If the machine JSON file is missing, the matching user `*.local.json` is ignored.
The tracked template files under `config/providers`, `config/drivers` and `config/connections` define the machine-level contract and examples.

For local development, set `DMS_PROVIDER_MACHINE_CONFIG_DIR` and optionally `DMS_PROVIDER_USER_CONFIG_DIR` to test config directories.
The default connection comes from `connection.default` in `bridge.json`; `DMS_PROVIDER_DEFAULT_CONNECTION` can override it for local runs.
Runtime temporary files are written to `%TEMP%\DMS Provider` by default; set `DMS_PROVIDER_TEMP_DIR` only when a different temp root is required.

Debug logging is opt-in and uses the same `debug` object in `bridge.json` and provider config files:

```json
{
  "debug": {
    "enable": true,
    "path": "%APPDATA%\\DMS Provider\\logs"
  }
}
```

When enabled in `bridge.json`, the bridge writes debug output to `bridge-debug.log` and runtime output to `bridge.log`.
When enabled in a provider config, provider debug output goes to `<provider>-debug.log`, for example `alfresco-debug.log`.

Provider config template for new providers:

```json
{
  "key": "sharepoint",
  "sharepoint": {
    "debug": {
      "enable": true,
      "path": "%APPDATA%\\DMS Provider\\logs"
    }
  }
}
```

Driver/connection implementations should use `connection_debug_logger(connection_name, config)` and the `log_connection_operation_start/done/failed` helpers from `dms_provider_bridge.core.debug` for operation-level diagnostics. Legacy `provider_debug_logger()` and `log_provider_operation_*()` helpers remain available as aliases. Config dumps are sanitized before logging sensitive keys such as passwords, tokens, secrets, and API keys.

Remote path format:

- `<connection>:/folder/file.txt`
- `alfresco:/folder/file.txt`

Endpoints:

- `GET /bridge/wfx/connections` (connection discovery for root listing in the WFX plugin)
- `GET /bridge/wfx/connections/{connection_name}`
- `GET /bridge/wfx/connections/audit`

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

The bridge uses one incoming authentication model for all connections. Driver-specific upstream HTTP authentication is resolved inside the driver implementation.

- `credentials`:
  `{ "auth": { "mode": "credentials", "credential_id": "dms-prod" } }`
  or
  `{ "auth": { "mode": "credentials", "username": "user", "password": "secret" } }`

  `credential_id` is read from Windows Credential Manager. For regular credentials, use a generic credential with `UserName` and a secret in the credential blob; if the blob contains JSON, the bridge can also read `username`, `password`, `token`, and optional `base_url`.
- `winuser`:
  `{ "auth": { "mode": "winuser", "win_user": "DOMAIN\\user" } }`

Example request:

`{ "path": "alfresco:/", "auth": { "mode": "winuser", "win_user": "DOMAIN\\user" } }`

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

- Config key: `upload.raw.maxBytes` in machine `bridge.json` (can be overridden by user `bridge.local.json`)
- Default: `536870912` (512 MB)
- Stream chunk size key: `upload.raw.chunkBytes` (clamped to 1-4 MB, default `1048576` = 1 MB)
- Bridge rejects larger payloads before provider upload and logs `bytes`, `max_bytes`, and `duration_ms`

Alfresco upload transport:

- Raw upload writes incoming multipart file to a temporary file in chunks (1-4 MB policy).
- Bridge then forwards this file to Alfresco as `multipart/form-data` using streamed file chunks.
- Large uploads avoid `content_base64` in the transfer path.

Alfresco Share URL to bridge path conversion:

- `resolve-share-url`: `{ "share_url": "https://.../documentlibrary#/Team%20Documents/Upload?page=1", "provider": "alfresco" }`
- Response returns `data.path` in `alfresco:/...` format, usable for `list/stat/copy/...`.

One-shot browse via Share URL:

- `browse-share-url`: `{ "share_url": "https://.../documentlibrary#/Team%20Documents/Upload?page=1", "connection": "alfresco", "operation": "list|stat|download|copy|move|mkdir|delete|upload", "execute": true, "auth": { ... }, "connection_path_override": "/optional/manual/path", "destination_share_url": "https://...", "destination_path_override": "/target/path", "file_name": "upload.txt", "content_base64": "...", "overwrite": true }`
- `browse-share-url` is the canonical endpoint; for dry-run validation, use the same endpoint with `execute=false`.
- Response includes `data.resolved` (URL resolution result), `data.path_source` (`share_url` or `connection_path_override`), and `data.result` (selected operation result). Legacy `provider` and `provider_path_override` request fields are still accepted as aliases.
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
- Verify provider format is `provider=alfresco`, not `provider=alfresco:`.
- Verify payload sends correct provider-prefixed `path` (`alfresco:/...`) and `auth`.
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

