# Real Excel Import Hardening v1

**Governance canonica:** [Operations Engine Vision](OPERATIONS_ENGINE_VISION.md),
[Operations Engine Roadmap](OPERATIONS_ENGINE_ROADMAP.md) e
[Development Sprint Rules](DEVELOPMENT_SPRINT_RULES.md). Excel e un ponte,
non il prodotto ne il modello del dominio.

## Scopo

Questa release rende deterministica e comprensibile l'analisi di workbook
operativi complessi prima dell'import. Non aggiunge funzioni operative e non
modifica Planning Engine, Decision Engine, Fleet Plugin, Configuration Engine
o Core Language.

La preview non equivale piu a "il file si apre": deve identificare una tabella,
spiegare la scelta e dichiarare se quella tabella puo alimentare il flusso
richiesto.

## Problema corretto

Il precedente lettore assumeva una struttura tabellare semplice. Su workbook
reali con molti fogli, titoli, celle unite, formule, calendari e intestazioni
spostate poteva:

- scegliere una riga dati o decorativa come intestazione;
- produrre colonne generiche e mapping a bassa confidenza;
- non distinguere una turnistica da un Planning operativo;
- restituire HTTP 500 durante la persistenza.

La causa precisa del 500 era:

```text
TypeError: Object of type datetime is not JSON serializable
```

Il valore nasceva da una cella Excel di tipo data presente nel dizionario
`raw` di una riga normalizzata. La chiamata
`import_repository.save_import()` eseguiva `json.dumps(normalized_rows)` senza
prima convertire i valori Pydantic/Excel in valori JSON.

La correzione e strutturale:

- il profiler converte date, orari e decimali durante la costruzione della
  tabella;
- le righe e il mapping sono serializzati con
  `model_dump(mode="json")` prima della persistenza;
- il test di regressione importa una fixture sintetica con `datetime` e
  verifica una risposta 200 e un valore ISO 8601;
- non e stato aggiunto un `try/except` generico per nascondere l'errore.

## Tipi di workbook

Il profiler espone quattro tipi:

| Tipo | Significato | Flusso ammesso |
| --- | --- | --- |
| `DAILY_OPERATIONAL_PLANNING` | Task/route, Operational Unit/station e Human Resource/driver nella stessa tabella | Planning |
| `WORKFORCE_SCHEDULE` | Turni, calendario, ferie, riposi, assenze o condizioni contrattuali | Workforce Planning |
| `FLEET_REGISTRY` | Identificativi Asset e attributi di stato del parco | Intelligent Fleet Registry |
| `UNKNOWN_WORKBOOK` | Evidenze insufficienti o struttura ambigua | Nessun import automatico |

La classificazione vive nel livello importer/Adapter. Nessun termine verticale
e stato introdotto nel Core neutrale.

## Workbook profiler

Il modulo `backend/app/importers/workbook_profiler/` e separato dagli importer
di normalizzazione:

- `workbook_scanner.py`: legge CSV, XLS e XLSX, fogli, celle unite, formule e
  valori senza eseguire macro o formule;
- `header_detector.py`: valuta fino alle prime 100 righe usate;
- `sheet_profiler.py`: assegna un punteggio ai fogli;
- `workbook_classifier.py`: classifica il workbook con motivazione;
- `preview_builder.py`: costruisce mapping, blocchi, avvisi e campione;
- `models.py`: contratti tipizzati;
- `errors.py`: errori attesi tipizzati.

La preview e read-only e non persiste file o righe.

## Selezione foglio

Ogni foglio riceve un punteggio basato su:

- confidenza della migliore intestazione;
- copertura alias dell'Adapter;
- continuita e numero delle righe dati;
- densita della tabella;
- parole chiave coerenti con il flusso richiesto;
- penalita per uso eccessivo di formule;
- struttura vuota o puramente decorativa.

La risposta include foglio scelto, punteggio, motivazione, alternative e fogli
ignorati. `sheet_name` consente la selezione manuale.

## Selezione intestazione

Il rilevatore non assume la riga 1. Per ogni candidata considera:

- prevalenza di testo;
- numero e unicita delle celle non vuote;
- alias riconosciuti;
- continuita delle righe successive;
- penalita per numeri/date, formule, titolo singolo e celle unite dominanti.

La risposta include riga scelta, confidenza, motivazione e candidate
alternative. `header_row` consente di confermare manualmente una riga tra 1 e
100. Una selezione manuale valida resta utilizzabile anche quando il punteggio
automatico e basso.

## Mapping

Gli alias provengono dall'Adapter attivo e dalle estensioni del Configuration
Engine gia supportate. Il profiler:

- riconosce automaticamente solo i campi sopra soglia;
- presenta i campi a bassa confidenza come da confermare;
- risolve target duplicati scegliendo il candidato con confidenza maggiore;
- limita le destinazioni ai campi accettati dall'import corrente;
- impedisce che lo stesso target sia scelto due volte;
- supporta la scelta esplicita `Ignora colonna`;
- non usa il mapping manuale per trasformare una vera turnistica in Planning
  operativo.

## Preview API

Non sono stati aggiunti endpoint. Sono stati estesi i form e la risposta di:

- `POST /api/imports/preview`
- `POST /api/imports/planning`
- `POST /api/imports/fleet`

I form accettano facoltativamente:

- `sheet_name`;
- `header_row`;
- `column_mapping`, lista JSON di coppie `source_column`/`target_field`.

La preview mantiene i campi precedenti e aggiunge:

- tipo, confidenza e motivazione del workbook;
- profili dei fogli;
- header selezionato e alternative;
- righe e colonne rilevate;
- mapping e opzioni compatibili;
- colonne riconosciute, ignorate e sconosciute;
- `import_allowed`;
- blocchi e warning tipizzati;
- campione massimo di 10 righe e 12 colonne dati.

La risposta espone inoltre `recommended_target` e
`recommended_action_label`. Il backend instrada `WORKFORCE_SCHEDULE` a
Workforce, `FLEET_REGISTRY` alla sincronizzazione Fleet e
`DAILY_OPERATIONAL_PLANNING` al Planning esistente. Il frontend non replica la
classificazione.

## Import atomico ed error handling

L'import procede soltanto quando tipo, foglio, header, mapping e campi
obbligatori sono compatibili. Normalizzazione e validazione avvengono prima
dell'unica scrittura del record import; la scrittura usa la transazione
`db_session`, con rollback su errore.

Gli stati attesi sono:

- preview 200 con `import_allowed=false` per struttura leggibile ma
  incompatibile;
- 400 `WORKBOOK_NOT_READABLE` per file corrotto/non leggibile;
- 422 `INVALID_WORKBOOK_SELECTION` per selezioni o mapping non validi;
- 422 `WORKBOOK_IMPORT_BLOCKED` per tentativo di import non compatibile.

HTTP 500 resta riservato agli errori imprevisti. Il frontend tratta i 404/400
attesi di Demo, latest Planning e Dashboard vuota come empty state, senza
registrarli come errori di console.

## Preview frontend

La vecchia sequenza di box e stata sostituita con:

- riepilogo tipo/foglio/header/righe/confidenza;
- avvisi e blocchi spiegati;
- selezione foglio e riga header;
- rianalisi obbligatoria dopo una modifica;
- mapping compatto in una sezione scorrevole;
- scelta esplicita di ignorare una colonna;
- campione tabellare limitato e con scroll orizzontale;
- pulsante Import disabilitato finche il backend non restituisce
  `import_allowed=true`.

`Genera Planning` resta disabilitato finche lo stato workspace non conferma un
import Planning valido. Il frontend non ricostruisce la classificazione.

## QA sui workbook reali

I due workbook sono stati letti esclusivamente dai percorsi locali originari,
senza copiarli nel repository.

### Workbook Workforce

- 6 fogli profilati e 5 fogli utili interpretati;
- classificazione `WORKFORCE_SCHEDULE` e target `workforce`;
- preview e import Workforce HTTP 200;
- calendario annuale rilevato su 370 giorni;
- 40 codici turno distinti e 519 assenze rilevate;
- 59 record contrattuali con date e tipologia part-time riconosciuti;
- 21 colonne strutturali restano da confermare o ignorare;
- stesso workbook reimportato con risultato idempotente;
- nessun record Planning o Assignment creato dal plugin.

Il parser usa tutti i fogli utili e non forza la turnistica nel Planning
operativo giornaliero. Conteggi e date sono stati verificati senza stampare
nomi o altri valori personali.

### Workbook Fleet

- 35 fogli rilevati;
- foglio selezionato: `Stato parco`;
- intestazione selezionata: riga 5;
- classificazione: `FLEET_REGISTRY`, confidenza 1,00;
- 21 colonne e 86 righe tabellari rilevate;
- target riconosciuti: `vehicle_plate`, `driver_name`,
  `second_driver_name`, `workshop`, `damage`, `vehicle_model`,
  `replacement_vehicle` e `parking`;
- 172 occorrenze di campi sensibili escluse prima della proposta;
- 59 Asset proposti disponibili, 26 indisponibili e 1 in manutenzione;
- preview e conferma HTTP 200;
- 86 Asset creati e 86 disponibilita neutrali pubblicate al Core;
- snapshot operativo aggiornato nella stessa transazione;
- secondo passaggio idempotente, senza Asset o eventi duplicati.

Fleet Snapshot e Asset Registry restano contratti distinti. Intelligent Fleet
Registry li aggiorna atomicamente e conserva eventi append-only, senza
spostare logica Fleet nel Planning Engine.

### Planning sintetico end-to-end

Una fixture esclusivamente sintetica ha verificato:

- import Planning 200;
- import Fleet 200;
- generazione Planning 200;
- 2 assegnazioni;
- Dashboard 200 con 2 Task;
- Briefing 200 con 7 sezioni.

## Prestazioni

Dopo l'eliminazione delle normalizzazioni e regex ripetute nei cicli interni,
il profiling locale e passato da circa 40 secondi per richiesta a:

- circa 5,8 secondi per il workbook driver;
- circa 8,0 secondi per il workbook Fleet.

I tempi dipendono da CPU, disco e complessita del workbook.

## Privacy

- I workbook reali restano fuori dal repository.
- Non sono presenti copie in `artifacts/` o nelle fixture.
- I test creano workbook sintetici in memoria.
- I database QA temporanei sono stati eliminati dopo ogni esecuzione.
- Report e log non contengono valori di celle, nomi, targhe, PIN o carte reali.
- `.gitignore` protegge anche l'ambiente virtuale e i pattern locali dei due
  workbook.

## Limiti e file ancora necessario

Il workbook Workforce analizzato alimenta turni e disponibilita, ma non e un
Planning operativo giornaliero. Per generare Assignment serve ancora un file
giornaliero con almeno:

- Task/route;
- Operational Unit/station;
- Human Resource/driver.

Asset/vehicle e Time Window/wave sono facoltativi ma raccomandati.

Il mapping v1 espone soltanto i campi gia accettati dai modelli normalizzati
esistenti. Nuovi concetti non devono essere aggiunti per replicare colonne
verticali dei workbook.
applicativo, e deve essere chiuso con una verifica browser sul deploy o da un
browser locale raggiungibile prima della promozione finale.
