import { getConfiguration } from "./api.js";
import { initFlow } from "./flow.js";
import { initMedia } from "./media.js";
import { render, renderEquipment, showError } from "./renderer.js";
import { resetState, state } from "./state.js";

async function start() {
  try {
    state.configuration = await getConfiguration();
    renderEquipment(); initFlow(); initMedia(showError); render();
  } catch (error) { showError(`Configurazione non disponibile: ${error.message}`); }
}
document.getElementById("restartButton").addEventListener("click", () => { resetState(); document.getElementById("journalForm").reset(); location.reload(); });
start();
