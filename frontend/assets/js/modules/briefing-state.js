const FILTER_SEVERITIES = {
  all: null,
  critical: new Set(["blocker", "critical"]),
  attention: new Set(["high", "medium"]),
  information: new Set(["low", "information"]),
};


export function createBriefingState(overrides = {}) {
  return {
    phase: "loading",
    briefing: null,
    filter: "all",
    expanded: false,
    error: null,
    demoEnabled: false,
    ...overrides,
  };
}


export function applyBriefingEvent(current, event) {
  const next = { ...current };
  if (event.type === "load-started") {
    next.phase = current.briefing ? current.phase : "loading";
    next.error = null;
  }
  if (event.type === "load-completed") {
    next.phase = event.briefing.status === "available"
      ? "available"
      : "unavailable";
    next.briefing = event.briefing;
    next.error = null;
  }
  if (event.type === "load-failed") {
    next.phase = current.briefing?.status === "available"
      ? "available"
      : "error";
    next.error = event.message;
  }
  if (
    event.type === "filter-selected"
    && Object.hasOwn(FILTER_SEVERITIES, event.filter)
  ) {
    next.filter = event.filter;
    next.expanded = true;
  }
  if (event.type === "expanded-toggled") {
    next.expanded = !current.expanded;
    if (!next.expanded) next.filter = "all";
  }
  if (event.type === "demo-availability") {
    next.demoEnabled = Boolean(event.enabled);
  }
  if (event.type === "workspace-reset") {
    next.phase = "unavailable";
    next.briefing = event.briefing || null;
    next.error = null;
    next.filter = "all";
    next.expanded = false;
  }
  return next;
}


export function filterBriefingSections(sections, filter) {
  const severities = FILTER_SEVERITIES[filter] || null;
  return [...sections]
    .sort((left, right) => left.priority - right.priority)
    .filter((section) => (
      !severities || severities.has(section.severity)
    ));
}


export function deriveBriefingView(current) {
  const briefing = current.briefing;
  const available = (
    current.phase === "available"
    && briefing?.status === "available"
  );
  const filteredSections = available
    ? filterBriefingSections(briefing.sections, current.filter)
    : [];
  return {
    loading: current.phase === "loading",
    error: current.phase === "error",
    empty: current.phase === "unavailable",
    available,
    errorMessage: current.error || "",
    emptyMessage: briefing?.executive_summary
      || "Il briefing sarà disponibile dopo la creazione del primo planning.",
    showDemoAction: current.demoEnabled,
    selectedFilter: current.filter,
    expanded: current.expanded,
    totalSections: available ? briefing.sections.length : 0,
    hasMore: available && briefing.sections.length > 3,
    sections: current.expanded
      ? filteredSections
      : filteredSections.slice(0, 3),
    briefing,
  };
}
