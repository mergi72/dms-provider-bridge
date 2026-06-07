# Changelog

## 0.3.0 - 2026-06-07

### Changed
- Release/version bump to `0.3.0`.
- Bridge config loading now uses `bridge.json` as the system config, with provider configs kept in same-named provider JSON files.
- Machine config is loaded from `C:\ProgramData\DMS Provider\config`; user `*.local.json` overrides are loaded from `%APPDATA%\DMS Provider\config` only when the matching machine JSON exists.
- User config files in `%APPDATA%\DMS Provider\config` must use local override names: `bridge.local.json` and `<provider>.local.json`.
- Installer and service launcher environment now use `DMS_PROVIDER_MACHINE_CONFIG_DIR` and `DMS_PROVIDER_USER_CONFIG_DIR`.
- Distribution builds now stage only explicit public config templates, preventing `*.local.json` files from entering release artifacts.
- Inno Setup payload now installs the public config templates under the application `config` directory before the install script copies them to the machine config directory.

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
