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
} from "./driver-shift-planning-api.js?v=6";
import {
  filterDistributionRecipients,
  renderDistributionRecipients,
  renderDistributionSummary,
} from "./driver-shift-distribution-presenter.js?v=3";
import { initDriverShiftCredentials } from "./driver-shift-credentials.js?v=1";
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


export function initDriverShiftDistribution() {
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
    credentialStatuses: new Map(),
  };
  const elements = {
    entry: byId("driverShiftDistributeBtn"),
    section: byId("driverShiftDistributionSection"),
    summary: byId("driverShiftDistributionSummary"),
    recipients: byId("driverShiftDistributionRecipients"),
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
  };

  function status(message = "", tone = "") {
    elements.status.textContent = message;
    elements.status.dataset.tone = tone;
  }

  const credentialsController = initDriverShiftCredentials({
    status,
    onChanged(_model, statusMap) {
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
    renderDistributionSummary(elements.summary, state.model.summary, state.selected.size);
    renderDistributionRecipients(
      elements.recipients,
      filterDistributionRecipients(state.model.recipients, state.filter, state.search),
      state.selected,
      state.credentialStatuses,
    );
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

  async function prepare() {
    if (!state.planning) return;
    setLoading(elements.entry, true, "Preparazione...");
    try {
      state.model = await prepareDistribution(state.planning.id);
      state.selectionDirty = false;
      state.prepared = null;
      syncSelection({ reset: true });
      credentialsController.setDistribution(state.model.distribution);
      render();
      status("Distribuzione pronta. Nessun messaggio è stato inviato.", "success");
    } catch (error) {
      status(userErrorPresentation("workforce.driver-shift-distribution", error).message, "error");
    } finally {
      setLoading(elements.entry, false);
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

  elements.entry.addEventListener("click", prepare);
  elements.portalPrepare.addEventListener("click", () => void preparePortal());
  elements.portalCopy.addEventListener("click", () => void copyPortal());
  elements.portalRevoke.addEventListener("click", () => void revokePortal());
  elements.portalRegenerate.addEventListener("click", () => void regeneratePortal());
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
    status("Aggiorna telefono o email nel profilo Workforce del driver.", "");
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
  elements.recipients.addEventListener("change", (event) => {
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
      const changed = state.planning?.id !== planning?.id || state.planning?.status !== planning?.status;
      state.planning = planning;
      elements.entry.hidden = planning?.status !== "ACTIVE";
      if (planning?.status !== "ACTIVE") {
        state.model = null;
        state.portal = null;
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
        state.credentialStatuses = new Map();
        credentialsController.setDistribution(null);
        render();
        void load({ quietMissing: true });
      }
    },
  };
}
