export function createOnboardingState(overrides = {}) {
  return {
    planningKnown: false,
    fleetKnown: false,
    planningImported: false,
    fleetImported: false,
    planningGenerated: false,
    dashboardAvailable: false,
    assetCount: 0,
    ...overrides,
  };
}


export function applyOnboardingEvent(current, event) {
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
    if (event.datasetType === "fleet") next.fleetImported = true;
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
  const systemEmpty = (
    !loading
    && !current.planningImported
    && !current.fleetImported
    && !current.planningGenerated
    && current.assetCount === 0
  );

  return {
    loading,
    showOnboarding: !systemOperational,
    showHero: systemEmpty,
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
