import {
  listDamageCases,
  listFleetAssets,
  listFleetDeadlines,
  listJournalControlRoom,
  listMaintenances,
  listVehicleDocuments,
  getPlanningOperationsSummary,
} from "../api.js?v=3";


function value(result, fallback) {
  return result.status === "fulfilled" ? result.value : fallback;
}


function recentEvents({ damage, maintenance, documents, journal }) {
  const events = [
    ...damage.map((item) => ({
      id: `damage-${item.id}`,
      timestamp: item.created_at || item.occurred_at,
      label: `Pratica danno ${item.case_number || "aperta"}`,
      source: item.plate ? `Danni · ${item.plate}` : "Danni",
    })),
    ...maintenance.map((item) => ({
      id: `maintenance-${item.id}`,
      timestamp: item.updated_at || item.opened_at || item.created_at,
      label: item.status === "completata" ? "Manutenzione completata" : "Manutenzione aggiornata",
      source: item.plate ? `Manutenzioni · ${item.plate}` : "Manutenzioni",
    })),
    ...documents.map((item) => ({
      id: `document-${item.id}`,
      timestamp: item.updated_at || item.uploaded_at || item.created_at,
      label: "Documento mezzo aggiornato",
      source: item.plate ? `Documenti · ${item.plate}` : "Documenti",
    })),
    ...journal.map((item) => ({
      id: `journal-${item.procedure_id || item.id}`,
      timestamp: item.completed_at || item.updated_at || item.occurred_at,
      label: item.status === "completed" ? "GDB completato" : "GDB aggiornato",
      source: item.plate ? `Journal · ${item.plate}` : "Journal",
    })),
  ].filter((item) => item.timestamp);
  return events
    .sort((left, right) => new Date(right.timestamp) - new Date(left.timestamp))
    .slice(0, 8);
}


export async function loadMissionControlSummary() {
  const settled = await Promise.allSettled([
    listFleetAssets(),
    listDamageCases(),
    listMaintenances(),
    listVehicleDocuments(),
    listJournalControlRoom(),
    listFleetDeadlines(),
    getPlanningOperationsSummary(),
  ]);
  const assets = value(settled[0], { items: [] }).items || [];
  const damage = value(settled[1], { items: [] }).items || [];
  const maintenanceResponse = value(settled[2], { items: [], summary: {} });
  const maintenance = maintenanceResponse.items || [];
  const documentResponse = value(settled[3], { items: [], summary: {} });
  const documents = documentResponse.items || [];
  const journalResponse = value(settled[4], { items: [], summary: {}, completion: {} });
  const journal = journalResponse.items || [];
  const deadlines = value(settled[5], { items: [], summary: {} });
  const planningResponse = value(settled[6], null);
  const failedSources = settled.reduce((count, result) => (
    count + Number(result.status === "rejected")
  ), 0);

  return {
    updatedAt: new Date().toISOString(),
    partial: failedSources > 0,
    failedSources,
    fleet: {
      available: assets.filter((item) => ["disponibile", "available"].includes(item.availability)).length,
      unavailable: assets.filter((item) => ["indisponibile", "unavailable"].includes(item.availability)).length,
      maintenance: assets.filter((item) => [
        "in_manutenzione", "in_officina", "maintenance", "workshop",
      ].includes(item.availability)).length,
      openDamage: damage.filter((item) => !["chiusa", "annullata"].includes(item.status)).length,
      criticalDocuments: Number(documentResponse.summary?.expired || 0)
        + Number(documentResponse.summary?.missing_files || 0),
      missingJournal: Number(journalResponse.completion?.checkout_missing || 0)
        + Number(journalResponse.completion?.checkin_missing || 0),
      deadlines: Number(deadlines.summary?.expired || 0)
        + Number(deadlines.summary?.next_30_days || 0),
    },
    maintenance: {
      urgent: maintenance.filter((item) => (
        ["alta", "critica"].includes(item.priority)
        && !["completata", "annullata"].includes(item.status)
      )).length,
      open: Number(maintenanceResponse.summary?.open || 0),
    },
    planning: planningResponse ? {
      driversAssigned: planningResponse.summary?.drivers_assigned ?? null,
      vehiclesAssigned: planningResponse.summary?.vehicles_assigned ?? null,
      conflicts: planningResponse.summary?.blocking_conflicts ?? planningResponse.summary?.conflicts ?? null,
      publication: planningResponse.lifecycle?.state || "Non disponibile",
    } : null,
    recent: recentEvents({ damage, maintenance, documents, journal }),
  };
}
