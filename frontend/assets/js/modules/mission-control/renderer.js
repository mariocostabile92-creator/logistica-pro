import { renderFleet } from "./fleet.js";
import { renderHero } from "./hero.js";
import { renderPlanning } from "./planning.js?v=2";
import { renderPriorities } from "./priority.js";
import { renderQuickActions } from "./quick-actions.js";
import { renderRecent } from "./recent.js";
import { renderWorkforce } from "./workforce.js";


export function renderMissionControl(view) {
  renderHero(view);
  renderPriorities(view);
  renderFleet(view);
  renderWorkforce(view);
  renderPlanning(view);
  renderRecent(view);
  renderQuickActions();
}
