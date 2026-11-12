"""The hexblade, the warlock's second chassis.

`#642`'s wave. 60 printed rows, and the first chassis whose forks key on a
**leg** rather than on a `chargen.BUILD_OPTIONS` answer -- the warlock's
seven pacts are legs already, and four of the hexblade's parents print
*"associated with your pact"*.

    14  play
     7  the pact weapon -- `chargen.pact_blade()`, 15 rows already wait
     4  the pact forks, which cannot pick without a mapping
    19  a summoned creature named and not referenced -- `defect=`
     9  "one of the following powers" and no list -- `defect=`
     2  another use of the pact-weapon attack per encounter
     5  the pact damage bonus, which is the best content here

## The pact forks cannot pick, and the reason is a gap in the import

`-f1`, `-f2`, `-f7` and `-f10` each read *"associated with your pact"* and
each has its own options. **The option-to-pact mapping is not in the
import.** The base class has it -- `cf:warlock-f1s0`..`s6` carry `on_leg`
headers for all seven pacts in alphabetical order -- and the hexblade's
own sub-options print only *"you gain the pXXXXX power"* with no pact
named.

It is partly derivable and that is not enough. Three of `-f1`'s five
options identify themselves by keyword:

    p16257  ELEMENTAL      -> the elemental pact
    p13669  TELEPORTATION  -> the fey pact
    p13962  SHADOW         -> the dark pact
    p13679  ARCANE only    -> ambiguous
    p13721  ARCANE only    -> ambiguous

Deriving three and guessing two is what `CLAUDE.md` forbids -- *"if a spec
is garbled, refer it up rather than guessing"* -- so the mapping is not
written.

**What is written instead is the arity, not the identity.** Each parent is
a `chargen.BUILD_OPTIONS` fork, so a hexblade is dealt **one** pact power
rather than all five or none, and each parent carries
`chargen.pact_option_map()` saying the chosen one may not be the one its
pact prescribes. That is strictly better than either alternative and the
marker says exactly what is wrong. `#1264`.

## The pact weapon already had a symbol

`-f3` and its six options are the pact weapon, and
`chargen.pact_blade()` is the symbol **15 rows already wait on** -- so
these seven join an existing group rather than minting a synonym, which
is what `blocked.py --group` exists to make possible.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    ENCOUNTER,
    NO_TARGET,
    PERSONAL,
    ActionType,
    Cast,
    Keyword,
    When,
    get,
    power,
)
from combat_engine.engine.events import PowerResolved

#: The summoning row `-f7` grants and `-f8`, `-f10` are about.
SUMMON = "p13649"

#: The four parents that print "associated with your pact", and the one
#: place the list is written.
PACT_FORKS = ("cf:warlock-hexblade-f1", "cf:warlock-hexblade-f2",
              "cf:warlock-hexblade-f7", "cf:warlock-hexblade-f10")


def _chosen(c: Cast, parent: str, options: tuple[str, ...]) -> str:
    """Which option this hexblade took on one of the pact forks.

    **Each fork draws its own**, which is the opposite of the blackguard's
    four vice parents reading one entry -- and it is right here for a
    reason that is not comfortable: the forks have 5, 5, 9 and 9 options
    and no mapping says which option belongs to which pact, so there is
    no shared answer for them to agree about. `#1264` is that gap.

    When the mapping lands, these four become readers of the **leg** --
    `c.build(<pact>)` -- and not of a `BUILD_OPTIONS` entry at all.
    """
    return c.chosen_option(parent) or options[0]


# -- the grants -------------------------------------------------------------


def _grant(ref: str, got: str, why: str, *, pact: bool = False) -> Any:
    """One of the thirteen "you gain <power>" rows."""

    @power(
        ref,
        level=0,
        cls="warlock",
        usage=ENCOUNTER,
        action=ActionType.NONE,
        reach=PERSONAL,
        target=NO_TARGET,
        keywords=[Keyword.ARCANE],
    )
    def row(c: Cast) -> None:
        c.grant_row(got, on=c.me, until=When.ENCOUNTER)

    row.__name__ = "hexblade_grant_" + ref.rsplit("-f", 1)[-1].replace("s", "_")
    row.__doc__ = f'"You gain the `{got}` power."\n\n{why}'
    return row


hexblade_grant_0 = _grant(
    "cf:warlock-hexblade-f0", "p13634",
    "**In the draw.** A level-1 warlock power at a level-1 character is "
    "inside `loadout`'s pool, so whether this grant matters depends on the "
    "hand -- the third category `drivers.blackguard_vice` was rewritten to "
    "see.")
hexblade_grant_5 = _grant(
    "cf:warlock-hexblade-f5", "p13641",
    "**A real grant, and the level is why.** Level 4 is above a level-1 "
    "character, so the draw cannot reach it.")
hexblade_grant_7 = _grant(
    "cf:warlock-hexblade-f7", SUMMON,
    "**A real grant.** Level 9, far above the draw -- and the row `-f8` "
    "and all eighteen of `-f7`'s and `-f10`'s options are about.")


# -- the pact forks: one option dealt, the identity unknown -----------------


_F1 = ("cf:warlock-hexblade-f1s0", "cf:warlock-hexblade-f1s1",
       "cf:warlock-hexblade-f1s2", "cf:warlock-hexblade-f1s3",
       "cf:warlock-hexblade-f1s4")

_F1_POWERS = {
    "cf:warlock-hexblade-f1s0": "p16257",
    "cf:warlock-hexblade-f1s1": "p13669",
    "cf:warlock-hexblade-f1s2": "p13962",
    "cf:warlock-hexblade-f1s3": "p13679",
    "cf:warlock-hexblade-f1s4": "p13721",
}

_F2 = ("cf:warlock-hexblade-f2s0", "cf:warlock-hexblade-f2s1",
       "cf:warlock-hexblade-f2s2", "cf:warlock-hexblade-f2s3",
       "cf:warlock-hexblade-f2s4")

#: Which ability each of `-f2`'s five options spends, read off the printed
#: text of each and **not** inferred from a pact: two name Constitution,
#: two Dexterity and one Intelligence.
_F2_ABILITY = {
    "cf:warlock-hexblade-f2s0": "con",
    "cf:warlock-hexblade-f2s1": "dex",
    "cf:warlock-hexblade-f2s2": "dex",
    "cf:warlock-hexblade-f2s3": "con",
    "cf:warlock-hexblade-f2s4": "int",
}

_F6 = tuple(f"cf:warlock-hexblade-f6s{n}" for n in range(6))
_F6_POWERS = {
    "cf:warlock-hexblade-f6s0": "p16260",
    "cf:warlock-hexblade-f6s1": "p13672",
    "cf:warlock-hexblade-f6s2": "p13752",
    "cf:warlock-hexblade-f6s3": "p13965",
    "cf:warlock-hexblade-f6s4": "p13682",
    "cf:warlock-hexblade-f6s5": "p13724",
}


def _pact_parent(ref: str, options: tuple[str, ...], what: str) -> Any:
    """One of the four parents that print "associated with your pact".

    `dropped=` and not `todo=`: the parent **does** hand over one option,
    so a hexblade gets one pact power rather than five or none. What is
    missing is the identity -- which option belongs to which pact -- and
    `chargen.pact_option_map()` names exactly that. `#1264`.
    """

    @power(
        ref,
        level=0,
        cls="warlock",
        usage=ENCOUNTER,
        action=ActionType.NONE,
        reach=PERSONAL,
        target=NO_TARGET,
        keywords=[Keyword.ARCANE],
        dropped=("chargen.pact_option_map()",),
    )
    def row(c: Cast) -> None:
        c.grant_row(_chosen(c, ref, options), on=c.me, until=When.ENCOUNTER)

    row.__name__ = "hexblade_pact_" + ref.rsplit("-f", 1)[-1]
    row.__doc__ = (
        f'*"You gain {what} associated with your pact."*\n\n'
        "A **parent**, and it hands over one of its options -- so the "
        "arity is right and the identity is not. The module docstring has "
        "the measurement: three of `-f1`'s five options identify their "
        "pact by keyword and two do not, so deriving the mapping would "
        "mean guessing at two of five, which `CLAUDE.md` forbids.\n\n"
        "When `#1264` lands this becomes a reader of the **leg** -- the "
        "warlock's seven pacts are legs already -- and not a "
        "`BUILD_OPTIONS` fork at all."
    )
    return row


hexblade_pact_1 = _pact_parent(
    "cf:warlock-hexblade-f1", _F1, "a power")
hexblade_pact_2 = _pact_parent(
    "cf:warlock-hexblade-f2", _F2, "a bonus to damage rolls")

for _ref, _got in _F1_POWERS.items():
    globals()["hexblade_grant_" + _ref.rsplit("-f", 1)[-1].replace("s", "_")] = (
        _grant(_ref, _got,
               "One of `-f1`'s five options. A no-op grant: a level-0 "
               "warlock row, already dealt -- so what the fork is worth is "
               "the exclusivity, and that is what `#1264` undoes."))


def _pact_damage(ref: str) -> Any:
    """One of `-f2`'s five damage bonuses.

    *"The bonus equals your <ability> modifier. The bonus increases to
    2 + at 5th level, 4 + at 15th, and 6 + at 25th."*

    **The ladder is written and not marked**, which is the distinction
    `features/thief.py` draws: this is a scaling number **inside one
    clause**, printed in the same sentence, not a separate feature row
    superseding a lower one. `#1261`'s line is about the second kind.

    The ability is read off each option's own printed text -- two name
    Constitution, two Dexterity, one Intelligence -- and **not** inferred
    from a pact, which is the mapping that does not exist.

    *"Your warlock and warlock paragon path attack powers"* is the class
    off the rolling row. A paragon path is not modelled here, so the test
    is the class, which is the whole of what this tree can say.

    Dropped: *"at 9th level, you also gain this bonus to the damage rolls
    of the creature you summon with `p13649`"*. The summon itself is
    `#1264`-adjacent -- all nineteen of its creatures are named and not
    referenced -- so there is nothing on the board to pay.
    """
    ability = _F2_ABILITY[ref]

    @power(
        ref,
        level=0,
        cls="warlock",
        usage=ENCOUNTER,
        action=ActionType.NONE,
        reach=PERSONAL,
        target=NO_TARGET,
        keywords=[Keyword.ARCANE],
        dropped=("chargen.companion_from_option()",),
    )
    def row(c: Cast) -> None:
        me = c.me
        step = 6 if c.level >= 25 else 4 if c.level >= 15 else 2 if c.level >= 5 else 0
        amount = step + getattr(c, f"{ability}_mod")
        if amount <= 0:
            return

        def a_warlock_row(ctx: dict[str, Any]) -> bool:
            rolling = get(ctx.get("power") or "")
            return (rolling is not None and rolling.cls == "warlock"
                    and rolling.is_attack)

        c.bonus("damage", amount, on=me, until=When.ENCOUNTER,
                kind="untyped", when=a_warlock_row)

    row.__name__ = "hexblade_damage_" + ref.rsplit("s", 1)[-1]
    row.__doc__ = (
        f"One pact's damage bonus: {ability.title()} modifier, rising to "
        f"2 + at 5th, 4 + at 15th and 6 + at 25th.\n\n"
        "The helper above has the argument for writing the ladder and for "
        "reading the ability off the printed text rather than off a pact."
    )
    return row


for _ref in _F2:
    globals()["hexblade_damage_" + _ref.rsplit("s", 1)[-1]] = _pact_damage(_ref)


@power(
    "cf:warlock-hexblade-f8",
    level=0,
    cls="warlock",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
    dropped=("chargen.companion_from_option()",),
)
def hexblade_summon_damage(c: Cast) -> None:
    """"When you summon a creature using p13649, it gains a +3 power bonus
    to damage rolls."

    The watch is written and the recipient is not. `PowerResolved` for
    `p13649` is the moment, and `c.bonus("damage", 3, on=<the summon>,
    kind="power")` is the whole effect -- but there is **no summon on the
    board**, because all nineteen creatures `-f7` and `-f10` name are
    printed names with no ref the importer resolved.

    So the row lays the bonus on whatever the summoning row put down, and
    lays nothing when it put down nothing -- which is the honest shape:
    the day the creatures have refs this works unchanged.

    `c.companions()` is the reader and it answers about **this** caster's
    own -- which matters, because a party with two summoners would
    otherwise have each boosting the other's.

    `kind="power"` because the card prints the word.
    """
    me = c.me

    def boost(ev: PowerResolved) -> None:
        if getattr(ev, "actor", None) != me:
            return
        if getattr(ev, "power", "") != SUMMON:
            return
        for who in c.companions():
            c.bonus("damage", 3, on=who, until=When.ENCOUNTER,
                    kind="power")

    c.watch(PowerResolved, boost, until=When.ENCOUNTER, on=me, label=c.ref)


# -- the pact weapon: seven rows on an existing symbol ----------------------


def _pact_blade(ref: str, what: str) -> Any:
    """One of the seven pact-weapon rows.

    `chargen.pact_blade()` is the symbol **15 rows already wait on**, so
    these seven join that group rather than minting a synonym -- which is
    what `content/CLAUDE.md` asks (*"reuse a symbol already in the tree so
    the groups mean something"*) and what makes `blocked.py --group` able
    to price the gap at 22 rows.

    What is missing, precisely: a weapon manifested in a hand that shares
    the implement's enhancement, critical effect, properties and powers,
    and which vanishes when either is let go. None of `w3740`..`w3752` is
    a declared row, and the engine has no verb that puts a weapon into a
    creature's `Gear` from a ref.
    """

    @power(
        ref,
        level=0,
        cls="warlock",
        usage=ENCOUNTER,
        action=ActionType.NONE,
        reach=PERSONAL,
        target=NO_TARGET,
        keywords=[Keyword.ARCANE],
        todo=("chargen.pact_blade()",),
    )
    def row(c: Cast) -> None:
        pass

    row.__name__ = "hexblade_blade_" + ref.rsplit("-f", 1)[-1].replace("s", "_")
    row.__doc__ = f"{what}\n\nThe helper above has the argument."
    return row


hexblade_blade_3 = _pact_blade(
    "cf:warlock-hexblade-f3",
    "The pact weapon itself: manifested as a minor action while an "
    "implement is in the other hand, sharing the implement's enhancement "
    "and properties, and gone when either is let go.")
for _n, _w in enumerate(("w3752", "w3740", "w3743", "w3744", "w3741", "w3742")):
    globals()[f"hexblade_blade_3_{_n}"] = _pact_blade(
        f"cf:warlock-hexblade-f3s{_n}",
        f"One pact's weapon: `{_w}`.")

hexblade_pact_6 = _pact_blade(
    "cf:warlock-hexblade-f6",
    "A power associated with the pact weapon chosen -- so this parent "
    "needs the weapon before it can pick.")
for _ref, _got in _F6_POWERS.items():
    globals()["hexblade_grant_" + _ref.rsplit("-f", 1)[-1].replace("s", "_")] = (
        _grant(_ref, _got,
               "One of `-f6`'s six options, each keyed to a pact weapon "
               "the engine cannot manifest -- so the option is written and "
               "its parent waits on `chargen.pact_blade()`."))


# -- another use, and the rest -----------------------------------------------


@power(
    "cf:warlock-hexblade-f4",
    level=0,
    cls="warlock",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
    todo=("chargen.feature_level()", "chargen.pact_blade()"),
)
def hexblade_another_use(c: Cast) -> None:
    """"You gain one more use per encounter of the `cf:warlock-hexblade-f3`
    attack power that you gained at 1st level."

    **Two symbols, and it was three.** `Powers.per_encounter(extra=)` is
    built now -- `c.more_uses` writes `Powers.extra_uses` and `dsl.usable`
    reads it -- so what is left is the level (`#1261`) and the pact weapon
    whose attack power this would add a use of (`chargen.pact_blade()`).
    A row cannot be written while either is absent, and marking fewer
    would report it ready early.
    """


# -- the nineteen summoned creatures, and the nine lists --------------------


def _defective(ref: str, why: str) -> Any:
    """A row naming something no ref resolves."""

    @power(
        ref,
        level=0,
        cls="warlock",
        usage=ENCOUNTER,
        action=ActionType.NONE,
        reach=PERSONAL,
        target=NO_TARGET,
        keywords=[Keyword.ARCANE],
        defect=why,
    )
    def row(c: Cast) -> None:
        pass

    row.__name__ = "hexblade_defect_" + ref.rsplit("-f", 1)[-1].replace("s", "_")
    row.__doc__ = f"Refused: {why}"
    return row


#: `-f7`'s and `-f10`'s options, and what each names. The ones that
#: resolved to a ref are marked so -- `defect=` is still right for those,
#: because a creature summoned by `p13649` needs a stat block the summon
#: can read and these refs are a power and five associates, not monsters.
_SUMMONS = {
    "cf:warlock-hexblade-f7s0": "a creature named and not referenced",
    "cf:warlock-hexblade-f7s1": "a creature named and not referenced",
    "cf:warlock-hexblade-f7s2": "p13680, which is a POWER and not a creature",
    "cf:warlock-hexblade-f7s3": "a creature named and not referenced, in "
                                "four elemental variants chosen on a d4",
    "cf:warlock-hexblade-f7s4": "x10_6, an associate and not a monster",
    "cf:warlock-hexblade-f7s5": "a creature named and not referenced",
    "cf:warlock-hexblade-f7s6": "x10_8, an associate and not a monster",
    "cf:warlock-hexblade-f7s7": "a creature named and not referenced",
    "cf:warlock-hexblade-f7s8": "a creature named and not referenced, and "
                                "gated on holding w3743, which is not a "
                                "declared weapon either",
    "cf:warlock-hexblade-f10s0": "a creature named and not referenced",
    "cf:warlock-hexblade-f10s1": "a creature named and not referenced",
    "cf:warlock-hexblade-f10s2": "a creature named and not referenced",
    "cf:warlock-hexblade-f10s3": "a creature named and not referenced, in "
                                 "four elemental variants chosen on a d4",
    "cf:warlock-hexblade-f10s4": "x10_7, an associate and not a monster",
    "cf:warlock-hexblade-f10s5": "x10_26, an associate and not a monster",
    "cf:warlock-hexblade-f10s6": "x10_9, an associate and not a monster",
    "cf:warlock-hexblade-f10s7": "a creature named and not referenced",
    "cf:warlock-hexblade-f10s8": "a creature named and not referenced, and "
                                 "gated on holding w3743",
}

for _ref, _what in _SUMMONS.items():
    globals()["hexblade_defect_"
              + _ref.rsplit("-f", 1)[-1].replace("s", "_")] = _defective(
        _ref,
        f"the spec says `p13649` can summon {_what}, so there is no stat "
        "block the summon can field")

hexblade_pact_7 = _pact_parent(
    "cf:warlock-hexblade-f10", tuple(
        r for r in _SUMMONS if r.startswith("cf:warlock-hexblade-f10")),
    "another creature to summon")

hexblade_defect_9 = _defective(
    "cf:warlock-hexblade-f9",
    "the spec reads 'you gain the cf:warlock-binder-f19/cf:warlock-hexblade"
    "-f9 power' -- a slash-joined pair of FEATURE refs where a power ref "
    "belongs, one of them this row itself, so nothing resolves")

_NO_LIST = ("the spec reads 'you gain one of the following powers of your "
            "choice' and then lists nothing, so there is no set to choose "
            "from")
for _n in (11, 12, 13, 14, 15, 17):
    globals()[f"hexblade_defect_{_n}"] = _defective(
        f"cf:warlock-hexblade-f{_n}", _NO_LIST)
for _n in (16, 18, 19):
    globals()[f"hexblade_defect_{_n}"] = _defective(
        f"cf:warlock-hexblade-f{_n}",
        _NO_LIST + ", and the new power is also meant to replace a daily "
        "the character already has")
