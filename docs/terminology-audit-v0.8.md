# Terminology Audit for 0.8.x

This document is the first 0.8.x refactor step.

Do not start by mechanically renaming every `provider` occurrence. The word
currently carries several different meanings. The goal is to separate meaning
first, then rename safely in small steps.

## Target Model

```text
TC VFS Contract
  shared internal Total Commander VFS/common operation contract

Driver
  concrete DMS/API implementation, for example alfresco, edocat, webdav

Connection
  named mount exposed to clients and Total Commander, for example alfresco:/,
  alfresco1:/, edocat:/, webdav:/

Auth
  credential/token/anonymous resolution layer used by connections and drivers

Operation
  list/stat/download/upload/copy/move/delete/mkdir execution
```

## Rules

- Use `TC VFS Contract` for the internal bridge filesystem contract.
- Do not rename the public `/bridge/wfx/*` API in 0.8.x unless there is a
  functional reason.
- Prefer `connection` for user-visible mounts.
- Prefer `driver` for implementation modules and DMS/API-specific behavior.
- Keep legacy `provider` request/response aliases during the transition.
- When both `provider` and `connection` are accepted, validate that they point
  to the same value.

## Current Meanings of `provider`

### TC VFS Contract

Meaning: internal common contract.

Examples:

- `config/providers/provider.json`
- Config UI section `/config/providers`
- `src/dms_provider_bridge/drivers/tc_vfs_contract.py`
- `class TcVfsContract(ABC)`
- README text `TC VFS Contract`
- runtime snapshot key `tc_vfs_contract`
- legacy runtime snapshot key `provider_abc`

Decision:

- Use the name `TC VFS Contract` in UI and docs.
- Use `dms_provider_bridge.drivers.tc_vfs_contract.TcVfsContract` as the primary Python contract.
- Keep `Provider ABC` and `provider_abc` only as compatibility aliases while 0.8.x is in transition.
- Keep `Provider = TcVfsContract` through the transition for old imports.
- Treat it as a read-only/internal contract in UI and docs.

### Driver

Meaning: implementation of one DMS/API type.

Examples:

- `src/dms_provider_bridge/providers/alfresco.py`
- `src/dms_provider_bridge/providers/edocat.py`
- `src/dms_provider_bridge/providers/webdav.py`
- `src/dms_provider_bridge/providers/base.py`
- `load_provider_config()` compatibility alias for `load_driver_config()`
- `list_provider_config_names()` compatibility alias for `list_driver_config_names()`

Decision:

- New code should use driver terminology.
- `providers/*.py` should move to `drivers/*.py` in a later 0.8.x step.
- Keep compatibility imports until the runtime and tests are fully moved.

### Connection

Meaning: named mount exposed to clients and Total Commander.

Examples:

- `config/connections/alfresco.json`
- `config/connections/alfresco1.json`
- `config/connections/edocat.json`
- `config/connections/webdav.json`
- `ParsedWfxPath.connection`
- `get_connection_runtime()`
- `_CONNECTION_RUNTIME_CACHE`

Decision:

- This is the preferred runtime meaning.
- Existing legacy aliases such as `provider`, `provider_name`, and
  `provider_path_override` should remain only as compatibility surfaces.

### Legacy/compat provider aliases

Meaning: old external or internal names that now point to connection or driver.

Examples:

- request field `provider` as alias for `connection`
- request field `provider_name` as alias for `connection_name`
- request field `provider_path_override` as alias for `connection_path_override`
- response metadata key `provider` kept next to preferred `connection`
- log fields that include both `connection=...` and `provider=...`
- exception type `ProviderNotFoundError`
- result models with field `provider`

Decision:

- Do not remove these in one pass.
- Keep them until WFX, tests and external clients are stable on connection-first
  naming.
- Mark them as compatibility when touching nearby code.

## 0.8.x Refactor Plan

### 0.8.0-beta: audit only

No runtime behavior changes.

Deliverables:

- This terminology audit.
- README link to the audit.
- Clear backlog ordering.

### 0.8.1-beta: service naming

Rename the runtime service by meaning:

```text
services/provider_service.py
  -> services/connection_runtime_service.py
```

Rules:

- Add a compatibility wrapper module at the old path.
- Keep old imports working while internal code moves to the new module.
- Keep `reload_provider_cache()` as an alias for `reload_connection_runtime_cache()`.

Implementation status:

- `services/connection_runtime_service.py` owns the runtime registry.
- `services/provider_service.py` remains as a compatibility wrapper.
- Internal bridge code imports `connection_runtime_service`.
- Config UI uses `reload_connection_runtime_cache()` while keeping
  `reload_provider_cache()` as a compatibility alias.
- `ConnectionNotFoundError` is the preferred runtime exception name.
  `ProviderNotFoundError` remains as a compatibility alias.
- `core/config_loader.py` uses keyed section, driver config path and driver
  config logging helpers internally. Provider-named helpers remain only as
  compatibility aliases.
- Auth code uses `AuthCredentials` as the primary credentials container.
  `ProviderCredentials` remains as a compatibility alias for older tests and
  imports.

### 0.8.2-beta: runtime API cleanup

Clean names inside runtime services and route glue.

Preferred names:

- `connection_name`
- `driver_name`
- `connection_runtime`
- `driver_factory`

Compatibility names:

- `provider_name`
- `provider`

Rules:

- Runtime internals should stop using `provider` when the value is a connection.
- Public payload aliases remain accepted.
- Tests should explicitly cover mismatch validation.

Implementation status:

- Runtime service tests use `connection_runtime_module` naming.
- Legacy provider service wrapper is covered by regression tests.
- Public `provider_name`, `provider`, and `provider_path_override` aliases are
  intentionally still accepted.
- Debug/log helpers now use `connection_debug_logger()` and
  `log_connection_operation_*()` as the primary API. Legacy
  `provider_debug_logger()` and `log_provider_operation_*()` remain as
  compatibility aliases and write connection operation events.
- `models.connection.ConnectionConfig` is the primary lightweight connection
  config model. `models.provider.ProviderConfig` remains as a compatibility
  alias.
- Legacy request alias resolution now lives in
  `core.connection_aliases`. `services.connection_aliases` remains as a
  compatibility wrapper. Listing can still accept a legacy
  `provider` value as a driver alias for a concrete connection, while edit and
  transfer use strict connection matching.
- Legacy `provider_path_override` handling for Share URL requests is resolved
  through the same core alias helper as `connection_path_override`.
- Share URL service internals and routes now pass `connection` as the primary
  name. Legacy `provider` request fields are mirrored into `connection` by the
  request model, and responses include both `connection` and legacy `provider`
  metadata during the transition.

### 0.8.3-beta: move implementation modules

Move concrete DMS implementations:

```text
src/dms_provider_bridge/providers/*.py
  -> src/dms_provider_bridge/drivers/*.py
```

Rules:

- Keep `providers` as a compatibility package temporarily.
- Remove the `drivers.__path__ = providers.__path__` hack only after direct
  driver imports are stable.
- Update package discovery to scan `dms_provider_bridge.drivers` directly.

Implementation status:

- Concrete implementations now live in `src/dms_provider_bridge/drivers`.
- `src/dms_provider_bridge/providers` contains compatibility wrappers for old
  imports.
- Runtime discovery scans `dms_provider_bridge.drivers` directly.
- Build hidden imports use driver module names.

### 0.8.4-beta: WFX/client naming cleanup

Clean remaining client-facing internal names:

```text
ProviderPath      -> ConnectionPath
ProviderName      -> ConnectionName
provider metadata -> connection metadata where appropriate
```

Rules:

- Keep HTTP `/bridge/wfx/*` endpoint paths unchanged.
- Do not force WFX to change its public behavior for a naming-only refactor.
- Bridge can return both `connection` and legacy `provider` metadata during the
  transition.

## Backlog Candidates After 0.8.x

- Remove legacy `Provider ABC` / `provider_abc` aliases only after the beta
  series, when UI/docs and user mental model are stable.
- Generate shared auth/request contracts for Bridge and WFX from one source.
- Decide when legacy edit/transfer service modules can be removed completely.
- Decide when response model field `provider` can become `connection` without
  breaking existing clients.

