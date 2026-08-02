import { resetWorkspace } from "../api.js?v=5";
import { byId, setMessage } from "../utils/dom.js";
import { userErrorPresentation } from "../utils/errors.js";
import {
  canConfirmWorkspaceReset,
  importFlowForState,
  WORKSPACE_STATES,
} from "./workspace-state.js";


export function initWorkspaceDialogs({
  onImport,
  onResetCompleted,
}) {
  const importDialog = byId("workspaceImportDialog");
  const resetDialog = byId("workspaceResetDialog");
  const resetForm = byId("workspaceResetForm");
  const confirmation = byId("workspaceResetConfirmation");
  const confirmButton = byId("confirmWorkspaceResetBtn");
  const cancelReset = byId("cancelWorkspaceResetBtn");
  const progress = byId("workspaceResetProgress");
  let busy = false;
  let continueToImport = false;
  let returnFocus = null;

  function restoreFocus() {
    if (returnFocus?.isConnected) {
      returnFocus.focus({ preventScroll: true });
    }
    returnFocus = null;
  }

  function updateConfirmation() {
    confirmButton.disabled = !canConfirmWorkspaceReset(
      confirmation.value,
      busy,
    );
  }

  function closeImport() {
    importDialog.close();
    restoreFocus();
  }

  function closeReset() {
    resetDialog.close();
    restoreFocus();
  }

  function openReset({
    opener = document.activeElement,
    importAfterReset = false,
    intent = "",
  } = {}) {
    returnFocus = opener;
    continueToImport = importAfterReset;
    resetForm.reset();
    busy = false;
    progress.textContent = "";
    byId("workspaceResetIntent").textContent = intent;
    confirmation.disabled = false;
    cancelReset.disabled = false;
    updateConfirmation();
    resetDialog.showModal();
    requestAnimationFrame(() => confirmation.focus());
  }

  function openImport(status, opener = document.activeElement) {
    const flow = importFlowForState(status.workspace_state);
    if (flow === "direct") {
      onImport();
      return;
    }
    returnFocus = opener;
    const isDemo = status.workspace_state === WORKSPACE_STATES.DEMO;
    byId("workspaceImportTitle").textContent = isDemo
      ? "Importa dati reali"
      : "Importa nuovi dati";
    byId("workspaceImportDescription").textContent = isDemo
      ? (
        "Il workspace contiene dati demo. Rimuovili prima di importare "
        + "file reali, cosi i due contesti non vengono mescolati."
      )
      : (
        "Puoi aggiungere nuovi file al workspace corrente oppure "
        + "ripristinare prima il workspace per iniziare una nuova "
        + "giornata pulita."
      );
    byId("continueWorkspaceImportBtn").hidden = isDemo;
    byId("resetAndImportBtn").textContent = isDemo
      ? "Rimuovi demo e continua"
      : "Ripristina e importa";
    importDialog.showModal();
  }

  confirmation.addEventListener("input", updateConfirmation);
  resetDialog.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    event.preventDefault();
    if (!busy) closeReset();
  });
  resetDialog.addEventListener("cancel", (event) => {
    if (busy) event.preventDefault();
  });
  resetDialog.addEventListener("close", () => {
    if (!busy) restoreFocus();
  });
  importDialog.addEventListener("close", restoreFocus);

  byId("cancelWorkspaceImportBtn").addEventListener("click", closeImport);
  byId("continueWorkspaceImportBtn").addEventListener("click", () => {
    importDialog.close();
    onImport();
  });
  byId("workspaceImportForm").addEventListener("submit", (event) => {
    event.preventDefault();
    const opener = returnFocus;
    importDialog.close();
    openReset({
      opener,
      importAfterReset: true,
      intent: (
        "Dopo il ripristino verrai portato alla sezione import per "
        + "caricare i nuovi file."
      ),
    });
  });

  cancelReset.addEventListener("click", closeReset);
  resetForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!canConfirmWorkspaceReset(confirmation.value, busy)) return;

    busy = true;
    confirmation.disabled = true;
    cancelReset.disabled = true;
    confirmButton.disabled = true;
    confirmButton.dataset.loading = "true";
    confirmButton.textContent = "Ripristino in corso...";
    progress.textContent = "Rimozione sicura dei dati operativi in corso.";
    resetDialog.setAttribute("aria-busy", "true");

    try {
      const response = await resetWorkspace();
      busy = false;
      resetDialog.removeAttribute("aria-busy");
      resetDialog.close();
      await onResetCompleted(response, {
        continueToImport,
      });
    } catch (error) {
      const presentation = userErrorPresentation(
        "workspace.reset",
        error,
        {
          statuses: [409, 500],
          codes: [
            "WORKSPACE_RESET_IN_PROGRESS",
            "WORKSPACE_RESET_FAILED",
          ],
          fallback: (
            "Il workspace non e stato ripristinato. "
            + "I dati operativi sono rimasti invariati."
          ),
        },
      );
      busy = false;
      confirmation.disabled = false;
      cancelReset.disabled = false;
      progress.textContent = presentation.message;
      resetDialog.removeAttribute("aria-busy");
      updateConfirmation();
      setMessage(presentation.message, presentation.tone);
    } finally {
      confirmButton.dataset.loading = "false";
      confirmButton.textContent = "Ripristina workspace";
    }
  });

  return { openImport, openReset };
}
