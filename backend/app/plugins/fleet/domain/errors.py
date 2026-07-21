class AssetIdentifierConflictError(ValueError):
    pass


class FleetSyncError(ValueError):
    code = "FLEET_SYNC_INVALID"


class FleetSyncConfirmationError(FleetSyncError):
    code = "FLEET_SYNC_CONFIRMATION_MISMATCH"


class FleetSyncSelectionError(FleetSyncError):
    code = "FLEET_SYNC_SELECTION_INVALID"
