export function isAbortError(error) {
  return error?.name === "AbortError";
}


export function createSnapshotCache({ ttlMs = 30000 } = {}) {
  let cachedValue = null;
  let cachedAt = 0;
  let inFlight = null;
  let controller = null;
  let requestVersion = 0;

  function isFresh(now = Date.now()) {
    return cachedValue !== null && now - cachedAt < ttlMs;
  }

  function peek() {
    return {
      value: cachedValue,
      timestamp: cachedAt,
      fresh: isFresh(),
    };
  }

  function write(value, timestamp = Date.now()) {
    cachedValue = value;
    cachedAt = timestamp;
    return value;
  }

  function abort() {
    requestVersion += 1;
    controller?.abort();
    controller = null;
    inFlight = null;
  }

  function invalidate({ abortRequest = false } = {}) {
    cachedAt = 0;
    if (abortRequest) abort();
  }

  async function read(loader, { force = false } = {}) {
    if (!force && isFresh()) {
      return { value: cachedValue, timestamp: cachedAt, fromCache: true };
    }
    if (inFlight && !force) return inFlight;
    if (force && inFlight) abort();

    const version = ++requestVersion;
    controller = new AbortController();
    const activeController = controller;
    const request = Promise.resolve(loader({ signal: activeController.signal }))
      .then((value) => {
        if (version !== requestVersion) {
          throw new DOMException("Richiesta obsoleta", "AbortError");
        }
        write(value);
        return { value, timestamp: cachedAt, fromCache: false };
      })
      .finally(() => {
        if (version === requestVersion) {
          inFlight = null;
          controller = null;
        }
      });
    inFlight = request;
    return request;
  }

  return {
    abort,
    invalidate,
    isFresh,
    peek,
    read,
    write,
  };
}
