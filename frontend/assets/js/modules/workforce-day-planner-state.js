export function createWorkforceDayPlannerState(initialDate = "") {
  return {
    focusedDate: initialDate,
    cycleFilter: "all",
    assignmentFilter: "all",
    activityFilter: "all",
    search: "",
    selectedMemberIds: new Set(),
    expandedMemberId: null,
    loading: false,
  };
}


export function focusWorkforcePlanningDay(state, date) {
  return {
    ...state,
    focusedDate: date,
    selectedMemberIds: new Set(),
    expandedMemberId: null,
  };
}


export function toggleWorkforcePlanningMember(state, memberId) {
  const selectedMemberIds = new Set(state.selectedMemberIds);
  if (selectedMemberIds.has(memberId)) selectedMemberIds.delete(memberId);
  else selectedMemberIds.add(memberId);
  return { ...state, selectedMemberIds };
}


export function clearWorkforcePlanningSelection(state) {
  return { ...state, selectedMemberIds: new Set(), expandedMemberId: null };
}
