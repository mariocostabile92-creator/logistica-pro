const startedAt = performance.now();

export function startAdministrativeBootstrap() {
  document.body.dataset.appState = "bootstrapping";
  performance.mark?.("operations-bootstrap-start");
}

export function revealAdministrativeApp() {
  const header = document.querySelector(".app-header");
  const main = document.querySelector(".app-shell");
  const shell = document.getElementById("appBootstrapShell");
  if (header) header.hidden = false;
  if (main) main.hidden = false;
  if (shell) shell.hidden = true;
  document.body.dataset.appState = "ready";
  document.body.dataset.shellReadyMs = String(Math.round(performance.now() - startedAt));
  performance.mark?.("operations-shell-ready");
  performance.measure?.(
    "operations-bootstrap-to-shell",
    "operations-bootstrap-start",
    "operations-shell-ready",
  );
}

export function failAdministrativeBootstrap() {
  const message = document.getElementById("appBootstrapMessage");
  const retry = document.getElementById("appBootstrapRetry");
  document.body.dataset.appState = "failed";
  if (message) message.textContent = "Impossibile preparare il workspace. Controlla la connessione e riprova.";
  if (retry) {
    retry.hidden = false;
    retry.addEventListener("click", () => location.reload(), { once: true });
  }
}
