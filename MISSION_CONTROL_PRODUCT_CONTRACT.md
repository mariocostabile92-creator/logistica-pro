# Mission Control Product Contract

**Stato:** contratto di prodotto per la prossima fase; non implementato in questo sprint
**Fase Roadmap:** Fase 3 - Mission Control
**Riferimenti:** [Operations Engine Roadmap](OPERATIONS_ENGINE_ROADMAP.md), [Product Screen Contracts](PRODUCT_SCREEN_CONTRACTS.md), [Operational Unit Model](OPERATIONAL_UNIT_MODEL.md)

## 1. Scopo

Mission Control e la Home operativa di Operations Engine. Deve consentire al responsabile operativo di capire in pochi secondi:

- se i dati sono aggiornati;
- se l'operazione e pronta;
- quali criticita richiedono attenzione;
- quale workspace possiede la prossima azione.

Mission Control non e una dashboard decorativa e non e un nuovo Decision Engine. Organizza snapshot spiegabili gia prodotti dai moduli proprietari.

## 2. Utente e domanda primaria

L'utente principale e il responsabile operativo che supervisiona una o piu Operational Unit.

La domanda primaria e: **cosa richiede la mia attenzione adesso?**

Le domande secondarie sono:

- quali dati mancano o sono obsoleti?
- quali risorse sono disponibili?
- dove esistono conflitti o copertura insufficiente?
- qual e l'impatto e dove posso intervenire?

## 3. Ambito della prima versione

La prima versione comprende:

- selezione dell'ambito organizzativo;
- freshness e completezza dei dati;
- readiness operativa sintetica;
- criticita ordinate per severita e priorita;
- snapshot Workforce e Fleet;
- stato del planning corrente;
- deep link alla workspace proprietaria;
- stati loading, empty, partial, ready, attention, critical ed error.

Non comprende editing, assegnazioni, modifica Asset, modifica turni, configurazione, notifiche, automazioni, AI o nuove regole decisionali.

## 4. Contratto degli snapshot

Mission Control consuma esclusivamente contratti pubblici. Ogni snapshot deve dichiarare almeno:

- `contract_version`;
- `generated_at`;
- `data_as_of`;
- `organization_id`;
- `operational_unit_ids`;
- `status`;
- `freshness`;
- `summary`;
- `issues`;
- `source`;
- `available_actions`.

I nomi sono indicativi del contratto concettuale e non autorizzano nuove API in questo sprint.

Uno snapshot e immutabile per l'istante descritto. Il refresh produce un nuovo snapshot e non altera la storia delle entita sorgente.

## 5. Ownership dei dati

- Planning, conflitti, capacity e readiness: Core.
- Asset, documenti e disponibilita osservata: Fleet Plugin.
- persone, turni, disponibilita e copertura: Workforce Plugin.
- nomenclature, soglie e policy: Configuration Engine.
- mapping del sistema esterno: Adapter attivo.

Mission Control compone i risultati. Non accede a repository, servizi applicativi o modelli interni dei Plugin. I Plugin espongono snapshot tramite porte pubbliche stabili.

## 6. Stati della schermata

### Loading

Mostra struttura stabile e skeleton. Non presenta valori zero come se fossero dati reali.

### Empty

Indica quali dati non esistono e collega al flusso di import corretto. L'assenza di dati non e un errore.

### Partial

Mostra i dati disponibili, segnala fonti mancanti o obsolete e non produce conclusioni che richiedono quelle fonti.

### Ready

Mostra che non risultano blocchi critici per l'ambito e l'istante selezionati. Non promette che eventi successivi non cambieranno lo stato.

### Attention

Mostra warning ordinati, impatto e workspace proprietaria.

### Critical

Porta in primo piano i blocchi operativi con motivazione e riferimenti. Non esegue correzioni automatiche.

### Error

Distingue errore previsto, fonte temporaneamente indisponibile ed errore imprevisto. Mantiene gli snapshot validi gia disponibili quando possibile.

## 7. Operational Unit

La selezione puo riguardare una singola unita o `Tutte`. La vista aggregata:

- conserva la provenienza di ogni criticita;
- non somma metriche incompatibili;
- segnala freshness differenti;
- non consente modifiche ambigue;
- applica le autorizzazioni future per organizzazione e unita.

Il label esterno, come una station, viene risolto dall'Adapter e non entra nel contratto Core.

## 8. Azioni e navigazione

Ogni criticita puo esporre soltanto azioni dichiarate dal modulo proprietario, per esempio:

- apri Operations;
- apri Workforce nel giorno e nell'unita interessati;
- apri Fleet sull'Asset interessato;
- aggiorna una fonte dati tramite il flusso esistente.

Mission Control non inventa pulsanti dalle stringhe dei messaggi e non replica form appartenenti alle workspace.

## 9. Spiegabilita

Ogni decisione o indicatore deve specificare:

- stato e severita;
- motivazione leggibile;
- dati e istante considerati;
- entita e unita coinvolte;
- regola o policy applicata;
- azione suggerita non distruttiva.

Un colore senza testo o una metrica senza provenienza non soddisfano il contratto.

## 10. Requisiti UX

- la situazione primaria deve essere leggibile nel primo viewport;
- il prodotto resta operativo e compatto, senza hero marketing;
- le criticita hanno gerarchia coerente e non dipendono solo dal colore;
- desktop, tablet e mobile mantengono ordine e accessibilita;
- il frontend non ricostruisce readiness o severita;
- nessun errore previsto produce rumore in console;
- refresh e navigazione non cancellano il contesto selezionato.

## 11. Piano incrementale della Fase 3

1. **MC-0 - Contratti pubblici:** definire porte e snapshot versionati senza cambiare UX.
2. **MC-1 - Composizione:** isolare il briefing dagli internals dei Plugin.
3. **MC-2 - Stati e freshness:** uniformare loading, empty, partial ed error.
4. **MC-3 - Ambito:** applicare Organization e Operational Unit alla vista.
5. **MC-4 - Priorita e deep link:** ordinare criticita e collegarle alle workspace proprietarie.
6. **MC-5 - QA:** test di contratto, browser, responsive, accessibilita e performance.

Ogni elemento e uno sprint distinto con un solo obiettivo, secondo [Development Sprint Rules](DEVELOPMENT_SPRINT_RULES.md).

## 12. Criteri di accettazione della fase

La Fase 3 e completata quando:

- Mission Control consuma solo contratti pubblici;
- nessuna regola business viene duplicata nel frontend;
- ogni informazione espone ambito e freshness;
- gli stati vuoto e parziale sono normali e comprensibili;
- ogni azione apre il modulo proprietario;
- Home e Operations hanno responsabilita non sovrapposte;
- i Plugin non dipendono tra loro;
- test e QA verificano i contratti su tutti i viewport previsti.
