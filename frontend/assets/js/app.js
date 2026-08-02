import { getHealth } from "./api.js";
import {
  abortBriefingRequest,
  initBriefing,
  refreshBriefing,
} from "./modules/briefing.js";
import { initMissionControl } from "./modules/mission-control.js";
import { initViewNavigation } from "./modules/view-navigation.js";
import {
  ensureWorkspaceInitialized,
  initWorkspaceLoader,
} from "./modules/workspace-loader.js?v=15";
import {
  initWorkspaceLifecycle,
  refreshWorkspaceStatus,
} from "./modules/workspace-lifecycle.js";
import { byId } from "./utils/dom.js";
import { requireAdministrativeSession } from "./auth/session.js?v=1";


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


async function refreshMissionControlData() {
  return Promise.allSettled([
    refreshBriefing({ announce: false }),
    refreshWorkspaceStatus({ force: true, preserveCurrent: true }),
  ]);
}


async function bootstrapAdministrativeApp() {
  await requireAdministrativeSession();
  initMissionControl({
    onRefresh: refreshMissionControlData,
    onOperationalUnitChange: abortBriefingRequest,
  });
  initBriefing();
  initWorkspaceLifecycle();
  initWorkspaceLoader();
  initViewNavigation({ loadWorkspace: ensureWorkspaceInitialized });
  checkHealth();
}

bootstrapAdministrativeApp();
