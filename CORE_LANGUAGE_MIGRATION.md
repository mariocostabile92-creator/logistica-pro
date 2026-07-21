# Core Language Migration

## Stato

- **Fase:** ponte di compatibilita' v1
- **Ambito:** linguaggio interno del dominio
- **Comportamento pubblico:** invariato
- **Documenti vincolanti:** [Operations Engine Philosophy](OPERATIONS_ENGINE_PHILOSOPHY.md),
  [Core, Adapter e Plugin Boundaries](CORE_ADAPTER_PLUGIN_BOUNDARIES.md),
  [Operational Unit Model](OPERATIONAL_UNIT_MODEL.md) e
  [Amazon Adapter](AMAZON_ADAPTER.md)

Questo documento definisce l'inizio della migrazione dal vocabolario verticale
esistente al linguaggio neutrale di Operations Engine.

La migrazione non e' una rinomina globale. Il vecchio linguaggio continua a
esistere nei contratti pubblici, nella persistenza e nel Planning. Il nuovo
linguaggio viene introdotto in parallelo e adottato solo dove il passaggio e'
verificabile e reversibile.

## Principio di convivenza

```text
Contratto legacy
  -> mapper di compatibilita'
  -> modello Core neutrale
  -> logica interna
  -> mapper di compatibilita'
  -> contratto legacy
```

In questa fase i mapper non normalizzano, correggono o reinterpretano gli
identificativi. Devono conservarli esattamente per garantire il round-trip.

## Concetti introdotti

| Concetto Core | Responsabilita' |
| --- | --- |
| `Task` | riferimento neutrale a un'unita' di lavoro |
| `OperationalUnit` | perimetro operativo o organizzativo |
| `HumanResource` | riferimento a una risorsa umana |
| `AssetReference` | riferimento a una risorsa materiale |
| `TimeWindow` | riferimento a una finestra temporale |
| `TaskCancellationEvent` | fatto di cancellazione relativo a un Task |
| `ResourceAvailability` | disponibilita' osservata di una Resource |

I modelli sono value object Pydantic immutabili. Non importano API, database,
Adapter, Plugin, repository, servizi o modelli legacy.

`TaskCancellationEvent` e `ResourceAvailability` sono contratti neutrali
pronti per fasi successive. Non sono ancora collegati al Planning o al Fleet
Plugin.

## Mapping di compatibilita'

| Linguaggio legacy | Mapper | Linguaggio Core |
| --- | --- | --- |
| route | `RouteMapper` | `Task` |
| station | `StationMapper` | `OperationalUnit` |
| driver | `DriverMapper` | `HumanResource` |
| vehicle / plate | `VehicleMapper` | `AssetReference` |
| cycle / wave | `CycleMapper` | `TimeWindow` |

Ogni mapper espone:

```text
to_core(legacy) -> Core model
to_legacy(Core model) -> legacy
```

La garanzia richiesta e':

```text
to_legacy(to_core(value)) == value
```

La stessa garanzia vale per `None` e per la stringa vuota, che continuano a
rappresentare un riferimento assente.

## Struttura

```text
backend/app/domain/core_language/
  __init__.py
  models.py
  mappers/
    __init__.py
    route_mapper.py
    station_mapper.py
    driver_mapper.py
    vehicle_mapper.py
    cycle_mapper.py
```

I termini legacy sono ammessi nei mapper perche' rappresentano il confine di
compatibilita'. Non devono entrare nei modelli Core.

## Componenti gia' migrati

### Conflict service

`conflict_service.py` usa gia' proiezioni neutrali per:

- identita' dei Task durante conteggio e rilevamento multi-route;
- identita' delle Operational Unit durante il riconoscimento;
- identita' delle Human Resource durante i confronti driver;
- identita' degli Asset durante i confronti vehicle/plate.

Codici conflitto, severita', messaggi, entity reference e payload restano
legacy e invariati.

### Test architetturali

I guardrail verificano che:

- il package Core Language non dipenda dai modelli legacy;
- il Domain non dipenda da livelli esterni;
- il conflict service consumi esplicitamente il ponte Core Language.

## Componenti ancora legacy

Restano intenzionalmente invariati:

- `NormalizedPlanningRow` e `NormalizedFleetRow`;
- `Assignment` e `AssignmentAlternative`;
- `OperationEventType` e `OperationEntityType`;
- Planning generation, ricalcolo, simulazione ed export;
- payload e schemi HTTP;
- endpoint e query parameter;
- tabelle, colonne e JSON persistiti;
- repository e snapshot esistenti;
- Fleet Plugin;
- Amazon Adapter;
- Configuration Engine;
- Decision Engine;
- Readiness e Capacity;
- frontend e nomenclature visibili.

`CycleMapper` e' testato ma non ancora usato da un consumer di produzione:
il consumer corrente e' il Planning, escluso dal perimetro di questa fase.

## Strategia futura

### Passo 1 - Proiezioni neutrali

Introdurre proiezioni Core in lettura nei servizi che possono adottarle senza
modificare output o persistenza.

### Passo 2 - Contratti applicativi neutrali

Creare comandi e risultati interni basati su Task, Resource, Asset e
Operational Unit. Router e repository continueranno a tradurre verso i
contratti legacy.

### Passo 3 - Planning interno neutrale

Migrare l'algoritmo di Planning soltanto dopo avere test di equivalenza su:

- assegnazioni;
- alternative;
- conflitti;
- capacity;
- readiness;
- eventi e ricalcolo;
- export.

### Passo 4 - Eventi neutrali

Tradurre `route_aborted`, `vehicle_unavailable` e `driver_absent` in eventi
Core attraverso mapper versionati, mantenendo gli enum pubblici correnti.

### Passo 5 - Persistenza e API

Valutare nuove versioni dei contratti solo dopo la migrazione interna. Nessuna
rinomina di database o HTTP deve avvenire come effetto collaterale.

## Regole della migrazione

- Nessuna sostituzione globale di termini.
- Nessun alias di campo dentro i modelli Core.
- Nessuna dipendenza Core verso Adapter o Plugin.
- Ogni mapper deve essere bidirezionale e coperto da test.
- Ogni adozione interna deve mantenere gli stessi risultati legacy.
- Nessun dato deve essere normalizzato silenziosamente dal mapper.
- I modelli legacy si rimuovono solo dopo una migrazione versionata.
- Le API restano un confine di compatibilita', non il linguaggio del Core.

## Rischi

### Doppio modello

Durante la convivenza esiste il rischio che modello legacy e modello Core
evolvano in modo divergente. I test round-trip e i mapper centralizzati sono
il controllo principale.

### Semantica incompleta

Un `cycle` o una `wave` sono oggi identificativi testuali. Non rappresentano
ancora un intervallo temporale completo. `TimeWindow` conserva quindi
l'identificativo senza inventare orari.

### Identificativi

I mapper v1 conservano gli identificativi byte per byte. Normalizzazione,
deduplicazione e canonicalizzazione restano responsabilita' dei confini gia'
esistenti.

### Migrazione parziale

La presenza dei nuovi modelli non implica che Planning, eventi, API o database
siano gia' neutrali. La documentazione e i test devono continuare a
distinguere componenti migrati e componenti legacy.

## Criterio di completamento futuro

La migrazione del linguaggio potra' dirsi completa solo quando:

1. i servizi Core useranno esclusivamente concetti neutrali;
2. Adapter e interfacce tradurranno i contratti esterni;
3. Plugin consumeranno soltanto porte Core;
4. Planning e Decision Engine non conosceranno route, station, vehicle o
   driver come concetti primari;
5. API e persistenza legacy saranno mantenute da mapper versionati oppure
   sostituite tramite una migrazione pubblica dichiarata.
