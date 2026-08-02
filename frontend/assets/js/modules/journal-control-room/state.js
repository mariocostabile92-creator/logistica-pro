export const journalControlRoomState = {
  items: [],
  selected: null,
  vehicle_id: null,
  live_filter: "all",
};

export function resetJournalControlRoomState(vehicleId = null) {
  journalControlRoomState.items = [];
  journalControlRoomState.selected = null;
  journalControlRoomState.vehicle_id = vehicleId;
  journalControlRoomState.live_filter = "all";
}
