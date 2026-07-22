const READINESS_STATUSES = Object.freeze([
  "READY",
  "WARNING",
  "BLOCKED",
  "STALE",
  "PARTIAL",
  "MISSING",
  "INVALID",
  "INCOMPATIBLE",
  "LEGACY",
]);


function normalizedText(value) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}


function normalizeIssue(issue) {
  return Object.freeze({
    code: normalizedText(issue?.code),
    message: normalizedText(issue?.message),
    remediationHint: normalizedText(issue?.remediation_hint),
    source: normalizedText(issue?.source),
  });
}


function operationalUnitLabel(value) {
  if (!value || typeof value !== "object") return null;
  return normalizedText(value.name) || normalizedText(value.external_identifier);
}


export function normalizePlanningReadiness(payload) {
  if (!payload || typeof payload !== "object") {
    throw new TypeError("Risposta readiness non valida.");
  }
  const status = normalizedText(payload.status)?.toUpperCase();
  if (!READINESS_STATUSES.includes(status)) {
    throw new TypeError("Stato readiness non riconosciuto.");
  }
  const rawScore = typeof payload.score === "object"
    ? payload.score?.value
    : payload.score;
  const score = Number(rawScore);
  if (!Number.isInteger(score) || score < 0 || score > 100) {
    throw new TypeError("Score readiness non valido.");
  }
  return Object.freeze({
    status,
    score,
    isReady: payload.is_ready === true,
    blockers: Object.freeze((payload.blockers || []).map(normalizeIssue)),
    warnings: Object.freeze((payload.warnings || []).map(normalizeIssue)),
    missingInputs: Object.freeze(
      (payload.missing_inputs || []).map(normalizeIssue),
    ),
    rationale: normalizedText(payload.rationale),
    evaluatedAt: normalizedText(payload.evaluated_at),
    operationalUnit: operationalUnitLabel(payload.operational_unit),
    planningDate: normalizedText(payload.planning_date),
    envelopeVersion: normalizedText(payload.envelope_version),
    legacyFlowActive: payload.legacy_flow_active === true,
  });
}


export function readinessEventType(status) {
  const normalized = normalizedText(status)?.toUpperCase();
  if (!READINESS_STATUSES.includes(normalized)) {
    throw new TypeError("Stato readiness non riconosciuto.");
  }
  return `${normalized.toLowerCase()}-received`;
}


export function createPlanningReadinessLoader(request) {
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
