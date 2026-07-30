export function bindDossierNavigation(container, handlers) {
  container.onclick = event => {
    const action = event.target.closest("[data-dossier-action]")?.dataset.dossierAction;
    if (action && handlers[action]) {
      handlers[action](event.target.closest("[data-dossier-action]").dataset);
      return;
    }
    const source = event.target.closest("[data-dossier-source]");
    if (source) handlers.openSource?.(source.dataset.dossierSource, source.dataset.dossierSourceId);
  };
}

