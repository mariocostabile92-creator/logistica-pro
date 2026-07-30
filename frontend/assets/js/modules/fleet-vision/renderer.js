import { criticalitiesSection, operationsSection, quickAccessSection, snapshotSection } from "./sections.js";
import { fleetVisionState } from "./state.js";

export function renderFleetVisionExcellence(root) {
  const data = fleetVisionState.data;
  root.innerHTML = `<header class="fve2-hero"><div><p class="eyebrow">Fleet Operations</p>
    <h2 id="fleetVisionWorkspaceTitle">Fleet Vision Engine</h2>
    <p>Comprendi lo stato operativo della flotta, le priorità e la loro origine.</p></div>
    ${data.partialErrors.length ? `<p class="view-state">Dati parziali: ${data.partialErrors.join(", ")}</p>` : ""}</header>
    ${snapshotSection(data.summary)}
    ${criticalitiesSection()}
    ${operationsSection(data)}
    ${quickAccessSection()}`;
}
