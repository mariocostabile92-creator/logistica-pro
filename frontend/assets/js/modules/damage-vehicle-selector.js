import { listFleetAssets } from "../api.js?v=6";
import { escapeHtml } from "../utils/dom.js";


const INITIAL_STATE = Object.freeze({ phase: "idle", assets: [] });


export function damageVehicleLabel(asset) {
  const plate = String(asset?.plate || asset?.external_identifier || "").trim();
  const model = String(asset?.category || "").trim();
  return model ? `${plate} — ${model}` : plate;
}


export function normalizeDamageVehicleAssets(response) {
  const items = Array.isArray(response?.items) ? response.items : [];
  return items
    .filter((asset) => Number.isInteger(Number(asset?.id))
      && Number(asset.id) > 0
      && damageVehicleLabel(asset))
    .map((asset) => ({
      id: Number(asset.id),
      plate: String(asset.plate || asset.external_identifier).trim(),
      model: String(asset.category || "").trim(),
      label: damageVehicleLabel(asset),
    }))
    .sort((left, right) => left.plate.localeCompare(right.plate, "it-IT", {
      numeric: true,
      sensitivity: "base",
    }));
}


export function damageVehicleOptionsMarkup(state) {
  if (state.phase === "loading" || state.phase === "idle") {
    return '<option value="">Caricamento mezzi…</option>';
  }
  if (state.phase === "empty") {
    return '<option value="">Nessun mezzo disponibile.</option>';
  }
  if (state.phase === "error") {
    return '<option value="">Impossibile caricare il parco mezzi.</option>';
  }
  return [
    '<option value="">Seleziona un mezzo</option>',
    ...state.assets.map((asset) => (
      `<option value="${asset.id}">${escapeHtml(asset.label)}</option>`
    )),
  ].join("");
}


export function createDamageVehicleSelectorController({
  loadAssets = listFleetAssets,
  onStateChange = () => {},
} = {}) {
  let state = INITIAL_STATE;
  let requestVersion = 0;

  const publish = (nextState) => {
    state = nextState;
    onStateChange(state);
  };

  const load = async () => {
    requestVersion += 1;
    const version = requestVersion;
    publish({ phase: "loading", assets: [] });
    try {
      const assets = normalizeDamageVehicleAssets(await loadAssets());
      if (version !== requestVersion) return state;
      publish({ phase: assets.length ? "ready" : "empty", assets });
    } catch (_error) {
      if (version !== requestVersion) return state;
      publish({ phase: "error", assets: [] });
    }
    return state;
  };

  const destroy = () => {
    requestVersion += 1;
    state = INITIAL_STATE;
  };

  return { load, destroy, getState: () => state };
}


export function mountDamageVehicleSelector(form) {
  const select = form.elements.vehicle_id;
  const status = form.querySelector("[data-damage-vehicle-status]");
  const submit = form.querySelector("[type='submit']");
  const render = (state) => {
    const available = state.phase === "ready";
    select.innerHTML = damageVehicleOptionsMarkup(state);
    select.disabled = !available;
    select.setAttribute("aria-busy", String(state.phase === "loading"));
    submit.disabled = !available;
    status.hidden = available;
    status.dataset.state = state.phase;
    status.textContent = state.phase === "loading" || state.phase === "idle"
      ? "Caricamento del parco mezzi…"
      : state.phase === "empty"
        ? "Nessun mezzo disponibile."
        : state.phase === "error"
          ? "Impossibile caricare il parco mezzi."
          : "";
  };
  const controller = createDamageVehicleSelectorController({ onStateChange: render });
  const ready = controller.load();
  return { ...controller, ready };
}
