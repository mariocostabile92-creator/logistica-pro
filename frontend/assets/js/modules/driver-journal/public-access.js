import { validateSharedAccess } from "./api.js?v=djh1";
import { state } from "./state.js?v=djh1";


const PUBLIC_ACCESS_PATTERN = /^\/app\/journal\/access\/([^/]+)\/?$/;


export function publicAccessToken() {
  const match = location.pathname.match(PUBLIC_ACCESS_PATTERN);
  return match ? decodeURIComponent(match[1]) : null;
}


export async function preparePublicAccess() {
  const token = publicAccessToken();
  if (!token) return false;
  await validateSharedAccess(token);
  state.accessToken = token;
  return true;
}


export function showPublicAccessError(message) {
  document.getElementById("journalForm").hidden = true;
  document.querySelector(".progress").hidden = true;
  document.getElementById("stepLabel").textContent = "Accesso non disponibile";
  const panel = document.querySelector(".journal-panel");
  const error = document.createElement("section");
  error.className = "journal-access-error";
  error.setAttribute("role", "alert");
  const title = document.createElement("h2");
  const detail = document.createElement("p");
  title.textContent = "Link non disponibile";
  detail.textContent = String(message);
  error.append(title, detail);
  panel.append(error);
}
