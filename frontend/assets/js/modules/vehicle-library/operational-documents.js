import { escapeHtml } from "../../utils/dom.js";

const FILTERS = {
  all: () => true,
  check_out: (item) => item.operation_type === "check_out",
  check_in: (item) => item.operation_type === "check_in",
  anomaly: (item) => item.anomaly_present,
  no_anomaly: (item) => !item.anomaly_present,
  last_7_days: (item, now) => withinDays(item.occurred_at, now, 7),
  last_30_days: (item, now) => withinDays(item.occurred_at, now, 30),
};

function withinDays(value, now, days) {
  const timestamp = new Date(value).getTime();
  return Number.isFinite(timestamp)
    && timestamp >= now.getTime() - (days * 24 * 60 * 60 * 1000);
}

function operationLabel(value) {
  return value === "check_out" ? "Ritiro" : value === "check_in" ? "Rientro" : "Movimentazione";
}

function cleanlinessLabel(value) {
  return {
    compliant: "Conforme",
    non_compliant: "Non conforme",
    verify: "Da verificare",
  }[value] || "Non registrata";
}

function equipmentStatusLabel(value) {
  return {
    present: "Presente",
    missing: "Mancante",
    absent: "Assente",
    damaged: "Danneggiata",
  }[value] || value || "Non registrato";
}

function dateParts(value) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return { date: value || "—", time: "" };
  return {
    date: parsed.toLocaleDateString("it-IT"),
    time: parsed.toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" }),
  };
}

function documentIdentifier(item) {
  return `DOC-${String(item.id).split("-")[0].toUpperCase()}`;
}

export function filterOperationalDocuments(
  movements,
  { filter = "all", query = "", now = new Date() } = {},
) {
  const predicate = FILTERS[filter] || FILTERS.all;
  const normalized = String(query).trim().toLocaleLowerCase("it-IT");
  return movements.filter((item) => {
    if (!predicate(item, now)) return false;
    if (!normalized) return true;
    const occurred = dateParts(item.occurred_at);
    return [
      occurred.date,
      occurred.time,
      item.declared_driver_identifier,
      item.operation_type,
      operationLabel(item.operation_type),
      item.plate_snapshot,
      documentIdentifier(item),
    ].some((value) => String(value || "").toLocaleLowerCase("it-IT").includes(normalized));
  });
}

function initialAndFinalKm(item, movements) {
  const chronological = [...movements].sort(
    (left, right) => new Date(left.occurred_at) - new Date(right.occurred_at),
  );
  const index = chronological.findIndex((candidate) => candidate.id === item.id);
  const previous = index > 0 ? chronological[index - 1] : null;
  return item.operation_type === "check_in"
    ? { initial: previous?.odometer_km ?? null, final: item.odometer_km }
    : { initial: item.odometer_km, final: null };
}

function operationalDocument(item, movements) {
  const occurred = dateParts(item.occurred_at);
  const kilometers = initialAndFinalKm(item, movements);
  const photos = (item.media || []).filter((media) => media.media_type === "image");
  const equipment = item.equipment || [];
  const equipmentComplete = equipment.length > 0
    && equipment.every((entry) => entry.equipment_status === "present");
  const checklist = equipment.length
    ? equipment.map((entry) => `
        <span class="operational-document-chip">
          ${escapeHtml(entry.equipment_label_snapshot)} ·
          ${escapeHtml(equipmentStatusLabel(entry.equipment_status))}
        </span>
      `).join("")
    : '<span class="section-note">Checklist non registrata.</span>';
  const media = photos.length
    ? photos.map((photo) => `
        <a href="${escapeHtml(photo.url)}" target="_blank" rel="noreferrer">
          <img src="${escapeHtml(photo.url)}" alt="Foto documento operativo" loading="lazy" />
        </a>
      `).join("")
    : '<p class="section-note">Nessuna foto allegata.</p>';
  const damageAction = item.anomaly_present
    ? item.damage_case_id
      ? `<button type="button" class="secondary" data-damage-case-link="${item.damage_case_id}">
          ${escapeHtml(item.damage_case_number)} · ${escapeHtml(item.damage_case_status)} · ${escapeHtml(item.damage_case_severity)} · Apri pratica
        </button>`
      : `<button type="button" data-damage-candidate-link="${escapeHtml(item.id)}">Crea pratica danno</button>`
    : "";
  return `
    <details class="operational-document" data-document-id="${escapeHtml(item.id)}">
      <summary>
        <span class="operational-document-date"><strong>${escapeHtml(occurred.date)}</strong><small>${escapeHtml(occurred.time)}</small></span>
        <span><strong>${escapeHtml(operationLabel(item.operation_type))}</strong><small>${escapeHtml(item.plate_snapshot || "Targa non registrata")}</small></span>
        <span><small>Driver dichiarato</small><strong>${escapeHtml(item.declared_driver_identifier || "—")}</strong></span>
        <span><small>Km</small><strong>${Number(item.odometer_km).toLocaleString("it-IT")}</strong></span>
        <span><small>Anomalia</small><strong class="${item.anomaly_present ? "document-alert" : ""}">${item.anomaly_present ? "Sì" : "No"}</strong></span>
        <span class="operational-document-state"><small>Stato</small><strong>Completata</strong></span>
      </summary>
      <div class="operational-document-body">
        <div class="operational-document-identity">
          <div><span>Identificativo documento</span><strong>${escapeHtml(documentIdentifier(item))}</strong><small>${escapeHtml(item.id)}</small></div>
          <div><span>Data</span><strong>${escapeHtml(occurred.date)}</strong></div>
          <div><span>Ora</span><strong>${escapeHtml(occurred.time)}</strong></div>
          <div><span>Tipo</span><strong>${escapeHtml(operationLabel(item.operation_type))}</strong></div>
          <div><span>Stato</span><strong>Registrazione completata</strong></div>
        </div>
        <dl class="operational-document-detail">
          <div><dt>Driver dichiarato</dt><dd>${escapeHtml(item.declared_driver_identifier || "—")}</dd></div>
          <div><dt>Targa</dt><dd>${escapeHtml(item.plate_snapshot || "—")}</dd></div>
          <div><dt>Turno</dt><dd>${escapeHtml(item.operational_shift || "Non registrato")}</dd></div>
          <div><dt>Km iniziali</dt><dd>${kilometers.initial == null ? "—" : Number(kilometers.initial).toLocaleString("it-IT")}</dd></div>
          <div><dt>Km finali</dt><dd>${kilometers.final == null ? "—" : Number(kilometers.final).toLocaleString("it-IT")}</dd></div>
          <div><dt>Carburante</dt><dd>${item.fuel_percentage}%</dd></div>
          <div><dt>Pulizia</dt><dd>${escapeHtml(cleanlinessLabel(item.cleanliness_status))}</dd></div>
          <div><dt>Dotazioni</dt><dd>${equipmentComplete ? "Complete" : "Da verificare"}</dd></div>
          <div><dt>Anomalie</dt><dd>${item.anomaly_present ? escapeHtml(item.anomaly_description || "Presenti") : "Nessuna"}</dd></div>
          <div><dt>Note</dt><dd>${escapeHtml(item.operational_note || "—")}</dd></div>
          <div><dt>Foto</dt><dd>${photos.length}</dd></div>
          <div><dt>Video</dt><dd>—</dd></div>
        </dl>
        <section><h4>Checklist completa</h4><div class="operational-document-chips">${checklist}</div></section>
        <section><h4>Foto</h4><div class="operational-document-media">${media}</div></section>
        <section><h4>Video</h4><div class="operational-document-placeholder">Video non disponibili in questa versione</div></section>
        ${damageAction ? `<section class="operational-document-damage"><h4>Pratica danno</h4>${damageAction}</section>` : ""}
        <footer class="operational-document-future" aria-label="Predisposizioni future">
          <span>PDF</span><span>Firma</span><span>Fleet Vision Engine</span>
          <span>Franchigia</span><span>Pratica danno</span><span>Assicurazione</span>
        </footer>
      </div>
    </details>
  `;
}

export function mountOperationalDocumentHistory({ movements, list, search, filters, count }) {
  let activeFilter = "all";
  filters._operationalDocumentsController?.abort();
  const controller = new AbortController();
  filters._operationalDocumentsController = controller;
  const render = () => {
    const filtered = filterOperationalDocuments(movements, {
      filter: activeFilter,
      query: search.value,
    });
    count.textContent = `${filtered.length} ${filtered.length === 1 ? "documento" : "documenti"}`;
    list.innerHTML = filtered.length
      ? filtered.map((item) => operationalDocument(item, movements)).join("")
      : '<div class="operational-document-empty">Nessun documento corrisponde ai criteri selezionati.</div>';
  };
  search.addEventListener("input", render, { signal: controller.signal });
  filters.addEventListener("click", (event) => {
    const target = event.target.closest("[data-document-filter]");
    if (!target) return;
    activeFilter = target.dataset.documentFilter;
    filters.querySelectorAll("[data-document-filter]").forEach((button) => {
      const active = button === target;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", String(active));
    });
    render();
  }, { signal: controller.signal });
  list.addEventListener("click", (event) => {
    const caseId = event.target.closest("[data-damage-case-link]")?.dataset.damageCaseLink;
    const movementId = event.target.closest("[data-damage-candidate-link]")?.dataset.damageCandidateLink;
    if (!caseId && !movementId) return;
    document.dispatchEvent(new CustomEvent("damage:open", {
      detail: { caseId: caseId || null, movementId: movementId || null },
    }));
  }, { signal: controller.signal });
  render();
}
