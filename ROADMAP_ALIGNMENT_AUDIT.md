# Roadmap Alignment Audit

**Data audit:** 2026-07-22
**Tipo:** analisi statica e documentale, senza modifiche applicative
**Riferimenti canonici:** [Operations Engine Vision](OPERATIONS_ENGINE_VISION.md), [Operations Engine Roadmap](OPERATIONS_ENGINE_ROADMAP.md), [Core, Adapter e Plugin Boundaries](CORE_ADAPTER_PLUGIN_BOUNDARIES.md)

## 1. Obiettivo

Questo audit verifica la coerenza dello stato corrente di Operations Engine con la missione, i confini architetturali e la roadmap ufficiale. Non corregge il codice e non rivaluta il comportamento funzionale gia coperto dagli sprint conclusi.

Sono stati esaminati:

- bootstrap e struttura backend;
- Core, dominio, servizi, repository e Configuration Engine;
- Amazon Adapter e registro Adapter;
- Fleet e Workforce Plugin;
- Planning e modelli di compatibilita;
- Daily Operations Briefing e demo orchestration;
- navigazione e composizione frontend;
- documentazione di architettura e prodotto.

## 2. Classificazioni

- **ALIGNED:** rispetta i confini e supporta la roadmap corrente.
- **ACCEPTABLE_DEBT:** compromesso noto e temporaneamente compatibile, da non estendere.
- **FUTURE_WORK:** capacita prevista dalla roadmap ma non necessaria nella fase conclusa.
- **VIOLATION:** dipendenza o dato che contraddice una regola canonica e richiede uno sprint correttivo dedicato.

## 3. Sintesi

| Classificazione | Totale | Valutazione |
|---|---:|---|
| ALIGNED | 6 | Le fondamenta Core, Adapter e Plugin sono separate e utilizzabili |
| ACCEPTABLE_DEBT | 4 | Compatibilita legacy e composizione temporanea da contenere |
| FUTURE_WORK | 4 | Multi-unita e Mission Control richiedono contratti pubblici piu maturi |
| VIOLATION | 2 | Nessun blocco alla documentazione; correzione necessaria prima della piena Fase 3/4 |

Il prodotto e coerente con le fasi gia concluse, ma non deve avanzare oltre Mission Control senza eliminare le due violazioni descritte.

## 4. Evidenze ALIGNED

### A1. Direzione delle dipendenze del Core

**Area:** `backend/app/core`, `backend/app/domain`, `backend/app/services`
**Esito:** ALIGNED

Il Core non importa moduli Amazon, Fleet o Workforce. Le ricerche statiche non hanno rilevato termini Amazon diretti nei moduli Core esaminati. Il bootstrap applicativo compone i moduli dall'esterno, come previsto per una composition root.

### A2. Amazon Adapter separato

**Area:** `backend/app/adapters/amazon`
**Esito:** ALIGNED

Alias, eventi e mapping verticali sono posseduti dall'Adapter. La dipendenza osservata procede dall'Adapter verso contratti Core e Configuration Engine, non nel verso opposto.

### A3. Traduzione verso il linguaggio Core

**Area:** `backend/app/adapters/amazon/adapter.py`, `backend/app/domain/core_language`
**Esito:** ALIGNED

Route, station, wave, driver e vehicle dispongono di una strategia di traduzione verso Task, Operational Unit, Time Window, Human Resource e Asset Reference. I mapper convivono con i contratti pubblici legacy senza rinomine distruttive.

### A4. Separazione tra Fleet e Workforce

**Area:** `backend/app/plugins/fleet`, `backend/app/plugins/workforce`
**Esito:** ALIGNED

Non sono state rilevate dipendenze dirette tra i due Plugin. Ogni Plugin mantiene dominio, applicazione e infrastruttura propri.

### A5. Planning non governato dai Plugin

**Area:** servizi Planning e Plugin
**Esito:** ALIGNED

Fleet e Workforce non assumono ownership di planning, assignment, capacity o readiness. I Plugin gestiscono il proprio ciclo di vita e rendono disponibili dati operativi senza sostituire le decisioni Core.

### A6. Frontend prevalentemente presentazionale

**Area:** `frontend/assets/js`
**Esito:** ALIGNED

Le workspace consumano lo stato restituito dal backend e non risultano proprietarie delle regole principali di readiness o conflitto. Home, Operations, Workforce, Fleet, Settings e Getting Started sono gia distinguibili nella navigazione.

## 5. Debito tecnico accettabile

### D1. Linguaggio legacy nel dominio compatibile

**Area:** modelli di planning, assignment, import e persistenza
**Esito:** ACCEPTABLE_DEBT
**Fase:** migrazione incrementale trasversale

`station`, `route`, `cycle`, `driver` e `vehicle` restano presenti in modelli e payload esistenti. Il debito e coerente con la strategia di doppio linguaggio, purche il nuovo codice Core non estenda questi termini come concetti definitivi.

### D2. Adapter Amazon attivo come default di composizione

**Area:** `backend/app/adapters/registry.py`
**Esito:** ACCEPTABLE_DEBT
**Fase:** 4 - Multi-Organization e Multi-Operational Unit

Il registro seleziona oggi l'Amazon Adapter come adapter attivo. E compatibile con il primo mercato, ma la scelta futura deve essere risolta per organizzazione e configurazione, senza introdurre condizionali Amazon nel Core.

### D3. Demo orchestration dipendente da moduli concreti

**Area:** `backend/app/demo/service.py`
**Esito:** ACCEPTABLE_DEBT
**Fase:** consolidamento successivo alla Fase 3

Il servizio demo orchestra Adapter e Fleet tramite implementazioni concrete. Essendo confinato al workspace demo non contamina il Core decisionale, ma non deve diventare il modello per flussi produttivi. Una futura porta pubblica di seed/import ridurra l'accoppiamento.

### D4. Persistenza e bootstrap ancora centralizzati

**Area:** `backend/app/core/database.py` e bootstrap applicativo
**Esito:** ACCEPTABLE_DEBT
**Fase:** 4

Schema legacy e inizializzazione condivisa conservano conoscenza di piu aree applicative. Non e richiesto dividerli ora: la separazione dovra seguire ownership e migrazioni reali, evitando repository o interfacce vuote.

## 6. Lavoro futuro previsto

### F1. Operational Unit di prima classe

**Area:** Core, Configuration, Planning, Fleet, Workforce
**Esito:** FUTURE_WORK
**Fase:** 4

Esistono `OperationalUnit`, mapper e campi `operational_unit_id`, ma manca ancora un registro Core completo e un riferimento uniforme su Asset, Task, Planning e Assignment. Il contratto da seguire e [Operational Unit Model](OPERATIONAL_UNIT_MODEL.md).

### F2. Organizzazione e selezione dell'ambito

**Area:** Configuration Engine e frontend
**Esito:** FUTURE_WORK
**Fase:** 4

La configurazione supporta gia organization e operational unit, ma ownership, selezione `Tutte`, aggregazione e futura autorizzazione non sono applicate in modo uniforme a tutte le workspace.

### F3. Contratti pubblici di snapshot

**Area:** Fleet, Workforce, Briefing
**Esito:** FUTURE_WORK
**Fase:** 3 - Mission Control

I Plugin possiedono modelli di snapshot utili, ma devono esporli tramite porte pubbliche versionate e stabili. Il Core e la composizione non devono importare servizi applicativi interni.

### F4. Ownership distinta tra Home e Operations

**Area:** navigazione e viste frontend
**Esito:** FUTURE_WORK
**Fase:** 3

Home presenta briefing e stato corrente; Operations presenta planning, dashboard e import. La distinzione e visibile ma alcune sintesi di readiness possono sovrapporsi. [Product Screen Contracts](PRODUCT_SCREEN_CONTRACTS.md) assegna a Home il ruolo di segnalazione e a Operations l'analisi del ciclo.

## 7. Violazioni

### V1. Operational Unit cliente nel catalogo globale Amazon

**Area:** `backend/app/adapters/amazon/catalog.v1.json`
**Esito:** VIOLATION
**Priorita:** alta prima della Fase 4

Il catalogo distribuito include una lista globale di unita riconosciute con codici e nomi propri di un contesto cliente, incluso `DLO2`. La collocazione nell'Adapter evita la contaminazione del Core, ma il dato resta improprio come default di piattaforma.

**Regola violata:** l'Adapter traduce il sistema esterno; la configurazione dell'organizzazione definisce le unita realmente valide. Nessun codice cliente deve essere distribuito come configurazione globale.

**Correzione futura:** spostare le unita riconosciute nella configurazione versionata di Organization/Operational Unit, mantenendo nel catalogo soltanto alias generici del formato Amazon. La migrazione richiede test di contratto e fallback compatibile; non e stata eseguita in questo sprint.

### V2. Briefing accoppiato agli internals dei Plugin

**Area:** `backend/app/briefing/briefing_service.py`, `backend/app/briefing/plugin_sections.py`, `backend/app/briefing/issue_collectors.py`
**Esito:** VIOLATION
**Priorita:** alta nella Fase 3

Il Briefing importa direttamente servizi applicativi e modelli concreti di Fleet e Workforce. La direzione crea conoscenza degli internals dei Plugin nel livello di composizione e rende Mission Control fragile rispetto all'evoluzione indipendente dei Plugin.

**Regola violata:** il Core e la composizione consumano contratti pubblici; non dipendono dall'implementazione interna dei Plugin.

**Correzione futura:** introdurre porte pubbliche minime e snapshot versionati, quindi iniettare i provider nella composizione. Non servono nuove regole di dominio e non va duplicata la logica esistente. La sequenza e definita in [Mission Control Product Contract](MISSION_CONTROL_PRODUCT_CONTRACT.md).

## 8. Verifica dei termini verticali

### Amazon

La conoscenza Amazon e concentrata nell'Adapter, nella documentazione dedicata e nel registro di composizione. Non e stata rilevata logica Amazon diretta nel Core esaminato.

### Station e route

I termini sono ancora diffusi nei contratti legacy, nella persistenza e nel Planning compatibile. Sono debito di linguaggio, non prova automatica di contaminazione Amazon: vengono tradotti tramite mapper e non devono essere rinominati senza una migrazione pubblica.

### DLO2

Il codice compare nel catalogo Amazon come unita riconosciuta globale e costituisce la violazione V1. I riferimenti documentali storici non devono essere copiati in esempi canonici o nuove fixture.

## 9. Impatto sulla Roadmap

- **Fasi 0-2:** completate e sostanzialmente coerenti.
- **Fase 3:** puo iniziare soltanto con i contratti pubblici di snapshot e la rimozione dell'accoppiamento V2.
- **Fase 4:** richiede la rimozione di V1 e il modello Operational Unit di prima classe.
- **Fasi 5-10:** non devono anticipare configurazioni verticali, workflow Plugin o automazioni prima dei relativi prerequisiti.

## 10. Decisioni operative dell'audit

1. Non modificare il comportamento corrente durante questo sprint documentale.
2. Trattare V2 come primo intervento tecnico della Fase 3.
3. Trattare V1 come gate della Fase 4.
4. Non estendere il linguaggio legacy in nuovi contratti Core.
5. Non creare un Generic Adapter finche il contratto Organization/Operational Unit non e stabile.
6. Usare [Development Sprint Rules](DEVELOPMENT_SPRINT_RULES.md) per ogni correzione.

## 11. Conclusione

Operations Engine dispone gia di una separazione reale tra Core, Amazon Adapter, Fleet Plugin e Workforce Plugin. Le principali lacune non richiedono una riscrittura: richiedono due correzioni mirate e il completamento progressivo dei contratti di Mission Control e Operational Unit.

Questo audit e un punto-in-tempo. Dopo ogni fase della roadmap deve essere aggiornato o sostituito da un nuovo audit, senza alterare retroattivamente le evidenze storiche.
