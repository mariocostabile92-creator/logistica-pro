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
  if (event?.type?.startsWith("publication-")) {
    const currentPublication = current.snapshot?.publication || {};
    const publicationStates = {
      "publication-load-started": Object.freeze({
        viewState: "loading",
        busy: false,
      }),
      "publication-loaded": Object.freeze({
        ...event.publication,
        busy: false,
      }),
      "publication-load-failed": Object.freeze({
        ...currentPublication,
        viewState: "error",
        busy: false,
        message: event.message || "Planning Publication non disponibile.",
      }),
      "publication-mutation-started": Object.freeze({
        ...currentPublication,
        busy: true,
        feedback: null,
        message: null,
      }),
      "publication-mutation-completed": Object.freeze({
        ...event.publication,
        busy: false,
        feedback: event.message || "Publication aggiornata.",
      }),
      "publication-mutation-failed": Object.freeze({
        ...currentPublication,
        viewState: "error",
        busy: false,
        message: event.message || "Operazione Publication non riuscita.",
      }),
    };
    const nextPublication = publicationStates[event.type];
    if (!nextPublication) return current;
    return planningWorkspaceModel({
      ...current,
      snapshot: {
        ...(current.snapshot || {}),
        publication: nextPublication,
      },
    });
  }
  if (event?.type?.startsWith("confirmation-")) {
    const currentConfirmation = current.snapshot?.confirmation || {};
    const confirmationStates = {
      "confirmation-load-started": Object.freeze({
        viewState: "loading",
        busy: false,
      }),
      "confirmation-loaded": Object.freeze({
        ...event.confirmation,
        busy: false,
      }),
      "confirmation-load-failed": Object.freeze({
        ...currentConfirmation,
        viewState: "error",
        busy: false,
        message: event.message || "Planning Confirmation non disponibile.",
      }),
      "confirmation-mutation-started": Object.freeze({
        ...currentConfirmation,
        busy: true,
        feedback: null,
        message: null,
      }),
      "confirmation-mutation-completed": Object.freeze({
        ...event.confirmation,
        busy: false,
        feedback: event.message || "Confirmation aggiornata.",
      }),
      "confirmation-mutation-failed": Object.freeze({
        ...currentConfirmation,
        viewState: "error",
        busy: false,
        message: event.message || "Operazione Confirmation non riuscita.",
      }),
    };
    const nextConfirmation = confirmationStates[event.type];
    if (!nextConfirmation) return current;
    return planningWorkspaceModel({
      ...current,
      snapshot: {
        ...(current.snapshot || {}),
        confirmation: nextConfirmation,
      },
    });
  }
  if (event?.type?.startsWith("draft-")) {
    const currentDraft = current.snapshot?.draft || {};
    const draftStates = {
      "draft-load-started": Object.freeze({ viewState: "loading", busy: false }),
      "draft-loaded": Object.freeze({ ...event.draft, busy: false }),
      "draft-load-failed": Object.freeze({
        ...currentDraft,
        viewState: "error",
        busy: false,
        message: event.message || "Planning Draft non disponibile.",
      }),
      "draft-mutation-started": Object.freeze({
        ...currentDraft,
        busy: true,
        feedback: null,
        message: null,
      }),
      "draft-mutation-completed": Object.freeze({
        ...event.draft,
        busy: false,
        feedback: event.message || "Draft aggiornato.",
      }),
      "draft-mutation-failed": Object.freeze({
        ...currentDraft,
        viewState: "error",
        busy: false,
        message: event.message || "Operazione Draft non riuscita.",
      }),
    };
    const nextDraft = draftStates[event.type];
    if (!nextDraft) return current;
    return planningWorkspaceModel({
      ...current,
      snapshot: {
        ...(current.snapshot || {}),
        draft: nextDraft,
      },
    });
  }
  if (event?.type?.startsWith("timeline-")) {
    const timelineStates = {
      "timeline-load-started": Object.freeze({ state: "loading" }),
      "timeline-loaded": event.timeline,
      "timeline-load-failed": Object.freeze({
        state: "error",
        message: event.message || "Planning Timeline non disponibile.",
      }),
    };
    const nextTimeline = timelineStates[event.type];
    if (!nextTimeline) return current;
    return planningWorkspaceModel({
      ...current,
      snapshot: {
        ...(current.snapshot || {}),
        timeline: nextTimeline,
      },
    });
  }
  const transitions = {
    "load-started": PLANNING_WORKSPACE_STATES.LOADING,
    "empty-detected": PLANNING_WORKSPACE_STATES.EMPTY,
    "ready-received": PLANNING_WORKSPACE_STATES.READY,
    "warning-received": PLANNING_WORKSPACE_STATES.WARNING,
    "blocked-received": PLANNING_WORKSPACE_STATES.BLOCKED,
    "stale-received": PLANNING_WORKSPACE_STATES.STALE,
    "partial-received": PLANNING_WORKSPACE_STATES.PARTIAL,
    "missing-received": PLANNING_WORKSPACE_STATES.MISSING,
    "invalid-received": PLANNING_WORKSPACE_STATES.INVALID,
    "incompatible-received": PLANNING_WORKSPACE_STATES.INCOMPATIBLE,
    "legacy-received": PLANNING_WORKSPACE_STATES.LEGACY,
    "load-failed": PLANNING_WORKSPACE_STATES.ERROR,
    "legacy-active": PLANNING_WORKSPACE_STATES.LEGACY,
  };
  const nextState = transitions[event?.type];
  if (!nextState) return current;
  return planningWorkspaceModel({
    ...current,
    state: nextState,
    message: event.message || null,
    snapshot: event.snapshot
      ? { ...(current.snapshot || {}), ...event.snapshot }
      : current.snapshot,
    operationalUnit: event.operationalUnit || current.operationalUnit,
    planningDate: event.planningDate || current.planningDate,
  });
}


function placeholder(value, detail) {
  return Object.freeze({ value, detail });
}


export function derivePlanningWorkspaceView(state) {
  const presentation = PLANNING_WORKSPACE_PRESENTATION[state.state];
  const snapshot = state.snapshot || {};
  const noRuntime = "Planning Runtime non ancora collegato.";
  const readiness = snapshot.readiness || null;
  return Object.freeze({
    state: state.state,
    loading: state.state === PLANNING_WORKSPACE_STATES.LOADING,
    tone: presentation.tone,
    badge: presentation.label,
    statusTitle: presentation.title,
    statusDescription: state.message || presentation.description,
    planningDate: state.planningDate,
    operationalUnit: state.operationalUnit,
    readiness: readiness
      ? Object.freeze({
        value: `${readiness.score}/100 · ${readiness.isReady ? "Pronto" : "Non pronto"}`,
        detail: readiness.rationale,
        ...readiness,
      })
      : placeholder("Non disponibile", state.message || noRuntime),
    conflicts: snapshot.conflicts || null,
    timeline: snapshot.timeline || Object.freeze({ state: "loading" }),
    draft: snapshot.draft || Object.freeze({
      viewState: "loading",
      busy: false,
    }),
    confirmation: snapshot.confirmation || Object.freeze({
      viewState: "loading",
      busy: false,
    }),
    publication: snapshot.publication || Object.freeze({
      viewState: "loading",
      busy: false,
    }),
    canConfirm: snapshot.confirmation?.result?.canConfirm === true,
    canPublish: snapshot.publication?.result?.canPublish === true,
    canRetry: state.state === PLANNING_WORKSPACE_STATES.ERROR,
  });
}
