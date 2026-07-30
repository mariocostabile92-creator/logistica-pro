import { listJournalControlRoom } from "../api.js";
import { mountJournalSharedAccess } from "./journal-shared-access.js?v=2";
import { journalCard, journalDetail } from "./journal-control-room/components.js";
import { journalControlRoomShell } from "./journal-control-room/renderer.js";
import {
  journalControlRoomState as state, resetJournalControlRoomState,
} from "./journal-control-room/state.js";

const root = () => document.getElementById("journalControlRoom");

async function load(preferredId = state.selected?.id) {
  const params = { vehicle_id: state.vehicle_id };
  for (const [selector, key] of [["[data-jcr-search]", "search"], ["[data-jcr-operation]", "operation_type"], ["[data-jcr-anomaly]", "anomaly"], ["[data-jcr-period]", "period"]]) {
    const value = root().querySelector(selector)?.value;
    if (value) params[key] = value;
  }
  const response = await listJournalControlRoom(params);
  state.items = response.items;
  state.selected = state.items.find(item => item.id === preferredId) || state.items[0] || null;
  root().querySelector("[data-jcr-list]").innerHTML = state.items.length
    ? state.items.map(item => journalCard(item, state.selected?.id)).join("")
    : `<div class="view-state">Nessuna procedura trovata.</div>`;
  root().querySelector("[data-jcr-detail]").innerHTML = journalDetail(state.selected);
  root().classList.toggle("detail-open", Boolean(state.selected));
  for (const [key, value] of Object.entries(response.summary)) {
    root().querySelector(`[data-jcr-kpi="${key}"]`).textContent = value;
  }
}

export async function showJournalControlRoom(options = {}) {
  document.querySelectorAll("#fleetWorkspaceHome,#fleetVehicleDossier,#damageWorkspace,#maintenanceWorkspace,#documentsWorkspace,#franchiseWorkspace,#insuranceWorkspace,#rentalWorkspace,#deadlinesWorkspace")
    .forEach(element => { element.hidden = true; });
  resetJournalControlRoomState(options.vehicle_id || null);
  root().hidden = false;
  root().innerHTML = journalControlRoomShell();
  await mountJournalSharedAccess(root().querySelector("[data-jcr-shared-access]"));
  await load();
}

document.addEventListener("input", event => {
  if (event.target.matches("[data-jcr-search]")) load();
});
document.addEventListener("change", event => {
  if (event.target.matches("[data-jcr-operation],[data-jcr-anomaly],[data-jcr-period]")) load();
});
document.addEventListener("click", event => {
  const entry = event.target.closest("[data-jcr-id]");
  if (entry) load(entry.dataset.jcrId);
  if (event.target.closest("[data-jcr-back]")) root().classList.remove("detail-open");
  const vehicle = event.target.closest("[data-jcr-vehicle]")?.dataset.jcrVehicle;
  if (vehicle) {
    root().hidden = true;
    document.dispatchEvent(new CustomEvent("fleet:vehicle-open", { detail: { assetId: Number(vehicle) } }));
  }
  const damage = event.target.closest("[data-jcr-damage]")?.dataset.jcrDamage;
  if (damage) {
    root().hidden = true;
    document.dispatchEvent(new CustomEvent("damage:open", { detail: { caseId: Number(damage) } }));
  }
  if (event.target.closest("[data-jcr-damage-new]")) {
    root().hidden = true;
    document.dispatchEvent(new CustomEvent("damage:open"));
  }
});
