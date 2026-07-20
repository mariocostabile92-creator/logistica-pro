# Demo Workspace v1

## Scopo

Il Demo Workspace consente di provare il flusso completo della Private Beta
senza file reali. I dati sono deterministici, sintetici e riconoscibili.

La demo non e una modalita alternativa del prodotto. Usa:

```text
Dataset factory
  -> CSV in memoria
  -> parser e mapping attivi
  -> normalizzazione reale
  -> import repository
  -> Fleet Plugin application service
  -> Planning generation service
  -> event simulation/application
  -> Capacity e Readiness
  -> dashboard ed export CSV esistenti
```

Non esistono un secondo Planning Engine, un secondo Fleet Plugin o regole di
assegnazione dedicate alla demo.

## Architettura

Il modulo vive in `backend/app/demo` ed e classificato come supporto
Application/Infrastructure della Private Beta.

```text
backend/app/demo/
  dataset_factory.py  dataset deterministico e validazione
  repository.py       registro centrale e reset selettivo
  router.py           endpoint Private Beta v1
  schemas.py          contratti HTTP tipizzati
  service.py          orchestrazione dei casi d'uso load/status/reset
  settings.py         feature flag
```

Core, Planning, Readiness, Capacity, Amazon Adapter e Fleet Plugin non
dipendono dal modulo demo. Un test architetturale verifica questa direzione.

## Dataset

Versione: `demo_dataset_v1`

Workspace: `private-beta-demo-v1`

Organizzazione: `Demo Logistics Italia`

Operational Unit: `HUB-NORD-01`

Data operativa: `2099-01-15`

Contenuto:

- 10 Task `TASK-DEMO-001` - `TASK-DEMO-010`;
- 12 Human Resource `DRV-DEMO-001` - `DRV-DEMO-012`;
- nomi visualizzati `Demo Driver 01` - `Demo Driver 12`;
- 11 Asset `AST-DEMO-001` - `AST-DEMO-011`;
- identificativi sintetici `DEMO-001` - `DEMO-011`;
- 2 Time Window: `WAVE-DEMO-A` e `WAVE-DEMO-B`;
- 1 Asset indisponibile;
- 1 Asset in riserva;
- 1 assenza Human Resource applicata tramite il servizio eventi;
- capability `large_capacity`, `electric` e `refrigerated`;
- un Task con requisito dichiarato `large_capacity`;
- margine operativo pari a zero con soglia di riserva pari a uno;
- warning `LOW_RESERVE_MARGIN`;
- alternative reali prodotte dal Planning Engine;
- eventi Fleet, documenti sintetici ed evento planning;
- planning completo ed esportabile in CSV.

Il requisito capability e presente nel contratto sintetico e negli Asset del
Fleet Plugin. La v1 del Planning non applica ancora vincoli capability ai Task:
la demo non introduce una regola parallela per simularli.

## Endpoint

- `GET /api/demo/v1/status`
- `POST /api/demo/v1/load`
- `POST /api/demo/v1/reset`

`load` non accetta payload o identificativi scelti dall'utente. La factory
versionata e l'unica fonte del dataset.

Il caricamento e idempotente. Se il workspace e gia `ready` e tutte le entita
registrate esistono, la risposta restituisce lo stesso planning senza creare
duplicati.

Il reset e idempotente. Richiamarlo piu volte restituisce conteggi pari a zero.

## Variabile ambiente

```text
DEMO_WORKSPACE_ENABLED=true|false
```

Comportamento:

- development/test senza variabile: abilitato;
- production senza variabile: disabilitato;
- valore esplicito `true`: abilitato;
- valore assente, falso o non riconosciuto in produzione: disabilitato.

Quando la demo e disabilitata, gli endpoint restituiscono `404` e il frontend
non mostra le card demo.

## Isolamento

Non sono state aggiunte colonne `is_demo` alle tabelle Core, Planning o Fleet.
Esiste un registro centrale `demo_workspaces` con:

- `demo_workspace_id`;
- `dataset_version`;
- `is_demo`;
- stato del workspace;
- `created_at`, `created_by`, `updated_at`, `reset_at`;
- ID import, Asset, Planning e snapshot creati;
- audit minimo delle transizioni;
- summary tipizzata della demo.

Gli altri record hanno marker gia disponibili:

- import: filename deterministico `DEMO__...` e firma esatta degli ID Task o
  delle targhe normalizzate attese;
- Asset: external identifier `AST-DEMO-*` e evento `AssetCreated` con actor
  `demo_workspace_loader`;
- Planning: import sorgente registrati e versione creata con actor demo;
- assignment, eventi e versioni: dipendono dal Planning demo;
- snapshot dashboard: riferisce gli import demo.

Il registro e la fonte primaria. I marker deterministici consentono il recupero
da un arresto tra creazione di un record e aggiornamento del registro. Un
filename uguale ma con contenuto normalizzato diverso non viene considerato
demo e non viene eliminato.

## Reset

Il reset esegue una sola transazione repository per le cancellazioni e usa
soltanto ID registrati o relazioni verso import demo verificati.

Ordine:

1. operation snapshot demo;
2. Planning demo, con cascade su assignment, eventi e versioni;
3. Asset demo, con cascade su documenti ed eventi;
4. import demo;
5. aggiornamento del registro allo stato `reset`.

Configurazioni, Asset non demo, import reali e Planning reali non vengono
toccati. Un test crea dati non demo prima del load e verifica che esistano
ancora dopo il reset.

## Errori e transazioni

I repository esistenti aprono transazioni separate. Per questo il load usa una
strategia compensativa:

1. registra `loading`;
2. aggiorna gli ID dopo ogni passo e usa `partial`;
3. pubblica `ready` solo dopo import, Fleet, Planning, evento e dashboard;
4. in caso di errore elimina le entita demo gia create;
5. registra `failed`;
6. un nuovo load ripulisce eventuali residui e riparte.

Il frontend non considera mai pronto un workspace `loading`, `partial` o
`failed`.

## Procedura locale

PowerShell, dalla cartella `backend`:

```powershell
$env:DEMO_WORKSPACE_ENABLED = "true"
$env:PORT = "8000"
$env:BASE_URL = "http://127.0.0.1:8000"
$env:API_URL = $env:BASE_URL
python -m app.start
```

Caricamento con un solo comando:

```powershell
Invoke-RestMethod -Method Post -Uri "$env:BASE_URL/api/demo/v1/load"
```

Stato:

```powershell
Invoke-RestMethod -Uri "$env:BASE_URL/api/demo/v1/status"
```

Reset:

```powershell
Invoke-RestMethod -Method Post -Uri "$env:BASE_URL/api/demo/v1/reset"
```

La stessa sequenza e disponibile nella UI attraverso `Carica demo`,
`Apri Operations`, `Apri Fleet`, `Esporta CSV` e `Reset demo`.

## Railway

Il deploy non richiede modifiche a `Dockerfile`, `railway.json` o `Procfile`.

Per la Private Beta impostare nel servizio applicativo Railway:

```text
DEMO_WORKSPACE_ENABLED=true
```

Railway esegue un nuovo deploy/restart quando la variabile viene applicata.
Verificare quindi:

1. `GET /api/health`;
2. `GET /api/demo/v1/status`;
3. load, dashboard, Planning, Fleet ed export;
4. reset e ritorno allo stato iniziale.

Per disabilitare la demo impostare `false` o rimuovere la variabile in
produzione.

## Compatibilita database

Il repository usa esclusivamente `db_session`, placeholder `?` tradotti dal
layer database e SQL supportato da SQLite e PostgreSQL. I test coprono SQLite
reale e la traduzione verso `PostgresConnection`.

La suite locale non avvia un'istanza PostgreSQL reale. Prima di promuovere
future modifiche DDL e necessario mantenere lo smoke test Railway PostgreSQL.

## Limiti e rischi

- non esiste multi-tenancy completa;
- il workspace demo e unico per installazione;
- il processo applicativo usa un lock locale; il deploy corrente usa un solo
  processo Uvicorn;
- una analisi legacy creata manualmente durante la demo non ha riferimenti agli
  import e non viene rimossa; il flusso UI demo usa gli snapshot dashboard;
- un Planning aggiuntivo basato sugli import demo viene riconosciuto dalle
  chiavi sorgente e rimosso;
- il Generic File Adapter non esiste ancora: la demo usa l'Adapter tabellare
  attivo attraverso il registry, senza dipendenza diretta da Amazon;
- le capability Task non sono ancora applicate dal Planning v1.

## Evoluzione a demo_dataset_v2

1. aggiungere una nuova factory o versione dichiarativa senza modificare v1;
2. mantenere ID, marker e filename versionati;
3. aggiungere test deterministici per il nuovo shape;
4. definire una migrazione esplicita o richiedere reset v1;
5. aggiornare il contratto summary solo in modo compatibile;
6. verificare load, idempotenza, reset e protezione dati reali;
7. aggiornare questo documento prima di attivare v2 su Railway.
