export function setJournalWorkspaceView(root, view) {
  const archive = root.querySelector("[data-jcr-archive]");
  const live = root.querySelector("[data-jcr-live]");
  const showArchive = view === "archive";
  live.hidden = showArchive;
  archive.hidden = !showArchive;
  root.querySelectorAll("[data-jcr-view]").forEach(button => {
    const active = button.dataset.jcrView === view;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
}
