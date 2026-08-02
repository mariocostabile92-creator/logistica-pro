export function archiveViewModeSwitcher(mode) {
  return `<div class="gdb-view-switcher" role="group" aria-label="Modalità di consultazione">
    <button type="button" data-gdb-view-mode="list" class="${mode === "list" ? "active" : ""}" aria-pressed="${mode === "list"}">Elenco</button>
    <button type="button" data-gdb-view-mode="timeline" class="${mode === "timeline" ? "active" : ""}" aria-pressed="${mode === "timeline"}">Timeline</button>
  </div>`;
}
