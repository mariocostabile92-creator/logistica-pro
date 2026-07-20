export const WORKSPACE_STATES = Object.freeze({
  EMPTY: "EMPTY",
  DEMO: "DEMO",
  PRODUCTION: "PRODUCTION",
});


export function createWorkspaceState(overrides = {}) {
  return {
    loading: true,
    status: null,
    error: null,
    ...overrides,
  };
}


export function applyWorkspaceEvent(current, event) {
  if (event.type === "load-started") {
    return { ...current, loading: true, error: null };
  }
  if (event.type === "load-completed") {
    return {
      loading: false,
      status: event.status,
      error: null,
    };
  }
  if (event.type === "load-failed") {
    return {
      ...current,
      loading: false,
      error: event.message,
    };
  }
  return current;
}


function copyFor(state) {
  const copies = {
    [WORKSPACE_STATES.EMPTY]: {
      label: "Workspace vuoto",
      shortLabel: "Vuoto",
      description: "Nessun dato operativo caricato.",
      tone: "empty",
      importLabel: "Importa dati",
    },
    [WORKSPACE_STATES.DEMO]: {
      label: "Workspace demo",
      shortLabel: "Demo",
      description: "Stai lavorando con dati sintetici della Private Beta.",
      tone: "demo",
      importLabel: "Importa dati reali",
    },
    [WORKSPACE_STATES.PRODUCTION]: {
      label: "Workspace produzione",
      shortLabel: "Produzione",
      description: "Il workspace contiene dati operativi non demo.",
      tone: "production",
      importLabel: "Importa nuovi dati",
    },
  };
  return copies[state] || copies[WORKSPACE_STATES.EMPTY];
}


export function deriveWorkspaceView(current) {
  if (current.loading && !current.status) {
    return {
      loading: true,
      label: "Verifica workspace",
      shortLabel: "Verifica in corso",
      description: "Caricamento dello stato operativo.",
      tone: "loading",
      status: null,
      actions: {},
    };
  }
  if (current.error && !current.status) {
    return {
      loading: false,
      label: "Workspace non disponibile",
      shortLabel: "Non disponibile",
      description: current.error,
      tone: "error",
      status: null,
      actions: {},
    };
  }

  const status = current.status;
  const state = status.workspace_state;
  const copy = copyFor(state);
  return {
    loading: current.loading,
    ...copy,
    status,
    actions: {
      import: true,
      loadDemo: (
        state === WORKSPACE_STATES.EMPTY
        && Boolean(status.demo_enabled)
      ),
      newDay: state !== WORKSPACE_STATES.EMPTY,
      reset: state !== WORKSPACE_STATES.EMPTY,
    },
  };
}


export function canConfirmWorkspaceReset(value, busy = false) {
  return !busy && value === "RIPRISTINA";
}


export function importFlowForState(state) {
  if (state === WORKSPACE_STATES.EMPTY) return "direct";
  if (state === WORKSPACE_STATES.DEMO) return "reset-demo";
  return "choose-production";
}
