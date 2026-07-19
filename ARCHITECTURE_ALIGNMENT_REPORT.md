# Architecture Alignment Report

## Operations Engine

**Data audit:** 19 luglio 2026  
**Documento vincolante:** `OPERATIONS_ENGINE_PHILOSOPHY.md`  
**Perimetro:** backend, frontend, importatori, planning, persistenza, legacy e
test del repository `logistica-mvp`

---

## 1. Executive Summary

L'architettura attuale è già modulare e dispone di una base valida per
Operations Engine:

- router, servizi, repository, schemi e dominio sono separati;
- il vecchio optimizer non è usato dall'applicazione corrente;
- parsing tabellare e normalizzazione sono distinti;
- readiness, capacity e planning sono deterministici;
- le decisioni del planning conservano motivi, warning e alternative;
- simulazione e applicazione degli eventi sono separate;
- il frontend consuma lo stato del backend e non ricalcola readiness o planning;
- Amazon dispone già di una directory Adapter separata.

L'allineamento non è ancora completo. Il dominio e i contratti pubblici
riflettono il primo verticale last-mile attraverso termini come `station`,
`route`, `wave`, `driver`, `vehicle` e `plate`. Questi termini non sono tutti
Amazon-specifici, ma non costituiscono ancora il vocabolario neutrale definitivo
descritto dalla Costituzione.

Non sono stati rinominati perché sono presenti in:

- API pubbliche;
- tabelle SQLite;
- dati persistiti;
- fixture;
- frontend;
- test;
- export CSV.

Una rinomina immediata avrebbe modificato i contratti e aumentato il rischio di
regressione. Il report li classifica e definisce la destinazione futura.

Il refactoring eseguito in questa attività ha:

- eliminato un ciclo di dipendenze di produzione tra generazione planning,
  modifica assignment e simulazione eventi;
- separato costruzione Resource, generazione Assignment e modifica manuale;
- spostato la logica applicativa fuori dal router operations;
- unificato due duplicazioni concrete;
- aggiunto test automatici sui confini architetturali;
- mantenuto invariati API, database, frontend e comportamento.

Baseline prima del refactoring:

```text
59 test superati
0 test falliti
```

---

## 2. Metodo di Analisi

Sono stati analizzati:

- albero completo dei file applicativi;
- import Python tra moduli;
- router FastAPI;
- modelli Pydantic e dominio;
- servizi operations e planning;
- repository e inizializzazione SQLite;
- parser `.xlsx`, `.xls` e `.csv`;
- normalizzatori planning e fleet;
- alias di mapping;
- Adapter Amazon;
- tutti i moduli JavaScript;
- struttura HTML e CSS;
- legacy optimizer e copie di compatibilità;
- test automatici esistenti.

I criteri di confronto derivano da:

- indipendenza del Core dal mercato;
- dipendenze rivolte verso il Core;
- separazione Core, Adapter e Plugin;
- singola responsabilità;
- frontend privo di decisioni business;
- configurazione al posto di workflow hardcoded;
- determinismo, spiegabilità e audit;
- refactoring incrementale senza over-engineering.

---

## 3. Mappa dell'Architettura Attuale

```text
FastAPI routers
  -> application services
     -> domain models and rules
     -> repositories
        -> SQLite infrastructure

File upload
  -> tabular parser
  -> column mapping
  -> planning/fleet normalizer
  -> import repository

Planning
  -> input validation
  -> resource projection
  -> assignment generation
  -> station capacity
  -> persistence and versioning
  -> manual changes / event simulation / recalculation

Frontend
  -> API client
  -> state
  -> presentation modules and components
```

Questa struttura è compatibile con un'evoluzione incrementale verso:

```text
Interfaces -> Application -> Domain
Infrastructure -> Core contracts
Adapters -> Core contracts
Plugins -> Core contracts
```

Non esistono ancora porte astratte o un event bus. Non sono stati creati perché
non esiste un secondo Adapter o Plugin che ne dimostri oggi la necessità.

---

## 4. Valutazione di Conformità

| Area | Stato | Valutazione |
| --- | --- | --- |
| Modularità backend | Conforme con debito | Struttura separata; alcuni servizi restano grandi |
| Router | Conforme dopo refactoring | Non accedono più direttamente ai repository |
| Dominio | Parzialmente conforme | Pulito da Amazon diretto, ma ancora last-mile |
| Adapter Amazon | Parzialmente conforme | Isolato, ma non ancora collegato ai flussi import |
| Plugin | Pronto strutturalmente | Nessun Plugin implementato, correttamente |
| Import | Conforme con debito | Parser e normalizzazione separati |
| Planning | Parzialmente conforme | Deterministico e spiegabile, vocabolario verticale |
| Decisioni | Conforme | Motivi, warning, alternative, diff e conferma |
| Simulazioni | Conforme | Non persistono finché non applicate |
| Persistenza | Conforme per la fase | Repository separati, SQLite come dettaglio infrastrutturale |
| Frontend | Conforme | Nessun calcolo di readiness, capacity o assegnazioni |
| Configurazione | Parzialmente conforme | Planning configurabile, alias e station ancora hardcoded |
| Legacy | Isolato dall'app corrente | Restano copie di compatibilità nel root backend |
| Test architetturali | Conforme dopo refactoring | Cinque guardrail automatici aggiunti |

---

## 5. Classificazione della Terminologia Verticale

### 5.1 Può rimanere temporaneamente

Questi termini sono parte dei contratti correnti. Possono rimanere durante una
migrazione compatibile, ma non devono essere copiati in nuovi moduli Core.

| Termine | Dove compare | Motivo della permanenza temporanea |
| --- | --- | --- |
| `station` | API, dominio, database, frontend, export | Rinomina incompatibile |
| `route` / `route_id` | import, planning, eventi, export | Identificativo pubblico e persistito |
| `cycle_or_wave` | planning, assignment, export | Contratto API esistente |
| `driver` | modelli, API, UI | Prima specializzazione di Human Resource |
| `vehicle` / `plate` | modelli, API, UI, database | Prima specializzazione di Asset |
| `fleet` | dataset type e endpoint import | Contratto pubblico esistente |
| `route_aborted` | enum evento e API | Evento pubblico versionato |
| `DSP Operations OS` | titolo API e UI | Branding UX fuori dal perimetro del refactoring |

Regola: i moduli nuovi devono preferire concetti neutrali quando non devono
mantenere un contratto esistente.

### 5.2 Deve diventare responsabilità di un futuro Adapter

| Elemento attuale | Destinazione |
| --- | --- |
| alias `wave`, `cycle`, `delivery station`, `route` | Adapter Amazon o Adapter file configurato |
| `AMAZON_PLANNING_FIELD_ALIASES` | Amazon Adapter |
| `AMAZON_EVENT_ALIASES` | Amazon Adapter |
| mapping `route_abort`, `van_down`, `driver_no_show` | Amazon Adapter |
| codici station noti come `DLO1` e `DLO2` | configurazione organizzazione o Adapter |
| interpretazione Amazon di station, route e wave | Amazon Adapter |
| futuri yard, dispatch e scorecard | Amazon Adapter |
| formati Excel proprietari Amazon | inbound Amazon Adapter |

La directory `backend/app/adapters/amazon` è già la collocazione corretta.
Attualmente è isolata e non viene importata dal Core, ma non partecipa ancora
alla pipeline di import. Collegarla ora avrebbe modificato il mapping e quindi
il comportamento.

### 5.3 Deve evolvere verso un concetto neutrale

| Concetto corrente | Concetto Operations Engine |
| --- | --- |
| station | Operational Unit |
| route | Task o Work Batch |
| cycle / wave | Time Window o Work Batch |
| driver | Human Resource con capability `driver` |
| vehicle | Asset |
| vehicle status | Resource Availability |
| plate | external identifier dell'Asset |
| fleet row | Asset observation proveniente da Adapter |
| planning row | Task demand proveniente da Adapter |
| route abort | Task cancellation event |
| driver absent | Resource unavailable event |
| vehicle unavailable | Asset unavailable event |
| reserve vehicle | Resource con policy di riserva |
| station capacity | Operational Unit capacity |

Questa evoluzione richiede contratti versionati e migrazioni dei dati. Non deve
essere realizzata con una sostituzione globale di stringhe.

---

## 6. Audit delle Responsabilità

### 6.1 Router

**Conforme**

- `health.py` espone solo il trasporto.
- `imports.py` delega a `import_service`.
- `planning.py` traduce richieste, risposte ed errori HTTP.

**Corretto in questa attività**

`operations.py` caricava import, validava disponibilità, convertiva modelli,
eseguiva l'analisi e salvava il risultato. Questa era logica applicativa nel
router.

La responsabilità è ora in:

```text
services/operations_analysis_service.py
```

Il router gestisce solo:

- request;
- response;
- query parameter;
- traduzione errori in status HTTP.

### 6.2 Servizi

**Già focalizzati**

- `capacity_service.py`;
- `readiness_service.py`;
- `summary_service.py`;
- `planning_validation_service.py`;
- `station_capacity_service.py`;
- `planning_export_service.py`;
- `import_service.py` come orchestratore dell'import.

**Separati in questa attività**

Il precedente `assignment_service.py` conteneva:

- proiezione Driver/Vehicle;
- algoritmo di generazione assignment;
- modifica manuale;
- validazione;
- persistenza;
- versionamento;
- emissione eventi.

Le implementazioni canoniche sono ora:

```text
resource_service.py
assignment_generation_service.py
manual_assignment_service.py
```

`assignment_service.py` rimane temporaneamente come compatibilità per import
Python storici. I moduli di produzione non dipendono più da quel percorso.

I vincoli di disponibilità derivati dagli eventi sono ora isolati in:

```text
event_resource_service.py
```

Questo rimuove la dipendenza della ricostruzione planning dal simulatore eventi.

**Debito residuo**

- `exception_simulation_service.py` simula e applica eventi nello stesso file;
- `planning_generation_service.py` genera, ricostruisce e aggiorna metriche;
- il vecchio corpo di `assignment_service.py` resta presente per compatibilità;
- `conflict_service.analyze_operations` usa un import locale di compatibilità.

Separare ulteriormente questi moduli è possibile, ma richiede test mirati sui
confini transazionali. Non è stato fatto in questa attività per evitare un
refactoring ampio senza beneficio comportamentale.

### 6.3 Modelli

**Conforme**

- stati ed enum sono espliciti;
- Assignment registra origine, confidenza, motivi, dati usati e alternative;
- Planning registra versione, configurazione e import sorgente;
- Event distingue simulato e applicato;
- Diff conserva prima e dopo;
- readiness e capacity sono modelli separati.

**Da migliorare**

- `NormalizedPlanningRow` e `NormalizedFleetRow` sono modelli di frontiera,
  non veri modelli Core;
- `PlanningBundle` aggrega risposta applicativa e dominio;
- `EventSimulation` contiene Assignment e PlanningDiff, quindi è più vicino a
  un risultato applicativo che a un evento di dominio;
- `DriverResource` e `VehicleResource` dovranno evolvere verso Human Resource
  e Asset;
- `PlanningConfiguration` contiene policy fortemente legate ai mezzi.

Queste modifiche richiedono una fase di contratti Core versionati.

### 6.4 Utility

**Conforme**

- `text_normalizer.py` contiene trasformazioni pure e generiche;
- `date_utils.py` contiene conversioni temporali;
- nessuna utility calcola planning, capacity o readiness.

**Attenzione futura**

`normalize_plate` è specifico di un identificativo Asset. Quando esisterà il
Fleet Plugin, dovrà essere valutato se mantenerlo come normalizzatore generico
di external identifier o spostarlo nel Plugin/Adapter.

### 6.5 Repository e database

**Conforme**

- SQL e JSON persistence sono fuori dai servizi di calcolo;
- i repository ricostruiscono modelli tipizzati;
- il database è inizializzato da infrastructure;
- planning, assignment, eventi e versioni sono separati.

**Corretto in questa attività**

L'INSERT SQL degli assignment era duplicato in:

- `assignment_repository.py`;
- `planning_repository.py`.

Ora esiste una sola implementazione transazionale:

```text
insert_assignment_in_session
```

`planning_repository` la usa all'interno della transazione di creazione del
planning.

**Debito residuo**

- `core/database.py` contiene DDL di tutte le tabelle;
- non esiste ancora un sistema di migrazioni;
- i nomi colonna sono verticali;
- i record restituiti dai repository sono in parte dizionari non tipizzati.

Non sono stati aggiunti database o migrazioni perché fuori perimetro.

---

## 7. Planning Engine

### 7.1 Parti già adatte al Core

- validazione di input mancanti o incompatibili;
- esclusione di Resource indisponibili;
- unicità delle assegnazioni;
- conservazione di override manuali confermati;
- generazione deterministica;
- motivi e dati usati;
- alternative ordinate;
- simulazione prima dell'applicazione;
- versionamento;
- diff;
- audit actor/timestamp;
- capacity;
- readiness;
- gestione di deficit e riserva configurabile;
- separazione tra calcolo e persistenza.

Questi comportamenti sono indipendenti da Amazon.

### 7.2 Parti ancora verticali

- scelta basata su `station`;
- Task rappresentato come `route_id`;
- Time Window rappresentata come `cycle_or_wave`;
- Human Resource rappresentata direttamente come Driver;
- Asset rappresentato direttamente come Vehicle/plate;
- stato Asset basato su termini `officina`, `riserva`, `guasto`;
- evento di cancellazione codificato come `ROUTE_ABORTED`;
- suggerimento `cross_station`;
- testi e conflict code legati a rotte e mezzi.

### 7.3 Destinazione futura

**Core**

- algoritmo generico Task-Resource;
- invarianti;
- Assignment;
- Planning;
- Capacity;
- Readiness;
- Conflict;
- Event;
- Decision e Alternative;
- versionamento e audit.

**Adapter**

- mapping station -> Operational Unit;
- mapping route -> Task;
- mapping wave/cycle -> Time Window;
- mapping abort -> Task cancellation;
- alias e codici esterni;
- formati import/export specifici.

**Plugin**

- anagrafica e ciclo di vita Vehicle/Asset -> Fleet Plugin;
- officina e interventi -> Maintenance Plugin;
- disponibilità e qualifiche Driver -> HR Plugin;
- costi dell'assegnazione -> Finance Plugin.

---

## 8. Import Excel e CSV

### 8.1 Separazione attuale

La pipeline è correttamente divisa:

```text
excel_reader.py
  -> legge il formato e restituisce colonne/righe

normalization_service.py
  -> suggerisce il mapping

planning_importer.py / fleet_importer.py
  -> trasformano righe mappate in modelli normalizzati

import_service.py
  -> orchestra validazione, parsing, mapping, normalizzazione e salvataggio
```

Il parser non decide conflitti, capacità o assegnazioni.

### 8.2 Duplicazione corretta

La costruzione del mapping confermato era duplicata nei due normalizzatori.
Ora è centralizzata in:

```text
importers/column_mapping.py
```

### 8.3 Debito residuo

- `excel_reader.py` dipende da FastAPI per `UploadFile` e `HTTPException`;
- `ColumnMappingSuggestion` vive negli schemi API ma viene usato dagli importer;
- alias generici e verticali sono raccolti nello stesso servizio;
- l'Amazon Adapter contiene alias propri ma non compone ancora il mapping;
- `dataset_type` è una stringa non tipizzata;
- la configurazione degli alias non è versionata.

La correzione futura dovrà introdurre un contratto di mapping neutrale e
comporre alias generici con quelli dell'Adapter attivo. Non è stato fatto ora
per non cambiare il riconoscimento delle colonne.

---

## 9. Frontend

### 9.1 Punti conformi

Il frontend:

- usa un client API centralizzato;
- mantiene solo stato di presentazione;
- visualizza readiness ricevuta dal backend;
- visualizza capacity ricevuta dal backend;
- visualizza Assignment, warning e alternative ricevuti dal backend;
- invia comandi per generare, ricalcolare, modificare e simulare;
- non assegna automaticamente Driver o Vehicle;
- non ricalcola conflitti;
- non ricalcola la readiness;
- non modifica direttamente la persistenza;
- mantiene moduli e componenti separati.

`dashboardDetail`, filtri e label sono logica di presentazione.

### 9.2 Logica applicativa transitoria

Due comportamenti meritano attenzione:

- `confirmValidAssignments` seleziona nel browser quali assignment confermare;
- `entityTypeFor` associa tipi evento a entità API.

Il backend valida ogni conferma, quindi il frontend non è fonte della verità.
Questa orchestrazione è accettabile finché non esiste un comando batch Core.
Non è stata aggiunta una nuova API in questa attività.

### 9.3 Terminologia

Il frontend mostra DSP, station, route, wave e vehicle perché sono il
vocabolario dell'API corrente. Una futura nomenclatura configurabile dovrà
cambiare le label senza cambiare i concetti Core.

Nessuna modifica UX è stata applicata.

---

## 10. Dipendenze Indesiderate

### Risolte

| Dipendenza | Correzione |
| --- | --- |
| Planning generation -> assignment service misto | usa assignment generation e resource service |
| Assignment patch -> planning generation con ciclo locale | manual assignment service dedicato |
| Planning reconstruction -> exception simulator | usa event resource service |
| Router operations -> repository import | usa operations analysis service |
| Planning repository -> SQL assignment duplicato | usa assignment repository |

### Residue

| Priorità | Dipendenza o accoppiamento | Motivo del rinvio |
| --- | --- | --- |
| Alta | alias verticali in `normalization_service.py` | modifica il mapping import |
| Alta | `KNOWN_STATIONS` hardcoded in `conflict_service.py` | modifica conflitti e comportamento |
| Alta | contratti Core con station/route/vehicle | richiede API e data migration |
| Media | `assignment_service.py` come compatibilità storica | possibile import Python esterno |
| Media | parser import dipendente da FastAPI | richiede custom error mapping |
| Media | domain event e simulation result nello stesso modulo | richiede separazione contratti |
| Media | planning service con query e metric refresh | confine transazionale da testare |
| Bassa | DDL centralizzato in `core/database.py` | SQLite è adeguato alla fase corrente |
| Bassa | API base frontend hardcoded | tema deployment, non business logic |

---

## 11. Parti Pronte per il Core

Possono essere consolidate come futuro Core senza cambiare il comportamento:

- `domain/assignment_models.py`;
- stati e severità di conflitto;
- principi di `planning_models.py`;
- `planning_diff.py`;
- calcolo readiness;
- calcolo capacity;
- validazione invarianti;
- generazione deterministica di Assignment;
- gestione delle alternative;
- versionamento Planning;
- audit delle modifiche;
- separazione simulate/apply.

Prima della promozione definitiva dovranno ricevere nomi neutrali e contratti
indipendenti dagli schemi HTTP.

---

## 12. Parti Destinate agli Adapter

### Amazon Adapter

- alias Amazon;
- termini station, route, wave e cycle nella loro semantica Amazon;
- eventi abort, van down e driver no-show;
- futuri yard, dispatch e scorecard;
- formati di file Amazon;
- codici e identificativi Amazon;
- eventuali export richiesti da Amazon.

### Generic File Adapter

- lettura `.xlsx`, `.xls`, `.csv`;
- selezione foglio;
- mapping configurato;
- provenienza file;
- conversione in contratti inbound neutrali.

Il parser fisico può essere condiviso come infrastructure. La semantica delle
colonne appartiene all'Adapter.

---

## 13. Parti Destinate ai Plugin

### Fleet Plugin

- anagrafica Asset;
- targa e identificativi esterni;
- modello mezzo;
- chiavi;
- carta carburante;
- dotazioni;
- stato e disponibilità osservata.

### Maintenance Plugin

- officina;
- guasto;
- manutenzione;
- scadenze tecniche;
- indisponibilità e ripristino Asset.

### HR Plugin

- anagrafica Human Resource;
- ruolo Driver;
- secondo Driver;
- capability;
- disponibilità;
- assenza e ripristino.

### Finance Plugin

- costo Asset;
- costo Human Resource;
- costo Task;
- impatto economico del planning;
- consuntivi.

### Analytics Plugin

- aggregazioni;
- trend;
- KPI;
- score storici;
- osservazioni derivate.

Nessun Plugin deve leggere direttamente file o concetti Amazon. I dati devono
prima passare attraverso Adapter e contratti Core.

---

## 14. Refactoring Eseguito

### File creati

```text
backend/app/importers/column_mapping.py
backend/app/services/assignment_generation_service.py
backend/app/services/event_resource_service.py
backend/app/services/manual_assignment_service.py
backend/app/services/operations_analysis_service.py
backend/app/services/resource_service.py
backend/tests/test_architecture.py
ARCHITECTURE_ALIGNMENT_REPORT.md
```

### File modificati

```text
backend/app/api/routers/operations.py
backend/app/api/routers/planning.py
backend/app/importers/fleet_importer.py
backend/app/importers/planning_importer.py
backend/app/repositories/assignment_repository.py
backend/app/repositories/planning_repository.py
backend/app/services/assignment_service.py
backend/app/services/exception_simulation_service.py
backend/app/services/planning_generation_service.py
backend/app/services/planning_recalculation_service.py
backend/app/services/station_capacity_service.py
```

### Compatibilità

Non sono stati modificati:

- path API;
- request/response pubbliche;
- status code;
- tabelle o colonne SQLite;
- algoritmo di assegnazione;
- regole readiness/capacity;
- frontend;
- flusso UX;
- export;
- legacy optimizer.

---

## 15. Guardrail Automatici

`backend/tests/test_architecture.py` verifica:

1. il Domain non importa Adapter, API, importer, repository, schema o service;
2. i router non accedono direttamente ai repository;
3. Core, Domain e servizi non dipendono da Adapter o Plugin;
4. i futuri Plugin non dipendono dagli Adapter;
5. i servizi di produzione non usano il modulo storico
   `assignment_service.py`.

Questi test rendono eseguibili alcune regole della Costituzione.

---

## 16. Debito Tecnico

### Alta priorità

1. Definire contratti neutrali per Operational Unit, Task, Human Resource e
   Asset.
2. Spostare station note e alias verticali fuori dai servizi generici.
3. Versionare mapping e nomenclature.
4. Definire una strategia compatibile per API e persistenza verticali.

### Media priorità

1. Rimuovere il corpo legacy da `assignment_service.py` quando non esisteranno
   più import esterni.
2. Separare simulazione e applicazione eventi dopo aver definito il confine
   transazionale.
3. Separare query/rebuild dal comando generate del planning.
4. Introdurre errori import indipendenti da FastAPI.
5. Separare modelli inbound normalizzati dai modelli Core.
6. Eliminare le copie root del vecchio optimizer dopo una verifica esplicita
   degli entrypoint legacy.

### Bassa priorità

1. Introdurre migrazioni SQLite quando il modello dati tornerà a cambiare.
2. Tipizzare i record repository oggi restituiti come dizionari.
3. Rendere configurabile l'URL API frontend in fase di deployment.

---

## 17. Rischi

### Rischi controllati

- nuovi moduli interni possono influire sugli import Python;
- la persistenza condivisa degli assignment deve mantenere la stessa
  transazione;
- lo spostamento dell'orchestrazione operations deve mantenere status e payload.

Mitigazioni:

- compatibilità mantenuta da `assignment_service.py`;
- stessa funzione SQL usata sia per insert singolo sia per create planning;
- test API e planning completi;
- nuovi test architetturali.

### Rischi non affrontati

- rinomina dei contratti verticali;
- migrazione dati;
- attivazione dinamica degli Adapter;
- caricamento Plugin;
- sostituzione del branding;
- introduzione di porte astratte.

Sono stati deliberatamente esclusi perché avrebbero superato il perimetro di un
refactoring comportamentalmente neutro.

---

## 18. Conclusione di Conformità

Il progetto è ora più vicino alla Costituzione senza anticipare l'architettura
futura.

Conformità raggiunta in questa attività:

- nessuna nuova funzionalità;
- nessuna nuova API;
- nessun nuovo database;
- nessuna modifica frontend o UX;
- router privi di persistenza diretta;
- dipendenze Core -> Adapter/Plugin vietate da test;
- responsabilità Assignment separate;
- vincoli evento separati dal simulatore;
- duplicazioni import e repository unificate;
- test esistenti mantenuti.

Conformità ancora da raggiungere:

- vocabolario Core completamente neutrale;
- configurazione di alias e Operational Unit;
- contratti Adapter realmente collegati;
- confini Plugin;
- rimozione dei percorsi di compatibilità legacy.

La prossima funzionalità non deve essere aggiunta direttamente ai modelli
verticali correnti. Deve prima essere classificata come Core, Adapter, Plugin,
Interface o Infrastructure secondo `OPERATIONS_ENGINE_PHILOSOPHY.md`.
