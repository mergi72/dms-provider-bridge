# Changelog

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
