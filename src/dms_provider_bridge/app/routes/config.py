from __future__ import annotations

import html
import json
import os
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Form, HTTPException
from fastapi.responses import HTMLResponse

from dms_provider_bridge.core.config_loader import driver_connection_names, load_config
from dms_provider_bridge.core.paths import MACHINE_CONFIG_DIR, PROJECT_ROOT
from dms_provider_bridge.models.bridge import BridgeAuthContext
from dms_provider_bridge.services.bridge_service import list_path
from dms_provider_bridge.services.provider_service import (
    audit_connection_runtime,
    get_connection_runtime,
    reload_provider_cache,
    runtime_registry_snapshot,
)

router = APIRouter()


_SECTION_TITLES = {
    "providers": "Provider ABC",
    "auth": "Auth",
    "drivers": "Drivers",
    "connections": "Connections",
}

_SECTION_ROLES = {
    "providers": "VFS/common contract",
    "auth": "credential/token resolution contract",
    "drivers": "filesystem driver definitions",
    "connections": "mount definitions",
}

_SECTION_HELP = {
    "providers": (
        "Provider ABC is the internal bridge contract. It can be changed and configured, "
        "but only when you know exactly what you are doing."
    ),
    "auth": (
        "Auth is the internal credential and token resolution contract. It can be changed and configured, "
        "but only when you know exactly what you are doing."
    ),
    "drivers": (
        "Driver defines how the bridge talks to one DMS type, for example Alfresco, eDoCat or WebDAV. "
        "Most users do not need to create a new driver."
    ),
    "connections": (
        "Connection is the named mount exposed to clients and Total Commander, for example alfresco:/ or firma-dms:/."
    ),
}

_TEMPLATE_FILES = {
    "drivers": "driver.json",
    "connections": "connection.json",
}

_RESERVED_KEYS = {"driver_name", "connection_name", "provider_name"}
_SAFE_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")

_NEW_KEYS = {
    "drivers": "new_driver",
    "connections": "new_connection",
}


def _machine_config_dir() -> Path:
    return Path(os.environ.get("DMS_PROVIDER_MACHINE_CONFIG_DIR", str(MACHINE_CONFIG_DIR)))


def _bridge_config_path() -> Path:
    return _machine_config_dir() / "bridge.json"


def _registry_paths() -> dict[str, Path]:
    config = load_config()
    paths = config.get("paths") if isinstance(config, dict) else None
    if not isinstance(paths, dict):
        paths = {}
    machine_config_dir = _machine_config_dir()
    return {
        "providers": machine_config_dir / str(paths.get("providers") or "providers"),
        "auth": machine_config_dir / str(paths.get("auth") or "auth"),
        "drivers": machine_config_dir / str(paths.get("drivers") or "drivers"),
        "connections": machine_config_dir / str(paths.get("connections") or "connections"),
    }


def _section_dir(section: str) -> Path:
    paths = _registry_paths()
    try:
        return paths[section]
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown config section: {section}") from exc


def _json_files(section: str) -> list[Path]:
    directory = _section_dir(section)
    files = []
    if directory.exists():
        files = [path for path in directory.glob("*.json") if path.is_file()]
    template_file = _TEMPLATE_FILES.get(section)
    if template_file and not any(path.name == template_file for path in files):
        fallback = _fallback_template_path(section, template_file)
        if fallback.exists() and fallback.is_file():
            files.append(fallback)
    return sorted(files, key=lambda path: path.name)


def _read_json_file(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            payload = json.load(handle)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"Invalid JSON in {path.name}: {exc}") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=500, detail=f"Config file must contain a JSON object: {path.name}")
    return payload


def _file_read_only(section: str, file_name: str) -> bool:
    return section in {"providers", "auth"} or _TEMPLATE_FILES.get(section) == file_name


def _section_can_create(section: str) -> bool:
    return section in _TEMPLATE_FILES


def _file_can_delete(section: str, file_name: str) -> bool:
    return _section_can_create(section) and not _file_read_only(section, file_name)


def _payload_key(payload: dict[str, Any], fallback: str) -> str:
    key = payload.get("key")
    return key.strip() if isinstance(key, str) and key.strip() else fallback


def _payload_display_name(payload: dict[str, Any], key: str) -> str:
    section = payload.get(key)
    if isinstance(section, dict):
        display_name = section.get("display_name")
        if isinstance(display_name, str) and display_name.strip():
            return display_name.strip()
    project_info = payload.get("projectInfo")
    if isinstance(project_info, dict):
        name = project_info.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return ""


def _payload_section(payload: dict[str, Any], key: str) -> dict[str, Any]:
    section = payload.get(key)
    return section if isinstance(section, dict) else {}


def _extra_table_headers(section: str) -> list[str]:
    if section == "connections":
        return ["Driver", "Mount"]
    if section == "drivers":
        return ["Connections"]
    return []


def _extra_table_cells(section: str, payload: dict[str, Any], key: str) -> list[str]:
    payload_section = _payload_section(payload, key)
    if section == "connections":
        return [
            _string_cell(payload_section.get("driver")),
            _string_cell(payload_section.get("mount")),
        ]
    if section == "drivers":
        names = driver_connection_names(key)
        return [html.escape(", ".join(names) if names else "")]
    return []


def _string_cell(value: Any) -> str:
    return html.escape(value.strip()) if isinstance(value, str) and value.strip() else ""


def _file_mode(section: str, file_name: str) -> str:
    if section == "providers":
        return "read-only contract"
    if section == "auth":
        return "read-only contract"
    if _TEMPLATE_FILES.get(section) == file_name:
        return "template read only"
    return "editable"


def _mode_badge_class(mode: str) -> str:
    if mode.startswith("read-only"):
        return "badge-read-only"
    if mode.startswith("template"):
        return "badge-template"
    return "badge-editable"


def _reload_runtime_snapshot() -> dict[str, Any]:
    reload_provider_cache()
    audit = audit_connection_runtime()
    registry = audit.get("runtime_registry") if isinstance(audit, dict) else None
    if not isinstance(registry, dict):
        registry = runtime_registry_snapshot()
    return {
        "ok": bool(audit.get("ok")) if isinstance(audit, dict) else False,
        "message": "Configuration cache was reloaded.",
        "audit": audit,
        "registry": registry,
    }


def _runtime_summary_html(snapshot: dict[str, Any]) -> str:
    audit = snapshot.get("audit") if isinstance(snapshot, dict) else {}
    registry = snapshot.get("registry") if isinstance(snapshot, dict) else {}
    if not isinstance(audit, dict):
        audit = {}
    if not isinstance(registry, dict):
        registry = {}
    wfx_connections = registry.get("wfx_connections")
    if not isinstance(wfx_connections, list):
        wfx_connections = audit.get("registered_connections") if isinstance(audit.get("registered_connections"), list) else []
    available_drivers = registry.get("available_drivers")
    if not isinstance(available_drivers, list):
        available_drivers = audit.get("available_drivers") if isinstance(audit.get("available_drivers"), list) else []
    status_text = "Runtime audit passed." if snapshot.get("ok") else "Runtime audit found issues."
    status_class = "notice" if snapshot.get("ok") else "read-only-warning"
    return (
        f'<p class="{status_class}">{html.escape(status_text)}</p>'
        f'<p class="muted">WFX connections: {html.escape(", ".join(str(name) for name in wfx_connections))}</p>'
        f'<p class="muted">Available drivers: {html.escape(", ".join(str(name) for name in available_drivers))}</p>'
    )


def _file_links(section: str, active_file: str) -> str:
    links = []
    if _section_can_create(section):
        links.append(f'<a class="new" href="/config/{html.escape(section)}/new">New {_SECTION_TITLES[section][:-1]}</a>')
    for path in _json_files(section):
        class_name = "active" if path.name == active_file else ""
        mode = _file_mode(section, path.name)
        label = path.name
        if mode.startswith("template"):
            label = f"{path.name} - TEMPLATE READ ONLY"
        links.append(
            f'<a class="{class_name}" href="/config/{html.escape(section)}/{html.escape(path.name)}">'
            f"{html.escape(label)}</a>"
        )
    return "\n".join(links) or '<span class="muted">No JSON files found.</span>'


def _template_path(section: str) -> Path:
    template_file = _TEMPLATE_FILES.get(section)
    if not template_file:
        raise HTTPException(status_code=400, detail=f"Section cannot create files: {section}")
    path = _section_dir(section) / template_file
    if not path.exists() or not path.is_file():
        path = _fallback_template_path(section, template_file)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail=f"Template file not found: {template_file}")
    return path


def _fallback_template_path(section: str, template_file: str) -> Path:
    return PROJECT_ROOT / "config" / section / template_file


def _config_file_path(section: str, file_name: str) -> Path:
    path = _section_dir(section) / file_name
    if path.exists() and path.is_file():
        return path
    if _TEMPLATE_FILES.get(section) == file_name:
        fallback = _fallback_template_path(section, file_name)
        if fallback.exists() and fallback.is_file():
            return fallback
    return path


def _validate_config_file_name(file_name: str) -> None:
    if "/" in file_name or "\\" in file_name or not file_name.endswith(".json"):
        raise HTTPException(status_code=400, detail="Invalid config file name.")


def _safe_file_name_from_key(key: str) -> str:
    normalized = key.strip()
    if not normalized:
        raise HTTPException(status_code=400, detail="Config key is required.")
    if normalized in _RESERVED_KEYS:
        raise HTTPException(status_code=400, detail=f"Config key must be changed from template value: {normalized}")
    if not _SAFE_NAME.match(normalized):
        raise HTTPException(status_code=400, detail="Config key may contain only letters, numbers, dot, underscore and dash.")
    return f"{normalized}.json"


def _driver_keys() -> set[str]:
    keys = set()
    for path in _json_files("drivers"):
        if _file_read_only("drivers", path.name):
            continue
        payload = _read_json_file(path)
        keys.add(_payload_key(payload, path.stem))
    return keys


def _connection_mounts(exclude_file_name: str = "") -> dict[str, str]:
    mounts = {}
    for path in _json_files("connections"):
        if path.name == exclude_file_name or _file_read_only("connections", path.name):
            continue
        payload = _read_json_file(path)
        key = _payload_key(payload, path.stem)
        section = _payload_section(payload, key)
        mount = section.get("mount")
        if isinstance(mount, str) and mount.strip():
            mounts[mount.strip()] = path.name
    return mounts


def _validate_config_payload(
    section: str,
    payload: dict[str, Any],
    target_file_name: str,
    original_file_name: str = "",
) -> list[str]:
    errors = []
    key = payload.get("key")
    if not isinstance(key, str) or not key.strip():
        errors.append("Root key 'key' is required.")
        return errors
    key = key.strip()
    if key in _RESERVED_KEYS:
        errors.append(f"Root key must be changed from template value: {key}.")
    if not _SAFE_NAME.match(key):
        errors.append("Root key may contain only letters, numbers, dot, underscore and dash.")

    section_payload = payload.get(key)
    if not isinstance(section_payload, dict):
        errors.append(f"Root object '{key}' is required and must be a JSON object.")
        return errors

    if section == "drivers":
        provider_abc = section_payload.get("provider_abc")
        if provider_abc is not None and not isinstance(provider_abc, str):
            errors.append("Driver field 'provider_abc' must be a string when present.")
        for object_key in ("api", "endpoints", "capabilities", "limits"):
            value = section_payload.get(object_key)
            if value is not None and not isinstance(value, dict):
                errors.append(f"Driver field '{object_key}' must be a JSON object when present.")

    if section == "connections":
        driver = section_payload.get("driver")
        if not isinstance(driver, str) or not driver.strip():
            errors.append("Connection field 'driver' is required.")
        elif driver.strip() not in _driver_keys():
            errors.append(f"Connection driver '{driver.strip()}' does not exist.")

        mount = section_payload.get("mount")
        if not isinstance(mount, str) or not mount.strip():
            errors.append("Connection field 'mount' is required.")
        else:
            mount = mount.strip()
            if not _SAFE_NAME.match(mount.removesuffix(":/")) or not mount.endswith(":/"):
                errors.append("Connection field 'mount' must use format name:/ with a safe name.")
            existing_mounts = _connection_mounts(exclude_file_name=original_file_name or target_file_name)
            existing_file = existing_mounts.get(mount)
            if existing_file:
                errors.append(f"Connection mount '{mount}' is already used by {existing_file}.")

        auth = section_payload.get("auth")
        credentials = section_payload.get("credentials")
        if auth is not None and not isinstance(auth, dict):
            errors.append("Connection field 'auth' must be a JSON object when present.")
        if credentials is not None and not isinstance(credentials, dict):
            errors.append("Connection field 'credentials' must be a JSON object when present.")

    return errors


def _parse_json_payload(raw_json: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Config JSON must contain an object.")
    return payload


def _new_payload_from_template(section: str, payload: dict[str, Any]) -> dict[str, Any]:
    old_key = payload.get("key")
    new_key = _NEW_KEYS.get(section, "new_config")
    if not isinstance(old_key, str) or not old_key:
        updated = dict(payload)
        updated["key"] = new_key
        return updated
    updated = dict(payload)
    updated["key"] = new_key
    section_payload = updated.pop(old_key, {})
    updated[new_key] = section_payload
    if isinstance(section_payload, dict):
        mount = section_payload.get("mount")
        if isinstance(mount, str) and mount == "connection:/":
            section_payload["mount"] = f"{new_key}:/"
    return updated


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, ensure_ascii=False, indent=4) + "\n"
    tmp_path = path.with_name(f"{path.name}.tmp")
    tmp_path.write_text(serialized, encoding="utf-8")
    tmp_path.replace(path)


def _render_nav(active: str | None = None) -> str:
    links = ['<a class="button button-muted home" href="/config">Config</a>']
    bridge_class = "active" if active == "bridge" else ""
    links.append(f'<a class="button button-muted {bridge_class}" href="/config/bridge">Bridge</a>')
    for section, title in _SECTION_TITLES.items():
        class_name = "active" if section == active else ""
        links.append(f'<a class="button button-muted {class_name}" href="/config/{section}">{html.escape(title)}</a>')
    utility = (
        '<span class="utility">'
        '<a class="button button-muted" href="/config/reload">Reload</a>'
        '<a class="button button-muted" href="/config/audit">Audit</a>'
        '<a class="button button-muted" href="/docs">Docs</a><a class="button button-muted" href="/health">Health</a>'
        "</span>"
    )
    return "\n".join(links) + utility


def _render_layout(title: str, body: str, active: str | None = None) -> HTMLResponse:
    return HTMLResponse(
        f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    body {{ margin: 0; font-family: Segoe UI, Arial, sans-serif; background: #f6f8fb; color: #1f2933; }}
    header {{ background: #1f2933; color: white; padding: 14px 20px; box-shadow: 0 1px 2px rgba(15, 23, 42, 0.25); }}
    main {{ max-width: 1240px; margin: 0 auto; padding: 18px 20px; }}
    nav {{ display: flex; gap: 8px; margin-bottom: 14px; flex-wrap: wrap; align-items: center; }}
    nav a.home {{ font-weight: 600; }}
    nav .utility {{ margin-left: auto; display: flex; gap: 6px; }}
    nav .utility a {{ font-size: 13px; padding: 6px 10px; }}
    .file-list {{ display: flex; flex-direction: column; gap: 6px; }}
    .file-list a {{ color: #1f2933; text-decoration: none; padding: 8px 10px; border: 1px solid #d7dde5; background: #fff; border-radius: 4px; }}
    .file-list a.active {{ background: #e7f0ff; border-color: #6b9de8; box-shadow: inset 3px 0 0 #2d6cdf; }}
    .file-list a.new {{ background: #eefaf1; border-color: #9ad1aa; color: #137333; font-weight: 600; }}
    table {{ width: 100%; border-collapse: collapse; background: white; }}
    th, td {{ border-bottom: 1px solid #d7dde5; padding: 8px 10px; text-align: left; vertical-align: top; }}
    th {{ background: #eef2f7; }}
    td.path-cell {{ max-width: 280px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #64748b; }}
    pre {{ margin: 0; padding: 12px; background: #111827; color: #e5e7eb; overflow: auto; }}
    textarea {{ width: 100%; min-height: 560px; box-sizing: border-box; font: 13px Consolas, monospace; border: 1px solid #9aa6b2; padding: 10px; background: #fcfcfd; }}
    textarea[readonly] {{ background: #f3f4f6; border-color: #c7ced8; color: #4b5563; }}
    form {{ margin: 0; }}
    button {{ font: inherit; }}
    button:disabled {{ cursor: default; border-color: #c7ced8; background: #eef2f7; color: #64748b; }}
    .button, button {{ display: inline-flex; align-items: center; justify-content: center; gap: 6px; min-height: 34px; box-sizing: border-box; cursor: pointer; border-radius: 4px; padding: 7px 13px; font-weight: 600; text-decoration: none; }}
    .button-primary, button {{ border: 1px solid #2d6cdf; background: #2d6cdf; color: white; }}
    .button-secondary {{ border: 1px solid #8db5f4; background: #e7f0ff; color: #1a5fb4; }}
    .button-success {{ border: 1px solid #9ad1aa; background: #eefaf1; color: #137333; }}
    .button-danger {{ border: 1px solid #e27b7b; background: #fff0f0; color: #b42318; }}
    .button-muted {{ border: 1px solid #c7ced8; background: white; color: #1f2933; }}
    .button.active, .button:hover {{ border-color: #6b9de8; background: #e7f0ff; color: #1a5fb4; }}
    .link-button {{ color: #1a5fb4; text-decoration: none; padding: 6px 10px; border: 1px solid #8db5f4; background: #e7f0ff; border-radius: 4px; font-size: 13px; font-weight: 600; }}
    .link-button.button-danger {{ border-color: #e27b7b; background: #fff0f0; color: #b42318; }}
    .table-action {{ display: inline-flex; min-height: 28px; align-items: center; padding: 4px 9px; }}
    .actions {{ display: flex; gap: 8px; align-items: center; margin-top: 10px; flex-wrap: wrap; }}
    .muted {{ color: #64748b; }}
    .notice {{ margin: 0 0 10px; padding: 8px 10px; border-radius: 4px; border: 1px solid #9ad1aa; background: #e6f4ea; color: #137333; }}
    .read-only-warning {{ margin: 0 0 10px; padding: 8px 10px; border-radius: 4px; border: 1px solid #f0c36d; background: #fff4e5; color: #9a5b00; font-weight: 600; }}
    .contract-warning {{ margin: 0 0 12px; padding: 10px 12px; border-radius: 4px; border: 1px solid #e27b7b; background: #fff0f0; color: #b42318; font-weight: 700; }}
    .help {{ margin: 0 0 12px; padding: 10px 12px; border-left: 4px solid #6b9de8; background: #eef5ff; color: #243b53; }}
    .meta {{ display: flex; gap: 10px; flex-wrap: wrap; margin: 0 0 10px; }}
    .meta span {{ background: #eef2f7; border: 1px solid #d7dde5; padding: 4px 7px; border-radius: 3px; }}
    .badge {{ display: inline-block; min-width: 82px; text-align: center; padding: 3px 7px; border-radius: 3px; font-size: 12px; font-weight: 600; }}
    .badge-read-only {{ background: #e6f4ea; color: #137333; border: 1px solid #9ad1aa; }}
    .badge-template {{ background: #fff4e5; color: #9a5b00; border: 1px solid #f0c36d; }}
    .badge-preview {{ background: #e7f0ff; color: #1a5fb4; border: 1px solid #9fc3ff; }}
    .badge-editable {{ background: #e7f0ff; color: #1a5fb4; border: 1px solid #9fc3ff; }}
    .grid {{ display: grid; grid-template-columns: 280px 1fr; gap: 16px; align-items: start; }}
    .panel {{ background: white; border: 1px solid #d7dde5; border-radius: 5px; overflow: hidden; box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04); }}
    .panel h2 {{ font-size: 16px; margin: 0; padding: 10px 12px; border-bottom: 1px solid #d7dde5; background: #eef2f7; }}
    .panel-content {{ padding: 14px; }}
    .editor-header {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; margin-bottom: 12px; }}
    .editor-title {{ margin: 0; font-size: 16px; }}
    .editor-subtitle {{ margin: 4px 0 0; }}
    .file-path {{ overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .section-grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }}
    .section-card {{ display: block; color: inherit; text-decoration: none; background: white; border: 1px solid #d7dde5; border-radius: 5px; overflow: hidden; box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04); }}
    .section-card h2 {{ font-size: 16px; margin: 0; padding: 10px 12px; border-bottom: 1px solid #d7dde5; background: #eef2f7; }}
    .section-card div {{ padding: 12px; }}
    .section-card:hover {{ border-color: #6b9de8; }}
    @media (max-width: 900px) {{
      main {{ padding: 12px; }}
      nav .utility {{ margin-left: 0; }}
      .grid, .section-grid {{ grid-template-columns: 1fr; }}
      .editor-header {{ display: block; }}
      td.path-cell, .file-path {{ white-space: normal; }}
    }}
  </style>
</head>
<body>
  <header><strong>DMS Provider Bridge Config</strong></header>
  <main>
    <nav>{_render_nav(active)}</nav>
    {body}
  </main>
</body>
</html>"""
    )


@router.get("", response_class=HTMLResponse)
def config_home() -> HTMLResponse:
    body = """
<div class="section-grid">
  <a class="section-card" href="/config/bridge">
    <h2>Bridge</h2>
    <div>
      <p><span class="badge badge-read-only">READ ONLY</span></p>
      <p class="contract-warning">Bridge config controls the local bridge service. It can be changed and configured, but only when you know exactly what you are doing.</p>
      <p>Local service configuration for server, runtime paths and bridge behavior.</p>
    </div>
  </a>
  <a class="section-card" href="/config/providers">
    <h2>Provider ABC</h2>
    <div>
      <p><span class="badge badge-read-only">READ ONLY</span></p>
      <p class="contract-warning">Provider ABC is the internal bridge contract. It can be changed and configured, but only when you know exactly what you are doing.</p>
      <p>VFS/common contract used internally by the bridge.</p>
    </div>
  </a>
  <a class="section-card" href="/config/auth">
    <h2>Auth</h2>
    <div>
      <p><span class="badge badge-read-only">READ ONLY</span></p>
      <p class="contract-warning">Auth is the internal credential and token resolution contract. It can be changed and configured, but only when you know exactly what you are doing.</p>
      <p>Credential, token and upstream auth resolution contract.</p>
    </div>
  </a>
  <a class="section-card" href="/config/drivers">
    <h2>Drivers</h2>
    <div>
      <p><span class="badge badge-preview">EDITABLE</span> <span class="badge badge-template">TEMPLATE READ ONLY</span></p>
      <p class="help">Driver defines how the bridge talks to a DMS type. Most users do not need a new driver.</p>
      <p>Filesystem driver definitions for concrete DMS implementations.</p>
    </div>
  </a>
  <a class="section-card" href="/config/connections">
    <h2>Connections</h2>
    <div>
      <p><span class="badge badge-preview">EDITABLE</span> <span class="badge badge-template">TEMPLATE READ ONLY</span></p>
      <p class="help">Connection is what Total Commander opens, for example alfresco:/Projects.</p>
      <p>Mount definitions exposed to clients as connection:/path.</p>
    </div>
  </a>
</div>
"""
    return _render_layout("DMS Provider Bridge Config", body)


@router.get("/bridge", response_class=HTMLResponse)
def config_bridge() -> HTMLResponse:
    path = _bridge_config_path()
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Bridge config file not found: bridge.json")
    body = f"""
<section class="panel">
  <h2>Bridge</h2>
  <div class="panel-content">
    <p>local bridge service configuration</p>
    <p class="contract-warning">Bridge config controls the local bridge service. It can be changed and configured, but only when you know exactly what you are doing.</p>
    <p class="muted file-path" title="{html.escape(str(path.parent))}">Directory: {html.escape(str(path.parent))}</p>
    <table>
      <tr><th>File</th><th>Key</th><th>Name</th><th>Path</th><th>Mode</th></tr>
      <tr>
        <td><a href="/config/bridge/bridge.json">bridge.json</a></td>
        <td>bridge</td>
        <td>DMS Provider Bridge</td>
        <td class="path-cell" title="{html.escape(str(path))}">{html.escape(str(path))}</td>
        <td><span class="badge badge-read-only">READ-ONLY CONFIG</span></td>
      </tr>
    </table>
  </div>
</section>
"""
    return _render_layout("Config Bridge", body, "bridge")


@router.get("/bridge/bridge.json", response_class=HTMLResponse)
def config_bridge_file() -> HTMLResponse:
    path = _bridge_config_path()
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Bridge config file not found: bridge.json")
    payload = _read_json_file(path)
    rendered = json.dumps(payload, ensure_ascii=False, indent=4)
    body = f"""
<div class="grid">
  <section class="panel">
    <h2>Bridge</h2>
    <div class="panel-content file-list">
      <a class="active" href="/config/bridge">bridge.json</a>
    </div>
  </section>
  <section class="panel">
    <h2>bridge.json</h2>
    <div class="panel-content">
      <div class="editor-header">
        <div>
          <p class="editor-title"><strong>bridge.json</strong> local bridge service</p>
          <p class="editor-subtitle muted file-path" title="{html.escape(str(path))}">{html.escape(str(path))}</p>
        </div>
        <span class="badge badge-read-only">READ ONLY</span>
      </div>
      <p class="meta">
        <span>Section: Bridge</span>
        <span>Role: local bridge service configuration</span>
        <span>Mode: read only</span>
      </p>
      <p class="contract-warning">Bridge config controls the local bridge service. It can be changed and configured, but only when you know exactly what you are doing.</p>
      <textarea readonly>{html.escape(rendered)}</textarea>
      <div class="actions">
        <button class="button-primary" type="button" disabled>Save</button>
        <a class="button button-muted" href="/config/reload">Reload</a>
        <a class="button button-muted" href="/config/bridge">Cancel</a>
        <span class="muted">Bridge config is read-only in Config UI.</span>
      </div>
    </div>
  </section>
</div>
"""
    return _render_layout("Bridge Config", body, "bridge")


@router.get("/reload", response_class=HTMLResponse)
def config_reload() -> HTMLResponse:
    snapshot = _reload_runtime_snapshot()
    body = f"""
<section class="panel">
  <h2>Reload Runtime</h2>
  <div class="panel-content">
    <p class="notice">Configuration cache was reloaded. Next bridge request will use current JSON files.</p>
    {_runtime_summary_html(snapshot)}
    <p><a class="button button-muted" href="/config">Back to Config</a></p>
  </div>
</section>
"""
    return _render_layout("Config Reload", body)


@router.post("/reload")
def config_reload_api() -> dict[str, Any]:
    return _reload_runtime_snapshot()


@router.get("/audit", response_class=HTMLResponse)
def config_audit() -> HTMLResponse:
    reload_provider_cache()
    audit = audit_connection_runtime()
    rows = []
    for row in audit["connections"]:
        issues = row["issues"]
        issue_text = ", ".join(str(issue) for issue in issues) if issues else "OK"
        badge_class = "badge-read-only" if row["ok"] else "badge-template"
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(row['name']))}</td>"
            f"<td>{html.escape(str(row.get('driver') or ''))}</td>"
            f"<td>{html.escape(str(row.get('mount') or ''))}</td>"
            f"<td>{html.escape(str(row.get('runtime_driver') or ''))}</td>"
            f"<td>{html.escape(str(row.get('runtime_mount') or ''))}</td>"
            f"<td><span class=\"badge {badge_class}\">{html.escape(issue_text)}</span></td>"
            "</tr>"
        )
    if not rows:
        rows.append('<tr><td colspan="6" class="muted">No connections found.</td></tr>')

    status_class = "notice" if audit["ok"] else "read-only-warning"
    status_text = "Connection runtime audit passed." if audit["ok"] else "Connection runtime audit found issues."
    registry = audit.get("runtime_registry") if isinstance(audit, dict) else None
    wfx_connections = registry.get("wfx_connections") if isinstance(registry, dict) else audit["registered_connections"]
    registered = ", ".join(str(name) for name in wfx_connections)
    drivers = ", ".join(str(name) for name in audit["available_drivers"])
    body = f"""
<section class="panel">
  <h2>Runtime Audit</h2>
  <div class="panel-content">
    <p class="{status_class}">{html.escape(status_text)}</p>
    <p class="help">Checks the ABC -> driver -> connection runtime registry. WFX exposes connection/mount names.</p>
    <p class="muted">WFX connections: {html.escape(registered)}</p>
    <p class="muted">Available drivers: {html.escape(drivers)}</p>
    <table>
      <tr><th>Connection</th><th>Driver</th><th>Mount</th><th>Runtime Driver</th><th>Runtime Mount</th><th>Status</th></tr>
      {''.join(rows)}
    </table>
  </div>
</section>
"""
    return _render_layout("Config Runtime Audit", body)


@router.get("/{section}", response_class=HTMLResponse)
def config_section(section: str) -> HTMLResponse:
    directory = _section_dir(section)
    files = _json_files(section)
    new_link = ""
    if _section_can_create(section):
        new_link = (
            f'<p><a class="button button-success" href="/config/{html.escape(section)}/new">'
            f"New {_SECTION_TITLES[section][:-1]}</a></p>"
        )
    rows = []
    extra_headers = "".join(f"<th>{html.escape(header)}</th>" for header in _extra_table_headers(section))
    actions_header = "<th>Actions</th>" if _section_can_create(section) else ""
    column_count = 5 + len(_extra_table_headers(section)) + (1 if actions_header else 0)
    for path in files:
        payload = _read_json_file(path)
        key = _payload_key(payload, path.stem)
        display_name = _payload_display_name(payload, key)
        mode = _file_mode(section, path.name)
        badge_class = _mode_badge_class(mode)
        extra_cells = "".join(f"<td>{cell}</td>" for cell in _extra_table_cells(section, payload, key))
        actions = ""
        if _section_can_create(section):
            delete_link = ""
            if _file_can_delete(section, path.name):
                delete_link = (
                    f'<a class="link-button table-action button-danger" href="/config/{html.escape(section)}/{html.escape(path.name)}/delete">'
                    "Delete</a>"
                )
            actions = f"<td>{delete_link}</td>"
        rows.append(
            "<tr>"
            f'<td><a href="/config/{html.escape(section)}/{html.escape(path.name)}">{html.escape(path.name)}</a></td>'
            f"<td>{html.escape(key)}</td>"
            f"<td>{html.escape(display_name)}</td>"
            f"{extra_cells}"
            f'<td class="path-cell" title="{html.escape(str(path))}">{html.escape(str(path))}</td>'
            f'<td><span class="badge {badge_class}">{html.escape(mode.upper())}</span></td>'
            f"{actions}"
            "</tr>"
        )
    if not rows:
        rows.append(f'<tr><td colspan="{column_count}" class="muted">No JSON files found.</td></tr>')
    body = f"""
<section class="panel">
  <h2>{html.escape(_SECTION_TITLES[section])}</h2>
  <div class="panel-content">
    <p>{html.escape(_SECTION_ROLES[section])}</p>
    <p class="{'contract-warning' if section == 'providers' else 'help'}">{html.escape(_SECTION_HELP[section])}</p>
    {new_link}
    <p class="muted file-path" title="{html.escape(str(directory))}">Directory: {html.escape(str(directory))}</p>
    <table>
      <tr><th>File</th><th>Key</th><th>Name</th>{extra_headers}<th>Path</th><th>Mode</th>{actions_header}</tr>
      {''.join(rows)}
    </table>
  </div>
</section>
"""
    return _render_layout(f"Config {section}", body, section)


@router.get("/{section}/new", response_class=HTMLResponse)
def config_new(section: str) -> HTMLResponse:
    template = _template_path(section)
    payload = _new_payload_from_template(section, _read_json_file(template))
    rendered = json.dumps(payload, ensure_ascii=False, indent=4)
    body = _render_editor(
        section=section,
        file_name="new.json",
        payload=payload,
        rendered=rendered,
        message=f"New file will be created from template {template.name}. Change the root key before saving.",
        is_new=True,
    )
    return _render_layout(f"New {section}", body, section)


@router.get("/{section}/{file_name}", response_class=HTMLResponse)
def config_file(section: str, file_name: str) -> HTMLResponse:
    _validate_config_file_name(file_name)
    path = _config_file_path(section, file_name)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail=f"Config file not found: {file_name}")
    payload = _read_json_file(path)
    rendered = json.dumps(payload, ensure_ascii=False, indent=4)
    body = _render_editor(section=section, file_name=file_name, payload=payload, rendered=rendered)
    return _render_layout(f"Config {file_name}", body, section)


@router.get("/{section}/{file_name}/test", response_class=HTMLResponse)
def config_test(section: str, file_name: str) -> HTMLResponse:
    if section != "connections":
        raise HTTPException(status_code=400, detail="Only connections can be tested.")
    _validate_config_file_name(file_name)
    path = _config_file_path(section, file_name)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail=f"Config file not found: {file_name}")
    payload = _read_json_file(path)
    key = _payload_key(payload, path.stem)
    try:
        reload_provider_cache()
        provider = get_connection_runtime(key)
        config = getattr(provider, "config", {})
        auth_config = {}
        if isinstance(config, dict):
            credentials = config.get("credentials")
            auth = config.get("auth")
            if isinstance(credentials, dict):
                auth_config.update(credentials)
            if isinstance(auth, dict):
                auth_config.update(auth)
        auth_mode = auth_config.get("mode")
        auth_scheme = auth_config.get("authScheme") or auth_config.get("scheme") or auth_config.get("type")
        auth_target = auth_config.get("target") or auth_config.get("credential_id") or auth_config.get("targetBase")
        rows = [
            ("Status", "Connection OK"),
            ("Name", getattr(provider, "name", key)),
            ("Driver", _string_value(config.get("driver") if isinstance(config, dict) else None)),
            ("Mount", _string_value(config.get("mount") if isinstance(config, dict) else None)),
            ("Display name", _string_value(config.get("display_name") if isinstance(config, dict) else None)),
            ("Base URL", _string_value(config.get("base_url") if isinstance(config, dict) else None)),
            ("Auth mode", _string_value(auth_mode)),
            ("Auth scheme", _string_value(auth_scheme)),
            ("Auth target", _string_value(auth_target)),
            ("List endpoint", _string_value(provider.bridge_endpoint_for("list"))),
        ]
        body_rows = "".join(
            f"<tr><th>{html.escape(label)}</th><td>{html.escape(value)}</td></tr>"
            for label, value in rows
        )
        mount = _string_value(config.get("mount") if isinstance(config, dict) else None) or f"{key}:/"
        auth_example = json.dumps(
            {
                "mode": "credentials",
                "username": "",
                "password": "",
            },
            ensure_ascii=False,
            indent=4,
        )
        body = f"""
<section class="panel">
  <h2>Test {html.escape(file_name)}</h2>
  <div class="panel-content">
    <p class="notice">Connection runtime configuration was loaded successfully. No live DMS request was made.</p>
    <table>{body_rows}</table>
    <h2>Live List Root</h2>
    <p class="help">Optional live test. Auth JSON is used only for this request and is not saved.</p>
    <form method="post" action="/config/{html.escape(section)}/{html.escape(file_name)}/test/live">
      <input type="hidden" name="mount" value="{html.escape(mount)}">
      <textarea name="auth_json" style="min-height: 150px;">{html.escape(auth_example)}</textarea>
      <div class="actions">
        <button class="button-primary" type="submit">Live List Root</button>
        <span class="muted">Target: {html.escape(mount)}</span>
      </div>
    </form>
    <p><a class="button button-muted" href="/config/{html.escape(section)}/{html.escape(file_name)}">Back to connection</a></p>
  </div>
</section>
"""
    except Exception as exc:
        body = f"""
<section class="panel">
  <h2>Test {html.escape(file_name)}</h2>
  <div class="panel-content">
    <p class="read-only-warning">Connection test failed: {html.escape(str(exc))}</p>
    <p><a class="button button-muted" href="/config/{html.escape(section)}/{html.escape(file_name)}">Back to connection</a></p>
  </div>
</section>
"""
    return _render_layout(f"Test {file_name}", body, section)


@router.post("/{section}/{file_name}/test/live", response_class=HTMLResponse)
def config_live_test(section: str, file_name: str, auth_json: str = Form(...), mount: str = Form(default="")) -> HTMLResponse:
    if section != "connections":
        raise HTTPException(status_code=400, detail="Only connections can be tested.")
    _validate_config_file_name(file_name)
    path = _config_file_path(section, file_name)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail=f"Config file not found: {file_name}")
    payload = _read_json_file(path)
    key = _payload_key(payload, path.stem)
    try:
        auth_payload = _parse_json_payload(auth_json)
        auth = BridgeAuthContext.model_validate(auth_payload)
        target_mount = mount.strip() or f"{key}:/"
        if not target_mount.endswith(":/"):
            target_mount = f"{target_mount.rstrip('/')}/"
        response = list_path(target_mount, auth)
        data = response.data if isinstance(response.data, dict) else {}
        items = data.get("items") if isinstance(data, dict) else None
        item_count = len(items) if isinstance(items, list) else 0
        status_class = "notice" if response.ok else "read-only-warning"
        status_text = "Live list root succeeded." if response.ok else "Live list root failed."
        rows = [
            ("Status", status_text),
            ("Mount", target_mount),
            ("OK", str(response.ok)),
            ("Error code", str(response.error_code)),
            ("Message", response.message or ""),
            ("Items", str(item_count)),
        ]
    except Exception as exc:
        status_class = "read-only-warning"
        rows = [
            ("Status", "Live list root failed."),
            ("Mount", mount.strip() or f"{key}:/"),
            ("OK", "False"),
            ("Error code", ""),
            ("Message", str(exc)),
            ("Items", "0"),
        ]

    body_rows = "".join(f"<tr><th>{html.escape(label)}</th><td>{html.escape(value)}</td></tr>" for label, value in rows)
    body = f"""
<section class="panel">
  <h2>Live Test {html.escape(file_name)}</h2>
  <div class="panel-content">
    <p class="{status_class}">{html.escape(rows[0][1])}</p>
    <table>{body_rows}</table>
    <p><a class="button button-muted" href="/config/{html.escape(section)}/{html.escape(file_name)}/test">Back to test</a></p>
  </div>
</section>
"""
    return _render_layout(f"Live Test {file_name}", body, section)


@router.get("/{section}/{file_name}/delete", response_class=HTMLResponse)
def config_delete_confirm(section: str, file_name: str) -> HTMLResponse:
    _validate_config_file_name(file_name)
    if not _file_can_delete(section, file_name):
        raise HTTPException(status_code=403, detail=f"Config file is read-only: {file_name}")
    path = _config_file_path(section, file_name)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail=f"Config file not found: {file_name}")
    body = f"""
<section class="panel">
  <h2>Delete {html.escape(file_name)}</h2>
  <div class="panel-content">
    <p class="read-only-warning">Delete config file {html.escape(file_name)}?</p>
    <p class="muted file-path" title="{html.escape(str(path))}">{html.escape(str(path))}</p>
    <form method="post" action="/config/{html.escape(section)}/{html.escape(file_name)}/delete">
      <div class="actions">
        <button class="button-danger" type="submit">Delete</button>
        <a class="button button-muted" href="/config/{html.escape(section)}/{html.escape(file_name)}">Cancel</a>
      </div>
    </form>
  </div>
</section>
"""
    return _render_layout(f"Delete {file_name}", body, section)


@router.post("/{section}/{file_name}/delete", response_class=HTMLResponse)
def config_delete(section: str, file_name: str) -> HTMLResponse:
    _validate_config_file_name(file_name)
    if not _file_can_delete(section, file_name):
        raise HTTPException(status_code=403, detail=f"Config file is read-only: {file_name}")
    path = _section_dir(section) / file_name
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail=f"Config file not found: {file_name}")
    path.unlink()
    reload_provider_cache()
    body = f"""
<section class="panel">
  <h2>Deleted</h2>
  <div class="panel-content">
    <p class="notice">Deleted {html.escape(file_name)}.</p>
    <p class="notice">Runtime cache was reloaded.</p>
    <p><a class="button button-muted" href="/config/{html.escape(section)}">Back to {html.escape(_SECTION_TITLES[section])}</a></p>
  </div>
</section>
"""
    return _render_layout(f"Deleted {file_name}", body, section)


def _string_value(value: Any) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else ""


def _render_editor(
    section: str,
    file_name: str,
    payload: dict[str, Any],
    rendered: str,
    message: str = "",
    is_new: bool = False,
    original_file_name: str = "",
    confirm_overwrite: bool = False,
    target_file_name: str = "",
    validation_errors: list[str] | None = None,
) -> str:
    readonly_attr = "readonly" if _file_read_only(section, file_name) else ""
    disabled_attr = "disabled" if readonly_attr else ""
    mode = _file_mode(section, file_name)
    badge_class = _mode_badge_class(mode)
    key = _payload_key(payload, Path(file_name).stem)
    display_name = _payload_display_name(payload, key)
    notice = f'<p class="notice">{html.escape(message)}</p>' if message else ""
    read_only_warning = ""
    if readonly_attr and section != "providers":
        read_only_warning = '<p class="read-only-warning">This file is read-only. Use New to create an editable copy.</p>'
    submit_label = "Create" if is_new else "Save"
    original_value = original_file_name or ("" if is_new else file_name)
    overwrite_value = "true" if confirm_overwrite else "false"
    confirm = ""
    if confirm_overwrite:
        submit_label = "Overwrite"
        confirm = (
            f'<p class="read-only-warning">File {html.escape(target_file_name)} already exists. '
            "Confirm overwrite or cancel.</p>"
        )
    validation = ""
    if validation_errors:
        items = "".join(f"<li>{html.escape(error)}</li>" for error in validation_errors)
        validation = (
            '<div class="read-only-warning">'
            "<strong>Validation failed. No file was written.</strong>"
            f"<ul>{items}</ul>"
            "</div>"
        )
    form_open = f'<form method="post" action="/config/{html.escape(section)}/save">'
    form_close = "</form>"
    test_link = ""
    if section == "connections" and not is_new and not _file_read_only(section, file_name):
        test_link = (
            f'<a class="button button-secondary" '
            f'href="/config/{html.escape(section)}/{html.escape(file_name)}/test">Test</a>'
        )
    delete_link = ""
    if not is_new and _file_can_delete(section, file_name):
        delete_link = (
            f'<a class="button button-danger" '
            f'href="/config/{html.escape(section)}/{html.escape(file_name)}/delete">Delete</a>'
        )
    section_path = _section_dir(section) / file_name
    return f"""
<div class="grid">
  <section class="panel">
    <h2>{html.escape(_SECTION_TITLES[section])}</h2>
    <div class="panel-content file-list">
      {_file_links(section, file_name)}
    </div>
  </section>
  <section class="panel">
    <h2>{html.escape(file_name)}</h2>
    <div class="panel-content">
      {notice}
      {read_only_warning}
      {confirm}
      {validation}
      <div class="editor-header">
        <div>
          <p class="editor-title"><strong>{html.escape(key)}</strong> {html.escape(display_name)}</p>
          <p class="editor-subtitle muted file-path" title="{html.escape(str(section_path))}">{html.escape(str(section_path))}</p>
        </div>
        <span class="badge {badge_class}">{html.escape(mode.upper())}</span>
      </div>
      <p class="meta">
        <span>Section: {html.escape(_SECTION_TITLES[section])}</span>
        <span>Role: {html.escape(_SECTION_ROLES[section])}</span>
        <span>Mode: {html.escape(mode)}</span>
      </p>
      <p class="{'contract-warning' if section in {'providers', 'auth'} else 'help'}">{html.escape(_SECTION_HELP[section])}</p>
      {form_open}
        <input type="hidden" name="file_name" value="{html.escape(original_value)}">
        <input type="hidden" name="overwrite" value="{html.escape(overwrite_value)}">
        <textarea name="payload" {readonly_attr}>{html.escape(rendered)}</textarea>
        <div class="actions">
          <button class="button-primary" type="submit" {disabled_attr}>{html.escape(submit_label)}</button>
          {test_link}
          {delete_link}
          <a class="button button-muted" href="/config/reload">Reload</a>
          <a class="button button-muted" href="/config/{html.escape(section)}">Cancel</a>
          <span class="muted">Templates and Provider ABC are read-only.</span>
        </div>
      {form_close}
    </div>
  </section>
</div>
"""


@router.post("/{section}/save", response_class=HTMLResponse)
def config_save(
    section: str,
    file_name: str = Form(default=""),
    payload: str = Form(...),
    overwrite: str = Form(default="false"),
) -> HTMLResponse:
    if not _section_can_create(section):
        raise HTTPException(status_code=403, detail=f"Section is read-only: {section}")
    original_file = file_name.strip()
    if original_file:
        _validate_config_file_name(original_file)
        if _file_read_only(section, original_file):
            raise HTTPException(status_code=403, detail=f"Config file is read-only: {original_file}")
    parsed = _parse_json_payload(payload)
    key = _payload_key(parsed, "")
    target_file = _safe_file_name_from_key(key)
    _validate_config_file_name(target_file)
    if _file_read_only(section, target_file):
        raise HTTPException(status_code=403, detail=f"Config file is read-only: {target_file}")
    validation_errors = _validate_config_payload(section, parsed, target_file, original_file)
    if validation_errors:
        rendered = json.dumps(parsed, ensure_ascii=False, indent=4)
        body = _render_editor(
            section=section,
            file_name=target_file,
            payload=parsed,
            rendered=rendered,
            message="No file was written yet.",
            is_new=not original_file,
            original_file_name=original_file,
            validation_errors=validation_errors,
        )
        return _render_layout(f"Validation {target_file}", body, section)
    target_path = _section_dir(section) / target_file
    is_same_file_save = bool(original_file) and original_file == target_file
    if target_path.exists() and not is_same_file_save and overwrite.casefold() != "true":
        rendered = json.dumps(parsed, ensure_ascii=False, indent=4)
        body = _render_editor(
            section=section,
            file_name=target_file,
            payload=parsed,
            rendered=rendered,
            message="No file was written yet.",
            is_new=not original_file,
            original_file_name=original_file,
            confirm_overwrite=True,
            target_file_name=target_file,
        )
        return _render_layout(f"Overwrite {target_file}", body, section)
    _write_json_atomic(target_path, parsed)
    reload_provider_cache()
    rendered = json.dumps(parsed, ensure_ascii=False, indent=4)
    body = _render_editor(
        section=section,
        file_name=target_file,
        payload=parsed,
        rendered=rendered,
        message=f"Saved {target_file}. Runtime cache was reloaded.",
    )
    return _render_layout(f"Config {target_file}", body, section)


@router.get("/{section}/{file_name}/json")
def config_file_json(section: str, file_name: str) -> dict[str, Any]:
    _validate_config_file_name(file_name)
    path = _config_file_path(section, file_name)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail=f"Config file not found: {file_name}")
    return {
        "section": section,
        "file": file_name,
        "path": str(path),
        "read_only": _file_read_only(section, file_name),
        "data": _read_json_file(path),
    }
