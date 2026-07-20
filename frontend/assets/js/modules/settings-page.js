import { getCurrentConfiguration } from "../api.js";
import { state } from "../state.js";
import { byId, setLoading, setMessage } from "../utils/dom.js";
import {
  isExpectedApiError,
  reportUnexpectedError,
  userMessageForError,
} from "../utils/errors.js";
import {
  renderConfiguration,
  renderSettingsFailure,
  renderSettingsLoading,
} from "./settings-view.js";


let loaded = false;


async function loadConfiguration() {
  const button = byId("settingsScopeForm").querySelector(
    "button[type='submit']",
  );
  renderSettingsLoading();
  byId("settingsTimestamp").textContent = "Caricamento configurazione...";
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
    const expected = isExpectedApiError(error, {
      statuses: [400, 404, 409, 422],
    });
    if (!expected) reportUnexpectedError("configuration.current", error);
    renderSettingsFailure();
    byId("settingsTimestamp").textContent = "Configurazione non disponibile.";
    if (expected) {
      setMessage(userMessageForError(error), "warning");
    }
  } finally {
    setLoading(button, false);
  }
}


export function initSettingsPage() {
  byId("settingsScopeForm").addEventListener("submit", (event) => {
    event.preventDefault();
    loadConfiguration();
  });
  byId("settingsViewState").addEventListener("click", (event) => {
    const action = event.target.closest("[data-view-action]")?.dataset.viewAction;
    if (action === "retry-settings") loadConfiguration();
  });
  document.addEventListener("workspace:view-changed", (event) => {
    if (event.detail.view === "settings" && !loaded) {
      loadConfiguration();
    }
  });
}
