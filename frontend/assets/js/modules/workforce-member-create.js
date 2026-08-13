import { createWorkforceMember } from "../api.js?v=19";
import { byId, setLoading } from "../utils/dom.js";


export function operationalCycleLabel(value) {
  return ({
    NEXT_DAY: "Next Day",
    SAME_DAY: "Same Day",
    NOT_SET: "Non impostato",
  })[value] || "Non impostato";
}


export function initWorkforceMemberCreate({ onCreated, onError }) {
  const dialog = byId("workforceMemberCreateDialog");
  const form = byId("workforceMemberCreateForm");

  function close() {
    if (dialog.open) dialog.close();
  }

  byId("workforceNewMemberBtn").addEventListener("click", () => {
    form.reset();
    byId("workforceNewOperationalCycle").value = "NOT_SET";
    byId("workforceNewMemberActive").value = "true";
    dialog.showModal();
    byId("workforceNewFirstName").focus();
  });
  byId("workforceNewMemberClose").addEventListener("click", close);
  byId("workforceNewMemberCancel").addEventListener("click", close);
  dialog.addEventListener("cancel", (event) => {
    event.preventDefault();
    close();
  });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submit = event.submitter || byId("workforceNewMemberSave");
    setLoading(submit, true, "Creazione...");
    try {
      const member = await createWorkforceMember({
        first_name: byId("workforceNewFirstName").value.trim(),
        last_name: byId("workforceNewLastName").value.trim(),
        external_identifier: byId("workforceNewExternalId").value.trim() || null,
        phone: byId("workforceNewPhone").value.trim() || null,
        email: byId("workforceNewEmail").value.trim() || null,
        employment_type: byId("workforceNewEmploymentType").value.trim() || null,
        active: byId("workforceNewMemberActive").value === "true",
        operational_cycle: byId("workforceNewOperationalCycle").value,
        operational_notes: byId("workforceNewNotes").value.trim() || null,
      });
      close();
      await onCreated(member);
    } catch (error) {
      onError(error);
    } finally {
      setLoading(submit, false);
    }
  });

  return { close };
}
