import { byId, escapeHtml } from "../utils/dom.js";


export function renderPlanningHistory(history) {
  const versions = history?.versions || [];
  const events = history?.events || [];
  const items = [
    ...versions.map((item) => ({
      title: `Versione ${item.version} · ${item.change_type}`,
      meta: `${item.actor} · ${new Date(item.created_at).toLocaleString("it-IT")}`,
    })),
    ...events.map((item) => ({
      title: `${item.event_type} · ${item.entity_id}`,
      meta: `${item.actor} · ${new Date(item.created_at).toLocaleString("it-IT")}`,
    })),
  ];
  byId("planningHistory").innerHTML = items.length
    ? items.map((item) => `
        <div class="history-item">
          <strong>${escapeHtml(item.title)}</strong>
          <span>${escapeHtml(item.meta)}</span>
        </div>
      `).join("")
    : '<div class="empty-state">Nessuna versione disponibile.</div>';
}
