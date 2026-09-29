/**
 * The chargen advisor: every option, ranked, with the reasons on hover.
 *
 * **This page never chooses.** It sorts what the server scored and explains
 * it; the human picks. The same scores drive a dealer on the other side of
 * the wire, for fights nobody is watching, and the two are deliberately not
 * the same code path — `chargen/choices.py` ranks, `sample` chooses, and only
 * the first is behind this endpoint.
 *
 * Rules of the house that apply here: the server decides and the page draws,
 * so no score is computed in this file; and every readable name comes over
 * the wire already resolved, so with `CE_NAMES=off` the labels are refs and
 * this page still works.
 */

import { hideCard, moveCard, showCard, choiceCard } from "./card.js";

const state = {
  cls: "fighter",
  build: "",
  level: 1,
  options: null,
  chosen: { race: "", feats: [] },
};

const $ = (id) => document.getElementById(id);

/**
 * A build leg, readably.
 *
 * Most legs are hand-written words — "great-weapon", "two-blade", "archer" —
 * and only need their hyphens back. Four are not: the artificer's and the
 * seeker's are `second-con`, `second-wis`, `second-str`, `second-dex`, and
 * `chargen.BUILDS` says why in as many words — the printed leg names are prose
 * and that file may not carry it, so the leg is named after the ability the
 * fork turns on instead.
 *
 * So this expands the slug rather than looking a name up: "secondary con"
 * comes out of the slug and the ability is an engine word, not a printed one.
 * Nothing here reaches for a name the server did not send.
 */
function legName(leg) {
  const slug = leg.name || "";
  if (slug.startsWith("second-")) return `secondary ${slug.slice(7)}`;
  return slug.replace(/-/g, " ") || "(first leg)";
}

async function get(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json();
}

// ------------------------------------------------------------------ drawing

/**
 * One option. The score sits beside the label rather than under it, because
 * the list is read down the score column and a row that has to be read twice
 * is not a ranking.
 */
function optionRow(choice, kind) {
  const row = document.createElement("li");
  row.className = "choice";
  row.dataset.ref = choice.ref;
  row.dataset.kind = kind;

  const name = document.createElement("span");
  name.className = "choice-label";
  name.textContent = choice.label || choice.ref;

  const ref = document.createElement("span");
  ref.className = "choice-ref";
  ref.textContent = choice.ref;

  const score = document.createElement("span");
  score.className = "choice-score";
  score.textContent = choice.score.toFixed(2);
  if (choice.score <= 0) score.classList.add("term-bad");

  row.append(name, ref, score);
  row.addEventListener("mouseenter", (ev) => showCard(choiceCard(choice), ev));
  row.addEventListener("mousemove", moveCard);
  row.addEventListener("mouseleave", hideCard);
  row.addEventListener("click", () => pick(kind, choice.ref));
  return row;
}

function draw() {
  const data = state.options;
  if (!data) return;
  $("leg").textContent =
    `${data.cls} · ${legName({ name: data.build })} · primary ${data.primary}` +
    ` · secondary ${data.secondary}` +
    (data.swings_a_weapon ? " · swings a weapon" : " · implements only");

  for (const [kind, list] of [["race", data.races], ["feat", data.feats]]) {
    const box = $(`${kind}s`);
    box.replaceChildren();
    // Already best-first from the server. Sorting again here would be a
    // second opinion about a ranking the page does not own.
    for (const choice of list) box.appendChild(optionRow(choice, kind));
    $(`${kind}-count`).textContent = String(list.length);
  }
  mark();
}

/** Show what has been picked, without re-fetching or re-ranking. */
function mark() {
  for (const row of document.querySelectorAll(".choice")) {
    const { kind, ref } = row.dataset;
    const taken =
      kind === "race" ? state.chosen.race === ref : state.chosen.feats.includes(ref);
    row.classList.toggle("taken", taken);
  }
  $("picked").textContent =
    `race ${state.chosen.race || "—"} · feats ` +
    (state.chosen.feats.join(", ") || "—");
}

function pick(kind, ref) {
  if (kind === "race") {
    state.chosen.race = state.chosen.race === ref ? "" : ref;
  } else {
    const at = state.chosen.feats.indexOf(ref);
    if (at >= 0) state.chosen.feats.splice(at, 1);
    else state.chosen.feats.push(ref);
  }
  mark();
}

// ------------------------------------------------------------------ loading

async function load() {
  $("leg").textContent = "ranking…";
  const q = new URLSearchParams({
    cls: state.cls,
    level: String(state.level),
    build: state.build,
  });
  state.options = await get(`/api/chargen/options?${q}`);
  draw();
}

async function start() {
  const classes = await get("/api/chargen/classes");
  const picker = $("cls");
  for (const entry of classes) {
    const opt = document.createElement("option");
    opt.value = entry.cls;
    opt.textContent = entry.cls;
    picker.appendChild(opt);
  }
  picker.value = state.cls;

  const legs = () => {
    const entry = classes.find((c) => c.cls === state.cls);
    const box = $("build");
    box.replaceChildren();
    for (const leg of entry ? entry.builds : []) {
      const opt = document.createElement("option");
      opt.value = leg.name;
      opt.textContent = `${legName(leg)} (${leg.primary}/${leg.secondary})`;
      box.appendChild(opt);
    }
    state.build = box.value || "";
  };
  legs();

  picker.addEventListener("change", () => {
    state.cls = picker.value;
    // A leg belongs to a class, so the choices reset with it rather than
    // carrying a ref that the new class cannot take.
    state.chosen = { race: "", feats: [] };
    legs();
    load();
  });
  $("build").addEventListener("change", () => {
    state.build = $("build").value;
    load();
  });
  $("level").addEventListener("change", () => {
    state.level = Number($("level").value) || 1;
    load();
  });
  await load();
}

start().catch((err) => {
  $("leg").textContent = `could not load: ${err.message}`;
});
