# Operational Unit Model

**Stato:** documento canonico di prodotto e dominio
**Ambito:** modello concettuale; nessuna modifica implementativa
**Riferimenti:** [Operations Engine Vision](OPERATIONS_ENGINE_VISION.md), [Core, Adapter e Plugin Boundaries](CORE_ADAPTER_PLUGIN_BOUNDARIES.md), [Operations Engine Roadmap](OPERATIONS_ENGINE_ROADMAP.md)

## 1. Definizione

Una **Operational Unit** e il perimetro organizzativo nel quale vengono osservati risorse, task, vincoli e decisioni operative.

Esempi neutrali possono essere una sede, un deposito, un hub, un impianto, un punto operativo o una squadra territoriale. Il Core non assume quale di queste interpretazioni sia corretta: la nomenclatura e il significato concreto appartengono alla configurazione dell'organizzazione o all'Adapter attivo.

Una Operational Unit non e una `station`. Una station Amazon viene tradotta dall'Amazon Adapter in una Operational Unit del Core.

## 2. Identita minima

Il modello definitivo dovra poter rappresentare almeno:

- identificatore stabile, univoco nell'organizzazione;
- organizzazione proprietaria;
- nome e label configurabile;
- stato operativo estendibile;
- fuso orario;
- eventuale unita padre, senza imporre una gerarchia;
- intervallo temporale di validita;
- capability e policy applicabili;
- metadati esterni conservati fuori dal linguaggio Core.

Questi attributi descrivono il contratto futuro. Non autorizzano l'introduzione anticipata di nuove tabelle o API.

## 3. Cardinalita e selezione

Un'organizzazione puo avere una o piu Operational Unit. Ogni vista operativa deve dichiarare esplicitamente il proprio ambito:

- una singola Operational Unit;
- un insieme autorizzato di Operational Unit;
- la vista aggregata `Tutte`.

`Tutte` e un aggregato di lettura, non una Operational Unit fittizia. Le modifiche che richiedono ownership certa non devono essere applicate implicitamente dalla vista aggregata.

La selezione dell'unita deve essere stabile durante il flusso di lavoro e condivisa tra le viste che rappresentano lo stesso contesto. Nessun modulo deve dedurre l'unita da stringhe libere quando esiste un identificatore stabile.

## 4. Relazioni con il dominio

### Workforce

Disponibilita, requisiti di copertura ed eventi delle Human Resource possono essere riferiti a una Operational Unit e a un intervallo temporale. Una persona puo essere abilitata a piu unita, ma ogni assegnazione operativa deve avere un ambito esplicito.

### Fleet

Un Asset puo avere una unita corrente, una unita proprietaria o una disponibilita condivisa. Trasferimenti e prestiti devono essere eventi temporali, non sovrascritture prive di storia.

### Task e Planning

Un Task appartiene al perimetro nel quale deve essere eseguito. Planning, capacity e readiness elaborano dati entro un ambito dichiarato e possono produrre aggregazioni multi-unita senza perdere la provenienza.

### Assignment

Ogni Assignment collega risorse e task mantenendo l'identificatore della Operational Unit. Le regole di compatibilita tra unita sono configurabili e non implicite nel nome della sede.

### Briefing ed eventi

Briefing, conflitti e indicatori devono riportare il proprio perimetro. Un risultato aggregato deve poter essere ricondotto alle unita che lo compongono.

## 5. Dati condivisi

Non tutti i dati appartengono a una sola unita. Il modello deve distinguere:

- dati organizzativi globali;
- dati propri di una Operational Unit;
- risorse condivise tra unita;
- dati aggregati di sola lettura;
- configurazioni ereditate e override locali.

L'assenza di unita non deve essere usata come scorciatoia per indicare `Tutte`. Deve significare realmente che il dato e organizzativo o non ancora classificato.

## 6. Risoluzione della configurazione

Il Configuration Engine risolve la configurazione secondo una precedenza esplicita:

1. default sicuro della piattaforma;
2. configurazione dell'organizzazione;
3. configurazione della Operational Unit;
4. configurazione dell'Adapter, quando applicabile;
5. override contestuale autorizzato.

Ogni valore risolto deve conservare origine e versione. Gli Adapter traducono termini esterni, ma non diventano proprietari della configurazione organizzativa.

## 7. Confine con gli Adapter

Un Adapter puo:

- riconoscere identificatori esterni;
- validare formati propri del sistema sorgente;
- tradurre una station, depot o hub in una Operational Unit;
- conservare metadati necessari alla sincronizzazione.

Un Adapter non puo:

- aggiungere codici cliente ai default globali;
- definire la struttura organizzativa per tutte le aziende;
- obbligare il Core a usare la propria nomenclatura;
- usare il nome dell'unita come chiave primaria.

## 8. Invarianti

1. Ogni Operational Unit appartiene a una Organization.
2. Gli identificatori Core sono neutrali e stabili.
3. Le label sono configurabili e non governano la logica.
4. Le viste aggregate non cancellano la provenienza dei dati.
5. I trasferimenti temporali mantengono la cronologia.
6. Core, Plugin e Adapter usano lo stesso riferimento neutrale.
7. Nessun codice cliente entra nei default della piattaforma.
8. Le autorizzazioni future saranno valutate sul perimetro organizzativo, non sul testo visualizzato.

## 9. Stato attuale e percorso

Il progetto possiede gia riferimenti parziali a `operational_unit_id` nel Configuration Engine, nel Workforce e nel Daily Operations Briefing. Il linguaggio legacy `station` resta presente nei contratti compatibili e nella persistenza.

La migrazione deve essere incrementale:

1. definire un riferimento Core stabile;
2. introdurre un registro organizzativo senza cambiare i payload pubblici;
3. tradurre i riferimenti legacy tramite mapper e Adapter;
4. aggiungere selezione e aggregazione coerenti nelle workspace;
5. migrare storage e API solo con un piano esplicito di compatibilita.

La roadmap ufficiale colloca il consolidamento multi-unita nella Fase 4. Questa fase documentale non implementa il registro, la gerarchia, le autorizzazioni o la migrazione dei dati.
