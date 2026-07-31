const escape = value => String(value).replace(/[&<>'"]/g, char => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
}[char]));

const roleLabel = role => ({
  operations_manager: "Operations Manager", fleet_manager: "Fleet Manager",
  dispatcher: "Dispatcher", viewer: "Viewer", administrator: "Administrator",
}[role] || role);

export function renderSessionControl(container, user) {
  container.innerHTML = `<div class="auth-session-user"><strong>${escape(user.email)}</strong>
    <small>${escape(roleLabel(user.role))} · ${escape(user.organization.name)}</small></div>
    <button type="button" class="header-config-button" data-auth-logout>Logout</button>`;
}
