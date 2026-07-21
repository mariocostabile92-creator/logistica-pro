import { escapeHtml } from "../utils/dom.js";


const STATUS_LABELS = {
  available: "Disponibile",
  scheduled: "Programmato",
  rest: "Riposo",
  holiday: "Ferie",
  sickness: "Malattia",
  leave: "Permesso",
  unavailable: "Non disponibile",
  unknown: "Da verificare",
};

const SHEET_ROLE_LABELS = {
  schedule: "Turni e disponibilita",
  members: "Anagrafiche",
  contracts: "Contratti",
  requirements: "Fabbisogno",
  ignored: "Non importato",
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
  const rest = statuses.filter((item) => item.status_code === "rest").length;
  const absent = statuses.filter((item) => (
    ["holiday", "sickness", "leave", "unavailable"].includes(item.status_code)
  )).length;
  const margins = coverage
    .map((item) => item.margin)
    .filter((item) => Number.isFinite(item));
  const deficit = margins.reduce((total, margin) => (
    margin < 0 ? total + Math.abs(margin) : total
  ), 0);
  return {
    members: members.length,
    available,
    scheduled,
    rest,
    absent,
    deficit: margins.length ? deficit : null,
    margin: margins.length ? Math.min(...margins) : null,
    coverageConfigured: margins.length > 0,
  };
}


export function renderWorkforceLanding(status) {
  const latest = status.latest_import || {};
  const summary = latest.summary || {};
  const period = summary.date_from
    ? `${summary.date_from} - ${summary.date_to || summary.date_from}`
    : "periodo non disponibile";
  document.getElementById("workforceTimestamp").textContent = (
    `${period} - aggiornato ${localTimestamp(latest.imported_at)}`
  );
}


export function renderWorkforceSummary(summary) {
  document.getElementById("workforceMemberCount").textContent = summary.members;
  document.getElementById("workforceAvailableCount").textContent = summary.available;
  document.getElementById("workforceScheduledCount").textContent = summary.scheduled;
  document.getElementById("workforceRestCount").textContent = summary.rest;
  document.getElementById("workforceAbsentCount").textContent = summary.absent;
  document.getElementById("workforceDeficitValue").textContent = (
    summary.coverageConfigured ? summary.deficit : "Non configurato"
  );
  document.getElementById("workforceMarginValue").textContent = (
    summary.coverageConfigured ? summary.margin : "Non configurato"
  );
  document.getElementById("workforceRequirementNotice").hidden = summary.coverageConfigured;
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
