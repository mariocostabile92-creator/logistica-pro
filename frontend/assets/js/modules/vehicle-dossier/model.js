const OPEN_DAMAGE = new Set([
  "nuova", "in_valutazione", "preventivo_richiesto", "preventivo_ricevuto",
  "riparazione_programmata", "in_riparazione",
]);
const OPEN_MAINTENANCE = new Set(["aperta", "programmata", "in_lavorazione"]);

const timestamp = value => {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date.getTime();
};

export const daysRemaining = value => {
  const target = timestamp(value);
  if (target == null) return null;
  return Math.ceil((target - Date.now()) / 86400000);
};

const attachmentsFor = (attachments, entityType, entityId) =>
  attachments.filter(item =>
    item.entity_type === entityType && Number(item.entity_id) === Number(entityId));

function timeline(data) {
  const attachments = (data.attachments || []).map(item => ({
    id: `attachment:${item.id}`,
    category: "attachments",
    source: item.entity_type,
    sourceId: item.entity_id,
    occurredAt: item.created_at,
    title: `${item.original_filename} caricato`,
    description: `Allegato ${item.mime_type}`,
    status: "Disponibile",
    attachment: item,
  }));
  const vision = (data.vision?.timeline || []).map(item => ({
    id: item.id,
    category: item.module,
    source: item.source,
    sourceId: item.source_id,
    occurredAt: item.occurred_at,
    title: item.label,
    description: `Origine: ${item.module}`,
    status: "Registrato",
  }));
  const insurance = (data.insurance || []).map(item => ({
    id: `insurance:${item.id}`,
    category: "insurance",
    source: "insurance",
    sourceId: item.id,
    occurredAt: item.updated_at || item.created_at || item.starts_on,
    title: `Polizza ${item.policy_number}`,
    description: `${item.company} · ${item.status}`,
    status: item.status,
  }));
  const deadlines = (data.deadlines || []).map(item => ({
    id: `deadline:${item.source_module}:${item.source_id}:${item.due_date}`,
    category: "deadlines",
    source: item.source_module,
    sourceId: item.source_id,
    occurredAt: item.due_date,
    title: `Scadenza ${item.deadline_type.replaceAll("_", " ")}`,
    description: item.module_label,
    status: item.status,
  }));
  const unique = new Map();
  [...vision, ...insurance, ...attachments, ...deadlines].forEach(item => {
    if (!unique.has(item.id) && item.occurredAt) unique.set(item.id, item);
  });
  return [...unique.values()].sort(
    (left, right) => (timestamp(right.occurredAt) || 0) - (timestamp(left.occurredAt) || 0),
  );
}

export function vehicleDossierModel({ data, errors }) {
  const movements = data.history.movements || [];
  const attachments = data.attachments || [];
  const latest = type => movements.find(item => item.operation_type === type) || null;
  const damageRows = (data.damages || []).map(item => {
    const files = attachmentsFor(attachments, "damage", item.id);
    return {
      ...item,
      attachments: files,
      photos: files.filter(file => file.mime_type.startsWith("image/")).length,
      videos: files.filter(file => file.mime_type.startsWith("video/")).length,
    };
  });
  return {
    asset: data.asset,
    journalAsset: data.history.asset,
    kpis: data.history.kpis || {},
    profile: data.asset.profile || null,
    documents: (data.documents || []).map(item => ({
      ...item,
      files: attachmentsFor(attachments, "document", item.id),
      daysRemaining: daysRemaining(item.expires_at),
    })),
    insurance: (data.insurance || []).map(item => ({
      ...item,
      files: attachmentsFor(attachments, "insurance", item.id),
      daysRemaining: daysRemaining(item.expires_on),
    })),
    rentals: (data.rentals || []).map(item => ({
      ...item,
      files: attachmentsFor(attachments, "rental", item.id),
      daysRemaining: daysRemaining(item.end_date || item.expected_end_date),
    })),
    maintenances: (data.maintenances || []).map(item => ({
      ...item,
      files: attachmentsFor(attachments, "maintenance", item.id),
      open: OPEN_MAINTENANCE.has(item.status),
    })),
    damages: damageRows,
    openDamages: damageRows.filter(item => OPEN_DAMAGE.has(item.status)),
    closedDamages: damageRows.filter(item => !OPEN_DAMAGE.has(item.status)),
    lastCheckout: latest("check_out"),
    lastCheckin: latest("check_in"),
    movements,
    vision: data.vision,
    attachments,
    timeline: timeline(data),
    errors,
  };
}

