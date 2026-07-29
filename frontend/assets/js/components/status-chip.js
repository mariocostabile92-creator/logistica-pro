import { escapeHtml } from "../utils/dom.js";


export function planningStatusLabel(status) {
  const labels = {
    draft: "Bozza",
    generated: "Generato",
    partially_assigned: "Parziale",
    ready: "Pronto",
    critical: "Critico",
    confirmed: "Confermato",
    superseded: "Superato",
    proposed: "Proposta",
    warning: "Attenzione",
    blocked: "Bloccata",
    unassigned: "Scoperta",
    manually_changed: "Modifica manuale",
    invalidated: "Invalidata",
  };
  return labels[status] || status || "Non disponibile";
}


export function assignmentStatusChip(status) {
  return `<span class="assignment-status-chip ${escapeHtml(status)}">${escapeHtml(planningStatusLabel(status))}</span>`;
}
