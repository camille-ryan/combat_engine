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
    Gear,
    Health,
    Keyword,
    Melee,
    Relation,
    When,
    leaves_me_out,
    power,
)
from combat_engine.engine.dsl import get
from combat_engine.engine.events import AttackDeclared, AttackRolled, Hit, Moved
from combat_engine.engine.query import alive, enemies

from . import CHANNEL_DIVINITY

#: "A melee or a close attack", as the reach kinds the header can carry.
_MELEE_OR_CLOSE = ("melee", "close_burst", "close_blast")


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
            # `c.basic` rather than `MELEE` outright: eight feats read
            # "in place of the melee basic attack that Combat Challenge
            # allows", and this is the window they name.
            c.basic(on=who, window="challenge")

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
    "cf:fighter-weaponmaster-f1",
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

    c.watch(AttackRolled, on_roll, until=When.ENCOUNTER, on=me, label="cf:fighter-weaponmaster-f1")


@power(
    "cf:fighter-weaponmaster-f2",
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

    The second sentence -- an enemy hit this way stops moving, if a move
    provoked the attack -- is **not here**; see `docs/blocked.json`.
    `movement.walk` asks `can_move` once, before the first step, and `step`
    never asks again, so immobilising the mover inside the opportunity
    window leaves it walking the rest of its path.

    One leg takes `cf:fighter-weaponmaster-f0` in place of this, and the printed
    sentence there says so outright.
    """
    if c.build("brawling"):
        return
    c.bonus(
        "attack",
        c.wis_mod,
        until=When.ENCOUNTER,
        on=c.me,
        kind="untyped",
        when=lambda ctx: bool(ctx.get("opportunity")),
    )


#: The row this feature hands over. It is a real level 0 fighter row, so
#: every fighter `chargen` deals already knows it.
_AGILITY = "p10469"


@power(
    "cf:fighter-weaponmaster-f0",
    level=0,
    cls="fighter",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def fighter_chase(c: Cast) -> None:
    """The opening one leg takes in place of `cf:fighter-weaponmaster-f2`.

    The printed feature is a single sentence: it replaces the bonus feature
    and hands over `p10469`. This row was written as a second copy of that
    row's body instead -- the shift, the swing and the knockdown, all of it
    -- so a fighter had the same opportunity attack twice under two refs,
    and had it whichever leg it was on.

    `chargen.loadout` deals a class every level 0 row it has, so the grant
    is a no-op for the leg that took this and the exclusivity is the half
    that has to happen: every other leg loses the row. Same shape as
    `cf:warlord-marshal-f1`, and for the same reason.
    """
    if c.build("brawling"):
        c.grant_row(_AGILITY)
    else:
        # `c.forbid` follows `c.target`, and a trait has none -- without
        # `on=` it takes the row away from nobody and reads as working.
        c.forbid(_AGILITY, until=When.ENCOUNTER, on=c.me)


@power(
    "cf:fighter-weaponmaster-f3",
    level=0,
    cls="fighter",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def fighter_grip(c: Cast) -> None:
    """Which of the six printed talents this fighter took.

    Every leg of `chargen.BUILDS["fighter"]` is one of them now, so the row
    asks the leg rather than assuming that a fighter which is not a
    great-weapon fighter fights one-handed -- four of the six do not.

    Three are written. The two weapon talents check what is actually in
    hand, which is the printed Requirement and not a restatement of the
    build: a great-weapon fighter who has swapped to one hand is not
    getting this. The third is the temporary hit points a hit buys.

    The other three are in `docs/blocked.json`: they turn on an empty off
    hand, on improvised weapons, and on wearing something lighter than
    the chassis wears, and `Build` records none of the three.
    """
    me, world = c.me, c.world

    def with_a_weapon(ctx: dict[str, Any]) -> bool:
        declared = get(str(ctx.get("power", "")))
        return declared is not None and Keyword.WEAPON in declared.keywords

    if c.build("great-weapon") or c.build("guardian"):
        two_handed = c.build("great-weapon")

        def grip(ctx: dict[str, Any]) -> bool:
            gear = world.get(me, Gear)
            held = gear.main if gear is not None else None
            return (
                with_a_weapon(ctx) and held is not None and held.two_handed == two_handed
            )

        c.bonus("attack", 1, until=When.ENCOUNTER, on=me, kind="untyped", when=grip)
        return

    if c.build("battlerager"):
        # "Plus any temporary hit points normally granted by the power" is
        # the power's own line and lands on its own; this is the rest of
        # the sentence. The damage half of the same talent is not written:
        # it wants light armour or chainmail and the chassis wears scale,
        # so a gate on it would be false for every fighter in the tree.
        def on_hit(ev: Hit) -> None:
            if ev.attacker != me:
                return
            dealt = get(ev.power)
            if dealt is not None and dealt.reach.kind in _MELEE_OR_CLOSE:
                c.temp_hp(c.con_mod, on=me)

        c.watch(Hit, on_hit, until=When.ENCOUNTER, on=me, label="cf:fighter-weaponmaster-f3")


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
    c.bonus("damage", c.str_mod, until=When.SONT, on=c.me, kind="untyped")
