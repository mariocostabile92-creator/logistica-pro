function conflictText(route) {
  if (!route.conflicts?.length) return `<span class="planning-route-ok">Nessun conflitto</span>`;
  return route.conflicts.map((item) => `<button type="button" class="planning-route-conflict" data-route-focus="${route.route_id}">${item.message}</button>`).join("");
}

export function renderRoutes(routes, writable) {
  if (!routes.length) return `<p class="planning-ops-empty">Nessuna rotta corrisponde ai filtri.</p>`;
  return `<div class="planning-routes-board">${routes.map((route) => `<article class="planning-route-card ${route.complete ? "is-complete" : "is-incomplete"}" data-route-id="${route.route_id}">
    <header><div><strong>${route.route_id}</strong><span>${route.cycle_or_wave || "Orario non disponibile"}</span></div><span>${route.complete ? "Completa" : "Da completare"}</span></header>
    <div class="planning-route-assignments">
      <label>Driver<input data-assignment-driver="${route.id}" value="${route.driver_name || ""}" placeholder="Assegna driver" ${writable ? "" : "disabled"}></label>
      <label>Mezzo<input data-assignment-vehicle="${route.id}" value="${route.plate || ""}" placeholder="Assegna targa" ${writable ? "" : "disabled"}></label>
    </div>
    <div class="planning-route-meta"><span>Riserva: Non disponibile</span><span>Note: ${route.notes || "Nessuna nota"}</span></div>
    <div class="planning-route-conflicts">${conflictText(route)}</div>
    <div class="planning-route-actions">
      <label>Convocazione <input type="time" value="${route.convocation?.scheduled_time || ""}" data-convocation-time="${route.id}" ${writable ? "" : "disabled"}></label>
      <select data-convocation-status="${route.id}" ${writable ? "" : "disabled"}><option value="da_preparare" ${route.convocation?.status === "da_preparare" ? "selected" : ""}>Da preparare</option><option value="pronta" ${route.convocation?.status === "pronta" ? "selected" : ""}>Pronta</option><option value="inviata" ${route.convocation?.status === "inviata" ? "selected" : ""}>Inviata</option><option value="confermata" ${route.convocation?.status === "confermata" ? "selected" : ""}>Confermata</option></select>
    </div>
  </article>`).join("")}</div>`;
}
