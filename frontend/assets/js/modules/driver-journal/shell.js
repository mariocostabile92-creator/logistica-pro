import { getHealth } from "../../api.js?v=5";
import { retireLegacyServiceWorker } from "../pwa.js?v=3";


async function checkJournalHealth() {
  const badge = document.getElementById("healthStatus");
  if (!badge) return;
  try {
    await getHealth();
    badge.textContent = "Backend online";
    badge.className = "status-pill ok";
  } catch {
    badge.textContent = "Backend non raggiungibile";
    badge.className = "status-pill";
  }
}


retireLegacyServiceWorker();
checkJournalHealth();
