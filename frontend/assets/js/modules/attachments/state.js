const stores = new WeakMap();

export function attachmentState(container) {
  if (!stores.has(container)) {
    stores.set(container, { items: [], loading: false, error: "", entityType: "", entityId: null });
  }
  return stores.get(container);
}
