// coords.js — the ONLY place engine (x, y) squares become screen positions.
//
// The engine board is flat: there is no vertical axis at all. #194 settled
// flight as three privileges on a flat board, so nothing in the engine carries
// a z. An isometric view is therefore a *projection* of this same flat board —
// a renderer concern and nothing else. Replacing squareToScreen /
// screenToSquare (and the rect helpers built on them) with an iso transform is
// the entire change; no other file needs to know it happened.
//
// Consequence: no other module may do arithmetic on engine coordinates. If you
// need a new kind of geometry, add a function here.

/** Edge length of one board square, in CSS pixels. */
export const TILE = 46;

/**
 * Top-left screen position of engine square (x, y).
 * @returns {{px: number, py: number}}
 */
export function squareToScreen(x, y) {
  return { px: x * TILE, py: y * TILE };
}

/**
 * Inverse of squareToScreen: the engine square containing a screen position.
 * Coordinates are relative to the board's own origin.
 * @returns {{x: number, y: number}}
 */
export function screenToSquare(px, py) {
  return { x: Math.floor(px / TILE), y: Math.floor(py / TILE) };
}

/** Pixel size of a whole board that is `width` x `height` squares. */
export function boardPixelSize(width, height) {
  const { px, py } = squareToScreen(width, height);
  return { width: px, height: py };
}

/** CSS box for a single square. */
export function squareRect(x, y) {
  const { px, py } = squareToScreen(x, y);
  return { left: px, top: py, width: TILE, height: TILE };
}

/**
 * How far, in pixels, one engine square is from another.
 *
 * What a token has to travel to walk one step of its path. Here rather than in
 * the animator for the usual reason: it is a conversion from engine squares to
 * screen pixels, and an isometric renderer would answer it differently.
 */
export function squareDelta(from, to) {
  const a = squareToScreen(from[0], from[1]);
  const b = squareToScreen(to[0], to[1]);
  return { dx: b.px - a.px, dy: b.py - a.py };
}

/**
 * A vector `tiles` tiles long, pointing wherever (dx, dy) points.
 *
 * For the nudges: a creature leans half a tile toward what it is hitting, and
 * a creature that is hit rocks a quarter of a tile. The caller knows the
 * direction in raw screen pixels; only this module knows how big a tile is.
 *
 * A zero-length direction stays zero — two creatures on the same square have
 * no "toward", and normalising that would divide by nothing.
 */
export function tilesAlong(dx, dy, tiles) {
  const length = Math.hypot(dx, dy);
  if (!length) return { dx: 0, dy: 0 };
  const reach = TILE * tiles;
  return { dx: (dx / length) * reach, dy: (dy / length) * reach };
}

/**
 * CSS box covering every square in `squares` — a Large creature occupies 2x2,
 * so its token is the union of its four squares, not one of them.
 * @param {Array<[number, number]>} squares
 */
export function squaresRect(squares) {
  const boxes = (squares || []).map(([x, y]) => squareRect(x, y));
  if (boxes.length === 0) return { left: 0, top: 0, width: 0, height: 0 };
  const left = Math.min(...boxes.map((b) => b.left));
  const top = Math.min(...boxes.map((b) => b.top));
  const right = Math.max(...boxes.map((b) => b.left + b.width));
  const bottom = Math.max(...boxes.map((b) => b.top + b.height));
  return { left, top, width: right - left, height: bottom - top };
}

/** The engine square a pointer event landed on, given the board element. */
export function pointerSquare(boardEl, ev) {
  const r = boardEl.getBoundingClientRect();
  return screenToSquare(ev.clientX - r.left, ev.clientY - r.top);
}

/** Apply a rect from this module to an absolutely positioned element. */
export function place(el, rect) {
  el.style.left = `${rect.left}px`;
  el.style.top = `${rect.top}px`;
  el.style.width = `${rect.width}px`;
  el.style.height = `${rect.height}px`;
  return el;
}
