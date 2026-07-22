import {
  createPlanningDraft,
  deletePlanningDraft,
  getCurrentPlanningDraft,
  getPlanningConflicts,
  getPlanningTimeline,
  restorePlanningDraft,
  savePlanningDraft,
  updatePlanningDraftMetadata,
} from "../../api.js";
import {
  createPlanningConflictLoader,
  normalizePlanningConflictResult,
} from "./conflicts.js";
import { createPlanningWorkspaceLayout } from "./layout.js";
import {
  readinessEventType,
} from "./readiness.js";
import { renderPlanningWorkspace } from "./renderer.js";
import {
  applyPlanningWorkspaceEvent,
  createPlanningWorkspaceState,
  derivePlanningWorkspaceView,
} from "./state.js";
import {
  createPlanningTimelineLoader,
  normalizePlanningTimelineResult,
} from "./timeline.js";
import {
  createPlanningDraftLoader,
  normalizePlanningDraftWorkspace,
} from "./draft.js";
import { focusRelativeAction } from "./utils.js";


let initialized = false;
let state;
let refs;
const conflictLoader = createPlanningConflictLoader(getPlanningConflicts);
const timelineLoader = createPlanningTimelineLoader(getPlanningTimeline);
const draftLoader = createPlanningDraftLoader(getCurrentPlanningDraft);


function today() {
  const now = new Date();
  const offset = now.getTimezoneOffset() * 60000;
  return new Date(now.getTime() - offset).toISOString().slice(0, 10);
}


function commit(event) {
  state = applyPlanningWorkspaceEvent(state, event);
  renderPlanningWorkspace(refs, derivePlanningWorkspaceView(state));
}


async function loadTimeline() {
  commit({ type: "timeline-load-started" });
  try {
    const payload = await timelineLoader.load({
      organizationId: "default",
      operationalUnitId: "default",
      planningDate: state.planningDate,
    });
    commit({
      type: "timeline-loaded",
      timeline: normalizePlanningTimelineResult(payload),
    });
  } catch (error) {
    if (error?.name === "AbortError") return;
    commit({
      type: "timeline-load-failed",
      message: error?.message || "Planning Timeline non disponibile. Riprova.",
    });
  }
}


async function loadDraft() {
  commit({ type: "draft-load-started" });
  try {
    const payload = await draftLoader.load({
      organizationId: "default",
      operationalUnitId: "default",
      planningDate: state.planningDate,
    });
    commit({
      type: "draft-loaded",
      draft: normalizePlanningDraftWorkspace(payload),
    });
  } catch (error) {
    if (error?.name === "AbortError") return;
    commit({
      type: "draft-load-failed",
      message: error?.message || "Planning Draft non disponibile. Riprova.",
    });
  }
}


async function loadConflictReview() {
  commit({ type: "load-started" });
  try {
    const payload = await conflictLoader.load({
      organizationId: "default",
      operationalUnitId: "default",
      planningDate: state.planningDate,
    });
    const { readiness, conflicts } = normalizePlanningConflictResult(payload);
    commit({
      type: readinessEventType(readiness.status),
      message: readiness.rationale,
      snapshot: { readiness, conflicts },
      operationalUnit: readiness.operationalUnit,
      planningDate: readiness.planningDate,
    });
    const supportingLoads = [loadTimeline()];
    if (!state.snapshot?.draft) supportingLoads.push(loadDraft());
    await Promise.all(supportingLoads);
  } catch (error) {
    if (error?.name === "AbortError") return;
    commit({
      type: "load-failed",
      message: error?.message || "Conflict Review non disponibile. Riprova.",
    });
  }
}


function currentDraft() {
  return state.snapshot?.draft || null;
}


async function runDraftMutation(operation, successMessage, focusTarget = null) {
  if (currentDraft()?.busy) return;
  commit({ type: "draft-mutation-started" });
  try {
    const payload = await operation();
    const draft = payload?.viewState
      ? payload
      : normalizePlanningDraftWorkspace(payload);
    commit({
      type: "draft-mutation-completed",
      draft,
      message: successMessage,
    });
    focusTarget?.()?.focus({ preventScroll: true });
  } catch (error) {
    if (error?.name === "AbortError") return;
    commit({
      type: "draft-mutation-failed",
      message: error?.message || "Operazione Draft non riuscita. Riprova.",
    });
  }
}


function createDraft() {
  const name = refs.draftNameInput.value.trim();
  if (!name) {
    refs.draftNameInput.focus();
    return;
  }
  const note = refs.draftNoteInput.value.trim();
  runDraftMutation(
    () => createPlanningDraft({
      organization_id: "default",
      operational_unit_id: "default",
      planning_date: state.planningDate,
      name,
      note: note || null,
    }),
    "Draft creato. Nessun effetto sul Planning operativo.",
    () => refs.draftNameInput,
  );
}


function saveDraft() {
  const workspace = currentDraft();
  const draft = workspace?.draft;
  const name = refs.draftNameInput.value.trim();
  if (!draft || !name) {
    refs.draftNameInput.focus();
    return;
  }
  const note = refs.draftNoteInput.value.trim();
  runDraftMutation(async () => {
    let current = workspace;
    const changes = {};
    if (name !== draft.name) changes.name = name;
    if (note !== draft.note) changes.note = note || null;
    if (Object.keys(changes).length) {
      current = normalizePlanningDraftWorkspace(
        await updatePlanningDraftMetadata(draft.id, {
          expected_version: draft.version.number,
          ...changes,
        }),
      );
    }
    if (["CREATED", "DIRTY"].includes(current.state)) {
      return savePlanningDraft(current.draft.id, {
        expected_version: current.draft.version.number,
      });
    }
    return current;
  }, "Draft salvato.", () => refs.draftSaveButton);
}


function restoreDraft() {
  const draft = currentDraft()?.draft;
  const targetVersion = Number(refs.draftRestoreSelect.value);
  if (!draft || !Number.isInteger(targetVersion)) return;
  runDraftMutation(
    () => restorePlanningDraft(draft.id, {
      expected_version: draft.version.number,
      target_version: targetVersion,
    }),
    `Versione ${targetVersion} ripristinata come nuova versione.`,
    () => refs.draftRestoreSelect,
  );
}


function confirmDeleteDraft() {
  const draft = currentDraft()?.draft;
  if (!draft) return;
  runDraftMutation(
    () => deletePlanningDraft(draft.id, draft.version.number),
    "Draft eliminato. La cronologia e stata conservata.",
    () => refs.draftNameInput,
  );
}


function updateDraftActionAvailability() {
  const workspace = currentDraft();
  const draft = workspace?.draft;
  const name = refs.draftNameInput.value.trim();
  const note = refs.draftNoteInput.value.trim();
  refs.draftCreateButton.disabled = workspace?.busy || !name;
  if (!draft || workspace?.state === "READ_ONLY") return;
  const changed = name !== draft.name || note !== draft.note;
  refs.draftSaveButton.disabled = workspace?.busy
    || !name
    || (workspace.state === "SAVED" && !changed);
}


function openLegacyFlow() {
  const legacy = document.getElementById("legacyOperationsRegion");
  const summary = document.getElementById("legacyOperationsSummary");
  legacy.open = true;
  refs.legacyButton.setAttribute("aria-expanded", "true");
  summary.focus({ preventScroll: true });
  legacy.scrollIntoView({ behavior: "smooth", block: "start" });
}


function handleActionClick(event) {
  const action = event.target.closest("[data-planning-action]")?.dataset
    .planningAction;
  if (action === "open-legacy") openLegacyFlow();
  if (action === "retry-conflicts") loadConflictReview();
  if (action === "retry-timeline") loadTimeline();
  if (action === "retry-draft") loadDraft();
  if (action === "create-draft") createDraft();
  if (action === "save-draft") saveDraft();
  if (action === "restore-draft") restoreDraft();
  if (action === "delete-draft") {
    refs.draftDeleteConfirm.hidden = false;
    refs.draftConfirmDeleteButton.focus();
  }
  if (action === "cancel-delete-draft") {
    refs.draftDeleteConfirm.hidden = true;
    refs.draftDeleteButton.focus();
  }
  if (action === "confirm-delete-draft") confirmDeleteDraft();
  if (action === "view-conflicts") {
    event.preventDefault();
    refs.conflictTitle.focus({ preventScroll: true });
    refs.conflictTitle.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}


function handleDraftKeydown(event) {
  if (event.key === "Escape" && !refs.draftDeleteConfirm.hidden) {
    event.preventDefault();
    refs.draftDeleteConfirm.hidden = true;
    refs.draftDeleteButton.focus();
    return;
  }
  if (event.key !== "Enter" || event.target !== refs.draftNameInput) return;
  event.preventDefault();
  const action = refs.draftCreateButton.hidden
    ? refs.draftSaveButton
    : refs.draftCreateButton;
  if (!action.disabled) action.click();
}


function handleActionKeydown(event) {
  if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
  event.preventDefault();
  if (event.key === "Home") {
    refs.actions.querySelector("button:not(:disabled)")?.focus();
    return;
  }
  if (event.key === "End") {
    const actions = refs.actions.querySelectorAll("button:not(:disabled)");
    actions[actions.length - 1]?.focus();
    return;
  }
  focusRelativeAction(
    refs.actions,
    event.target,
    event.key === "ArrowRight" ? 1 : -1,
  );
}


function handleLegacyKeydown(event) {
  if (event.key !== "Escape" || !event.currentTarget.open) return;
  event.currentTarget.open = false;
  refs.legacyButton.setAttribute("aria-expanded", "false");
  refs.legacyButton.focus();
}


export function initPlanningWorkspace() {
  if (initialized) return;
  initialized = true;
  const root = document.getElementById("planningWorkspaceRoot");
  state = createPlanningWorkspaceState({ planningDate: today() });
  refs = createPlanningWorkspaceLayout(root);
  renderPlanningWorkspace(refs, derivePlanningWorkspaceView(state));
  refs.root.addEventListener("click", handleActionClick);
  refs.draftEditor.addEventListener("submit", (event) => event.preventDefault());
  refs.draftEditor.addEventListener("input", updateDraftActionAvailability);
  refs.draftEditor.addEventListener("keydown", handleDraftKeydown);
  refs.actions.addEventListener("keydown", handleActionKeydown);
  document.getElementById("legacyOperationsRegion").addEventListener(
    "keydown",
    handleLegacyKeydown,
  );
  loadConflictReview();
}
