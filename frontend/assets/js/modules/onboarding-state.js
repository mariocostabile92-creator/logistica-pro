export function createOnboardingState(overrides = {}) {
  return {
    planningKnown: false,
    fleetKnown: false,
    planningImported: false,
    fleetImported: false,
    planningGenerated: false,
    dashboardAvailable: false,
    assetCount: 0,
    workforceMemberCount: 0,
    ...overrides,
  };
}


export function applyOnboardingEvent(current, event) {
  if (event.type === "workspace-reset") {
    return createOnboardingState({
      planningKnown: true,
      fleetKnown: true,
    });
  }

  const next = { ...current };

  if (event.type === "planning-availability") {
    next.planningKnown = true;
    next.planningGenerated = Boolean(event.hasPlanning);
    if (event.hasPlanning) {
      next.planningImported = true;
      next.fleetImported = true;
    }
  }

  if (event.type === "fleet-registry-loaded") {
    next.fleetKnown = true;
    next.assetCount = Number.isInteger(event.assetCount)
      ? event.assetCount
      : null;
  }

  if (event.type === "dataset-imported") {
    if (event.datasetType === "planning") next.planningImported = true;
    if (event.datasetType === "workforce") next.planningImported = true;
    if (event.datasetType === "fleet") next.fleetImported = true;
  }

  if (event.type === "workspace-status") {
    next.workforceMemberCount = Number(event.workforceMemberCount || 0);
    if (next.workforceMemberCount > 0) next.planningImported = true;
  }

  if (event.type === "dashboard-availability") {
    next.dashboardAvailable = Boolean(event.available);
  }

  return next;
}


export function deriveOnboardingView(current) {
  const loading = !current.planningKnown || !current.fleetKnown;
  const systemOperational = (
    current.planningGenerated && current.dashboardAvailable
  );
  let activeStep = null;
  if (!current.planningImported) activeStep = "planning";
  else if (!current.fleetImported) activeStep = "fleet";
  else if (!current.planningGenerated) activeStep = "generate";

  return {
    loading,
    homeState: loading
      ? "loading"
      : current.planningGenerated
        ? "ready"
        : "setup",
    showOnboarding: !current.planningGenerated,
    showHero: !loading && !current.planningGenerated,
    activeStep,
    steps: {
      planningImported: current.planningImported,
      fleetImported: current.fleetImported,
      planningGenerated: current.planningGenerated,
    },
    checklist: {
      planningImported: current.planningImported,
      fleetImported: current.fleetImported,
      planningGenerated: current.planningGenerated,
      systemOperational,
    },
  };
}
