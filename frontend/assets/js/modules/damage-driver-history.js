import { listWorkforceMembers } from "../api.js?v=6";
import { escapeHtml } from "../utils/dom.js";
import { damagePolicySummaryMarkup } from "./damage-policy.js?v=1";

export const ALL_DRIVERS = "all";
export const UNASSIGNED_DRIVER = "unassigned";

export async function loadDamageDriverDirectory() {
  const response = await listWorkforceMembers();
  return [...(response.items || [])].sort((left, right) =>
    String(left.display_name || "").localeCompare(String(right.display_name || ""), "it-IT"));
}

export function normalizeDamageDriverFilter(value, members) {
  if (value === UNASSIGNED_DRIVER) return value;
  const memberId = Number(value);
  return members.some((member) => Number(member.workforce_member_id) === memberId)
    ? String(memberId)
    : ALL_DRIVERS;
}

export function damageDriverQuery(value) {
  if (value === UNASSIGNED_DRIVER) return { driver_unassigned: true };
  const memberId = Number(value);
  return Number.isInteger(memberId) && memberId > 0
    ? { workforce_member_id: memberId }
    : {};
}

export function damageDriverOptionsMarkup(members, selected = ALL_DRIVERS) {
  return [
    `<option value="${ALL_DRIVERS}" ${selected === ALL_DRIVERS ? "selected" : ""}>Tutti i driver</option>`,
    `<option value="${UNASSIGNED_DRIVER}" ${selected === UNASSIGNED_DRIVER ? "selected" : ""}>Driver non attribuito</option>`,
    ...members.map((member) => {
      const value = String(member.workforce_member_id);
      return `<option value="${value}" ${selected === value ? "selected" : ""}>${escapeHtml(member.display_name || "Driver senza nome")}</option>`;
    }),
  ].join("");
}

export function selectedDamageDriver(members, selected) {
  if (selected === UNASSIGNED_DRIVER) {
    return { workforce_member_id: null, display_name: "Driver non attribuito", unassigned: true };
  }
  return members.find(
    (member) => Number(member.workforce_member_id) === Number(selected),
  ) || null;
}

export function damageDriverHistoryMarkup(driver, summary, policyState = null) {
  if (!driver) return "";
  return `<section class="damage-driver-history" aria-label="Storico driver">
    <div><p class="eyebrow">Storico driver</p><h3>${escapeHtml(driver.display_name)}</h3></div>
    <dl>
      <div><dt>Pratiche attribuite</dt><dd>${Number(summary?.total_cases || 0)}</dd></div>
      <div><dt>Aperte</dt><dd>${Number(summary?.open_cases || 0)}</dd></div>
      <div><dt>Chiuse</dt><dd>${Number(summary?.closed_cases || 0)}</dd></div>
    </dl>
    ${driver.unassigned ? "" : damagePolicySummaryMarkup(policyState)}
  </section>`;
}

export function damageDriverEmptyMessage(selected) {
  if (selected === UNASSIGNED_DRIVER) return "Nessuna pratica senza attribuzione driver.";
  if (selected !== ALL_DRIVERS) return "Nessuna pratica danno attribuita a questo driver.";
  return null;
}
