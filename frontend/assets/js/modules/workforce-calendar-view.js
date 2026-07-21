import { escapeHtml } from "../utils/dom.js";
import { workforceStatusLabel } from "./workforce-view.js";


function selectedDates(statuses, mode) {
  const dates = [...new Set(statuses.map((item) => item.date))].sort();
  if (mode === "day") return dates.slice(0, 1);
  if (mode === "week") return dates.slice(0, 7);
  return dates.slice(0, 14);
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


function statusButton(member, day, status) {
  const code = status?.status_code || "unknown";
  const label = workforceStatusLabel(code);
  const time = workforceTimeLabel(status);
  const primary = status?.shift_code || label;
  const secondary = [status?.shift_code ? label : "", time].filter(Boolean).join(" · ");
  const detail = [label, status?.shift_code, time].filter(Boolean).join(", ");
  return `
    <button
      type="button"
      class="workforce-status-button ${escapeHtml(code)}"
      data-workforce-status-id="${status?.status_id || ""}"
      data-workforce-member-id="${member.workforce_member_id}"
      data-workforce-date="${day}"
      aria-label="${escapeHtml(`${member.display_name}, ${day}, ${detail}`)}"
      title="${escapeHtml(detail)}"
    >
      <strong class="workforce-status-badge">${escapeHtml(primary)}</strong>
      ${secondary ? `<span>${escapeHtml(secondary)}</span>` : ""}
    </button>
  `;
}


function memberButton(member) {
  return `
    <button
      type="button"
      class="workforce-member-button"
      data-workforce-member-edit="${member.workforce_member_id}"
    >${escapeHtml(member.display_name)}</button>
    <small>${escapeHtml(resourceMeta(member))}</small>
  `;
}


function renderDayList(members, date, byKey) {
  return `
    <div class="workforce-day-list" role="list" aria-label="Planning del ${escapeHtml(date)}">
      ${members.map((member) => {
        const status = byKey.get(`${member.workforce_member_id}:${date}`);
        return `
          <article class="workforce-day-card" role="listitem">
            <div class="workforce-day-person">${memberButton(member)}</div>
            <div class="workforce-day-status">${statusButton(member, date, status)}</div>
          </article>
        `;
      }).join("")}
    </div>
  `;
}


function renderTable(members, dates, byKey) {
  return `
    <table class="workforce-calendar-table">
      <caption class="visually-hidden">Planning turni per risorsa e giornata</caption>
      <thead><tr>
        <th scope="col">Risorsa</th>
        ${dates.map((day) => `<th scope="col"><span>${escapeHtml(shortDate(day))}</span><small>${escapeHtml(day)}</small></th>`).join("")}
      </tr></thead>
      <tbody>
        ${members.map((member) => `
          <tr>
            <th scope="row">${memberButton(member)}</th>
            ${dates.map((day) => `
              <td class="workforce-calendar-cell">
                ${statusButton(member, day, byKey.get(`${member.workforce_member_id}:${day}`))}
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
) {
  const dates = selectedDates(statuses, mode);
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
    ? renderDayList(members, dates[0], byKey)
    : renderTable(members, dates, byKey);

  container.querySelectorAll("[data-workforce-member-id]").forEach((button) => {
    button.addEventListener("click", () => {
      const memberId = Number(button.dataset.workforceMemberId);
      const statusId = Number(button.dataset.workforceStatusId || 0);
      onEditStatus({
        member: members.find((item) => item.workforce_member_id === memberId),
        status: statusId ? statuses.find((item) => item.status_id === statusId) : null,
        date: button.dataset.workforceDate,
        trigger: button,
      });
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
}
