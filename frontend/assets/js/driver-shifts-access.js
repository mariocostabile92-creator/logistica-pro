const loading = document.getElementById("driverShiftsAccessLoading");
const content = document.getElementById("driverShiftsAccessContent");
const error = document.getElementById("driverShiftsAccessError");


function tokenFromFragment() {
  const params = new URLSearchParams(location.hash.replace(/^#/, ""));
  return params.get("token") || "";
}


function show(target) {
  loading.hidden = target !== loading;
  content.hidden = target !== content;
  error.hidden = target !== error;
}


async function validate() {
  const token = tokenFromFragment();
  if (!token || token.length > 256) {
    show(error);
    return;
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
  } catch {
    show(error);
  }
}


void validate();
