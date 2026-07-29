# Amazon Adapter v1

## Stato

- **Tipo:** Adapter inbound della piattaforma Operations Engine
- **Versione contratto:** `1.0`
- **Adapter ID:** `amazon`
- **Stato:** attivo per gli import tabellari esistenti
- **Documenti vincolanti:** `OPERATIONS_ENGINE_PHILOSOPHY.md` e
  `ARCHITECTURE_ALIGNMENT_REPORT.md`

Amazon Adapter e' il livello anticorruzione tra il vocabolario Amazon e i
contratti neutrali di Operations Engine. Amazon non e' il prodotto e non
definisce il dominio Core.

## Responsabilita'

Amazon Adapter v1:

- possiede il catalogo degli alias dei file planning e fleet;
- possiede l'elenco base delle Operational Unit riconosciute;
- traduce station, route, wave, cycle, vehicle e driver;
- traduce abort, van down e driver no-show;
- dichiara i contratti futuri di yard, dispatch e scorecard;
- espone mapping tipizzati verso concetti Core;
- usa il Configuration Engine per estensioni organizzative degli alias;
- conserva i nomi di compatibilita' richiesti dalle API e dai modelli correnti;
- non modifica Planning, Fleet Plugin, Readiness, Capacity o Decision Engine.

Non decide assegnazioni, conflitti, capacita', readiness o disponibilita'.

## Flusso inbound

```text
File Excel/CSV
  -> parser tabellare condiviso
  -> Adapter attivo
  -> catalogo alias + configurazione organizzazione
  -> motore generico di matching
  -> campi di compatibilita'
  -> modelli normalizzati correnti
  -> Core / Planning
```

Il parser fisico legge righe e colonne. L'Adapter assegna la semantica. Il
normalizzatore generico calcola soltanto similarita', soglie e necessita' di
conferma.

## Mapping verso il Core

| Termine Amazon | Concetto Core | Campo compatibile v1 | Stato |
| --- | --- | --- | --- |
| route | Task | `route` | attivo |
| station | Operational Unit | `station` | attivo |
| wave | Time Window | `cycle` | attivo |
| cycle | Time Window | `cycle` | attivo |
| vehicle | Asset | `vehicle_plate` | attivo |
| driver | Human Resource | `driver_name` | attivo |
| yard | Resource Pool | nessuno | futuro |
| dispatch | Operation State Transition | nessuno | futuro |
| scorecard | Metric Observation | nessuno | futuro |

I campi compatibili restano necessari per non cambiare API, database,
Planning ed export esistenti. Non rappresentano il vocabolario Core definitivo.

## Mapping eventi

| Evento Amazon | Concetto Core | Evento compatibile v1 |
| --- | --- | --- |
| abort / route_abort | Task Cancellation Event | `route_aborted` |
| van_down | Asset Unavailable Event | `vehicle_unavailable` |
| driver_no_show | Human Resource Unavailable Event | `driver_absent` |

L'Adapter espone la traduzione, ma non applica gli eventi al Planning. La
simulazione e l'applicazione restano responsabilita' del Core corrente.

## Alias e configurazione

Gli alias predefiniti non sono dizionari hardcoded nei servizi. La fonte
versionata e dichiarativa e':

```text
backend/app/adapters/amazon/catalog.v1.json
```

Il Configuration Engine puo' aggiungere alias per organizzazione nello scope
`adapter_id = amazon`, usando `generic_mappings.mappings`.

Esempio di valore configurato:

```json
{
  "planning": {
    "route": ["tour code"],
    "station": ["delivery hub"]
  }
}
```

Gli override v1 sono additivi: i default sicuri dell'Adapter non vengono
rimossi. Alias malformati o target sconosciuti vengono ignorati e il catalogo
versionato resta il fallback.

Le Operational Unit riconosciute sono versionate nel catalogo v1. Il
rilevatore conflitti riceve questo insieme come contratto neutrale e non
conosce codici Amazon. La configurazione organizzativa delle unità richiedera'
che la versione Adapter entri anche nella chiave delle snapshot operative;
questa migrazione non appartiene alla v1.

## Contratti e compatibilita'

I contratti neutrali sono definiti in:

```text
backend/app/importers/adapter_contract.py
```

Il composition boundary seleziona l'Adapter in:

```text
backend/app/adapters/registry.py
```

Le API pubbliche non espongono ancora un parametro Adapter. Amazon rimane il
default applicativo per mantenere il comportamento corrente.

`field_aliases.py`, `event_types.py` e `planning_adapter.py` sono facade di
compatibilita'. Non contengono piu' cataloghi verticali propri.

## Limiti v1

- nessuna selezione Adapter da UI o API;
- nessun formato outbound Amazon;
- nessuna integrazione yard;
- nessuna transizione dispatch;
- nessuna importazione scorecard;
- nessuna traduzione automatica di eventi dentro il Planning;
- nessuna modifica dei contratti pubblici station/route/cycle;
- nessun accesso diretto al Fleet Plugin.

Yard, dispatch e scorecard sono dichiarati come mapping futuri, non come
funzionalita' implementate.

## Esempio

Con intestazioni:

```text
Driver | Vehicle | Delivery Station | Route ID | Wave
```

Amazon Adapter produce i target compatibili:

```text
driver_name | vehicle_plate | station | route | cycle
```

Il contratto dichiara contemporaneamente i concetti neutrali:

```text
Human Resource | Asset | Operational Unit | Task | Time Window
```

## Futuro Generic File Adapter

Il Generic File Adapter dovra':

- possedere alias generici non legati ad Amazon;
- supportare profili configurati per organizzazione e fonte;
- riutilizzare il parser fisico Excel/CSV senza duplicarlo;
- produrre gli stessi contratti `AdapterConceptMapping`;
- dichiarare provenienza, versione del formato e mapping applicato;
- gestire selezione Adapter fuori dal Core;
- distinguere alias generici da semantiche di vettore;
- avere fixture e test di contratto propri.

Quando esistera', gli alias italiani generici oggi mantenuti nel catalogo
Amazon per compatibilita' potranno essere estratti senza modificare il motore
di matching o il Planning.
