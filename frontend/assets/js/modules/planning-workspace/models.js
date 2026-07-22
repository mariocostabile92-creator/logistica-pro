export const PLANNING_WORKSPACE_STATES = Object.freeze({
  LOADING: "loading",
  EMPTY: "empty",
  READY: "ready",
  WARNING: "warning",
  BLOCKED: "blocked",
  STALE: "stale",
  PARTIAL: "partial",
  MISSING: "missing",
  INVALID: "invalid",
  INCOMPATIBLE: "incompatible",
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
    title: "Pronto con avvisi",
    description: "Il piano puo essere preparato dopo una verifica degli avvisi.",
    tone: "attention",
  }),
  [PLANNING_WORKSPACE_STATES.BLOCKED]: Object.freeze({
    label: "Bloccato",
    title: "Intervento richiesto",
    description: "Risolvi i blocker indicati prima di preparare il piano.",
    tone: "critical",
  }),
  [PLANNING_WORKSPACE_STATES.STALE]: Object.freeze({
    label: "Da aggiornare",
    title: "Dati non aggiornati",
    description: "Aggiorna gli snapshot operativi prima di procedere.",
    tone: "attention",
  }),
  [PLANNING_WORKSPACE_STATES.PARTIAL]: Object.freeze({
    label: "Parziale",
    title: "Dati incompleti",
    description: "Completa gli input indicati prima di preparare il piano.",
    tone: "attention",
  }),
  [PLANNING_WORKSPACE_STATES.MISSING]: Object.freeze({
    label: "Dati mancanti",
    title: "Input non disponibili",
    description: "Aggiorna Workforce e Fleet per calcolare la readiness.",
    tone: "critical",
  }),
  [PLANNING_WORKSPACE_STATES.INVALID]: Object.freeze({
    label: "Non valido",
    title: "Dati da correggere",
    description: "Gli input contengono errori bloccanti.",
    tone: "critical",
  }),
  [PLANNING_WORKSPACE_STATES.INCOMPATIBLE]: Object.freeze({
    label: "Non compatibile",
    title: "Contesto operativo non coerente",
    description: "Allinea Operational Unit, data e versioni degli input.",
    tone: "critical",
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
