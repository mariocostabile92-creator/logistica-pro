import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { PHOTO_SLOTS, checkpointProgress, evidenceProgress, evidenceStatusLabel } from "../assets/js/modules/driver-journal/evidence.js";

const file = path => readFile(new URL(`../${path}`, import.meta.url), "utf8");
const completedEvidence = {
  checkpoints: {
    CHECK_IN: { mode: "VIDEO", completed: true },
    CHECK_OUT: { mode: "PHOTO", completed: true },
  },
};

test("check-in is presented before check-out", async () => {
  const [media, evidence] = await Promise.all([
    file("assets/js/modules/driver-journal/media.js"),
    file("assets/js/modules/driver-journal/evidence.js"),
  ]);
  assert.ok(evidence.indexOf('"CHECK_IN"') < evidence.indexOf('"CHECK_OUT"'));
  assert.match(media, /Controllo presa in carico/);
});

test("photo mode is an explicit checkpoint choice", async () => {
  const media = await file("assets/js/modules/driver-journal/media.js");
  assert.match(media, /data-checkpoint-mode="PHOTO"/);
  assert.match(media, /startCheckpoint/);
});

test("photo mode owns exactly five semantic slots", () => {
  assert.deepEqual(PHOTO_SLOTS, ["FRONT", "REAR", "LEFT", "RIGHT", "ODOMETER"]);
  const progress = checkpointProgress([], "CHECK_IN", "PHOTO", false);
  assert.deepEqual(progress.missing, PHOTO_SLOTS);
});

test("video mode is independently selectable", async () => {
  const media = await file("assets/js/modules/driver-journal/media.js");
  assert.match(media, /data-checkpoint-mode="VIDEO"/);
  assert.match(media, /evidenceMode: mode/);
});

test("video guidance names four sides and odometer", async () => {
  const media = await file("assets/js/modules/driver-journal/media.js");
  assert.match(media, /tutti e quattro i lati/);
  assert.match(media, /contachilometri/);
});

test("checkpoint CTA remains disabled while slots are missing", async () => {
  const media = await file("assets/js/modules/driver-journal/media.js");
  assert.match(media, /progress\.evidenceComplete \? "" : "disabled"/);
  assert.equal(checkpointProgress([], "CHECK_IN", "VIDEO", false).evidenceComplete, false);
});

test("checkpoint completion uses the dedicated API", async () => {
  const [api, media] = await Promise.all([
    file("assets/js/modules/driver-journal/api.js"),
    file("assets/js/modules/driver-journal/media.js"),
  ]);
  assert.match(api, /checkpoints\/\$\{checkpoint\}\/complete/);
  assert.match(media, /completeCheckpoint/);
});

test("check-out is locked until check-in completion", async () => {
  const media = await file("assets/js/modules/driver-journal/media.js");
  assert.match(media, /checkpoint === "CHECK_OUT" && !progressFor\("CHECK_IN"\)\.completed/);
  assert.match(media, /Completa prima il controllo presa in carico/);
});

test("check-out photo mode reuses all five required slots", () => {
  const media = PHOTO_SLOTS.map(slot => ({ checkpoint: "CHECK_OUT", evidence_slot: slot }));
  assert.equal(checkpointProgress(media, "CHECK_OUT", "PHOTO", false).evidenceComplete, true);
});

test("final Journal close remains blocked until both checkpoints complete", async () => {
  const flow = await file("assets/js/modules/driver-journal/flow.js");
  assert.match(flow, /state\.step === 6[\s\S]*evidence\.complete/);
  assert.match(flow, /Completa presa in carico e controllo fine turno/);
  assert.equal(evidenceProgress([], { checkpoints: {} }).complete, false);
});

test("progress distinguishes pickup and end-of-shift", async () => {
  const media = await file("assets/js/modules/driver-journal/media.js");
  assert.match(media, /presa in carico/i);
  assert.match(media, /fine turno/i);
  assert.equal(evidenceProgress([
    { checkpoint: "CHECK_IN", evidence_slot: "VIDEO" },
    ...PHOTO_SLOTS.map(slot => ({ checkpoint: "CHECK_OUT", evidence_slot: slot })),
  ], completedEvidence).complete, true);
});

test("archive renders separate IN and OUT evidence blocks", async () => {
  const reviewer = await file("assets/js/modules/journal-control-room/media-section.js");
  assert.match(reviewer, /checkpointBlock\("CHECK_IN"/);
  assert.match(reviewer, /checkpointBlock\("CHECK_OUT"/);
  assert.match(reviewer, /Presa in carico/);
  assert.match(reviewer, /Fine turno/);
});

test("Control Room shows mode completion timestamp and verification", async () => {
  const reviewer = await file("assets/js/modules/journal-control-room/media-section.js");
  for (const label of ["Modalità", "Completato", "Ricevuta", "Verifica", "Data operativa", "Mezzo"]) {
    assert.match(reviewer, new RegExp(label));
  }
});

test("mobile 390 keeps touch targets and one-column mode controls", async () => {
  const [components, responsive] = await Promise.all([
    file("assets/css/driver-journal-components.css"),
    file("assets/css/driver-journal-responsive.css"),
  ]);
  assert.match(components, /min-height:48px/);
  assert.match(responsive, /@media \(max-width: 480px\)[\s\S]*checkpoint-mode-picker\{grid-template-columns:1fr\}/);
});

test("evidence layout has no fixed wide canvas and legacy status remains readable", async () => {
  const css = await file("assets/css/driver-journal-components.css");
  assert.doesNotMatch(css, /\.journal-checkpoint[^}]*min-width:\s*[4-9]\d{2}px/);
  assert.equal(evidenceStatusLabel({ freshness_status: "NOT_VERIFIABLE" }), "Data non verificabile");
  assert.equal(evidenceProgress([], { historical: true }).complete, true);
});
