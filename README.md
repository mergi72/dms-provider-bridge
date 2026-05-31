# edocat-bridge

`edocat-bridge` je základní skeleton služby pro propojení Edocat a dalších providerů (Alfresco, FSO, ...).

## Rychlý start

```bash
python -m venv .venv312
.venv312\\Scripts\\activate
pip install -e .
python -m uvicorn edocat_bridge.app.server:app --host 127.0.0.1 --port 8765
```

## VS Code (Windows)

Workspace má přednastavený interpreter na `.venv312` v souboru `.vscode/settings.json`.

## WFX Bridge API (pro C# plugin)

Formát vzdálené cesty:

- `edocat:/folder/file.txt`
- `alfresco:/folder/file.txt`

Endpointy (POST):

- `/bridge/wfx/list`
- `/bridge/wfx/stat`
- `/bridge/wfx/mkdir`
- `/bridge/wfx/delete`
- `/bridge/wfx/rename`
- `/bridge/wfx/copy`
- `/bridge/wfx/download`
- `/bridge/wfx/upload`

Autentizace (`auth`) je povinná pro každé volání:

Bridge používá jednu vstupní autentizaci pro oba providery. Provider-specific HTTP autentizace se řeší až uvnitř provideru.

- `credentials`:
  `{ "auth": { "mode": "credentials", "credential_id": "edocat-prod" } }`
  nebo
  `{ "auth": { "mode": "credentials", "username": "user", "password": "secret" } }`
- `winuser`:
  `{ "auth": { "mode": "winuser", "win_user": "DOMAIN\\uzivatel" } }`

Příklad requestu:

`{ "path": "edocat:/", "auth": { "mode": "winuser", "win_user": "DOMAIN\\uzivatel" } }`

Odpověď má sjednocený tvar:

- `ok` (`true/false`)
- `error_code` (`0` = OK)
- `message` (text chyby)
- `data` (payload operace)
- `metadata.provider` (aktivní provider)
- `metadata.upstream_auth_scheme` (např. `basic`, `ticket`)
- `metadata.upstream_endpoint` (reálný upstream endpoint provideru)

Přenosové operace:

- `download`: `{ "path": "alfresco:/contracts/sample.txt", "auth": { ... } }`
- `upload`: `{ "destination": "alfresco:/contracts", "file_name": "upload.txt", "content_base64": "...", "overwrite": true, "auth": { ... } }`

## Struktura

Projekt je rozdělen na:

- `app/` API vrstva
- `services/` business logika
- `providers/` implementace providerů
- `clients/` API klienti
- `models/` datové modely
- `core/` konfigurace, logování a utility jádra
