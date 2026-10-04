"""Which weapons a power's own text is about, as data rather than as English.

**Three consumers were asking this question by substring match and a fourth was
coming.** `chargen.choices._rows_needing` scores which weapon a character should
hold by matching `requires_text` and `trigger`; `scripts/audit._hand_it_the_weapon`
puts a weapon in the board's hand for 257 rows the same way; the advisor page
wants "powers this build can use", which is the question again. #237.

`requires_text` is the wrong floor for it twice over. It is **our** sentence,
written by hand per row, so the vocabulary drifts row by row -- and it is not
where the answer always lives. 39 powers name a weapon in a **rider**, a clause
that merely rewards holding the right thing, and a rider is not a requirement, so
no amount of reading `requires_text` can see one.

So the answer is extracted once, here, from the compendium's own prose, and kept
in a column. Two axes, because they are two different relationships:

* a **gate** -- the printed Requirement. Not holding it means the power is
  refused.
* a **rider** -- a clause that pays out for holding it. Not holding it means a
  weaker version of the same power.

The vocabulary is read out of the `weapon` table rather than written down, for
the reason `audit._weapon_words` gives: a list beside the data goes stale the
next time the importer runs, and silently.

**The care here is all in not over-matching**, and `scripts/weapons.py` -- which
prototyped this and is where the numbers in #237 come from -- was wrong three
times before it was right. `pick` is a weapon group and also an ordinary verb:
"picks up an object", "pick a pocket", "You pick an adjacent enemy". A bare word
match counted 17 pick powers where 3 were real. So a rider is read only out of a
sentence that says you are *wielding* the thing, and a gate only out of the
Requirement line.
"""

from __future__ import annotations

import json
import re
import sqlite3

#: A clause is about holding something only if it says so. See the module note.
WIELDING = re.compile(r"\b(?:wielding|wield|armed with|holding|in your hand)\b", re.I)
SENTENCE = re.compile(r"[^.\n]+[.\n]")
REQUIREMENT = re.compile(r"^Requirement[s]?:\s*(.+?)$", re.M | re.S)
TRIGGER = re.compile(r"^Trigger:\s*(.+?)$", re.M)
SPLIT = re.compile(r",|\bor\b|\band\b")

#: The three proficiency bands, which are `Weapon.category` and not a group. A
#: card reading "you must use this power with a **simple** weapon" names one of
#: these, and reading only groups missed every such clause -- eight cleric riders
#: among them. Found by diffing against `scripts/weapons.py`.
CATEGORIES = ("simple", "military", "superior")
ARTICLE = re.compile(r"^(?:a|an|the|your|with|using|wielding|be|must|you)\b\s*")

#: The shapes a requirement names that are not a weapon group. Each is a
#: question `query.holding` or `Gear` can already answer, which is the test for
#: belonging here -- a shape nothing can ask about would be a column nobody
#: reads.
#:
#: **`implement` is deliberately not one.** `Keyword.IMPLEMENT` already says
#: whether a power is an implement power, so an entry here would be a second
#: answer to a settled question -- and it read four rows wrong: `p5032` says
#: "you drop anything you are **holding**, except **implements** you can use",
#: which is prose about beast form and not a grip that rewards anything.
SHAPES = {
    # **"with both hands" is the same shape spelt as prose**, and leaving it out
    # lost eight cleric riders -- "if you're wielding your weapon with both
    # hands, you gain a +2 bonus to the damage roll". Found by diffing this
    # against `scripts/weapons.py`, which had it.
    "two-handed": ("two-handed", "two handed", "both hands"),
    "two weapons": ("two weapons", "two melee weapons"),
    "free hand": ("hand free", "free hand"),
    "shield": ("shield",),
    "thrown": ("thrown",),
    "reach": ("reach weapon",),
    "melee weapon": ("melee weapon",),
    "ranged weapon": ("ranged weapon",),
}

#: Shapes that are a **gate** only. "You must be wielding a melee weapon" is a
#: requirement; the same words inside a rider are almost always prose about
#: something else, because every weapon power is already melee or ranged and its
#: own `reach` says which.
GATE_ONLY = ("melee weapon", "ranged weapon")


def _vocabulary(
    out: sqlite3.Connection,
) -> tuple[list[str], dict[str, str], dict[str, str]]:
    """The groups, and every weapon name that implies one.

    **From the `slug` column, not from un-slugging the ref.** This used to read
    `ref.removeprefix("w:").replace("-", " ")`, which only worked because a ref
    *was* the printed name slugified -- the fault #339 fixes, so it had to go
    with it.

    The obvious replacement was the localisation, and it is wrong: **no weapon
    has an entry in `names.json`.** A weapon's name is mechanics by this
    project's reckoning -- thirty are in `sanitise.RULES_TERMS` -- so it was
    never sent there, and the ref was carrying it instead. Reading
    `names.get(ref)` therefore returned `None` 117 times out of 117 and emptied
    this index silently: `power.wields` fell **329 rows to 304** with nothing
    raising. Caught by stashing the change and rebuilding for a before figure,
    which is the only reason the number was looked at.
    """
    groups = sorted({r[0] for r in out.execute("SELECT grp FROM weapon") if r[0]})
    by_name = {
        slug.replace("-", " "): grp
        for slug, grp in out.execute(
            "SELECT slug, grp FROM weapon WHERE grp != '' AND slug != ''"
        )
    }
    # And by ref, for the named weapons the scrubber substitutes. See `_groups_in`.
    by_ref = {
        ref: grp
        for ref, grp in out.execute("SELECT ref, grp FROM weapon WHERE grp != ''")
    }
    return groups, by_name, by_ref


def _fragments(text: str) -> list[str]:
    """A compound requirement, split into the things it names."""
    out: list[str] = []
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


#: A weapon's ref where its name used to be. The scrubber substitutes one when
#: the weapon is a *named* weapon rather than a type, which is 51 specs.
_WEAPON_REF = re.compile(r"\bw(\d{3,})\b")


def _groups_in(
    text: str, groups: list[str], by_name: dict[str, str],
    by_ref: dict[str, str] | None = None,
) -> set[str]:
    """Every weapon group this text names.

    A text naming one *weapon* counts under that weapon's group -- "wielding a
    dagger" is a light-blade clause, narrower than the group but on the same
    axis. Longest name first, so `spiked chain` is not read as `chain`, and
    `pike` is never found inside `spiked`.

    **A ref counts as well as a name, and has to.** Giving weapons localisation
    entries let the scrubber do its job on the six that are *named* weapons
    rather than types, so 51 specs now read `w3740` where the name used to be --
    and reading only names lost their group. `weapon rows` fell **329 to 320**
    twice over before this was added, once for each attempt.
    """
    found: set[str] = set()
    if by_ref:
        for m in _WEAPON_REF.finditer(text):
            group = by_ref.get(f"w{m.group(1)}")
            if group:
                found.add(group)
    for fragment in _fragments(text):
        for group in groups:
            if re.search(rf"(?<!\w){re.escape(group)}(?!\w)", fragment):
                found.add(group)
        for name in sorted(by_name, key=len, reverse=True):
            if re.search(rf"(?<!\w){re.escape(name)}(?!\w)", fragment):
                found.add(by_name[name])
                break
    return found


def _categories_in(text: str) -> set[str]:
    """Every proficiency band this text names."""
    low = text.lower()
    return {c for c in CATEGORIES
            if re.search(rf"(?<!\w){c}(?!\w)\s+weapon", low)}


def _shapes_in(text: str) -> set[str]:
    low = text.lower()
    return {shape for shape, words in SHAPES.items() if any(w in low for w in words)}


def of(
    spec: str, groups: list[str], by_name: dict[str, str],
    by_ref: dict[str, str] | None = None,
) -> dict[str, list[str]]:
    """What one power's text says about weapons, split by relationship."""
    spec = spec or ""
    printed = REQUIREMENT.search(spec)
    gate = printed.group(1).strip().split("\n")[0] if printed else ""
    # **A Trigger that says "while you are wielding X" is a gate, not a reward.**
    # The power cannot fire at all without it, which is what a gate means -- and
    # counting it as a rider said the opposite: that holding something else gives
    # a weaker version of the same power, when it gives nothing.
    fires = TRIGGER.search(spec)
    if fires and WIELDING.search(fires.group(1)):
        gate = f"{gate} {fires.group(1)}".strip()
    gate_groups = _groups_in(gate, groups, by_name, by_ref) if gate else set()
    gate_shapes = (_shapes_in(gate) | _categories_in(gate)) if gate else set()

    # The rider axis: the sentences of the card, minus its Requirement, that are
    # about what is in your hands. A `Weapon:` line is one by definition;
    # anything else has to say it is.
    body = spec
    for said in (printed.group(1) if printed else "", fires.group(1) if fires else ""):
        if said:
            body = body.replace(said, "")
    rest = " ".join(
        part for part in SENTENCE.findall(body + "\n")
        if WIELDING.search(part) or part.lstrip().lower().startswith("weapon:")
    )
    # A group named in the gate is not also a rider: the same sentence would be
    # counted twice under two relationships that mean different things.
    rider_groups = _groups_in(rest, groups, by_name, by_ref) - gate_groups
    rider_shapes = (
        (_shapes_in(rest) | _categories_in(rest)) - gate_shapes - set(GATE_ONLY)
    )
    return {
        "gate_groups": sorted(gate_groups),
        "gate_shapes": sorted(gate_shapes),
        "rider_groups": sorted(rider_groups),
        "rider_shapes": sorted(rider_shapes),
    }


def record(out: sqlite3.Connection) -> int:
    """Fill `power.wields` for every row that says anything about a weapon.

    A late pass, after both `power` and `weapon` are built -- the vocabulary is
    the weapon table, so running this earlier would read an empty one and write
    nothing, which is the quiet kind of wrong.

    Returns how many rows got a non-empty answer.
    """
    groups, by_name, by_ref = _vocabulary(out)
    filled = 0
    for ref, spec in out.execute("SELECT ref, spec FROM power").fetchall():
        found = of(spec or "", groups, by_name, by_ref)
        if not any(found.values()):
            continue
        out.execute(
            "UPDATE power SET wields = ? WHERE ref = ?", (json.dumps(found), ref)
        )
        filled += 1
    return filled
