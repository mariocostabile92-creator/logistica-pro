import { bootstrap, bootstrapStatus } from "./api.js";

const form = document.getElementById("bootstrapForm");
const panels = [...document.querySelectorAll("[data-bootstrap-step]")];
const message = document.getElementById("bootstrapMessage");
let step = 0;
const escape = value => String(value).replace(/[&<>'"]/g, char => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
}[char]));

function showStep(next) {
  step = Math.max(0, Math.min(panels.length - 1, next));
  panels.forEach((panel, index) => { panel.hidden = index !== step; });
  document.getElementById("bootstrapProgress").textContent = `Passaggio ${step + 1} di ${panels.length}`;
}

function payload() {
  return {
    organization: { name: form.organizationName.value.trim(),
      primary_station: form.primaryStation.value.trim() || null,
      timezone: form.timezone.value, language: form.language.value },
    administrator: { first_name: form.firstName.value.trim(),
      last_name: form.lastName.value.trim(), email: form.email.value.trim(),
      password: form.password.value,
      password_confirmation: form.passwordConfirmation.value },
  };
}

function validateCurrent() {
  return [...panels[step].querySelectorAll("input,select")]
    .every(control => control.reportValidity());
}

document.addEventListener("click", event => {
  const action = event.target.closest("[data-bootstrap-action]")?.dataset.bootstrapAction;
  if (action === "next" && validateCurrent()) showStep(step + 1);
  if (action === "back") showStep(step - 1);
  if (action === "review" && validateCurrent()) {
    const data = payload();
    document.getElementById("bootstrapReview").innerHTML = `
      <strong>${escape(data.organization.name)}</strong><span>${escape(data.organization.timezone)} · ${escape(data.organization.language)}</span>
      <strong>${escape(data.administrator.first_name)} ${escape(data.administrator.last_name)}</strong><span>${escape(data.administrator.email)} · Administrator</span>`;
    showStep(3);
  }
});

form.addEventListener("submit", async event => {
  event.preventDefault();
  const button = form.querySelector("button[type=submit]");
  button.disabled = true;
  message.textContent = "Creazione dell'organizzazione in corso…";
  try { await bootstrap(payload()); location.replace("/app/"); }
  catch (error) { message.textContent = error.message; button.disabled = false; }
});

bootstrapStatus().then(({ required }) => {
  if (!required) location.replace("/app/login.html");
}).catch(() => { message.textContent = "Impossibile verificare il primo avvio."; });
showStep(0);
