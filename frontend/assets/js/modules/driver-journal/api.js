const BASE = "/api/plugins/fleet/v1/journal";

export class JournalApiError extends Error {
  constructor(message, { status = 0, code = "JOURNAL_REQUEST_FAILED", details = null } = {}) {
    super(message);
    this.name = "JournalApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(`${BASE}${path}`, options);
  } catch {
    throw new JournalApiError("Connessione non disponibile. Riprova.", {
      code: "NETWORK_UNAVAILABLE",
    });
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    const detail = payload.detail;
    throw new JournalApiError(
      (detail && typeof detail === "object" ? detail.message : detail)
        || "Operazione non riuscita. Riprova.",
      {
        status: response.status,
        code: detail?.code || "JOURNAL_REQUEST_FAILED",
        details: typeof detail === "object" ? detail : null,
      },
    );
  }
  return response.status === 204 ? null : response.json();
}
export const getConfiguration = () => request("/configuration");
export const findAsset = async (plate, accessToken) => {
  try {
    return await request(
      `/assets?plate=${encodeURIComponent(plate)}&access_token=${encodeURIComponent(accessToken || "")}`,
    );
  } catch (error) {
    if (error.status === 404 || error.status === 422) throw error;
    throw new JournalApiError("Impossibile caricare i mezzi. Riprova.", {
      status: error.status,
      code: "ASSET_LOAD_FAILED",
    });
  }
};
export const listAssets = async accessToken => {
  try {
    return await request(
      `/assets?access_token=${encodeURIComponent(accessToken || "")}`,
    );
  } catch (error) {
    throw new JournalApiError("Impossibile caricare i mezzi. Riprova.", {
      status: error.status,
      code: "ASSET_LIST_LOAD_FAILED",
    });
  }
};
export const createSession = body => request("/sessions", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body) });
export const createSharedSession = body => request("/sessions/shared", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body) });
export const validateSharedAccess = async token => {
  try {
    return await request(`/shared-access/${encodeURIComponent(token)}`);
  } catch (error) {
    if ([403, 404, 410].includes(error.status)) {
      throw new JournalApiError("Il link non è valido o non è più attivo.", {
        status: error.status,
        code: "INVALID_SHARED_LINK",
      });
    }
    throw error;
  }
};
export const getSharedSession = sessionId => request(`/sessions/${encodeURIComponent(sessionId)}`);
export const markSessionInProgress = (sessionId, token) => request(`/sessions/${encodeURIComponent(sessionId)}/progress`, { method: "POST", headers: {"X-Journal-Token": token} });
export const checkSessionWarnings = (sessionId, token, odometerKm) => request(`/sessions/${encodeURIComponent(sessionId)}/warnings`, { method: "POST", headers: {"Content-Type": "application/json", "X-Journal-Token": token}, body: JSON.stringify({odometer_km: odometerKm}) });
export const startCheckpoint = (sessionId, token, checkpoint, mode) => request(`/sessions/${encodeURIComponent(sessionId)}/checkpoints/${checkpoint}/start`, { method: "POST", headers: {"Content-Type": "application/json", "X-Journal-Token": token}, body: JSON.stringify({mode}) });
export const completeCheckpoint = (sessionId, token, checkpoint) => request(`/sessions/${encodeURIComponent(sessionId)}/checkpoints/${checkpoint}/complete`, { method: "POST", headers: {"X-Journal-Token": token} });
export const uploadMedia = (sessionId, token, file, metadata = {}) => {
  const body = new FormData();
  body.append("file", file);
  if (metadata.capturedAt) body.append("captured_at", metadata.capturedAt);
  body.append("capture_source", metadata.captureSource || "file");
  if (metadata.evidenceSlot) body.append("evidence_slot", metadata.evidenceSlot);
  if (metadata.checkpoint) body.append("checkpoint", metadata.checkpoint);
  if (metadata.evidenceMode) body.append("evidence_mode", metadata.evidenceMode);
  return request(`/sessions/${sessionId}/media`, { method: "POST", headers: {"X-Journal-Token": token}, body });
};
export const deleteMedia = (sessionId, token, mediaId) => request(`/sessions/${sessionId}/media/${mediaId}`, { method: "DELETE", headers: {"X-Journal-Token": token} });
export const completeSession = (sessionId, token, body) => request(`/sessions/${sessionId}/complete`, { method: "POST", headers: {"Content-Type": "application/json", "X-Journal-Token": token}, body: JSON.stringify(body) });
