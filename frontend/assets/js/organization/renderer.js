const escape = value => String(value ?? "").replace(/[&<>'"]/g, char => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
}[char]));
const roleLabel = role => ({ administrator:"Administrator",operations_manager:"Operations Manager",fleet_manager:"Fleet Manager",dispatcher:"Dispatcher",viewer:"Viewer" }[role] || role);
const date = value => value ? new Intl.DateTimeFormat("it-IT", {dateStyle:"medium",timeStyle:"short"}).format(new Date(value)) : "Mai";

export function renderOrganization(organization) {
  const values = { organizationName: organization.name, organizationStation: organization.primary_station || "Non configurata", organizationTimezone: organization.timezone, organizationLanguage: organization.language === "it" ? "Italiano" : organization.language, organizationCreatedAt: date(organization.created_at) };
  Object.entries(values).forEach(([id, value]) => { document.getElementById(id).textContent = value; });
}

export function renderUsers(users) {
  const container = document.getElementById("organizationUsersList");
  container.innerHTML = users.length ? users.map(user => `<article class="organization-user-card ${user.active ? "" : "inactive"}">
    <div><strong>${escape(user.first_name)} ${escape(user.last_name)}</strong><span>${escape(user.email)}</span></div>
    <div><span class="role-badge">${escape(roleLabel(user.role))}</span><span class="user-status ${user.active ? "active" : ""}">${user.active ? "Attivo" : "Disattivato"}</span></div>
    <div><small>Ultimo accesso</small><span>${escape(date(user.last_login_at))}</span></div>
    <button type="button" class="secondary" data-edit-organization-user="${escape(user.id)}">Gestisci</button>
  </article>`).join("") : `<div class="empty-state">Nessun utente configurato.</div>`;
}
