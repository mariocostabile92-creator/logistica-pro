# Fleet Plugin v1

Il Fleet Plugin possiede l'anagrafica e il ciclo di vita osservato degli
Asset. Registra identificativi, targa opzionale, categoria, stato, disponibilita,
capability, metadati documentali ed eventi cronologici.

Il Plugin non importa Adapter e non legge vocabolari esterni. Non genera
planning, assegnazioni, conflitti, readiness o capacity. La rimozione o la
disattivazione del Plugin non modifica il comportamento del Core.

Gli interventi, gli ordini di lavoro, i fornitori, i costi, le notifiche e le
regole sulle scadenze appartengono al futuro Maintenance Plugin. In questa
versione `maintenance` e soltanto uno stato di disponibilita osservato.

Il contratto HTTP e versionato nel namespace `/api/plugins/fleet/v1`. Gli
eventi sono append-only e includono `contract_version`.
