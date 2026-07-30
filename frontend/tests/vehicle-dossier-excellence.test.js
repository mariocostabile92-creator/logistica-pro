import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { vehicleDossierModel } from "../assets/js/modules/vehicle-dossier/model.js";

const file = path => readFile(new URL(`../${path}`, import.meta.url), "utf8");

const base = () => ({
  data: {
    asset: {
      id: 7, plate: "AA001BB", category: "Mercedes Sprinter",
      availability: "disponibile", updated_at: "2026-07-30T10:00:00Z",
      profile: { contract_type: "leasing", company: "Fleet Co", contract_number: "C-7" },
    },
    history: {
      asset: { id: 7, plate: "AA001BB" },
      kpis: { current_odometer_km: 50010 },
      movements: [
        { id: "in", operation_type: "check_in", occurred_at: "2026-07-30T18:00:00Z", declared_driver_identifier: "Mario", odometer_km: 50010, anomaly_present: true },
        { id: "out", operation_type: "check_out", occurred_at: "2026-07-30T07:00:00Z", declared_driver_identifier: "Mario", odometer_km: 49820, anomaly_present: false },
      ],
    },
    documents: [{ id: 10, title: "Revisione", document_type: "revisione", status: "valido", expires_at: "2027-01-01" }],
    insurance: [{ id: 11, company: "Assicura", policy_number: "P-1", status: "attiva", starts_on: "2026-01-01", expires_on: "2027-01-01" }],
    rentals: [{ id: 12, rental_company: "Rent", replacement_vehicle: "Van", status: "attivo", start_date: "2026-07-20", expected_end_date: "2026-08-20" }],
    maintenances: [{ id: 13, maintenance_number: "M-1", maintenance_type: "freni", status: "aperta", opened_at: "2026-07-29" }],
    damages: [{ id: 14, case_number: "D-1", severity: "alta", status: "nuova", description: "Fanale", occurred_at: "2026-07-30" }],
    franchises: [],
    deadlines: [],
    attachments: [
      { id: "a", entity_type: "document", entity_id: 10, original_filename: "rev.pdf", mime_type: "application/pdf", created_at: "2026-07-30T12:00:00Z" },
      { id: "b", entity_type: "damage", entity_id: 14, original_filename: "foto.png", mime_type: "image/png", created_at: "2026-07-30T16:00:00Z" },
    ],
    vision: {
      timeline: [{ id: "journal:in", source: "journal", source_id: "in", occurred_at: "2026-07-30T18:00:00Z", module: "journal", label: "Rientro" }],
      decisions: [{ title: "Pratica danno aperta", priority: "alta" }],
      actions: [{ title: "Apri Danni", motivation: "Pratica aperta" }],
    },
  },
  errors: {},
});

test("dossier model aggregates domains and attachments without copies", () => {
  const model = vehicleDossierModel(base());
  assert.equal(model.documents[0].files[0].id, "a");
  assert.equal(model.damages[0].photos, 1);
  assert.equal(model.damages[0].videos, 0);
  assert.equal(model.lastCheckout.id, "out");
  assert.equal(model.lastCheckin.id, "in");
  assert.equal(model.attachments.length, 2);
  assert.equal(new Set(model.attachments.map(item => item.id)).size, 2);
});

test("unified timeline is newest-first and deduplicated", () => {
  const model = vehicleDossierModel(base());
  assert.deepEqual(model.timeline.map(item => item.id), [
    "journal:in", "attachment:b", "attachment:a", "insurance:11",
  ]);
});

test("dossier renderer covers every ordered operational section and real links", async () => {
  const renderer = await file("assets/js/modules/vehicle-dossier/renderer.js");
  const ordered = [
    'data-section="profile"', 'data-section="status"', 'data-section="documents"',
    'data-section="insurance"', 'data-section="rentals"', 'data-section="maintenances"',
    'data-section="damages"', 'data-section="journal"', 'data-section="timeline"',
    'data-section="vision"', 'data-section="brain"',
  ];
  let previous = -1;
  for (const heading of ordered) {
    const index = renderer.indexOf(heading);
    assert.ok(index > previous, `${heading} deve rispettare l'ordine dossier`);
    previous = index;
  }
  for (const action of [
    "Apri documento", "Apri polizza", "Apri noleggio", "Apri manutenzione",
    "Apri pratica", "Vai al Journal", "Apri Fleet Vision", "Apri Action Center",
  ]) assert.match(renderer, new RegExp(action));
  assert.doesNotMatch(renderer, /N\/A|Prossimamente/);
});

test("loader coordinates existing APIs and preserves partial section errors", async () => {
  const loader = await file("assets/js/modules/vehicle-dossier/loader.js");
  assert.match(loader, /Promise\.allSettled/);
  assert.match(loader, /errors\[key\]/);
  assert.match(loader, /listVehicleAttachments/);
  assert.match(loader, /getFleetVision/);
  assert.doesNotMatch(loader, /fetch\(/);
});

test("timeline is filterable bounded and opens original records", async () => {
  const timeline = await file("assets/js/modules/vehicle-dossier/timeline.js");
  assert.match(timeline, /Filtra storico/);
  assert.match(timeline, /slice\(0, limit\)/);
  assert.match(timeline, /Mostra altri/);
  assert.match(timeline, /data-dossier-source/);
});

test("Vehicle dossier is responsive at desktop tablet and mobile without fixed canvas", async () => {
  const css = await file("assets/css/vehicle-dossier.css");
  assert.match(css, /@media\(max-width:768px\)/);
  assert.match(css, /@media\(max-width:480px\)/);
  assert.match(css, /min-width:0/);
  assert.doesNotMatch(css, /(?<!max-)width:(?:390|768|1440)px/);
});
