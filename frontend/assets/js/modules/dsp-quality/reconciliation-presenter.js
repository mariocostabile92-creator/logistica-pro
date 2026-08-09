const escapeHtml = value => String(value ?? "")
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");


const STATUS_LABELS = {
  MATCHED: "Associato",
  UNMAPPED: "Da associare",
  AMBIGUOUS: "Ambiguo",
};


export function filterReconciliationRows(rows = [], filter = "all", search = "") {
  const expected = {
    matched: "MATCHED",
    unmapped: "UNMAPPED",
    ambiguous: "AMBIGUOUS",
  }[filter] || null;
  const needle = String(search || "").trim().toLocaleLowerCase("it");
  return rows.filter(row => (
    (!expected || row.mapping_status === expected)
    && (!needle || `${row.transporter_external_id} ${row.workforce_display_name || ""}`
      .toLocaleLowerCase("it").includes(needle))
  ));
}


function summaryMarkup(summary = {}) {
  return `
    <dl class="dsp-quality-reconciliation-summary" aria-label="Riepilogo associazioni">
      <div><dt>Totali</dt><dd>${escapeHtml(summary.total ?? 0)}</dd></div>
      <div><dt>Associati</dt><dd>${escapeHtml(summary.matched ?? 0)}</dd></div>
      <div><dt>Da associare</dt><dd>${escapeHtml(summary.unmapped ?? 0)}</dd></div>
      <div><dt>Ambigui</dt><dd>${escapeHtml(summary.ambiguous ?? 0)}</dd></div>
    </dl>
  `;
}


function historyMarkup(history = []) {
  if (!history.length) return '<p class="dsp-quality-reconciliation-neutral">Nessuna modifica precedente.</p>';
  const labels = {
    mapping_created: "Associazione creata",
    mapping_replaced: "Associazione modificata",
    mapping_removed: "Associazione rimossa",
  };
  return `<ol class="dsp-quality-mapping-history">${history.map(item => `
    <li>
      <strong>${escapeHtml(labels[item.action] || item.action)}</strong>
      <span>${escapeHtml(item.previous_workforce_display_name || "—")} → ${escapeHtml(item.new_workforce_display_name || "—")}</span>
      <small>${escapeHtml(item.actor)} · ${escapeHtml(item.created_at)}</small>
    </li>
  `).join("")}</ol>`;
}


function candidateMarkup(state) {
  if (state.candidatePhase === "loading") {
    return '<p class="dsp-quality-reconciliation-neutral" role="status">Ricerca driver…</p>';
  }
  if (state.candidatePhase === "available" && !state.candidates.length) {
    return '<p class="dsp-quality-reconciliation-neutral" role="status">Nessun driver Workforce trovato.</p>';
  }
  return `<div class="dsp-quality-workforce-candidates" role="listbox" aria-label="Risultati Workforce">${state.candidates.map((candidate, index) => `
    <button type="button" role="option"
      aria-selected="${state.selectedCandidate?.workforce_member_id === candidate.workforce_member_id}"
      data-quality-candidate-index="${index}"
      data-quality-candidate-id="${candidate.workforce_member_id}">
      <strong>${escapeHtml(candidate.display_name)}</strong>
      <span>${escapeHtml(candidate.station || "Station non indicata")} · ${escapeHtml(candidate.contract || "Contratto non indicato")}</span>
      <small>${escapeHtml(candidate.external_identifier || "")}${candidate.active ? "" : " · Non attivo"}</small>
    </button>
  `).join("")}</div>`;
}


function associationPanel(row, state) {
  if (!row) return "";
  const selected = state.selectedCandidate;
  const action = row.mapping_status === "MATCHED" ? "Modifica associazione" : "Associa driver";
  return `
    <section class="dsp-quality-association-panel" role="dialog" aria-modal="true" aria-labelledby="qualityAssociationTitle">
      <header>
        <div><p class="eyebrow">Transporter</p><h3 id="qualityAssociationTitle">${escapeHtml(action)}</h3><strong>${escapeHtml(row.transporter_external_id)}</strong></div>
        <button type="button" class="secondary" data-quality-association-close aria-label="Chiudi selettore">Chiudi</button>
      </header>
      ${row.mapping_status === "MATCHED" ? `<p class="dsp-quality-current-mapping">Associazione attuale: <strong>${escapeHtml(row.workforce_display_name)}</strong></p>` : ""}
      <label for="qualityWorkforceSearch">Cerca driver Workforce</label>
      <input id="qualityWorkforceSearch" type="search" data-quality-candidate-search
        value="${escapeHtml(state.candidateSearch)}" placeholder="Nome, ID o station" autocomplete="off" />
      ${candidateMarkup(state)}
      ${selected ? `
        <div class="dsp-quality-mapping-confirmation" role="status">
          <span>${escapeHtml(row.transporter_external_id)}</span><strong aria-hidden="true">→</strong><span>${escapeHtml(selected.display_name)}</span>
        </div>
        <button type="button" class="primary" data-quality-mapping-confirm>Conferma associazione</button>
      ` : '<p class="dsp-quality-reconciliation-neutral">Seleziona un risultato. Nessuna associazione viene salvata automaticamente.</p>'}
      ${row.mapping_status === "MATCHED" ? '<button type="button" class="danger-outline" data-quality-mapping-remove>Rimuovi associazione</button>' : ""}
      ${state.error ? `<p class="dsp-quality-reconciliation-error" role="alert">${escapeHtml(state.error)}</p>` : ""}
      <details class="dsp-quality-mapping-history-wrap">
        <summary>Cronologia associazione</summary>
        ${historyMarkup(state.history)}
      </details>
    </section>
  `;
}


function listMarkup(state) {
  const rows = filterReconciliationRows(
    state.data?.rows || [],
    state.filter,
    state.search,
  );
  if (!rows.length) {
    return '<p class="dsp-quality-reconciliation-empty" role="status">Nessuna associazione corrisponde ai filtri.</p>';
  }
  return `<div class="dsp-quality-reconciliation-list">${rows.map(row => `
    <article data-mapping-status="${escapeHtml(row.mapping_status)}">
      <div><span>Transporter</span><strong>${escapeHtml(row.transporter_external_id)}</strong><small>${row.delivered ? `${escapeHtml(row.delivered)} consegne` : ""}</small></div>
      <div><span>Stato</span><strong>${escapeHtml(STATUS_LABELS[row.mapping_status] || "Da associare")}</strong></div>
      <div><span>Driver</span><strong>${escapeHtml(row.workforce_display_name || "—")}</strong></div>
      <button type="button" data-quality-reconciliation-row="${escapeHtml(row.transporter_external_id)}">${row.mapping_status === "MATCHED" ? "Modifica" : row.mapping_status === "AMBIGUOUS" ? "Risolvi" : "Associa"}</button>
    </article>
  `).join("")}</div>`;
}


export function reconciliationMarkup(state = {}) {
  if (!state.open) return "";
  if (["idle", "loading"].includes(state.phase)) {
    return '<section class="dsp-quality-reconciliation-workspace" role="status" aria-busy="true">Caricamento associazioni…</section>';
  }
  if (state.phase === "error") {
    return `<section class="dsp-quality-reconciliation-workspace" role="alert"><p>${escapeHtml(state.error)}</p><button type="button" data-quality-reconciliation-retry>Riprova</button></section>`;
  }
  const active = (state.data?.rows || []).find(
    row => row.transporter_external_id === state.activeExternalId,
  );
  return `
    <section class="dsp-quality-reconciliation-workspace" aria-labelledby="qualityReconciliationTitle">
      <header class="dsp-quality-reconciliation-heading">
        <div><p class="eyebrow">Quality · Driver</p><h2 id="qualityReconciliationTitle">Associazioni Transporter</h2><p>Collega manualmente gli ID Amazon ai driver Workforce verificati.</p></div>
        <button type="button" class="secondary" data-quality-reconciliation-close>Chiudi</button>
      </header>
      ${summaryMarkup(state.data?.summary)}
      <div class="dsp-quality-reconciliation-controls">
        <div role="group" aria-label="Filtra associazioni">${[["all", "Tutti"], ["unmapped", "Da associare"], ["matched", "Associati"], ["ambiguous", "Ambigui"]].map(([key, label]) => `
          <button type="button" data-quality-reconciliation-filter="${key}" aria-pressed="${state.filter === key}" class="${state.filter === key ? "active" : ""}">${label}</button>
        `).join("")}</div>
        <label>Ricerca<input type="search" data-quality-reconciliation-search value="${escapeHtml(state.search)}" placeholder="Transporter ID o driver" /></label>
      </div>
      ${listMarkup(state)}
      ${associationPanel(active, state)}
    </section>
  `;
}

