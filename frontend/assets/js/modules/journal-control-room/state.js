export const journalControlRoomState = {
  items: [],
  selected: null,
  vehicle_id: null,
};

export function resetJournalControlRoomState(vehicleId = null) {
  journalControlRoomState.items = [];
  journalControlRoomState.selected = null;
  journalControlRoomState.vehicle_id = vehicleId;
}
