import { state } from "./state.js";
const $ = id => document.getElementById(id);
export function render() {
  document.querySelectorAll(".step").forEach((node, index) => node.classList.toggle("active", index === state.step));
  $("progressBar").style.width = `${Math.min(state.step + 1, 6) / 6 * 100}%`;
  $("stepLabel").textContent = state.step < 6 ? `Passaggio ${state.step + 1} di 6` : "Completato";
  $("navigation").hidden = state.step === 0 || state.step === 6;
  $("backButton").hidden = state.step === 0;
  $("nextButton").textContent = state.step === 5 ? "Conferma movimentazione" : "Continua";
  $("shiftField").hidden = state.operationType !== "check_out";
  $("cleanlinessField").hidden = state.operationType !== "check_in";
}
export function renderEquipment() {
  $("equipmentList").innerHTML = state.configuration.equipment.map(item => `<label class="equipment-item"><span>${item.label}</span><select data-equipment="${item.code}" aria-label="Stato ${item.label}"><option value="">Seleziona</option><option value="present">Presente</option><option value="missing">Mancante</option><option value="damaged">Danneggiato</option></select></label>`).join("");
}
export function renderSummary() {
  const equipment = [...document.querySelectorAll("[data-equipment]")].map(node => `${node.closest("label").querySelector("span").textContent}: ${node.options[node.selectedIndex].text}`);
  const pairs = [["Operazione", state.operationType === "check_out" ? "Ritiro" : "Rientro"], ["Targa", state.asset.plate], ["Identificativo", $("driverIdentifier").value], ["Chilometri", $("odometer").value], ["Carburante", `${$("fuel").value}%`], ["Dotazioni", equipment.join(", ")], ["Anomalia", $("anomaly").checked ? $("anomalyDescription").value : "No"], ["Foto", String(state.media.length)]];
  $("summary").innerHTML = pairs.map(([key, value]) => `<dt>${key}</dt><dd>${value}</dd>`).join("");
}
export function showReceipt(receipt) {
  $("receiptMessage").textContent = `Ricevuta ${receipt.verification_id}`;
  $("receipt").innerHTML = [["ID verificabile", receipt.verification_id], ["Targa", receipt.plate_snapshot], ["Data e ora", new Date(receipt.occurred_at).toLocaleString("it-IT")], ["Chilometri", receipt.odometer_km], ["Carburante", `${receipt.fuel_percentage}%`]].map(([key, value]) => `<dt>${key}</dt><dd>${value}</dd>`).join("");
}
export const showError = message => { $("journalError").textContent = message || ""; };
export const setLoading = active => { $("loading").hidden = !active; $("nextButton").disabled = active; };
