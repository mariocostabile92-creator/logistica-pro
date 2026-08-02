import {
  getPlanningOperations,
  generatePlanning,
  importDataset,
  patchPlanningAssignment,
  patchPlanningConvocation,
  previewImport,
  transitionOperationalPlanning,
} from "../../api.js?v=5";

export const planningOperationsApi = Object.freeze({
  load: getPlanningOperations,
  assign: patchPlanningAssignment,
  convocation: patchPlanningConvocation,
  transition: transitionOperationalPlanning,
  previewImport: (file) => previewImport(file, "planning"),
  importRoutes: (file) => importDataset(file, "planning"),
  generate: generatePlanning,
});
