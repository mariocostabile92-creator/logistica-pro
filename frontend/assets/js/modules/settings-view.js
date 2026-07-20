import {
  byId,
  escapeHtml,
  renderViewState,
  showDataView,
} from "../utils/dom.js";


const SECTION_LABELS = {
  nomenclature: "Nomenclature",
  capabilities: "Capability",
  asset_states: "Stati Asset",
  severities: "Severità",
  readiness_levels: "Livelli Readiness",
  reserve_policy: "Policy di riserva",
  priorities: "Priorità",
  generic_mappings: "Mapping generici",
};


const SOURCE_LABELS = {
  platform_default: "Default piattaforma",
  organization: "Organizzazione",
  operational_unit: "Operational Unit",
  future_adapter: "Future Adapter",
};


const SECTION_DESCRIPTIONS = {
  nomenclature: "Etichette usate per descrivere il dominio operativo.",
  capabilities: "Capability disponibili per Asset e Risorse.",
  asset_states: "Stati osservabili nel ciclo di vita degli Asset.",
  severities: "Livelli usati per classificare le criticità.",
  readiness_levels: "Livelli sintetici della prontezza operativa.",
  reserve_policy: "Soglie che proteggono la capacità di riserva.",
  priorities: "Livelli disponibili per ordinare il lavoro.",
  generic_mappings: "Soglie e mapping condivisi dagli import generici.",
};


function formatTimestamp(value) {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? value
    : parsed.toLocaleString("it-IT");
}


function formatValue(value) {
  if (typeof value === "string") return value;
  return JSON.stringify(value, null, 2);
}


function resolvedScopeLabel(configuration) {
  const scope = configuration.metadata.resolved_scope;
  if (!scope) return "Default piattaforma";
  if (scope.operational_unit_id) return scope.operational_unit_id;
  if (scope.adapter_id) return scope.adapter_id;
  return scope.organization_id;
}


function renderValue(item) {
  return `
    <div class="settings-value-row">
      <div class="settings-value-key">${escapeHtml(item.key)}</div>
      <div class="settings-value-content">${escapeHtml(formatValue(item.value))}</div>
      <span class="settings-value-source">
        ${escapeHtml(SOURCE_LABELS[item.source] || item.source)}
      </span>
    </div>
  `;
}


function renderSection(section) {
  const inherited = section.values.every(
    (item) => item.source === "platform_default",
  );
  return `
    <details class="settings-config-section">
      <summary>
        <span class="settings-section-copy">
          <strong>${escapeHtml(SECTION_LABELS[section.key] || section.key)}</strong>
          <span>${escapeHtml(SECTION_DESCRIPTIONS[section.key] || "Configurazione disponibile per questo ambito.")}</span>
        </span>
        <span class="settings-section-meta">
          <span>${section.values.length} elementi</span>
          <span class="settings-section-status">
            ${inherited ? "Default piattaforma" : "Ambito personalizzato"}
          </span>
        </span>
      </summary>
      <div class="settings-config-body">
        ${section.values.map(renderValue).join("")}
      </div>
    </details>
  `;
}


export function renderConfiguration(configuration) {
  showDataView("settingsViewState", "settingsDataView", true);
  byId("settingsVersion").textContent = `v${configuration.version.number}`;
  byId("settingsUpdatedAt").textContent = formatTimestamp(
    configuration.version.created_at,
  );
  byId("settingsResolvedScope").textContent = resolvedScopeLabel(configuration);
  byId("settingsFallback").textContent = configuration.metadata.fallback_used
    ? "Attivo"
    : "Non necessario";
  byId("settingsSectionCount").textContent = configuration.sections.length;
  byId("settingsSections").innerHTML = configuration.sections.length
    ? configuration.sections.map(renderSection).join("")
    : '<div class="empty-state">Nessuna configurazione disponibile.</div>';
}


export function renderSettingsLoading() {
  showDataView("settingsViewState", "settingsDataView", false);
  renderViewState(byId("settingsViewState"), {
    state: "loading",
    title: "Caricamento configurazione",
  });
}


export function renderSettingsFailure() {
  showDataView("settingsViewState", "settingsDataView", false);
  renderViewState(byId("settingsViewState"), {
    state: "error",
    title: "Impossibile caricare la configurazione",
    description: "Il servizio non ha completato il caricamento. Riprova tra poco.",
    actionLabel: "Riprova",
    action: "retry-settings",
  });
}
