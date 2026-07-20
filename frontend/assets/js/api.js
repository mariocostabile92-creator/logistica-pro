import { ApiError } from "./utils/errors.js";


const API_BASE = globalThis.OPERATIONS_API_URL || "";


async function parseResponse(response) {
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = data.detail;
    const message = typeof detail === "object"
      ? detail.message || detail.code
      : detail;
    throw new ApiError(message || "Operazione non riuscita.", {
      status: response.status,
      code: typeof detail === "object" ? detail.code || null : null,
      detail,
    });
  }
  return data;
}


export async function getHealth() {
  return parseResponse(await fetch(`${API_BASE}/api/health`));
}


export async function getLatestDailyBriefing() {
  return parseResponse(await fetch(`${API_BASE}/api/briefing/v1/daily/latest`));
}


export async function generateDailyBriefing(planningId = null) {
  const payload = planningId ? { planning_id: planningId } : {};
  return parseResponse(await fetch(`${API_BASE}/api/briefing/v1/daily/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }));
}


export async function getDemoWorkspaceStatus() {
  return parseResponse(await fetch(`${API_BASE}/api/demo/v1/status`));
}


export async function loadDemoWorkspace() {
  return parseResponse(await fetch(`${API_BASE}/api/demo/v1/load`, {
    method: "POST",
  }));
}


export async function resetDemoWorkspace() {
  return parseResponse(await fetch(`${API_BASE}/api/demo/v1/reset`, {
    method: "POST",
  }));
}


export async function getCurrentConfiguration(
  organizationId = "default",
  operationalUnitId = null,
) {
  const params = new URLSearchParams({ organization_id: organizationId });
  if (operationalUnitId) {
    params.set("operational_unit_id", operationalUnitId);
  }
  return parseResponse(await fetch(`${API_BASE}/api/configuration/v1/current?${params}`));
}


export async function listFleetAssets() {
  return parseResponse(await fetch(`${API_BASE}/api/plugins/fleet/v1/assets`));
}


export async function getFleetAsset(assetId) {
  return parseResponse(await fetch(`${API_BASE}/api/plugins/fleet/v1/assets/${assetId}`));
}


export async function createFleetAsset(payload) {
  return parseResponse(await fetch(`${API_BASE}/api/plugins/fleet/v1/assets`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }));
}


export async function updateFleetAsset(assetId, payload) {
  return parseResponse(await fetch(`${API_BASE}/api/plugins/fleet/v1/assets/${assetId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }));
}


export async function observeFleetAssetAvailability(assetId, payload) {
  return parseResponse(await fetch(`${API_BASE}/api/plugins/fleet/v1/assets/${assetId}/availability`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }));
}


export async function addFleetAssetDocument(assetId, payload) {
  return parseResponse(await fetch(`${API_BASE}/api/plugins/fleet/v1/assets/${assetId}/documents`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }));
}


export async function getFleetAssetEvents(assetId) {
  return parseResponse(await fetch(`${API_BASE}/api/plugins/fleet/v1/assets/${assetId}/events`));
}


export async function previewImport(file, datasetType, sheetName) {
  const form = new FormData();
  form.append("file", file);
  form.append("dataset_type", datasetType);
  if (sheetName) form.append("sheet_name", sheetName);
  return parseResponse(await fetch(`${API_BASE}/api/imports/preview`, { method: "POST", body: form }));
}


export async function importDataset(file, datasetType, sheetName) {
  const form = new FormData();
  form.append("file", file);
  if (sheetName) form.append("sheet_name", sheetName);
  return parseResponse(await fetch(`${API_BASE}/api/imports/${datasetType}`, { method: "POST", body: form }));
}


export async function analyzeOperations(reserveThreshold) {
  return parseResponse(await fetch(`${API_BASE}/api/operations/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reserve_threshold: reserveThreshold }),
  }));
}


export async function getOperationsDashboard(reserveThreshold = 1) {
  const params = new URLSearchParams({ reserve_threshold: String(reserveThreshold) });
  return parseResponse(await fetch(`${API_BASE}/api/operations/dashboard?${params}`));
}


export async function generatePlanning(payload) {
  return parseResponse(await fetch(`${API_BASE}/api/planning/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }));
}


export async function getLatestPlanning() {
  return parseResponse(await fetch(`${API_BASE}/api/planning/latest`));
}


export async function getPlanning(planningId) {
  return parseResponse(await fetch(`${API_BASE}/api/planning/${planningId}`));
}


export async function patchPlanningAssignment(assignmentId, payload) {
  return parseResponse(await fetch(`${API_BASE}/api/planning/assignments/${assignmentId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }));
}


export async function recalculatePlanning(planningId) {
  return parseResponse(await fetch(`${API_BASE}/api/planning/${planningId}/recalculate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  }));
}


export async function simulatePlanningEvent(planningId, payload) {
  return parseResponse(await fetch(`${API_BASE}/api/planning/${planningId}/simulate-event`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }));
}


export async function applyPlanningEvent(planningId, payload) {
  return parseResponse(await fetch(`${API_BASE}/api/planning/${planningId}/apply-event`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }));
}


export async function getPlanningHistory(planningId) {
  return parseResponse(await fetch(`${API_BASE}/api/planning/${planningId}/history`));
}


export async function downloadPlanningCsv(planningId) {
  const response = await fetch(`${API_BASE}/api/planning/${planningId}/export?format=csv`);
  if (!response.ok) {
    await parseResponse(response);
    return;
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `planning-operativo-${planningId}.csv`;
  link.click();
  URL.revokeObjectURL(url);
}
