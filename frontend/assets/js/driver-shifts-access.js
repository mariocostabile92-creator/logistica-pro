const loading = document.getElementById("driverShiftsAccessLoading");
const content = document.getElementById("driverShiftsAccessContent");
const success = document.getElementById("driverShiftsAccessSuccess");
const error = document.getElementById("driverShiftsAccessError");
const form = document.getElementById("driverShiftsLoginForm");
const loginError = document.getElementById("driverShiftsLoginError");
const submit = document.getElementById("driverShiftsLoginSubmit");
const logout = document.getElementById("driverShiftsLogout");
const welcome = document.getElementById("driverShiftsWelcome");
const period = document.getElementById("driverShiftsPeriod");


export function tokenFromFragment(fragment = location.hash) {
  const params = new URLSearchParams(fragment.replace(/^#/, ""));
  return params.get("token") || "";
}


function show(target) {
  [loading, content, success, error].forEach((section) => {
    section.hidden = section !== target;
  });
}


function renderSession(session) {
  welcome.textContent = `Ciao, ${session.driver_name}`;
  period.textContent = `Periodo ${session.period_start} – ${session.period_end}`;
  show(success);
}


async function currentSession() {
  const response = await fetch("/api/public/driver-shifts/me", {
    credentials: "include",
    cache: "no-store",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) return false;
  renderSession(await response.json());
  return true;
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
  try {
    if (await currentSession()) return;
  } catch {
    // A missing/expired session is expected on first access.
  }
  await validatePortal();
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
    renderSession(await response.json());
  } catch {
    loginError.hidden = false;
  } finally {
    submit.disabled = false;
    submit.textContent = "Accedi";
  }
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
