class WorkforceValidationError(ValueError):
    pass


class WorkforceMemberNotFoundError(LookupError):
    pass


class WorkforceStatusNotFoundError(LookupError):
    pass


class WorkforceDayMemberBatchConflictError(ValueError):
    code = "WORKFORCE_DAY_MEMBER_BATCH_CONFIRMATION_REQUIRED"

    def __init__(self, message: str, details: dict[str, object]):
        super().__init__(message)
        self.details = details


class WorkforceImportError(ValueError):
    code = "WORKFORCE_IMPORT_INVALID"


class WorkforceImportConfirmationError(WorkforceImportError):
    code = "WORKFORCE_IMPORT_CONFIRMATION_MISMATCH"
