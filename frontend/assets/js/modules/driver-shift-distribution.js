import {
  getDistribution,
  getRecipientAccessLink,
  prepareDistribution,
  regenerateRecipientAccess,
  revokeRecipientAccess,
} from "./driver-shift-planning-api.js?v=3";
import {
  filterDistributionRecipients,
  renderDistributionRecipients,
  renderDistributionSummary,
} from "./driver-shift-distribution-presenter.js?v=1";
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


export function initDriverShiftDistribution() {
  const state = { planning: null, model: null, filter: "", search: "", request: 0 };
  const elements = {
    entry: byId("driverShiftDistributeBtn"),
    section: byId("driverShiftDistributionSection"),
    summary: byId("driverShiftDistributionSummary"),
    recipients: byId("driverShiftDistributionRecipients"),
    status: byId("driverShiftDistributionStatus"),
    search: byId("driverShiftDistributionSearch"),
    refresh: byId("driverShiftDistributionRefresh"),
  };

  function status(message = "", tone = "") {
    elements.status.textContent = message;
    elements.status.dataset.tone = tone;
  }

  function render() {
    if (!state.model) {
      elements.section.hidden = true;
      return;
    }
    elements.section.hidden = false;
    renderDistributionSummary(elements.summary, state.model.summary);
    renderDistributionRecipients(
      elements.recipients,
      filterDistributionRecipients(state.model.recipients, state.filter, state.search),
    );
    document.querySelectorAll("[data-distribution-filter]").forEach((button) => {
      const active = button.dataset.distributionFilter === state.filter;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", String(active));
    });
  }

  async function load({ quietMissing = false } = {}) {
    if (!state.planning || state.planning.status !== "ACTIVE") return;
    const request = ++state.request;
    try {
      const model = await getDistribution(state.planning.id);
      if (request !== state.request) return;
      state.model = model;
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

  async function prepare() {
    if (!state.planning) return;
    setLoading(elements.entry, true, "Preparazione...");
    try {
      state.model = await prepareDistribution(state.planning.id);
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
      await load();
      status("Nuovo link copiato. Il precedente non è più valido.", "success");
    } catch (error) {
      status(userErrorPresentation("workforce.driver-shift-access", error).message, "error");
    } finally {
      setLoading(button, false);
    }
  }

  elements.entry.addEventListener("click", prepare);
  elements.refresh.addEventListener("click", () => load());
  elements.search.addEventListener("input", () => { state.search = elements.search.value; render(); });
  document.querySelectorAll("[data-distribution-filter]").forEach((button) => {
    button.addEventListener("click", () => { state.filter = button.dataset.distributionFilter; render(); });
  });
  elements.recipients.addEventListener("click", (event) => {
    const copy = event.target.closest("[data-copy-shift-link]");
    const regenerateButton = event.target.closest("[data-regenerate-shift-link]");
    const revokeButton = event.target.closest("[data-revoke-shift-link]");
    if (copy) void copyRecipientLink(Number(copy.dataset.copyShiftLink), copy);
    else if (regenerateButton) void regenerate(Number(regenerateButton.dataset.regenerateShiftLink), regenerateButton);
    else if (revokeButton) void revoke(Number(revokeButton.dataset.revokeShiftLink), revokeButton);
  });

  return {
    setPlanning(planning) {
      const changed = state.planning?.id !== planning?.id || state.planning?.status !== planning?.status;
      state.planning = planning;
      elements.entry.hidden = planning?.status !== "ACTIVE";
      if (planning?.status !== "ACTIVE") {
        state.model = null;
        state.request += 1;
        render();
      } else if (changed) {
        state.model = null;
        render();
        void load({ quietMissing: true });
      }
    },
  };
}
