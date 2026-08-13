import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  findAsset,
  listAssets,
  validateSharedAccess,
} from "../assets/js/modules/driver-journal/api.js";


const file = path => readFile(new URL(`../${path}`, import.meta.url), "utf8");
const jsonResponse = (body, status = 200) => ({
  ok: status >= 200 && status < 300,
  status,
  json: async () => body,
});


async function captureAssetLookup({ plate = "AB123CD", token = "shared-token" } = {}) {
  const originalFetch = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options });
    return jsonResponse({ id: 7, plate, category: "van" });
  };
  try {
    const asset = await findAsset(plate, token);
    return { asset, calls };
  } finally {
    globalThis.fetch = originalFetch;
  }
}


test("Shared Link desktop resolves a vehicle through the public Journal endpoint", async () => {
  const { asset, calls } = await captureAssetLookup();
  assert.equal(asset.plate, "AB123CD");
  assert.equal(calls.length, 1);
  assert.match(calls[0].url, /^\/api\/plugins\/fleet\/v1\/journal\/assets\?/);
});


test("mobile-equivalent lookup uses the same endpoint and payload as desktop", async () => {
  const desktop = await captureAssetLookup({ plate: "MO B123", token: "mobile/token" });
  const mobile = await captureAssetLookup({ plate: "MO B123", token: "mobile/token" });
  assert.equal(mobile.calls[0].url, desktop.calls[0].url);
  assert.equal(mobile.asset.id, desktop.asset.id);
});


test("Shared Link token is preserved and URL encoded during vehicle lookup", async () => {
  const { calls } = await captureAssetLookup({ token: "token/with+symbols=" });
  assert.match(calls[0].url, /access_token=token%2Fwith%2Bsymbols%3D/);
});


test("Shared Link loads the organization vehicle list through the same token", async () => {
  const originalFetch = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async url => {
    calls.push(url);
    return jsonResponse({ items: [{ id: 7, plate: "AB123CD" }] });
  };
  try {
    const response = await listAssets("mobile/token");
    assert.deepEqual(response.items.map(item => item.plate), ["AB123CD"]);
    assert.equal(
      calls[0],
      "/api/plugins/fleet/v1/journal/assets?access_token=mobile%2Ftoken",
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});


test("vehicle endpoint is same-origin and contains no localhost fallback", async () => {
  const [{ calls }, api] = await Promise.all([
    captureAssetLookup(),
    file("assets/js/modules/driver-journal/api.js"),
  ]);
  assert.ok(calls[0].url.startsWith("/api/"));
  assert.doesNotMatch(api, /localhost|127\.0\.0\.1|http:\/\//);
});


test("vehicle API failure has a dedicated retryable message", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => jsonResponse({ detail: "Errore interno" }, 500);
  try {
    await assert.rejects(
      findAsset("AB123CD", "shared-token"),
      error => error.code === "ASSET_LOAD_FAILED"
        && error.message === "Impossibile caricare i mezzi. Riprova.",
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});


test("invalid Shared Link is classified separately from vehicle failures", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => jsonResponse({ detail: "Non trovato" }, 404);
  try {
    await assert.rejects(
      validateSharedAccess("invalid-token"),
      error => error.code === "INVALID_SHARED_LINK"
        && /link non è valido/i.test(error.message),
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});


test("retry action repeats only the explicit vehicle lookup", async () => {
  const [flow, html] = await Promise.all([
    file("assets/js/modules/driver-journal/flow.js"),
    file("journal/index.html"),
  ]);
  assert.match(html, /id="assetRetryButton"[\s\S]*>Riprova<\/button>/);
  assert.match(flow, /assetRetryButton[\s\S]*nextButton[\s\S]*click\(\)/);
  assert.doesNotMatch(flow, /setInterval|while\s*\(true\)/);
});


test("invalid-link presentation is not reused for generic startup failures", async () => {
  const [index, access] = await Promise.all([
    file("assets/js/modules/driver-journal/index.js"),
    file("assets/js/modules/driver-journal/public-access.js"),
  ]);
  assert.match(index, /error\.code === "INVALID_SHARED_LINK"/);
  assert.match(access, /Link non disponibile/);
  assert.match(index, /Impossibile avviare il Giornale di bordo/);
});


test("cache busting invalidates every changed Shared Link module", async () => {
  const [html, index, flow, access, publicAccess, media] = await Promise.all([
    file("journal/index.html"),
    file("assets/js/modules/driver-journal/index.js"),
    file("assets/js/modules/driver-journal/flow.js"),
    file("assets/js/modules/driver-journal/session-access.js"),
    file("assets/js/modules/driver-journal/public-access.js"),
    file("assets/js/modules/driver-journal/media.js"),
  ]);
  assert.match(html, /index\.js\?v=djh1/);
  assert.match(html, /shell\.js\?v=djh1/);
  for (const source of [index, flow, access, publicAccess, media]) {
    assert.match(source, /\?v=djh1/);
  }
});


test("vehicle list no longer uses the authenticated Fleet endpoint", async () => {
  const [api, access] = await Promise.all([
    file("assets/js/modules/driver-journal/api.js"),
    file("assets/js/modules/driver-journal/session-access.js"),
  ]);
  assert.match(api, /listAssets[\s\S]*\/assets\?access_token=/);
  assert.match(access, /listAssets\(state\.accessToken\)/);
  assert.doesNotMatch(api, /fetch\("\/api\/plugins\/fleet\/v1\/assets/);
  assert.doesNotMatch(access, /Elenco mezzi non disponibile/);
});


test("Shared Link does not depend on storage cookies or user-agent branches", async () => {
  const sources = await Promise.all([
    file("assets/js/modules/driver-journal/api.js"),
    file("assets/js/modules/driver-journal/public-access.js"),
    file("assets/js/modules/driver-journal/session-access.js"),
    file("assets/js/modules/driver-journal/flow.js"),
  ]);
  assert.doesNotMatch(
    sources.join("\n"),
    /localStorage|sessionStorage|document\.cookie|userAgent|URLPattern|AbortSignal\.timeout|structuredClone/,
  );
});


test("Journal entry retires legacy PWA caches without touching runtime data", async () => {
  const [shell, pwa, worker] = await Promise.all([
    file("assets/js/modules/driver-journal/shell.js"),
    file("assets/js/modules/pwa.js"),
    file("sw.js"),
  ]);
  assert.match(shell, /retireLegacyServiceWorker\(\)/);
  assert.match(pwa, /updateViaCache: "none"/);
  assert.match(worker, /caches\.delete/);
  assert.match(worker, /registration\.unregister/);
});


test("mobile Journal layout remains constrained at 390px", async () => {
  const [html, responsive] = await Promise.all([
    file("journal/index.html"),
    file("assets/css/driver-journal-responsive.css"),
  ]);
  assert.match(html, /width=device-width, initial-scale=1\.0/);
  assert.match(responsive, /@media \(max-width: 480px\)/);
  assert.doesNotMatch(responsive, /min-width:\s*[4-9]\d{2}px/);
});
