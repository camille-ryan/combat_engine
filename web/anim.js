// anim.js — the board, played back rather than snapped to.
//
// The engine applies a whole turn synchronously, so every event of that turn
// reaches the page in one burst: a creature walked six squares, swung, and hit,
// all in the same tick. Rendering each state frame as it arrived made tokens
// teleport, and a player watching the board could not tell who had moved or
// what had hit them. The log said so and the board did not.
//
// So events go in a queue and are played back one at a time, and the board is
// held at the old snapshot until the queue drains. That is the whole design,
// and the ordering it produces is the ordering the log already has.
//
// **No rules live here.** A step says "this creature moved from here to there"
// or "this one was hit"; what that meant is the server's business. Nothing in
// this file reads a power, a defence, or a hit point.
//
// Pixels come from coords.js. This module reads element rectangles to find out
// which way one token lies from another, which is a layout question and not a
// coordinate conversion — it never multiplies by a tile size of its own.

import { squareDelta, tilesAlong } from "./coords.js";

// How long one step takes. "Instant" is not a speed but a switch: it empties
// the queue on arrival, so the board behaves exactly as it did before any of
// this existed, which is the right escape hatch for somebody who wants to
// click through a fight quickly.
export const SPEEDS = {
  instant: { ms: 0, label: "Instant" },
  fast: { ms: 90, label: "Fast" },
  normal: { ms: 190, label: "Normal" },
  slow: { ms: 380, label: "Slow" },
};

const STORE_KEY = "dnd4e.speed";

// How far a creature leans when it attacks, and how far it rocks when hit,
// in tiles. Both are the numbers the board was asked for.
const LUNGE_TILES = 0.5;
const RECOIL_TILES = 0.25;

let speed = read();
let tokenFor = () => null;
let onIdle = () => {};

const queue = [];
let running = false;
// How far each actor's token has been slid from where the last render put it.
// Cleared when the board is rendered again, because that render puts every
// token where it actually stands.
const offsets = new Map();

function read() {
  try {
    const saved = localStorage.getItem(STORE_KEY);
    return saved && SPEEDS[saved] ? saved : "normal";
  } catch {
    return "normal"; // private browsing, or storage switched off
  }
}

/** Wire up the animator. `tokenFor(actorId)` returns the element, or null. */
export function init(options) {
  tokenFor = options.tokenFor;
  onIdle = options.onIdle;
}

export function getSpeed() {
  return speed;
}

export function setSpeed(name) {
  if (!SPEEDS[name]) return;
  speed = name;
  try {
    localStorage.setItem(STORE_KEY, name);
  } catch {
    /* not worth telling anybody about */
  }
  // Switching to instant mid-fight must not strand a half-played queue.
  if (stepMs() === 0) flush();
}

export function stepMs() {
  return SPEEDS[speed].ms;
}

/** Whether the board is mid-playback and a render would jump ahead of it. */
export function busy() {
  return running || queue.length > 0;
}

/**
 * Forget the playback: where tokens have been slid to, and what was still
 * queued to happen to them.
 *
 * Called just before the board is redrawn, and both halves matter.
 *
 * The offsets are spent, because a render puts every token at the square it
 * actually stands on with no transform — carrying them over would slide the
 * next walk twice as far.
 *
 * The **queue** is stale for a subtler reason, and this is the one that put a
 * creature outside the board. A render that lands mid-playback has jumped the
 * board to a position those steps were describing the route *to*. Replaying
 * them afterwards slides a token that has already arrived by the same deltas
 * again, and six steps of that walks it off the edge while the game has it in
 * the right square all along. A superseded step is not worth showing late.
 */
export function reset() {
  offsets.clear();
  queue.length = 0;
}

/** `reset`, plus letting a held snapshot through at once. */
export function flush() {
  reset();
  if (!running) onIdle();
}

/**
 * Turn one engine event into a step, if it is one of the three worth showing.
 *
 * Deliberately a small set. Every event is already in the log; the board is
 * for the three a player watches for — somebody crossed the floor, somebody
 * swung, somebody got hit.
 */
export function enqueue(event) {
  if (stepMs() === 0 || !event) return;
  const kind = event.kind;
  if (kind === "moved" && event.actor && event.data?.from && event.data?.to) {
    queue.push({ do: "walk", actor: event.actor, from: event.data.from, to: event.data.to });
  } else if (kind === "attack_rolled" && event.actor && event.target) {
    queue.push({ do: "lunge", actor: event.actor, at: event.target });
  } else if (kind === "attack_hit" && event.target) {
    queue.push({ do: "recoil", actor: event.target });
  } else {
    return;
  }
  if (!running) run();
}

async function run() {
  running = true;
  try {
    while (queue.length) {
      const step = queue.shift();
      await play(step);
    }
  } finally {
    running = false;
    // Only hand the board back if nothing arrived while the last step ran.
    if (!queue.length) onIdle();
  }
}

function play(step) {
  const ms = stepMs();
  const token = tokenFor(step.actor);
  if (!token || ms === 0) return wait(0);
  switch (step.do) {
    case "walk":
      return walk(token, step, ms);
    case "lunge":
      return lunge(token, step, ms);
    case "recoil":
      return recoil(token, ms);
    default:
      return wait(0);
  }
}

/**
 * One square of a walk.
 *
 * The board still shows where the creature started, so the token is slid by
 * however far it has walked so far rather than being placed. The offset is
 * cumulative: six `moved` events are six slides that add up, and the next
 * render puts the token at its real square and clears the lot.
 */
function walk(token, step, ms) {
  const here = offsets.get(step.actor) || { dx: 0, dy: 0 };
  const { dx, dy } = squareDelta(step.from, step.to);
  const next = { dx: here.dx + dx, dy: here.dy + dy };
  offsets.set(step.actor, next);
  token.style.transition = `transform ${ms}ms linear`;
  token.style.transform = `translate(${next.dx}px, ${next.dy}px)`;
  return wait(ms);
}

/** Lean half a tile toward whatever is being attacked, then settle back. */
function lunge(token, step, ms) {
  const target = tokenFor(step.at);
  if (!target) return wait(0);
  const { dx, dy } = tilesAlong(...direction(token, target), LUNGE_TILES);
  return nudge(token, [{ dx, dy }], ms);
}

/** Rock a quarter tile left, then a quarter right. */
function recoil(token, ms) {
  const step = tilesAlong(-1, 0, RECOIL_TILES);
  return nudge(token, [step, { dx: -step.dx, dy: -step.dy }], ms);
}

/** Which way `to` lies from `from`, in raw screen pixels. */
function direction(from, to) {
  const a = from.getBoundingClientRect();
  const b = to.getBoundingClientRect();
  return [b.left + b.width / 2 - (a.left + a.width / 2), b.top + b.height / 2 - (a.top + a.height / 2)];
}

/**
 * Move the token through some offsets and back to rest.
 *
 * `composite: "add"` so the nudge rides on top of whatever `walk` has already
 * slid the token by. Setting `transform` outright would snap a creature that
 * has walked this turn back to where it started, mid-swing.
 */
function nudge(token, steps, ms) {
  const frames = [{ transform: "translate(0px, 0px)" }];
  for (const s of steps) frames.push({ transform: `translate(${s.dx}px, ${s.dy}px)` });
  frames.push({ transform: "translate(0px, 0px)" });
  token.animate(frames, { duration: ms * frames.length * 0.5, composite: "add", easing: "ease-out" });
  return wait(ms);
}

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
