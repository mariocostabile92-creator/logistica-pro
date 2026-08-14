import {
  renderForecastEditor,
  sourceLabel,
} from "./forecast-editor.js?v=forecast1";


const BUCKETS = [
  ["NEXT_DAY", null, "Next Day"],
  ["SAME_DAY", "A", "Same Day A"],
  ["SAME_DAY", "B_C", "Same Day B-C"],
];

const value = (item, key) => item?.[key] ?? "—";


export function renderForecast(coverage, {
  operationLabel,
  writable = false,
  editor = null,
} = {}) {
  const items = coverage?.items || [];
  const action = writable
    ? '<button type="button" class="secondary" data-open-planning-forecast>Modifica fabbisogno</button>'
    : "";
  if (!coverage?.available) {
    return `<section class="planning-ops-panel"><header><div><p class="eyebrow">Preparazione risorse</p><h3>Forecast Amazon</h3></div>${action}</header><p class="planning-ops-empty">Forecast non disponibile per la data selezionata.</p></section>${renderForecastEditor({ operationLabel, coverage, editor })}`;
  }
  return `<section class="planning-ops-panel planning-coverage-panel"><header><div><p class="eyebrow">Totale della giornata</p><h3>Forecast Amazon e copertura</h3></div><div class="planning-coverage-actions"><small>Fonte: Coverage Workforce</small>${action}</div></header>
  <div class="planning-coverage-buckets">${BUCKETS.map(([cycle, segment, label]) => {
    const item = items.find((entry) => entry.cycle === cycle && entry.segment === segment);
    const status = item?.status === "REQUIREMENT_COVERED"
      ? "Coperto"
      : item?.status === "NO_FORECAST" ? "Forecast assente" : "Da coprire";
    return `<article><header><h4>${label}</h4><span>${status}</span></header><dl>
      <div><dt>Forecast</dt><dd>${value(item, "forecast")}</dd></div>
      <div><dt>Requirement +10%</dt><dd>${value(item, "requirement")}</dd></div>
      <div><dt>Assegnati</dt><dd>${value(item, "assigned")}</dd></div>
      <div><dt>Gap requirement</dt><dd>${value(item, "requirement_gap")}</dd></div>
      <div><dt>Scorta</dt><dd>${value(item, "reserve")}</dd></div>
    </dl><small class="planning-coverage-source">Fonte: ${sourceLabel(item?.source)}</small></article>`;
  }).join("")}</div></section>${renderForecastEditor({ operationLabel, coverage, editor })}`;
}
