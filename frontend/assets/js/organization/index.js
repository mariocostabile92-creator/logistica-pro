import { changePassword, createUser, getOrganization, listUsers, updateUser } from "./api.js";
import { renderOrganization, renderUsers } from "./renderer.js";
import { organizationState, setOrganizationData } from "./state.js";

let initialized = false;

async function load() {
  const [organization, users] = await Promise.all([getOrganization(), listUsers()]);
  setOrganizationData(organization, users.items);
  renderOrganization(organization); renderUsers(users.items);
  document.getElementById("organizationSettingsStatus").textContent = `${users.items.length} utenti configurati`;
}

function openEditor(user = null) {
  const form = document.getElementById("organizationUserForm");
  form.reset(); form.userId.value = user?.id || "";
  form.firstName.value = user?.first_name || ""; form.lastName.value = user?.last_name || "";
  form.email.value = user?.email || ""; form.email.disabled = Boolean(user);
  form.role.value = user?.role || "viewer"; form.active.checked = user?.active ?? true;
  form.temporaryPassword.required = !user;
  document.getElementById("organizationUserDialogTitle").textContent = user ? "Gestisci utente" : "Nuovo utente";
  document.getElementById("organizationUserMessage").textContent = "";
  document.getElementById("organizationUserDialog").showModal();
}

async function save(event) {
  event.preventDefault(); const form = event.currentTarget; const button = form.querySelector("button[type=submit]");
  button.disabled = true; const id = form.userId.value;
  const common = { first_name:form.firstName.value.trim(), last_name:form.lastName.value.trim(), role:form.role.value, active:form.active.checked };
  try {
    if (id) {
      await updateUser(id, common);
      if (form.temporaryPassword.value) await changePassword(id, form.temporaryPassword.value);
    } else await createUser({ ...common, email:form.email.value.trim(), temporary_password:form.temporaryPassword.value });
    document.getElementById("organizationUserDialog").close(); await load();
  } catch (error) { document.getElementById("organizationUserMessage").textContent = error.message; }
  finally { button.disabled = false; }
}

export function initOrganizationSettings() {
  if (initialized) return; initialized = true;
  document.getElementById("organizationSettingsTabs").addEventListener("click", event => {
    const tab = event.target.closest("[data-organization-tab]")?.dataset.organizationTab;
    if (!tab) return;
    document.querySelectorAll("[data-organization-tab]").forEach(button => button.classList.toggle("active", button.dataset.organizationTab === tab));
    document.querySelectorAll("[data-organization-panel]").forEach(panel => { panel.hidden = panel.dataset.organizationPanel !== tab; });
  });
  document.getElementById("newOrganizationUser").addEventListener("click", () => openEditor());
  document.getElementById("organizationUsersList").addEventListener("click", event => {
    const id = event.target.closest("[data-edit-organization-user]")?.dataset.editOrganizationUser;
    if (id) openEditor(organizationState.users.find(user => user.id === id));
  });
  document.getElementById("organizationUserForm").addEventListener("submit", save);
  document.querySelector("[data-close-user-dialog]").addEventListener("click", () => document.getElementById("organizationUserDialog").close());
  load().catch(error => { document.getElementById("organizationSettingsStatus").textContent = error.message; });
}
