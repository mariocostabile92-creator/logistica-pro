export async function saveEntityWithAttachments({
  draft, entityType, saveRecord,
}) {
  if (draft.uploading) throw new Error("Attendi il completamento dell’upload.");
  let record = draft.record;
  if (!draft.entityId) {
    record = await saveRecord();
    draft.setEntity(record);
  }
  await draft.uploadPending(entityType, draft.entityId);
  return record;
}

