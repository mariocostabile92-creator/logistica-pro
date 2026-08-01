# Journal runtime storage

Operations Engine salva nel database esclusivamente chiavi relative dei media Journal. La root fisica è risolta dal provider runtime condiviso con le primitive locali dell'Attachment Engine; repository, API e regole dei due domini restano separati.

## Locale

Senza configurazione la root è `backend/data`. Per usare una posizione esplicita:

```text
RUNTIME_STORAGE_ROOT=C:/operations-engine-data
REQUIRE_PERSISTENT_STORAGE=false
```

All'avvio l'applicazione crea e verifica la root e il namespace `journal_media`. Con `REQUIRE_PERSISTENT_STORAGE=true` l'avvio viene bloccato se la variabile manca o la root non è scrivibile.

## Railway

1. Aprire il progetto Railway e il servizio web di Operations Engine.
2. Aprire **Volumes** e creare un volume persistente.
3. Impostare il mount path su `/data`.
4. Aggiungere `RUNTIME_STORAGE_ROOT=/data`.
5. Aggiungere `REQUIRE_PERSISTENT_STORAGE=true`.
6. Eseguire il redeploy del servizio.
7. Caricare una foto e un video dal Driver Journal e verificarli in Control Room.
8. Eseguire un nuovo redeploy.
9. Verificare nuovamente preview e download degli stessi media.

Un filesystem del container senza volume non è persistente e non costituisce una configurazione valida per la produzione.
