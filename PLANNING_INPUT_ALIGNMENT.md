# Planning Input Alignment

## Stato del documento

| Campo | Valore |
|---|---|
| Sprint | PW-1 |
| Ambito | Planning Input Layer di dominio |
| Owner | Core Operations e Planning |
| Contratto | `1.0` |
| Comportamento prodotto | Invariato |
| Integrazione runtime | Non attiva |

Questo documento descrive il layer di dominio introdotto da PW-1. Il layer prepara il passaggio futuro dagli import normalizzati legacy ai contratti pubblici Workforce e Fleet, ma non modifica il flusso di generazione corrente.

Riferimenti vincolanti:

- `OPERATIONS_ENGINE_VISION.md`;
- `OPERATIONS_ENGINE_ROADMAP.md`;
- `CORE_ADAPTER_PLUGIN_BOUNDARIES.md`;
- `OPERATIONAL_UNIT_MODEL.md`;
- `PLANNING_WORKSPACE_PRODUCT_CONTRACT.md`;
- `PLANNING_WORKSPACE_CONTRACT_INVENTORY.md`.

## 1. Problema confermato

Il Planning Engine corrente risolve gli ultimi import planning e fleet, ricostruisce `NormalizedPlanningRow` e `NormalizedFleetRow` e li passa ai servizi di generazione.

```text
Dataset normalizzati legacy
  -> Planning Generation Service
  -> Planning corrente
```

Workforce e Fleet pubblicano già parte dei concetti necessari, ma il Planning non li acquisisce come un insieme scoped, versionato e verificabile. Prima di cambiare il motore serve un contratto Core indipendente dai modelli interni dei Plugin.

PW-1 introduce quel contratto senza collegarlo al runtime:

```text
Workforce public contract --+
                            |
                            +--> Planning Input Contract
Fleet public contract ------+        -> Validation
                                     -> Snapshot
                                     -> Envelope
                                     -> futuro Planning consumer
```

Le frecce dai Plugin descrivono la direzione futura dei dati. PW-1 non modifica i Plugin e non implementa ancora la composizione.

## 2. Collocazione architetturale

Il layer vive in:

```text
backend/app/domain/planning_inputs/
  __init__.py
  models.py
  validation.py
```

La collocazione nel dominio Core è motivata da quattro proprietà:

1. rappresenta l'invariante generale con cui Planning riceve input;
2. usa esclusivamente linguaggio neutrale;
3. non possiede il ciclo di vita di Workforce o Fleet;
4. non traduce formati o vocaboli esterni.

Non sono stati creati repository, servizi applicativi o adapter. Nessuno di questi livelli avrebbe oggi una responsabilità reale: l'envelope non è persistito, non è esposto via API e non è ancora consumato dal Planning Engine.

## 3. Contratti introdotti

### 3.1 Contratti principali

| Contratto | Responsabilità |
|---|---|
| `PlanningInputContract` | Associa metadati, payload neutrale e dipendenze di un singolo producer. |
| `PlanningInputEnvelope` | Raggruppa snapshot Workforce e Fleet riferiti allo stesso scope. |
| `PlanningInputSnapshot` | Conserva un input immutabile insieme all'esito della sua validazione. |
| `PlanningInputSource` | Dichiara producer, nome e versione del contratto, riferimento, provenienza e istante di produzione. |
| `PlanningInputFreshness` | Dichiara istante osservato e scadenza dell'input. |
| `PlanningInputScope` | Identifica organizzazione, Operational Unit e data operativa. |
| `PlanningInputVersion` | Dichiara versione sorgente e sequenza opzionale. |
| `PlanningInputMetadata` | Compone tipo, source, scope, versione e freshness. |
| `PlanningInputValidation` | Pubblica stato, istante di verifica e issue rilevate. |
| `PlanningInputDependency` | Dichiara dipendenza, producer, obbligatorietà, soddisfacimento e versione. |

### 3.2 Value object di supporto

| Contratto | Responsabilità |
|---|---|
| `PlanningResourceCapability` | Collega una capability configurabile a una risorsa neutrale. |
| `PlanningCoverage` | Trasporta la coverage già prodotta da Workforce senza ricalcolarla. |
| `PlanningAssetRegistry` | Rappresenta l'insieme degli `AssetReference` pubblicati da Fleet. |
| `PlanningInputValidationIssue` | Spiega un problema di integrità, completezza, dipendenza o freshness. |

Tutti i modelli sono Pydantic, tipizzati, immutabili e serializzabili. Il contratto del layer è versionato come `1.0`.

## 4. Payload Workforce

`WorkforcePlanningInput` può trasportare:

- `HumanResource`;
- `ResourceAvailability` di tipo `human_resource`;
- capability delle Human Resource;
- coverage già calcolata dal Plugin;
- `TimeWindow`.

Il Core non importa `WorkforceMember`, `WorkforceDayStatus`, `WorkforceCoverage` o altri modelli interni del Plugin. Il futuro producer Workforce dovrà tradurre il proprio stato nel contratto Core.

Il Planning Input Layer:

- non crea persone;
- non modifica turni o assenze;
- non calcola coverage;
- non decide se una persona deve essere assegnata;
- non accede al repository Workforce.

## 5. Payload Fleet

`FleetPlanningInput` può trasportare:

- Registry di `AssetReference`;
- `ResourceAvailability` di tipo `asset`;
- capability configurabili degli Asset.

Il Core non importa `Asset`, `AssetDocument`, `AssetEvent` o modelli di sincronizzazione interni del Fleet Plugin. Il futuro producer Fleet dovrà pubblicare una proiezione Core senza trasferire note, documenti o dettagli non necessari al Planning.

Il Planning Input Layer:

- non modifica Asset;
- non cambia availability;
- non interpreta documenti o manutenzione;
- non usa il driver osservato come assegnazione;
- non accede al repository Fleet.

## 6. Operational Unit e scope

Ogni `PlanningInputContract` deve dichiarare un `PlanningInputScope` composto da:

- `organization_id`;
- `OperationalUnit` Core;
- `operation_date`.

Ogni `PlanningInputEnvelope` accetta esclusivamente snapshot con la stessa identità di scope. L'identità usa l'identificatore stabile della Operational Unit, non la label visualizzata.

PW-1 prepara una singola Operational Unit per envelope. Non implementa:

- selezione multi-unità;
- vista aggregata `Tutte`;
- registry organizzativo;
- gerarchie;
- autorizzazioni;
- migrazione di `station` nei payload o nel database.

`Tutte` non è rappresentata come Operational Unit fittizia.

## 7. Source, provenienza, versione e freshness

Ogni input dichiara obbligatoriamente:

| Informazione | Campo |
|---|---|
| Chi lo produce | `source.producer` |
| Quando è stato prodotto | `source.produced_at` |
| Operational Unit | `scope.operational_unit` |
| Organizzazione | `scope.organization_id` |
| Data operativa | `scope.operation_date` |
| Versione | `version.value` e `version.sequence` opzionale |
| Freshness | `freshness.observed_at` e `freshness.expires_at` |
| Stato | `validation.status` |
| Provenienza | `source.provenance` e `source.source_reference` |
| Tipo | `metadata.input_type` |

Gli istanti richiedono timezone esplicita. Le stringhe vuote vengono rifiutate. I modelli non leggono l'orologio di sistema: l'istante di valutazione viene passato esplicitamente, rendendo la classificazione deterministica e testabile.

## 8. Classificazione degli input

La validazione classifica la qualità del contratto. Non rappresenta la Planning Readiness e non autorizza conferma o pubblicazione.

| Stato | Significato nel Planning Input Layer |
|---|---|
| `READY` | Il contratto è integro, completo per il payload v1, non scaduto e senza dipendenze insoddisfatte. |
| `STALE` | L'intervallo di freshness è scaduto all'istante di valutazione. |
| `PARTIAL` | Il producer ha pubblicato l'input, ma una sezione o dipendenza opzionale è assente. |
| `MISSING` | Manca il contenuto principale o una dipendenza obbligatoria. |
| `INVALID` | Riferimenti, tipi di risorsa, duplicati o sequenza temporale sono incoerenti. |

La precedenza è:

```text
INVALID -> MISSING -> STALE -> PARTIAL -> READY
```

Le issue mantengono codice stabile, messaggio, campo coinvolto e indicazione bloccante. Nessuna issue viene convertita in conflitto Planning in PW-1.

## 9. Invarianti

1. Metadata e payload devono dichiarare lo stesso tipo di input.
2. Un envelope non può contenere due snapshot dello stesso tipo.
3. Tutti gli snapshot di un envelope condividono organizzazione, Operational Unit e data.
4. Gli identificatori di risorsa devono essere univoci nel proprio payload.
5. Availability e capability devono riferirsi a risorse presenti nel payload.
6. Il tipo di risorsa deve essere coerente con Workforce o Fleet.
7. `expires_at` non può precedere `observed_at`.
8. Tutti i timestamp sono timezone-aware.
9. Una dipendenza obbligatoria insoddisfatta produce `MISSING`.
10. I contratti sono immutabili dopo la validazione Pydantic.

## 10. Ownership e responsabilità

| Componente | Owner | Responsabilità attuale | Responsabilità esclusa |
|---|---|---|---|
| Planning Input models | Core | Linguaggio e invarianti neutrali | Lettura dei Plugin |
| Planning Input validation | Core | Integrità, completezza e freshness | Readiness e decisioni |
| Workforce data | Workforce Plugin | Verità su persone, turni e availability | Assignment e Planning |
| Fleet data | Fleet Plugin | Verità su Asset e availability | Assignment e Planning |
| Configuration data | Configuration Engine | Valori risolti e versionati | Codice eseguibile |
| Envelope composition | Non implementato | Futura composizione di contratti pubblici | Proprietà dei dati sorgente |
| Planning consumption | Non implementato | Futuro ingresso unico al Planning Engine | Modifica dei Plugin |

## 11. Dipendenze consentite

Il package dipende solo da:

- libreria standard;
- Pydantic;
- `app.domain.core_language`.

Sono vietate e assenti dipendenze da:

- `app.plugins`;
- `app.adapters`;
- `app.api`;
- `app.repositories`;
- `app.schemas`;
- `app.services`;
- FastAPI;
- database o file system.

Configuration Engine può essere dichiarato come producer di una dipendenza, ma PW-1 non lo interroga direttamente.

## 12. Compatibilità

### 12.1 Planning Engine attuale

Compatibilità completa. `planning_generation_service.py` continua a usare gli import e i modelli normalizzati esistenti. Nessuna firma, regola, query, persistenza o risposta è stata modificata.

Il nuovo layer non viene importato dal Planning Engine. Non esiste doppia esecuzione e non cambia il risultato del piano.

### 12.2 Workforce

Compatibilità completa. Nessun file Workforce è stato modificato. Il nuovo payload usa proiezioni Core e non importa modelli interni del Plugin.

Resta da implementare, in uno sprint successivo, la produzione effettiva di `WorkforcePlanningInput` attraverso un boundary pubblico versionato.

### 12.3 Fleet

Compatibilità completa. Nessun file Fleet è stato modificato. Asset e availability esistenti non vengono letti o trasformati in PW-1.

Resta da implementare, in uno sprint successivo, la produzione effettiva di `FleetPlanningInput` attraverso un boundary pubblico versionato.

### 12.4 Configuration Engine

Compatibilità completa. Nessun file Configuration è stato modificato. Versione e dipendenze sono rappresentabili, ma il layer non applica configurazioni o fallback.

### 12.5 API e database

Non sono stati creati endpoint, schemi HTTP, router, repository o tabelle. Il Planning Input Layer è un contratto interno Core pronto per una futura composizione applicativa.

## 13. Audit dei gap PW-0

### 13.1 Gap preparati a livello di dominio

| Gap PW-0 | Stato dopo PW-1 | Risultato |
|---|---|---|
| GC-02 Planning input envelope | Da ASSENTE a PARZIALE | Envelope, contract, snapshot, metadata e validation ora esistono nel Core; producer e consumer non sono collegati. |
| GC-03 Operational Unit uniforme | PARZIALE, migliorato | Ogni input ed envelope richiede uno scope Core stabile; il resto del sistema conserva ancora `station` e scope parziali. |
| GI-01 Availability scoped e versionata | PARZIALE, migliorato | Il contratto può trasportare availability dentro scope, versione e freshness; i Plugin non lo emettono ancora. |
| GI-07 Workforce core contract completo | PARZIALE, preparato | Esiste il target Core tipizzato; l'attuale endpoint Workforce non è stato modificato. |
| Doppia fonte degli input | Non risolto, boundary preparato | È definito il futuro punto unico di ingresso, ma il motore usa ancora gli import legacy. |

### 13.2 Gap risolti nel perimetro PW-1

- assenza di un modello Core `PlanningInputContract`;
- assenza di un `PlanningInputEnvelope` immutabile;
- assenza di source, provenance, version e freshness comuni;
- assenza di scope obbligatorio per gli input;
- assenza di una classificazione uniforme della qualità dell'input;
- assenza di dipendenze input esplicite;
- assenza di payload neutrali target per Workforce e Fleet.

### 13.3 Gap ancora aperti

- producer Workforce del contratto Core;
- producer Fleet del contratto Core;
- application orchestrator che compone l'envelope;
- persistenza o audit degli envelope, se richiesta da una fase futura;
- consumo del nuovo envelope nel Planning Engine;
- migrazione dai dataset legacy;
- readiness legata a planning ID, versione e input envelope;
- capability compatibility;
- proiezione Task neutrale;
- multi-unità e vista `Tutte`;
- concorrenza, conferma atomica e pubblicazione;
- Decision Proposal canonica.

## 14. Planning Workspace Readiness Score aggiornato

Il metodo PW-0 assegna:

- VERDE = 2;
- GIALLO = 1;
- ROSSO = 0.

La matrice operativa resta:

- 3 VERDI;
- 8 GIALLI;
- 1 ROSSO;
- **14/24 = 58/100**.

Il punteggio resta **58/100** perché misura contratti pubblici realmente consumabili dal Planning Workspace. PW-1 ha creato la fondazione Core, ma per vincolo non ha modificato i producer pubblici né il Planning Engine. Aumentare il punteggio prima dell'integrazione dichiarerebbe disponibile un flusso che oggi non è eseguito.

Il cambiamento verificabile è qualitativo: il gap dell'envelope passa da assenza totale a contratto Core parziale e testato.

## 15. Test e QA

I test di dominio coprono:

- contratto Workforce completo;
- contratto Fleet completo;
- Registry Asset e capability;
- source, scope, versione e provenienza;
- `READY`, `STALE`, `PARTIAL`, `MISSING`, `INVALID`;
- dipendenze obbligatorie e opzionali;
- mismatch tra metadata e payload;
- unicità dei tipi nell'envelope;
- incompatibilità tra Operational Unit;
- immutabilità;
- assenza di dipendenze verso livelli esterni;
- mancato consumo del layer da parte del Planning Engine corrente.

La QA di PW-1 è backend/domain-only. Non sono previste verifiche visuali perché nessuna UI è stata modificata.

## 16. Rischi residui

| Rischio | Stato |
|---|---|
| Il contratto resta inutilizzato | Intenzionale in PW-1; evita cambi di comportamento. |
| Plugin e Core possono divergere durante l'evoluzione | Da controllare con futuri contract test producer -> Core. |
| Freshness non usa ancora soglie Configuration | La scadenza è dichiarata dal producer; nessuna policy è stata inventata. |
| Lo scope non copre `Tutte` | Intenzionale; un aggregato non deve essere modellato come unità fittizia. |
| Planning continua a leggere import legacy | Gap noto e non modificabile in PW-1. |
| Il Readiness Score non aumenta | Coerente con l'assenza di integrazione pubblica e runtime. |

## 17. Dichiarazioni finali

- Nessuna UI, pagina, CSS, HTML o JavaScript è stata modificata.
- Mission Control è invariata.
- Workforce e Fleet sono invariati.
- Planning Engine e relativo comportamento sono invariati.
- Configuration Engine è invariato.
- API pubbliche e database sono invariati.
- README, roadmap e documentazione esistente sono invariati.
- Non sono stati eseguiti commit, push o deploy.
