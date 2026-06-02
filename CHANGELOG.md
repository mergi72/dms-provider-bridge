# Changelog

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
