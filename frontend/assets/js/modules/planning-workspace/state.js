import {
  PLANNING_WORKSPACE_PRESENTATION,
  PLANNING_WORKSPACE_STATES,
  planningWorkspaceModel,
} from "./models.js";


export function createPlanningWorkspaceState({ planningDate = null } = {}) {
  return planningWorkspaceModel({
    state: PLANNING_WORKSPACE_STATES.LOADING,
    planningDate,
  });
}


export function applyPlanningWorkspaceEvent(current, event) {
  const transitions = {
    "load-started": PLANNING_WORKSPACE_STATES.LOADING,
    "empty-detected": PLANNING_WORKSPACE_STATES.EMPTY,
    "ready-received": PLANNING_WORKSPACE_STATES.READY,
    "warning-received": PLANNING_WORKSPACE_STATES.WARNING,
    "load-failed": PLANNING_WORKSPACE_STATES.ERROR,
    "legacy-active": PLANNING_WORKSPACE_STATES.LEGACY,
  };
  const nextState = transitions[event?.type];
  if (!nextState) return current;
  return planningWorkspaceModel({
    ...current,
    state: nextState,
    message: event.message || null,
    snapshot: event.snapshot || null,
    operationalUnit: event.operationalUnit || current.operationalUnit,
  });
}


function placeholder(value, detail) {
  return Object.freeze({ value, detail });
}


export function derivePlanningWorkspaceView(state) {
  const presentation = PLANNING_WORKSPACE_PRESENTATION[state.state];
  const snapshot = state.snapshot || {};
  const noRuntime = "Planning Runtime non ancora collegato.";
  return Object.freeze({
    state: state.state,
    loading: state.state === PLANNING_WORKSPACE_STATES.LOADING,
    tone: presentation.tone,
    badge: presentation.label,
    statusTitle: presentation.title,
    statusDescription: state.message || presentation.description,
    planningDate: state.planningDate,
    operationalUnit: state.operationalUnit,
    readiness: snapshot.readiness || placeholder("Non disponibile", noRuntime),
    conflicts: snapshot.conflicts || placeholder("Non disponibili", noRuntime),
    timeline: placeholder(
      "Timeline non disponibile",
      "La timeline sarà collegata nelle prossime fasi.",
    ),
    draft: placeholder(
      "Draft non disponibile",
      "Draft disponibile nelle prossime fasi.",
    ),
    publication: placeholder(
      "Non disponibile",
      "Publication non disponibile.",
    ),
    canConfirm: Boolean(snapshot.canConfirm),
  });
}
