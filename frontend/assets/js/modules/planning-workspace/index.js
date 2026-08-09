import {
  confirmPlanningConfirmation,
  createPlanningDraft,
  deletePlanningDraft,
  getCurrentPlanningDraft,
  getCurrentPlanningConfirmation,
  getCurrentPlanningPublication,
  getPlanningConflicts,
  getPlanningTimeline,
  restorePlanningDraft,
  savePlanningDraft,
  publishPlanningPublication,
  updatePlanningDraftMetadata,
  validatePlanningConfirmation,
  validatePlanningPublication,
} from "../../api.js?v=5";
import {
  createPlanningConfirmationLoader,
  normalizePlanningConfirmationReport,
} from "./confirmation.js";
import {
  createPlanningPublicationLoader,
  normalizePlanningPublicationReport,
} from "./publication.js";
import {
  createPlanningConflictLoader,
  normalizePlanningConflictResult,
} from "./conflicts.js";
import { createPlanningWorkspaceLayout } from "./layout.js?v=5";
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
let firstPaintPromise = null;
let state;
let refs;
const conflictLoader = createPlanningConflictLoader(getPlanningConflicts);
const timelineLoader = createPlanningTimelineLoader(getPlanningTimeline);
const draftLoader = createPlanningDraftLoader(getCurrentPlanningDraft);
const confirmationLoader = createPlanningConfirmationLoader(
  getCurrentPlanningConfirmation,
);
const publicationLoader = createPlanningPublicationLoader(
  getCurrentPlanningPublication,
);


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
      message: error?.message || "Cronologia del piano non disponibile. Riprova.",
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
      message: error?.message || "Bozza di pianificazione non disponibile. Riprova.",
    });
  }
}


async function loadConfirmation({ force = false } = {}) {
  commit({ type: "confirmation-load-started" });
  try {
    const payload = await confirmationLoader.load(
      {
        organizationId: "default",
        operationalUnitId: "default",
        planningDate: state.planningDate,
      },
      { force },
    );
    commit({
      type: "confirmation-loaded",
      confirmation: normalizePlanningConfirmationReport(payload),
    });
  } catch (error) {
    if (error?.name === "AbortError") return;
    commit({
      type: "confirmation-load-failed",
      message: error?.message || "Conferma del piano non disponibile. Riprova.",
    });
  }
}


async function loadPublication({ force = false } = {}) {
  commit({ type: "publication-load-started" });
  try {
    const payload = await publicationLoader.load(
      {
        organizationId: "default",
        operationalUnitId: "default",
        planningDate: state.planningDate,
      },
      { force },
    );
    commit({
      type: "publication-loaded",
      publication: normalizePlanningPublicationReport(payload),
    });
  } catch (error) {
    if (error?.name === "AbortError") return;
    commit({
      type: "publication-load-failed",
      message: error?.message || "Pubblicazione del piano non disponibile. Riprova.",
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
    if (!state.snapshot?.confirmation) supportingLoads.push(loadConfirmation());
    if (!state.snapshot?.publication) supportingLoads.push(loadPublication());
    await Promise.all(supportingLoads);
  } catch (error) {
    if (error?.name === "AbortError") return;
    commit({
      type: "load-failed",
      message: error?.message || "Verifica conflitti non disponibile. Riprova.",
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
    await loadConfirmation({ force: true });
    focusTarget?.()?.focus({ preventScroll: true });
  } catch (error) {
    if (error?.name === "AbortError") return;
    commit({
      type: "draft-mutation-failed",
      message: error?.message || "Operazione sulla bozza non riuscita. Riprova.",
    });
  }
}


function currentConfirmation() {
  return state.snapshot?.confirmation || null;
}


function confirmationPayload() {
  const draft = currentDraft()?.draft;
  if (!draft) return null;
  return {
    organization_id: "default",
    operational_unit_id: "default",
    planning_date: state.planningDate,
    draft_id: draft.id,
    draft_version: draft.version.number,
  };
}


async function runConfirmationMutation(operation, successMessage) {
  if (currentConfirmation()?.busy) return;
  commit({ type: "confirmation-mutation-started" });
  try {
    const payload = await operation();
    const confirmation = normalizePlanningConfirmationReport(payload);
    commit({
      type: "confirmation-mutation-completed",
      confirmation,
      message: successMessage,
    });
    await loadPublication({ force: true });
    const focusTarget = refs.confirmationBeginButton.disabled
      ? refs.confirmationBody
      : refs.confirmationBeginButton;
    focusTarget.focus({ preventScroll: true });
  } catch (error) {
    if (error?.name === "AbortError") return;
    commit({
      type: "confirmation-mutation-failed",
      message: error?.message || "Operazione di conferma non riuscita. Riprova.",
    });
  }
}


function currentPublication() {
  return state.snapshot?.publication || null;
}


function publicationPayload() {
  const confirmation = currentConfirmation()?.current;
  if (!confirmation) return null;
  return {
    organization_id: "default",
    operational_unit_id: "default",
    planning_date: state.planningDate,
    confirmation_id: confirmation.id,
    confirmation_version: confirmation.version,
    confirmation_fingerprint: confirmation.fingerprint,
  };
}


async function runPublicationMutation(operation, successMessage) {
  if (currentPublication()?.busy) return;
  commit({ type: "publication-mutation-started" });
  try {
    const payload = await operation();
    const publication = normalizePlanningPublicationReport(payload);
    commit({
      type: "publication-mutation-completed",
      publication,
      message: successMessage,
    });
    const focusTarget = refs.publicationBeginButton.disabled
      ? refs.publicationBody
      : refs.publicationBeginButton;
    focusTarget.focus({ preventScroll: true });
  } catch (error) {
    if (error?.name === "AbortError") return;
    commit({
      type: "publication-mutation-failed",
      message: error?.message || "Operazione di pubblicazione non riuscita. Riprova.",
    });
  }
}


function validatePublication() {
  const payload = publicationPayload();
  if (!payload) {
    loadPublication();
    return;
  }
  runPublicationMutation(
    () => validatePlanningPublication(payload),
    "Verifica della pubblicazione aggiornata.",
  );
}


function publishNow() {
  const payload = publicationPayload();
  if (!payload) return;
  runPublicationMutation(
    () => publishPlanningPublication(payload),
    "Piano confermato pubblicato. Nessuna esecuzione avviata.",
  );
}


function validateConfirmation() {
  const payload = confirmationPayload();
  if (!payload) {
    loadConfirmation();
    return;
  }
  runConfirmationMutation(
    () => validatePlanningConfirmation(payload),
    "Verifica della conferma aggiornata.",
  );
}


function confirmNow() {
  const payload = confirmationPayload();
  if (!payload) return;
  runConfirmationMutation(
    () => confirmPlanningConfirmation(payload),
    "Bozza resa immutabile come piano confermato. Nessuna pubblicazione eseguita.",
  );
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
    "Bozza creata. Nessun effetto sul piano operativo.",
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
  }, "Bozza salvata.", () => refs.draftSaveButton);
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
    "Bozza eliminata. La cronologia è stata conservata.",
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
  if (action === "retry-confirmation") loadConfirmation();
  if (action === "retry-publication") loadPublication();
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
  if (action === "validate-confirmation") validateConfirmation();
  if (action === "begin-confirmation") {
    refs.confirmationExplicit.hidden = false;
    refs.confirmationConfirmButton.focus();
  }
  if (action === "cancel-confirmation") {
    refs.confirmationExplicit.hidden = true;
    refs.confirmationBeginButton.focus();
  }
  if (action === "confirm-now") confirmNow();
  if (action === "validate-publication") validatePublication();
  if (action === "begin-publication") {
    refs.publicationExplicit.hidden = false;
    refs.publicationPublishButton.focus();
  }
  if (action === "cancel-publication") {
    refs.publicationExplicit.hidden = true;
    refs.publicationBeginButton.focus();
  }
  if (action === "publish-now") publishNow();
  if (action === "view-conflicts") {
    event.preventDefault();
    refs.conflictTitle.focus({ preventScroll: true });
    refs.conflictTitle.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}


function handleConfirmationKeydown(event) {
  if (event.key !== "Escape" || refs.confirmationExplicit.hidden) return;
  event.preventDefault();
  refs.confirmationExplicit.hidden = true;
  refs.confirmationBeginButton.focus();
}


function handlePublicationKeydown(event) {
  if (event.key !== "Escape" || refs.publicationExplicit.hidden) return;
  event.preventDefault();
  refs.publicationExplicit.hidden = true;
  refs.publicationBeginButton.focus();
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


export async function openPlanningDate(planningDate) {
  const normalized = String(planningDate || "");
  if (!initialized || !/^\d{4}-\d{2}-\d{2}$/.test(normalized)) return false;
  commit({ type: "load-started", planningDate: normalized });
  const diagnostics = refs.root.querySelector(".planning-advanced-diagnostics");
  diagnostics.dataset.loaded = "true";
  diagnostics.open = true;
  await loadConflictReview();
  refs.root.querySelector("[data-planning-role='date']")
    ?.scrollIntoView({ block: "center", inline: "nearest" });
  return true;
}


export function initPlanningWorkspace() {
  if (initialized) return firstPaintPromise || Promise.resolve();
  initialized = true;
  const root = document.getElementById("planningWorkspaceRoot");
  state = createPlanningWorkspaceState({ planningDate: today() });
  refs = createPlanningWorkspaceLayout(root);
  renderPlanningWorkspace(refs, derivePlanningWorkspaceView(state));
  refs.root.addEventListener("click", handleActionClick);
  refs.draftEditor.addEventListener("submit", (event) => event.preventDefault());
  refs.draftEditor.addEventListener("input", updateDraftActionAvailability);
  refs.draftEditor.addEventListener("keydown", handleDraftKeydown);
  refs.confirmationBody.addEventListener("keydown", handleConfirmationKeydown);
  refs.publicationBody.addEventListener("keydown", handlePublicationKeydown);
  refs.actions.addEventListener("keydown", handleActionKeydown);
  document.getElementById("legacyOperationsRegion").addEventListener(
    "keydown",
    handleLegacyKeydown,
  );
  const diagnostics = refs.root.querySelector(".planning-advanced-diagnostics");
  diagnostics?.addEventListener("toggle", () => {
    if (diagnostics.open && !diagnostics.dataset.loaded) {
      diagnostics.dataset.loaded = "true";
      loadConflictReview();
    }
  });
  document.addEventListener("planning:open-date", (event) => {
    void openPlanningDate(event.detail?.operationDate);
  });
  firstPaintPromise = Promise.resolve(refs.operationsReady);
  return firstPaintPromise;
}
