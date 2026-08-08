import { getDamagePolicy, updateDamagePolicy } from "../api.js?v=7";
import { escapeHtml } from "../utils/dom.js";

export const DAMAGE_POLICY_PERIODS = {
  all_time: "Sempre",
  calendar_year: "Anno solare",
  rolling_12_months: "Ultimi 12 mesi",
};

export function damagePolicyDialogMarkup() {
  return `<dialog class="damage-policy-dialog" data-damage-policy-dialog aria-labelledby="damagePolicyTitle">
    <form class="damage-policy-form" data-damage-policy-form>
      <header>
        <div><p class="eyebrow">Configurazione Danni</p><h3 id="damagePolicyTitle">Policy danni driver</h3></div>
        <button type="button" class="quiet" data-damage-policy-close aria-label="Chiudi">×</button>
      </header>
      <p class="section-note">La policy aiuta a classificare gli eventi attribuiti al driver. Non determina automaticamente responsabilità economiche o disciplinari.</p>
      <label class="damage-policy-toggle"><input type="checkbox" name="enabled"> Policy attiva</label>
      <label>Eventi agevolati
        <input type="number" name="free_events_count" min="0" step="1" required>
      </label>
      <label>Periodo di conteggio
        <select name="counting_period" required>
          ${Object.entries(DAMAGE_POLICY_PERIODS).map(([value, label]) => `<option value="${value}">${label}</option>`).join("")}
        </select>
      </label>
      <p class="damage-policy-help">Il conteggio considera soltanto pratiche attribuite in modo canonico e non annullate.</p>
      <p class="damage-policy-status" data-damage-policy-status role="status" aria-live="polite"></p>
      <footer>
        <button type="button" class="secondary" data-damage-policy-close>Annulla</button>
        <button type="submit" data-damage-policy-save>Salva policy</button>
      </footer>
    </form>
  </dialog>`;
}

function italianDate(value) {
  if (!value) return "Nessun limite";
  return new Date(`${value}T00:00:00`).toLocaleDateString("it-IT");
}

export function damagePolicySummaryMarkup(state) {
  if (!state) return "";
  if (state.policy_load_error) {
    return `<section class="damage-policy-summary is-disabled" aria-label="Policy danni driver">
      <strong>Dati policy non disponibili</strong>
      <p>Lo storico pratiche resta consultabile.</p>
    </section>`;
  }
  if (!state.policy_enabled) {
    return `<section class="damage-policy-summary is-disabled" aria-label="Policy danni driver">
      <strong>Policy danni non attiva</strong>
      <p>Lo storico resta disponibile senza classificazione rispetto a una soglia.</p>
    </section>`;
  }
  const period = DAMAGE_POLICY_PERIODS[state.counting_period] || "Periodo configurato";
  return `<section class="damage-policy-summary" aria-label="Policy danni driver">
    <div><p class="eyebrow">Policy danni</p><h4>${escapeHtml(period)}</h4></div>
    <dl>
      <div><dt>Eventi conteggiabili nel periodo</dt><dd>${Number(state.countable_cases || 0)}</dd></div>
      <div><dt>Eventi agevolati previsti</dt><dd>${Number(state.free_events_count || 0)}</dd></div>
      <div><dt>Eventi agevolati utilizzati</dt><dd>${Number(state.free_events_used || 0)}</dd></div>
      <div><dt>Eventi oltre soglia</dt><dd>${Number(state.events_over_threshold || 0)}</dd></div>
    </dl>
    <p class="damage-policy-period">Periodo: ${escapeHtml(italianDate(state.period_start))} – ${escapeHtml(italianDate(state.period_end))}</p>
    ${state.next_event_is_over_threshold ? '<p class="damage-policy-notice">Il prossimo evento conteggiabile supererebbe la soglia agevolata configurata.</p>' : ""}
  </section>`;
}

export function policyFormPayload(form) {
  return {
    enabled: Boolean(form.elements.enabled.checked),
    free_events_count: Number(form.elements.free_events_count.value),
    counting_period: String(form.elements.counting_period.value),
  };
}

export function fillDamagePolicyForm(form, policy) {
  form.elements.enabled.checked = Boolean(policy.enabled);
  form.elements.free_events_count.value = String(policy.free_events_count ?? 0);
  form.elements.counting_period.value = policy.counting_period || "all_time";
}

export function createDamagePolicyController({
  dialog,
  opener,
  loadPolicy = getDamagePolicy,
  savePolicy = updateDamagePolicy,
}) {
  const form = dialog.querySelector("[data-damage-policy-form]");
  const status = dialog.querySelector("[data-damage-policy-status]");
  const saveButton = dialog.querySelector("[data-damage-policy-save]");
  let current = null;

  function setStatus(message, kind = "") {
    status.textContent = message;
    status.dataset.state = kind;
  }

  function fill(policy) {
    fillDamagePolicyForm(form, policy);
  }

  async function open() {
    setStatus("Caricamento configurazione…", "loading");
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
    try {
      current = await loadPolicy();
      fill(current);
      setStatus("");
    } catch (error) {
      setStatus(error.message || "Impossibile caricare la policy danni.", "error");
    }
  }

  function close() {
    if (typeof dialog.close === "function") dialog.close();
    else dialog.removeAttribute("open");
  }

  async function submit(event) {
    event.preventDefault();
    saveButton.disabled = true;
    setStatus("Salvataggio in corso…", "saving");
    try {
      current = await savePolicy(policyFormPayload(form));
      fill(current);
      setStatus("Policy salvata.", "success");
    } catch (error) {
      setStatus(error.message || "Impossibile salvare la policy danni.", "error");
    } finally {
      saveButton.disabled = false;
    }
  }

  const closeButtons = [...dialog.querySelectorAll("[data-damage-policy-close]")];
  opener.addEventListener("click", open);
  closeButtons.forEach((button) => button.addEventListener("click", close));
  form.addEventListener("submit", submit);

  return {
    open,
    current: () => current,
    destroy() {
      opener.removeEventListener("click", open);
      closeButtons.forEach((button) => button.removeEventListener("click", close));
      form.removeEventListener("submit", submit);
    },
  };
}

export function mountDamagePolicy(root) {
  const dialog = root.querySelector("[data-damage-policy-dialog]");
  const opener = root.querySelector("[data-damage-policy-open]");
  if (!dialog || !opener) return null;
  return createDamagePolicyController({ dialog, opener });
}
