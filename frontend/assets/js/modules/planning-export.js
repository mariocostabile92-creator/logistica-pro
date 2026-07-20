import { downloadPlanningCsv } from "../api.js";
import { state } from "../state.js";
import { byId, setLoading, setMessage } from "../utils/dom.js";
import { userErrorPresentation } from "../utils/errors.js";


export function initPlanningExport() {
  const button = byId("exportPlanningBtn");
  button.addEventListener("click", async () => {
    const planningId = state.planningOperational.data?.planning?.id;
    if (!planningId) return;
    setLoading(button, true, "Export...");
    try {
      await downloadPlanningCsv(planningId);
      setMessage("");
    } catch (error) {
      const presentation = userErrorPresentation("planning.export", error);
      setMessage(presentation.message, presentation.tone);
    } finally {
      setLoading(button, false);
    }
  });
}
