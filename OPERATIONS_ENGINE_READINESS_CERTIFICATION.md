# Operations Engine Readiness Certification

**Stato:** vincolante  
**Ambito:** certificazione di Architecture, Runtime, Migration, Production e
Legacy Retirement  
**Owner del processo:** Certification Authority di Operations Engine  
**Riferimenti normativi:** `OPERATIONS_ENGINE_PHILOSOPHY.md`,
`OPERATIONS_ENGINE_VISION.md`, `OPERATIONS_ENGINE_ROADMAP.md`,
`PLANNING_RUNTIME_MIGRATION_STRATEGY.md`,
`DEVELOPMENT_SPRINT_RULES.md`

Questo documento definisce quando Operations Engine puo essere considerato
pronto. Non certifica una funzionalita perche esiste, ne una release perche i
test passano. Certifica che un insieme dichiarato di invarianti, evidenze,
controlli operativi e responsabilita e stato verificato nel contesto in cui
verra utilizzato.

Nel documento:

- **DEVE** indica un requisito obbligatorio;
- **NON DEVE** indica un divieto;
- **DOVREBBE** indica il comportamento predefinito;
- **PUO** indica una scelta ammessa;
- **evidenza** indica un artefatto verificabile, riproducibile e attribuito;
- **promozione** indica il passaggio a un livello di autorita o rischio
  superiore;
- **scope** indica almeno Organization, Operational Unit, planning date e
  timezone IANA.

---

## 1. Executive Summary

Operations Engine adotta una certificazione progressiva. Nessuna componente
diventa autorevole per effetto della sola implementazione, del deploy o di una
decisione informale.

Il percorso ufficiale e:

```text
Architecture Ready
        |
        v
Runtime Ready
        |
        v
Migration Ready
        |
        v
Production Ready
        |
        v
Enterprise Certified
```

La promozione operativa segue invece:

```text
Legacy writer
    -> Runtime osserva
    -> Runtime verifica
    -> Canary controllato
    -> Runtime production writer
    -> Legacy disabilitato
    -> Legacy rimosso
```

I due percorsi sono collegati ma non equivalenti. Il livello di certificazione
stabilisce che cosa la piattaforma e autorizzata a tentare. La fase di
migrazione stabilisce chi e il writer effettivo per ogni scope.

Una promozione e consentita solo quando:

1. ogni gate applicabile ha un esito;
2. non esiste alcun `FAIL`;
3. tutti i `PASS` obbligatori del livello target sono presenti;
4. le evidenze sono valide, firmate e non scadute;
5. scope, release e configurazione certificati coincidono con quelli da
   promuovere;
6. rollback, owner e finestra di osservazione sono dichiarati;
7. la Certification Authority emette un record `GO`.

Un punteggio elevato non compensa un gate fallito. L'Operations Engine Maturity
Index misura maturita; non concede autorita.

---

## 2. Scopo Della Certificazione

### 2.1 Obiettivi

La certificazione deve:

- impedire promozioni basate su percezioni o demo;
- mantenere un solo writer per scope;
- dimostrare comportamento fail-closed;
- rendere misurabili integrita, sicurezza e recovery;
- collegare ogni decisione a evidenze e owner;
- distinguere readiness tecnica da readiness operativa;
- rendere reversibili le fasi ancora reversibili;
- impedire il retirement prematuro del legacy;
- fornire una lingua comune per Architecture, Engineering, Operations,
  Security e Release Management.

### 2.2 Oggetti Certificabili

Una certificazione si applica a un oggetto identificato da:

- release o commit;
- versione dei contratti;
- versione della configurazione;
- Organization;
- una o piu Operational Unit dichiarate;
- planning date o intervallo di date;
- timezone;
- ambiente;
- modalita operativa;
- writer autorizzato;
- dataset e fingerprint delle evidenze;
- periodo di validita.

Una certificazione non e trasferibile automaticamente a un'altra release,
configurazione, Organization, Operational Unit o modalita.

### 2.3 Promozioni Governate

Il processo governa:

- introduzione di nuovi contratti Runtime;
- abilitazione della modalita Shadow o Verify;
- inizio del Canary con Runtime writer;
- espansione della coorte Canary;
- abilitazione del Runtime come writer primario;
- passaggio del legacy a fallback;
- disabilitazione del legacy;
- rimozione del legacy;
- estensione enterprise, multi-tenant o multi-unit.

### 2.4 Esclusioni

La certificazione:

- non sostituisce la Definition of Done dello sprint;
- non sostituisce test, security review o incident management;
- non autorizza nuove funzionalita;
- non modifica automaticamente Authority;
- non modifica configurazioni o dati;
- non consente eccezioni silenziose;
- non certifica ambienti o scope non inclusi nel record.

---

## 3. Principi Fondamentali

### 3.1 Un Solo Writer

Per ogni scope deve esistere un solo writer operativo effettivo. Shadow,
Comparator, Canary osservativo e strumenti di certificazione non scrivono lo
stato operativo.

La presenza di due writer possibili, anche per una finestra breve o in caso di
retry, e un `FAIL` non derogabile.

### 3.2 Fail-Closed

Autorita assente, scope ambiguo, versione incoerente, fingerprint non valido,
lock non disponibile, audit non garantito o outcome indeterminato devono
bloccare l'azione.

Il fallback non puo essere implicito. Richiede una transizione autorizzata,
scoped e auditata.

### 3.3 Evidenza Prima Dell'Autorita

Una funzionalita implementata ma non verificata e `UNASSESSED`, non `PASS`.
Una verifica senza artefatto riproducibile non e evidenza.

### 3.4 Immutabilita E Storia

Draft, Confirmation, Publication, Intent, Attempt, Execution outcome,
Authority decision e Rollback record conservano identita e storia. Una
correzione produce una nuova versione o un nuovo evento; non riscrive il
passato.

### 3.5 Scope Esplicito

Ogni decisione deve essere scoped. `Tutte` e un aggregato di consultazione e
non puo essere usato come scope mutante.

### 3.6 Separazione Dei Ruoli

Chi implementa un controllo non deve essere l'unico soggetto che lo certifica.
Le promozioni che cambiano writer richiedono almeno Engineering, Operations e
Release Authority. Security firma i gate di propria competenza.

### 3.7 Nessuna Compensazione A Punteggio

Un `PASS` in performance non compensa un `FAIL` in sicurezza. Un indice di
maturita alto non compensa duplicate execution, perdita di audit, writer
ambiguo o rollback non dimostrato.

### 3.8 Promozione Per Coorte

Ogni abilitazione avviene per coorte minima, scope esplicito e finestra
osservabile. L'espansione automatica e vietata.

### 3.9 Recovery Prima Del Retirement

Il legacy non viene disabilitato o rimosso finche recovery, rollback,
reconciliation e disaster recovery del Runtime non sono dimostrati.

### 3.10 Certificazione A Scadenza

Le evidenze scadono quando cambia un presupposto materiale o termina la loro
finestra di validita. Una certificazione scaduta equivale a `UNASSESSED` per
una nuova promozione.

### 3.11 Esiti Dei Gate

Ogni gate produce uno dei seguenti esiti:

| Esito | Significato | Effetto |
| --- | --- | --- |
| `PASS` | Tutti i controlli obbligatori applicabili sono soddisfatti da evidenze valide | Il gate non blocca la promozione |
| `WARNING` | Nessuna invariante critica e violata, ma esiste un limite non bloccante, circoscritto e con scadenza | Ammesso solo se il livello target non richiede `PASS` per quel controllo |
| `FAIL` | Un controllo obbligatorio manca, fallisce o non e verificabile | Promozione vietata |
| `UNASSESSED` | Il gate non e stato valutato | Equivale a `FAIL` per un gate obbligatorio |
| `NOT_APPLICABLE` | Il controllo non si applica allo scope, con motivazione firmata | Non altera il risultato |

Ogni `WARNING` deve indicare owner, rischio, compensazione, scadenza e criterio
di chiusura. Un `WARNING` non puo riguardare single writer, duplicate
execution, critical mismatch, tenant isolation, audit atomico o rollback
indeterminato.

---

## 4. Livelli Di Certificazione

### 4.1 Matrice Dei Livelli

| Livello | Nome | Autorita massima consentita | Gate minimi |
| --- | --- | --- | --- |
| 0 | Architecture Ready | Design, contratti e sviluppo controllato | Gate 1 e 2 |
| 1 | Runtime Ready | Runtime deterministico in sola osservazione | Gate 1, 2, 3, 6 e 7 |
| 2 | Migration Ready | Canary eleggibile dopo approvazione | Gate 1-10 in staging |
| 3 | Production Ready | Runtime writer per coorti approvate | Gate 1-10 con evidenze production |
| 4 | Enterprise Certified | Uso esteso, multi-unit e multi-tenant certificato | Gate 1-10 con prove sostenute e audit indipendente |

Il superamento di un livello non attiva automaticamente la relativa autorita.
Authority e deployment restano decisioni separate.

### 4.2 Level 0 - Architecture Ready

**Obiettivo**

Dimostrare che la piattaforma possiede confini, contratti e invarianti
coerenti prima di introdurre autorita operativa.

**Prerequisiti**

- Costituzione e ownership approvate;
- writer map dichiarata;
- state machine e transizioni vietate documentate;
- scope canonico definito;
- contratti pubblici versionati;
- dipendenze Core, Plugin e Adapter dichiarate.

**Evidenze richieste**

- architecture review firmata;
- dependency map;
- catalogo dei contratti;
- contract compatibility report;
- verifica immutabilita e fail-closed;
- decision log per assunzioni ancora aperte.

**Criteri di superamento**

- Gate 1 `PASS`;
- Gate 2 `PASS` sul piano dei contratti e dell'integrita strutturale;
- nessuna dipendenza vietata;
- nessuna transizione ambigua capace di produrre due writer.

**Motivi di fallimento**

- writer non identificabile;
- stato mutabile senza versione;
- contratti privi di scope;
- Core dipendente da Adapter, Plugin, UI o storage concreto;
- regole critiche affidate a convenzioni non verificabili.

### 4.3 Level 1 - Runtime Ready

**Obiettivo**

Dimostrare che il Runtime puo produrre e confrontare risultati deterministici
in memoria o in ambiente isolato, senza effetti operativi.

**Prerequisiti**

- Level 0 valido;
- input, output, Authority, Intent, Attempt e Publication identificabili;
- Producer e Comparator disponibili;
- write-set operativo atteso pari a zero.

**Evidenze richieste**

- determinism report;
- fingerprint verification;
- report differenziale su dataset rappresentativo;
- write-set assertion;
- diagnostica fail-closed;
- misure di latenza, payload e risorse;
- correlazione minima tra Publication, Authority, Intent e Attempt.

**Criteri di superamento**

- Gate 1, 2, 3, 6 e 7 `PASS` per modalita osservativa;
- parity almeno 99,5% sul campione approvato;
- critical mismatch pari a zero;
- duplicate execution pari a zero;
- nessun side effect operativo;
- stesso input e stessa configurazione producono stesso output e fingerprint.

**Motivi di fallimento**

- output parziale;
- risultato non deterministico;
- Comparator non usa gli stessi input del Producer;
- side effect osservato;
- diagnostica insufficiente;
- metriche non attribuibili allo scope.

### 4.4 Level 2 - Migration Ready

**Obiettivo**

Dimostrare che la piattaforma e pronta a iniziare un Canary controllato, senza
abilitarlo automaticamente.

**Prerequisiti**

- Level 1 valido;
- Execution e Rollback lifecycle definiti;
- idempotenza e fencing verificati;
- failure injection completata in staging;
- runbook, monitoring e owner disponibili.

**Evidenze richieste**

- concurrency e race report;
- crash-boundary report;
- rollback drill con successo 100%;
- security assessment;
- tenant isolation report;
- mixed-version deployment report;
- load e soak report;
- audit reconciliation;
- checklist operativa del Canary.

**Criteri di superamento**

- tutti i Gate 1-10 `PASS` in staging per lo scope target;
- nessun writer concorrente in alcuno scenario;
- recovery deterministico;
- rollback scoped e idempotente;
- audit atomico o azione bloccata;
- coorte e stop conditions approvate.

**Motivi di fallimento**

- failure injection incompleta;
- outcome indeterminato non riconciliabile;
- autenticazione o autorizzazione non dimostrate;
- rollback non provato;
- deploy misto non sicuro;
- runbook non eseguibile da Operations.

### 4.5 Level 3 - Production Ready

**Obiettivo**

Autorizzare il Runtime come writer per coorti e scope approvati, mantenendo
rollback e legacy fallback secondo la strategia di migrazione.

**Prerequisiti**

- Level 2 valido;
- Canary autorizzato e completato;
- SLO, alert ed error budget attivi;
- supporto operativo disponibile;
- rollback production-like dimostrato.

**Evidenze richieste**

- almeno 14 giorni di Canary;
- almeno 500 execution eleggibili;
- execution success almeno 99,9%;
- zero Sev-1 e Sev-2 attribuibili al Runtime;
- duplicate execution pari a zero;
- critical mismatch pari a zero;
- report di espansione 5/25/50/100%;
- almeno 30 giorni stabili prima della disabilitazione del legacy;
- incident, rollback e audit report.

**Criteri di superamento**

- tutti i Gate 1-10 `PASS` con evidenze production;
- error budget rispettato;
- nessun `WARNING` su controlli obbligatori;
- approvazione congiunta Engineering, Operations, Security e Release;
- rollback window ancora valida.

**Motivi di fallimento**

- soglie Canary non raggiunte;
- incidenti critici aperti;
- metriche mancanti;
- espansione non reversibile;
- dipendenze operative dal legacy non inventariate;
- on-call o runbook insufficienti.

### 4.6 Level 4 - Enterprise Certified

**Obiettivo**

Dimostrare affidabilita sostenuta, isolamento, governance e disaster recovery
per uso enterprise, multi-unit e multi-tenant.

**Prerequisiti**

- Level 3 valido;
- almeno 90 giorni di evidenze production;
- multi-tenant e multi-unit certificati;
- disaster recovery provato;
- processi di access review e incident response attivi.

**Evidenze richieste**

- audit indipendente;
- penetration e authorization assessment;
- tenant isolation campaign;
- restore e regional recovery drill;
- capacity e soak test estesi;
- SLO history;
- access review;
- data retention e deletion evidence;
- business continuity report;
- zero-use legacy report quando applicabile.

**Criteri di superamento**

- tutti i Gate 1-10 `PASS` con validita enterprise;
- nessun rischio critico o alto non trattato;
- RTO e RPO rispettati;
- segregazione dei privilegi verificata;
- controllo periodico e recertificazione programmati.

**Motivi di fallimento**

- isolamento tenant non dimostrato;
- DR non provato;
- privilegi non revisionati;
- audit incompleto;
- dipendenza legacy non dichiarata;
- SLO non sostenuti nel periodo richiesto.

---

## 5. Standard Delle Evidenze

### 5.1 Contenuto Minimo

Ogni evidenza deve includere:

- evidence ID univoco;
- gate e controllo coperti;
- livello target;
- release o commit;
- ambiente;
- Organization e Operational Unit;
- planning date e timezone;
- versioni di contratti e configurazione;
- dataset ID e fingerprint;
- procedura eseguita;
- risultato grezzo e sintesi;
- timestamp di inizio e fine;
- actor o service identity;
- owner;
- reviewer indipendente;
- hash dell'artefatto;
- data di scadenza;
- limitazioni note.

### 5.2 Qualita

Un'evidenza deve essere:

- riproducibile;
- attribuibile;
- integra;
- leggibile senza accesso al sistema originale;
- priva di secret e dati personali non necessari;
- prodotta nell'ambiente richiesto dal livello;
- rappresentativa dello scope certificato;
- conservata secondo retention approvata.

Screenshot, messaggi di chat e dichiarazioni verbali possono accompagnare una
evidenza, ma non sostituiscono log, report, metriche o risultati firmati.

### 5.3 Validita

Validita massima predefinita:

| Evidenza | Validita massima |
| --- | --- |
| Architecture e contract review | 90 giorni o fino a modifica materiale |
| Security assessment | 90 giorni o fino a modifica del boundary |
| Performance e load report | 30 giorni o fino a modifica di runtime/infrastruttura |
| Failure injection | 90 giorni o fino a modifica del recovery path |
| Rollback e restore drill | 90 giorni |
| Canary metrics | finestra corrente, senza interruzioni non spiegate |
| Production SLO | finestra rolling di 30 giorni |
| Enterprise evidence | massimo 12 mesi, salvo frequenza piu severa |

Una modifica a writer, fencing, idempotenza, scope, schema, audit, deployment,
security boundary o recovery invalida immediatamente le evidenze correlate.

### 5.4 Firma

Ogni gate deve avere:

- owner responsabile dell'evidenza;
- reviewer che non sia l'unico autore del controllo;
- approvatore del gate;
- Certification Authority per il record finale.

---

## 6. Gate 1 - Architecture Integrity

### 6.1 Obiettivo

Dimostrare che l'architettura impedisce autorita ambigua, dipendenze vietate e
mutazioni non governate.

### 6.2 Controlli Obbligatori

| Controllo | Evidenza | PASS | FAIL |
| --- | --- | --- | --- |
| Single writer | writer map e test di mutua esclusione | un solo writer per scope e istante | due writer possibili o writer ignoto |
| Fail-closed | test negativi e state transition report | ogni anomalia blocca | fallback o write implicito |
| Contratti | catalogo versionato | input/output/scopo espliciti | contratto ambiguo o non versionato |
| Dipendenze | dependency report | direzione conforme alla Costituzione | Core dipende da livelli esterni |
| Immutabilita | contract test | fatti storici non sovrascritti | update distruttivo del passato |
| State machine | transition matrix | transizioni e divieti completi | transizione ambigua o non auditata |
| Separation of concerns | architecture review | ownership unica e chiara | responsabilita duplicate o circolari |

### 6.3 Criteri Di Superamento

- tutti i controlli applicabili `PASS`;
- single writer e fail-closed non ammettono `WARNING`;
- ogni deroga architetturale ha ADR, scadenza e piano di rimozione;
- nessun componente osservativo puo acquisire autorita di scrittura.

### 6.4 Motivi Di Fallimento

- doppia autorita potenziale;
- state machine incompleta;
- transizione mutante senza expected version;
- dipendenza vietata;
- simulazione capace di produrre side effect;
- regola critica delegata al frontend o a convenzioni operative.

**Owner:** Principal Architect.  
**Co-owner:** Runtime Owner e Planning Owner.

---

## 7. Gate 2 - Data Integrity

### 7.1 Obiettivo

Dimostrare che identita, contenuto, versione e storia possono essere verificati
e ricostruiti.

### 7.2 Controlli Obbligatori

| Controllo | Evidenza richiesta | PASS |
| --- | --- | --- |
| Fingerprint | canonicalization e tamper tests | stesso contenuto produce stesso hash; alterazione rilevata |
| Versioning | version chain report | versioni monotone, scope coerente, mismatch rifiutato |
| Append-only | storage e domain tests | nuovi fatti aggiunti, nessuna riscrittura |
| History | reconstruction report | actor, timestamp, causa e versione ricostruibili |
| Replay | deterministic replay report | replay uguale non duplica effetti |
| Idempotenza | retry e duplicate command tests | stessa chiave restituisce stesso outcome |
| Provenienza | lineage report | input, config, rules e Publication tracciabili |
| Retention | policy e restore test | evidenze disponibili per la finestra richiesta |

### 7.3 Catena Minima Di Integrita

```text
Input fingerprint
    -> Draft version/fingerprint
    -> Confirmation version/fingerprint
    -> Publication version/fingerprint
    -> Intent identity/idempotency key
    -> Attempt number/fencing token
    -> Execution result fingerprint
    -> Audit record
```

Ogni collegamento deve poter essere verificato senza fidarsi del client.

### 7.4 Criteri Di Superamento

- zero mismatch non spiegati nella catena;
- replay deterministico;
- nessun numero di Attempt riutilizzato;
- storia ricostruibile dalla sorgente al risultato;
- audit e dato operativo coerenti.

### 7.5 Motivi Di Fallimento

- hash calcolato su rappresentazioni non canoniche;
- versione decrementata o riutilizzata;
- storia modificabile;
- replay capace di duplicare un effetto;
- gap tra commit operativo e audit;
- perdita della provenienza.

**Owner:** Data Integrity Owner.  
**Reviewer:** Runtime Owner e Audit Owner.

---

## 8. Gate 3 - Runtime Safety

### 8.1 Obiettivo

Dimostrare che il percorso Authority, Intent, Attempt, Producer, Shadow e
Comparator e coerente, fail-closed e privo di effetti non autorizzati.

### 8.2 Controlli Per Componente

| Componente | Verifica obbligatoria | Esito atteso |
| --- | --- | --- |
| Authority | scope, validita, priorita, fencing e conflitti | una sola decisione valida oppure `NO_WRITE` |
| Intent | identita, Publication, fingerprint, actor e idempotenza | immutabile, unico e verificabile |
| Attempt | numbering, expected version, lock logico e fencing | append-only, mai riutilizzato |
| Producer | completezza, determinismo e immutabilita | output completo oppure nessun output |
| Shadow | stesso input del legacy e write-set vuoto | osservazione senza side effect |
| Comparator | confronto semantico, severita e latenza | mismatch spiegabili e metriche coerenti |
| Canary | policy, soglie, report e decisione informativa | nessuna promozione automatica |

### 8.3 Invarianti

- Authority `NO_WRITE` impedisce ogni percorso mutante;
- Intent non `READY` non produce Attempt eseguibile;
- Attempt non `READY_TO_EXECUTE` non autorizza esecuzione;
- Publication assente o incoerente blocca;
- fencing obsoleto blocca;
- Producer invalido non produce output parziale;
- Comparator assente blocca il Canary;
- un Canary `PASS` e un'evidenza, non un comando;
- legacy resta writer finche Authority non cambia esplicitamente.

### 8.4 Criteri Di Superamento

- tutte le invarianti provate con casi positivi e negativi;
- zero side effect in Shadow e Canary osservativo;
- diagnostica leggibile per ogni rifiuto;
- scope e versioni coerenti end-to-end;
- parity e mismatch attribuiti a una coppia precisa di output.

### 8.5 Motivi Di Fallimento

- input diversi tra legacy e Runtime;
- risultato parziale;
- componente mancante trattato come successo;
- `PASS` trasformato automaticamente in Authority;
- lock o fencing non verificato;
- duplicate execution maggiore di zero.

**Owner:** Runtime Owner.  
**Approvatore:** Principal Architect.

---

## 9. Gate 4 - Operational Safety

### 9.1 Obiettivo

Dimostrare che il sistema rimane sicuro durante guasti reali o parziali, non
soltanto durante il percorso nominale.

### 9.2 Scenari Minimi

Devono essere simulati almeno:

- crash prima dell'acquisizione del lock;
- crash dopo il lock e prima del write;
- crash dopo il write e prima dell'outcome;
- timeout del client;
- timeout tra componenti;
- perdita o scadenza dell'Authority;
- database non disponibile;
- commit con outcome sconosciuto;
- audit non disponibile;
- processo obsoleto durante rolling deploy;
- perdita di observability;
- rollback interrotto.

### 9.3 Comportamento Atteso

In ogni scenario:

1. nessun secondo writer viene abilitato;
2. retry usa la stessa idempotency key o un nuovo Attempt dello stesso Intent;
3. outcome sconosciuto entra in `RECONCILIATION_REQUIRED`;
4. fallback resta bloccato finche il tentativo precedente non e determinato;
5. audit mancante blocca il write oppure viene garantito atomicamente;
6. Recovery Owner e runbook sono identificabili;
7. l'operatore riceve diagnostica senza stack trace o dati sensibili.

### 9.4 Criteri Di Superamento

- 100% degli scenari obbligatori produce l'outcome atteso;
- zero duplicate execution;
- zero writer overlap;
- recovery completato entro RTO;
- nessuna perdita di storia;
- reconciliation provata.

### 9.5 Motivi Di Fallimento

- retry non idempotente;
- fallback avviato mentre l'outcome e incerto;
- audit perso;
- lock non rilasciato o rubato senza fencing;
- recovery manuale non documentato;
- scenario non riproducibile.

**Owner:** Reliability Owner.  
**Co-owner:** Operations Owner.

---

## 10. Gate 5 - Failure Injection

### 10.1 Obiettivo

Provare intenzionalmente i failure boundary e documentare expected behaviour,
recovery e ownership prima che il guasto avvenga in produzione.

### 10.2 Regole Della Campagna

- ogni scenario usa uno scope isolato;
- l'iniezione e autorizzata;
- il writer atteso e dichiarato prima del test;
- log, metriche e audit vengono conservati;
- il test verifica sia l'errore sia il recovery;
- nessun test termina con outcome indeterminato;
- i dati usati sono sintetici o anonimizzati;
- un risultato inatteso apre un `FAIL`, non un nuovo expected behaviour.

### 10.3 Matrice Completa Dei Failure Scenario

| ID | Scenario | Expected behaviour | Recovery | Owner |
| --- | --- | --- | --- | --- |
| FI-01 | Authority assente | `NO_WRITE`, nessun Attempt eseguibile | ripristinare Authority valida e creare nuovo comando | Authority Owner |
| FI-02 | Authority scaduta durante il flusso | commit rifiutato dal fencing | risolvere nuova Authority, riconciliare Attempt | Authority Owner |
| FI-03 | Due Authority con stessa priorita | conflitto esplicito, `NO_WRITE` | revocare o supersedere una decisione | Authority Owner |
| FI-04 | Fencing token obsoleto | stale writer rifiutato | ricaricare decisione corrente; mai riusare il token | Runtime Owner |
| FI-05 | Intent non READY | nessun Attempt eseguibile | correggere prerequisiti o creare nuovo Intent valido | Execution Owner |
| FI-06 | Intent duplicato | restituzione idempotente dello stesso Intent | nessuna azione oppure query outcome | Execution Owner |
| FI-07 | Intent key con payload diverso | conflitto di integrita | nuova Publication o nuova chiave valida | Execution Owner |
| FI-08 | Attempt duplicato | numero precedente non riusato | append di un nuovo Attempt monotono | Execution Owner |
| FI-09 | Publication assente | fail-closed | pubblicare tramite workflow autorizzato | Publication Owner |
| FI-10 | Publication superseded o revoked | esecuzione bloccata | selezionare Publication corrente | Publication Owner |
| FI-11 | Fingerprint alterato | mismatch critico, nessun output/esecuzione | rigenerare dal contenuto canonico | Data Integrity Owner |
| FI-12 | Version mismatch | rifiuto con expected/current version | rileggere stato e creare nuovo comando | Data Integrity Owner |
| FI-13 | Snapshot stale | stato `STALE` o blocco secondo policy | aggiornare input e ricalcolare | Input Owner |
| FI-14 | Producer non disponibile | nessun Runtime output | mantenere legacy writer; retry controllato | Runtime Owner |
| FI-15 | Producer restituisce output parziale | output scartato | correggere input o Producer; nuovo tentativo | Runtime Owner |
| FI-16 | Comparator non disponibile | Canary `ABORTED/FAIL` | ripristinare Comparator e ripetere osservazione | Runtime Owner |
| FI-17 | Parity sotto soglia | `FAIL`, nessuna promozione | triage mismatch e nuova campagna | Operations Owner |
| FI-18 | Critical mismatch | stop immediato della coorte | root cause, remediation e recertificazione | Operations Owner |
| FI-19 | Duplicate execution rilevata | stop, Authority bloccata, incidente critico | reconciliation e incident review | Reliability Owner |
| FI-20 | Crash prima del lock | nessun writer acquisito | retry idempotente | Runtime Owner |
| FI-21 | Crash dopo lock, prima del write | lease/fencing impediscono writer parallelo | scadenza controllata e nuovo Attempt | Runtime Owner |
| FI-22 | Crash dopo write, prima dell'outcome | `RECONCILIATION_REQUIRED` | verificare write e completare outcome senza duplicare | Reliability Owner |
| FI-23 | Timeout client prima della risposta | retry restituisce stesso outcome | query per idempotency key | API Owner |
| FI-24 | Timeout interno | nessun fallback implicito | retry bounded o reconciliation | Reliability Owner |
| FI-25 | Database non raggiungibile prima del commit | nessun cambiamento operativo | ripristinare DB e retry | Data Platform Owner |
| FI-26 | Connessione persa durante commit | outcome indeterminato, write bloccati sullo scope | reconciliation dal database autorevole | Data Platform Owner |
| FI-27 | Deadlock o serialization failure | transazione abortita | retry con backoff e stessa idempotency key | Data Platform Owner |
| FI-28 | Audit sink non disponibile prima del write | write bloccato se audit non atomico | ripristinare audit e retry | Audit Owner |
| FI-29 | Fallimento audit dopo commit | scenario vietato o outbox atomica recuperabile | replay outbox, verifica completezza | Audit Owner |
| FI-30 | Correlation ID mancante | richiesta rifiutata al gate operativo | ricreare comando completo | Observability Owner |
| FI-31 | Metric backend non disponibile | nessuna espansione Canary | ripristinare monitoring; mantenere coorte | Observability Owner |
| FI-32 | Log pipeline in ritardo | promozione sospesa | recuperare backlog e verificare audit | Observability Owner |
| FI-33 | CPU satura | backpressure, nessun duplicate retry | ridurre coorte o scalare | Performance Owner |
| FI-34 | Memoria oltre soglia | istanza rimossa in sicurezza, scope protetto | restart controllato e analisi leak | Performance Owner |
| FI-35 | Processo legacy e Runtime convivono | Authority consente un solo writer | terminare processo non autorizzato | Release Owner |
| FI-36 | Rolling deploy con schema misto | reader compatibili, writer con capability gate | fermare rollout o downgrade verificato | Release Owner |
| FI-37 | Configurazione incompatibile | fail-closed prima dell'esecuzione | rollback configurazione versionata | Configuration Owner |
| FI-38 | Clock skew | lease e timestamp non concedono doppia autorita | sincronizzazione e nuova valutazione | Platform Owner |
| FI-39 | Cambio DST o planning date | scope resta sulla data operativa corretta | riconciliare solo lo scope interessato | Operations Owner |
| FI-40 | Comando cross-tenant | accesso negato, nessuna informazione esposta | security incident e review | Security Owner |
| FI-41 | Privilegio insufficiente | comando negato e auditato | approvazione tramite ruolo corretto | Security Owner |
| FI-42 | Actor revocato durante operazione | nuovo commit negato | nuova approvazione, mai ereditare sessione | Security Owner |
| FI-43 | Replay malevolo | idempotenza o replay protection bloccano | audit security e rotazione se necessaria | Security Owner |
| FI-44 | Rollback concorrente con execution | uno solo acquisisce Authority/lock | completare o riconciliare il vincitore | Rollback Owner |
| FI-45 | Due rollback concorrenti | uno solo accettato | query rollback corrente | Rollback Owner |
| FI-46 | Crash durante rollback | scope bloccato, nessun writer ordinario | nuovo Attempt dello stesso Rollback Intent | Rollback Owner |
| FI-47 | Target rollback mancante | rollback rifiutato | selezionare target verificabile | Rollback Owner |
| FI-48 | Restore backup fallisce | nessuna dichiarazione di recovery | correggere backup e ripetere drill | Disaster Recovery Owner |
| FI-49 | Perdita parziale di rete tra repliche | fencing impedisce split-brain | isolare replica, riconciliare scope | Platform Owner |
| FI-50 | Arresto manuale del Canary | nessuna espansione o cambio writer implicito | chiudere sessione, conservare report | Release Owner |

### 10.4 Criteri Di Superamento

- tutti gli scenari applicabili eseguiti;
- tutti gli expected behaviour osservati;
- recovery completato;
- owner e runbook confermati;
- nessun gap di audit;
- nessun duplicate execution;
- nessun risultato classificato come "non riproducibile" senza nuova campagna.

### 10.5 Motivi Di Fallimento

- scenario saltato senza `NOT_APPLICABLE` firmato;
- expected behaviour modificato dopo il test;
- recovery non completato;
- evidenza priva di scope o correlation ID;
- owner non disponibile;
- test distruttivo fuori dall'ambiente autorizzato.

**Owner:** Reliability Owner.  
**Approvatore:** Certification Authority.

---

## 11. Gate 6 - Observability

### 11.1 Obiettivo

Rendere ogni decisione, tentativo, confronto e outcome ricostruibile senza
accedere a dati personali o payload grezzi.

### 11.2 Identificatori Obbligatori

Ogni evento rilevante deve esporre:

- Correlation ID;
- Causation ID quando applicabile;
- Authority ID e versione;
- Intent ID;
- Attempt ID e attempt number;
- Publication ID e versione;
- Organization ID;
- Operational Unit ID;
- planning date;
- timezone;
- actor o service identity;
- modalita;
- versioni di input, configurazione e regole;
- fingerprint;
- latency;
- audit reference;
- outcome;
- error code sanitizzato.

### 11.3 Segnali Obbligatori

| Segnale | Requisito |
| --- | --- |
| Log strutturati | ricercabili per tutti gli identificatori obbligatori |
| Metriche | rate, latency, errori, parity, mismatch, retry, rollback |
| Trace | confini Authority, Intent, Attempt, Producer, Comparator ed execution |
| Audit | actor, decisione, motivazione, versione e risultato |
| Alert | soglie critiche con owner e escalation |
| Dashboard | stato per scope e coorte, non solo media globale |

### 11.4 Alert Minimi

- writer conflict;
- Authority conflict o expiry inattesa;
- stale fencing;
- duplicate execution;
- critical mismatch;
- parity sotto soglia;
- fingerprint mismatch;
- audit gap;
- reconciliation richiesta;
- rollback fallito;
- error budget burn;
- metriche mancanti durante Canary.

### 11.5 Criteri Di Superamento

- 100% degli eventi mutanti correlabili;
- audit reconciliation senza gap;
- alert provati e ricevuti dall'owner;
- nessun payload personale grezzo nei log;
- dashboard disponibile durante la finestra di certificazione;
- retention coerente con incident e audit policy.

### 11.6 Motivi Di Fallimento

- eventi senza scope o ID;
- metriche aggregate che nascondono una OU;
- alert non instradati;
- log contenenti secret;
- impossibilita di ricostruire un Attempt;
- monitoring assente durante Canary.

**Owner:** Observability Owner.  
**Reviewer:** Audit Owner.

---

## 12. Gate 7 - Performance Certification

### 12.1 Obiettivo

Dimostrare che osservazione, confronto ed esecuzione rispettano budget
misurabili senza degradare il writer corrente o saturare l'infrastruttura.

### 12.2 KPI Minimi

| KPI | Soglia minima |
| --- | --- |
| Parity | >= 99,5% su almeno 1.000 casi rappresentativi |
| Critical mismatch | 0 |
| Duplicate execution | 0 |
| Execution success | >= 99,9% nella finestra Canary/production |
| Comparator latency | p95 < 50 ms |
| Producer latency | p95 < 50 ms per payload nel profilo certificato |
| Canary evaluation latency | p95 < 15 ms esclusa acquisizione dati |
| Canary overhead | < 5% rispetto al baseline dichiarato |
| Degrado legacy in Shadow/Verify | < 10% p95 |
| Payload osservativo | < 5 KB salvo contratto approvato |
| Control-plane execution latency | p95 <= 200 ms, p99 <= 500 ms, esclusi sistemi esterni |
| Error rate tecnico | < 0,1% nella finestra certificata |
| CPU | p95 < 70%; nessun periodo >85% per 5 minuti |
| Memoria | picco <70% del limite; crescita steady-state <5% in 8 ore |
| Database pool | p95 utilizzo <80%; zero exhaustion |

Le soglie sono baseline minime. Una policy puo essere piu severa. Non puo
essere rilassata durante un Canary senza una nuova decisione Go/No-Go.

### 12.3 Profili Di Carico

La certificazione deve includere:

- nominale;
- picco mattutino;
- burst di retry;
- multi-OU;
- rolling deploy;
- Comparator attivo;
- failure recovery;
- soak di almeno 8 ore per Level 2;
- soak di almeno 24 ore per Level 3;
- profilo enterprise concordato per Level 4.

### 12.4 Criteri Di Superamento

- tutte le soglie rispettate;
- dataset e hardware dichiarati;
- nessun risultato escluso senza motivazione;
- percentili calcolati su campione sufficiente;
- capacity headroom disponibile;
- degradazione controllata disabilita Shadow, mai la sicurezza del writer.

### 12.5 Motivi Di Fallimento

- uso della sola media;
- benchmark non rappresentativo;
- soglie modificate dopo il test;
- memory growth non spiegata;
- saturazione senza backpressure;
- Comparator che rallenta il legacy oltre budget.

**Owner:** Performance Owner.  
**Approvatore:** Reliability Owner.

---

## 13. Gate 8 - Security Certification

### 13.1 Obiettivo

Dimostrare che solo identita autorizzate possono cambiare stato e che scope,
tenant, segreti e audit sono protetti.

### 13.2 Controlli Obbligatori

| Area | Requisito |
| --- | --- |
| Autenticazione | identita umane e service identity verificabili |
| Autorizzazione | deny-by-default, ruolo e scope controllati server-side |
| Replay protection | idempotency key, nonce o controllo equivalente |
| Tenant isolation | test positivi e negativi cross-tenant |
| Privilege separation | Planner, Approver, Publisher, Operator e Rollback Approver separabili |
| Fencing | token verificato a ogni write boundary |
| Secret management | nessun secret nel repository o nei log |
| Audit integrity | actor, ruolo, decisione e outcome non ripudiabili |
| Session security | revoca ed expiry effettive |
| Data minimization | log e report privi di dati personali non necessari |
| Dependency security | vulnerabilita critiche e alte trattate |
| Incident response | owner, escalation e revoca di emergenza provati |

### 13.3 Criteri Di Superamento

- autenticazione obbligatoria per ogni comando mutante;
- authorization matrix verificata;
- zero accessi cross-tenant;
- stale fencing sempre rifiutato;
- separation of duties applicata al livello target;
- nessun secret rilevato;
- security test e review validi.

### 13.4 Motivi Di Fallimento

- endpoint mutante anonimo;
- ruolo eccessivo;
- tenant isolation non testata;
- controllo solo frontend;
- actor non attribuibile;
- replay capace di creare un nuovo effetto;
- vulnerabilita critica aperta.

**Owner:** Security Owner.  
**Approvatore:** Security Authority.

---

## 14. Gate 9 - Deployment Certification

### 14.1 Obiettivo

Dimostrare che la release puo essere introdotta, osservata, abilitata,
arrestata e rimossa senza perdere compatibilita o controllo del writer.

### 14.2 Sequenza Obbligatoria

```text
Expand -> Observe -> Verify -> Enable -> Contract
                    |
                    v
                 Rollback
```

### 14.3 Fasi

**Expand**

- introdurre contratti e storage additive;
- mantenere reader e writer precedenti;
- vietare migration distruttive.

**Observe**

- distribuire componenti disabilitati o read-only;
- verificare log, metriche, audit e capacity;
- mantenere legacy unico writer.

**Verify**

- attivare Shadow/Comparator;
- misurare parity e performance;
- non concedere ancora autorita al Runtime.

**Enable**

- abilitare la coorte minima approvata;
- cambiare Authority solo per scope espliciti;
- osservare stop conditions.

**Contract**

- rimuovere compatibilita solo dopo zero-use window;
- conservare restore path finche richiesto;
- eseguire uno sprint separato per Legacy Retirement.

**Rollback**

- fermare espansione;
- bloccare nuovi Intent;
- determinare gli Attempt aperti;
- riconciliare;
- cambiare Authority una sola volta;
- verificare outcome e audit.

### 14.4 Controlli Obbligatori

- mixed-version compatibility;
- capability negotiation;
- feature flag server-side e scoped;
- stale writer fencing;
- database backup e restore;
- downgrade o forward-fix documentato;
- release artifact identificabile;
- health e readiness separati;
- stop conditions automatiche solo per fermare, mai per promuovere;
- zero modifica non dichiarata a Railway o infrastruttura equivalente.

### 14.5 Criteri Di Superamento

- deployment rehearsal riuscito;
- rollback rehearsal riuscito;
- zero writer overlap;
- contratti backward-compatible;
- osservabilita disponibile prima dell'Enable;
- approvazione Release Authority.

### 14.6 Motivi Di Fallimento

- enable globale;
- migration distruttiva nello stesso passo;
- rollback non provato;
- feature flag deciso dal frontend;
- mixed version non supportata;
- assenza di backup verificato;
- promozione senza finestra di osservazione.

**Owner:** Release Owner.  
**Approvatore:** Release Authority.

---

## 15. Gate 10 - Business Readiness

### 15.1 Obiettivo

Dimostrare che la piattaforma puo essere gestita da persone reali durante
operativita normale, degrado e incidente.

### 15.2 Evidenze Obbligatorie

- runbook avvio giornata;
- runbook Canary;
- runbook stop e rollback;
- runbook reconciliation;
- runbook database failure;
- runbook audit failure;
- escalation matrix;
- manuale operativo aggiornato;
- guida di diagnostica;
- demo ripetibile;
- dashboard e alert accessibili;
- on-call e backup owner;
- registro delle decisioni;
- audit sample;
- formazione degli operatori;
- support e incident communication;
- business continuity plan.

### 15.3 Criteri Di Superamento

- un operatore non autore esegue correttamente i runbook;
- tempi e responsabilita sono misurati;
- nessun passaggio dipende da conoscenza non documentata;
- demo e training usano la release certificata;
- monitoring e audit sono consultabili;
- stakeholder approvano la finestra e le stop conditions.

### 15.4 Motivi Di Fallimento

- runbook non provato;
- owner singolo senza sostituto;
- manuale non coerente con la release;
- alert senza destinatario;
- demo basata su workaround;
- rollback dipendente dallo sviluppatore originale.

**Owner:** Operations Owner.  
**Approvatore:** Business Operations Authority.

---

## 16. Checklist Di Esito Per Ogni Gate

Ogni gate deve produrre un record con:

```text
Gate:
Target level:
Release:
Environment:
Scope:
Status: PASS | WARNING | FAIL | UNASSESSED | NOT_APPLICABLE
Mandatory controls:
Evidence IDs:
Motivation:
Open risks:
Compensating controls:
Owner:
Reviewer:
Approver:
Issued at:
Expires at:
Reassessment trigger:
```

Checklist obbligatoria:

- [ ] scope completo;
- [ ] release e configurazione identificate;
- [ ] controlli obbligatori elencati;
- [ ] evidenze integre e accessibili;
- [ ] risultati negativi inclusi;
- [ ] owner e reviewer distinti;
- [ ] motivazione dell'esito;
- [ ] validita temporale;
- [ ] trigger di invalidazione;
- [ ] nessun secret o dato personale non necessario;
- [ ] warning con scadenza;
- [ ] failure con remediation e blocco esplicito.

---

## 17. Go / No-Go

### 17.1 Regola

La decisione e `GO` solo se:

- nessun gate applicabile e `FAIL`;
- nessun gate obbligatorio e `UNASSESSED`;
- tutti i `PASS` richiesti dal livello target sono presenti;
- ogni `WARNING` e ammesso dal livello e non riguarda un'invariante critica;
- tutte le evidenze sono valide;
- rollout, coorte, owner, stop conditions e rollback sono approvati;
- la Certification Authority firma.

In ogni altro caso la decisione e `NO-GO`.

### 17.2 Checklist Finale

- [ ] Livello attuale valido.
- [ ] Livello target dichiarato.
- [ ] Scope di promozione minimo e completo.
- [ ] Writer attuale dichiarato.
- [ ] Writer dopo la promozione dichiarato.
- [ ] Gate 1 Architecture Integrity `PASS`.
- [ ] Gate 2 Data Integrity `PASS`.
- [ ] Gate 3 Runtime Safety `PASS`.
- [ ] Gate 4 Operational Safety `PASS`.
- [ ] Gate 5 Failure Injection `PASS`.
- [ ] Gate 6 Observability `PASS`.
- [ ] Gate 7 Performance `PASS`.
- [ ] Gate 8 Security `PASS`.
- [ ] Gate 9 Deployment `PASS`.
- [ ] Gate 10 Business Readiness `PASS`.
- [ ] Parity >=99,5%.
- [ ] Critical mismatch = 0.
- [ ] Duplicate execution = 0.
- [ ] Authority conflict = 0.
- [ ] Rollback drill = 100%.
- [ ] Audit reconciliation = 100%.
- [ ] Nessun Sev-1/Sev-2 aperto.
- [ ] Error budget disponibile.
- [ ] Finestra di osservazione completata.
- [ ] Owner e on-call confermati.
- [ ] Backup e restore verificati.
- [ ] Legacy fallback coerente con la fase.
- [ ] Stop conditions configurate.
- [ ] Record firmato.

### 17.3 Stop Conditions

La promozione viene fermata immediatamente in caso di:

- duplicate execution;
- critical mismatch;
- writer conflict;
- tenant isolation failure;
- audit gap;
- stale fencing accettato;
- outcome indeterminato non riconciliato;
- rollback fallito;
- soglia di error budget superata;
- osservabilita obbligatoria non disponibile.

Lo stop non abilita automaticamente il legacy. Il ritorno al legacy segue il
workflow di rollback e Authority.

---

## 18. Operations Engine Maturity Index

### 18.1 Scopo

L'Operations Engine Maturity Index, `OEMI`, misura la maturita complessiva da
0 a 100. Non sostituisce i gate e non autorizza promozioni.

### 18.2 Dimensioni E Pesi

| Dimensione | Peso |
| --- | ---: |
| Architecture | 15 |
| Runtime | 15 |
| Migration | 15 |
| Security | 15 |
| Performance | 10 |
| Observability | 10 |
| Testing | 12 |
| Documentation | 8 |
| **Totale** | **100** |

### 18.3 Scala Di Maturita

Ogni dimensione riceve un valore da 0 a 5:

| Valore | Significato |
| ---: | --- |
| 0 | assente |
| 1 | definita, non implementata o non verificata |
| 2 | implementata parzialmente |
| 3 | verificata in ambiente controllato |
| 4 | operativa con evidenze sostenute |
| 5 | auditata, resiliente e migliorata continuamente |

Formula:

```text
OEMI = somma(peso_dimensione * valore_dimensione / 5)
```

Il risultato viene arrotondato all'intero piu vicino.

### 18.4 Bande

| OEMI | Interpretazione |
| ---: | --- |
| 0-19 | iniziale |
| 20-39 | strutturato |
| 40-59 | controllato |
| 60-79 | migration capable |
| 80-94 | production mature |
| 95-100 | enterprise sustained |

### 18.5 Regole Di Ceiling

- Gate 1 `FAIL`: OEMI pubblicabile massimo 19.
- Violazione osservata di single writer, duplicate execution o tenant
  isolation: massimo 39.
- Gate 4, 5, 8 o 9 `FAIL`: nessuna classificazione `Production Ready`.
- Evidenze scadute: la dimensione torna al massimo a 2.
- Level 4 richiede OEMI almeno 95, ma OEMI 95 non concede Level 4.

### 18.6 Evidenza Del Calcolo

Ogni valore deve indicare:

- motivazione;
- evidence IDs;
- data;
- owner;
- reviewer;
- delta rispetto alla valutazione precedente.

---

## 19. Ciclo Di Certificazione

### 19.1 Passi

1. definire target level e promozione;
2. congelare release, configurazione e scope;
3. nominare owner e reviewer;
4. raccogliere evidenze esistenti;
5. classificare i gap;
6. eseguire test, failure injection, performance e security campaign;
7. emettere esito per ogni gate;
8. calcolare OEMI;
9. svolgere Go/No-Go review;
10. firmare il record;
11. eseguire la promozione approvata;
12. osservare la finestra richiesta;
13. chiudere o revocare la certificazione.

### 19.2 Recertificazione

La recertificazione e obbligatoria dopo:

- modifica del writer;
- modifica a Authority, fencing, lock o idempotenza;
- modifica incompatibile dei contratti;
- modifica del fingerprint canonico;
- nuova strategia di persistence;
- nuova modalita multi-tenant;
- cambiamento del recovery path;
- incidente Sev-1 o Sev-2;
- rollback reale;
- cambio infrastrutturale materiale;
- scadenza delle evidenze.

### 19.3 Revoca

La Certification Authority puo revocare un livello quando:

- emerge un'evidenza falsa o incompleta;
- un'invariante viene violata;
- le evidenze scadono;
- lo scope reale supera quello certificato;
- un incidente dimostra che l'expected behaviour era errato.

La revoca non cancella il record. Produce un nuovo evento di certificazione.

---

## 20. Roadmap Di Certificazione

| Step | Obiettivo di certificazione | Livello atteso | Evidenza principale |
| --- | --- | --- | --- |
| PW-9G | Canary Runtime reale, coorte minima, mixed-version deploy, stop conditions | uscita da Level 2 verso Level 3 | 14 giorni, 500 execution, zero Sev-1/2, duplicate 0 |
| PW-9H | espansione 5/25/50/100%, SLO, capacity, DR e hardening | Level 3 | 30 giorni stabili, success >=99,9%, rollback e DR |
| PW-X | security enterprise, multi-tenant, audit indipendente e business continuity | Level 4 | tenant isolation, access review, pen test, 90 giorni |
| PW-Y | Legacy Retirement controllato | mantenimento Level 3/4 | zero-use, dependency inventory, restore window e decisione irreversibile |

Associazione completa dei livelli:

| Livello | Relazione con gli step futuri |
| --- | --- |
| Level 0 | baseline obbligatoria; non autorizza PW-9G |
| Level 1 | prerequisito tecnico da certificare prima della campagna Migration Ready |
| Level 2 | gate di ingresso obbligatorio per PW-9G |
| Level 3 | risultato atteso di PW-9G/PW-9H e prerequisito per PW-Y |
| Level 4 | obiettivo di PW-X; deve essere mantenuto durante PW-Y se richiesto dallo scope enterprise |

### 20.1 PW-9G

PW-9G puo iniziare solo dopo Level 2. Il Canary non puo superare la coorte
approvata. L'espansione richiede un nuovo record Go/No-Go.

### 20.2 PW-9H

PW-9H dimostra stabilita sostenuta. Non rimuove il legacy. Chiude i requisiti
per rendere il Runtime writer primario su tutte le OU approvate.

### 20.3 PW-X

PW-X porta sicurezza, isolamento, disaster recovery e governance al livello
enterprise. Non puo ridurre le soglie dei livelli precedenti.

### 20.4 PW-Y

PW-Y governa il retirement. Deve distinguere:

1. legacy disabilitato ma deployabile;
2. legacy escluso dal runtime attivo;
3. legacy rimosso dopo zero-use window.

La rimozione e irreversibile nel record corrente e richiede decisione
esplicita, backup, restore evidence e inventario dipendenze pari a zero.

---

## 21. Valutazione Attuale

### 21.1 Perimetro Della Valutazione

Questa e una valutazione iniziale documentale al 23 luglio 2026. Non sostituisce
una campagna firmata e non promuove alcun writer.

Stato operativo dichiarato:

```text
Planning legacy = unico writer operativo
Runtime = osservazione e confronto
Canary = valutazione informativa
Production Runtime writer = non autorizzato
Legacy Retirement = non autorizzato
```

### 21.2 Esito Dei Gate Verso La Prossima Promozione

| Gate | Esito attuale | Motivazione |
| --- | --- | --- |
| 1 Architecture Integrity | `PASS` per Level 0 | single writer e confini risultano dichiarati; nessuna promozione implicita |
| 2 Data Integrity | `PASS` per Level 0; `WARNING` verso Level 1/2 | fingerprint, versioning e append-only sono definiti; replay operativo end-to-end richiede certificazione |
| 3 Runtime Safety | `PASS` in modalita osservativa | pipeline Runtime/Shadow/Canary disponibile senza autorita operativa |
| 4 Operational Safety | `FAIL` | crash, timeout, audit failure e recovery non hanno una campagna firmata completa |
| 5 Failure Injection | `FAIL` | matrice definita in questo documento ma non ancora eseguita |
| 6 Observability | `WARNING` | identificatori di dominio esistono; correlazione, trace, audit e alert end-to-end non sono certificati |
| 7 Performance | `WARNING` | misure locali rispettano budget iniziali; mancano load, soak e campione production rappresentativo |
| 8 Security | `FAIL` | autenticazione, authorization matrix, tenant isolation e separation of duties non sono certificate |
| 9 Deployment | `FAIL` | expand/observe/verify/enable/rollback non sono stati provati come campagna completa |
| 10 Business Readiness | `WARNING` | documentazione architetturale ampia; runbook operativi, on-call e drill non sono certificati |

### 21.3 Livello Attuale

**Livello certificabile con le evidenze oggi disponibili:**

```text
LEVEL 0 - ARCHITECTURE READY
```

**Stato del livello successivo:**

```text
LEVEL 1 - RUNTIME READY: CANDIDATE, NON ANCORA CERTIFICATO
```

### 21.4 Decisione Attuale

```text
NO-GO
```

Il `NO-GO` si applica a:

- Runtime come writer;
- Canary con effetti operativi;
- espansione production;
- disabilitazione del legacy;
- rimozione del legacy.

Sono consentiti soltanto sviluppo controllato, test, osservazione, raccolta
evidenze e campagne in ambienti autorizzati che mantengono il legacy come
unico writer.

### 21.5 Operations Engine Maturity Index Attuale

Valutazione iniziale:

| Dimensione | Valore 0-5 | Peso | Contributo |
| --- | ---: | ---: | ---: |
| Architecture | 4 | 15 | 12,0 |
| Runtime | 3 | 15 | 9,0 |
| Migration | 2 | 15 | 6,0 |
| Security | 1 | 15 | 3,0 |
| Performance | 2 | 10 | 4,0 |
| Observability | 2 | 10 | 4,0 |
| Testing | 3 | 12 | 7,2 |
| Documentation | 4 | 8 | 6,4 |
| **OEMI** |  |  | **51,6 -> 52/100** |

Classificazione: **controllato**.

Il punteggio non modifica il `NO-GO`, perche Gate 4, 5, 8 e 9 sono `FAIL`.

### 21.6 Gap Aperti

**Critici**

- failure injection non eseguita;
- autenticazione e autorizzazione non certificate;
- tenant isolation non certificata;
- execution e rollback recovery non dimostrati;
- deployment misto e rollback non provati;
- audit atomico end-to-end non certificato.

**Importanti**

- correlation e tracing end-to-end;
- load e soak test;
- replay deterministico operativo;
- runbook e on-call;
- alert e stop conditions provati;
- campione parity di almeno 1.000 casi.

**Futuri**

- 14 giorni e 500 execution Canary;
- espansione 5/25/50/100%;
- 30 giorni di stabilita Runtime;
- 90 giorni di zero-use legacy;
- audit enterprise e disaster recovery esteso.

---

## 22. Raccomandazioni E Record Ufficiale

### 22.1 Raccomandazioni Immediate

1. Non cambiare il writer attuale.
2. Costituire la Certification Authority e assegnare gli owner dei dieci gate.
3. Creare un evidence register con ID, hash, owner e scadenza.
4. Certificare formalmente Level 1 con campione parity almeno 1.000.
5. Eseguire Gate 4 e Gate 5 in staging prima di qualsiasi Canary operativo.
6. Chiudere Gate 8 prima di introdurre endpoint mutanti Runtime.
7. Provare mixed-version deploy e rollback prima di PW-9G.
8. Preparare runbook e on-call prima della richiesta Level 2.
9. Non rilassare le soglie per ottenere un `PASS`.
10. Trattare ogni failure inatteso come gap, non come nuova normalita.

### 22.2 Template Del Record Di Certificazione

```text
CERTIFICATION ID:
TARGET LEVEL:
DECISION: GO | NO-GO | REVOKED

RELEASE / COMMIT:
CONTRACT VERSION:
CONFIGURATION VERSION:
ENVIRONMENT:
ORGANIZATION:
OPERATIONAL UNIT:
PLANNING DATE / WINDOW:
TIMEZONE:

CURRENT WRITER:
TARGET WRITER:
MIGRATION PHASE:
CANARY COHORT:

GATE 1:
GATE 2:
GATE 3:
GATE 4:
GATE 5:
GATE 6:
GATE 7:
GATE 8:
GATE 9:
GATE 10:

OEMI:
OPEN WARNINGS:
OPEN FAILURES:
STOP CONDITIONS:
ROLLBACK PLAN:
EVIDENCE REGISTER:

ARCHITECTURE APPROVER:
RUNTIME APPROVER:
SECURITY APPROVER:
OPERATIONS APPROVER:
RELEASE APPROVER:
CERTIFICATION AUTHORITY:

ISSUED AT:
EXPIRES AT:
REASSESSMENT TRIGGERS:
```

### 22.3 Clausola Vincolante

Nessun documento di sprint, risultato di test, dashboard, decisione di deploy
o approvazione informale puo sostituire questo processo.

Prima di ogni promozione:

```text
Runtime -> Canary -> Production -> Legacy Retirement
```

deve esistere un record di certificazione completo, valido e firmato.

In assenza del record, la decisione ufficiale e:

```text
NO-GO
```
