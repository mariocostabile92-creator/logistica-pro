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
    ? "Importa le rotte definitive per preparare la giornata."
    : summary.blocking_conflicts
      ? `${summary.blocking_conflicts} conflitti devono essere risolti.`
      : summary.routes_incomplete
        ? `Mancano ${summary.routes_incomplete} assegnazioni complete.`
        : payload.lifecycle.state === "published"
          ? "Il piano è pubblicato."
          : "Il piano è pronto per la pubblicazione.";
  return `
    <header class="planning-ops-hero">
      <div><p class="eyebrow">Cabina di regia Dispatcher</p><h2>Piano operativo</h2><p>${sentence}</p></div>
      <dl><div><dt>Data</dt><dd>${planning?.operation_date || "Non disponibile"}</dd></div>
      <div><dt>Station</dt><dd>${planning?.station || "Tutte"}</dd></div>
      <div><dt>Stato</dt><dd><span class="planning-ops-status">${STATUS[payload.lifecycle.state] || "Nessun piano"}</span></dd></div>
      <div><dt>Aggiornato</dt><dd>${planning?.updated_at ? new Date(planning.updated_at).toLocaleString("it-IT") : "Non disponibile"}</dd></div></dl>
    </header>`;
}
