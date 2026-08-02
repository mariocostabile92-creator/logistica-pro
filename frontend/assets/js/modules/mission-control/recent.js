import { node } from "./dom.js";


export function renderRecent(view) {
  const list = document.getElementById("operationsHomeRecentList");
  if (view.loading) {
    list.replaceChildren(node("li", "mission-recent-empty", "Attività in aggiornamento."));
    return;
  }
  if (!view.recent.length) {
    list.replaceChildren(node("li", "mission-recent-empty", "Nessuna attività recente disponibile."));
    return;
  }
  list.replaceChildren(...view.recent.map((item) => {
    const row = node("li", "mission-recent-item");
    const time = node("time", "", new Date(item.timestamp).toLocaleString("it-IT", {
      day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit",
    }));
    time.dateTime = item.timestamp;
    row.append(time, node("strong", "", item.label), node("span", "", item.source));
    return row;
  }));
}
