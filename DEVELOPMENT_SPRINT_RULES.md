# Development Sprint Rules

**Stato:** regole vincolanti di esecuzione
**Ambito:** ogni sprint di prodotto, architettura, UX o infrastruttura
**Riferimenti:** [Operations Engine Vision](OPERATIONS_ENGINE_VISION.md), [Operations Engine Roadmap](OPERATIONS_ENGINE_ROADMAP.md), [Core, Adapter e Plugin Boundaries](CORE_ADAPTER_PLUGIN_BOUNDARIES.md)

## 1. Una fase, un obiettivo

Ogni sprint ha un solo obiettivo verificabile. Funzioni adiacenti, refactoring opportunistici e anticipazioni della roadmap restano fuori scope.

Lo sprint deve dichiarare prima delle modifiche:

- problema e utente coinvolto;
- risultato osservabile;
- owner architetturale;
- scope e non-obiettivi;
- contratti che non possono cambiare;
- criteri di accettazione;
- verifiche richieste.

## 2. Preflight architetturale

Prima di scrivere codice occorre stabilire se la modifica appartiene a:

- Core;
- Adapter;
- Plugin;
- Configuration Engine;
- frontend di una workspace;
- infrastruttura o documentazione.

La dipendenza deve rispettare [Core, Adapter e Plugin Boundaries](CORE_ADAPTER_PLUGIN_BOUNDARIES.md). Un'incertezza di ownership blocca l'implementazione, non viene risolta creando un servizio generico.

## 3. Compatibilita

Ogni sprint elenca esplicitamente API, payload, database, comportamenti e flussi UX da mantenere. Le migrazioni di linguaggio convivono con i contratti legacy finche non esiste un piano di deprecazione separato.

Una modifica interna non autorizza:

- rinomina silenziosa di campi pubblici;
- variazione di semantica;
- cancellazione di dati o storia;
- modifica delle decisioni esistenti;
- sostituzione di fallback sicuri con errori.

## 4. Configurazione e dati verticali

Nuovi stati, soglie, nomenclature, capability e policy devono essere configurabili quando rappresentano variabilita organizzativa. I termini di un operatore o mercato restano nel relativo Adapter.

Nessun codice cliente, station reale, targa, PIN, email, token o file operativo reale entra nel repository o nelle fixture.

## 5. Qualita dell'implementazione

- nessun file monolitico;
- una responsabilita principale per modulo;
- nessuna logica business importante nel frontend;
- nessuna duplicazione intenzionale di decisioni;
- nessuna astrazione senza un uso reale;
- nessuna dipendenza diretta tra Plugin;
- nessun accesso agli internals di un Plugin da parte del Core;
- eventi cronologici quando la storia e parte del dominio;
- errori previsti distinti dagli errori imprevisti.

## 6. Test e verifica

La copertura cresce con il rischio. Ogni sprint esegue almeno:

- test mirati del comportamento modificato;
- suite esistente pertinente;
- test di contratto quando cambia un confine;
- controllo regressioni delle API quando applicabile;
- `git diff --check`;
- scansione dei file modificati per secret e dati personali.

Gli sprint frontend includono QA browser su desktop, tablet e mobile, stati loading/empty/error, navigazione tastiera e controllo della console. Gli screenshot documentano il risultato ma non sostituiscono i test.

Gli sprint esclusivamente documentali validano link, percorsi, coerenza terminologica e Markdown. Non eseguono test applicativi privi di relazione con le modifiche.

## 7. Git e deploy

Prima di intervenire si registra lo stato del working tree. Le modifiche preesistenti vengono preservate e non ripristinate senza consenso.

Sono vietati senza autorizzazione esplicita:

- commit;
- push o force-push;
- deploy;
- riscrittura della cronologia;
- modifica di Railway o altri ambienti;
- operazioni distruttive sui dati.

Il report finale puo fornire i comandi proposti senza eseguirli.

## 8. Privacy e sicurezza

Secret e credenziali sono esclusivamente variabili d'ambiente o secret manager. I log non espongono payload sensibili. File di esempio e fixture usano dati sintetici chiaramente non reali.

Ogni nuovo ingresso dati deve definire validazione, limiti, gestione dei file corrotti e messaggi senza stack trace. La sicurezza non viene rinviata a uno sprint successivo quando il cambiamento amplia la superficie di input.

## 9. Stop conditions

Lo sprint si ferma e viene rivalutato quando:

- richiede una nuova API non prevista;
- modifica il modello o il database esclusi dallo scope;
- introduce una dipendenza vietata;
- necessita di dati reali per essere testato;
- fallisce un contratto pubblico esistente;
- la funzione appartiene a una fase futura;
- il comportamento desiderato non e verificabile.

## 10. Definition of Done

Uno sprint e concluso solo quando:

1. l'obiettivo unico e raggiunto;
2. i non-obiettivi sono rimasti invariati;
3. i criteri di accettazione sono verificati;
4. test e QA richiesti sono conclusi;
5. non restano errori noti non dichiarati;
6. documentazione e contratti sono aggiornati;
7. il diff contiene solo file pertinenti;
8. rischi residui e attivita manuali sono riportati;
9. nessuna operazione Git o remota non autorizzata e stata eseguita;
10. il risultato rispetta la fase corrente della Roadmap.

## 11. Template minimo dello sprint

```text
Titolo:
Fase Roadmap:
Obiettivo unico:
Utente e problema:
Owner architetturale:
Scope:
Non-obiettivi:
Contratti invariati:
Criteri di accettazione:
Test e QA:
Rischi:
Operazioni vietate:
Output finale:
```

Questo template e obbligatorio per le nuove iniziative. Uno sprint privo di non-obiettivi o verifiche esplicite non e pronto.
