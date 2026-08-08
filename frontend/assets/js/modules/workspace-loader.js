const prepared = new Map();
const initialized = new Set();
const loadedStyles = new Map();
const sharedInitializers = new Set();
let loaderInitialized = false;


const STYLES = {
  operations: [
    "planning-workspace.css?v=5",
  ],
  "operations-legacy": [
    "fleet-sync.css",
    "excel-import.css",
  ],
  workforce: [
    "workforce.css?v=5",
    "workforce-layout.css?v=3",
    "workforce-calendar.css?v=3",
    "workforce-panel.css?v=4",
    "workforce-responsive.css?v=5",
    "workforce-foundation.css?v=2",
  ],
  fleet: [
    "fleet.css",
    "fleet-sync.css",
  ],
  "fleet-secondary": [
    "damage-workspace.css?v=4",
    "maintenance-workspace.css?v=2",
    "documents-workspace.css?v=1",
    "franchise-workspace.css?v=1",
    "insurance-workspace.css?v=1",
    "rental-workspace.css?v=1",
    "journal-control-room.css?v=6",
    "journal-completion.css?v=1",
    "journal-archive.css?v=3",
    "journal-calendar-intelligence.css?v=4",
    "journal-shared-access.css?v=2",
    "attachments.css?v=2",
    "vehicle-dossier.css?v=1",
    "fleet-vision-workspace.css?v=3",
  ],
  settings: ["settings.css", "organization-settings.css?v=1"],
  demo: ["demo-workspace.css"],
};

let legacyOperationsPreparation = null;


function prepareLegacyOperations() {
  if (legacyOperationsPreparation) return legacyOperationsPreparation;
  legacyOperationsPreparation = Promise.all([
    import("./import-planning.js"),
    import("./import-fleet.js"),
    import("./operations-dashboard.js"),
    import("./planning-page.js"),
    loadWorkspaceStyles("operations-legacy"),
  ]).then(([planningImport, fleetImport, operationsDashboard, planningPage]) => {
    planningImport.initPlanningImport();
    fleetImport.initFleetImport();
    operationsDashboard.initOperationsDashboard();
    planningPage.initPlanningPage();
  });
  return legacyOperationsPreparation;
}


function initializeLegacyOperationsTrigger() {
  initializeOnce("operations-legacy-trigger", () => {
    const disclosure = document.getElementById("legacyOperationsRegion");
    if (!disclosure) return;
    disclosure.addEventListener("toggle", () => {
      if (disclosure.open) void prepareLegacyOperations();
    });
  });
}


function loadStylesheet(filename) {
  const url = new URL(`../../css/${filename}`, import.meta.url).href;
  if (loadedStyles.has(url)) return loadedStyles.get(url);
  const existing = [...document.styleSheets].find((sheet) => sheet.href === url);
  if (existing) return Promise.resolve();
  const promise = new Promise((resolve) => {
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = url;
    link.addEventListener("load", resolve, { once: true });
    link.addEventListener("error", resolve, { once: true });
    document.head.append(link);
  });
  loadedStyles.set(url, promise);
  return promise;
}


async function loadWorkspaceStyles(view) {
  await Promise.all((STYLES[view] || []).map(loadStylesheet));
}


function initializeOnce(key, callback) {
  if (sharedInitializers.has(key)) return;
  callback();
  sharedInitializers.add(key);
}


const WORKSPACE_PREPARERS = {
  operations: async () => {
    const [planningWorkspace] = await Promise.all([
      import("./planning-workspace/index.js?v=5"),
      loadWorkspaceStyles("operations"),
    ]);
    return async () => {
      await planningWorkspace.initPlanningWorkspace();
      initializeLegacyOperationsTrigger();
    };
  },
  workforce: async () => {
    const [module] = await Promise.all([
      import("./workforce-page.js?v=8"),
      loadWorkspaceStyles("workforce"),
    ]);
    return async () => {
      module.initWorkforcePage();
      await module.prepareWorkforceFirstPaint();
    };
  },
  fleet: async () => {
    const [module, fleetSync] = await Promise.all([
      import("./fleet-page.js?v=25"),
      import("./fleet-sync.js"),
      loadWorkspaceStyles("fleet"),
    ]);
    return async () => {
      module.initFleetPage();
      initializeOnce("fleet-sync", fleetSync.initFleetSync);
      await module.prepareFleetFirstPaint();
      const loadSecondaryStyles = () => void loadWorkspaceStyles("fleet-secondary");
      if ("requestIdleCallback" in window) window.requestIdleCallback(loadSecondaryStyles);
      else queueMicrotask(loadSecondaryStyles);
    };
  },
  settings: async () => {
    const [module] = await Promise.all([
      import("./settings-page.js"),
      loadWorkspaceStyles("settings"),
    ]);
    return module.initSettingsPage;
  },
  demo: async () => {
    const [module] = await Promise.all([
      import("./demo-workspace.js"),
      loadWorkspaceStyles("demo"),
    ]);
    return module.initDemoWorkspace;
  },
};


async function prepareWorkspace(view) {
  if (!WORKSPACE_PREPARERS[view] || initialized.has(view)) return null;
  if (!prepared.has(view)) prepared.set(view, WORKSPACE_PREPARERS[view]());
  return prepared.get(view);
}


export async function preloadWorkspace(view) {
  if (!WORKSPACE_PREPARERS[view] || initialized.has(view)) return false;
  await prepareWorkspace(view);
  return true;
}


export async function ensureWorkspaceInitialized(view) {
  if (!WORKSPACE_PREPARERS[view] || initialized.has(view)) return false;
  const initialize = await prepareWorkspace(view);
  if (!initialize || initialized.has(view)) return false;
  await initialize();
  initialized.add(view);
  return true;
}


function replayAfterInitialization(eventName, view) {
  document.addEventListener(eventName, async (event) => {
    if (event.detail?.replayed || initialized.has(view)) return;
    await ensureWorkspaceInitialized(view);
    document.dispatchEvent(new CustomEvent(eventName, {
      detail: { ...(event.detail || {}), replayed: true },
    }));
  });
}


export function initWorkspaceLoader() {
  if (loaderInitialized) return;
  loaderInitialized = true;
  replayAfterInitialization("demo:load-requested", "demo");
  replayAfterInitialization("workforce:import-requested", "workforce");
}
