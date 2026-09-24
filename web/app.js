// app.js — the page. One encounter, four panels.
//
// Reads EncounterStateDTO / ActorDTO / OptionDTO / PowerDTO / EventDTO exactly
// as plans/20260921-api-contract.md defines them. The only write is
// POST /api/encounter/{id}/act with {actor_id, action_index}.
//
// No coordinate arithmetic lives here — see coords.js. No rules knowledge
// either, and the roster is where that line is easiest to cross: "2 squares
// closer" is computed in engine/actions.py and printed here, because working
// out what a power could reach from a square nobody is standing on is a rules
// question (#332).
//
// The hover card is card.js; `div` and `clear` are dom.js, shared with it.

import * as anim from "./anim.js";
import {
  creatureCard,
  hideCard,
  moveCard,
  powerCard,
  showCard,
  zoneCard,
} from "./card.js";
import {
  boardPixelSize,
  place,
  pointerSquare,
  squareRect,
  squaresRect,
} from "./coords.js";
import { clear, div } from "./dom.js";

// Tells index.html this module resolved and ran. Without it, a module that
// 404s or throws on load leaves an empty page that looks exactly like a server
// that is not answering.
window.__dnd4e_app_loaded = true;

// What the form does *not* send. The party is a server-side default and naming
// it here would be a second copy that drifts — it already had, listing a party
// of one against the server's party of two. It also keeps the roster out of
// this file: the names of the creatures in the default fight are printed names,
// and a static asset is the last place they should be written down (#325).
//
// Level and the budget multiplier *are* sent, because those are the player's
// to choose (#338) — and only those. The defaults in `index.html` match the
// server's, so an untouched form asks for exactly what it always did.

// Headings for the powers that have no place in the action economy. A trait is
// always running and a reaction waits for its trigger; neither is something
// you spend an action on, and both would otherwise land under "none" beside
// "End turn" as though you had chosen not to use them.
const ALWAYS_ON = "always on";
const TRIGGERED = "triggered";

// Cost buckets in the order a player thinks about them. Anything the engine
// hands back that is not in this list is appended after, in first-seen order
// — which is where `ALWAYS_ON` ends up, and where it belongs.
const COST_ORDER = ["standard", "move", "minor", "immediate", "free", "none"];

// What the wire calls ending your turn. `Action.kind` is "end" and both modes
// looked for "end_turn", so neither ever found it: the button was never lifted
// out of the buckets and sat at the bottom of "none", under every power and
// every square you could walk to, which is the one place it must not be.
const END_TURN = "end";

let state = null;
let stream = null;
let lastSeq = -1;
let lastNarration = -1;
let shownRound = null;
let busy = false;
// The newest state the server has sent, held back while the animator is
// playing the events that led to it.
let pendingState = null;
// The highest event seq already handed to the animator, so a reconnect that
// replays the log does not replay the fight.
let animatedThrough = -1;
// Freeform targeting: show the powers, let the player point. Remembered, like
// the board speed, because it is a way of playing rather than a setting you
// fiddle with mid-fight.
let freeform = readFreeform();
// What is waiting for a square: an index into `roster`, or "walk"/"shift".
// Movement is offered the same way a power is, because in freeform it is the
// same gesture and a player should not have to know that one of them is not a
// power.
let aiming = null;
// The power whose aim squares are on the board right now, and which of them
// is showing its footprint. Held because the aim squares are lit from the
// action list and the aim point is picked on the board, and the two gestures
// have no element in common.
let aimed = null;
let aimedAt = null;

function readFreeform() {
  try {
    return localStorage.getItem("dnd4e.freeform") === "on";
  } catch {
    return false;
  }
}
// The day, when there is one. Null for a single fight, which is why every
// reader of it asks first — a day is a thing that outlives an encounter, and
// most of this file only knows about encounters.
let day = null;

const el = {
  board: document.getElementById("board"),
  movement: document.getElementById("movement"),
  highlights: document.getElementById("highlights"),
  order: document.getElementById("order"),
  actions: document.getElementById("actions"),
  log: document.getElementById("log"),
  status: document.getElementById("status"),
  turn: document.getElementById("turn"),
  hover: document.getElementById("hover"),
  day: document.getElementById("day"),
  dayLegs: document.getElementById("day-legs"),
  dayCurve: document.getElementById("day-curve"),
  dayFoot: document.getElementById("day-foot"),
};

// ---------------------------------------------------------------- utilities

const key = (sq) => `${sq[0]},${sq[1]}`;

function setOf(squares) {
  return new Set((squares || []).map(key));
}

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

// True while the board is showing a snapshot the server has already moved
// past — the reply to an action arrives before the events that explain it,
// so the list on screen is held back until the animation catches up.
//
// An option index only means anything for the snapshot it came from, so
// acting on a held one sends an index the server has no record of. It did:
// "no option 111", every run, once dual-range roughly doubled the list.
function settling() {
  return busy || pendingState !== null;
}

function say(text, kind) {
  el.status.textContent = text || "";
  el.status.className = kind ? `status ${kind}` : "status";
}

// -------------------------------------------------------------------- board

function renderBoard(s) {
  const board = s.board || {};
  const width = board.width || 0;
  const height = board.height || 0;

  clear(el.board);
  clear(el.movement);
  clear(el.highlights);
  // The aim squares went with that layer, so nothing is aimed until somebody
  // lights them again — otherwise the next mouse move over the board redraws
  // a power the player has already put down.
  aimed = null;
  aimedAt = null;

  const size = boardPixelSize(width, height);
  for (const layer of [el.board, el.movement, el.highlights]) {
    layer.style.width = `${size.width}px`;
    layer.style.height = `${size.height}px`;
  }

  const blocking = setOf(board.blocking);
  const difficult = setOf(board.difficult);
  const obscuring = setOf(board.obscuring);

  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const k = `${x},${y}`;
      const tile = div("tile");
      if (blocking.has(k)) tile.classList.add("t-blocking");
      if (difficult.has(k)) tile.classList.add("t-difficult");
      if (obscuring.has(k)) tile.classList.add("t-obscuring");
      place(tile, squareRect(x, y));
      el.board.appendChild(tile);
    }
  }

  (board.zones || []).forEach((zone, i) => {
    const squares = zone.squares || [];
    for (const sq of squares) {
      const z = div(`zone zone-${i % 4}`);
      place(z, squareRect(sq[0], sq[1]));
      // Hoverable, unlike every other overlay: the shading is the only sign
      // an aura is there at all, and a player who cannot find out whose it is
      // cannot find out what it does. Tokens are appended after these, so a
      // creature standing in a zone still wins the hover.
      const owner = (actorsById().get(zone.owner) || {}).label || zone.owner;
      hovers(z, () => zoneCard(zone, owner));
      el.board.appendChild(z);
    }
    if (squares.length) {
      const tag = div("zone-label", zone.label || zone.id || "");
      const r = squaresRect(squares);
      tag.style.left = `${r.left}px`;
      tag.style.top = `${r.top}px`;
      el.board.appendChild(tag);
    }
  });

  for (const actor of s.actors || []) {
    const squares =
      actor.squares && actor.squares.length
        ? actor.squares
        : actor.square
          ? [actor.square]
          : [];
    if (!squares.length) continue;

    const down = isDown(actor);
    const token = div(`token side-${actor.side || "npc"}`);
    if (actor.is_current) token.classList.add("current");
    if (down) token.classList.add("dead");
    if (actor.bloodied && !down) token.classList.add("bloodied");
    place(token, squaresRect(squares));
    token.dataset.actor = actor.id;
    hovers(token, () => creatureCard(actor, withNames));

    token.appendChild(div("token-name", shortLabel(actor.label || actor.id)));
    const bar = div("token-hp");
    const fill = div("token-hp-fill");
    fill.style.width = `${hpFraction(actor) * 100}%`;
    bar.appendChild(fill);
    token.appendChild(bar);

    el.board.appendChild(token);
  }

  renderMovement(s.movement);
  // With a question open there is no movement range — the turn is not where
  // you can walk, it is what you owe an answer to — so the same layer shows
  // the squares the answers are on instead.
  renderPendingSquares(s.pending);
}

// Where the acting creature may walk — drawn only while the player is asking.
//
// It used to be painted on every render, so the board carried a wash of
// forty highlighted squares from the moment a turn began, whether or not
// anybody was thinking about moving. Now `Move` is a thing you press, and
// the squares are the answer to having pressed it.
//
// Green is clear, yellow is "something happens on the way". **No rule is read
// here** — what provokes an opportunity attack and what a zone does to
// whoever walks through it are questions `engine/movement.risk_along` answers
// before this ever sees them. Which of the two lists a square is in is the
// whole of this function's knowledge.
function renderMovement(movement) {
  if (!movement) return;
  if (aiming !== "walk" && aiming !== "shift") return;
  const lists =
    aiming === "shift"
      ? [["free", movement.shift]]
      : [["risky", movement.risky], ["free", movement.free]];
  for (const [tone, squares] of lists) {
    for (const sq of squares || []) {
      const h = div(`mv mv-${tone}`);
      place(h, squareRect(sq[0], sq[1]));
      el.movement.appendChild(h);
    }
  }
}

// The route to the square under the pointer, drawn a step at a time.
//
// The server sends every route with the squares, because the line drawn has
// to be the line walked: working the path out again in JavaScript is how the
// two come to disagree, and the one a player can see is the one they trust.
let shownPath = null;

function previewPath(at) {
  if (aiming !== "walk" && aiming !== "shift") {
    shownPath = null;
    return;
  }
  const move = (state && state.movement) || {};
  const path = at ? (move.paths || {})[at] : null;
  if (at === shownPath) return;
  shownPath = at;
  clear(el.highlights);
  if (!path) return;
  for (const sq of path) {
    const h = div("hl hl-path");
    place(h, squareRect(sq[0], sq[1]));
    el.highlights.appendChild(h);
  }
  const why = (move.warnings || {})[at];
  if (why) say(why, "warn");
}

// Whether to show a creature as out of the fight.
//
// `dead` alone is not enough: a creature dropped to 0 or below is dying, not
// dead, and the engine keeps `dead` false for it. A whole 11-round fixture
// finished with two actors on negative hp and `dead` false throughout, so a
// panel keyed on `dead` never once marked anybody down — which is exactly the
// thing a player needs to see at a glance.
function isDown(actor) {
  return Boolean(actor.dead) || (actor.hp ?? 1) <= 0;
}

function hpFraction(actor) {
  const max = actor.hp_max || 0;
  if (max <= 0) return 0;
  const hp = Math.max(0, Math.min(actor.hp ?? 0, max));
  return hp / max;
}

function shortLabel(label) {
  const words = String(label).trim().split(/\s+/);
  if (words.length === 1) return words[0].slice(0, 6);
  return words.map((w) => w[0]).join("").slice(0, 4).toUpperCase();
}

// Attach the hover card to anything. `build` is called on entry rather than
// up front, so a card is only assembled for the one thing being looked at —
// and so it reads whatever the latest snapshot says rather than whatever the
// board looked like when the element was made.
//
// `mousemove` as well as `mouseenter`: the card follows the pointer, which is
// what keeps it out of the way of the square underneath it on a board where
// tokens are two squares wide.
function hovers(node, build) {
  node.addEventListener("mouseenter", (ev) => showCard(build(), ev));
  node.addEventListener("mousemove", moveCard);
  node.addEventListener("mouseleave", hideCard);
}

// The squares an option lights up as its target.
//
// `affected` is the *area*, and the engine only fills it in for bursts and
// blasts (actions.py:1089) — a single-target attack leaves it empty and names
// the victim in `targets` instead. Highlighting `affected` alone therefore
// lights up nothing for most attacks, which is the one hover a player most
// needs. Fall back to wherever the named targets are standing.
function actorsById() {
  return new Map((state && state.actors ? state.actors : []).map((a) => [a.id, a]));
}

function affectedSquares(option) {
  if ((option.affected || []).length) return option.affected;
  const byId = actorsById();
  const out = [];
  for (const t of option.targets || []) {
    const a = byId.get(t);
    if (!a) continue;
    const squares = a.squares && a.squares.length ? a.squares : a.square ? [a.square] : [];
    out.push(...squares);
  }
  return out;
}

// Wire ids, as the names on screen. The server sends `pc_1` inside an effect's
// text and its duration — deliberately, because an id is what survives the
// name switch — and a player reading a card wants the creature. A rewrite, not
// a rule: wire ids have one fixed shape, so this cannot mistranslate, and with
// names off every label *is* its wire id and it does nothing.
const WIRE_ID = /\b(?:pc|npc)_\d+\b/g;

function withNames(text) {
  if (!text) return text;
  const byId = actorsById();
  return String(text).replace(WIRE_ID, (id) => (byId.get(id) || {}).label || id);
}

/** An option's targets as the names on screen, not the ActorIds on the wire. */
function namedTargets(option) {
  const byId = actorsById();
  return (option.targets || []).map((t) => (byId.get(t) || {}).label || t);
}

// Hover highlighting. `path` is literally the squares to walk — the engine
// already computed it.
function highlight(option) {
  clear(el.highlights);
  aimed = null;
  aimedAt = null;
  if (!option) return;
  for (const sq of option.path || []) {
    const h = div("hl hl-path");
    place(h, squareRect(sq[0], sq[1]));
    el.highlights.appendChild(h);
  }
  for (const sq of affectedSquares(option)) {
    const h = div("hl hl-affected");
    place(h, squareRect(sq[0], sq[1]));
    el.highlights.appendChild(h);
  }
  if (option.origin) {
    const h = div("hl hl-origin");
    place(h, squareRect(option.origin[0], option.origin[1]));
    el.highlights.appendChild(h);
  }
}

// -------------------------------------------------------------- turn order
//
// The turn order as a strip of unit icons along the top, which is how a table
// tracks it. `s.actors` arrives in initiative order, so the strip is the array
// — and it only does since render.py sorted it by `Encounter.order`. It used
// to arrive in the order the world spawned its creatures, which is party then
// monsters every time and looks enough like an order to be believed.
//
// It replaces a vertical list that repeated each creature's initiative bonus.
// That number decides the order once, at the start of the fight, and answers
// nothing afterwards — worse, two creatures that rolled the same total are
// indistinguishable by it, so the one thing it looked like it was telling you
// it could not tell you. The order is the information; this is the order.

function renderOrder(s) {
  clear(el.order);
  for (const a of s.actors || []) {
    const down = isDown(a);
    const chip = div(`unit side-${a.side || "npc"}`);
    chip.dataset.actor = a.id;
    if (a.is_current) chip.classList.add("current");
    if (down) chip.classList.add("dead");

    const face = div("unit-face", shortLabel(a.label || a.id));
    chip.appendChild(face);

    const bar = div("unit-hp");
    const fill = div("unit-hp-fill");
    if (a.bloodied) fill.classList.add("bloodied");
    if (down) fill.classList.add("gone");
    fill.style.width = `${hpFraction(a) * 100}%`;
    bar.appendChild(fill);
    chip.appendChild(bar);

    chip.appendChild(div("unit-name", a.label || a.id));
    // One dot per effect, so "something is on this creature" survives the
    // shrink to an icon. What the something is, is on the card.
    const marks = (a.effects || []).length || (a.conditions || []).length;
    if (marks) {
      const dots = div("unit-dots");
      for (let i = 0; i < Math.min(marks, 4); i++) dots.appendChild(div("unit-dot"));
      chip.appendChild(dots);
    }

    chip.addEventListener("mouseenter", (ev) => {
      const token = el.board.querySelector(`.token[data-actor="${CSS.escape(a.id)}"]`);
      if (token) token.classList.add("peek");
      showCard(creatureCard(a, withNames), ev);
    });
    chip.addEventListener("mousemove", moveCard);
    chip.addEventListener("mouseleave", () => {
      for (const t of el.board.querySelectorAll(".token.peek")) t.classList.remove("peek");
      hideCard();
    });

    el.order.appendChild(chip);
  }
}

// ------------------------------------------------------------------ actions

function renderActions(s) {
  clear(el.actions);

  // A question outranks everything. The action it belongs to has begun and
  // cannot be un-begun, so there is nothing else to show and nothing to cancel
  // — no end-turn button, no powers, no movement. Answering is the only move.
  if (s.pending) {
    renderPending(s.pending);
    return;
  }

  const options = s.options || [];
  if (freeform && s.awaiting_input && options.length) {
    renderFreeform(s);
    return;
  }
  if (!s.awaiting_input || options.length === 0) {
    const why = s.status === "finished"
      ? "Encounter over."
      : s.current
        ? "Waiting on the other side."
        : "Waiting…";
    el.actions.appendChild(div("empty", why));
    return;
  }

  // Everything goes in the section it belongs to. An out-of-reach power sits
  // under STANDARD beside the attacks you *can* make, greyed and carrying its
  // reason — that is the comparison a player is actually making, and a list of
  // unusable powers parked at the bottom of the page is not in front of them
  // when they make it (#332).
  const buckets = new Map();
  const put = (cost, entry) => {
    if (!buckets.has(cost)) buckets.set(cost, []);
    buckets.get(cost).push(entry);
  };
  // End turn goes first, not last. It is the one action a player reaches for
  // when nothing in the list is worth doing, and hunting for it past nine
  // powers and four movement options is the wrong way round. Pulled out of the
  // buckets entirely so it is not also listed under "none" further down.
  const ending = options.find((o) => o.kind === END_TURN);
  if (ending) el.actions.appendChild(optionButton(s, ending));

  for (const o of options) {
    if (o === ending) continue;
    put(o.cost || "none", { option: o });
  }
  for (const p of s.roster || []) {
    // An available power is already in the list as its option(s); only the
    // ones that produced none need a row of their own. Traits and auras are
    // not actions at any price, so they go last under their own heading
    // rather than into the bucket a cost of "none" would put them in.
    if (p.available) continue;
    put(sectionFor(p), { power: p });
  }

  const costs = [...buckets.keys()].sort((a, b) => {
    const ia = COST_ORDER.indexOf(a);
    const ib = COST_ORDER.indexOf(b);
    return (ia < 0 ? COST_ORDER.length : ia) - (ib < 0 ? COST_ORDER.length : ib);
  });

  for (const cost of costs) {
    const group = buckets.get(cost);
    el.actions.appendChild(costHead(s, cost));

    // Best first, within the section. The scorer has weighed every option on
    // every turn it has ever taken and the list was showing them in whatever
    // order the engine enumerated them, so the strongest attack could sit
    // under three weaker ones.
    //
    // Sorting the *rendering* only. `index` is the position in
    // `legal_actions` and is what a click posts, so it travels with the entry
    // and reordering the page cannot disturb it (#325).
    //
    // Unavailable powers have no score — there is no option to score — so they
    // settle below everything that can actually be done.
    group.sort((a, b) => scoreOf(b) - scoreOf(a));

    for (const entry of group) {
      el.actions.appendChild(
        entry.option ? optionButton(s, entry.option) : unavailableRow(entry.power),
      );
    }
  }
}

/**
 * The question a half-taken action is waiting on.
 *
 * **Nothing here knows a rule.** The sentence at the top was written by the
 * server, every button's words came with it, and where each answer sits on the
 * board arrived as a list of squares — including the four a Large creature
 * fills, because working that out is a rule and this file must never answer
 * one. What goes back is the position of the button that was pressed.
 *
 * There is no cancel button because there is no cancel: an action that has
 * begun cannot be un-begun. The pre-selected answer is the engine's own, so a
 * player who does not care can press one thing and get the fight the engine
 * would have given them.
 */
function renderPending(p) {
  el.actions.appendChild(div("pending-prompt", withNames(p.prompt)));
  for (const a of p.answers || []) {
    const b = document.createElement("button");
    b.className = "option pending-answer";
    b.type = "button";
    b.disabled = settling();
    if (a.index === p.default) b.classList.add("suggested");
    const line = div("option-line");
    line.appendChild(div("option-label", withNames(a.label)));
    if (a.index === p.default) line.appendChild(div("option-usage", "the engine's pick"));
    b.appendChild(line);
    b.addEventListener("click", () => answer(p.chooser, a.index));
    b.addEventListener("mouseenter", () => highlightSquares(a.squares));
    b.addEventListener("mouseleave", () => highlight(null));
    el.actions.appendChild(b);
  }
}

/** Light up a bare list of squares — an answer's place on the board. */
function highlightSquares(squares) {
  clear(el.highlights);
  for (const sq of squares || []) {
    const h = div("hl hl-affected");
    place(h, squareRect(sq[0], sq[1]));
    el.highlights.appendChild(h);
  }
}

/** Every square any answer sits on, drawn so a player can see where to click. */
function renderPendingSquares(pending) {
  if (!pending) return;
  for (const a of pending.answers || []) {
    for (const sq of a.squares || []) {
      const h = div("mv mv-answer");
      place(h, squareRect(sq[0], sq[1]));
      el.movement.appendChild(h);
    }
  }
}

/**
 * Freeform: the powers, and nothing worked out for you.
 *
 * The enumerated list answers "which of these eleven attacks" and this answers
 * "what have I got" — the player supplies the target by pointing. Ending a
 * turn is still a button, because there is no square to point at for it.
 */
function renderFreeform(s) {
  const ending = (s.options || []).find((o) => o.kind === END_TURN);
  if (ending) el.actions.appendChild(optionButton(s, ending));

  el.actions.appendChild(
    div(
      "freeform-hint",
      aiming === null ? "Pick something, then click a square." : "Now click a square.",
    ),
  );

  // Grouped by what it costs, exactly as the enumerated mode groups. Freeform
  // used to show one flat "powers" heading, which hid the only question that
  // matters before you point at anything: what have I still got to spend. A
  // player with a standard left and a minor spent wants to see that.
  const buckets = new Map();
  const put = (cost, entry) => {
    if (!buckets.has(cost)) buckets.set(cost, []);
    buckets.get(cost).push(entry);
  };

  // Movement rides in its own section rather than in a bucket, because "move"
  // is both a cost and a thing you do, and the two would print the same word.
  const move = s.movement || { free: [], risky: [], shift: [] };
  const walkable = [...(move.free || []), ...(move.risky || [])];
  const risky = (move.risky || []).length;
  put("move", {
    movement: [
      "Move",
      "walk",
      walkable,
      risky ? `${risky} of them provoke` : "anywhere you can reach",
    ],
  });
  if ((move.shift || []).length) {
    put("move", { movement: ["Shift", "shift", move.shift, "one square, provokes nothing"] });
  }

  for (const p of s.roster || []) put(sectionFor(p), { power: p });

  // Actions with nothing to point at — total defense, a second wind, a buff on
  // yourself. Freeform showed none of them, because it only ever rendered the
  // roster and the roster is powers. They are offered as plain buttons for the
  // same reason ending a turn is: there is no square, so there is no aiming
  // step, and making a player hunt for a mode in which they exist is worse
  // than showing a button.
  const aimable = new Set();
  for (const p of s.roster || []) for (const i of p.option_indices || []) aimable.add(i);
  for (const o of s.options || []) {
    if (o === ending || aimable.has(o.index)) continue;
    if (o.kind === "move" || o.kind === "shift" || o.kind === "run") continue;
    put(o.cost || "none", { option: o });
  }

  const costs = [...buckets.keys()].sort((a, b) => {
    const ia = COST_ORDER.indexOf(a);
    const ib = COST_ORDER.indexOf(b);
    return (ia < 0 ? COST_ORDER.length : ia) - (ib < 0 ? COST_ORDER.length : ib);
  });

  for (const cost of costs) {
    el.actions.appendChild(costHead(s, cost));
    for (const entry of buckets.get(cost)) {
      if (entry.movement) {
        el.actions.appendChild(movementButton(...entry.movement, s));
      } else if (entry.option) {
        el.actions.appendChild(optionButton(s, entry.option));
      } else {
        el.actions.appendChild(freeformPower(s, entry.power));
      }
    }
  }
}

/** One power in freeform: click it, then click a square. */
function freeformPower(s, p) {
  // A power with nowhere to aim cannot be pointed anywhere, so it is shown the
  // same way the enumerated mode shows it: greyed, with the reason.
  if (!p.available || !(p.squares || []).length) return unavailableRow(p);

  const i = (s.roster || []).indexOf(p);
  const b = document.createElement("button");
  b.className = "option";
  b.type = "button";
  b.disabled = p.affordable === false || settling();
  if (p.affordable === false) b.classList.add("unaffordable");
  if (i === aiming) b.classList.add("aiming");

  const line = div("option-line");
  line.appendChild(div("option-label", p.name));
  line.appendChild(div("option-usage", p.usage || ""));
  b.appendChild(line);
  b.appendChild(usageBar(p));
  const foot = div("option-line");
  foot.appendChild(div("power-range", p.range_text || ""));
  const n = p.squares.length;
  foot.appendChild(div("power-link", `${n} square${n === 1 ? "" : "s"}`));
  b.appendChild(foot);
  // Same sentence the enumerated list shows, for the same reason: freeform is
  // the surface being played, and it was the one with no price on it at all.
  if (p.cost_note) b.appendChild(div("option-cost", p.cost_note));

  // Back to whatever is actually picked, which may be nothing.
  const restore = () => {
    if (typeof aiming === "number") showAimable((s.roster || [])[aiming]);
    else highlight(null);
  };
  b.addEventListener("mouseenter", () => {
    showCard(powerCard(p));
    showAimable(p);
  });
  b.addEventListener("mousemove", moveCard);
  b.addEventListener("mouseleave", () => {
    hideCard();
    restore();
  });
  // Keyboard, tabbing down the list: the squares a power can be aimed at are
  // the whole of what the row does not say.
  b.addEventListener("focus", () => showAimable(p));
  b.addEventListener("blur", restore);
  b.addEventListener("click", () => {
    aiming = aiming === i ? null : i;
    render();
    if (typeof aiming === "number") showAimable((state.roster || [])[aiming]);
  });
  return b;
}

/**
 * Whether an action slot can still be paid for, by itself or by a bigger one.
 *
 * Both halves come from the server: `spent` is what this turn has used and
 * `buys` is what would stand in. The page only puts them together.
 */
function costPayable(s, cost) {
  const economy = s.economy || {};
  return !(economy.spent || []).includes(cost) || Boolean((economy.buys || {})[cost]);
}

/** Move or shift, offered the way a power is. */
function movementButton(name, mode, squares, note, s) {
  const b = document.createElement("button");
  b.className = "option";
  b.type = "button";
  // Freeform walks by pointing, so there is no option carrying a price — and
  // with both the move and the standard gone the server refuses the walk. It
  // used to be offered anyway and answered with an error (#373).
  b.disabled = settling() || !squares.length || !costPayable(s, "move");
  if (aiming === mode) b.classList.add("aiming");

  const line = div("option-line");
  line.appendChild(div("option-label", name));
  line.appendChild(div("option-usage", s.round ? "" : ""));
  b.appendChild(line);
  const foot = div("option-line");
  foot.appendChild(div("power-range", note));
  foot.appendChild(
    div("power-link", `${squares.length} square${squares.length === 1 ? "" : "s"}`),
  );
  b.appendChild(foot);

  // Hovering the row is a preview of pressing it: the squares appear, and
  // go again when the pointer leaves unless the row is the one being aimed.
  const light = () => {
    clear(el.movement);
    for (const [tone, list] of [["risky", s.movement?.risky], ["free", s.movement?.free]]) {
      if (mode === "shift" && tone === "risky") continue;
      for (const sq of mode === "shift" ? squares : list || []) {
        const h = div(`mv mv-${tone}`);
        place(h, squareRect(sq[0], sq[1]));
        el.movement.appendChild(h);
      }
      if (mode === "shift") break;
    }
  };
  b.addEventListener("mouseenter", light);
  b.addEventListener("mouseleave", () => {
    if (aiming === null) highlight(null);
    else if (aiming === mode) light();
  });
  b.addEventListener("click", () => {
    aiming = aiming === mode ? null : mode;
    render();
    if (aiming === mode) light();
  });
  return b;
}

/**
 * Light the squares a power may be aimed at, and what one of them would hit.
 *
 * `at` is an aim square as `"x,y"`. For a blast or a burst the square you
 * click is not a square the power lands on — a blast 3 is aimed at the ring
 * two out and covers nine squares somewhere else entirely — so `footprints`
 * carries, per aim point, the squares it catches. **The server drew every one
 * of them**: which squares a shape covers is a rule, and none are read here.
 */
function showAimable(power, at) {
  clear(el.highlights);
  aimed = power || null;
  aimedAt = null;
  if (!power) return;
  for (const sq of power.squares || []) {
    const h = div("hl hl-affected");
    place(h, squareRect(sq[0], sq[1]));
    el.highlights.appendChild(h);
  }
  const covers = at ? (power.footprints || {})[at] : null;
  if (!covers) return;
  aimedAt = at;
  // After the aim squares, so it draws over them: this is the more specific
  // answer, the same way a hovered path draws over the movement range.
  for (const sq of covers) {
    const h = div("hl hl-hit");
    place(h, squareRect(sq[0], sq[1]));
    el.highlights.appendChild(h);
  }
}

/** Show what the aim square under the pointer would catch, if anything. */
function previewFootprint(at) {
  if (!aimed) return;
  const covers = (aimed.footprints || {})[at];
  if (covers ? at === aimedAt : aimedAt === null) return; // nothing changed
  showAimable(aimed, covers ? at : null);
}

/**
 * One section heading, struck through when that action has been spent.
 *
 * Read from `economy.spent`, which is the server's own turn bookkeeping. The
 * page used to work it out from the options instead — "every option in here is
 * unaffordable" — and that inference was wrong in the one case that costs a
 * player something: with the move gone, every move option is still affordable,
 * because the standard action pays for it. So the heading said the move was
 * still in hand (#373).
 *
 * `buys[cost]` is which action would pay, when one still can. The server
 * decides that; this only prints it.
 */
function costHead(s, cost) {
  const economy = s.economy || {};
  const head = div("cost-head", cost);
  if (!(economy.spent || []).includes(cost)) return head;
  head.classList.add("spent");
  const payer = (economy.buys || {})[cost];
  if (payer) head.appendChild(div("cost-buys", `${payer} pays`));
  return head;
}

/** An entry's score for ordering. Unavailable powers sink to the bottom. */
function scoreOf(entry) {
  if (!entry.option) return -Infinity;
  return typeof entry.option.score === "number" ? entry.option.score : 0;
}

/** Which heading an unusable power belongs under. Declared fields, not prose. */
function sectionFor(p) {
  if (p.action === "trait" || p.usage === "aura" || p.usage === "trait") return ALWAYS_ON;
  if (p.action === "triggered") return TRIGGERED;
  return p.cost || "none";
}

/** A power that produced no option: greyed, in its own section, with why. */
function unavailableRow(p) {
  const b = document.createElement("button");
  b.className = "option unavailable";
  b.type = "button";
  b.disabled = true;

  const line = div("option-line");
  line.appendChild(div("option-label", p.name));
  line.appendChild(div("option-usage", p.usage || ""));
  b.appendChild(line);
  b.appendChild(usageBar(p));

  const foot = div("option-line");
  foot.appendChild(div("power-range", p.range_text || ""));
  // `reason` is why the engine offered no option — out of reach, already
  // expended. `cost_note` is why the turn cannot pay for the one it did offer.
  // Either is a sentence; "not available now" is the fallback and says nothing,
  // which is what a spent action used to read as (#373).
  foot.appendChild(div("power-why", p.reason || p.cost_note || "not available now"));
  b.appendChild(foot);

  // `disabled` kills mouse events on a button in every browser, so the card
  // hangs off a wrapper that is still listening.
  const shell = div("option-shell");
  shell.appendChild(b);
  shell.addEventListener("mouseenter", (ev) => showCard(powerCard(p), ev));
  shell.addEventListener("mousemove", moveCard);
  shell.addEventListener("mouseleave", hideCard);
  return shell;
}

/**
 * The coloured rule under a power's name, as the sourcebooks print it: green
 * for at-will, red for encounter, grey for daily.
 *
 * Purely a reading of `usage`, which is the game's own vocabulary. A recharge
 * power is red — it comes back inside the fight, which is what the red band
 * means on the page.
 */
function usageBar(p) {
  const usage = String(p.usage || "").toLowerCase();
  let tone = "other";
  if (usage.startsWith("at will")) tone = "at-will";
  else if (usage.startsWith("encounter") || usage.startsWith("recharge")) tone = "encounter";
  else if (usage.startsWith("daily")) tone = "daily";
  return div(`usage-bar usage-${tone}`);
}

function optionButton(s, o) {
  const b = document.createElement("button");
  b.className = "option";
  b.type = "button";
  // affordable is false once the cost is spent this turn. Show it, greyed —
  // "my standard is gone" is information, a shorter list is not.
  const affordable = o.affordable !== false;
  b.disabled = !affordable || settling();
  if (!affordable) b.classList.add("unaffordable");
  if (o.kind) b.dataset.kind = o.kind;

  const label = o.label || o.kind || `#${o.index}`;
  const line = div("option-line");
  line.appendChild(div("option-label", label));
  // `targets` holds wire ids, and most labels already read "Power → <the
  // creature>". Printing the raw ids beside that put "npc_1" next to the name
  // it stands for. Resolve to labels and keep only what the label does not
  // already say — which leaves the self-buffs and the multi-target powers,
  // the two cases where it tells you something.
  const extra = namedTargets(o).filter((t) => !label.includes(t));
  if (extra.length) line.appendChild(div("option-targets", extra.join(", ")));
  b.appendChild(line);

  // The sourcebook's coloured band, between the name and everything else.
  // Only for options that are a power — moving and ending your turn have no
  // usage to colour.
  const power = rosterFor(s, o.index);
  if (power) {
    line.appendChild(div("option-usage", power.usage || ""));
    b.appendChild(usageBar(power));
  }

  // forecast is null on anything that is not an attack.
  if (o.forecast && o.forecast.summary) {
    b.appendChild(div("option-summary", o.forecast.summary));
  }
  // What it really costs, when that is not the heading it is sitting under.
  // Before the click, which is the whole of #373: a move with the move action
  // gone is paid for out of the standard, and the player was finding that out
  // afterwards by looking for the attack they no longer had.
  if (o.cost_note) b.appendChild(div("option-cost", o.cost_note));
  for (const n of o.notes || []) b.appendChild(div("option-note", n));

  b.addEventListener("mouseenter", (ev) => {
    highlight(o);
    // The power behind this option, if the roster has one for it — that is
    // where the stat-block text lives, and "50% to hit" does not say whether
    // the power dazes, slides or heals (#335).
    const p = rosterFor(s, o.index);
    if (p) showCard(powerCard(p), ev);
  });
  b.addEventListener("mousemove", moveCard);
  b.addEventListener("focus", () => highlight(o));
  b.addEventListener("mouseleave", () => {
    highlight(null);
    hideCard();
  });
  b.addEventListener("blur", () => highlight(null));
  b.addEventListener("click", () => act(s.current, o.index));
  return b;
}

/** The roster entry this option came from, if any. A join, not a rule. */
function rosterFor(s, index) {
  return (s.roster || []).find((p) => (p.option_indices || []).includes(index)) || null;
}

// ---------------------------------------------------------------------- log
//
// Two streams down one panel. `narration` frames are the fight as a reader
// wants it — one sentence per action, written server-side by
// content.render.plain_summary — and `encounter_event` frames are the engine
// talking to a developer. Both arrive in log order and are appended in arrival
// order, so the panel needs no sorting: the server closes a span and sends its
// sentence straight after the raw lines it summarises.
//
// No rules knowledge lives here. The client decides what is prominent; it
// never decides what happened.

function atLogBottom() {
  return el.log.scrollTop + el.log.clientHeight >= el.log.scrollHeight - 24;
}

function appendLog(row) {
  const stick = atLogBottom();
  el.log.appendChild(row);
  if (stick) el.log.scrollTop = el.log.scrollHeight;
}

function appendEvent(ev) {
  if (!ev) return;
  if (typeof ev.seq === "number") {
    if (ev.seq <= lastSeq) return; // replayed on reconnect
    lastSeq = ev.seq;
  }
  const row = div(`logline raw kind-${ev.kind || "event"}`);
  row.appendChild(div("log-seq", ev.seq ?? ""));
  row.appendChild(div("log-text", ev.text || ev.kind || ""));
  appendLog(row);
}

// A narration frame borrows the seq of the last event in its span, so two of
// them never share one and a strictly-increasing check dedupes a reconnect the
// same way `appendEvent` does. It is a separate counter because narration
// arrives *after* the event of the same seq, and one counter would swallow it.
function appendNarration(n) {
  if (!n || typeof n.text !== "string" || !n.text) return;
  if (typeof n.seq === "number") {
    if (n.seq <= lastNarration) return;
    lastNarration = n.seq;
  }
  // The only structure the raw log gave for free was `round_started`, and it
  // goes away with the raw lines. The round is on every narration frame, so
  // put the divider in when it changes.
  if (typeof n.round === "number" && n.round !== shownRound) {
    shownRound = n.round;
    appendLog(div("log-round", `Round ${n.round}`));
  }
  appendLog(div("narration", n.text));
}

function setRawShown(shown) {
  el.log.classList.toggle("with-raw", Boolean(shown));
}

// ---------------------------------------------------------------------- day
//
// The surge curve, which is the thing an adventuring day exists to reveal
// (#338). A short rest heals to full for exactly as long as there are surges
// to pay for it, so hit points come back flat and the whole of the attrition
// sits in the surge column — until the fight where it does not, which is the
// cliff.
//
// Nothing here is computed. Every number is a field of DayStateDTO and every
// sentence is the server's; this panel chooses layout, the same line the rest
// of the file draws.

function totals(party) {
  const hp = (party || []).reduce((n, s) => n + s.hp, 0);
  const hpMax = (party || []).reduce((n, s) => n + s.hp_max, 0);
  const surges = (party || []).reduce((n, s) => n + s.surges, 0);
  return { hp, hpMax, surges, pct: hpMax ? Math.round((100 * hp) / hpMax) : 0 };
}

function renderDay() {
  if (!day) {
    el.day.hidden = true;
    return;
  }
  el.day.hidden = false;
  clear(el.dayLegs);
  clear(el.dayCurve);
  clear(el.dayFoot);

  for (const leg of day.legs || []) {
    const chip = div(`leg leg-${leg.status}`);
    if (leg.index === day.leg && !day.finished) chip.classList.add("current");
    chip.appendChild(div("leg-n", `${leg.index + 1}`));
    chip.appendChild(div("leg-scale", `×${leg.scale}`));
    chip.appendChild(
      div("leg-note", leg.rounds ? `${leg.status}, ${leg.rounds} rounds` : leg.status),
    );
    el.dayLegs.appendChild(chip);
  }

  // One row per fight that has happened: what the party brought in, what the
  // fight left, and what the rest could buy back. The third minus the second
  // is what the fight actually cost, and it is usually the larger half.
  for (const leg of day.legs || []) {
    if (leg.status === "pending" || !leg.ended.length) continue;
    const row = div("curve-row");
    const inn = totals(leg.entering);
    const out = totals(leg.ended);
    const rest = totals(leg.rested);
    row.appendChild(div("curve-n", `fight ${leg.index + 1}`));
    row.appendChild(
      div(
        "curve-line",
        `${inn.pct}% hp / ${inn.surges} surges → ended ${out.pct}% → rested to ` +
          `${rest.pct}% (${rest.surges} left)`,
      ),
    );
    // Per character, because surges are **personal** and do not pool: the
    // party can hold five and be unable to spend one, since the character who
    // needs them is not the one holding them. That is invisible in the total
    // and it is the reason a day ends when it does.
    const who = div("curve-who");
    for (const s of leg.rested) {
      const pip = div("surge-pips");
      pip.appendChild(div("pip-name", s.label || s.id));
      const track = div("pip-track");
      for (let i = 0; i < s.surges_max; i++) {
        track.appendChild(div(i < s.surges ? "pip" : "pip spent"));
      }
      pip.appendChild(track);
      pip.appendChild(div("pip-count", `${s.surges}/${s.surges_max}`));
      if (!s.surges) pip.classList.add("dry");
      who.appendChild(pip);
    }
    row.appendChild(who);
    // Through the same rewriter an effect's text goes through. The server
    // writes the rest report with wire ids — deliberately, because an id is
    // what survives the name switch — and the line above it in this very panel
    // says "Dwarf Fighter", so leaving it would print two names for one
    // character two lines apart. With names off every label *is* its wire id
    // and this does nothing.
    if (leg.rest_text) row.appendChild(div("curve-rest", withNames(leg.rest_text)));
    if (leg.exhausted) {
      row.appendChild(div("curve-warn", "The surges to heal to full are gone."));
    }
    el.dayCurve.appendChild(row);
  }

  if (day.finished) {
    el.dayFoot.appendChild(div("day-outcome", day.outcome || "The day ends."));
    return;
  }
  if (day.awaiting_next) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "day-next";
    b.textContent = `Walk into encounter ${day.leg + 1} (×${day.scales[day.leg]})`;
    b.addEventListener("click", nextEncounter);
    el.dayFoot.appendChild(b);
  }
}

async function refreshDay() {
  if (!day) return;
  try {
    day = await getJSON(`/api/day/${day.id}`);
  } catch (e) {
    say(`Could not read the day: ${e.message}`, "bad");
    return;
  }
  renderDay();
}

async function nextEncounter() {
  if (!day || busy) return;
  busy = true;
  say("Building the next encounter…");
  try {
    day = await postJSON(`/api/day/${day.id}/next`, {});
    renderDay();
    await openEncounter(day.encounter);
  } catch (e) {
    say(`Could not start the next encounter: ${e.message}`, "bad");
  } finally {
    busy = false;
  }
}

// -------------------------------------------------------------------- state

/**
 * Take a new snapshot, but not before the board has finished showing the last
 * one's events.
 *
 * The engine applies a whole turn at once, so the state frame for "the goblin
 * walked six squares and hit you" arrives in the same burst as the six `moved`
 * events. Rendering it straight away puts the goblin at its destination before
 * the walk has been drawn, and the walk then plays from a token that is
 * already there — which looks like nothing happening at all.
 *
 * So the snapshot waits, and `anim`'s idle callback lets it through. Nothing
 * is dropped: a newer snapshot simply replaces the one waiting, which is right,
 * because a snapshot is a whole picture and not a delta.
 */
function commit(next) {
  pendingState = next;
  maybeCommit();
}

// Let a held snapshot through once the board has caught up with it, or after
// this long if the events explaining it never arrive — a closed stream, or a
// turn that emitted nothing worth animating.
const CATCH_UP_MS = 1500;
let catchUp = null;

function maybeCommit() {
  if (!pendingState || anim.busy()) return;
  // `POST /act` answers with the state *after* the monsters have moved, and
  // beats its own events down the stream. Committing on arrival puts every
  // creature at its final square, and the walk then plays from a token that
  // is already there — which looks like nothing happening at all. So the
  // snapshot waits for the stream to reach the seq it was taken at.
  const behind = anim.stepMs() > 0 && animatedThrough < (pendingState.seq ?? 0);
  if (behind) {
    if (catchUp === null) catchUp = setTimeout(force, CATCH_UP_MS);
    return;
  }
  force();
}

function force() {
  if (catchUp !== null) {
    clearTimeout(catchUp);
    catchUp = null;
  }
  // The timer is a *stall* detector, not a deadline. It fired regardless, so
  // a monster round — four creatures, six squares each, two dozen steps — ran
  // past 1500ms and the snapshot was forced through mid-walk. `render` puts
  // every token on its real square, so the enemies stopped where they were
  // and reappeared at the far end: the whole monster turn animated for a
  // second and a half and then jumped. If the animator is still working it
  // has not stalled, so wait for it and come back.
  if (anim.busy()) {
    catchUp = setTimeout(force, CATCH_UP_MS);
    return;
  }
  if (!pendingState) return;
  state = pendingState;
  pendingState = null;
  // Whatever was half-aimed described the board before this snapshot.
  aiming = null;
  render();
}

function render() {
  const s = state;
  if (!s) return;
  // Every render puts each token at the square it actually stands on, with no
  // transform, so whatever the animator had slid them by is spent. Clearing it
  // here rather than beside one caller is the whole point: `act`, `done`,
  // `openEncounter` and the day panel all render, and any of them leaving a
  // stale total behind made the *next* walk start from it — a creature would
  // slide to a square it was not on while the game had it in the right one.
  anim.reset();
  el.board.classList.toggle("freeform", freeform && Boolean(s.awaiting_input) && !s.pending);
  // The board is a control while a question is open, in either mode: the
  // answers are squares and clicking one is how you give it.
  el.board.classList.toggle("deciding", Boolean(s.pending));
  // The card is built from a snapshot, so anything on screen from the last one
  // is about a board that no longer exists.
  hideCard();
  renderBoard(s);
  renderOrder(s);
  renderActions(s);

  const current = (s.actors || []).find((a) => a.id === s.current);
  const who = current ? current.label || current.id : "—";
  const bits = [`Round ${s.round ?? "?"}`, `seed ${s.seed ?? "?"}`, `#${s.seq ?? 0}`];
  if (s.status === "finished") {
    bits.push(
      s.winner ? `${s.winner} wins in ${s.rounds ?? s.round ?? "?"} rounds` : "finished",
    );
    el.turn.textContent = "Encounter over";
    el.turn.className = "turn over";
  } else {
    if (s.pending) {
      const asked = (s.actors || []).find((a) => a.id === s.pending.chooser);
      el.turn.textContent = `${asked ? asked.label || asked.id : who} — your call`;
      el.turn.className = "turn yours deciding";
    } else {
      el.turn.textContent = s.awaiting_input ? `Your turn — ${who}` : `${who} is acting`;
      el.turn.className = s.awaiting_input ? "turn yours" : "turn";
    }
  }
  document.getElementById("meta").textContent = bits.join("  ·  ");
}

/**
 * Freeform's write: point at a square.
 *
 * `powerIndex` null means "walk there". Both go to `POST /aim`, which resolves
 * to an ordinary option and applies it the same way a click on the action list
 * would — the two modes differ in what they show, not in what the engine
 * accepts.
 */
async function aimAt(square, powerIndex, mode) {
  if (busy || !state || !state.current) return;
  busy = true;
  render();
  say("");
  try {
    const body = { actor_id: state.current, square };
    if (typeof powerIndex === "number") body.power_index = powerIndex;
    if (mode) body.mode = mode;
    const reply = await postJSON(`/api/encounter/${state.id}/aim`, body);
    aiming = null;
    highlight(null);
    if (reply.status === "finished") await refreshDay();
    commit(reply);
  } catch (e) {
    say(`${e.message}`, "bad");
  } finally {
    busy = false;
    if (!anim.busy()) render();
  }
}

/**
 * Answer the question, and let the action finish.
 *
 * Its own call rather than a flag on `act`, because it is a different thing:
 * `act` starts something and this finishes something already started. The
 * reply is the ordinary snapshot — a second question if the power asks two,
 * otherwise the turn as it stands once the action has landed.
 */
async function answer(actorId, index) {
  if (busy || !state || typeof index !== "number") return;
  busy = true;
  render();
  say("");
  try {
    const reply = await postJSON(`/api/encounter/${state.id}/decide`, {
      actor_id: actorId,
      answer_index: index,
    });
    highlight(null);
    if (reply.status === "finished") await refreshDay();
    commit(reply);
  } catch (e) {
    say(`${e.message}`, "bad");
  } finally {
    busy = false;
    if (!anim.busy()) render();
  }
}

async function act(actorId, index) {
  if (busy || !state || !actorId || typeof index !== "number") return;
  busy = true;
  render();
  say("");
  try {
    // Through `commit`, not straight into `state`: this reply is the snapshot
    // *after* the monsters have taken their turns, and the events that explain
    // them are still arriving on the stream. Assigning it here would put every
    // creature at its final square before the board had shown a single step.
    const reply = await postJSON(`/api/encounter/${state.id}/act`, {
      actor_id: actorId,
      action_index: index,
    });
    highlight(null);
    // The server harvests and rests the instant the fight ends — inside this
    // very request — so by the time it answers, the day already knows what the
    // fight cost. Nothing to poll for.
    if (reply.status === "finished") await refreshDay();
    commit(reply);
  } catch (e) {
    // An option index is only meaningful for the snapshot it came from, and
    // the board can still be showing an older one while the animation
    // catches up — so a click can carry an index the server has already
    // moved past. That is not a failure worth shouting about; it is a stale
    // list. Fetch the current one and let the player pick again.
    if (/no option/i.test(e.message)) {
      commit(await getJSON(`/api/encounter/${state.id}`));
      say("That list was out of date — try again.", "warn");
    } else {
      say(`Action failed: ${e.message}`, "bad");
    }
  } finally {
    busy = false;
    if (!anim.busy()) render();
  }
}

function connect() {
  if (stream) stream.close();
  // `from` is exclusive and event seq is 1-based, so from=0 is the whole log
  // — the panel opens with the full story rather than joining mid-fight.
  // appendEvent still dedupes by seq because EventSource resends
  // Last-Event-ID on reconnect, which can overlap what we already have.
  stream = new EventSource(`/api/encounter/${state.id}/events?from=0`);

  stream.addEventListener("encounter_event", (e) => {
    try {
      const ev = JSON.parse(e.data);
      appendEvent(ev);
      // Only events newer than the cursor are worth watching. A reconnect
      // replays the whole log, and re-animating a fight the player has
      // already seen would strand them behind a wall of old movement.
      if (ev.seq > animatedThrough) {
        animatedThrough = ev.seq;
        anim.enqueue(ev);
        // The arrival may be the one a held snapshot was waiting for.
        maybeCommit();
      }
    } catch (err) {
      console.warn("bad event payload", err, e.data);
    }
  });

  stream.addEventListener("narration", (e) => {
    try {
      appendNarration(JSON.parse(e.data));
    } catch (err) {
      console.warn("bad narration payload", err, e.data);
    }
  });

  stream.addEventListener("state", (e) => {
    try {
      commit(JSON.parse(e.data));
      say("");
    } catch (err) {
      console.warn("bad state payload", err, e.data);
    }
  });

  stream.addEventListener("done", (e) => {
    try {
      if (e.data) {
        const payload = JSON.parse(e.data);
        if (payload && payload.board) {
          state = payload;
          render();
        }
      }
    } catch {
      /* done may carry no body */
    }
    stream.close();
    stream = null;
    say("Stream closed — encounter finished.", "ok");
    // The other way a fight can end: the monsters finished it on their own
    // turn, so no `POST /act` of ours came back saying so.
    refreshDay();
  });

  stream.onerror = () => {
    if (stream && stream.readyState === EventSource.CLOSED) {
      say("Stream closed.", "bad");
    } else {
      say("Reconnecting…", "warn");
    }
  };
}

// --------------------------------------------------------------- the config
//
// Three numbers and a checkbox, which is the whole of #338's form: how strong
// the party is, how hard the fight is, and whether this is one fight or a day.
// Deliberately not a settings panel — everything else `POST /api/encounter`
// takes has a server-side default and the page is better for not restating it.

const cfg = {
  level: document.getElementById("level"),
  party: document.getElementById("party"),
  enemies: document.getElementById("enemies"),
  enemiesField: document.getElementById("enemies-field"),
  seed: document.getElementById("seed"),
  scale: document.getElementById("scale"),
  dayOn: document.getElementById("day-on"),
  dayScales: document.getElementById("day-scales"),
  scaleField: document.getElementById("scale-field"),
  form: document.getElementById("config"),
};

function number(input, fallback) {
  const v = Number.parseFloat(input.value);
  return Number.isFinite(v) ? v : fallback;
}

/** A comma-separated box as a list, or nothing at all when it is empty. */
function list(input) {
  const items = input.value
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  return items.length ? items : null;
}

/**
 * The body for `POST /api/encounter`.
 *
 * **A key is omitted rather than defaulted whenever its box is empty**, and
 * that is the whole shape of this function. Every field has a server-side
 * default and two of them are not constants — an empty `enemies` builds a
 * fight worth the party, an absent `seed` draws one and keeps it (#337). A
 * client that filled those in would be a second copy of the defaults, which
 * this file has already been wrong about once, and it would write the names
 * of the default party into a static asset (#325).
 */
function commonBody() {
  const body = { level: Math.round(number(cfg.level, 1)) };
  const party = list(cfg.party);
  if (party) body.pcs = party;
  const seed = Number.parseInt(cfg.seed.value, 10);
  if (Number.isFinite(seed)) body.seed = seed;
  return body;
}

function encounterBody() {
  const body = { ...commonBody(), scale: number(cfg.scale, 1.25) };
  const enemies = list(cfg.enemies);
  if (enemies) body.enemies = enemies;
  return body;
}

/**
 * The body for `POST /api/day`.
 *
 * Built from `commonBody` rather than from its own reading of the form. It
 * used to send `{level, scales}` and nothing else, so a day ignored the party
 * you typed and ran the default one — the form looked like it worked and
 * quietly did not.
 *
 * No `enemies`: a day builds each fight to a budget, so there is nothing for a
 * named monster to be. The box is hidden while the checkbox is ticked rather
 * than being sent and dropped on the floor.
 */
function dayBody() {
  return {
    ...commonBody(),
    scales: [...cfg.dayScales.querySelectorAll(".leg-scale")].map((i) => number(i, 1)),
  };
}

/** Show the four per-encounter multipliers only when they mean something. */
function syncConfig() {
  const on = cfg.dayOn.checked;
  cfg.dayScales.hidden = !on;
  // Hidden rather than disabled-in-place: with a day running, the single
  // multiplier is not "the same setting greyed out", it is a different
  // question, and the four boxes are the answer to it.
  cfg.scaleField.hidden = on;
  // A day has no enemies box to honour: every fight is built to a budget, so
  // a named monster has nowhere to go. Hidden rather than ignored.
  cfg.enemiesField.hidden = on;
  document.getElementById("restart").textContent = on ? "Start the day" : "Start";
}

/** Open one encounter — a standalone fight, or one leg of a day. */
async function openEncounter(encounterId) {
  say("Loading the encounter…");
  try {
    state = await getJSON(`/api/encounter/${encounterId}`);
  } catch (e) {
    say(`Could not read the encounter: ${e.message}`, "bad");
    return;
  }
  lastSeq = -1;
  lastNarration = -1;
  shownRound = null;
  // Everything already in the log happened before the player was looking.
  // Without this the page opens by replaying the whole fight so far, one
  // step at a time, before it will accept a click.
  animatedThrough = state.seq ?? -1;
  clear(el.log);
  render();
  say("");
  connect();
}

async function start() {
  if (stream) {
    stream.close();
    stream = null;
  }
  anim.flush();
  animatedThrough = -1;
  if (cfg.dayOn.checked) {
    say("Building the day…");
    try {
      day = await postJSON("/api/day", dayBody());
    } catch (e) {
      day = null;
      renderDay();
      say(`Could not start a day: ${e.message}`, "bad");
      return;
    }
    renderDay();
    await openEncounter(day.encounter);
    return;
  }
  day = null;
  renderDay();
  say("Starting encounter…");
  try {
    state = await postJSON("/api/encounter", encounterBody());
  } catch (e) {
    say(`Could not start an encounter: ${e.message}`, "bad");
    return;
  }
  lastSeq = -1;
  lastNarration = -1;
  shownRound = null;
  // Everything already in the log happened before the player was looking.
  // Without this the page opens by replaying the whole fight so far, one
  // step at a time, before it will accept a click.
  animatedThrough = state.seq ?? -1;
  clear(el.log);
  render();
  say("");
  connect();
}

// ----------------------------------------------------------------- settings

const gear = document.getElementById("settings-btn");
const settings = document.getElementById("settings");
const speedPicker = document.getElementById("speed");

for (const [name, spec] of Object.entries(anim.SPEEDS)) {
  const option = document.createElement("option");
  option.value = name;
  option.textContent = spec.label;
  speedPicker.appendChild(option);
}
speedPicker.value = anim.getSpeed();
speedPicker.addEventListener("change", () => anim.setSpeed(speedPicker.value));

const freeformBox = document.getElementById("freeform");
freeformBox.checked = freeform;
freeformBox.addEventListener("change", () => {
  freeform = freeformBox.checked;
  try {
    localStorage.setItem("dnd4e.freeform", freeform ? "on" : "off");
  } catch {
    /* storage off; the mode still works for this session */
  }
  // A power half-aimed in one mode means nothing in the other.
  aiming = null;
  highlight(null);
  render();
});

gear.addEventListener("click", () => {
  settings.hidden = !settings.hidden;
});
// Click anywhere else to put it away. A settings panel that only closes by its
// own button is one more thing to remember.
document.addEventListener("click", (ev) => {
  if (!settings.hidden && !settings.contains(ev.target) && ev.target !== gear) {
    settings.hidden = true;
  }
});

// The animator needs two things from the page: how to find a token, and
// somewhere to hand the board back when it has finished playing.
anim.init({
  tokenFor: (actorId) =>
    el.board.querySelector(`.token[data-actor="${CSS.escape(actorId)}"]`),
  onIdle: maybeCommit,
});

// Freeform's one gesture. The board is a control in this mode: click a square
// to use the power you picked, or — with nothing picked — to walk there.
//
// No rules here. Which squares are legal came from the server (a power's
// `squares`, and `movement.free` / `movement.risky`), and what a click means
// is decided by the server too; this only refuses to send one the server has
// already said is not on.
el.board.addEventListener("click", (ev) => {
  if (!state || busy) return;
  // A question turns the board into the answer sheet, in both modes. The
  // squares each answer covers came from the server — a Large creature fills
  // four of them and working out which four is a rule — so this is a lookup
  // and not a reading of the board.
  if (state.pending) {
    const { x, y } = pointerSquare(el.board, ev);
    const found = (state.pending.answers || []).find((a) =>
      (a.squares || []).some((s) => s[0] === x && s[1] === y),
    );
    if (found) answer(state.pending.chooser, found.index);
    else say("Nothing to choose on that square.", "warn");
    return;
  }
  if (!freeform || !state.awaiting_input) return;
  const { x, y } = pointerSquare(el.board, ev);
  const square = [x, y];
  const move = state.movement || { free: [], risky: [], shift: [] };
  const here = (list) => (list || []).some((s) => s[0] === x && s[1] === y);

  if (aiming === "walk" || aiming === null) {
    // Bare board with nothing picked still walks, because it is the gesture
    // anybody tries first.
    if (here(move.free) || here(move.risky)) aimAt(square, null, "walk");
    else if (aiming === "walk") say("You cannot reach that square.", "warn");
    return;
  }
  if (aiming === "shift") {
    if (here(move.shift)) aimAt(square, null, "shift");
    else say("A shift is one square, and not onto somebody else.", "warn");
    return;
  }
  const power = (state.roster || [])[aiming];
  if (power && here(power.squares)) aimAt(square, aiming);
  else say("That power cannot be aimed there.", "warn");
});

el.board.addEventListener("mousemove", (ev) => {
  const { x, y } = pointerSquare(el.board, ev);
  el.hover.textContent = `(${x}, ${y})`;
  // Point at an aim square and the blast it would make appears under the
  // pointer. The board is the only place to do this: aiming is picked in the
  // action list and the aim point is a square, so there is nothing else to
  // hover.
  previewFootprint(`${x},${y}`);
  previewPath(`${x},${y}`);
});
el.board.addEventListener("mouseleave", () => {
  el.hover.textContent = "";
  previewFootprint(null);
  previewPath(null);
});

const rawToggle = document.getElementById("show-raw");
rawToggle.addEventListener("change", () => setRawShown(rawToggle.checked));
setRawShown(rawToggle.checked);

cfg.dayOn.addEventListener("change", syncConfig);
syncConfig();

// On the form's submit rather than the button's click, so Enter in any of the
// number fields starts the fight the same way the button does.
cfg.form.addEventListener("submit", (ev) => {
  ev.preventDefault();
  start();
});

start();
