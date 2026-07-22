export const PLANNING_WORKSPACE_STATES = Object.freeze({
  LOADING: "loading",
  EMPTY: "empty",
  READY: "ready",
  WARNING: "warning",
  ERROR: "error",
  LEGACY: "legacy",
});


export const PLANNING_WORKSPACE_PRESENTATION = Object.freeze({
  [PLANNING_WORKSPACE_STATES.LOADING]: Object.freeze({
    label: "Caricamento",
    title: "Preparazione Planning Workspace",
    description: "Verifica della struttura applicativa in corso.",
    tone: "neutral",
  }),
  [PLANNING_WORKSPACE_STATES.EMPTY]: Object.freeze({
    label: "Nessun piano",
    title: "Nessun planning disponibile",
    description: "Importa i dati operativi dal flusso attuale per iniziare.",
    tone: "neutral",
  }),
  [PLANNING_WORKSPACE_STATES.READY]: Object.freeze({
    label: "Pronto",
    title: "Planning pronto per la verifica",
    description: "Lo stato READY deve essere fornito da un contratto esplicito.",
    tone: "stable",
  }),
  [PLANNING_WORKSPACE_STATES.WARNING]: Object.freeze({
    label: "Attenzione",
    title: "Planning da verificare",
    description: "Sono presenti elementi espliciti che richiedono attenzione.",
    tone: "attention",
  }),
  [PLANNING_WORKSPACE_STATES.ERROR]: Object.freeze({
    label: "Non disponibile",
    title: "Planning Workspace non disponibile",
    description: "Lo stato non può essere presentato in questo momento.",
    tone: "critical",
  }),
  [PLANNING_WORKSPACE_STATES.LEGACY]: Object.freeze({
    label: "Legacy",
    title: "Flusso legacy attivo",
    description: "Planning Runtime non ancora collegato.",
    tone: "information",
  }),
});


export function planningWorkspaceModel({
  state,
  planningDate,
  operationalUnit = "Tutte",
  message = null,
  snapshot = null,
} = {}) {
  const normalizedState = Object.values(PLANNING_WORKSPACE_STATES).includes(state)
    ? state
    : PLANNING_WORKSPACE_STATES.LOADING;
  return Object.freeze({
    state: normalizedState,
    planningDate: planningDate || null,
    operationalUnit,
    message,
    snapshot,
  });
}
