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

const COVERAGE_LABELS = {
  covered: "Copertura adeguata",
  surplus: "Margine disponibile",
  deficit: "Copertura insufficiente",
  requirement_unavailable: "Fabbisogno non disponibile",
};

const SHEET_ROLE_LABELS = {
  schedule: "Turni e disponibilita",
  members: "Anagrafiche",
  contracts: "Contratti",
  requirements: "Fabbisogno",
  ignored: "Non importato",
};

const CHANGE_LABELS = {
  workforce_import: "Dato importato",
  workforce_import_update: "Dato aggiornato da import",
  manual_update: "Modifica manuale",
};


function integer(value) {
  return new Intl.NumberFormat("it-IT").format(Number(value) || 0);
}


function localTimestamp(value) {
  if (!value) return "Non disponibile";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString("it-IT");
}


function utcDate(value) {
  const [year, month, day] = String(value).split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day));
}


function isoDate(value) {
  return value.toISOString().slice(0, 10);
}


function addDays(value, days) {
  const result = new Date(value);
  result.setUTCDate(result.getUTCDate() + days);
  return result;
}


export function workforceStatusLabel(value) {
  return STATUS_LABELS[value] || "Da verificare";
}


export function workforceCalendarWindow(latestImport, today = new Date()) {
  const summary = latestImport?.summary || {};
  if (!summary.date_from || !summary.date_to) {
    return { dateFrom: "", dateTo: "" };
  }
  const minimum = utcDate(summary.date_from);
  const maximum = utcDate(summary.date_to);
  const currentIso = typeof today === "string" ? today : isoDate(today);
  const current = utcDate(currentIso);
  const cursor = current >= minimum && current <= maximum ? current : minimum;
  const mondayOffset = (cursor.getUTCDay() + 6) % 7;
  let start = addDays(cursor, -mondayOffset);
  if (start < minimum) start = minimum;
  let end = addDays(start, 6);
  if (end > maximum) end = maximum;
  return { dateFrom: isoDate(start), dateTo: isoDate(end) };
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


export function renderWorkforceLanding(status) {
  const latest = status.latest_import || {};
  const summary = latest.summary || {};
  const attentionCount = (
    Number(summary.excluded_rows || 0)
    + (Array.isArray(summary.confirmation_columns) ? summary.confirmation_columns.length : 0)
  );
  document.getElementById("workforceReadyMemberCount").textContent = integer(status.member_count);
  document.getElementById("workforceReadyPeriod").textContent = summary.date_from
    ? `${summary.date_from} - ${summary.date_to || summary.date_from}`
    : "Non disponibile";
  document.getElementById("workforceReadyStatusCount").textContent = integer(summary.status_count);
  document.getElementById("workforceReadyContractCount").textContent = integer(summary.contracts_detected);
  document.getElementById("workforceReadyAbsenceCount").textContent = integer(summary.absences_detected);
  document.getElementById("workforceReadyUpdatedAt").textContent = localTimestamp(latest.imported_at);
  document.getElementById("workforceReadySource").textContent = latest.source || "Excel";
  const attention = document.getElementById("workforceReadyAttention");
  attention.hidden = attentionCount === 0;
  attention.textContent = attentionCount
    ? `${integer(attentionCount)} elementi richiedono attenzione.`
    : "";
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
              <button type="button" class="quiet" data-workforce-member-edit="${member.workforce_member_id}">Modifica profilo</button>
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
    ? coverage.slice(0, 7).map((item) => `
        <div>
          <strong>${escapeHtml(item.date)} - ${escapeHtml(COVERAGE_LABELS[item.status] || "Da verificare")}</strong>
          <span>Richieste ${item.required ?? "--"}, disponibili ${item.available}, margine ${item.margin ?? "--"}</span>
        </div>
      `).join("")
    : '<div><strong>Fabbisogno non disponibile.</strong><span>Importalo o configuralo prima di valutare il margine.</span></div>';

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
        <div><strong>${escapeHtml(CHANGE_LABELS[item.reason] || "Aggiornamento registrato")}</strong>
        <span>${escapeHtml(localTimestamp(item.timestamp))}</span></div>
      `).join("")
    : '<div><strong>Nessuna modifica registrata.</strong></div>';
}


export function clearWorkforceImportPreview() {
  document.getElementById("workforceImportState").replaceChildren();
  document.getElementById("workforceSheetRoles").replaceChildren();
  document.getElementById("workforceMatrixPreview").replaceChildren();
  document.getElementById("workforceImportIssuesList").replaceChildren();
  document.getElementById("workforceImportIssues").hidden = true;
}


export function renderWorkforceImportPreview(preview) {
  const usefulSheets = preview.sheets.filter((sheet) => sheet.responsibility !== "ignored");
  const confirmationColumns = Array.isArray(preview.confirmation_columns)
    ? preview.confirmation_columns
    : [];
  const anomalies = Array.isArray(preview.anomalies) ? preview.anomalies : [];
  const attentionCount = Number(preview.excluded_rows || 0) + confirmationColumns.length + anomalies.length;
  document.getElementById("workforceImportState").innerHTML = `
    <div class="workforce-import-summary">
      <div><span>Tipo</span><strong>Planning turni</strong></div>
      <div><span>Risorse</span><strong>${integer(preview.people_detected)}</strong></div>
      <div><span>Periodo</span><strong>${escapeHtml(preview.date_from || "Non rilevato")} - ${escapeHtml(preview.date_to || "--")}</strong></div>
      <div><span>Contratti</span><strong>${integer(preview.contracts_detected)}</strong></div>
      <div><span>Assenze</span><strong>${integer(preview.absences_detected)}</strong></div>
      <div><span>Righe escluse</span><strong>${integer(preview.excluded_rows)}</strong></div>
      <div><span>Colonne da confermare</span><strong>${integer(confirmationColumns.length)}</strong></div>
    </div>
  `;
  document.getElementById("workforceSheetRoles").innerHTML = usefulSheets.map((sheet) => `
    <div class="workforce-sheet-role">
      <strong>${escapeHtml(sheet.name)}</strong>
      <span>${escapeHtml(SHEET_ROLE_LABELS[sheet.responsibility] || "Dati Workforce")} - ${integer(sheet.importable_rows)} righe</span>
    </div>
  `).join("");

  const issues = document.getElementById("workforceImportIssues");
  issues.hidden = attentionCount === 0;
  document.getElementById("workforceImportIssuesSummary").textContent = attentionCount
    ? `${integer(attentionCount)} elementi richiedono attenzione`
    : "Nessun elemento da verificare";
  const issueItems = [
    ...confirmationColumns.slice(0, 5).map((item) => `Colonna da confermare: ${item}`),
    ...anomalies.slice(0, 5),
  ];
  document.getElementById("workforceImportIssuesList").innerHTML = issueItems.length
    ? `<ul>${issueItems.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`
    : '<p>Il riepilogo contiene righe escluse dall\'import automatico.</p>';

  const rows = (Array.isArray(preview.matrix) ? preview.matrix : []).slice(0, 5);
  const matrix = document.getElementById("workforceMatrixPreview");
  if (!rows.length) {
    matrix.innerHTML = '<p>Nessun campione calendario disponibile.</p>';
    return;
  }
  const columns = Object.keys(rows[0]).slice(0, 8);
  matrix.innerHTML = `
    <p class="workforce-sample-label">Campione: massimo 5 risorse e 7 giorni.</p>
    <table><thead><tr>${columns.map((item) => `<th>${escapeHtml(item)}</th>`).join("")}</tr></thead>
    <tbody>${rows.map((row) => `<tr>${columns.map((item) => `<td>${escapeHtml(row[item])}</td>`).join("")}</tr>`).join("")}</tbody></table>
  `;
}
