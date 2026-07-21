# Daily Operations Briefing v1

**Governance canonica:** [Mission Control Product Contract](MISSION_CONTROL_PRODUCT_CONTRACT.md),
[Product Screen Contracts](PRODUCT_SCREEN_CONTRACTS.md) e
[Core, Adapter e Plugin Boundaries](CORE_ADAPTER_PLUGIN_BOUNDARIES.md).

## Scopo

Daily Operations Briefing risponde alla domanda:

> Cosa richiede la tua attenzione oggi?

È una capacità applicativa separata di Operations Engine. Raccoglie risultati
già prodotti dal sistema, li ordina con regole esplicite, ne spiega la
rilevanza e propone azioni non distruttive. Non è una nuova fonte della verità.

Il modulo vive in `backend/app/briefing` e non appartiene al Planning Engine,
al Fleet Plugin o a un Adapter.

## Cosa è e cosa non è

Il briefing:

- legge dati tipizzati già disponibili;
- conserva il collegamento tra ogni affermazione e le fonti;
- distingue fatti osservati, dati configurati e dati derivati;
- ordina le issue in modo deterministico;
- propone raccomandazioni che richiedono conferma umana;
- persiste un audit minimo versionato.

Il briefing non:

- modifica Planning, Assignment, Asset, eventi o configurazioni;
- ricalcola Planning, Readiness o Capacity;
- applica raccomandazioni;
- invia comunicazioni esterne;
- usa file verticali o dati grezzi;
- usa un chatbot, un LLM o un provider AI;
- inventa valori quando una fonte non è disponibile.

## Architettura

```text
Planning / Assignment / Eventi
Operations snapshot (Readiness e Capacity)
Fleet Plugin application service
Configuration Engine
        |
        v
briefing_service.py
        |
        +-- issue_collectors.py
        +-- prioritization.py
        +-- recommendations.py
        +-- repository.py
        |
        v
DailyOperationsBriefing v1
        |
        +-- API versionata
        +-- UI Operations
```

Responsabilità:

- `models.py`: contratto neutrale, tipizzato e versionato;
- `briefing_service.py`: lettura fonti, fingerprint, snapshot ed esecuzione del
  caso d'uso;
- `issue_collectors.py`: traduzione dei risultati esistenti in issue del
  briefing;
- `prioritization.py`: ranking e attention level;
- `recommendations.py`: regole dichiarative e non distruttive;
- `repository.py`: schema e persistenza idempotente;
- `router.py`: due endpoint HTTP;
- `schemas.py`: richiesta di generazione.

Il frontend non contiene soglie o regole operative. Ordina e filtra soltanto
la lista già classificata dal backend.

## Fonti

Le fonti consentite e usate sono:

- ultimo Planning o Planning richiesto esplicitamente;
- Assignment e alternative persistite nel Planning;
- conflitti del Planning;
- eventi applicati e versioni del Planning;
- ultimo operation snapshot compatibile con gli import e la soglia del
  Planning;
- Readiness e Capacity contenute nello snapshot;
- Capacity per Operational Unit già presente nel Planning;
- Asset e documenti esposti dal servizio applicativo pubblico del Fleet
  Plugin;
- snapshot pubblico Workforce con assenze, copertura, deficit, contratti in
  scadenza e capability mancanti;
- snapshot pubblico Fleet Sync con indisponibili, manutenzione, riserva,
  conflitti, documenti in attenzione e aggiornamenti recenti;
- configurazione effettiva restituita dal Configuration Engine.

La demo non è importata dal modulo briefing. `is_demo` deriva dai marker degli
import realmente creati dal Demo Workspace.

Se l'ultimo operation snapshot non corrisponde alle fonti del Planning,
Readiness è dichiarata non disponibile. Il briefing usa la Capacity già
presente nel Planning e non invoca il Decision Engine.

## Modelli

`DailyOperationsBriefing` include:

- ID, revisione, fingerprint e versione contratto;
- data di generazione e data operativa;
- riferimenti a Planning e Configuration;
- organizzazione e Operational Unit disponibili;
- stato e attention level;
- executive summary e motivazione;
- snapshot minimi Readiness e Capacity;
- metriche;
- sezioni ordinate;
- source references complessive;
- limiti dichiarati;
- flag demo.

Ogni `BriefingSection` include codice stabile, categoria, severity, priorità,
punteggio, urgenza, impatto, spiegazione del ranking, fatti, rationale,
raccomandazione, alternative, fonti, action link e indicazione della decisione
umana richiesta.

Ogni fatto espone una provenienza:

- `observed`: valore presente nella fonte;
- `configured`: policy o soglia configurata;
- `derived`: risultato già calcolato o confronto deterministico di valori
  disponibili;
- `suggestion`: azione proposta, mai applicata;
- `limitation`: dato non disponibile o non esposto.

Versione contratto corrente:

```text
1.0
```

## Priorità

Il punteggio è deterministico:

```text
priority_score = severity_base + urgency * 10 + operational_impact
```

Valori base:

| Severity | Base |
| --- | ---: |
| blocker | 600 |
| critical | 500 |
| high | 400 |
| medium | 300 |
| low | 200 |
| information | 100 |

Urgenza e impatto usano una scala da 1 a 4. In caso di parità l'ordine usa
codice issue ed entità sorgente, producendo un risultato stabile. Ogni sezione
riporta la spiegazione del proprio punteggio.

Il payload applica limiti tipizzati. Sono conservate al massimo 300 sezioni e
1.000 source references complessive, privilegiando sempre la priorità più
alta.

## Attention Level

- `stable`: nessun blocker, margine conforme e nessuna issue high/medium;
- `attention`: Readiness yellow, margine sotto soglia, sostituzioni o warning
  significativi;
- `critical`: Task scoperti, Planning critico, Readiness red, capacità
  insufficiente o issue blocker/critical;
- `unavailable`: nessun Planning oppure nessun briefing persistito per le
  fonti correnti.

Il livello include sempre una motivazione. L'executive summary viene composto
in funzione di livello e temi realmente presenti; il risultato demo non è
hardcoded.

## Recommendation Engine

Le regole dichiarative coprono:

- Task scoperti;
- capacità insufficiente;
- margine di riserva basso;
- sostituzione di Human Resource;
- Asset indisponibile o assegnato nonostante l'indisponibilità;
- ultimo Asset di riserva in uso;
- override manuali;
- warning del Planning;
- Readiness attention o critical;
- Operational Unit non riconosciuta, raggruppata per entità;
- documenti Asset scaduti o prossimi alla scadenza.

Ogni raccomandazione espone codice, testo, motivo, fonti usate, alternative,
impatto atteso, conferma umana obbligatoria e link interno. Nessuna regola
esegue una modifica.

Non sono proposte eliminazioni, riassegnazioni automatiche, azioni finanziarie
o comunicazioni esterne.

## Spiegabilità

Ogni card UI mostra:

1. severity e posizione in priorità;
2. fatto osservato o derivato;
3. provenienza del fatto;
4. motivo per cui il fatto conta;
5. azione consigliata, se applicabile;
6. spiegazione del ranking;
7. riferimenti sorgente;
8. collegamento interno alla schermata pertinente.

Le source references usano tipo, ID tecnico, versione, field path ed etichetta.
Il briefing non copia l'intero dataset sorgente nel proprio record.

## Idempotenza e versionamento

Il fingerprint SHA-256 include:

- contratto briefing;
- Planning completo e relativa storia;
- snapshot operativo compatibile, senza ID e timestamp tecnici che non
  cambiano il contenuto;
- Asset e documenti Fleet esposti;
- snapshot pubblici Workforce e Fleet Sync;
- configurazione effettiva;
- indicatore demo derivato.

Il Briefing non ricalcola questi conteggi. Li riceve dai servizi applicativi
pubblici dei plugin e aggiunge sezioni `WORKFORCE_DEFICIT`,
`WORKFORCE_ATTENTION` o `FLEET_REGISTRY_ATTENTION` soltanto quando i relativi
snapshot richiedono attenzione.

Se il fingerprint esiste, `POST generate` restituisce il record persistito,
incluso lo stesso `generated_at`. Non viene creato un duplicato.

Se una fonte cambia, viene creata una nuova `briefing_revision`. Le revisioni
precedenti restano persistite finché esiste il Planning sorgente.

## Persistenza

Tabella additiva:

```text
daily_briefings
```

Campi:

- `briefing_id`;
- `fingerprint`;
- `planning_id`;
- `planning_version`;
- `configuration_version`;
- `contract_version`;
- `briefing_revision`;
- `generated_at`;
- `payload`;
- `is_demo`.

Il payload è validato dal modello Pydantic. Il Planning è una foreign key con
`ON DELETE CASCADE`: cancellare un Planning demo elimina i soli briefing
collegati. Non esiste un event store parallelo.

Lo schema usa l'infrastruttura database corrente ed è compatibile con SQLite e
con la traduzione PostgreSQL usata su Railway.

## API

```text
GET  /api/briefing/v1/daily/latest
POST /api/briefing/v1/daily/generate
```

`GET latest`:

- restituisce il briefing persistito corrispondente alle fonti correnti;
- senza Planning restituisce HTTP 200 con `status=unavailable`;
- non genera errori 400/404 nel primo utilizzo;
- non restituisce come corrente un briefing obsoleto.

`POST generate`:

- accetta un body vuoto per l'ultimo Planning;
- accetta facoltativamente `planning_id`;
- è idempotente a fonti invariate;
- persiste una nuova revisione solo quando cambiano le fonti;
- non modifica dati operativi.

Non è stato aggiunto un endpoint di dettaglio perché la UI v1 non lo richiede.

## UI

La Home Operations contiene la sezione principale:

```text
Cosa richiede la tua attenzione oggi
```

Mostra attention level, executive summary, motivazione, Planning analizzato,
Readiness, Capacity, conteggi e card ordinate. I filtri sono:

- Tutto;
- Critico;
- Attenzione;
- Informazioni.

I filtri sono esclusivamente presentazione: non cambiano severity o ordine.
Le card usano API DOM con `textContent`; non inseriscono HTML ricevuto dal
backend.

Lo stato di caricamento è comunicato con `aria-live` e skeleton. Badge e
severity hanno sempre testo, non soltanto colore. Il layout contiene breakpoint
desktop, tablet e mobile e rispetta `prefers-reduced-motion`.

## Empty State

Senza Planning l'API restituisce un payload tipizzato e la UI mostra:

> Il briefing sarà disponibile dopo la creazione del primo planning.

Sono disponibili:

- `Importa dati`;
- `Carica demo`, soltanto quando il Demo Workspace è abilitato.

Non vengono prodotti 400/404 previsti o errori console.

## Demo Workspace

Il `demo_dataset_v1`, processato dalle pipeline reali, produce:

- attention level `attention`;
- Readiness `yellow`;
- margine operativo `0`;
- sostituzione di una Human Resource assente;
- riserva Asset ridotta;
- warning e alternative;
- nessun Task scoperto.

Il frontend non contiene questi risultati. Dopo il reset il Planning demo
viene eliminato e la foreign key rimuove il briefing demo. Planning e briefing
reali restano invariati.

## Sicurezza

- nessun secret o nuova variabile d'ambiente;
- nessuna chiamata esterna;
- nessuna dipendenza AI;
- nessun dato personale nelle fixture;
- source references tecniche e prive di contenuti grezzi;
- payload Pydantic dimensionato;
- nessun HTML backend inserito nella UI;
- nessuna azione distruttiva automatica;
- errori inattesi presentati senza stack trace nel frontend.

## Limiti

- la compatibilità tra capability richieste dal Task e disponibili nelle
  Resource non è ancora esposta come esito tipizzato dal Planning v1; il
  briefing lo dichiara e non la ricostruisce;
- in assenza di operation snapshot compatibile, Readiness è dichiarata non
  disponibile;
- il Fleet Plugin non associa ancora formalmente Asset e Planning a una
  Organization;
- la repository conserva le revisioni ma la v1 non espone un browser storico;
- il processo usa un lock locale; il deploy corrente usa un solo processo
  Uvicorn;
- la suite verifica la traduzione PostgreSQL, ma non avvia un PostgreSQL reale.

## Roadmap futura

Sviluppi compatibili, non inclusi nella v1:

1. porta applicativa esplicita per snapshot storici Readiness/Capacity;
2. collegamento Organization e Operational Unit a Fleet e Planning;
3. contratto tipizzato per compatibilità capability;
4. consultazione audit delle revisioni;
5. notifiche soltanto tramite Plugin dedicati e conferma esplicita;
6. eventuale `BriefingNarrativeProvider` per migliorare la forma del testo.

Un eventuale narrative provider AI dovrà essere opzionale, non potrà cambiare
fatti, priorità, raccomandazioni o source references e dovrà avere un fallback
deterministico completo. Nessun provider AI è presente nella v1.
