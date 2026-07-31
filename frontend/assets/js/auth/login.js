import { login } from "./api.js";

const form = document.getElementById("loginForm");
const message = document.getElementById("loginMessage");

form.addEventListener("submit", async event => {
  event.preventDefault();
  const submit = form.querySelector("button[type=submit]");
  submit.disabled = true;
  message.textContent = "Accesso in corso…";
  try {
    await login({
      email: form.email.value,
      password: form.password.value,
      remember_me: form.remember.checked,
    });
    location.replace("/app/");
  } catch (error) {
    message.textContent = error.message;
    submit.disabled = false;
    form.password.focus();
  }
});
