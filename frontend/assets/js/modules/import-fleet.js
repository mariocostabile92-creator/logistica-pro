import { initWorkbookImport } from "./import-workbook.js";


export function initFleetImport() {
  initWorkbookImport({
    datasetType: "fleet",
    prefix: "fleet",
    fileMissingMessage: "Seleziona un file parco auto.",
    importedEventType: "fleet",
    stateKey: "fleet",
    expectedTarget: "fleet_snapshot_legacy",
  });
}
