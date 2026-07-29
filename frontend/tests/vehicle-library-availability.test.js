import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { availability } from "../assets/js/modules/vehicle-library/index.js";


test("Vehicle Library maps canonical Fleet availability states", () => {
  assert.equal(availability("disponibile"), "Disponibile");
  assert.equal(
    availability("disponibile_con_limitazioni"),
    "Disponibile con limitazioni",
  );
  assert.equal(availability("indisponibile"), "Indisponibile");
  assert.equal(availability("in_manutenzione"), "In manutenzione");
  assert.equal(availability("in_officina"), "In officina");
});


test("Vehicle Library preserves legacy availability compatibility", () => {
  assert.equal(availability("available"), "Disponibile");
  assert.equal(availability("reserve"), "Disponibile con limitazioni");
  assert.equal(availability("unavailable"), "Indisponibile");
  assert.equal(availability("maintenance"), "In manutenzione");
  assert.equal(availability("workshop"), "In officina");
});


test("Vehicle Library never exposes unknown technical availability values", () => {
  assert.equal(availability("internal_future_state"), "Non classificato");
  assert.doesNotMatch(availability("internal_future_state"), /internal_future_state/);
  assert.equal(availability(null), "Non classificato");
});


test("Vehicle Library applies the existing Fleet status badge classes", async () => {
  const module = await readFile(
    new URL("../assets/js/modules/vehicle-library/index.js", import.meta.url),
    "utf8",
  );
  assert.match(module, /fleet-status-badge fleet-status-\$\{operationalStatus\.tone\}/);
});
