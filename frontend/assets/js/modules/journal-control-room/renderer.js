import { journalLiveKpis } from "./live-overview.js";

export function journalControlRoomShell() {
  return `<header class="jcr-header"><div><p class="eyebrow">Fleet Operations</p>
    <h2 id="journalControlRoomTitle">Journal Control Room</h2>
    <p>Monitor operativo della giornata corrente.</p>
    <p class="jcr-operational-context" data-jcr-context></p></div></header>
    <aside class="jcr-archive-hint">Per consultare le giornate precedenti apri <strong>Archivio GDB</strong>.</aside>
    <section class="jcr-shared-access" data-jcr-shared-access aria-label="Accesso condiviso Driver Journal"></section>
    <section class="jcr-kpis" aria-label="Riepilogo monitoraggio live">${journalLiveKpis()}</section>
    <section class="jcr-filter-panel" aria-label="Filtri Journal Control Room">
      <div class="jcr-tools"><label>Ricerca<input data-jcr-search type="search" placeholder="Driver, targa, data, note"></label>
        <label>Procedura<select data-jcr-operation><option value="">Tutte</option><option value="check_out">Prese in carico</option><option value="check_in">Rientri</option></select></label>
        <label>Anomalie<select data-jcr-anomaly><option value="">Tutte</option><option value="with">Con anomalie</option><option value="without">Senza anomalie</option></select></label>
      </div>
    </section>
    <div class="jcr-master-detail"><aside data-jcr-list aria-label="Lista procedure"></aside>
      <article data-jcr-detail></article></div>`;
}
