# Operations Engine Roadmap

**Stato:** canonico e bloccato
**Ambito:** sequenza ufficiale delle macro-fasi
**Missione:** [Operations Engine Vision](OPERATIONS_ENGINE_VISION.md)

Questa roadmap sostituisce ogni precedente sequenza di delivery come fonte
dello stato corrente. Le roadmap storiche restano utili per comprendere
l'evoluzione tecnica, ma non autorizzano nuovi lavori.

Una fase `COMPLETATA` indica che i criteri v1 dichiarati sono verificati. Non
significa che il dominio sia definitivamente esaurito. Ogni nuovo sprint deve
rispettare [uno sprint, un obiettivo](DEVELOPMENT_SPRINT_RULES.md).

## Quadro ufficiale

| Fase | Nome | Stato | Risultato verificabile |
| --- | --- | --- | --- |
| 0 | Fondamenta | COMPLETATA | Architettura, motori Core, deploy e guardrail sono operativi. |
| 1 | Excel Bridge | COMPLETATA | Fonti tabellari sono profilate, confermate e importate in sicurezza. |
| 2 | Operational Workspaces | COMPLETATA PER IL V1 ATTUALE | Workforce e Fleet sono workspace operativi responsive. |
| 3 | Mission Control | PROSSIMA FASE | Home diventa il centro operativo quotidiano senza duplicare logica. |
| 4 | Daily Operations | FUTURA | Task, Assignment e Planning giornaliero sono governati end-to-end. |
| 5 | Daily Timeline | FUTURA | Gli eventi della giornata sono consultabili in ordine causale. |
| 6 | Decision Support | FUTURA | Il sistema produce proposte spiegabili e confermabili. |
| 7 | Operational Notifications | FUTURA | Solo eventi operativamente rilevanti generano notifiche. |
| 8 | Scenario Simulator | FUTURA | Gli scenari sono simulati senza modificare lo stato reale. |
| 9 | Operations Intelligence | FUTURA | Pattern e previsioni prudenti emergono dai dati auditabili. |
| 10 | Multi-Adapter | FUTURA | Nuovi mercati e fonti entrano senza modificare il Core. |

## Fase 0 - Fondamenta

**Stato:** COMPLETATA

Comprende Costituzione architetturale, Core, Plugin architecture, Adapter
architecture, Configuration Engine, Planning Engine, Decision Engine,
Readiness, Capacity, Core Language Migration, Amazon Adapter iniziale,
PostgreSQL, Railway, sicurezza Git, Workspace Lifecycle, Demo Workspace, Daily
Operations Briefing e test automatici.

**Criteri di completamento v1:**

- la Costituzione è vincolante;
- il Core non importa Adapter o Plugin;
- il vecchio optimizer è isolato;
- il deploy usa configurazione esterna e PostgreSQL in produzione;
- Demo e Production hanno lifecycle distinti;
- Planning, Capacity e Readiness sono testati e spiegabili.

## Fase 1 - Excel Bridge

**Stato:** COMPLETATA

Comprende Workbook Profiler, classificazione, rilevamento foglio e header,
mapping, preview, persistenza JSON-safe, import Workforce e Fleet, privacy,
idempotenza, diff e sincronizzazione.

**Criteri di completamento v1:**

- XLSX, XLS e CSV sono trattati come fonti non attendibili;
- il mapping ambiguo richiede conferma;
- i campi sensibili non necessari sono esclusi;
- parser, interpretazione e normalizzazione sono separati;
- il reimport non duplica lo stato;
- Excel è documentato come ponte temporaneo.

## Fase 2 - Operational Workspaces

**Stato:** COMPLETATA PER IL V1 ATTUALE

**Workforce:** landing, calendario giorno/settimana/persona, KPI, copertura,
eventi, import secondario, modifica rapida, tastiera, responsive e UX polish.

**Fleet:** Registry-first, ricerca, KPI, badge, dettaglio laterale, cronologia,
import secondario, export, empty state e responsive.

**Criteri di completamento v1:**

- ogni workspace risponde a una domanda operativa distinta;
- import e sincronizzazione sono funzioni secondarie;
- desktop, tablet e mobile sono verificati;
- il frontend non ricalcola decisioni di dominio;
- Fleet e Workforce non dipendono direttamente tra loro.

## Fase 3 - Mission Control

**Stato:** PROSSIMA FASE

**Obiettivo unico della macro-fase:** trasformare Home nel centro operativo
quotidiano che risponde a "Cosa sta succedendo oggi e cosa richiede la mia
attenzione?".

Mission Control deve leggere snapshot pubblici e mostrare stato Workforce,
Fleet, Task e Planning, Briefing, criticità, azioni richieste, Operational Unit,
ultima attività e readiness della giornata.

**Criteri di completamento:**

- esiste un contratto aggregato o una composizione esplicita di snapshot
  pubblici versionati;
- nessun dato viene ricalcolato nel frontend;
- Mission Control non importa modelli interni dei Plugin;
- empty, loading, partial, error e ready sono distinguibili;
- l'Operational Unit selezionata è sempre visibile, inclusa la vista `Tutte`;
- ogni azione porta al workspace proprietario;
- responsive, accessibilità, performance e QA browser sono verificati;
- nessuna modifica operativa viene applicata dalla Home.

Il contratto completo è in
[Mission Control Product Contract](MISSION_CONTROL_PRODUCT_CONTRACT.md).

## Fase 4 - Daily Operations

**Stato:** FUTURA

Comprende Planning operativo giornaliero, Task, fabbisogno, Assignment,
Conflict, Readiness, ricalcolo, conferma, pubblicazione, export, conservazione
delle modifiche manuali e filtro Operational Unit.

**Criteri di completamento:** un responsabile può creare, verificare,
correggere, confermare e pubblicare un piano senza perdere provenienza,
versioni o modifiche manuali.

## Fase 5 - Daily Timeline

**Stato:** FUTURA

Raccoglie import, sincronizzazioni, assenze, guasti, modifiche, decisioni e
transizioni del Planning.

**Criteri di completamento:** ogni elemento ha timestamp, actor, fonte,
Operational Unit, entità e collegamento allo stato risultante; la timeline non
ricostruisce fatti non registrati.

## Fase 6 - Decision Support

**Stato:** FUTURA

Produce proposte per deficit, conflitti, riassegnazioni, capability mancanti e
possibili correzioni.

**Criteri di completamento:** ogni proposta è motivata, prudente, verificabile,
annullabile, collegata alle fonti e soggetta a conferma umana.

## Fase 7 - Operational Notifications

**Stato:** FUTURA

Copre assenze, Asset indisponibili, conflitti, documenti in attenzione,
contratti in scadenza, copertura insufficiente e Planning non pronto.

**Criteri di completamento:** regole, destinatari e canali sono configurabili;
deduplicazione, priorità, audit e silenziamento impediscono rumore inutile.

## Fase 8 - Scenario Simulator

**Stato:** FUTURA

Simula assenza di una persona, guasto di un Asset, aumento Task, perdita di
capacità, trasferimento tra Operational Unit e cambi di soglia o turno.

**Criteri di completamento:** simulazione e stato reale sono tecnicamente
separati; ogni risultato dichiara ipotesi, differenze e limiti; applicare uno
scenario richiede un comando distinto e confermato.

## Fase 9 - Operations Intelligence

**Stato:** FUTURA

Analizza pattern ricorrenti, colli di bottiglia, trend, deficit, affidabilità
Asset e criticità ripetute. Non è un chatbot generico.

**Criteri di completamento:** dati e metriche sono sufficienti e auditabili;
previsioni e suggerimenti espongono qualità, incertezza, fonte e spiegazione;
nessun output probabilistico modifica automaticamente lo stato.

## Fase 10 - Multi-Adapter

**Stato:** FUTURA

Estende la piattaforma a nuovi vettori, corrieri locali, ERP, API e settori che
coordinano persone, Asset e Task.

**Criteri di completamento:** almeno un secondo Adapter reale soddisfa gli
stessi test di contratto senza modificare il Core; selezione, configurazione e
provenienza dell'Adapter sono esplicite per organizzazione e fonte.

## Dipendenze tra le fasi

```text
Fondamenta
  -> Excel Bridge
  -> Operational Workspaces
  -> Mission Control
  -> Daily Operations
  -> Daily Timeline
  -> Decision Support
  -> Operational Notifications
  -> Scenario Simulator
  -> Operations Intelligence
  -> Multi-Adapter
```

Le dipendenze non impongono che una fase futura sia un unico sprint. Ogni fase
deve essere suddivisa in incrementi con un solo obiettivo, contratti espliciti
e criteri di uscita verificabili.

## Regole di avanzamento

Una fase può iniziare solo quando:

1. il contratto di prodotto è documentato;
2. il proprietario architetturale è identificato;
3. dipendenze e dati sorgente sono disponibili;
4. scope e non-obiettivi sono espliciti;
5. il primo sprint è verificabile in pochi minuti;
6. debiti bloccanti della fase precedente sono classificati;
7. non è necessario inventare dati o workflow.
