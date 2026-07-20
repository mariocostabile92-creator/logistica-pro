# Real Excel Import Hardening v1

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
| `WORKFORCE_SCHEDULE` | Turni, calendario, ferie, riposi, assenze o condizioni contrattuali | Nessun import Planning automatico |
| `FLEET_REGISTRY` | Identificativi Asset e attributi di stato del parco | Fleet |
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

### Workbook driver

- 6 fogli rilevati;
- foglio tabellare selezionato: `Turni da inviare`;
- intestazione selezionata: riga 1;
- classificazione: `WORKFORCE_SCHEDULE`, confidenza 0,65;
- 11 colonne e 135 righe tabellari rilevate;
- 2 target canonici riconosciuti e 9 colonne da confermare/ignorare;
- preview HTTP 200;
- import Planning bloccato con HTTP 422
  `WORKBOOK_IMPORT_BLOCKED`;
- nessun record Planning persistito e nessun HTTP 500.

### Workbook Fleet

- 35 fogli rilevati;
- foglio selezionato: `Stato parco`;
- intestazione selezionata: riga 5;
- classificazione: `FLEET_REGISTRY`, confidenza 1,00;
- 21 colonne e 86 righe tabellari rilevate;
- target riconosciuti: `vehicle_plate`, `driver_name`,
  `second_driver_name`, `workshop`, `notes`, `fuel_card`;
- 15 colonne non necessarie al contratto v1 restano da
  confermare/ignorare;
- preview HTTP 200 e import HTTP 200;
- workspace operativo popolato con 86 righe Fleet.

L'import Fleet rappresenta lo snapshot operativo usato dal Core. Non crea
automaticamente record di lifecycle nell'Asset Registry del Fleet Plugin:
confondere i due modelli violerebbe le responsabilita definite nella
Costituzione e richiederebbe un contratto di sincronizzazione atomico
separato.

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

Il workbook driver analizzato e una turnistica e non contiene un contratto
sufficiente per generare il Planning operativo giornaliero. Serve ancora un
file giornaliero con almeno:

- Task/route;
- Operational Unit/station;
- Human Resource/driver.

Asset/vehicle e Time Window/wave sono facoltativi ma raccomandati.

Il mapping v1 espone soltanto i campi gia accettati dai modelli normalizzati
esistenti. Nuovi concetti non devono essere aggiunti per replicare colonne
verticali dei workbook.

La verifica responsive automatica e coperta da test frontend per desktop,
tablet e mobile. In questa sessione il browser integrato ha bloccato per policy
l'accesso al server localhost; non sono quindi disponibili screenshot runtime
alle tre risoluzioni. Questo limite riguarda l'ambiente di QA, non un errore
applicativo, e deve essere chiuso con una verifica browser sul deploy o da un
browser locale raggiungibile prima della promozione finale.
