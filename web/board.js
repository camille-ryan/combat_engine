/**
 * Drawing a board from one snapshot. No fetch, no clicks, no live session.
 *
 * Split out of `app.js` so a second page can draw the same board. `app.js` is all
 * module-level side effects -- it looks up its DOM and wires every listener at import
 * time -- so importing it from another page would wire the live encounter's handlers to
 * elements that are not there. Nothing in this file has a side effect at import.
 *
 * **The three overlay layers are found by id**, which is the contract with both pages:
 * `#board`, `#movement`, `#highlights`, same size, absolutely positioned, siblings inside
 * `.board-wrap`. `coords.place` writes identical offsets into all three, so a page that
 * nests them differently draws the board in the wrong place and nothing says so.
 *
 * `renderBoard` clears and redraws everything. Nothing here is incremental, which is the
 * rule in `web/CLAUDE.md` and the reason this is safe to call from a timeline scrubber.
 */

import {
  creatureCard,
  hideCard,
  moveCard,
  showCard,
  thingCard,
  zoneCard,
} from "./card.js";
import { boardPixelSize, place, squareRect, squaresRect } from "./coords.js";
import { clear, div } from "./dom.js";

/**
 * The snapshot currently on screen, set by `renderBoard`.
 *
 * **Held so the hover cards read the frame being drawn.** In `app.js` the equivalent
 * lookup read the module-global `state`, which on the live page is the same object
 * `renderBoard` was handed -- but only by coincidence of call order. A replay scrubs
 * between frames, where "the snapshot being drawn" and "the newest snapshot" are
 * routinely different things, and a card built from the wrong one is a card describing a
 * creature's hit points two turns from now.
 */
let shown = null;

const layer = (id) => document.getElementById(id);
const key = (sq) => `${sq[0]},${sq[1]}`;

function setOf(squares) {
  return new Set((squares || []).map(key));
}

/** The actors of the frame on screen, by wire id. */
export function actorsById() {
  return new Map((shown && shown.actors ? shown.actors : []).map((a) => [a.id, a]));
}

/** Wire ids as the names on screen. A rewrite, not a rule -- see `app.js`. */
const WIRE_ID = /\b(?:pc|npc)_\d+\b/g;

export function withNames(text) {
  if (!text) return text;
  const byId = actorsById();
  return String(text).replace(WIRE_ID, (id) => (byId.get(id) || {}).label || id);
}

export function isDown(actor) {
  return Boolean(actor.dead) || (actor.hp ?? 1) <= 0;
}

export function hpFraction(actor) {
  const max = actor.hp_max || 0;
  if (max <= 0) return 0;
  const hp = Math.max(0, Math.min(actor.hp ?? 0, max));
  return hp / max;
}

export function shortLabel(label) {
  const words = String(label).trim().split(/\s+/);
  if (words.length === 1) return words[0].slice(0, 6);
  return words
    .map((w) => w[0])
    .join("")
    .slice(0, 4)
    .toUpperCase();
}

/**
 * Attach the hover card to anything. `build` is called on entry rather than up front, so
 * a card is only assembled for the one thing being looked at.
 */
export function hovers(node, build) {
  node.addEventListener("mouseenter", (ev) => showCard(build(), ev));
  node.addEventListener("mousemove", moveCard);
  node.addEventListener("mouseleave", hideCard);
}

/** The squares one way of moving reaches, in two tones. Risky first, because
 * `scripts/browser.py` clicks `.mv-free` and relies on the build order. */
function movementTones(movement, mode) {
  const m = movement || {};
  if (mode === "shift") {
    return [
      ["risky", []],
      ["free", m.shift || []],
    ];
  }
  if (mode === "run") {
    const warned = m.warnings || {};
    const risky = [];
    const free = [];
    for (const sq of m.run || []) (warned[key(sq)] ? risky : free).push(sq);
    return [
      ["risky", risky],
      ["free", free],
    ];
  }
  return [
    ["risky", m.risky || []],
    ["free", m.free || []],
  ];
}

export function paintMovement(movement, mode) {
  const movementLayer = layer("movement");
  clear(movementLayer);
  for (const [tone, squares] of movementTones(movement, mode)) {
    for (const sq of squares) {
      const h = div(`mv mv-${tone}`);
      place(h, squareRect(sq[0], sq[1]));
      movementLayer.appendChild(h);
    }
  }
}

/** With a question open there is no movement range, so the same layer shows the squares
 * the answers are on instead. */
export function renderPendingSquares(pending) {
  if (!pending) return;
  const movementLayer = layer("movement");
  for (const a of pending.answers || []) {
    for (const sq of a.squares || []) {
      const h = div("mv mv-answer");
      place(h, squareRect(sq[0], sq[1]));
      movementLayer.appendChild(h);
    }
  }
}

/**
 * Everything on the board, from one snapshot.
 *
 * Terrain, then zones, then things, then tokens -- appended in that order so a creature
 * standing on something still wins the hover.
 *
 * Does **not** paint the movement range: that is the caller's business, because on the
 * live page it is drawn only while somebody has pressed Move, and a replay has nobody
 * pressing anything. Call `paintMovement` after this if you want it.
 */
export function renderBoard(s) {
  shown = s;
  const board = s.board || {};
  const width = board.width || 0;
  const height = board.height || 0;

  const boardLayer = layer("board");
  clear(boardLayer);
  clear(layer("movement"));
  clear(layer("highlights"));

  const size = boardPixelSize(width, height);
  for (const id of ["board", "movement", "highlights"]) {
    const node = layer(id);
    node.style.width = `${size.width}px`;
    node.style.height = `${size.height}px`;
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
      boardLayer.appendChild(tile);
    }
  }

  (board.zones || []).forEach((zone, i) => {
    const squares = zone.squares || [];
    for (const sq of squares) {
      const z = div(`zone zone-${i % 4}`);
      place(z, squareRect(sq[0], sq[1]));
      const owner = (actorsById().get(zone.owner) || {}).label || zone.owner;
      hovers(z, () => zoneCard(zone, owner));
      boardLayer.appendChild(z);
    }
    if (squares.length) {
      const tag = div("zone-label", zone.label || zone.id || "");
      const r = squaresRect(squares);
      tag.style.left = `${r.left}px`;
      tag.style.top = `${r.top}px`;
      boardLayer.appendChild(tag);
    }
  });

  for (const thing of board.things || []) {
    for (const sq of thing.squares || []) {
      const t = div(`thing thing-${thing.kind}${thing.sprung ? " sprung" : ""}`);
      place(t, squareRect(sq[0], sq[1]));
      hovers(t, () => thingCard(thing));
      boardLayer.appendChild(t);
    }
  }

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

    boardLayer.appendChild(token);
  }
}

/** The initiative strip. `s.actors` arrives already sorted by the server. */
export function renderOrder(s) {
  const orderLayer = layer("order");
  const boardLayer = layer("board");
  clear(orderLayer);
  for (const a of s.actors || []) {
    const down = isDown(a);
    const chip = div(`unit side-${a.side || "npc"}`);
    chip.dataset.actor = a.id;
    if (a.is_current) chip.classList.add("current");
    if (down) chip.classList.add("dead");

    chip.appendChild(div("unit-face", shortLabel(a.label || a.id)));

    const bar = div("unit-hp");
    const fill = div("unit-hp-fill");
    if (a.bloodied) fill.classList.add("bloodied");
    if (down) fill.classList.add("gone");
    fill.style.width = `${hpFraction(a) * 100}%`;
    bar.appendChild(fill);
    chip.appendChild(bar);

    chip.appendChild(div("unit-name", a.label || a.id));
    // One dot per effect *and* condition, added rather than `||` -- see `app.js`.
    const marks = (a.effects || []).length + (a.conditions || []).length;
    if (marks) {
      const dots = div("unit-dots");
      for (let i = 0; i < Math.min(marks, 4); i++) dots.appendChild(div("unit-dot"));
      chip.appendChild(dots);
    }

    chip.addEventListener("mouseenter", (ev) => {
      const token = boardLayer.querySelector(`.token[data-actor="${CSS.escape(a.id)}"]`);
      if (token) token.classList.add("peek");
      showCard(creatureCard(a, withNames), ev);
    });
    chip.addEventListener("mousemove", moveCard);
    chip.addEventListener("mouseleave", () => {
      for (const t of boardLayer.querySelectorAll(".token.peek")) t.classList.remove("peek");
      hideCard();
    });

    orderLayer.appendChild(chip);
  }
}
