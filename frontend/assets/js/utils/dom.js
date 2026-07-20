export function byId(id) {
  return document.getElementById(id);
}


export function setText(id, value) {
  byId(id).textContent = value;
}


export function setMessage(message, tone = "error") {
  const element = byId("message");
  element.textContent = message || "";
  element.hidden = !message;
  element.className = `message ${tone}`;
  element.setAttribute("role", tone === "error" ? "alert" : "status");
}


export function setLoading(button, isLoading, label) {
  button.disabled = isLoading;
  if (!button.dataset.label) button.dataset.label = button.textContent;
  button.textContent = isLoading ? label : button.dataset.label;
  if (isLoading) {
    button.dataset.loading = "true";
  } else {
    delete button.dataset.loading;
  }
}


export function renderViewState(
  container,
  {
    state = "empty",
    title = "",
    description = "",
    actionLabel = "",
    action = "",
  } = {},
) {
  container.hidden = false;
  container.className = `view-state ${state}`;
  container.setAttribute("aria-busy", String(state === "loading"));
  if (state === "loading") {
    container.innerHTML = `
      <span class="visually-hidden">${escapeHtml(title || "Caricamento in corso")}</span>
      <div class="skeleton-grid" aria-hidden="true">
        <span class="skeleton-block"></span>
        <span class="skeleton-block"></span>
        <span class="skeleton-block"></span>
      </div>
      <span class="skeleton-line" aria-hidden="true"></span>
    `;
    return;
  }
  container.innerHTML = `
    <div class="view-state-copy">
      <strong>${escapeHtml(title)}</strong>
      <p>${escapeHtml(description)}</p>
    </div>
    ${actionLabel ? `
      <button
        type="button"
        class="secondary view-state-action"
        data-view-action="${escapeHtml(action)}"
      >
        ${escapeHtml(actionLabel)}
      </button>
    ` : ""}
  `;
}


export function showDataView(stateId, dataId, showData) {
  byId(stateId).hidden = showData;
  byId(dataId).hidden = !showData;
}


export function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
