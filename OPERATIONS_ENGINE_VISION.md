# Operations Engine Vision

**Stato:** canonico e vincolante
**Ambito:** missione, identità del prodotto e criteri di valore
**Autorità superiore:** [Operations Engine Philosophy](OPERATIONS_ENGINE_PHILOSOPHY.md)

Questo documento stabilisce la visione ufficiale di Operations Engine. Deve
essere letto insieme alla [Roadmap](OPERATIONS_ENGINE_ROADMAP.md) e ai
[confini architetturali](CORE_ADAPTER_PLUGIN_BOUNDARIES.md) prima di ogni nuova
macro-fase.

## Missione

> Operations Engine è il sistema operativo del responsabile operativo.

La piattaforma offre un punto unico, affidabile e spiegabile dal quale
un'organizzazione coordina la propria operatività quotidiana. Il prodotto
trasforma fonti eterogenee in stato operativo, rende visibili criticità e
dipendenze, prepara piani verificabili e conserva la storia delle decisioni.

Il responsabile operativo deve poter comprendere:

- quali persone, Asset e Task sono disponibili;
- quale capacità esiste per ogni Operational Unit;
- quali vincoli impediscono l'esecuzione;
- quali decisioni richiedono conferma;
- quali fatti hanno prodotto lo stato corrente;
- cosa è cambiato durante la giornata.

## Definizione del prodotto

Operations Engine coordina:

- Workforce Member e Human Resource;
- Asset e disponibilità;
- Operational Task e Time Window;
- Operational Unit;
- Planning e Assignment;
- Conflict, Capacity e Readiness;
- Decision Proposal e conferme umane;
- Briefing e Operational Event;
- configurazioni, provenienza e storico operativo.

Il prodotto non coincide con una singola schermata o fonte dati. Il suo valore
è la continuità tra osservazione, interpretazione, pianificazione, controllo,
decisione e audit.

## Cosa è

Operations Engine è:

- un motore operativo configurabile;
- una piattaforma multi-azienda e multi-settore;
- un sistema human-in-the-loop;
- un insieme di Core, Plugin, Adapter e configurazione separati;
- una fonte di stato operativo con provenienza esplicita;
- un ambiente per decisioni prudenti, verificabili e annullabili;
- un prodotto che migliora il processo, non che riproduce il formato sorgente.

## Cosa non è

Operations Engine non è:

- un importatore Excel;
- un gestionale Amazon;
- un Fleet Manager isolato;
- un software Workforce isolato;
- un ERP monolitico;
- un TMS tradizionale;
- un route optimizer;
- un foglio elettronico trasferito nel browser;
- un chatbot che decide al posto dell'operatore;
- un insieme di eccezioni costruite per un singolo cliente.

Amazon DSP è il primo caso di validazione e il primo Adapter. Non definisce il
prodotto, il Core o la roadmap generale.

## Excel come ponte

Excel è un ponte, non il prodotto.

Nella fase iniziale:

```text
Excel
  -> import
  -> interpretazione
  -> normalizzazione
  -> conferma
  -> Operations Engine
```

Nella fase matura:

```text
Operations Engine
  -> pianificazione
  -> modifica
  -> controllo
  -> decisione
  -> storico
  -> export quando necessario
```

L'obiettivo è rendere non necessario l'uso quotidiano di Excel per governare
l'operazione. L'import deve rispettare il significato dei dati senza assumere
che un nome file, un foglio, una riga di intestazione o un layout siano
universali.

I file reali usati in QA validano la robustezza. Non sono specifiche di
prodotto. XLSX, CSV, export ERP, API e documenti proprietari sono fonti esterne
equivalenti quando producono gli stessi contratti neutrali.

## Concetto operativo, non formato

La piattaforma riconosce concetti, non coordinate di celle. Un Adapter o un
profilo configurato traduce il significato esterno verso il Core. Il Core non
conosce la forma fisica della fonte.

Una nuova sorgente è compatibile quando può dichiarare:

- origine e versione;
- mapping applicato;
- livello di confidenza;
- dati ignorati o sensibili;
- elementi che richiedono conferma;
- contratto neutrale prodotto.

## Multi-azienda e multi-settore

Ogni organizzazione può avere workflow, nomenclature, policy, soglie,
capability, tipi di risorsa e Operational Unit differenti. Queste differenze
appartengono alla configurazione o agli Adapter, non a ramificazioni nel Core.

La stessa piattaforma deve poter supportare last-mile, field service,
manutenzione, facility management e altri settori che coordinano persone,
Asset e attività. L'estensione a un nuovo mercato non deve richiedere la
riscrittura di Planning, Capacity, Readiness o Decision Engine.

## Operational Unit

Operational Unit è il perimetro neutrale dell'operazione. Può essere mostrata
con una nomenclatura configurata come Station, deposito, hub, sede, filiale,
area operativa o centro servizi.

Un'organizzazione può operare su una unità, su più unità o in vista aggregata.
La semantica completa è definita nel
[modello Operational Unit](OPERATIONAL_UNIT_MODEL.md).

## Decision support

Operations Engine non sostituisce il responsabile operativo. Il sistema:

- osserva;
- normalizza;
- confronta;
- rileva;
- spiega;
- propone;
- registra.

Il sistema non inventa dati, non nasconde la provenienza, non applica modifiche
ambigue e non altera silenziosamente dati confermati. Ogni proposta deve essere
motivata, prudente, verificabile, annullabile e soggetta a conferma umana quando
ha impatto operativo.

## Criterio di coerenza

Una nuova capacità è coerente con la visione solo se:

1. risponde a una necessità operativa reale;
2. usa il linguaggio neutrale del Core;
3. assegna correttamente la responsabilità a Core, Plugin, Adapter o
   Configuration;
4. migliora il processo anziché imitare la fonte;
5. espone provenienza, limiti e stato;
6. mantiene l'operatore responsabile della decisione finale;
7. è verificabile in uno sprint con un solo obiettivo.
