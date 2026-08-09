import { reconciliationMarkup } from "./reconciliation-presenter.js?v=8";


const escapeHtml = value => String(value ?? "")
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");


const METRICS = [
  ["delivery_completion_rate", "DCR"],
  ["photo_on_delivery", "POD"],
  ["contact_compliance", "CC"],
  ["delivery_success_conditions_dpmo", "DSC DPMO"],
  ["customer_delivery_feedback_dpmo", "CDF DPMO"],
  ["customer_escalations_count", "CE"],
  ["delivered", "Delivered"],
  ["lost_on_road_dpmo", "LoR DPMO"],
];


const MAPPING_LABELS = {
  MATCHED: "Associato",
  UNMAPPED: "Da associare",
  AMBIGUOUS: "Associazione ambigua",
};


const VALUE_STATE_LABELS = {
  NOT_AVAILABLE: "Non disponibile",
  NOT_APPLICABLE: "Non applicabile",
  MISSING: "Dato mancante",
};


const IMPROVEMENT_LABELS = {
  improved: "Migliorata",
  worsened: "Peggiorata",
  unchanged: "Invariata",
  unknown: "Confronto non disponibile",
};


function metric(row, key) {
  return (row?.metrics || []).find(item => item.metric_key === key) || null;
}


export function driverDisplayName(row = {}) {
  if (row.mapping_status === "MATCHED" && row.workforce_display_name) {
    return row.workforce_display_name;
  }
  return `Transporter ${row.transporter_external_id || "non disponibile"}`;
}


export function driverMetricValue(item) {
  const current = item?.current || {};
  if (current.value_state !== "PRESENT") {
    return VALUE_STATE_LABELS[current.value_state] || "Dato mancante";
  }
  if (current.raw_value != null && current.raw_value !== "") return String(current.raw_value);
  if (current.numeric_value != null && Number.isFinite(Number(current.numeric_value))) {
    return String(current.numeric_value);
  }
  if (current.text_value != null && current.text_value !== "") return String(current.text_value);
  return "Dato mancante";
}


function searchableText(row) {
  return `${driverDisplayName(row)} ${row.transporter_external_id || ""}`.toLocaleLowerCase("it");
}


export function filterQualityDrivers(rows = [], filter = "all", search = "") {
  const needle = String(search || "").trim().toLocaleLowerCase("it");
  const expectedStatus = {
    matched: "MATCHED",
    unmapped: "UNMAPPED",
    ambiguous: "AMBIGUOUS",
  }[filter] || null;
  return rows.filter(row => (
    (!expectedStatus || row.mapping_status === expectedStatus)
    && (!needle || searchableText(row).includes(needle))
  ));
}


function sortValue(row, key) {
  if (key === "driver") return driverDisplayName(row).toLocaleLowerCase("it");
  if (key === "row_index") return Number(row.row_index || 0);
  const numeric = metric(row, key)?.current?.numeric_value;
  return numeric == null || !Number.isFinite(Number(numeric)) ? null : Number(numeric);
}


export function sortQualityDrivers(rows = [], sort = {}) {
  const key = sort.key || "row_index";
  const direction = sort.direction === "desc" ? -1 : 1;
  return rows.map((row, index) => ({ row, index })).sort((left, right) => {
    const leftValue = sortValue(left.row, key);
    const rightValue = sortValue(right.row, key);
    if (leftValue == null && rightValue == null) return left.index - right.index;
    if (leftValue == null) return 1;
    if (rightValue == null) return -1;
    const comparison = typeof leftValue === "string"
      ? leftValue.localeCompare(rightValue, "it", { sensitivity: "base" })
      : leftValue - rightValue;
    return comparison === 0 ? left.index - right.index : comparison * direction;
  }).map(item => item.row);
}


function mappingBadge(row) {
  const status = row.mapping_status || "UNMAPPED";
  return `<span class="dsp-quality-driver-mapping tone-${status.toLowerCase()}">${escapeHtml(MAPPING_LABELS[status] || "Da associare")}</span>`;
}


function sortHeading(label, key, state, className = "") {
  const active = state.sort?.key === key;
  const direction = active ? state.sort.direction : null;
  return `
    <th scope="col" class="${className}" aria-sort="${active ? (direction === "desc" ? "descending" : "ascending") : "none"}">
      <button type="button" data-quality-drivers-sort="${key}" aria-label="Ordina per ${escapeHtml(label)}">${escapeHtml(label)}${active ? `<span aria-hidden="true">${direction === "desc" ? "↓" : "↑"}</span>` : ""}</button>
    </th>
  `;
}


function mappingAction(row, canManageMappings) {
  if (!canManageMappings) return "";
  const label = row.mapping_status === "MATCHED"
    ? "Modifica associazione"
    : row.mapping_status === "AMBIGUOUS" ? "Risolvi associazione" : "Associa driver";
  return `<button type="button" class="dsp-quality-driver-map-action" data-quality-reconciliation-row="${escapeHtml(row.transporter_external_id)}">${label}</button>`;
}


function tableRow(row, state) {
  const cell = (key, label, extraClass = "") => `<td data-label="${label}" class="${extraClass}">${escapeHtml(driverMetricValue(metric(row, key)))}</td>`;
  return `
    <tr data-quality-driver-row="${escapeHtml(row.row_id)}">
      <th scope="row">
        <button type="button" class="dsp-quality-driver-open" data-quality-driver-open="${escapeHtml(row.row_id)}">
          <strong>${escapeHtml(driverDisplayName(row))}</strong>
          <span>${escapeHtml(row.transporter_external_id || "Transporter non disponibile")}</span>
          ${mappingBadge(row)}
        </button>
        ${mappingAction(row, state.canManageMappings)}
      </th>
      ${cell("delivery_completion_rate", "DCR")}
      ${cell("photo_on_delivery", "POD")}
      ${cell("contact_compliance", "CC")}
      ${cell("delivery_success_conditions_dpmo", "DSC", "is-table-secondary")}
      ${cell("customer_delivery_feedback_dpmo", "CDF", "is-table-secondary")}
      ${cell("customer_escalations_count", "CE")}
      ${cell("delivered", "Delivered")}
    </tr>
  `;
}


function previousLabel(item) {
  if (!item?.previous?.available) return "Non disponibile";
  const previous = item.previous;
  if (previous.value_state !== "PRESENT") return VALUE_STATE_LABELS[previous.value_state] || "Dato mancante";
  if (previous.raw_value != null && previous.raw_value !== "") return String(previous.raw_value);
  if (previous.numeric_value != null) return String(previous.numeric_value);
  return "Non disponibile";
}


function deltaLabel(item) {
  const value = item?.delta?.numeric_delta;
  if (value == null || !Number.isFinite(Number(value))) return "—";
  return Number(value) > 0 ? `+${value}` : String(value);
}


function detailMetric(row, [key, label]) {
  const item = metric(row, key);
  const improvement = item?.delta?.direction_adjusted_improvement || "unknown";
  return `
    <article class="dsp-quality-driver-detail-metric" data-improvement="${escapeHtml(improvement)}">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(driverMetricValue(item))}</strong>
      <dl>
        <div><dt>Precedente</dt><dd>${escapeHtml(previousLabel(item))}</dd></div>
        <div><dt>Delta</dt><dd>${escapeHtml(deltaLabel(item))}</dd></div>
      </dl>
      <small>${escapeHtml(IMPROVEMENT_LABELS[improvement] || IMPROVEMENT_LABELS.unknown)}</small>
    </article>
  `;
}


function driverDetail(row, state) {
  if (!row) return "";
  const hasPrevious = (row.metrics || []).some(item => item.previous?.available);
  return `
    <aside class="dsp-quality-driver-detail" aria-labelledby="dspQualityDriverDetailTitle">
      <header>
        <div>
          <p class="eyebrow">Dettaglio Transporter</p>
          <h4 id="dspQualityDriverDetailTitle">${escapeHtml(driverDisplayName(row))}</h4>
          <p>${escapeHtml(row.transporter_external_id || "Transporter non disponibile")} · ${mappingBadge(row)}</p>
        </div>
        <button type="button" class="secondary" data-quality-driver-close aria-label="Chiudi dettaglio driver">Chiudi</button>
      </header>
      ${hasPrevious ? "" : '<p class="dsp-quality-driver-no-previous">Nessun confronto precedente disponibile.</p>'}
      <div class="dsp-quality-driver-detail-grid">${METRICS.map(item => detailMetric(row, item)).join("")}</div>
      ${row.mapping_status === "MATCHED" && row.workforce_member_id ? `
        <button type="button" class="dsp-quality-driver-workforce" data-quality-driver-workforce="${escapeHtml(row.workforce_member_id)}">Apri driver Workforce</button>
      ` : ""}
      ${mappingAction(row, state.canManageMappings)}
    </aside>
  `;
}


function driverContent(data, state) {
  if (!data?.available) {
    return '<div class="dsp-quality-drivers-empty" role="status">Nessuna scorecard disponibile. Importa una scorecard dalla sezione Quality.</div>';
  }
  if (!data.drivers_available || !data.rows?.length) {
    return '<div class="dsp-quality-drivers-empty" role="status">Nessuna performance driver disponibile.</div>';
  }
  const visible = sortQualityDrivers(
    filterQualityDrivers(data.rows, state.filter, state.search),
    state.sort,
  );
  if (!visible.length) {
    return '<div class="dsp-quality-drivers-empty" role="status">Nessun driver corrisponde ai filtri selezionati.</div>';
  }
  return `
    <div class="dsp-quality-driver-table-wrap">
      <table class="dsp-quality-driver-table">
        <thead><tr>
          ${sortHeading("Driver / Transporter", "driver", state)}
          ${sortHeading("DCR", "delivery_completion_rate", state)}
          ${sortHeading("POD", "photo_on_delivery", state)}
          ${sortHeading("CC", "contact_compliance", state)}
          ${sortHeading("DSC", "delivery_success_conditions_dpmo", state, "is-table-secondary")}
          ${sortHeading("CDF", "customer_delivery_feedback_dpmo", state, "is-table-secondary")}
          ${sortHeading("CE", "customer_escalations_count", state)}
          ${sortHeading("Delivered", "delivered", state)}
        </tr></thead>
        <tbody>${visible.map(row => tableRow(row, state)).join("")}</tbody>
      </table>
    </div>
  `;
}


export function qualityDriversMarkup(driversState = {}) {
  if (["idle", "loading"].includes(driversState.phase)) {
    return '<div class="dsp-quality-drivers-loading" role="status" aria-busy="true"><span aria-hidden="true"></span><strong>Caricamento performance driver</strong></div>';
  }
  if (driversState.phase === "error") {
    return `
      <div class="dsp-quality-drivers-error" role="alert">
        <strong>Performance driver temporaneamente non disponibili</strong>
        <span>${escapeHtml(driversState.error || "Impossibile caricare i driver.")}</span>
        <button type="button" data-quality-drivers-retry>Riprova</button>
      </div>
    `;
  }
  const data = driversState.data || {};
  const summary = data.summary || {};
  const selected = (data.rows || []).find(row => row.row_id === driversState.selectedRowId) || null;
  return `
    <section class="dsp-quality-drivers" aria-labelledby="dspQualityDriversTitle">
      <header class="dsp-quality-drivers-heading">
        <div>
          <p class="eyebrow">Driver</p>
          <h3 id="dspQualityDriversTitle">Performance Week ${escapeHtml(data.current_period?.week ?? "—")} · ${escapeHtml(data.current_period?.year ?? "—")}</h3>
          <p>Valori reali per Transporter ID. Nessun ranking proprietario applicato.</p>
        </div>
        <dl class="dsp-quality-drivers-summary" aria-label="Riepilogo driver">
          <div><dt>Transporter totali</dt><dd>${escapeHtml(summary.total ?? 0)}</dd></div>
          <div><dt>Associati</dt><dd>${escapeHtml(summary.matched ?? 0)}</dd></div>
          <div><dt>Da associare</dt><dd>${escapeHtml(summary.unmapped ?? 0)}</dd></div>
        </dl>
        ${Number(summary.ambiguous || 0) > 0 ? `<p class="dsp-quality-drivers-ambiguous" role="status">Associazioni ambigue: <strong>${escapeHtml(summary.ambiguous)}</strong></p>` : ""}
        ${driversState.canManageMappings ? '<button type="button" class="dsp-quality-reconciliation-entry" data-quality-reconciliation-open>Gestisci associazioni</button>' : ""}
      </header>
      <div class="dsp-quality-drivers-controls">
        <div role="group" aria-label="Filtra mapping driver">
          ${[["all", "Tutti"], ["matched", "Associati"], ["unmapped", "Da associare"], ["ambiguous", "Ambigui"]].map(([key, label]) => `
            <button type="button" data-quality-drivers-filter="${key}" aria-pressed="${driversState.filter === key}" class="${driversState.filter === key ? "active" : ""}">${label}</button>
          `).join("")}
        </div>
        <label>Ricerca driver<input type="search" data-quality-drivers-search value="${escapeHtml(driversState.search || "")}" placeholder="Nome o Transporter ID" /></label>
      </div>
      ${driverDetail(selected, driversState)}
      ${driverContent(data, driversState)}
      ${reconciliationMarkup(driversState.reconciliation)}
    </section>
  `;
}
