import { getHealth } from "./api.js?v=5";
import { initBriefing } from "./modules/briefing.js";
import { initMissionControl } from "./modules/mission-control.js?v=6";
import { initViewNavigation } from "./modules/view-navigation.js?v=3";
import {
  ensureWorkspaceInitialized,
  initWorkspaceLoader,
} from "./modules/workspace-loader.js?v=24";
import { initWorkspaceLifecycle } from "./modules/workspace-lifecycle.js";
import { byId } from "./utils/dom.js";
import { requireAdministrativeSession } from "./auth/session.js?v=2";
import {
  failAdministrativeBootstrap,
  revealAdministrativeApp,
  startAdministrativeBootstrap,
} from "./modules/app-bootstrap.js?v=1";
import { registerServiceWorker } from "./modules/pwa.js?v=1";


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
    initMissionControl();
    initBriefing();
    initWorkspaceLifecycle();
    initWorkspaceLoader();
    initViewNavigation({ loadWorkspace: ensureWorkspaceInitialized });
    await revealAdministrativeApp();
    checkHealth();
    registerServiceWorker();
  } catch (error) {
    if (error?.status !== 401) failAdministrativeBootstrap();
  }
}

bootstrapAdministrativeApp();
