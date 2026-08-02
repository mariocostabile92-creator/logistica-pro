import {
  createWorkforceConsecutivityOverride,
  getWorkforceConsecutivityPolicy,
  updateWorkforceConsecutivityPolicy,
} from "../../api.js";

let snapshot = null;

function close(id) {
  document.getElementById(id)?.close();
}

async function openPolicy() {
  const dialog = document.getElementById("workforcePolicyDialog");
  const policy = await getWorkforceConsecutivityPolicy();
  document.getElementById("workforcePolicyWarning").value = policy.warning_threshold;
  document.getElementById("workforcePolicyLimit").value = policy.rest_required_threshold;
  document.getElementById("workforcePolicyRestDays").value = policy.rest_break_days;
  dialog.showModal();
}

function openOverride(memberId) {
  const dialog = document.getElementById("workforceOverrideDialog");
  const driver = snapshot?.drivers?.find((item) => item.workforce_member_id === memberId);
  if (!driver) return;
  document.getElementById("workforceOverrideDriver").textContent = driver.display_name;
  document.getElementById("workforceOverrideMemberId").value = memberId;
  document.getElementById("workforceOverrideDate").value = snapshot.operation_date;
  document.getElementById("workforceOverrideUntil").value = snapshot.operation_date;
  dialog.showModal();
}

export function initConsecutivityPresenter() {
  document.getElementById("workforcePolicyOpen")?.addEventListener("click", openPolicy);
  document.getElementById("workforcePolicyClose")?.addEventListener("click", () => close("workforcePolicyDialog"));
  document.getElementById("workforceOverrideClose")?.addEventListener("click", () => close("workforceOverrideDialog"));
  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-workforce-override-open]");
    if (button) openOverride(Number(button.dataset.workforceOverrideOpen));
  });
  document.getElementById("workforcePolicyForm")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    await updateWorkforceConsecutivityPolicy({
      warning_threshold: Number(document.getElementById("workforcePolicyWarning").value),
      rest_required_threshold: Number(document.getElementById("workforcePolicyLimit").value),
      rest_break_days: Number(document.getElementById("workforcePolicyRestDays").value),
    });
    close("workforcePolicyDialog");
    document.dispatchEvent(new CustomEvent("workforce:consecutivity-changed"));
  });
  document.getElementById("workforceOverrideForm")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    await createWorkforceConsecutivityOverride({
      workforce_member_id: Number(document.getElementById("workforceOverrideMemberId").value),
      operation_date: document.getElementById("workforceOverrideDate").value,
      valid_until: document.getElementById("workforceOverrideUntil").value,
      target_callability: document.getElementById("workforceOverrideTarget").value,
      reason: document.getElementById("workforceOverrideReason").value,
    });
    close("workforceOverrideDialog");
    document.dispatchEvent(new CustomEvent("workforce:consecutivity-changed"));
  });
}

export function presentConsecutivity(snapshotValue) {
  snapshot = snapshotValue;
  const policyButton = document.getElementById("workforcePolicyOpen");
  if (policyButton) policyButton.hidden = !snapshot?.permissions?.can_configure_policy;
}
