# Changelog

## 0.4.15 - 2026-06-11

### Changed
- Release/version bump to `0.4.15`.
- Moved shared debug config helpers into `core.debug` so bridge logging and config loader use one `debug.enable` / `debug.path` contract.
- Added provider debug logger helpers and provider operation start/done/failed diagnostics for future provider implementations.
- Documented provider debug config template and provider-level debug logging expectations.

---

## 0.4.14 - 2026-06-11

### Changed
- Release/version bump to `0.4.14`.
- eDoCat list item mapping now reads file size from multiple upstream metadata shapes, including nested `content`, `props`, `properties`, and `metadata` fields.
- eDoCat query paging now uses 200-item pages and guards against repeated upstream pages.
- Bridge WFX `stat` responses can surface upstream HTTP status metadata while successful operations continue to return HTTP 200.
- Config debug settings are now expressed as `debug.enable` and `debug.path` in `bridge.json` and provider configs.
- Runtime `bridge.log` is written to `%APPDATA%\DMS Provider\logs` by default, next to user `config`.
- Provider-specific debug config logging writes separate `<provider>-debug.log` files and masks sensitive values.

---

## 0.4.13 - 2026-06-11

### Changed
- Release/version bump to `0.4.13`.
- Refactored Alfresco provider internals into focused helper modules for config limits, share URL parsing, item mapping, and versioning metadata.
- Kept the external bridge/provider contract unchanged while reducing `alfresco.py` size.
- Verified local FastAPI runtime for Alfresco list/stat/version-upload flow after the helper split.

---

## 0.4.12 - 2026-06-11

### Changed
- Release/version bump to `0.4.12`.
- Refactored eDoCat provider internals into focused helper modules for config, node metadata, item mapping, and tree/path operations.
- Kept the external bridge/provider contract unchanged while reducing `edocat.py` size and preserving Alfresco runtime behavior.
- Verified local FastAPI runtime for Alfresco list/stat/upload flow after the eDoCat helper split.

---

## 0.4.11 - 2026-06-11

### Changed
- Release/version bump to `0.4.11`.
- Refactored shared WFX path splitting into `adapters/commander_api.py`.
- Extracted bridge share URL orchestration into `services/bridge_share_url.py`.
- Extracted bridge exception-to-WFX mapping into `services/bridge_errors.py`.
- Made provider root listing tolerate missing or invalid default provider config while still returning registered providers.
- Added `reload_provider_cache()` for development/test cache refresh.
- Added compatibility handling for request auth `mode="windows"` with `target` mapped to `credential_id`.
- Split deterministic eDoCat path helpers into `providers/edocat_paths.py`.
- Verified local FastAPI runtime for Alfresco and eDoCat listing after refactor.

---

## 0.4.10 - 2026-06-11

### Changed
- Release/version bump to `0.4.10`.
- Removed the local filesystem `fso` provider from bridge runtime, config templates, installer payload, build scripts, smoke tests, and unit tests.
- Kept bridge provider paths focused on DMS providers only (`provider:/provider_path`); local filesystem handling belongs to TC-WFX and uploads enter bridge through upload endpoints.
- Simplified cross-provider `copy` behavior so bridge no longer performs hidden local-filesystem-to-provider transfers.
- Made provider-facing bridge/service/model paths more generic and moved provider-specific share URL/version capability details behind the provider interface.
- Verified local FastAPI runtime for Alfresco and eDoCat provider listing after the refactor.

---

## 0.4.9 - 2026-06-11

### Changed
- Release/version bump to `0.4.9`.
- Fixed Windows one-file build packaging so dynamically loaded bridge providers (`alfresco`, `edocat`, `fso`) are included in the executable.
- Restored stable Alfresco runtime listing against the configured `doc_library` after the eDoCat provider work.
- Kept provider local config templates out of committed config and generated empty `*.local.json` templates only in distribution payloads.

---

## 0.4.8 - 2026-06-10

### Changed
- Release/version bump to `0.4.8`.
- Alfresco `stat` and `list` now include version metadata (`version_label`, `version_type`, `is_versioned`) from `properties` and `aspectNames`.
- Alfresco node reads request `properties` and `aspectNames` where version-aware responses are needed.
- Alfresco create/update upload responses now include changed version/audit metadata when the created or updated node detail is available.
- Added tests for Alfresco version metadata in `stat`, `list`, created upload metadata, and children include parameters.

---

## 0.4.7 - 2026-06-10

### Changed
- Release/version bump to `0.4.7`.
- Added Alfresco existing-document upload semantics: existing documents now require an explicit version choice instead of filesystem-style overwrite.
- Added typed upload `versioning` payload with `mode: "version"`, Alfresco-compatible `majorVersion`, and optional `comment`.
- Alfresco version uploads now use `PUT /nodes/{nodeId}/content?majorVersion=true|false&comment=...`.
- Bridge provider detail exposes Alfresco versioning capabilities for TC-WFX discovery.
- Alfresco upload metadata now returns current version/audit data before version upload and changed version/audit data after upload.
- Added tests for Alfresco version-required responses, version upload mapping, OpenAPI versioning schema, and provider versioning capabilities.

---

## 0.4.6 - 2026-06-09

### Changed
- Release/version bump to `0.4.6`.
- Added streaming raw download support for Alfresco so `/bridge/wfx/download-raw` can return a real streamed response with `Content-Length` instead of buffering the whole file through base64 first.
- Added provider-level Alfresco content stream handling and bridge service fallback to the existing JSON/base64 download path for providers without streaming support.
- Updated credential validation so inline credentials supplied by TC-WFX/credential-broker take precedence over `credential_id` lookup.
- Added tests for raw streaming download and inline credential precedence.

---

## 0.4.5 - 2026-06-08

### Changed
- Release/version bump to `0.4.5`.
- Added `GET /bridge/wfx/providers/{provider}` provider detail endpoint for TC-WFX discovery.
- Provider detail exposes provider auth requirements from merged config and operation capabilities.

---

## 0.4.4 - 2026-06-07

### Changed
- Release/version bump to `0.4.4`.
- Runtime temporary files now default to `%TEMP%\DMS Provider` instead of the project/install directory, with `DMS_PROVIDER_TEMP_DIR` available as an override.
- Provider config diagnostic logging now masks sensitive keys such as password, secret, token, and API key values.
- Default provider environment override is now `DMS_PROVIDER_DEFAULT_PROVIDER`; the legacy `EDOCAT_PROVIDER` fallback has been removed.
- Default provider resolution no longer silently falls back to `edocat`; missing or invalid defaults now raise a configuration error.

---

## 0.4.3 - 2026-06-07

### Changed
- Release/version bump to `0.4.3`.
- Default FSO config no longer points to `C:/MyDocuments`; packaged `allowedRoots` is empty until a local override enables explicit roots.
- Service ZIP build now writes archive entry paths with `/` separators for better compatibility with GitHub release and CI tooling.

---

## 0.4.2 - 2026-06-07

### Changed
- Release/version bump to `0.4.2`.
- Provider discovery no longer uses a hard-coded provider registry; provider classes are discovered dynamically from `dms_provider_bridge.providers` and filtered by configured provider JSON files.
- `/bridge/wfx/providers` and root `/bridge/wfx/list` expose the dynamically configured provider list for TC-WFX provider selection.
- `/bridge/wfx/list` accepts root provider navigation without auth and keeps provider-path operations protected by auth.
- Provider config loading logs the final merged provider config, including machine and user config paths, to simplify local diagnostics.
- Provider config loading accepts wrapped provider sections and direct provider payloads while preserving the machine-first, user-local override rule.
- VS Code bridge start/restart/debug tasks now set `DMS_PROVIDER_MACHINE_CONFIG_DIR` to the repo `config` directory and `DMS_PROVIDER_USER_CONFIG_DIR` to `%APPDATA%\DMS Provider\config`.

---

## 0.4.1 - 2026-06-07

### Changed
- Release/version bump to `0.4.1`.
- Default provider tests are isolated from real machine/user config so installed `bridge.json` defaults do not make the test suite environment-dependent.
- README now clearly separates TC user mode from the current Service mode installer and documents that the `v0.4.1` setup installs `DMSProviderBridge` as `LocalSystem`.

---

## 0.4.0 - 2026-06-07

### Changed
- Release/version bump to `0.4.0`.
- Installer now creates the active-user config structure before elevation, then installs application files and machine config during the admin phase.
- Installer registers `DMSProviderBridge` as an automatic `LocalSystem` Windows service, replaces an existing service when present, starts it, and validates the real service state.
- Installer writes service control helpers and Start Menu shortcuts for start/stop/status with UAC elevation.
- Installer logs PowerShell warning stream output from service startup into the admin installer log.
- Bridge and Uvicorn runtime logs are routed to stdout so normal startup and health output are written to `bridge-stdout.log`.
- `/health` now logs a successful health check to stdout.

---

## 0.3.3 - 2026-06-07

### Changed
- Installer now passes `-InstallRoot "{app}"` explicitly to the PowerShell install script, keeping the script install root aligned with the Inno target directory.
- Install script resolves user AppData more robustly when Inno passes a short `{username}`, using Windows `ProfileList` and `C:\Users\<username>` fallbacks.
- Installer detail logging now reports ProgramData config, AppData config, service registration, service startup, health check, and provider check as separate `[STEP]` entries.

---

## 0.3.2 - 2026-06-07

### Changed
- Release/version bump to `0.3.2`.
- Installer now stages empty user `*.local.json` placeholders under the application `user-config` directory and lets the PowerShell install script create/seed the resolved user AppData config directory.
- Service ZIP now includes the same `user-config` placeholder payload as the Inno installer.
- Install script can resolve a sibling `user-config` payload automatically when `-UserConfigSourceDirPath` is not passed.
- Install script now checks NSSM exit codes and verifies that `DMSProviderBridge` exists immediately after service registration.

---

## 0.3.1 - 2026-06-07

### Changed
- Release/version bump to `0.3.1`.
- Installer now registers `DMSProviderBridge` as a Windows Service (`DisplayName`: `DMS Provider Bridge`) using `LocalSystem`, automatic startup, and starts it immediately after installation.
- Installer detail logging now reports installation steps with `[INFO]`, `[STEP]`, `[OK]`, `[WARN]`, and `[FAIL]` messages.
- Installer validates startup with `GET /health` and `GET /bridge/wfx/providers`.
- Installer writes service logs under the application `logs` directory and passes both machine and user config directories to the service environment.

---

## 0.3.0 - 2026-06-07

### Changed
- Release/version bump to `0.3.0`.
- Bridge config loading now uses `bridge.json` as the system config, with provider configs kept in same-named provider JSON files.
- Machine config is loaded from `C:\ProgramData\DMS Provider\config`; user `*.local.json` overrides are loaded from `%APPDATA%\DMS Provider\config` only when the matching machine JSON exists.
- User config files in `%APPDATA%\DMS Provider\config` must use local override names: `bridge.local.json` and `<provider>.local.json`.
- Installer and service launcher environment now use `DMS_PROVIDER_MACHINE_CONFIG_DIR` and `DMS_PROVIDER_USER_CONFIG_DIR`.
- Distribution builds now stage only explicit public config templates, preventing `*.local.json` files from entering release artifacts.
- Inno Setup payload now installs the public config templates under the application `config` directory before the install script copies them to the machine config directory.
- Inno Setup now explicitly creates both machine and user config directories, including `%APPDATA%\DMS Provider\config` for user `*.local.json` overrides.
- Inno Setup seeds empty provider user override files (`alfresco.local.json`, `edocat.local.json`, `fso.local.json`) with `{}` only when they do not already exist.
- Installer registers `DMSProviderBridge` as a Windows Service using `LocalSystem`, starts it, and verifies `/health` and `/bridge/wfx/providers`.

---

## 0.2.8-alpha - 2026-06-07

### Fixed
- Installation config copy now uses strict explicit allow-lists only (no wildcard `*.json`, no recursive config copy).
- Machine config deployment target is fixed to `C:\ProgramData\DMS Provider\config` with allowed files only: `default.json`, `alfresco.json`, `edocat.json`, `fso.json`.
- User config deployment target remains `%APPDATA%\DMS Provider\config`; `user.json` is seeded there only, and `*.local.json` is never copied from public payload.
- Installer self-heals invalid legacy state by removing machine-scoped `user.json` if found in `C:\ProgramData\DMS Provider\config`.

---

## 0.2.7-alpha - 2026-06-07

### Fixed
- Installer config seeding is now split by scope: machine templates remain in `C:\ProgramData\DMS Provider\config`, while `user.json` is seeded to the user config path (`%APPDATA%\DMS Provider\config`).
- `install-bridge-service.ps1` now resolves the User mode config root from the effective `RunAsUser` profile and seeds user config from a dedicated user template source.
- Service mode config copy now excludes both `*.local.json` and `user.json` from machine-wide config deployment.

---

## 0.2.6-alpha - 2026-06-07

### Fixed
- User mode config root is now resolved against the effective `RunAsUser` profile (`%APPDATA%\DMS Provider\config`) instead of relying on installer process context.
- Bridge setup no longer passes `-ConfigRoot` explicitly in `[Run]`, preventing per-user path mismatches during elevated install execution.

---

## 0.2.5-alpha - 2026-06-07

### Changed
- User mode config target was moved to `%APPDATA%\DMS Provider\config` for per-user bridge preferences and overrides.
- Installer config split was aligned to machine-wide templates in `C:\ProgramData\DMS Provider\config` and user-specific config in `%APPDATA%\DMS Provider\config`.
- Config copy behavior in install script now keeps `*.local.json` for **User mode**, while **Service mode** still excludes local config files.

---

## 0.2.4-alpha - 2026-06-06

### Added
- Bridge startup and standalone service installer now print Health, Swagger UI, and OpenAPI URLs explicitly for diagnostics.

### Changed
- Bridge standalone release assets were refreshed for `v0.2.4-alpha` (`dms-provider-bridge.exe`, service ZIP, setup EXE).
- Bridge setup runtime model now defaults to **User mode** (Scheduled Task at user logon) for Total Commander usage, while **Service mode** (NSSM) remains available as advanced/server mode.

---

## 0.2.3-alpha - 2026-06-06

### Added
- `scripts/install-bridge-service.ps1` — standalone Windows Service installer for bridge, no TC plugin dependency.
- `scripts/uninstall-bridge-service.ps1` — standalone Windows Service uninstall script for bridge.
- `scripts/build-bridge-service-package.ps1` — creates service package ZIP for ops/dev deployment.
- `scripts/build-bridge-installer.ps1` + `bridge-installer.iss` — bridge-only Inno Setup EXE installer build.
- `DMS_PROVIDER_CONFIG_DIR` environment variable support in `core/paths.py` for installed EXE deployments.

### Fixed
- `provider.default` from `default.json` is now correctly used as the default provider (previously only `EDOCAT_PROVIDER` env var was checked).

---

## 0.2.1 - 2026-06-03

### Changed
- Bridge WFX rename endpoint was replaced by move endpoint: use `POST /bridge/wfx/move`.
- Share URL browse operation name was aligned from `rename` to `move`.
- Share URL operation contract now uses `move` only; `rename` is no longer accepted.
- Cross-provider copy routing now supports `fso -> dms` via upload flow.
- Alfresco file uploads now use `multipart/form-data` payloads for content upload compatibility.

## 0.2.0 - 2026-06-02

### Added
- New raw download endpoint `POST /bridge/wfx/download-raw` for binary streaming.
- FSO provider path restriction via `allowedRoots` / `allowed_roots` configuration.
- VS Code task buttons for Start/Stop/Restart bridge workflow.

### Changed
- `POST /bridge/wfx/download` is now a consistent JSON contract endpoint.
- eDoCat query paging is aggregated across pages to avoid partial tree results.
- eDoCat query error handling now distinguishes access issues from upstream failures.
- Swagger tags and Share URL endpoint grouping were normalized for cleaner UI.
- Project/application version bumped to `0.2.0`.

### Fixed
- Startup task behavior when port `8765` is already in use.
- Content-Disposition for raw download now includes RFC 5987 `filename*` for Unicode filenames.
