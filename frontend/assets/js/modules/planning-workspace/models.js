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
    title: "Preparazione area Planning",
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
    description: "Il piano è pronto per la verifica operativa.",
    tone: "stable",
  }),
  [PLANNING_WORKSPACE_STATES.WARNING]: Object.freeze({
    label: "Attenzione",
    title: "Pronto con avvisi",
    description: "Il piano può essere preparato dopo una verifica degli avvisi.",
    tone: "attention",
  }),
  [PLANNING_WORKSPACE_STATES.BLOCKED]: Object.freeze({
    label: "Bloccato",
    title: "Intervento richiesto",
    description: "Risolvi i blocchi indicati prima di preparare il piano.",
    tone: "critical",
  }),
  [PLANNING_WORKSPACE_STATES.STALE]: Object.freeze({
    label: "Da aggiornare",
    title: "Dati non aggiornati",
    description: "Aggiorna i dati operativi prima di procedere.",
    tone: "attention",
  }),
  [PLANNING_WORKSPACE_STATES.PARTIAL]: Object.freeze({
    label: "Parziale",
    title: "Dati incompleti",
    description: "Completa i dati indicati prima di preparare il piano.",
    tone: "attention",
  }),
  [PLANNING_WORKSPACE_STATES.MISSING]: Object.freeze({
    label: "Dati mancanti",
    title: "Dati operativi non disponibili",
    description: "Aggiorna Workforce e Fleet per calcolare la preparazione.",
    tone: "critical",
  }),
  [PLANNING_WORKSPACE_STATES.INVALID]: Object.freeze({
    label: "Non valido",
    title: "Dati da correggere",
    description: "I dati contengono errori bloccanti.",
    tone: "critical",
  }),
  [PLANNING_WORKSPACE_STATES.INCOMPATIBLE]: Object.freeze({
    label: "Non compatibile",
    title: "Contesto operativo non coerente",
    description: "Allinea unità operativa, data e versioni dei dati.",
    tone: "critical",
  }),
  [PLANNING_WORKSPACE_STATES.ERROR]: Object.freeze({
    label: "Non disponibile",
    title: "Area Planning non disponibile",
    description: "Lo stato non può essere presentato in questo momento.",
    tone: "critical",
  }),
  [PLANNING_WORKSPACE_STATES.LEGACY]: Object.freeze({
    label: "Flusso precedente",
    title: "Flusso precedente attivo",
    description: "Il nuovo motore di pianificazione non è ancora collegato.",
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
