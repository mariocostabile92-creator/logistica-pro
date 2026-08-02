import { setText } from "./dom.js";


function freshness(value) {
  if (!value) return "Aggiornamento in corso";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Ultimo aggiornamento non disponibile";
  return `Ultimo aggiornamento ${date.toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" })}`;
}


export function renderHero(view) {
  const now = new Date();
  setText("operationsHomeGreeting", "Buongiorno");
  setText("operationsHomeDate", now.toLocaleDateString("it-IT", {
    weekday: "long", day: "numeric", month: "long", year: "numeric",
  }));
  setText("operationsHomeFreshness", freshness(view.updatedAt));
  const status = document.getElementById("operationsHomeStatus");
  status.className = `mission-day-status is-${view.status.tone}`;
  status.setAttribute("aria-busy", String(view.loading));
  setText("operationsHomeStatusLabel", view.status.label);
  setText("operationsHomeStatusDescription", view.status.description);
  setText("operationsHomeDataNotice", view.partial ? "Alcuni riepiloghi sono temporaneamente non disponibili." : "Dati operativi aggiornati in background.");
}
