async function parse(response) {
  const payload = await response.json().catch(() => ({}));
  if (response.ok) return payload;
  const error = new Error(payload.detail || "Autenticazione non riuscita.");
  error.status = response.status;
  throw error;
}

export const login = credentials => fetch("/api/auth/login", {
  method: "POST", headers: { "Content-Type": "application/json" },
  credentials: "same-origin", body: JSON.stringify(credentials),
}).then(parse);

export const session = () => fetch("/api/auth/session", {
  credentials: "same-origin",
}).then(parse);

export const logout = () => fetch("/api/auth/logout", {
  method: "POST", credentials: "same-origin",
}).then(response => response.ok ? null : parse(response));

export const bootstrapStatus = () => fetch("/api/auth/bootstrap/status", {
  credentials: "same-origin",
}).then(parse);

export const bootstrap = payload => fetch("/api/auth/bootstrap", {
  method: "POST", headers: { "Content-Type": "application/json" },
  credentials: "same-origin", body: JSON.stringify(payload),
}).then(parse);
