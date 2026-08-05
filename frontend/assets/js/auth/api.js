const FIELD_LABELS = {
  organization_name: "nome azienda",
  name: "nome azienda",
  primary_station: "station principale",
  first_name: "nome",
  last_name: "cognome",
  email: "email",
  password: "password",
  password_confirmation: "conferma password",
};

export function authErrorMessage(detail) {
  if (typeof detail === "string" && detail.trim()) return detail;
  const issues = Array.isArray(detail) ? detail : detail ? [detail] : [];
  const messages = issues.map(issue => {
    if (!issue || typeof issue !== "object") return null;
    const field = Array.isArray(issue.loc) ? issue.loc.at(-1) : null;
    const label = FIELD_LABELS[field] || "campo indicato";
    if (issue.type === "missing") return `Compila il campo ${label}.`;
    if (issue.type === "string_too_short") {
      const minimum = issue.ctx?.min_length;
      return minimum
        ? `Il campo ${label} deve contenere almeno ${minimum} caratteri.`
        : `Il campo ${label} è troppo corto.`;
    }
    if (typeof issue.msg === "string") {
      return issue.msg.replace(/^Value error,\s*/i, "");
    }
    return null;
  }).filter(Boolean);
  return [...new Set(messages)].join(" ") || "Controlla i dati inseriti e riprova.";
}

async function parse(response) {
  const payload = await response.json().catch(() => ({}));
  if (response.ok) return payload;
  const error = new Error(authErrorMessage(payload.detail));
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


export const registerOrganization = payload => fetch("/api/auth/register", {
  method: "POST", headers: { "Content-Type": "application/json" },
  credentials: "same-origin", body: JSON.stringify(payload),
}).then(parse);
