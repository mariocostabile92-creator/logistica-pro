export const WORKFORCE_SECTIONS = Object.freeze({
  PLANNING: "planning",
  PEOPLE: "people",
  DATA: "data",
});

export const WORKFORCE_SECTION_ORDER = Object.freeze([
  WORKFORCE_SECTIONS.PLANNING,
  WORKFORCE_SECTIONS.PEOPLE,
  WORKFORCE_SECTIONS.DATA,
]);


export function normalizeWorkforceSection(value) {
  return WORKFORCE_SECTION_ORDER.includes(value)
    ? value
    : WORKFORCE_SECTIONS.PLANNING;
}


export function workforceSectionFromLocation(location = window.location) {
  return normalizeWorkforceSection(
    new URL(location.href).searchParams.get("workforce"),
  );
}


export function writeWorkforceSection(
  section,
  {
    mode = "push",
    history = window.history,
    location = window.location,
  } = {},
) {
  const normalized = normalizeWorkforceSection(section);
  const url = new URL(location.href);
  url.searchParams.set("workforce", normalized);
  const method = mode === "replace" ? "replaceState" : "pushState";
  history[method]({ ...history.state, workforce: normalized }, "", url);
  return normalized;
}


export function nextWorkforceSection(current, key) {
  const currentIndex = WORKFORCE_SECTION_ORDER.indexOf(
    normalizeWorkforceSection(current),
  );
  if (key === "Home") return WORKFORCE_SECTION_ORDER[0];
  if (key === "End") return WORKFORCE_SECTION_ORDER.at(-1);
  const direction = key === "ArrowRight" ? 1 : -1;
  return WORKFORCE_SECTION_ORDER[
    (currentIndex + direction + WORKFORCE_SECTION_ORDER.length)
      % WORKFORCE_SECTION_ORDER.length
  ];
}
