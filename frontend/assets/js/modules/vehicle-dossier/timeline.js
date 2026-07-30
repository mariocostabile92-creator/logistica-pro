import { escapeHtml } from "../../utils/dom.js";

const dateTime = value => {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? { date: value, time: "" }
    : {
        date: parsed.toLocaleDateString("it-IT", { dateStyle: "medium" }),
        time: parsed.toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" }),
      };
};

export function mountDossierTimeline(container, items) {
  let category = "all";
  let limit = 8;
  const categories = [...new Set(items.map(item => item.category))];
  const render = () => {
    const filtered = items.filter(item => category === "all" || item.category === category);
    container.innerHTML = `
      <div class="vehicle-timeline-tools">
        <label>Filtra storico<select data-dossier-timeline-filter>
          <option value="all">Tutte le origini</option>
          ${categories.map(value => `<option value="${escapeHtml(value)}" ${value === category ? "selected" : ""}>${escapeHtml(value.replaceAll("_", " "))}</option>`).join("")}
        </select></label>
        <span>${filtered.length} eventi</span>
      </div>
      <ol class="vehicle-timeline">${filtered.slice(0, limit).map(item => {
        const occurred = dateTime(item.occurredAt);
        return `<li>
          <time><strong>${escapeHtml(occurred.date)}</strong><span>${escapeHtml(occurred.time)}</span></time>
          <div><span class="vehicle-origin">${escapeHtml(item.category.replaceAll("_", " "))}</span>
            <h4>${escapeHtml(item.title)}</h4><p>${escapeHtml(item.description || "")}</p>
            <small>${escapeHtml(item.status || "Registrato")}</small>
            <button type="button" class="quiet" data-dossier-source="${escapeHtml(item.source)}"
              data-dossier-source-id="${escapeHtml(item.sourceId ?? "")}">Apri origine</button>
          </div>
        </li>`;
      }).join("")}</ol>
      ${filtered.length > limit ? '<button type="button" class="secondary" data-dossier-more>Mostra altri</button>' : ""}
      ${filtered.length ? "" : '<div class="vehicle-empty">Nessun evento per il filtro selezionato.</div>'}`;
  };
  container.onchange = event => {
    if (!event.target.matches("[data-dossier-timeline-filter]")) return;
    category = event.target.value;
    limit = 8;
    render();
  };
  container.onclick = event => {
    if (!event.target.closest("[data-dossier-more]")) return;
    limit += 8;
    render();
  };
  render();
}

