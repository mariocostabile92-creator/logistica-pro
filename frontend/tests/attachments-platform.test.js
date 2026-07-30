import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { saveEntityWithAttachments } from "../assets/js/modules/attachments/entity-adapter.js";

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

test("creation dialogs expose the shared draft uploader before final actions", async () => {
  const modules = await Promise.all([
    "documents-workspace.js", "insurance-workspace.js", "damage-workspace.js",
    "rental-workspace.js", "maintenance-workspace.js",
  ].map(name => file(`assets/js/modules/${name}`)));
  const titles = [
    "Allegati", "Allegati polizza", "Foto e video del danno",
    "Contratto e allegati", "Preventivi, fatture e foto",
  ];
  modules.forEach((source, index) => {
    assert.match(source, /createAttachmentDraft/);
    assert.match(source, /saveEntityWithAttachments/);
    assert.match(source, new RegExp(titles[index]));
    assert.match(source, /submit\.disabled = true/);
    assert.match(source, /attachments:retry/);
  });
});

test("draft uploader centralizes multiple selection drag drop removal and progress", async () => {
  const [uploader, renderer, state] = await Promise.all([
    file("assets/js/modules/attachments/draft-uploader.js"),
    file("assets/js/modules/attachments/draft-renderer.js"),
    file("assets/js/modules/attachments/draft-state.js"),
  ]);
  assert.match(renderer, /multiple/);
  assert.match(renderer, /Trascina e rilascia/);
  assert.match(renderer, /Seleziona file/);
  assert.match(renderer, /Rimuovi/);
  assert.match(renderer, /Caricamento in corso/);
  assert.match(uploader, /ondrop/);
  assert.match(uploader, /uploadAttachment\(entityType, entityId, file\)/);
  assert.match(uploader, /state\.files\.shift\(\)/);
  assert.match(state, /WeakMap/);
});

test("partial upload retry never creates the entity twice", async () => {
  let creates = 0;
  let attempts = 0;
  const draft = {
    entityId: null,
    record: null,
    uploading: false,
    setEntity(record) {
      this.entityId = record.id;
      this.record = record;
    },
    async uploadPending(entityType, entityId) {
      attempts += 1;
      assert.equal(entityType, "document");
      assert.equal(entityId, 42);
      if (attempts === 1) throw new Error("rete non disponibile");
    },
  };
  const saveRecord = async () => {
    creates += 1;
    return { id: 42 };
  };
  await assert.rejects(
    saveEntityWithAttachments({ draft, entityType: "document", saveRecord }),
    /rete non disponibile/,
  );
  const result = await saveEntityWithAttachments({ draft, entityType: "document", saveRecord });
  assert.equal(result.id, 42);
  assert.equal(creates, 1);
  assert.equal(attempts, 2);
});

test("Vehicle Library renders attachment origin without duplicating storage", async () => {
  const renderer = await file("assets/js/modules/attachments/renderer.js");
  assert.match(renderer, /Origine:/);
  assert.match(renderer, /options\.aggregateVehicle/);
});
