import { byId } from "../utils/dom.js";


const HOME_SECTIONS = [
  "missionControlSection",
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
  workforce: ["workforceSection"],
  fleet: ["fleetPluginSection"],
  settings: ["settingsSection"],
  learn: ["gettingStartedSection"],
};

const deferredSections = new Map();
let initializeWorkspace = async () => false;
let navigationVersion = 0;
let initialized = false;


function sectionNode(sectionId) {
  return deferredSections.get(sectionId)?.node || byId(sectionId);
}


function prepareDeferredSections() {
  Object.entries(WORKSPACE_SECTIONS).forEach(([view, sectionIds]) => {
    if (view === "home") return;
    sectionIds.forEach((sectionId) => {
      const node = byId(sectionId);
      const anchor = document.createComment(`workspace:${sectionId}`);
      node.before(anchor);
      node.remove();
      deferredSections.set(sectionId, { node, anchor, attached: false });
    });
  });
}


function attachWorkspaceSections(view) {
  (WORKSPACE_SECTIONS[view] || []).forEach((sectionId) => {
    const deferred = deferredSections.get(sectionId);
    if (!deferred || deferred.attached) return;
    deferred.anchor.after(deferred.node);
    deferred.attached = true;
  });
}


function showWorkspace(view) {
  const selectedView = WORKSPACE_SECTIONS[view] ? view : "home";
  const activeSections = WORKSPACE_SECTIONS[selectedView];
  attachWorkspaceSections(selectedView);
  document.body.dataset.activeWorkspace = selectedView;
  for (const sectionId of Object.values(WORKSPACE_SECTIONS).flat()) {
    const section = sectionNode(sectionId);
    if (section?.isConnected) section.hidden = !activeSections.includes(sectionId);
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
  document.dispatchEvent(new CustomEvent("workspace:view-started", {
    detail: { view: selectedView },
  }));
  return selectedView;
}


function announceWorkspace(view) {
  document.dispatchEvent(new CustomEvent("workspace:view-changed", {
    detail: { view },
  }));
}


function revealTarget(targetId) {
  const target = byId(targetId);
  if (!target) return;
  target.closest("details")?.setAttribute("open", "");
  target.scrollIntoView({
    behavior: "smooth",
    block: "start",
  });
}


async function navigate(view, targetId = null) {
  const version = ++navigationVersion;
  const selectedView = showWorkspace(view);
  await initializeWorkspace(selectedView);
  if (version !== navigationVersion) return;
  announceWorkspace(selectedView);
  if (targetId) requestAnimationFrame(() => revealTarget(targetId));
}


function handleNavigationClick(event) {
  const button = event.target.closest("[data-workspace-view]");
  if (!button) return;
  navigate(button.dataset.workspaceView);
}


export function initViewNavigation({ loadWorkspace } = {}) {
  if (initialized) return;
  initialized = true;
  if (loadWorkspace) initializeWorkspace = loadWorkspace;
  prepareDeferredSections();
  document.addEventListener("click", handleNavigationClick);
  document.addEventListener("workspace:navigate", (event) => {
    navigate(event.detail.view, event.detail.targetId || null);
  });
  navigate("home");
}
