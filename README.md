# dms-provider-bridge

[![CI](https://github.com/mergi72/edocat-bridge/actions/workflows/ci.yml/badge.svg)](https://github.com/mergi72/edocat-bridge/actions/workflows/ci.yml)

`dms-provider-bridge` (repo: `edocat-bridge`) je základní skeleton služby pro propojení více DMS providerů (eDoCat, Alfresco, FSO, ...).

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

## Cisty Release ZIP (Bez Cache)

Pro release balicek pouzij archivaci z Gitu, ktera bere jen trackovane soubory:

```powershell
.\scripts\build-release-zip.ps1
```

Tento postup automaticky vylouci lokalni balast jako `__pycache__/`, `*.pyc`, `.venv/` a runtime logy.

Pokud chces predtim uklidit lokalni workspace, pouzij:

```powershell
.\scripts\clean-artifacts.ps1
```

## Bezpecne Testovani (ENV)

Pro lokalni smoke testy nepouzivej hardcoded hesla v historii shellu. Nastav si je do environment promennych a payload skladat z nich.

PowerShell:

```powershell
$env:BRIDGE_USER = "user@domain"
$env:BRIDGE_PASSWORD = "secret"

$body = @{
  path = "edocat:/deals"
  auth = @{
    mode = "credentials"
    username = $env:BRIDGE_USER
    password = $env:BRIDGE_PASSWORD
  }
} | ConvertTo-Json -Depth 10

Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8765/bridge/wfx/list -ContentType "application/json" -Body $body
```

Bash:

```bash
export BRIDGE_USER='user@domain'
export BRIDGE_PASSWORD='secret'

curl -sS http://127.0.0.1:8765/bridge/wfx/list \
  -H 'Content-Type: application/json' \
  -d "{\"path\":\"edocat:/deals\",\"auth\":{\"mode\":\"credentials\",\"username\":\"$BRIDGE_USER\",\"password\":\"$BRIDGE_PASSWORD\"}}"
```

## WFX Bridge API (pro C# plugin)

Formát vzdálené cesty:

- `edocat:/folder/file.txt`
- `alfresco:/folder/file.txt`

Endpointy:

- `GET /bridge/wfx/providers` (provider discovery pro root listing ve WFX pluginu)

- `POST /bridge/wfx/list`
- `POST /bridge/wfx/stat`
- `POST /bridge/wfx/mkdir`
- `POST /bridge/wfx/delete`
- `POST /bridge/wfx/move`
- `POST /bridge/wfx/copy`
- `POST /bridge/wfx/download`
- `POST /bridge/wfx/download-raw`
- `POST /bridge/wfx/upload`
- `POST /bridge/wfx/resolve-share-url`
- `POST /bridge/wfx/browse-share-url`
- `POST /bridge/wfx/browse-share-url-validate`

Autentizace (`auth`) je povinná pro každé volání:

Bridge používá jednu vstupní autentizaci pro oba providery. Provider-specific HTTP autentizace se řeší až uvnitř provideru.

- `credentials`:
  `{ "auth": { "mode": "credentials", "credential_id": "edocat-prod" } }`
  nebo
  `{ "auth": { "mode": "credentials", "username": "user", "password": "secret" } }`

  `credential_id` se čte z Windows Credential Manageru. Pro běžné přihlašovací údaje použij generic credential s `UserName` a tajemstvím v blobu; pokud blob obsahuje JSON, bridge z něj umí vzít i `username`, `password`, `token` a volitelně `base_url`.
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

- `browse-share-url`: `{ "share_url": "https://.../documentlibrary#/03%20.../Upload?page=1", "provider": "alfresco", "operation": "list|stat|download|copy|move|mkdir|delete|upload", "execute": true, "auth": { ... }, "provider_path_override": "/optional/manual/path", "destination_share_url": "https://...", "destination_path_override": "/target/path", "file_name": "upload.txt", "content_base64": "...", "overwrite": true }`
- `browse-share-url` je canonical endpoint; pro dry-run validaci používej stejný endpoint s `execute=false`.
- V odpovědi je `data.resolved` (výsledek převodu URL), `data.path_source` (`share_url` nebo `provider_path_override`) a `data.result` (výsledek zvolené operace).
- Pro `copy|move` je navíc povinné zadat `destination_path_override` nebo `destination_share_url`; odpověď obsahuje `data.destination`.
- Pro `upload` je povinné `file_name`; cíl lze zadat přes `destination_path_override`/`destination_share_url`, jinak se použije cesta vyřešená ze `share_url`.
- OpenAPI operationId: `bridgeResolveShareUrl`, `bridgeBrowseShareUrl` (canonical), deprecated alias: `bridgeBrowseShareUrlValidateDeprecated`.
- Pokud `execute=false`, endpoint nic neprovede a vrátí dry-run validaci stejnou logikou jako `browse-share-url-validate`.

Lightweight validace bez spuštění operace:

- `browse-share-url-validate`: stejné vstupy jako `browse-share-url`, ale bez `auth` a bez `content_base64`.
- Endpoint vrací vypočtené `source`/`destination` cesty a validační chyby payloadu, bez volání provider operace.
- Interně je to alias na `browse-share-url` s `execute=false` (jedna společná implementační cesta).
- V OpenAPI je endpoint označen jako deprecated; preferovaný endpoint je `browse-share-url` s `execute=false`.

Poznámka k `download` payloadu:

- `/bridge/wfx/download` vrací vždy JSON kontrakt (včetně `ok`, `error_code`, `data`).
- `/bridge/wfx/download-raw` vrací binární stream souboru (`Content-Disposition` + `Content-Type`).
- V `live` režimu JSON `download` vrací `data.content_base64`, `data.mime_type` a `data.size`.
- V `preview` režimu jsou tyto položky `null` a v `data.message` je uveden cílový endpoint.

Poznámka k FSO bezpečnosti:

- FSO provider podporuje omezení lokálních cest přes `allowedRoots` v `config/fso.json`.
- Operace mimo tyto kořeny jsou blokované (`ProviderOperationError`).
- Pro lokální prostředí nastav vlastní absolutní cesty (Windows příklad):

```json
{
  "key": "fso",
  "fso": {
    "allowedRoots": [
      "C:/Users/merhautr/python_projects"
    ]
  }
}
```

Poznámka k výkonu Alfresco:

- Klient obsahuje in-memory cache pro resolve doc library, lookup child node a resolve cesty.
- Opakované volání stejné Alfresco cesty je proto výrazně rychlejší než první cold lookup.

## Runbook

Restart lokalniho serveru:

```powershell
$conn = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 8765 -ErrorAction SilentlyContinue | Where-Object { $_.State -eq 'Listen' }
if ($conn) { Stop-Process -Id $conn.OwningProcess -Force }
.\.venv312\Scripts\python.exe -m uvicorn edocat_bridge.app.server:app --app-dir src --host 127.0.0.1 --port 8765
```

Health check:

```powershell
Invoke-RestMethod -Method Get -Uri http://127.0.0.1:8765/health | ConvertTo-Json -Depth 10
```

Diagnostika, kdy se vraci stale stejny soubor (typicky "welcome.pdf"):

- Ověr, ze volas `POST /bridge/wfx/list` (ne legacy `GET /listing`).
- Ověr format provideru: `provider=edocat`, ne `provider=edocat:`.
- Ověr, ze payload posila spravne `path` s provider prefixem (`edocat:/...` nebo `alfresco:/...`) a `auth`.
- Pokud jde o Alfresco, prvni volani muze byt pomalejsi; druhe opakovane volani by melo byt rychlejsi (cache warm).

## Struktura

Projekt je rozdělen na:

- `app/` API vrstva
- `services/` business logika
- `providers/` implementace providerů
- `clients/` API klienti
- `models/` datové modely
- `core/` konfigurace, logování a utility jádra

## License

Projekt je licencovaný pod MIT licencí. Plný text je v souboru `LICENSE`.
