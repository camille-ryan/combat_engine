"""The printed armour table: what each kind costs and what it gives.

**Below every component, for the reason `db.py` is.** Nothing here imports
anything in `combat_engine` except `db`, so the engine, content, chargen and
the instruments can all read these four numbers without any of them reaching
through another.

These lived in `chargen/__init__.py`, and that was the wrong place in the same
way the database read path was wrong inside `etl/build.py` (#334) -- which is
why this module's shape copies that one's:

* **Six readers across four layers, and chargen is only one of them.**
  `engine/skills.py`, four content files (`feats/general_o.py`,
  `feats/general_s.py`, `features/racial.py`, `items/armour.py`),
  `scripts/drivers.py`, and chargen itself.
* **Four of those six imports were function-local** -- buried in the function
  that needed them rather than at the top of the file. As `db.py` says of the
  same symptom, that is not a style choice, it is people avoiding the import,
  and what they were avoiding here is the whole of `chargen` (3,100+ lines,
  every build and every draw) pulled in to look up a check penalty.
* **And it made a documented seam claim false.** `engine/skills.py:263` was
  the one `engine -> chargen` import in the tree, which `CLAUDE.md`'s seam
  table never mentioned, and through it `etl.build -> engine.skills ->
  chargen -> content` made *"etl → content is zero"* false as a statement
  about the graph. `import-linter` found it; grep could not, because it is not
  a direct edge. #852.

The numbers are a **table, not behaviour** -- read off the compendium's armour
page by the ETL, and read back here once at import. Nothing in this module
decides anything, which is the test for whether something belongs this low.
"""

from __future__ import annotations


#: Armour, by the bonus it gives. Light armour also takes a modifier.
#: The basic armours, **read off the `armour` table** rather than remembered.
#: #452 built that table and nothing outside `etl/` ever queried it, so these
#: six numbers and the two penalties below were carried as constants in
#: `chargen`.
#:
#: Keyed on `armour.type`, and restricted to **ids 1-8**, which is the care
#: this needs: the table holds 15 `kind='base'` rows because later books
#: print variant materials under the same type names, so `chainmail` appears
#: at +3 and at +6 and `leather` at +2 and +3. Reading by type alone would
#: pick whichever row came back first and move a character's AC by three.
#: Ids 1-8 are the PHB set -- cloth, leather, hide, chainmail, scale, plate,
#: light shield, heavy shield -- and the constants that used to live in
#: `chargen` agreed with them exactly, which is what made the move a
#: relocation rather than a correction.
def _basics() -> tuple[dict[str, int], ...]:
    from combat_engine.db import game

    ac: dict[str, int] = {}
    check: dict[str, int] = {}
    speed: dict[str, int] = {}
    shield: dict[str, int] = {}
    for row in game().execute(
        "SELECT type, ac_bonus, check_penalty, speed_penalty FROM armour"
        " WHERE kind = 'base' AND id BETWEEN 1 AND 8"
    ):
        kind = row["type"]
        if kind.endswith("shields"):
            # `light shields` / `heavy shields` on the page; one shield in
            # hand, so the key is singular and `Gear.shield`'s 1 and 2 index
            # straight into it.
            shield[kind.split()[0]] = row["check_penalty"] or 0
            continue
        # `chain` is what every reader in the tree calls it, and the page
        # prints `chainmail`. The content rows asking `gear.armour in
        # ("scale", "plate")` would all go quiet on a rename.
        kind = "chain" if kind == "chainmail" else kind
        ac[kind] = row["ac_bonus"] or 0
        check[kind] = row["check_penalty"] or 0
        speed[kind] = row["speed_penalty"] or 0
    return ac, check, speed, shield


ARMOUR, ARMOUR_CHECK, ARMOUR_SPEED, SHIELD_CHECK = _basics()
