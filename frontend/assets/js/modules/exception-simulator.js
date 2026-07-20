import { applyPlanningEvent, simulatePlanningEvent } from "../api.js";
import { changeDiff } from "../components/change-diff.js";
import { state } from "../state.js";
import { byId, setLoading, setMessage } from "../utils/dom.js";
import {
  ExpectedUserError,
  userErrorPresentation,
} from "../utils/errors.js";


let onPlanningUpdated = null;


function showSimulationError(context, error) {
  const presentation = userErrorPresentation(context, error);
  setMessage(presentation.message, presentation.tone);
}


function entityTypeFor(eventType) {
  if (eventType === "driver_absent") return "driver";
  if (eventType === "vehicle_unavailable") return "vehicle";
  return "route";
}


function currentRequest() {
  const eventType = byId("eventType").value;
  return {
    event_type: eventType,
    entity_type: entityTypeFor(eventType),
    entity_id: byId("eventEntityId").value.trim(),
    reason: byId("eventReason").value.trim(),
  };
}


async function runSimulation() {
  const planningId = state.planningOperational.data?.planning?.id;
  if (!planningId) {
    throw new ExpectedUserError("Genera prima un planning operativo.");
  }
  const request = currentRequest();
  if (!request.entity_id || !request.reason) {
    throw new ExpectedUserError("Entità e motivo sono obbligatori.");
  }
  const simulation = await simulatePlanningEvent(planningId, request);
  state.planningOperational.simulation = { request, simulation };
  byId("simulationResult").innerHTML = changeDiff(simulation.diff);
  byId("applySimulationBtn").disabled = false;
  return simulation;
}


export async function startQuickSimulation(eventType, assignment) {
  const entity = eventType === "driver_absent"
    ? assignment.driver_id
    : eventType === "vehicle_unavailable"
      ? assignment.plate
      : assignment.route_id;
  if (!entity) {
    setMessage("L'assegnazione non contiene l'entità richiesta.", "warning");
    return;
  }
  byId("eventType").value = eventType;
  byId("eventEntityId").value = entity;
  byId("eventReason").value = "Simulazione operativa";
  try {
    await runSimulation();
    byId("simulatorTitle").scrollIntoView({ behavior: "smooth", block: "start" });
    setMessage("");
  } catch (error) {
    showSimulationError("planning.quick-simulation", error);
  }
}


function cancelSimulation() {
  state.planningOperational.simulation = null;
  byId("simulationResult").innerHTML = '<div class="empty-state">Nessuna simulazione attiva.</div>';
  byId("applySimulationBtn").disabled = true;
}


export function initExceptionSimulator(onUpdated) {
  onPlanningUpdated = onUpdated;
  const form = byId("eventSimulationForm");
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = form.querySelector('button[type="submit"]');
    setLoading(button, true, "Simulazione...");
    try {
      await runSimulation();
      setMessage("");
    } catch (error) {
      showSimulationError("planning.simulation", error);
    } finally {
      setLoading(button, false);
    }
  });
  byId("cancelSimulationBtn").addEventListener("click", cancelSimulation);
  byId("applySimulationBtn").addEventListener("click", async () => {
    const active = state.planningOperational.simulation;
    if (!active) return;
    const button = byId("applySimulationBtn");
    setLoading(button, true, "Applicazione...");
    try {
      const planningId = state.planningOperational.data.planning.id;
      const response = await applyPlanningEvent(planningId, active.request);
      cancelSimulation();
      await onPlanningUpdated(response.planning);
      setMessage("");
    } catch (error) {
      showSimulationError("planning.apply-simulation", error);
    } finally {
      setLoading(button, false);
    }
  });
}
