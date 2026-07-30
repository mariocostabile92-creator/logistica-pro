import {
  createJournalSharedAccess,
  getActiveJournalSharedAccess,
  revokeJournalSharedAccess,
} from "../api.js";
import { escapeHtml } from "../utils/dom.js";


const absoluteUrl = path => `${location.origin}${path}`;
const createdAt = value => new Date(value).toLocaleString("it-IT");


function presentation(item) {
  if (!item) {
    return `<div class="jcr-shared-empty">
      <p>Nessun link condiviso attivo.</p>
      <button type="button" data-shared-create>Genera link condiviso GDB</button>
    </div>`;
  }
  const url = absoluteUrl(item.link_path);
  return `<div class="jcr-shared-card">
    <div><span class="status-pill">Attivo</span><strong>Link condiviso GDB</strong>
      <small>Creato il ${escapeHtml(createdAt(item.created_at))}</small></div>
    <label>URL pubblico<input data-shared-url value="${escapeHtml(url)}" readonly /></label>
    <div class="jcr-shared-actions">
      <button type="button" data-shared-copy>Copia link</button>
      <a class="header-config-button" href="${escapeHtml(item.link_path)}" target="_blank" rel="noopener">Apri come Driver</a>
      <button type="button" class="secondary" data-shared-regenerate>Rigenera</button>
      <button type="button" class="quiet" data-shared-revoke>Revoca</button>
    </div>
    <p data-shared-feedback aria-live="polite"></p>
  </div>`;
}


export async function mountJournalSharedAccess(container) {
  let item = (await getActiveJournalSharedAccess()).item;
  const render = () => { container.innerHTML = presentation(item); };
  render();
  container.addEventListener("click", async event => {
    const target = event.target;
    if (target.closest("[data-shared-create]")) {
      item = await createJournalSharedAccess(false);
      render();
      return;
    }
    if (target.closest("[data-shared-copy]")) {
      await navigator.clipboard.writeText(container.querySelector("[data-shared-url]").value);
      container.querySelector("[data-shared-feedback]").textContent = "Link copiato.";
      return;
    }
    if (target.closest("[data-shared-regenerate]")) {
      if (!window.confirm("Revocare il link attivo e generarne uno nuovo?")) return;
      item = await createJournalSharedAccess(true);
      render();
      return;
    }
    if (target.closest("[data-shared-revoke]")) {
      if (!window.confirm("Revocare il link condiviso attivo?")) return;
      await revokeJournalSharedAccess(item.id);
      item = null;
      render();
    }
  });
}

