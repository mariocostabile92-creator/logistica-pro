import { bootstrapStatus, registerOrganization } from "./api.js?v=2";

const form = document.getElementById("registerForm");
const message = document.getElementById("registerMessage");

bootstrapStatus().then(({ required }) => {
  if (required) location.replace("/app/bootstrap.html");
}).catch(() => {
  message.textContent = "Impossibile verificare la configurazione iniziale.";
});

form.addEventListener("submit", async event => {
  event.preventDefault();
  if (form.password.value !== form.password_confirmation.value) {
    message.textContent = "Le password non coincidono.";
    form.password_confirmation.focus();
    return;
  }
  const submit = form.querySelector("button[type=submit]");
  submit.disabled = true;
  message.textContent = "Creazione organizzazione in corso…";

  try {
    await registerOrganization({
      organization: {
        name: form.organization_name.value,
        primary_station: form.primary_station.value || null,
        timezone: "Europe/Rome",
        language: "it",
      },
      administrator: {
        first_name: form.first_name.value,
        last_name: form.last_name.value,
        email: form.email.value,
        password: form.password.value,
        password_confirmation: form.password_confirmation.value,
      },
    });
    location.replace("/app/");
  } catch (error) {
    message.textContent = error.message;
    submit.disabled = false;
    if (error.status === 409) form.email.focus();
  }
});
