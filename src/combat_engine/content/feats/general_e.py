"""General feats, fifth batch: the last exploit riders and a few
standalone ones worth the space.

`_riders` is the same machine `exploits.py` uses -- one watcher per
feat, the clause picked by which power hit -- so the four Associated
Powers rows here are four short entries rather than sixteen `c.watch`
calls.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.feats.exploits import _riders
from combat_engine.engine import (
    DAILY,
    ENCOUNTER,
    ONE_CREATURE,
    PERSONAL,
    REF,
    SELF,
    Ability,
    ActionType,
    Attack,
    Cast,
    Gear,
    Keyword,
    Melee,
    When,
    power,
)
from combat_engine.engine.dsl import get
from combat_engine.engine.query import allies, holding


def _shift_after(c: Cast, ev: Any) -> None:
    c.shift(1)


def _temp_hp(mod: str):  # noqa: ANN202
    def clause(c: Cast, ev: Any) -> None:
        c.temp_hp(getattr(c, mod), on=c.me)

    return clause


def _ally_shift(c: Cast, ev: Any) -> None:
    for friend in allies(c.world, c.me):
        if c.adjacent(to=friend):
            c.shift(1, who=friend)
            return


_riders("f990", {"p971": _shift_after, "p2105": _shift_after,
                 "p919": _ally_shift, "p1063": _ally_shift})

_riders("f993", {"p4541": _temp_hp("con_mod")},
        dropped=("c.forgo_damage()",))

_riders("f991", {}, todo=("c.on_miss(ref)",))

_riders("f995", {}, todo=("c.shield_bonus()",))


@power("f1002", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1002(c: Cast) -> None:
    """Combat advantage at range against anyone your allies are flanking
    -- which is normally a melee-only benefit, and is the whole point of
    the feat. `query.flanked` is the printed question."""
    from combat_engine.engine.query import flanked_by

    me = c.me

    def by_my_allies(ctx: dict) -> bool:
        foe = ctx.get("target")
        if not ctx.get("ranged", False) or foe is None:
            return False
        # `flanked_by` asks whether *that* creature flanks the target,
        # so the question is asked once per ally rather than once: the
        # printed line is about the allies flanking, not about me.
        return any(
            friend != me and flanked_by(c.world, foe, friend)
            for friend in allies(c.world, me)
        )

    c.bonus("attack", 2, on=me, until=When.ENCOUNTER, when=by_my_allies)


@power("f1032", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1032(c: Cast) -> None:
    """"Choose a weapon group" is a build-time choice nothing records,
    so the group is read as the one the character is carrying -- which
    is what the choice comes to for a character with one weapon, and
    every chassis has one."""
    gear = c.world.get(c.me, Gear)
    arm = gear.main if gear else None
    if arm is None:
        return
    group = arm.group
    c.bonus(
        "attack", 1, on=c.me, until=When.ENCOUNTER, kind="feat",
        when=lambda ctx: bool(holding(c.world, c.me, group))
        and (p := get(ctx.get("power", ""))) is not None
        and Keyword.WEAPON in p.keywords,
    )


@power("f1033", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1033(c: Cast) -> None:
    """Rolling a check twice is narrative; the initiative bonus is not,
    and it is the reason this is not an `out_of_combat` row.

    **`c.bonus("initiative", ...)` is read by nothing.**
    `Initiative.bonus` is summed before the d20 and `Mods` is never
    consulted, which `c.initiative`'s own docstring says outright -- so
    the modifier I laid here sat in the table and no roll ever saw it.
    `c.initiative` moves the creature in the order after the fact,
    which is the only thing that can say this from a trait.

    A trait is armed *after* the opening rolls, so this lands as an
    adjustment rather than a bonus -- the same arrangement `f288` and
    `f2055` make.
    """
    c.initiative(3, on=c.me)


@power("f1016", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.basic_ability()",))
def f1016(c: Cast) -> None:
    """Swaps which ability a melee basic attack rolls. The basic's
    attack line is header data on `mba` and shared by everyone, so
    rewriting it for one character has nowhere to go."""


@power("f1023", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.maximise(healing=)",))
def f1023(c: Cast) -> None:
    """Maximises healing after a rest, until the next fight starts.
    `c.maximise` maximises damage; healing has no counterpart, and the
    duration is "before your next encounter", which no `When` names."""


@power("f969", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f969(c: Cast) -> None:
    c.grant_row("f969b", on=c.me, until=When.ENCOUNTER)


@power("f969b", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, keywords=[Keyword.WEAPON])
def f969b(c: Cast) -> None:
    """Threaten at the whip's reach rather than at adjacency.

    I marked this `c.threaten_at(reach)`. **`c.threatens` exists** and
    is that verb -- "it can make opportunity attacks against enemies
    within 2 squares" is its docstring's own example, and it is held as
    a modifier so a reach weapon can raise it.
    """
    c.threatens(2, on=c.me, until=When.ENCOUNTER)


@power("f970", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f970(c: Cast) -> None:
    c.grant_row("f970b", on=c.me, until=When.ENCOUNTER)


@power("f970b", level=1, cls="", usage=DAILY, action=ActionType.STANDARD,
       reach=Melee(2), target=ONE_CREATURE, keywords=[Keyword.WEAPON],
       attack=Attack(Ability.DEX, vs=REF),
       dropped=("c.grab(pull_as_minor=)",))
def f970b(c: Cast) -> None:
    """The grab and the prone land on a hit *and* on a miss -- only the
    damage differs -- so both are written outside the branch. Dropped:
    pulling the grabbed creature as a minor action, which wants an
    action the grab itself hands over."""
    hit = c.strike().hit
    if hit:
        c.damage(c.w(2), c.dex_mod)
    c.grab()
    c.prone()
    c.penalty("escape", 5)
