export function element(tagName, {
  className = "",
  text = null,
  attributes = {},
} = {}) {
  const node = document.createElement(tagName);
  if (className) node.className = className;
  if (text !== null) node.textContent = text;
  Object.entries(attributes).forEach(([name, value]) => {
    node.setAttribute(name, String(value));
  });
  return node;
}


export function setNodeText(node, value) {
  node.textContent = value ?? "";
}


export function formatPlanningDate(value) {
  if (!value) return "Data non collegata";
  const parsed = new Date(`${value}T12:00:00`);
  if (Number.isNaN(parsed.getTime())) return "Data non collegata";
  return new Intl.DateTimeFormat("it-IT", {
    weekday: "long",
    day: "2-digit",
    month: "long",
    year: "numeric",
  }).format(parsed);
}


export function focusRelativeAction(container, current, direction) {
  const actions = [...container.querySelectorAll("button:not(:disabled)")];
  const index = actions.indexOf(current);
  if (index < 0 || actions.length < 2) return;
  const target = (index + direction + actions.length) % actions.length;
  actions[target].focus();
}
