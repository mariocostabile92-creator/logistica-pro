const BASE = "/api/plugins/fleet/v1/journal";
async function request(path, options = {}) {
  const response = await fetch(`${BASE}${path}`, options);
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || "Operazione non riuscita. Riprova.");
  }
  return response.status === 204 ? null : response.json();
}
export const getConfiguration = () => request("/configuration");
export const findAsset = plate => request(`/assets?plate=${encodeURIComponent(plate)}`);
export const listAssets = async () => {
  const response = await fetch("/api/plugins/fleet/v1/assets");
  if (!response.ok) throw new Error("Elenco mezzi non disponibile.");
  return response.json();
};
export const createSession = body => request("/sessions", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body) });
export const createSharedSession = body => request("/sessions/shared", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body) });
export const getSharedSession = sessionId => request(`/sessions/${encodeURIComponent(sessionId)}`);
export const markSessionInProgress = (sessionId, token) => request(`/sessions/${encodeURIComponent(sessionId)}/progress`, { method: "POST", headers: {"X-Journal-Token": token} });
export const checkSessionWarnings = (sessionId, token, odometerKm) => request(`/sessions/${encodeURIComponent(sessionId)}/warnings`, { method: "POST", headers: {"Content-Type": "application/json", "X-Journal-Token": token}, body: JSON.stringify({odometer_km: odometerKm}) });
export const uploadMedia = (sessionId, token, file) => { const body = new FormData(); body.append("file", file); return request(`/sessions/${sessionId}/media`, { method: "POST", headers: {"X-Journal-Token": token}, body }); };
export const deleteMedia = (sessionId, token, mediaId) => request(`/sessions/${sessionId}/media/${mediaId}`, { method: "DELETE", headers: {"X-Journal-Token": token} });
export const completeSession = (sessionId, token, body) => request(`/sessions/${sessionId}/complete`, { method: "POST", headers: {"Content-Type": "application/json", "X-Journal-Token": token}, body: JSON.stringify(body) });
