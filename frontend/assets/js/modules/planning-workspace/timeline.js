const CATEGORIES = Object.freeze([
  "IMPORT",
  "VALIDATION",
  "WORKFORCE",
  "FLEET",
  "READINESS",
  "CONFLICT",
  "RUNTIME",
  "SYSTEM",
  "LEGACY",
]);
const SEVERITIES = Object.freeze([
  "INFO",
  "SUCCESS",
  "WARNING",
  "ERROR",
  "CRITICAL",
]);


function text(value, field) {
  if (typeof value !== "string" || !value.trim()) {
    throw new TypeError(`Campo timeline non valido: ${field}.`);
  }
  return value.trim();
}


function count(value, field) {
  if (!Number.isInteger(value) || value < 0 || value > 100) {
    throw new TypeError(`Conteggio timeline non valido: ${field}.`);
  }
  return value;
}


function normalizeEvent(value) {
  const category = text(value?.category, "event.category").toUpperCase();
  const severity = text(value?.severity, "event.severity").toUpperCase();
  if (!CATEGORIES.includes(category) || !SEVERITIES.includes(severity)) {
    throw new TypeError("Classificazione evento timeline non riconosciuta.");
  }
  const operationalUnit = value?.operational_unit || {};
  return Object.freeze({
    id: text(value?.id, "event.id"),
    timestamp: text(value?.timestamp, "event.timestamp"),
    category,
    severity,
    title: text(value?.title, "event.title"),
    description: text(value?.description, "event.description"),
    status: text(value?.status, "event.status"),
    source: text(value?.source, "event.source"),
    operationalUnit: Object.freeze({
      externalIdentifier: text(
        operationalUnit.external_identifier,
        "event.operational_unit.external_identifier",
      ),
      name: operationalUnit.name || null,
    }),
    planningDate: text(value?.planning_date, "event.planning_date"),
    reference: typeof value?.reference === "string" ? value.reference : null,
    relatedConflicts: Object.freeze(
      (value?.related_conflicts || []).map((item) => text(
        item,
        "event.related_conflicts",
      )),
    ),
    relatedReadiness: value?.related_readiness || null,
    metadata: Object.freeze((value?.metadata || []).map((item) => Object.freeze({
      key: text(item?.key, "event.metadata.key"),
      value: text(item?.value, "event.metadata.value"),
    }))),
  });
}


function normalizeGroup(value) {
  return Object.freeze({
    key: text(value?.key, "group.key"),
    label: text(value?.label, "group.label"),
    eventCount: count(value?.event_count, "group.event_count"),
    eventIds: Object.freeze([...(value?.event_ids || [])]),
  });
}


export function normalizePlanningTimelineResult(payload) {
  if (!payload || typeof payload !== "object" || !payload.report) {
    throw new TypeError("Risposta della cronologia del piano non valida.");
  }
  const events = Object.freeze((payload.report.events || []).map(normalizeEvent));
  const eventCount = count(payload.report.event_count, "event_count");
  if (eventCount !== events.length) {
    throw new TypeError("Totale eventi timeline incoerente.");
  }
  return Object.freeze({
    state: eventCount ? "ready" : "empty",
    eventCount,
    lastUpdated: payload.report.last_updated || null,
    currentStatus: text(payload.report.current_status, "current_status"),
    groups: Object.freeze((payload.report.groups || []).map(normalizeGroup)),
    events,
  });
}


export function createPlanningTimelineLoader(request) {
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
