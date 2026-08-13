import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  evidenceProgress,
  evidenceStatusLabel,
} from "../assets/js/modules/driver-journal/evidence.js";


const file = path => readFile(new URL(`../${path}`, import.meta.url), "utf8");


test("evidence progress reports missing photo and video deterministically", () => {
  assert.deepEqual(evidenceProgress([]).missing, ["photo", "video"]);
  assert.deepEqual(
    evidenceProgress([{ evidence_type: "photo" }]).missing,
    ["video"],
  );
  assert.deepEqual(
    evidenceProgress([{ evidence_type: "video" }]).missing,
    ["photo"],
  );
});


test("one valid photo and video unlock the complete evidence state", () => {
  const progress = evidenceProgress([
    { evidence_type: "photo", freshness_status: "VERIFIED_SESSION_CAPTURE" },
    { evidence_type: "video", freshness_status: "SAME_DAY_RECEIVED" },
  ]);
  assert.deepEqual(progress.counts, { photo: 1, video: 1 });
  assert.equal(progress.complete, true);
});


test("date mismatch and reused hashes remain blocking even with complete counts", () => {
  const mismatch = evidenceProgress([
    { evidence_type: "photo", freshness_status: "DATE_MISMATCH" },
    { evidence_type: "video", freshness_status: "SAME_DAY_RECEIVED" },
  ]);
  assert.equal(mismatch.complete, false);
  assert.equal(mismatch.blocked.length, 1);
  const reused = evidenceProgress([
    { evidence_type: "photo", reuse_detected: true },
    { evidence_type: "video" },
  ]);
  assert.equal(reused.complete, false);
});


test("driver Journal is camera-first and keeps gallery as secondary fallback", async () => {
  const html = await file("journal/index.html");
  assert.match(html, /Scatta foto[\s\S]*capture="environment"/);
  assert.match(html, /Registra video[\s\S]*capture="environment"/);
  assert.match(html, /Scegli file esistente/);
  assert.ok(html.indexOf("Scatta foto") < html.indexOf("Scegli file esistente"));
});


test("completion remains disabled until evidence progress is complete", async () => {
  const [renderer, flow] = await Promise.all([
    file("assets/js/modules/driver-journal/renderer.js"),
    file("assets/js/modules/driver-journal/flow.js"),
  ]);
  assert.match(renderer, /nextButton[\s\S]*disabled = !evidenceProgress/);
  assert.match(flow, /state\.step === 6[\s\S]*evidence\.complete/);
  assert.match(flow, /evidenze obbligatorie mancanti/);
});


test("upload sends capture metadata and replaces the same evidence slot", async () => {
  const [api, media] = await Promise.all([
    file("assets/js/modules/driver-journal/api.js"),
    file("assets/js/modules/driver-journal/media.js"),
  ]);
  for (const field of ["captured_at", "capture_source", "evidence_slot"]) {
    assert.match(api, new RegExp(field));
  }
  assert.match(media, /replaced_media_id/);
  assert.match(media, /Rifai \/ sostituisci/);
});


test("reviewer shows received time freshness warning journal date and vehicle", async () => {
  const reviewer = await file("assets/js/modules/journal-control-room/media-section.js");
  for (const label of [
    "Ricevuta", "Verifica", "Giornale", "Data operativa", "Mezzo",
    "Acquisita durante questo controllo", "Data evidenza non coerente",
    "Evidenza già utilizzata",
  ]) assert.match(reviewer, new RegExp(label));
});


test("historical evidence has an explicit backward-compatible status", () => {
  assert.equal(
    evidenceStatusLabel({ freshness_status: "NOT_VERIFIABLE" }),
    "Data non verificabile",
  );
});


test("390px evidence actions use one column and accessible touch targets", async () => {
  const css = await file("assets/css/driver-journal-responsive.css");
  assert.match(css, /@media \(max-width: 480px\)[\s\S]*\.evidence-progress,.evidence-capture-actions\{grid-template-columns:1fr\}/);
  assert.match(css, /evidence-capture-actions \.upload-button\{min-height:48px;width:100%\}/);
  assert.doesNotMatch(css, /min-width:\s*[4-9]\d{2}px/);
});
