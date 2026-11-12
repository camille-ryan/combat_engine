"""The binder, the warlock's third chassis and the last of `#642`'s 25.

69 printed rows, the most of any chassis, and **nine** parents printing
*"associated with your pact"* -- where the hexblade has four. Same gap,
same shape, same marker: the option-to-pact mapping is absent from the
import, so each fork is a `chargen.BUILD_OPTIONS` entry that deals one
option without knowing which pact it belongs to. `#1264`, and
`features/hexblade.py` has the argument at length.

    13  play
     9  pact forks -- one option dealt, the identity unknown
    18  a summoned creature named with no stat block -- `defect=`
    12  a named power with no ref the importer resolved -- `defect=`
     6  a `c7` power of your choice -- `chargen.power_choice()`
     3  a power replacing a daily -- `chargen.power_swap(daily)`
     1  the slash-joined ref pair this chassis shares with the hexblade

## The three pacts ARE derivable here, and it still is not enough

The binder's forks have **three** options each, and the keywords separate
all three of `-f1`'s cleanly:

    p16350  POISON,  SHADOW   p13904  PSYCHIC, FEAR, SHADOW
    p13914  COLD,    SHADOW,  ZONE

So a reading is available -- and it is a reading, not the mapping. Nothing
says which pact takes poison, which fear and which cold; the three are
distinguishable from each other without being identifiable. That is a
weaker position than the hexblade's, where three of five named a pact
outright, and it is the same conclusion: do not guess. `#1264`.

## The best content is `-f8`, and it is written

*"You gain a `cf:warlock-binder-f8` feature associated with your pact"* --
three concrete standing benefits rather than a power grant, so all three play.
They are the only rows on this chassis whose worth does not depend on the
mapping: whichever one a binder is dealt, it is a correct printed
benefit.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    ENCOUNTER,
    NO_TARGET,
    PERSONAL,
    WILL,
    ActionType,
    Cast,
    DamageType,
    Keyword,
    When,
    get,
    power,
)
from combat_engine.engine.events import Moved
from combat_engine.engine.query import team

#: The summoning row `-f12` grants and `-f21` adds to.
SUMMON = "p13649"

#: The reaches `-f4`'s bonus names -- "ranged attack rolls and area attack
#: rolls", which is two of the five reach kinds and not everything.
_RANGED_OR_AREA = ("ranged", "area")


def _lonely(c: Cast, victim: int) -> bool:
    """"Any enemy that has no other creature adjacent to it."

    **Any creature, not any ally**, which the card says and is the half
    worth getting right: a binder's bonus goes away when one of its own
    allies steps up to the target, not only when another enemy does. Read
    live, because it changes whenever anybody moves.
    """
    world = c.world
    return not any(other != victim and c.adjacent_to(victim, other)
                   for other in (*c.allies(), *c.enemies())
                   if other != victim and team(world, other) is not None)


def _a_ranged_or_area_row(ctx: dict[str, Any]) -> bool:
    """"Ranged attack rolls and area attack rolls", off the rolling row."""
    rolling = get(ctx.get("power") or "")
    return rolling is not None and rolling.reach.kind in _RANGED_OR_AREA


# -- the rows that play ------------------------------------------------------


@power(
    "cf:warlock-binder-f3",
    level=0,
    cls="warlock",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
)
def binder_grant(c: Cast) -> None:
    """"You gain the p13877 power."

    **In the draw.** A level-1 warlock power at a level-1 character is
    inside `loadout`'s pool, so whether this grant matters depends on the
    hand -- the third category `drivers.blackguard_vice` was rewritten to
    see.
    """
    c.grant_row("p13877", on=c.me, until=When.ENCOUNTER)


@power(
    "cf:warlock-binder-f4",
    level=0,
    cls="warlock",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
)
def binder_isolation(c: Cast) -> None:
    """"You gain a +1 bonus to ranged attack rolls and area attack rolls
    against any enemy that has no other creature adjacent to it."

    Two gates, both live. The reach kind is read off the rolling row --
    *ranged* and *area*, which is two of five and not everything, so a
    melee swing and a close burst get nothing. And the target's isolation
    is read at the moment of the roll, because it changes whenever
    anybody moves.

    **"No other creature" is any creature.** A binder's bonus goes away
    when one of its own allies steps up to the target, not only when
    another enemy does -- which is what the card says and is the half a
    reading of "no other enemy" would quietly get wrong in the binder's
    favour.
    """
    me = c.me

    def alone(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        if victim is None or not _a_ranged_or_area_row(ctx):
            return False
        return _lonely(c, victim)

    c.bonus("attack", 1, on=me, until=When.ENCOUNTER, kind="untyped",
            when=alone)


@power(
    "cf:warlock-binder-f5",
    level=0,
    cls="warlock",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
)
def binder_shroud(c: Cast) -> None:
    """"On your turn, if you move at least 3 squares away from where you
    started your turn, you gain concealment until the end of your next
    turn."

    A `Moved` watch that measures the distance from where the turn began,
    which is **not** the same as the distance walked: a binder that goes
    three squares out and three back has moved six and is where it
    started. `Moved` carries `from_` and `to`, and the square the turn
    began in is the first `from_` of the turn -- `query.since_turn_began`
    is the reader that makes that findable without a latch of this row's
    own.

    Laid once per turn rather than once per step. `c.latch(per_turn=True)`
    is the guard: without it a binder walking five squares would lay the
    concealment three times, and each would carry its own clock.
    """
    me = c.me

    def walked(ev: Moved) -> None:
        if getattr(ev, "actor", None) != me:
            return
        if c.latched(c.ref, per_turn=True):
            return
        began = _turn_start_square(c, me)
        here = getattr(ev, "to", None)
        if began is None or here is None:
            return
        if max(abs(began[0] - here[0]), abs(began[1] - here[1])) < 3:
            return
        c.latch(c.ref, per_turn=True)
        c.conceal(on=me, until=When.EONT)

    c.watch(Moved, walked, until=When.ENCOUNTER, on=me, label=c.ref)


def _turn_start_square(c: Cast, me: int) -> Any:
    """Where this creature's turn began, or `None`.

    The first `Moved.from_` of the turn, off `query.since_turn_began` --
    which is the reader `docs/symbols/reading.md` exists to surface, and
    the one three families were marked as engine gaps for want of.
    """
    from combat_engine.engine.query import since_turn_began

    for event in since_turn_began(c.world, me):
        if isinstance(event, Moved) and getattr(event, "actor", None) == me:
            return getattr(event, "from_", None)
    from combat_engine.engine.query import Position

    here = c.world.get(me, Position)
    return here.square if here is not None else None


@power(
    "cf:warlock-binder-f12",
    level=0,
    cls="warlock",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
)
def binder_summoning(c: Cast) -> None:
    """"You gain the p13649 power."

    **A real grant.** Level 9, far above a level-1 character, so the draw
    cannot reach it -- the same row `cf:warlock-hexblade-f7` grants and
    for the same reason.

    All nine of this row's own options and all nine of `-f21`'s are
    `defect=`: every creature they name is a printed name with no stat
    block the summon can field.
    """
    c.grant_row(SUMMON, on=c.me, until=When.ENCOUNTER)


@power(
    "cf:warlock-binder-f21",
    level=0,
    cls="warlock",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
    dropped=("chargen.pact_option_map()",),
)
def binder_second_summon(c: Cast) -> None:
    """*"You gain another creature that you can summon when you use p13649.
    The specific creature depends on your pact."*

    The tenth pact fork, and the only one of the eleven whose options are
    **all** `defect=` for a second reason: each names a creature with no
    stat block the summon can field, so the mapping would not make any of
    them playable. `cf:warlock-hexblade-f10` is the same row on the
    sibling chassis with the same nine options.

    So the parent hands one over and the option refuses itself, which is
    the case `cf:paladin-blackguard-f19` and `cf:paladin-cavalier-f14` are
    in: the parent is not broken, its options are.
    """
    options = tuple(f"cf:warlock-binder-f21s{i}" for i in range(9))
    c.grant_row(c.chosen_option("cf:warlock-binder-f21") or options[0],
                on=c.me, until=When.ENCOUNTER)


# -- `-f8`'s options, the one fork whose options all play -------------------


_LORE = ("cf:warlock-binder-f8s0", "cf:warlock-binder-f8s1",
         "cf:warlock-binder-f8s2")


@power(
    "cf:warlock-binder-f8s0",
    level=0,
    cls="warlock",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
)
def binder_lore_wards(c: Cast) -> None:
    """One `cf:warlock-binder-f8` option: *"you gain a +1 bonus to AC and
    Will."*

    Two calls, because AC and Will are separate keys and one `c.bonus`
    pays only one of them -- the mistake `cf:barbarian-f0` records at the
    top of `strikers_sb.py` and the fourth row in this wave to need
    saying.

    Untyped: a class feature stacks with everything and the card prints
    no type word.
    """
    for defence in (AC, WILL):
        c.bonus(defence, 1, on=c.me, until=When.ENCOUNTER, kind="untyped")


@power(
    "cf:warlock-binder-f8s1",
    level=0,
    cls="warlock",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
)
def binder_lore_dark(c: Cast) -> None:
    """Another `-f8` option: darkvision, and necrotic resistance that stacks
    with itself rather than beside itself.

    *"You gain darkvision and resist 5 necrotic. If you already have
    necrotic resistance of 5 or higher, that resistance instead increases
    by 5."*

    **The conditional is the clause**, and it is the whole reason this is
    not one `c.resist(5)`: resistances do not add in this engine -- the
    best one applies -- so a binder who already resists 5 would gain
    nothing from a second 5 and the card plainly means it to gain
    something. Reading what is already standing and laying `held + 5`
    answers both printings with one call.

    `c.resist` with no `dtype` would be resistance to everything, which is
    `cf:paladin-cavalier-f16`'s shape and not this one.
    """
    me = c.me
    c.darkvision(on=me, until=When.ENCOUNTER)
    held = c.resistances(on=me).get(DamageType.NECROTIC, 0)
    c.resist(held + 5 if held >= 5 else 5, DamageType.NECROTIC,
             until=When.ENCOUNTER, on=me)


@power(
    "cf:warlock-binder-f8s2",
    level=0,
    cls="warlock",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
    narrative=("skill:arcana",),
)
def binder_lore_mind(c: Cast) -> None:
    """The third `-f8` option: *"you gain resist 5 psychic and a +2 bonus to
    Arcana checks and Religion checks."*

    The resistance plays. The two skill bonuses are `narrative=`: an
    Arcana or Religion check is the story engine's, and
    `c.bonus("skill:arcana", ...)` would be laid where nothing in a fight
    reads it.

    `narrative=` and not `out_of_combat=True`, which is the distinction
    `cf:ranger-scout-f17s1` had to be corrected on: the row **has** a
    combat half, so the clause-level marker is the right one and the sweep
    will see the resistance fire.
    """
    c.resist(5, DamageType.PSYCHIC, until=When.ENCOUNTER, on=c.me)


# -- the nine pact forks ----------------------------------------------------


#: Every pact fork on this chassis, with the three options each offers.
#: Written out rather than derived from the refs, because the forks are
#: what `#1264` is about and a derived list would hide which rows are
#: affected.
PACT_FORKS: dict[str, tuple[str, ...]] = {
    f"cf:warlock-binder-f{n}": tuple(
        f"cf:warlock-binder-f{n}s{i}" for i in range(3))
    for n in (1, 2, 7, 8, 11, 14, 17, 20, 22)
}


def _pact_parent(ref: str, what: str, *, replaces: bool = False) -> Any:
    """One of the nine parents printing "associated with your pact".

    `dropped=` and not `todo=`: the parent **does** hand over one option,
    so a binder gets one pact power rather than three or none. What is
    missing is the identity, and `chargen.pact_option_map()` names exactly
    that -- the same symbol the hexblade's four parents carry, so
    `blocked.py --group` prices the gap at thirteen rows across two
    chassis rather than two gaps of four and nine.

    `replaces=True` adds the second symbol for the five later forks, whose
    text also says the new power **replaces** the one gained earlier: a
    grant without the replacement leaves a binder a power up on print.
    """
    marks = ["chargen.pact_option_map()"]
    if replaces:
        marks.append("chargen.power_swap(encounter)")

    @power(
        ref,
        level=0,
        cls="warlock",
        usage=ENCOUNTER,
        action=ActionType.NONE,
        reach=PERSONAL,
        target=NO_TARGET,
        keywords=[Keyword.ARCANE],
        dropped=tuple(marks),
    )
    def row(c: Cast) -> None:
        options = PACT_FORKS[ref]
        c.grant_row(c.chosen_option(ref) or options[0], on=c.me,
                    until=When.ENCOUNTER)

    row.__name__ = "binder_pact_" + ref.rsplit("-f", 1)[-1]
    row.__doc__ = (
        f'*"You gain {what} associated with your pact."*\n\n'
        "A **parent**, and it hands over one of its three options -- so "
        "the arity is right and the identity is not. The module docstring "
        "has the measurement: the three options are distinguishable from "
        "each other by keyword and not identifiable as pacts, which is a "
        "weaker position than the hexblade's and the same conclusion.\n\n"
        + ("The printed *replaces the power you gained earlier* is the "
           "second symbol: a grant without the replacement leaves a binder "
           "a power up on print, which is the wrong direction to land half "
           "of.\n\n" if replaces else "")
        + "`#1264`."
    )
    return row


binder_pact_1 = _pact_parent("cf:warlock-binder-f1", "an encounter attack power")
binder_pact_2 = _pact_parent(
    "cf:warlock-binder-f2", "an at-will attack power and a utility power")
binder_pact_7 = _pact_parent("cf:warlock-binder-f7", "an encounter attack power")
binder_pact_8 = _pact_parent("cf:warlock-binder-f8", "a `cf:warlock-binder-f8` feature")
binder_pact_11 = _pact_parent(
    "cf:warlock-binder-f11", "an encounter attack power")
for _n in (14, 17, 20, 22):
    globals()[f"binder_pact_{_n}"] = _pact_parent(
        f"cf:warlock-binder-f{_n}", "an encounter attack power", replaces=True)


# -- the options that grant a ref -------------------------------------------


def _grant(ref: str, got: tuple[str, ...], why: str) -> Any:
    """One of the pact options that grants one or two refs."""

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
        for one in got:
            c.grant_row(one, on=c.me, until=When.ENCOUNTER)

    row.__name__ = "binder_grant_" + ref.rsplit("-f", 1)[-1].replace("s", "_")
    row.__doc__ = (
        f'"You gain the {" and ".join(f"`{g}`" for g in got)} '
        f'power{"s" if len(got) > 1 else ""}."\n\n{why}')
    return row


_OPTION_REFS: dict[str, tuple[str, ...]] = {
    "cf:warlock-binder-f1s0": ("p16350",),
    "cf:warlock-binder-f1s1": ("p13904",),
    "cf:warlock-binder-f1s2": ("p13914",),
    "cf:warlock-binder-f2s0": ("p16348", "p16349"),
    "cf:warlock-binder-f2s1": ("p13902", "p13903"),
    "cf:warlock-binder-f2s2": ("p13912", "p13913"),
    "cf:warlock-binder-f7s0": ("p16351",),
    "cf:warlock-binder-f7s1": ("p13905",),
    "cf:warlock-binder-f7s2": ("p13915",),
    "cf:warlock-binder-f11s0": ("p16352",),
    "cf:warlock-binder-f11s1": ("p13906",),
    "cf:warlock-binder-f11s2": ("p13916",),
}

for _ref, _got in _OPTION_REFS.items():
    # One `get` per ref rather than two: the comprehension called it in
    # the guard and again in the value, so nothing narrowed `Power |
    # None` and `scripts/types.py` named it.
    _rows = [r for r in (get(g) for g in _got) if r is not None]
    _lvl = max(r.level for r in _rows)
    globals()["binder_grant_" + _ref.rsplit("-f", 1)[-1].replace("s", "_")] = (
        _grant(_ref, _got,
               "**In the draw**: a level-1 warlock power at a level-1 "
               "character is inside `loadout`'s pool."
               if _lvl <= 1 else
               f"**A real grant, and the level is why.** Level {_lvl} is "
               "above a level-1 character, so the draw cannot reach it."))


# -- the six draws and the three swaps --------------------------------------


def _pick(ref: str, what: str, *, swap: bool = False,
          gained: bool = False) -> Any:
    """One of the nine "a `c7` power of your choice" rows.

    `gained=True` is the two whose own text states the level the gain
    happens at -- *"a 1st-level"*, *"a 2nd-level"* -- so they carry a
    `chargen.EXTRA_GAINS` entry and no marker. The other seven say *"of
    your level or lower"* and name no level, and `class_feature` carries
    none (`#1261`), so an entry for them would be a guess about **when**
    the gain happens rather than about what it draws from.

    That is the whole difference between a row on this chassis that is
    finished and one that is not, and it is a property of the printed
    sentence rather than of the mechanism.
    """
    marks: tuple[str, ...] = ()
    if swap:
        marks = ("chargen.power_swap(daily)",)
    elif not gained:
        marks = ("chargen.power_choice()",)

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
        out_of_combat=gained,
    )
    def row(c: Cast) -> None:
        pass

    row.__name__ = "binder_pick_" + ref.rsplit("-f", 1)[-1]
    row.__doc__ = (
        f"{what}\n\n"
        + ("`chargen.power_swap(daily)` and not `power_choice()`, which is "
           "`cf:paladin-blackguard-f18`'s distinction: these **trade** a "
           "daily rather than adding one, and a draw that added without "
           "replacing leaves a binder a daily up on print."
           if swap else
           "**Finished.** The card states the level the gain happens at, "
           "so `chargen.EXTRA_GAINS` carries it: `loadout` deals the "
           "extra power to a character holding this row and to nobody "
           "else, which is `#1112`'s mechanism. `out_of_combat=True` "
           "because the whole row is a draw -- a fight has no use for it "
           "and the sweep credits it as silent on a board as claimed."
           if gained else
           "`chargen.power_choice()`'s gap -- and specifically the "
           "**level** half of it: this card says *of your level or lower* "
           "and names no level for the gain itself, which `#1261` is "
           "about. The two rows beside it that do name one are finished.")
    )
    return row


binder_pick_0 = _pick("cf:warlock-binder-f0",
                      "A 1st-level `c7` attack power.", gained=True)
binder_pick_6 = _pick("cf:warlock-binder-f6",
                      "A 2nd-level `c7` utility power.", gained=True)
binder_pick_9 = _pick("cf:warlock-binder-f9", "A `c7` attack power.")
binder_pick_10 = _pick("cf:warlock-binder-f10", "A `c7` utility power.")
binder_pick_13 = _pick("cf:warlock-binder-f13", "Another `c7` utility power.")
binder_pick_16 = _pick("cf:warlock-binder-f16", "Another `c7` utility power.")
binder_pick_15 = _pick(
    "cf:warlock-binder-f15", "A `c7` attack power replacing a daily.",
    swap=True)
binder_pick_18 = _pick(
    "cf:warlock-binder-f18", "Another, replacing a daily.", swap=True)
binder_pick_23 = _pick(
    "cf:warlock-binder-f23", "Another, replacing a daily.", swap=True)


# -- the thirty-one rows the import cannot supply ---------------------------


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

    row.__name__ = "binder_defect_" + ref.rsplit("-f", 1)[-1].replace("s", "_")
    row.__doc__ = f"Refused: {why}"
    return row


#: `-f12`'s and `-f21`'s eighteen summon options, identical to the
#: hexblade's `-f7` and `-f10` -- the same eighteen creatures, named the
#: same way, with the same six refs resolving to associates and a power
#: rather than to monsters.
_NAMED = ("a creature named and not referenced, so there is no stat block "
          "the summon can field")
_AS_REF = ("the ref the spec gives is an associate or a power rather than "
           "a monster, so there is no stat block the summon can field")

for _base in (12, 21):
    for _i in range(9):
        _r = f"cf:warlock-binder-f{_base}s{_i}"
        globals()["binder_defect_" + _r.rsplit("-f", 1)[-1].replace("s", "_")] = (
            _defective(_r, _AS_REF if _i in (2, 4, 6) else _NAMED))

#: The twelve later pact options, every one a printed power name with no
#: ref. Four forks of three, and the pattern is what makes it worth a
#: shared reason: the import resolved every option of `-f1`, `-f2`, `-f7`
#: and `-f11` and **none** of `-f14`, `-f17`, `-f20` and `-f22`.
for _base in (14, 17, 20, 22):
    for _i in range(3):
        _r = f"cf:warlock-binder-f{_base}s{_i}"
        globals()["binder_defect_" + _r.rsplit("-f", 1)[-1].replace("s", "_")] = (
            _defective(
                _r,
                "the spec names the granted power by its printed name "
                "instead of a ref, so the importer did not resolve it -- "
                "every option of the four later pact forks is like this "
                "and every option of the four earlier ones resolved"))

binder_defect_19 = _defective(
    "cf:warlock-binder-f19",
    "the spec reads 'you gain the cf:warlock-binder-f19/cf:warlock-hexblade"
    "-f9 power' -- a slash-joined pair of FEATURE refs where a power ref "
    "belongs, one of them this row itself. `cf:warlock-hexblade-f9` carries "
    "the identical spec, so the two chassis share one unresolved line")
