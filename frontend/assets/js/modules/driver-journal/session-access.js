import { createSharedSession, getSharedSession, listAssets } from "./api.js?v=dj4";
import { state } from "./state.js?v=dj4";
import { escapeHtml } from "../../utils/dom.js?v=dj4";
import { preparePublicAccess } from "./public-access.js?v=dj4";

const $ = id => document.getElementById(id);

function showContext({ driver, plate, operation, scheduledAt = null }) {
  $("sessionContext").hidden = false;
  $("sessionContext").innerHTML = `<strong>Procedura in corso</strong><dl>
    <div><dt>Driver</dt><dd>${escapeHtml(driver)}</dd></div>
    <div><dt>Veicolo</dt><dd>${escapeHtml(plate)}</dd></div>
    <div><dt>Tipo</dt><dd>${operation === "check_out" ? "Presa in carico" : "Rientro mezzo"}</dd></div>
    ${scheduledAt ? `<div><dt>Data e ora</dt><dd>${escapeHtml(new Date(scheduledAt).toLocaleString("it-IT"))}</dd></div>` : ""}
  </dl>`;
}

export async function prepareJournalAccess() {
  await preparePublicAccess();
  const assets = await listAssets();
  $("journalAssetSuggestions").innerHTML = (assets.items || []).map((asset) =>
    `<option value="${escapeHtml(asset.plate || "")}">${escapeHtml(asset.vehicle_model || asset.category || "Mezzo")}</option>`
  ).join("");
  const sessionId = new URLSearchParams(location.search).get("session");
  if (!sessionId) return;
  const session = await getSharedSession(sessionId);
  const parts = String(session.declared_driver_identifier || "").trim().split(/\s+/);
  const name = session.driver_name || parts.shift() || "";
  const surname = session.driver_surname || parts.join(" ");
  state.sharedSession = session;
  state.sessionId = session.id;
  state.token = session.token;
  state.operationType = session.operation_type;
  state.asset = { id: session.asset_id, plate: session.plate_snapshot };
  state.source = "fleet_manager";
  state.step = 4;
  state.minStep = 4;
  $("driverName").value = name;
  $("driverSurname").value = surname;
  $("driverIdentifier").value = session.declared_driver_identifier;
  $("plate").value = session.plate_snapshot;
  ["driverName", "driverSurname", "plate"].forEach((id) => { $(id).readOnly = true; });
  showContext({
    driver: session.declared_driver_identifier,
    plate: session.plate_snapshot,
    operation: session.operation_type,
    scheduledAt: session.scheduled_at,
  });
}

export async function createSpontaneousSession() {
  const response = await createSharedSession({
    driver_name: $("driverName").value,
    driver_surname: $("driverSurname").value,
    vehicle_plate: $("plate").value,
    procedure_type: state.operationType,
    access_token: state.accessToken,
  });
  state.sessionId = response.session_id;
  state.token = response.token;
  state.asset = response.asset;
  state.warnings = response.warnings || [];
  state.source = "shared_link";
  state.minStep = 1;
  $("driverName").value = response.driver_name;
  $("driverSurname").value = response.driver_surname;
  $("driverIdentifier").value = `${response.driver_name} ${response.driver_surname}`;
  $("plate").value = response.asset.plate;
  showContext({
    driver: $("driverIdentifier").value,
    plate: response.asset.plate,
    operation: response.procedure_type,
  });
}

export function clearAccessPresentation() {
  $("sessionContext").hidden = true;
  $("sessionContext").innerHTML = "";
  ["driverName", "driverSurname", "plate"].forEach((id) => { $(id).readOnly = false; });
}
