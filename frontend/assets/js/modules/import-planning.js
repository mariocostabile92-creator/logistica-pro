import { initWorkbookImport } from "./import-workbook.js";


export function initPlanningImport() {
  initWorkbookImport({
    datasetType: "planning",
    prefix: "planning",
    fileMissingMessage: "Seleziona un file planning.",
    importedEventType: "planning",
    stateKey: "planning",
    expectedTarget: "daily_operations",
  });
}
