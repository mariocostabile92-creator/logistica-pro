# Operations Engine - Security Hardening Plan

## 0. Controllo Del Documento

| Campo | Valore |
| --- | --- |
| Documento | `SECURITY_HARDENING_PLAN.md` |
| Iniziativa | PP-1 |
| Stato | Piano ufficiale di hardening; nessuna implementazione inclusa |
| Data assessment | 2026-07-23 |
| Baseline repository | `56dc49c` |
| Ambito | Backend, API, dati, Runtime, Plugin, configurazione, deploy e processi operativi |
| Esclusioni | Modifiche a codice, endpoint, frontend, database, Planning Engine e Runtime |
| Decisione attuale | `NO-GO` per esposizione Production senza controllo accessi |
| Security Readiness Score | **30/100** |

Questo documento valuta la postura reale del repository e definisce il percorso
necessario per preparare Operations Engine alla Production. Non certifica il
deploy Railway, l'infrastruttura esterna, il comportamento sotto attacco o
l'assenza assoluta di vulnerabilita.

L'assessment e stato eseguito tramite analisi statica di:

- applicazione FastAPI e relativa OpenAPI;
- router, schemi, servizi, repository e modelli di dominio;
- Configuration Engine;
- Planning, Draft, Confirmation, Publication e Runtime osservativo;
- Workforce e Fleet Plugin;
- import Excel/CSV ed export CSV;
- audit esistenti;
- configurazione di produzione, Docker e Railway;
- test di sicurezza e integrita gia presenti;
- stato corrente dei file tracciati e ricerca euristica di secret nel working
  tree.

Non sono stati eseguiti penetration test, DAST, fuzzing, load test, verifica
delle variabili Railway, verifica TLS del database, analisi dell'account cloud o
test di compromissione. Queste evidenze restano obbligatorie prima della
Production.

---

## 1. Executive Summary

Operations Engine possiede una buona base di integrita per i contratti Runtime:
versioni, fingerprint, fencing, idempotenza dell'Execution Intent, repository
append-only e comportamento fail closed. Possiede inoltre header HTTP utili,
configurazione Production fail-fast, dipendenze Python bloccate a versione,
container non-root e gestione dei secret prevista tramite variabili d'ambiente.

Questi controlli non costituiscono ancora un perimetro di sicurezza Production.
La superficie HTTP corrente comprende:

- **63 path OpenAPI**;
- **66 operazioni HTTP**;
- **36 GET**, **26 POST**, **3 PATCH**, **1 DELETE**;
- **0 security scheme OpenAPI**;
- **0 operazioni protette da un requisito di sicurezza dichiarato**.

Le API non identificano l'utente o il servizio chiamante. Non esiste una
authorization matrix applicata. `organization_id`, `operational_unit_id`,
identificatori numerici e campi `actor` possono essere forniti dal client o
sono sostituiti da identita sintetiche. Di conseguenza:

- un chiamante anonimo puo leggere dati operativi e personali;
- un chiamante anonimo puo invocare mutazioni Workforce, Fleet, Planning,
  Configuration, Confirmation e Publication;
- non e possibile dimostrare chi ha eseguito un'azione;
- non e possibile garantire isolamento tra organizzazioni o Operational Unit;
- gli audit esistenti non forniscono non-ripudio;
- l'endpoint di reset del workspace rappresenta una superficie distruttiva
  critica;
- la protezione replay e forte solo in alcuni contratti Runtime e non nel
  flusso API legacy completo.

La decisione PP-1 e pertanto:

```text
Architecture security foundations: PARTIAL
Private Beta con accesso di rete ristretto: POSSIBILE CON CONTROLLI COMPENSATIVI
Internet-facing Production: NO-GO
Runtime writer / Canary operativo: NO-GO
```

I primi obiettivi non sono aggiungere una login artigianale, ma introdurre un
confine affidabile:

1. identita verificata;
2. autorizzazione deny-by-default;
3. scope tenant derivato server-side;
4. actor non modificabile dal payload;
5. protezione delle azioni ad alto impatto;
6. audit security-grade;
7. limiti di consumo e hardening degli import;
8. evidenze automatizzate e test negative-path.

---

## 2. Principi Di Sicurezza

1. **Deny by default.** Ogni operazione e negata finche una policy esplicita non
   la autorizza.
2. **Un solo principal.** Identita, organizzazione, Operational Unit e ruoli
   derivano da una credenziale verificata, non dal payload.
3. **Least privilege.** Ogni ruolo umano o di servizio riceve il minimo insieme
   di azioni e scope.
4. **Separation of duties.** Creazione, conferma, pubblicazione, esecuzione,
   rollback e amministrazione non appartengono automaticamente allo stesso
   attore.
5. **Tenant isolation by construction.** Lo scope deve essere applicato in API,
   servizi, repository, query, cache, idempotenza, audit e metriche.
6. **Fail closed.** Errori di autenticazione, autorizzazione, audit, scope,
   versione o integrita bloccano le azioni ad alto impatto.
7. **No trust in client metadata.** `actor`, tenant, ruolo, IP inoltrato,
   Content-Type e identificatori client sono input non attendibili.
8. **Immutable evidence.** Le transizioni critiche producono evidenze
   append-only, correlate e protette da alterazione.
9. **Safe replay.** Ogni comando critico e idempotente e legato a actor, scope,
   payload, versione e finestra temporale.
10. **Security is a release gate.** Nessun punteggio aggregato compensa un FAIL
    su autenticazione, autorizzazione, tenant isolation o audit critico.

---

## 3. Riferimenti Normativi

Il piano usa i seguenti riferimenti come baseline, senza dichiarare conformita
formale:

- [OWASP API Security Top 10 2023](https://owasp.org/API-Security/editions/2023/en/0x11-t10/),
  in particolare BOLA, Broken Authentication, Broken Function Level
  Authorization e Unrestricted Resource Consumption;
- [OWASP Application Security Verification Standard](https://owasp.org/www-project-application-security-verification-standard/),
  come catalogo di requisiti verificabili;
- [OWASP Multi-Tenant Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Multi_Tenant_Security_Cheat_Sheet.html),
  per scope server-side, query tenant-aware e difesa in profondita;
- [OWASP File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html),
  per validazione, limiti decompressi e autorizzazione degli upload;
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html),
  per interaction ID, protezione dei log e dati da non registrare;
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html);
- [NIST SP 800-63B](https://pages.nist.gov/800-63-4/sp800-63b.html),
  per autenticazione, phishing resistance e replay resistance.

Target consigliato: OWASP ASVS Level 2 come baseline applicativa, con controlli
selezionati Level 3 per Publication, Authority, Execution, Rollback, audit e
amministrazione.

---

## 4. Threat Model

### 4.1 Asset Da Proteggere

| Asset | Valore di sicurezza | Impatto di compromissione |
| --- | --- | --- |
| Dati Workforce | Riservatezza, integrita | Esposizione dati personali, turni e assenze; modifica disponibilita |
| Dati Fleet | Riservatezza, integrita | Esposizione targhe, driver, documenti e stato mezzi |
| Planning | Integrita, disponibilita | Assegnazioni errate, interruzione operativa, decisioni non affidabili |
| Draft e Confirmation | Integrita, auditabilita | Approvazione di un piano non autorizzato |
| Publication | Integrita, non-ripudio | Disponibilita di un piano non approvato agli altri workspace |
| Authority, Intent, Attempt | Integrita, unicita | Futuro comando operativo non autorizzato o duplicato |
| Configuration | Integrita | Alterazione di stati, soglie, nomenclature e policy |
| Import ed export | Integrita, disponibilita | Parser abuse, dati malevoli, esfiltrazione, formula injection |
| Audit e history | Integrita, disponibilita | Perdita di attribuzione e ricostruzione degli eventi |
| Secret e credenziali | Riservatezza | Accesso a database, sessioni, deploy o servizi |
| PostgreSQL | Tutte | Compromissione trasversale di tenant e moduli |
| Disponibilita piattaforma | Disponibilita | Blocco del lavoro operativo giornaliero |

### 4.2 Attori Di Minaccia

| Attore | Capacita assunta | Obiettivo possibile |
| --- | --- | --- |
| Chiamante Internet anonimo | Conosce URL e OpenAPI | Lettura, modifica, reset, denial of service |
| Utente autenticato a basso privilegio futuro | Token valido, scope limitato | Escalation verticale |
| Utente di un altro tenant futuro | Token valido per tenant diverso | Accesso orizzontale a dati o comandi |
| Insider operativo | Accesso legittimo parziale | Bypass separation of duties, modifica audit |
| Browser o token compromesso | Sessione valida | Replay, azioni ad alto impatto |
| File malevolo | Controllo su XLSX/XLS/CSV | Resource exhaustion, parser exploit, formula injection |
| Servizio interno compromesso | Identita machine-to-machine | Creazione di comandi o accesso cross-scope |
| Operatore cloud o supply-chain attacker | Accesso a build/deploy/dipendenze | Esfiltrazione secret, immagine compromessa |
| Errore operativo | Configurazione errata | Demo/reset esposti, host trust eccessivo, perdita audit |

### 4.3 Trust Boundary

```text
[Browser / API Client]
        |
        | Internet, input non attendibile
        v
[Railway Edge / TLS / Proxy]
        |
        | Header forwarded, limiti, routing
        v
[FastAPI Boundary]
        |
        +----> [Static Frontend]
        |
        +----> [Upload Parser XLSX/XLS/CSV]
        |
        +----> [Core / Planning / Plugin / Runtime Services]
                         |
                         +----> [Configuration]
                         |
                         +----> [Audit / Logs]
                         |
                         v
                   [PostgreSQL Railway]

[Railway Environment / Build Supply Chain] ---> [Application Process]
```

Il confine mancante oggi e tra client e FastAPI: non esiste una trasformazione
verificata da richiesta anonima a `SecurityPrincipal`. Anche quando i contratti
interni contengono organization, Operational Unit, actor, versioni e
fingerprint, tali valori non sono ancora ancorati a una identita autorizzata.

### 4.4 Assunzioni Esplicite

- TLS pubblico e terminato dal provider; non verificato in PP-1.
- PostgreSQL di produzione e raggiungibile solo tramite configurazione Railway;
  ACL, TLS interno, backup e rotazione non sono stati verificati.
- Il Planning Engine legacy rimane l'unico writer operativo.
- Runtime, Shadow e Canary non producono effetti operativi.
- Production disabilita Demo Workspace salvo override esplicito.
- I file caricati vengono processati in memoria e non salvati in chiaro come
  file sorgente.
- Nessuna di queste assunzioni sostituisce un'evidenza di deploy.

---

## 5. Attack Surface

### 5.1 Superficie HTTP

| Area | Letture sensibili | Mutazioni sensibili |
| --- | --- | --- |
| Import | Preview e righe normalizzate | Import Planning e Fleet |
| Operations / Planning | Stato, assegnazioni, export, history | Analyze, generate, patch assignment, recalculate, event |
| Workforce | Persone, calendario, assenze, coverage, history, export | Import, membro, stato giorno |
| Fleet | Asset, driver, documenti, eventi, availability | Asset, availability, documenti, sync |
| Draft | Current e history | Create, update, save, restore, delete |
| Confirmation | Current, validation, history | Confirm |
| Publication | Current, validation, history | Publish |
| Configuration | Current e versions | Validate e create version |
| Runtime | Authority, Intent, Attempt, Output, Shadow, Canary | Nessuna scrittura Runtime pubblica corrente |
| Workspace / Demo | Stato | Reset, demo load/reset |
| Briefing | Stato giornaliero | Generate |

OpenAPI e Swagger UI sono esposti ai path FastAPI predefiniti. Non esiste un
security scheme e nessuna operazione dichiara requisiti di sicurezza.

### 5.2 Superficie File

- `.xlsx`, `.xls`, `.csv`;
- Content-Type controllato ma fornito dal client;
- `application/octet-stream` ammesso;
- file letto completamente prima del controllo applicativo della dimensione;
- XLSX e un contenitore compresso e richiede budget post-decompressione;
- formule non vengono eseguite dal codice, ma sono rilevate come metadata;
- gli export CSV non neutralizzano celle che iniziano con caratteri formula.

### 5.3 Superficie Dati

- tabelle legacy Planning e import prive di scope organization/Operational Unit;
- Fleet Registry globale;
- Workforce parzialmente scoped solo nei requirements;
- nuovi contratti Draft, Confirmation, Publication e Runtime scoped;
- molte query usano ID diretti senza ownership filter;
- nessuna Row Level Security PostgreSQL verificata;
- nessuna cifratura applicativa dei campi sensibili.

### 5.4 Superficie Deploy E Supply Chain

- image base `python:3.14-slim` referenziata con tag mutabile;
- dipendenze Python pinning esatto, controllo positivo;
- processo container non-root, controllo positivo;
- file `.env` esclusi dal build e dal repository, controllo positivo;
- nessuna evidenza di SBOM, firma immagine, SAST, SCA o secret scan CI;
- `forwarded_allow_ips="*"` e `TRUSTED_HOSTS` con fallback `"*"` richiedono
  configurazione Production rigorosa;
- startup applicativo esegue DDL senza migration coordinator verificato.

---

## 6. Valutazione Delle 20 Aree

| # | Area | Stato | Evidenza attuale | Requisito Production |
| ---: | --- | --- | --- | --- |
| 1 | Authentication | `FAIL` | Nessun principal, token, sessione o security scheme | IdP standard, MFA per ruoli privilegiati, sessioni revocabili |
| 2 | Authorization | `FAIL` | Nessuna policy su endpoint, azione o oggetto | Policy deny-by-default su action, resource e scope |
| 3 | Role Model | `FAIL` | Actor testuale, nessun ruolo applicato | Ruoli espliciti e separation of duties |
| 4 | Tenant Isolation | `FAIL` | Scope client-controlled e dati legacy globali | Tenant server-side, query scoped, RLS defense-in-depth |
| 5 | Replay Protection | `PARTIAL` | Forte su Execution Intent; assente sui comandi legacy | Idempotency e freshness su ogni comando critico |
| 6 | Authority Protection | `PARTIAL` | Versione, fencing e fail closed; nessuna identita service | Principal di servizio, policy scope e audit identity |
| 7 | Execution Protection | `PARTIAL` | Intent/Attempt senza effetto, controlli interni solidi | Autorizzazione service-to-service e lock certificato prima del writer |
| 8 | Publication Protection | `PARTIAL` | Version/fingerprint validati; POST pubblico | Publisher autorizzato, re-auth e separation of duties |
| 9 | Confirmation Protection | `PARTIAL` | Draft/readiness/fingerprint validati; POST pubblico | Approver autorizzato e diverso dal Planner |
| 10 | Audit Integrity | `PARTIAL` | History e audit locali; actor sintetico o client-controlled | Audit identity-bound, append-only, correlato, protetto |
| 11 | Secrets Management | `PARTIAL` | Env-only, ignore e scan corrente positivi | Inventory, rotation, CI scan, least privilege, incident process |
| 12 | Configuration Security | `PARTIAL` | Schema, versioni e secret-key guard; POST pubblico | Config Admin, approval, scope verificato, value scanning |
| 13 | API Security | `FAIL` | 66 operazioni non protette, docs pubblici, no rate limit | Gateway controls, auth, quotas, inventory e negative tests |
| 14 | Input Validation | `PARTIAL` | Pydantic, allowlist file e size limit | Limite pre-read, signature, budget decompressi e parser isolation |
| 15 | Privilege Escalation | `FAIL` | Non esistono livelli di privilegio applicati | Matrice ruoli e test BFLA |
| 16 | Horizontal Access | `FAIL` | ID e scope arbitrari, ownership non verificata | Repository sempre tenant-aware e test BOLA |
| 17 | Vertical Access | `FAIL` | Reset, config, confirm e publish invocabili anonimamente | Azioni privilegiate separate e re-auth |
| 18 | Injection Risks | `PARTIAL` | SQL parametrizzato; rischio CSV formula e parser input | Encoding export, fuzzing, allowlist query e SAST |
| 19 | Sensitive Data Exposure | `FAIL` | Workforce/Fleet/Planning leggibili senza identita | Data minimization, authorization, no-store e audit export |
| 20 | Operational Security | `PARTIAL` | Non-root, HSTS/CSP, prod fail-fast; manca runbook security | Monitoring, incident response, backup/restore, hardened deploy |

---

## 7. Risk Scoring

### 7.1 Scala

**Probabilita**

| Valore | Definizione |
| ---: | --- |
| 1 | Improbabile |
| 2 | Bassa |
| 3 | Media |
| 4 | Alta |
| 5 | Quasi certa nelle condizioni attuali |

**Impatto**

| Valore | Definizione |
| ---: | --- |
| 1 | Trascurabile |
| 2 | Limitato |
| 3 | Significativo |
| 4 | Alto |
| 5 | Critico operativo, legale o cross-tenant |

`Risk Score = Probabilita x Impatto`

| Score | Severita |
| ---: | --- |
| 20-25 | `CRITICAL` |
| 15-19 | `HIGH` |
| 8-14 | `MEDIUM` |
| 1-7 | `LOW` |

### 7.2 Effort

| Effort | Stima |
| --- | --- |
| `XS` | Meno di 1 giorno |
| `S` | 1-3 giorni |
| `M` | 4-10 giorni |
| `L` | 2-4 settimane |
| `XL` | Migrazione multi-sprint |

Le stime descrivono ordine di grandezza, non commitment.

---

## 8. Risk Matrix

| ID | Vulnerabilita / rischio | Prob. | Impatto | Score | Severita | Mitigazione primaria | Priorita | Effort |
| --- | --- | ---: | ---: | ---: | --- | --- | --- | --- |
| SEC-001 | Tutte le API operano senza autenticazione | 5 | 5 | 25 | `CRITICAL` | IdP standard, principal verificato, deny-by-default | P0 | L |
| SEC-002 | Nessuna authorization function-level o object-level | 5 | 5 | 25 | `CRITICAL` | Policy engine leggero su action, resource e scope | P0 | L |
| SEC-003 | `organization_id` e Operational Unit sono client-controlled | 5 | 5 | 25 | `CRITICAL` | Derivare tenant/scope dal principal e validare ogni override | P0 | L |
| SEC-004 | Tabelle legacy, Fleet e parte Workforce non sono tenant-scoped | 4 | 5 | 20 | `CRITICAL` | Migrazione schema, ownership obbligatoria, RLS e query scoped | P0 | XL |
| SEC-005 | Workspace reset distruttivo invocabile senza identita | 5 | 5 | 25 | `CRITICAL` | Disabilitare fuori ambiente autorizzato; break-glass con MFA e doppia conferma | P0 | S |
| SEC-006 | Planning, Confirmation e Publication mutabili anonimamente | 5 | 5 | 25 | `CRITICAL` | Ruoli Planner/Approver/Publisher, re-auth e separation of duties | P0 | L |
| SEC-007 | Actor fornito dal client o sostituito da `private-beta` | 5 | 4 | 20 | `CRITICAL` | Actor immutabile derivato dal principal o service identity | P0 | M |
| SEC-008 | Dati Workforce, Fleet e Planning leggibili anonimamente | 5 | 4 | 20 | `CRITICAL` | Autorizzazione read, minimizzazione payload e audit export | P0 | L |
| SEC-009 | Versioni Configuration creabili senza privilegio | 5 | 4 | 20 | `CRITICAL` | Config Admin scoped, approval e audit atomico | P0 | M |
| SEC-010 | Assenza di anti-replay/idempotenza nei comandi legacy | 4 | 4 | 16 | `HIGH` | Idempotency key legata a actor, scope, payload e versione | P1 | L |
| SEC-011 | Nessun rate limit o quota per endpoint/tenant | 4 | 4 | 16 | `HIGH` | Limiti edge e applicativi, quota upload/export, backpressure | P1 | M |
| SEC-012 | Upload letto in memoria prima del rifiuto per dimensione | 4 | 4 | 16 | `HIGH` | Streaming con limite hard e request limit al proxy | P1 | M |
| SEC-013 | Nessun budget post-decompressione o complessita workbook | 4 | 4 | 16 | `HIGH` | Limiti su bytes decompressi, sheet, righe, colonne e tempo CPU | P1 | M |
| SEC-014 | MIME permissivo e nessuna verifica signature file | 4 | 3 | 12 | `MEDIUM` | Magic/signature validation e coerenza extension/MIME/content | P1 | M |
| SEC-015 | Trusted host wildcard e proxy forwarded trust esteso di default | 4 | 4 | 16 | `HIGH` | Host allowlist obbligatoria e proxy trust limitato in Production | P0 | S |
| SEC-016 | Swagger/OpenAPI pubblici espongono inventario completo | 4 | 2 | 8 | `MEDIUM` | Disabilitare o proteggere docs in Production | P2 | XS |
| SEC-017 | Audit non identity-bound e non tamper-evident end-to-end | 5 | 4 | 20 | `CRITICAL` | Audit centralizzato, append-only, correlato e access-controlled | P0 | L |
| SEC-018 | Lock del workspace reset solo in-process | 3 | 5 | 15 | `HIGH` | Lock transazionale/distribuito e idempotenza scoped | P1 | M |
| SEC-019 | Filtro secret Configuration controlla il nome ma non il valore | 3 | 3 | 9 | `MEDIUM` | Schema allowlist, scanner valori e divieto strutturale di secret | P2 | S |
| SEC-020 | Export CSV vulnerabile a spreadsheet formula injection | 3 | 4 | 12 | `MEDIUM` | Neutralizzare celle `=`, `+`, `-`, `@`, tab e CR | P1 | S |
| SEC-021 | Nessuna RLS o constraint di ownership verificata | 4 | 5 | 20 | `CRITICAL` | Tenant key NOT NULL, FK composite, RLS defense-in-depth | P0 | XL |
| SEC-022 | Limiti DB/request timeout e pool non certificati | 3 | 4 | 12 | `MEDIUM` | Statement timeout, pool bounds, cancellation e circuit breaker | P1 | M |
| SEC-023 | Nessun request/correlation ID e security event pipeline | 4 | 4 | 16 | `HIGH` | Correlation middleware, eventi standard, alert e retention | P1 | M |
| SEC-024 | Demo load/reset esponibile per errore di configurazione | 3 | 4 | 12 | `MEDIUM` | Build/deploy guard e hard-disable Production | P1 | S |
| SEC-025 | Rotation, scadenza e least privilege dei secret non evidenziati | 3 | 4 | 12 | `MEDIUM` | Secret inventory, owner, rotazione, revoca e drill | P1 | M |
| SEC-026 | Nessun SBOM, SCA, firma immagine o attestazione build verificata | 3 | 4 | 12 | `MEDIUM` | CI supply-chain gate, digest base image, SBOM e signing | P1 | M |
| SEC-027 | Risposte API sensibili senza policy `no-store` | 3 | 3 | 9 | `MEDIUM` | Cache-Control per dati personali e operativi | P2 | S |
| SEC-028 | DDL all'avvio senza migration coordinator certificato | 3 | 4 | 12 | `MEDIUM` | Migrazioni versionate, lock schema ed expand/contract | P1 | L |
| SEC-029 | Nessuna suite completa auth/tenant/security e nessun pentest | 5 | 4 | 20 | `CRITICAL` | Negative tests, DAST, fuzzing e assessment indipendente | P0 | L |
| SEC-030 | Identificatori sequenziali facilitano enumerazione | 4 | 3 | 12 | `MEDIUM` | Ownership check obbligatorio; ID opachi dove opportuno | P1 | M |
| SEC-031 | Eccezioni server possono finire nei log cloud con dati interni | 2 | 4 | 8 | `MEDIUM` | Redaction, accesso log ristretto, retention e test leakage | P2 | S |
| SEC-032 | CSRF non predisposto per una futura autenticazione cookie | 3 | 4 | 12 | `MEDIUM` | SameSite, CSRF token e Origin check prima di usare cookie auth | P1 | M |

### 8.1 Interpretazione

- **13 rischi P0** bloccano la Production.
- I rischi P0 non sono accettabili tramite disclaimer.
- Gli ID opachi non sostituiscono l'ownership check.
- Fingerprint e fencing proteggono integrita e ordine, non identita o
  autorizzazione.
- L'assenza di un writer Runtime riduce l'impatto immediato di SEC-010, ma non
  rende sicure le mutazioni legacy gia esposte.

---

## 9. Controlli Positivi Gia Presenti

Questi controlli devono essere conservati:

1. `DEBUG=false` richiesto in Production.
2. `SECRET_KEY` con lunghezza minima e `DATABASE_URL` PostgreSQL obbligatori in
   Production.
3. CORS wildcard rifiutato in Production.
4. Header CSP, HSTS, frame deny, nosniff, referrer e permissions policy.
5. Risposte 500 generiche senza stack trace verso il client.
6. Container avviato con utente non-root.
7. File `.env` esclusi da Git e build; `.env.example` privo di valori reali.
8. Nessuna credenziale ad alta confidenza trovata dalla scansione euristica del
   working tree corrente.
9. Dipendenze Python con versioni esatte.
10. Query SQL osservate prevalentemente parametrizzate.
11. Pydantic e allowlist sui principali contratti HTTP.
12. Allowlist estensione/MIME e limite nominale sugli upload.
13. Formule Excel lette come dati/metadata, non eseguite come codice.
14. Versioning e fingerprint di Draft, Confirmation e Publication.
15. Authority con versioni e fencing monotoni.
16. Execution Intent con idempotency key scoped e verifica del payload.
17. Execution Attempt append-only e fail closed.
18. Planning Engine legacy ancora unico writer operativo.

Questa lista non deve essere interpretata come `PASS` Production. Sono
fondamenta utili che riducono il lavoro residuo.

---

## 10. Authentication Plan

### 10.1 Requisiti

- usare un Identity Provider standard OIDC/OAuth 2.1;
- non implementare password storage proprietario;
- validare issuer, audience, signature, expiration, not-before e token type;
- usare chiavi pubbliche con cache e rotazione sicura;
- token access short-lived e sessioni revocabili;
- MFA obbligatoria per Approver, Publisher, Config Admin, Platform Admin e
  break-glass;
- autenticazione phishing-resistant per i ruoli con potere operativo quando
  supportata dall'IdP;
- service identity distinta per ogni componente machine-to-machine;
- nessun secret condiviso tra ambienti;
- nessun `actor` accettato dal client;
- logout, revoca e disabilitazione utente con SLA definito;
- clock synchronization monitorata per evitare errori su scadenza e freshness.

### 10.2 Security Principal Minimo

Ogni richiesta autenticata deve produrre internamente:

| Campo | Origine attendibile |
| --- | --- |
| `subject_id` | Claim verificato IdP |
| `actor_type` | Human o service, definito dalla registration |
| `organization_id` | Membership server-side/claim autorizzato |
| `allowed_operational_units` | Entitlement server-side |
| `roles` | Directory/policy store verificato |
| `authentication_time` | Token/sessione |
| `authentication_strength` | AAL/MFA state |
| `session_id` | Sessione verificata, mai loggata in chiaro |
| `token_id` | Hash o riferimento per revoca/replay |

Claim non riconosciuti o scope incoerenti devono produrre `401` o `403` senza
fallback a `default`.

### 10.3 Re-authentication

Richiedere autenticazione recente e MFA per:

- conferma Planning;
- Publication;
- cambio Configuration con impatto operativo;
- reset workspace;
- authority switch futuro;
- execution o rollback futuri;
- export massivo di dati personali;
- gestione ruoli e tenant.

---

## 11. Authorization And Role Model

### 11.1 Modello

Il modello consigliato e RBAC con vincoli ABAC:

```text
Allow =
  authenticated
  AND role permits action
  AND organization matches
  AND operational_unit is allowed
  AND resource belongs to scope
  AND planning_date is within policy
  AND object state permits transition
  AND separation_of_duties passes
```

### 11.2 Ruoli Baseline

| Ruolo | Responsabilita | Divieti |
| --- | --- | --- |
| Viewer | Lettura scoped di Mission Control e snapshot | Nessuna mutazione |
| Importer | Preview e import scoped | Nessuna conferma/pubblicazione |
| Workforce Manager | Gestione Workforce scoped | Nessuna gestione Fleet o Planning approval |
| Fleet Manager | Gestione Fleet scoped | Nessuna gestione Workforce o Planning approval |
| Planner | Draft e Planning preparation | Non conferma il proprio Draft |
| Approver | Validation e Confirmation | Distinto dal Planner |
| Publisher | Publication | Distinto dall'Approver in Production |
| Runtime Operator | Osservazione e futuri intent autorizzati | Nessun authority switch |
| Config Admin | Proposta Configuration | Nessuna auto-approvazione critica |
| Security Auditor | Lettura audit/security evidence | Nessuna mutazione operativa |
| Platform Admin | Tenant, OU e recovery controllato | Break-glass non autonomo |
| Planning Executor Service | Futuro writer autorizzato | Non crea approval o Authority |

### 11.3 Matrice Endpoint

| Gruppo | Read | Write | Vincolo speciale |
| --- | --- | --- | --- |
| Health | Pubblico minimale | Nessuno | Nessun dettaglio infrastrutturale |
| OpenAPI/docs | Sviluppo o ruolo tecnico | Nessuno | Disabilitato o protetto in Production |
| Imports | Importer scoped | Importer scoped | Quota, audit, malware/parser policy |
| Workforce | Viewer/Workforce Manager | Workforce Manager | OU ownership |
| Fleet | Viewer/Fleet Manager | Fleet Manager | OU ownership |
| Planning legacy | Viewer/Planner | Planner | Versione e idempotenza |
| Draft | Planner/Approver | Planner | Actor e version expected |
| Confirmation | Planner/Approver | Approver | Non autore del Draft |
| Publication | Viewer/Publisher | Publisher | Non Approver; re-auth |
| Configuration | Viewer scoped | Config Admin | Approval per sezioni critiche |
| Runtime read | Runtime Operator/Auditor | Nessuno oggi | Scope e data operativa |
| Workspace reset | Nessuno ordinario | Platform Admin break-glass | MFA, motivo, doppia approvazione |
| Demo | Solo ambienti demo | Solo ambienti demo | Hard-disable Production |
| Export | Ruolo proprietario | Nessuno | Audit e data minimization |

---

## 12. Tenant Isolation Plan

### 12.1 Regola Centrale

`organization_id` non deve essere scelto dal client. L'Operational Unit non e
un tenant e non sostituisce l'organizzazione.

Il flusso target e:

```text
Verified token
  -> SecurityPrincipal
  -> TenantContext
  -> Authorization decision
  -> Scoped service command
  -> Scoped repository query
  -> Database tenant policy
  -> Tenant-aware audit
```

### 12.2 Requisiti Per Ogni Layer

**API**

- ignorare o rifiutare organization arbitrarie;
- consentire selezione OU solo tra gli entitlement del principal;
- non usare mai `default` come fallback di sicurezza;
- usare errori non enumerabili.

**Service**

- richiedere `TenantContext` per ogni read/write;
- vietare service method non scoped salvo funzioni platform esplicite;
- applicare separation of duties prima della transazione.

**Repository**

- tutte le query per ID includono organization e OU quando applicabile;
- insert con tenant key obbligatoria;
- update/delete verificano ownership nella stessa query;
- unique key e idempotency key includono tenant;
- history e audit mantengono lo scope originale.

**Database**

- `organization_id NOT NULL` sulle entita tenant-owned;
- foreign key composite o constraint equivalente;
- RLS PostgreSQL come difesa in profondita;
- ruolo applicativo senza `BYPASSRLS`;
- ruolo migration separato;
- backup, restore e export tenant-aware.

**Cache e file**

- cache key prefissata con tenant e OU;
- preview upload legata a principal e tenant;
- nessun artifact condiviso tramite fingerprint soltanto;
- export temporanei con scope e scadenza.

### 12.3 Migrazione Necessaria

La migrazione riguarda almeno:

- imports e normalized rows;
- analyses e operation snapshots;
- plannings, assignments, events e versions;
- Fleet assets, documents, events e sync metadata;
- Workforce members, statuses, changes e imports;
- briefing, demo e workspace state;
- configuration e nuovi contratti gia scoped, da collegare al principal;
- cache applicative e idempotency records.

Prima della migrazione, la piattaforma non deve dichiararsi multi-tenant.

---

## 13. Replay, Authority And Execution Protection

### 13.1 Controlli Gia Validi

- Authority versionata e fencing monotono;
- Execution Intent idempotente;
- riuso di idempotency key con payload diverso rifiutato;
- verifica scope, Publication, versione e fingerprint;
- Execution Attempt numerato, append-only e fail closed;
- Runtime osservativo senza writer operativo.

### 13.2 Gap

- actor non autenticato;
- idempotency non estesa alle mutazioni legacy;
- nessun binding tra token/sessione e comando;
- nessuna freshness window generale;
- nessun rate limit per actor/tenant/action;
- lock distribuito non certificato;
- nessun revoke path security-grade;
- audit end-to-end non atomico e non correlato;
- nessun test contro replay concorrente attraverso piu repliche Production.

### 13.3 Contratto Anti-Replay Target

Ogni comando critico deve legare:

```text
idempotency_key
actor_id
organization_id
operational_unit_id
planning_date
action
resource_id
expected_version
payload_fingerprint
authority_decision_id
fencing_token
issued_at
expires_at
```

La risposta a un replay identico puo restituire lo stesso risultato. Un replay
con payload, actor, scope o versione differente deve essere rifiutato e
auditato come evento security.

### 13.4 Protezione Per Fase

| Fase | Controllo identita | Controllo integrita | Controllo autorizzazione |
| --- | --- | --- | --- |
| Draft | Planner autenticato | expected version + fingerprint | Scope e ownership |
| Confirmation | Approver con re-auth | Draft/version/fingerprint | Separation from Planner |
| Publication | Publisher con re-auth | Confirmation/version/fingerprint | Separation from Approver |
| Authority | Security/Release authority | Version + fencing | Policy e doppia approvazione |
| Intent | Service/human principal | Idempotency + payload hash | WRITE_ALLOWED scoped |
| Attempt | Planning Executor service | Attempt number + lock token | Intent READY scoped |
| Execution futura | Dedicated writer identity | Transaction + outcome fingerprint | Canary/production policy |
| Rollback futuro | Rollback Approver | Idempotent rollback intent | Separation from writer |

---

## 14. Audit Integrity Plan

### 14.1 Audit Event Minimo

Ogni azione rilevante deve registrare:

- `event_id`;
- `occurred_at` in UTC;
- `request_id` e `trace_id`;
- actor subject e actor type;
- authentication method e strength;
- organization e Operational Unit;
- action;
- resource type, ID e versione;
- planning date;
- previous e resulting fingerprint quando applicabile;
- authority, intent, attempt, confirmation e publication ID quando presenti;
- idempotency key hash;
- decision `ALLOW` o `DENY`;
- outcome;
- reason code stabile;
- source service e release version;
- client/network metadata minimizzati;
- security classification.

### 14.2 Integrita

- append-only per gli eventi critici;
- nessun update/delete ordinario;
- scrittura atomica con la transizione o transactional outbox;
- export su storage con retention lock quando richiesto;
- hash chaining o firma come controllo aggiuntivo, non come sostituto
  dell'access control;
- accesso audit separato da accesso operativo;
- alert su gap di sequenza, tampering, write failure e clock anomaly;
- backup e restore testati;
- retention differenziata per security, operations e dati personali.

### 14.3 Fail Closed

Confirmation, Publication, Authority switch, Execution, Rollback, Configuration
critica e reset devono fallire se l'evidenza audit obbligatoria non puo essere
registrata. Le letture ordinarie possono degradare solo secondo policy
esplicita.

### 14.4 Privacy Dei Log

Non registrare:

- password;
- access/refresh token;
- cookie o session ID in chiaro;
- connection string;
- secret o chiavi;
- file Excel completi;
- note personali complete;
- payload Workforce/Fleet non necessari;
- stack trace nel client.

---

## 15. Secrets Management Plan

### 15.1 Stato Corrente

Controlli positivi:

- secret previsti tramite variabili d'ambiente;
- `.env` esclusi da repository e immagine;
- `.env.example` usa placeholder;
- nessun secret ad alta confidenza trovato nella scansione euristica del
  working tree corrente;
- Production richiede `SECRET_KEY` e PostgreSQL.

Limiti:

- lo scan corrente non prova che la cronologia remota sia pulita;
- non prova che Railway non contenga variabili obsolete;
- non prova rotation, owner, expiration o least privilege;
- `SECRET_KEY` e richiesto ma non e ancora usato da un sistema di sessione o
  firma applicativa, quindi non deve essere presentato come controllo auth;
- non esiste evidenza CI di secret scanning bloccante.

### 15.2 Requisiti

Per ogni secret:

| Campo inventory | Obbligatorio |
| --- | --- |
| Nome logico | Si |
| Owner | Si |
| Ambiente | Si |
| Consumer | Si |
| Scope/privilegi | Si |
| Data creazione | Si |
| Data ultima rotazione | Si |
| Scadenza/SLA | Si |
| Procedura revoca | Si |
| Procedura incident | Si |

Regole:

- credenziali diverse per development, test, staging e Production;
- database user con privilegi minimi;
- credenziali migration separate da runtime;
- nessun secret in Configuration Engine;
- secret scan su working tree, commit, artifact e container;
- rotazione periodica e immediata dopo sospetta esposizione;
- redaction log obbligatoria;
- deploy fail closed se manca un secret richiesto;
- accesso alle variabili Railway limitato e auditato;
- nessun secret condiviso tra servizi futuri.

---

## 16. Configuration Security Plan

Il Configuration Engine e una superficie amministrativa, non un semplice
endpoint dati.

Requisiti:

- lettura scoped;
- scrittura solo Config Admin;
- approvazione distinta per sezioni ad alto impatto;
- `created_by` derivato dal principal;
- schema allowlist per sezione e tipo;
- dimensioni massime per sezioni, liste e stringhe;
- nessun secret nei nomi o nei valori;
- URL e riferimenti esterni validati;
- versione immutabile;
- fingerprint della revisione;
- effective date e rollback controllato;
- audit atomico;
- fallback sicuro esplicito e monitorato;
- nessun fallback cross-tenant;
- diff leggibile prima dell'attivazione;
- protezione da rollback a versione vulnerabile;
- test di compatibilita prima dell'activation.

Il controllo corrente sui nomi `api_key`, `credential`, `password`, `secret` e
`token` e utile ma insufficiente: un secret puo essere inserito in un valore con
un nome neutro. La policy Production deve vietare strutturalmente i secret nel
Configuration Engine.

---

## 17. API Security Plan

### 17.1 Edge Controls

- TLS only e redirect HTTPS;
- host allowlist esatta;
- proxy trusted list limitata al provider;
- body size hard limit prima dell'applicazione;
- rate limit per IP non autenticato e per principal/tenant autenticato;
- timeout request e upstream;
- connection/concurrency limit;
- protezione bot/automation per flussi sensibili;
- docs/OpenAPI protetti o disabilitati;
- health minimale senza versione, DB URL o dettagli interni;
- log di `401`, `403`, `409`, `429` e pattern anomali;
- nessuna fiducia automatica negli header forwarded.

### 17.2 Application Controls

- autenticazione globale con allowlist delle sole route pubbliche;
- authorization esplicita per endpoint;
- object-level ownership check;
- property-level authorization per campi modificabili;
- modelli request separati da modelli persistence;
- limiti Pydantic su tutte le collection e stringhe;
- pagination e maximum page size;
- idempotency per comandi;
- optimistic concurrency con expected version;
- media type esatto;
- error code stabile senza differenze che facilitino enumeration;
- `Cache-Control: no-store` sui dati sensibili;
- CORS limitato alle origin necessarie;
- CSRF prima di introdurre autenticazione cookie.

### 17.3 API Inventory

Mantenere un inventario machine-readable con:

- endpoint;
- owner;
- public/internal;
- read/write;
- dati trattati;
- role;
- organization/OU scope;
- rate limit;
- idempotency;
- audit requirement;
- retention;
- deprecation date;
- test di authorization associato.

---

## 18. Input Validation And Injection Plan

### 18.1 Upload

Ordine obbligatorio:

1. autenticare e autorizzare uploader;
2. applicare quota e content-length edge;
3. leggere in streaming con limite hard;
4. validare filename length ed extension;
5. validare MIME solo come segnale;
6. verificare signature e struttura;
7. rifiutare macro e contenuti non ammessi;
8. applicare budget decompressi;
9. applicare limiti sheet/row/column/cell/formula/merged-range;
10. eseguire parser con timeout e memory budget;
11. validare mapping e cardinalita;
12. produrre preview;
13. confermare tramite fingerprint scoped a principal/tenant;
14. auditare import, rifiuto e consumo risorse.

Nessun file parziale deve produrre dati persistiti.

### 18.2 CSV Formula Injection

Ogni export destinato a spreadsheet deve neutralizzare valori che, dopo
eventuali spazi iniziali, cominciano con:

- `=`
- `+`
- `-`
- `@`
- tab
- carriage return

La neutralizzazione deve essere applicata centralmente a Planning, Workforce,
Fleet e futuri export, con test round-trip.

### 18.3 SQL E Query

- mantenere query parametrizzate;
- permettere nomi tabella/colonna dinamici solo da costanti allowlist;
- vietare concatenazione di input in SQL;
- limitare query complesse e intervalli data;
- statement timeout;
- least-privilege DB role;
- SAST e test injection.

### 18.4 Frontend E Output

- encoding context-aware di ogni dato importato;
- nessun `innerHTML` con input non trusted;
- mantenere CSP senza `unsafe-inline` e `unsafe-eval`;
- validare URL;
- non mostrare stack trace o dettagli repository;
- download con filename applicativo sicuro.

---

## 19. Operational Security

### 19.1 Deploy

- ambienti separati;
- account e database separati;
- deploy da artifact immutabile;
- image base referenziata per digest;
- SBOM e firma artifact;
- branch protection e review obbligatoria;
- CI con SAST, SCA, secret scan, test security e policy gate;
- deploy `expand -> observe -> verify -> enable -> contract`;
- migration job singleton;
- rollback artifact e schema provato;
- nessuna modifica manuale non auditata in Production.

### 19.2 Database

- TLS verificato;
- credential runtime least privilege;
- credential migration separata;
- statement, lock e idle transaction timeout;
- pool con limiti;
- backup automatici e restore drill;
- point-in-time recovery secondo RPO/RTO;
- RLS e tenant tests;
- audit accessi amministrativi;
- rotazione credenziali;
- replica/deploy overlap testati.

### 19.3 Incident Response

Runbook minimi:

- token o account compromesso;
- database credential leak;
- cross-tenant data exposure;
- publication non autorizzata;
- actor spoofing;
- audit unavailable o tampered;
- malicious workbook;
- denial of service;
- supply-chain compromise;
- reset workspace non autorizzato.

Ogni runbook definisce owner, detection, containment, revoca, evidenze,
comunicazioni, recovery e post-incident review.

### 19.4 Break-Glass

- disabilitato per default;
- MFA;
- due approvatori;
- scope e durata minimi;
- motivo obbligatorio;
- alert immediato;
- sessione registrata;
- revoca automatica;
- review entro un SLA definito.

---

## 20. Quick Wins

Questi interventi riducono l'esposizione ma non sostituiscono
Authentication/Tenant Isolation.

### P0 - Prima Di Ogni Esposizione Non Controllata

| Azione | Rischi ridotti | Effort | Evidenza di chiusura |
| --- | --- | --- | --- |
| Limitare accesso Private Beta a utenti/rete approvati | SEC-001, 002, 008 | S | Test anonimo negato |
| Disabilitare hard reset e Demo in Production | SEC-005, 024 | S | Config test + richiesta negata |
| Impostare `TRUSTED_HOSTS` esatto | SEC-015 | XS | Test host invalido |
| Limitare trusted forwarded proxy | SEC-015 | S | Header spoof test |
| Proteggere/disabilitare docs e OpenAPI | SEC-016 | XS | Accesso anonimo negato |
| Applicare limite body all'edge | SEC-011, 012 | S | Upload oversized rifiutato pre-app |
| Applicare `no-store` ai dati sensibili | SEC-027 | S | Header test |
| Neutralizzare CSV formula | SEC-020 | S | Test payload formula |
| Verificare Demo flag e secret mancanti al deploy | SEC-024, 025 | S | Deploy policy test |

### P1 - Fondazione Production

| Azione | Rischi ridotti | Effort | Evidenza di chiusura |
| --- | --- | --- | --- |
| Scegliere IdP e creare SecurityPrincipal | SEC-001, 007 | L | Authentication contract tests |
| Definire e applicare authorization matrix | SEC-002, 006, 009 | L | Negative role matrix |
| Derivare tenant e OU server-side | SEC-003 | L | Tampered scope denied |
| Actor derivato dal principal | SEC-007, 017 | M | Audit actor immutable test |
| Correlation ID e security logging | SEC-017, 023 | M | Trace completo per comando |
| Streaming upload e workbook budgets | SEC-012, 013, 014 | M | Zip bomb/resource tests |
| Rate limit e quota tenant | SEC-011 | M | `429` e metriche |
| Idempotenza per comandi legacy critici | SEC-010 | L | Replay/concurrency tests |

---

## 21. Long-Term Improvements

### 21.1 30-90 Giorni

- migrazione tenant-aware di tutte le entita;
- RLS PostgreSQL;
- service identities separate;
- audit centralizzato e transactional outbox;
- separation of duties completa;
- security event alerting;
- DAST e fuzzing import;
- SCA, SBOM e image signing;
- database hardening e restore drill;
- CI authorization matrix;
- incident runbook e tabletop exercise.

### 21.2 90+ Giorni

- phishing-resistant MFA per ruoli critici;
- policy-as-code con decision log;
- tamper-evident audit export;
- per-tenant encryption strategy dove richiesto;
- continuous access evaluation;
- anomaly detection su export, reset, confirmation e publication;
- JIT privileged access;
- break-glass certificato;
- red-team / independent penetration test;
- security chaos su IdP, audit, DB, rate limit e revoca;
- formalizzazione ASVS Level 2 con evidenze Level 3 selezionate.

---

## 22. Production Requirements

Operations Engine puo entrare in Production solo se tutti i requisiti
obbligatori seguenti sono `PASS`.

### 22.1 Identity

- [ ] IdP standard configurato.
- [ ] Tutte le API non pubbliche richiedono autenticazione.
- [ ] MFA per ruoli privilegiati.
- [ ] Service identities distinte.
- [ ] Revoca e offboarding testati.

### 22.2 Authorization

- [ ] Matrice role/action/resource approvata.
- [ ] Deny-by-default.
- [ ] Object e property authorization testate.
- [ ] Separation of duties per Draft/Confirm/Publish.
- [ ] Re-auth per azioni critiche.

### 22.3 Tenant

- [ ] Tenant derivato dal principal.
- [ ] OU verificata contro entitlement.
- [ ] Tutte le tabelle tenant-owned scoped.
- [ ] Tutte le query per ID scoped.
- [ ] RLS o controllo DB equivalente verificato.
- [ ] Cache, idempotenza, audit ed export tenant-aware.
- [ ] Test cross-tenant positivi e negativi.

### 22.4 Integrity And Replay

- [ ] Versione e fingerprint coerenti.
- [ ] Idempotenza sui comandi critici.
- [ ] Replay differente rifiutato.
- [ ] Fencing testato su piu repliche.
- [ ] Lock e concorrenza certificati.
- [ ] Nessuna doppia Confirmation, Publication o Execution.

### 22.5 Audit

- [ ] Actor identity-bound.
- [ ] Request/trace correlation end-to-end.
- [ ] Audit append-only e protetto.
- [ ] Audit failure fail closed sulle transizioni critiche.
- [ ] Retention e access control verificati.
- [ ] Tampering e log gap alertati.

### 22.6 API And Input

- [ ] Rate limit, quota e timeout.
- [ ] Request size pre-app.
- [ ] Upload signature e decompression budgets.
- [ ] CSV formula injection mitigata.
- [ ] Docs/OpenAPI protetti.
- [ ] Dati sensibili con `no-store`.
- [ ] Fuzzing e negative tests superati.

### 22.7 Secrets And Supply Chain

- [ ] Secret inventory con owner e rotation.
- [ ] Nessun secret nel repository, history, artifact o image.
- [ ] DB credential least privilege.
- [ ] SAST, SCA e secret scan bloccanti.
- [ ] SBOM e image signature.
- [ ] Base image per digest.

### 22.8 Operations

- [ ] Backup e restore drill.
- [ ] Incident response runbook.
- [ ] Alerting security.
- [ ] Migration/deploy rollback provato.
- [ ] Penetration test indipendente senza issue Critical/High aperte.
- [ ] Security sign-off.

Qualunque FAIL nelle sezioni Identity, Authorization, Tenant, Audit o Integrity
produce automaticamente `NO-GO`.

---

## 23. Security Testing Strategy

### 23.1 Unit E Contract

- token invalidi, scaduti, issuer/audience errati;
- principal senza tenant o ruolo;
- policy deny-by-default;
- actor non sovrascrivibile;
- scope OU non autorizzato;
- separation of duties;
- idempotency stessa key/stesso payload;
- idempotency stessa key/payload diverso;
- stale version e stale fencing;
- audit event completo e redatto;
- Configuration secret/value policy;
- CSV formula neutralization;
- workbook complexity budget.

### 23.2 Integration

- ogni endpoint con anonimo, ruolo insufficiente e ruolo valido;
- BOLA su ogni identificatore;
- cross-tenant read/write/export;
- mass assignment;
- concurrent confirm/publish/reset;
- replay tra repliche;
- audit DB unavailable;
- IdP/JWKS unavailable;
- DB timeout e transaction failure;
- oversized/compressed workbook;
- malicious filename e content-type spoof;
- cache e preview cross-tenant;
- logout/revocation.

### 23.3 Security Tooling

- SAST;
- dependency/SCA scan;
- secret scan su history e artifact;
- container scan;
- SBOM;
- DAST su staging;
- API fuzzing da OpenAPI;
- IaC/deploy configuration scan;
- independent penetration test.

### 23.4 Evidence

Ogni test security deve registrare:

- release e commit;
- ambiente;
- config fingerprint;
- test case;
- expected e actual;
- timestamp;
- owner;
- artifact;
- issue associata;
- approvazione.

---

## 24. Security Readiness Score

### 24.1 Metodo

Lo score misura la maturita dei controlli osservabili nel repository. Non
sostituisce i gate.

| Dimensione | Punteggio | Massimo | Evidenza principale |
| --- | ---: | ---: | --- |
| Authentication | 0 | 12 | Nessun principal o security scheme |
| Authorization e Role Model | 0 | 14 | Nessuna policy applicata |
| Tenant Isolation | 1 | 14 | Nuovi contratti scoped, dati legacy non scoped |
| Runtime Integrity e Replay | 8 | 10 | Fingerprint, versioning, fencing, idempotency Intent |
| Data Protection e Audit | 3 | 10 | History presente, identity binding assente |
| API e Input Security | 5 | 10 | Pydantic/header/allowlist; rate e resource control assenti |
| Secrets e Configuration | 6 | 10 | Env-only e prod checks; lifecycle non certificato |
| Operational e Deployment Security | 4 | 10 | Non-root/HSTS; deploy security evidence assente |
| Observability e Incident Response | 1 | 5 | Logging base, nessuna security pipeline |
| Security Testing e Governance | 2 | 5 | Test Runtime integrity; auth/tenant/pentest assenti |
| **Totale** | **30** | **100** | **Non Production Ready** |

### 24.2 Interpretazione

| Score | Maturita |
| ---: | --- |
| 0-24 | Non controllata |
| 25-44 | Fondazioni parziali |
| 45-64 | Controllata, non certificata |
| 65-79 | Candidate Production |
| 80-89 | Production Ready con gate PASS |
| 90-100 | Enterprise security maturity |

Stato attuale:

```text
30/100 - FONDAZIONI PARZIALI
Security Gate - FAIL
Production - NO-GO
```

Lo score e superiore a zero grazie ai controlli di integrita Runtime, alla
configurazione fail-fast, agli header, al container non-root e alla gestione
env-only. Resta basso perche identita, autorizzazione e tenant isolation sono
controlli moltiplicatori: se assenti, gli altri controlli non impediscono a un
chiamante non autorizzato di raggiungere dati e funzioni.

---

## 25. Gap Aperti

### 25.1 Critici

1. Nessuna autenticazione.
2. Nessuna autorizzazione.
3. Nessun role model applicato.
4. Nessuna tenant isolation end-to-end.
5. Reset workspace anonimo.
6. Confirmation, Publication e Configuration write anonimi.
7. Actor non identity-bound.
8. Dati personali e operativi leggibili senza controllo.
9. Audit non security-grade.
10. Nessuna suite auth/tenant e nessun pentest.

### 25.2 Importanti

1. Replay protection non estesa al legacy.
2. Rate limit e quote assenti.
3. Upload size verificata dopo lettura completa.
4. Nessun decompression/complexity budget.
5. CSV formula injection.
6. Proxy/host trust da irrigidire.
7. Security observability assente.
8. Supply-chain evidence assente.
9. Database hardening non certificato.
10. Migration process non certificato.

### 25.3 Futuri

1. Execution Runtime authentication.
2. Writer service identity.
3. Canary cohort authorization.
4. Rollback approval e break-glass.
5. Continuous access evaluation.
6. Per-tenant cryptographic isolation.
7. Enterprise compliance mapping.

---

## 26. Priorita Di Esecuzione

### Security Phase S0 - Containment

- restringere accesso Private Beta;
- proteggere reset/demo/docs;
- host/proxy hardening;
- request size edge;
- no-store;
- CSV neutralization.

**Exit:** nessuna funzione distruttiva o dati sensibili esposti anonimamente
fuori dal gruppo beta autorizzato.

### Security Phase S1 - Identity

- IdP;
- SecurityPrincipal;
- actor identity-bound;
- authentication globale;
- MFA e revoca.

**Exit:** ogni richiesta non pubblica possiede una identita verificabile.

### Security Phase S2 - Authorization

- role model;
- authorization matrix;
- separation of duties;
- re-auth;
- negative tests.

**Exit:** ogni funzione e oggetto applica deny-by-default.

### Security Phase S3 - Tenant Isolation

- data model migration;
- scoped repositories;
- RLS;
- cache/audit/idempotency scoped;
- BOLA suite.

**Exit:** nessun read/write cross-tenant nei test applicativi e DB.

### Security Phase S4 - Integrity And Audit

- idempotenza legacy;
- audit centralizzato;
- correlation;
- security alerting;
- fail-closed critical actions.

**Exit:** ogni transizione critica e attribuibile, ricostruibile e replay-safe.

### Security Phase S5 - Production Certification

- security tooling CI;
- DAST/fuzz/load;
- failure injection;
- backup/restore;
- incident exercise;
- independent pentest;
- Security sign-off.

**Exit:** tutte le checklist Production `PASS`, nessun Critical/High aperto.

---

## 27. Raccomandazioni Finali

1. Non costruire una login locale temporanea destinata a diventare definitiva.
   Scegliere un IdP standard e mantenere l'applicazione come relying party.
2. Non aggiungere ruoli senza tenant context. Authorization e tenant isolation
   devono essere progettate insieme.
3. Non usare `organization_id` dal payload come prova di appartenenza.
4. Non considerare `actor`, fingerprint o idempotency key come autenticazione.
5. Conservare i controlli Runtime gia esistenti e collegarli in futuro a
   principal e policy, senza riscriverli.
6. Trattare reset, Configuration, Confirmation e Publication come azioni
   privilegiate.
7. Completare la migrazione tenant prima di dichiarare multi-tenancy.
8. Rendere l'audit parte della transazione, non un log accessorio.
9. Applicare limiti di risorsa prima del parser.
10. Bloccare la promozione Production finche Security Gate resta `FAIL`.

---

## 28. Decisione PP-1

### Decisione

```text
SECURITY READINESS: 30/100
PRODUCTION SECURITY GATE: FAIL
PRIVATE BETA: SOLO CON ACCESSO RISTRETTO E CONTROLLI COMPENSATIVI
RUNTIME WRITER: NON AUTORIZZATO
LEGACY RETIREMENT: NON AUTORIZZATO
```

### Motivazione

Operations Engine possiede controlli interni di integrita promettenti, ma oggi
non puo distinguere un operatore autorizzato da un chiamante anonimo, non puo
dimostrare l'appartenenza a organization/Operational Unit e non puo attribuire
in modo affidabile le azioni critiche. Questi gap prevalgono sui controlli
positivi.

### Condizione Di Riesame

Il Security Gate puo essere rivalutato quando saranno disponibili evidenze
firmate per:

- Authentication;
- authorization matrix;
- tenant isolation;
- actor identity;
- audit integrity;
- replay/idempotency end-to-end;
- resource limits;
- security testing;
- operational runbook;
- penetration test.

---

## 29. Dichiarazione Di Non Modifica

PP-1 ha prodotto esclusivamente questo documento.

- Nessun codice applicativo modificato.
- Nessun endpoint modificato o aggiunto.
- Nessun frontend modificato.
- Nessun database o schema modificato.
- Nessun Planning Engine modificato.
- Nessun Runtime modificato.
- Nessun algoritmo modificato.
- Nessun test creato o modificato.
- Nessun commit eseguito.
- Nessun push eseguito.
- Nessun deploy eseguito.
