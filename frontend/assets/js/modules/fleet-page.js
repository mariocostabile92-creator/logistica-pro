import {
  addFleetAssetDocument,
  createFleetAsset,
  getFleetAsset,
  getFleetVehicleHistory,
  getLatestFleetSync,
  listFleetAssets,
  listDamageCases,
  listMaintenances,
  listVehicleDocuments,
  listFranchiseCases,
  listInsurancePolicies,
  listRentals,
  listFleetDeadlines,
  saveFleetAssetProfile,
  updateFleetAsset,
} from "../api.js";
import { state } from "../state.js";
import { mountAttachments } from "./attachments/component.js";
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
} from "./fleet-view.js?v=3";
import { showDamageWorkspace } from "./damage-workspace.js?v=4";
import { showMaintenanceWorkspace } from "./maintenance-workspace.js?v=1";
import { showDocumentsWorkspace } from "./documents-workspace.js?v=1";
import { showFranchiseWorkspace } from "./franchise-workspace.js?v=1";
import { showInsuranceWorkspace } from "./insurance-workspace.js?v=1";
import { showRentalWorkspace } from "./rental-workspace.js?v=1";
import { showDeadlinesWorkspace } from "./deadlines-workspace.js?v=1";
import { showJournalControlRoom } from "./journal-control-room.js?v=1";
import { showFleetVisionWorkspace } from "./fleet-vision-workspace.js?v=1";
import { openOperationalStatusControl } from "./operational-status-control.js";


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
  byId("maintenanceWorkspace").hidden = true;
  byId("documentsWorkspace").hidden = true;
  byId("franchiseWorkspace").hidden = true;
  byId("insuranceWorkspace").hidden = true;
  byId("rentalWorkspace").hidden = true;
  byId("deadlinesWorkspace").hidden = true;
  byId("journalControlRoom").hidden = true;
  byId("fleetVisionWorkspace").hidden = true;
  byId("fleetWorkspaceHome").hidden = true;
  byId("fleetVehicleDossier").hidden = false;
  byId("fleetDossierState").hidden = false;
  byId("fleetDossierState").className = "view-state loading";
  byId("fleetDossierState").textContent = "Caricamento scheda mezzo";
  byId("fleetDossierContent").hidden = true;
  const [asset, history, damageCases, maintenances, documents, franchises, insurance, rentals, deadlines] = await Promise.all([
    getFleetAsset(assetId),
    getFleetVehicleHistory(assetId),
    listDamageCases().then((response) => response.items),
    listMaintenances({ vehicle_id: assetId }).then((response) => response.items),
    listVehicleDocuments({ vehicle_id: assetId }).then((response) => response.items),
    listFranchiseCases({ vehicle_id: assetId }).then((response) => response.items),
    listInsurancePolicies({ vehicle_id: assetId }).then((response) => response.items),
    listRentals({ vehicle_id: assetId }).then((response) => response.items),
    listFleetDeadlines({ vehicle_id: assetId }).then((response) => response.items),
  ]);
  state.fleetPlugin.selectedAssetId = assetId;
  renderFleetTree(state.fleetPlugin.assets, assetId);
  byId("fleetTreeSelection").textContent = asset.plate || asset.external_identifier;
  byId("fleetTreeSelection").hidden = false;
  renderVehicleDossier(
    history,
    asset,
    damageCases.filter((item) => Number(item.vehicle_id) === Number(assetId)),
    maintenances,
    documents,
    franchises,
    insurance,
    rentals,
    deadlines,
  );
  await mountAttachments(byId("fleetDossierAttachments"), {
    entityType: "vehicle", entityId: assetId, aggregateVehicle: true,
    title: "Allegati del mezzo",
  });
  byId("fleetAssetTree").open = false;
  closeFleetSidebar();
}


function showFleetLibrary() {
  byId("damageWorkspace").hidden = true;
  byId("maintenanceWorkspace").hidden = true;
  byId("documentsWorkspace").hidden = true;
  byId("franchiseWorkspace").hidden = true;
  byId("insuranceWorkspace").hidden = true;
  byId("rentalWorkspace").hidden = true;
  state.fleetPlugin.selectedAssetId = null;
  byId("fleetVehicleDossier").hidden = true;
  byId("fleetWorkspaceHome").hidden = false;
  byId("fleetAssetTree").open = true;
  byId("fleetTreeSelection").hidden = true;
  renderFleetTree(state.fleetPlugin.assets);
  document.querySelector("[data-fleet-module='library']")?.classList.add("active");
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

function syncProfileFields() {
  const form = byId("fleetProfileForm");
  const type = form.elements.contract_type.value;
  const property = type === "proprieta";
  const other = type === "altro";
  form.querySelector("[data-profile-company]").hidden = property;
  form.querySelector("[data-profile-owner]").hidden = !property;
  form.querySelector("[data-profile-contract-number]").hidden = property;
  form.querySelector("[data-profile-start]").hidden = property;
  form.querySelector("[data-profile-end]").hidden = property;
  form.querySelector("[data-profile-status]").hidden = property;
  form.querySelector("[data-profile-purchase]").hidden = !property;
  form.querySelector("[data-profile-monthly]").hidden =
    ["breve_termine", "proprieta"].includes(type);
  form.querySelector("[data-profile-daily]").hidden =
    !["breve_termine", "altro"].includes(type);
  form.querySelector("[data-profile-deductible]").hidden =
    !["lungo_termine", "leasing", "altro"].includes(type);
  form.querySelectorAll("[data-profile-km]").forEach((field) => {
    field.hidden = !["lungo_termine", "altro"].includes(type);
  });
  form.elements.company.required = [
    "lungo_termine", "breve_termine", "leasing",
  ].includes(type);
  form.elements.monthly_fee.required = type === "lungo_termine";
  form.elements.daily_cost.required = type === "breve_termine";
  if (property) form.elements.contract_status.value = "attivo";
}

function openProfileEditor() {
  const asset = selectedAsset();
  const profile = asset?.profile || {};
  const form = byId("fleetProfileForm");
  form.reset();
  for (const [key, value] of Object.entries(profile)) {
    if (form.elements[key]) form.elements[key].value = value ?? "";
  }
  if (!profile.contract_type) form.elements.contract_type.value = "lungo_termine";
  if (!profile.contract_status) form.elements.contract_status.value = "attivo";
  byId("fleetProfileStatus").textContent = "";
  syncProfileFields();
  byId("fleetProfileEditor").showModal();
}

async function submitProfile(event) {
  event.preventDefault();
  const asset = selectedAsset();
  const values = Object.fromEntries(new FormData(event.currentTarget).entries());
  for (const field of [
    "monthly_fee", "daily_cost", "deductible", "included_km",
    "excess_km_cost", "starts_on", "expires_on",
    "purchased_on",
  ]) {
    if (values[field] === "") values[field] = null;
  }
  try {
    await saveFleetAssetProfile(asset.id, values);
    byId("fleetProfileEditor").close();
    await refreshFleet(asset.id);
  } catch (error) {
    byId("fleetProfileStatus").textContent = error.message;
  }
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
  const statusAction = event.target.closest("[data-operational-status-asset]");
  if (statusAction) {
    event.stopPropagation();
    const asset = state.fleetPlugin.assets.find(
      (item) => item.id === Number(statusAction.dataset.operationalStatusAsset),
    );
    if (asset) openOperationalStatusControl({ asset, origin: "parco_mezzi" });
    return;
  }
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
    if (module !== "deadlines") byId("deadlinesWorkspace").hidden = true;
    if (module !== "journal") byId("journalControlRoom").hidden = true;
    if (module !== "vision") byId("fleetVisionWorkspace").hidden = true;
    if (module === "library") showFleetLibrary();
    if (module === "journal") {
      showJournalControlRoom().catch(
        (error) => showFleetActionError("fleet.journal-control-room", error),
      );
      closeFleetSidebar();
    }
    if (module === "damage") {
      showDamageWorkspace().catch((error) => showFleetActionError("fleet.damage", error));
      closeFleetSidebar();
    }
    if (module === "maintenance") {
      showMaintenanceWorkspace().catch(
        (error) => showFleetActionError("fleet.maintenance", error),
      );
      closeFleetSidebar();
    }
    if (module === "documents") {
      showDocumentsWorkspace().catch(
        (error) => showFleetActionError("fleet.documents", error),
      );
      closeFleetSidebar();
    }
    if (module === "franchises") {
      showFranchiseWorkspace().catch(
        (error) => showFleetActionError("fleet.franchises", error),
      );
      closeFleetSidebar();
    }
    if (module === "insurance") {
      showInsuranceWorkspace().catch(
        (error) => showFleetActionError("fleet.insurance", error),
      );
      closeFleetSidebar();
    }
    if (module === "rentals") {
      showRentalWorkspace().catch(
        (error) => showFleetActionError("fleet.rentals", error),
      );
      closeFleetSidebar();
    }
    if (module === "deadlines") {
      showDeadlinesWorkspace().catch(
        (error) => showFleetActionError("fleet.deadlines", error),
      );
      closeFleetSidebar();
    }
    if (module === "vision") {
      showFleetVisionWorkspace().catch(
        (error) => showFleetActionError("fleet.vision", error),
      );
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
  document.addEventListener("maintenance:open", (event) => {
    document.querySelectorAll("[data-fleet-module]").forEach(
      (node) => node.classList.toggle(
        "active",
        node.dataset.fleetModule === "maintenance",
      ),
    );
    showMaintenanceWorkspace(event.detail || {}).catch(
      (error) => showFleetActionError("fleet.maintenance", error),
    );
  });
  document.addEventListener("maintenance:error", (event) => {
    setMessage(event.detail.message, "error");
  });
  document.addEventListener("documents:open", (event) => {
    document.querySelectorAll("[data-fleet-module]").forEach(
      (node) => node.classList.toggle(
        "active",
        node.dataset.fleetModule === "documents",
      ),
    );
    showDocumentsWorkspace(event.detail || {}).catch(
      (error) => showFleetActionError("fleet.documents", error),
    );
  });
  document.addEventListener("franchise:open", (event) => {
    document.querySelectorAll("[data-fleet-module]").forEach(
      (node) => node.classList.toggle(
        "active",
        node.dataset.fleetModule === "franchises",
      ),
    );
    showFranchiseWorkspace(event.detail || {}).catch(
      (error) => showFleetActionError("fleet.franchises", error),
    );
  });
  document.addEventListener("insurance:open", (event) => {
    document.querySelectorAll("[data-fleet-module]").forEach(
      (node) => node.classList.toggle(
        "active",
        node.dataset.fleetModule === "insurance",
      ),
    );
    showInsuranceWorkspace(event.detail || {}).catch(
      (error) => showFleetActionError("fleet.insurance", error),
    );
  });
  document.addEventListener("rental:open", (event) => {
    document.querySelectorAll("[data-fleet-module]").forEach(
      (node) => node.classList.toggle(
        "active", node.dataset.fleetModule === "rentals",
      ),
    );
    showRentalWorkspace(event.detail || {}).catch(
      (error) => showFleetActionError("fleet.rentals", error),
    );
  });
  document.addEventListener("deadline:open-source", (event) => {
    const item = event.detail || {};
    if (item.source_module === "document") {
      document.dispatchEvent(new CustomEvent("documents:open", { detail: { documentId: item.source_id, vehicle_id: item.vehicle_id } }));
    } else if (item.source_module === "insurance") {
      document.dispatchEvent(new CustomEvent("insurance:open", { detail: { policyId: item.source_id, vehicle_id: item.vehicle_id } }));
    } else if (item.source_module === "maintenance") {
      document.dispatchEvent(new CustomEvent("maintenance:open", { detail: { maintenanceId: item.source_id } }));
    } else {
      showAsset(Number(item.vehicle_id)).catch(
        (error) => showFleetActionError("fleet.asset-detail", error),
      );
    }
  });
  document.addEventListener("fleet:vehicle-open", (event) => {
    showAsset(Number(event.detail.assetId)).catch(
      (error) => showFleetActionError("fleet.asset-detail", error),
    );
  });
  document.addEventListener("fleet:operational-status-changed", async () => {
    await refreshFleet(state.fleetPlugin.selectedAssetId);
  });
  byId("fleetDossierDamageCases").addEventListener("click", (event) => {
    const caseId = event.target.closest("[data-damage-case-link]")?.dataset.damageCaseLink;
    if (caseId) {
      document.dispatchEvent(new CustomEvent("damage:open", { detail: { caseId } }));
    }
  });
  byId("fleetDossierMaintenances").addEventListener("click", (event) => {
    const maintenanceId = event.target.closest("[data-maintenance-link]")
      ?.dataset.maintenanceLink;
    if (maintenanceId) {
      document.dispatchEvent(new CustomEvent("maintenance:open", {
        detail: { maintenanceId: Number(maintenanceId) },
      }));
    }
  });
  byId("fleetDossierFranchises").addEventListener("click", (event) => {
    const franchiseId = event.target.closest("[data-franchise-link]")
      ?.dataset.franchiseLink;
    if (franchiseId) {
      document.dispatchEvent(new CustomEvent("franchise:open", {
        detail: { franchiseId: Number(franchiseId) },
      }));
    }
  });
  byId("fleetDossierInsurance").addEventListener("click", (event) => {
    const policyId = event.target.closest("[data-insurance-link]")?.dataset.insuranceLink;
    if (policyId) {
      document.dispatchEvent(new CustomEvent("insurance:open", {
        detail: { policyId: Number(policyId) },
      }));
    }
  });
  byId("fleetDossierRentals").addEventListener("click", (event) => {
    const rentalId = event.target.closest("[data-rental-link]")?.dataset.rentalLink;
    if (rentalId) document.dispatchEvent(new CustomEvent("rental:open", {
      detail: { rentalId: Number(rentalId) },
    }));
  });
  byId("fleetDossierManageDocuments").addEventListener("click", () => {
    document.dispatchEvent(new CustomEvent("documents:open", {
      detail: { vehicleId: state.fleetPlugin.selectedAssetId },
    }));
  });
  byId("fleetDossierManageFranchises").addEventListener("click", () => {
    document.dispatchEvent(new CustomEvent("franchise:open", {
      detail: { vehicleId: state.fleetPlugin.selectedAssetId },
    }));
  });
  byId("fleetDossierManageInsurance").addEventListener("click", () => {
    document.dispatchEvent(new CustomEvent("insurance:open", {
      detail: { vehicleId: state.fleetPlugin.selectedAssetId },
    }));
  });
  byId("fleetDossierManageRentals").addEventListener("click", () => {
    document.dispatchEvent(new CustomEvent("rental:open", {
      detail: { vehicleId: state.fleetPlugin.selectedAssetId },
    }));
  });
  byId("fleetDossierManageDeadlines").addEventListener("click", () => {
    showDeadlinesWorkspace({ vehicle_id: state.fleetPlugin.selectedAssetId }).catch(
      (error) => showFleetActionError("fleet.deadlines", error),
    );
  });
  byId("fleetDossierOpenControlRoom").addEventListener("click", () => {
    showJournalControlRoom({ vehicle_id: state.fleetPlugin.selectedAssetId }).catch(
      (error) => showFleetActionError("fleet.journal-control-room", error),
    );
  });
  byId("fleetDossierOpenVision").addEventListener("click", () => {
    showFleetVisionWorkspace({ vehicle_id: state.fleetPlugin.selectedAssetId }).catch(
      (error) => showFleetActionError("fleet.vision", error),
    );
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
    openOperationalStatusControl({
      asset: selectedAsset(),
      origin: "parco_mezzi",
    });
  });
  byId("fleetDossierChangeStatus").addEventListener("click", () => {
    const asset = selectedAsset();
    openOperationalStatusControl({
      asset,
      origin: "vehicle_library",
    });
  });
  byId("fleetProfileEdit").addEventListener("click", openProfileEditor);
  byId("fleetProfileForm").elements.contract_type.addEventListener(
    "change",
    syncProfileFields,
  );
  byId("fleetProfileForm").addEventListener("submit", submitProfile);
  byId("fleetProfileClose").addEventListener(
    "click",
    () => byId("fleetProfileEditor").close(),
  );
  byId("fleetProfileCancel").addEventListener(
    "click",
    () => byId("fleetProfileEditor").close(),
  );
  byId("addAssetDocumentBtn").addEventListener("click", () => {
    openDocumentEditor(selectedAsset());
  });
  byId("assetEditorForm").addEventListener("submit", submitAsset);
  byId("documentEditorForm").addEventListener("submit", submitDocument);
  byId("closeAssetEditorBtn").addEventListener("click", () => closeDialog("assetEditor"));
  byId("cancelAssetEditorBtn").addEventListener("click", () => closeDialog("assetEditor"));
  byId("closeDocumentEditorBtn").addEventListener("click", () => closeDialog("documentEditor"));
  byId("cancelDocumentEditorBtn").addEventListener("click", () => closeDialog("documentEditor"));
}
