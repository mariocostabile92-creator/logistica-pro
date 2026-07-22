const DRAFT_STATES = Object.freeze([
  "EMPTY",
  "CREATED",
  "DIRTY",
  "SAVED",
  "READ_ONLY",
  "ERROR",
]);
const CHANGE_TYPES = Object.freeze([
  "CREATED",
  "METADATA_UPDATED",
  "SAVED",
  "RESTORED",
  "DELETED",
]);


function text(value, field) {
  if (typeof value !== "string" || !value.trim()) {
    throw new TypeError(`Campo Draft non valido: ${field}.`);
  }
  return value.trim();
}


function count(value, field) {
  if (!Number.isInteger(value) || value < 0) {
    throw new TypeError(`Conteggio Draft non valido: ${field}.`);
  }
  return value;
}


function normalizeVersion(value) {
  const number = count(value?.number, "version.number");
  if (number < 1) throw new TypeError("Versione Draft non valida.");
  return Object.freeze({
    number,
    createdAt: text(value?.created_at, "version.created_at"),
    createdBy: text(value?.created_by, "version.created_by"),
    restoredFromVersion: value?.restored_from_version || null,
  });
}


function normalizeDraft(value) {
  const state = text(value?.state, "draft.state").toUpperCase();
  if (!DRAFT_STATES.includes(state) || ["EMPTY", "ERROR"].includes(state)) {
    throw new TypeError("Stato Draft persistito non riconosciuto.");
  }
  return Object.freeze({
    id: text(value?.draft_id, "draft.draft_id"),
    state,
    name: text(value?.metadata?.name, "draft.metadata.name"),
    note: value?.metadata?.note || "",
    version: normalizeVersion(value?.version),
    createdAt: text(value?.created_at, "draft.created_at"),
    updatedAt: text(value?.updated_at, "draft.updated_at"),
    deletedAt: value?.deleted_at || null,
    scope: Object.freeze({
      organizationId: text(
        value?.scope?.organization_id,
        "draft.scope.organization_id",
      ),
      operationalUnitId: text(
        value?.scope?.operational_unit?.external_identifier,
        "draft.scope.operational_unit.external_identifier",
      ),
      planningDate: text(value?.scope?.planning_date, "draft.scope.planning_date"),
    }),
  });
}


function normalizeChange(value) {
  const changeType = text(value?.change_type, "change.change_type").toUpperCase();
  if (!CHANGE_TYPES.includes(changeType)) {
    throw new TypeError("Tipo modifica Draft non riconosciuto.");
  }
  return Object.freeze({
    id: text(value?.change_id, "change.change_id"),
    changeType,
    fromVersion: value?.from_version || null,
    toVersion: count(value?.to_version, "change.to_version"),
    actor: text(value?.actor, "change.actor"),
    occurredAt: text(value?.occurred_at, "change.occurred_at"),
    summary: text(value?.summary, "change.summary"),
  });
}


function normalizeSnapshot(value) {
  const state = text(value?.state, "snapshot.state").toUpperCase();
  if (!DRAFT_STATES.includes(state) || ["EMPTY", "ERROR"].includes(state)) {
    throw new TypeError("Stato snapshot Draft non riconosciuto.");
  }
  return Object.freeze({
    id: text(value?.snapshot_id, "snapshot.snapshot_id"),
    state,
    version: normalizeVersion(value?.version),
    name: text(value?.metadata?.name, "snapshot.metadata.name"),
  });
}


function normalizeHistory(value, draftId) {
  const changes = Object.freeze((value?.changes || []).map(normalizeChange));
  const snapshots = Object.freeze((value?.snapshots || []).map(normalizeSnapshot));
  const totalChanges = count(value?.total_changes, "history.total_changes");
  const totalVersions = count(value?.total_versions, "history.total_versions");
  if (text(value?.draft_id, "history.draft_id") !== draftId) {
    throw new TypeError("Cronologia associata a un altro Draft.");
  }
  if (totalChanges < changes.length || totalVersions < snapshots.length) {
    throw new TypeError("Conteggi cronologia Draft incoerenti.");
  }
  return Object.freeze({ totalChanges, totalVersions, changes, snapshots });
}


export function normalizePlanningDraftWorkspace(payload) {
  if (!payload || typeof payload !== "object") {
    throw new TypeError("Risposta Planning Draft non valida.");
  }
  const state = text(payload.state, "state").toUpperCase();
  if (!DRAFT_STATES.includes(state)) {
    throw new TypeError("Stato Planning Draft non riconosciuto.");
  }
  if (state === "EMPTY") {
    return Object.freeze({ viewState: "empty", state, draft: null, history: null });
  }
  if (!payload.draft || !payload.history) {
    throw new TypeError("Draft e cronologia sono obbligatori.");
  }
  const draft = normalizeDraft(payload.draft);
  if (draft.state !== state) {
    throw new TypeError("Stato workspace Draft incoerente.");
  }
  return Object.freeze({
    viewState: state === "READ_ONLY" ? "read-only" : "ready",
    state,
    draft,
    history: normalizeHistory(payload.history, draft.id),
  });
}


export function createPlanningDraftLoader(request) {
  let pending = null;
  let controller = null;
  return Object.freeze({
    load(parameters = {}) {
      if (pending) return pending;
      controller = new AbortController();
      pending = request({ ...parameters, signal: controller.signal })
        .finally(() => {
          pending = null;
          controller = null;
        });
      return pending;
    },
    abort() {
      controller?.abort();
    },
  });
}
