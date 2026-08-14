import { escapeHtml } from "../../utils/dom.js";


export const FORECAST_BUCKETS = Object.freeze([
  Object.freeze({ key: "NEXT_DAY", cycle: "NEXT_DAY", segment: null, label: "Next Day" }),
  Object.freeze({ key: "SAME_DAY_A", cycle: "SAME_DAY", segment: "A", label: "Same Day A" }),
  Object.freeze({ key: "SAME_DAY_B_C", cycle: "SAME_DAY", segment: "B_C", label: "Same Day B-C" }),
]);


export function sourceLabel(source) {
  if (source === "MANUAL_PLANNING_INPUT") return "Inserimento manuale";
  if (source === "IMPORT" || source === "LEGACY_IMPORT_BACKFILL") {
    return "Planning Amazon importato";
  }
  if (source === "MANUAL") return "Inserimento manuale legacy";
  return "Nessun dato";
}


export function requirementPreview(rawValue) {
  if (rawValue === "" || rawValue === null || rawValue === undefined) return null;
  const value = Number(rawValue);
  if (!Number.isInteger(value) || value < 0) return null;
  return Math.floor(((value * 110) + 50) / 100);
}


export function forecastDraft(coverage) {
  const items = coverage?.items || [];
  const draft = {};
  FORECAST_BUCKETS.forEach((bucket) => {
    const item = items.find(
      (candidate) => candidate.cycle === bucket.cycle
        && candidate.segment === bucket.segment,
    );
    draft[bucket.key] = item?.forecast === null || item?.forecast === undefined
      ? ""
      : String(item.forecast);
  });
  return draft;
}


function sourceFor(coverage, bucket) {
  return (coverage?.items || []).find(
    (candidate) => candidate.cycle === bucket.cycle
      && candidate.segment === bucket.segment,
  )?.source || null;
}


export function changedRequirements(editor) {
  const requirements = [];
  let clearedExisting = false;
  FORECAST_BUCKETS.forEach((bucket) => {
    const current = String(editor.draft?.[bucket.key] ?? "");
    const initial = String(editor.initial?.[bucket.key] ?? "");
    if (current === initial) return;
    if (current === "") {
      if (initial !== "") clearedExisting = true;
      return;
    }
    const forecast = Number(current);
    if (!Number.isInteger(forecast) || forecast < 0) return;
    requirements.push({
      cycle: bucket.cycle,
      segment: bucket.segment,
      forecast_routes: forecast,
    });
  });
  return { requirements, clearedExisting };
}


export function renderForecastEditor({
  operationLabel,
  coverage,
  editor,
}) {
  if (!editor?.open) return "";
  return `<div class="planning-forecast-modal" role="dialog" aria-modal="true" aria-labelledby="planningForecastEditorTitle">
    <form class="planning-forecast-editor" data-planning-forecast-form>
      <header>
        <div><p class="eyebrow">Fabbisogno giornaliero</p><h3 id="planningForecastEditorTitle">${escapeHtml(operationLabel)}</h3></div>
        <button type="button" class="icon-button" data-close-planning-forecast aria-label="Chiudi">×</button>
      </header>
      <p>Inserisci le rotte comunicate da Amazon. Il requirement applica la riserva operativa del 10%.</p>
      <div class="planning-forecast-fields">
        ${FORECAST_BUCKETS.map((bucket) => {
          const raw = editor.draft?.[bucket.key] ?? "";
          const preview = requirementPreview(raw);
          return `<label data-forecast-bucket="${bucket.key}">
            <span><strong>${bucket.label}</strong><small>Fonte attuale: ${sourceLabel(sourceFor(coverage, bucket))}</small></span>
            <span class="planning-forecast-input-row"><span>Rotte Amazon</span><input type="number" min="0" step="1" inputmode="numeric" value="${escapeHtml(String(raw))}" data-manual-coverage-input="${bucket.key}"></span>
            <span class="planning-forecast-requirement">Requirement +10% <output data-manual-coverage-preview="${bucket.key}">${preview ?? "—"}</output></span>
          </label>`;
        }).join("")}
      </div>
      ${editor.error ? `<p class="planning-forecast-error" role="alert">${escapeHtml(editor.error)}</p>` : ""}
      <footer>
        <button type="button" class="secondary" data-close-planning-forecast ${editor.saving ? "disabled" : ""}>Annulla</button>
        <button type="submit" data-save-planning-forecast ${editor.saving ? "disabled" : ""}>${editor.saving ? "Salvataggio…" : "Salva fabbisogno"}</button>
      </footer>
    </form>
  </div>`;
}
