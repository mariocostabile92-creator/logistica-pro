const SERVICE_WORKER_URL = "/app/sw.js?v=1";

export function registerServiceWorker() {
  if (!("serviceWorker" in navigator) || location.protocol === "file:") return;
  navigator.serviceWorker.register(SERVICE_WORKER_URL, {
    scope: "/app/",
    updateViaCache: "none",
  }).catch(() => {
    // PWA support is progressive: application navigation remains network-first.
  });
}
