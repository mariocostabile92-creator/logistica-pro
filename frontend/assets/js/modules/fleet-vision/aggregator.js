import { getFleetVision, listJournalControlRoom } from "../../api.js";
import { listVehicleAttachments } from "../attachments/api.js";

const priorityRank = { alta: 0, media: 1, bassa: 2 };
const incompleteJournal = new Set(["generata", "aperta", "in_compilazione"]);

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

export async function loadFleetVisionExcellence(options = {}) {
  const [visionResult, journalResult] = await Promise.allSettled([
    getFleetVision(options.vehicle_id ? { vehicle_id: options.vehicle_id } : {}),
    listJournalControlRoom({ limit: 200 }),
  ]);
  if (visionResult.status === "rejected") throw visionResult.reason;
  const vision = visionResult.value;
  const journalItems = journalResult.status === "fulfilled"
    ? (journalResult.value.items || []) : [];
  const attachments = await Promise.all(
    vision.items.map(item => listVehicleAttachments(item.id).catch(() => [])),
  );
  const items = vision.items.map((item, index) => ({
    ...item,
    attachments: attachments[index],
    journal_incomplete: journalItems.filter(session =>
      Number(session.vehicle_id || session.asset_id) === Number(item.id)
      && incompleteJournal.has(session.status)).length,
  }));
  const criticalities = items.flatMap(item =>
    (item.decisions || []).map(decision => normalizeDecision(item, decision)))
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
      journal_incomplete: items.reduce((sum, item) => sum + item.journal_incomplete, 0),
    },
    partialErrors: journalResult.status === "rejected" ? ["Driver Journal"] : [],
  };
}
