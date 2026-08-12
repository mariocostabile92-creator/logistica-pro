import { ApiError } from "../../utils/errors.js";


const API_BASE = globalThis.OPERATIONS_API_URL || "";


async function parseQualityResponse(response) {
  const payload = await response.json().catch(() => ({}));
  if (response.ok) return payload;
  if (response.status === 401 && globalThis.document) {
    document.dispatchEvent(new CustomEvent("auth:expired"));
  }
  const detail = payload?.detail;
  throw new ApiError("Operazione Quality non riuscita.", {
    status: response.status,
    code: typeof detail === "object" ? detail?.code || null : null,
    detail,
  });
}


export async function previewQualityScorecard(
  file,
  { signal, fetcher = globalThis.fetch } = {},
) {
  const form = new FormData();
  form.append("file", file);
  return parseQualityResponse(await fetcher(
    `${API_BASE}/api/dsp-quality/scorecards/preview`,
    { method: "POST", body: form, signal },
  ));
}


export async function getLatestQualityScorecard(
  { signal, fetcher = globalThis.fetch } = {},
) {
  return parseQualityResponse(await fetcher(
    `${API_BASE}/api/dsp-quality/scorecards/latest`,
    { method: "GET", signal },
  ));
}


export async function getQualityScorecardHistory(
  { signal, fetcher = globalThis.fetch } = {},
) {
  return parseQualityResponse(await fetcher(
    `${API_BASE}/api/dsp-quality/scorecards`,
    { method: "GET", signal },
  ));
}


export async function getQualityScorecard(
  scorecardId,
  { signal, fetcher = globalThis.fetch } = {},
) {
  return parseQualityResponse(await fetcher(
    `${API_BASE}/api/dsp-quality/scorecards/${encodeURIComponent(scorecardId)}`,
    { method: "GET", signal },
  ));
}


export async function getLatestQualityMetrics(
  { signal, fetcher = globalThis.fetch } = {},
) {
  return parseQualityResponse(await fetcher(
    `${API_BASE}/api/dsp-quality/scorecards/latest/metrics`,
    { method: "GET", signal },
  ));
}


export async function getQualityMetrics(
  scorecardId,
  { signal, fetcher = globalThis.fetch } = {},
) {
  return parseQualityResponse(await fetcher(
    `${API_BASE}/api/dsp-quality/scorecards/${encodeURIComponent(scorecardId)}/metrics`,
    { method: "GET", signal },
  ));
}


export async function getLatestQualityDrivers(
  { signal, fetcher = globalThis.fetch } = {},
) {
  return parseQualityResponse(await fetcher(
    `${API_BASE}/api/dsp-quality/scorecards/latest/drivers`,
    { method: "GET", signal },
  ));
}


export async function getQualityDrivers(
  scorecardId,
  { signal, fetcher = globalThis.fetch } = {},
) {
  return parseQualityResponse(await fetcher(
    `${API_BASE}/api/dsp-quality/scorecards/${encodeURIComponent(scorecardId)}/drivers`,
    { method: "GET", signal },
  ));
}


export async function getLatestQualityAttention(
  { signal, fetcher = globalThis.fetch } = {},
) {
  return parseQualityResponse(await fetcher(
    `${API_BASE}/api/dsp-quality/scorecards/latest/attention`,
    { method: "GET", signal },
  ));
}


export async function getQualityAttention(
  scorecardId,
  { signal, fetcher = globalThis.fetch } = {},
) {
  return parseQualityResponse(await fetcher(
    `${API_BASE}/api/dsp-quality/scorecards/${encodeURIComponent(scorecardId)}/attention`,
    { method: "GET", signal },
  ));
}


export async function getQualityDriverHistory(
  transporterExternalId,
  {
    scorecardId = null,
    limit = 52,
    signal,
    fetcher = globalThis.fetch,
  } = {},
) {
  const params = new URLSearchParams({ limit: String(limit) });
  if (scorecardId) params.set("scorecard_id", scorecardId);
  return parseQualityResponse(await fetcher(
    `${API_BASE}/api/dsp-quality/drivers/${encodeURIComponent(transporterExternalId)}/history?${params}`,
    { method: "GET", signal },
  ));
}


export async function getTransporterReconciliation(
  { scorecardId = null, signal, fetcher = globalThis.fetch } = {},
) {
  const params = new URLSearchParams();
  if (scorecardId) params.set("scorecard_id", scorecardId);
  const query = params.size ? `?${params}` : "";
  return parseQualityResponse(await fetcher(
    `${API_BASE}/api/dsp-quality/transporter-mappings/reconciliation${query}`,
    { method: "GET", signal },
  ));
}


export async function searchQualityWorkforceCandidates(
  query,
  { signal, fetcher = globalThis.fetch } = {},
) {
  const params = new URLSearchParams({ q: query });
  return parseQualityResponse(await fetcher(
    `${API_BASE}/api/dsp-quality/transporter-mappings/workforce-candidates?${params}`,
    { method: "GET", signal },
  ));
}


export async function putTransporterMapping(
  transporterExternalId,
  payload,
  { scorecardId = null, signal, fetcher = globalThis.fetch } = {},
) {
  const params = new URLSearchParams();
  if (scorecardId) params.set("scorecard_id", scorecardId);
  const query = params.size ? `?${params}` : "";
  return parseQualityResponse(await fetcher(
    `${API_BASE}/api/dsp-quality/transporter-mappings/${encodeURIComponent(transporterExternalId)}${query}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal,
    },
  ));
}


export async function deleteTransporterMapping(
  transporterExternalId,
  expectedUpdatedAt,
  { scorecardId = null, signal, fetcher = globalThis.fetch } = {},
) {
  const params = new URLSearchParams();
  if (scorecardId) params.set("scorecard_id", scorecardId);
  const query = params.size ? `?${params}` : "";
  return parseQualityResponse(await fetcher(
    `${API_BASE}/api/dsp-quality/transporter-mappings/${encodeURIComponent(transporterExternalId)}${query}`,
    {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ expected_updated_at: expectedUpdatedAt }),
      signal,
    },
  ));
}


export async function getTransporterMappingHistory(
  transporterExternalId,
  { scorecardId = null, signal, fetcher = globalThis.fetch } = {},
) {
  const params = new URLSearchParams();
  if (scorecardId) params.set("scorecard_id", scorecardId);
  const query = params.size ? `?${params}` : "";
  return parseQualityResponse(await fetcher(
    `${API_BASE}/api/dsp-quality/transporter-mappings/${encodeURIComponent(transporterExternalId)}/history${query}`,
    { method: "GET", signal },
  ));
}


export async function previewTransporterIdentitySource(
  {
    file = null,
    scorecardId,
    usePlanning = false,
    sheet = "",
    transporterColumn = "",
    driverColumn = "",
  },
  { signal, fetcher = globalThis.fetch } = {},
) {
  const form = new FormData();
  form.append("scorecard_id", scorecardId);
  form.append("use_planning", String(Boolean(usePlanning)));
  if (file) form.append("file", file);
  if (sheet) form.append("sheet", sheet);
  if (transporterColumn) form.append("transporter_column", transporterColumn);
  if (driverColumn) form.append("driver_column", driverColumn);
  return parseQualityResponse(await fetcher(
    `${API_BASE}/api/dsp-quality/transporter-mappings/source-preview`,
    { method: "POST", body: form, signal },
  ));
}


export async function applyExactTransporterIdentitySource(
  { file = null, scorecardId, previewToken, usePlanning = false },
  { signal, fetcher = globalThis.fetch } = {},
) {
  const form = new FormData();
  form.append("scorecard_id", scorecardId);
  form.append("preview_token", previewToken);
  form.append("use_planning", String(Boolean(usePlanning)));
  if (file) form.append("file", file);
  return parseQualityResponse(await fetcher(
    `${API_BASE}/api/dsp-quality/transporter-mappings/source-apply-exact`,
    { method: "POST", body: form, signal },
  ));
}


export async function importQualityScorecard(
  { file, previewToken, expectedAction },
  { signal, fetcher = globalThis.fetch } = {},
) {
  const form = new FormData();
  form.append("file", file);
  form.append("preview_token", previewToken);
  if (expectedAction) form.append("expected_action", expectedAction);
  return parseQualityResponse(await fetcher(
    `${API_BASE}/api/dsp-quality/scorecards/import`,
    { method: "POST", body: form, signal },
  ));
}
