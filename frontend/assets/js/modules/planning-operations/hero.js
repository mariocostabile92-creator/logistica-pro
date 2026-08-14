import { formatOperationalDay } from "./day-navigation.js?v=day1";

const STATUS = {
  draft: "Bozza",
  generated: "Bozza",
  partially_assigned: "In completamento",
  critical: "In completamento",
  ready: "Pronto",
  confirmed: "Confermato",
  published: "Pubblicato",
};

export function renderHero(payload) {
  const planning = payload.planning;
  const summary = payload.summary;
  const sentence = !planning
    ? "Workforce e Coverage preparano le risorse. Importa le rotte definitive per completare la giornata."
    : summary.blocking_conflicts
      ? `${summary.blocking_conflicts} conflitti devono essere risolti.`
      : summary.routes_incomplete
        ? `Mancano ${summary.routes_incomplete} assegnazioni complete.`
        : payload.lifecycle.state === "published"
          ? "Il piano è pubblicato."
          : "Il piano è pronto per la pubblicazione.";
  return `
    <header class="planning-ops-hero">
      <div><p class="eyebrow oe-workspace-eyebrow"><img class="oe-workspace-mark" src="/app/assets/brand/operations-engine-mark.png?v=1" width="192" height="134" alt="" aria-hidden="true"><span>Cabina di regia Dispatcher</span></p><h2>Piano operativo</h2><p class="planning-hero-date">${formatOperationalDay(payload.operation_date)}</p><p>${sentence}</p></div>
      <dl><div><dt>Giornata</dt><dd>${formatOperationalDay(payload.operation_date)}</dd></div>
      <div><dt>Fonte persone</dt><dd>Workforce</dd></div>
      <div><dt>Station</dt><dd>${planning?.station || "Tutte"}</dd></div>
      <div><dt>Stato</dt><dd><span class="planning-ops-status">${STATUS[payload.lifecycle.state] || (payload.route_data_available ? "In preparazione" : "Rotte da importare")}</span></dd></div>
      <div><dt>Aggiornato</dt><dd>${planning?.updated_at ? new Date(planning.updated_at).toLocaleString("it-IT") : "Dati Workforce correnti"}</dd></div></dl>
    </header>`;
}
