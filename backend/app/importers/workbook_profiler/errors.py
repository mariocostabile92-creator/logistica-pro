from app.importers.workbook_profiler.models import ProfileIssue


class WorkbookProfileError(ValueError):
    code = "WORKBOOK_PROFILE_ERROR"


class WorkbookReadError(WorkbookProfileError):
    code = "WORKBOOK_NOT_READABLE"


class WorkbookSelectionError(WorkbookProfileError):
    code = "INVALID_WORKBOOK_SELECTION"


class WorkbookImportBlockedError(WorkbookProfileError):
    code = "WORKBOOK_IMPORT_BLOCKED"

    def __init__(self, issues: list[ProfileIssue]):
        self.issues = issues
        message = (
            issues[0].message
            if issues
            else "Il workbook non puo alimentare questo flusso."
        )
        super().__init__(message)
