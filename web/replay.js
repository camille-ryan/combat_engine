/**
 * Watch a recorded fight, and argue with it.
 *
 * Read-only by construction. There is no `/act`, `/aim` or `/decide` call anywhere in this
 * file, and no click handler on the board -- the live page's whole interaction surface is
 * simply absent rather than disabled, which is the version that cannot come back by
 * accident.
 *
 * The board drawing is `board.js`, shared with the encounter page. Everything else here is
 * the timeline, the decision panel and the notes.
 */

import { renderBoard, renderOrder, withNames } from "./board.js";
import { choiceCard, hideCard, moveCard, showCard } from "./card.js";
import { clear, div } from "./dom.js";

const el = {
  where: document.getElementById("where"),
  level: document.getElementById("level"),
  seed: document.getElementById("seed"),
  play: document.getElementById("play"),
  pick: document.getElementById("pick"),
  timeline: document.getElementById("timeline"),
  decision: document.getElementById("decision"),
  decisionWhere: document.getElementById("decision-where"),
  note: document.getElementById("note"),
  saveNote: document.getElementById("save-note"),
  noteSaid: document.getElementById("note-said"),
  notes: document.getElementById("notes"),
  log: document.getElementById("log"),
  showRaw: document.getElementById("show-raw"),
};

//: The recording on screen, and where in it we are.
let shown = null;
let at = 0;

//: Bookkeeping events, hidden unless `raw` is ticked. The same set
//: `scripts/transcript.py` hides by default, and for the same reason: about 41% of a
//: fight's events are effect and adjacency housekeeping, which is correct to record and
//: not what a reader is looking for.
const NOISE = new Set([
  "effect_applied",
  "effect_expired",
  "entered_square",
  "left_square",
  "adjacent_gained",
  "adjacent_lost",
  "relation_set",
  "relation_cleared",
  "action_spent",
]);

async function getJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} — ${url}`);
  return res.json();
}

async function postJSON(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} — ${url}`);
  return res.json();
}

function say(text, kind) {
  el.where.textContent = text || "";
  el.where.className = kind ? `turn ${kind}` : "turn";
}

// ------------------------------------------------------------------ timeline

/** One chip per frame, which is one per turn. The `.leg` strip on the encounter page is
 * the visual precedent. */
function renderTimeline() {
  clear(el.timeline);
  shown.frames.forEach((frame, i) => {
    const chip = div(`leg${i === at ? " current" : ""}`);
    chip.appendChild(div("leg-n", String(frame.round)));
    chip.appendChild(div("leg-note", frame.current || "—"));
    chip.addEventListener("click", () => show(i));
    el.timeline.appendChild(chip);
  });
}

// ------------------------------------------------------------------ decision

/** The decision taken on the frame being shown, if there is one.
 *
 * Matched by sequence rather than by index: a frame is a turn and a turn holds several
 * decisions, so the one worth showing is the last one taken at or before this frame.
 */
function decisionAt(frame) {
  let found = null;
  for (const d of shown.decisions) {
    if (d.seq <= frame.seq) found = d;
    else break;
  }
  return found;
}

/** An action, its score, and the terms behind it -- as a `ChoiceDTO`, so `choiceCard`
 * draws it. That DTO already means "a score and the named terms that sum to it", which is
 * exactly a decision, and reusing it means the terms render the way chargen's already do. */
function asChoice(entry) {
  return {
    ref: entry.ref || entry.kind,
    label: withNames(entry.label),
    score: entry.score,
    terms: Object.entries(entry.terms || {}).map(([name, value]) => ({ name, value })),
  };
}

function renderDecision(frame) {
  clear(el.decision);
  const d = decisionAt(frame);
  el.decisionWhere.textContent = d ? `round ${d.round} · ${d.actor}` : "";
  if (!d) {
    el.decision.appendChild(div("replay-empty", "no decision on this frame"));
    return;
  }

  const rows = [["chose", d.chosen], ...d.passed.map((p) => ["passed", p])];
  for (const [how, entry] of rows) {
    const row = div(`replay-choice ${how === "chose" ? "taken" : "passed"}`);
    row.appendChild(div("choice-label", withNames(entry.label)));
    row.appendChild(div("choice-score", entry.score.toFixed(2)));
    // Hover for the terms, which is how this project already explains a number --
    // `choiceCard` and `.card-terms`, the same as a chargen row.
    const choice = asChoice(entry);
    row.addEventListener("mouseenter", (ev) => showCard(choiceCard(choice), ev));
    row.addEventListener("mousemove", moveCard);
    row.addEventListener("mouseleave", hideCard);
    el.decision.appendChild(row);
  }
}

// ---------------------------------------------------------------------- log

/** Every event up to this frame. Rebuilt per frame rather than appended, because a
 * timeline goes backwards as well as forwards and an appender cannot. */
function renderLog(frame) {
  clear(el.log);
  let round = null;
  for (const ev of shown.events) {
    if (ev.seq > frame.seq) break;
    if (typeof ev.round === "number" && ev.round !== round) {
      round = ev.round;
      el.log.appendChild(div("log-round", `Round ${round}`));
    }
    const quiet = NOISE.has(ev.kind);
    const row = div(`logline kind-${ev.kind || "event"}${quiet ? " raw" : ""}`);
    row.appendChild(div("log-seq", ev.seq ?? ""));
    row.appendChild(div("log-text", withNames(ev.text || ev.kind || "")));
    el.log.appendChild(row);
  }
  el.log.scrollTop = el.log.scrollHeight;
}

// -------------------------------------------------------------------- notes

async function loadNotes() {
  // Notes live beside the recording and there is no endpoint to read them back yet, so
  // what is on screen is what this session pinned. Said plainly rather than faked.
  clear(el.notes);
  for (const n of shown.notes || []) {
    const li = div("replay-note-row");
    li.appendChild(div("choice-ref", `r${n.round} ${n.actor}`));
    li.appendChild(div("choice-label", n.note));
    el.notes.appendChild(li);
  }
}

async function pinNote() {
  const text = (el.note.value || "").trim();
  if (!text || !shown) return;
  const frame = shown.frames[at];
  const d = decisionAt(frame);
  const entry = {
    round: d ? d.round : frame.round,
    actor: d ? d.actor : frame.current || "",
    seq: frame.seq,
    action: d ? d.chosen.label : "",
    note: text,
  };
  try {
    await postJSON(`/api/replay/${encodeURIComponent(shown.name)}/note`, entry);
    shown.notes = [...(shown.notes || []), entry];
    el.note.value = "";
    el.noteSaid.textContent = `pinned to round ${entry.round}`;
    loadNotes();
  } catch (err) {
    el.noteSaid.textContent = String(err.message || err);
  }
}

// ------------------------------------------------------------------ showing

function show(i) {
  if (!shown || !shown.frames.length) return;
  at = Math.max(0, Math.min(i, shown.frames.length - 1));
  const frame = shown.frames[at];
  // `traits` is hoisted out of the frames into `cast` because it is identical in every
  // one; put it back so the hover card has it.
  const actors = (frame.actors || []).map((a) => ({
    ...a,
    traits: (shown.cast || {})[a.id] || [],
  }));
  renderBoard({ board: frame.board, actors });
  renderOrder({ actors });
  renderTimeline();
  renderDecision(frame);
  renderLog(frame);
  say(`${shown.name} · round ${frame.round} · frame ${at + 1}/${shown.frames.length}`);
}

async function open(name) {
  shown = await getJSON(`/api/replay/${encodeURIComponent(name)}`);
  shown.notes = [];
  at = 0;
  loadNotes();
  show(0);
}

async function refreshList(select) {
  const all = await getJSON("/api/replay");
  clear(el.pick);
  for (const r of all) {
    const opt = document.createElement("option");
    opt.value = r.name;
    opt.textContent = `${r.name} · ${r.paradigm || "?"} · ${r.rounds}r · ${r.decisions} decisions`;
    el.pick.appendChild(opt);
  }
  if (select) el.pick.value = select;
  return all;
}

async function recordOne() {
  el.play.disabled = true;
  say("recording…");
  try {
    const body = { level: Number(el.level.value) || 1 };
    const seed = Number(el.seed.value);
    if (seed) body.seed = seed;
    const made = await postJSON("/api/replay", body);
    await refreshList(made.name);
    await open(made.name);
  } catch (err) {
    say(String(err.message || err), "bad");
  } finally {
    el.play.disabled = false;
  }
}

el.play.addEventListener("click", recordOne);
el.pick.addEventListener("change", () => open(el.pick.value));
el.saveNote.addEventListener("click", pinNote);
el.showRaw.addEventListener("change", () =>
  el.log.classList.toggle("with-raw", el.showRaw.checked),
);
// Arrow keys step the timeline, because scrubbing one turn at a time is the whole gesture.
document.addEventListener("keydown", (ev) => {
  if (ev.target === el.note) return;
  if (ev.key === "ArrowLeft") show(at - 1);
  if (ev.key === "ArrowRight") show(at + 1);
});

refreshList()
  .then((all) => (all.length ? open(all[0].name) : say("nothing recorded yet")))
  .catch((err) => say(String(err.message || err), "bad"));
