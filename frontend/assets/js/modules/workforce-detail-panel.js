import { byId, escapeHtml } from "../utils/dom.js";
import { workforceTimeLabel } from "./workforce-calendar-view.js";
import { createWorkforceSurface } from "./workforce-surface.js";
import { workforceStatusLabel } from "./workforce-view.js";


export function initWorkforceDetailPanel({ getStatuses }) {
  let selectedMember = null;

  function clearSelection() {
    byId("workforceDesk").dataset.detailOpen = "false";
    byId("workforceCalendar").querySelectorAll(".is-selected").forEach((element) => {
      element.classList.remove("is-selected");
    });
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

  function openStatus({ member, status, date, trigger }) {
    clearSelection();
    trigger.classList.add("is-selected");
    const form = byId("workforceStatusEditor");
    form.reset();
    byId("workforceDetailKind").textContent = "Stato giornaliero";
    byId("workforceDetailTitle").textContent = member.display_name;
    byId("workforceStatusId").value = status?.status_id || "";
    byId("workforceStatusMemberId").value = member.workforce_member_id;
    byId("workforceStatusDate").value = status?.date || date;
    byId("workforceStatusCode").value = status?.status_code || "unknown";
    byId("workforceShiftCode").value = status?.shift_code || "";
    byId("workforceStartTime").value = status?.start_time || "";
    byId("workforceEndTime").value = status?.end_time || "";
    byId("workforceStatusNotes").value = status?.notes || "";
    byId("workforceStatusTime").textContent = workforceTimeLabel(status) || "Non disponibile";
    byId("workforceStatusSource").textContent = status?.source_reference || "Non disponibile";
    form.hidden = false;
    byId("workforceDesk").dataset.detailOpen = "true";
    surface.show(byId("workforceStatusCode"));
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
    byId("workforceMemberRole").value = member.role || "";
    byId("workforceEmploymentType").value = member.employment_type || "";
    byId("workforceContractEnd").value = member.contract_end || "";
    byId("workforceWeeklyHours").value = member.weekly_hours ?? "";
    byId("workforceCapabilities").value = member.capabilities.join(", ");
  }

  function openMember(member, trigger) {
    clearSelection();
    selectedMember = member;
    trigger.classList.add("is-selected");
    byId("workforceDetailKind").textContent = "Profilo risorsa";
    byId("workforceDetailTitle").textContent = member.display_name;
    byId("workforceMemberDetailRole").textContent = member.role || "Non disponibile";
    byId("workforceMemberDetailContract").textContent = member.employment_type || "Non disponibile";
    byId("workforceMemberDetailCapabilities").textContent = member.capabilities.length
      ? member.capabilities.join(", ")
      : "Nessuna capability";
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

  return {
    close: surface.hide,
    openMember,
    openStatus,
  };
}
