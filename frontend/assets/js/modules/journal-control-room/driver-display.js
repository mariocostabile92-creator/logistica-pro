const value = candidate => String(candidate || "").trim();

const technicalIdentifier = identifier =>
  /^(?:source-|workforce-)/i.test(identifier);

export function driverDisplayName(item = {}) {
  const visualName = [item.driver_name, item.driver_surname]
    .map(value).filter(Boolean).join(" ");
  if (visualName) return visualName;
  const resolvedName = value(
    item.driver_display_name
    || item.workforce_driver_display_name
    || item.display_name,
  );
  if (resolvedName) return resolvedName;
  const legacyIdentifier = value(item.declared_driver_identifier);
  if (!legacyIdentifier || technicalIdentifier(legacyIdentifier)) {
    return "Driver non disponibile";
  }
  return legacyIdentifier;
}
