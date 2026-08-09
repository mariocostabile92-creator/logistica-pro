import {
  initDspWorkspace,
  prepareDspFirstPaint,
} from "../dsp-workspace/index.js?v=5";


let initialized = false;
let activeArea = "operations";
let qualityModulePromise = null;


function refs() {
  return {
    root: document.getElementById("dspWorkspaceSection"),
    tabs: [...document.querySelectorAll("[data-dsp-area]")],
    operations: document.getElementById("dspOperationsPanel"),
    quality: document.getElementById("dspQualityPanel"),
  };
}


function loadQuality() {
  if (!qualityModulePromise) {
    qualityModulePromise = import("../dsp-quality/index.js?v=4");
  }
  return qualityModulePromise;
}


export async function activateDspArea(area, { focus = false } = {}) {
  const selected = area === "quality" ? "quality" : "operations";
  const nodes = refs();
  activeArea = selected;
  nodes.operations.hidden = selected !== "operations";
  nodes.quality.hidden = selected !== "quality";
  nodes.tabs.forEach((tab) => {
    const active = tab.dataset.dspArea === selected;
    tab.classList.toggle("active", active);
    tab.setAttribute("aria-selected", String(active));
    tab.tabIndex = active ? 0 : -1;
    if (active && focus) tab.focus();
  });
  if (selected === "quality") {
    const quality = await loadQuality();
    quality.initDspQuality();
  }
  return selected;
}


function onKeydown(event) {
  const current = event.target.closest("[data-dsp-area]");
  if (!current) return;
  const tabs = refs().tabs;
  const currentIndex = tabs.indexOf(current);
  let nextIndex = null;
  if (event.key === "ArrowRight") nextIndex = (currentIndex + 1) % tabs.length;
  if (event.key === "ArrowLeft") nextIndex = (currentIndex - 1 + tabs.length) % tabs.length;
  if (event.key === "Home") nextIndex = 0;
  if (event.key === "End") nextIndex = tabs.length - 1;
  if (nextIndex == null) return;
  event.preventDefault();
  void activateDspArea(tabs[nextIndex].dataset.dspArea, { focus: true });
}


export function initDspShell() {
  if (initialized) return;
  initialized = true;
  const nodes = refs();
  initDspWorkspace();
  nodes.root.addEventListener("click", (event) => {
    const tab = event.target.closest("[data-dsp-area]");
    if (tab) void activateDspArea(tab.dataset.dspArea);
  });
  nodes.root.addEventListener("keydown", onKeydown);
  void activateDspArea(activeArea);
}


export function prepareDspShellFirstPaint() {
  initDspShell();
  return activeArea === "operations" ? prepareDspFirstPaint() : Promise.resolve();
}
