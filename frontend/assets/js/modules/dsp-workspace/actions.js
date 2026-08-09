import { can } from "../../auth/state.js";


export const SIGNAL_ACTIONS = Object.freeze({
  DRIVER_WITHOUT_VEHICLE: "planning",
  DRIVER_NOT_AVAILABLE: "driver",
  VEHICLE_NOT_AVAILABLE: "vehicle",
  JOURNAL_CHECKOUT_MISSING: "journal",
  JOURNAL_CHECKIN_MISSING: "journal",
  JOURNAL_ANOMALY: "journal",
  JOURNAL_IN_PROGRESS: "journal",
  OPEN_DAMAGE_CASE: "damage",
  VEHICLE_BLOCKED_BY_DAMAGE: "damage",
  HIGH_SEVERITY_DAMAGE: "damage",
});

const ACTION_LABELS = Object.freeze({
  planning: "Apri Planning",
  driver: "Apri driver",
  vehicle: "Apri mezzo",
  journal: "Apri Giornale",
  damage: "Apri danni",
});


function positiveInteger(value) {
  const normalized = Number(value);
  return Number.isInteger(normalized) && normalized > 0 ? normalized : null;
}


function validOperationDate(value) {
  return /^\d{4}-\d{2}-\d{2}$/.test(String(value || ""))
    ? String(value)
    : null;
}


function action(id, detail) {
  return Object.freeze({ id, label: ACTION_LABELS[id], detail: Object.freeze(detail) });
}


function damageAction(row, driverId, vehicleId) {
  const relevantIds = [...new Set(
    (row.damage?.relevant_case_ids || []).map(positiveInteger).filter(Boolean),
  )];
  if (relevantIds.length === 1) {
    return action("damage", { caseId: relevantIds[0] });
  }
  const hasRelevantDamage = relevantIds.length > 1
    || Number(row.damage?.open_cases_count || 0) > 0;
  if (!hasRelevantDamage || (!driverId && !vehicleId)) return null;
  return action("damage", {
    ...(driverId ? { driverId } : {}),
    ...(vehicleId ? { vehicleId } : {}),
  });
}


export function buildDspRowActions(row, {
  operationDate = row?.operation_date,
  canPermission = can,
} = {}) {
  const actions = [];
  const date = validOperationDate(operationDate);
  const driverId = positiveInteger(row?.driver?.workforce_member_id);
  const vehicleId = positiveInteger(row?.vehicle?.fleet_asset_id);

  if (date && canPermission("planning:read")) {
    actions.push(action("planning", { operationDate: date }));
  }
  if (driverId && canPermission("workforce:read")) {
    actions.push(action("driver", { driverId }));
  }
  if (vehicleId && canPermission("fleet:read")) {
    actions.push(action("vehicle", { assetId: vehicleId }));
  }
  if (date && row?.journal?.available !== false && canPermission("journal:read")) {
    actions.push(action("journal", {
      operationDate: date,
      ...(vehicleId ? { vehicleId } : {}),
      ...(driverId ? { driverId } : {}),
    }));
  }
  if (canPermission("fleet:read")) {
    const damage = damageAction(row, driverId, vehicleId);
    if (damage) actions.push(damage);
  }

  const byId = new Map(actions.map((item) => [item.id, item]));
  const primary = (row?.signals || [])
    .map((signal) => byId.get(SIGNAL_ACTIONS[signal.code]))
    .find(Boolean) || null;
  return Object.freeze({
    primary,
    secondary: Object.freeze(actions.filter((item) => item !== primary)),
    all: Object.freeze(actions),
  });
}


function navigateThen(target, view, eventName, detail) {
  const onViewChanged = (event) => {
    if (event.detail?.view !== view) return;
    target.removeEventListener("workspace:view-changed", onViewChanged);
    target.dispatchEvent(new CustomEvent(eventName, { detail }));
  };
  target.addEventListener("workspace:view-changed", onViewChanged);
  target.dispatchEvent(new CustomEvent("workspace:navigate", {
    detail: { view },
  }));
}


export function dispatchDspAction(selectedAction, target = document) {
  if (!selectedAction?.id) return false;
  const detail = selectedAction.detail || {};
  if (selectedAction.id === "planning") {
    navigateThen(target, "operations", "planning:open-date", {
      operationDate: detail.operationDate,
    });
    return true;
  }
  if (selectedAction.id === "driver") {
    target.dispatchEvent(new CustomEvent("workspace:navigate", {
      detail: { view: "workforce", driverId: detail.driverId },
    }));
    return true;
  }
  if (selectedAction.id === "vehicle") {
    navigateThen(target, "fleet", "fleet:vehicle-open", {
      assetId: detail.assetId,
    });
    return true;
  }
  if (selectedAction.id === "journal") {
    navigateThen(target, "fleet", "journal:open", {
      operation_date: detail.operationDate,
      vehicle_id: detail.vehicleId || null,
      driver_id: detail.driverId || null,
    });
    return true;
  }
  if (selectedAction.id === "damage") {
    navigateThen(target, "fleet", "damage:open", detail);
    return true;
  }
  return false;
}
