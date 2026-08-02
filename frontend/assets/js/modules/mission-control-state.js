const PRIORITY_TONE = { critical: 0, attention: 1, neutral: 2 };


export function createMissionControlState(overrides = {}) {
  return {
    briefing: null,
    workspace: null,
    summary: null,
    phase: "loading",
    error: "",
    ...overrides,
  };
}


export function applyMissionControlEvent(current, event) {
  if (event.type === "summary-loading") return { ...current, phase: "loading", error: "" };
  if (event.type === "summary-loaded") {
    return { ...current, summary: event.summary, phase: "ready", error: "" };
  }
  if (event.type === "summary-failed") {
    return { ...current, phase: current.summary ? "ready" : "error", error: event.message };
  }
  if (event.type === "briefing-loaded") return { ...current, briefing: event.briefing || null };
  if (event.type === "workspace-loaded") return { ...current, workspace: event.workspace || null };
  if (event.type === "workspace-reset") return createMissionControlState({ workspace: event.workspace });
  return current;
}


function factValue(briefing, category, factType) {
  const section = (briefing?.sections || []).find((item) => item.category === category);
  return section?.facts?.find((fact) => fact.fact_type === factType)?.value || null;
}


function workforceView(briefing) {
  const coverage = factValue(briefing, "human_resources", "workforce_coverage");
  if (!coverage) return { available: false, status: "Workspace in preparazione" };
  return {
    available: true,
    drivers: Number(coverage.available || 0),
    required: Number(coverage.required || 0),
    absences: Number(coverage.absences || 0),
    coverage: Number(coverage.margin || 0),
    status: coverage.status === "deficit" ? "Copertura da verificare" : "Copertura regolare",
  };
}


function planningView(summary, briefing) {
  if (summary?.planning) return summary.planning;
  if (!briefing?.planning_id) return null;
  const readiness = briefing.readiness_snapshot || {};
  return {
    driversAssigned: null,
    vehiclesAssigned: null,
    conflicts: readiness.available ? Number(readiness.blocking_issues || 0) : null,
    publication: "Non disponibile",
  };
}


function priorities(summary, briefing) {
  if (!summary) return [];
  const candidates = [
    [summary.fleet.missingJournal, "GDB mancanti", "Verifica le procedure attese per oggi.", "critical", "journal"],
    [summary.fleet.unavailable, "Mezzi indisponibili", "Controlla i mezzi che non possono essere impiegati.", "critical", "library"],
    [summary.maintenance.urgent, "Manutenzioni urgenti", "Sono presenti interventi ad alta priorità.", "critical", "maintenance"],
    [summary.fleet.criticalDocuments, "Documenti critici", "Verifica documenti mancanti o scaduti.", "attention", "documents"],
    [summary.planning?.conflicts || 0, "Conflitti Planning", "Risolvi i conflitti prima della pubblicazione.", "critical", "planning"],
    [summary.fleet.openDamage, "Danni aperti", "Consulta le pratiche ancora in lavorazione.", "attention", "damage"],
    [summary.fleet.deadlines, "Scadenze da presidiare", "Sono presenti scadenze scadute o entro 30 giorni.", "attention", "vision"],
  ].filter(([count]) => count > 0).map(([count, title, description, tone, target]) => ({
    id: target, count, title, description, tone, target,
  }));
  if (!candidates.length && briefing?.status === "available") {
    return (briefing.sections || []).slice(0, 3).map((section) => ({
      id: section.section_id,
      count: null,
      title: section.title,
      description: section.summary,
      tone: ["blocker", "critical", "high"].includes(section.severity) ? "critical" : "attention",
      target: section.category === "human_resources" ? "workforce" : "planning",
    }));
  }
  return candidates.sort((left, right) => PRIORITY_TONE[left.tone] - PRIORITY_TONE[right.tone]).slice(0, 7);
}


function generalStatus(summary) {
  if (!summary) return { tone: "loading", label: "Giornata operativa", description: "Riepilogo in aggiornamento." };
  const critical = summary.fleet.missingJournal + summary.fleet.unavailable
    + summary.maintenance.urgent + Number(summary.planning?.conflicts || 0);
  if (!summary.planning) return { tone: "attention", label: "Planning incompleto", description: "Completa il Planning della giornata operativa." };
  if (critical) return { tone: "critical", label: `${critical} criticità richiedono attenzione`, description: "Apri le attività prioritarie e intervieni sui moduli indicati." };
  return { tone: "ready", label: "Operatività regolare", description: "Non risultano criticità bloccanti nei dati aggiornati." };
}


export function deriveMissionControlView(state) {
  const summary = state.summary;
  const planning = planningView(summary, state.briefing);
  return {
    loading: state.phase === "loading" && !summary,
    error: state.error,
    status: generalStatus(summary ? { ...summary, planning } : null),
    priorities: priorities(summary ? { ...summary, planning } : null, state.briefing),
    fleet: summary?.fleet || null,
    workforce: workforceView(state.briefing),
    planning,
    recent: (summary?.recent || []).slice(0, 8),
    updatedAt: summary?.updatedAt || state.briefing?.generated_at || null,
    partial: Boolean(summary?.partial),
  };
}
