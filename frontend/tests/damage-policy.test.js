import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  DAMAGE_POLICY_PERIODS,
  damagePolicyDialogMarkup,
  damagePolicySummaryMarkup,
  fillDamagePolicyForm,
  policyFormPayload,
} from "../assets/js/modules/damage-policy.js";
import { damageDriverHistoryMarkup } from "../assets/js/modules/damage-driver-history.js";

const file = (path) => readFile(new URL(`../${path}`, import.meta.url), "utf8");
const enabledState = {
  policy_enabled: true,
  countable_cases: 4,
  free_events_count: 2,
  free_events_used: 2,
  events_over_threshold: 2,
  next_event_is_over_threshold: true,
  counting_period: "calendar_year",
  period_start: "2026-01-01",
  period_end: "2026-12-31",
};

test("Damage API client exposes policy read write and driver state operations", async () => {
  const api = await file("assets/js/api.js");
  assert.match(api, /getDamagePolicy/);
  assert.match(api, /updateDamagePolicy[\s\S]*method: "PUT"/);
  assert.match(api, /getDamageDriverPolicyState/);
  assert.match(api, /drivers\/\$\{workforceMemberId\}\/policy-state/);
});

test("Policy dialog contains the three allowed configuration fields", () => {
  const markup = damagePolicyDialogMarkup();
  assert.match(markup, /name="enabled"/);
  assert.match(markup, /name="free_events_count" min="0"/);
  assert.match(markup, /name="counting_period"/);
});

test("Policy dialog exposes readable period labels", () => {
  assert.deepEqual(DAMAGE_POLICY_PERIODS, {
    all_time: "Sempre",
    calendar_year: "Anno solare",
    rolling_12_months: "Ultimi 12 mesi",
  });
});

test("Policy settings use an explicit save action and lifecycle messages", async () => {
  const source = await file("assets/js/modules/damage-policy.js");
  assert.match(source, /Salva policy/);
  assert.match(source, /Salvataggio in corso…/);
  assert.match(source, /Policy salvata\./);
  assert.match(source, /Impossibile salvare la policy danni\./);
});

test("Initial GET state fills toggle count and period fields", () => {
  const form = { elements: {
    enabled: { checked: false },
    free_events_count: { value: "" },
    counting_period: { value: "" },
  } };
  fillDamagePolicyForm(form, {
    enabled: true,
    free_events_count: 3,
    counting_period: "rolling_12_months",
  });
  assert.equal(form.elements.enabled.checked, true);
  assert.equal(form.elements.free_events_count.value, "3");
  assert.equal(form.elements.counting_period.value, "rolling_12_months");
});

test("Save payload preserves toggle numeric input and canonical period only", () => {
  const payload = policyFormPayload({ elements: {
    enabled: { checked: true },
    free_events_count: { value: "2" },
    counting_period: { value: "calendar_year" },
  } });
  assert.deepEqual(payload, {
    enabled: true,
    free_events_count: 2,
    counting_period: "calendar_year",
  });
});

test("Disabled policy has the required neutral state", () => {
  const markup = damagePolicySummaryMarkup({ policy_enabled: false });
  assert.match(markup, /Policy danni non attiva/);
  assert.match(markup, /senza classificazione rispetto a una soglia/);
});

test("Enabled policy summary shows period count and configured free events", () => {
  const markup = damagePolicySummaryMarkup(enabledState);
  assert.match(markup, /Eventi conteggiabili nel periodo[\s\S]*4/);
  assert.match(markup, /Eventi agevolati previsti[\s\S]*2/);
});

test("Enabled policy summary shows used and over-threshold events", () => {
  const markup = damagePolicySummaryMarkup(enabledState);
  assert.match(markup, /Eventi agevolati utilizzati[\s\S]*2/);
  assert.match(markup, /Eventi oltre soglia[\s\S]*2/);
});

test("Policy summary renders readable bounded dates", () => {
  const markup = damagePolicySummaryMarkup(enabledState);
  assert.match(markup, /Anno solare/);
  assert.match(markup, /01\/01\/2026/);
  assert.match(markup, /31\/12\/2026/);
});

test("Next-event notice remains factual and neutral", () => {
  const markup = damagePolicySummaryMarkup(enabledState);
  assert.match(markup, /Il prossimo evento conteggiabile supererebbe la soglia agevolata configurata\./);
  assert.doesNotMatch(markup, /pagare|multa|sanzione|trattenuta/i);
});

test("Policy configuration microcopy excludes economic enforcement", () => {
  const markup = damagePolicyDialogMarkup();
  assert.match(markup, /Non determina automaticamente responsabilità economiche o disciplinari/);
  assert.doesNotMatch(markup, /pagamento|multa|trattenuta/i);
});

test("Fleet Damage workspace mounts the compact policy dialog", async () => {
  const workspace = await file("assets/js/modules/damage-workspace.js");
  assert.match(workspace, /data-damage-policy-open>Policy danni/);
  assert.match(workspace, /damagePolicyDialogMarkup/);
  assert.match(workspace, /mountDamagePolicy/);
});

test("Driver history includes policy only for a selected canonical driver", () => {
  const driver = { workforce_member_id: 7, display_name: "Mario Rossi" };
  assert.match(damageDriverHistoryMarkup(driver, {}, enabledState), /Policy danni/);
  assert.doesNotMatch(
    damageDriverHistoryMarkup({ ...driver, unassigned: true }, {}, enabledState),
    /Policy danni/,
  );
});

test("Workforce summary remains free from policy details", async () => {
  const workforce = await file("assets/js/modules/workforce-damage-summary.js");
  assert.doesNotMatch(workforce, /policy|soglia|eventi liberi/i);
});

test("Policy UI is bounded on desktop tablet and 390px mobile", async () => {
  const css = await file("assets/css/damage-workspace.css");
  assert.match(css, /\.damage-policy-dialog[\s\S]*width: min\(520px, calc\(100vw - 32px\)\)/);
  assert.match(css, /@media \(max-width: 900px\)[\s\S]*\.damage-policy-summary dl/);
  assert.match(css, /@media \(max-width: 480px\)[\s\S]*\.damage-policy-dialog/);
  assert.match(css, /width: calc\(100vw - 20px\)/);
  assert.doesNotMatch(css, /\.damage-policy-(?:dialog|summary)[^{]*\{[^}]*min-width:\s*[4-9]\d{2}px/);
});
