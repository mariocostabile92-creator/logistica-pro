export function applyDocumentFilters(items, { expiry = "", sort = "expiry" } = {}) {
  const filtered = items.filter(item => {
    if (expiry === "dated") return Boolean(item.expires_at);
    if (expiry === "undated") return !item.expires_at;
    if (expiry === "expired") return item.status === "scaduto";
    if (expiry === "expiring") return item.status === "in_scadenza";
    return true;
  });
  const compareText = (a, b) => String(a).localeCompare(String(b), "it");
  return filtered.sort((a, b) => {
    if (sort === "updated") return String(b.updated_at).localeCompare(String(a.updated_at));
    if (sort === "plate") return compareText(a.plate || a.external_identifier, b.plate || b.external_identifier);
    if (sort === "title") return compareText(a.title, b.title);
    return String(a.expires_at || "9999-12-31").localeCompare(String(b.expires_at || "9999-12-31"));
  });
}

