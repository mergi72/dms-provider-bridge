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
from dms_provider_bridge.services.provider_service import get_provider, reload_provider_cache

router = APIRouter()


_SECTION_TITLES = {
    "providers": "Provider ABC",
    "drivers": "Drivers",
    "connections": "Connections",
}

_SECTION_ROLES = {
    "providers": "VFS/common contract",
    "drivers": "filesystem driver definitions",
    "connections": "mount definitions",
}

_SECTION_HELP = {
    "providers": (
        "Provider ABC is the internal bridge contract. It can be changed and configured, "
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


def _registry_paths() -> dict[str, Path]:
    config = load_config()
    paths = config.get("paths") if isinstance(config, dict) else None
    if not isinstance(paths, dict):
        paths = {}
    machine_config_dir = Path(os.environ.get("DMS_PROVIDER_MACHINE_CONFIG_DIR", str(MACHINE_CONFIG_DIR)))
    return {
        "providers": machine_config_dir / str(paths.get("providers") or "providers"),
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
    return section == "providers" or _TEMPLATE_FILES.get(section) == file_name


def _section_can_create(section: str) -> bool:
    return section in _TEMPLATE_FILES


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
    if _TEMPLATE_FILES.get(section) == file_name:
        return "template read only"
    return "editable"


def _mode_badge_class(mode: str) -> str:
    if mode.startswith("read-only"):
        return "badge-read-only"
    if mode.startswith("template"):
        return "badge-template"
    return "badge-editable"


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
    links = ['<a class="home" href="/config">Config</a>']
    for section, title in _SECTION_TITLES.items():
        class_name = "active" if section == active else ""
        links.append(f'<a class="{class_name}" href="/config/{section}">{html.escape(title)}</a>')
    utility = (
        '<span class="utility">'
        '<a href="/config/reload">Reload</a>'
        '<a href="/docs">Docs</a><a href="/health">Health</a>'
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
    body {{ margin: 0; font-family: Segoe UI, Arial, sans-serif; background: #f7f8fa; color: #1f2933; }}
    header {{ background: #1f2933; color: white; padding: 14px 20px; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 16px 20px; }}
    nav {{ display: flex; gap: 8px; margin-bottom: 14px; flex-wrap: wrap; align-items: center; }}
    nav a {{ color: #1f2933; text-decoration: none; padding: 7px 11px; border: 1px solid #c7ced8; background: white; border-radius: 3px; }}
    nav a.active {{ background: #e7f0ff; border-color: #6b9de8; }}
    nav a.home {{ font-weight: 600; }}
    nav .utility {{ margin-left: auto; display: flex; gap: 6px; }}
    nav .utility a {{ font-size: 13px; padding: 5px 9px; }}
    .file-list {{ display: flex; flex-direction: column; gap: 6px; }}
    .file-list a {{ color: #1f2933; text-decoration: none; padding: 7px 9px; border: 1px solid #d7dde5; background: #fff; border-radius: 3px; }}
    .file-list a.active {{ background: #e7f0ff; border-color: #6b9de8; }}
    .file-list a.new {{ background: #eefaf1; border-color: #9ad1aa; color: #137333; font-weight: 600; }}
    table {{ width: 100%; border-collapse: collapse; background: white; }}
    th, td {{ border-bottom: 1px solid #d7dde5; padding: 8px 10px; text-align: left; vertical-align: top; }}
    th {{ background: #eef2f7; }}
    pre {{ margin: 0; padding: 12px; background: #111827; color: #e5e7eb; overflow: auto; }}
    textarea {{ width: 100%; min-height: 560px; box-sizing: border-box; font: 13px Consolas, monospace; border: 1px solid #9aa6b2; padding: 10px; background: #fcfcfd; }}
    textarea[readonly] {{ background: #f3f4f6; border-color: #c7ced8; color: #4b5563; }}
    form {{ margin: 0; }}
    button {{ cursor: pointer; border: 1px solid #2d6cdf; background: #2d6cdf; color: white; padding: 7px 14px; border-radius: 3px; font-weight: 600; }}
    button:disabled {{ cursor: default; border-color: #c7ced8; background: #eef2f7; color: #64748b; }}
    .link-button {{ color: #1f2933; text-decoration: none; padding: 5px 9px; border: 1px solid #c7ced8; background: white; border-radius: 3px; font-size: 13px; font-weight: 400; }}
    .actions {{ display: flex; gap: 8px; align-items: center; margin-top: 10px; }}
    .muted {{ color: #64748b; }}
    .notice {{ margin: 0 0 10px; padding: 8px 10px; border-radius: 3px; border: 1px solid #9ad1aa; background: #e6f4ea; color: #137333; }}
    .read-only-warning {{ margin: 0 0 10px; padding: 8px 10px; border-radius: 3px; border: 1px solid #f0c36d; background: #fff4e5; color: #9a5b00; font-weight: 600; }}
    .help {{ margin: 0 0 12px; padding: 10px 12px; border-left: 4px solid #6b9de8; background: #eef5ff; color: #243b53; }}
    .meta {{ display: flex; gap: 10px; flex-wrap: wrap; margin: 0 0 10px; }}
    .meta span {{ background: #eef2f7; border: 1px solid #d7dde5; padding: 4px 7px; border-radius: 3px; }}
    .badge {{ display: inline-block; min-width: 82px; text-align: center; padding: 3px 7px; border-radius: 3px; font-size: 12px; font-weight: 600; }}
    .badge-read-only {{ background: #e6f4ea; color: #137333; border: 1px solid #9ad1aa; }}
    .badge-template {{ background: #fff4e5; color: #9a5b00; border: 1px solid #f0c36d; }}
    .badge-preview {{ background: #e7f0ff; color: #1a5fb4; border: 1px solid #9fc3ff; }}
    .badge-editable {{ background: #e7f0ff; color: #1a5fb4; border: 1px solid #9fc3ff; }}
    .grid {{ display: grid; grid-template-columns: 260px 1fr; gap: 16px; align-items: start; }}
    .panel {{ background: white; border: 1px solid #d7dde5; border-radius: 4px; overflow: hidden; }}
    .panel h2 {{ font-size: 16px; margin: 0; padding: 10px 12px; border-bottom: 1px solid #d7dde5; background: #eef2f7; }}
    .panel-content {{ padding: 12px; }}
    .section-grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }}
    .section-card {{ display: block; color: inherit; text-decoration: none; background: white; border: 1px solid #d7dde5; border-radius: 4px; overflow: hidden; }}
    .section-card h2 {{ font-size: 16px; margin: 0; padding: 10px 12px; border-bottom: 1px solid #d7dde5; background: #eef2f7; }}
    .section-card div {{ padding: 12px; }}
    .section-card:hover {{ border-color: #6b9de8; }}
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
  <a class="section-card" href="/config/providers">
    <h2>Provider ABC</h2>
    <div>
      <p><span class="badge badge-read-only">READ ONLY</span></p>
      <p class="help">Provider ABC is the internal bridge contract. It can be changed and configured, but only when you know exactly what you are doing.</p>
      <p>VFS/common contract used internally by the bridge.</p>
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


@router.get("/reload", response_class=HTMLResponse)
def config_reload() -> HTMLResponse:
    reload_provider_cache()
    body = """
<section class="panel">
  <h2>Reload</h2>
  <div class="panel-content">
    <p class="notice">Configuration cache was reloaded. Next bridge request will use current JSON files.</p>
    <p><a href="/config">Back to Config</a></p>
  </div>
</section>
"""
    return _render_layout("Config Reload", body)


@router.get("/{section}", response_class=HTMLResponse)
def config_section(section: str) -> HTMLResponse:
    directory = _section_dir(section)
    files = _json_files(section)
    new_link = ""
    if _section_can_create(section):
        new_link = f'<p><a class="badge badge-read-only" href="/config/{html.escape(section)}/new">NEW {_SECTION_TITLES[section][:-1].upper()}</a></p>'
    rows = []
    extra_headers = "".join(f"<th>{html.escape(header)}</th>" for header in _extra_table_headers(section))
    for path in files:
        payload = _read_json_file(path)
        key = _payload_key(payload, path.stem)
        display_name = _payload_display_name(payload, key)
        mode = _file_mode(section, path.name)
        badge_class = _mode_badge_class(mode)
        extra_cells = "".join(f"<td>{cell}</td>" for cell in _extra_table_cells(section, payload, key))
        rows.append(
            "<tr>"
            f'<td><a href="/config/{html.escape(section)}/{html.escape(path.name)}">{html.escape(path.name)}</a></td>'
            f"<td>{html.escape(key)}</td>"
            f"<td>{html.escape(display_name)}</td>"
            f"{extra_cells}"
            f"<td>{html.escape(str(path))}</td>"
            f'<td><span class="badge {badge_class}">{html.escape(mode.upper())}</span></td>'
            "</tr>"
        )
    if not rows:
        rows.append('<tr><td colspan="5" class="muted">No JSON files found.</td></tr>')
    body = f"""
<section class="panel">
  <h2>{html.escape(_SECTION_TITLES[section])}</h2>
  <div class="panel-content">
    <p>{html.escape(_SECTION_ROLES[section])}</p>
    <p class="help">{html.escape(_SECTION_HELP[section])}</p>
    {new_link}
    <p class="muted">Directory: {html.escape(str(directory))}</p>
    <table>
      <tr><th>File</th><th>Key</th><th>Name</th>{extra_headers}<th>Path</th><th>Mode</th></tr>
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
        provider = get_provider(key)
        config = getattr(provider, "config", {})
        credentials = config.get("credentials") if isinstance(config, dict) else None
        auth_mode = credentials.get("mode") if isinstance(credentials, dict) else None
        auth_target = credentials.get("target") if isinstance(credentials, dict) else None
        rows = [
            ("Status", "Connection OK"),
            ("Name", getattr(provider, "name", key)),
            ("Driver", _string_value(config.get("driver") if isinstance(config, dict) else None)),
            ("Mount", _string_value(config.get("mount") if isinstance(config, dict) else None)),
            ("Display name", _string_value(config.get("display_name") if isinstance(config, dict) else None)),
            ("Base URL", _string_value(config.get("base_url") if isinstance(config, dict) else None)),
            ("Auth mode", _string_value(auth_mode)),
            ("Auth target", _string_value(auth_target)),
            ("List endpoint", _string_value(provider.bridge_endpoint_for("list"))),
        ]
        body_rows = "".join(
            f"<tr><th>{html.escape(label)}</th><td>{html.escape(value)}</td></tr>"
            for label, value in rows
        )
        body = f"""
<section class="panel">
  <h2>Test {html.escape(file_name)}</h2>
  <div class="panel-content">
    <p class="notice">Connection runtime configuration was loaded successfully. No live DMS request was made.</p>
    <table>{body_rows}</table>
    <p><a href="/config/{html.escape(section)}/{html.escape(file_name)}">Back to connection</a></p>
  </div>
</section>
"""
    except Exception as exc:
        body = f"""
<section class="panel">
  <h2>Test {html.escape(file_name)}</h2>
  <div class="panel-content">
    <p class="read-only-warning">Connection test failed: {html.escape(str(exc))}</p>
    <p><a href="/config/{html.escape(section)}/{html.escape(file_name)}">Back to connection</a></p>
  </div>
</section>
"""
    return _render_layout(f"Test {file_name}", body, section)


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
) -> str:
    readonly_attr = "readonly" if _file_read_only(section, file_name) else ""
    disabled_attr = "disabled" if readonly_attr else ""
    mode = _file_mode(section, file_name)
    badge_class = _mode_badge_class(mode)
    key = _payload_key(payload, Path(file_name).stem)
    display_name = _payload_display_name(payload, key)
    notice = f'<p class="notice">{html.escape(message)}</p>' if message else ""
    read_only_warning = ""
    if readonly_attr:
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
    form_open = f'<form method="post" action="/config/{html.escape(section)}/save">'
    form_close = "</form>"
    test_link = ""
    if section == "connections" and not is_new and not _file_read_only(section, file_name):
        test_link = f'<a class="link-button" href="/config/{html.escape(section)}/{html.escape(file_name)}/test">Test</a>'
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
      <p class="meta">
        <span>Section: {html.escape(_SECTION_TITLES[section])}</span>
        <span>Role: {html.escape(_SECTION_ROLES[section])}</span>
        <span>Mode: <span class="badge {badge_class}">{html.escape(mode.upper())}</span></span>
      </p>
      <p class="help">{html.escape(_SECTION_HELP[section])}</p>
      <p><strong>{html.escape(key)}</strong> {html.escape(display_name)}</p>
      <p class="muted">{html.escape(str(_section_dir(section) / file_name))}</p>
      {form_open}
        <input type="hidden" name="file_name" value="{html.escape(original_value)}">
        <input type="hidden" name="overwrite" value="{html.escape(overwrite_value)}">
        <textarea name="payload" {readonly_attr}>{html.escape(rendered)}</textarea>
        <div class="actions">
          <button type="submit" {disabled_attr}>{html.escape(submit_label)}</button>
          <a href="/config/{html.escape(section)}">Cancel</a>
          <a class="link-button" href="/config/reload">Reload</a>
          {test_link}
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
        message=f"Saved {target_file}.",
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
