# Product Screen Contracts

**Stato:** documento canonico di prodotto
**Ambito:** ownership delle schermate e dei flussi
**Riferimenti:** [Operations Engine Vision](OPERATIONS_ENGINE_VISION.md), [Mission Control Product Contract](MISSION_CONTROL_PRODUCT_CONTRACT.md), [Operational Unit Model](OPERATIONAL_UNIT_MODEL.md)

## 1. Regola generale

Ogni schermata di Operations Engine deve rispondere a una domanda operativa primaria. Le schermate non duplicano decisioni, non ricostruiscono regole di dominio nel browser e non diventano contenitori generici di funzioni.

L'import Excel e una funzione di alimentazione dati. Non e il prodotto, non e la home e non definisce l'architettura.

## 2. Home / Mission Control

**Domanda primaria:** cosa richiede la mia attenzione adesso?

**Mostra:** stato sintetico dell'operazione, criticita spiegabili, copertura, disponibilita delle risorse, freshness dei dati e prossime azioni. Ogni informazione dichiara organizzazione, Operational Unit e istante di riferimento.

**Azioni:** aggiornare il briefing e aprire la workspace proprietaria del problema.

**Non deve:** modificare direttamente Asset, turni, Task o configurazioni; duplicare tabelle complete; accedere agli internals dei Plugin; calcolare readiness nel frontend.

**Dipendenze ammesse:** contratti di snapshot pubblici del Core e dei Plugin, Configuration Engine e collegamenti alle workspace.

**Stato attuale:** Home e briefing esistono, ma la separazione dai dettagli di Operations e i contratti pubblici dei Plugin devono essere consolidati nella Fase 3.

## 3. Operations

**Domanda primaria:** qual e il piano operativo e quali conflitti impediscono di eseguirlo?

**Mostra:** planning, assegnazioni, capacity, readiness, conflitti e stato delle importazioni necessarie al ciclo corrente.

**Azioni:** importare dati, verificare mapping, generare o consultare il planning e analizzare i conflitti tramite le API esistenti.

**Non deve:** gestire il ciclo di vita degli Asset, amministrare persone, mostrare configurazioni tecniche come contenuto principale o replicare il briefing di Mission Control.

**Owner:** Core Operations e Planning. Gli Adapter forniscono traduzione; i Plugin forniscono dati tramite contratti stabili.

## 4. Workforce

**Domanda primaria:** chi e disponibile e come e coperto il fabbisogno operativo?

**Mostra:** calendario, turni, disponibilita, copertura, eventi e dettaglio della persona entro l'ambito selezionato.

**Azioni:** consultare e aggiornare le informazioni Workforce gia supportate, importare ed esportare tramite i flussi esistenti.

**Non deve:** generare Planning, assegnare Asset, calcolare conflitti del Core o conoscere termini Amazon.

**Owner:** Workforce Plugin. Il Core consuma solo i suoi contratti pubblici.

## 5. Fleet

**Domanda primaria:** qual e lo stato del parco mezzi e quali Asset richiedono attenzione?

**Mostra:** KPI sintetici, Asset Registry, stato osservato, driver associato, categoria, documenti, note e cronologia disponibile.

**Azioni:** consultare gli Asset e usare sincronizzazione/import/export gia esistenti.

**Non deve:** decidere assegnazioni, capacity, readiness o planning; trasformare l'import nella schermata principale; introdurre workflow di manutenzione non ancora previsti.

**Owner:** Fleet Plugin. Il Planning puo consumare disponibilita e capability tramite contratti Core, senza dipendere dalla UI Fleet.

## 6. Learn

**Domanda primaria:** come si completa correttamente il primo ciclo operativo?

**Mostra:** concetti essenziali, workflow consigliato, FAQ e collegamenti alle workspace corrette.

**Azioni:** navigare verso il punto del prodotto necessario.

**Non deve:** diventare documentazione tecnica, duplicare impostazioni o nascondere funzioni operative dentro tutorial.

**Owner:** esperienza prodotto. Il contenuto deve restare coerente con Vision e Roadmap.

## 7. Configuration

**Domanda primaria:** quale configurazione governa questo contesto?

**Mostra:** versione corrente, data di aggiornamento, ambito risolto, fallback e sezioni disponibili.

**Azioni:** nella versione attuale, sola consultazione secondo le API esistenti. Un editor richiede uno sprint dedicato.

**Non deve:** contenere alias verticali fuori dagli Adapter, modificare dati dei Plugin o esporre secret e dettagli infrastrutturali.

**Owner:** Configuration Engine nel Core.

## 8. Import e sincronizzazione

Import e sincronizzazione sono ingressi secondari accessibili dalla workspace proprietaria:

- Planning e dati operativi da Operations;
- stato del parco da Fleet;
- disponibilita o turni da Workforce quando previsto.

Ogni flusso segue lo schema `file -> preview -> mapping -> conferma -> risultato`. Il browser presenta lo stato prodotto dal backend e non inventa associazioni o correzioni.

## 9. Confini tra Home e Operations

Home segnala e indirizza. Operations analizza ed esegue il ciclo di planning.

Una metrica puo comparire in entrambe solo se cambia il livello di dettaglio:

- Home: sintesi, severita, freshness e deep link;
- Operations: evidenze, entita coinvolte, regole applicate e azioni consentite.

La stessa decisione deve avere una sola fonte. Le due schermate non mantengono implementazioni parallele.

## 10. Checklist per nuove schermate

Prima di creare o ampliare una schermata occorre rispondere:

1. Quale domanda primaria risolve?
2. Quale modulo e proprietario dei dati?
3. Quale contratto pubblico viene consumato?
4. Quali decisioni restano nel backend?
5. Quali altre schermate rischiano di essere duplicate?
6. Come si comporta per loading, empty, partial, error e dati obsoleti?
7. Come applica Organization e Operational Unit?
8. La funzione appartiene alla fase corrente della Roadmap?

Se queste risposte non sono esplicite, lo sviluppo non e pronto per iniziare.
