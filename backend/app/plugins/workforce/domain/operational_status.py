ABSENCE_STATUS_CODES = frozenset({
    "holiday",
    "sickness",
    "leave",
    "unavailable",
})

NON_OPERATIONAL_STATUS_CODES = ABSENCE_STATUS_CODES | frozenset({
    "rest",
    "unknown",
})
