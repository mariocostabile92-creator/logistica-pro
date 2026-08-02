import { journalCard, journalDetail } from "../journal-control-room/components.js";
import { archiveCalendar } from "./calendar.js";

export function archiveShell() {
  return `<section class="gdb-calendar-panel" aria-busy="true">
    <header><div><p class="eyebrow">Storico operativo</p><h3>Archivio GDB</h3><small data-gdb-context></small></div>
      <div class="gdb-month-actions"><button type="button" data-gdb-month="-1" aria-label="Mese precedente">←</button>
      <button type="button" data-gdb-today>Oggi</button><strong data-gdb-month-label></strong>
      <button type="button" data-gdb-month="1" aria-label="Mese successivo">→</button></div></header>
    <div data-gdb-calendar><div class="gdb-loading">Caricamento calendario…</div></div>
    <p class="gdb-month-state" data-gdb-month-state></p></section>
    <section class="gdb-day-panel" aria-busy="true"><header><div><p class="eyebrow">Giorno selezionato</p><h3 data-gdb-day-title></h3></div></header>
      <div class="gdb-kpis" data-gdb-kpis></div>
      <form class="gdb-filters" data-gdb-filters><label>Ricerca<input name="search" type="search" placeholder="Targa, driver, note, ID"></label>
        <label>Targa<input name="plate" type="search" placeholder="Filtra targa"></label>
        <label>Driver<input name="driver" type="search" placeholder="Filtra driver"></label>
        <label>Procedura<select name="operation_type"><option value="">Tutte</option><option value="check_out">Prese in carico</option><option value="check_in">Rientri</option></select></label>
        <label>Stato<select name="status"><option value="">Tutti</option><option value="complete">Complete</option><option value="incomplete">Incomplete</option></select></label>
        <label>Anomalia<select name="anomaly"><option value="">Tutte</option><option value="with">Con anomalie</option><option value="without">Senza anomalie</option></select></label>
        <label>Media<select name="media"><option value="">Tutti</option><option value="with">Con media</option><option value="without">Senza media</option></select></label>
        <button type="reset" class="gdb-reset">Reimposta</button></form>
      <div class="gdb-master-detail"><aside data-gdb-list></aside><article data-gdb-detail></article></div></section>`;
}

export function renderMonth(root, state) {
  const label = new Date(`${state.month}-01T12:00:00Z`).toLocaleDateString("it-IT", { month: "long", year: "numeric" });
  root.querySelector("[data-gdb-month-label]").textContent = label;
  root.querySelector("[data-gdb-context]").textContent = `${state.monthData.context.timezone} · giornata dalle ${String(state.monthData.context.operational_day_start_hour).padStart(2, "0")}:00`;
  root.querySelector("[data-gdb-calendar]").innerHTML = archiveCalendar(state.month, state.selectedDate, state.monthData?.days || []);
  root.querySelector("[data-gdb-month-state]").textContent = state.monthData.total
    ? `${state.monthData.total} procedure nel mese selezionato.`
    : "Nessuna procedura registrata nel mese selezionato.";
  root.querySelector(".gdb-calendar-panel").setAttribute("aria-busy", "false");
}

export function renderDay(root, state) {
  const data = state.dayData;
  root.querySelector("[data-gdb-day-title]").textContent = new Date(`${state.selectedDate}T12:00:00`).toLocaleDateString("it-IT", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  const kpis = [["total", "Totali", ""], ["check_outs", "Prese in carico", "check_out"], ["check_ins", "Rientri", "check_in"], ["complete", "Complete", "complete"], ["incomplete", "Incomplete", "incomplete"], ["with_anomalies", "Con anomalie", "anomaly"], ["with_media", "Con media", "media"]];
  root.querySelector("[data-gdb-kpis]").innerHTML = kpis.map(([key, label, filter]) => `<button type="button" class="${state.activeKpi === filter ? "active" : ""}" data-gdb-kpi="${filter}" aria-pressed="${state.activeKpi === filter}"><strong>${data.summary[key]}</strong><span>${label}</span></button>`).join("");
  root.querySelector("[data-gdb-list]").innerHTML = data.items.length ? data.items.map(item => journalCard(item, state.selected?.id)).join("") : `<div class="jcr-empty"><strong>Nessuna procedura</strong><p>Non ci sono registrazioni per il giorno e i filtri selezionati.</p></div>`;
  root.querySelector("[data-gdb-detail]").innerHTML = journalDetail(state.selected);
  root.querySelector(".gdb-master-detail").classList.toggle("detail-open", Boolean(state.selected));
  root.querySelector(".gdb-day-panel").setAttribute("aria-busy", "false");
}
