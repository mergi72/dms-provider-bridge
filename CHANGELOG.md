# Changelog

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
