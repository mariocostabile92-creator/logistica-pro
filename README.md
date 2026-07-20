# Operations Engine

**Release Candidate v1.0 - Private Beta**

Piattaforma modulare per operations last-mile. Importa planning e stato del
parco auto, costruisce una proposta spiegabile driver-rotta-mezzo, consente
correzioni manuali, simulazioni di eccezioni, ricalcolo ed export CSV.

Il vecchio ottimizzatore e il router gratuito non sono usati dal nuovo core e
restano isolati in `backend/app/legacy`.

## Funzioni disponibili

- Import e preview di file `.xlsx`, `.xls` e `.csv`.
- Normalizzazione di driver, targhe, station e stato mezzo.
- Operations Engine con conflitti, capacita e readiness.
- Generazione planning dagli ultimi import o da import selezionati.
- Conservazione delle assegnazioni importate quando sono valide.
- Preferenza per mezzo abituale operativo, poi mezzo libero della stessa
  station, poi mezzo classificato come riserva.
- Alternative ordinate e motivazioni per ogni assegnazione.
- Modifica manuale di driver e mezzo con validazione.
- Conferma e conservazione degli override manuali durante il ricalcolo.
- Simulazione e applicazione di assenza driver, mezzo KO, abort/aggiunta rotta
  e ripristino risorsa.
- Capacita e soglia di riserva per station.
- Suggerimenti cross-station espliciti, mai applicati automaticamente.
- Versioni, eventi applicati e storico modifiche.
- Export CSV del planning operativo.
- Fleet Plugin v1 con registro Asset, capability configurabili, disponibilita
  osservata, metadati documentali e cronologia eventi append-only.
- Configuration Engine v1 con configurazioni organizzative tipizzate,
  versionate, validate e risolte tramite fallback sicuri.
- Amazon Adapter v1 con catalogo alias dichiarativo e mapping tipizzati verso
  Task, Operational Unit, Time Window, Asset e Human Resource.
- Ponte Core Language v1 con value object neutrali e mapper bidirezionali,
  senza rinominare API, database o Planning.
- Schermata Settings in sola consultazione per versione, ambito e sezioni
  effettive.
- Demo Workspace v1 con dataset sintetico deterministico, load e reset
  idempotenti, Planning reale, Fleet, readiness ed export CSV.
- Daily Operations Briefing v1 deterministico con priorità, source references,
  raccomandazioni non distruttive, audit minimo e stato demo derivato.
- Workspace Lifecycle v1 con stati `EMPTY`, `DEMO` e `PRODUCTION`, badge
  globale, reset transazionale auditabile e configurazioni preservate.
- Interfaccia responsive con tabella desktop e card mobile.

## Dati richiesti

Prima di generare un planning devono esistere:

1. un import `planning` con almeno route, driver e station riconoscibili;
2. un import `fleet` con almeno targa, station e stato mezzo riconoscibili.

Sono supportati alias italiani e inglesi, per esempio `route`/`rotta`,
`driver`/`autista`, `plate`/`targa`, `station`/`deposito` e
`status`/`stato`. Colonne con confidenza bassa non sono inventate: la preview
le segnala come mapping da confermare.

La data operativa e facoltativa. Se non viene fornita, il sistema usa il
timestamp dell'import planning e dichiara la fonte in `generation_metadata`.

## Avvio su Windows PowerShell

Dal repository:

```powershell
cd C:\Users\Mario\Desktop\logistica-mvp
```

Creazione e attivazione dell'ambiente virtuale:

```powershell
cd backend
py -m venv venv
.\venv\Scripts\Activate.ps1
```

Installazione dipendenze:

```powershell
python -m pip install -r requirements-dev.txt
```

Avvio backend:

```powershell
$env:PORT = Read-Host "Porta locale"
$env:BASE_URL = "http://127.0.0.1:$env:PORT"
$env:API_URL = $env:BASE_URL
python -m app.start
```

Il backend pubblica anche il frontend. Per aprirlo:

```powershell
Start-Process "$env:BASE_URL/app/"
```

Esecuzione completa dei test:

```powershell
cd C:\Users\Mario\Desktop\logistica-mvp\backend
.\venv\Scripts\python.exe -m pytest -q
```

## Configurazione ambiente

La configurazione applicativa deriva esclusivamente da variabili d'ambiente.
`backend/.env.example` documenta i nomi ammessi e non contiene credenziali.
I file `.env` reali sono ignorati da Git.

| Variabile | Locale | Produzione Railway |
| --- | --- | --- |
| `PORT` | porta libera scelta all'avvio | fornita automaticamente da Railway |
| `APP_ENV` | `development` | `production` |
| `DEBUG` | `false` | `false` |
| `SECRET_KEY` | facoltativa | obbligatoria, almeno 32 caratteri |
| `BASE_URL` | `http://127.0.0.1:8000` | URL HTTPS pubblico |
| `API_URL` | uguale a `BASE_URL` | URL HTTPS pubblico |
| `CORS_ORIGINS` | origini locali separate da virgola | origini HTTPS autorizzate |
| `TRUSTED_HOSTS` | `*` o host locali | dominio pubblico, senza protocollo |
| `DATABASE_URL` | non impostare per SQLite | reference URL del PostgreSQL Railway |
| `OPERATIONS_DB_PATH` | percorso SQLite facoltativo | non impostare con PostgreSQL |
| `LOG_LEVEL` | `INFO` | `INFO` |
| `MAX_UPLOAD_SIZE_MB` | `8` | da `1` a `100`, consigliato `8` |
| `FLEET_PLUGIN_ENABLED` | `true` | `true` |
| `DEMO_WORKSPACE_ENABLED` | `true` o non impostata | `false` se non impostata |

In produzione l'avvio viene interrotto se `DEBUG=true`, se manca
`DATABASE_URL`, se `SECRET_KEY` e assente o troppo corta, oppure se
`CORS_ORIGINS` contiene `*`.

Per generare una chiave senza salvarla nel repository:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Inserire il risultato direttamente nelle variabili Railway e applicare
l'opzione **Seal**. Non inserirlo in file versionati.

## Deploy Railway

Il repository usa un solo servizio applicativo. Il container FastAPI espone
API e frontend sullo stesso dominio; non serve un servizio frontend separato.

File di deploy:

- `Dockerfile`: immagine Python non-root e dipendenze runtime bloccate.
- `.dockerignore`: esclude Git, ambienti virtuali, test, database e secret.
- `railway.json`: build Docker, start command, health check e restart policy.
- `Procfile`: fallback per piattaforme che usano il formato Procfile.

Procedura:

1. Pubblicare il repository su GitHub senza file `.env`.
2. In Railway creare un progetto e collegare il repository.
3. Aggiungere un servizio PostgreSQL.
4. Nel servizio Operations Engine creare `DATABASE_URL` come reference alla
   variabile `DATABASE_URL` del servizio PostgreSQL.
5. Impostare `APP_ENV=production`, `DEBUG=false` e una `SECRET_KEY` sigillata.
6. Impostare `BASE_URL`, `API_URL` e `CORS_ORIGINS` all'URL HTTPS generato da
   Railway.
7. Impostare `TRUSTED_HOSTS` al solo hostname Railway, senza `https://`.
8. Avviare il deploy e verificare `GET /api/health`.
9. Aprire l'applicazione all'indirizzo `https://<dominio>/app/`.

Railway fornisce `PORT`; non deve essere impostata manualmente. Il launcher
`app.start` legge e valida direttamente la variabile, senza dipendere
dall'espansione della shell e senza usare una porta predefinita. La
configurazione usa `/api/health`, timeout 120 secondi, cinque retry e arresto
graduale. Il primo startup crea in modo idempotente le tabelle Core,
Configuration, Fleet, Demo, Daily Operations Briefing e audit Workspace
Lifecycle. Gli startup successivi applicano gli stessi controlli senza
cancellare dati.

### Database

Senza `DATABASE_URL` il progetto usa SQLite e `OPERATIONS_DB_PATH`. Con una
URL `postgres://` o `postgresql://` usa PostgreSQL tramite Psycopg. I
repository e i contratti applicativi restano invariati; il layer
`app/core/database.py` traduce placeholder, identita e righe nel contratto
gia usato dall'applicazione.

I dati presenti in un database SQLite locale non vengono copiati
automaticamente nel PostgreSQL Railway. Per la prima Private Beta si puo
iniziare con un database PostgreSQL vuoto. Un eventuale trasferimento dei dati
locali richiede un'attivita separata con backup e verifica.

### Aggiornamento

1. Eseguire localmente `python -m pytest -q`.
2. Creare un commit e pubblicarlo sul branch collegato a Railway.
3. Verificare build, startup e `/api/health` nei log Railway.
4. Eseguire uno smoke test su `/app/`, import, Planning, Fleet e Settings.

### Rollback

1. Aprire **Deployments** nel servizio Railway.
2. Selezionare l'ultimo deployment stabile.
3. Usare **Redeploy** o **Rollback**.
4. Verificare `/api/health` e `/app/`.

Le inizializzazioni database della Release Candidate sono additive e
idempotenti; il rollback applicativo non elimina tabelle. Prima di futuri
cambi schema distruttivi sara necessario introdurre una procedura di backup e
migrazione versionata.

### Sicurezza credenziali

Le precedenti copie `backend/.env` e `backend/.env.txt` sono state rimosse.
I file legacy `users.json`, `report_consegne.json` e `storico_giri.json`
restano disponibili come liste JSON vuote, senza account, token o dati
operativi personali. Anche il bytecode Python precedentemente tracciato e
stato rimosso.
Poiche erano gia tracciate, la stringa di connessione puo essere ancora
presente nella cronologia Git: la relativa credenziale deve essere ruotata
prima di pubblicare il repository. La sola rimozione dal branch corrente non
revoca una credenziale esposta.

## API import e operations

- `GET /api/health`
- `POST /api/imports/preview`
- `POST /api/imports/planning`
- `POST /api/imports/fleet`
- `POST /api/operations/analyze`
- `GET /api/operations/latest`
- `GET /api/operations/dashboard`
- `GET /api/operations/issues`
- `GET /api/operations/capacity`
- `GET /api/operations/readiness`

## Workspace Lifecycle v1

Il backend espone lo stato operativo corrente e impedisce nuovi workspace con
dati demo e reali mescolati.

- `GET /api/workspace/v1/status`
- `POST /api/workspace/v1/reset`

Il reset rimuove import, Planning, Assignment, eventi, snapshot, analisi,
Briefing, Asset e registro demo in una transazione. Le versioni del
Configuration Engine non vengono eliminate. Un workspace gia vuoto restituisce
successo con conteggi a zero.

Stati, ordine di cancellazione, audit, rollback, concorrenza e procedura
Railway sono descritti in
[`WORKSPACE_LIFECYCLE.md`](WORKSPACE_LIFECYCLE.md).

## Demo Workspace v1

La demo usa le pipeline reali e non viene caricata automaticamente. In locale
e abilitata per default; in produzione richiede:

```text
DEMO_WORKSPACE_ENABLED=true
```

Endpoint:

- `GET /api/demo/v1/status`
- `POST /api/demo/v1/load`
- `POST /api/demo/v1/reset`

Caricamento locale con un solo comando:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "$env:BASE_URL/api/demo/v1/load"
```

La strategia di isolamento, il dataset `demo_dataset_v1`, la delega al reset
globale e la procedura Railway sono descritti in
[`DEMO_WORKSPACE.md`](DEMO_WORKSPACE.md).

## Daily Operations Briefing v1

Il briefing operativo legge Planning, Assignment, conflitti, alternative,
Readiness, Capacity, Asset, eventi e configurazione già disponibili. Non
ricalcola i motori esistenti, non applica raccomandazioni e non usa provider
AI.

Endpoint:

- `GET /api/briefing/v1/daily/latest`
- `POST /api/briefing/v1/daily/generate`

Senza Planning `GET latest` restituisce HTTP 200 con stato tipizzato
`unavailable`. La generazione è idempotente: fonti invariate restituiscono lo
stesso briefing; una modifica reale crea una nuova revisione.

Modelli, ranking, source references, persistenza, comportamento demo e limiti
sono descritti in
[`DAILY_OPERATIONS_BRIEFING.md`](DAILY_OPERATIONS_BRIEFING.md).

## API planning

- `POST /api/planning/generate`
- `GET /api/planning/latest`
- `GET /api/planning/{planning_id}`
- `PATCH /api/planning/assignments/{assignment_id}`
- `POST /api/planning/{planning_id}/recalculate`
- `POST /api/planning/{planning_id}/simulate-event`
- `POST /api/planning/{planning_id}/apply-event`
- `GET /api/planning/{planning_id}/history`
- `GET /api/planning/{planning_id}/export?format=csv`

## API Fleet Plugin v1

Il Plugin usa il concetto neutrale di `Asset`. `plate` rimane facoltativo per
la compatibilita con i veicoli. Il Plugin non modifica planning, assegnazioni,
readiness o capacity.

- `GET /api/plugins/fleet/v1/assets`
- `POST /api/plugins/fleet/v1/assets`
- `GET /api/plugins/fleet/v1/assets/{asset_id}`
- `PATCH /api/plugins/fleet/v1/assets/{asset_id}`
- `POST /api/plugins/fleet/v1/assets/{asset_id}/availability`
- `POST /api/plugins/fleet/v1/assets/{asset_id}/documents`
- `GET /api/plugins/fleet/v1/assets/{asset_id}/events`

Per disabilitare il Plugin prima dell'avvio:

```powershell
$env:FLEET_PLUGIN_ENABLED = "false"
```

Gli interventi, le notifiche, i fornitori e le regole sulle scadenze sono
esclusi: appartengono al futuro Maintenance Plugin.

## API Configuration Engine v1

Il Configuration Engine e un servizio Core. Applica in ordine deterministico
i default sicuri della piattaforma, la configurazione dell'organizzazione,
quella dell'Operational Unit e gli ambiti generici preparati per sorgenti
future. Ogni valore espone la propria provenienza.

- `GET /api/configuration/v1/current`
- `GET /api/configuration/v1/versions`
- `POST /api/configuration/v1/validate`
- `POST /api/configuration/v1/versions`

La schermata Settings usa esclusivamente `GET /current` e non consente
modifiche. Le revisioni persistite sono immutabili: una modifica crea sempre
una nuova versione.

## Amazon Adapter v1

L'Adapter Amazon e il confine inbound attivo per gli import correnti. Separa
alias e vocabolario Amazon dal normalizzatore generico senza modificare API,
Planning o Fleet Plugin.

Il catalogo dichiarativo vive in
`backend/app/adapters/amazon/catalog.v1.json`. Gli alias organizzativi possono
essere estesi attraverso il Configuration Engine nello scope
`adapter_id = amazon`.

Responsabilita, mapping, esempi e limiti sono descritti in
[`AMAZON_ADAPTER.md`](AMAZON_ADAPTER.md).

## Core Language Migration

La prima migrazione interna introduce `Task`, `OperationalUnit`,
`HumanResource`, `AssetReference`, `TimeWindow`, `TaskCancellationEvent` e
`ResourceAvailability`. Route, station, driver, vehicle e cycle restano
disponibili attraverso mapper bidirezionali di compatibilita'.

Stato, componenti migrati e strategia futura sono descritti in
[`CORE_LANGUAGE_MIGRATION.md`](CORE_LANGUAGE_MIGRATION.md).

### Generare un planning

Gli ID sono facoltativi. Se assenti, vengono usati gli ultimi import
compatibili.

```powershell
$body = @{
  operation_date = "2026-07-20"
  configuration = @{
    reserve_vehicle_threshold_global = 1
    reserve_vehicle_threshold_by_station = @{
      DLO1 = 2
      DLO2 = 1
    }
    prefer_habitual_vehicle = $true
    preserve_imported_assignment = $true
    preserve_confirmed_manual_override = $true
    allow_cross_station_suggestion = $true
    maximum_assignments_per_driver = 1
    maximum_alternatives_per_assignment = 3
  }
} | ConvertTo-Json -Depth 6

$planning = Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/api/planning/generate `
  -Method Post `
  -ContentType "application/json" `
  -Body $body

$planning.planning.id
```

Per una sola station aggiungere `station = "DLO1"` al body.

### Modificare e confermare un'assegnazione

```powershell
$planningId = $planning.planning.id
$assignmentId = $planning.assignments[0].id

$patch = @{
  driver_id = "driver-01"
  driver_name = "Driver 01"
  plate = "AA001AA"
  confirm = $true
  manual_override = $true
  note = "Sostituzione confermata dal responsabile"
  actor = "local_operator"
} | ConvertTo-Json

Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/api/planning/assignments/$assignmentId" `
  -Method Patch `
  -ContentType "application/json" `
  -Body $patch
```

Per rimuovere una risorsa usare `remove_driver = $true` oppure
`remove_vehicle = $true`. Il backend rifiuta duplicazioni, mezzi bloccati,
station incompatibili e targhe non valide.

### Simulare e applicare un evento

La simulazione non modifica il planning.

```powershell
$event = @{
  event_type = "vehicle_unavailable"
  entity_type = "vehicle"
  entity_id = "AA001AA"
  reason = "Mezzo fermo prima del loadout"
  actor = "local_operator"
} | ConvertTo-Json

$simulation = Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/api/planning/$planningId/simulate-event" `
  -Method Post `
  -ContentType "application/json" `
  -Body $event

$simulation.diff
```

Applicazione esplicita dello stesso evento:

```powershell
$applied = Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/api/planning/$planningId/apply-event" `
  -Method Post `
  -ContentType "application/json" `
  -Body $event

$applied.version
```

Tipi simulabili: `driver_absent`, `vehicle_unavailable`, `route_aborted`,
`route_added`, `driver_restored`, `vehicle_restored`.

### Ricalcolo, storico ed export

Il ricalcolo conserva assegnazioni confermate valide e override manuali
confermati.

```powershell
$recalculated = Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/api/planning/$planningId/recalculate" `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"actor":"local_operator"}'

$history = Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/api/planning/$planningId/history"

Invoke-WebRequest `
  -Uri "http://127.0.0.1:8000/api/planning/$planningId/export?format=csv" `
  -OutFile ".\planning-operativo-$planningId.csv"
```

## Modello operativo

Il planning mantiene ID degli import sorgente, data, station opzionale, stato,
versione, soglia di riserva, configurazione e timestamp. Gli stati previsti
sono `draft`, `generated`, `partially_assigned`, `ready`, `critical`,
`confirmed` e `superseded`.

Ogni assegnazione include rotta, cycle/wave, driver, mezzo, stato, origine,
confidenza, motivi, dati usati, warning, alternative, note, flag di override e
conferma. Le origini includono assegnazione importata, mezzo abituale, mezzo
libero, riserva, modifica manuale, fallback e ricalcolo.

## Capacita per station

Per ogni station vengono calcolati rotte, driver disponibili/assegnati/liberi,
mezzi fisici/operativi/assegnati/liberi/bloccati, riserva sicura, deficit o
surplus e margine operativo:

```text
margine operativo = mezzi operativi - rotte attive
```

Il rischio e `critical` se mancano mezzi o driver, `high` con margine zero,
`medium` sotto la soglia di riserva e `low` quando capacita e riserva sono
conformi.

## Fixture realistiche

`backend/tests/fixtures/realistic_planning.csv` e
`backend/tests/fixtures/realistic_fleet.csv` rappresentano 20 rotte, 22
driver, 24 mezzi, due station, mezzi abituali, officina, blocco, targa non
valida, deficit, riserva sotto soglia e surplus. I test aggiungono anche
assenza driver e abort di rotta.

Nel repository non sono presenti file reali `.xlsx`, `.xls` o `.csv` diversi
dalle fixture sintetiche. Nessun dato personale reale viene distribuito.

## Limiti reali

- Non esiste ancora un'anagrafica driver separata: disponibilita e abbinamenti
  derivano dagli import normalizzati.
- La compatibilita data dipende dalla data richiesta o dal timestamp import,
  perche i file senza una colonna data non permettono verifiche piu precise.
- Station, stato mezzo e assegnazione abituale richiedono mapping manuale
  quando la confidenza degli alias e bassa.
- Un mezzo con stato non riconosciuto resta bloccante finche il dato non viene
  corretto o confermato tramite una futura funzione dedicata.
- I trasferimenti cross-station sono solo suggerimenti.
- Il comando frontend "conferma valide" esegue conferme singole; non e una
  transazione batch.
- L'actor e locale e generico: autenticazione e ruoli non fanno parte di
  questa fase.
- Il lock Workspace Reset e locale al processo. Il deploy corrente usa un
  solo processo; piu repliche richiederebbero un lock transazionale condiviso.
- L'export disponibile e CSV; non e presente un export XLSX.

## Esclusioni intenzionali

Non sono inclusi gestione officine completa, manutenzione predittiva, sinistri,
assicurazioni, fotografie, AI damage detection, GPS, tracking driver,
monitoraggio consegne, payroll, turnistica HR completa, scorecard, WhatsApp,
notifiche push, multi-tenancy avanzata, dashboard economica, integrazioni
Amazon dirette, navigazione, ottimizzazione percorsi, chatbot o AI generativa.
