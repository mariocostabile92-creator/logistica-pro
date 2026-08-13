import { escapeHtml } from "../utils/dom.js";
import { workforceStatusLabel } from "./workforce-view.js";


function statusDates(statuses, mode) {
  const dates = [...new Set(statuses.map((item) => item.date))].sort();
  if (mode === "day") return dates.slice(0, 1);
  if (mode === "week") return dates.slice(0, 7);
  return dates.slice(0, 14);
}


function addDays(value, days) {
  const parsed = new Date(`${value}T00:00:00Z`);
  parsed.setUTCDate(parsed.getUTCDate() + days);
  return parsed.toISOString().slice(0, 10);
}


export function workforceCalendarDates(statuses, mode, dateFrom = "", dateTo = "") {
  if (!dateFrom) return statusDates(statuses, mode);
  if (mode === "day") return [dateFrom];
  const maximum = mode === "week" ? 7 : 14;
  const dates = [];
  for (let offset = 0; offset < maximum; offset += 1) {
    const value = addDays(dateFrom, offset);
    if (mode !== "week" && dateTo && value > dateTo) break;
    dates.push(value);
  }
  return dates;
}


function shortDate(value) {
  const parsed = new Date(`${value}T00:00:00Z`);
  return new Intl.DateTimeFormat("it-IT", {
    weekday: "short",
    day: "2-digit",
    month: "short",
    timeZone: "UTC",
  }).format(parsed);
}


export function workforceCellKey(memberId, date) {
  return `${memberId}:${date}`;
}


export function nextWorkforceCellPosition(
  { row, column },
  key,
  rowCount,
  columnCount,
) {
  const position = { row, column };
  if (key === "ArrowUp") position.row = Math.max(0, row - 1);
  if (key === "ArrowDown") position.row = Math.min(rowCount - 1, row + 1);
  if (key === "ArrowLeft") position.column = Math.max(0, column - 1);
  if (key === "ArrowRight") position.column = Math.min(columnCount - 1, column + 1);
  return position;
}


export function workforceTimeLabel(status) {
  if (!status?.start_time && !status?.end_time) return "";
  if (status.start_time && status.end_time) return `${status.start_time}–${status.end_time}`;
  return status.start_time || status.end_time;
}


function resourceMeta(member) {
  return [member.role || member.employment_type, member.capabilities?.[0]]
    .filter(Boolean)
    .join(" - ") || "Risorsa";
}


function statusButton(
  member,
  day,
  status,
  rowIndex,
  columnIndex,
  selectedCellKey,
  editingMemberId,
  multiDayDates,
) {
  const code = status?.status_code || "unknown";
  const label = workforceStatusLabel(code);
  const time = workforceTimeLabel(status);
  const primary = status?.shift_code || label;
  const activity = status?.operational_activity || "";
  const secondary = [status?.shift_code ? label : "", time].filter(Boolean).join(" · ");
  const detail = [label, status?.shift_code, time].filter(Boolean).join(", ");
  const key = workforceCellKey(member.workforce_member_id, day);
  const selected = key === selectedCellKey;
  const multiSelected = editingMemberId === member.workforce_member_id && multiDayDates.has(day);
  const editing = editingMemberId === member.workforce_member_id;
  const locked = Boolean(editingMemberId) && !editing;
  return `
    <button
      type="button"
      class="workforce-status-button ${escapeHtml(code)}${selected ? " is-selected" : ""}${multiSelected ? " is-multi-selected" : ""}${editing ? " is-editing" : ""}${locked ? " is-locked" : ""}"
      data-workforce-status-id="${status?.status_id || ""}"
      data-workforce-member-id="${member.workforce_member_id}"
      data-workforce-date="${day}"
      data-workforce-cell-key="${escapeHtml(key)}"
      data-workforce-row="${rowIndex}"
      data-workforce-column="${columnIndex}"
      aria-pressed="${multiSelected || selected}"
      aria-disabled="${locked}"
      aria-label="${escapeHtml(`${member.display_name}, ${day}, ${detail}`)}"
      title="${escapeHtml(detail)}"
    >
      <strong class="workforce-status-badge">${escapeHtml(primary)}</strong>
      ${secondary ? `<span>${escapeHtml(secondary)}</span>` : ""}
      ${activity ? `<small class="workforce-operational-activity">${escapeHtml(activity)}</small>` : ""}
    </button>
  `;
}


function memberButton(member) {
  const cycle = member.operational_cycle || "NOT_SET";
  return `
    <button type="button" class="workforce-member-button" data-workforce-member-edit="${member.workforce_member_id}">${escapeHtml(member.display_name)}</button>
    <small>${escapeHtml(resourceMeta(member))}</small>
    <span class="workforce-planning-cycle-badge is-${escapeHtml(cycle.toLowerCase().replaceAll("_", "-"))}">${escapeHtml(operationalCyclePlanningLabel(cycle))}</span>
    ${cycle === "NOT_SET" ? `<button type="button" class="workforce-complete-profile" data-workforce-member-edit="${member.workforce_member_id}">Completa anagrafica</button>` : ""}
    <button type="button" class="workforce-member-schedule" data-workforce-member-schedule="${member.workforce_member_id}">Modifica turni</button>
  `;
}

export function operationalCyclePlanningLabel(value) {
  return ({ NEXT_DAY: "NEXT DAY", SAME_DAY: "SAME DAY", NOT_SET: "CICLO NON IMPOSTATO" })[value]
    || "CICLO NON IMPOSTATO";
}


function renderDayList(members, date, byKey, selectedCellKey, editingMemberId, multiDayDates) {
  return `
    <div class="workforce-day-list" role="list" aria-label="Planning del ${escapeHtml(date)}">
      ${members.map((member, rowIndex) => {
        const status = byKey.get(`${member.workforce_member_id}:${date}`);
        return `
          <article class="workforce-day-card" role="listitem">
            <div class="workforce-day-person">${memberButton(member)}</div>
            <div class="workforce-day-status">${statusButton(member, date, status, rowIndex, 0, selectedCellKey, editingMemberId, multiDayDates)}</div>
          </article>
        `;
      }).join("")}
    </div>
  `;
}


function renderTable(members, dates, byKey, selectedCellKey, editingMemberId, multiDayDates) {
  return `
    <table class="workforce-calendar-table">
      <caption class="visually-hidden">Planning turni per risorsa e giornata</caption>
      <thead><tr>
        <th scope="col">Risorsa</th>
        ${dates.map((day) => `<th scope="col"><span>${escapeHtml(shortDate(day))}</span><small>${escapeHtml(day)}</small></th>`).join("")}
      </tr></thead>
      <tbody>
        ${members.map((member, rowIndex) => `
          <tr>
            <th scope="row">${memberButton(member)}</th>
            ${dates.map((day, columnIndex) => `
              <td class="workforce-calendar-cell">
                ${statusButton(
                  member,
                  day,
                  byKey.get(`${member.workforce_member_id}:${day}`),
                  rowIndex,
                  columnIndex,
                  selectedCellKey,
                  editingMemberId,
                  multiDayDates,
                )}
              </td>
            `).join("")}
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;
}


export function renderWorkforceCalendar(
  container,
  members,
  statuses,
  mode,
  onEditStatus,
  onEditMember,
  {
    selectedCellKey = null,
    onSelectCell = () => {},
    dateFrom = "",
    dateTo = "",
    editingMemberId = null,
    multiDayDates = new Set(),
    onStartMultiDayEdit = () => {},
    onToggleMultiDayDate = () => {},
  } = {},
) {
  const dates = workforceCalendarDates(statuses, mode, dateFrom, dateTo);
  if (!members.length) {
    container.innerHTML = '<p class="empty-state">Nessuna risorsa Workforce disponibile.</p>';
    return;
  }
  if (!dates.length) {
    container.innerHTML = '<p class="empty-state">Nessun turno disponibile nel periodo selezionato.</p>';
    return;
  }
  const byKey = new Map(
    statuses.map((item) => [`${item.workforce_member_id}:${item.date}`, item]),
  );
  container.innerHTML = mode === "day"
    ? renderDayList(members, dates[0], byKey, selectedCellKey, editingMemberId, multiDayDates)
    : renderTable(members, dates, byKey, selectedCellKey, editingMemberId, multiDayDates);

  const statusButtons = [...container.querySelectorAll("[data-workforce-member-id]")];
  const markSelected = (button) => {
    statusButtons.forEach((item) => {
      const selected = item === button;
      item.classList.toggle("is-selected", selected);
      item.setAttribute("aria-pressed", String(selected));
    });
    onSelectCell(button.dataset.workforceCellKey);
  };

  statusButtons.forEach((button) => {
    button.addEventListener("click", (event) => {
      const memberId = Number(button.dataset.workforceMemberId);
      if (editingMemberId) {
        if (memberId !== Number(editingMemberId)) return;
        onToggleMultiDayDate({
          member: members.find((item) => item.workforce_member_id === memberId),
          date: button.dataset.workforceDate,
          shiftKey: event.shiftKey,
          visibleDates: dates,
          trigger: button,
        });
        return;
      }
      markSelected(button);
      const statusId = Number(button.dataset.workforceStatusId || 0);
      onEditStatus({
        member: members.find((item) => item.workforce_member_id === memberId),
        status: statusId ? statuses.find((item) => item.status_id === statusId) : null,
        date: button.dataset.workforceDate,
        trigger: button,
      });
    });
    button.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        button.click();
        return;
      }
      if (!["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"].includes(event.key)) return;
      event.preventDefault();
      const next = nextWorkforceCellPosition(
        {
          row: Number(button.dataset.workforceRow),
          column: Number(button.dataset.workforceColumn),
        },
        event.key,
        members.length,
        dates.length,
      );
      const target = statusButtons.find((item) => (
        Number(item.dataset.workforceRow) === next.row
        && Number(item.dataset.workforceColumn) === next.column
      ));
      if (!target || target === button) return;
      markSelected(target);
      target.focus({ preventScroll: true });
      target.scrollIntoView({ block: "nearest", inline: "nearest" });
    });
  });
  container.querySelectorAll("[data-workforce-member-edit]").forEach((button) => {
    button.addEventListener("click", () => {
      onEditMember(
        members.find((item) => item.workforce_member_id === Number(button.dataset.workforceMemberEdit)),
        button,
      );
    });
  });
  container.querySelectorAll("[data-workforce-member-schedule]").forEach((button) => {
    button.addEventListener("click", () => {
      onStartMultiDayEdit(
        members.find((item) => item.workforce_member_id === Number(button.dataset.workforceMemberSchedule)),
        button,
      );
    });
  });
}
