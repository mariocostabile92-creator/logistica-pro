# Planning Workspace Contract Inventory

## Stato del documento

| Campo | Valore |
|---|---|
| Fase | PW-0 |
| Scopo | Inventario dei contratti realmente disponibili al Planning Workspace |
| Natura | Audit documentale e statico del repository |
| Data audit | 22 luglio 2026 |
| Implementazione | Esclusa |
| Modifiche applicative | Nessuna |

Questo documento fotografa lo stato reale del repository al momento dell'audit. Non definisce nuovi contratti, non introduce workaround e non autorizza il Planning Workspace a ricostruire nel frontend informazioni che il backend non pubblica.

## 1. Metodo e criteri

L'analisi ha incluso modelli di dominio, schemi HTTP, router, servizi, repository, importer, adapter, configurazione e consumer frontend relativi a:

- Core;
- Planning Engine;
- Decision Engine;
- Workforce;
- Fleet;
- Mission Control;
- Workbook Profiler;
- Configuration Engine;
- Workspace Lifecycle;
- Daily Operations Briefing;
- Amazon Adapter.

La classificazione usata nel documento è:

| Stato | Significato |
|---|---|
| **ESISTE** | Il contratto è pubblicato e utilizzabile oggi per lo scopo indicato, senza deduzioni sostanziali. |
| **PARZIALE** | Il dato o il contratto esiste, ma manca almeno una proprietà necessaria al Planning Workspace: scope, versione, freschezza, tipizzazione, integrazione o semantica operativa completa. |
| **ASSENTE** | Non esiste oggi un contratto consumabile che rappresenti il concetto richiesto. |

Per **pubblico** si intende un payload esposto da una API esistente. Un modello Python, un servizio richiamato direttamente o uno stato derivato nel frontend è classificato come **interno**, anche quando il nome del modello è stabile.

## 2. Sintesi esecutiva

Sono state censite **44 famiglie di contratto esistenti**. La base attuale pubblica già planning, assegnazioni, conflitti, versioni, asset, persone, calendari, configurazione, stato del workspace e briefing. Tuttavia, la semplice esistenza di questi payload non li rende tutti contratti validi per Planning Workspace.

I principali limiti rilevati sono:

- il Planning Engine continua a costruire il piano dai dataset normalizzati legacy più recenti, non dai contratti Core pubblicati da Workforce e Fleet;
- readiness e capacity pubbliche non sono sempre legate in modo univoco a `planning_id`, versione, data e Operational Unit;
- Operational Unit è presente in più forme, ma non è ancora uno scope uniforme e obbligatorio;
- disponibilità e capability esistono, ma non producono ancora un esito di compatibilità consumabile dal Planning;
- conferma atomica e pubblicazione del planning sono assenti;
- il Decision Engine non possiede ancora un contratto canonico autonomo;
- Mission Control e Daily Briefing sono consumer e viste riassuntive: non sono fonti autorevoli per assegnazioni, conflitti o readiness.

Il **Planning Workspace Readiness Score è 58/100**. Il punteggio misura la copertura contrattuale, non la qualità generale del prodotto né la quantità di codice già sviluppato.

## 3. Inventario completo dei contratti

### 3.1 Registro dei contratti trovati

| ID | Contratto | Proprietario | Tipo | Visibilità | Stato oggi | Responsabile | Consumer attuali o ammessi | Dipendenze principali | Fase roadmap |
|---|---|---|---|---|---|---|---|---|---|
| CORE-01 | `Task` | Core Language | Modello dominio neutrale | Interno | PARZIALE | Core | Mapper Core; futuro Planning Workspace | Identificativo esterno e tipo task | Fase 2 / ponte linguistico |
| CORE-02 | `OperationalUnit` | Core Language | Modello dominio neutrale | Interno | PARZIALE | Core | Mapper station; configurazione | Identificativo esterno e nome | Fase 2 / ponte linguistico |
| CORE-03 | `HumanResource` | Core Language | Modello dominio neutrale | Interno | PARZIALE | Core | Workforce core contract; mapper driver | Identità e capability | Fase 2 / ponte linguistico |
| CORE-04 | `AssetReference` | Core Language | Modello dominio neutrale | Interno | PARZIALE | Core | Mapper vehicle | Identità esterna e categoria | Fase 2 / ponte linguistico |
| CORE-05 | `TimeWindow` | Core Language | Value object | Interno | PARZIALE | Core | Workforce core contract; mapper cycle | Date e orari | Fase 2 / ponte linguistico |
| CORE-06 | `ResourceAvailability` | Core Language | Value object | Pubblico tramite Plugin | PARZIALE | Core | Workforce e Fleet API | Risorsa, tipo, disponibilità, stato osservato | Fase 2 / PW-2 |
| CORE-07 | `OperationsDashboard` | Operations Core | Aggregato operativo | Pubblico | ESISTE | Core | Operations UI; Briefing | Import latest, conflitti, capacity, readiness | Fase 2 |
| CORE-08 | `OperationalReadiness` | Operations Core | Risultato deterministico | Pubblico | PARZIALE | Core | Operations UI; Briefing | Conflitti, capacity, soglia riserva | Fase 2 / PW-2 |
| CORE-09 | `OperationalCapacity` | Operations Core | Risultato deterministico | Pubblico | PARZIALE | Core | Operations UI; Briefing | Planning e fleet importati | Fase 2 / PW-2 |
| CORE-10 | `OperationalIssue` | Operations Core | Problema operativo | Pubblico | PARZIALE | Core | Operations UI | Conflitti normalizzati | Fase 2 / PW-3 |
| PLAN-01 | `PlanningResponse` / `PlanningBundle` | Planning Engine | Aggregato di lettura | Pubblico | ESISTE | Planning | Planning UI; futuro Planning Workspace | Planning, assegnazioni, conflitti, capacity | Fase 3 / PW-1-PW-4 |
| PLAN-02 | `OperationalPlanning` | Planning Engine | Entità versionata | Pubblico | ESISTE | Planning | Planning UI | Import sorgente, stato e configurazione | Fase 3 |
| PLAN-03 | `Assignment` | Planning Engine | Entità operativa | Pubblico | ESISTE | Planning | Planning UI | Route, driver, vehicle, alternative | Fase 3 / PW-4-PW-6 |
| PLAN-04 | `PlanningConflict` | Planning Engine | Conflitto del piano | Pubblico | ESISTE | Planning | Planning UI | Generazione e validazione planning | Fase 3 / PW-3 |
| PLAN-05 | `PlanningSummary` | Planning Engine | Riepilogo | Pubblico | ESISTE | Planning | Planning UI | Assignment e conflict | Fase 3 / PW-1 |
| PLAN-06 | `StationCapacity` | Planning Engine | Capacità per station | Pubblico | PARZIALE | Planning | Planning UI; Briefing | Risorse aggregate per station legacy | Fase 3 / PW-2 |
| PLAN-07 | `GenerationMetadata` | Planning Engine | Metadati di generazione | Pubblico | ESISTE | Planning | Planning UI | Strategia e timestamp generazione | Fase 3 / PW-1 |
| PLAN-08 | `PlanningHistoryResponse` | Planning Engine | Storico versioni ed eventi | Pubblico | PARZIALE | Planning | Planning UI | Repository versioni, eventi e modifiche | Fase 3 / PW-7 |
| PLAN-09 | Event simulation, application e diff | Planning Engine | Comando e risultato | Pubblico | ESISTE | Planning | Planning UI | Planning corrente ed evento operativo | Fase 3 / PW-5 |
| DEC-01 | `AssignmentAlternative` | Planning Engine | Suggerimento annidato | Pubblico | PARZIALE | Planning | Planning UI | Candidati e motivazioni dell'assegnazione | Fase 6 / PW-8 gate |
| DEC-02 | `CrossStationSuggestion` | Planning Engine | Suggerimento annidato | Pubblico | PARZIALE | Planning | Planning UI | Capacità station | Fase 6 / PW-8 gate |
| DEC-03 | `BriefingRecommendation` | Daily Briefing | Raccomandazione riassuntiva | Pubblico | PARZIALE | Briefing | Mission Control | Regole briefing e snapshot moduli | Fase 6 / PW-8 gate |
| WF-01 | `WorkforceStatusResponse` | Workforce Plugin | Stato tecnico Plugin | Pubblico | ESISTE | Workforce | Workforce UI | Feature flag e storage Workforce | Fase 7 |
| WF-02 | `WorkforceMember` | Workforce Plugin | Risorsa umana | Pubblico | ESISTE | Workforce | Workforce UI; core contract | Registry Workforce | Fase 7 / PW-2 |
| WF-03 | `WorkforceDayStatus` | Workforce Plugin | Stato giornaliero e turno | Pubblico | ESISTE | Workforce | Workforce UI; core contract | Persona, data, stato e fascia oraria | Fase 7 / PW-2 |
| WF-04 | `WorkforceCoverage` | Workforce Plugin | Copertura aggregata | Pubblico | PARZIALE | Workforce | Workforce UI | Requisiti e disponibilità per data | Fase 7 / PW-2 |
| WF-05 | `WorkforceChange` | Workforce Plugin | Audit change | Pubblico | PARZIALE | Workforce | Workforce UI | Modifiche a membri e calendario | Fase 7 / PW-7 |
| WF-06 | Workforce Core Contracts | Workforce Plugin | Proiezione Core | Pubblico | PARZIALE | Workforce | Futuri consumer Core | `HumanResource`, `ResourceAvailability`, `TimeWindow` | Fase 7 / PW-2 |
| WF-07 | `WorkforceBriefingSnapshot` | Workforce Plugin | Snapshot riepilogativo | Interno | PARZIALE | Workforce | Daily Briefing via chiamata diretta | Coverage, assenze, contratti, capability | Fase 3 / debito Plugin |
| FL-01 | `AssetListResponse` / `Asset` | Fleet Plugin | Registry Asset | Pubblico | ESISTE | Fleet | Fleet UI | Repository Fleet | Fase 5 / PW-2 |
| FL-02 | Fleet `ResourceAvailability` | Fleet Plugin | Proiezione Core | Pubblico | PARZIALE | Fleet | Futuri consumer Core | Asset e stato osservato | Fase 5 / PW-2 |
| FL-03 | `AssetDocument` | Fleet Plugin | Documento Asset | Pubblico | ESISTE | Fleet | Fleet UI | Asset Registry | Fase 5 |
| FL-04 | `AssetEvent` / event list | Fleet Plugin | Evento cronologico | Pubblico | ESISTE | Fleet | Fleet UI | Asset Registry | Fase 5 / PW-7 |
| FL-05 | `FleetBriefingSnapshot` | Fleet Plugin | Snapshot riepilogativo | Interno | PARZIALE | Fleet | Daily Briefing via chiamata diretta | Asset, documenti, availability | Fase 3 / debito Plugin |
| FL-06 | Fleet Sync Preview / Result | Fleet Plugin | Contratto import e sync | Pubblico | ESISTE | Fleet | Fleet UI | Profiler, matching e Asset Registry | Fase 5 |
| MC-01 | Mission Control View State | Mission Control | Vista derivata frontend | Interno | PARZIALE | Mission Control | Solo Mission Control | Briefing e Workspace Status | Fase 3 |
| IMP-01 | `ImportPreviewResponse` / workbook profile | Workbook Profiler | Profilo import | Pubblico | ESISTE | Import | Import UI | Lettura workbook, classificazione, mapping | Fase 1 |
| IMP-02 | `ImportResultResponse` / normalized rows | Import Service | Risultato import | Pubblico | ESISTE | Import | Operations e Planning legacy | Profiler, importer e repository import | Fase 1 / legacy input |
| CFG-01 | `Configuration` | Configuration Engine | Configurazione versionata | Pubblico | ESISTE | Core Configuration | Settings; servizi che la interrogano | Scope, versioni e fallback | Fase 4 |
| CFG-02 | Configuration versions / validation | Configuration Engine | Comandi e risultati | Pubblico | ESISTE | Core Configuration | Settings e amministrazione | Repository configurazione e validazione | Fase 4 |
| WS-01 | `WorkspaceStatusResponse` | Workspace Lifecycle | Stato aggregato workspace | Pubblico | ESISTE | Core Application | Home e Mission Control | Import, asset, workforce, planning, briefing | Fase 3 / PW-1 |
| BR-01 | `DailyOperationsBriefing` | Daily Briefing | Snapshot persistito | Pubblico | ESISTE | Mission Control | Mission Control | Planning, Operations, Workforce, Fleet | Fase 3 |
| AD-01 | `TabularImportAdapter` | Adapter boundary | Protocollo interno | Interno | ESISTE | Adapter layer | Importer | Alias, mapping e normalizzazione verticale | Fase 10 |
| AD-02 | Amazon catalog, aliases e mappings | Amazon Adapter | Configurazione verticale | Interno | ESISTE | Amazon Adapter | Solo pipeline import attiva | Configuration Engine e Core mappings | Fase 10 |

### 3.2 Contratti assenti come famiglie autonome

I seguenti concetti non hanno oggi un contratto pubblico autonomo e sufficientemente completo:

| Contratto atteso | Stato | Evidenza dello stato reale | Consumer previsto | PW associato |
|---|---|---|---|---|
| Planning input envelope versionato | ASSENTE | Gli input sono ricavati dagli ultimi import normalizzati e da riferimenti separati | Planning Workspace e Planning Engine | PW-2 |
| Readiness vincolata a planning/versione/scope | ASSENTE | La readiness Operations può riferirsi agli ultimi import e alla soglia richiesta, non obbligatoriamente alla versione visualizzata | Planning Workspace | PW-2 |
| Operational Unit uniforme e obbligatoria | ASSENTE | Esistono modello Core, `station` legacy e scope config, ma non un contratto trasversale unico | Tutti i workspace | PW-1 |
| Compatibility result tra task, persone e asset | ASSENTE | Le capability sono pubblicate, ma non esiste un esito di compatibilità | Planning Workspace | PW-3 |
| Comando atomico di conferma planning | ASSENTE | La UI corrente conferma assegnazioni singolarmente | Planning Workspace | PW-6 |
| Stato e comando di pubblicazione | ASSENTE | `PlanningStatus` non include uno stato pubblicato e non esiste endpoint di pubblicazione | Planning Workspace | PW-7 |
| Precondizione di versione sulle modifiche | ASSENTE | Le modifiche non richiedono una `expected_version` del client | Planning Workspace | PW-5 |
| `DecisionProposal` canonica | ASSENTE | Esistono alternative e raccomandazioni locali, non un contratto Decision Engine | Planning Workspace futuro | PW-8 gate / Fase 6 |
| Proiezione pubblica neutrale Task-HR-Asset | ASSENTE | Il payload Planning rimane intenzionalmente nel linguaggio legacy | Planning Workspace | PW-4 |
| Eventi tipizzati di conferma e pubblicazione | ASSENTE | Lo storico è disponibile, ma usa collezioni generiche e non copre la pubblicazione | Planning Workspace | PW-7 |

## 4. Analisi per modulo

### 4.1 Core

**Dati pubblicati**

- dashboard operativa;
- readiness;
- capacity;
- issue operative;
- disponibilità Core tramite proiezioni dei Plugin.

**Contratti pubblici**

- `OperationsDashboard`;
- `OperationalReadiness`;
- `OperationalCapacity`;
- `OperationalIssue`;
- `ResourceAvailability` quando restituita dalle API Workforce o Fleet.

**Consumabile dal Planning Workspace**

- issue e capacity come informazioni di supporto, quando i riferimenti sorgente coincidono con il planning visualizzato;
- readiness solo con verifica esplicita di coerenza rispetto agli input correnti;
- value object neutrali come vocabolario interno futuro, non come API già disponibili.

**Da non consumare**

- modelli Python interni tramite accesso diretto dal frontend;
- readiness globale come prova automatica della readiness di una specifica versione del piano;
- mapping legacy come sostituto di un contratto pubblico neutrale.

**Dati mancanti**

- scope uniforme per data, Operational Unit e versione del planning;
- provenienza completa delle issue;
- envelope degli input usati dal piano.

### 4.2 Planning Engine

**Dati pubblicati**

- planning corrente e per ID;
- stato e versione del planning;
- assegnazioni, alternative e risorse non assegnate;
- conflitti;
- riepilogo e capacità per station;
- simulazioni, applicazione eventi e differenze;
- storico versioni, modifiche ed eventi;
- export.

**Contratti pubblici**

- `PlanningResponse`;
- `OperationalPlanning`;
- `Assignment` e `AssignmentAlternative`;
- `PlanningConflict`;
- `PlanningSummary`;
- `StationCapacity`;
- `GenerationMetadata`;
- `PlanningHistoryResponse`;
- contratti di simulazione, applicazione evento e diff.

**Consumabile dal Planning Workspace**

- `planning.id`, `planning.version`, data, station, stato e timestamp;
- assegnazioni e relativi stati;
- conflitti del bundle;
- alternative già prodotte dal Planning Engine;
- summary, unassigned routes e risorse inutilizzate;
- diff e storico già pubblicati.

**Da non consumare**

- `raw` degli import come modello di dominio del Workspace;
- stato del briefing come sostituto dello stato del planning;
- frontend legacy come sorgente di regole;
- conferma multipla ricostruita come se fosse un comando atomico;
- `station` come prova dell'esistenza di una Operational Unit canonica.

**Dati mancanti**

- conferma atomica del piano;
- pubblicazione;
- controllo di concorrenza basato sulla versione attesa;
- proiezioni neutrali pubbliche per Task, Human Resource, Asset e Operational Unit;
- readiness autorevole della specifica versione;
- storico tipizzato per tutte le transizioni del ciclo di vita.

#### Classificazione Planning Engine

| Voce | Stato | Motivo |
|---|---|---|
| Assignment | ESISTE | Entità pubblica, persistita e inclusa nel bundle Planning. |
| Readiness | PARZIALE | Esiste nel Core Operations, ma non è sempre vincolata alla versione del planning visualizzato. |
| Conflict | ESISTE | `PlanningConflict` è pubblicato nel bundle e nello storico operativo del piano. |
| Capacity | PARZIALE | È disponibile, ma parte della semantica usa ancora station e import legacy. |
| Version | ESISTE | Il planning possiede versione e storico delle versioni. |
| Planning State | ESISTE | Sono definiti e pubblicati gli stati fino a `confirmed` e `superseded`. |
| Publication State | ASSENTE | Non esiste stato, comando o evento di pubblicazione. |

### 4.3 Decision Engine

**Dati pubblicati**

- alternative di assegnazione annidate nelle assegnazioni;
- suggerimenti cross-station annidati nella capacity;
- raccomandazioni sintetiche nel briefing.

**Contratti pubblici**

Non esiste un contratto pubblico autonomo del Decision Engine. Le tre forme presenti appartengono a Planning o Briefing.

**Consumabile dal Planning Workspace**

- le alternative già incluse in `Assignment`, presentandole come output del Planning Engine;
- motivazioni e ragioni di non selezione già pubblicate.

**Da non consumare**

- raccomandazioni del briefing come decisioni applicabili al planning;
- regole client-side ricostruite dalle alternative;
- suggerimenti come comandi automatici.

**Dati mancanti**

- identificativo, stato, contesto, impatto e ciclo di vita canonico di una decisione proposta;
- contratto di applicazione e risultato;
- separazione pubblica tra proposta, decisione umana ed effetto.

### 4.4 Workforce

**Dati pubblicati**

- registry persone;
- capability;
- stati giornalieri, disponibilità e fasce turno;
- copertura aggregata;
- contratti di lavoro presenti sul membro;
- audit delle modifiche;
- proiezioni Core di Human Resource, Resource Availability e Time Window.

**Consumabile dal Planning Workspace**

- persone attive e capability;
- stato giornaliero e fascia oraria;
- disponibilità osservata;
- coverage come contesto, non come verifica definitiva di fattibilità del piano.

**Da non consumare**

- dati personali o contrattuali non necessari all'assegnazione;
- `WorkforceBriefingSnapshot` tramite chiamata interna;
- conteggi aggregati come sostituto delle risorse nominative;
- stato tecnico del Plugin come stato operativo della giornata.

**Dati mancanti o incompleti**

- scope Operational Unit coerente nella coverage e nella proiezione Core;
- versione/freschezza esplicita del set di disponibilità;
- contratto pubblico dedicato alle assenze;
- stream di eventi di dominio tipizzato;
- integrazione effettiva degli input Workforce nella generazione Planning.

#### Classificazione Workforce

| Voce | Stato | Motivo |
|---|---|---|
| Human Resource | ESISTE | Il membro e la proiezione Core sono pubblici. |
| Availability | PARZIALE | Data, stato e fascia sono presenti, ma mancano scope uniforme, versione e integrazione Planning. |
| Capability | ESISTE | Le capability sono pubblicate sul membro e sulla proiezione Core. |
| Workforce Status | PARZIALE | Esistono stato Plugin e stati giornalieri, non un unico stato operativo scoped. |
| Coverage | PARZIALE | È pubblica ma aggregata; lo scope Operational Unit non è preservato in modo uniforme. |
| Assenze | PARZIALE | Sono inferibili dagli stati e presenti nello snapshot interno, non in un contratto pubblico dedicato. |
| Turni | ESISTE | Il calendario pubblica stato giornaliero e fascia turno. |
| Contratti | ESISTE | I dati contrattuali necessari sono presenti sul membro pubblico. |
| Eventi | PARZIALE | Esiste un audit delle modifiche, non un event stream di dominio versionato. |

Nota operativa: l'esposizione del Plugin Workforce dipende dal relativo feature flag. L'audit conferma il contratto nel codice, non lo stato della variabile nell'ambiente Railway.

### 4.5 Fleet

**Dati pubblicati**

- Asset Registry;
- stato e disponibilità osservata;
- capability;
- documenti;
- eventi cronologici;
- preview e risultato della sincronizzazione;
- proiezione Core di Resource Availability.

**Consumabile dal Planning Workspace**

- identificativo Asset, targa, categoria, stato e capability;
- disponibilità osservata;
- eventi e aggiornamento come contesto di freschezza, senza dedurne decisioni;
- documenti solo quando il backend pubblica già una conseguenza operativa, non tramite regole client-side.

**Da non consumare**

- note e documenti non necessari alla pianificazione;
- `FleetBriefingSnapshot` tramite accesso interno;
- driver osservato come assegnazione autorevole;
- risultato del matching/import come regola di planning;
- stato di manutenzione come workflow completo, perché tale Plugin non esiste ancora.

**Dati mancanti o incompleti**

- Operational Unit sull'Asset e sulle availability pubbliche;
- data di validità e versione dello snapshot di disponibilità;
- compatibilità capability tra Asset e Task;
- associazione neutrale e pubblica del driver osservato;
- integrazione diretta del Fleet Plugin negli input Planning.

#### Classificazione Fleet

| Voce | Stato | Motivo |
|---|---|---|
| Asset | ESISTE | Il modello è pubblico, tipizzato e parte del Registry. |
| Availability | PARZIALE | La proiezione Core è pubblica, ma non è scoped o versionata per il piano. |
| Registry | ESISTE | Lista e dettaglio Asset sono pubblici. |
| Documenti | ESISTE | Il modello e le operazioni documentali sono pubblici. |
| Maintenance | PARZIALE | Esistono stato ed eventi di manutenzione, non il futuro Maintenance Plugin. |
| Eventi | ESISTE | Gli Asset Events sono cronologici, tipizzati e pubblici. |
| Driver osservato | PARZIALE | È conservato nei metadati di sync legacy, non nel contratto pubblico Asset. |
| Capability | ESISTE | Le capability configurabili sono pubblicate sull'Asset. |

### 4.6 Mission Control

**Dati consumati**

- `DailyOperationsBriefing`;
- `WorkspaceStatusResponse`.

**Snapshot usati**

- stato generale e azioni dal briefing;
- fatti sintetici Workforce, Fleet e Planning dal briefing;
- conteggi e timestamp del Workspace Lifecycle;
- timeline sintetizzata nel frontend da timestamp disponibili.

**Contratti usati**

- `/api/briefing/v1/daily/latest` e generazione briefing;
- `/api/workspace/v1/status`;
- stato interno `MissionControlView` derivato nel frontend.

**Consumabile dal Planning Workspace**

- nessun contratto Mission Control deve essere usato come fonte autorevole;
- il Workspace Status può essere interrogato direttamente dal suo proprietario per l'empty state globale, non attraverso lo stato derivato di Mission Control.

**Da non consumare**

- azioni temporanee ricostruite nel frontend;
- timeline sintetizzata nel frontend;
- snapshot di modulo come sostituti dei contratti Workforce, Fleet e Planning;
- selezione Operational Unit oggi disabilitata come se fosse uno scope operativo applicato.

**Dati mancanti o incoerenti**

- Mission Control richiede `coverage.absences`, non pubblicato nel fatto Workforce corrente del briefing;
- Mission Control richiede `available_assets`, non presente nello snapshot Fleet corrente;
- il selettore Operational Unit è predisposto ma non applica ancora uno scope.

### 4.7 Workbook Profiler

**Dati pubblicati**

- fogli, intestazioni, righe di esempio e classificazione workbook;
- mapping riconosciuti, da verificare e non riconosciuti;
- issue di profiling;
- risultato import, mapping e righe normalizzate.

**Contratti pubblici**

- `ImportPreviewResponse`;
- `ImportResultResponse`.

**Consumabile dal Planning Workspace**

- riferimento all'import sorgente;
- timestamp e stato dell'import;
- conteggio righe come metadato di input.

**Da non consumare**

- nome file, foglio, intestazioni e confidence come stato operativo;
- righe raw o sample come entità di dominio;
- classificazione workbook come readiness;
- alias specifici dell'Adapter.

**Dati mancanti**

- envelope versionato che colleghi un import agli input effettivamente usati da una versione del planning;
- scope Operational Unit uniforme nel risultato di import.

### 4.8 Configuration Engine

**Valori configurabili oggi**

- nomenclature Core;
- cataloghi capability;
- stati Asset;
- livelli di severità;
- livelli readiness;
- policy di riserva generale e per Operational Unit;
- priorità;
- soglie e mapping generici;
- stati e mapping Workforce;
- mapping turni Workforce;
- mapping di disponibilità, colonne, alias sensibili e comportamenti del Fleet Registry.

**Contratti pubblici**

- configurazione corrente con metadati di risoluzione e fallback;
- elenco versioni;
- validazione;
- creazione di una nuova versione.

**Consumabile dal Planning Workspace**

- versione configurazione associata al contesto;
- nomenclature e valori già risolti dal backend;
- policy pubblicate come dati descrittivi.

**Da non consumare**

- applicazione di regole di configurazione nel frontend;
- mapping verticali Amazon;
- valori di default del codice importati direttamente dai moduli Python;
- configurazione come sostituto del risultato calcolato dal Core.

**Hardcoded ancora presenti fuori dal flusso effettivo di configurazione**

- flag, limiti e stati bloccanti di `PlanningConfiguration`;
- soglia riserva predefinita negli endpoint Operations;
- enum di stato e sorgente Assignment;
- codici e regole Conflict;
- transizioni Planning e readiness;
- pesi e regole delle raccomandazioni del Briefing;
- stati e azioni del Workspace Lifecycle;
- selezione dell'Adapter attivo e unità note del catalogo Amazon.

I safe default dichiarativi del Configuration Engine non sono considerati automaticamente debito: il limite è costituito dai valori operativi usati da servizi che non interrogano il Configuration Engine.

### 4.9 Workspace Lifecycle

**Stati esposti**

- `EMPTY`;
- `DEMO`;
- `PRODUCTION`.

**Dati pubblicati**

- flag demo;
- riferimenti agli ultimi import planning e fleet;
- conteggi task, asset, persone, planning e briefing;
- ultimo aggiornamento;
- azioni disponibili.

**Consumabile dal Planning Workspace**

- rilevamento di workspace vuoto;
- presenza grossolana degli input;
- distinzione demo/production;
- timestamp di aggiornamento come informazione, non come garanzia di coerenza.

**Da non consumare**

- conteggi aggregati per decidere readiness o capacity;
- azioni generiche come comandi Planning;
- ultimo import come prova che è quello usato dalla versione visualizzata.

**Dati mancanti**

- scope per Operational Unit e data;
- relazione esplicita con una versione del planning;
- stato del ciclo di vita Planning fino alla pubblicazione.

### 4.10 Daily Operations Briefing

**Dati utilizzati**

- planning e relativa versione;
- Configuration version;
- dashboard Operations quando coerente con gli import del planning;
- capacity del Planning come fallback;
- snapshot interni Workforce e Fleet;
- metriche, limitazioni e source reference.

**Contratto pubblico**

- `DailyOperationsBriefing`, versionato come contratto `1.0`, con revision, fingerprint, data, planning, configuration, organization, Operational Unit, attention, readiness, capacity, metriche, sezioni, raccomandazioni, riferimenti sorgente e limitazioni.

**Consumabile dal Planning Workspace**

- solo come contesto informativo e prova storica del briefing generato;
- non come sorgente primaria di assegnazioni, conflitti o readiness.

**Da non consumare**

- snapshot persistito come stato live;
- raccomandazioni come decisioni già approvate;
- fallback capacity come contratto Planning completo;
- dati Plugin ottenuti tramite accoppiamento interno come API stabile.

**Dipendenze e limiti**

- dipende direttamente da servizi interni Fleet e Workforce invece che da porte pubbliche versionate;
- può dichiarare readiness non disponibile quando gli import o la soglia non coincidono;
- dichiara esplicitamente l'assenza della verifica di compatibilità capability;
- appartiene a Mission Control e non al Planning Engine.

### 4.11 Amazon Adapter

**Dati e mapping gestiti**

- alias colonne verticali;
- mapping di route, station, wave, cycle, vehicle e driver verso concetti Core;
- mapping eventi Amazon;
- catalogo di unità riconosciute;
- normalizzazione richiesta dalla pipeline import.

**Contratti pubblici**

Nessuna API pubblica dedicata. `TabularImportAdapter` è un protocollo interno; catalogo e mapping Amazon sono interni all'Adapter.

**Consumabile dal Planning Workspace**

- esclusivamente l'output già normalizzato e pubblicato dal Core o dal Planning Engine.

**Da non consumare**

- alias Amazon;
- catalogo station;
- mapping eventi verticali;
- riconoscimento wave/cycle;
- registry dell'Adapter attivo.

**Dati mancanti o debito rilevato**

- selezione dinamica dell'Adapter;
- separazione delle Operational Unit del cliente dal catalogo verticale globale;
- configurazione di istanza dell'Adapter per organizzazione e unità.

## 5. Matrice Planning Workspace

Legenda:

- **VERDE**: contratto pubblico direttamente utilizzabile oggi;
- **GIALLO**: contratto o dato presente, ma non sufficiente come fonte autorevole;
- **ROSSO**: contratto assente.

| Contratto richiesto dal Planning Workspace | Stato | Fonte reale oggi | Vincolo rilevato | PW |
|---|---|---|---|---|
| Readiness | **GIALLO** | Operations Core / Briefing | Non sempre legata a planning ID, versione, data e OU | PW-2 |
| Conflict | **VERDE** | `PlanningConflict` nel Planning bundle | Mancano provenienza tipizzata e categoria di verifica | PW-3 |
| Assignment | **VERDE** | `Assignment` nel Planning bundle | Linguaggio pubblico ancora legacy, come previsto dalla migrazione | PW-4-PW-6 |
| Availability | **GIALLO** | Workforce e Fleet core contracts | Scope, versione, freschezza e integrazione Planning incompleti | PW-2 |
| Capability | **GIALLO** | WorkforceMember e Asset | Cataloghi presenti, esito di compatibilità assente | PW-2-PW-3 |
| Asset | **GIALLO** | Fleet Asset Registry | Pubblico ma non scoped per OU/data né usato direttamente dal Planning | PW-2-PW-4 |
| Human Resource | **GIALLO** | Workforce member/core contract | Pubblico ma non integrato come input Planning versionato | PW-2-PW-4 |
| Operational Unit | **GIALLO** | Core model, config scope, station legacy | Nessun contratto trasversale uniforme e obbligatorio | PW-1 |
| Task | **GIALLO** | Core model interno e route legacy pubblica | Nessuna proiezione pubblica neutrale dei task del piano | PW-4 |
| Version | **VERDE** | `OperationalPlanning.version` e history | Nessuna precondizione client sulle modifiche concorrenti | PW-5-PW-7 |
| Publication | **ROSSO** | Nessuna | Stato, comando e risultato assenti | PW-7 |
| Decision | **GIALLO** | Alternative e raccomandazioni locali | Nessun `DecisionProposal` canonico | PW-8 gate / Fase 6 |

### 5.1 Calcolo del Readiness Score

Metodo dichiarato:

- VERDE = 2 punti;
- GIALLO = 1 punto;
- ROSSO = 0 punti.

Risultato:

- 3 contratti VERDI = 6 punti;
- 8 contratti GIALLI = 8 punti;
- 1 contratto ROSSO = 0 punti;
- totale = 14 punti su 24;
- score normalizzato = **58/100**.

Il punteggio indica che il Workspace può leggere una parte consistente dello stato corrente, ma non può ancora completare in modo contrattualmente sicuro l'intero ciclo input-readiness-correzione-conferma-pubblicazione.

## 6. Gap Analysis

### 6.1 Gap critici

| ID | Gap | Perché manca oggi | Impatto | Quando | PW |
|---|---|---|---|---|---|
| GC-01 | Readiness autorevole per piano | Il Core Operations può analizzare gli ultimi import indipendentemente dalla versione Planning aperta | Il Workspace potrebbe mostrare uno stato riferito a input diversi | Prima della schermata readiness | PW-2 |
| GC-02 | Planning input envelope | Planning legge import normalizzati legacy; Workforce e Fleet pubblicano contratti separati non acquisiti come set versionato | Non è dimostrabile quali risorse abbiano prodotto il piano | Prima di rendere gli input autorevoli | PW-2 |
| GC-03 | Operational Unit uniforme | Coesistono `station`, modello Core e scope configurazione senza identità trasversale unica | Latest, availability e capacity possono riferirsi a scope diversi | Prima del context selector definitivo | PW-1 |
| GC-04 | Concorrenza sulle modifiche draft | Le patch non richiedono la versione attesa dal client | Due sessioni possono modificare lo stesso piano senza rilevare una base obsoleta | Prima delle correzioni draft complete | PW-5 |
| GC-05 | Conferma atomica | La UI esistente conferma assegnazioni con patch sequenziali | La conferma può essere parziale e non rappresenta un unico atto operativo | Prima del flusso conferma | PW-6 |
| GC-06 | Pubblicazione | Non esistono stato, comando, risultato o evento di pubblicazione | Il ciclo di vita progettato non può essere completato | Prima dello storico finale | PW-7 |

### 6.2 Gap importanti

| ID | Gap | Perché manca oggi | Impatto | Quando | PW |
|---|---|---|---|---|---|
| GI-01 | Availability scoped e versionata | I Plugin pubblicano stato osservato, non un input set con OU, data, versione e freschezza uniformi | Disponibilità non attribuibile con certezza al piano | Input e readiness | PW-2 |
| GI-02 | Capability compatibility | Capability Asset e Workforce sono catalogate, ma nessun contratto pubblica il confronto con il Task | I conflitti di compatibilità non possono essere mostrati come esito Core | Conflitti | PW-3 |
| GI-03 | Provenienza tipizzata dei conflitti | `PlanningConflict` non identifica in modo uniforme modulo sorgente e categoria di verifica | Filtri e spiegazioni cross-module restano limitati | Conflitti | PW-3 |
| GI-04 | Proiezione neutrale del piano | Il payload pubblico usa route, driver, vehicle e station; i modelli Core neutrali restano interni | Il nuovo Workspace dipenderebbe dal vocabolario legacy | Proposta Planning | PW-4 |
| GI-05 | Storico Planning tipizzato | Versioni, eventi e modifiche sono collezioni generiche e la pubblicazione non esiste | Timeline e audit non hanno un ciclo uniforme | History | PW-7 |
| GI-06 | Configurazione Planning effettiva | Molti default Planning e Operations non passano dal Configuration Engine | La versione config non descrive tutte le regole usate | Readiness e input | PW-2 |
| GI-07 | Workforce core contract completo | La proiezione è non versionata, condizionata dal feature flag e la coverage perde lo scope OU | Il Planning non dispone di un contratto stabile di staffing | Input | PW-2 |
| GI-08 | Confine driver osservato Fleet | Il driver osservato vive nei metadati sync legacy e non nel contratto Asset | Un consumer potrebbe confonderlo con un'assegnazione Workforce | Proposta e boundary QA | PW-4 |

### 6.3 Gap futuri

| ID | Gap | Perché è futuro | Fase reale | Relazione con PW |
|---|---|---|---|---|
| GF-01 | `DecisionProposal` canonico | Il Decision Engine autonomo non fa parte della Fase 3 | Fase 6 / DS-1 | PW-8 deve solo verificare che il Workspace non inventi decisioni |
| GF-02 | Porte Plugin pubbliche per il Briefing | Il Briefing richiama snapshot interni Fleet e Workforce | Debito Fase 3 / confini Plugin | PW-1 verifica il boundary, senza usare il Briefing come input Planning |
| GF-03 | Timeline operativa completa | Oggi esistono storico Planning ed eventi separati, non una timeline trasversale | Fase 5 | PW-7 usa solo lo storico Planning realmente disponibile |
| GF-04 | Selezione dinamica Adapter | L'Adapter Amazon è registrato come attivo e il catalogo contiene unità globali | Fase 10 | PW-1 non deve esporre concetti Adapter nello scope OU |

## 7. Associazione completa PW-1 - PW-8

Questa associazione non propone implementazioni. Indica quali condizioni contrattuali devono risultare vere prima che il relativo micro-sprint possa essere considerato pronto.

| PW | Ambito già progettato | Contratti oggi disponibili | Gap da chiudere o verificare |
|---|---|---|---|
| PW-1 | Shell, contesto e page state | Planning latest, Workspace Status, planning data/station | GC-03; verificare GF-02 e GF-04 come confini |
| PW-2 | Readiness e input | Operations readiness/capacity, Workforce e Fleet contracts, config | GC-01, GC-02, GI-01, GI-06, GI-07 |
| PW-3 | Conflitti | `PlanningConflict`, `OperationalIssue`, capability catalog | GI-02, GI-03 |
| PW-4 | Proposta Planning responsive | Planning bundle, Assignment, alternatives | GI-04, GI-08 |
| PW-5 | Correzioni draft | Assignment patch, recalc, simulation e diff, version | GC-04 |
| PW-6 | Conferma | Assignment confirmation singola | GC-05 |
| PW-7 | Pubblicazione e storico | Version history, changes ed events parziali | GC-06, GI-05; limitare GF-03 allo storico Planning |
| PW-8 | QA operativo | Tutti i contratti precedenti | Verifica finale dei boundary; GF-01 resta DS-1/Fase 6 |

### PW consigliati

L'ordine progettato PW-1 -> PW-8 resta coerente, ma lo stato reale impone i seguenti gate:

1. **PW-1** può iniziare solo usando contesto e stati realmente pubblicati, senza trattare `station` come Operational Unit canonica.
2. **PW-2** è il primo gate sostanziale: readiness e input non sono ancora sufficientemente correlati al piano.
3. **PW-3** può usare i conflitti esistenti, dichiarando assente la compatibilità capability finché il Core non la pubblica.
4. **PW-4** dispone già di Assignment e alternative, ma resta sul contratto legacy finché non esiste una proiezione neutrale pubblica.
5. **PW-5** richiede una garanzia di versione prima di supportare correzioni concorrenti affidabili.
6. **PW-6** è bloccato dall'assenza di una conferma atomica del planning.
7. **PW-7** è bloccato dall'assenza della pubblicazione; lo storico attuale è solo parziale.
8. **PW-8** deve validare contratti, accessibilità e boundary; non deve anticipare il Decision Engine della Fase 6.

## 8. Dati ammessi e dati vietati per Planning Workspace

### Dati ammessi oggi

- Planning bundle restituito dal Planning Engine;
- assegnazioni, alternative e conflitti già calcolati dal backend;
- stato e versione del planning;
- riepilogo, capacità e metadati di generazione con le limitazioni dichiarate;
- Workspace Status per empty/demo/production state;
- contratti pubblici Workforce e Fleet, solo per i campi e gli scope che dichiarano realmente;
- configurazione corrente e relativa versione;
- riferimenti import come provenienza tecnica degli input.

### Dati da non consumare

- stato derivato del frontend Mission Control;
- timeline sintetizzata nel browser;
- snapshot interni Fleet o Workforce;
- dettagli Amazon Adapter;
- dati raw del workbook come dominio;
- Daily Briefing come fonte autorevole del piano;
- driver osservato dal Fleet come assegnazione Workforce;
- conteggi Workspace Lifecycle come capacity o readiness;
- configurazioni hardcoded importate nel frontend;
- inferenze client-side per capability, conflitti, readiness, conferma o pubblicazione.

## 9. Rischi architetturali

| Rischio | Evidenza | Effetto possibile | Severità |
|---|---|---|---|
| Doppia fonte degli input | Planning usa import legacy mentre Plugin pubblicano registry e availability | Divergenza tra Workspace e piano generato | Critica |
| Readiness non correlata | Operations latest e Planning version possono riferirsi a snapshot diversi | Stato giornata non affidabile per il piano aperto | Critica |
| Operational Unit frammentata | `station`, Core model, config scope e briefing IDs non formano un contratto unico | Dati di unità differenti possono essere aggregati | Critica |
| Conferma non atomica | Conferme assignment sequenziali | Stato parzialmente confermato dopo errore o interruzione | Critica |
| Pubblicazione assente | Nessun contratto di publication | Ciclo operativo incompleto | Critica |
| Accoppiamento Briefing-Plugin | Import diretto di servizi e snapshot interni | Evoluzione dei Plugin può rompere Mission Control | Importante |
| Migrazione linguistica incompleta | Core neutrale interno, payload Planning legacy | Il nuovo Workspace rischia di consolidare il legacy | Importante |
| Configurazione non applicata ovunque | Planning e Operations conservano default propri | Versione config non spiega integralmente il risultato | Importante |
| Decisioni distribuite | Alternative e recommendation appartengono a moduli diversi | Semantica decisionale incoerente se aggregata dal frontend | Importante |
| Adapter attivo statico | Registry Amazon non dinamico | Scope multi-organizzazione non ancora generalizzabile | Futuro |

## 10. Conclusioni PW-0

### 10.1 Contratti trovati

- 44 famiglie di contratto esistenti censite;
- 12 righe della matrice Planning Workspace valutate;
- 3 contratti direttamente pronti: Conflict, Assignment e Version;
- 8 contratti parziali;
- 1 contratto completamente assente nella matrice: Publication.

### 10.2 Contratti mancanti

I dieci contratti o capacità contrattuali mancanti principali sono:

1. input envelope versionato del planning;
2. readiness scoped e vincolata alla versione;
3. Operational Unit trasversale;
4. compatibility result;
5. conferma atomica;
6. pubblicazione;
7. precondizione di versione sulle modifiche;
8. Decision Proposal canonica;
9. proiezione pubblica neutrale del piano;
10. eventi tipizzati di conferma e pubblicazione.

### 10.3 Valutazione finale

Il repository dispone di una base Planning concreta e pubblica, ma Planning Workspace non può ancora utilizzare tutti i contratti previsti dal prodotto come fonti autorevoli. La priorità contrattuale è rendere coerenti contesto, input e readiness; seguono concorrenza, conferma e pubblicazione. Le decisioni suggerite restano correttamente fuori da PW-1-PW-7 e appartengono alla futura Fase 6.

**Planning Workspace Readiness Score: 58/100.**

### 10.4 Dichiarazioni di non modifica

- Nessun file frontend è stato modificato.
- Nessun file backend è stato modificato.
- Nessuna API è stata modificata.
- Nessun database o dato è stato modificato.
- Nessun test è stato modificato.
- Nessuna configurazione, roadmap, README o documentazione esistente è stata modificata.
- Nessun codice è stato creato.
- Nessun commit è stato eseguito.
- Nessun push o deploy è stato eseguito.
- L'unico artefatto creato da PW-0 è questo inventario documentale.
