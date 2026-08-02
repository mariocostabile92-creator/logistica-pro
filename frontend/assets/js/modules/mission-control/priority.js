import { node, setText } from "./dom.js";


export function renderPriorities(view) {
  const list = document.getElementById("operationsHomePriorityList");
  setText("operationsHomePriorityCount", view.loading ? "—" : view.priorities.length);
  if (view.loading) {
    list.replaceChildren(...[1, 2, 3].map(() => node("span", "mission-skeleton-card")));
    return;
  }
  if (!view.priorities.length) {
    const empty = node("div", "mission-empty-state");
    empty.append(node("strong", "", "Nessuna priorità aperta"), node("p", "", "La giornata non presenta attenzioni operative nei dati correnti."));
    list.replaceChildren(empty);
    return;
  }
  list.replaceChildren(...view.priorities.map((item) => {
    const card = node("article", `mission-priority-card is-${item.tone}`);
    const copy = node("div", "mission-priority-copy");
    const title = item.count === null ? item.title : `${item.count} ${item.title}`;
    copy.append(node("h4", "", title), node("p", "", item.description));
    const button = node("button", "mission-link", "Apri");
    button.type = "button";
    button.dataset.missionTarget = item.target;
    card.append(copy, button);
    return card;
  }));
}
