import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const file = path => readFile(new URL(`../${path}`, import.meta.url), "utf8");

test("document status is derived and never editable by the client", async () => {
  const [workspace, presenter] = await Promise.all([
    file("assets/js/modules/documents-workspace.js"),
    file("assets/js/modules/documents/status-presenter.js"),
  ]);
  assert.doesNotMatch(workspace, /<select name="status"/);
  for (const state of ["completo", "file_mancante", "in_scadenza", "scaduto", "senza_scadenza", "archiviato"]) {
    assert.match(presenter, new RegExp(state));
  }
});

test("snapshot, combined filters and reset are interactive", async () => {
  const workspace = await file("assets/js/modules/documents-workspace.js");
  for (const token of ["data-doc-kpi-filter", "data-doc-quick-filter", "documentsVehicle", "documentsExpiry", "documentsSort", "data-reset-document-filters", "applyDocumentFilters"]) {
    assert.match(workspace, new RegExp(token));
  }
});

test("detail exposes source record, validity, attachments, history and actions", async () => {
  const workspace = await file("assets/js/modules/documents-workspace.js");
  for (const label of ["Documento", "Veicolo", "Validità", "Allegati", "Storico", "Azioni", "Apri dossier mezzo", "Archivia"]) {
    assert.match(workspace, new RegExp(label));
  }
  assert.match(workspace, /mountAttachments/);
  assert.match(workspace, /archiveVehicleDocument/);
});

test("document upload accepts no video and preserves retry and double-submit protection", async () => {
  const [workspace, draft] = await Promise.all([
    file("assets/js/modules/documents-workspace.js"),
    file("assets/js/modules/attachments/draft-uploader.js"),
  ]);
  assert.match(workspace, /accept:\s*"\.pdf,\.jpg,\.jpeg,\.png,\.webp"/);
  assert.doesNotMatch(workspace, /accept:[^\n]*(?:\.mp4|\.mov)/);
  assert.match(workspace, /if \(submit\.disabled\) return/);
  assert.match(draft, /I file già caricati non saranno duplicati/);
  assert.match(draft, /attachments:retry/);
});

test("permissions hide writes and attachment mutation while backend remains authoritative", async () => {
  const workspace = await file("assets/js/modules/documents-workspace.js");
  assert.match(workspace, /can\("documents:write"\)/);
  assert.match(workspace, /can\("documents:archive"\)/);
  assert.match(workspace, /readOnly:\s*!can\("attachments:write"\)/);
});

test("loading, error and contextual empty states are explicit without reload", async () => {
  const workspace = await file("assets/js/modules/documents-workspace.js");
  for (const label of ["Caricamento documenti", "Documenti non disponibili", "Nessun risultato", "Nessun file allegato"]) {
    assert.match(workspace, new RegExp(label));
  }
  assert.doesNotMatch(workspace, /location\.(?:reload|href)|history\.pushState/);
});
