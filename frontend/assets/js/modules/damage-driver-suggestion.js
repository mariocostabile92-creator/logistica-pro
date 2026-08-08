import { getDamageDriverSuggestion } from "../api.js?v=6";
import { escapeHtml } from "../utils/dom.js";


const EMPTY_STATE = Object.freeze({ phase: "idle", result: null });


export function operationalDateFromInput(value) {
  const match = String(value || "").match(/^(\d{4}-\d{2}-\d{2})/);
  if (!match) return null;
  const parsed = new Date(`${match[1]}T00:00:00`);
  return Number.isNaN(parsed.getTime()) ? null : match[1];
}


export function damageDriverSuggestionMarkup(state) {
  if (state.phase === "loading") {
    return `
      <p class="eyebrow">Driver associato</p>
      <p class="damage-driver-suggestion-message">Ricerca driver associato&hellip;</p>`;
  }
  if (state.phase === "error") {
    return `
      <p class="eyebrow">Driver associato</p>
      <p class="damage-driver-suggestion-message">Impossibile recuperare il driver associato.</p>`;
  }
  const result = state.result;
  if (!result) return "";
  if (result.status === "MATCH") {
    const journal = result.source === "journal";
    return `
      <p class="eyebrow">${journal ? "Driver associato" : "Driver suggerito"}</p>
      <strong class="damage-driver-suggestion-name">${escapeHtml(result.driver?.display_name || "Driver non disponibile")}</strong>
      <p class="damage-driver-suggestion-source">Fonte: <strong>${journal ? "Journal" : "Planning"}</strong></p>
      <p class="damage-driver-suggestion-note">${journal
        ? "Rilevato dal Giornale di Bordo"
        : "Associato al mezzo nella pianificazione della giornata"}</p>`;
  }
  if (result.status === "CONFLICT") {
    return `
      <p class="eyebrow">Conflitto di attribuzione</p>
      <div class="damage-driver-conflict">
        <div><span>Journal</span><strong>${escapeHtml(result.journal_driver?.display_name || "Non disponibile")}</strong></div>
        <div><span>Planning</span><strong>${escapeHtml(result.planning_driver?.display_name || "Non disponibile")}</strong></div>
      </div>
      <p class="damage-driver-suggestion-note">Journal e Planning indicano driver differenti.</p>`;
  }
  if (result.status === "AMBIGUOUS") {
    return `
      <p class="eyebrow">Driver associato</p>
      <p class="damage-driver-suggestion-message">Pi&ugrave; driver compatibili trovati. Sar&agrave; necessaria una selezione manuale.</p>`;
  }
  return `
    <p class="eyebrow">Driver associato</p>
    <p class="damage-driver-suggestion-message">Nessun driver determinato automaticamente per mezzo e data selezionati.</p>`;
}


export function createDamageDriverSuggestionController({
  requestSuggestion = getDamageDriverSuggestion,
  onStateChange = () => {},
} = {}) {
  let state = EMPTY_STATE;
  let activeKey = null;
  let requestVersion = 0;
  let abortController = null;

  const publish = (nextState) => {
    state = nextState;
    onStateChange(state);
  };

  const update = async ({ vehicleId, occurredAt }) => {
    const parsedVehicleId = Number(vehicleId);
    const operationalDate = operationalDateFromInput(occurredAt);
    const validVehicle = Number.isInteger(parsedVehicleId) && parsedVehicleId > 0;
    const nextKey = validVehicle && operationalDate
      ? `${parsedVehicleId}:${operationalDate}`
      : null;
    if (nextKey === activeKey) return state;
    activeKey = nextKey;
    requestVersion += 1;
    const version = requestVersion;
    abortController?.abort();
    abortController = null;
    if (!nextKey) {
      publish(EMPTY_STATE);
      return state;
    }
    abortController = new AbortController();
    publish({ phase: "loading", result: null });
    try {
      const result = await requestSuggestion(parsedVehicleId, operationalDate, {
        signal: abortController.signal,
      });
      if (version !== requestVersion) return state;
      publish({
        phase: "ready",
        result,
        workforceMemberId: result.driver?.workforce_member_id || null,
        source: result.source || null,
        status: result.status,
      });
    } catch (error) {
      if (version !== requestVersion || error?.name === "AbortError") return state;
      publish({ phase: "error", result: null });
    }
    return state;
  };

  const destroy = () => {
    requestVersion += 1;
    abortController?.abort();
    abortController = null;
    activeKey = null;
    state = EMPTY_STATE;
  };

  return { update, destroy, getState: () => state };
}


export function mountDamageDriverSuggestion(form) {
  const vehicleInput = form.elements.vehicle_id;
  const dateInput = form.elements.occurred_at;
  const container = form.querySelector("[data-damage-driver-suggestion]");
  const render = (state) => {
    container.hidden = state.phase === "idle";
    container.dataset.state = state.phase;
    container.innerHTML = damageDriverSuggestionMarkup(state);
  };
  const controller = createDamageDriverSuggestionController({ onStateChange: render });
  const update = () => controller.update({
    vehicleId: vehicleInput.value,
    occurredAt: dateInput.value,
  });
  const listener = (event) => {
    if (event.target === vehicleInput || event.target === dateInput) void update();
  };
  form.addEventListener("input", listener);
  form.addEventListener("change", listener);
  void update();
  return {
    ...controller,
    destroy() {
      form.removeEventListener("input", listener);
      form.removeEventListener("change", listener);
      controller.destroy();
    },
  };
}
