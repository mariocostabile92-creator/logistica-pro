import {
  getFleetAsset,
  getFleetVehicleHistory,
  getFleetVision,
  listDamageCases,
  listFleetDeadlines,
  listFranchiseCases,
  listInsurancePolicies,
  listMaintenances,
  listRentals,
  listVehicleDocuments,
} from "../../api.js?v=5";
import { listVehicleAttachments } from "../attachments/api.js";

const sources = assetId => ({
  asset: getFleetAsset(assetId),
  history: getFleetVehicleHistory(assetId),
  damages: listDamageCases({ vehicle_id: assetId }).then(response =>
    response.items.filter(item => Number(item.vehicle_id) === Number(assetId))),
  maintenances: listMaintenances({ vehicle_id: assetId }).then(response => response.items),
  documents: listVehicleDocuments({ vehicle_id: assetId }).then(response => response.items),
  franchises: listFranchiseCases({ vehicle_id: assetId }).then(response => response.items),
  insurance: listInsurancePolicies({ vehicle_id: assetId }).then(response => response.items),
  rentals: listRentals({ vehicle_id: assetId }).then(response => response.items),
  deadlines: listFleetDeadlines({ vehicle_id: assetId }).then(response => response.items),
  vision: getFleetVision({ vehicle_id: assetId }).then(response => response.items[0] || null),
  attachments: listVehicleAttachments(assetId).then(response => response.items),
});

export async function loadVehicleDossier(assetId) {
  const entries = Object.entries(sources(assetId));
  const settled = await Promise.allSettled(entries.map(([, promise]) => promise));
  const data = {};
  const errors = {};
  settled.forEach((result, index) => {
    const key = entries[index][0];
    if (result.status === "fulfilled") data[key] = result.value;
    else errors[key] = result.reason?.message || "Dati temporaneamente non disponibili.";
  });
  if (!data.asset || !data.history) {
    throw new Error(errors.asset || errors.history || "Scheda mezzo non disponibile.");
  }
  return { data, errors };
}
