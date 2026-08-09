const escapeHtml = value => String(value ?? "")
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");


const CATEGORY_LABELS = {
  overall: "Overall",
  safety: "Safety",
  compliance: "Compliance",
  customer_delivery_experience: "Customer Delivery Experience",
  quality: "Quality",
  standard_work_compliance: "Standard Work Compliance",
  capacity: "Capacity",
  other: "Other",
};


const STATUS_LABELS = {
  TARGET_MET: "Target raggiunto",
  BELOW_TARGET: "Sotto target",
  BELOW_MINIMUM: "Sotto minimo",
  NO_STANDARD: "Standard non disponibile",
  NOT_EVALUABLE: "Non valutabile",
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


export function effectiveMetricStatus(metric) {
  if (metric?.status?.minimum_status === "BELOW_MINIMUM") return "BELOW_MINIMUM";
  return metric?.status?.target_status || "NOT_EVALUABLE";
}


export function metricValueLabel(current = {}) {
  if (current.value_state !== "PRESENT") {
    return VALUE_STATE_LABELS[current.value_state] || "Dato mancante";
  }
  if (current.raw_value != null && current.raw_value !== "") return String(current.raw_value);
  if (current.numeric_value != null) return String(current.numeric_value);
  if (current.text_value != null && current.text_value !== "") return String(current.text_value);
  return "Dato mancante";
}


function previousValueLabel(metric) {
  if (!metric.previous?.available) return "Non disponibile";
  if (metric.previous.numeric_value != null) return String(metric.previous.numeric_value);
  if (metric.previous.text_value != null && metric.previous.text_value !== "") {
    return String(metric.previous.text_value);
  }
  return "Non disponibile";
}


function standardValue(raw, numeric) {
  if (raw != null && raw !== "") return String(raw);
  return numeric == null ? "Non disponibile" : String(numeric);
}


function deltaLabel(metric) {
  const delta = metric.delta?.numeric_delta;
  if (delta == null) return "—";
  const number = Number(delta);
  if (!Number.isFinite(number)) return "—";
  return number > 0 ? `+${number}` : String(number);
}


function statusPriority(metric) {
  return {
    BELOW_MINIMUM: 0,
    BELOW_TARGET: 1,
    TARGET_MET: 2,
    NO_STANDARD: 3,
    NOT_EVALUABLE: 4,
  }[effectiveMetricStatus(metric)] ?? 4;
}


export function filterQualityMetrics(metrics = [], filter = "all", search = "") {
  const needle = String(search || "").trim().toLocaleLowerCase("it");
  return metrics.filter(metric => {
    const status = effectiveMetricStatus(metric);
    if (filter === "attention" && !["BELOW_TARGET", "BELOW_MINIMUM"].includes(status)) return false;
    if (filter === "target" && status !== "TARGET_MET") return false;
    return !needle || String(metric.label || "").toLocaleLowerCase("it").includes(needle);
  });
}


function metricCard(metric) {
  const status = effectiveMetricStatus(metric);
  const improvement = metric.delta?.direction_adjusted_improvement || "unknown";
  return `
    <article class="dsp-quality-metric-card tone-${status.toLowerCase().replaceAll("_", "-")}">
      <header>
        <h4>${escapeHtml(metric.label || "Metrica")}</h4>
        ${metric.current?.rating ? `<span class="dsp-quality-rating">${escapeHtml(metric.current.rating)}</span>` : ""}
      </header>
      <div class="dsp-quality-metric-primary">
        <strong>${escapeHtml(metricValueLabel(metric.current))}</strong>
        <span class="dsp-quality-metric-status">${escapeHtml(STATUS_LABELS[status] || STATUS_LABELS.NOT_EVALUABLE)}</span>
      </div>
      <dl class="dsp-quality-metric-standard">
        <div><dt>Target</dt><dd>${escapeHtml(standardValue(metric.standard?.raw_target, metric.standard?.target))}</dd></div>
        <div><dt>Minimum</dt><dd>${escapeHtml(standardValue(metric.standard?.raw_minimum, metric.standard?.minimum))}</dd></div>
      </dl>
      <div class="dsp-quality-metric-wow" data-improvement="${escapeHtml(improvement)}">
        <span>Precedente <strong>${escapeHtml(previousValueLabel(metric))}</strong></span>
        <span>Delta <strong>${escapeHtml(deltaLabel(metric))}</strong></span>
        <strong>${escapeHtml(IMPROVEMENT_LABELS[improvement] || IMPROVEMENT_LABELS.unknown)}</strong>
      </div>
    </article>
  `;
}


function metricsContent(data, filter, search) {
  if (!data?.available) {
    return '<div class="dsp-quality-metrics-empty" role="status">Nessuna scorecard disponibile. Importa una scorecard dalla sezione Quality.</div>';
  }
  if (!data.metrics_available || !data.metrics?.length) {
    return '<div class="dsp-quality-metrics-empty" role="status">Nessuna metrica disponibile per questa scorecard.</div>';
  }
  const visible = filterQualityMetrics(data.metrics, filter, search);
  if (!visible.length) {
    return '<div class="dsp-quality-metrics-empty" role="status">Nessuna metrica corrisponde ai filtri selezionati.</div>';
  }
  const categoryOrder = data.categories || [];
  return categoryOrder.map(category => {
    const items = visible
      .filter(metric => metric.category === category)
      .sort((left, right) => statusPriority(left) - statusPriority(right));
    if (!items.length) return "";
    const label = CATEGORY_LABELS[category] || CATEGORY_LABELS.other;
    const headingId = `quality-category-${String(category).replace(/[^a-z0-9_-]/gi, "-")}`;
    return `
      <section class="dsp-quality-metric-category" aria-labelledby="${headingId}">
        <h3 id="${headingId}">${escapeHtml(label)}</h3>
        <div class="dsp-quality-metric-grid">${items.map(metricCard).join("")}</div>
      </section>
    `;
  }).join("");
}


export function qualityMetricsMarkup(metricsState = {}) {
  if (["idle", "loading"].includes(metricsState.phase)) {
    return '<div class="dsp-quality-metrics-loading" role="status" aria-busy="true"><span aria-hidden="true"></span><strong>Caricamento metriche</strong></div>';
  }
  if (metricsState.phase === "error") {
    return `
      <div class="dsp-quality-metrics-error" role="alert">
        <strong>Metriche temporaneamente non disponibili</strong>
        <span>${escapeHtml(metricsState.error || "Impossibile caricare le metriche.")}</span>
        <button type="button" data-quality-metrics-retry>Riprova</button>
      </div>
    `;
  }
  const data = metricsState.data || {};
  const current = data.current_period || {};
  const previous = data.previous_period || {};
  const summary = data.summary || {};
  return `
    <section class="dsp-quality-metrics" aria-labelledby="dspQualityMetricsTitle">
      <header class="dsp-quality-metrics-heading">
        <div>
          <p class="eyebrow">Metriche</p>
          <h3 id="dspQualityMetricsTitle">Week ${escapeHtml(current.week ?? "—")} · ${escapeHtml(current.year ?? "—")}</h3>
          <p>${data.previous_available
            ? `Confronto: vs Week ${escapeHtml(previous.week)} · ${escapeHtml(previous.year)}`
            : "Nessuna scorecard precedente disponibile per il confronto."}</p>
        </div>
        <dl class="dsp-quality-metrics-summary" aria-label="Riepilogo metriche">
          <div><dt>Metriche valutabili</dt><dd>${escapeHtml(summary.evaluatable ?? 0)}</dd></div>
          <div><dt>Target raggiunti</dt><dd>${escapeHtml(summary.target_met ?? 0)}</dd></div>
          <div><dt>Da attenzionare</dt><dd>${escapeHtml(summary.attention ?? 0)}</dd></div>
        </dl>
      </header>
      <div class="dsp-quality-metrics-controls">
        <div role="group" aria-label="Filtra metriche">
          ${[["all", "Tutte"], ["attention", "Da attenzionare"], ["target", "Target raggiunto"]].map(([key, label]) => `
            <button type="button" data-quality-metrics-filter="${key}" aria-pressed="${metricsState.filter === key}" class="${metricsState.filter === key ? "active" : ""}">${label}</button>
          `).join("")}
        </div>
        <label>Ricerca metrica<input type="search" data-quality-metrics-search value="${escapeHtml(metricsState.search || "")}" placeholder="Nome metrica" /></label>
      </div>
      <div class="dsp-quality-metrics-categories">${metricsContent(data, metricsState.filter, metricsState.search)}</div>
    </section>
  `;
}

