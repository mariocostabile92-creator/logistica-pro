const BASE = "/api/attachments";

async function parse(response) {
  if (response.ok) return response.status === 204 ? null : response.json();
  const payload = await response.json().catch(() => ({}));
  throw new Error(payload.detail || "Operazione allegati non riuscita.");
}

export const listAttachments = (entityType, entityId) =>
  fetch(`${BASE}?entity_type=${encodeURIComponent(entityType)}&entity_id=${entityId}`).then(parse);

export const listVehicleAttachments = vehicleId =>
  fetch(`${BASE}/vehicle/${vehicleId}`).then(parse);

export const uploadAttachment = (entityType, entityId, file, notes = "") => {
  const body = new FormData();
  body.append("entity_type", entityType);
  body.append("entity_id", entityId);
  body.append("file", file);
  if (notes) body.append("notes", notes);
  return fetch(BASE, { method: "POST", body }).then(parse);
};

export const deleteAttachment = attachmentId =>
  fetch(`${BASE}/${encodeURIComponent(attachmentId)}`, { method: "DELETE" }).then(parse);
