const escapeHtml = value => String(value ?? "")
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");


const RESULT_LABELS = {
  OPEN: "Aperto",
  REVIEW_DUE: "Da verificare",
  IMPROVED: "Migliorata",
  UNCHANGED: "Invariata",
  WORSENED: "Peggiorata",
  CLOSED: "Chiuso",
};


function number(value, unit = null) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
  const formatted = new Intl.NumberFormat("it-IT", {
    maximumFractionDigits: 2,
    signDisplay: unit === "pp" ? "exceptZero" : "auto",
  }).format(Number(value));
  if (unit === "percent" || unit === "%") return `${formatted}%`;
  return unit ? `${formatted} ${unit}` : formatted;
}


function period(value) {
  return value ? `W${value.week} · ${value.year}` : "—";
}


export function activeFollowup(followups, transporterExternalId, metricKey) {
  return (followups?.data?.items || []).find(item => (
    item.transporter_external_id === transporterExternalId
    && item.metric_key === metricKey
    && item.status !== "CLOSED"
  )) || null;
}


export function followupActionMarkup(
  followups,
  { transporterExternalId, metricKey, canWrite = false } = {},
) {
  const existing = activeFollowup(followups, transporterExternalId, metricKey);
  if (existing) {
    return `<button type="button" class="secondary quality-followup-marker" data-quality-followup-open="${escapeHtml(existing.id)}">Follow-up aperto</button>`;
  }
  if (!canWrite) return "";
  return `<button type="button" class="secondary" data-quality-followup-create="${escapeHtml(metricKey)}" data-quality-followup-driver="${escapeHtml(transporterExternalId)}">Crea follow-up</button>`;
}


export function followupSummaryMarkup(followups = {}) {
  const summary = followups.data?.summary || {};
  return `<dl class="dsp-quality-followup-summary" aria-label="Riepilogo follow-up Quality">
    <div><dt>Follow-up aperti</dt><dd>${Number(summary.open || 0)}</dd></div>
    <div><dt>Da verificare</dt><dd>${Number(summary.review_due || 0)}</dd></div>
    <div><dt>Migliorati</dt><dd>${Number(summary.improved || 0)}</dd></div>
    <div><dt>Peggiorati</dt><dd>${Number(summary.worsened || 0)}</dd></div>
  </dl>`;
}


function reviewMarkup(item) {
  const review = item.review || {};
  if (!review.period) return `<p class="quality-followup-review-message">${escapeHtml(review.message)}</p>`;
  return `<dl class="quality-followup-periods">
    <div><dt>Baseline ${period(item.baseline)}</dt><dd>${number(item.baseline?.value, item.metric_unit)}</dd></div>
    <div><dt>Review ${period(review.period)}</dt><dd>${number(review.period?.value, item.metric_unit)}</dd></div>
    <div><dt>Delta</dt><dd>${number(review.delta, review.delta_unit)}</dd></div>
  </dl><p class="quality-followup-review-message">${escapeHtml(review.message)}</p>`;
}


function followupCard(item, { history = false } = {}) {
  return `<article class="dsp-quality-followup-card" data-followup-status="${escapeHtml(item.status)}">
    <header><div><strong>${escapeHtml(item.driver_display_name)}</strong><span>${escapeHtml(item.transporter_external_id)}</span></div><span class="dsp-quality-followup-badge">${RESULT_LABELS[item.status] || item.status}</span></header>
    <div class="quality-followup-metric"><strong>${escapeHtml(item.metric_label)}</strong><span>Baseline ${period(item.baseline)} · ${number(item.baseline?.value, item.metric_unit)}</span></div>
    ${reviewMarkup(item)}
    <p class="quality-followup-note">${escapeHtml(item.note)}</p>
    ${history ? "" : `<button type="button" class="secondary" data-quality-followup-open="${escapeHtml(item.id)}">Vedi dettaglio</button>`}
  </article>`;
}


export function followupListMarkup(followups = {}, { history = false } = {}) {
  if (followups.phase === "loading") return '<div class="dsp-quality-selection-loading" role="status">Caricamento follow-up Quality…</div>';
  if (followups.phase === "error") return `<div class="dsp-quality-error-state" role="alert"><strong>Follow-up non disponibili</strong><span>${escapeHtml(followups.error)}</span></div>`;
  const items = followups.data?.items || [];
  if (!items.length) return '<p class="dsp-quality-neutral">Nessun follow-up Quality disponibile.</p>';
  return `<div class="dsp-quality-followup-list">${items.map(item => followupCard(item, { history })).join("")}</div>`;
}


export function historyFollowupsMarkup(followups = {}, { transporterExternalId, canWrite, focus = [] } = {}) {
  return `<section class="dsp-quality-history-followups" aria-labelledby="qualityHistoryFollowupsTitle">
    <div><div><p class="eyebrow">Azioni verificabili</p><h4 id="qualityHistoryFollowupsTitle">Follow-up Quality</h4></div></div>
    ${focus.length ? `<div class="quality-followup-focus-actions">${focus.map(item => `<div><span><strong>${escapeHtml(item.label)}</strong><small>${escapeHtml(item.reason)}</small></span>${followupActionMarkup(followups, { transporterExternalId, metricKey: item.metric_key, canWrite })}</div>`).join("")}</div>` : ""}
    ${followupListMarkup(followups, { history: true })}
  </section>`;
}


export function followupDialogMarkup(dialog = {}, { canWrite = false } = {}) {
  if (!dialog.phase || dialog.phase === "closed") return "";
  if (dialog.mode === "create") {
    const context = dialog.context || {};
    return `<div class="quality-followup-overlay" role="presentation"><section class="quality-followup-dialog" role="dialog" aria-modal="true" aria-labelledby="qualityFollowupDialogTitle">
      <header><div><p class="eyebrow">Follow-up Quality</p><h3 id="qualityFollowupDialogTitle">Crea follow-up</h3></div><button type="button" class="secondary" data-quality-followup-dialog-close aria-label="Chiudi">×</button></header>
      <dl class="quality-followup-create-baseline">
        <div><dt>Driver</dt><dd>${escapeHtml(context.driverDisplayName || context.transporterExternalId)}</dd></div>
        <div><dt>Metrica</dt><dd>${escapeHtml(context.metricLabel)}</dd></div>
        <div><dt>Valore attuale</dt><dd>${number(context.current, context.unit)}</dd></div>
        <div><dt>Settimana baseline</dt><dd>${escapeHtml(context.periodLabel)}</dd></div>
      </dl>
      <label>Nota<textarea data-quality-followup-note maxlength="1200" placeholder="Azione concordata con il driver…">${escapeHtml(dialog.note || "")}</textarea></label>
      ${dialog.error ? `<p class="dsp-quality-error" role="alert">${escapeHtml(dialog.error)}</p>` : ""}
      <footer><button type="button" class="secondary" data-quality-followup-dialog-close>Annulla</button><button type="button" data-quality-followup-save ${dialog.phase === "saving" || !(dialog.note || "").trim() ? "disabled" : ""}>${dialog.phase === "saving" ? "Creazione…" : "Crea follow-up"}</button></footer>
    </section></div>`;
  }
  const item = dialog.item;
  if (dialog.phase === "loading") return '<div class="quality-followup-overlay"><section class="quality-followup-dialog" role="dialog" aria-modal="true"><div class="dsp-quality-selection-loading">Caricamento follow-up…</div></section></div>';
  if (!item) return `<div class="quality-followup-overlay"><section class="quality-followup-dialog" role="dialog" aria-modal="true"><p class="dsp-quality-error">${escapeHtml(dialog.error || "Follow-up non disponibile.")}</p><button type="button" data-quality-followup-dialog-close>Chiudi</button></section></div>`;
  const closeAllowed = canWrite && item.status !== "CLOSED" && item.review?.state === "COMPARABLE";
  return `<div class="quality-followup-overlay" role="presentation"><section class="quality-followup-dialog" role="dialog" aria-modal="true" aria-labelledby="qualityFollowupDetailTitle">
    <header><div><p class="eyebrow">Follow-up Quality</p><h3 id="qualityFollowupDetailTitle">${escapeHtml(item.metric_label)}</h3></div><button type="button" class="secondary" data-quality-followup-dialog-close aria-label="Chiudi">×</button></header>
    ${followupCard(item, { history: true })}
    ${closeAllowed ? `<label>Nota finale <span>(facoltativa)</span><textarea data-quality-followup-close-note maxlength="600">${escapeHtml(dialog.closeNote || "")}</textarea></label>` : ""}
    ${dialog.error ? `<p class="dsp-quality-error" role="alert">${escapeHtml(dialog.error)}</p>` : ""}
    <footer><button type="button" class="secondary" data-quality-followup-dialog-close>Chiudi finestra</button>${closeAllowed ? `<button type="button" data-quality-followup-close ${dialog.phase === "closing" ? "disabled" : ""}>${dialog.phase === "closing" ? "Chiusura…" : "Chiudi follow-up"}</button>` : ""}</footer>
  </section></div>`;
}
