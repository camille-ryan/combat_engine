// dom.js — the two element helpers every panel builds out of.
//
// Here rather than in app.js because the hover card (card.js) builds elements
// too, and two copies of `div` is the sort of duplication that drifts one
// `textContent` into an `innerHTML`. There is deliberately nothing else in
// this module: it is a shorthand, not a framework.

/** A div with an optional class and optional text. Text, never markup. */
export function div(cls, text) {
  const d = document.createElement("div");
  if (cls) d.className = cls;
  if (text !== undefined && text !== null) d.textContent = String(text);
  return d;
}

/** Empty a node. */
export function clear(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
}
