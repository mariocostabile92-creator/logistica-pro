const stores = new WeakMap();

export function attachmentDraftState(container) {
  if (!stores.has(container)) {
    stores.set(container, {
      files: [], uploading: false, error: "", feedback: "", entityId: null, record: null,
    });
  }
  return stores.get(container);
}

