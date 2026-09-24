// card.js — the hover card, for a creature (#333) and for a power (#335).
//
// One widget, two contents. A creature card and a power card want the same
// things — appear instantly, be styled, hold a bar and a list, follow the
// pointer, get out of the way — and building them as two popups would have
// been the same code twice with different padding.
//
// It replaces a `title` attribute, which is the whole point: a native tooltip
// cannot be styled, waits a second before it appears, and cannot draw a hit
// point bar. Nothing here is a rules decision. Every number and every sentence
// on these cards is a field the server sent; this file chooses layout and
// nothing else — which is the same line `app.js` draws, and the reason a burst
// that would catch two enemies from a square you are not standing on is
// computed in `engine/actions.py` and merely printed here.

import { clear, div } from "./dom.js";

// How far the card sits from the pointer, and how close it may get to the
// window edge before it flips to the other side.
const GAP = 14;
const MARGIN = 8;

let host = null;

function panel() {
  if (!host) host = document.getElementById("card");
  return host;
}

/** Put a built card on screen, near the pointer. */
export function showCard(node, ev) {
  const box = panel();
  if (!box) return;
  clear(box);
  box.appendChild(node);
  box.hidden = false;
  moveCard(ev);
}

export function hideCard() {
  const box = panel();
  if (box) {
    box.hidden = true;
    clear(box);
  }
}

/** Follow the pointer, flipping rather than sliding off the window. */
export function moveCard(ev) {
  const box = panel();
  if (!box || box.hidden || !ev) return;
  const r = box.getBoundingClientRect();
  let left = ev.clientX + GAP;
  let top = ev.clientY + GAP;
  if (left + r.width > window.innerWidth - MARGIN) left = ev.clientX - GAP - r.width;
  if (top + r.height > window.innerHeight - MARGIN) top = ev.clientY - GAP - r.height;
  box.style.left = `${Math.max(MARGIN, left)}px`;
  box.style.top = `${Math.max(MARGIN, top)}px`;
}

// ------------------------------------------------------------------ pieces

function row(label, value) {
  const r = div("card-row");
  r.appendChild(div("card-key", label));
  r.appendChild(div("card-val", value));
  return r;
}

function prose(label, text) {
  const p = div("card-prose");
  p.appendChild(div("card-prose-key", label));
  p.appendChild(div("card-prose-text", text));
  return p;
}

function sentence(words) {
  return words.filter(Boolean).join(" ");
}

// ---------------------------------------------------------------- creature

/**
 * The stat block a player needs to choose a target (#333).
 *
 * The lead line is the one a stat block leads with — "Level 5 Soldier
 * (Elite)" — because role says what the creature will do to you next turn and
 * rank says whether one hit ends it, and those are the two facts that decide
 * whether to attack this one or the one beside it.
 */
export function creatureCard(a, names = (t) => t) {
  const card = div("card-body");

  const head = div("card-head");
  head.appendChild(div(`card-name side-${a.side || "npc"}`, a.label || a.id));
  head.appendChild(div("card-id", a.id));
  card.appendChild(head);

  const rank = a.rank && a.rank !== "standard" ? ` (${a.rank})` : "";
  // A creature with no role sends null, one way, for all three spellings the
  // books use — so there is nothing to work around here any more (#340).
  card.appendChild(div("card-lead", `${sentence([`Level ${a.level ?? "?"}`, a.role])}${rank}`));

  const kind = sentence([a.origin, a.mtype]);
  const sub = a.subtypes ? ` (${a.subtypes})` : "";
  if (kind) card.appendChild(div("card-kind", `${kind}${sub}`));

  card.appendChild(hpBlock(a));

  const defs = div("card-defs");
  for (const [name, value] of [
    ["AC", a.ac],
    ["Fort", a.fort],
    ["Ref", a.ref],
    ["Will", a.will],
  ]) {
    const cell = div("card-def");
    cell.appendChild(div("card-def-name", name));
    cell.appendChild(div("card-def-value", value ?? "?"));
    defs.appendChild(cell);
  }
  card.appendChild(defs);

  // Healing surges, for anybody who has any (#338). Monsters have none, so
  // the row is absent on them rather than reading "Surges 0" on every bandit.
  // On a character it is the number that decides whether the *day* is going
  // well, and it is asked mid-fight because second wind spends one.
  if (a.surges_max) card.appendChild(row("Surges", `${a.surges ?? 0} / ${a.surges_max}`));

  // No initiative bonus. It decides the turn order once, at the start, and
  // after that it answers nothing a player can act on — the order itself is
  // on screen as the strip of tokens along the top.
  card.appendChild(row("Speed", `${a.speed ?? "?"}`));
  card.appendChild(row("Size", a.size || "?"));
  if (a.senses) card.appendChild(row("Senses", a.senses));
  // The scorer's own threat figure. Comparative rather than absolute: it
  // answers "which of these two hurts me more", which is the question a target
  // is chosen on, and it is the number the engine itself weighs options by.
  if (typeof a.threat === "number") card.appendChild(row("Threat", a.threat));

  // Only when there is something to say. An empty "Resist —" row on every
  // creature is three lines of noise hiding the one creature that has one.
  if (a.resist) card.appendChild(row("Resist", a.resist));
  if (a.immune) card.appendChild(row("Immune", a.immune));
  if (a.vulnerable) card.appendChild(row("Vulnerable", a.vulnerable));

  card.appendChild(effectsBlock(a, names));
  card.appendChild(traitsBlock(a));
  return card;
}

/**
 * What is currently on the creature, and when each of it ends.
 *
 * `effects` is the list with durations; `conditions` is the closed-over set of
 * short words, which includes the ones nothing applied — `dying` is derived
 * from hit points and implies unconscious, helpless and prone. So the words
 * that no effect accounts for are shown as bare chips underneath, and nothing
 * is listed twice.
 *
 * Ongoing damage gets its own class, because "is that still burning?" is the
 * question this block exists to answer.
 */
function effectsBlock(a, names) {
  const box = div("card-effects");
  const effects = a.effects || [];
  const spoken = new Set();
  for (const e of effects) {
    for (const word of (e.text || "").split(/[,+]/)) spoken.add(word.trim());
    const row = div("effect");
    if (e.ongoing) row.classList.add("ongoing");
    if (e.save_ends) row.classList.add("save-ends");
    row.appendChild(div("effect-text", names(e.text || e.name)));
    row.appendChild(div("effect-duration", names(e.duration || "")));
    box.appendChild(row);
  }
  const loose = (a.conditions || []).filter((c) => !spoken.has(c));
  if (loose.length) {
    const chips = div("conds");
    for (const c of loose) chips.appendChild(div("cond", c));
    box.appendChild(chips);
  }
  return box;
}

function hpBlock(a) {
  const box = div("card-hp");
  const max = a.hp_max || 0;
  const hp = Math.max(0, Math.min(a.hp ?? 0, max));
  const line = max > 0 ? `${a.hp ?? "?"} / ${max}` : `${a.hp ?? "?"}`;
  const temp = a.temp_hp ? ` +${a.temp_hp}` : "";
  const bloodied =
    typeof a.bloodied_value === "number" ? `  (bloodied ${a.bloodied_value})` : "";
  box.appendChild(div("card-hp-line", `HP ${line}${temp}${bloodied}`));

  const bar = div("hpbar");
  const fill = div("hpbar-fill");
  if (a.bloodied) fill.classList.add("bloodied");
  if (a.dead || (a.hp ?? 1) <= 0) fill.classList.add("gone");
  fill.style.width = `${max > 0 ? (hp / max) * 100 : 0}%`;
  bar.appendChild(fill);
  box.appendChild(bar);
  return box;
}

// ------------------------------------------------------------------- power

/**
 * A patch of ground: what it is called, and whose it is.
 *
 * The owner is the point. An aura is labelled from the power that declared it,
 * and the creature's stat block usually calls the same trait something else
 * entirely, so the shading alone is a dead end. Naming the creature turns it
 * into a question the card can answer.
 */
export function zoneCard(zone, ownerLabel) {
  const card = div("card-body");
  const head = div("card-head");
  head.appendChild(div("card-name", zone.label || zone.id || "zone"));
  head.appendChild(div("card-id", zone.id));
  card.appendChild(head);
  if (ownerLabel) card.appendChild(div("card-lead", ownerLabel));
  card.appendChild(div("card-kind", `${(zone.squares || []).length} squares`));
  return card;
}

/**
 * Traits and auras — what the creature does without choosing to.
 *
 * An aura shades squares on the board, and until now nothing anywhere said
 * what standing in them did to you. The radius is on the entry's range line
 * ("aura 2"), and the rider is its effect text, which is withheld rather than
 * neutralised when the server is running with names off.
 */
function traitsBlock(a) {
  const box = div("card-traits");
  for (const t of a.traits || []) {
    const row = div(`trait${t.usage === "aura" ? " aura" : ""}`);
    const head = div("trait-head");
    head.appendChild(div("trait-name", t.name));
    // Only an aura has a range worth printing; a plain trait's is "—".
    if (t.usage === "aura") head.appendChild(div("trait-range", t.range_text || ""));
    row.appendChild(head);
    const body = t.effect_text || t.hit_text || t.requirement_text;
    if (body) row.appendChild(div("trait-text", body));
    box.appendChild(row);
  }
  return box;
}

/**
 * A power's stat-block entry, read the way it is read on paper (#335).
 *
 * The prose fields are absent rather than empty when the server is running
 * with names off — see `dto._prose` for why that rule differs from every
 * other one — so the card degrades to the mechanical skeleton on its own,
 * without this file knowing anything about the switch.
 */
export function powerCard(p) {
  const card = div("card-body");

  const head = div("card-head");
  head.appendChild(div("card-name", p.name));
  if (!p.available) head.appendChild(div("card-id", "unavailable"));
  card.appendChild(head);

  card.appendChild(div("card-lead", sentence([p.action, "action", "·", p.usage])));

  const kw = (p.keywords || []).join(", ");
  card.appendChild(div("card-kind", sentence([p.range_text, kw && `· ${kw}`])));

  if (p.targets) card.appendChild(row("Target", p.targets));
  if (p.attack_text) card.appendChild(row("Attack", p.attack_text));
  else if (p.damage) card.appendChild(row("Damage", p.damage));

  if (p.requirement_text) card.appendChild(prose("Requirement", p.requirement_text));
  if (p.hit_text) card.appendChild(prose("Hit", p.hit_text));
  if (p.miss_text) card.appendChild(prose("Miss", p.miss_text));
  if (p.effect_text) card.appendChild(prose("Effect", p.effect_text));

  if (p.available && p.option_label) {
    card.appendChild(div("card-note", `→ ${p.option_label}`));
  }
  if (!p.available && p.reason) {
    card.appendChild(div("card-bad", p.reason));
  }
  return card;
}
