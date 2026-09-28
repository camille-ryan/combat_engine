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
    AC,
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
    Moved,
    When,
    power,
)
from combat_engine.engine.dsl import get
from combat_engine.engine.query import allies, enemies, holding, squares


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


def _intimidating(c: Cast, ev: Any) -> None:
    """Strength on Intimidate for the rest of the fight.

    A skill bonus, and a live one: `engine/skills.py` reads
    `skill:intimidate` off `Mods` for every check, and Intimidate is
    one of the five skills this engine actually rolls in a fight.
    """
    c.bonus("skill:intimidate", c.str_mod, on=c.me, until=When.ENCOUNTER,
            kind="feat")


def _companion_steps(c: Cast, ev: Any) -> None:
    """"Before the attack" is why this hangs on `used=` rather than a hit."""
    beast = c.companion()
    if beast is not None:
        c.shift(1, who=beast)


def _no_long_range(c: Cast, ev: Any) -> None:
    """Laid on the use, so it is standing by the time the row rolls."""
    c.ignores_long_range(on=c.me, until=When.EOT)


def _second_shot(c: Cast, ev: Any) -> None:
    """A miss bought back with a ranged basic, paid for in openings.

    `c.may` is the printed "you can", asked of the caster because it is
    the caster's defence being sold. `c.grants_advantage`'s words name
    my own side, so handing it to the other one is `to=<that enemy>`,
    once per enemy.
    """
    gear = c.world.get(c.me, Gear)
    if gear is None or gear.ranged is None:
        return
    if not c.may("grant combat advantage for a second shot"):
        return
    for foe in enemies(c.world, c.me):
        c.grants_advantage(on=c.me, to=foe, until=When.SONT)
    c.basic(on=ev.target, ranged=True)


def _shield_the_neighbour(c: Cast, ev: Any) -> None:
    """A shield bonus that ends early if the target leaves its square.

    Two endings, "whichever comes first": `until=` carries one and the
    other is `Moved` plus `c.end_effect`. `Moved` is the movement event
    that carries both ends of the step, so "left its square" is one
    comparison rather than a remembered position.
    """
    foe = ev.target
    where = squares(c.world, foe)
    for friend in allies(c.world, c.me):
        if friend == c.me or not c.adjacent_to(foe, friend):
            continue
        held = c.bonus(AC, 1, on=friend, until=When.EONT, kind="shield")

        def moved(mv: Any, held: Any = held) -> None:
            if mv.actor == foe and mv.to not in where:
                c.end_effect(held, why=f"{c.ref} target moved")

        c.watch(Moved, moved, on=c.me, until=When.EONT,
                label=f"{c.ref} shield held")
        return


_riders("f990", {"p971": _shift_after, "p2105": _shift_after,
                 "p919": _ally_shift, "p1063": _ally_shift})

_riders("f993", {"p4541": _temp_hp("con_mod"), "p2248": _intimidating},
        used={"p4369": _companion_steps},
        dropped=("c.forgo_damage()",))

_riders("f991", {}, missed={"p917": _second_shot},
        used={"p970": _no_long_range})

_riders("f995", {"p1000": _shield_the_neighbour},
        dropped=("query.shield_bonus()",))


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
       reach=PERSONAL, target=SELF)
def f1016(c: Cast) -> None:
    """Swaps which ability a melee basic attack rolls.

    **Re-aimed off `c.basic_ability()` and then written.** The header on
    `mba` is indeed shared and must not be rewritten -- but the printed
    line is arithmetic, not a rewrite: `mba` rolls Strength and adds
    `c.str_mod` to the damage, so the swap is the difference between the
    two abilities, laid as a gated modifier on the one row. Exactly the
    printed numbers, and the shared header is untouched.

    "Choose an ability other than Strength" is a build-time choice
    nothing records, so it is read as the character's best other one --
    the same proxy `f1032` makes for a weapon group, and for the same
    reason: it is what the choice comes to for the chassis in hand.
    """
    best = max(c.dex_mod, c.con_mod, c.int_mod, c.wis_mod, c.cha_mod)
    # A printed "you can", so it is taken only where it is an
    # improvement -- laid unguarded on a chassis whose Strength is the
    # better score it was a **penalty** to the basic attack, which is
    # what an optional benefit written as a compulsory one looks like.
    if best <= c.str_mod:
        return
    swing = lambda ctx: ctx.get("power") == "mba"  # noqa: E731
    c.bonus("attack", best - c.str_mod, on=c.me, until=When.ENCOUNTER,
            when=swing)
    c.bonus("damage", best // 2 - c.str_mod, on=c.me, until=When.ENCOUNTER,
            when=swing)


@power("f1023", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f1023(c: Cast) -> None:
    """Maximises healing after a rest, **before the next encounter**.

    **Re-aimed off `c.maximise(healing=)`, which would not help.** The
    duration is the hold, and it is not a duration this engine is
    missing -- it is one that ends where the engine begins. Every hit
    point this feat maximises is restored between fights, so there is
    no moment inside an encounter at which it is ever true. That is an
    inert row rather than a marked one, and a `c.maximise(healing=)`
    would sit in the tree waiting for a verb that would change nothing.
    """


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
