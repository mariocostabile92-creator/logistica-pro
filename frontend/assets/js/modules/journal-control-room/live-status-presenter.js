const presentations = {
  not_started: { label: "Non iniziata", tone: "not_started", marker: "○" },
  generated: { label: "Generata", tone: "generated", marker: "●" },
  opened: { label: "Aperta", tone: "opened", marker: "●" },
  in_progress: { label: "In compilazione", tone: "in_progress", marker: "●" },
  completed: { label: "Completata", tone: "completed", marker: "●" },
  con_anomalia: { label: "Completata con anomalia", tone: "anomaly", marker: "!" },
  completed_with_anomaly: { label: "Completata con anomalia", tone: "anomaly", marker: "!" },
  late: { label: "In ritardo", tone: "late", marker: "!" },
};

export function statusPresentation(value) {
  return presentations[value] || { label: "Non classificata", tone: "unknown", marker: "?" };
}

export function liveCardPriority(item) {
  if (item.is_late) return { tone: "late", label: "In ritardo" };
  if (item.anomaly_present) return { tone: "anomaly", label: "Anomalia presente" };
  return { tone: statusPresentation(item.status).tone, label: "" };
}

export const liveKpiDefinitions = [
  ["expected_drivers", "Driver attesi", "all", "expected"],
  ["not_started", "Non iniziati", "not_started", "not_started"],
  ["in_progress_live", "In compilazione", "in_progress", "in_progress"],
  ["completed_live", "Completati", "completed", "completed"],
  ["with_anomalies", "Con anomalie", "anomaly", "anomaly"],
  ["late", "In ritardo", "late", "late"],
];
