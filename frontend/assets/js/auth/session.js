import { logout, session } from "./api.js";
import { renderSessionControl } from "./components.js";
import { setSession } from "./state.js";

let sessionRedirecting = false;

function redirectToLogin() {
  if (sessionRedirecting) return;
  sessionRedirecting = true;
  location.replace("/app/login.html");
}

export async function requireAdministrativeSession() {
  try {
    const payload = await session();
    setSession(payload.user);
    const control = document.getElementById("authSessionControl");
    if (control) renderSessionControl(control, payload.user);
    const organizationSettings = document.getElementById("configurationNavBtn");
    if (organizationSettings) organizationSettings.hidden = !payload.user.permissions.includes("users:manage");
    return payload.user;
  } catch (error) {
    setSession(null);
    if (error.status === 401) redirectToLogin();
    throw error;
  }
}

document.addEventListener("click", async event => {
  if (!event.target.closest("[data-auth-logout]")) return;
  await logout();
  setSession(null);
  location.replace("/app/login.html");
});

document.addEventListener("auth:expired", redirectToLogin);
