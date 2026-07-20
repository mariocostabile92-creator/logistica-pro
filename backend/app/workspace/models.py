from enum import Enum


class WorkspaceState(str, Enum):
    EMPTY = "EMPTY"
    DEMO = "DEMO"
    PRODUCTION = "PRODUCTION"


class WorkspaceAction(str, Enum):
    IMPORT_DATA = "import_data"
    LOAD_DEMO = "load_demo"
    IMPORT_REAL_DATA = "import_real_data"
    IMPORT_NEW_DATA = "import_new_data"
    RESET_WORKSPACE = "reset_workspace"
    NEW_OPERATIONAL_DAY = "new_operational_day"
