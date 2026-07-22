const PUBLICATION_STATES = Object.freeze([
  "NOT_PUBLISHED",
  "READY_TO_PUBLISH",
  "PUBLISHED",
  "FAILED",
  "ERROR",
]);


function text(value, field) {
  if (typeof value !== "string" || !value.trim()) {
    throw new TypeError(`Valore Publication non valido: ${field}.`);
  }
  return value.trim();
}


function count(value, field, minimum = 0) {
  if (!Number.isInteger(value) || value < minimum) {
    throw new TypeError(`Conteggio Publication non valido: ${field}.`);
  }
  return value;
}


function fingerprint(value, field) {
  const normalized = text(value, field);
  if (!/^[a-f0-9]{64}$/i.test(normalized)) {
    throw new TypeError(`Fingerprint Publication non valido: ${field}.`);
  }
  return normalized;
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
  if (!PUBLICATION_STATES.includes(state)) {
    throw new TypeError("Stato Publication non riconosciuto.");
  }
  const rules = Object.freeze((value?.rules || []).map(normalizeRule));
  if (!rules.length) throw new TypeError("Regole Publication mancanti.");
  const canPublish = value?.can_publish === true;
  if (canPublish !== (state === "READY_TO_PUBLISH")) {
    throw new TypeError("Disponibilita Publication incoerente.");
  }
  return Object.freeze({
    state,
    canPublish,
    rules,
    rationale: text(value?.rationale, "result.rationale"),
    evaluatedAt: text(value?.evaluated_at, "result.evaluated_at"),
  });
}


function normalizePublication(value) {
  if (!value) return null;
  const state = text(value?.state, "publication.state").toUpperCase();
  if (state !== "PUBLISHED") {
    throw new TypeError("Published Plan non valido.");
  }
  return Object.freeze({
    id: text(value?.publication_id, "publication.publication_id"),
    state,
    version: count(value?.version, "publication.version", 1),
    confirmationId: text(
      value?.confirmation_id,
      "publication.confirmation_id",
    ),
    confirmationVersion: count(
      value?.confirmation_version,
      "publication.confirmation_version",
      1,
    ),
    confirmationFingerprint: fingerprint(
      value?.confirmation_fingerprint,
      "publication.confirmation_fingerprint",
    ),
    fingerprint: fingerprint(
      value?.fingerprint,
      "publication.fingerprint",
    ),
    actor: text(value?.actor, "publication.actor"),
    publishedAt: text(value?.published_at, "publication.published_at"),
  });
}


function normalizeHistory(value) {
  const publications = Object.freeze(
    (value?.publications || []).map(normalizePublication),
  );
  const total = count(value?.total, "history.total");
  if (total < publications.length) {
    throw new TypeError("Cronologia Publication incoerente.");
  }
  return Object.freeze({ total, publications });
}


export function normalizePlanningPublicationReport(payload) {
  if (!payload || typeof payload !== "object") {
    throw new TypeError("Risposta Planning Publication non valida.");
  }
  const state = text(payload.state, "state").toUpperCase();
  const result = normalizeResult(payload.result);
  if (state !== result.state) {
    throw new TypeError("Stato report Publication incoerente.");
  }
  const current = normalizePublication(payload.current);
  if (state === "PUBLISHED" && !current) {
    throw new TypeError("Published Plan corrente mancante.");
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


export function createPlanningPublicationLoader(request) {
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
