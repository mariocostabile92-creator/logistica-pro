import { getHealth } from "./api.js";
import { initBriefing } from "./modules/briefing.js";
import { initFleetImport } from "./modules/import-fleet.js";
import { initFleetPage } from "./modules/fleet-page.js";
import { initDemoWorkspace } from "./modules/demo-workspace.js";
import { initOnboarding } from "./modules/onboarding.js";
import { initOperationsDashboard } from "./modules/operations-dashboard.js";
import { initPlanningPage } from "./modules/planning-page.js";
import { initPlanningImport } from "./modules/import-planning.js";
import { initSettingsPage } from "./modules/settings-page.js";
import { initViewNavigation } from "./modules/view-navigation.js";
import { initWorkspaceLifecycle } from "./modules/workspace-lifecycle.js";
import { byId } from "./utils/dom.js";


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


initPlanningImport();
initFleetImport();
initBriefing();
initOnboarding();
initOperationsDashboard();
initPlanningPage();
initFleetPage();
initSettingsPage();
initViewNavigation();
initDemoWorkspace();
initWorkspaceLifecycle();
checkHealth();
