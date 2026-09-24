"""The two defenders' marking features, and the paladin's hand-off heal.

A defender's whole job is that leaving it alone costs you, and these are the
rows that make that true. Without them a fighter is a creature with a sword.
"""

from __future__ import annotations

from combat_engine.engine import (
    AT_WILL,
    ENCOUNTER,
    MINOR,
    NO_TARGET,
    ONE_ALLY,
    ONE_CREATURE,
    PERSONAL,
    SELF,
    ActionType,
    Cast,
    CloseBurst,
    DamageType,
    Health,
    Keyword,
    Melee,
    Relation,
    When,
    power,
)
from combat_engine.engine.basic import MELEE
from combat_engine.engine.dsl import use
from combat_engine.engine.events import AttackDeclared, Moved
from combat_engine.engine.query import alive


@power(
    "p7419",
    level=0,
    cls="fighter",
    # A trait: the arrangement stands from the moment the fight begins. The
    # riposte inside it is the immediate action, and it costs one each time
    # it fires; arming is not itself something the fighter does.
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL, Keyword.WEAPON],
    trigger="an enemy you marked, adjacent to you, shifts or attacks somebody else",
)
def p7419(c: Cast) -> None:
    """The fighter's punishment: walk away, or swing at somebody else, and it
    swings back.

    A standing arrangement rather than something used on a turn. It watches
    the two things the printed trigger names -- a marked enemy shifting, and
    a marked enemy attacking anybody but the fighter -- and answers each with
    a melee basic attack. `c.watch` ties the subscription to an effect, so it
    ends when the fight does.
    """
    me = c.me
    world = c.world

    def riposte(who: int) -> None:
        if not world.relations.holds(Relation.MARKED_BY, me, who):
            return
        if not (alive(world, me) and alive(world, who)):
            return
        if c.adjacent(who):
            use(world, me, MELEE, targets=[who], spend=False)

    def on_attack(ev: AttackDeclared) -> None:
        # Attacking anybody *but* the fighter is the trigger. Attacking the
        # fighter is what the mark was asking for and costs nothing.
        if ev.attacker != me and ev.target != me:
            riposte(ev.attacker)

    def on_shift(ev: Moved) -> None:
        riposte(ev.actor)

    c.watch(AttackDeclared, on_attack, until=When.ENCOUNTER, on=me, label="fighter mark")
    c.watch(Moved, on_shift, until=When.ENCOUNTER, on=me, label="fighter mark")


@power(
    "p805",
    level=0,
    cls="paladin",
    usage=AT_WILL,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_CREATURE,
    keywords=[Keyword.DIVINE, Keyword.RADIANT],
)
def p805(c: Cast) -> None:
    """The paladin's mark, thrown across the room rather than earned in melee.

    One target at a time: the printed text says the mark lasts until the
    power is used again, and `Relation.MARKED_BY` already allows a creature
    only one marker. What the mark costs is radiant damage the first time
    each round the target attacks somebody else.
    """
    me, mark = c.me, c.target
    if mark is None:
        return
    c.mark(until=When.ENCOUNTER)
    struck: dict[int, int] = {}

    def on_attack(ev: AttackDeclared) -> None:
        if ev.attacker != mark or ev.target == me:
            return
        if struck.get(mark) == c.world.round:
            return  # the first time each round, and no more
        struck[mark] = c.world.round
        c.flat(3 + c.cha_mod, dtype=DamageType.RADIANT, on=mark)

    c.watch(AttackDeclared, on_attack, until=When.ENCOUNTER, on=me, label="paladin mark")


@power(
    "p1566",
    level=0,
    cls="paladin",
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(1),
    target=ONE_ALLY,
    keywords=[Keyword.DIVINE, Keyword.HEALING],
    uses=1,
    once_per_round=True,
)
def p1566(c: Cast) -> None:
    """The paladin spends its own surge and somebody else gets the healing.

    The printed text allows this a Wisdom-modifier number of times per *day*.
    A day is not something the engine has, so once per fight is the closest
    honest reading, and it is written down here rather than left implied.
    """
    who = c.target
    mine = c.world.get(c.me, Health)
    if who is None or mine is None or not c.spend_surge(on=c.me):
        return
    theirs = c.world.get(who, Health)
    if theirs is not None:
        c.heal(theirs.surge_value, on=who)


@power(
    "p1747",
    level=0,
    cls="paladin",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.DIVINE],
)
def p1747(c: Cast) -> None:
    """Extra damage on the paladin's next attack this turn."""
    c.bonus("damage", c.str_mod, until=When.SONT, on=c.me, kind="power")
