export function scheduleIdle(callback, { timeout = 500 } = {}) {
  if (typeof window.requestIdleCallback === "function") {
    const id = window.requestIdleCallback(callback, { timeout });
    return () => window.cancelIdleCallback(id);
  }
  const id = window.setTimeout(callback, 32);
  return () => window.clearTimeout(id);
}
