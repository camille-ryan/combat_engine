"""Monster abilities, level 2, minions: the second sweep.

Seventeen stat blocks whose rows were still undeclared. A minion's attack row is
the plainest thing in the tree -- one fixed number, declared as
`Damage(bonus=5, kind=MINION)` so it stays data, and `if c.strike(): c.hit()`
underneath it -- and almost everything interesting about these blocks is in the
traits beside it.

Two shapes recur so often here that they are settled once at the top:

* "+2 power bonus to all defences while at least two others of its kind are
  within 5 squares" is a count of a *kind*, and the only thing an author is
  given to compare is the ref, so that is what is compared. Gated rather than
  fixed when the trait arms: who is standing where changes every turn;
* "5 damage, or 7 with combat advantage" reads the advantage off the roll, not
  off the board afterwards -- a one-shot grant has already been spent by the
  time the attack is over.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_01.skirmishers import _ref_of
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_OTHER,
    ENCOUNTER,
    FORT,
    INTERRUPT,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    WILL,
    ActionType,
    Attack,
    Cast,
    CloseBurst,
    Condition,
    Damage,
    DamageType,
    Keyword,
    Melee,
    Size,
    When,
    World,
    power,
)
from combat_engine.engine.events import Dropped, Hit, TurnStart
from combat_engine.engine.monster_math import MINION
from combat_engine.engine.query import distance_between, enemies
from combat_engine.engine.triggers import Trigger, about_me, targets_me

# -- what the blocks in this file share -------------------------------------


def _kin_within(c: Cast, radius: int, of: int) -> list[int]:
    """Creatures of the caster's own stat block standing near somebody.

    `side="team"` counts the caster in, which is why the printed "two **other**"
    is tested against three.
    """
    mine = _ref_of(c, c.me)
    return [w for w in c.within(radius, of=of, side="team") if _ref_of(c, w) == mine]


def _in_company(c: Cast) -> bool:
    return len(_kin_within(c, 5, c.me)) >= 3


def _closes_ranks(c: Cast, value: int, kind: str = "power") -> None:
    """"+N bonus to all defences while two others of its kind are near."""
    for defence in (AC, FORT, REF, WILL):
        c.bonus(
            defence, value, on=c.me, until=When.ENCOUNTER, kind=kind,
            when=lambda _ctx: _in_company(c),
        )


def _triggering_enemy(c: Cast) -> int | None:
    ev = c.trigger
    if ev is None:
        return None
    who = getattr(ev, "attacker", None)
    return who if who is not None else getattr(ev, "actor", None)


# --------------------------------------------------------------------------
# m115725
# --------------------------------------------------------------------------


@power(
    "m115725a0",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.ignores_difficult(when=)",),
)
def m115725a0(c: Cast) -> None:
    """The whole of this row is the narrowing: rough ground is ignored *when it
    shifts* and not when it walks. `c.ignores_difficult` writes a terrain word
    and takes no gate, so installing it bare would be a row stronger than its
    card."""


@power(
    "m115725a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage(bonus=5, kind=MINION),
)
def m115725a1(c: Cast) -> None:
    """Both outcomes move it, which is the whole shape of the row: a hit buys
    two squares and a miss still buys one."""
    if c.strike():
        c.hit()
        c.shift(2)
    else:
        c.shift(1)


# --------------------------------------------------------------------------
# m115800
# --------------------------------------------------------------------------


@power(
    "m115800a0",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m115800a0(c: Cast) -> None:
    _closes_ranks(c, 2)


@power(
    "m115800a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage(bonus=5, kind=MINION),
)
def m115800a1(c: Cast) -> None:
    if c.strike():
        c.hit()


# --------------------------------------------------------------------------
# m1682
# --------------------------------------------------------------------------


@power(
    "m1682a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage(bonus=3, kind=MINION),
)
def m1682a0(c: Cast) -> None:
    """Two numbers on one hit, so the larger is dealt flat: the header can hold
    only the one the card leads with, and `c.flat` is a fixed number rather than
    dice, which is what a minion's damage is."""
    result = c.strike()
    if not result:
        return
    if result.advantage:
        c.flat(5)
    else:
        c.hit()


@power(
    "m1682a1",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1682a1(c: Cast) -> None:
    """Counted off the attack's own context rather than paired when the trait
    arms: who is hemmed in changes every time anybody walks. "Adjacent to one or
    more creatures" is read as the attacker's friends -- the attacker itself is
    adjacent to anything it can reach, which would make the trait always true
    and the card say nothing."""
    c.gains_advantage(
        lambda ctx: isinstance(ctx.get("target"), int)
        and any(c.adjacent_to(ctx["target"], mate) for mate in c.allies()),
        until=When.ENCOUNTER,
        on=c.me,
    )


# --------------------------------------------------------------------------
# m2019
# --------------------------------------------------------------------------


@power(
    "m2019a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=5),
    damage=Damage(bonus=4, kind=MINION),
)
def m2019a0(c: Cast) -> None:
    if c.strike():
        c.hit()


# --------------------------------------------------------------------------
# m2238
# --------------------------------------------------------------------------


@power(
    "m2238a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage(bonus=5, kind=MINION),
)
def m2238a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2238a1",
    level=2,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m2238a1(c: Cast) -> None:
    c.shift(1)


@power(
    "m2238a2",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it hits with its sword",
    on=Trigger(
        Hit,
        lambda world, me, ev: getattr(ev, "attacker", None) == me
        and getattr(ev, "power", "") == "m2238a0",
        "it hits with its sword",
    ),
)
def m2238a2(c: Cast) -> None:
    """"One other enemy adjacent to it" is a choice, so it is offered rather
    than taken: the first enemy in a list is the lowest eid and not a decision.
    A No Action with a printed Trigger is not a trait -- a trait is simply true
    -- and `WINDOW_OF` puts it after the thing it answers."""
    struck = getattr(c.trigger, "target", None)
    others = [foe for foe in c.within(1, side="enemy") if foe != struck]
    picked = c.choose(others, "who else the blow catches") if others else None
    if picked is not None:
        c.flat(2, on=picked)


@power(
    "m2238a3",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2238a3(c: Cast) -> None:
    """A plain "+2 bonus" with no type word is untyped, so no `kind=`. The gate
    reads the attacker out of the roll's own context, which is the only place
    "against traps" can be asked from."""
    for defence in (AC, FORT, REF, WILL):
        c.bonus(
            defence, 2, on=c.me, until=When.ENCOUNTER,
            when=lambda ctx: c.is_trap(ctx.get("attacker")),
        )


# --------------------------------------------------------------------------
# m3243
# --------------------------------------------------------------------------


@power(
    "m3243a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage(bonus=4, kind=MINION),
)
def m3243a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3243a1",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=Melee(1),
    target=NO_TARGET,
    trigger="it drops to 0 hit points",
    on=Trigger(Dropped, about_me, "it drops to 0 hit points"),
    dropped=("spec.weapon_ref()",),
)
def m3243a1(c: Cast) -> None:
    """The parting swing is the creature's own basic attack, so a block whose
    basic has been replaced swings with the right thing.

    "Requires a flail" cannot be enforced: a monster carries no named gear and
    the spec gives no ref for the weapon this card wants, so the Requirement is
    vacuously true rather than checked.
    """
    reachable = [foe for foe in c.within(1, side="enemy")]
    if reachable:
        c.basic(on=reachable[0])


# --------------------------------------------------------------------------
# m3333
# --------------------------------------------------------------------------


@power(
    "m3333a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    todo=("etl.monster.ability_text()",),
)
def m3333a0(c: Cast) -> None:
    """The card is empty. The extraction gives the action, the usage and nothing
    else -- no attack line, no damage, no effect -- so there is no sentence to
    write and nothing to guess from."""


@power(
    "m3333a1",
    level=2,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    todo=("etl.monster.ability_text()",),
)
def m3333a1(c: Cast) -> None:
    """Empty, as above."""


# --------------------------------------------------------------------------
# m3552
# --------------------------------------------------------------------------


@power(
    "m3552a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage(bonus=5, kind=MINION),
)
def m3552a0(c: Cast) -> None:
    """The printed +12 is high for the level and is written as printed:
    `Attack(printed=)` takes the level term back out itself, so a number that
    looks wrong on the page is not the header's business."""
    if c.strike():
        c.hit()


@power(
    "m3552a1",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3552a1(c: Cast) -> None:
    _closes_ranks(c, 2)


# --------------------------------------------------------------------------
# m3831
# --------------------------------------------------------------------------


def _started_turn_near_me(world: World, me: int, ev: Any) -> bool:
    actor = getattr(ev, "actor", None)
    if actor is None or actor == me or getattr(ev, "ghost", False):
        return False
    return distance_between(world, me, actor) <= 3


@power(
    "m3831a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage(bonus=4, kind=MINION),
)
def m3831a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3831a1",
    level=2,
    usage=AT_WILL,
    action=ActionType.OPPORTUNITY,
    reach=CloseBurst(3),
    target=NO_TARGET,
    trigger="a creature starts its turn within 3 squares of it",
    on=Trigger(
        TurnStart, _started_turn_near_me, "a creature starts its turn within 3 squares"
    ),
)
def m3831a1(c: Cast) -> None:
    """Declared on `TurnStart` because that is the printed moment, and the
    creature is slid where it stands rather than where it is going."""
    who = _triggering_enemy(c)
    if who is not None:
        c.slide(1, on=who)


@power(
    "m3831a2",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PSYCHIC],
    trigger="it drops to 0 hit points",
    on=Trigger(Dropped, about_me, "it drops to 0 hit points"),
)
def m3831a2(c: Cast) -> None:
    """"Adjacent to one or more of these" counts the dying creature's own kind,
    itself included -- it is still on the board when `Dropped` is announced,
    which is why the printed line reads the way it does."""
    for foe in c.enemies():
        if _kin_within(c, 1, foe):
            c.flat(2, dtype=DamageType.PSYCHIC, on=foe)


@power(
    "m3831a3",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3831a3(c: Cast) -> None:
    _closes_ranks(c, 2)


# --------------------------------------------------------------------------
# m4633
# --------------------------------------------------------------------------


def _above_an_enemy(world: World, eid: int) -> bool:
    """"Must be on a surface above the target", asked of the board.

    A gate is handed the caster and no target, so the nearest thing it can say
    is that there is somebody below it. Which one is then the chooser's
    business, and the body checks the one actually picked.
    """
    from combat_engine.engine.falling import height

    return any(height(world, eid) > height(world, foe) for foe in enemies(world, eid))


@power(
    "m4633a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage(bonus=4, kind=MINION),
)
def m4633a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4633a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=7),
    damage=Damage(bonus=5, kind=MINION),
    requires=_above_an_enemy,
    requires_text="must be on a surface above the target",
)
def m4633a1(c: Cast) -> None:
    """The drop comes before the swing, as printed. "It does not take falling
    damage from using this power" needs nothing written: the move is a shift and
    a shift does not drop anybody, so there is no fall to soften."""
    if c.target is None:
        return
    c.shift(3)
    if c.strike():
        c.hit()


@power(
    "m4633a2",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=CloseBurst(2),
    target=EACH_OTHER,
    attack=Attack(vs=REF, printed=5),
    damage=Damage(bonus=4, kind=MINION),
    trigger="it drops to 0 hit points",
    on=Trigger(Dropped, about_me, "it drops to 0 hit points"),
)
def m4633a2(c: Cast) -> None:
    if c.strike():
        c.hit()


# --------------------------------------------------------------------------
# m4695
# --------------------------------------------------------------------------


@power(
    "m4695a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage(bonus=5, kind=MINION),
)
def m4695a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.shift(1)


@power(
    "m4695a1",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4695a1(c: Cast) -> None:
    """A plain "+2 bonus to damage" with no type word is untyped, and it is
    gated rather than fixed when the trait arms: the company it keeps changes
    every turn."""
    c.bonus("damage", 2, on=c.me, until=When.ENCOUNTER, when=lambda _ctx: _in_company(c))


# --------------------------------------------------------------------------
# m4758
# --------------------------------------------------------------------------


@power(
    "m4758a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=7),
    damage=Damage(bonus=4, kind=MINION),
)
def m4758a0(c: Cast) -> None:
    """The bigger number is for a target already down, so it is asked before the
    row knocks anybody over -- the two clauses are not the same sentence."""
    result = c.strike()
    if not result:
        return
    if c.is_(Condition.PRONE):
        c.flat(5)
    else:
        c.hit()
    if result.advantage:
        c.prone()


# --------------------------------------------------------------------------
# m6033
# --------------------------------------------------------------------------


@power(
    "m6033a0",
    level=2,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    trigger="an enemy hits it with an attack",
    on=Trigger(Hit, targets_me, "an enemy hits it with an attack"),
)
def m6033a0(c: Cast) -> None:
    """`keep="new"` is "must use the new result". `c.reroll_attack` reads the
    roll off `c.trigger`, which is the only place a spent d20 still exists -- and
    an interrupt is the window where changing it still decides the blow."""
    c.reroll_attack(keep="new")


# --------------------------------------------------------------------------
# m6036
# --------------------------------------------------------------------------


@power(
    "m6036a0",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6036a0(c: Cast) -> None:
    """`ctx["actor"]` is whoever would swing, which is the only place the size
    the card names can be read from. `Size` is a `StrEnum` and does not order,
    so "Medium or larger" is written as the two it excludes."""
    c.no_provoke(
        on=c.me,
        until=When.ENCOUNTER,
        when=lambda ctx: c.size_of(ctx.get("actor")) not in (Size.TINY, Size.SMALL),
    )


@power(
    "m6036a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage(bonus=5, kind=MINION),
)
def m6036a1(c: Cast) -> None:
    result = c.strike()
    if not result:
        return
    if result.advantage:
        c.flat(7)
    else:
        c.hit()


# --------------------------------------------------------------------------
# m6630
# --------------------------------------------------------------------------


@power(
    "m6630a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.DISEASE],
    attack=Attack(vs=AC, printed=7),
    damage=Damage(bonus=5, kind=MINION),
    dropped=("c.disease()",),
)
def m6630a0(c: Cast) -> None:
    """The contagion is the clause with nowhere to go: it is a saving throw made
    *after* the encounter against a track of stages, and nothing here lasts past
    the last round or carries a stage."""
    result = c.strike()
    if not result:
        return
    if result.advantage:
        c.flat(7)
    else:
        c.hit()
    c.shift(1)


# --------------------------------------------------------------------------
# m6673
# --------------------------------------------------------------------------


@power(
    "m6673a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage(bonus=5, dtype=DamageType.POISON, kind=MINION),
)
def m6673a0(c: Cast) -> None:
    result = c.strike()
    if not result:
        return
    if result.advantage:
        c.flat(7, dtype=DamageType.POISON)
    else:
        c.hit()


@power(
    "m6673a1",
    level=2,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    dropped=("query.acted_this_turn()",),
)
def m6673a1(c: Cast) -> None:
    """The step is the playable half. "Must have taken no actions this turn" has
    nothing to ask: a turn records what it has left to spend and not what it has
    already spent, so the Requirement is vacuously true."""
    c.shift(max(1, c.speed_of(c.me) // 2))


# --------------------------------------------------------------------------
# m6694
# --------------------------------------------------------------------------


@power(
    "m6694a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=7),
    damage=Damage(bonus=5, kind=MINION),
)
def m6694a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6694a1",
    level=2,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m6694a1(c: Cast) -> None:
    c.shift(max(1, c.speed_of(c.me) // 2))
