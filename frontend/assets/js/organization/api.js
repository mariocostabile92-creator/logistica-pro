async function parse(response) {
  if (response.status === 204) return null;
  const payload = await response.json().catch(() => ({}));
  if (response.ok) return payload;
  const error = new Error(payload.detail || "Operazione non riuscita.");
  error.status = response.status;
  throw error;
}

const request = (path, options = {}) => fetch(`/api/organization${path}`, {
  credentials: "same-origin", ...options,
  headers: options.body ? { "Content-Type": "application/json" } : undefined,
}).then(parse);

export const getOrganization = () => request("");
export const listUsers = () => request("/users");
export const createUser = data => request("/users", { method: "POST", body: JSON.stringify(data) });
export const updateUser = (id, data) => request(`/users/${id}`, { method: "PATCH", body: JSON.stringify(data) });
export const changePassword = (id, password) => request(`/users/${id}/password`, { method: "POST", body: JSON.stringify({ password }) });

export const createMaintenanceToken = data => fetch("/api/admin/maintenance-tokens", {
  method: "POST",
  credentials: "same-origin",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(data),
}).then(parse);
