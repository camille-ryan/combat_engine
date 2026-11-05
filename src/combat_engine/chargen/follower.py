"""A companion character: DMG2's formulas, built from a role rather than a class.

`#1015`. A party member that fills an empty role or pads a short party, and
the book is explicit that its own system is the right one for the job:

> *"These new rules are better at crafting an adventuring ally for the PCs,
> whereas the NPC rules are better at helping you build enemies for your
> characters. These new rules are more abstract: **They focus entirely on the
> companion character's role in the party, rather than building the character
> through the filter of its class.**"*

So it is a **table, not behaviour** -- the same shape as `armour.py` and
`dc.py`: printed numbers read once, with the formulas that index them, and no
decisions of its own. That is why it is a module beside `choices.py` rather
than more surface on `Character`.

**Called `follower` and not `companion`, deliberately.** The word is already
three unrelated things in this tree -- `content.loader.companion` reads an
11-row beast table, `Cast.companion` summons one, `loader.spawn_companion`
puts it on a board -- so a fourth meaning would make every grep for any of
them ambiguous. DMG2 uses *"follower"* for this very thing a page earlier
(*"If no monster matches your vision for a follower"*), so the word is the
book's as well as unused.

## What it is cheaper than, which reverses an assumption

> *"As a general rule, companion characters don't use magic items. [...] do
> not add the magic item's enhancement bonus [...] The companion character's
> attack and defense values are already set at appropriate values for the
> character's level."*

No inventory, no items, no feats, no gear arithmetic, no enhancement. A
companion is the **cheapest** body to add to a party, not the most expensive.

## What is here and what is not

Here: the statistics table, the attack and damage formulas, the four role
features by name, the role-to-class mapping, and the level-up table.

Not here: spawning one onto a board, and the power selection. The printed
rule for powers is *"choose a character class that has the same role ... note
that class's appropriate melee and ranged basic attacks. Then select one
other at-will attack power, one encounter attack power, and one utility power
from that class"* -- which is `dealt_hand`'s job with three narrowings, and is
its own piece of work. `classes_for` is the half of it this module owns.

Nor the party constraint on skills: *"Make at least one of these skills one in
which a PC has training"* is a rule about the **other sheets**, so it belongs
wherever a party is assembled, not here. It is the only part of the whole
system that has to look outside the companion.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

#: The four party roles, as `class.role` spells them once folded.
ROLES = ("controller", "defender", "leader", "striker")

#: Every defence other than AC, before the level term. One number for all
#: four roles, which is the row of the printed table most easily lost: AC is
#: the only defence a role changes.
OTHER_DEFENCES = 13

#: The attack bonus before the level term. *"A companion character's attack
#: bonus equals 4 + level. For attacks with weapons, add the weapon's
#: proficiency bonus. Do not apply modifiers for ability scores or magic
#: items."*
#:
#: The proficiency bonus is **not** added here: this module does not know
#: what the companion is holding, and the printed sentence makes it a property
#: of the weapon rather than of the character.
ATTACK = 4


@dataclass(frozen=True)
class Shape:
    """One column of DMG2 p30's `COMPANION CHARACTER STATISTICS`.

    Verbatim, so the four rows can be checked against the page:

        Statistic        Controller  Defender  Leader  Striker
        Hit points       (lvl x 4)+6 (lvl x 6)+9 (lvl x 5)+7 (lvl x 5)+7
                         + Con score, every column
        Healing surges   6 + Con mod 9 + Con mod 7 + Con mod 6 + Con mod
        Armor Class      13 + level  17 + level 15 + level 15 + level
        Other defenses   13 + level  13 + level 13 + level 13 + level

    **Two things in that table are easy to read past and both are modelled
    here rather than simplified.**

    *Hit points take the Con **score**; healing surges take the Con
    **modifier**.* Four of the eight cells say "Con score" and four say "Con
    modifier", and at a Con of 14 that is the difference between +14 and +2.

    *Leader and striker share the hit-point formula and do **not** share the
    surges* -- `(level x 5) + 7` both, then 7 surges against 6. A reader
    collapsing the two columns because their first row matches gets the
    striker a surge too many.
    """

    #: Hit points per level.
    hp_per: int
    #: Hit points before the level term, before the Con **score** is added.
    hp_flat: int
    #: Healing surges before the Con **modifier** is added.
    surges: int
    #: AC before the level term. The only defence a role changes.
    ac: int
    #: Hit points gained per level. *"Controller companion characters gain 4
    #: hit points, leaders or strikers gain 5 hit points, and defenders gain
    #: 6 hit points."*
    #:
    #: **It equals `hp_per` for all four roles, and is held anyway.** This
    #: field first carried a note saying three of the four agreed and the
    #: leader did not; measured, all four agree -- 4/4, 6/6, 5/5, 5/5 -- so
    #: the claim was simply wrong and the field needs a better reason than a
    #: difference that is not there.
    #:
    #: The reason is that the page states them as **two separate rules** on
    #: two different pages, and deriving one printed number from another
    #: printed number is what this project's own rule forbids. If a later
    #: printing changes one of them, a derived field would silently follow
    #: and a held one goes red. `drivers.follower` asserts the two agree
    #: today, which is the honest version of the coincidence: recorded, and
    #: checked, rather than assumed and collapsed.
    grows: int
    #: The role feature, in the book's own words.
    feature: str


#: DMG2 p30 and p31, step 8. Read once.
SHAPES: dict[str, Shape] = {
    "controller": Shape(
        hp_per=4, hp_flat=6, surges=6, ac=13, grows=4,
        feature="once per encounter as a free action, extend an effect on an"
                " enemy to end at the end of its next turn rather than its"
                " current one",
    ),
    "defender": Shape(
        hp_per=6, hp_flat=9, surges=9, ac=17, grows=6,
        feature="when it hits an enemy with a melee basic attack, it marks"
                " that target until the end of its next turn",
    ),
    "leader": Shape(
        hp_per=5, hp_flat=7, surges=7, ac=15, grows=5,
        feature="twice per encounter as a minor action, let an ally within 5"
                " squares spend a healing surge; three times from 16th level",
    ),
    "striker": Shape(
        hp_per=5, hp_flat=7, surges=6, ac=15, grows=5,
        feature="once per round, 1d6 extra damage on a hit against an enemy"
                " it has combat advantage over; 2d6 at 11th, 3d6 at 21st",
    ),
}


@dataclass(frozen=True)
class Follower:
    """A companion character's finished numbers.

    Frozen, and `advanced()` returns a new one, because the printed level-up
    is an increment on what is there rather than a re-derivation -- see that
    method.
    """

    role: str
    level: int
    #: The Constitution **score**, not its modifier. Both are used and by
    #: different rows; see `Shape`.
    con: int
    hp: int
    surges: int
    ac: int
    fortitude: int
    reflex: int
    will: int
    attack: int
    #: The half-level term only. *"A companion character adds the appropriate
    #: ability modifier to damage rolls as normal. In addition, the character
    #: adds one-half his or her level to all damage rolls."*
    #:
    #: The ability half is **not** here, because which ability it is belongs
    #: to the power being used and this module does not know what the
    #: companion is about to do. Carrying a single number would mean picking
    #: an ability on its behalf.
    damage: int
    feature: str

    def advanced(self) -> Follower:
        """One level, by the printed table rather than by re-deriving.

        > *"Hit Points: Controller companion characters gain 4 hit points,
        > leaders or strikers gain 5 hit points, and defenders gain 6 hit
        > points. Attack Bonus: increases by 1. Defenses: Each of the
        > character's defenses increases by 1. Damage: When a companion
        > character achieves an even-numbered level, increase his or her
        > damage rolls by 1."*

        **This is why a companion can level long before `#1013` can.**
        Advancing a PC means re-dealing a pinned hand, and `dealt_hand` is
        not monotonic in level -- a cleric at one seed drops three held rows
        between 6 and 7. A companion's advancement is four increments and
        touches no hand at all.

        Checked against a fresh build rather than assumed equal to one: the
        increments and the formulas are two different statements of the same
        table and `drivers.follower` asserts they agree, which is the one
        thing that could silently drift. Measured over four roles and eleven
        levels: **0 disagreements**, so the two printed statements are
        consistent today and the check is what keeps that true.

        The optional encounter-power swap is not here -- it is a choice, and
        this module holds no powers. See the module docstring.
        """
        shape = SHAPES[self.role]
        return replace(
            self,
            level=self.level + 1,
            hp=self.hp + shape.grows,
            attack=self.attack + 1,
            ac=self.ac + 1,
            fortitude=self.fortitude + 1,
            reflex=self.reflex + 1,
            will=self.will + 1,
            # **Even levels only**, and the level being *reached* is what the
            # printed sentence is about -- "when a companion character
            # achieves an even-numbered level".
            damage=self.damage + (1 if (self.level + 1) % 2 == 0 else 0),
        )


def modifier(score: int) -> int:
    """An ability modifier from a score, the printed way."""
    return (score - 10) // 2


def follower(role: str, level: int = 1, con: int = 14) -> Follower:
    """Build one from its role and level. `#1015`.

    `con` is the **score**. It is the only ability this needs: ability
    modifiers *"don't influence a companion character's attack or defense
    numbers"* and the three places they do apply -- damage, skills and
    initiative -- are either the power's business (damage) or outside this
    module.

    Refuses an unknown role rather than defaulting to one, because every
    number here comes off the role and a default would quietly build a
    different character than was asked for.
    """
    want = role.strip().lower()
    if want not in SHAPES:
        raise ValueError(
            f"{role!r} is not a party role: {', '.join(ROLES)}")
    level = max(1, int(level))
    shape = SHAPES[want]
    return Follower(
        role=want,
        level=level,
        con=con,
        hp=(level * shape.hp_per) + shape.hp_flat + con,
        surges=shape.surges + modifier(con),
        ac=shape.ac + level,
        fortitude=OTHER_DEFENCES + level,
        reflex=OTHER_DEFENCES + level,
        will=OTHER_DEFENCES + level,
        attack=ATTACK + level,
        damage=level // 2,
        feature=shape.feature,
    )


def classes_for(role: str) -> list[str]:
    """Which classes share a party role, for the power selection.

    > *"Choose a character class that has the same role as the companion
    > character."*

    Off `class.role`, which the importer fills, rather than a hand-written
    map: all four roles are populated for all 25 classes, so there is nothing
    to derive and nothing to go stale.

    This module's half of step 7. The other half -- the two basic attacks,
    one more at-will, one encounter attack and one utility, none above the
    companion's level -- is `dealt_hand` with three narrowings and is its own
    piece of work.
    """
    from combat_engine.db import game

    want = role.strip().lower()
    if want not in SHAPES:
        raise ValueError(
            f"{role!r} is not a party role: {', '.join(ROLES)}")
    return [
        str(row["name"])
        for row in game().execute(
            "SELECT name FROM class WHERE lower(role) = ? ORDER BY name",
            (want,),
        ).fetchall()
    ]
