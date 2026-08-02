const RETIREMENT_WORKER_URL = "/app/sw.js?v=3";

export function retireLegacyServiceWorker() {
  if (!("serviceWorker" in navigator) || location.protocol === "file:") return;
  navigator.serviceWorker.getRegistrations().then((registrations) => {
    const hasApplicationWorker = registrations.some(
      (registration) => new URL(registration.scope).pathname.startsWith("/app/"),
    );
    if (!hasApplicationWorker) return null;
    return navigator.serviceWorker.register(RETIREMENT_WORKER_URL, {
      scope: "/app/",
      updateViaCache: "none",
    });
  }).catch(() => {
    // Retirement is best-effort and never blocks the administrative workspace.
  });
}
