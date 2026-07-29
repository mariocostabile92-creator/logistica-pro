import {
  addFleetAssetDocument,
  createFleetAsset,
  getFleetAsset,
  getFleetVehicleHistory,
  getLatestFleetSync,
  listFleetAssets,
  observeFleetAssetAvailability,
  updateFleetAsset,
} from "../api.js";
import { state } from "../state.js";
import { byId, setLoading, setMessage } from "../utils/dom.js";
import {
  isExpectedApiError,
  reportUnexpectedError,
  userErrorPresentation,
} from "../utils/errors.js";
import {
  filterFleetAssets,
  fleetRegistryCsv,
  hideAssetDetail,
  renderAssetList,
  renderFleetFailure,
  renderFleetLoading,
  renderFleetTree,
  renderVehicleDossier,
  setFleetMetricPriority,
} from "./fleet-view.js";
import { showDamageWorkspace } from "./damage-workspace.js";


let loaded = false;
let demoEnabled = false;
let searchTerm = "";
let latestFleetImportAt = null;


async function refreshSyncSummary(hasAssets) {
  if (!hasAssets) {
    byId("fleetRecentUpdates").textContent = "0";
    setFleetMetricPriority("fleetRecentUpdates", 0);
    byId("fleetUnresolvedConflicts").textContent = "0";
    return null;
  }
  try {
    const latest = await getLatestFleetSync();
    const summary = latest.summary || {};
    const recentUpdates = Number(summary.created_assets || 0)
      + Number(summary.updated_assets || 0);
    byId("fleetRecentUpdates").textContent = recentUpdates;
    setFleetMetricPriority("fleetRecentUpdates", recentUpdates);
    byId("fleetUnresolvedConflicts").textContent = summary.unresolved_conflicts || 0;
    return latest;
  } catch (error) {
    if (!isExpectedApiError(error, { statuses: [404] })) throw error;
    byId("fleetRecentUpdates").textContent = "0";
    setFleetMetricPriority("fleetRecentUpdates", 0);
    byId("fleetUnresolvedConflicts").textContent = "0";
    return null;
  }
}


function fleetTimestamp(value) {
  if (!value) return "Ultimo aggiornamento non disponibile.";
  const parsed = new Date(value);
  const label = Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString("it-IT");
  return `Ultimo aggiornamento: ${label}`;
}


function renderFilteredFleet() {
  const filtered = filterFleetAssets(state.fleetPlugin.assets, searchTerm);
  renderAssetList(filtered, {
    allAssets: state.fleetPlugin.assets,
    demoEnabled,
    searchTerm,
  });
  renderFleetTree(state.fleetPlugin.assets, state.fleetPlugin.selectedAssetId);
}


function showFleetActionError(context, error) {
  const presentation = userErrorPresentation(context, error);
  setMessage(presentation.message, presentation.tone);
}


function capabilitiesFromInput() {
  return byId("assetCapabilities").value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}


function closeDialog(id) {
  byId(id).close();
}


async function showAsset(assetId) {
  byId("damageWorkspace").hidden = true;
  byId("fleetWorkspaceHome").hidden = true;
  byId("fleetVehicleDossier").hidden = false;
  byId("fleetDossierState").hidden = false;
  byId("fleetDossierState").className = "view-state loading";
  byId("fleetDossierState").textContent = "Caricamento scheda mezzo";
  byId("fleetDossierContent").hidden = true;
  const [asset, history] = await Promise.all([
    getFleetAsset(assetId),
    getFleetVehicleHistory(assetId),
  ]);
  state.fleetPlugin.selectedAssetId = assetId;
  renderFleetTree(state.fleetPlugin.assets, assetId);
  byId("fleetTreeSelection").textContent = asset.plate || asset.external_identifier;
  byId("fleetTreeSelection").hidden = false;
  renderVehicleDossier(history, asset);
  byId("fleetAssetTree").open = false;
  closeFleetSidebar();
}


function showFleetLibrary() {
  byId("damageWorkspace").hidden = true;
  state.fleetPlugin.selectedAssetId = null;
  byId("fleetVehicleDossier").hidden = true;
  byId("fleetWorkspaceHome").hidden = false;
  byId("fleetAssetTree").open = true;
  byId("fleetTreeSelection").hidden = true;
  renderFleetTree(state.fleetPlugin.assets);
  document.querySelector("[data-fleet-module='library']")?.classList.add("active");
  closeFleetSidebar();
}


function showJournalGateway() {
  byId("damageWorkspace").hidden = true;
  state.fleetPlugin.selectedAssetId = null;
  byId("fleetWorkspaceHome").hidden = true;
  byId("fleetVehicleDossier").hidden = false;
  byId("fleetDossierContent").hidden = true;
  byId("fleetDossierState").hidden = false;
  byId("fleetDossierState").className = "fleet-module-gateway";
  byId("fleetDossierState").innerHTML = `
    <p class="eyebrow">Fleet Operations</p>
    <h2>Giornale di bordo</h2>
    <p>Il flusso operativo Driver resta disponibile sul suo accesso dedicato.</p>
    <a class="header-config-button" href="/app/journal/">Apri Giornale di bordo</a>
  `;
  closeFleetSidebar();
}


function setFleetSidebar(open) {
  byId("fleetWorkspaceSidebar").classList.toggle("open", open);
  byId("fleetSidebarBackdrop").hidden = !open;
  byId("fleetSidebarToggle").setAttribute("aria-expanded", String(open));
}


function closeFleetSidebar() {
  setFleetSidebar(false);
}


async function refreshFleet(selectedAssetId = state.fleetPlugin.selectedAssetId) {
  renderFleetLoading();
  const response = await listFleetAssets();
  state.fleetPlugin.assets = response.items;
  const latestSync = await refreshSyncSummary(
    response.items.length > 0 && document.body.dataset.workspaceState !== "DEMO",
  );
  renderFilteredFleet();
  const latestAssetUpdate = response.items.reduce(
    (latest, item) => !latest || item.updated_at > latest ? item.updated_at : latest,
    "",
  );
  byId("fleetPluginTimestamp").textContent = fleetTimestamp(
    latestSync?.imported_at || latestFleetImportAt || latestAssetUpdate,
  );
  document.dispatchEvent(new CustomEvent("fleet:registry-loaded", {
    detail: { assetCount: response.items.length },
  }));
  if (selectedAssetId && response.items.some((item) => item.id === selectedAssetId)) {
    await showAsset(selectedAssetId);
  } else {
    state.fleetPlugin.selectedAssetId = null;
    hideAssetDetail();
    renderFleetTree(response.items);
  }
  loaded = true;
}


function openAssetEditor(asset = null) {
  const editing = Boolean(asset);
  byId("assetEditorForm").reset();
  byId("assetId").value = asset?.id || "";
  byId("assetEditorTitle").textContent = editing ? "Modifica Asset" : "Nuovo Asset";
  byId("assetExternalIdentifier").value = asset?.external_identifier || "";
  byId("assetExternalIdentifier").disabled = editing;
  byId("assetPlate").value = asset?.plate || "";
  byId("assetCategory").value = asset?.category || "";
  byId("assetStatus").value = asset?.status || "active";
  byId("assetAvailability").value = asset?.availability || "available";
  byId("assetAvailabilityField").hidden = editing;
  byId("assetCapabilities").value = (asset?.capabilities || []).join(", ");
  byId("assetNotes").value = asset?.notes || "";
  byId("assetEditor").showModal();
}


function selectedAsset() {
  return state.fleetPlugin.assets.find(
    (item) => item.id === state.fleetPlugin.selectedAssetId,
  );
}


async function submitAsset(event) {
  event.preventDefault();
  const submit = event.submitter;
  setLoading(submit, true, "Salvataggio...");
  const assetId = Number(byId("assetId").value || 0);
  const common = {
    plate: byId("assetPlate").value.trim() || null,
    category: byId("assetCategory").value.trim() || null,
    status: byId("assetStatus").value.trim(),
    notes: byId("assetNotes").value.trim() || null,
    capabilities: capabilitiesFromInput(),
  };
  try {
    const asset = assetId
      ? await updateFleetAsset(assetId, common)
      : await createFleetAsset({
          ...common,
          external_identifier: byId("assetExternalIdentifier").value.trim(),
          availability: byId("assetAvailability").value.trim(),
        });
    closeDialog("assetEditor");
    await refreshFleet(asset.id);
    setMessage("");
  } catch (error) {
    showFleetActionError("fleet.save-asset", error);
  } finally {
    setLoading(submit, false);
  }
}


function openAvailabilityEditor(asset) {
  byId("availabilityEditorForm").reset();
  byId("availabilityAssetId").value = asset.id;
  byId("assetAvailabilityValue").value = asset.availability;
  byId("availabilityEditor").showModal();
}


async function submitAvailability(event) {
  event.preventDefault();
  const submit = event.submitter;
  setLoading(submit, true, "Registrazione...");
  const assetId = Number(byId("availabilityAssetId").value);
  try {
    await observeFleetAssetAvailability(assetId, {
      availability: byId("assetAvailabilityValue").value.trim(),
      note: byId("assetAvailabilityNote").value.trim() || null,
    });
    closeDialog("availabilityEditor");
    await refreshFleet(assetId);
    setMessage("");
  } catch (error) {
    showFleetActionError("fleet.observe-availability", error);
  } finally {
    setLoading(submit, false);
  }
}


function openDocumentEditor(asset) {
  byId("documentEditorForm").reset();
  byId("documentAssetId").value = asset.id;
  byId("documentEditor").showModal();
}


async function submitDocument(event) {
  event.preventDefault();
  const submit = event.submitter;
  setLoading(submit, true, "Aggiunta...");
  const assetId = Number(byId("documentAssetId").value);
  try {
    await addFleetAssetDocument(assetId, {
      document_type: byId("documentType").value.trim(),
      name: byId("documentName").value.trim(),
      reference: byId("documentReference").value.trim() || null,
      issued_on: byId("documentIssuedOn").value || null,
      expires_on: byId("documentExpiresOn").value || null,
      notes: byId("documentNotes").value.trim() || null,
    });
    closeDialog("documentEditor");
    await refreshFleet(assetId);
    setMessage("");
  } catch (error) {
    showFleetActionError("fleet.add-document", error);
  } finally {
    setLoading(submit, false);
  }
}


async function handleAssetSelection(event) {
  const target = event.target.closest("[data-fleet-action='select']");
  if (!target) return;
  try {
    await showAsset(Number(target.dataset.assetId));
    setMessage("");
  } catch (error) {
    showFleetActionError("fleet.asset-detail", error);
  }
}


function handleAssetSelectionKeydown(event) {
  if (event.key !== "Enter" && event.key !== " ") return;
  const target = event.target.closest("[data-fleet-action='select']");
  if (!target) return;
  event.preventDefault();
  target.click();
}


function exportFleetRegistry() {
  if (!state.fleetPlugin.assets.length) return;
  const now = new Date();
  const dateStamp = [
    now.getFullYear(),
    String(now.getMonth() + 1).padStart(2, "0"),
    String(now.getDate()).padStart(2, "0"),
  ].join("-");
  const blob = new Blob(["\uFEFF", fleetRegistryCsv(state.fleetPlugin.assets)], {
    type: "text/csv;charset=utf-8",
  });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `parco-mezzi-${dateStamp}.csv`;
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(link.href);
}


export function initFleetPage() {
  document.addEventListener("workspace:view-changed", async (event) => {
    if (event.detail.view !== "fleet" || loaded) return;
    try {
      await refreshFleet();
    } catch (error) {
      reportUnexpectedError("fleet.list", error);
      renderFleetFailure();
      byId("fleetPluginTimestamp").textContent = "Asset non disponibili.";
    }
  });
  document.addEventListener("demo:workspace-changed", () => {
    loaded = false;
    refreshFleet().catch((error) => {
      reportUnexpectedError("fleet.demo-refresh", error);
      renderFleetFailure();
    });
  });
  document.addEventListener("demo:availability-changed", (event) => {
    demoEnabled = Boolean(event.detail.enabled);
    if (loaded && state.fleetPlugin.assets.length === 0) {
      renderFilteredFleet();
    }
  });
  document.addEventListener("workspace:status-changed", (event) => {
    latestFleetImportAt = event.detail.latest_fleet_import?.imported_at || null;
    demoEnabled = Boolean(
      event.detail.demo_enabled
      && event.detail.workspace_state === "EMPTY"
    );
    if (loaded && state.fleetPlugin.assets.length === 0) {
      renderFilteredFleet();
    }
  });
  document.addEventListener("fleet:sync-completed", () => {
    refreshFleet().catch((error) => {
      reportUnexpectedError("fleet.refresh-after-sync", error);
      renderFleetFailure();
    });
  });
  byId("fleetViewState").addEventListener("click", (event) => {
    const action = event.target.closest("[data-view-action]")?.dataset.viewAction;
    if (action === "create-asset") openAssetEditor();
    if (action === "sync-fleet") {
      document.dispatchEvent(new CustomEvent("fleet:sync-requested"));
    }
    if (action === "open-imports") {
      document.dispatchEvent(new CustomEvent("workspace:navigate", {
        detail: {
          view: "operations",
          targetId: "importsSection",
        },
      }));
      requestAnimationFrame(() => {
        byId("importsDisclosure").open = true;
        byId("fleetFile").focus({ preventScroll: true });
      });
    }
    if (action === "load-demo") {
      document.dispatchEvent(new CustomEvent("demo:load-requested"));
    }
    if (action === "retry-fleet") {
      refreshFleet().catch((error) => {
        reportUnexpectedError("fleet.list", error);
        renderFleetFailure();
      });
    }
  });
  byId("createAssetBtn").addEventListener("click", () => openAssetEditor());
  byId("fleetSearchInput").addEventListener("input", (event) => {
    searchTerm = event.target.value;
    renderFilteredFleet();
  });
  byId("fleetExportBtn").addEventListener("click", exportFleetRegistry);
  byId("fleetAssetTableBody").addEventListener("click", handleAssetSelection);
  byId("fleetAssetTableBody").addEventListener("keydown", handleAssetSelectionKeydown);
  byId("fleetAssetCards").addEventListener("click", handleAssetSelection);
  byId("fleetTreeAssets").addEventListener("click", (event) => {
    const target = event.target.closest("[data-fleet-tree-asset]");
    if (!target) return;
    showAsset(Number(target.dataset.fleetTreeAsset)).catch((error) => {
      showFleetActionError("fleet.asset-detail", error);
    });
  });
  byId("fleetWorkspaceSidebar").addEventListener("click", (event) => {
    const module = event.target.closest("[data-fleet-module]")?.dataset.fleetModule;
    if (!module) return;
    document.querySelectorAll("[data-fleet-module]").forEach(
      (node) => node.classList.toggle("active", node.dataset.fleetModule === module),
    );
    if (module === "library") showFleetLibrary();
    if (module === "journal") showJournalGateway();
    if (module === "damage") {
      showDamageWorkspace().catch((error) => showFleetActionError("fleet.damage", error));
      closeFleetSidebar();
    }
  });
  document.addEventListener("damage:open", (event) => {
    document.querySelectorAll("[data-fleet-module]").forEach(
      (node) => node.classList.toggle("active", node.dataset.fleetModule === "damage"),
    );
    showDamageWorkspace(event.detail || {}).catch(
      (error) => showFleetActionError("fleet.damage", error),
    );
  });
  byId("fleetDossierDamageCases").addEventListener("click", (event) => {
    const caseId = event.target.closest("[data-damage-case-link]")?.dataset.damageCaseLink;
    if (caseId) {
      document.dispatchEvent(new CustomEvent("damage:open", { detail: { caseId } }));
    }
  });
  byId("fleetDossierBack").addEventListener("click", showFleetLibrary);
  byId("fleetSidebarToggle").addEventListener("click", () => {
    setFleetSidebar(!byId("fleetWorkspaceSidebar").classList.contains("open"));
  });
  byId("fleetSidebarClose").addEventListener("click", closeFleetSidebar);
  byId("fleetSidebarBackdrop").addEventListener("click", closeFleetSidebar);
  byId("fleetAssetDetailClose").addEventListener("click", hideAssetDetail);
  byId("editAssetBtn").addEventListener("click", () => openAssetEditor(selectedAsset()));
  byId("observeAvailabilityBtn").addEventListener("click", () => {
    openAvailabilityEditor(selectedAsset());
  });
  byId("addAssetDocumentBtn").addEventListener("click", () => {
    openDocumentEditor(selectedAsset());
  });
  byId("assetEditorForm").addEventListener("submit", submitAsset);
  byId("availabilityEditorForm").addEventListener("submit", submitAvailability);
  byId("documentEditorForm").addEventListener("submit", submitDocument);
  byId("closeAssetEditorBtn").addEventListener("click", () => closeDialog("assetEditor"));
  byId("cancelAssetEditorBtn").addEventListener("click", () => closeDialog("assetEditor"));
  byId("closeAvailabilityEditorBtn").addEventListener("click", () => closeDialog("availabilityEditor"));
  byId("cancelAvailabilityEditorBtn").addEventListener("click", () => closeDialog("availabilityEditor"));
  byId("closeDocumentEditorBtn").addEventListener("click", () => closeDialog("documentEditor"));
  byId("cancelDocumentEditorBtn").addEventListener("click", () => closeDialog("documentEditor"));
}
