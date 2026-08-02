export const completionKpiGroups = [
  {
    key: "drivers", label: "Driver attesi", entries: [
      ["drivers_expected", "Attesi", completion => completion.drivers_expected],
    ],
  },
  {
    key: "checkout", label: "Presa in carico", entries: [
      ["checkout_expected", "Attese", completion => completion.check_out.expected],
      ["checkout_completed", "Compilate", completion => completion.check_out.completed],
      ["checkout_missing", "Mancanti", completion => completion.check_out.missing],
    ],
  },
  {
    key: "checkin", label: "Rientro", entries: [
      ["checkin_expected", "Attesi", completion => completion.check_in.expected],
      ["checkin_completed", "Compilati", completion => completion.check_in.completed],
      ["checkin_missing", "Mancanti", completion => completion.check_in.missing],
    ],
  },
  {
    key: "procedures", label: "Procedure", entries: [
      ["procedures_open", "Aperte", completion => completion.procedures.open],
      ["procedures_in_progress", "In compilazione", completion => completion.procedures.in_progress],
      ["procedures_late", "In ritardo", completion => completion.procedures.late],
      ["procedures_anomaly", "Con anomalie", completion => completion.procedures.anomalies],
    ],
  },
];
