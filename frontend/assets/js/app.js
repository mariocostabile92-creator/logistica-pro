import { getHealth } from "./api.js";
import { initBriefing } from "./modules/briefing.js";
import { initMissionControl } from "./modules/mission-control.js?v=5";
import { initViewNavigation } from "./modules/view-navigation.js?v=2";
import {
  ensureWorkspaceInitialized,
  initWorkspaceLoader,
} from "./modules/workspace-loader.js?v=23";
import { initWorkspaceLifecycle } from "./modules/workspace-lifecycle.js";
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


async function bootstrapAdministrativeApp() {
  await requireAdministrativeSession();
  initMissionControl();
  initBriefing();
  initWorkspaceLifecycle();
  initWorkspaceLoader();
  initViewNavigation({ loadWorkspace: ensureWorkspaceInitialized });
  checkHealth();
}

bootstrapAdministrativeApp();
