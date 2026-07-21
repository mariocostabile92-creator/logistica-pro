# Intelligent Fleet Registry v1

**Governance canonica:** [Operations Engine Roadmap](OPERATIONS_ENGINE_ROADMAP.md),
[Core, Adapter e Plugin Boundaries](CORE_ADAPTER_PLUGIN_BOUNDARIES.md) e
[Product Screen Contracts](PRODUCT_SCREEN_CONTRACTS.md).

## Scopo

Intelligent Fleet Registry estende il Fleet Plugin esistente. Trasforma un
workbook `FLEET_REGISTRY` in una proposta controllata di sincronizzazione per
Asset, disponibilita, metadati, documenti ed eventi. Non e un secondo plugin
e non decide assegnazioni, readiness o capacity.

Excel e un ponte di ingresso. L'Asset Registry persistito e la fonte di stato
del plugin; lo snapshot Fleet normalizzato continua a servire il Planning
esistente senza modificarne il comportamento.

## Flusso

```text
Workbook -> Profiler -> target fleet_registry -> mapping semantico
         -> matching Asset -> diff -> selezione utente -> conferma
         -> transazione atomica -> Registry + eventi + snapshot + Core
```

Il codice e separato in importer, application service, dominio, repository,
schema e router dentro `backend/app/plugins/fleet/`.

## Interpretazione semantica

Ogni mapping o valore e classificato come:

- `RECOGNIZED`: corrispondenza esplicita ad alta confidenza;
- `INFERRED`: risultato di regole configurate su piu segnali;
- `NEEDS_CONFIRMATION`: ambiguo e non selezionato automaticamente;
- `IGNORED`: non necessario al contratto;
- `SENSITIVE`: escluso prima della costruzione della proposta.

Le regole di availability provengono dalla sezione `fleet_registry` del
Configuration Engine. Lo stato esplicito ha priorita; seguono presenza di
officina e indicatore danno. La policy `infer_available_when_no_issue` decide
se un Asset senza problemi osservati puo essere proposto come disponibile.

Alias specifici della struttura del file restano nell'import layer. I default
coprono identificativo, targa, modello, categoria, noleggio, stato, officina,
danno, sostitutivo, parcheggio, driver osservati, documenti e scadenze.

## Matching e diff

Il matching usa in ordine:

1. `external_identifier` esatto;
2. targa normalizzata esatta;
3. identificativi alternativi gia osservati.

Modello e societa di noleggio non sono mai identita. Targhe simili non vengono
fuse. La preview classifica ogni riga come `NEW_ASSET`, `UPDATE_EXISTING`,
`NO_CHANGE`, `POSSIBLE_DUPLICATE`, `CONFLICT` o `INVALID_ROW`.

Duplicati, conflitti e righe invalide non sono selezionabili. Le selezioni
restano stabili quando l'utente cambia filtro nella UI.

## Privacy

Header PIN, password, codice carta, numero carta e tessera carburante sono
classificati `SENSITIVE`. Anche un valore che sembra un PIN o un numero carta
completo viene escluso, indipendentemente dall'header.

Il valore sensibile non entra in preview, proposed values, log, eventi,
metadata, documenti o snapshot. La UI mostra soltanto il nome del campo e il
messaggio `Campo sensibile rilevato: escluso dall'import automatico.`

Note personali e campi ambigui non vengono importati automaticamente.

## Sincronizzazione atomica

La conferma riceve fingerprint del workbook e ID delle righe selezionate. In
una sola transazione:

- crea o aggiorna Asset;
- aggiorna availability e metadati osservati;
- aggiunge documenti strutturati;
- registra eventi reali;
- salva il run di sincronizzazione;
- crea lo snapshot Fleet normalizzato usato dal Planning;
- rende disponibile il contratto neutrale `ResourceAvailability`.

Qualsiasi errore esegue rollback completo. Nessun Asset, evento o snapshot
parziale rimane persistito.

La relazione `observed_assigned_human_resource` e solo osservata. Se il
riferimento non esiste nel Workforce Plugin resta non risolto; non viene
creata una persona e non nasce un Assignment.

## Eventi e idempotenza

Gli eventi supportati includono `AssetCreated`, `AssetUpdated`,
`AssetAvailable`, `AssetUnavailable`, `AssetMaintenanceStarted`,
`AssetMaintenanceEnded`, `AssetReserveAssigned`, `AssetDocumentObserved` e
`AssetAssociationChanged`.

Gli eventi sono append-only e hanno fingerprint. Lo stesso workbook gia
applicato produce `NO_CHANGE`, restituisce un risultato idempotente e non crea
Asset, run, documenti o eventi duplicati. Se cambia una sola riga, il diff e la
chiave applicativa includono lo stato corrente e aggiornano soltanto l'Asset
interessato.

## Documenti

Un `AssetDocument` viene creato solo quando tipo e data sono strutturati. Una
data non interpretabile resta da confermare. La stessa combinazione Asset,
tipo e scadenza non viene duplicata. Le notifiche e i workflow di intervento
appartengono al futuro Maintenance Plugin.

## API

Endpoint registry v1 gia esistenti:

- `GET /api/plugins/fleet/v1/assets`
- `POST /api/plugins/fleet/v1/assets`
- `GET/PATCH /api/plugins/fleet/v1/assets/{asset_id}`
- `POST /api/plugins/fleet/v1/assets/{asset_id}/availability`
- `POST /api/plugins/fleet/v1/assets/{asset_id}/documents`
- `GET /api/plugins/fleet/v1/assets/{asset_id}/events`

Endpoint di sincronizzazione:

- `POST /api/plugins/fleet/v1/sync/preview`
- `POST /api/plugins/fleet/v1/sync/confirm`
- `GET /api/plugins/fleet/v1/sync/latest`
- `GET /api/plugins/fleet/v1/availability`

## Workspace e UI

In `DEMO` la conferma di dati reali restituisce 409 tipizzato. In
`PRODUCTION` sono ammessi diff incrementali. Il reset elimina metadata, run,
fingerprint, documenti, eventi, Asset e snapshot in ordine compatibile con le
foreign key, preservando Configuration Engine.

La pagina Fleet mostra totale, disponibili, indisponibili, officina, riserva,
documenti in attenzione, aggiornamenti e conflitti. Il flusso UI e upload,
analisi, preview, filtri, selezione, conferma e risultato. Non espone valori
sensibili.

## Fleet Snapshot e Asset Registry

Il Fleet Snapshot e una fotografia normalizzata destinata ai motori Core e al
Planning compatibile. L'Asset Registry conserva identita e lifecycle. La sync
aggiorna entrambi atomicamente, ma i due contratti restano distinti.

## Limiti v1

- nessuna notifica scadenze;
- nessun ordine di manutenzione o gestione officina;
- nessun matching fuzzy di targhe;
- nessuna deduzione ambigua applicata automaticamente;
- nessuna creazione di Human Resource da note Fleet;
- nessuna decisione o Assignment operativa.
