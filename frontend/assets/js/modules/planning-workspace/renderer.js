import { formatPlanningDate, setNodeText } from "./utils.js";


function renderPlaceholder(refs, name, value) {
  setNodeText(refs[`${name}Value`], value.value);
  setNodeText(refs[`${name}Detail`], value.detail);
}


export function renderPlanningWorkspace(refs, view) {
  refs.root.dataset.planningWorkspaceState = view.state;
  refs.root.dataset.planningWorkspaceTone = view.tone;
  refs.root.setAttribute("aria-busy", String(view.loading));
  refs.loading.hidden = !view.loading;
  refs.content.hidden = view.loading;
  document.body.dataset.planningWorkspaceState = view.state;

  setNodeText(refs.badge, view.badge);
  setNodeText(refs.date, formatPlanningDate(view.planningDate));
  setNodeText(refs.unit, view.operationalUnit || "Tutte");
  setNodeText(refs.statusTitle, view.statusTitle);
  setNodeText(refs.statusDescription, view.statusDescription);
  renderPlaceholder(refs, "readiness", view.readiness);
  renderPlaceholder(refs, "conflicts", view.conflicts);
  renderPlaceholder(refs, "timeline", view.timeline);
  renderPlaceholder(refs, "draft", view.draft);
  renderPlaceholder(refs, "publication", view.publication);
  refs.confirmButton.disabled = !view.canConfirm;
}
