import { changeVehicleOperationalStatus } from "../api.js";


export const OPERATIONAL_STATUS_OPTIONS = Object.freeze([
  ["disponibile", "Disponibile"],
  ["disponibile_con_limitazioni", "Disponibile con limitazioni"],
  ["indisponibile", "Indisponibile"],
  ["in_manutenzione", "In manutenzione"],
  ["in_officina", "In officina"],
]);

const label = (value) => (
  OPERATIONAL_STATUS_OPTIONS.find(([key]) => key === value)?.[1]
  || "Non classificato"
);

function ensureDialog() {
  let dialog = document.getElementById("operationalStatusControl");
  if (dialog) return dialog;
  dialog = document.createElement("dialog");
  dialog.id = "operationalStatusControl";
  dialog.className = "assignment-editor fleet-dialog";
  dialog.innerHTML = `
    <form id="operationalStatusControlForm" method="dialog">
      <div class="editor-heading">
        <div><p class="eyebrow">Fleet Operations</p><h3>Modifica stato operativo</h3></div>
        <button type="button" class="icon-button" data-operational-close aria-label="Chiudi">&times;</button>
      </div>
      <dl class="damage-form">
        <div><dt>Stato attuale</dt><dd data-operational-current>—</dd></div>
        <div data-operational-case-wrap hidden><dt>Pratica collegata</dt><dd data-operational-case>—</dd></div>
      </dl>
      <label>Nuovo stato<select name="status" required></select></label>
      <label>Motivazione<textarea name="reason" rows="3" maxlength="2000" required></textarea></label>
      <p class="section-note" data-operational-warning role="alert" hidden></p>
      <label data-operational-override-wrap hidden>
        <input name="override_restriction" type="checkbox" />
        Confermo la modifica nonostante la pratica aperta
      </label>
      <p class="section-note" data-operational-result role="status" aria-live="polite"></p>
      <div class="editor-actions">
        <button type="button" class="secondary" data-operational-close>Annulla</button>
        <button type="submit">Conferma</button>
      </div>
    </form>`;
  document.body.append(dialog);
  return dialog;
}

export function openOperationalStatusControl({
  asset,
  origin,
  linkedCase = null,
  actor = "fleet_manager",
  onChanged = () => {},
}) {
  const dialog = ensureDialog();
  const form = dialog.querySelector("form");
  form.reset();
  form.elements.status.innerHTML = OPERATIONAL_STATUS_OPTIONS.map(
    ([value, text]) => `<option value="${value}" ${value === asset.availability ? "selected" : ""}>${text}</option>`,
  ).join("");
  dialog.querySelector("[data-operational-current]").textContent =
    label(asset.availability);
  const caseWrap = dialog.querySelector("[data-operational-case-wrap]");
  caseWrap.hidden = !linkedCase;
  dialog.querySelector("[data-operational-case]").textContent =
    linkedCase?.case_number || "Nessuna";
  const warning = dialog.querySelector("[data-operational-warning]");
  const overrideWrap = dialog.querySelector("[data-operational-override-wrap]");
  const result = dialog.querySelector("[data-operational-result]");
  warning.hidden = true;
  overrideWrap.hidden = true;
  result.textContent = "";

  dialog.querySelectorAll("[data-operational-close]").forEach((button) => {
    button.onclick = () => dialog.close();
  });
  form.onsubmit = async (event) => {
    event.preventDefault();
    const submit = event.submitter;
    submit.disabled = true;
    result.textContent = "Aggiornamento in corso…";
    const values = Object.fromEntries(new FormData(form).entries());
    try {
      const response = await changeVehicleOperationalStatus(asset.id, {
        status: values.status,
        reason: values.reason,
        origin,
        actor,
        override_restriction: values.override_restriction === "on",
      });
      document.dispatchEvent(new CustomEvent("fleet:operational-status-changed", {
        detail: response,
      }));
      document.dispatchEvent(new CustomEvent("planning:availability-changed", {
        detail: { vehicleId: asset.id, availability: response.new_status },
      }));
      await onChanged(response);
      dialog.close();
    } catch (error) {
      if (error.status === 409) {
        warning.textContent = error.message;
        warning.hidden = false;
        overrideWrap.hidden = false;
      }
      result.textContent = error.message;
    } finally {
      submit.disabled = false;
    }
  };
  dialog.showModal();
}
