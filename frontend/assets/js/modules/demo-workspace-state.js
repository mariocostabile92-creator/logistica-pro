export function createDemoWorkspaceState(overrides = {}) {
  return {
    initialized: false,
    enabled: null,
    status: "no_demo",
    summary: null,
    busy: false,
    error: null,
    ...overrides,
  };
}


export function applyDemoWorkspaceEvent(current, event) {
  const next = { ...current };

  if (event.type === "disabled") {
    next.initialized = true;
    next.enabled = false;
    next.busy = false;
    next.error = null;
  }

  if (event.type === "status-loaded") {
    next.initialized = true;
    next.enabled = true;
    next.status = event.status;
    next.summary = event.summary || null;
    next.busy = false;
    next.error = null;
  }

  if (event.type === "operation-started") {
    next.busy = true;
    next.error = null;
  }

  if (event.type === "load-completed") {
    next.initialized = true;
    next.enabled = true;
    next.status = "ready";
    next.summary = event.summary;
    next.busy = false;
    next.error = null;
  }

  if (event.type === "reset-completed") {
    next.initialized = true;
    next.enabled = true;
    next.status = "reset";
    next.summary = null;
    next.busy = false;
    next.error = null;
  }

  if (event.type === "operation-failed") {
    next.initialized = true;
    next.enabled = true;
    next.status = "failed";
    next.busy = false;
    next.error = event.message;
  }

  return next;
}


export function deriveDemoWorkspaceView(current) {
  const active = current.status === "ready" && Boolean(current.summary);
  const loading = !current.initialized || current.busy;
  const statusMessages = {
    failed: "Il caricamento precedente non e stato completato. Puoi riprovare in sicurezza.",
    partial: "Il workspace demo e incompleto. Riprendi il caricamento per ricostruirlo.",
    reset: "I dati demo sono stati rimossi. Puoi caricarli di nuovo quando vuoi.",
  };
  return {
    hidden: current.enabled === false,
    loading,
    active,
    inactive: !loading && !active,
    badge: active ? "Modalit\u00e0 demo attiva" : "DEMO",
    loadLabel: ["failed", "partial"].includes(current.status)
      ? "Riprova caricamento"
      : "Carica demo",
    statusMessage: current.error
      || statusMessages[current.status]
      || "",
    summary: current.summary,
  };
}
