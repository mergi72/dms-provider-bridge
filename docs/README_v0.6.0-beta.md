# dms-provider-bridge v0.6.0-beta - návrh architektury konfigurace

Tento dokument popisuje plánovaný refaktor konfigurace pro `v0.6.0-beta`.

`v0.5.0-beta` je stabilní funkční baseline. Do ní nepatří velké změny provider registry, WFX kontraktu ani installer logiky. `v0.6.0-beta` je samostatný krok pro konfigurátor, provider instance a čistší abstrakci providerů.

## Cíl

Cílem je doplnit uživatelsky použitelný konfigurátor bridge bez rozbití stávající runtime logiky.

Konfigurátor má umožnit:

- upravit konfiguraci bridge přes `bridge.local.json`,
- upravit konfiguraci providerů přes `<provider_name>.local.json`,
- zakládat a upravovat konkrétní provider instance,
- testovat připojení jednorázovým user/password bez uložení hesla,
- reloadnout konfiguraci bez restartu služby, pokud to bridge umožní.

## Stabilní baseline v0.5.0-beta

`v0.5.0-beta` necháváme jako stabilní funkční verzi:

- Total Commander WFX plugin,
- bridge runtime API,
- Credential Broker,
- hlavní installer,
- provider-to-provider copy/move,
- version-aware upload/copy/move,
- lokalizace dialogů,
- CI a release balíčky.

Do `v0.5.0-beta` patří už jen minimální bugfixy. Větší architektonické změny jdou do `v0.6.0-beta`.

## Základní pravidla

- Nehrabat se zbytečně do staré funkční runtime logiky.
- Nejdřív analýza, potom diskuze, potom úpravy.
- WFX zůstává hloupý klient.
- Broker zůstává vlastník uložených credentials.
- Bridge zůstává vlastník provider konfigurace a provider registry.
- Obecné machine configy se nikdy needitují přes UI/API.
- Každý update konfigurace vytváří nebo upravuje pouze `*.local.json`.

## Finální slovník architektury

Pro `v0.6.0-beta` používáme tyto pojmy:

```text
DMS Provider Bridge
Provider ABC
Driver
Connection
```

Význam vrstev:

```text
DMS Provider Bridge
  celá lokální služba a hostitel architektury

Provider ABC
  společný základ a abstraktní kontrakt
  definuje povinné runtime operace
  definuje společný konfigurační základ

Driver
  konkrétní implementace jednoho typu DMS
  vychází z Provider ABC
  může rozšířit základní config o vlastní special klíče
  může rozšířit capabilities podle možností konkrétního systému

Connection
  konkrétní pojmenované připojení
  používá jeden driver
  nese konkrétní local config
  jde ven do WFX/API a používá ho uživatel
```

Krátká definice:

```text
Provider ABC říká, co musí umět každý DMS provider.
Driver říká, jak se mluví s konkrétním DMS.
Connection říká, kam se konkrétní uživatel připojuje.
```

Příklad:

```text
DMS Provider Bridge
├─ Provider ABC
├─ Driver: alfresco
│  ├─ Connection: alfresco
│  ├─ Connection: moje_alfresco
│  └─ Connection: test_alfresco
└─ Driver: edocat
   ├─ Connection: edocat
   └─ Connection: chem_edocat
```

Pravidlo proti budoucímu zmatku:

```text
Provider ABC není Driver.
Driver není Connection.
Connection je to, co vidí uživatel ve WFX.
```

## Hlavní mentální model: jsme mount

`DMS Provider Bridge` není framework pro vývojáře. Je to runtime, který vystavuje DMS systémy jako pojmenované mounty.

Unix/VFS model:

```text
application
  -> mount point
  -> VFS operations
  -> filesystem driver
```

Náš model:

```text
Total Commander / user application
  -> connection:/
  -> Provider ABC operations
  -> Driver
  -> DMS
```

Mapování pojmů:

```text
Provider ABC = ops kontrakt
Driver       = filesystem/DMS driver
Connection   = mount instance
```

Venku existuje jen runtime kontrakt:

```text
connection:/path
```

Příklad:

```text
moje_alfresco:/03 zakázky/Test_DMS/file.pdf
chem_edocat:/03 zakázky/Test_DMS/file.pdf
```

User application neřeší driver, config schema, credentials internals ani provider speciality. User application zná jen connection name a runtime operace.

Pravda pro pozdější implementaci:

```text
resolve connection
find driver
call ops
```

Žádná magie navíc.

## Config layout podle Unix/VFS

Fyzické rozložení config šablon:

```text
config/
  provider.json
  provider.local.json

  drivers/
    driver.json
    alfresco.json
    edocat.json

  connections/
    connection.json
```

Význam:

```text
provider.json
  jeden globální skrytý Provider ABC / VFS contract

provider.local.json
  volitelný advanced override Provider ABC contractu

drivers/
  filesystem driver definitions

connections/
  mount definitions
```

Poznámka k odladěným limitům z `v0.5.0-beta`:

```json
{
  "upload": {
    "raw": {
      "chunkBytes": 1048576,
      "maxBytes": 536870912
    }
  }
}
```

Ve slepé `driver.json` šabloně jsou tyto hodnoty `0`. Konkrétní driver je může použít jako rozumný výchozí limit, pokud pro něj dávají smysl.

Uživatel běžně řeší jen:

```text
drivers
connections
```

`provider.json` je interní základ bridge. AOS ho může ukázat read-only. Pokud bude existovat `provider.local.json`, AOS ho může editovat jen jako advanced local override, nikdy nesmí zapisovat do `provider.json`.

Driver special nastavení:

```text
Provider ABC dá společný základ.
Driver k němu přidá svoje rozšíření.
Connection vyplní konkrétní hodnoty.
```

## Provider ABC a provider.json

`provider.json` je obecný základ Provider ABC. Není to konfigurace konkrétního DMS a nesmí obsahovat názvy konkrétních implementací.

`provider.json` definuje:

```text
operations
transfer
capabilities
config
```

Význam:

```text
operations
  obecné funkce, které Provider ABC zná

transfer
  obecné mantinely přenosu souborů

capabilities
  obecný tvar volitelných schopností

config
  společný konfigurační základ
```

Obecné funkce musí být definované v ABC:

```text
list
stat
download
upload
copy
move
delete
mkdir
```

Tyto funkce nejsou seznam konkrétních implementací. Jsou to operace, které tvoří společný jazyk bridge.

Transfer mantinely patří do ABC:

```json
{
    "transfer": {
        "maxInlineBytes": 10485760,
        "maxBase64Bytes": 314572800,
        "preferStream": true,
        "tempFallback": true
    }
}
```

Význam:

```text
maxInlineBytes
  hranice pro malý inline přenos

maxBase64Bytes
  horní mantinel pro base64 fallback

preferStream
  preferovat stream, pokud ho implementace umí

tempFallback
  povolit fallback přes dočasný soubor
```

Pravidlo:

```text
Co je obecná DMS operace, patří do ABC.
Co je zvláštní pro konkrétní systém, patří do implementace.
Co je konkrétní adresa nebo hodnota, patří do connection.
```

## Dva druhy konfigurace

Konfigurace se dělí na dvě hlavní oblasti.

### 1. Bridge config

Bridge config odpovídá:

```text
%ProgramData%\DMS Provider\config\bridge.json
%APPDATA%\DMS Provider\config\bridge.local.json
```

`bridge.json` je obecný machine/base config a je read-only.

Uživatelské změny se zapisují pouze do:

```text
bridge.local.json
```

Typické položky:

- default provider,
- upload raw limity,
- debug/log nastavení,
- temp nastavení,
- server/runtime nastavení, pokud je bezpečné je měnit za běhu.

### 2. Provider config

Provider config odpovídá:

```text
%ProgramData%\DMS Provider\config\<provider>.json
%APPDATA%\DMS Provider\config\<provider_name>.local.json
```

Machine provider config je base/template a needituje se přes konfigurátor.

Uživatelské změny nebo nové connection instance se zapisují pouze jako local config.

## Provider model

Dnes je pojem provider částečně smíchaný:

```text
provider class
provider config
provider viditelný ve WFX
```

Pro `v0.6.0-beta` chceme tyto vrstvy oddělit.

### 1. Provider ABC

Provider ABC je abstraktní kontrakt.

Obsahuje základní runtime schopnosti:

- list,
- stat,
- download,
- upload,
- copy,
- move/rename,
- delete,
- mkdir,
- share URL capability,
- versioning capability.

Pro konfigurátor bude Provider ABC navíc poskytovat základní konfigurační kontrakt:

- základní local config template,
- validaci local configu,
- popis editovatelných polí, pokud bude později potřeba formulář,
- test connection,
- označení citlivých hodnot, které se nesmí logovat ani vracet.

Základní provider template z ABC by měl obsahovat společné položky:

```json
{
    "base_url": "https://your-dms.example/base-url",
    "timeouts": {
        "requestSeconds": 60,
        "downloadSeconds": 300,
        "uploadSeconds": 7200
    },
    "debug": {
        "enable": false,
        "path": "%APPDATA%\\DMS Provider\\logs"
    }
}
```

### 2. Provider type / driver

Provider type je konkrétní implementace nebo driver:

```text
alfresco
edocat
webdav
sharepoint
```

Je to podobné jako ODBC driver.

Provider type ví:

- jaké API používá,
- jaké endpointy potřebuje,
- jak funguje versioning,
- jak se mapují cesty,
- jak se dělá test connection,
- jaké provider-specific položky patří do local configu.

Provider type může rozšířit základní ABC template o svoje položky.

Například Alfresco:

```json
{
    "doc_library": "/app:company_home/st:sites/cm:deals/cm:documentLibrary",
    "api": {
        "search_root": "/api/-default-/public/search/versions/1",
        "repo_root": "/api/-default-/public/alfresco/versions/1"
    }
}
```

Například eDoCat:

```json
{
    "api": "/edocat/api/v1",
    "doc_library": "/deals",
    "nodeType": {
        "baseFolder": "com.onlio.edocat.BaseFolder",
        "baseDoc": "com.onlio.edocat.BaseDoc",
        "file": "com.onlio.edocat.File"
    }
}
```

### 3. Provider name / connection instance

Provider name je konkrétní spojení/instance viditelná ve WFX:

```text
alfresco1
moje_alfresco
cheminvest_edocat
test_alfresco
```

Tohle se bude objevovat v:

```text
/bridge/wfx/providers
```

A v Total Commanderu jako root:

```text
\moje_alfresco
\cheminvest_edocat
```

Runtime cesta:

```text
moje_alfresco:/folder/file.pdf
```

Bridge resolver:

```text
provider.name -> provider.type -> Provider class -> provider config
```

## Doporučený tvar provider instance local JSON

Nová instance by měla mít jasný `key` a `type`.

Příklad:

```json
{
    "key": "moje_alfresco",
    "type": "alfresco",
    "moje_alfresco": {
        "base_url": "https://firma.example/alfresco",
        "doc_library": "/app:company_home/st:sites/cm:deals/cm:documentLibrary",
        "timeouts": {
            "requestSeconds": 60,
            "downloadSeconds": 300,
            "uploadSeconds": 7200
        },
        "debug": {
            "enable": false,
            "path": "%APPDATA%\\DMS Provider\\logs"
        }
    }
}
```

Význam:

```text
key  = název connection instance
type = provider driver / implementace
```

## Zpětná kompatibilita

Stávající konfigurace musí dál fungovat:

```text
alfresco:/...
edocat:/...
```

Dnešní soubory:

```text
alfresco.json
edocat.json
```

lze chápat jako legacy instance:

```text
key = alfresco
type = alfresco

key = edocat
type = edocat
```

Tím se zachová kompatibilita s existující WFX konfigurací a testy.

## /bridge/wfx/providers

Dnes `/bridge/wfx/providers` vrací provider typy podle machine configu.

Po refaktoru má vracet provider instance:

```json
{
    "providers": [
        "alfresco",
        "edocat",
        "moje_alfresco",
        "cheminvest_edocat"
    ]
}
```

WFX nemusí vědět, jestli provider root reprezentuje Alfresco, eDoCat nebo WebDAV. WFX jen zobrazí názvy, které vrátí bridge.

## Config UI

Konfigurátor bude dostupný na:

```text
http://127.0.0.1:8765/config
```

Je to uživatelská stránka podobná Swagger `/docs`, ale zaměřená jen na konfiguraci.

Pro první verzi nebude formulář po jednotlivých polích. Bude to JSON editor v textovém okně.

Princip:

```text
Bridge config
  textarea s bridge.local.json
  Save
  Delete local
  Reload

Providers
  výběr provider instance
  textarea s <provider_name>.local.json
  Save
  Delete local
  Reload
  Test connection
```

Výhody:

- nemusíme hardcodovat provider-specific pole do UI,
- provider speciality zůstanou v JSONu,
- admin vidí přesně, co se ukládá,
- je to podobné `/docs`, ale jednodušší pro konfiguraci.

## Config API

API nemá zbytečně opakovat názvy v cestě.

UI:

```text
GET /config
```

API:

```text
GET    /bridge/config
PUT    /bridge/config/local
DELETE /bridge/config/local

GET    /bridge/config/providers
GET    /bridge/config/providers/{provider_name}
PUT    /bridge/config/providers/{provider_name}/local
DELETE /bridge/config/providers/{provider_name}/local
POST   /bridge/config/providers/{provider_name}/test
```

`PUT` a `DELETE` endpointy vždy pracují jen s `*.local.json`.

Endpointy typu:

```text
PUT /bridge/config
PUT /bridge/config/providers/{provider_name}
```

nechceme, protože by to mohlo vypadat jako editace machine/base configu.

## Hesla a credentials

Runtime režim TC/WFX:

```text
WFX -> bridge -> broker -> Windows Credential Manager
```

Tady dál platí credentials target/credential_id přes broker.

Config UI/AOS režim:

- nepoužívá credentials_id,
- pro test connection přijme přímo username/password,
- heslo použije jen jednorázově pro test,
- heslo se nikdy neuloží do JSONu,
- heslo se nikdy nevrátí v response,
- heslo se nikdy neloguje.

Pro test lze použít existující auth model:

```json
{
    "mode": "credentials",
    "username": "user",
    "password": "pass"
}
```

`BridgeAuthContext` to dnes podporuje, takže není potřeba měnit auth kontrakt jen kvůli konfigurátoru.

## Reload konfigurace

Po uložení local configu:

```text
1. uložit *.local.json
2. reloadnout provider cache
3. vrátit výsledek
```

Dnes už existuje:

```python
reload_provider_cache()
```

Pokud to bude stačit, není nutné restartovat bridge službu.

## Co neměnit bez samostatné diskuze

- WFX request/response runtime kontrakt.
- Credential Broker runtime flow.
- Provider upload/download/copy/move logiku.
- Versioning chování.
- Installer orchestrace.
- Machine/base config zápis.

Pokud bude nutná změna některé staré logiky, nejdřív analýza a diskuze.

## Postup implementace

Navržený postup pro `v0.6.0-beta`:

1. Dokumentace a finální odsouhlasení tohoto modelu.
2. Provider registry refaktor:
   - oddělit provider type/driver od provider name/instance,
   - zachovat legacy `alfresco` a `edocat`,
   - cache podle provider instance.
3. Provider ABC config kontrakt:
   - base template,
   - provider-specific template,
   - validace,
   - test connection.
4. Config loader rozšíření:
   - číst legacy machine configy,
   - číst nové provider instance local configy,
   - nikdy needitovat machine config.
5. Config API:
   - bridge local,
   - provider local,
   - provider test.
6. `/config` HTML UI:
   - JSON textarea,
   - save/delete/reload/test,
   - výpis výsledku jako JSON.
7. Testy:
   - legacy kompatibilita,
   - nové instance,
   - local-only zápis,
   - žádné ukládání hesel,
   - provider cache reload.

## Otevřené otázky

- Přesný fyzický layout nových provider instance souborů.
- Jestli nové instance ukládat přímo jako `<provider_name>.local.json` v user config rootu, nebo později zavést podadresář.
- Jak přesně zobrazit legacy providery v `/config`.
- Jaký minimální test connection použít pro každý provider.
- Jestli provider-specific template bude jen dict, nebo i jednoduché schema pro budoucí formuláře.
