import { getConfiguration } from "./api.js?v=dj6101";
import { initFlow } from "./flow.js?v=dj6101";
import { initMedia } from "./media.js?v=dj6101";
import { render, renderEquipment, showError } from "./renderer.js?v=dj4";
import { clearAccessPresentation, prepareJournalAccess } from "./session-access.js?v=dj6101";
import { resetState, state } from "./state.js?v=dj4";
import { publicAccessToken, showPublicAccessError } from "./public-access.js?v=dj6101";

async function start() {
  try {
    state.configuration = await getConfiguration();
    await prepareJournalAccess();
    renderEquipment();
    initFlow();
    initMedia(showError);
    render();
  } catch (error) {
    if (publicAccessToken() && error.code === "INVALID_SHARED_LINK") {
      showPublicAccessError(error.message);
      return;
    }
    showError(`Impossibile avviare il Giornale di bordo: ${error.message}`);
  }
}

document.getElementById("restartButton").addEventListener("click", () => {
  const configuration = state.configuration;
  const accessToken = state.accessToken;
  resetState();
  state.configuration = configuration;
  state.accessToken = accessToken;
  document.getElementById("journalForm").reset();
  document.getElementById("assetResult").hidden = true;
  document.getElementById("journalWarnings").hidden = true;
  clearAccessPresentation();
  if (!publicAccessToken()) history.replaceState({}, "", "/app/journal/");
  renderEquipment();
  render();
});

start();
