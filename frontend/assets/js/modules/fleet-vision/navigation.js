const eventMap = {
  damage: ["damage:open", "caseId"],
  maintenance: ["maintenance:open", "maintenanceId"],
  documents: ["documents:open", "documentId"],
  insurance: ["insurance:open", "policyId"],
  rentals: ["rental:open", "rentalId"],
};

export function openFleetVisionSource(module, vehicleId, recordId, driverId = null) {
  if (module === "workforce") {
    document.dispatchEvent(new CustomEvent("workspace:navigate", {
      detail: { view: "workforce", driverId },
    }));
    return;
  }
  if (module === "brain") {
    document.dispatchEvent(new CustomEvent("fleet:vehicle-open", { detail: { assetId: vehicleId } }));
    window.setTimeout(() => {
      document.querySelector('[data-section="brain"]')?.scrollIntoView({
        behavior: "smooth", block: "start",
      });
    }, 0);
    return;
  }
  if (module === "library") {
    document.dispatchEvent(new CustomEvent("fleet:vehicle-open", { detail: { assetId: vehicleId } }));
    return;
  }
  if (eventMap[module]) {
    const [name, key] = eventMap[module];
    document.dispatchEvent(new CustomEvent(name, {
      detail: { vehicle_id: vehicleId, ...(recordId ? { [key]: recordId } : {}) },
    }));
    return;
  }
  const fleetModule = module === "journal" ? "journal" : module;
  document.querySelector(`[data-fleet-module="${fleetModule}"]`)?.click();
}

export function directActionLabel(item) {
  if (item.module === "damage") return `Apri ${item.record_label || "pratica danno"}`;
  if (item.module === "maintenance") return `Apri ${item.record_label || "manutenzione"}`;
  if (item.module === "insurance") return `Apri polizza ${item.record_label || ""}`.trim();
  if (item.module === "documents") return "Apri Documenti";
  if (item.module === "rentals") return `Apri ${item.record_label || "contratto noleggio"}`;
  if (item.module === "journal") return "Apri Driver Journal";
  if (item.module === "library") return "Apri scheda mezzo";
  return "Apri record originale";
}
