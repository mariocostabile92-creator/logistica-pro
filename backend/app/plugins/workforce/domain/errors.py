class WorkforceValidationError(ValueError):
    pass


class WorkforceMemberNotFoundError(LookupError):
    pass


class WorkforceStatusNotFoundError(LookupError):
    pass


class WorkforceImportError(ValueError):
    code = "WORKFORCE_IMPORT_INVALID"


class WorkforceImportConfirmationError(WorkforceImportError):
    code = "WORKFORCE_IMPORT_CONFIRMATION_MISMATCH"
