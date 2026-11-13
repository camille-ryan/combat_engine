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

## Both of this file's headline findings turned out to be false

They are kept, corrected, because each was argued at length from a real
measurement and each was wrong about where to look.

**"The option-to-pact mapping is not in the import."** `-f1`, `-f2`,
`-f7` and `-f10` each read *"associated with your pact"*, and this file
measured that only three of `-f1`'s five options identify their pact by
keyword -- `ELEMENTAL`, `TELEPORTATION`, `SHADOW`, with two carrying
`ARCANE` and nothing else. All of that is true, and deriving three and
guessing two is what `CLAUDE.md` forbids. The conclusion does not
follow: the pact is in each option's **printed name**, for all 61
options of all 16 pact-keyed forks across both chassis, and nothing had
looked there. `chargen.OPTION_PACT` is the transcription,
`deal_build_options` narrows a fork to the character's leg, and
`drivers.pact_weapon` checks the table against the names on every run.
The same shape as `#1261`'s level and found the same way. `#1264`.

**"The engine has no verb that puts a weapon into a creature's `Gear`
from a ref."** `-f3`'s six options are the pact weapon, and the 24 rows
on `chargen.pact_blade()` rested on that plus *"none of `w3740`..`w3752`
is a declared row"*. All six are ordinary rows of the `weapon` table and
`chargen.PRINTED` had carried them throughout. There is no verb because
a pact weapon needs none -- it is **dealt**, and chargen is where gear
comes from. `#730`.

What survives from both: the arity reasoning was sound, and writing the
arity while the identity was unknown was better than either alternative.
The marker was doing its job; its premise was not re-measured for a
year.
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
from combat_engine.engine.events import PowerResolved, Summoned

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
    """One of the parents that print "associated with your pact".

    **The identity is known now, and these carried `dropped=
    ("chargen.pact_option_map()",)` saying it was not.** The parent always
    handed over one option, so a hexblade got one pact power rather than
    five or none; what was missing was *which* pact that option belonged
    to, and `#1264` recorded it as "absent from the import".

    The columns do not carry it, which is what that was measured on. The
    option's own printed **name** does: each begins with its pact, and
    the one pact printed twice says which of the two it is. That holds
    for all 61 options of all 16 pact-keyed forks, checked against
    `db.localisation()`. `chargen.OPTION_PACT` is the transcription and
    `deal_build_options` narrows the fork to the character's own leg
    before drawing, so the option a hexblade is dealt is its pact's.
    `#1264`, and the same shape as `#1261`'s level.
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

    **The summon half is written now, and the premise that refused it was
    false.** It read *"the summon itself is `#1264`-adjacent -- all
    nineteen of its creatures are named and not referenced -- so there is
    nothing on the board to pay"*, and `#1268` disproved every clause of
    that: the creatures are in `associate`, the ETL imports them, and
    `c.summon` has fielded an `x10_` ref since `#459`. `p13649` now
    summons the pact's own creature, so there IS something to pay.

    *"At 9th level you also gain this bonus to the damage rolls of the
    creature you summon with `p13649`"* is therefore a `Summoned` watch:
    the creature does not exist when this trait arms, so the bonus cannot
    be laid on it then. Gated on level 9 and on the summoner being this
    character, because a hexblade standing beside another one's summon
    pays nothing for it.

    The marker it carried was `chargen.companion_from_option()`, which was
    simply the wrong symbol -- this row has no companion and no option of
    its own to read. Recorded because a wrong symbol is worse than a
    missing one: `blocked.py --group` filed five damage rows under a
    companion gap.
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
        if c.level < 9:
            return

        def summoned(ev: Summoned) -> None:
            if getattr(ev, "actor", None) != me:
                return
            if getattr(ev, "ref", "") != SUMMON:
                return
            c.bonus("damage", amount, on=ev.summon, until=When.ENCOUNTER,
                    kind="untyped")

        c.watch(Summoned, summoned, until=When.ENCOUNTER, on=me, label=c.ref)

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


def _pact_blade(ref: str, what: str, *, marks: tuple[str, ...] = ()) -> Any:
    """One of the pact-weapon rows.

    **The weapon is dealt now, and these used to say it could not be.**
    `chargen.pact_blade()` was the symbol 15 power rows waited on too, 24
    in all, and the claim under it was that *"none of `w3740`..`w3752` is
    a declared row, and the engine has no verb that puts a weapon into a
    creature's `Gear` from a ref"*. Both halves were false about the
    thing that mattered: all six are ordinary rows of the `weapon` table
    and `chargen.PRINTED` has carried them the whole time. There was no
    verb because the weapon does not need one -- it is **dealt**, not
    manifested by a body, and `chargen` is where a character's gear comes
    from.

    So `cf:warlock-hexblade-f3`'s six options each carry a weapon that
    `chargen.PACT_BLADE` names and `spawn` appends to the loadout, keyed
    to the pact by `chargen.OPTION_PACT` so the weapon follows the pact
    the way the page prints it. The body stays empty for the reason every
    `BUILD_OPTIONS` option's does: the dealing *is* the effect.

    `marks` is for the parent, which is not finished -- see its call.
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
        todo=marks,
    )
    def row(c: Cast) -> None:
        pass

    row.__name__ = "hexblade_blade_" + ref.rsplit("-f", 1)[-1].replace("s", "_")
    row.__doc__ = f"{what}\n\nThe helper above has the argument."
    return row


hexblade_blade_3 = _pact_blade(
    "cf:warlock-hexblade-f3",
    "The pact weapon itself. The weapon is dealt -- see the helper -- and "
    "what is still missing is the rest of the printed sentence: it is "
    "manifested as a minor action while an implement is in the other "
    "hand, shares that implement's enhancement, critical effect, "
    "properties and powers, and is gone when either is let go.",
    # **A narrower symbol than the one this used to carry**, naming what
    # is actually left rather than the weapon. The weapon arrives; what
    # no facility does is make one carried item take another's
    # enhancement and properties for as long as both are held.
    marks=("c.shares_enhancement()",))
for _n, _w in enumerate(("w3752", "w3740", "w3743", "w3744", "w3741", "w3742")):
    globals()[f"hexblade_blade_3_{_n}"] = _pact_blade(
        f"cf:warlock-hexblade-f3s{_n}",
        f"One pact's weapon: `{_w}`. Dealt by `chargen.PACT_BLADE` when "
        f"this option is the one the character's pact takes.")

for _ref, _got in _F6_POWERS.items():
    globals()["hexblade_grant_" + _ref.rsplit("-f", 1)[-1].replace("s", "_")] = (
        _grant(_ref, _got,
               "One of `-f6`'s six options, keyed to a pact weapon by "
               "`chargen.OPTION_PACT` -- the same six pacts in the same "
               "printed order as `-f3`'s, so the rider and the weapon "
               "agree without either row reading the other."))


@power(
    "cf:warlock-hexblade-f6",
    level=0,
    cls="warlock",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
)
def hexblade_pact_6(c: Cast) -> None:
    """*"You gain a power associated with your pact weapon."*

    **It used to wait on `chargen.pact_blade()` for a reason that read
    backwards**: the note said this parent "needs the weapon before it
    can pick". It does not -- it needs to know *which option of `-f3` was
    taken*, and that is now recorded.

    **It reads `-f3`'s answer rather than drawing its own, and the fey
    pact is why.** A `BUILD_OPTIONS` entry of its own was the first
    attempt and it is a second independent draw: six options keyed to
    five pacts, because the fey pact's section is printed twice -- a
    plain one and a variant -- so on that one pact the two draws
    disagree. Measured, with an entry in place: a fey hexblade came out
    holding the plain weapon and carrying the variant's rider, which no
    gate would have reported because each half was individually right.

    One choice, one entry, several readers is the arrangement
    `content/CLAUDE.md` already prescribes -- the blackguard's vice, the
    cavalier's virtue, the sentinel's season -- and this is a fourth
    case of it.

    The six options sit in the same printed order under both parents
    -- each parent's option for a given pact sits at the same index --
    so the index carries across and `_F6_POWERS` is read by
    position rather than by a second mapping that could drift from the
    first.
    """
    took = c.chosen_option("cf:warlock-hexblade-f3")
    mine = took.replace("-f3s", "-f6s") if took else ""
    if mine in _F6_POWERS:
        c.grant_row(mine, on=c.me, until=When.ENCOUNTER)


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
    todo=("chargen.pact_blade()",),
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


def _printed_pick(ref: str, options: tuple[str, ...], what: str) -> Any:
    """A row printing *"one of the following powers"* with the list recovered.

    These carried `defect=` saying the spec *"lists nothing, so there is no
    set to choose from"*. The **spec** lists nothing; the compendium's class
    page prints the list immediately after the sentence, and every power in
    it is already imported. So the marker was describing the import rather
    than the source. `#1268`.

    How each list was recovered, and why it is a join rather than a parse:
    the page carries a `LEVEL N <CHASSIS> <USAGE> POWER` banner above the
    sentence, so a section is bounded on both sides; within it, the options
    are found by asking which of **this class's already-imported power
    names at that level** appear in the section. Presence of a known name,
    never a guess at where an unknown one ends -- so a boundary read wrongly
    cannot invent a power. The join is on `(level, usage)` from the banner
    against `combat_engine.levels` on this ref, and it **refuses** rather
    than guessing wherever the number of features at a level does not match
    the number of printed sections: the sentinel prints two level-1 banners
    (at-will and daily) and an earlier pass gave both features the first
    list.

    `chargen.BUILD_OPTIONS` carries the options and `c.chosen_option` reads
    the draw, which is the arrangement the pact forks already use -- and
    `c.grant_row` grants a power ref as readily as a feature one.
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
    )
    def row(c: Cast) -> None:
        # **Every option the build took, not the first of them.** A
        # fork that deals one answers a single-entry tuple, so this is
        # the same behaviour there -- and `cf:ranger-hunter-f19` and its
        # scout twin deal TWO, with more rungs adding a third and a
        # fourth, so granting `[0]` alone would hand over one aspect and
        # silently drop the rest. `chargen.OPTION_PICKS` and
        # `chargen.EXTRA_PICKS` decide how many.
        for took in c.chosen_options(ref) or options[:1]:
            c.grant_row(took, on=c.me, until=When.ENCOUNTER)

    row.__name__ = "hexblade_pick_" + ref.rsplit("-f", 1)[-1]
    row.__doc__ = (
        f'*"You gain one of the following powers of your choice."* {what}\n\n'
        f"{len(options)} options, recovered from the printed page rather "
        f"than from the spec -- see `_printed_pick`. `#1268`."
    )
    return row


def _summon_option(ref: str) -> Any:
    """One `-f7` option whose creature `p13649` summons.

    A pointer: the creature is named here and fielded there, because
    `p13649` is the row that summons and no modifier can reach into
    another row's `c.summon` call. The binder's `-f12` prints the same
    seven creatures and `features/binder.py` has the identical helper --
    two chassis, one list, and `p13649` names both chassis' refs in each
    of its seven branches.

    What these were marked with was wrong three times over: the
    compendium's `Associate` table carries the block, `etl/build.py`
    imports it into `associate`, and `c.summon` has routed an `x10_` ref
    to `loader.spawn_associate` since `#459`. `#1268`.
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
        implemented_in=("p13649",),
    )
    def row(c: Cast) -> None:
        pass

    row.__name__ = ("hexblade_summon_"
                    + ref.rsplit("-f", 1)[-1].replace("s", "_"))
    row.__doc__ = (
        '*"You can use `p13649` to summon a creature."*\n\n'
        "Written into `p13649`, which reads which option the character "
        "holds and fields the matching `associate` block. `#1268`."
    )
    return row


_SUMMON_OPTIONS = (
    "cf:warlock-hexblade-f7s0",
    "cf:warlock-hexblade-f7s1",
    "cf:warlock-hexblade-f7s4",
    "cf:warlock-hexblade-f7s5",
    "cf:warlock-hexblade-f7s6",
    "cf:warlock-hexblade-f7s7",
    "cf:warlock-hexblade-f7s8",
)

for _r in _SUMMON_OPTIONS:
    globals()["hexblade_summon_"
              + _r.rsplit("-f", 1)[-1].replace("s", "_")] = _summon_option(_r)


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
    "cf:warlock-hexblade-f7s2": "p13680, which is a POWER and not a creature",
    "cf:warlock-hexblade-f7s3": "a creature named and not referenced, in "
                                "four elemental variants chosen on a d4",
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
# **The in-scope ones had their list recovered from the page.**
# `#1268`: the spec lists nothing, the class page prints the list
# straight after the sentence, and every power in it is already
# imported. The rest are printed above level 10, which this
# project does not import, so they keep the marker.
hexblade_pick_11 = _printed_pick(
    "cf:warlock-hexblade-f11",
    ('p13635', 'p13636', 'p13637'),
    "The level-1 daily list.")
hexblade_pick_12 = _printed_pick(
    "cf:warlock-hexblade-f12",
    ('p13638', 'p13640', 'p1923'),
    "The level-2 utility list.")
hexblade_pick_13 = _printed_pick(
    "cf:warlock-hexblade-f13",
    ('p13642b', 'p13644', 'p13645'),
    "The level-5 daily list.")
hexblade_pick_14 = _printed_pick(
    "cf:warlock-hexblade-f14",
    ('p13646', 'p13648', 'p2264'),
    "The level-6 utility list.")
hexblade_pick_15 = _printed_pick(
    "cf:warlock-hexblade-f15",
    ('p13650b', 'p13652', 'p13653'),
    "The level-10 utility list.")
for _n in (17,):
    globals()[f"hexblade_defect_{_n}"] = _defective(
        f"cf:warlock-hexblade-f{_n}", _NO_LIST)
for _n in (16, 18, 19):
    globals()[f"hexblade_defect_{_n}"] = _defective(
        f"cf:warlock-hexblade-f{_n}",
        _NO_LIST + ", and the new power is also meant to replace a daily "
        "the character already has")
