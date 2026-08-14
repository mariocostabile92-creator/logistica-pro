const SEVERITY_RANK = Object.freeze({
  critical: 0,
  warning: 1,
  info: 2,
});

const SOURCE_LABELS = Object.freeze({
  planning: "Planning",
  workforce: "Workforce",
  coverage: "Coverage",
  fleet: "Fleet",
  journal: "Journal",
  damage: "Danni",
});


export function severityRank(value) {
  return SEVERITY_RANK[String(value || "").toLowerCase()] ?? 3;
}


export function orderedSignals(signals = []) {
  return signals
    .map((signal, index) => ({ signal, index }))
    .sort((left, right) => (
      severityRank(left.signal.severity) - severityRank(right.signal.severity)
      || left.index - right.index
    ))
    .map(({ signal }) => signal);
}


export function rowTone(row) {
  return orderedSignals(row?.signals)[0]?.severity || "clear";
}


export function compareAttentionRows(left, right) {
  const leftSignals = orderedSignals(left?.signals);
  const rightSignals = orderedSignals(right?.signals);
  return (
    severityRank(leftSignals[0]?.severity) - severityRank(rightSignals[0]?.severity)
    || rightSignals.length - leftSignals.length
  );
}


export function partialSourceItems(sources = {}) {
  return Object.entries(sources).flatMap(([source, metadata]) => {
    const label = SOURCE_LABELS[source] || source;
    if (!metadata?.available) {
      return [{ source, label, message: `Stato ${label} temporaneamente non disponibile.` }];
    }
    if (metadata.partial) {
      return [{ source, label, message: `Dati ${label} parzialmente disponibili.` }];
    }
    return [];
  });
}
