import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const file = path => readFile(new URL(`../${path}`, import.meta.url), "utf8");

test("one Attachment component owns upload list preview download and delete", async () => {
  const [api, state, renderer, component] = await Promise.all([
    file("assets/js/modules/attachments/api.js"),
    file("assets/js/modules/attachments/state.js"),
    file("assets/js/modules/attachments/renderer.js"),
    file("assets/js/modules/attachments/component.js"),
  ]);
  for (const operation of ["listAttachments", "uploadAttachment", "deleteAttachment"]) {
    assert.match(api, new RegExp(operation));
  }
  assert.match(state, /WeakMap/);
  for (const label of ["Allegati", "Aggiungi allegato", "Preview", "Download", "Elimina"]) {
    assert.match(renderer, new RegExp(label));
  }
  assert.match(component, /mountAttachments/);
  assert.match(renderer, /multiple/);
  assert.match(component, /window\.confirm/);
});

test("all Fleet modules reuse the same Attachment component", async () => {
  const modules = await Promise.all([
    "documents-workspace.js", "insurance-workspace.js", "damage-workspace.js",
    "rental-workspace.js", "maintenance-workspace.js", "fleet-page.js",
  ].map(name => file(`assets/js/modules/${name}`)));
  for (const source of modules) assert.match(source, /mountAttachments/);
  assert.match(modules[0], /entityType: "document"/);
  assert.match(modules[1], /entityType: "insurance"/);
  assert.match(modules[2], /entityType: "damage"/);
  assert.match(modules[3], /entityType: "rental"/);
  assert.match(modules[4], /entityType: "maintenance"/);
  assert.match(modules[5], /aggregateVehicle: true/);
});

test("Attachment layout is responsive without fixed product widths", async () => {
  const css = await file("assets/css/attachments.css");
  assert.match(css, /@media\(max-width:768px\)/);
  assert.match(css, /@media\(max-width:480px\)/);
  assert.match(css, /min-width:0/);
  assert.doesNotMatch(css, /(?<!max-)width:(?:390|768|1440)px/);
});
