import { byId, escapeHtml } from "../utils/dom.js";
import { workforceTimeLabel } from "./workforce-calendar-view.js";
import { createWorkforceSurface } from "./workforce-surface.js";
import { workforceStatusLabel } from "./workforce-view.js";


function readableDate(value) {
  return new Intl.DateTimeFormat("it-IT", {
    weekday: "short",
    day: "2-digit",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${value}T00:00:00Z`));
}


export function initWorkforceDetailPanel({ getStatuses, onSelectionCleared = () => {} }) {
  let selectedMember = null;
  let preserveSelectionOnClose = false;

  function clearSelection() {
    byId("workforceDesk").dataset.detailOpen = "false";
    if (!preserveSelectionOnClose) {
      byId("workforceCalendar").querySelectorAll(".is-selected").forEach((element) => {
        element.classList.remove("is-selected");
        element.setAttribute("aria-pressed", "false");
      });
      onSelectionCleared();
    }
    preserveSelectionOnClose = false;
    byId("workforceStatusEditor").hidden = true;
    byId("workforceMemberDetail").hidden = true;
    byId("workforceMemberEditor").hidden = true;
    selectedMember = null;
  }

  const surface = createWorkforceSurface({
    surface: byId("workforceDetailPanel"),
    backdrop: byId("workforceDetailBackdrop"),
    onClose: clearSelection,
  });

  function populateShiftOptions(currentShift) {
    const shifts = [...new Set(
      getStatuses().map((item) => item.shift_code).filter(Boolean),
    )].sort((left, right) => left.localeCompare(right, "it"));
    if (currentShift && !shifts.includes(currentShift)) shifts.unshift(currentShift);
    const list = byId("workforceShiftOptions");
    list.replaceChildren(...shifts.map((shift) => {
      const option = document.createElement("option");
      option.value = shift;
      option.label = shift.replace(/[_-]+/g, " ").toLocaleLowerCase("it")
        .replace(/\b\p{L}/gu, (letter) => letter.toLocaleUpperCase("it"));
      return option;
    }));
  }

  function selectStatusChoice(code) {
    const choices = [...document.querySelectorAll('[name="workforceStatusCode"]')];
    const selected = choices.find((choice) => choice.value === code)
      || choices.find((choice) => choice.value === "unknown");
    if (selected) selected.checked = true;
    return selected;
  }

  function openStatus({ member, status, date, trigger }) {
    preserveSelectionOnClose = true;
    clearSelection();
    trigger.classList.add("is-selected");
    trigger.setAttribute("aria-pressed", "true");
    const form = byId("workforceStatusEditor");
    form.reset();
    byId("workforceDetailKind").textContent = "Planning turni";
    byId("workforceDetailTitle").textContent = "Modifica turno";
    byId("workforceStatusId").value = status?.status_id || "";
    byId("workforceStatusMemberId").value = member.workforce_member_id;
    byId("workforceStatusDate").value = status?.date || date;
    byId("workforceStatusPerson").textContent = member.display_name;
    byId("workforceStatusDateLabel").textContent = readableDate(status?.date || date);
    const selectedChoice = selectStatusChoice(status?.status_code || "unknown");
    byId("workforceShiftCode").value = status?.shift_code || "";
    populateShiftOptions(status?.shift_code || "");
    byId("workforceStartTime").value = status?.start_time || "";
    byId("workforceEndTime").value = status?.end_time || "";
    byId("workforceStatusNotes").value = status?.notes || "";
    form.hidden = false;
    byId("workforceDesk").dataset.detailOpen = "true";
    surface.show(selectedChoice);
  }

  function recentMemberHistory(memberId) {
    return getStatuses()
      .filter((item) => item.workforce_member_id === memberId)
      .sort((left, right) => right.date.localeCompare(left.date))
      .slice(0, 5);
  }

  function populateMemberEditor(member) {
    const form = byId("workforceMemberEditor");
    form.reset();
    byId("workforceMemberId").value = member.workforce_member_id;
    byId("workforceMemberEditorTitle").textContent = member.display_name;
    byId("workforceMemberFirstName").value = member.first_name || "";
    byId("workforceMemberLastName").value = member.last_name || "";
    byId("workforceMemberRole").value = member.role || "";
    byId("workforceMemberStation").value = member.station || "";
    byId("workforceEmploymentType").value = member.employment_type || "";
    byId("workforceContractEnd").value = member.contract_end || "";
    byId("workforceWeeklyHours").value = member.weekly_hours ?? "";
    byId("workforceCapabilities").value = member.capabilities.join(", ");
    byId("workforceMemberOperationalNotes").value = member.operational_notes || "";
    byId("workforceMemberReserve").checked = Boolean(member.is_reserve);
  }

  function openMember(member, trigger) {
    clearSelection();
    selectedMember = member;
    trigger.classList.add("is-selected");
    byId("workforceDetailKind").textContent = "Profilo risorsa";
    byId("workforceDetailTitle").textContent = member.display_name;
    byId("workforceMemberDetailId").textContent = member.external_identifier;
    byId("workforceMemberDetailRole").textContent = member.role || "Non disponibile";
    byId("workforceMemberDetailStation").textContent = member.station || "Non disponibile";
    byId("workforceMemberDetailContract").textContent = member.employment_type || "Non disponibile";
    byId("workforceMemberDetailCapabilities").textContent = member.capabilities.length
      ? member.capabilities.join(", ")
      : "Nessuna capability";
    byId("workforceMemberDetailNotes").textContent = member.operational_notes || "Nessuna nota";
    byId("workforceMemberDetailReserve").textContent = member.is_reserve ? "Si" : "No";
    const history = recentMemberHistory(member.workforce_member_id);
    byId("workforceMemberHistory").innerHTML = history.length
      ? history.map((item) => `
          <div>
            <strong>${escapeHtml(item.date)} - ${escapeHtml(workforceStatusLabel(item.status_code))}</strong>
            <span>${escapeHtml(item.shift_code || workforceTimeLabel(item) || "Nessun turno")}</span>
          </div>
        `).join("")
      : '<div><strong>Nessuno storico nel periodo.</strong></div>';
    populateMemberEditor(member);
    byId("workforceMemberDetail").hidden = false;
    byId("workforceMemberEditor").hidden = true;
    byId("workforceDesk").dataset.detailOpen = "true";
    surface.show(byId("workforceMemberEditBtn"));
  }

  byId("workforceDetailClose").addEventListener("click", surface.requestClose);
  byId("workforceStatusCancel").addEventListener("click", surface.requestClose);
  byId("workforceMemberCancel").addEventListener("click", () => {
    byId("workforceMemberEditor").hidden = true;
    byId("workforceMemberDetail").hidden = false;
    byId("workforceMemberEditBtn").focus();
  });
  byId("workforceMemberEditBtn").addEventListener("click", () => {
    if (!selectedMember) return;
    byId("workforceMemberDetail").hidden = true;
    byId("workforceMemberEditor").hidden = false;
    byId("workforceMemberRole").focus();
  });
  byId("workforceStatusEditor").addEventListener("keydown", (event) => {
    if (event.key !== "Enter" || event.repeat || event.isComposing) return;
    if (event.target.closest("button")) return;
    event.preventDefault();
    byId("workforceStatusEditor").requestSubmit(byId("workforceStatusSave"));
  });

  return {
    close: surface.hide,
    completeStatusSave() {
      preserveSelectionOnClose = true;
      surface.hide({ restoreFocus: false });
    },
    openMember,
    openStatus,
  };
}
