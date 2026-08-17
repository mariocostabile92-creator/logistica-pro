import { getHealth } from "./api.js?v=5";
import { initMissionControl } from "./modules/mission-control.js?v=7";
import { initViewNavigation } from "./modules/view-navigation.js?v=56";
import {
  ensureWorkspaceInitialized,
  initWorkspaceLoader,
  preloadWorkspace,
} from "./modules/workspace-loader.js?v=111";
import { initWorkspaceLifecycle } from "./modules/workspace-lifecycle.js?v=2";
import { byId } from "./utils/dom.js";
import { requireAdministrativeSession } from "./auth/session.js?v=2";
import {
  failAdministrativeBootstrap,
  revealAdministrativeApp,
  startAdministrativeBootstrap,
} from "./modules/app-bootstrap.js?v=2";
import { retireLegacyServiceWorker } from "./modules/pwa.js?v=3";


function retirePwaAfterHome(homeReady) {
  Promise.resolve(homeReady).finally(() => {
    const retire = () => retireLegacyServiceWorker();
    if ("requestIdleCallback" in window) window.requestIdleCallback(retire);
    else queueMicrotask(retire);
  });
}


async function checkHealth() {
  const badge = byId("healthStatus");
  try {
    await getHealth();
    badge.textContent = "Backend online";
    badge.className = "status-pill ok";
  } catch {
    badge.textContent = "Backend non raggiungibile";
    badge.className = "status-pill";
  }
}


async function bootstrapAdministrativeApp() {
  startAdministrativeBootstrap();
  try {
    await requireAdministrativeSession();
    const homeReady = initMissionControl();
    initWorkspaceLifecycle();
    initWorkspaceLoader();
    initViewNavigation({
      loadWorkspace: ensureWorkspaceInitialized,
      prepareWorkspace: preloadWorkspace,
    });
    checkHealth();
    retirePwaAfterHome(homeReady);
    await homeReady;
    revealAdministrativeApp();
    const warmPrimaryWorkspaces = () => void Promise.all(
      ["operations", "workforce", "dsp", "fleet"].map(preloadWorkspace),
    );
    if ("requestIdleCallback" in window) {
      window.requestIdleCallback(warmPrimaryWorkspaces, { timeout: 1500 });
    } else window.setTimeout(warmPrimaryWorkspaces, 250);
  } catch (error) {
    if (error?.status !== 401) failAdministrativeBootstrap();
  }
}

bootstrapAdministrativeApp();
