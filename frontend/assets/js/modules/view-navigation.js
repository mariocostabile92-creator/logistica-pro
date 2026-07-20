import { byId } from "../utils/dom.js";


const HOME_SECTIONS = [
  "workspaceCurrentSection",
  "onboardingSection",
  "briefingSection",
  "demoWorkspaceHomeSection",
];

const OPERATIONS_SECTIONS = [
  "planningSection",
  "dashboardSection",
  "importsSection",
];

const WORKSPACE_SECTIONS = {
  home: HOME_SECTIONS,
  operations: OPERATIONS_SECTIONS,
  fleet: ["fleetPluginSection"],
  settings: ["settingsSection"],
  learn: ["gettingStartedSection"],
};


function showWorkspace(view) {
  const selectedView = WORKSPACE_SECTIONS[view] ? view : "home";
  const activeSections = WORKSPACE_SECTIONS[selectedView];
  for (const sectionId of Object.values(WORKSPACE_SECTIONS).flat()) {
    byId(sectionId).hidden = !activeSections.includes(sectionId);
  }

  document.querySelectorAll("[data-workspace-view]").forEach((button) => {
    const active = button.dataset.workspaceView === selectedView;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
    if (button.classList.contains("workspace-tab")) {
      if (active) button.setAttribute("aria-current", "page");
      else button.removeAttribute("aria-current");
    }
  });

  document.dispatchEvent(new CustomEvent("workspace:view-changed", {
    detail: { view: selectedView },
  }));
}


function revealTarget(targetId) {
  const target = byId(targetId);
  target.closest("details")?.setAttribute("open", "");
  target.scrollIntoView({
    behavior: "smooth",
    block: "start",
  });
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
        revealTarget(event.detail.targetId);
      });
    }
  });
  showWorkspace("home");
}
