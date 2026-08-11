import {
  getCredentials,
  prepareCredentials,
  resetCredential,
  revokeCredential,
} from "./driver-shift-planning-api.js?v=8";
import {
  credentialStatusMap,
  renderCredentialSummary,
  renderInitialCredentials,
} from "./driver-shift-credentials-presenter.js?v=2";
import { byId, setLoading } from "../utils/dom.js";
import { userErrorPresentation } from "../utils/errors.js";


function safeCsvValue(value) {
  let text = String(value ?? "").replace(/\r?\n/g, " ");
  if (/^[=+\-@\t\r]/.test(text)) text = `'${text}`;
  return `"${text.replace(/"/g, '""')}"`;
}


export function initialCredentialCsv(credentials) {
  const rows = ["Driver,Access Code,PIN iniziale"];
  credentials.forEach((credential) => rows.push([
    credential.display_name, credential.access_code, credential.initial_pin,
  ].map(safeCsvValue).join(",")));
  return `\ufeff${rows.join("\r\n")}\r\n`;
}


function downloadCsv(credentials) {
  const blob = new Blob([initialCredentialCsv(credentials)], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "credenziali-driver-iniziali.csv";
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}


export function initDriverShiftCredentials({ onChanged = () => {}, status = () => {} } = {}) {
  const state = { distributionId: null, model: null, initial: [], resetOutput: false, request: 0 };
  const elements = {
    root: byId("driverShiftCredentials"),
    initial: byId("driverShiftInitialCredentials"),
  };

  function notify() {
    renderCredentialSummary(elements.root, state.model);
    renderInitialCredentials(elements.initial, state.initial, { reset: state.resetOutput });
    onChanged(state.model, credentialStatusMap(state.model));
  }

  async function load() {
    const request = ++state.request;
    state.initial = [];
    state.resetOutput = false;
    if (!state.distributionId) {
      state.model = null;
      elements.root.hidden = true;
      renderInitialCredentials(elements.initial, []);
      onChanged(null, new Map());
      return;
    }
    elements.root.hidden = false;
    renderCredentialSummary(elements.root, null);
    try {
      const model = await getCredentials(state.distributionId);
      if (request !== state.request) return;
      state.model = model;
      notify();
    } catch (error) {
      if (request !== state.request) return;
      elements.root.innerHTML = '<p class="driver-shift-credentials-error">Impossibile caricare gli accessi driver.</p>';
      status(userErrorPresentation("workforce.driver-shift-credentials", error).message, "error");
    }
  }

  async function prepare(button) {
    setLoading(button, true, "Preparazione...");
    try {
      const result = await prepareCredentials(state.distributionId);
      state.initial = result.initial_credentials || [];
      const readModel = { ...result };
      delete readModel.initial_credentials;
      state.model = readModel;
      state.resetOutput = false;
      notify();
      status(state.initial.length
        ? `${state.initial.length} nuovi accessi creati. Scarica ora le credenziali iniziali.`
        : "Nessuna nuova credenziale: gli accessi esistenti sono rimasti invariati.", "success");
    } catch (error) {
      status(userErrorPresentation("workforce.driver-shift-credentials", error).message, "error");
    } finally {
      setLoading(button, false);
    }
  }

  async function reset(memberId, button) {
    setLoading(button, true, "Reimpostazione...");
    try {
      const result = await resetCredential(memberId);
      state.initial = [{
        display_name: result.display_name,
        initial_pin: result.initial_pin,
      }];
      state.resetOutput = true;
      state.model = await getCredentials(state.distributionId);
      notify();
      status("Nuovo PIN creato. Viene mostrato una sola volta.", "success");
    } catch (error) {
      status(userErrorPresentation("workforce.driver-shift-credentials", error).message, "error");
    } finally {
      setLoading(button, false);
    }
  }

  async function revoke(memberId, button) {
    setLoading(button, true, "Revoca...");
    try {
      await revokeCredential(memberId);
      state.initial = [];
      state.resetOutput = false;
      state.model = await getCredentials(state.distributionId);
      notify();
      status("Credenziale driver revocata.", "success");
    } catch (error) {
      status(userErrorPresentation("workforce.driver-shift-credentials", error).message, "error");
    } finally {
      setLoading(button, false);
    }
  }

  elements.root.addEventListener("click", (event) => {
    const button = event.target.closest("[data-prepare-driver-credentials]");
    if (button) void prepare(button);
  });
  elements.initial.addEventListener("click", (event) => {
    if (event.target.closest("[data-download-initial-credentials]") && state.initial.length) {
      downloadCsv(state.initial);
    }
  });

  return {
    setDistribution(distribution) {
      const nextId = distribution?.id || null;
      if (nextId === state.distributionId) return;
      state.distributionId = nextId;
      state.model = null;
      state.initial = [];
      state.resetOutput = false;
      void load();
    },
    refresh: load,
    prepareMissing: prepare,
    statusMap: () => credentialStatusMap(state.model),
    reset,
    revoke,
  };
}
