const prepared = new Map();
const initialized = new Set();
const loadedStyles = new Map();
const sharedInitializers = new Set();
let loaderInitialized = false;


const STYLES = {
  operations: [
    "planning-workspace.css?v=1",
    "onboarding.css",
    "fleet-sync.css",
    "excel-import.css",
  ],
  workforce: [
    "workforce.css?v=5",
    "workforce-layout.css?v=3",
    "workforce-calendar.css?v=3",
    "workforce-panel.css?v=3",
    "workforce-responsive.css?v=5",
  ],
  fleet: ["fleet.css", "fleet-sync.css", "operational-documents.css?v=1", "damage-workspace.css?v=2", "maintenance-workspace.css?v=1"],
  settings: ["settings.css", "organization-settings.css?v=1"],
  demo: ["demo-workspace.css"],
};


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
    const [
      planningImport,
      fleetImport,
      operationsDashboard,
      planningPage,
      onboarding,
      planningWorkspace,
    ] = await Promise.all([
      import("./import-planning.js"),
      import("./import-fleet.js"),
      import("./operations-dashboard.js"),
      import("./planning-page.js"),
      import("./onboarding.js"),
      import("./planning-workspace/index.js"),
      loadWorkspaceStyles("operations"),
    ]);
    return () => {
      planningWorkspace.initPlanningWorkspace();
      planningImport.initPlanningImport();
      fleetImport.initFleetImport();
      operationsDashboard.initOperationsDashboard();
      planningPage.initPlanningPage();
      onboarding.initOnboarding();
    };
  },
  workforce: async () => {
    const [module] = await Promise.all([
      import("./workforce-page.js"),
      loadWorkspaceStyles("workforce"),
    ]);
    return module.initWorkforcePage;
  },
  fleet: async () => {
    const [module, fleetSync] = await Promise.all([
      import("./fleet-page.js?v=16"),
      import("./fleet-sync.js"),
      loadWorkspaceStyles("fleet"),
    ]);
    return async () => {
      module.initFleetPage();
      initializeOnce("fleet-sync", fleetSync.initFleetSync);
      await module.prepareFleetFirstPaint();
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
