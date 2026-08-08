import { checkSessionWarnings, completeSession, findAsset, markSessionInProgress } from "./api.js?v=dj6101";
import { assetListNeedsRetry, createSpontaneousSession, loadAssetSuggestions } from "./session-access.js?v=dj6101";
import { state } from "./state.js?v=dj4";
import { render, renderSummary, renderWarnings, setLoading, showError, showReceipt } from "./renderer.js?v=dj4";

const $ = id => document.getElementById(id);

function requiredName(id, label) {
  const value = $(id).value.trim();
  if (value.length < 2) throw new Error(`Inserisci ${label.toLowerCase()} (almeno 2 caratteri).`);
}

async function validateCurrentStep() {
  if (state.step === 1) {
    requiredName("driverName", "Nome");
    requiredName("driverSurname", "Cognome");
  }
  if (state.step === 2) {
    if (!$("plate").value.trim()) throw new Error("Inserisci la targa.");
    try {
      state.asset = await findAsset($("plate").value, state.accessToken);
    } catch (error) {
      $("assetRetryButton").hidden = error.code !== "ASSET_LOAD_FAILED";
      throw error;
    }
    $("assetRetryButton").hidden = true;
    $("plate").value = state.asset.plate;
    $("assetResult").hidden = false;
    $("assetResult").textContent = `Mezzo verificato: ${state.asset.plate} · ${state.asset.category || "Modello non registrato"}`;
  }
  if (state.step === 3 && !state.operationType) {
    throw new Error("Scegli presa in carico oppure rientro mezzo.");
  }
  if (state.step === 4) {
    if ($("odometer").value === "" || Number($("odometer").value) < 0) {
      throw new Error("Inserisci chilometri validi.");
    }
    if (state.operationType === "check_in" && !$("cleanliness").value) {
      throw new Error("Seleziona lo stato pulizia.");
    }
  }
  if (state.step === 5) {
    if ([...document.querySelectorAll("[data-equipment]")].some(node => !node.value)) {
      throw new Error("Completa la checklist delle dotazioni.");
    }
    if ($("anomaly").checked && !$("anomalyDescription").value.trim()) {
      throw new Error("Descrivi l'anomalia.");
    }
  }
  if (state.step === 7 && !$("confirmSummary").checked) {
    throw new Error("Conferma che il riepilogo è corretto.");
  }
}

async function finish() {
  if (state.submitting) return;
  state.submitting = true;
  setLoading(true);
  try {
    const equipment = [...document.querySelectorAll("[data-equipment]")].map(node => ({
      code: node.dataset.equipment,
      status: node.value,
    }));
    state.receipt = await completeSession(state.sessionId, state.token, {
      odometer_km: Number($("odometer").value),
      fuel_percentage: Number($("fuel").value),
      cleanliness_status: state.operationType === "check_in" ? $("cleanliness").value : null,
      anomaly_present: $("anomaly").checked,
      anomaly_description: $("anomaly").checked ? $("anomalyDescription").value : null,
      operational_note: $("operationalNote").value || null,
      equipment,
      client_submission_id: state.clientSubmissionId,
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "Europe/Rome",
    });
    state.warnings = state.receipt.warnings || state.warnings;
    state.step = 8;
    showReceipt(state.receipt);
    render();
  } finally {
    state.submitting = false;
    setLoading(false);
  }
}

export function initFlow() {
  $("startButton").addEventListener("click", () => {
    state.step = 1;
    state.minStep = 1;
    render();
  });
  document.querySelectorAll("[data-operation]").forEach(button => button.addEventListener("click", () => {
    state.operationType = button.dataset.operation;
    document.querySelectorAll("[data-operation]").forEach(item => {
      item.classList.toggle("selected", item === button);
    });
  }));
  $("nextButton").addEventListener("click", async () => {
    showError("");
    try {
      await validateCurrentStep();
      if (state.step === 3 && !state.sessionId) await createSpontaneousSession();
      if (state.step === 4 && !state.progressMarked) {
        await markSessionInProgress(state.sessionId, state.token);
        state.progressMarked = true;
      }
      if (state.step === 6) {
        const response = await checkSessionWarnings(
          state.sessionId,
          state.token,
          Number($("odometer").value),
        );
        state.warnings = response.warnings;
        renderWarnings();
        renderSummary();
      }
      if (state.step === 7) return await finish();
      state.step += 1;
      render();
    } catch (error) {
      showError(error.message);
    }
  });
  $("assetRetryButton").addEventListener("click", () => {
    if (assetListNeedsRetry()) {
      void loadAssetSuggestions();
      return;
    }
    $("nextButton").click();
  });
  $("plate").addEventListener("input", () => {
    $("assetRetryButton").hidden = true;
    showError("");
  });
  $("backButton").addEventListener("click", () => {
    showError("");
    state.step = Math.max(state.minStep, state.step - 1);
    render();
  });
  $("anomaly").addEventListener("change", () => {
    $("anomalyDescriptionField").hidden = !$("anomaly").checked;
  });
  $("fuel").addEventListener("input", () => {
    $("fuelValue").textContent = `${$("fuel").value}%`;
  });
}
