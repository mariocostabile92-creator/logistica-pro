import { escapeHtml } from "../utils/dom.js";
import { workforceStatusLabel } from "./workforce-view.js";


const COVERAGE_LABELS = {
  covered: "Coperto",
  surplus: "Coperto",
  attention: "Attenzione",
  deficit: "Scoperto",
  requirement_unavailable: "Non configurato",
};

const ANOMALY_LABELS = {
  absence: "Assenze",
  unavailable: "Non disponibili",
  unknown: "Da verificare",
};


function anomalyCategory(status) {
  if (status.status_code === "unknown") return "unknown";
  if (status.status_code === "unavailable") return "unavailable";
  if (["holiday", "sickness", "leave"].includes(status.status_code)) return "absence";
  return null;
}


export function workforceAnomalies(statuses, members, filter = "all") {
  const memberById = new Map(members.map((item) => [item.workforce_member_id, item]));
  const counts = { absence: 0, unavailable: 0, unknown: 0 };
  const allItems = statuses.flatMap((status) => {
    const category = anomalyCategory(status);
    if (!category) return [];
    counts[category] += 1;
    return [{
      ...status,
      category,
      memberName: memberById.get(status.workforce_member_id)?.display_name || "Risorsa",
    }];
  });
  return {
    counts,
    total: allItems.length,
    items: filter === "all"
      ? allItems
      : allItems.filter((item) => item.category === filter),
  };
}


export function renderWorkforceCoverage(container, coverage) {
  if (!coverage.length) {
    container.innerHTML = `
      <div class="workforce-requirement-empty">
        <strong>Fabbisogno non configurato</strong>
        <span>Non sono disponibili dati di copertura per il periodo selezionato.</span>
      </div>
    `;
    return;
  }
  container.innerHTML = `
    <table>
      <caption class="visually-hidden">Copertura Workforce del periodo selezionato</caption>
      <thead><tr>
        <th scope="col">Data</th>
        <th scope="col">Fabbisogno</th>
        <th scope="col">Disponibili</th>
        <th scope="col">Programmate</th>
        <th scope="col">Assenti</th>
        <th scope="col">Deficit</th>
        <th scope="col">Margine</th>
        <th scope="col">Esito</th>
        <th scope="col">Limitazioni</th>
      </tr></thead>
      <tbody>${coverage.slice(0, 14).map((item) => `
        <tr>
          <th scope="row">${escapeHtml(item.date)}</th>
          <td>${item.status === "requirement_unavailable" ? "--" : item.required ?? "--"}</td>
          <td>${item.available}</td>
          <td>${item.scheduled}</td>
          <td>${item.unavailable}</td>
          <td>${Number.isFinite(item.margin) && item.margin < 0 ? Math.abs(item.margin) : 0}</td>
          <td>${item.status === "requirement_unavailable" ? "--" : item.margin ?? "--"}</td>
          <td><span class="workforce-coverage-status ${escapeHtml(item.status)}">${escapeHtml(COVERAGE_LABELS[item.status] || "Da verificare")}</span></td>
          <td>${item.limitations?.length ? escapeHtml(item.limitations.join(", ")) : "Nessuna"}</td>
        </tr>
      `).join("")}</tbody>
    </table>
  `;
}


export function renderWorkforceAnomalies({
  container,
  summaryElement,
  categoriesElement,
  statuses,
  members,
  filter,
  limit = 25,
}) {
  const result = workforceAnomalies(statuses, members, filter);
  summaryElement.textContent = result.total
    ? `${result.total} warning operativi nel periodo selezionato.`
    : "Nessuna anomalia operativa nel periodo selezionato.";
  categoriesElement.innerHTML = Object.entries(result.counts).map(([category, count]) => `
    <span class="${escapeHtml(category)}"><strong>${count}</strong> ${escapeHtml(ANOMALY_LABELS[category])}</span>
  `).join("");
  const visibleItems = result.items.slice(0, limit);
  container.innerHTML = visibleItems.length
    ? visibleItems.map((item) => `
        <div>
          <strong>${escapeHtml(item.memberName)} - ${escapeHtml(workforceStatusLabel(item.status_code))}</strong>
          <span>${escapeHtml(item.date)}${item.shift_code ? ` - ${escapeHtml(item.shift_code)}` : ""}</span>
        </div>
      `).join("")
    : '<div><strong>Nessun evento per il filtro selezionato.</strong></div>';
  return { hasMore: result.items.length > limit, visibleCount: visibleItems.length };
}
