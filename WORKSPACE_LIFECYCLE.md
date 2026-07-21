# Workspace Lifecycle v1

## Scopo

Workspace Lifecycle e un servizio Core che rende esplicito il contesto
operativo corrente e ne governa il ripristino. Il backend e la fonte della
verita: il frontend visualizza lo stato ricevuto e non lo ricostruisce.

Il servizio distingue un workspace vuoto, demo o di produzione, impedisce
nuovi workspace con dati demo e reali mescolati e rimuove in modo atomico i
dati operativi preservando Configuration Engine e impostazioni applicative.

Workspace Lifecycle non modifica Planning, Decision Engine, Readiness,
Capacity, Fleet Plugin, Configuration Engine o Amazon Adapter.

## Stati

| Stato | Significato |
| --- | --- |
| `EMPTY` | Nessun import, Planning, Asset operativo, snapshot, analisi o Briefing. |
| `DEMO` | Esiste un registro demo attivo e tutti i dati operativi sono riconducibili alla sua provenienza persistita. |
| `PRODUCTION` | Esiste almeno un dato operativo non appartenente alla demo. |

Un registro demo `loading`, `partial` o `ready` e attivo. I record `reset` e
`failed` non rendono il workspace `DEMO` in assenza di dati operativi.

## Determinazione dello stato

`backend/app/workspace/status_service.py` coordina l'inventario prodotto dal
repository. La provenienza demo deriva da:

- ID import registrati in `demo_workspaces.metadata`;
- Planning collegati agli import demo;
- snapshot collegati agli import demo;
- Asset registrati nel metadata demo;
- Briefing collegati ai Planning demo o marcati `is_demo`.

Il nome del file non viene usato per classificare un record come reale o
demo. Le firme e i filename deterministici restano esclusivamente un
meccanismo di recupero del loader demo in caso di interruzione parziale.

Se un workspace storico contiene contemporaneamente record demo e non demo,
lo stato esposto e `PRODUCTION` con `mixed_data_detected=true`. I dati non
vengono modificati automaticamente.

I contatori esposti sono:

- Task: righe normalizzate dell'ultimo import Planning;
- Asset: massimo tra Asset persistiti e righe dell'ultimo import Fleet;
- Workforce: membri persistiti nel Workforce Plugin;
- Planning: righe nella tabella `plannings`;
- Briefing: righe nella tabella `daily_briefings`.

## Regole Demo e Produzione

I nuovi flussi applicano queste transizioni:

```text
EMPTY -> DEMO
DEMO -> RESET -> EMPTY
EMPTY -> PRODUCTION
PRODUCTION -> RESET -> EMPTY
```

Non sono consentiti nuovi flussi `DEMO + PRODUCTION`:

- un import reale in stato `DEMO` restituisce HTTP `409`;
- la creazione manuale di un nuovo Asset in stato `DEMO` restituisce HTTP
  `409`;
- il caricamento demo in stato `PRODUCTION` restituisce HTTP `409`.

Preview, letture e operazioni sui dati gia presenti non cambiano.

## Endpoint

### GET `/api/workspace/v1/status`

Restituisce `WorkspaceStatusResponse` con stato, provenienza demo, ultimi
import, conteggi, ultimo aggiornamento e azioni contestuali.

### POST `/api/workspace/v1/reset`

Non richiede payload nella Private Beta. L'actor audit e
`system/private-beta`. Restituisce `reset_id`, stato finale `EMPTY`, esito
idempotente, messaggio tipizzato, conteggi rimossi e timestamp.

Un workspace gia vuoto restituisce HTTP `200`,
`workspace_already_empty` e conteggi tutti a zero.

## Audit delle tabelle

### Dati operativi rimossi

| Ordine | Tabella | Contenuto |
| --- | --- | --- |
| 1 | `daily_briefings` | Briefing persistiti. |
| 2 | `planning_events` | Eventi e simulazioni applicate. |
| 3 | `planning_versions` | Versioni e change payload. |
| 4 | `assignments` | Assegnazioni del Planning. |
| 5 | `plannings` | Planning e riepiloghi persistiti. |
| 6 | `operation_snapshots` | Snapshot dashboard, Capacity e Readiness derivate. |
| 7 | `analyses` | Analisi legacy ancora usate dalle API compatibili. |
| 8 | `workforce_changes` | Audit Workforce. |
| 9 | `workforce_day_statuses` | Calendario e disponibilita. |
| 10 | `workforce_requirements` | Fabbisogno Workforce. |
| 11 | `workforce_members` | Anagrafica Workforce. |
| 12 | `workforce_imports` | Fingerprint e riepiloghi import Workforce. |
| 13 | `fleet_asset_documents` | Metadati documentali Asset. |
| 14 | `fleet_sync_event_fingerprints` | Idempotenza eventi Fleet. |
| 15 | `fleet_asset_events` | Cronologia eventi Asset. |
| 16 | `fleet_sync_runs` | Conferme e riepiloghi sincronizzazione. |
| 17 | `fleet_asset_metadata` | Associazioni e provenienza osservata. |
| 18 | `fleet_assets` | Registry Asset operativo. |
| 19 | `imports` | Mapping e righe normalizzate Planning/Fleet. |
| 20 | `demo_workspaces` | Registro, riferimenti e metadata demo. |

L'ordine elimina prima i record dipendenti e poi le radici. Le foreign key
con cascade restano una protezione aggiuntiva, non l'unico meccanismo.

### Dati preservati

- `configuration_versions`;
- `workspace_reset_audits`;
- default e fallback del Configuration Engine;
- nomenclature, capability, policy, priorita e mapping;
- configurazione di processo e Railway;
- mapping e policy `workforce_statuses`, `workforce_shift_codes` e
  `fleet_registry`;
- codice e struttura di Core, Adapter e Plugin.

Le tabelle `users`, `routes_history` e `delivery_reports` appartengono al
database legacy isolato in `backend/app/legacy/database_legacy.py`. Non sono
inizializzate dall'applicazione corrente e non vengono cancellate
automaticamente.

## Transazione e rollback

Tutte le cancellazioni operative vengono eseguite dentro una singola
`db_session`. La stessa implementazione usa SQLite in locale e PostgreSQL
tramite `PostgresConnection` su Railway.

Se una cancellazione o la verifica finale fallisce:

1. `db_session` esegue rollback;
2. il workspace operativo resta invariato;
3. l'API restituisce `WORKSPACE_RESET_FAILED`;
4. l'errore tecnico non viene esposto al frontend;
5. l'audit registra `failed` e `workspace_reset_failed`.

L'audit di avvio e completamento usa transazioni separate: deve sopravvivere
al rollback dei dati, ma non contiene copie dei record eliminati.

## Audit reset

La tabella `workspace_reset_audits` conserva soltanto:

- `reset_id`;
- `started_at` e `completed_at`;
- `actor`;
- stato precedente e finale;
- conteggi rimossi;
- esito;
- errore sanitizzato.

Non conserva payload, file, righe importate o dati personali.

## Concorrenza

Un lock backend non bloccante impedisce due reset contemporanei nello stesso
processo. Il secondo tentativo restituisce HTTP `409` con
`WORKSPACE_RESET_IN_PROGRESS`.

Limite v1: il lock non e distribuito tra piu processi o repliche. Il deploy
Railway corrente usa un solo processo Uvicorn. Prima di aumentare repliche o
worker sara necessario introdurre un lock transazionale PostgreSQL o una
strategia equivalente. Redis non e richiesto dalla v1.

## Integrazione Demo Workspace

`POST /api/demo/v1/reset` resta disponibile per compatibilita. Quando il
workspace e `DEMO`, delega al reset globale e adatta la risposta al contratto
demo esistente.

Per un eventuale workspace storico gia misto, il vecchio endpoint mantiene
una procedura di bonifica selettiva compatibile, senza cancellare dati reali.
Questo percorso non puo essere creato dai nuovi entry point ed e un rimedio
legacy, non una modalita supportata.

Il reset globale elimina il registro demo; lo status demo successivo e
`no_demo`.

## UI

L'header mostra sempre `Workspace vuoto`, `Workspace demo` oppure
`Workspace produzione`. Il colore e solo un rinforzo semantico. Il menu
compatto espone azioni coerenti con lo stato e la Home mostra una card
`Workspace corrente` con soli dati disponibili.

I flussi import sono:

- `EMPTY`: apertura diretta della sezione import;
- `DEMO`: dialog informativo, poi `Rimuovi demo e continua`;
- `PRODUCTION`: scelta tra continuare nel workspace o ripristinare e importare.

`Nuova giornata operativa` usa lo stesso endpoint e lo stesso dialog del
reset. Non esiste un secondo reset.

## Accessibilita

Il dialog distruttivo:

- usa `<dialog>` con `aria-labelledby` e `aria-describedby`;
- richiede la parola esatta `RIPRISTINA`;
- mantiene disabilitato il pulsante fino alla conferma;
- espone avanzamento tramite `aria-live`;
- impedisce Escape e doppio invio durante la richiesta;
- restituisce il focus all'elemento di apertura alla chiusura;
- distingue chiaramente dati rimossi e preservati.

## Procedure

### Demo -> dati reali

1. selezionare `Importa dati reali`;
2. scegliere `Rimuovi demo e continua`;
3. leggere l'impatto del reset;
4. scrivere `RIPRISTINA`;
5. attendere il completamento;
6. importare i nuovi file dalla sezione aperta automaticamente.

### Nuova giornata di produzione

1. selezionare `Nuova giornata operativa`;
2. confermare con `RIPRISTINA`;
3. verificare il badge `Workspace vuoto`;
4. importare Planning e Fleet della nuova giornata.

## QA Railway

Dopo il deploy:

1. verificare `GET /api/health`;
2. verificare `GET /api/workspace/v1/status`;
3. provare `EMPTY -> DEMO -> RESET -> EMPTY`;
4. importare fixture sintetiche e verificare `PRODUCTION`;
5. creare una versione Configuration;
6. eseguire reset e verificare che la Configuration esista ancora;
7. controllare l'audit reset nel PostgreSQL;
8. verificare assenza di errori console su desktop, tablet e mobile.

## Limiti

- non esiste autenticazione: l'actor e fisso;
- non esiste undo del reset;
- non vengono conservate copie dei dati eliminati;
- non esiste lock distribuito;
- l'inventario appartiene all'installazione, non a un multi-tenant avanzato;
- le tabelle legacy isolate non fanno parte del workspace corrente.

Prima di un reset in produzione resta consigliato usare i backup PostgreSQL
Railway previsti dalla policy operativa dell'ambiente.
