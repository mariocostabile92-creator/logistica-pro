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


export async function getWorkspaceStatus({ signal } = {}) {
  return parseResponse(await fetch(`${API_BASE}/api/workspace/v1/status`, { signal }));
}


export async function resetWorkspace() {
  return parseResponse(await fetch(`${API_BASE}/api/workspace/v1/reset`, {
    method: "POST",
  }));
}


export async function getLatestDailyBriefing({ signal } = {}) {
  return parseResponse(await fetch(`${API_BASE}/api/briefing/v1/daily/latest`, { signal }));
}


export async function generateDailyBriefing(planningId = null, { signal } = {}) {
  const payload = planningId ? { planning_id: planningId } : {};
  return parseResponse(await fetch(`${API_BASE}/api/briefing/v1/daily/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal,
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

export async function saveFleetAssetProfile(assetId, payload) {
  return parseResponse(await fetch(
    `${API_BASE}/api/plugins/fleet/v1/assets/${assetId}/profile`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  ));
}


export async function changeVehicleOperationalStatus(vehicleId, payload) {
  return parseResponse(await fetch(`${API_BASE}/api/fleet/vehicles/${vehicleId}/operational-status`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }));
}


export async function getFleetVehicleHistory(assetId) {
  return parseResponse(await fetch(
    `${API_BASE}/api/plugins/fleet/v1/journal/vehicles/${assetId}/history`,
  ));
}

export async function listDamageCases(params = {}) {
  const query = new URLSearchParams(Object.entries(params).filter(([, value]) => value != null && value !== ""));
  return parseResponse(await fetch(`${API_BASE}/api/fleet/damage-cases?${query}`));
}

export async function getDamageCase(caseId) {
  return parseResponse(await fetch(`${API_BASE}/api/fleet/damage-cases/${caseId}`));
}

export async function listDamageCandidates() {
  return parseResponse(await fetch(`${API_BASE}/api/fleet/damage-candidates`));
}

export async function createDamageCase(payload) {
  return parseResponse(await fetch(`${API_BASE}/api/fleet/damage-cases`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
  }));
}

export async function updateDamageCase(caseId, payload) {
  return parseResponse(await fetch(`${API_BASE}/api/fleet/damage-cases/${caseId}`, {
    method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
  }));
}

export async function changeDamageCaseStatus(caseId, payload) {
  return parseResponse(await fetch(`${API_BASE}/api/fleet/damage-cases/${caseId}/status`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
  }));
}

export async function addDamageCaseNote(caseId, payload) {
  return parseResponse(await fetch(`${API_BASE}/api/fleet/damage-cases/${caseId}/notes`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
  }));
}

export async function listMaintenances(params = {}) {
  const query = new URLSearchParams(
    Object.entries(params).filter(([, value]) => value != null && value !== ""),
  );
  return parseResponse(await fetch(`${API_BASE}/api/fleet/maintenances?${query}`));
}

export async function getMaintenance(maintenanceId) {
  return parseResponse(await fetch(
    `${API_BASE}/api/fleet/maintenances/${maintenanceId}`,
  ));
}

export async function createMaintenance(payload) {
  return parseResponse(await fetch(`${API_BASE}/api/fleet/maintenances`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }));
}

export async function updateMaintenance(maintenanceId, payload) {
  return parseResponse(await fetch(
    `${API_BASE}/api/fleet/maintenances/${maintenanceId}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  ));
}

export async function listVehicleDocuments(params = {}) {
  const query = new URLSearchParams(
    Object.entries(params).filter(([, value]) => value != null && value !== ""),
  );
  return parseResponse(await fetch(`${API_BASE}/api/fleet/documents?${query}`));
}

export async function getVehicleDocument(documentId) {
  return parseResponse(await fetch(`${API_BASE}/api/fleet/documents/${documentId}`));
}

export async function createVehicleDocument(payload) {
  return parseResponse(await fetch(`${API_BASE}/api/fleet/documents`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }));
}

export async function updateVehicleDocument(documentId, payload) {
  return parseResponse(await fetch(`${API_BASE}/api/fleet/documents/${documentId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }));
}

export async function archiveVehicleDocument(documentId) {
  return parseResponse(await fetch(`${API_BASE}/api/fleet/documents/${documentId}/archive`, {
    method: "POST",
  }));
}

export async function listFranchiseCases(params = {}) {
  const query = new URLSearchParams(
    Object.entries(params).filter(([, value]) => value != null && value !== ""),
  );
  return parseResponse(await fetch(`${API_BASE}/api/fleet/franchises?${query}`));
}

export async function getFranchiseCase(caseId) {
  return parseResponse(await fetch(`${API_BASE}/api/fleet/franchises/${caseId}`));
}

export async function ensureFranchiseCase(payload) {
  return parseResponse(await fetch(`${API_BASE}/api/fleet/franchises`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }));
}

export async function updateFranchiseCase(caseId, payload) {
  return parseResponse(await fetch(`${API_BASE}/api/fleet/franchises/${caseId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }));
}

export async function listInsurancePolicies(params = {}) {
  const query = new URLSearchParams(
    Object.entries(params).filter(([, value]) => value != null && value !== ""),
  );
  return parseResponse(await fetch(`${API_BASE}/api/fleet/insurance-policies?${query}`));
}

export async function getInsurancePolicy(policyId) {
  return parseResponse(await fetch(`${API_BASE}/api/fleet/insurance-policies/${policyId}`));
}

export async function createInsurancePolicy(payload) {
  return parseResponse(await fetch(`${API_BASE}/api/fleet/insurance-policies`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }));
}

export async function updateInsurancePolicy(policyId, payload) {
  return parseResponse(await fetch(`${API_BASE}/api/fleet/insurance-policies/${policyId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }));
}

export async function listRentals(params = {}) {
  const query = new URLSearchParams(
    Object.entries(params).filter(([, value]) => value != null && value !== ""),
  );
  return parseResponse(await fetch(`${API_BASE}/api/fleet/rentals?${query}`));
}

export async function listFleetDeadlines(params = {}) {
  const query = new URLSearchParams(
    Object.entries(params).filter(([, value]) => value != null && value !== ""),
  );
  return parseResponse(await fetch(`${API_BASE}/api/fleet/deadlines?${query}`));
}

export async function listJournalControlRoom(params = {}) {
  const query = new URLSearchParams(
    Object.entries(params).filter(([, value]) => value != null && value !== ""),
  );
  return parseResponse(await fetch(`${API_BASE}/api/fleet/journal-control-room?${query}`));
}

export async function getJournalControlRoomProcedure(procedureId) {
  return parseResponse(await fetch(
    `${API_BASE}/api/fleet/journal-control-room/${encodeURIComponent(procedureId)}`,
  ));
}

export async function getJournalArchiveMonth(month) {
  return parseResponse(await fetch(
    `${API_BASE}/api/fleet/journal-archive/month?month=${encodeURIComponent(month)}`,
  ));
}

export async function getJournalArchiveDay(date, params = {}) {
  const query = new URLSearchParams({ date });
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") query.set(key, value);
  });
  return parseResponse(await fetch(`${API_BASE}/api/fleet/journal-archive/day?${query}`));
}

export async function deleteJournalMedia(mediaId) {
  return parseResponse(await fetch(
    `${API_BASE}/api/fleet/journal-control-room/media/${encodeURIComponent(mediaId)}`,
    { method: "DELETE" },
  ));
}

export async function createJournalDriverSession(payload) {
  return parseResponse(await fetch(`${API_BASE}/api/fleet/journal-control-room/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }));
}

export async function getActiveJournalSharedAccess() {
  return parseResponse(await fetch(
    `${API_BASE}/api/fleet/journal-control-room/shared-access/active`,
  ));
}

export async function createJournalSharedAccess(regenerate = false) {
  return parseResponse(await fetch(
    `${API_BASE}/api/fleet/journal-control-room/shared-access`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ regenerate }),
    },
  ));
}

export async function revokeJournalSharedAccess(accessId) {
  return parseResponse(await fetch(
    `${API_BASE}/api/fleet/journal-control-room/shared-access/${encodeURIComponent(accessId)}/revoke`,
    { method: "POST" },
  ));
}

export async function getFleetVision(params = {}) {
  const query = new URLSearchParams(
    Object.entries(params).filter(([, value]) => value != null && value !== ""),
  );
  return parseResponse(await fetch(`${API_BASE}/api/fleet/vision?${query}`));
}

export async function getRental(rentalId) {
  return parseResponse(await fetch(`${API_BASE}/api/fleet/rentals/${rentalId}`));
}

export async function createRental(payload) {
  return parseResponse(await fetch(`${API_BASE}/api/fleet/rentals`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }));
}

export async function updateRental(rentalId, payload) {
  return parseResponse(await fetch(`${API_BASE}/api/fleet/rentals/${rentalId}`, {
    method: "PATCH", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }));
}


export async function getWorkforceStatus() {
  return parseResponse(await fetch(`${API_BASE}/api/plugins/workforce/v1/status`));
}


export async function listWorkforceMembers() {
  return parseResponse(await fetch(`${API_BASE}/api/plugins/workforce/v1/members`));
}


export async function getWorkforceCalendar(dateFrom = "", dateTo = "") {
  const params = new URLSearchParams();
  if (dateFrom) params.set("date_from", dateFrom);
  if (dateTo) params.set("date_to", dateTo);
  return parseResponse(await fetch(`${API_BASE}/api/plugins/workforce/v1/calendar?${params}`));
}


export async function getWorkforceCoverage(dateFrom = "", dateTo = "") {
  const params = new URLSearchParams();
  if (dateFrom) params.set("date_from", dateFrom);
  if (dateTo) params.set("date_to", dateTo);
  return parseResponse(await fetch(`${API_BASE}/api/plugins/workforce/v1/coverage?${params}`));
}


export async function getWorkforceChanges() {
  return parseResponse(await fetch(`${API_BASE}/api/plugins/workforce/v1/changes`));
}


export async function previewWorkforceImport(file) {
  const form = new FormData();
  form.append("file", file);
  return parseResponse(await fetch(`${API_BASE}/api/plugins/workforce/v1/import/preview`, {
    method: "POST",
    body: form,
  }));
}


export async function confirmWorkforceImport(file, fingerprint) {
  const form = new FormData();
  form.append("file", file);
  form.append("confirmed_fingerprint", fingerprint);
  return parseResponse(await fetch(`${API_BASE}/api/plugins/workforce/v1/import`, {
    method: "POST",
    body: form,
  }));
}


export async function saveWorkforceDayStatus(statusId, payload) {
  const path = statusId
    ? `/api/plugins/workforce/v1/day-status/${statusId}`
    : "/api/plugins/workforce/v1/day-status";
  return parseResponse(await fetch(`${API_BASE}${path}`, {
    method: statusId ? "PATCH" : "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }));
}


export async function updateWorkforceMember(memberId, payload) {
  return parseResponse(await fetch(`${API_BASE}/api/plugins/workforce/v1/members/${memberId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }));
}


export async function downloadWorkforceExport(section = "calendar") {
  const response = await fetch(`${API_BASE}/api/plugins/workforce/v1/export?section=${encodeURIComponent(section)}`);
  if (!response.ok) return parseResponse(response);
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `workforce-${section}.csv`;
  link.click();
  URL.revokeObjectURL(url);
}


export async function previewFleetSync(file, options = {}) {
  const form = new FormData();
  form.append("file", file);
  appendImportOptions(form, options);
  return parseResponse(await fetch(`${API_BASE}/api/plugins/fleet/v1/sync/preview`, {
    method: "POST",
    body: form,
  }));
}


export async function confirmFleetSync(file, fingerprint, selectedRows, options = {}) {
  const form = new FormData();
  form.append("file", file);
  form.append("confirmed_fingerprint", fingerprint);
  form.append("selected_rows", JSON.stringify(selectedRows));
  appendImportOptions(form, options);
  return parseResponse(await fetch(`${API_BASE}/api/plugins/fleet/v1/sync/confirm`, {
    method: "POST",
    body: form,
  }));
}


export async function getLatestFleetSync() {
  return parseResponse(await fetch(`${API_BASE}/api/plugins/fleet/v1/sync/latest`));
}


function appendImportOptions(
  form,
  {
    sheetName = "",
    headerRow = null,
    columnMapping = [],
  } = {},
) {
  if (sheetName) form.append("sheet_name", sheetName);
  if (headerRow) form.append("header_row", String(headerRow));
  if (columnMapping.length) {
    form.append("column_mapping", JSON.stringify(columnMapping));
  }
}


export async function previewImport(file, datasetType, options = {}) {
  const form = new FormData();
  form.append("file", file);
  form.append("dataset_type", datasetType);
  appendImportOptions(form, options);
  return parseResponse(await fetch(`${API_BASE}/api/imports/preview`, { method: "POST", body: form }));
}


export async function importDataset(file, datasetType, options = {}) {
  const form = new FormData();
  form.append("file", file);
  appendImportOptions(form, options);
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


export async function getPlanningReadiness({
  organizationId = "default",
  operationalUnitId = "default",
  planningDate = null,
  signal,
} = {}) {
  const params = new URLSearchParams({
    organization_id: organizationId,
    operational_unit_id: operationalUnitId,
  });
  if (planningDate) params.set("operation_date", planningDate);
  return parseResponse(await fetch(
    `${API_BASE}/api/planning/readiness?${params}`,
    { signal },
  ));
}


export async function getPlanningConflicts({
  organizationId = "default",
  operationalUnitId = "default",
  planningDate = null,
  signal,
} = {}) {
  const params = new URLSearchParams({
    organization_id: organizationId,
    operational_unit_id: operationalUnitId,
  });
  if (planningDate) params.set("operation_date", planningDate);
  return parseResponse(await fetch(
    `${API_BASE}/api/planning/conflicts?${params}`,
    { signal },
  ));
}


export async function getPlanningTimeline({
  organizationId = "default",
  operationalUnitId = "default",
  planningDate = null,
  signal,
} = {}) {
  const params = new URLSearchParams({
    organization_id: organizationId,
    operational_unit_id: operationalUnitId,
  });
  if (planningDate) params.set("operation_date", planningDate);
  return parseResponse(await fetch(
    `${API_BASE}/api/planning/timeline?${params}`,
    { signal },
  ));
}


export async function getCurrentPlanningDraft({
  organizationId = "default",
  operationalUnitId = "default",
  planningDate = null,
  signal,
} = {}) {
  const params = new URLSearchParams({
    organization_id: organizationId,
    operational_unit_id: operationalUnitId,
  });
  if (planningDate) params.set("planning_date", planningDate);
  return parseResponse(await fetch(
    `${API_BASE}/api/planning/drafts/current?${params}`,
    { signal },
  ));
}


export async function createPlanningDraft(payload, { signal } = {}) {
  return parseResponse(await fetch(`${API_BASE}/api/planning/drafts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal,
  }));
}


export async function updatePlanningDraftMetadata(
  draftId,
  payload,
  { signal } = {},
) {
  return parseResponse(await fetch(
    `${API_BASE}/api/planning/drafts/${encodeURIComponent(draftId)}/metadata`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal,
    },
  ));
}


export async function savePlanningDraft(draftId, payload, { signal } = {}) {
  return parseResponse(await fetch(
    `${API_BASE}/api/planning/drafts/${encodeURIComponent(draftId)}/save`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal,
    },
  ));
}


export async function restorePlanningDraft(draftId, payload, { signal } = {}) {
  return parseResponse(await fetch(
    `${API_BASE}/api/planning/drafts/${encodeURIComponent(draftId)}/restore`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal,
    },
  ));
}


export async function deletePlanningDraft(
  draftId,
  expectedVersion,
  { signal } = {},
) {
  const params = new URLSearchParams({
    expected_version: String(expectedVersion),
  });
  return parseResponse(await fetch(
    `${API_BASE}/api/planning/drafts/${encodeURIComponent(draftId)}?${params}`,
    { method: "DELETE", signal },
  ));
}


export async function getCurrentPlanningConfirmation({
  organizationId = "default",
  operationalUnitId = "default",
  planningDate = null,
  signal,
} = {}) {
  const params = new URLSearchParams({
    organization_id: organizationId,
    operational_unit_id: operationalUnitId,
  });
  if (planningDate) params.set("planning_date", planningDate);
  return parseResponse(await fetch(
    `${API_BASE}/api/planning/confirmation/current?${params}`,
    { signal },
  ));
}


export async function validatePlanningConfirmation(payload, { signal } = {}) {
  return parseResponse(await fetch(
    `${API_BASE}/api/planning/confirmation/validate`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal,
    },
  ));
}


export async function confirmPlanningConfirmation(payload, { signal } = {}) {
  return parseResponse(await fetch(
    `${API_BASE}/api/planning/confirmation/confirm`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal,
    },
  ));
}


export async function getPlanningConfirmationHistory({
  organizationId = "default",
  operationalUnitId = "default",
  planningDate = null,
  signal,
} = {}) {
  const params = new URLSearchParams({
    organization_id: organizationId,
    operational_unit_id: operationalUnitId,
  });
  if (planningDate) params.set("planning_date", planningDate);
  return parseResponse(await fetch(
    `${API_BASE}/api/planning/confirmation/history?${params}`,
    { signal },
  ));
}


export async function getCurrentPlanningPublication({
  organizationId = "default",
  operationalUnitId = "default",
  planningDate = null,
  signal,
} = {}) {
  const params = new URLSearchParams({
    organization_id: organizationId,
    operational_unit_id: operationalUnitId,
  });
  if (planningDate) params.set("planning_date", planningDate);
  return parseResponse(await fetch(
    `${API_BASE}/api/planning/publication/current?${params}`,
    { signal },
  ));
}


export async function validatePlanningPublication(payload, { signal } = {}) {
  return parseResponse(await fetch(
    `${API_BASE}/api/planning/publication/validate`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal,
    },
  ));
}


export async function publishPlanningPublication(payload, { signal } = {}) {
  return parseResponse(await fetch(
    `${API_BASE}/api/planning/publication/publish`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal,
    },
  ));
}


export async function getPlanningPublicationHistory({
  organizationId = "default",
  operationalUnitId = "default",
  planningDate = null,
  signal,
} = {}) {
  const params = new URLSearchParams({
    organization_id: organizationId,
    operational_unit_id: operationalUnitId,
  });
  if (planningDate) params.set("planning_date", planningDate);
  return parseResponse(await fetch(
    `${API_BASE}/api/planning/publication/history?${params}`,
    { signal },
  ));
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
