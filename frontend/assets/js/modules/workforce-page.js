import {
  confirmWorkforceImport,
  downloadWorkforceExport,
  getWorkforceCalendar,
  getWorkforceChanges,
  getWorkforceCoverage,
  getWorkforceStatus,
  listWorkforceMembers,
  previewWorkforceImport,
  saveWorkforceDayStatus,
  updateWorkforceMember,
} from "../api.js";
import { byId, renderViewState, setLoading, setMessage, showDataView } from "../utils/dom.js";
import { isExpectedApiError, userErrorPresentation } from "../utils/errors.js";
import {
  renderWorkforceCalendar,
  renderWorkforceImportPreview,
  renderWorkforceLists,
  renderWorkforceSummary,
  workforceSummary,
} from "./workforce-view.js";


let loaded = false;
let routedFile = null;
let importPreview = null;
let currentData = { members: [], statuses: [], coverage: [], changes: [] };
let viewMode = "week";


function selectedFile() {
  return byId("workforceFile").files[0] || routedFile;
}


function errorMessage(context, error) {
  const presentation = userErrorPresentation(context, error);
  setMessage(presentation.message, presentation.tone);
}


function openImport(file = null) {
  routedFile = file || routedFile;
  byId("workforceImportPanel").hidden = false;
  if (routedFile) {
    byId("workforceImportState").innerHTML = `
      <p class="import-notice ok"><strong>Planning turni riconosciuto.</strong>
      Il file selezionato e pronto per l'analisi Workforce.</p>
    `;
  }
  byId("workforceImportPanel").scrollIntoView({ behavior: "smooth", block: "start" });
}


function openStatusEditor({ member, status, date }) {
  const form = byId("workforceStatusEditor");
  form.reset();
  byId("workforceStatusId").value = status?.status_id || "";
  byId("workforceStatusMemberId").value = member.workforce_member_id;
  byId("workforceStatusDate").value = status?.date || date;
  byId("workforceStatusCode").value = status?.status_code || "unknown";
  byId("workforceShiftCode").value = status?.shift_code || "";
  byId("workforceStatusNotes").value = status?.notes || "";
  byId("workforceStatusEditorTitle").textContent = member.display_name;
  form.hidden = false;
  form.scrollIntoView({ behavior: "smooth", block: "nearest" });
}


function openMemberEditor(member) {
  const form = byId("workforceMemberEditor");
  form.reset();
  byId("workforceMemberId").value = member.workforce_member_id;
  byId("workforceMemberEditorTitle").textContent = member.display_name;
  byId("workforceMemberRole").value = member.role || "";
  byId("workforceEmploymentType").value = member.employment_type || "";
  byId("workforceContractEnd").value = member.contract_end || "";
  byId("workforceWeeklyHours").value = member.weekly_hours ?? "";
  byId("workforceCapabilities").value = member.capabilities.join(", ");
  form.hidden = false;
  form.scrollIntoView({ behavior: "smooth", block: "nearest" });
}


function renderData() {
  const { members, statuses, coverage, changes } = currentData;
  renderWorkforceSummary(workforceSummary(members, statuses, coverage));
  renderWorkforceCalendar(
    byId("workforceCalendar"),
    members,
    statuses,
    viewMode,
    openStatusEditor,
    openMemberEditor,
  );
  renderWorkforceLists(currentData);
}


async function refresh() {
  renderViewState(byId("workforceViewState"), {
    state: "loading",
    title: "Caricamento Workforce",
  });
  showDataView("workforceViewState", "workforceDataView", false);
  const dateFrom = byId("workforceDateFrom").value;
  const dateTo = byId("workforceDateTo").value;
  try {
    const [status, members, calendar, coverage, changes] = await Promise.all([
      getWorkforceStatus(),
      listWorkforceMembers(),
      getWorkforceCalendar(dateFrom, dateTo),
      getWorkforceCoverage(dateFrom, dateTo),
      getWorkforceChanges(),
    ]);
    currentData = {
      members: members.items,
      statuses: calendar.items,
      coverage: coverage.items,
      changes: changes.items,
    };
    byId("workforceTimestamp").textContent = status.latest_import
      ? `Ultimo import ${status.latest_import.imported_at}`
      : "Nessun import Workforce.";
    if (!members.items.length) {
      renderViewState(byId("workforceViewState"), {
        state: "empty",
        title: "Nessuna risorsa Workforce",
        description: "Importa il planning turni per creare calendario e disponibilita.",
        actionLabel: "Importa turni",
        action: "import-workforce",
        actionTone: "primary",
      });
      byId("workforceViewState").querySelector("[data-view-action]")
        ?.addEventListener("click", () => openImport());
    } else {
      showDataView("workforceViewState", "workforceDataView", true);
      renderData();
    }
    loaded = true;
  } catch (error) {
    const disabled = isExpectedApiError(error, { statuses: [404] });
    renderViewState(byId("workforceViewState"), {
      state: disabled ? "empty" : "error",
      title: disabled ? "Workforce non attivo" : "Workforce non disponibile",
      description: disabled
        ? "Il Plugin Workforce non e abilitato in questo ambiente."
        : "Non e stato possibile caricare il calendario.",
    });
    if (!disabled) errorMessage("workforce.load", error);
  }
}


async function analyzeImport() {
  const file = selectedFile();
  if (!file) {
    setMessage("Seleziona un file turni.", "warning");
    return;
  }
  setLoading(byId("workforceAnalyzeBtn"), true, "Analisi...");
  byId("workforceConfirmBtn").disabled = true;
  try {
    importPreview = await previewWorkforceImport(file);
    renderWorkforceImportPreview(importPreview);
    byId("workforceConfirmBtn").disabled = importPreview.people_detected === 0;
    setMessage("");
  } catch (error) {
    importPreview = null;
    byId("workforceImportState").innerHTML = '<p class="import-notice blocking">Analisi Workforce non riuscita.</p>';
    errorMessage("workforce.import-preview", error);
  } finally {
    setLoading(byId("workforceAnalyzeBtn"), false);
  }
}


async function confirmImport(event) {
  event.preventDefault();
  const file = selectedFile();
  if (!file || !importPreview) {
    setMessage("Analizza il file prima di confermare.", "warning");
    return;
  }
  if (document.body.dataset.workspaceState === "DEMO") {
    document.dispatchEvent(new CustomEvent("workspace:import-requested", {
      detail: { opener: byId("workforceConfirmBtn") },
    }));
    return;
  }
  setLoading(byId("workforceConfirmBtn"), true, "Import...");
  try {
    const result = await confirmWorkforceImport(file, importPreview.fingerprint);
    byId("workforceImportState").innerHTML = `
      <p class="import-notice ok"><strong>Workforce aggiornato.</strong>
      ${result.members_created} nuove risorse, ${result.statuses_created + result.statuses_updated} stati elaborati.</p>
    `;
    document.dispatchEvent(new CustomEvent("operations:data-imported", {
      detail: { datasetType: "workforce" },
    }));
    await refresh();
    setMessage("");
  } catch (error) {
    errorMessage("workforce.import", error);
  } finally {
    setLoading(byId("workforceConfirmBtn"), false);
    byId("workforceConfirmBtn").disabled = !importPreview;
  }
}


async function submitStatus(event) {
  event.preventDefault();
  const submit = event.submitter;
  setLoading(submit, true, "Salvataggio...");
  try {
    await saveWorkforceDayStatus(Number(byId("workforceStatusId").value || 0), {
      workforce_member_id: Number(byId("workforceStatusMemberId").value),
      date: byId("workforceStatusDate").value,
      status_code: byId("workforceStatusCode").value,
      shift_code: byId("workforceShiftCode").value.trim() || null,
      notes: byId("workforceStatusNotes").value.trim() || null,
      source_reference: "manual",
    });
    byId("workforceStatusEditor").hidden = true;
    await refresh();
    setMessage("Modifica Workforce registrata.", "ok");
  } catch (error) {
    errorMessage("workforce.save-status", error);
  } finally {
    setLoading(submit, false);
  }
}


async function submitMember(event) {
  event.preventDefault();
  const submit = event.submitter;
  setLoading(submit, true, "Salvataggio...");
  try {
    await updateWorkforceMember(Number(byId("workforceMemberId").value), {
      role: byId("workforceMemberRole").value.trim() || null,
      employment_type: byId("workforceEmploymentType").value.trim() || null,
      contract_end: byId("workforceContractEnd").value || null,
      weekly_hours: byId("workforceWeeklyHours").value
        ? Number(byId("workforceWeeklyHours").value)
        : null,
      capabilities: byId("workforceCapabilities").value
        .split(",").map((item) => item.trim()).filter(Boolean),
    });
    byId("workforceMemberEditor").hidden = true;
    await refresh();
    setMessage("Profilo Workforce aggiornato.", "ok");
  } catch (error) {
    errorMessage("workforce.save-member", error);
  } finally {
    setLoading(submit, false);
  }
}


export function initWorkforcePage() {
  byId("workforceImportToggle").addEventListener("click", () => openImport());
  byId("workforceImportClose").addEventListener("click", () => {
    byId("workforceImportPanel").hidden = true;
  });
  byId("workforceAnalyzeBtn").addEventListener("click", analyzeImport);
  byId("workforceImportForm").addEventListener("submit", confirmImport);
  byId("workforceRefreshBtn").addEventListener("click", refresh);
  byId("workforceExportBtn").addEventListener("click", async () => {
    try {
      await downloadWorkforceExport();
    } catch (error) {
      errorMessage("workforce.export", error);
    }
  });
  byId("workforceStatusEditor").addEventListener("submit", submitStatus);
  byId("workforceStatusCancel").addEventListener("click", () => {
    byId("workforceStatusEditor").hidden = true;
  });
  byId("workforceMemberEditor").addEventListener("submit", submitMember);
  byId("workforceMemberCancel").addEventListener("click", () => {
    byId("workforceMemberEditor").hidden = true;
  });
  document.querySelectorAll("[data-workforce-view-mode]").forEach((button) => {
    button.addEventListener("click", () => {
      viewMode = button.dataset.workforceViewMode;
      document.querySelectorAll("[data-workforce-view-mode]").forEach((item) => {
        item.classList.toggle("active", item === button);
      });
      renderData();
    });
  });
  document.addEventListener("workforce:import-requested", (event) => {
    document.dispatchEvent(new CustomEvent("workspace:navigate", {
      detail: { view: "workforce", targetId: "workforceImportPanel" },
    }));
    openImport(event.detail?.file || null);
    if (event.detail?.file) analyzeImport();
  });
  document.addEventListener("workspace:view-changed", (event) => {
    if (event.detail.view === "workforce" && !loaded) refresh();
  });
  document.addEventListener("workspace:reset-completed", () => {
    loaded = false;
    importPreview = null;
    routedFile = null;
    refresh();
  });
}
