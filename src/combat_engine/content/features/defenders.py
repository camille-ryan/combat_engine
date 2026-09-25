"""The two defenders' marking features, and the paladin's hand-off heal.

A defender's whole job is that leaving it alone costs you, and these are the
rows that make that true. Without them a fighter is a creature with a sword.

The fighter's half is four rows because the book prints four things. `p7419`
is the riposte and has a compendium id of its own; the mark that makes it
mean anything, the bonus to punishing an opening, the chase that replaces
that bonus, and the fork in how the weapon is held are described only on the
class's page and carry `cf:` refs.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    ENCOUNTER,
    MINOR,
    NO_TARGET,
    ONE_ALLY,
    ONE_CREATURE,
    OPPORTUNITY,
    PERSONAL,
    SELF,
    STR,
    ActionType,
    Attack,
    Cast,
    CloseBurst,
    DamageType,
    Gear,
    Health,
    Keyword,
    Melee,
    OpportunityWindow,
    Relation,
    Trigger,
    When,
    World,
    distance,
    leaves_me_out,
    power,
)
from combat_engine.engine.basic import MELEE
from combat_engine.engine.dsl import get, use
from combat_engine.engine.events import AttackDeclared, AttackRolled, Moved
from combat_engine.engine.query import alive, enemies
from combat_engine.engine.query import squares as squares_of

from . import CHANNEL_DIVINITY


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
        # fighter is what the mark was asking for and costs nothing -- and
        # that has to be judged over the whole attack, not this one
        # announcement, or a burst that caught the fighter still drew a
        # riposte off one of its other targets.
        if ev.attacker != me and leaves_me_out(world, me, ev):
            riposte(ev.attacker)

    def on_shift(ev: Moved) -> None:
        riposte(ev.actor)

    c.watch(AttackDeclared, on_attack, until=When.ENCOUNTER, on=me, label="fighter mark")
    c.watch(Moved, on_shift, until=When.ENCOUNTER, on=me, label="fighter mark")


@power(
    "cf:fighter-mark",
    level=0,
    cls="fighter",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def fighter_mark(c: Cast) -> None:
    """The other half of the arrangement `p7419` punishes: laying the mark.

    `p7419` was written as the riposte alone, so the fighter had a standing
    threat against creatures nothing ever marked -- and the -2 the printed
    text hangs on the mark went with it. Only the laying is here; the penalty
    itself is `resolve._mark_penalty`, which already charges a marked
    creature for leaving its marker out of the attack.

    Announced off the roll rather than the declaration, because the printed
    line is "whether the attack hits or misses" -- an attack that an
    interrupt cancelled never happened and marks nobody. One mark per
    creature is the relation's own rule, so a second attack on the same
    target simply refreshes it.
    """
    me, world = c.me, c.world

    def on_roll(ev: AttackRolled) -> None:
        if ev.attacker != me or ev.target not in enemies(world, me):
            return
        if c.marked(on=ev.target):
            return  # already carrying this fighter's mark; nothing to ask
        if c.may("mark it", who=me):
            c.mark(on=ev.target, until=When.EONT)

    c.watch(AttackRolled, on_roll, until=When.ENCOUNTER, on=me, label="cf:fighter-mark")


@power(
    "cf:fighter-opening",
    level=0,
    cls="fighter",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def fighter_opening(c: Cast) -> None:
    """The fighter is better at punishing an opening than anyone else.

    `opportunity` is a key the attack context already carries, so the whole
    of the first printed sentence is one gated modifier. Untyped, because the
    printed line names no bonus type and a typed one would refuse to stack
    with the weapon's.

    The second sentence -- an enemy hit this way stops moving -- is **not
    here**; see `docs/blocked.json`. `movement.walk` never asks again whether
    the creature may still move once the walk has begun, so immobilising it
    inside the opportunity window leaves it walking the rest of its path.
    """
    c.bonus(
        "attack",
        c.wis_mod,
        until=When.ENCOUNTER,
        on=c.me,
        kind="untyped",
        when=lambda ctx: bool(ctx.get("opportunity")),
    )


_AN_OPENING = "an enemy takes an action that gives you an opening"


def _my_opening(world: World, me: int, ev: OpportunityWindow) -> bool:
    """The window is only ever opened for somebody who threatens the provoker.

    `movement.step`, `Cast.provoke` and the ranged-in-melee check all name
    the responder as `actor`, so "an enemy adjacent to you" is already
    decided by the time this is asked -- the engine does not open a window
    for anyone out of reach.
    """
    return ev.actor == me and alive(world, ev.provoker)


@power(
    "cf:fighter-chase",
    level=0,
    cls="fighter",
    usage=AT_WILL,
    action=OPPORTUNITY,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL, Keyword.WEAPON],
    attack=Attack(STR, vs=AC),
    trigger=_AN_OPENING,
    on=Trigger(OpportunityWindow, _my_opening, _AN_OPENING),
)
def fighter_chase(c: Cast) -> None:
    """Chase the opening down before swinging at it.

    The window names the provoker; the dispatcher would aim a targeted row at
    `actor`, which is the fighter itself, so the victim is read off the
    trigger and the header takes no target.

    "You must end the shift closer to the target" is a filter on the
    destination rather than a distance to cover, so the squares are picked
    here and named outright -- handed to the mover the fighter would happily
    shift the wrong way.

    **This and `cf:fighter-opening` replace each other**, and both are
    declared because the class page lists both. Nothing enforces the choice:
    neither leg of `chargen.BUILDS["fighter"]` is this fork, so a dealt
    fighter carries both and is a little stronger at an opening than any
    printed one. A leg for it would settle it.
    """
    foe = getattr(c.trigger, "provoker", None)
    if foe is None:
        return
    steps = max(0, c.dex_mod)
    anchor = min(squares_of(c.world, foe))
    was = min(distance(sq, anchor) for sq in squares_of(c.world, c.me))
    if steps:
        options = sorted(
            sq
            for sq in c.world.reachable_squares(c.me, steps)
            if distance(sq, anchor) < was
        )
        where = c.choose(options, "cf:fighter-chase: where to end up") if options else None
        if where is not None:
            c.shift(steps, to=where)
    if c.strike(on=foe):
        c.damage(c.w(), c.str_mod, on=foe)
        c.prone(on=foe)


@power(
    "cf:fighter-grip",
    level=0,
    cls="fighter",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def fighter_grip(c: Cast) -> None:
    """The fork in how the fighter holds its weapon, worth +1 to hit with it.

    Six talents are printed and `chargen.BUILDS["fighter"]` carries two legs,
    so only the two that *are* the legs are written: the one-handed talent and
    the two-handed one. The other four fork on things no `Build` records --
    an open off hand, temporary hit points, a second weapon -- and are in
    `docs/blocked.json` rather than folded into a leg that does not mean them.

    Both halves check what is actually in hand, which is the printed
    Requirement and not a restatement of the build: a great-weapon fighter
    who has swapped to one hand is not getting this.

    **The two-handed half is presently unreachable.** Neither fighter leg in
    `chargen.BUILDS` names a weapon, so both fall back to the class line's
    one-hander and `held.two_handed` is never true. The gate is the printed
    one and is left alone; the leg is what wants fixing.
    """
    me, world = c.me, c.world
    two_handed = c.build("great-weapon")

    def gate(ctx: dict[str, Any]) -> bool:
        declared = get(str(ctx.get("power", "")))
        if declared is None or Keyword.WEAPON not in declared.keywords:
            return False
        gear = world.get(me, Gear)
        held = gear.main if gear is not None else None
        return held is not None and held.two_handed == two_handed

    c.bonus("attack", 1, until=When.ENCOUNTER, on=me, kind="untyped", when=gate)


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
        # "Attacks somebody else" means the paladin was not among the
        # targets at all. Testing this announcement's target instead let a
        # burst that included the paladin pay out anyway, off whichever
        # other target happened to be announced first.
        if ev.attacker != mark or not leaves_me_out(c.world, me, ev):
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
    group=CHANNEL_DIVINITY,
)
def p1747(c: Cast) -> None:
    """Extra damage on the paladin's next attack this turn."""
    c.bonus("damage", c.str_mod, until=When.SONT, on=c.me, kind="power")
