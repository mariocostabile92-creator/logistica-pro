import { escapeHtml } from "../../utils/dom.js";

export function planningDriverOptions(workforce) {
  const source = workforce?.planning?.drivers || workforce?.drivers || [];
  return source.filter((item) => item.selectable ?? item.callable).map((item) => {
    const warning = item.warning || (item.callability_status === "limited" ? item.reason : "");
    return `<option value="${escapeHtml(item.display_name)}">${escapeHtml(item.external_identifier)}${warning ? " · Attenzione" : ""}</option>`;
  }).join("");
}
