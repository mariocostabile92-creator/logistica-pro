import { getFleetVision, listJournalControlRoom } from "../../api.js";
import { listVehicleAttachments } from "../attachments/api.js";

const priorityRank = { alta: 0, media: 1, bassa: 2 };
const incompleteJournal = new Set([
  "generated", "opened", "in_progress", "generata", "aperta", "in_compilazione",
]);

function recordFor(item, decision) {
  if (decision.module === "damage") {
    const record = item.latest?.damage;
    return { id: record?.id, label: record?.case_number || "pratica danno" };
  }
  if (decision.module === "maintenance") {
    const record = item.latest?.maintenance;
    return { id: record?.id, label: record?.maintenance_number || "manutenzione" };
  }
  if (decision.module === "insurance") {
    return { id: item.insurance?.id, label: item.insurance?.policy_number || "polizza" };
  }
  if (decision.module === "rentals") {
    const entry = item.timeline?.find(event => event.module === "rentals");
    return { id: entry?.source_id, label: entry?.label || "contratto noleggio" };
  }
  return { id: decision.evidence?.source_id, label: null };
}

function normalizeDecision(item, decision) {
  const record = recordFor(item, decision);
  return {
    ...decision,
    vehicle_id: item.id,
    vehicle: item.plate || item.external_identifier,
    record_id: record.id,
    record_label: record.label,
    date: item.latest?.status_change?.occurred_at
      || item.latest?.damage?.occurred_at
      || item.latest?.maintenance?.opened_at
      || null,
    status: decision.priority === "alta" ? "Richiede attenzione" : "Da monitorare",
  };
}

function normalizeCompletionDecision(decision, operationalDate) {
  return {
    ...decision,
    vehicle_id: Number(decision.vehicle_id) || -1,
    vehicle: decision.vehicle || "Intera flotta",
    record_id: null,
    record_label: null,
    date: operationalDate,
    status: decision.priority === "alta" ? "Richiede attenzione" : "Da monitorare",
  };
}

export async function loadFleetVisionExcellence(options = {}) {
  const [visionResult, journalResult] = await Promise.allSettled([
    getFleetVision(options.vehicle_id ? { vehicle_id: options.vehicle_id } : {}),
    listJournalControlRoom({ limit: 200 }),
  ]);
  if (visionResult.status === "rejected") throw visionResult.reason;
  const vision = visionResult.value;
  const journalItems = journalResult.status === "fulfilled"
    ? (journalResult.value.items || []) : [];
  const completion = journalResult.status === "fulfilled"
    ? journalResult.value.completion : null;
  const missing = completion?.missing || [];
  const attachments = await Promise.all(
    vision.items.map(item => listVehicleAttachments(item.id).catch(() => [])),
  );
  const items = vision.items.map((item, index) => ({
    ...item,
    attachments: attachments[index],
    journal_incomplete: missing.filter(entry =>
      Number(entry.vehicle_id) === Number(item.id)).length
      + journalItems.filter(session =>
        Number(session.vehicle_id || session.asset_id) === Number(item.id)
        && incompleteJournal.has(session.status)
        && !missing.some(entry => entry.procedure_id === session.id)).length,
  }));
  const completionCriticalities = (completion?.decisions || []).map(decision =>
    normalizeCompletionDecision(decision, completion.operational_date));
  const criticalities = [...items.flatMap(item =>
    (item.decisions || []).map(decision => normalizeDecision(item, decision))),
  ...completionCriticalities]
    .sort((a, b) => priorityRank[a.priority] - priorityRank[b.priority]);
  const grouped = Object.values(criticalities.reduce((acc, decision) => {
    acc[decision.vehicle_id] ||= {
      vehicle_id: decision.vehicle_id,
      vehicle: decision.vehicle,
      criticalities: [],
    };
    acc[decision.vehicle_id].criticalities.push(decision);
    return acc;
  }, {}));
  return {
    items,
    grouped,
    criticalities,
    summary: {
      ...vision.summary,
      expiring_insurance: items.filter(item =>
        item.insurance?.status === "in_scadenza").length,
      journal_incomplete: missing.length,
    },
    partialErrors: journalResult.status === "rejected" ? ["Driver Journal"] : [],
  };
}
