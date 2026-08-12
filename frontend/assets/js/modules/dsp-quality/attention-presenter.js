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


const STATUS_ORDER = Object.keys(STATUS_LABELS);


function summaryMarkup(data) {
  const counts = data?.summary?.statuses || {};
  const values = {
    DA_ATTENZIONARE: counts.da_attenzionare,
    DA_MIGLIORARE: counts.da_migliorare,
    IN_MIGLIORAMENTO: counts.in_miglioramento,
    STABILE: counts.stabile,
    SENZA_STORICO: counts.senza_storico,
  };
  return `<dl class="dsp-quality-attention-summary" aria-label="Riepilogo attenzione Quality">
    ${STATUS_ORDER.map(status => `<div data-attention-tone="${status}">
      <dt>${STATUS_LABELS[status]}</dt><dd>${Number(values[status] || 0)}</dd>
    </div>`).join("")}
  </dl>`;
}


function filtersMarkup(view) {
  const active = view.filter || "all";
  return `<div class="dsp-quality-attention-controls">
    <label>Ricerca
      <input type="search" data-quality-attention-search value="${escapeHtml(view.search || "")}" placeholder="Nome o Transporter ID" />
    </label>
    <div role="group" aria-label="Filtra stato attenzione">
      ${[["all", "Tutti"], ...STATUS_ORDER.map(status => [status, STATUS_LABELS[status]])]
        .map(([status, label]) => `<button type="button" class="secondary ${active === status ? "active" : ""}" data-quality-attention-filter="${status}" aria-pressed="${active === status}">${label}</button>`)
        .join("")}
    </div>
  </div>`;
}


function focusMarkup(items = []) {
  if (!items.length) return "";
  return `<ul class="dsp-quality-attention-focus" aria-label="Focus settimanali">
    ${items.map(item => `<li>
      <strong>${escapeHtml(item.label)}</strong>
      <span>${escapeHtml(item.reason)}</span>
    </li>`).join("")}
  </ul>`;
}


function driverCard(driver) {
  return `<article class="dsp-quality-attention-card" data-attention-status="${driver.status}">
    <header>
      <div><strong>${escapeHtml(driver.display_name)}</strong><span>${escapeHtml(driver.transporter_external_id)}</span></div>
      <span class="dsp-quality-attention-badge">${STATUS_LABELS[driver.status]}</span>
    </header>
    <dl>
      <div><dt>Peggiorate</dt><dd>${Number(driver.worsened_metrics || 0)}</dd></div>
      <div><dt>Migliorate</dt><dd>${Number(driver.improved_metrics || 0)}</dd></div>
      <div><dt>Confrontabili</dt><dd>${Number(driver.comparable_metrics || 0)}</dd></div>
    </dl>
    ${focusMarkup(driver.focus)}
    <p class="dsp-quality-attention-reason">${escapeHtml(driver.reasons?.join(" ") || "Nessuna evidenza disponibile.")}</p>
    <button type="button" class="secondary" data-quality-attention-driver="${escapeHtml(driver.transporter_external_id)}">Vedi andamento</button>
  </article>`;
}


function dspSignalsMarkup(signals = []) {
  if (!signals.length) return '<p class="dsp-quality-neutral">Nessuna metrica DSP richiede attenzione per la settimana selezionata.</p>';
  return `<div class="dsp-quality-dsp-signals">${signals.map(signal => `<article>
    <header><strong>${escapeHtml(signal.label)}</strong><span>${escapeHtml(signal.status)}</span></header>
    <p>${escapeHtml(signal.reason)}</p>
    <dl>
      <div><dt>Corrente</dt><dd>${escapeHtml(signal.current ?? "—")}</dd></div>
      <div><dt>Precedente</dt><dd>${escapeHtml(signal.previous ?? "—")}</dd></div>
      <div><dt>Delta</dt><dd>${escapeHtml(signal.delta ?? "—")}</dd></div>
    </dl>
  </article>`).join("")}</div>`;
}


function visibleDrivers(view) {
  const query = String(view.search || "").trim().toLocaleLowerCase("it");
  const filtered = (view.data?.drivers || []).filter(driver => {
    if (view.filter !== "all" && driver.status !== view.filter) return false;
    if (!query) return true;
    return `${driver.display_name} ${driver.transporter_external_id}`
      .toLocaleLowerCase("it").includes(query);
  });
  const groups = new Map();
  for (const driver of filtered) {
    const current = groups.get(driver.status) || [];
    if (current.length < 10) current.push(driver);
    groups.set(driver.status, current);
  }
  return STATUS_ORDER.flatMap(status => groups.get(status) || []);
}


export function qualityAttentionMarkup(view = {}) {
  if (view.phase === "loading") return '<div class="dsp-quality-selection-loading" role="status">Calcolo delle attenzioni operative…</div>';
  if (view.phase === "error") return `<div class="dsp-quality-error-state" role="alert"><strong>Attenzione Quality non disponibile</strong><span>${escapeHtml(view.error)}</span></div><button type="button" data-quality-attention-retry>Riprova</button>`;
  const data = view.data;
  if (!data?.available) return '<div class="dsp-quality-neutral" role="status">Nessun dato Quality disponibile.</div>';
  const drivers = visibleDrivers(view);
  return `<section class="dsp-quality-attention" aria-labelledby="qualityAttentionTitle">
    <header><p class="eyebrow">Lettura operativa</p><h3 id="qualityAttentionTitle">Attenzione Quality</h3><p>Segnali oggettivi derivati dalla settimana selezionata e dalla precedente scorecard realmente disponibile.</p></header>
    ${summaryMarkup(data)}
    <section class="dsp-quality-dsp-attention" aria-labelledby="qualityDspSignalsTitle">
      <h4 id="qualityDspSignalsTitle">Attenzioni DSP</h4>${dspSignalsMarkup(data.dsp_signals)}
    </section>
    ${filtersMarkup(view)}
    <section class="dsp-quality-driver-attention" aria-labelledby="qualityDriverAttentionTitle">
      <div><h4 id="qualityDriverAttentionTitle">Driver</h4><span>Massimo 10 risultati per categoria</span></div>
      ${drivers.length ? `<div class="dsp-quality-attention-grid">${drivers.map(driverCard).join("")}</div>` : '<p class="dsp-quality-neutral">Nessun driver corrisponde ai filtri.</p>'}
    </section>
  </section>`;
}

