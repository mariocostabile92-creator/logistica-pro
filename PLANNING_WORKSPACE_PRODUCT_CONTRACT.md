# Planning Workspace Product Contract

**Stato:** contratto di Product Design; non implementato
**Fase Roadmap:** Fase 4 - Daily Operations
**Owner:** Core Operations e Planning
**Riferimenti vincolanti:** [Operations Engine Vision](OPERATIONS_ENGINE_VISION.md), [Operations Engine Roadmap](OPERATIONS_ENGINE_ROADMAP.md), [Mission Control Product Contract](MISSION_CONTROL_PRODUCT_CONTRACT.md), [Product Screen Contracts](PRODUCT_SCREEN_CONTRACTS.md), [Operational Unit Model](OPERATIONAL_UNIT_MODEL.md), [Core, Adapter, Plugin and Configuration Boundaries](CORE_ADAPTER_PLUGIN_BOUNDARIES.md), [Development Sprint Rules](DEVELOPMENT_SPRINT_RULES.md)

Questo documento definisce il prodotto futuro. Non autorizza modifiche a frontend, backend, API, database, Railway o modelli esistenti. Ogni incremento implementativo richiede uno sprint separato, un contratto dati verificato e il rispetto della roadmap canonica.

## 1. Missione

Planning Workspace è il luogo nel quale il responsabile operativo risponde a una sola domanda:

> Il piano operativo di oggi è corretto e pronto per essere confermato?

La schermata raccoglie gli input già prodotti dai moduli proprietari, ne mostra validità e aggiornamento, espone conflitti e proposte spiegabili, presenta il piano operativo e consente al responsabile di confermarlo e pubblicarlo.

Planning Workspace non è una dashboard. È una scrivania decisionale focalizzata su un piano, una data operativa e un perimetro dichiarato.

## 2. Risultato atteso

Un responsabile deve poter:

1. riconoscere in meno di 10 secondi data, Operational Unit, versione e stato del Planning;
2. capire in meno di 30 secondi se il piano è pronto, incompleto o bloccato;
3. individuare l'elemento che richiede intervento e il modulo proprietario;
4. valutare le conseguenze di una proposta senza leggere dettagli tecnici;
5. correggere esclusivamente il Planning, senza modificare Workforce o Fleet;
6. confermare consapevolmente una versione identificata;
7. pubblicare soltanto la versione confermata e ancora valida;
8. ricostruire chi ha generato, confermato e pubblicato ogni versione.

## 3. Posizione nel prodotto

```text
Mission Control osserva, riassume e indirizza.
Planning Workspace verifica, coordina e decide il piano.
Workforce gestisce persone, disponibilità e turni.
Fleet gestisce Asset, disponibilità e documenti.
Decision Engine produce proposte spiegabili.
Il responsabile operativo conferma e pubblica.
```

### 3.1 Relazione con Mission Control

Mission Control mostra lo stato sintetico e apre Planning Workspace con data e Operational Unit già selezionate. Non replica conflitti dettagliati, proposta operativa, comandi di conferma o pubblicazione.

Planning Workspace restituisce a Mission Control uno stato sintetico già prodotto dal Core. Mission Control non ricalcola readiness, priorità o stato del Planning.

### 3.2 Relazione con Workforce

Planning Workspace utilizza riferimenti a Human Resource, disponibilità e capability pubblicate da Workforce. Può indicare che una risorsa non è disponibile o che un dato deve essere aggiornato, ma non crea persone, non modifica turni, non registra assenze e non amministra profili.

Quando il problema appartiene a Workforce, l'azione apre Workforce mantenendo data, Operational Unit e riferimento coinvolto. Al ritorno, Planning Workspace aggiorna il proprio stato senza perdere il contesto di lavoro.

### 3.3 Relazione con Fleet

Planning Workspace utilizza riferimenti ad Asset, disponibilità e capability pubblicate da Fleet. Può sostituire il riferimento a un Asset dentro una bozza di Planning, ma non cambia lo stato osservato dell'Asset, i documenti, le note o la cronologia Fleet.

Quando il problema appartiene a Fleet, l'azione apre Fleet sull'Asset interessato. La correzione del dato avviene nel workspace proprietario.

### 3.4 Relazione con Adapter e Configuration

Planning Workspace usa soltanto concetti Core e nomenclature risolte. Un Adapter traduce termini e identificatori esterni prima che raggiungano il Planning; non appare come attore operativo nell'interfaccia.

Soglie, policy, priorità, capability e label variabili provengono dalla configurazione risolta. Il frontend non interpreta alias esterni e non contiene regole per una singola organizzazione o mercato.

## 4. Confini inviolabili

| Planning Workspace può | Planning Workspace non può |
| --- | --- |
| mostrare disponibilità pubblicate | creare o modificare persone |
| usare riferimenti a Human Resource e Asset | modificare turni o assenze |
| generare e correggere una bozza di Planning | cambiare lo stato osservato di un Asset |
| mostrare Conflict, Capacity e Readiness del Core | gestire documenti o manutenzione |
| applicare una decisione alla bozza dopo conferma umana | applicare modifiche silenziose ad altri moduli |
| confermare e pubblicare una versione | pubblicare dalla vista aggregata `Tutte` |
| conservare provenienza e storia delle versioni | esporre dettagli di file, mapping o sistemi esterni |

Il Planning coordina Resource e Task; non diventa proprietario del loro ciclo di vita.

## 5. Utente e contesto operativo

L'utente principale è il responsabile operativo incaricato di verificare e rendere ufficiale il piano della giornata. Gli utenti secondari possono consultare il piano secondo autorizzazioni future, ma il contratto non introduce ruoli o permessi.

Il contesto minimo di ogni sessione è:

- organizzazione;
- data operativa;
- una Operational Unit oppure la vista aggregata `Tutte`;
- versione del Planning;
- istante di riferimento degli input;
- stato del ciclo di vita.

Data e Operational Unit non sono filtri decorativi: definiscono l'identità del piano osservato.

## 6. Workflow operativo

```text
Mission Control
  |
  +--> Workforce, solo se persone o turni richiedono intervento
  |
  +--> Fleet, solo se Asset o disponibilità richiedono intervento
  |
  v
Planning Workspace
  -> verifica input
  -> genera o apre la proposta corrente
  -> esamina conflitti
  -> valuta proposte
  -> corregge la bozza di Planning
  -> verifica readiness
  -> conferma una versione
  -> pubblica la versione confermata
  v
Operatività
  -> Timeline
  -> Analisi
```

La sequenza Workforce -> Fleet -> Planning rappresenta ownership e preparazione, non obbliga l'utente a visitare ogni schermata. Se gli input sono aggiornati e validi, Mission Control può aprire direttamente Planning Workspace.

### 6.1 Percorso standard

1. Il responsabile apre Planning Workspace da Mission Control.
2. Data e Operational Unit vengono mantenute.
3. L'Header identifica la versione corrente e l'ultimo aggiornamento.
4. Readiness fornisce una sola risposta.
5. Gli input dichiarano disponibilità, stato e freshness.
6. I conflitti sono ordinati per impatto operativo.
7. Le decisioni suggerite spiegano motivo, impatto e modulo origine.
8. Il responsabile valuta e modifica soltanto la bozza del Planning.
9. Quando il Core dichiara il piano pronto, il responsabile conferma la versione.
10. La pubblicazione rende ufficiale quella stessa versione.
11. Generazione, conferma e pubblicazione entrano nello storico.

### 6.2 Ritorno da un workspace proprietario

Quando l'utente apre Workforce o Fleet per correggere un dato:

- data e Operational Unit restano nel collegamento;
- il browser Back riporta alla stessa versione e posizione del Planning;
- il contenuto valido rimane visibile durante l'aggiornamento;
- eventuali cambi di input sono dichiarati;
- una versione già confermata non viene alterata silenziosamente.

## 7. Gerarchia delle informazioni

### Livello 1 - Decisione

Readiness risponde se il Planning è pronto, incompleto o bloccato. Stato, motivazione principale e prossima azione devono stare nel primo viewport.

### Livello 2 - Intervento

Conflitti bloccanti, warning ed elementi da verificare. L'utente deve sapere cosa impedisce la conferma e dove intervenire.

### Livello 3 - Piano

La proposta operativa è il contenuto principale e occupa la maggior parte dello spazio disponibile.

### Livello 4 - Evidenze

Input disponibili e decisioni suggerite spiegano perché il piano si trova nello stato corrente. Non duplicano i workspace proprietari.

### Livello 5 - Contesto e audit

Versione, ultimo aggiornamento, conferma, pubblicazione e storico supportano fiducia e ricostruzione senza competere con il lavoro corrente.

## 8. Layout desktop

### 8.1 Struttura

- griglia a 12 colonne;
- contenuto principale Planning: 8 colonne;
- colonna decisionale: 4 colonne;
- Header, Readiness e Input disponibili a larghezza piena;
- Storico a larghezza piena dopo l'area di lavoro;
- nessuna card dentro un'altra card;
- nessun pannello con scroll verticale indipendente nel flusso principale;
- barra di conferma contestuale e stabile, senza coprire il contenuto.

### 8.2 Wireframe desktop

```text
+--------------------------------------------------------------------------------------+
| PLANNING WORKSPACE                                  Aggiorna                          |
| Mar 22 luglio | Operational Unit: Unità A | v12 | Bozza | Aggiornato 07:18          |
+--------------------------------------------------------------------------------------+
| READINESS                                                                            |
| [ATTENZIONE] Planning incompleto                                                      |
| 2 elementi devono essere verificati prima della conferma.          Verifica conflitti |
+--------------------------------------------------------------------------------------+
| INPUT DISPONIBILI                                                                    |
| Workforce  Disponibile  07:10 | Fleet  Disponibile  07:12 | Task  Parziale  06:58   |
+---------------------------------------------------------+----------------------------+
| PROPOSTA OPERATIVA                                      | CONFLITTI                  |
| [Tutti] [Blocchi] [Da verificare]                       | Bloccanti (1)             |
|                                                         | Asset non disponibile      |
| Task      Finestra       Risorsa       Asset    Stato   | Impatto: 1 Task scoperto  |
| T-021     08:00-12:00    Risorsa 14    A-08     Pronto  | Apri Fleet                |
| T-022     08:30-13:00    Risorsa 09    --       Blocco  |                            |
| T-023     09:00-14:00    Risorsa 07    A-11     Verifica| Da verificare (1)         |
| ...                                                     | Capability da confermare  |
|                                                         +----------------------------+
|                                                         | DECISIONI SUGGERITE        |
|                                                         | Sostituisci Asset A-08     |
|                                                         | Motivo · Impatto · Origine |
|                                                         | Valuta proposta            |
+---------------------------------------------------------+----------------------------+
| VERSIONE CORRENTE v12 | 24 Task | 1 blocco | 1 verifica                           |
| [Conferma Planning - non disponibile]                         Pubblica - non disponibile|
+--------------------------------------------------------------------------------------+
| STORICO | v12 Generata 07:18 | v11 Confermata 06:54 | v10 Pubblicata ieri 07:26    |
+--------------------------------------------------------------------------------------+
```

Il primo viewport contiene Header, Readiness, stato degli input e l'inizio di Planning e conflitti. Lo storico può restare sotto la piega.

## 9. Contratto dei blocchi

### 9.1 Blocco 1 - Header

#### Scopo

Identificare senza ambiguità il piano sul quale l'utente sta lavorando.

#### Contenuti obbligatori

- titolo `Planning Workspace`;
- data operativa, distinta dalla data corrente;
- Operational Unit;
- versione del Planning;
- stato del Planning;
- ultimo aggiornamento;
- comando di aggiornamento non distruttivo.

#### Stati del Planning nell'Header

| Stato | Significato | Azione principale |
| --- | --- | --- |
| Non generato | non esiste ancora una proposta per il contesto | genera proposta |
| Bozza | versione modificabile e non confermata | verifica e correggi |
| Da rivedere | input rilevanti sono cambiati dopo la generazione | aggiorna la proposta |
| Pronto per conferma | readiness positiva per la versione corrente | conferma Planning |
| Confermato | versione approvata e immutabile | pubblica |
| Pubblicato | versione ufficiale per l'operatività | consulta o crea nuova bozza |
| Superato | esiste una versione successiva | apri versione corrente |

Lo stato è prodotto dal Core. Il frontend non lo deduce combinando badge o conteggi.

#### Operational Unit

- una singola unità abilita le azioni coerenti con lo stato;
- `Tutte` mostra una panoramica di sola lettura per unità;
- conferma, pubblicazione e modifiche sono disabilitate nella vista aggregata;
- scegliere un'unità conserva data e, quando valida, versione selezionata;
- una risorsa condivisa conserva sempre la propria provenienza.

`Tutte` non è un'unità fittizia e non produce una versione aggregata modificabile.

### 9.2 Blocco 2 - Readiness

#### Scopo

Fornire una sola risposta alla domanda primaria della schermata.

#### Stati canonici

| Stato | Etichetta | Significato | Comportamento |
| --- | --- | --- | --- |
| Ready | Planning pronto | input richiesti validi, proposta corrente e nessun blocco dichiarato | abilita il percorso di conferma |
| Incomplete | Planning incompleto | manca un input, una proposta o una verifica richiesta | indica il prossimo passo |
| Blocked | Conflitti bloccanti | almeno un conflitto impedisce la conferma | porta al primo blocco operativo |

Priorità di presentazione: `Conflitti bloccanti` precede `Planning incompleto`, che precede `Planning pronto`. Questa priorità appartiene al contratto Core; non viene ricostruita nel browser.

#### Contenuto

- etichetta completa;
- una frase che spiega il motivo principale;
- numero di elementi solo quando aiuta l'azione;
- istante dei dati considerati;
- una sola azione primaria.

Readiness non contiene una griglia KPI, percentuali decorative o semafori privi di testo.

#### Regole

- un warning non diventa automaticamente bloccante;
- un elemento `Da verificare` segue la policy dichiarata dal Core;
- dati mancanti non producono un falso stato positivo;
- durante loading o indisponibilità globale non viene simulata una risposta;
- la conferma è disponibile solo per la versione alla quale la readiness si riferisce.

### 9.3 Blocco 3 - Input disponibili

#### Scopo

Rendere visibile se Planning sta lavorando su input completi e recenti, senza ricreare Workforce o Fleet.

#### Righe previste

- Workforce;
- Fleet;
- Task;
- eventuali altre fonti Core dichiarate in futuro.

#### Informazioni per riga

| Campo | Contenuto |
| --- | --- |
| Input | nome operativo comprensibile |
| Disponibilità | copertura del dato richiesto per il piano |
| Stato | Disponibile, Parziale, Mancante, Da aggiornare, Non disponibile |
| Freshness visibile | `Aggiornato 8 min fa` |
| Istante preciso | disponibile nel dettaglio accessibile |
| Impatto | cosa limita o impedisce nel Planning |
| Azione | apri il workspace proprietario quando necessaria |

#### Regole

- non mostra persone, turni, Asset o documenti in elenco completo;
- non usa il valore `0` per rappresentare una fonte non caricata;
- mantiene visibile l'ultimo dato valido quando dichiarato obsoleto;
- non somma fonti con Operational Unit incompatibili;
- non consente modifiche inline a dati di Workforce o Fleet.

### 9.4 Blocco 4 - Conflitti

#### Scopo

Mostrare esclusivamente ciò che condiziona correttezza e conferma del piano.

#### Gruppi

1. **Conflitti bloccanti:** impediscono la conferma.
2. **Warning:** richiedono attenzione ma non impediscono automaticamente la conferma.
3. **Da verificare:** ambiguità o dati che richiedono una decisione umana secondo policy.

#### Anatomia di un conflitto

- titolo operativo;
- Task, Assignment o Resource coinvolta;
- motivo leggibile;
- impatto sul piano;
- Operational Unit;
- istante dei dati;
- modulo origine;
- azione consentita.

I codici stabili restano disponibili per audit e supporto, ma non sono il titolo visibile.

#### Comportamento

- selezionare un conflitto evidenzia la parte correlata del Planning;
- il CTA apre il workspace proprietario quando la causa non appartiene al Planning;
- il ritorno conserva conflitto selezionato, scroll e contesto;
- un conflitto risolto scompare solo dopo una nuova valutazione dichiarata;
- l'ordinamento segue severità e impatto ricevuti, non parole cercate nel messaggio;
- nessuna correzione viene applicata automaticamente.

#### Stato senza conflitti

```text
Nessun conflitto rilevato
Valutazione eseguita sui dati aggiornati alle 07:18.
```

La frase non equivale a `Planning pronto` se mancano altri requisiti.

### 9.5 Blocco 5 - Decisioni suggerite

#### Scopo

Offrire supporto decisionale spiegabile. Non è una chat, non è AI e non sostituisce il responsabile.

#### Contenuto obbligatorio di ogni proposta

- azione suggerita;
- motivo;
- impatto atteso;
- modulo origine dei fatti;
- regola o vincolo applicato in forma leggibile;
- alternative disponibili, quando esistono;
- stato: Da valutare, Applicata alla bozza, Non applicata.

#### Esempi di microcopy

```text
Sostituisci Asset A-08
Motivo: l'Asset assegnato risulta indisponibile.
Impatto: il Task T-022 torna coperto senza modificare Fleet.
Origine: Fleet
[Valuta proposta]
```

```text
Riduci la capacità pianificata di 1 Task
Motivo: le risorse disponibili non coprono il fabbisogno corrente.
Impatto: un Task resta fuori dalla versione da confermare.
Origine: Workforce e Planning
[Valuta proposta]
```

#### Regole

- `Valuta proposta` apre il contesto, non applica subito la decisione;
- l'applicazione riguarda soltanto la bozza corrente;
- ogni applicazione produce una modifica attribuibile e annullabile finché la bozza non è confermata;
- una proposta obsoleta non può essere applicata;
- il sistema non presenta una proposta se motivo o impatto non sono disponibili;
- l'assenza di proposte è uno stato normale;
- proposte probabilistiche future devono essere dichiarate come tali, senza confonderle con regole deterministiche.

L'implementazione di questo blocco appartiene alla fase Decision Support della roadmap e non deve essere anticipata senza il relativo contratto Core. Prima di allora il workspace può mostrare solo risultati già prodotti da capacità esistenti, senza placeholder che fingano decisioni reali.

### 9.6 Blocco 6 - Planning

#### Scopo

Mostrare e correggere la proposta operativa. È il contenuto principale della pagina.

#### Contenuto ammesso

- Task o gruppo operativo;
- Time Window;
- riferimenti alle Resource assegnate;
- riferimento all'Asset assegnato quando necessario;
- stato dell'Assignment;
- indicatori di conflitto o verifica;
- provenienza della modifica manuale;
- stato della riga rispetto alla versione corrente.

#### Contenuto vietato

- profilo completo della persona;
- calendario Workforce;
- modifica turno o assenza;
- documenti, note tecniche o cronologia completa dell'Asset;
- modifica dello stato Fleet;
- mapping di colonne, file sorgente o termini di un sistema esterno;
- readiness ricalcolata nel frontend.

#### Forma desktop

Una tabella operativa densa ma leggibile. Le colonne identificative e lo stato restano stabili; dettagli secondari sono accessibili su richiesta. Filtri ammessi: Tutti, Blocchi, Warning, Da verificare. I filtri non cambiano il risultato della valutazione.

#### Comportamento

- selezione di una riga mostra il contesto strettamente necessario alla decisione;
- una modifica riguarda solo Assignment o attributi posseduti dal Planning;
- i riferimenti a Resource e Asset usano liste già autorizzate e disponibili;
- una modifica invalida non viene accettata dal Core;
- il salvataggio aggiorna la bozza senza refresh completo;
- modifiche manuali indicano actor, timestamp e motivazione quando richiesta;
- ogni cambiamento che incide sulla readiness richiede una nuova valutazione;
- nessuna modifica cambia in modo implicito i moduli origine.

### 9.7 Blocco 7 - Conferma e pubblicazione

#### Principio

Conferma e pubblicazione sono due atti distinti.

```text
Bozza pronta
  -> Conferma Planning
  -> Versione confermata e immutabile
  -> Pubblica
  -> Versione ufficiale per l'operatività
```

#### Conferma

La conferma dichiara che il responsabile ha verificato una specifica versione per una data e una Operational Unit.

Prima del comando vengono mostrati:

- versione;
- data operativa;
- Operational Unit;
- numero di Task inclusi;
- warning ancora aperti;
- istante degli input considerati.

La conferma non è disponibile quando:

- la vista è `Tutte`;
- non esiste una bozza;
- la readiness non è `Planning pronto`;
- gli input rilevanti sono cambiati;
- la versione selezionata non è quella corrente;
- un aggiornamento o una valutazione è ancora in corso.

#### Pubblicazione

La pubblicazione rende ufficiale una versione già confermata. Il comando deve nominare chiaramente versione, data e Operational Unit.

La pubblicazione non è disponibile quando:

- la versione non è confermata;
- esiste un cambiamento che ha invalidato la conferma;
- la pubblicazione è già in corso;
- l'ambito è aggregato;
- la versione è stata superata.

#### Cambi successivi

- una versione confermata o pubblicata non viene sovrascritta;
- una correzione crea o apre una nuova bozza collegata alla versione precedente;
- lo stato ufficiale resta riconoscibile finché la nuova versione non viene pubblicata;
- nessun ricalcolo sostituisce silenziosamente una versione confermata;
- ogni transizione registra actor, timestamp e motivo disponibile.

#### Feedback

```text
Planning v12 confermato
Confermato da Responsabile operativo alle 07:31.
```

```text
Planning v12 pubblicato
La versione è ora quella operativa per Unità A.
```

Il feedback è inline, accessibile e non richiede un refresh pagina.

### 9.8 Blocco 8 - Storico

#### Scopo

Ricostruire il ciclo del Planning senza duplicare la futura Timeline operativa generale.

#### Eventi minimi

- versione generata;
- versione aggiornata;
- versione confermata;
- versione pubblicata;
- versione superata;
- conferma invalidata da un cambiamento rilevante, se previsto dal Core.

#### Informazioni

- versione;
- evento;
- data e ora;
- actor;
- Operational Unit;
- collegamento alla versione consultabile;
- motivazione quando disponibile.

#### Regole

- ordine cronologico inverso iniziale;
- massimo cinque eventi nel riepilogo;
- `Mostra storico` apre la consultazione completa;
- lo storico è immutabile e non offre azioni di modifica;
- gli eventi del Planning possono alimentare la futura Timeline, ma non vengono ricostruiti nel browser;
- la storia non è un log tecnico.

## 10. Ciclo di vita del Planning

```text
Non generato
    |
    v
Bozza <-------------------------------+
    |                                  |
    +--> Da rivedere ------------------+
    |
    +--> Conflitti bloccanti -> correzione -> nuova valutazione
    |
    v
Pronto per conferma
    |
    v
Confermato -- cambiamento rilevante --> nuova Bozza
    |
    v
Pubblicato -- correzione necessaria --> nuova Bozza
```

Il ciclo non consente salti diretti da Bozza a Pubblicato. Una transizione fallita mantiene lo stato precedente e spiega l'azione necessaria.

## 11. Stati della schermata

### 11.1 Loading iniziale

- Header, Readiness, Input, Planning e colonna decisionale mantengono dimensioni stabili;
- gli skeleton riproducono la forma del contenuto senza mostrare valori fittizi;
- non viene mostrato `0 conflitti` prima della risposta valida;
- l'animazione è discreta e rispettosa di `prefers-reduced-motion`;
- dopo una soglia ragionevole appare `Caricamento del Planning in corso`.

### 11.2 Aggiornamento locale

Il contenuto valido resta visibile. Il blocco interessato mostra `Aggiornamento in corso` e conserva l'ultimo istante valido. Focus, selezione e scroll non vengono azzerati.

### 11.3 Empty state

```text
Planning non ancora generato
Non esiste una proposta per martedì 22 luglio, Unità A.

Workforce   Disponibile
Fleet       Da aggiornare
Task        Disponibile

[Aggiorna Fleet]   [Genera proposta - non disponibile]
```

Lo stato vuoto spiega la sequenza necessaria. Non mostra un errore e non presenta come attivo un comando i cui prerequisiti mancano.

### 11.4 Stato parziale

Mostra il piano e gli input validi disponibili, identifica il dato mancante e disabilita soltanto le azioni che richiedono quel dato. Non formula una readiness positiva se la valutazione è incompleta.

### 11.5 Dati da aggiornare

- mantiene visibile l'ultima versione valida;
- mostra quale input è cambiato o ha superato la soglia configurata;
- usa `Planning da rivedere`, non `Planning pronto`;
- offre l'azione corretta senza rigenerare automaticamente;
- non perde modifiche manuali senza una decisione esplicita.

### 11.6 Errore previsto

Esempi: versione non più corrente, conflitto già risolto, input non disponibile, conferma non consentita.

Il messaggio descrive cosa è accaduto e come continuare. Non usa codici tecnici e non produce rumore in console.

### 11.7 Indisponibilità di un blocco

Il problema resta confinato al blocco interessato. Gli altri dati restano consultabili. Se esiste una versione valida precedente, viene mostrata con il relativo timestamp e la limitazione operativa.

### 11.8 Indisponibilità globale

```text
Planning temporaneamente non disponibile
Non è stato possibile caricare lo stato corrente.

[Riprova]   [Torna a Mission Control]
```

Nessun dettaglio infrastrutturale, stack trace o payload viene mostrato. Una versione non verificata non può essere confermata o pubblicata.

### 11.9 Stato `Tutte`

```text
Operational Unit: Tutte

Unità A   Pronto per conferma    v12   Aggiornato 07:18   Apri
Unità B   Conflitti bloccanti    v08   Aggiornato 07:14   Apri
Unità C   Planning incompleto    --    Aggiornato 06:55   Apri
```

È una vista di orientamento. Non somma piani incompatibili, non crea un Planning aggregato e non consente conferma o pubblicazione multipla.

## 12. Colori semantici

I colori restano coerenti con Mission Control.

| Ruolo | Testo/bordo | Fondo tenue | Uso nel Planning Workspace |
| --- | --- | --- | --- |
| Pronto | `#176B45` | `#E8F5EE` | readiness positiva, conferma riuscita, pubblicazione riuscita |
| Attenzione | `#8A5700` | `#FFF3D6` | Planning incompleto, warning, dati da aggiornare |
| Critico | `#A62A21` | `#FDECEA` | conflitti bloccanti e azioni impedite |
| Informazione | `#245B85` | `#EAF2F8` | selezione, versione confermata, collegamenti e aggiornamenti |
| Neutro | `#4F5B56` | `#F1F3F2` | bozza, stato non disponibile, storico e metadati |
| Testo principale | `#17211D` | `#FFFFFF` | contenuto operativo |
| Bordo | `#C9D1CD` | - | separazione delle aree |

### Regole

- il colore non è mai l'unico segnale;
- ogni stato usa icona, etichetta e spiegazione;
- contrasto minimo WCAG AA;
- focus visibile di almeno 2 px;
- rosso riservato ai blocchi reali;
- verde non viene mostrato durante loading o su dati non aggiornati;
- niente gradienti o decorazioni prive di significato;
- lo stato del ciclo di vita e la severità non condividono badge ambigui.

## 13. Comportamento e interazioni

### 13.1 Aggiornamento

- aggiorna i dati senza reset completo della pagina;
- mantiene contesto, filtri, selezione e focus;
- dichiara il nuovo istante di riferimento;
- segnala se la versione è cambiata;
- non applica automaticamente una nuova proposta sopra modifiche manuali.

### 13.2 Selezione e navigazione

- un conflitto seleziona la riga Planning correlata;
- una riga Planning può mostrare soltanto il dettaglio necessario alla decisione;
- i deep link verso Workforce e Fleet conservano il contesto;
- il browser Back ripristina posizione e focus quando possibile;
- `Esc` chiude pannelli o menu non persistenti;
- `Enter` attiva il comando focalizzato;
- nessuna scorciatoia esegue conferma o pubblicazione senza riepilogo esplicito.

### 13.3 Comandi primari

In ogni stato esiste una sola azione primaria visivamente dominante:

| Stato | Azione primaria |
| --- | --- |
| Non generato | Genera proposta |
| Incompleto | Completa input o verifica richiesta |
| Bloccato | Risolvi primo conflitto |
| Pronto | Conferma Planning |
| Confermato | Pubblica |
| Pubblicato | Consulta versione ufficiale |

Le azioni secondarie restano disponibili ma non competono visivamente.

### 13.4 Sicurezza delle decisioni

- nessun autosalvataggio trasforma una bozza in versione confermata;
- conferma e pubblicazione richiedono comandi espliciti;
- doppio invio non duplica la transizione;
- durante una transizione il comando mostra stato in corso e non cambia dimensione;
- un conflitto di versione interrompe l'azione e propone di aggiornare;
- una risposta tardiva non sovrascrive una versione più recente;
- i messaggi di successo nominano sempre versione e ambito.

## 14. Responsive

Desktop, tablet e mobile presentano lo stesso prodotto e gli stessi stati. Cambiano densità e forma, non ownership o significato.

### 14.1 Tablet - da 768 a 1199 px

- Header su due righe;
- Readiness a larghezza piena;
- Input disponibili in griglia 2 + 1, senza testo troncato;
- conflitti prima del Planning quando esiste un blocco;
- Planning in tabella compatta con identificatore iniziale stabile;
- decisioni suggerite sotto i conflitti;
- storico in fondo;
- target interattivi di almeno 44 x 44 px;
- eventuale scorrimento orizzontale è confinato alla sola tabella Planning e dichiarato visivamente.

#### Wireframe tablet

```text
+----------------------------------------------------------+
| PLANNING WORKSPACE                         Aggiorna       |
| Mar 22 luglio | Operational Unit: Unità A                |
| v12 | Bozza | Aggiornato 07:18                           |
+----------------------------------------------------------+
| PLANNING INCOMPLETO                                      |
| 2 elementi devono essere verificati.       Verifica      |
+----------------------------------------------------------+
| Workforce Disponibile | Fleet Disponibile                |
| Task Parziale          | Dati aggiornati 07:18           |
+----------------------------------------------------------+
| CONFLITTI                                               |
| [Blocco] Asset non disponibile              Apri Fleet   |
+----------------------------------------------------------+
| DECISIONI SUGGERITE                                    |
| Sostituisci Asset A-08                     Valuta        |
+----------------------------------------------------------+
| PROPOSTA OPERATIVA                                     |
| Task | Finestra | Risorsa | Asset | Stato               |
| ...                                                     |
+----------------------------------------------------------+
| v12 | [Conferma non disponibile] [Pubblica non disponibile]|
+----------------------------------------------------------+
| STORICO                                                 |
+----------------------------------------------------------+
```

### 14.2 Mobile - fino a 767 px

- una sola colonna;
- data e versione nella prima riga;
- selettore Operational Unit a larghezza piena;
- Readiness immediatamente visibile;
- input in righe compatte;
- conflitti e decisioni prima delle schede Planning;
- proposta operativa resa come schede Task, non come tabella compressa;
- una sola azione primaria in barra contestuale non sovrapposta alla navigazione;
- storico inizialmente sintetico;
- nessuno scroll orizzontale;
- nessuna informazione essenziale disponibile solo al passaggio del mouse.

#### Wireframe mobile

```text
+--------------------------------+
| PLANNING               v12     |
| Mar 22 luglio                   |
| [Operational Unit: Unità A  v] |
| Bozza | Aggiornato 07:18        |
+--------------------------------+
| PLANNING INCOMPLETO             |
| 2 elementi da verificare        |
| Verifica conflitti              |
+--------------------------------+
| INPUT                           |
| Workforce  Disponibile   07:10  |
| Fleet      Disponibile   07:12  |
| Task       Parziale      06:58  |
+--------------------------------+
| CONFLITTI                       |
| Blocca conferma                 |
| Asset non disponibile           |
| Task T-022 | Unità A            |
| Apri Fleet                      |
+--------------------------------+
| DECISIONE SUGGERITA             |
| Sostituisci Asset A-08          |
| Motivo e impatto                |
| Valuta proposta                 |
+--------------------------------+
| PROPOSTA OPERATIVA              |
| Task T-021          Pronto      |
| 08:00-12:00                    > |
| Risorsa 14 | Asset A-11         |
| --------------------------------|
| Task T-022          Blocco      |
| 08:30-13:00                    > |
+--------------------------------+
| Conferma non disponibile        |
+--------------------------------+
| Storico                         |
+--------------------------------+
```

### 14.3 Ordine responsive stabile

1. Header;
2. Readiness;
3. Input disponibili;
4. conflitti;
5. decisioni suggerite;
6. Planning;
7. conferma o pubblicazione;
8. storico.

L'ordine non cambia automaticamente in base alla severità. La priorità è resa all'interno del blocco, così l'utente conserva memoria spaziale.

## 15. Linguaggio operativo

### 15.1 Principi

- usare verbi come `Verifica`, `Risolvi`, `Valuta`, `Conferma`, `Pubblica`;
- descrivere effetto e impatto, non implementazione;
- usare la nomenclatura organizzativa solo quando risolta in modo esplicito;
- preferire `risorsa`, `Asset`, `Task`, `Planning` e `Operational Unit` nel linguaggio neutrale;
- non promettere correttezza oltre i dati e l'istante disponibili;
- non usare punti esclamativi o tono allarmistico;
- rendere chiaro quando un'informazione è parziale o da aggiornare.

### 15.2 Termini vietati nell'interfaccia

- `errore 500`;
- `warning tecnico`;
- `JSON`;
- `adapter`;
- `snapshot`;
- stack trace, nomi di tabelle o endpoint;
- codici di conflitto come titolo principale;
- termini esterni non risolti dalla nomenclatura configurata.

### 15.3 Esempi

| Evitare | Usare |
| --- | --- |
| `Fleet API error` | `Stato Fleet non disponibile` |
| `Conflict VU-03` | `L'Asset assegnato non è disponibile` |
| `Snapshot stale` | `Dati da aggiornare` |
| `Invalid payload` | `Il Planning è cambiato: aggiorna prima di confermare` |
| `Publish failed` | `Pubblicazione non completata. La versione confermata è ancora disponibile.` |

## 16. Accessibilità

- un solo `h1` e sezioni in ordine logico;
- landmark distinti per intestazione, navigazione, contenuto e storico;
- stato Readiness esposto come frase completa;
- colore sempre accompagnato da icona e testo;
- contrasto WCAG AA;
- focus visibile e non coperto dalla barra contestuale;
- ordine Tab coerente con la gerarchia visiva;
- target touch di almeno 44 x 44 px;
- aggiornamenti locali annunciati con modalità non invasiva;
- conferma e pubblicazione annunciate chiaramente;
- skeleton non letti ripetutamente dagli screen reader;
- zoom 200% senza sovrapposizioni o perdita di comandi;
- supporto a `prefers-reduced-motion`;
- tabelle desktop con intestazioni correttamente associate;
- schede mobile con lo stesso nome accessibile delle righe desktop.

## 17. Continuità e prestazioni percepite

- il primo viewport deve diventare utile prima dello storico;
- Header e struttura principale non devono spostarsi durante il caricamento;
- aggiornare un blocco non oscura l'intera pagina;
- l'ultimo stato valido resta consultabile quando consentito;
- nessun polling aggressivo è richiesto dal contratto;
- filtri e selezioni non avviano ricalcoli non necessari;
- il ritorno da Workforce o Fleet non ricostruisce la pagina da zero quando il contesto è ancora valido;
- liste lunghe adottano progressivamente tecniche di rendering efficienti senza cambiare il contratto UX;
- la pagina non richiede nuove query o endpoint finché i contratti disponibili non sono stati inventariati in uno sprint dedicato.

## 18. Motivazioni UX

### Perché una sola Readiness

Il responsabile deve prendere una decisione, non interpretare una parete di indicatori. I dettagli spiegano la risposta, ma non la sostituiscono.

### Perché il Planning occupa più spazio

Il prodotto della schermata è il piano operativo. Input, conflitti e proposte esistono per verificarlo e correggerlo.

### Perché gli input sono sintetici

Workforce e Fleet hanno workspace propri. Duplicarne i dettagli produrrebbe dati divergenti, azioni ambigue e dipendenze tra moduli.

### Perché conflitti e proposte sono distinti

Un conflitto è un fatto o una violazione rilevata. Una proposta è una possibile risposta. Separarli impedisce che una raccomandazione venga scambiata per obbligo.

### Perché conferma e pubblicazione sono separate

Confermare significa approvare il contenuto; pubblicare significa renderlo operativo. La separazione riduce pubblicazioni accidentali e rende l'audit comprensibile.

### Perché `Tutte` è di sola lettura

Una decisione operativa deve avere ownership certa. La vista aggregata orienta, ma non applica azioni potenzialmente incompatibili a più unità.

### Perché la storia è sintetica

Il responsabile deve riconoscere la versione corrente senza trasformare la schermata in un registro tecnico. La futura Timeline conserva la visione causale completa della giornata.

## 19. Allineamento alla roadmap

Questo contratto dettaglia la **Fase 4 - Daily Operations** già presente nella roadmap canonica. Non modifica lo stato delle fasi e non anticipa la Fase 5 Timeline o la Fase 6 Decision Support.

La seguente formulazione è la proposta di allineamento da valutare in un futuro sprint documentale dedicato:

> Planning Workspace è il cuore operativo del prodotto. Mission Control osserva. Planning Workspace decide. Workforce gestisce persone. Fleet gestisce mezzi. Decision Engine propone. Il responsabile conferma.

Il rapporto tra le macro-fasi resta:

```text
Fase 3 - Mission Control
  osserva e indirizza
       |
       v
Fase 4 - Planning Workspace / Daily Operations
  verifica, coordina, conferma e pubblica
       |
       v
Fase 5 - Daily Timeline
  conserva la sequenza causale
       |
       v
Fase 6 - Decision Support
  propone alternative spiegabili
```

## 20. Criteri di accettazione del prodotto

### Missione e comprensione

- [ ] La schermata risponde soltanto alla domanda sulla correttezza e confermabilità del piano.
- [ ] Data, Operational Unit, versione, stato e ultimo aggiornamento sono riconoscibili nel primo viewport.
- [ ] Il responsabile distingue pronto, incompleto e conflitti bloccanti entro 30 secondi.
- [ ] Non esiste una parete di KPI.

### Ownership

- [ ] Planning Workspace non crea persone o Asset.
- [ ] Planning Workspace non modifica turni, assenze, documenti o stato Fleet.
- [ ] I dati dei Plugin arrivano tramite contratti pubblici e non tramite modelli interni.
- [ ] Adapter e dettagli di import non appaiono nella logica o nel linguaggio della schermata.
- [ ] Readiness, Capacity, Conflict e stato del Planning non vengono ricalcolati nel frontend.

### Input, conflitti e decisioni

- [ ] Ogni input dichiara stato, disponibilità, freshness e impatto.
- [ ] I dati mancanti non vengono presentati come zero.
- [ ] I conflitti sono separati in bloccanti, warning e da verificare.
- [ ] Ogni conflitto mostra motivo, impatto, ambito e azione.
- [ ] Ogni proposta mostra motivo, impatto e modulo origine.
- [ ] Nessuna proposta viene applicata senza valutazione umana.
- [ ] Una modifica suggerita cambia soltanto la bozza del Planning.

### Planning e lifecycle

- [ ] La proposta operativa è il contenuto principale.
- [ ] Il Planning non duplica dettagli Workforce o Fleet.
- [ ] Una modifica manuale conserva actor, timestamp e provenienza.
- [ ] Conferma e pubblicazione sono comandi distinti.
- [ ] Solo una versione pronta, corrente e riferita a una singola unità può essere confermata.
- [ ] Solo una versione confermata e valida può essere pubblicata.
- [ ] Le versioni confermate o pubblicate non vengono sovrascritte.
- [ ] Generazione, conferma e pubblicazione sono visibili nello storico.

### Stati e resilienza

- [ ] Loading, empty, partial, dati da aggiornare, errore locale ed errore globale sono distinguibili.
- [ ] Gli skeleton non mostrano valori fittizi.
- [ ] Un errore locale non nasconde i blocchi ancora validi.
- [ ] Un dato obsoleto conserva timestamp e limitazione.
- [ ] Nessun errore previsto produce rumore in console.
- [ ] Nessun problema mostra dettagli tecnici all'utente.

### Operational Unit

- [ ] Il contesto selezionato è stabile tra Mission Control, Planning, Workforce e Fleet.
- [ ] `Tutte` è una vista aggregata di sola lettura.
- [ ] Ogni riga aggregata mantiene la propria Operational Unit.
- [ ] Metriche o piani incompatibili non vengono sommati.
- [ ] Conferma e pubblicazione non sono disponibili nella vista `Tutte`.

### Responsive e accessibilità

- [ ] Desktop assegna la maggior parte dello spazio al Planning.
- [ ] Tablet mantiene conflitti e azioni prima del piano quando bloccanti.
- [ ] Mobile usa schede Task senza scroll orizzontale.
- [ ] L'ordine dei blocchi resta stabile.
- [ ] Tutte le azioni sono disponibili da tastiera e touch.
- [ ] Colore, icona e testo comunicano insieme lo stato.
- [ ] Zoom 200% e `prefers-reduced-motion` sono supportati.
- [ ] Il linguaggio visibile rispetta i termini operativi definiti dal contratto.

## 21. Rischi progettuali

| Rischio | Effetto | Mitigazione contrattuale |
| --- | --- | --- |
| Planning diventa una copia di Workforce o Fleet | ownership confusa e dati divergenti | mostrare solo riferimenti e deep link |
| Readiness viene ricostruita nel browser | decisioni incoerenti | consumare esclusivamente lo stato Core |
| Vista `Tutte` abilita modifiche ambigue | azioni applicate al perimetro errato | sola lettura e selezione obbligatoria dell'unità |
| Proposta scambiata per decisione | automazione non controllata | motivo, impatto e conferma umana |
| Conferma e pubblicazione fuse | piano reso operativo accidentalmente | transizioni e comandi distinti |
| Input cambiano dopo la conferma | versione ufficiale non più coerente | immutabilità, nuova bozza e stato Da rivedere |
| Troppi indicatori riducono la leggibilità | decisione lenta | una Readiness e una sola azione primaria |
| Dati obsoleti sembrano correnti | falsa sicurezza | freshness e timestamp sempre dichiarati |
| Storico diventa log tecnico | rumore e scarsa comprensione | eventi operativi sintetici e Timeline separata |
| Decision Support anticipato | dipendenze premature dalla Fase 6 | blocco implementato solo dopo contratto dedicato |
| Linguaggio esterno entra nel Core | perdita di neutralità | traduzione a monte e nomenclature configurate |
| Piano mobile inutilizzabile | omissioni o errori operativi | schede Task e una sola colonna |

## 22. Micro-sprint consigliati

Ogni micro-sprint ha un solo obiettivo e deve iniziare soltanto quando la fase precedente della roadmap soddisfa i propri criteri di uscita.

1. **PW-0 - Inventario dei contratti disponibili**
   Verificare quali dati esistenti coprono Header, input, readiness, conflitti e versioni. Nessuna UX nuova e nessuna API introdotta implicitamente.

2. **PW-1 - Shell, contesto e stati di pagina**
   Costruire Header, Operational Unit, skeleton, empty, partial ed error usando esclusivamente contratti esistenti.

3. **PW-2 - Readiness e Input disponibili**
   Presentare la risposta Core e la freshness dei tre input senza ricalcolo frontend.

4. **PW-3 - Revisione dei conflitti**
   Introdurre gruppi, gerarchia, collegamento al Planning e deep link ai workspace proprietari.

5. **PW-4 - Proposta operativa responsive**
   Rendere il Planning contenuto principale su desktop, tablet e mobile, inizialmente in consultazione.

6. **PW-5 - Correzioni della bozza**
   Abilitare soltanto modifiche possedute dal Planning, con validazione Core, audit e conservazione delle modifiche manuali.

7. **PW-6 - Conferma**
   Implementare i prerequisiti, il riepilogo e la transizione idempotente verso una versione confermata.

8. **PW-7 - Pubblicazione e storico Planning**
   Separare pubblicazione, versione ufficiale e riepilogo cronologico senza anticipare la Timeline generale.

9. **PW-8 - QA operativo**
   Verificare percorso completo, concorrenza di versione, desktop, tablet, mobile, accessibilità, performance e console.

10. **DS-1 - Decisioni suggerite**
    Solo durante la Fase 6 e dopo un contratto Decision Support: motivo, impatto, alternative, applicazione alla bozza e conferma umana.

## 23. Non-obiettivi del primo ciclo implementativo

- gestione anagrafica di persone o Asset;
- modifica turni, assenze, documenti o manutenzione;
- nuove regole specifiche di un mercato;
- Timeline operativa completa;
- AI, chat o raccomandazioni opache;
- simulazione di scenari;
- modifiche massive multi-unità;
- pubblicazione automatica;
- notifiche;
- analytics o KPI economici;
- editor della configurazione;
- nuove API o tabelle senza uno sprint di contratto dedicato.

## 24. Decisione finale

Planning Workspace è il cuore operativo nel quale dati già posseduti da Core e Plugin diventano un piano verificabile. La schermata non assorbe Workforce, Fleet o Mission Control: li coordina attraverso confini pubblici.

Il modello finale è:

```text
Mission Control osserva.
Planning Workspace decide il piano.
Workforce gestisce persone.
Fleet gestisce Asset.
Decision Engine propone.
Il responsabile conferma.
La pubblicazione rende operativa una versione identificata.
La storia conserva ciò che è accaduto.
```

Ogni futura implementazione che riduca la visibilità di versione, provenienza, Operational Unit o conferma umana non è conforme a questo contratto.
