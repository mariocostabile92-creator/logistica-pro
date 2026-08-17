import { state } from "./state.js?v=djh2";
import { escapeHtml } from "../../utils/dom.js?v=djh2";
import { evidenceProgress } from "./evidence.js?v=djh2";

const $ = id => document.getElementById(id);
const TOTAL_STEPS = 8;

export function render() {
  document.querySelectorAll(".step").forEach((node, index) => {
    node.classList.toggle("active", index === state.step);
  });
  const progress = state.step === 0 ? 0 : Math.min(state.step, TOTAL_STEPS) / TOTAL_STEPS * 100;
  $("progressBar").style.width = `${progress}%`;
  $("stepLabel").textContent = state.step === 0
    ? "Pronto per iniziare"
    : state.step < 8 ? `Passaggio ${state.step} di ${TOTAL_STEPS}` : "Completato";
  $("navigation").hidden = state.step === 0 || state.step === 8;
  $("backButton").hidden = state.step <= state.minStep;
  $("nextButton").textContent = state.step === 7 ? "Conferma movimentazione" : "Continua";
  if (state.step === 7) {
    $("nextButton").disabled = !evidenceProgress(
      state.media,
      state.evidence,
    ).complete || state.submitting;
  } else if (!state.submitting) {
    $("nextButton").disabled = false;
  }
  $("cleanlinessField").hidden = state.operationType !== "check_in";
}

export function renderEquipment() {
  $("equipmentList").innerHTML = state.configuration.equipment.map(item =>
    `<label class="equipment-item"><span>${escapeHtml(item.label)}</span><select data-equipment="${escapeHtml(item.code)}" aria-label="Stato ${escapeHtml(item.label)}"><option value="">Seleziona</option><option value="present">Presente</option><option value="missing">Mancante</option><option value="damaged">Danneggiato</option></select></label>`
  ).join("");
}

export function renderWarnings() {
  const container = $("journalWarnings");
  container.hidden = !state.warnings.length;
  container.innerHTML = state.warnings.length
    ? `<strong>Verifica prima di confermare</strong><ul>${state.warnings.map(warning =>
      `<li>${escapeHtml(warning.message)}</li>`
    ).join("")}</ul>`
    : "";
}

export function renderSummary() {
  const equipment = [...document.querySelectorAll("[data-equipment]")].map(node =>
    `${node.closest("label").querySelector("span").textContent}: ${node.options[node.selectedIndex].text}`
  );
  const driver = `${$("driverName").value} ${$("driverSurname").value}`.trim()
    || $("driverIdentifier").value;
  const pairs = [
    ["Driver", driver],
    ["Operazione", state.operationType === "check_out" ? "Presa in carico" : "Rientro mezzo"],
    ["Targa", state.asset.plate],
    ["Chilometri", $("odometer").value],
    ["Carburante", `${$("fuel").value}%`],
    ["Dotazioni", equipment.join(", ")],
    ["Anomalia", $("anomaly").checked ? $("anomalyDescription").value : "No"],
    ["Presa in carico", state.evidence?.checkpoints?.CHECK_IN?.completed ? "Completata" : "Incompleta"],
    ["Fine turno", state.evidence?.checkpoints?.CHECK_OUT?.completed ? "Completata" : "Incompleta"],
  ];
  $("summary").innerHTML = pairs.map(([key, value]) =>
    `<dt>${escapeHtml(key)}</dt><dd>${escapeHtml(value)}</dd>`
  ).join("");
}

export function showReceipt(receipt) {
  const driver = `${$("driverName").value} ${$("driverSurname").value}`.trim()
    || $("driverIdentifier").value;
  const occurred = new Date(receipt.occurred_at);
  const pairs = [
    ["Driver", driver],
    ["Targa", receipt.plate_snapshot],
    ["Procedura", receipt.operation_type === "check_out" ? "Presa in carico" : "Rientro mezzo"],
    ["Data", occurred.toLocaleDateString("it-IT")],
    ["Ora", occurred.toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" })],
  ];
  $("receipt").innerHTML = pairs.map(([key, value]) =>
    `<dt>${escapeHtml(key)}</dt><dd>${escapeHtml(value)}</dd>`
  ).join("");
}

export const showError = message => { $("journalError").textContent = message || ""; };
export const setLoading = active => {
  $("loading").hidden = !active;
  $("nextButton").disabled = active;
};
