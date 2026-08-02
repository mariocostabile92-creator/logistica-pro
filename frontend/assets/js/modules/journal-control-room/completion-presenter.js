export const completionStatus = value => ({
  atteso: { label: "Atteso", tone: "expected" },
  in_ritardo: { label: "In ritardo", tone: "late" },
  critico: { label: "Critico", tone: "critical" },
  completato: { label: "Completato", tone: "completed" },
  eccezione: { label: "Eccezione", tone: "exception" },
}[value] || { label: "Da verificare", tone: "unknown" });

export const completionPlanningLabel = completion => completion.planning_id
  ? `Planning ${completion.planning_id} · ${completion.operational_date}`
  : `Nessun planning per la giornata operativa ${completion.operational_date}`;
