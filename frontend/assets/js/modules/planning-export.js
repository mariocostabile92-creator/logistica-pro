import { downloadPlanningCsv } from "../api.js";
import { state } from "../state.js";
import { byId, setLoading, setMessage } from "../utils/dom.js";


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
      setMessage(error.message);
    } finally {
      setLoading(button, false);
    }
  });
}
