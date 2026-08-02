export function renderQuickActions() {
  document.querySelectorAll("[data-mission-target]").forEach((button) => {
    button.setAttribute("aria-label", `${button.textContent.trim()} nel workspace operativo`);
  });
}
