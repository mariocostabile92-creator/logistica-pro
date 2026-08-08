const BASE = "/api/plugins/fleet/v1/journal";

export class JournalApiError extends Error {
  constructor(message, { status = 0, code = "JOURNAL_REQUEST_FAILED" } = {}) {
    super(message);
    this.name = "JournalApiError";
    this.status = status;
    this.code = code;
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
    throw new JournalApiError(
      payload.detail || "Operazione non riuscita. Riprova.",
      { status: response.status },
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
export const uploadMedia = (sessionId, token, file) => { const body = new FormData(); body.append("file", file); return request(`/sessions/${sessionId}/media`, { method: "POST", headers: {"X-Journal-Token": token}, body }); };
export const deleteMedia = (sessionId, token, mediaId) => request(`/sessions/${sessionId}/media/${mediaId}`, { method: "DELETE", headers: {"X-Journal-Token": token} });
export const completeSession = (sessionId, token, body) => request(`/sessions/${sessionId}/complete`, { method: "POST", headers: {"Content-Type": "application/json", "X-Journal-Token": token}, body: JSON.stringify(body) });
