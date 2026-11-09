"use strict";

const $ = (id) => document.getElementById(id);
const PAGE = 50;
let offset = 0;
const applyFilter = tableFilter($("a-q"), $("a-body"), $("a-count"));
const BADGE = { delete: "chip-absent", move: "chip-late", update: "chip-late" };

function backupHref() {
  const q = new URLSearchParams();
  if ($("b-from").value) q.set("date_from", $("b-from").value);
  if ($("b-to").value) q.set("date_to", $("b-to").value);
  $("b-btn").href = "/api/admin/backup.xlsx" + (q.toString() ? "?" + q : "");
}
for (const el of [$("b-from"), $("b-to")]) el.addEventListener("change", backupHref);

async function load(reset = true) {
  if (reset) { offset = 0; $("a-body").replaceChildren(); }
  const q = new URLSearchParams({ kind: $("a-kind").value, limit: PAGE, offset });
  if ($("a-from").value) q.set("date_from", $("a-from").value);
  if ($("a-to").value) q.set("date_to", $("a-to").value);
  $("a-loading").classList.remove("hidden");
  try {
    const rows = await api("/api/admin/audit?" + q);
    $("a-body").append(...rows.map((r) => h("tr", {},
      h("td", { class: "nowrap small" }, thaiDateTime(r.at)),
      h("td", { class: "small" }, r.user),
      h("td", {}, h("span", { class: "chip " + (BADGE[r.action] || "chip-present") }, r.action_label), h("div", { class: "muted small" }, r.entity_label)),
      h("td", { class: "small" }, r.what),
      h("td", { class: "small" }, r.change),
    )));
    offset += rows.length;
    $("a-more").classList.toggle("hidden", rows.length < PAGE);
    $("a-table").classList.toggle("hidden", offset === 0);
    $("a-empty").classList.toggle("hidden", offset > 0);
    applyFilter();
  } catch (e) {
    toast(e.message, "error");
  } finally {
    $("a-loading").classList.add("hidden");
  }
}

for (const el of [$("a-kind"), $("a-from"), $("a-to")]) el.addEventListener("change", () => load());
$("a-more").addEventListener("click", () => load(false));
load();
