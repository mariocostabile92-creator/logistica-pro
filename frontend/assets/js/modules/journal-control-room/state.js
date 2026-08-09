export const journalControlRoomState = {
  items: [],
  selected: null,
  vehicle_id: null,
  operation_date: null,
  live_filter: "all",
  completion_filter: "all",
};

export function resetJournalControlRoomState(vehicleId = null, operationDate = null) {
  journalControlRoomState.items = [];
  journalControlRoomState.selected = null;
  journalControlRoomState.vehicle_id = vehicleId;
  journalControlRoomState.operation_date = operationDate;
  journalControlRoomState.live_filter = "all";
  journalControlRoomState.completion_filter = "all";
}
