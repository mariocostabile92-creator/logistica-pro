# Core, Adapter, Plugin and Configuration Boundaries

**Stato:** canonico e vincolante
**Ambito:** ownership, dipendenze e criteri di collocazione
**Costituzione:** [Operations Engine Philosophy](OPERATIONS_ENGINE_PHILOSOPHY.md)

## Modello architetturale

Core, Plugin, Adapter e Configuration sono responsabilità differenti. La
sequenza di prodotto può essere rappresentata come:

```text
Core
  -> capacità offerte dai Plugin
  -> integrazioni offerte dagli Adapter
  -> comportamento parametrizzato dalla configurazione cliente
```

Questa sequenza non è la direzione degli import software. La regola di
dipendenza è:

```text
Plugin ------> contratti Core <------ Adapter
                         ^
                         |
              Configuration Engine
```

Il Core non importa Plugin o Adapter. Plugin e Adapter non si importano tra
loro. La composizione avviene al bootstrap o in un application orchestrator
attraverso contratti pubblici.

## Core

### Responsabilità

Il Core possiede:

- linguaggio operativo neutrale;
- invarianti universali;
- contratti di Task, Resource, AssetReference e Operational Unit;
- Planning, Assignment, Conflict, Capacity e Readiness;
- Decision Proposal, Alternative e spiegabilità;
- contratti del Briefing e degli snapshot pubblici;
- eventi operativi neutrali;
- versionamento, idempotenza e audit generali;
- porte applicative consumabili da interfacce, Plugin e Adapter.

### Divieti

Il Core non deve conoscere:

- nomi di vettori, clienti o mercati;
- file, colonne o codici proprietari;
- Station, route o wave come concetti primari;
- UI, FastAPI, Railway o un database specifico;
- modelli interni di un Plugin;
- la presenza dell'Amazon Adapter;
- workflow configurabili di una singola organizzazione.

### Esempi corretti

- `TaskCancellationEvent` rappresenta una cancellazione neutrale.
- `OperationalUnit` rappresenta un perimetro operativo.
- Capacity confronta domanda e risorse senza conoscere un vettore.
- Readiness espone risultato, motivi e fonti.

### Esempi vietati

- `if adapter == "amazon"` dentro Planning.
- un elenco di Station cliente nel Core.
- una regola di assegnazione codificata con un nome di file.
- il Briefing Core che importa un repository concreto del Fleet Plugin.

## Plugin

### Responsabilità

Un Plugin possiede un dominio applicativo opzionale e separato. Può avere
modelli, application service, repository, importer e interfacce propri.

Plugin attuali:

- Workforce: persone, disponibilità, turni, assenze, copertura ed eventi;
- Fleet: ciclo di vita Asset, disponibilità, documenti, capability ed eventi.

Plugin futuri possibili includono Maintenance, Documents, Notifications,
Finance e Analytics.

### Regole

- Un Plugin comunica con il Core tramite contratti o eventi pubblici.
- Un Plugin pubblica snapshot piccoli, tipizzati e versionati.
- Un Plugin non decide Planning, Assignment, Capacity o Readiness.
- Un Plugin non dipende da un Adapter.
- Due Plugin non condividono direttamente repository o modelli interni.
- La disattivazione di un Plugin non corrompe lo stato Core.

### Esempi corretti

- Fleet pubblica disponibilità Asset e un `FleetBriefingSnapshot`.
- Workforce pubblica disponibilità Human Resource e copertura.
- Maintenance emette un evento di indisponibilità Asset.

### Esempi vietati

- Fleet assegna automaticamente un Asset a un Task.
- Workforce importa alias Amazon.
- Maintenance aggiorna direttamente le tabelle Planning.
- Fleet importa modelli interni Workforce.

## Adapter

### Responsabilità

Un Adapter è un livello anticorruzione verso una fonte, un sistema o un
vocabolario esterno. Possiede:

- alias e mapping esterni;
- interpretazione semantica della fonte;
- traduzione inbound e outbound;
- identificazione e versione del formato;
- provenienza e limiti della traduzione;
- test di contratto verso i concetti Core.

Amazon DSP è il primo Adapter. Un futuro Generic File Adapter, un ERP Adapter
o altri Adapter di vettore devono produrre gli stessi contratti neutrali.

### Regole

- Un Adapter dipende dai contratti Core, mai il contrario.
- Un Adapter non decide assegnazioni, readiness o capacity.
- Un Adapter non accede direttamente ai repository di un Plugin.
- Alias e codici cliente-specifici appartengono alla configurazione
  organizzativa, non al default globale dell'Adapter.
- Parser fisico e semantica Adapter restano separati.
- La selezione dell'Adapter avviene al composition boundary.

### Esempi corretti

- `route` viene tradotto in `Task`.
- `station` viene tradotto in `OperationalUnit`.
- un evento esterno di cancellazione produce `TaskCancellationEvent`.
- il parser XLSX restituisce celle; l'Adapter assegna il significato.

### Esempi vietati

- l'Adapter modifica direttamente un Assignment.
- l'Adapter contiene policy di riserva del cliente.
- il Core importa il catalogo Amazon.
- un elenco globale dell'Adapter pretende di rappresentare le unità di tutte le
  organizzazioni.

## Configuration Engine

### Responsabilità

Configuration è un servizio Core. Definisce valori versionati e risolti per:

- organizzazione;
- Operational Unit;
- Adapter;
- default piattaforma.

Può governare nomenclature, capability, stati, severità, readiness, policy di
riserva, priorità e mapping. Non contiene codice eseguibile e non sostituisce
le invarianti Core.

### Regole

- Il fallback è sicuro, esplicito e auditabile.
- Ogni valore dichiara origine e versione.
- La configurazione cliente non entra nel repository come dato hardcoded.
- Un Adapter può leggere il proprio scope configurato.
- Un Plugin può leggere sezioni pubbliche pertinenti al proprio dominio.
- Il Core non delega alla configurazione la validità delle invarianti.

## Flussi consentiti

### Inbound esterno

```text
Fonte esterna
  -> parser fisico
  -> Adapter selezionato
  -> contratto Core neutrale
  -> servizio applicativo
  -> eventuale Plugin proprietario
```

### Snapshot operativo

```text
Plugin
  -> snapshot pubblico versionato
  -> application orchestrator
  -> Briefing o Mission Control
```

### Configurazione

```text
Scope organizzazione/unità/Adapter
  -> Configuration Engine
  -> valore risolto con provenienza
  -> consumer autorizzato
```

## Checklist decisionale

Prima di collocare una capacità, rispondere in ordine:

1. È un'invariante valida in ogni settore? Se sì, Core.
2. Gestisce il ciclo di vita di un dominio opzionale? Se sì, Plugin.
3. Traduce una fonte o un vocabolario esterno? Se sì, Adapter.
4. Cambia per organizzazione senza cambiare codice? Se sì, Configuration.
5. Coordina contratti pubblici senza possederli? Application orchestration.
6. Presenta stato o raccoglie comandi? Interface.
7. Persiste o trasporta dati? Infrastructure.
8. Richiede un import inverso verso un livello esterno? Fermarsi e ridisegnare.

## Checklist per la review

- [ ] Il nome del concetto è neutrale nel Core.
- [ ] Il Core non importa Plugin o Adapter.
- [ ] Plugin e Adapter non dipendono direttamente tra loro.
- [ ] I contratti pubblici sono piccoli, tipizzati e versionati.
- [ ] Gli snapshot non espongono repository o modelli interni.
- [ ] Le policy cliente sono configurate, non hardcodate.
- [ ] La provenienza del dato è conservata.
- [ ] Le decisioni restano spiegabili e confermabili.
- [ ] Il frontend non ricostruisce logica di dominio.
- [ ] Rimozione o sostituzione del modulo non rompe il Core.
