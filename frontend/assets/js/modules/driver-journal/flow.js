import { completeSession, createSession, findAsset } from "./api.js";
import { state } from "./state.js";
import { render, renderSummary, setLoading, showError, showReceipt } from "./renderer.js";
const $ = id => document.getElementById(id);
function validateStep() {
  if (state.step === 1 && (!$("driverIdentifier").value.trim() || !$("plate").value.trim())) throw new Error("Compila identificativo e targa.");
  if (state.step === 1 && state.operationType === "check_out" && !$("shift").value) throw new Error("Seleziona la fascia operativa.");
  if (state.step === 2 && ($("odometer").value === "" || Number($("odometer").value) < 0)) throw new Error("Inserisci chilometri validi.");
  if (state.step === 2 && state.operationType === "check_in" && !$("cleanliness").value) throw new Error("Seleziona lo stato pulizia.");
  if (state.step === 3 && [...document.querySelectorAll("[data-equipment]")].some(node => !node.value)) throw new Error("Completa la checklist delle dotazioni.");
  if (state.step === 3 && $("anomaly").checked && !$("anomalyDescription").value.trim()) throw new Error("Descrivi l'anomalia.");
  if (state.step === 5 && !$("confirmSummary").checked) throw new Error("Conferma che il riepilogo è corretto.");
}
async function establishSession() {
  state.asset = await findAsset($("plate").value);
  $("assetResult").hidden = false; $("assetResult").textContent = `Mezzo verificato: ${state.asset.plate}`;
  const session = await createSession({operation_type: state.operationType, plate: $("plate").value, declared_driver_identifier: $("driverIdentifier").value, operational_shift: state.operationType === "check_out" ? $("shift").value : null});
  state.sessionId = session.id; state.token = session.token;
}
async function finish() {
  if (state.submitting) return;
  state.submitting = true; setLoading(true);
  try {
    const equipment = [...document.querySelectorAll("[data-equipment]")].map(node => ({code: node.dataset.equipment, status: node.value}));
    state.receipt = await completeSession(state.sessionId, state.token, {odometer_km: Number($("odometer").value), fuel_percentage: Number($("fuel").value), cleanliness_status: state.operationType === "check_in" ? $("cleanliness").value : null, anomaly_present: $("anomaly").checked, anomaly_description: $("anomaly").checked ? $("anomalyDescription").value : null, operational_note: $("operationalNote").value || null, equipment, client_submission_id: state.clientSubmissionId, timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "Europe/Rome"});
    state.step = 6; showReceipt(state.receipt); render();
  } finally { state.submitting = false; setLoading(false); }
}
export function initFlow() {
  document.querySelectorAll("[data-operation]").forEach(button => button.addEventListener("click", () => { state.operationType = button.dataset.operation; state.step = 1; render(); }));
  $("nextButton").addEventListener("click", async () => {
    showError("");
    try { validateStep(); if (state.step === 1) await establishSession(); if (state.step === 4) renderSummary(); if (state.step === 5) return await finish(); state.step += 1; render(); }
    catch (error) { showError(error.message); }
  });
  $("backButton").addEventListener("click", () => { showError(""); state.step = Math.max(0, state.step - 1); render(); });
  $("anomaly").addEventListener("change", () => { $("anomalyDescriptionField").hidden = !$("anomaly").checked; });
  $("fuel").addEventListener("input", () => { $("fuelValue").textContent = `${$("fuel").value}%`; });
}
