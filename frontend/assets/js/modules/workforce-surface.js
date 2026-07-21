const FOCUSABLE_SELECTOR = [
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[href]",
  "[tabindex]:not([tabindex='-1'])",
].join(",");


function focusableElements(surface) {
  return [...surface.querySelectorAll(FOCUSABLE_SELECTOR)]
    .filter((element) => (
      !element.hidden
      && !element.closest("[hidden]")
      && element.getAttribute("aria-hidden") !== "true"
    ));
}


export function createWorkforceSurface({
  surface,
  backdrop = null,
  canClose = () => true,
  onClose = () => {},
  lockScroll = false,
}) {
  let previousFocus = null;
  let open = false;

  function hide({ restoreFocus = true } = {}) {
    if (!open) return;
    open = false;
    surface.hidden = true;
    if (backdrop) backdrop.hidden = true;
    document.removeEventListener("keydown", handleKeydown);
    if (lockScroll) document.body.classList.remove("workforce-surface-open");
    onClose();
    if (restoreFocus && previousFocus?.isConnected) previousFocus.focus();
  }

  function requestClose() {
    if (canClose()) hide();
  }

  function handleKeydown(event) {
    if (!open) return;
    if (event.key === "Escape") {
      event.preventDefault();
      requestClose();
      return;
    }
    if (event.key !== "Tab") return;
    const focusable = focusableElements(surface);
    if (!focusable.length) {
      event.preventDefault();
      surface.focus();
      return;
    }
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  function show(initialFocus = null) {
    previousFocus = document.activeElement;
    open = true;
    surface.hidden = false;
    if (backdrop) backdrop.hidden = false;
    if (lockScroll) document.body.classList.add("workforce-surface-open");
    document.addEventListener("keydown", handleKeydown);
    requestAnimationFrame(() => (initialFocus || surface).focus());
  }

  backdrop?.addEventListener("click", requestClose);
  return { show, hide, requestClose, isOpen: () => open };
}
