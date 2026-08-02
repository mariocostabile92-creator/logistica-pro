export function setText(id, value) {
  const node = document.getElementById(id);
  if (node && node.textContent !== String(value)) node.textContent = value;
}


export function node(tag, className = "", text = "") {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== "") element.textContent = text;
  return element;
}
