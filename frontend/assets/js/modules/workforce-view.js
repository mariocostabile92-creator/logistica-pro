import { escapeHtml } from "../utils/dom.js";


const STATUS_LABELS = {
  available: "Disponibile",
  scheduled: "Programmato",
  rest: "Riposo",
  holiday: "Ferie",
  sickness: "Malattia",
  leave: "Permesso",
  unavailable: "Indisponibile",
  unknown: "Da verificare",
};


export function workforceStatusLabel(value) {
  return STATUS_LABELS[value] || value || "Non definito";
}


export function workforceSummary(members, statuses, coverage) {
  const available = statuses.filter((item) => item.availability).length;
  const scheduled = statuses.filter((item) => item.status_code === "scheduled").length;
  const absent = statuses.filter((item) => !item.availability).length;
  const margins = coverage
    .map((item) => item.margin)
    .filter((item) => Number.isFinite(item));
  return {
    members: members.length,
    available,
    scheduled,
    absent,
    margin: margins.length ? Math.min(...margins) : null,
  };
}


export function renderWorkforceSummary(summary) {
  document.getElementById("workforceMemberCount").textContent = summary.members;
  document.getElementById("workforceAvailableCount").textContent = summary.available;
  document.getElementById("workforceScheduledCount").textContent = summary.scheduled;
  document.getElementById("workforceAbsentCount").textContent = summary.absent;
  document.getElementById("workforceMarginValue").textContent = summary.margin ?? "--";
}


function selectedDates(statuses, mode) {
  const dates = [...new Set(statuses.map((item) => item.date))].sort();
  if (mode === "day") return dates.slice(0, 1);
  if (mode === "week") return dates.slice(0, 7);
  return dates.slice(0, 14);
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
  container.innerHTML = `
    <table class="workforce-calendar-table">
      <thead><tr>
        <th>Risorsa</th>
        ${dates.map((day) => `<th>${escapeHtml(day)}</th>`).join("")}
      </tr></thead>
      <tbody>
        ${members.map((member) => `
          <tr>
            <td>
              <strong>${escapeHtml(member.display_name)}</strong>
              <small>${escapeHtml(member.role || member.employment_type || "Risorsa")}</small>
              <button
                type="button"
                class="quiet"
                data-workforce-member-edit="${member.workforce_member_id}"
              >Modifica profilo</button>
            </td>
            ${dates.map((day) => {
              const status = byKey.get(`${member.workforce_member_id}:${day}`);
              const code = status?.status_code || "unknown";
              return `
                <td class="workforce-calendar-cell">
                  <button
                    type="button"
                    class="${escapeHtml(code)}"
                    data-workforce-status-id="${status?.status_id || ""}"
                    data-workforce-member-id="${member.workforce_member_id}"
                    data-workforce-date="${day}"
                  >
                    <strong>${escapeHtml(workforceStatusLabel(code))}</strong>
                    <small>${escapeHtml(status?.shift_code || "")}</small>
                  </button>
                </td>
              `;
            }).join("")}
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;
  container.querySelectorAll("[data-workforce-member-id]").forEach((button) => {
    button.addEventListener("click", () => {
      const statusId = Number(button.dataset.workforceStatusId || 0);
      onEditStatus({
        member: members.find((item) => item.workforce_member_id === Number(button.dataset.workforceMemberId)),
        status: statusId ? statuses.find((item) => item.status_id === statusId) : null,
        date: button.dataset.workforceDate,
      });
    });
  });
  container.querySelectorAll("[data-workforce-member-edit]").forEach((button) => {
    button.addEventListener("click", () => {
      onEditMember(members.find(
        (item) => item.workforce_member_id === Number(button.dataset.workforceMemberEdit),
      ));
    });
  });
}


export function renderWorkforceLists({ coverage, statuses, members, changes }) {
  const coverageEl = document.getElementById("workforceCoverage");
  coverageEl.innerHTML = coverage.length
    ? coverage.map((item) => `
        <div>
          <strong>${escapeHtml(item.date)} - ${escapeHtml(item.status)}</strong>
          <span>Richieste ${item.required ?? "--"}, disponibili ${item.available}, margine ${item.margin ?? "--"}</span>
        </div>
      `).join("")
    : '<div><strong>Fabbisogno non disponibile.</strong><span>Importalo o configurarlo prima di valutare il margine.</span></div>';

  const memberById = new Map(members.map((item) => [item.workforce_member_id, item]));
  const absences = statuses.filter((item) => !item.availability);
  document.getElementById("workforceAbsences").innerHTML = absences.length
    ? absences.slice(0, 12).map((item) => `
        <div><strong>${escapeHtml(memberById.get(item.workforce_member_id)?.display_name || "Risorsa")}</strong>
        <span>${escapeHtml(item.date)} - ${escapeHtml(workforceStatusLabel(item.status_code))}</span></div>
      `).join("")
    : '<div><strong>Nessuna assenza rilevata.</strong></div>';

  const contracts = members.filter((item) => item.contract_end || item.employment_type);
  document.getElementById("workforceContracts").innerHTML = contracts.length
    ? contracts.slice(0, 12).map((item) => `
        <div><strong>${escapeHtml(item.display_name)}</strong>
        <span>${escapeHtml(item.employment_type || "Contratto")} - scadenza ${escapeHtml(item.contract_end || "non disponibile")}</span></div>
      `).join("")
    : '<div><strong>Nessun contratto strutturato disponibile.</strong></div>';

  document.getElementById("workforceChanges").innerHTML = changes.length
    ? changes.slice(0, 12).map((item) => `
        <div><strong>${escapeHtml(item.reason)}</strong>
        <span>${escapeHtml(item.timestamp)} - ${escapeHtml(item.source)}</span></div>
      `).join("")
    : '<div><strong>Nessuna modifica registrata.</strong></div>';
}


export function renderWorkforceImportPreview(preview) {
  document.getElementById("workforceImportState").innerHTML = `
    <p class="import-notice ok"><strong>Planning turni riconosciuto.</strong>
    ${preview.people_detected} persone, ${preview.date_from || "date non rilevate"} - ${preview.date_to || "--"}.
    ${preview.confirmation_columns.length} colonne da confermare; ${preview.excluded_rows} righe escluse.</p>
  `;
  document.getElementById("workforceSheetRoles").innerHTML = preview.sheets.map((sheet) => `
    <div class="workforce-sheet-role">
      <strong>${escapeHtml(sheet.name)}</strong>
      <span>${escapeHtml(sheet.responsibility)} - ${sheet.importable_rows} righe</span>
    </div>
  `).join("");
  const matrix = preview.matrix;
  if (!matrix.length) {
    document.getElementById("workforceMatrixPreview").innerHTML = '<p>Nessuna matrice calendario disponibile nel campione.</p>';
    return;
  }
  const columns = Object.keys(matrix[0]);
  document.getElementById("workforceMatrixPreview").innerHTML = `
    <table><thead><tr>${columns.map((item) => `<th>${escapeHtml(item)}</th>`).join("")}</tr></thead>
    <tbody>${matrix.map((row) => `<tr>${columns.map((item) => `<td>${escapeHtml(row[item])}</td>`).join("")}</tr>`).join("")}</tbody></table>
  `;
}
