import {
  exportDistributionBatchCsv,
  getDistribution,
  getRecipientAccessLink,
  getSharedPortal,
  prepareDistribution,
  prepareDistributionBatch,
  regenerateRecipientAccess,
  regenerateSharedPortal,
  revokeRecipientAccess,
  revokeSharedPortal,
  prepareSharedPortal,
} from "./driver-shift-planning-api.js?v=8";
import {
  filterDistributionRecipients,
  renderManualShareRecipients,
  renderDistributionRecipients,
  renderDistributionSummary,
} from "./driver-shift-distribution-presenter.js?v=4";
import { initDriverShiftCredentials } from "./driver-shift-credentials.js?v=2";
import {
  buildDriverShiftGroupMessage,
  copyGroupMessage,
} from "./driver-shift-group-message.js?v=1";
import { byId, setLoading } from "../utils/dom.js";
import { userErrorPresentation } from "../utils/errors.js";


async function copyText(value) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(value);
    return;
  }
  const input = document.createElement("textarea");
  input.value = value;
  input.setAttribute("readonly", "");
  input.style.position = "fixed";
  input.style.opacity = "0";
  document.body.append(input);
  input.select();
  document.execCommand("copy");
  input.remove();
}


function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}


function isoDateUtc(value) {
  return value.toISOString().slice(0, 10);
}


function addIsoDays(value, days) {
  const [year, month, day] = value.split("-").map(Number);
  return isoDateUtc(new Date(Date.UTC(year, month - 1, day + days)));
}


export function distributionWindowForAnchor(anchor) {
  const fallback = isoDateUtc(new Date());
  const value = /^\d{4}-\d{2}-\d{2}$/.test(anchor || "") ? anchor : fallback;
  const [year, month, day] = value.split("-").map(Number);
  const weekday = new Date(Date.UTC(year, month - 1, day)).getUTCDay();
  const mondayOffset = (weekday + 6) % 7;
  const periodStart = addIsoDays(value, -mondayOffset);
  return { period_start: periodStart, period_end: addIsoDays(periodStart, 6) };
}


export function initDriverShiftDistribution({ getDefaultWindow = () => null } = {}) {
  const state = {
    planning: null,
    model: null,
    filter: "",
    search: "",
    request: 0,
    selected: new Set(),
    selectionDirty: false,
    prepared: null,
    portal: null,
    credentialModel: null,
    credentialStatuses: new Map(),
    newRevision: false,
    pendingWindow: null,
    windowTrigger: null,
  };
  const elements = {
    entry: byId("driverShiftDistributeBtn"),
    section: byId("driverShiftDistributionSection"),
    summary: byId("driverShiftDistributionSummary"),
    recipients: byId("driverShiftDistributionRecipients"),
    manualRecipients: byId("driverShiftManualRecipients"),
    weekContext: byId("driverShiftDistributionWeekContext"),
    groupPeriod: byId("driverShiftGroupPeriod"),
    trackingSummary: byId("driverShiftTrackingSummary"),
    status: byId("driverShiftDistributionStatus"),
    search: byId("driverShiftDistributionSearch"),
    refresh: byId("driverShiftDistributionRefresh"),
    selectAll: byId("driverShiftSelectAllReady"),
    openWorkforce: byId("driverShiftOpenWorkforce"),
    actions: byId("driverShiftBatchActions"),
    selectedCount: byId("driverShiftSelectedCount"),
    prepareBatch: byId("driverShiftPrepareBatch"),
    exportBatch: byId("driverShiftExportBatch"),
    prepared: byId("driverShiftPreparedBatch"),
    preparedCount: byId("driverShiftPreparedCount"),
    copyBatch: byId("driverShiftCopyBatch"),
    exportPrepared: byId("driverShiftExportPrepared"),
    backRecipients: byId("driverShiftBackRecipients"),
    portal: byId("driverShiftPortal"),
    portalEmpty: byId("driverShiftPortalEmpty"),
    portalDetails: byId("driverShiftPortalDetails"),
    portalInput: byId("driverShiftPortalLink"),
    portalState: byId("driverShiftPortalState"),
    portalExpiry: byId("driverShiftPortalExpiry"),
    portalPrepare: byId("driverShiftPortalPrepare"),
    portalCopy: byId("driverShiftPortalCopy"),
    portalRevoke: byId("driverShiftPortalRevoke"),
    portalRegenerate: byId("driverShiftPortalRegenerate"),
    groupReadiness: byId("driverShiftGroupReadiness"),
    groupSummary: byId("driverShiftGroupSummary"),
    groupWarning: byId("driverShiftGroupWarning"),
    prepareMissingAccesses: byId("driverShiftPrepareMissingAccesses"),
    revisionNotice: byId("driverShiftRevisionNotice"),
    groupCopy: byId("driverShiftGroupMessageCopy"),
    messageFallback: byId("driverShiftMessageFallback"),
    messageFallbackText: byId("driverShiftMessageFallbackText"),
    windowDialog: byId("driverShiftDistributionWindowDialog"),
    windowDate: byId("driverShiftDistributionWeek"),
    windowLabel: byId("driverShiftDistributionWindowLabel"),
    windowError: byId("driverShiftDistributionWindowError"),
    windowCancel: byId("driverShiftDistributionWindowCancel"),
    windowConfirm: byId("driverShiftDistributionWindowConfirm"),
  };

  function status(message = "", tone = "") {
    elements.status.textContent = message;
    elements.status.dataset.tone = tone;
  }

  const credentialsController = initDriverShiftCredentials({
    status,
    onChanged(model, statusMap) {
      state.credentialModel = model;
      state.credentialStatuses = statusMap;
      if (state.model) render();
    },
  });

  function readyRecipients() {
    return (state.model?.recipients || []).filter((recipient) => (
      recipient.readiness === "READY" && !recipient.access_revoked
    ));
  }

  function syncSelection({ reset = false } = {}) {
    const readyIds = new Set(readyRecipients().map((recipient) => recipient.id));
    if (reset || !state.selectionDirty) state.selected = readyIds;
    else state.selected = new Set([...state.selected].filter((id) => readyIds.has(id)));
  }

  function render() {
    if (!state.model) {
      elements.section.hidden = true;
      return;
    }
    elements.section.hidden = false;
    renderPortal();
    syncSelection();
    renderDistributionSummary(elements.summary, state.model.summary, state.credentialModel?.summary);
    renderDistributionRecipients(
      elements.recipients,
      filterDistributionRecipients(
        state.model.recipients, state.filter, state.search, state.credentialStatuses,
      ),
      state.credentialStatuses,
    );
    renderManualShareRecipients(elements.manualRecipients, state.model.recipients, state.selected);
    elements.selectedCount.textContent = String(state.selected.size);
    elements.actions.hidden = state.selected.size === 0 || Boolean(state.prepared);
    elements.prepared.hidden = !state.prepared;
    elements.preparedCount.textContent = String(state.prepared?.prepared_count || 0);
    document.querySelectorAll("[data-distribution-filter]").forEach((button) => {
      const active = button.dataset.distributionFilter === state.filter;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", String(active));
    });
  }

  function renderPortal() {
    elements.portal.hidden = !state.model;
    if (!state.model) return;
    const active = state.portal?.status === "ACTIVE" && Boolean(state.portal.access_url);
    elements.portalEmpty.hidden = Boolean(state.portal);
    elements.portalDetails.hidden = !state.portal;
    elements.portalInput.value = active ? state.portal.access_url : "";
    elements.portalState.textContent = state.portal?.status || "NON CREATO";
    elements.portalState.dataset.status = state.portal?.status || "MISSING";
    elements.portalExpiry.textContent = state.portal?.expires_at
      ? `Valido fino al ${new Intl.DateTimeFormat("it-IT", { dateStyle: "medium" }).format(new Date(state.portal.expires_at))}`
      : "";
    elements.portalCopy.disabled = !active;
    elements.portalRevoke.disabled = !active;
    elements.portalRegenerate.hidden = !state.portal;
    renderWeekContext();
    renderGroupShare();
  }

  function renderMetricSummary(element, values) {
    const fragment = document.createDocumentFragment();
    values.forEach(([label, value]) => {
      const item = document.createElement("div");
      const term = document.createElement("dt");
      const detail = document.createElement("dd");
      term.textContent = label;
      detail.textContent = String(value ?? 0);
      item.append(term, detail);
      fragment.append(item);
    });
    element.replaceChildren(fragment);
  }

  function renderGroupSummary(summary, credentialsReady, credentialsMissing) {
    const values = [
      ["Destinatari settimana", summary?.recipients_total],
      ["Accessi pronti", credentialsReady],
      ["Accessi da preparare", credentialsMissing],
    ];
    renderMetricSummary(elements.groupSummary, values);
    renderMetricSummary(elements.trackingSummary, [
      ["Visualizzati", summary?.opened],
      ["Presa visione", summary?.acknowledged],
      ["Non visualizzati", summary?.not_opened],
    ]);
  }

  function formatWeek(periodStart, periodEnd, { includeYear = true } = {}) {
    if (!periodStart || !periodEnd) return "Settimana non disponibile";
    const start = new Date(`${periodStart}T12:00:00Z`);
    const end = new Date(`${periodEnd}T12:00:00Z`);
    const startDay = new Intl.DateTimeFormat("it-IT", { day: "numeric" }).format(start);
    const endFormat = new Intl.DateTimeFormat("it-IT", {
      day: "numeric", month: "long", ...(includeYear ? { year: "numeric" } : {}),
    });
    return `${startDay}–${endFormat.format(end)}`;
  }

  function renderWeekContext() {
    const distribution = state.model?.distribution;
    const total = Number(state.model?.summary?.recipients_total || 0);
    const week = formatWeek(distribution?.period_start, distribution?.period_end);
    elements.weekContext.textContent = `Settimana: ${week} · ${total} ${total === 1 ? "destinatario" : "destinatari"}`;
    elements.groupPeriod.textContent = `Settimana ${formatWeek(distribution?.period_start, distribution?.period_end, { includeYear: false })}`;
  }

  function renderGroupShare() {
    const credentialSummary = state.credentialModel?.summary;
    const distributionSummary = state.model?.summary;
    const total = Number(credentialSummary?.recipients_total ?? distributionSummary?.recipients_total ?? 0);
    const ready = Number(credentialSummary?.credentials_ready ?? 0);
    const notReady = Math.max(0, total - ready);
    elements.groupReadiness.textContent = credentialSummary
      ? (notReady === 0
        ? "Tutti i driver della settimana hanno un accesso personale."
        : `${notReady} ${notReady === 1 ? "driver non ha" : "driver non hanno"} ancora un accesso personale.`)
      : "Verifica accessi personali...";
    elements.groupWarning.hidden = !credentialSummary || notReady === 0;
    elements.groupWarning.textContent = notReady === 1
      ? "1 driver non ha ancora un accesso personale."
      : `${notReady} driver non hanno ancora un accesso personale.`;
    elements.prepareMissingAccesses.hidden = !credentialSummary || Number(credentialSummary.missing || 0) === 0;
    elements.prepareMissingAccesses.textContent = `Prepara ${Number(credentialSummary?.missing || 0)} accessi`;
    elements.groupCopy.disabled = !credentialSummary || ready === 0;
    elements.revisionNotice.hidden = !state.newRevision;
    renderGroupSummary(distributionSummary, ready, notReady);
  }

  function groupMessage() {
    return buildDriverShiftGroupMessage({
      periodStart: state.model.distribution.period_start,
      periodEnd: state.model.distribution.period_end,
      sharedPortalUrl: state.portal.access_url,
    });
  }

  function showMessageFallback(message) {
    elements.messageFallbackText.value = message;
    elements.messageFallback.hidden = false;
    elements.messageFallbackText.focus();
    elements.messageFallbackText.select();
  }

  function clearMessageFallback() {
    elements.messageFallback.hidden = true;
    elements.messageFallbackText.value = "";
  }

  async function ensureActivePortal() {
    if (state.portal?.status === "ACTIVE" && state.portal.access_url) return true;
    if (state.portal) {
      status("Il link condiviso non è attivo. Rigeneralo prima di copiare il messaggio.", "error");
      return false;
    }
    state.portal = await prepareSharedPortal(state.model.distribution.id);
    renderPortal();
    const active = state.portal?.status === "ACTIVE" && Boolean(state.portal.access_url);
    if (!active) status("Il link condiviso non è attivo. Rigeneralo prima di copiare il messaggio.", "error");
    return active;
  }

  async function copyGroupMessageForWhatsApp() {
    const credentialSummary = state.credentialModel?.summary;
    if (!credentialSummary || Number(credentialSummary.credentials_ready || 0) === 0) {
      status("Prepara almeno un accesso personale prima di copiare il messaggio.", "error");
      return;
    }
    setLoading(elements.groupCopy, true, "Preparazione...");
    try {
      if (!await ensureActivePortal()) return;
      const message = groupMessage();
      elements.messageFallback.hidden = true;
      elements.messageFallbackText.value = "";
      if (await copyGroupMessage(message)) {
        status("Messaggio copiato. Ora puoi incollarlo nel gruppo WhatsApp.", "success");
      } else {
        showMessageFallback(message);
        status("Copia automatica non disponibile. Copia il messaggio dal campo mostrato.", "");
      }
    } catch (error) {
      status(userErrorPresentation("workforce.driver-shift-group-message", error).message, "error");
    } finally {
      setLoading(elements.groupCopy, false);
      renderGroupShare();
    }
  }

  async function loadPortal({ quietMissing = false } = {}) {
    if (!state.model) return;
    try {
      state.portal = await getSharedPortal(state.model.distribution.id);
    } catch (error) {
      if (quietMissing && error?.status === 404) state.portal = null;
      else throw error;
    }
  }

  async function load({ quietMissing = false } = {}) {
    if (!state.planning || state.planning.status !== "ACTIVE") return;
    const request = ++state.request;
    try {
      const model = await getDistribution(state.planning.id);
      if (request !== state.request) return;
      const changed = state.model?.distribution?.id !== model.distribution.id;
      state.model = model;
      if (changed) {
        state.selectionDirty = false;
        state.prepared = null;
        state.portal = null;
        state.credentialModel = null;
        clearMessageFallback();
        syncSelection({ reset: true });
      }
      await loadPortal({ quietMissing: true });
      credentialsController.setDistribution(state.model.distribution);
      render();
    } catch (error) {
      if (request !== state.request) return;
      if (quietMissing && error?.status === 404) {
        state.model = null;
        render();
        return;
      }
      status(userErrorPresentation("workforce.driver-shift-distribution", error).message, "error");
    }
  }

  async function preparePortal() {
    setLoading(elements.portalPrepare, true, "Creazione...");
    try {
      state.portal = await prepareSharedPortal(state.model.distribution.id);
      renderPortal();
      status("Link condiviso pronto. Nessun turno personale è visibile nel portale.", "success");
    } catch (error) {
      status(userErrorPresentation("workforce.driver-shift-portal", error).message, "error");
    } finally {
      setLoading(elements.portalPrepare, false);
    }
  }

  async function copyPortal() {
    if (!state.portal?.access_url) return;
    setLoading(elements.portalCopy, true, "Copia...");
    try {
      await copyText(state.portal.access_url);
      status("Link condiviso copiato. Puoi condividerlo una sola volta con tutti i driver.", "success");
    } finally {
      setLoading(elements.portalCopy, false);
    }
  }

  async function revokePortal() {
    setLoading(elements.portalRevoke, true, "Revoca...");
    try {
      state.portal = await revokeSharedPortal(state.model.distribution.id);
      renderPortal();
      status("Portale condiviso revocato.", "success");
    } catch (error) {
      status(userErrorPresentation("workforce.driver-shift-portal", error).message, "error");
    } finally {
      setLoading(elements.portalRevoke, false);
    }
  }

  async function regeneratePortal() {
    setLoading(elements.portalRegenerate, true, "Rigenera...");
    try {
      state.portal = await regenerateSharedPortal(state.model.distribution.id);
      renderPortal();
      status("Nuovo link condiviso pronto. Il precedente non è più valido.", "success");
    } catch (error) {
      status(userErrorPresentation("workforce.driver-shift-portal", error).message, "error");
    } finally {
      setLoading(elements.portalRegenerate, false);
    }
  }

  function selectedWindowIsValid(window) {
    return Boolean(
      window
      && state.planning
      && window.period_start >= state.planning.period_start
      && window.period_end <= state.planning.period_end
    );
  }

  function syncWindow(anchor) {
    const window = distributionWindowForAnchor(anchor);
    const valid = selectedWindowIsValid(window);
    state.pendingWindow = valid ? window : null;
    elements.windowDate.value = window.period_start;
    elements.windowLabel.textContent = `${window.period_start} - ${window.period_end}`;
    elements.windowError.hidden = valid;
    elements.windowConfirm.disabled = !valid;
  }

  function openWindowDialog() {
    if (!state.planning) return;
    const selected = getDefaultWindow() || {};
    state.windowTrigger = document.activeElement;
    elements.windowDate.min = state.planning.period_start;
    elements.windowDate.max = state.planning.period_end;
    syncWindow(selected.dateFrom || selected.period_start || isoDateUtc(new Date()));
    elements.windowDialog.showModal();
    elements.windowDate.focus();
  }

  function closeWindowDialog() {
    elements.windowDialog.close();
  }

  async function prepare() {
    if (!state.planning || !state.pendingWindow) return;
    setLoading(elements.windowConfirm, true, "Preparazione...");
    try {
      state.model = await prepareDistribution(state.planning.id, state.pendingWindow);
      state.selectionDirty = false;
      state.prepared = null;
      clearMessageFallback();
      syncSelection({ reset: true });
      credentialsController.setDistribution(state.model.distribution);
      render();
      closeWindowDialog();
      status("Distribuzione pronta. Nessun messaggio è stato inviato.", "success");
    } catch (error) {
      status(userErrorPresentation("workforce.driver-shift-distribution", error).message, "error");
    } finally {
      setLoading(elements.windowConfirm, false);
    }
  }

  async function copyRecipientLink(recipientId, button) {
    setLoading(button, true, "Copia...");
    try {
      const link = await getRecipientAccessLink(state.model.distribution.id, recipientId);
      await copyText(link.access_url);
      status("Link personale copiato. Condividilo soltanto con il destinatario.", "success");
    } catch (error) {
      status(userErrorPresentation("workforce.driver-shift-access", error).message, "error");
    } finally {
      setLoading(button, false);
    }
  }

  async function revoke(recipientId, button) {
    setLoading(button, true, "Revoca...");
    try {
      state.model = await revokeRecipientAccess(state.model.distribution.id, recipientId);
      state.prepared = null;
      render();
      status("Accesso personale revocato.", "success");
    } catch (error) {
      status(userErrorPresentation("workforce.driver-shift-access", error).message, "error");
    } finally {
      setLoading(button, false);
    }
  }

  async function regenerate(recipientId, button) {
    setLoading(button, true, "Rigenera...");
    try {
      const link = await regenerateRecipientAccess(state.model.distribution.id, recipientId);
      await copyText(link.access_url);
      state.prepared = null;
      await load();
      status("Nuovo link copiato. Il precedente non è più valido.", "success");
    } catch (error) {
      status(userErrorPresentation("workforce.driver-shift-access", error).message, "error");
    } finally {
      setLoading(button, false);
    }
  }

  async function prepareBatch() {
    if (!state.selected.size) return;
    setLoading(elements.prepareBatch, true, "Preparazione...");
    try {
      state.prepared = await prepareDistributionBatch(
        state.model.distribution.id, [...state.selected],
      );
      render();
      status(`Batch pronto per ${state.prepared.prepared_count} destinatari. Nessun invio eseguito.`, "success");
    } catch (error) {
      status(userErrorPresentation("workforce.driver-shift-batch", error).message, "error");
    } finally {
      setLoading(elements.prepareBatch, false);
    }
  }

  async function exportCsv(button, recipientIds = [...state.selected]) {
    if (!recipientIds.length) return;
    setLoading(button, true, "Esportazione...");
    try {
      const result = await exportDistributionBatchCsv(state.model.distribution.id, recipientIds);
      downloadBlob(result.blob, result.filename);
      status("CSV personale generato. Nessun destinatario è stato marcato come inviato.", "success");
    } catch (error) {
      status(userErrorPresentation("workforce.driver-shift-batch", error).message, "error");
    } finally {
      setLoading(button, false);
    }
  }

  elements.entry.addEventListener("click", openWindowDialog);
  elements.windowDate.addEventListener("change", () => syncWindow(elements.windowDate.value));
  elements.windowCancel.addEventListener("click", closeWindowDialog);
  elements.windowConfirm.addEventListener("click", () => void prepare());
  elements.windowDialog.addEventListener("close", () => {
    state.windowTrigger?.focus?.();
    state.windowTrigger = null;
  });
  elements.portalPrepare.addEventListener("click", () => void preparePortal());
  elements.portalCopy.addEventListener("click", () => void copyPortal());
  elements.portalRevoke.addEventListener("click", () => void revokePortal());
  elements.portalRegenerate.addEventListener("click", () => void regeneratePortal());
  elements.groupCopy.addEventListener("click", () => void copyGroupMessageForWhatsApp());
  elements.prepareMissingAccesses.addEventListener("click", () => (
    void credentialsController.prepareMissing(elements.prepareMissingAccesses)
  ));
  elements.refresh.addEventListener("click", () => load());
  elements.search.addEventListener("input", () => { state.search = elements.search.value; render(); });
  elements.selectAll.addEventListener("click", () => {
    state.selected = new Set(readyRecipients().map((recipient) => recipient.id));
    state.selectionDirty = true;
    state.prepared = null;
    render();
  });
  elements.openWorkforce.addEventListener("click", () => {
    document.dispatchEvent(new CustomEvent("workspace:navigate", { detail: { view: "workforce" } }));
    status("Aperto Workforce per il supporto individuale.", "");
  });
  elements.prepareBatch.addEventListener("click", () => void prepareBatch());
  elements.exportBatch.addEventListener("click", () => void exportCsv(elements.exportBatch));
  elements.exportPrepared.addEventListener("click", () => void exportCsv(
    elements.exportPrepared, state.prepared?.recipients.map((item) => item.recipient_id) || [],
  ));
  elements.copyBatch.addEventListener("click", () => void (async () => {
    const text = (state.prepared?.recipients || []).map((item) => (
      `${item.display_name}\n${item.phone || item.email || "Contatto disponibile"}\n${item.message}`
    )).join("\n\n");
    await copyText(text);
    status("Elenco copiato. I link sono personali: condividili solo con i destinatari.", "success");
  })());
  elements.backRecipients.addEventListener("click", () => { state.prepared = null; render(); });
  document.querySelectorAll("[data-distribution-filter]").forEach((button) => {
    button.addEventListener("click", () => { state.filter = button.dataset.distributionFilter; render(); });
  });
  elements.manualRecipients.addEventListener("change", (event) => {
    const checkbox = event.target.closest("[data-select-shift-recipient]");
    if (!checkbox) return;
    const recipientId = Number(checkbox.dataset.selectShiftRecipient);
    if (checkbox.checked) state.selected.add(recipientId);
    else state.selected.delete(recipientId);
    state.selectionDirty = true;
    state.prepared = null;
    render();
  });
  elements.recipients.addEventListener("click", (event) => {
    const copy = event.target.closest("[data-copy-shift-link]");
    const regenerateButton = event.target.closest("[data-regenerate-shift-link]");
    const revokeButton = event.target.closest("[data-revoke-shift-link]");
    const resetCredentialButton = event.target.closest("[data-reset-driver-credential]");
    const revokeCredentialButton = event.target.closest("[data-revoke-driver-credential]");
    if (copy) void copyRecipientLink(Number(copy.dataset.copyShiftLink), copy);
    else if (regenerateButton) void regenerate(Number(regenerateButton.dataset.regenerateShiftLink), regenerateButton);
    else if (revokeButton) void revoke(Number(revokeButton.dataset.revokeShiftLink), revokeButton);
    else if (resetCredentialButton) void credentialsController.reset(
      Number(resetCredentialButton.dataset.resetDriverCredential), resetCredentialButton,
    );
    else if (revokeCredentialButton) void credentialsController.revoke(
      Number(revokeCredentialButton.dataset.revokeDriverCredential), revokeCredentialButton,
    );
  });

  return {
    setPlanning(planning) {
      if (state.planning?.id && planning?.id && state.planning.id !== planning.id) {
        state.newRevision = true;
      } else if (!planning) {
        state.newRevision = false;
      }
      const changed = state.planning?.id !== planning?.id || state.planning?.status !== planning?.status;
      state.planning = planning;
      elements.entry.hidden = planning?.status !== "ACTIVE";
      if (planning?.status !== "ACTIVE") {
        state.model = null;
        state.portal = null;
        state.credentialModel = null;
        clearMessageFallback();
        state.credentialStatuses = new Map();
        credentialsController.setDistribution(null);
        state.selected.clear();
        state.request += 1;
        render();
      } else if (changed) {
        state.model = null;
        state.selected.clear();
        state.selectionDirty = false;
        state.prepared = null;
        state.portal = null;
        state.credentialModel = null;
        clearMessageFallback();
        state.credentialStatuses = new Map();
        credentialsController.setDistribution(null);
        render();
      }
    },
  };
}
