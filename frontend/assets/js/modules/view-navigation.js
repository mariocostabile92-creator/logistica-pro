import { byId } from "../utils/dom.js";


const OPERATIONS_SECTIONS = [
  "onboardingSection",
  "planningSection",
  "dashboardSection",
  "importsSection",
];

const WORKSPACE_SECTIONS = {
  operations: OPERATIONS_SECTIONS,
  fleet: ["fleetPluginSection"],
  settings: ["settingsSection"],
  "getting-started": ["gettingStartedSection"],
};


function showWorkspace(view) {
  const activeSections = WORKSPACE_SECTIONS[view] || OPERATIONS_SECTIONS;
  for (const sectionId of Object.values(WORKSPACE_SECTIONS).flat()) {
    byId(sectionId).hidden = !activeSections.includes(sectionId);
  }

  document.querySelectorAll("[data-workspace-view]").forEach((button) => {
    const active = button.dataset.workspaceView === view;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  });

  document.dispatchEvent(new CustomEvent("workspace:view-changed", {
    detail: { view },
  }));
}


export function initViewNavigation() {
  document.querySelectorAll("[data-workspace-view]").forEach((button) => {
    button.addEventListener("click", () => {
      showWorkspace(button.dataset.workspaceView);
    });
  });
  document.addEventListener("workspace:navigate", (event) => {
    showWorkspace(event.detail.view);
    if (event.detail.targetId) {
      requestAnimationFrame(() => {
        byId(event.detail.targetId).scrollIntoView({
          behavior: "smooth",
          block: "start",
        });
      });
    }
  });
}
