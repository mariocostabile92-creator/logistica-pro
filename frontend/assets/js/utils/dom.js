export function byId(id) {
  return document.getElementById(id);
}


export function setText(id, value) {
  byId(id).textContent = value;
}


export function setMessage(message) {
  byId("message").textContent = message || "";
}


export function setLoading(button, isLoading, label) {
  button.disabled = isLoading;
  if (!button.dataset.label) button.dataset.label = button.textContent;
  button.textContent = isLoading ? label : button.dataset.label;
}


export function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
