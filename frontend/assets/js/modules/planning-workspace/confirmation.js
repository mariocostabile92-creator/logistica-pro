const CONFIRMATION_STATES = Object.freeze([
  "NOT_READY",
  "READY_TO_CONFIRM",
  "CONFIRMED",
  "REJECTED",
  "ERROR",
]);


function text(value, field) {
  if (typeof value !== "string" || !value.trim()) {
    throw new TypeError(`Valore della conferma non valido: ${field}.`);
  }
  return value.trim();
}


function count(value, field, minimum = 0) {
  if (!Number.isInteger(value) || value < minimum) {
    throw new TypeError(`Conteggio della conferma non valido: ${field}.`);
  }
  return value;
}


function normalizeRule(value) {
  return Object.freeze({
    code: text(value?.code, "rule.code"),
    passed: value?.passed === true,
    reason: text(value?.reason, "rule.reason"),
    remediationHint: text(
      value?.remediation_hint,
      "rule.remediation_hint",
    ),
  });
}


function normalizeResult(value) {
  const state = text(value?.state, "result.state").toUpperCase();
  if (!CONFIRMATION_STATES.includes(state)) {
    throw new TypeError("Stato della conferma non riconosciuto.");
  }
  const rules = Object.freeze((value?.rules || []).map(normalizeRule));
  if (!rules.length) throw new TypeError("Regole di conferma mancanti.");
  const canConfirm = value?.can_confirm === true;
  if (canConfirm !== (state === "READY_TO_CONFIRM")) {
    throw new TypeError("Disponibilità della conferma incoerente.");
  }
  return Object.freeze({
    state,
    canConfirm,
    rules,
    rationale: text(value?.rationale, "result.rationale"),
    evaluatedAt: text(value?.evaluated_at, "result.evaluated_at"),
  });
}


function normalizeConfirmation(value) {
  if (!value) return null;
  const state = text(value?.state, "confirmation.state").toUpperCase();
  if (state !== "CONFIRMED") {
    throw new TypeError("Piano confermato non valido.");
  }
  const readinessScore = count(
    value?.readiness_score,
    "confirmation.readiness_score",
  );
  if (readinessScore > 100) {
    throw new TypeError("Punteggio della conferma non valido.");
  }
  const fingerprint = text(
    value?.fingerprint,
    "confirmation.fingerprint",
  );
  if (!/^[a-f0-9]{64}$/i.test(fingerprint)) {
    throw new TypeError("Fingerprint della conferma non valido.");
  }
  return Object.freeze({
    id: text(value?.confirmation_id, "confirmation.confirmation_id"),
    state,
    version: count(value?.version, "confirmation.version", 1),
    draftId: text(value?.draft_id, "confirmation.draft_id"),
    draftVersion: count(
      value?.draft_version,
      "confirmation.draft_version",
      1,
    ),
    draftName: text(value?.draft_name, "confirmation.draft_name"),
    readinessStatus: text(
      value?.readiness_status,
      "confirmation.readiness_status",
    ),
    readinessScore,
    fingerprint,
    actor: text(value?.actor, "confirmation.actor"),
    confirmedAt: text(value?.confirmed_at, "confirmation.confirmed_at"),
  });
}


function normalizeHistory(value) {
  const confirmations = Object.freeze(
    (value?.confirmations || []).map(normalizeConfirmation),
  );
  const total = count(value?.total, "history.total");
  if (total < confirmations.length) {
    throw new TypeError("Cronologia delle conferme incoerente.");
  }
  return Object.freeze({ total, confirmations });
}


export function normalizePlanningConfirmationReport(payload) {
  if (!payload || typeof payload !== "object") {
    throw new TypeError("Risposta di conferma del piano non valida.");
  }
  const state = text(payload.state, "state").toUpperCase();
  const result = normalizeResult(payload.result);
  if (state !== result.state) {
    throw new TypeError("Stato del report di conferma incoerente.");
  }
  const current = normalizeConfirmation(payload.current);
  if (state === "CONFIRMED" && !current) {
    throw new TypeError("Piano confermato corrente mancante.");
  }
  return Object.freeze({
    viewState: state === "ERROR" ? "error" : "ready",
    state,
    result,
    current,
    history: normalizeHistory(payload.history),
    generatedAt: text(payload.generated_at, "generated_at"),
  });
}


export function createPlanningConfirmationLoader(request) {
  let pending = null;
  let controller = null;
  return Object.freeze({
    load(parameters = {}, { force = false } = {}) {
      if (pending && !force) return pending;
      if (force) controller?.abort();
      const activeController = new AbortController();
      let activeRequest;
      activeRequest = request({
        ...parameters,
        signal: activeController.signal,
      })
        .finally(() => {
          if (pending === activeRequest) {
            pending = null;
            controller = null;
          }
        });
      controller = activeController;
      pending = activeRequest;
      return activeRequest;
    },
    abort() {
      controller?.abort();
    },
  });
}
