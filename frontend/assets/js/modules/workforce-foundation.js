import { escapeHtml } from "../utils/dom.js";


const STATUS_LABELS = {
  available: "Disponibile",
  scheduled: "Disponibile",
  rest: "Riposo",
  holiday: "Ferie",
  sickness: "Malattia",
  leave: "Permesso",
  unavailable: "Non disponibile",
  unknown: "Da verificare",
};

let snapshot = null;


function filteredDrivers() {
  const query = document.getElementById("workforceFoundationSearch")?.value.trim().toLocaleLowerCase("it") || "";
  const filter = document.getElementById("workforceFoundationFilter")?.value || "all";
  return (snapshot?.drivers || []).filter((driver) => {
    const searchable = [driver.display_name, driver.external_identifier, driver.station, driver.role]
      .filter(Boolean).join(" ").toLocaleLowerCase("it");
    const matchesQuery = !query || searchable.includes(query);
    const matchesFilter = filter === "all"
      || (filter === "callable" && driver.callable)
      || (filter === "reserve" && driver.callable && driver.is_reserve)
      || driver.availability_status === filter;
    return matchesQuery && matchesFilter;
  });
}


function renderDrivers() {
  const root = document.getElementById("workforceFoundationDrivers");
  if (!root || !snapshot) return;
  const drivers = filteredDrivers();
  if (!drivers.length) {
    root.innerHTML = '<p class="workforce-foundation-empty">Nessun driver corrisponde ai filtri.</p>';
    return;
  }
  root.innerHTML = drivers.map((driver) => `
    <article class="workforce-driver-readiness ${driver.callable ? "is-callable" : "is-not-callable"}">
      <div class="workforce-driver-identity">
        <strong>${escapeHtml(driver.display_name)}</strong>
        <span>${escapeHtml(driver.external_identifier)} · ${escapeHtml(driver.role || "Ruolo non indicato")}</span>
      </div>
      <div><span>Station</span><strong>${escapeHtml(driver.station || "Non indicata")}</strong></div>
      <div><span>Contratto</span><strong>${escapeHtml(driver.contract || "Non indicato")}</strong></div>
      <div><span>Abilitazioni</span><strong>${escapeHtml(driver.capabilities?.join(", ") || "Nessuna")}</strong></div>
      <div class="workforce-driver-state">
        <span class="workforce-readiness-badge" data-status="${escapeHtml(driver.availability_status)}">${escapeHtml(STATUS_LABELS[driver.availability_status] || "Da verificare")}</span>
        <strong>${driver.callable ? "Convocabile" : "Non convocabile"}${driver.is_reserve ? " · Riserva" : ""}</strong>
      </div>
    </article>
  `).join("");
}


export function renderWorkforceFoundation(value) {
  snapshot = value;
  const summary = value.summary;
  document.getElementById("workforceFoundationDate").textContent = value.operation_date;
  [
    ["Total", summary.total], ["Available", summary.available],
    ["Callable", summary.callable], ["Holiday", summary.holiday],
    ["Sickness", summary.sickness], ["Leave", summary.leave],
    ["Rest", summary.rest], ["NotCallable", summary.not_callable],
    ["Reserves", summary.reserves],
  ].forEach(([suffix, count]) => {
    document.getElementById(`workforceFoundation${suffix}`).textContent = count;
  });
  document.getElementById("workforceFoundationLimit").textContent = value.limitations[0] || "";
  renderDrivers();
}


export function initWorkforceFoundation() {
  document.getElementById("workforceFoundationSearch")?.addEventListener("input", renderDrivers);
  document.getElementById("workforceFoundationFilter")?.addEventListener("change", renderDrivers);
}
