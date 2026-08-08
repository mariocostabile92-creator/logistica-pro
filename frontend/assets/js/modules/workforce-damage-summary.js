import { listDamageCases } from "../api.js?v=6";
import { can } from "../auth/state.js";

function summaryValues(summary = {}) {
  return {
    total: Number(summary.total_cases || 0),
    open: Number(summary.open_cases || 0),
    closed: Number(summary.closed_cases || 0),
  };
}

export function workforceDamageSummaryMarkup(summary) {
  const values = summaryValues(summary);
  if (values.total === 0) {
    return `<div class="workforce-damage-summary-empty">
      <p>Nessuna pratica danno attribuita.</p>
      <button type="button" class="quiet" data-workforce-damage-history>Apri Fleet → Danni</button>
    </div>`;
  }
  return `<dl class="workforce-damage-summary-metrics">
    <div><dt>Pratiche attribuite</dt><dd>${values.total}</dd></div>
    <div><dt>Aperte</dt><dd>${values.open}</dd></div>
    <div><dt>Chiuse</dt><dd>${values.closed}</dd></div>
  </dl>
  <button type="button" class="quiet" data-workforce-damage-history>Apri storico in Fleet</button>`;
}

export function openDamageHistoryInFleet(driverId, target = document) {
  const canonicalId = Number(driverId);
  if (!Number.isInteger(canonicalId) || canonicalId <= 0) return false;
  const onViewChanged = (event) => {
    if (event.detail?.view !== "fleet") return;
    target.removeEventListener("workspace:view-changed", onViewChanged);
    target.dispatchEvent(new CustomEvent("damage:open", {
      detail: { driverId: canonicalId },
    }));
  };
  target.addEventListener("workspace:view-changed", onViewChanged);
  target.dispatchEvent(new CustomEvent("workspace:navigate", {
    detail: { view: "fleet" },
  }));
  return true;
}

export function createWorkforceDamageSummary({
  container = document.getElementById("workforceDamageSummary"),
  loadSummary = (memberId) => listDamageCases({ workforce_member_id: memberId }),
  canReadFleet = () => can("fleet:read"),
} = {}) {
  let requestVersion = 0;
  let selectedMemberId = null;

  container.addEventListener("click", (event) => {
    if (!event.target.closest("[data-workforce-damage-history]")) return;
    openDamageHistoryInFleet(selectedMemberId);
  });

  function hide() {
    requestVersion += 1;
    selectedMemberId = null;
    container.hidden = true;
    container.replaceChildren();
  }

  async function show(member) {
    hide();
    if (!canReadFleet()) return;
    const memberId = Number(member?.workforce_member_id);
    if (!Number.isInteger(memberId) || memberId <= 0) return;
    selectedMemberId = memberId;
    const version = requestVersion;
    container.hidden = false;
    container.innerHTML = `<h4>Danni</h4><p class="section-note" role="status">Caricamento dati danni…</p>`;
    try {
      const response = await loadSummary(memberId);
      if (version !== requestVersion || selectedMemberId !== memberId) return;
      container.innerHTML = `<h4>Danni</h4>${workforceDamageSummaryMarkup(response.summary)}`;
    } catch {
      if (version !== requestVersion || selectedMemberId !== memberId) return;
      container.innerHTML = `<h4>Danni</h4><p class="section-note" role="status">Dati danni non disponibili.</p>`;
    }
  }

  return { hide, show };
}
