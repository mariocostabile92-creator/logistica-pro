const loading = document.getElementById("driverShiftsLoading");
const error = document.getElementById("driverShiftsError");
const content = document.getElementById("driverShiftsContent");
const acknowledgeButton = document.getElementById("driverShiftsAcknowledge");
const acknowledgeStatus = document.getElementById("driverShiftsAckStatus");
let token = "";


function extractToken() {
  const params = new URLSearchParams(location.hash.replace(/^#/, ""));
  return params.get("token") || "";
}


function dateLabel(value) {
  return new Intl.DateTimeFormat("it-IT", {
    weekday: "long", day: "numeric", month: "long", year: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${value}T00:00:00Z`));
}


function shortDate(value) {
  return new Intl.DateTimeFormat("it-IT", {
    day: "2-digit", month: "2-digit", year: "numeric", timeZone: "UTC",
  }).format(new Date(`${value}T00:00:00Z`));
}


async function request(path, options = {}) {
  const response = await fetch(path, { ...options, credentials: "omit", cache: "no-store" });
  if (!response.ok) throw new Error("DRIVER_SHIFTS_NOT_AVAILABLE");
  return response.json();
}


function fact(label, value) {
  const item = document.createElement("div");
  const term = document.createElement("dt");
  const detail = document.createElement("dd");
  term.textContent = label;
  detail.textContent = value || "—";
  item.append(term, detail);
  return item;
}


function renderShift(shift) {
  const card = document.createElement("article");
  card.className = "driver-shift-day";
  const header = document.createElement("header");
  const title = document.createElement("strong");
  const state = document.createElement("span");
  title.textContent = dateLabel(shift.operational_date);
  state.textContent = shift.availability ? "Programmato" : "Riposo";
  header.append(title, state);
  const facts = document.createElement("dl");
  facts.append(
    fact("Orario", shift.start_time && shift.end_time ? `${shift.start_time} – ${shift.end_time}` : "Non indicato"),
    fact("Turno", shift.shift || (shift.availability ? "Non indicato" : "Riposo")),
    fact("Station", shift.station || "Non indicata"),
  );
  card.append(header, facts);
  return card;
}


function render(model) {
  loading.hidden = true;
  error.hidden = true;
  content.hidden = false;
  document.getElementById("driverShiftsDriver").textContent = model.driver_name;
  document.getElementById("driverShiftsPeriod").textContent = `${shortDate(model.period_start)} – ${shortDate(model.period_end)}`;
  const list = document.getElementById("driverShiftsList");
  list.replaceChildren(...model.shifts.map(renderShift));
  const acknowledged = model.access_status === "ACKNOWLEDGED";
  acknowledgeButton.disabled = acknowledged;
  acknowledgeButton.textContent = acknowledged ? "Presa visione registrata" : "Ho visto i turni";
  acknowledgeStatus.textContent = acknowledged ? "Presa visione registrata." : "";
}


function showError() {
  loading.hidden = true;
  content.hidden = true;
  error.hidden = false;
}


async function load() {
  token = extractToken();
  if (!token) { showError(); return; }
  try {
    render(await request(`/api/public/driver-shifts/${encodeURIComponent(token)}`));
  } catch { showError(); }
}


acknowledgeButton.addEventListener("click", async () => {
  acknowledgeButton.disabled = true;
  acknowledgeStatus.textContent = "Registrazione in corso…";
  try {
    render(await request(`/api/public/driver-shifts/${encodeURIComponent(token)}/acknowledge`, { method: "POST" }));
  } catch {
    acknowledgeButton.disabled = false;
    acknowledgeStatus.textContent = "Impossibile registrare la presa visione. Riprova.";
  }
});


void load();
