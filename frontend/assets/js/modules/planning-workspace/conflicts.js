import { normalizePlanningReadiness } from "./readiness.js";


const CATEGORIES = Object.freeze([
  "WORKFORCE",
  "FLEET",
  "CAPABILITY",
  "OPERATIONAL_UNIT",
  "VALIDATION",
  "FRESHNESS",
  "VERSION",
  "DEPENDENCY",
  "RUNTIME",
  "LEGACY",
]);
const SEVERITIES = Object.freeze([
  "INFO",
  "LOW",
  "MEDIUM",
  "HIGH",
  "CRITICAL",
]);


function text(value, field) {
  if (typeof value !== "string" || !value.trim()) {
    throw new TypeError(`Campo conflitto non valido: ${field}.`);
  }
  return value.trim();
}


function count(value, field) {
  if (!Number.isInteger(value) || value < 0) {
    throw new TypeError(`Conteggio conflitti non valido: ${field}.`);
  }
  return value;
}


function normalizeSuggestion(value) {
  return Object.freeze({
    action: text(value?.action, "suggestion.action"),
    workspace: text(value?.workspace, "suggestion.workspace"),
    rationale: text(value?.rationale, "suggestion.rationale"),
  });
}


function normalizeConflict(value) {
  const category = text(value?.category, "category").toUpperCase();
  const severity = text(value?.severity, "severity").toUpperCase();
  if (!CATEGORIES.includes(category) || !SEVERITIES.includes(severity)) {
    throw new TypeError("Classificazione conflitto non riconosciuta.");
  }
  return Object.freeze({
    id: text(value?.id, "id"),
    code: text(value?.code, "code"),
    category,
    severity,
    title: text(value?.title, "title"),
    description: text(value?.description, "description"),
    source: text(value?.source, "source"),
    blocking: value?.blocking === true,
    affectedEntities: Object.freeze([...(value?.affected_entities || [])]),
    suggestion: normalizeSuggestion(value?.suggestion),
    documentationReference: text(
      value?.documentation_reference,
      "documentation_reference",
    ),
  });
}


function normalizeGroup(value) {
  const category = text(value?.category, "group.category").toUpperCase();
  if (!CATEGORIES.includes(category)) {
    throw new TypeError("Categoria gruppo non riconosciuta.");
  }
  return Object.freeze({
    category,
    label: text(value?.label, "group.label"),
    totalConflicts: count(value?.total_conflicts, "group.total_conflicts"),
    totalBlocking: count(value?.total_blocking, "group.total_blocking"),
    highestSeverity: text(
      value?.highest_severity,
      "group.highest_severity",
    ).toUpperCase(),
    conflictIds: Object.freeze([...(value?.conflict_ids || [])]),
  });
}


export function normalizePlanningConflictResult(payload) {
  if (!payload || typeof payload !== "object" || !payload.report) {
    throw new TypeError("Risposta di verifica conflitti non valida.");
  }
  const readiness = normalizePlanningReadiness(payload.readiness);
  const conflicts = Object.freeze(
    (payload.report.conflicts || []).map(normalizeConflict),
  );
  const report = Object.freeze({
    totalConflicts: count(
      payload.report.total_conflicts,
      "total_conflicts",
    ),
    totalBlocking: count(
      payload.report.total_blocking,
      "total_blocking",
    ),
    totalWarnings: count(
      payload.report.total_warnings,
      "total_warnings",
    ),
    groups: Object.freeze((payload.report.groups || []).map(normalizeGroup)),
    conflicts,
    topConflicts: Object.freeze(conflicts.slice(0, 5)),
    timestamp: text(payload.report.timestamp, "timestamp"),
    planningVersion: payload.report.planning_version || null,
  });
  if (report.totalConflicts !== conflicts.length) {
    throw new TypeError("Totale conflitti incoerente.");
  }
  return Object.freeze({ readiness, conflicts: report });
}


export function createPlanningConflictLoader(request) {
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
