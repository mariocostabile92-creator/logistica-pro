import { deleteJournalMedia, listJournalControlRoom } from "../api.js";
import { escapeHtml } from "../utils/dom.js";
import { mountJournalSharedAccess } from "./journal-shared-access.js?v=2";
import { journalLiveCard } from "./journal-control-room/live-overview.js";
import { journalLiveDetail } from "./journal-control-room/live-detail.js";
import { setJournalWorkspaceView } from "./journal-control-room/navigation.js";
import { wireJournalMediaFallback } from "./journal-control-room/media-section.js";
import { journalControlRoomShell } from "./journal-control-room/renderer.js";
import { mountJournalArchive } from "./journal-archive/index.js?v=2";
import {
  journalControlRoomState as state, resetJournalControlRoomState,
} from "./journal-control-room/state.js";

const root = () => document.getElementById("journalControlRoom");

async function load(preferredId = state.selected?.id) {
  root().setAttribute("aria-busy", "true");
  const params = { vehicle_id: state.vehicle_id };
  if (state.live_filter !== "all") params.live_status = state.live_filter;
  for (const [selector, key] of [["[data-jcr-search]", "search"], ["[data-jcr-operation]", "operation_type"], ["[data-jcr-anomaly]", "anomaly"]]) {
    const value = root().querySelector(selector)?.value;
    if (value) params[key] = value;
  }
  let response;
  try {
    response = await listJournalControlRoom(params);
  } catch (error) {
    root().querySelector("[data-jcr-list]").innerHTML = `<div class="jcr-empty"><strong>Control Room non disponibile</strong><p>${escapeHtml(error.message)}</p><button type="button" data-jcr-retry>Riprova</button></div>`;
    root().querySelector("[data-jcr-detail]").innerHTML = `<div class="jcr-empty"><strong>Dettaglio non disponibile</strong><p>Riprova il caricamento della Control Room.</p></div>`;
    root().setAttribute("aria-busy", "false");
    return;
  }
  state.items = response.items;
  state.selected = state.items.find(item => item.id === preferredId) || state.items[0] || null;
  root().querySelector("[data-jcr-list]").innerHTML = state.items.length
    ? state.items.map(item => journalLiveCard(item, state.selected?.id)).join("")
    : `<div class="view-state"><strong>Nessuna procedura per la giornata operativa.</strong><p>Per consultare lo storico apri Archivio GDB.</p></div>`;
  root().querySelector("[data-jcr-detail]").innerHTML = journalLiveDetail(state.selected);
  root().classList.toggle("detail-open", Boolean(state.selected));
  for (const [key, value] of Object.entries(response.summary)) {
    const target = root().querySelector(`[data-jcr-kpi="${key}"]`);
    if (target) target.textContent = value;
  }
  root().querySelectorAll("[data-jcr-live-filter]").forEach(button => {
    const active = button.dataset.jcrLiveFilter === state.live_filter;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
  const context = response.context;
  root().querySelector("[data-jcr-context]").textContent = `Giornata operativa ${context.operational_date} · ${context.timezone} · dalle ${String(context.operational_day_start_hour).padStart(2, "0")}:00`;
  root().setAttribute("aria-busy", "false");
}

export async function showJournalControlRoom(options = {}) {
  document.querySelectorAll("#fleetWorkspaceHome,#fleetVehicleDossier,#damageWorkspace,#maintenanceWorkspace,#documentsWorkspace,#franchiseWorkspace,#insuranceWorkspace,#rentalWorkspace,#deadlinesWorkspace")
    .forEach(element => { element.hidden = true; });
  resetJournalControlRoomState(options.vehicle_id || null);
  root().hidden = false;
  root().innerHTML = `<nav class="jcr-workspace-nav" aria-label="Viste Giornale di bordo">
    <button type="button" class="active" data-jcr-view="control" aria-pressed="true">Control Room</button>
    <button type="button" data-jcr-view="archive" aria-pressed="false">Archivio GDB</button>
  </nav><div data-jcr-live>${journalControlRoomShell()}</div><div data-jcr-archive hidden></div>`;
  wireJournalMediaFallback(root());
  await mountJournalSharedAccess(root().querySelector("[data-jcr-shared-access]"));
  await load();
}

document.addEventListener("input", event => {
  if (event.target.matches("[data-jcr-search]")) load();
});
document.addEventListener("change", event => {
  if (event.target.matches("[data-jcr-operation],[data-jcr-anomaly]")) load();
});
document.addEventListener("click", async event => {
  const liveFilter = event.target.closest("[data-jcr-live-filter]")?.dataset.jcrLiveFilter;
  if (liveFilter && root() && !root().hidden) {
    state.live_filter = liveFilter;
    state.selected = null;
    await load();
  }
  const entry = event.target.closest("[data-jcr-id]");
  if (entry && !entry.closest("[data-jcr-archive]")) load(entry.dataset.jcrId);
  const view = event.target.closest("[data-jcr-view]")?.dataset.jcrView;
  if (view && root() && !root().hidden) {
    const archive = root().querySelector("[data-jcr-archive]");
    setJournalWorkspaceView(root(), view);
    if (view === "archive" && !archive.dataset.mounted) {
      archive.dataset.mounted = "true";
      await mountJournalArchive(archive);
    }
  }
  const fullJournal = event.target.closest("[data-jcr-open-archive]");
  if (fullJournal) {
    const archive = root().querySelector("[data-jcr-archive]");
    setJournalWorkspaceView(root(), "archive");
    archive.dataset.mounted = "true";
    await mountJournalArchive(archive, {
      selectedDate: fullJournal.dataset.jcrOperationalDate,
      selectedId: fullJournal.dataset.jcrOpenArchive,
    });
  }
  if (event.target.closest("[data-jcr-back]")) root().classList.remove("detail-open");
  if (event.target.closest("[data-jcr-retry]")) load();
  const mediaDelete = event.target.closest("[data-jcr-media-delete]");
  if (mediaDelete && window.confirm("Eliminare definitivamente questo media Journal?")) {
    mediaDelete.disabled = true;
    await deleteJournalMedia(mediaDelete.dataset.jcrMediaDelete);
    const archive = mediaDelete.closest("[data-jcr-archive]");
    if (archive) archive.dispatchEvent(new CustomEvent("journal:media-deleted"));
    else await load();
  }
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
