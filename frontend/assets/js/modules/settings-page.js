import { getCurrentConfiguration } from "../api.js";
import { state } from "../state.js";
import { byId, setLoading, setMessage } from "../utils/dom.js";
import { renderConfiguration } from "./settings-view.js";


let loaded = false;


async function loadConfiguration() {
  const button = byId("settingsScopeForm").querySelector(
    "button[type='submit']",
  );
  setLoading(button, true, "Caricamento...");
  try {
    const configuration = await getCurrentConfiguration(
      byId("settingsOrganization").value.trim() || "default",
      byId("settingsOperationalUnit").value.trim() || null,
    );
    state.configuration.data = configuration;
    renderConfiguration(configuration);
    byId("settingsTimestamp").textContent = (
      `Configurazione ${configuration.configuration_id}`
    );
    loaded = true;
    setMessage("");
  } catch (error) {
    setMessage(error.message);
  } finally {
    setLoading(button, false);
  }
}


export function initSettingsPage() {
  byId("settingsScopeForm").addEventListener("submit", (event) => {
    event.preventDefault();
    loadConfiguration();
  });
  document.addEventListener("workspace:view-changed", (event) => {
    if (event.detail.view === "settings" && !loaded) {
      loadConfiguration();
    }
  });
}
