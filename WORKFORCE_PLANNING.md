# Workforce Planning v1

## Scopo

Workforce Planning e il plugin che descrive disponibilita, turni, assenze,
contratti e copertura delle risorse umane. Risponde alla domanda: quali
risorse sono disponibili in una data, con quali capability e vincoli?

Non genera Assignment, non sostituisce il Planning operativo giornaliero e
non implementa paghe, presenze fiscali o funzioni da consulente del lavoro.
Il Planning Engine resta l'unico responsabile delle assegnazioni operative.

Excel e un ponte: serve per l'import iniziale e per l'export compatibile. Una
volta confermati, i dati vengono gestiti dal plugin e non dipendono dal file
come fonte operativa primaria.

## Confini architetturali

Il codice vive in `backend/app/plugins/workforce/`:

- `domain`: contratti neutrali e tipizzati;
- `application`: use case, validazione, copertura e contratti Core;
- `infrastructure`: schema e repository SQLite/PostgreSQL compatibili;
- `interfaces`: API versionate e schemi HTTP;
- `importer`: interpretazione multi-sheet del workbook;
- `bootstrap.py`: feature flag e registrazione del router.

Il dominio non importa Adapter, router o repository. Il plugin pubblica
`HumanResource`, `ResourceAvailability`, capability, time window e
Operational Unit. Non importa conoscenza Amazon e non crea Assignment.

## Modelli

- `WorkforceMember`: identita, ruolo, contratto, ore, capability e fonte.
- `WorkforceDayStatus`: stato giornaliero, availability, turno, orari e note.
- `WorkforceRequirement`: fabbisogno osservato o configurato per data e unita.
- `WorkforceCoverage`: required, available, scheduled, unavailable e margin.
- `WorkforceChange`: audit append-only di import e modifiche manuali.
- `WorkforceImportPreview`: fogli, mapping, matrice, anomalie e conteggi.

Gli status canonici sono configurabili. I default sicuri includono
`available`, `scheduled`, `rest`, `holiday`, `sickness`, `leave`,
`unavailable` e `unknown`. I codici esterni sono tradotti dalla sezione
`workforce_statuses` del Configuration Engine.

## Import multi-sheet

Il flusso e:

```text
Workbook -> Profiler -> target workforce -> interpretazione multi-sheet
         -> preview -> conferma fingerprint -> persistenza Workforce
```

Ogni foglio viene classificato come `schedule`, `members`, `contracts`,
`requirements` oppure `ignored`. Il parser riconosce sia tabelle verticali
sia matrici risorsa per giorno. Le colonne sono marcate `recognized`,
`inferred`, `needs_confirmation` o `ignored`.

Se manca un identificativo esplicito, l'identita sorgente e un hash stabile
del nome normalizzato; l'ordine dei token non crea un duplicato. Il valore
originale non compare nell'identificativo. Campi non mappati, inclusi
identificativi personali non necessari, non vengono persistiti.

La preview mostra tipo, fogli usati, responsabilita, persone, intervallo,
codici turno, contratti, assenze, righe escluse, anomalie, colonne da
confermare e una matrice limitata. Non replica l'intera larghezza del file.

## Calendario e modifiche

La pagina Workforce offre viste giorno, settimana e persona, riepilogo,
copertura, assenze, contratti, modifiche, import ed export. Su mobile la vista
usa un flusso verticale e mantiene le tabelle in contenitori scorrevoli.

Stato giornaliero, turno, note, capability e dati contrattuali v1 sono
modificabili nell'app. Ogni modifica viene validata e aggiunge un
`WorkforceChange` con before, after, actor, reason, source e timestamp. La
provenienza importata non viene sovrascritta silenziosamente.

## Copertura

La copertura usa esclusivamente dati disponibili:

```text
margin = available - required
```

Espone risorse richieste, disponibili, programmate, indisponibili, margine,
stato e capability mancanti. Se il fabbisogno non esiste, `required` e
`margin` restano null e lo stato e `requirement_unavailable`; il plugin non
inventa un valore.

## Export

`GET /api/plugins/workforce/v1/export?section=...` produce CSV per calendario,
members, coverage o changes. L'export e normalizzato e operativo; non tenta di
ricostruire colori, formule o layout del workbook sorgente.

## API

- `GET /api/plugins/workforce/v1/status`
- `GET /api/plugins/workforce/v1/members`
- `PATCH /api/plugins/workforce/v1/members/{member_id}`
- `GET /api/plugins/workforce/v1/calendar`
- `GET /api/plugins/workforce/v1/coverage`
- `GET /api/plugins/workforce/v1/changes`
- `POST /api/plugins/workforce/v1/import/preview`
- `POST /api/plugins/workforce/v1/import`
- `POST /api/plugins/workforce/v1/day-status`
- `PATCH /api/plugins/workforce/v1/day-status/{status_id}`
- `GET /api/plugins/workforce/v1/contracts/core`
- `GET /api/plugins/workforce/v1/export`

Il plugin e disabilitato se `WORKFORCE_PLUGIN_ENABLED` non e impostata. Su
Railway abilitarlo esplicitamente con `WORKFORCE_PLUGIN_ENABLED=true`.

## Workspace, idempotenza e privacy

- In `EMPTY` un import confermato porta il workspace a `PRODUCTION`.
- In `DEMO` ogni scrittura reale restituisce 409
  `DEMO_WORKSPACE_RESET_REQUIRED`.
- In `PRODUCTION` sono ammessi aggiornamenti incrementali.
- Il reset elimina import, membri, status, requirements e audit Workforce,
  ma preserva Configuration Engine, mapping, nomenclature e policy.
- Il fingerprint SHA-256 rende idempotente lo stesso workbook.
- Un workbook aggiornato applica soltanto i diff e conserva l'audit.
- Il file originale non viene salvato; restano nome sorgente, fingerprint,
  mapping e record normalizzati necessari.

I file reali sono ammessi soltanto per QA locale in lettura e sono esclusi da
Git. Fixture, documentazione, log e screenshot usano esclusivamente dati
sintetici.

## Limiti v1

- nessun editor completo di fabbisogno o workflow;
- nessuna gestione payroll, cedolini o presenze legali;
- nessuna ricostruzione pixel-perfect dell'Excel;
- nessuna notifica automatica;
- nessuna Assignment creata dal plugin;
- nessun matching probabilistico di persone con identita ambigua.

