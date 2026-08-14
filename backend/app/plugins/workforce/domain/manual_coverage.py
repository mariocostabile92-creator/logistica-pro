class ManualCoverageError(ValueError):
    code = "MANUAL_COVERAGE_INVALID"


class ManualCoverageConflictError(ManualCoverageError):
    code = "MANUAL_COVERAGE_STALE"


class ManualCoverageBucketError(ManualCoverageError):
    code = "MANUAL_COVERAGE_BUCKET_INVALID"
