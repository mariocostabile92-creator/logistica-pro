import {
  planningCoverageBucketDefinitions,
  planningCoverageBucketKey,
  planningCoverageDays,
} from "./workforce-coverage-presenter.js";


const ABSENCE_CODES = new Set(["holiday", "sickness", "leave", "unavailable"]);
const NON_AVAILABLE_CODES = new Set([...ABSENCE_CODES, "rest"]);


export function workforceDayStatusMap(statuses, date) {
  return new Map(
    statuses
      .filter((item) => item.date === date)
      .map((item) => [Number(item.workforce_member_id), item]),
  );
}


function matchesSearch(member, search) {
  const needle = String(search || "").trim().toLocaleLowerCase("it-IT");
  if (!needle) return true;
  return [
    member.display_name,
    member.external_identifier,
    member.transporter_id,
  ].some((value) => String(value || "").toLocaleLowerCase("it-IT").includes(needle));
}


export function filterWorkforceDayMembers(members, statuses, date, filters = {}) {
  const byMember = workforceDayStatusMap(statuses, date);
  return members.filter((member) => {
    const status = byMember.get(Number(member.workforce_member_id));
    const cycle = member.operational_cycle || "NOT_SET";
    const cycleFilter = filters.cycleFilter || "all";
    const assignmentFilter = filters.assignmentFilter || "all";
    if (cycleFilter !== "all" && cycle !== cycleFilter) return false;
    if (assignmentFilter === "unassigned" && status?.status_code === "scheduled") return false;
    if (assignmentFilter === "assigned" && status?.status_code !== "scheduled") return false;
    if (assignmentFilter === "rest" && status?.status_code !== "rest") return false;
    if (assignmentFilter === "absence" && !ABSENCE_CODES.has(status?.status_code)) return false;
    if (
      filters.activityFilter
      && filters.activityFilter !== "all"
      && status?.operational_activity !== filters.activityFilter
    ) return false;
    return matchesSearch(member, filters.search);
  });
}


export function workforceDayCounts(members, statuses, date) {
  const byMember = workforceDayStatusMap(statuses, date);
  const daily = members.map((member) => byMember.get(Number(member.workforce_member_id)));
  return {
    total: members.length,
    assigned: daily.filter((item) => item?.status_code === "scheduled").length,
    unassigned: daily.filter((item) => item?.status_code !== "scheduled").length,
    absent: daily.filter((item) => ABSENCE_CODES.has(item?.status_code)).length,
    available: daily.filter((item) => item?.availability === true).length,
  };
}


export function workforceDayAvailability(status) {
  if (!status) return { label: "Da pianificare", tone: "unknown", warning: false };
  if (status.status_code === "rest") return { label: "Riposo", tone: "rest", warning: true };
  if (ABSENCE_CODES.has(status.status_code)) {
    return { label: "Non disponibile", tone: "unavailable", warning: true };
  }
  return status.availability
    ? { label: "Disponibile", tone: "available", warning: false }
    : { label: "Non disponibile", tone: "unavailable", warning: true };
}


export function workforceDayCoverage(response, date) {
  return planningCoverageDays(response).find((item) => item.date === date) || {
    date,
    buckets: planningCoverageBucketDefinitions().map((bucket) => ({ ...bucket, item: null })),
  };
}


export function workforceWeekProgress(response) {
  return planningCoverageDays(response).map((day) => {
    const available = day.buckets
      .map((bucket) => bucket.item)
      .filter((item) => item && item.coverage_status !== "NO_FORECAST");
    let status = "NO_FORECAST";
    if (available.length) {
      if (available.every((item) => item.coverage_status === "REQUIREMENT_COVERED")) status = "COMPLETE";
      else if (available.every((item) => Number(item.forecast_gap || 0) === 0)) status = "REQUIREMENT_GAP";
      else status = "FORECAST_GAP";
    }
    return { date: day.date, status };
  });
}


export function workforceDayExitWarning(response, date) {
  const items = workforceDayCoverage(response, date).buckets
    .map((bucket) => bucket.item)
    .filter((item) => item && item.coverage_status !== "NO_FORECAST");
  const forecastGap = items.reduce((total, item) => total + Number(item.forecast_gap || 0), 0);
  if (forecastGap > 0) return `Forecast non ancora coperto: mancano ${forecastGap} driver.`;
  const requirementGap = items.reduce((total, item) => total + Number(item.requirement_gap || 0), 0);
  if (requirementGap > 0) return `Forecast coperto, mancano ${requirementGap} driver al requirement +10%.`;
  return "";
}


export function workforceDayBatchPayload({
  date,
  memberIds,
  choice,
  activity,
  notes,
  overwritePolicy,
  confirmOverwrite = false,
  confirmUnavailableOverride = false,
}) {
  const [kind, rawValue = ""] = String(choice || "").split(":", 2);
  const value = rawValue.trim();
  const normalizedMemberIds = memberIds ? [...memberIds] : [];
  if (!date || !normalizedMemberIds.length || !value || !["shift", "status"].includes(kind)) return null;
  return {
    operational_date: date,
    workforce_member_ids: normalizedMemberIds.map(Number).sort((left, right) => left - right),
    status_code: kind === "shift" ? "scheduled" : value,
    shift_code: kind === "shift" ? value : null,
    operational_activity: String(activity || "").trim() || null,
    notes: String(notes || "").trim() || null,
    overwrite_policy: overwritePolicy || "APPLY_TO_EMPTY_ONLY",
    confirm_overwrite: confirmOverwrite,
    confirm_unavailable_override: confirmUnavailableOverride,
    source_reference: "manual_day_planning",
  };
}


export function workforceCoverageImpact(response, date, members, statuses, selectedMemberIds, choice) {
  const [kind, rawCode = ""] = String(choice || "").split(":", 2);
  const shiftCode = kind === "shift" ? rawCode.trim().toUpperCase() : "";
  if (!shiftCode) return [];
  const byMember = workforceDayStatusMap(statuses, date);
  const buckets = new Map(
    workforceDayCoverage(response, date).buckets.map((bucket) => [bucket.key, {
      key: bucket.key,
      label: bucket.label,
      current: Number(bucket.item?.assigned_drivers || 0),
      added: 0,
      requirement: bucket.item?.required_capacity ?? null,
    }]),
  );
  members.filter((member) => selectedMemberIds.has(Number(member.workforce_member_id)))
    .filter((member) => byMember.get(Number(member.workforce_member_id))?.status_code !== "scheduled")
    .forEach((member) => {
      const key = member.operational_cycle === "NEXT_DAY" && ["C1", "L1", "L2", "L3", "VMC1"].includes(shiftCode)
        ? "NEXT_DAY"
        : member.operational_cycle === "SAME_DAY" && shiftCode === "SA" ? "SAME_DAY_A"
          : member.operational_cycle === "SAME_DAY" && shiftCode === "SB" ? "SAME_DAY_B_C" : null;
      if (key && buckets.has(key)) buckets.get(key).added += 1;
    });
  return [...buckets.values()].filter((item) => item.added > 0);
}


export function coverageItemKey(item) {
  return planningCoverageBucketKey(item);
}


export function workforceProtectedStatus(status) {
  return NON_AVAILABLE_CODES.has(status?.status_code);
}
