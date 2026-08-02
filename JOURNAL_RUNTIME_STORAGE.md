# Journal runtime storage

Operations Engine salva nel database esclusivamente chiavi relative dei media Journal. La root fisica è risolta dal provider runtime condiviso con le primitive locali dell'Attachment Engine; repository, API e regole dei due domini restano separati.

## Locale

Senza configurazione la root è `backend/data`. Per usare una posizione esplicita:

```text
RUNTIME_STORAGE_ROOT=C:/operations-engine-data
REQUIRE_PERSISTENT_STORAGE=false
```

All'avvio l'applicazione crea e verifica la root. Con `REQUIRE_PERSISTENT_STORAGE=true` l'avvio viene bloccato se la variabile manca o la root non è scrivibile.

Nel container l'entrypoint prepara esclusivamente `/data` oppure la root locale `/app/backend/data`, crea `journal_media` e `attachments` con modalità `0770` e ownership `operations:operations`, quindi abbandona i privilegi con `gosu`. Uvicorn non viene mai eseguito come root.

## Railway

1. Aprire il progetto Railway e il servizio web di Operations Engine.
2. Mantenere il volume collegato al servizio web.
3. Impostare il mount path su `/data`.
4. Mantenere `RUNTIME_STORAGE_ROOT=/data`.
5. Lasciare inizialmente `REQUIRE_PERSISTENT_STORAGE=false` o non impostata; la patch resta compatibile con `true` quando si vorrà rendere il volume obbligatorio.
6. Eseguire il push e attendere il deploy dello stesso servizio web.
7. Verificare che `/api/health` risponda HTTP 200.
8. Aprire Operations Engine, caricare una foto Journal e verificarne preview e download.
9. Eseguire **Redeploy** dello stesso commit.
10. Verificare nuovamente preview e download della stessa foto.

Il `startCommand` Railway richiama esplicitamente `/usr/local/bin/operations-entrypoint` e gli passa il comando Uvicorn come argomento. In questo modo la preparazione del volume non dipende dal modo in cui Railway applica l'override del comando dell'immagine. L'entrypoint è idempotente: l'invocazione root prepara la root e passa a `operations`; un'eventuale seconda invocazione come `operations` verifica la scrivibilità e avvia il comando senza tentare un nuovo `chown`. Non configurare `RAILWAY_RUN_UID=0`.

Il file `docker/entrypoint.sh` è forzato a LF tramite `.gitattributes` e viene copiato nell'immagine con modalità eseguibile `0755`.

Un filesystem del container senza volume non è persistente e non costituisce una configurazione valida per la produzione.

## Verifica Docker su Linux

Con Docker attivo, creare l'immagine e una directory root-owned, quindi montarla su `/data`. Dopo l'avvio verificare:

- `/api/health` restituisce 200;
- il processo Python ha UID/GID di `operations`, non UID 0;
- `/data`, `/data/journal_media` e `/data/attachments` appartengono a `operations:operations` e hanno modalità `0770`;
- un media resta disponibile dopo l'arresto e una nuova istanza con lo stesso mount;
- non esistono file `*.tmp` residui.
