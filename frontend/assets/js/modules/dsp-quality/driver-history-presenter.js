const escapeHtml = value => String(value ?? "")
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");


const STATUS_LABELS = {
  DA_ATTENZIONARE: "Da attenzionare",
  DA_MIGLIORARE: "Da migliorare",
  IN_MIGLIORAMENTO: "In miglioramento",
  STABILE: "Stabile",
  SENZA_STORICO: "Senza storico",
};


const COMPARISON_LABELS = {
  IMPROVED: "Migliorata",
  WORSENED: "Peggiorata",
  UNCHANGED: "Invariata",
  NOT_COMPARABLE: "Non confrontabile",
};


const CHART_METRICS = [
  "delivery_completion_rate",
  "photo_on_delivery",
  "customer_delivery_feedback_dpmo",
  "contact_compliance",
  "delivery_success_conditions_dpmo",
  "lost_on_road_dpmo",
  "customer_escalations_count",
];


function metricCatalog(data) {
  const catalog = new Map();
  for (const entry of data?.timeline || []) {
    for (const metric of entry.metrics || []) catalog.set(metric.metric_key, metric);
  }
  return CHART_METRICS.map(key => catalog.get(key)).filter(Boolean);
}


export function defaultHistoryMetricKey(data) {
  const available = new Set(metricCatalog(data).map(metric => metric.metric_key));
  const focus = data?.summary?.current_focus || [];
  return focus.find(item => available.has(item.metric_key))?.metric_key
    || (available.has("delivery_completion_rate") ? "delivery_completion_rate" : null)
    || metricCatalog(data)[0]?.metric_key
    || null;
}


export function buildHistoryChart(data, metricKey) {
  const points = (data?.timeline || []).map((entry, index) => {
    const metric = (entry.metrics || []).find(item => item.metric_key === metricKey);
    const numeric = metric?.value?.numeric_value;
    return {
      index,
      year: entry.year,
      week: entry.week,
      value: Number.isFinite(Number(numeric)) && numeric !== null
        ? Number(numeric)
        : null,
    };
  });
  const values = points.map(point => point.value).filter(value => value !== null);
  const minimum = values.length ? Math.min(...values) : null;
  const maximum = values.length ? Math.max(...values) : null;
  const segments = [];
  let current = [];
  for (const point of points) {
    if (point.value === null) {
      if (current.length) segments.push(current);
      current = [];
    } else {
      current.push(point);
    }
  }
  if (current.length) segments.push(current);
  return { points, segments, minimum, maximum };
}


function number(value, unit = null) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
  const formatted = new Intl.NumberFormat("it-IT", { maximumFractionDigits: 2 }).format(Number(value));
  return unit === "%" ? `${formatted}%` : `${formatted}${unit ? ` ${unit}` : ""}`;
}


function period(periodValue) {
  return periodValue ? `W${periodValue.week} · ${periodValue.year}` : "—";
}


function focusMarkup(focus = []) {
  if (!focus.length) return '<p class="dsp-quality-neutral">Nessun focus deterministico per questa settimana.</p>';
  return `<ul class="dsp-quality-history-focus">${focus.map(item => `
    <li><strong>${escapeHtml(item.label)}</strong><span>${escapeHtml(item.reason)}</span></li>
  `).join("")}</ul>`;
}


function trendSummaryMarkup(data) {
  const recurring = data?.summary?.recurring_worsening_metrics || [];
  const improving = data?.summary?.recurring_improving_metrics || [];
  const trends = data?.metric_trends || [];
  const recovery = trends.filter(item => item.recovery);
  if (!recurring.length && !improving.length) {
    return '<p class="dsp-quality-neutral">Nessuna sequenza ricorrente disponibile.</p>';
  }
  return `<div class="dsp-quality-history-trends">
    ${recurring.map(item => `<article data-trend="recurring"><strong>${escapeHtml(item.label)}</strong><span>Ricorrente · ${item.consecutive_worsening_comparisons} confronti consecutivi in peggioramento</span></article>`).join("")}
    ${improving.map(item => `<article data-trend="improving"><strong>${escapeHtml(item.label)}</strong><span>${item.consecutive_improving_comparisons} confronti consecutivi in miglioramento${recovery.some(entry => entry.metric_key === item.metric_key) ? " · In recupero" : ""}</span></article>`).join("")}
  </div>`;
}


function chartMarkup(data, metricKey) {
  const catalog = metricCatalog(data);
  const selected = catalog.find(item => item.metric_key === metricKey) || catalog[0];
  if (!selected) return '<p class="dsp-quality-neutral">Nessuna metrica disponibile per il grafico.</p>';
  const chart = buildHistoryChart(data, selected.metric_key);
  const width = 720;
  const height = 250;
  const left = 48;
  const right = 18;
  const top = 20;
  const bottom = 48;
  const innerWidth = width - left - right;
  const innerHeight = height - top - bottom;
  const range = chart.maximum === chart.minimum ? 1 : chart.maximum - chart.minimum;
  const x = point => left + (chart.points.length <= 1 ? innerWidth / 2 : point.index * innerWidth / (chart.points.length - 1));
  const y = point => top + (chart.maximum - point.value) * innerHeight / range;
  const lines = chart.segments.map(segment => (
    segment.length > 1
      ? `<polyline points="${segment.map(point => `${x(point)},${y(point)}`).join(" ")}" fill="none" vector-effect="non-scaling-stroke" />`
      : ""
  )).join("");
  const points = chart.points.map(point => point.value === null
    ? `<text x="${x(point)}" y="${top + innerHeight / 2}" class="chart-gap" text-anchor="middle">gap</text>`
    : `<circle cx="${x(point)}" cy="${y(point)}" r="5"><title>W${point.week} ${point.year}: ${number(point.value, selected.unit)}</title></circle>`).join("");
  const labels = chart.points.map(point => `<text x="${x(point)}" y="${height - 16}" text-anchor="middle">W${point.week}</text>`).join("");
  return `<section class="dsp-quality-history-chart" aria-labelledby="qualityHistoryChartTitle">
    <div><div><p class="eyebrow">Metrica selezionata</p><h4 id="qualityHistoryChartTitle">${escapeHtml(selected.label)}</h4></div>
      <label>Metrica<select data-quality-driver-history-metric>${catalog.map(metric => `<option value="${escapeHtml(metric.metric_key)}" ${metric.metric_key === selected.metric_key ? "selected" : ""}>${escapeHtml(metric.label)}</option>`).join("")}</select></label>
    </div>
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Andamento ${escapeHtml(selected.label)} sulle scorecard disponibili">
      <line x1="${left}" y1="${top + innerHeight}" x2="${width - right}" y2="${top + innerHeight}" class="chart-axis" />
      ${lines}${points}${labels}
    </svg>
    <p>Nessuna interpolazione tra settimane mancanti. Nessun target driver applicato.</p>
  </section>`;
}


function timelineMetric(entry, metricKey) {
  const metric = (entry.metrics || []).find(item => item.metric_key === metricKey);
  if (!metric) return "";
  const trend = metric.recurring
    ? '<span class="trend-label recurring">Ricorrente</span>'
    : metric.recovery
      ? '<span class="trend-label recovery">In recupero</span>'
      : "";
  return `<div class="dsp-quality-history-metric" data-comparison="${metric.comparison}">
    <strong>${escapeHtml(metric.label)}</strong>
    <span>${number(metric.value?.numeric_value, metric.unit)}</span>
    <small>${COMPARISON_LABELS[metric.comparison] || "Non confrontabile"}${metric.numeric_delta == null ? "" : ` · Δ ${number(metric.numeric_delta, metric.unit)}`}</small>
    ${trend}
  </div>`;
}


function timelineMarkup(data, metricKey) {
  return `<section class="dsp-quality-history-timeline" aria-labelledby="qualityHistoryTimelineTitle">
    <h4 id="qualityHistoryTimelineTitle">Andamento settimana per settimana</h4>
    <ol>${(data.timeline || []).map(entry => {
      const focusKeys = (entry.weekly_focus || []).map(item => item.metric_key);
      const metricKeys = [...new Set([metricKey, ...focusKeys])].filter(Boolean).slice(0, 3);
      return `<li data-history-week="${entry.week}">
        <article>
          <header><div><strong>Week ${entry.week}</strong><span>${entry.year}</span></div><span class="dsp-quality-attention-badge" data-history-status="${entry.weekly_status}">${STATUS_LABELS[entry.weekly_status] || entry.weekly_status}</span></header>
          ${Number(entry.customer_escalations || 0) > 0 ? `<p class="dsp-quality-history-escalation"><strong>${number(entry.customer_escalations)}</strong> Customer Escalation${Number(entry.customer_escalations) === 1 ? "" : "s"}</p>` : ""}
          <div class="dsp-quality-history-week-metrics">${metricKeys.map(key => timelineMetric(entry, key)).join("")}</div>
          <div class="dsp-quality-history-week-focus"><strong>Focus</strong>${focusMarkup(entry.weekly_focus)}</div>
          <p>${escapeHtml((entry.reasons || []).join(" ") || "Nessun confronto disponibile.")}</p>
        </article>
      </li>`;
    }).join("")}</ol>
  </section>`;
}


function availableMarkup(view) {
  const data = view.data;
  if (!data?.available) return `<section class="dsp-quality-driver-history"><button type="button" class="secondary" data-quality-driver-history-back>← Torna ad Attenzione</button><p class="dsp-quality-neutral">Nessuno storico disponibile per questo Transporter ID.</p></section>`;
  const summary = data.summary || {};
  const name = data.workforce_display_name || "Driver non associato";
  const focus = summary.current_focus || [];
  const metricKey = view.metricKey || defaultHistoryMetricKey(data);
  return `<section class="dsp-quality-driver-history" aria-labelledby="qualityDriverHistoryTitle">
    <button type="button" class="secondary dsp-quality-history-back" data-quality-driver-history-back>← Torna ad Attenzione</button>
    <header class="dsp-quality-history-header">
      <div><p class="eyebrow">Storico Quality driver</p><h3 id="qualityDriverHistoryTitle">${escapeHtml(name)}</h3><p>Amazon T-ID: <code>${escapeHtml(data.transporter_external_id)}</code></p></div>
      <dl><div><dt>Periodo storico</dt><dd>${period(summary.first_period)} → ${period(summary.latest_period)}</dd></div><div><dt>Stato corrente</dt><dd><span class="dsp-quality-attention-badge" data-history-status="${summary.current_status}">${STATUS_LABELS[summary.current_status] || "—"}</span></dd></div><div><dt>Focus corrente</dt><dd>${focus.length ? focus.map(item => escapeHtml(item.label)).join(" · ") : "Nessun focus"}</dd></div></dl>
    </header>
    <dl class="dsp-quality-history-kpis">
      <div><dt>Scorecard disponibili</dt><dd>${Number(summary.weeks_available || 0)}</dd></div>
      <div><dt>Metriche ricorrenti</dt><dd>${Number(summary.recurring_worsening_metrics?.length || 0)}</dd></div>
      <div><dt>Metriche in miglioramento</dt><dd>${Number(summary.recurring_improving_metrics?.length || 0)}</dd></div>
      <div><dt>Customer Escalations recenti</dt><dd>${number(summary.recent_customer_escalations)}</dd></div>
    </dl>
    <section class="dsp-quality-history-current-focus"><h4>Focus attuale</h4>${focusMarkup(focus)}</section>
    <section aria-labelledby="qualityHistoryTrendsTitle"><h4 id="qualityHistoryTrendsTitle">Trend deterministici</h4>${trendSummaryMarkup(data)}</section>
    ${chartMarkup(data, metricKey)}
    ${timelineMarkup(data, metricKey)}
  </section>`;
}


export function qualityDriverHistoryMarkup(view = {}) {
  if (view.phase === "loading") return `<section class="dsp-quality-driver-history"><button type="button" class="secondary" data-quality-driver-history-back>← Torna ad Attenzione</button><div class="dsp-quality-selection-loading" role="status">Caricamento storico driver…</div></section>`;
  if (view.phase === "error") return `<section class="dsp-quality-driver-history"><button type="button" class="secondary" data-quality-driver-history-back>← Torna ad Attenzione</button><div class="dsp-quality-error-state" role="alert"><strong>Storico driver non disponibile</strong><span>${escapeHtml(view.error)}</span></div><button type="button" data-quality-driver-history-retry>Riprova</button></section>`;
  return availableMarkup(view);
}
