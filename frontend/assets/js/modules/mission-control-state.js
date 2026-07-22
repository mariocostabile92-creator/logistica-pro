const STATUS_PRESENTATION = {
  stable: {
    tone: "ready",
    label: "Giornata pronta",
  },
  attention: {
    tone: "attention",
    label: "Attenzione",
  },
  critical: {
    tone: "critical",
    label: "Intervento richiesto",
  },
};

const READINESS_LABELS = {
  green: "Pronta",
  yellow: "Attenzione",
  red: "Critica",
};

const CATEGORY_LABELS = {
  human_resources: "Workforce",
  assets: "Fleet",
  planning_decisions: "Operations",
  readiness: "Operations",
  capacity: "Operations",
  critical_attention: "Operations",
};

const WORKSPACE_ACTION_LABELS = {
  workforce: "Apri Workforce",
  fleet: "Apri Fleet",
  operations: "Apri Operations",
  settings: "Apri Configurazione",
};

const SEVERITY_PRESENTATION = {
  blocker: { label: "Bloccante", tone: "critical" },
  critical: { label: "Critica", tone: "critical" },
  high: { label: "Alta priorità", tone: "attention" },
  medium: { label: "Da verificare", tone: "attention" },
  low: { label: "Informativa", tone: "neutral" },
  information: { label: "Informativa", tone: "neutral" },
};

const SNAPSHOT_PRESENTATION = {
  blocker: { label: "Intervento richiesto", tone: "critical" },
  critical: { label: "Intervento richiesto", tone: "critical" },
  high: { label: "Attenzione", tone: "attention" },
  medium: { label: "Attenzione", tone: "attention" },
  low: { label: "Da verificare", tone: "attention" },
  information: { label: "Da verificare", tone: "attention" },
};


export function createMissionControlState(overrides = {}) {
  return {
    briefingPhase: "loading",
    briefing: null,
    briefingError: "",
    workspace: null,
    ...overrides,
  };
}


export function applyMissionControlEvent(current, event) {
  const next = { ...current };
  if (event.type === "briefing-loading") {
    next.briefingPhase = next.briefing ? "refreshing" : "loading";
    next.briefingError = "";
  }
  if (event.type === "briefing-loaded") {
    next.briefingPhase = event.briefing?.status === "available"
      ? "available"
      : "unavailable";
    next.briefing = event.briefing || null;
    next.briefingError = "";
  }
  if (event.type === "briefing-failed") {
    next.briefingPhase = next.briefing ? "available" : "error";
    next.briefingError = event.message || "Stato temporaneamente non disponibile.";
  }
  if (event.type === "workspace-loaded") {
    next.workspace = event.workspace || null;
  }
  if (event.type === "workspace-reset") {
    return createMissionControlState({ workspace: event.workspace || null });
  }
  return next;
}


function sectionFor(briefing, category) {
  return (briefing?.sections || []).find((section) => section.category === category) || null;
}


function factValue(section, factType) {
  const fact = (section?.facts || []).find((item) => item.fact_type === factType);
  return fact?.value && typeof fact.value === "object" ? fact.value : null;
}


function numeric(value) {
  return Number.isFinite(Number(value)) ? Number(value) : null;
}


function snapshotState(section) {
  if (!section) {
    return { label: "Snapshot temporaneo", tone: "temporary" };
  }
  return SNAPSHOT_PRESENTATION[section.severity]
    || { label: "Da verificare", tone: "attention" };
}


function workforceSnapshot(briefing) {
  const section = sectionFor(briefing, "human_resources");
  const coverage = factValue(section, "workforce_coverage") || {};
  const available = numeric(coverage.available);
  const required = numeric(coverage.required);
  const absences = numeric(coverage.absences);
  return {
    state: snapshotState(section),
    available,
    required,
    absences,
    availabilityLabel: available === null
      ? "Non esposta dallo snapshot"
      : required === null
        ? String(available)
        : `${available} su ${required}`,
    absencesLabel: absences === null ? "Non esposte" : String(absences),
  };
}


function fleetSnapshot(briefing) {
  const section = sectionFor(briefing, "assets");
  const summary = factValue(section, "fleet_registry_summary") || {};
  const available = numeric(summary.available_assets);
  const maintenance = numeric(summary.maintenance_assets);
  const documents = numeric(summary.documents_attention);
  return {
    state: snapshotState(section),
    available,
    maintenance,
    documents,
    availableLabel: available === null ? "Non esposti dallo snapshot" : String(available),
    maintenanceLabel: maintenance === null ? "Non disponibile" : String(maintenance),
    documentsLabel: documents === null ? "Non disponibili" : `${documents} in attenzione`,
  };
}


function planningSnapshot(briefing) {
  const readiness = briefing?.readiness_snapshot || {};
  const blocking = readiness.available ? numeric(readiness.blocking_issues) : null;
  const warnings = readiness.available ? numeric(readiness.warnings) : null;
  const planningAvailable = Boolean(briefing?.planning_id);
  return {
    state: planningAvailable
      ? { label: "Planning disponibile", tone: "ready" }
      : { label: "Snapshot temporaneo", tone: "temporary" },
    readiness: readiness.available
      ? READINESS_LABELS[readiness.level] || readiness.level || "Disponibile"
      : "Non disponibile",
    blocking,
    warnings,
    conflictsLabel: blocking === null
      ? "Non disponibili"
      : `${blocking} bloccanti · ${warnings || 0} avvisi`,
    generatedAt: briefing?.generated_at || null,
    version: briefing?.planning_version || null,
  };
}


function backendActions(briefing) {
  return [...(briefing?.sections || [])]
    .sort((left, right) => Number(left.priority || 0) - Number(right.priority || 0))
    .slice(0, 5)
    .map((section) => {
      const link = section.action_links?.[0] || null;
      const severity = SEVERITY_PRESENTATION[section.severity]
        || { label: "Da verificare", tone: "neutral" };
      return {
        id: section.section_id,
        priority: section.priority,
        priorityLabel: severity.label,
        tone: severity.tone,
        title: section.title,
        summary: section.summary,
        sourceLabel: CATEGORY_LABELS[section.category] || "Operations",
        workspace: link?.workspace || null,
        targetId: link?.target_id || null,
        entityType: link?.entity_type || null,
        entityId: link?.entity_id || null,
        actionLabel: link
          ? WORKSPACE_ACTION_LABELS[link.workspace] || link.label
          : null,
        temporary: false,
      };
    });
}


function temporaryActions(workspace) {
  if (!workspace) return [];
  const actions = [];
  if (!workspace.workforce_member_count) {
    actions.push({
      id: "temporary-workforce",
      priorityLabel: "Dati necessari",
      tone: "neutral",
      title: "Prepara Workforce",
      summary: "Lo snapshot Workforce non è ancora disponibile per la giornata.",
      sourceLabel: "Stato temporaneo",
      workspace: "workforce",
      actionLabel: "Apri Workforce",
      temporary: true,
    });
  }
  if (!workspace.asset_count) {
    actions.push({
      id: "temporary-fleet",
      priorityLabel: "Dati necessari",
      tone: "neutral",
      title: "Aggiorna Fleet",
      summary: "Lo snapshot Fleet non è ancora disponibile per la giornata.",
      sourceLabel: "Stato temporaneo",
      workspace: "fleet",
      actionLabel: "Apri Fleet",
      temporary: true,
    });
  }
  if (!workspace.planning_count) {
    actions.push({
      id: "temporary-planning",
      priorityLabel: "Dati necessari",
      tone: "neutral",
      title: "Genera o verifica il Planning",
      summary: "Non esiste ancora un Planning utilizzabile nello snapshot corrente.",
      sourceLabel: "Stato temporaneo",
      workspace: "operations",
      actionLabel: "Apri Operations",
      temporary: true,
    });
  }
  return actions.slice(0, 5);
}


function statusView(state) {
  const briefing = state.briefing;
  if (state.briefingPhase === "loading") {
    return {
      tone: "loading",
      label: "Stato in aggiornamento",
      description: "Verifica degli snapshot operativi disponibili.",
      temporary: true,
    };
  }
  if (state.briefingPhase === "error") {
    return {
      tone: "unknown",
      label: "Stato temporaneamente non disponibile",
      description: state.briefingError,
      temporary: true,
    };
  }
  if (!briefing || briefing.status !== "available") {
    return {
      tone: "unknown",
      label: "Stato non determinabile",
      description: briefing?.executive_summary || "Gli snapshot necessari non sono ancora disponibili.",
      temporary: true,
    };
  }
  const presentation = STATUS_PRESENTATION[briefing.attention_level];
  if (!presentation) {
    return {
      tone: "unknown",
      label: "Stato temporaneo",
      description: briefing.attention_reason || "Stato non ancora classificato dal backend.",
      temporary: true,
    };
  }
  return {
    ...presentation,
    description: briefing.attention_reason || briefing.executive_summary,
    temporary: false,
  };
}


function operationalUnits(briefing) {
  const ids = [...new Set((briefing?.operational_unit_ids || []).filter(Boolean))];
  return {
    options: [
      { value: "all", label: ids.length > 1 ? `Tutte (${ids.length})` : "Tutte" },
      ...ids.map((id) => ({ value: id, label: id })),
    ],
    selected: ids.length === 1 ? ids[0] : "all",
    disabled: true,
    temporary: true,
  };
}


function timelineItems(state) {
  const workspace = state.workspace || {};
  const briefing = state.briefing || {};
  const candidates = [
    workspace.latest_planning_import?.imported_at && {
      id: `planning-import-${workspace.latest_planning_import.import_id}`,
      timestamp: workspace.latest_planning_import.imported_at,
      label: "Import Planning completato",
      source: "Operations",
    },
    workspace.latest_fleet_import?.imported_at && {
      id: `fleet-import-${workspace.latest_fleet_import.import_id}`,
      timestamp: workspace.latest_fleet_import.imported_at,
      label: "Sincronizzazione Fleet disponibile",
      source: "Fleet",
    },
    briefing.generated_at && {
      id: `briefing-${briefing.briefing_id || briefing.generated_at}`,
      timestamp: briefing.generated_at,
      label: "Briefing aggiornato",
      source: "Mission Control",
    },
    workspace.last_operational_update && {
      id: `workspace-${workspace.last_operational_update}`,
      timestamp: workspace.last_operational_update,
      label: "Workspace operativo aggiornato",
      source: "Operations Engine",
    },
  ].filter(Boolean);
  const unique = new Map();
  candidates.forEach((item) => unique.set(`${item.timestamp}-${item.label}`, item));
  return [...unique.values()]
    .sort((left, right) => new Date(right.timestamp) - new Date(left.timestamp))
    .slice(0, 6);
}


export function deriveMissionControlView(state) {
  const briefing = state.briefing;
  const workforce = workforceSnapshot(briefing);
  const fleet = fleetSnapshot(briefing);
  const planning = planningSnapshot(briefing);
  const available = state.briefingPhase === "available" && briefing?.status === "available";
  const actions = available ? backendActions(briefing) : temporaryActions(state.workspace);
  return {
    loading: state.briefingPhase === "loading" && !briefing,
    refreshing: state.briefingPhase === "refreshing",
    error: state.briefingPhase === "error",
    status: statusView(state),
    actions,
    actionState: state.briefingPhase === "loading" && !state.workspace
      ? "loading"
      : actions.length
        ? "available"
        : "empty",
    actionEmptyTitle: available
      ? "Nessuna azione richiesta"
      : state.briefingPhase === "error"
        ? "Azioni temporaneamente non disponibili"
        : "Preparazione non ancora disponibile",
    actionEmptyDescription: available
      ? "Il Briefing non segnala interventi nello snapshot corrente."
      : state.briefingError || "Completa i dati operativi per ottenere azioni verificate.",
    workforce,
    fleet,
    planning,
    operationalUnits: operationalUnits(briefing),
    timeline: timelineItems(state),
    freshnessAt: briefing?.generated_at || state.workspace?.last_operational_update || null,
  };
}
