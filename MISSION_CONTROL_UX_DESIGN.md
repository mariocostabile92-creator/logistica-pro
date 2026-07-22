# Mission Control UX Design

**Stato:** contratto UX ufficiale per il prossimo sprint

**Ambito:** progettazione completa; nessuna implementazione

**Riferimenti canonici:** [Mission Control Product Contract](MISSION_CONTROL_PRODUCT_CONTRACT.md), [Product Screen Contracts](PRODUCT_SCREEN_CONTRACTS.md), [Operational Unit Model](OPERATIONAL_UNIT_MODEL.md), [Development Sprint Rules](DEVELOPMENT_SPRINT_RULES.md)

## 1. Missione

Mission Control deve rispondere a una sola domanda:

> È tutto pronto per iniziare la giornata operativa?

Alle 07:00 il responsabile operativo deve poter capire in meno di 30 secondi:

- cosa è pronto;
- cosa manca;
- quali elementi bloccano l'avvio;
- quale modulo richiede attenzione;
- dove intervenire.

Mission Control non è una dashboard piena di numeri. È la scrivania operativa dalla quale osservare la situazione, comprenderla e raggiungere il Workspace proprietario dell'azione.

Mission Control:

- **osserva** snapshot pubblici prodotti dal Core e dai Plugin;
- **riassume** solo ciò che conta per l'avvio della giornata;
- **spiega** stato, impatto, provenienza e aggiornamento dei dati;
- **collega** ogni intervento al Workspace corretto.

Mission Control non gestisce Workforce, Fleet o Planning. Non modifica turni, Asset, Assignment o configurazioni. Non sostituisce i Plugin e non ricalcola decisioni nel frontend.

## 2. Obiettivo di esperienza

L'esperienza deve rispettare quattro tempi:

1. **Entro 5 secondi:** riconoscere Operational Unit, data e stato generale.
2. **Entro 15 secondi:** individuare la prima azione bloccante.
3. **Entro 30 secondi:** capire il percorso da seguire tra Workforce, Fleet e Operations.
4. **Con un click:** aprire il Workspace proprietario nel contesto corretto.

La pagina non deve richiedere scorrimento per conoscere stato generale e prime azioni su un normale desktop. I dettagli secondari possono proseguire sotto il primo viewport.

## 3. Modello mentale

La pagina segue una sequenza stabile:

```text
CONTESTO
  -> RISPOSTA GENERALE
  -> AZIONI RICHIESTE
  -> FONTI DELLO STATO
  -> COSA È SUCCESSO
  -> SINTESI DELLA GIORNATA
```

La risposta generale dice se la giornata è pronta. Le azioni richieste dicono cosa fare. Gli snapshot spiegano quale modulo ha prodotto il dato. Timeline e Briefing forniscono contesto senza duplicare le azioni.

## 4. Architettura dell'informazione

L'ordine obbligatorio è:

1. Header contestuale.
2. Stato della giornata.
3. Azioni richieste.
4. Snapshot Workforce, Fleet e Planning.
5. Timeline operativa.
6. Briefing.

I KPI non costituiscono una sezione autonoma. I pochi indicatori indispensabili vivono nello stato generale o nello snapshot proprietario.

### Budget informativo

- una risposta generale;
- una spiegazione generale di massimo due righe;
- massimo cinque azioni visibili prima di un eventuale approfondimento;
- tre snapshot di modulo;
- massimo tre indicatori sintetici complessivi nel primo viewport;
- massimo sei eventi nella timeline;
- massimo cinque righe nel Briefing.

Questo budget impedisce alla Home di trasformarsi in una copia delle Workspace.

## 5. Wireframe desktop

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ MISSION CONTROL                                      Ultimo aggiornamento 2m │
│ Martedì 22 luglio  ·  07:03  ·  Europe/Rome   [Operational Unit: Tutte  v]  ↻ │
├──────────────────────────────────────────────────────────────────────────────┤
│ !  INTERVENTO RICHIESTO                                                     │
│    La giornata non è pronta: 2 blocchi devono essere risolti.               │
│    Copertura persone 24/25  ·  Mezzi operativi 26/27  ·  1 conflitto critico│
├───────────────────────────────────────────────────┬──────────────────────────┤
│ AZIONI RICHIESTE                                  │ STATO DEI MODULI         │
│                                                   │                          │
│ [Blocca avvio]  Risorsa assente                   │ Workforce      Attenzione│
│ Unità A · Copertura incompleta · aggiornato 06:58 │ 24 disponibili · 1 ass. │
│                                      Apri Workforce│          Apri Workforce →│
│ ───────────────────────────────────────────────── │                          │
│ [Blocca avvio]  Asset indisponibile               │ Fleet           Attenzione│
│ Unità A · Sostituzione necessaria · aggiornato 07:00│ 26 disponibili · 1 off. │
│                                          Apri Fleet│              Apri Fleet →│
│ ───────────────────────────────────────────────── │                          │
│ [Da completare]  Planning non confermato          │ Planning    Non confermato│
│ Ultima generazione 06:52                           │ Readiness 82% · 1 confl. │
│                                     Apri Operations│         Apri Operations →│
├───────────────────────────────────────────────────┴──────────────────────────┤
│ TIMELINE OPERATIVA                         │ BRIEFING                        │
│ 06:35  Import Workforce completato         │ 1. Copertura incompleta Unità A│
│ 06:42  Fleet sincronizzata                 │ 2. Un Asset richiede verifica │
│ 06:52  Planning generato                   │ 3. Planning da confermare      │
│ 07:00  Stato aggiornato                    │                                 │
└────────────────────────────────────────────┴─────────────────────────────────┘
```

Il wireframe rappresenta una situazione sintetica e non prescrive dati, soglie o testi restituiti dai servizi. Lo stato e le priorità arrivano dai contratti pubblici; il frontend ne cura soltanto la presentazione.

## 6. Layout desktop

### Griglia

- contenuto centrato con larghezza massima compresa tra 1180 e 1280 px;
- griglia a 12 colonne;
- gutter da 24 px;
- margine pagina minimo da 24 px;
- nessuna sezione flottante scollegata dal flusso verticale.

### Primo viewport

Il primo viewport contiene Header, Stato della giornata, intestazione delle Azioni richieste e almeno le prime due azioni. Su schermi con altezza sufficiente mostra anche l'inizio degli snapshot.

### Distribuzione principale

- Azioni richieste: 8 colonne;
- Stato dei moduli: 4 colonne;
- Timeline: 7 colonne;
- Briefing: 5 colonne.

Lo Stato della giornata è una banda a larghezza piena, non una card promozionale. Le Azioni sono una lista operativa. Gli snapshot sono pannelli compatti e non contengono altre card.

## 7. Blocco 1 - Header

### Contenuti

- titolo `Mission Control`;
- data operativa per esteso;
- ora locale nel formato `HH:mm`, senza secondi;
- fuso orario quando l'organizzazione opera su più zone;
- selettore Operational Unit;
- freshness generale: `Aggiornato adesso`, `2 min fa`, `Dati non aggiornati`;
- comando di aggiornamento con icona `RefreshCw` e tooltip `Aggiorna stato`.

### Gerarchia

La data e l'Operational Unit sono più importanti del titolo tecnico. L'ora è di supporto. La freshness è visibile ma non compete con lo stato generale.

### Comportamento

- il cambio Operational Unit aggiorna l'intero contesto, non un singolo pannello;
- la selezione resta stabile quando si apre un Workspace e quando si torna indietro;
- il refresh non azzera il contenuto già valido durante il caricamento;
- l'ora viene aggiornata una volta al minuto senza annunci accessibili invasivi;
- data, ora e freshness non vengono usate dal frontend per dedurre readiness.

## 8. Blocco 2 - Stato della giornata

Questo blocco contiene una sola risposta e una sola spiegazione. Non mostra una collezione di KPI.

### Stati canonici di presentazione

| Stato | Etichetta | Significato operativo | Colore | Icona |
|---|---|---|---|---|
| `ready` | Giornata pronta | Fonti richieste disponibili, nessun blocco attivo e Planning nello stato previsto dalla policy | Verde | `CircleCheck` |
| `attention` | Attenzione | Esistono avvisi o dati da verificare che non bloccano ancora l'avvio | Ambra | `TriangleAlert` |
| `action_required` | Intervento richiesto | Esiste almeno un blocco operativo o un passaggio obbligatorio non completato | Rosso | `OctagonAlert` |
| `unknown` | Stato non determinabile | Dati mancanti, obsoleti o non disponibili impediscono una risposta affidabile | Grigio con accento blu | `CircleHelp` |

Loading, Empty ed Error non devono apparire come `ready`, `attention` o `action_required` se il sistema non dispone di informazioni sufficienti.

### Criteri

I criteri vengono valutati dal contratto aggregato di Mission Control o dai moduli proprietari, mai dal JavaScript della pagina.

- `ready`: tutti gli snapshot obbligatori sono utilizzabili e il Core dichiara assenza di blocchi.
- `attention`: il contratto espone warning non bloccanti o una scadenza prossima.
- `action_required`: il contratto espone almeno un'azione bloccante, un conflitto critico o un passaggio richiesto dalla policy.
- `unknown`: non è possibile valutare la giornata con i dati disponibili.

Soglie temporali, freshness e requisiti obbligatori provengono dalla Configuration, non sono hardcoded nella UI.

### Comportamento

- lo stato resta nella stessa posizione durante gli aggiornamenti;
- il colore è sempre accompagnato da icona, etichetta e testo;
- il cambio di stato viene annunciato con una regione `aria-live` non invasiva;
- nessun suono, popup o animazione urgente;
- la spiegazione cita il numero di blocchi solo se il dato è disponibile;
- un click sullo stato porta alla prima azione richiesta, non apre un editor.

## 9. Blocco 3 - Workforce Snapshot

### Domanda

Le persone necessarie sono disponibili per l'Operational Unit selezionata?

### Contenuto ammesso

- persone disponibili rispetto al fabbisogno, quando entrambi i valori esistono;
- assenze rilevanti per la giornata;
- sostituzioni richieste;
- freshness dello snapshot;
- stato sintetico;
- link `Apri Workforce`.

### Contenuto vietato

- calendario;
- elenco completo delle persone;
- modifica turno;
- dettaglio contratti;
- ricostruzione della copertura;
- azioni di sostituzione dentro Mission Control.

### Forma

Pannello compatto con titolo, stato, massimo tre righe informative e un solo link. Se esiste una criticità, la riga descrive l'impatto e non il dettaglio personale.

Esempio:

```text
Workforce                         Attenzione
24 disponibili su 25 richieste
1 assenza · 1 sostituzione richiesta
Aggiornato 06:58          Apri Workforce →
```

## 10. Blocco 4 - Fleet Snapshot

### Domanda

Gli Asset necessari sono operativi e utilizzabili?

### Contenuto ammesso

- mezzi disponibili rispetto al fabbisogno, quando disponibile;
- Asset in officina;
- documenti in attenzione;
- criticità che incidono sulla giornata;
- freshness dello snapshot;
- link `Apri Fleet`.

### Contenuto vietato

- Asset Registry completo;
- targhe o note estese nel riepilogo;
- modifica stato Asset;
- sincronizzazione dettagliata;
- decisioni di assegnazione;
- workflow di manutenzione.

### Forma

```text
Fleet                             Attenzione
26 mezzi operativi su 27 richiesti
1 in officina · documenti regolari
Aggiornato 07:00              Apri Fleet →
```

I documenti vengono mostrati solo quando richiedono attenzione operativa. Il totale dei documenti regolari non è un KPI utile.

## 11. Blocco 5 - Planning Snapshot

### Domanda

Esiste un piano operativo verificabile e pronto per l'uso?

### Contenuto ammesso

- stato del Planning;
- conflitti bloccanti e warning;
- readiness prodotta dal Core;
- ora dell'ultima generazione;
- stato di conferma o pubblicazione, quando previsto dal contratto;
- link `Apri Operations`.

### Contenuto vietato

- tabella delle Assignment;
- modifica del Planning;
- ricalcolo nel frontend;
- risoluzione dei conflitti;
- pulsanti di conferma o pubblicazione;
- duplicazione della vista Operations.

### Forma

```text
Planning                    Non confermato
Readiness 82% · 1 conflitto bloccante
Ultima generazione 06:52
Aggiornato 06:53          Apri Operations →
```

Se la readiness non è disponibile, viene mostrato `Readiness non disponibile`, mai `0%`.

## 12. Blocco 6 - Azioni richieste

È il cuore della pagina e occupa lo spazio visivo principale.

### Differenza tra azione e notifica

Un'azione:

- descrive un risultato da ottenere;
- indica perché serve;
- dichiara impatto e Operational Unit;
- appartiene a un Workspace;
- offre un solo percorso principale.

Una notifica comunica soltanto che qualcosa è successo. Le notifiche non appartengono a questa lista.

### Anatomia di una riga

1. Priorità testuale.
2. Titolo orientato all'azione.
3. Motivo o impatto in una riga.
4. Operational Unit.
5. Fonte e freshness.
6. CTA verso il Workspace proprietario.

### Priorità

| Priorità | Etichetta utente | Uso | Ordinamento |
|---|---|---|---|
| P0 | Blocca avvio | Impedisce di dichiarare pronta la giornata | Sempre in cima |
| P1 | Da completare | Passaggio richiesto prima della soglia configurata | Dopo i blocchi |
| P2 | Da verificare | Warning non bloccante o dato vicino alla scadenza | Dopo le attività richieste |

La priorità viene fornita dal backend. Il frontend non la deduce dalla severità testuale, dal colore o dall'orario locale.

A parità di priorità, l'ordine segue scadenza operativa, impatto dichiarato e orario di rilevazione. Se il contratto non fornisce un ordinamento, viene mantenuto quello ricevuto.

### Esempi

```text
[Blocca avvio] Risolvi la copertura mancante
Unità A · Una risorsa richiesta non è coperta
Workforce · aggiornato 06:58                 Apri Workforce →

[Blocca avvio] Sostituisci l'Asset indisponibile
Unità A · Un Task non dispone di Asset operativo
Fleet · aggiornato 07:00                         Apri Fleet →

[Da completare] Conferma il Planning
Unità A · Planning generato alle 06:52
Operations · aggiornato 06:53              Apri Operations →
```

### Comportamento

- nessuna azione può essere completata o ignorata dalla Home;
- il CTA apre il Workspace con data, Operational Unit e riferimento dell'entità quando disponibili;
- tornando a Mission Control, contesto e posizione vengono preservati;
- lo snapshot viene aggiornato al ritorno senza polling aggressivo;
- le azioni risolte scompaiono solo dopo conferma della fonte;
- massimo cinque azioni sono mostrate nel riepilogo iniziale;
- eventuali azioni ulteriori usano `Mostra tutte le azioni`, senza scroll interno.

### Stato senza azioni

Con giornata pronta:

```text
Nessuna azione richiesta
I moduli non segnalano blocchi per l'Operational Unit selezionata.
```

Non viene mostrata una lista vuota né una celebrazione invasiva.

## 13. Blocco 7 - Timeline operativa

### Scopo

Rispondere a: che cosa è già successo oggi?

### Eventi ammessi

- import completato o fallito;
- sincronizzazione completata;
- Planning generato;
- Planning confermato;
- Planning pubblicato;
- cambi di stato operativi esposti dai contratti pubblici.

### Regole

- mostra massimo sei eventi rilevanti della giornata;
- ordina dal più recente al meno recente su mobile e in ordine cronologico su desktop, con indicazione chiara;
- evidenzia l'ultimo evento senza animazioni;
- mostra ora, evento, fonte e Operational Unit quando necessaria;
- non mostra log tecnici, actor sensibili o payload;
- non diventa uno storico infinito;
- non inventa milestone future.

Quando non esistono eventi:

```text
Nessuna attività registrata oggi.
Le operazioni compariranno qui dopo il primo aggiornamento dei moduli.
```

## 14. Blocco 8 - Briefing

### Scopo

Fornire una sintesi leggibile della situazione senza ripetere l'elenco delle azioni.

### Regole editoriali

- massimo cinque righe;
- una informazione per riga;
- ordine per impatto operativo;
- frasi dichiarative e verificabili;
- nessun linguaggio da chat;
- nessun testo generico motivazionale;
- nessuna previsione non supportata;
- nessun dettaglio tecnico;
- fonte e freshness disponibili su richiesta, non dentro ogni frase.

Esempio:

```text
1. La copertura Workforce è incompleta nell'Unità A.
2. Un Asset operativo richiede sostituzione.
3. Il Planning è stato generato ma non è confermato.
```

Il Briefing spiega il quadro; la lista Azioni indica dove intervenire.

## 15. Blocco 9 - KPI essenziali

Mission Control non possiede una griglia di KPI. Sono ammessi al massimo tre indicatori contestuali:

1. **Copertura persone:** disponibili rispetto al fabbisogno.
2. **Copertura Asset:** Asset operativi rispetto al fabbisogno.
3. **Conflitti bloccanti:** numero prodotto dal Planning/Core.

### Regole

- compaiono soltanto quando numeratore, denominatore, ambito e freshness sono affidabili;
- non vengono sommati tra Operational Unit incompatibili;
- `0` significa zero reale, non dato assente;
- dato assente viene mostrato come `Non disponibile`;
- nessun confronto percentuale decorativo;
- nessuna freccia di trend senza serie temporale valida;
- nessun KPI su totale persone, totale Asset, import eseguiti o attività storiche se non risponde alla domanda della giornata.

Gli indicatori vivono nella banda Stato o negli snapshot. Non usano card autonome.

## 16. Gerarchia visiva

### Livello 1 - Decisione

Stato della giornata e prima azione bloccante. Testo grande ma operativo, non hero marketing.

### Livello 2 - Intervento

Lista Azioni richieste, con priorità, motivo e CTA.

### Livello 3 - Evidenze

Snapshot Workforce, Fleet e Planning.

### Livello 4 - Contesto

Timeline e Briefing.

### Tipografia

- titolo pagina: 24-28 px;
- stato generale: 24 px desktop, 20 px mobile;
- titoli sezione: 16-18 px;
- corpo: 14-16 px;
- metadati: almeno 12 px;
- font size fissa per breakpoint, mai scalata con la larghezza del viewport;
- letter spacing `0`;
- peso semibold riservato a stato, azioni e titoli.

### Spaziatura

- sistema base da 4 px;
- distanza tra sezioni: 24-32 px;
- padding pannelli: 16-20 px;
- righe azione: minimo 64 px, espandibili senza tagliare il testo;
- radius massimo: 6 px;
- nessuna card dentro un'altra card.

## 17. Colori semantici

| Ruolo | Testo/bordo | Fondo tenue | Uso |
|---|---|---|---|
| Pronto | `#176B45` | `#E8F5EE` | Stato ready e conferme |
| Attenzione | `#8A5700` | `#FFF3D6` | Warning non bloccanti |
| Critico | `#A62A21` | `#FDECEA` | Blocchi e interventi richiesti |
| Informazione | `#245B85` | `#EAF2F8` | Dati parziali, aggiornamenti, link |
| Neutro | `#4F5B56` | `#F1F3F2` | Unknown, metadati e stato non disponibile |
| Testo principale | `#17211D` | `#FFFFFF` | Contenuto operativo |
| Bordo | `#C9D1CD` | - | Separazione delle aree |

### Regole di accessibilità

- il colore non è mai l'unico segnale;
- ogni stato usa icona, etichetta e testo;
- contrasto minimo WCAG AA;
- focus visibile con contorno da almeno 2 px;
- i fondi semantici sono usati in bande o indicatori, non su intere pagine;
- niente palette dominata da un unico colore;
- niente gradienti, bokeh o decorazioni prive di significato.

## 18. Operational Unit

### Selettore

Il selettore è sempre visibile nell'Header e mostra:

- una Operational Unit;
- più unità autorizzate;
- vista aggregata `Tutte`.

La label è configurata dall'organizzazione. Il contratto Core continua a usare Operational Unit.

### Vista singola

Tutti gli stati, snapshot, eventi e link sono filtrati sull'unità selezionata. Il Workspace di destinazione riceve lo stesso contesto.

### Vista multipla o `Tutte`

- ogni azione dichiara l'unità di provenienza;
- i blocchi sono ordinati senza perdere il contesto;
- metriche non aggregabili non vengono sommate;
- freshness differenti restano visibili;
- lo stato generale riflette il peggior blocco dichiarato dal contratto, non una media calcolata dal frontend;
- le modifiche non avvengono in Mission Control, quindi non esiste ambiguità di destinazione.

### Dati organizzativi

I dati validi per tutta l'organizzazione sono etichettati `Organizzazione`. L'assenza di Operational Unit non viene interpretata come `Tutte`.

### Persistenza del contesto

La selezione deve sopravvivere a:

- navigazione verso un Workspace e ritorno;
- refresh della pagina;
- aggiornamento degli snapshot;
- passaggio tra desktop e viewport responsive.

## 19. Stati della pagina

### Loading iniziale

- Header e selettore mantengono dimensioni stabili;
- banda Stato, lista Azioni e snapshot mostrano skeleton coerenti con il layout finale;
- nessun valore `0`, percentuale o stato positivo viene simulato;
- animazione leggera e disattivata con `prefers-reduced-motion`;
- dopo la soglia prevista compare un messaggio testuale senza rimuovere lo skeleton all'improvviso.

### Aggiornamento parziale

Il contenuto valido resta visibile. Il modulo in aggiornamento mostra un indicatore locale e la freshness precedente. Non si blocca l'intera pagina.

### Empty state globale

```text
Preparazione della giornata non iniziata
Non sono ancora disponibili dati operativi per oggi.

1. Prepara Workforce                 Apri Workforce →
2. Aggiorna Fleet                        Apri Fleet →
3. Genera il Planning               Apri Operations →
```

Lo stato generale è `Stato non determinabile`, non `Intervento richiesto`, salvo diversa dichiarazione del contratto in base alla policy e all'orario operativo.

### Empty state di un modulo

Lo snapshot resta nella sua posizione e indica:

- quale dato manca;
- perché impedisce o limita la valutazione;
- quale Workspace aprire.

L'assenza prevista di dati non produce un errore in console.

### Partial state

Mission Control mostra i dati disponibili, identifica la fonte mancante e usa `Stato parziale`. Non formula conclusioni che richiedono lo snapshot assente.

### Dati obsoleti

- mostra `Aggiornato 28 min fa` e `Dati da aggiornare`;
- usa la soglia ricevuta dalla Configuration;
- mantiene visibile l'ultimo snapshot valido;
- non trasforma automaticamente dati obsoleti in dati correnti;
- offre refresh o deep link alla fonte.

### Errore di un modulo

Il problema resta confinato allo snapshot interessato. Gli altri moduli continuano a essere leggibili. Se esiste un ultimo snapshot valido, viene mostrato con timestamp e avviso.

### Errore globale

```text
Stato della giornata non disponibile
Non è stato possibile aggiornare Mission Control.

[Riprova]   Workforce →   Fleet →   Operations →
```

Non vengono mostrati stack trace, codici interni o dettagli infrastrutturali. L'errore imprevisto può includere un riferimento di supporto non sensibile.

## 20. Workflow delle 07:00

### Scenario A - Giornata pronta

1. Alle 07:00 il responsabile apre Mission Control.
2. Vede Operational Unit, freshness e `Giornata pronta`.
3. Verifica che non esistano azioni richieste.
4. Legge l'ultima generazione del Planning e i principali eventi.
5. Entra in Operations solo se deve consultare o proseguire il ciclo previsto.

Tempo obiettivo: meno di 15 secondi per confermare il quadro.

### Scenario B - Assenza Workforce

1. Lo stato mostra `Intervento richiesto`.
2. La prima azione è `Risolvi la copertura mancante`.
3. Il responsabile apre Workforce con data e Operational Unit già selezionate.
4. Esegue la modifica nel Workspace Workforce.
5. Tornando a Mission Control, la pagina aggiorna lo snapshot e rimuove l'azione solo dopo conferma della fonte.

### Scenario C - Asset indisponibile

1. Fleet segnala un Asset non operativo che incide sulla giornata.
2. L'azione indica impatto e unità, senza esporre il Registry completo.
3. Il responsabile apre Fleet sul contesto interessato.
4. La gestione avviene in Fleet.
5. Mission Control osserva il nuovo snapshot e aggiorna stato e azioni.

### Scenario D - Planning non confermato

1. Workforce e Fleet risultano utilizzabili.
2. Lo Stato resta `Intervento richiesto` o `Attenzione` secondo la policy ricevuta.
3. L'azione `Conferma il Planning` apre Operations.
4. Conferma, ricalcolo o pubblicazione avvengono esclusivamente in Operations.
5. Al ritorno, Mission Control mostra il nuovo stato e registra l'evento nella Timeline quando disponibile.

### Percorso raccomandato in presenza di più blocchi

L'ordine non è deciso dalla posizione fissa dei moduli. Segue le priorità ricevute:

```text
Mission Control
  -> prima azione P0
  -> Workspace proprietario
  -> ritorno con contesto preservato
  -> aggiornamento snapshot
  -> successiva azione P0/P1
  -> Operations quando input e risorse sono pronti
```

## 21. Responsive

### Desktop - da 1200 px

- griglia 12 colonne;
- Azioni 8 colonne, snapshot 4;
- Timeline e Briefing affiancati;
- stato e prime azioni nel primo viewport;
- nessuno scroll interno ai pannelli.

### Tablet - da 768 a 1199 px

- Header su due righe: contesto sopra, Operational Unit e refresh sotto;
- Stato a larghezza piena;
- Azioni a larghezza piena prima degli snapshot;
- snapshot in griglia a due colonne, con Planning a larghezza piena se necessario;
- Timeline e Briefing in sequenza verticale;
- target interattivi di almeno 44 px.

Wireframe tablet:

```text
┌──────────────────────────────────────────────┐
│ Martedì 22 luglio · 07:03                    │
│ [Operational Unit: Tutte v]  Aggiornato 2m ↻│
├──────────────────────────────────────────────┤
│ INTERVENTO RICHIESTO                         │
│ 2 blocchi impediscono l'avvio                │
├──────────────────────────────────────────────┤
│ AZIONI RICHIESTE                             │
│ [P0] Copertura mancante     Apri Workforce → │
│ [P0] Asset indisponibile        Apri Fleet → │
├──────────────────────┬───────────────────────┤
│ Workforce            │ Fleet                 │
├──────────────────────┴───────────────────────┤
│ Planning                                     │
├──────────────────────────────────────────────┤
│ Timeline                                     │
├──────────────────────────────────────────────┤
│ Briefing                                     │
└──────────────────────────────────────────────┘
```

### Mobile - fino a 767 px

- una sola colonna;
- Header compatto con data e ora sulla prima riga;
- selettore Operational Unit a larghezza piena;
- Stato immediatamente sotto;
- Azioni prima di ogni snapshot;
- snapshot in ordine stabile Workforce, Fleet, Planning;
- Timeline compatta con massimo quattro eventi iniziali;
- Briefing per ultimo;
- nessuna tabella e nessuno scroll orizzontale;
- CTA testuali a larghezza sufficiente, senza abbreviazioni ambigue;
- barra di navigazione esistente preservata senza sovrapposizioni.

Wireframe mobile:

```text
┌──────────────────────────────┐
│ Mar 22 luglio        07:03   │
│ [Operational Unit: Tutte  v]│
│ Aggiornato 2 min fa        ↻ │
├──────────────────────────────┤
│ INTERVENTO RICHIESTO         │
│ 2 blocchi da risolvere       │
├──────────────────────────────┤
│ AZIONI RICHIESTE             │
│ Blocca avvio                 │
│ Risolvi copertura mancante   │
│ Unità A                      │
│ Apri Workforce →             │
│ ──────────────────────────── │
│ Blocca avvio                 │
│ Sostituisci Asset            │
│ Apri Fleet →                 │
├──────────────────────────────┤
│ Workforce          Attenzione│
│ 24 su 25 disponibili         │
│ Apri Workforce →             │
├──────────────────────────────┤
│ Fleet              Attenzione│
├──────────────────────────────┤
│ Planning       Non confermato│
├──────────────────────────────┤
│ Timeline                     │
├──────────────────────────────┤
│ Briefing                     │
└──────────────────────────────┘
```

L'ordine non cambia dinamicamente in base alla severità: la stabilità spaziale facilita l'uso ripetuto. La priorità resta evidente dentro le Azioni.

## 22. Navigazione e interazioni

- il logo o la voce Home apre Mission Control;
- i link di modulo usano icona `ArrowRight` e label esplicita;
- il click sulla riga azione può aprire la stessa destinazione del CTA, ma il focus tastiera resta sul link dichiarato;
- `Tab` segue Header, Stato, Azioni, snapshot, Timeline e Briefing;
- `Enter` attiva selettore, refresh e link;
- `Esc` chiude il selettore Operational Unit;
- il browser Back ripristina Operational Unit, scroll e focus quando possibile;
- nessun comando distruttivo è presente;
- nessun popup automatico;
- nessun pannello laterale per modificare dati.

## 23. Freshness e aggiornamento

Ogni informazione deve rendere comprensibile quanto è recente senza riempire la pagina di timestamp.

- freshness generale nell'Header;
- freshness specifica nel footer di ogni snapshot;
- timestamp preciso disponibile tramite tooltip o dettaglio accessibile;
- differenze importanti tra moduli evidenziate nello stato `partial`;
- aggiornamento all'ingresso, al ritorno da un Workspace e su comando manuale;
- nessun polling aggressivo imposto dal contratto UX;
- nessun reset visivo dell'intera pagina durante un refresh locale;
- eventuali dati nuovi non spostano il focus dell'utente.

## 24. Linguaggio e microcopy

### Principi

- usare verbi operativi: `Risolvi`, `Verifica`, `Conferma`, `Apri`;
- descrivere l'effetto, non il codice tecnico;
- evitare `Errore 404`, `snapshot missing`, `status critical`;
- non usare Amazon, Station, route o wave salvo label prodotte dall'Adapter per il contesto utente;
- preferire Asset, risorsa, Planning e Operational Unit nel contratto neutrale;
- non usare punti esclamativi o toni allarmistici;
- non promettere certezza oltre i dati disponibili.

### Esempi

| Evitare | Usare |
|---|---|
| `Fleet error` | `Stato Fleet non disponibile` |
| `0 driver` | `Disponibilità persone non disponibile` |
| `Conflict code VU-01` | `Un Asset assegnato non è operativo` |
| `Fix now` | `Apri Fleet` |
| `All good` | `Giornata pronta` |

## 25. Accessibilità

- struttura con un solo `h1` e sezioni ordinate;
- landmark per Header, contenuto principale e navigazione;
- stato generale esposto come testo completo;
- icone decorative nascoste agli screen reader;
- icone informative con label accessibile;
- contrasto WCAG AA;
- focus visibile e ordine coerente;
- target da almeno 44 x 44 px su touch;
- aggiornamenti non critici annunciati con modalità `polite`;
- errori e stato generale non affidati al colore;
- skeleton non annunciati ripetutamente;
- supporto a zoom 200% senza sovrapposizioni o perdita di azioni;
- `prefers-reduced-motion` rispettato.

## 26. Motivazioni progettuali

### Perché una sola risposta generale

Il responsabile non deve interpretare sei KPI per decidere se iniziare. Lo stato generale riduce il carico cognitivo e rimanda alle evidenze.

### Perché le Azioni vengono prima degli snapshot

Gli snapshot spiegano. Le Azioni permettono di proseguire. Quando esiste un blocco, il percorso utile è più importante del riepilogo numerico.

### Perché nessun editing

Ogni modifica appartiene al Workspace proprietario, che possiede regole, validazione, audit e contesto. Replicare i form in Home creerebbe due comportamenti per la stessa operazione.

### Perché pochi KPI

Totali e trend non collegati all'avvio della giornata aumentano il rumore. Copertura persone, copertura Asset e conflitti bloccanti sono ammessi perché spiegano direttamente la readiness.

### Perché Timeline e Briefing sono distinti

La Timeline descrive fatti ordinati nel tempo. Il Briefing interpreta sinteticamente il quadro già prodotto. Nessuno dei due sostituisce le Azioni.

### Perché l'Operational Unit è sempre visibile

Uno stato senza perimetro è ambiguo. Il responsabile deve sapere immediatamente se sta osservando una singola unità o l'organizzazione aggregata.

## 27. Contenuti vietati

Mission Control non deve contenere:

- calendari Workforce;
- Asset Registry;
- tabella completa del Planning;
- editor o form di dominio;
- import come esperienza principale;
- grafici decorativi;
- classifiche;
- storico infinito;
- log tecnici;
- notifiche generiche;
- chat o chatbot;
- automazioni decisionali;
- duplicazione di readiness o priority nel frontend;
- dati personali non necessari;
- codici o termini specifici di un cliente nei default;
- pulsanti di conferma, pubblicazione o modifica appartenenti ad altri Workspace.

## 28. Criteri UX per il prossimo sprint

Il futuro sprint di implementazione potrà considerare il contratto UX soddisfatto soltanto quando:

1. la domanda `È tutto pronto?` riceve una risposta nel primo viewport;
2. lo stato generale proviene dal contratto backend e non da calcoli frontend;
3. le Azioni richieste precedono i dettagli dei moduli;
4. ogni azione apre il Workspace proprietario con il contesto disponibile;
5. Workforce, Fleet e Planning restano snapshot sintetici;
6. la selezione Operational Unit governa tutta la pagina;
7. `Tutte` conserva provenienza e freshness delle singole unità;
8. loading, empty, partial, stale ed error non mostrano falsi zeri;
9. il Briefing non supera cinque righe;
10. la Timeline non supera sei eventi iniziali;
11. non esiste una griglia di KPI;
12. desktop, tablet, mobile, tastiera e zoom 200% sono verificati;
13. nessun errore previsto genera rumore in console;
14. nessuna funzionalità di modifica viene aggiunta alla Home;
15. nessuna logica dei Plugin viene duplicata.

## 29. Decisione finale

Mission Control sarà una scrivania operativa, non una dashboard analitica.

La struttura definitiva è:

```text
Header contestuale
  -> Stato della giornata
  -> Azioni richieste
  -> Workforce / Fleet / Planning snapshot
  -> Timeline operativa
  -> Briefing
```

Il valore della schermata non dipende dalla quantità di informazioni mostrate, ma dalla capacità di dare una risposta affidabile e guidare l'utente verso il punto corretto senza sostituirsi ai moduli proprietari.

Questo documento progetta il comportamento e la gerarchia della futura schermata. Non introduce componenti, endpoint, modelli, query o modifiche applicative.
