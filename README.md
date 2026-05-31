# edocat-bridge

[![CI](https://github.com/mergi72/edocat-bridge/actions/workflows/ci.yml/badge.svg)](https://github.com/mergi72/edocat-bridge/actions/workflows/ci.yml)

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

## Testy

Instalace test závislostí:

```bash
python -m pip install -e .[dev]
```

Rychlé spuštění (PowerShell):

```powershell
.\scripts\run-tests.ps1 unit
.\scripts\run-tests.ps1 integration
.\scripts\run-tests.ps1 all
```

Rychlé spuštění (Bash, např. Git Bash/WSL):

```bash
./scripts/run-tests.sh unit
./scripts/run-tests.sh integration
./scripts/run-tests.sh all
```

Poznámka: oba skripty hledají interpreter v pořadí `.venv312`, `.venv`, a nakonec systémový `python`/`python3` z PATH.

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
- `/bridge/wfx/resolve-share-url`
- `/bridge/wfx/browse-share-url`
- `/bridge/wfx/browse-share-url-validate`

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

Poznámka k režimu vykonání:

- Pokud bridge získá použitelné upstream credentials/ticket, operace běží v režimu `live`.
- Pokud credentials/ticket nejsou dostupné, bridge vrací bezpečný `preview` výstup (s přesným endpointem), aby WFX vrstva věděla, co bude voláno.

Přenosové operace:

- `download`: `{ "path": "alfresco:/contracts/sample.txt", "auth": { ... } }`
- `upload`: `{ "destination": "alfresco:/contracts", "file_name": "upload.txt", "content_base64": "...", "overwrite": true, "auth": { ... } }`

Převod eDoCat Share URL na bridge path:

- `resolve-share-url`: `{ "share_url": "https://.../documentlibrary#/03%20.../Upload?page=1", "provider": "alfresco" }`
- Odpověď vrací `data.path` ve formátu `alfresco:/...`, který lze použít pro `list/stat/copy/...`.

One-shot browse přes Share URL:

- `browse-share-url`: `{ "share_url": "https://.../documentlibrary#/03%20.../Upload?page=1", "provider": "alfresco", "operation": "list|stat|download|copy|rename|mkdir|delete|upload", "execute": true, "auth": { ... }, "provider_path_override": "/optional/manual/path", "destination_share_url": "https://...", "destination_path_override": "/target/path", "file_name": "upload.txt", "content_base64": "...", "overwrite": true }`
- `browse-share-url` je canonical endpoint; pro dry-run validaci používej stejný endpoint s `execute=false`.
- V odpovědi je `data.resolved` (výsledek převodu URL), `data.path_source` (`share_url` nebo `provider_path_override`) a `data.result` (výsledek zvolené operace).
- Pro `copy|rename` je navíc povinné zadat `destination_path_override` nebo `destination_share_url`; odpověď obsahuje `data.destination`.
- Pro `upload` je povinné `file_name`; cíl lze zadat přes `destination_path_override`/`destination_share_url`, jinak se použije cesta vyřešená ze `share_url`.
- OpenAPI operationId: `bridgeResolveShareUrl`, `bridgeBrowseShareUrl` (canonical), deprecated alias: `bridgeBrowseShareUrlValidateDeprecated`.
- Pokud `execute=false`, endpoint nic neprovede a vrátí dry-run validaci stejnou logikou jako `browse-share-url-validate`.

Lightweight validace bez spuštění operace:

- `browse-share-url-validate`: stejné vstupy jako `browse-share-url`, ale bez `auth` a bez `content_base64`.
- Endpoint vrací vypočtené `source`/`destination` cesty a validační chyby payloadu, bez volání provider operace.
- Interně je to alias na `browse-share-url` s `execute=false` (jedna společná implementační cesta).
- V OpenAPI je endpoint označen jako deprecated; preferovaný endpoint je `browse-share-url` s `execute=false`.

Poznámka k `download` payloadu:

- V `live` režimu vrací `data.content_base64`, `data.mime_type` a `data.size`.
- V `preview` režimu jsou tyto položky `null` a v `data.message` je uveden cílový endpoint.

## Struktura

Projekt je rozdělen na:

- `app/` API vrstva
- `services/` business logika
- `providers/` implementace providerů
- `clients/` API klienti
- `models/` datové modely
- `core/` konfigurace, logování a utility jádra
