from __future__ import annotations

import html
import json
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from dms_provider_bridge.core.config_loader import load_config
from dms_provider_bridge.core.paths import MACHINE_CONFIG_DIR

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
    if not directory.exists():
        return []
    return sorted(path for path in directory.glob("*.json") if path.is_file())


def _read_json_file(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            payload = json.load(handle)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"Invalid JSON in {path.name}: {exc}") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=500, detail=f"Config file must contain a JSON object: {path.name}")
    return payload


def _section_read_only(section: str) -> bool:
    return section == "providers"


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


def _file_mode(section: str, file_name: str) -> str:
    if section == "providers":
        return "read-only contract"
    if file_name in {"driver.json", "connection.json"}:
        return "template preview"
    return "preview"


def _mode_badge_class(mode: str) -> str:
    if mode.startswith("read-only"):
        return "badge-read-only"
    if mode.startswith("template"):
        return "badge-template"
    return "badge-preview"


def _file_links(section: str, active_file: str) -> str:
    links = []
    for path in _json_files(section):
        class_name = "active" if path.name == active_file else ""
        links.append(
            f'<a class="{class_name}" href="/config/{html.escape(section)}/{html.escape(path.name)}">'
            f"{html.escape(path.name)}</a>"
        )
    return "\n".join(links) or '<span class="muted">No JSON files found.</span>'


def _render_nav(active: str | None = None) -> str:
    links = ['<a class="home" href="/config">Config</a>']
    for section, title in _SECTION_TITLES.items():
        class_name = "active" if section == active else ""
        links.append(f'<a class="{class_name}" href="/config/{section}">{html.escape(title)}</a>')
    utility = '<span class="utility"><a href="/docs">Docs</a><a href="/health">Health</a></span>'
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
    table {{ width: 100%; border-collapse: collapse; background: white; }}
    th, td {{ border-bottom: 1px solid #d7dde5; padding: 8px 10px; text-align: left; vertical-align: top; }}
    th {{ background: #eef2f7; }}
    pre {{ margin: 0; padding: 12px; background: #111827; color: #e5e7eb; overflow: auto; }}
    textarea {{ width: 100%; min-height: 560px; box-sizing: border-box; font: 13px Consolas, monospace; border: 1px solid #9aa6b2; padding: 10px; background: #fcfcfd; }}
    .muted {{ color: #64748b; }}
    .meta {{ display: flex; gap: 10px; flex-wrap: wrap; margin: 0 0 10px; }}
    .meta span {{ background: #eef2f7; border: 1px solid #d7dde5; padding: 4px 7px; border-radius: 3px; }}
    .badge {{ display: inline-block; min-width: 82px; text-align: center; padding: 3px 7px; border-radius: 3px; font-size: 12px; font-weight: 600; }}
    .badge-read-only {{ background: #e6f4ea; color: #137333; border: 1px solid #9ad1aa; }}
    .badge-template {{ background: #fff4e5; color: #9a5b00; border: 1px solid #f0c36d; }}
    .badge-preview {{ background: #e7f0ff; color: #1a5fb4; border: 1px solid #9fc3ff; }}
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
      <p>VFS/common contract used internally by the bridge.</p>
    </div>
  </a>
  <a class="section-card" href="/config/drivers">
    <h2>Drivers</h2>
    <div>
      <p><span class="badge badge-preview">PREVIEW</span></p>
      <p>Filesystem driver definitions for concrete DMS implementations.</p>
    </div>
  </a>
  <a class="section-card" href="/config/connections">
    <h2>Connections</h2>
    <div>
      <p><span class="badge badge-preview">PREVIEW</span></p>
      <p>Mount definitions exposed to clients as connection:/path.</p>
    </div>
  </a>
</div>
"""
    return _render_layout("DMS Provider Bridge Config", body)


@router.get("/{section}", response_class=HTMLResponse)
def config_section(section: str) -> HTMLResponse:
    directory = _section_dir(section)
    files = _json_files(section)
    rows = []
    for path in files:
        payload = _read_json_file(path)
        key = _payload_key(payload, path.stem)
        display_name = _payload_display_name(payload, key)
        mode = _file_mode(section, path.name)
        badge_class = _mode_badge_class(mode)
        rows.append(
            "<tr>"
            f'<td><a href="/config/{html.escape(section)}/{html.escape(path.name)}">{html.escape(path.name)}</a></td>'
            f"<td>{html.escape(key)}</td>"
            f"<td>{html.escape(display_name)}</td>"
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
    <p class="muted">Directory: {html.escape(str(directory))}</p>
    <table>
      <tr><th>File</th><th>Key</th><th>Name</th><th>Path</th><th>Mode</th></tr>
      {''.join(rows)}
    </table>
  </div>
</section>
"""
    return _render_layout(f"Config {section}", body, section)


@router.get("/{section}/{file_name}", response_class=HTMLResponse)
def config_file(section: str, file_name: str) -> HTMLResponse:
    if "/" in file_name or "\\" in file_name or not file_name.endswith(".json"):
        raise HTTPException(status_code=400, detail="Invalid config file name.")
    path = _section_dir(section) / file_name
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail=f"Config file not found: {file_name}")
    payload = _read_json_file(path)
    rendered = json.dumps(payload, ensure_ascii=False, indent=4)
    readonly = "readonly" if _section_read_only(section) else ""
    mode = _file_mode(section, file_name)
    badge_class = _mode_badge_class(mode)
    key = _payload_key(payload, path.stem)
    display_name = _payload_display_name(payload, key)
    body = f"""
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
      <p class="meta">
        <span>Section: {html.escape(_SECTION_TITLES[section])}</span>
        <span>Role: {html.escape(_SECTION_ROLES[section])}</span>
        <span>Mode: <span class="badge {badge_class}">{html.escape(mode.upper())}</span></span>
      </p>
      <p><strong>{html.escape(key)}</strong> {html.escape(display_name)}</p>
      <p class="muted">{html.escape(str(path))}</p>
      <textarea {readonly}>{html.escape(rendered)}</textarea>
    </div>
  </section>
</div>
"""
    return _render_layout(f"Config {file_name}", body, section)


@router.get("/{section}/{file_name}/json")
def config_file_json(section: str, file_name: str) -> dict[str, Any]:
    if "/" in file_name or "\\" in file_name or not file_name.endswith(".json"):
        raise HTTPException(status_code=400, detail="Invalid config file name.")
    path = _section_dir(section) / file_name
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail=f"Config file not found: {file_name}")
    return {
        "section": section,
        "file": file_name,
        "path": str(path),
        "read_only": section == "providers",
        "data": _read_json_file(path),
    }
