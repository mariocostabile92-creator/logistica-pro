import {
  addFleetAssetDocument,
  createFleetAsset,
  getFleetAsset,
  getFleetAssetEvents,
  listFleetAssets,
  observeFleetAssetAvailability,
  updateFleetAsset,
} from "../api.js";
import { state } from "../state.js";
import { byId, setLoading, setMessage } from "../utils/dom.js";
import {
  reportUnexpectedError,
  userErrorPresentation,
} from "../utils/errors.js";
import {
  hideAssetDetail,
  renderAssetDetail,
  renderAssetList,
  renderFleetFailure,
  renderFleetLoading,
} from "./fleet-view.js";


let loaded = false;
let demoEnabled = false;


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
  const [asset, events] = await Promise.all([
    getFleetAsset(assetId),
    getFleetAssetEvents(assetId),
  ]);
  state.fleetPlugin.selectedAssetId = assetId;
  renderAssetDetail(asset, events.items);
}


async function refreshFleet(selectedAssetId = state.fleetPlugin.selectedAssetId) {
  renderFleetLoading();
  const response = await listFleetAssets();
  state.fleetPlugin.assets = response.items;
  renderAssetList(response.items, { demoEnabled });
  byId("fleetPluginTimestamp").textContent = response.items.length
    ? `${response.items.length} asset registrati.`
    : "Nessun Asset registrato.";
  document.dispatchEvent(new CustomEvent("fleet:registry-loaded", {
    detail: { assetCount: response.items.length },
  }));
  if (selectedAssetId && response.items.some((item) => item.id === selectedAssetId)) {
    await showAsset(selectedAssetId);
  } else {
    state.fleetPlugin.selectedAssetId = null;
    hideAssetDetail();
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
  const button = event.target.closest("[data-fleet-action='select']");
  if (!button) return;
  try {
    await showAsset(Number(button.dataset.assetId));
    setMessage("");
  } catch (error) {
    showFleetActionError("fleet.asset-detail", error);
  }
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
      renderAssetList([], { demoEnabled });
    }
  });
  document.addEventListener("workspace:status-changed", (event) => {
    demoEnabled = Boolean(
      event.detail.demo_enabled
      && event.detail.workspace_state === "EMPTY"
    );
    if (loaded && state.fleetPlugin.assets.length === 0) {
      renderAssetList([], { demoEnabled });
    }
  });
  byId("fleetViewState").addEventListener("click", (event) => {
    const action = event.target.closest("[data-view-action]")?.dataset.viewAction;
    if (action === "create-asset") openAssetEditor();
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
  byId("fleetAssetTableBody").addEventListener("click", handleAssetSelection);
  byId("fleetAssetCards").addEventListener("click", handleAssetSelection);
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
