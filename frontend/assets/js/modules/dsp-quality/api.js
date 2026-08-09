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


export async function getLatestQualityMetrics(
  { signal, fetcher = globalThis.fetch } = {},
) {
  return parseQualityResponse(await fetcher(
    `${API_BASE}/api/dsp-quality/scorecards/latest/metrics`,
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
