#!/usr/bin/env python
"""What a power needs in its hands, by class and by secondary ability.

    uv run scripts/weapons.py                 both breakdowns
    uv run scripts/weapons.py --what groups   the named weapon groups only
    uv run scripts/weapons.py --what shapes   how the weapon is held
    uv run scripts/weapons.py --class rogue   one class, in full
    uv run scripts/weapons.py --lines         the requirement lines themselves

**Two separate readings**, because a requirement says two different kinds of
thing and mixing them makes both unreadable:

* **groups** -- the named, enumerable weapon groups the book prints: flail,
  heavy blade, light blade, crossbow, sling. Seventeen of them, read off the
  `weapon` table rather than listed here, so the vocabulary cannot drift from
  what a character can actually hold.
* **shapes** -- how it is held or what kind it is: two-handed, two weapons, a
  free hand, a shield, thrown, reach. These are not groups and do not belong in
  the same column: "a light blade" narrows *which* weapon, "two melee weapons"
  narrows *how many*.

**A compound is split and counted in every category it names.** "You must be
wielding a crossbow, a light blade, or a sling" is one power under each of
three groups, which is the only reading that answers "how many powers can this
weapon be used for".

**Two relationships, not one.** A weapon is named either as a **gate** -- the
printed Requirement, which refuses the power without it -- or as a **rider**,
a clause that pays out only when you happen to be holding one:

    Weapon: If you're wielding an axe, a hammer, or a mace, you gain a bonus
            to the damage roll equal to your Constitution modifier.

That is not a requirement and the power works without it, so counting it in
the same column would say a weapon is needed where it is merely rewarded.
Riders are **59 powers the Requirement axis cannot see at all**, and the two
sets do not overlap on a single power.

The **secondary ability** is read off the power's own printed text: the
`Attack:` line names the primary, and any other ability the card mentions is
one the power leans on. A power that names none is counted under `--`, and that
is a real answer rather than a gap -- it means the power suits any build of its
class.

Everything here is read from `spec`, which is the mechanical text with the
names stripped, so nothing printed reaches this file.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict

from combat_engine.db import game

ABIL = {
    "Strength": "str", "Constitution": "con", "Dexterity": "dex",
    "Intelligence": "int", "Wisdom": "wis", "Charisma": "cha",
}

#: Shapes that a power *prints a Requirement* for. Kept apart from the three
#: below, which every weapon power has by virtue of its range line -- counting
#: 895 melee powers beside 32 shield ones would drown the thing being asked.
REQUIREMENT_SHAPES = {
    "two weapons", "two-handed", "free hand", "shield", "heavy thrown",
    "light thrown", "thrown", "reach weapon", "off-hand", "versatile",
    "high crit", "defensive", "small", "simple", "military", "superior",
    "unarmed",
}

#: Phrases per shape. Ordered longest-first within a label so "heavy thrown"
#: is not also counted as plain "thrown".
SHAPES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("two weapons", ("two melee weapons", "two weapons", "wielding two")),
    ("two-handed", ("two-handed", "two handed", "in two hands", "both hands")),
    ("free hand", ("hand free", "free hand")),
    ("shield", ("shield",)),
    ("heavy thrown", ("heavy thrown",)),
    ("light thrown", ("light thrown",)),
    ("thrown", ("thrown",)),
    ("reach weapon", ("reach weapon", "a reach")),
    ("off-hand", ("off-hand", "off hand")),
    ("versatile", ("versatile",)),
    ("high crit", ("high crit",)),
    ("defensive", ("defensive",)),
    ("small", ("small weapon",)),
    ("simple", ("simple weapon",)),
    ("military", ("military weapon",)),
    ("superior", ("superior weapon",)),
    ("unarmed", ("unarmed",)),
)

REQ = re.compile(r"^Requirements?:\s*(.+)$", re.M)
#: A clause that pays out for holding the right thing. `Weapon:` is the label
#: the book prints for most of them; the rest sit inside an `Effect:` or an
#: `Attack:` line, so the label alone finds 24 of the 60.
#:
#: **The clause has to be about holding something, and scanning the whole card
#: is not good enough.** `pick` is a weapon group and also an ordinary verb --
#: "picks up an object", "pick a pocket", "You pick an adjacent enemy" -- and a
#: bare word match counted 17 powers where 3 were real. So a rider is read only
#: out of a sentence that says you are wielding, holding or armed with the
#: thing.
WIELDING = re.compile(r"\b(?:wielding|wield|armed with|holding|in your hand)\b", re.I)
SENTENCE = re.compile(r"[^.\n]+[.\n]")
ATTACK = re.compile(r"^Attack:\s*([^\n]+)$", re.M)
SPLIT = re.compile(r",|\bor\b|\band\b")
ARTICLE = re.compile(r"^(?:a|an|the|your|with|using|wielding|be|must|you)\b\s*")


def _vocabulary() -> tuple[list[str], dict[str, str]]:
    """The groups, and every weapon name that implies one.

    Read out of the `weapon` table rather than written down, for the reason
    `audit.py`'s `_weapon_words` is: a list beside the data goes stale the next
    time the importer runs, and this one would go stale silently.
    """
    db = game()
    groups = sorted({r[0] for r in db.execute("SELECT grp FROM weapon") if r[0]})
    # `slug`, not the ref. The ref is the compendium id now and un-slugging it
    # would match nothing -- silently, which is the half that matters. #339.
    by_name = {
        slug.replace("-", " "): grp
        for slug, grp in db.execute(
            "SELECT slug, grp FROM weapon WHERE grp != '' AND slug != ''"
        )
    }
    return groups, by_name


def _fragments(text: str) -> list[str]:
    """A compound requirement, split into the things it names."""
    out = []
    for part in SPLIT.split(text.lower()):
        part = part.strip(" .")
        while True:
            shorter = ARTICLE.sub("", part).strip()
            if shorter == part:
                break
            part = shorter
        if part:
            out.append(part)
    return out


def _groups_in(text: str, groups: list[str], by_name: dict[str, str]) -> set[str]:
    """Every group a requirement names.

    A requirement that names one *weapon* counts under that weapon's group --
    "you must be wielding a dagger" is a light-blade requirement, narrower than
    the group but on the same axis.
    """
    found: set[str] = set()
    for part in _fragments(text):
        for grp in groups:
            if re.search(rf"\b{re.escape(grp)}s?\b", part):
                found.add(grp)
        for name, grp in by_name.items():
            if re.search(rf"\b{re.escape(name)}s?\b", part):
                found.add(grp)
    return found


def _shapes_in(text: str) -> set[str]:
    low = text.lower()
    found = {label for label, words in SHAPES if any(w in low for w in words)}
    # A heavy or light thrown requirement is not also a plain thrown one.
    if found & {"heavy thrown", "light thrown"}:
        found.discard("thrown")
    return found


def read() -> tuple[list[dict], Counter]:
    """Every classed power, with what it needs in hand."""
    groups, by_name = _vocabulary()
    rows: list[dict] = []
    unreadable: Counter[str] = Counter()
    for ref, cls, level, reach, keywords, spec in game().execute(
        "SELECT ref, class, level, reach, keywords, spec FROM power WHERE class != ''"
    ):
        spec = spec or ""
        line = ATTACK.search(spec)
        primary = next(
            (a for a in ABIL if line and re.search(rf"\b{a}\b", line.group(1))), ""
        )
        seconds = sorted(
            {a for a in ABIL if re.search(rf"\b{a}\b", spec)}
            - ({primary} if primary else set())
        )
        printed = REQ.search(spec)
        text = printed.group(1).strip() if printed else ""
        grps = _groups_in(text, groups, by_name) if text else set()
        shps = _shapes_in(text) if text else set()
        if text and not grps and not shps:
            unreadable[text] += 1
        # The rider axis: the clauses of the card, minus its Requirement, that
        # are about what is in your hands. A `Weapon:` line is one by
        # definition; anything else has to say so.
        body = spec.replace(text, "") if text else spec
        rest = " ".join(
            part for part in SENTENCE.findall(body + "\n")
            if WIELDING.search(part) or part.lstrip().lower().startswith("weapon:")
        )
        rider_g = _groups_in(rest, groups, by_name)
        rider_s = _shapes_in(rest) & REQUIREMENT_SHAPES
        # A group named in the gate is not also a rider -- the same sentence
        # would otherwise be counted twice under two different relationships.
        rider_g -= grps
        rider_s -= shps
        # The range line says melee or ranged weapon for every weapon power,
        # not only those printing a Requirement, so the shape axis reads it.
        low = (reach or "").lower()
        if "melee weapon" in low:
            shps.add("melee weapon")
        if "ranged weapon" in low:
            shps.add("ranged weapon")
        if "implement" in json.loads(keywords or "[]"):
            shps.add("implement")
        rows.append(
            {
                "ref": ref, "cls": cls.lower(), "level": level, "req": text,
                "primary": ABIL.get(primary, ""),
                "seconds": [ABIL[s] for s in seconds],
                "groups": sorted(grps), "shapes": sorted(shps),
                "rider_groups": sorted(rider_g), "rider_shapes": sorted(rider_s),
                "rewards": bool(rest.strip()),
            }
        )
    return rows, unreadable


def _cross(rows: list[dict], axis: str, keep: set[str] | None) -> dict:
    out: dict[tuple[str, str], Counter] = defaultdict(Counter)
    for row in rows:
        values = [v for v in row[axis] if keep is None or v in keep]
        if not values:
            continue
        for sec in row["seconds"] or ["--"]:
            for value in values:
                out[(row["cls"], sec)][value] += 1
    return out


def _totals(rows: list[dict], axis: str, keep: set[str] | None) -> Counter:
    out: Counter[str] = Counter()
    for row in rows:
        for value in row[axis]:
            if keep is None or value in keep:
                out[value] += 1
    return out


def _show(title: str, totals: Counter, table: dict, only: str) -> None:
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")
    print("  -- every power that names one --")
    for value, n in totals.most_common():
        print(f"     {value:16} {n:5}")
    print(f"     {'named in all':16} {sum(totals.values()):5}")
    print("\n  -- by class and secondary ability --")
    for key in sorted(table, key=lambda k: (-sum(table[k].values()), k)):
        cls, sec = key
        if only and cls != only:
            continue
        counted = table[key]
        listed = ", ".join(f"{k} {n}" for k, n in counted.most_common())
        print(f"     {cls:12} sec {sec:4} {sum(counted.values()):4}   {listed}")


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--what", choices=("groups", "shapes", "both"), default="both")
    ap.add_argument("--how", choices=("gate", "rider", "both"), default="both",
                    help="required for the power, or merely rewarded by it")
    ap.add_argument("--class", dest="cls", default="", help="one class only")
    ap.add_argument("--lines", action="store_true",
                    help="the distinct requirement lines and their counts")
    args = ap.parse_args()

    rows, unreadable = read()
    printed = [r for r in rows if r["req"]]
    print(f"classed powers {len(rows)}   printing a Requirement {len(printed)}")
    # Counted on the **requirement** only. `shapes` also carries melee/ranged/
    # implement, which comes off the range line and every weapon power has one,
    # so counting those here would say almost every power names a shape.
    named = sum(1 for r in printed if set(r["shapes"]) & REQUIREMENT_SHAPES)
    print(f"  naming a weapon group {sum(1 for r in printed if r['groups'])}"
          f"   naming a shape {named}"
          f"   about neither {sum(unreadable.values())}")
    riders = [r for r in rows if r["rider_groups"] or r["rider_shapes"]]
    print(f"powers rewarding a weapon in a rider rather than requiring it: "
          f"{len(riders)}"
          f"   (group {sum(1 for r in riders if r['rider_groups'])}"
          f", shape {sum(1 for r in riders if r['rider_shapes'])})")

    if args.lines:
        lines = Counter(r["req"] for r in printed)
        print(f"\n  {len(lines)} distinct requirement lines:")
        for text, n in lines.most_common():
            print(f"     {n:4}  {text[:96]}")
        return 0

    want_gate = args.how in ("gate", "both")
    want_rider = args.how in ("rider", "both")
    if args.what in ("groups", "both"):
        if want_gate:
            _show("WEAPON GROUPS, REQUIRED -- the power is refused without one",
                  _totals(rows, "groups", None), _cross(rows, "groups", None),
                  args.cls)
        if want_rider:
            _show("WEAPON GROUPS, REWARDED -- a rider pays out for holding one",
                  _totals(rows, "rider_groups", None),
                  _cross(rows, "rider_groups", None), args.cls)
    if args.what in ("shapes", "both"):
        if want_gate:
            _show("WEAPON SHAPES, REQUIRED -- how it must be held",
                  _totals(rows, "shapes", REQUIREMENT_SHAPES),
                  _cross(rows, "shapes", REQUIREMENT_SHAPES), args.cls)
        if want_rider:
            _show("WEAPON SHAPES, REWARDED -- how it pays to be held",
                  _totals(rows, "rider_shapes", None),
                  _cross(rows, "rider_shapes", None), args.cls)
        wide = {"melee weapon", "ranged weapon", "implement"}
        _show("DELIVERY -- from the power's own range line, neither of the above",
              _totals(rows, "shapes", wide), _cross(rows, "shapes", wide), args.cls)

    if unreadable:
        print(f"\n  {sum(unreadable.values())} requirements are about something else "
              f"entirely, e.g.:")
        for text, n in unreadable.most_common(5):
            print(f"     {n:4}  {text[:70]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
