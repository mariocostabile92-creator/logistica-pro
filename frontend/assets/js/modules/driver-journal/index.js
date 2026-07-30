import { getConfiguration, getSharedSession } from "./api.js?v=dj3";
import { initFlow } from "./flow.js?v=dj3";
import { initMedia } from "./media.js?v=dj3";
import { render, renderEquipment, showError } from "./renderer.js?v=dj3";
import { resetState, state } from "./state.js?v=dj3";
import { escapeHtml } from "../../utils/dom.js?v=dj3";

async function start() {
  try {
    state.configuration = await getConfiguration();
    const sessionId = new URLSearchParams(location.search).get("session");
    if (sessionId) {
      const session = await getSharedSession(sessionId);
      state.sharedSession = session;
      state.sessionId = session.id;
      state.token = session.token;
      state.operationType = session.operation_type;
      state.asset = { id: session.asset_id, plate: session.plate_snapshot };
      state.step = 2;
      document.getElementById("driverIdentifier").value = session.declared_driver_identifier;
      document.getElementById("driverIdentifier").readOnly = true;
      document.getElementById("plate").value = session.plate_snapshot;
      document.getElementById("plate").readOnly = true;
      document.getElementById("shift").value = session.operational_shift || "";
      const scheduled = new Date(session.scheduled_at);
      document.getElementById("sessionContext").hidden = false;
      document.getElementById("sessionContext").innerHTML = `
        <strong>Procedura assegnata</strong>
        <dl>
          <div><dt>Driver</dt><dd>${escapeHtml(session.declared_driver_identifier)}</dd></div>
          <div><dt>Veicolo</dt><dd>${escapeHtml(session.plate_snapshot)}</dd></div>
          <div><dt>Tipo</dt><dd>${session.operation_type === "check_out" ? "Presa in carico" : "Rientro mezzo"}</dd></div>
          <div><dt>Data e ora</dt><dd>${scheduled.toLocaleString("it-IT")}</dd></div>
        </dl>`;
    }
    renderEquipment(); initFlow(); initMedia(showError); render();
  } catch (error) { showError(`Configurazione non disponibile: ${error.message}`); }
}
document.getElementById("restartButton").addEventListener("click", () => { resetState(); document.getElementById("journalForm").reset(); location.reload(); });
start();
