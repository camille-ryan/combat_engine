"""The printed weapon table: what each base weapon's columns say.

**Below every component, for the reason `db.py` and `armour.py` are**, and
this module's shape copies `armour.py`'s because it is the same situation
one table over: a printed table that lived inside `chargen` while a second
reader wanted it from the kernel.

`#852` is the precedent and the argument is identical:

* **The reader already existed and was in the wrong layer.**
  `chargen._printed_weapons` has read this table into `Weapon` objects
  since `#339`, correctly and in detail -- the `melee` split between
  `ranged` and `thrown`, a weapon filed under two groups keeping the first
  -- and `chargen.PRINTED` is the result.
* **`engine -> chargen` is contractually zero**, and its contract carries
  no `ignore_imports` deliberately, because `#852` removed that edge
  rather than allow-listing it. So `c.as_weapon(base=)` could not reach
  the printed columns at all: not by importing chargen, which the gate
  refuses, and not by a second read, which is the duplication `#852`
  existed to end.

So the **columns** come out here and the **`Weapon`** is built one layer
up, in `components.weapon_from_printed`. That split is what lets this
module sit below everything: `Weapon` is an engine component, and a
printed table that imported the engine would not be a table any more.

The numbers are a **table, not behaviour**. Nothing here decides anything,
which is the test for whether something belongs this low.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache


@dataclass(frozen=True)
class Printed:
    """One row of the `weapon` table, the range columns split in two.

    The table prints **one** pair of range columns for both meanings and
    tells them apart with its `melee` flag, so `ranged` and `thrown` are
    the one thing here that is not a straight copy of a column. That is a
    reading of the page, so it belongs beside the page's own numbers.

    `melee` is kept as well. It is what the split is made from and a set
    filter should be able to ask the page's own question.

    All 117 printed weapons: 102 melee, 15 not, and the three categories
    the cards name (`simple`, `military`, `superior`) are the whole table
    rather than a subset of it.

    `chargen`'s reader has carried both halves since `#214`, where
    treating "not a ranged weapon" as "has no range" threw a dagger's
    printed 5/10 and a javelin's 10/20 away. Keep them separate:
    `Gear.ranged` means *can be fired*, and letting a thrown melee weapon
    answer it hands a rogue a ranged basic attack it does not have.
    """

    ref: str
    slug: str
    category: str
    hands: str
    damage: str
    proficiency: int
    reach: int
    group: str
    properties: frozenset[str]
    #: The table's own `melee` flag, kept as a column rather than derived
    #: back out of the two below. `ranged is None` does mean melee today,
    #: but it says so by accident -- a melee weapon that is not thrown
    #: carries `None` in both -- and a set filter asking "is this a melee
    #: weapon" should read the page's own word for it.
    melee: bool
    #: Short and long range when **fired**; `None` for a melee weapon.
    ranged: tuple[int, int] | None
    #: Short and long range when **thrown**; `None` for a weapon that is not.
    thrown: tuple[int, int] | None


@cache
def printed() -> dict[str, Printed]:
    """Every base weapon the book prints, by ref.

    `@cache`d, so the table is read once per process however many readers
    ask -- `armour.py` and `dc.py` both do the same, and there are three
    callers here (chargen's constants, `chargen.PRINTED`, and
    `Cast.as_weapon`).

    **Returns `{}` when there is no database rather than raising**, which
    is `chargen`'s own behaviour and is load-bearing there: its sixteen
    hand-written constants still work without one, and a `chargen` that
    raised at import would take every instrument with it.
    """
    from combat_engine.db import game

    out: dict[str, Printed] = {}
    try:
        rows = list(game().execute("SELECT * FROM weapon"))
    except Exception:            # no database yet; the constants still work
        return out
    for row in rows:
        span = (
            (row["range_short"], row["range_long"])
            if row["range_short"]
            else None
        )
        out[row["ref"]] = Printed(
            ref=row["ref"],
            # The printed word a card can name this weapon by. The ref used
            # to be this string and three sites un-slugged it to ask; see
            # `Weapon.slug`. #339.
            slug=row["slug"] or "",
            category=row["category"],
            hands=row["hands"] or "",
            damage=row["damage"],
            proficiency=row["proficiency"],
            reach=row["reach"],
            group=row["grp"],
            melee=bool(row["melee"]),
            # A weapon filed under two printed groups keeps the first as its
            # `group` and carries the rest as properties, which is where
            # `chargen._fits_base` already looks: a khopesh is an axe that a
            # heavy-blade item may still be laid on. `hands` joins them
            # because ten content sites gate on "two-handed" as a property.
            properties=frozenset(
                [*json.loads(row["properties"] or "[]"), row["hands"]]
            ),
            ranged=span if not row["melee"] else None,
            thrown=span if row["melee"] else None,
        )
    return out


def melee(*categories: str) -> tuple[str, ...]:
    """The refs of every printed melee weapon in those categories, sorted.

    For a card that names a **set** of weapons rather than one -- *"a
    different weapon from any melee category (simple, military, or
    superior)"* -- so the row offers `c.choose` a list it did not invent.

    Sorted, because two characters offered the same choice must see the
    same order; the same reason `_wild_talents` and `_arcane_rows` sort.

    With no categories it is every melee weapon, which is what those three
    words come to: the table carries exactly `simple`, `military` and
    `superior` and nothing else.
    """
    want = {c.lower() for c in categories}
    return tuple(
        ref
        for ref, row in sorted(printed().items())
        if row.melee
        if not want or row.category.lower() in want
    )
