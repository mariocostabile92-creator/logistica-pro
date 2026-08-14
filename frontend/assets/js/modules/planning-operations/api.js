import {
  getPlanningOperations,
  generatePlanning,
  importDataset,
  patchPlanningAssignment,
  patchPlanningConvocation,
  previewImport,
  saveManualPlanningCoverage,
  transitionOperationalPlanning,
} from "../../api.js?v=forecast1";

export const planningOperationsApi = Object.freeze({
  load: getPlanningOperations,
  assign: patchPlanningAssignment,
  convocation: patchPlanningConvocation,
  transition: transitionOperationalPlanning,
  previewImport: (file) => previewImport(file, "planning"),
  importRoutes: (file) => importDataset(file, "planning"),
  generate: generatePlanning,
  saveForecast: saveManualPlanningCoverage,
});
