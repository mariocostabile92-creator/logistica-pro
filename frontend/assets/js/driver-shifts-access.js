import { formatShiftPeriod, renderDriverShiftWeek } from "./driver-shifts-week.js?v=1";


const loading = document.getElementById("driverShiftsAccessLoading");
const content = document.getElementById("driverShiftsAccessContent");
const success = document.getElementById("driverShiftsAccessSuccess");
const error = document.getElementById("driverShiftsAccessError");
const form = document.getElementById("driverShiftsLoginForm");
const loginError = document.getElementById("driverShiftsLoginError");
const submit = document.getElementById("driverShiftsLoginSubmit");
const logout = document.getElementById("driverShiftsLogout");
const driverName = document.getElementById("driverShiftsDriverName");
const period = document.getElementById("driverShiftsPeriod");
const weekStatus = document.getElementById("driverShiftsWeekStatus");
const weekRoot = document.getElementById("driverShiftsWeek");
const weekError = document.getElementById("driverShiftsWeekError");
const weekRetry = document.getElementById("driverShiftsWeekRetry");
const acknowledgement = document.getElementById("driverShiftsAcknowledgement");
const acknowledge = document.getElementById("driverShiftsAcknowledge");
const ackResult = document.getElementById("driverShiftsAckResult");


export function tokenFromFragment(fragment = location.hash) {
  const params = new URLSearchParams(fragment.replace(/^#/, ""));
  return params.get("token") || "";
}


function show(target) {
  [loading, content, success, error].forEach((section) => {
    section.hidden = section !== target;
  });
}


function showWeekLoading() {
  show(success);
  weekStatus.hidden = false;
  weekStatus.textContent = "Caricamento turni…";
  weekRoot.hidden = true;
  weekError.hidden = true;
  acknowledgement.hidden = true;
}


function showWeekFailure() {
  show(success);
  weekStatus.hidden = true;
  weekRoot.hidden = true;
  acknowledgement.hidden = true;
  weekError.hidden = false;
}


function renderAcknowledgement(week) {
  acknowledgement.hidden = false;
  ackResult.hidden = !week.acknowledged;
  acknowledge.hidden = week.acknowledged;
  acknowledge.disabled = false;
}


function renderWeek(week) {
  driverName.textContent = week.driver_name;
  period.textContent = formatShiftPeriod(week.period_start, week.period_end);
  renderDriverShiftWeek(weekRoot, week);
  weekStatus.hidden = true;
  weekError.hidden = true;
  weekRoot.hidden = false;
  renderAcknowledgement(week);
  show(success);
}


async function loadWeek({ initial = false } = {}) {
  if (initial) show(loading);
  else showWeekLoading();
  try {
    const response = await fetch("/api/public/driver-shifts/me/shifts", {
      credentials: "include",
      cache: "no-store",
      headers: { Accept: "application/json" },
    });
    if (response.status === 401) return "invalid";
    if (!response.ok) throw new Error("DRIVER_SHIFT_WEEK_UNAVAILABLE");
    renderWeek(await response.json());
    return "loaded";
  } catch {
    showWeekFailure();
    return "error";
  }
}


async function validatePortal() {
  const token = tokenFromFragment();
  if (!token || token.length > 256) {
    show(error);
    return false;
  }
  try {
    const response = await fetch("/api/public/driver-shifts/access/validate", {
      method: "POST",
      credentials: "omit",
      cache: "no-store",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
    });
    if (!response.ok) throw new Error("DRIVER_SHIFT_PORTAL_NOT_AVAILABLE");
    show(content);
    return true;
  } catch {
    show(error);
    return false;
  }
}


async function initialize() {
  const state = await loadWeek({ initial: true });
  if (state === "invalid") await validatePortal();
}


form.addEventListener("submit", async (event) => {
  event.preventDefault();
  loginError.hidden = true;
  submit.disabled = true;
  submit.textContent = "Accesso in corso…";
  const fields = new FormData(form);
  try {
    const response = await fetch("/api/public/driver-shifts/portal/login", {
      method: "POST",
      credentials: "include",
      cache: "no-store",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({
        portal_token: tokenFromFragment(),
        access_code: String(fields.get("access_code") || ""),
        pin: String(fields.get("pin") || ""),
        remember_device: fields.get("remember_device") === "on",
      }),
    });
    if (!response.ok) throw new Error("DRIVER_SHIFT_LOGIN_INVALID");
    form.reset();
    const state = await loadWeek();
    if (state === "invalid") {
      show(content);
      loginError.hidden = false;
    }
  } catch {
    show(content);
    loginError.hidden = false;
  } finally {
    submit.disabled = false;
    submit.textContent = "Accedi";
  }
});


acknowledge.addEventListener("click", async () => {
  acknowledge.disabled = true;
  try {
    const response = await fetch("/api/public/driver-shifts/me/acknowledge", {
      method: "POST",
      credentials: "include",
      cache: "no-store",
      headers: { Accept: "application/json" },
    });
    if (response.status === 401) {
      await validatePortal();
      return;
    }
    if (!response.ok) throw new Error("DRIVER_SHIFT_ACK_UNAVAILABLE");
    renderWeek(await response.json());
  } catch {
    acknowledge.disabled = false;
    weekStatus.hidden = false;
    weekStatus.textContent = "Impossibile registrare la presa visione. Riprova.";
  }
});


weekRetry.addEventListener("click", async () => {
  const state = await loadWeek();
  if (state === "invalid") await validatePortal();
});


logout.addEventListener("click", async () => {
  logout.disabled = true;
  try {
    await fetch("/api/public/driver-shifts/logout", {
      method: "POST",
      credentials: "include",
      cache: "no-store",
      headers: { Accept: "application/json" },
    });
  } finally {
    logout.disabled = false;
    await validatePortal();
  }
});


void initialize();
