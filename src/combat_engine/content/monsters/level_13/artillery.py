"""Monster abilities, level 13: the artillery, and then the minions.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=AC,
printed=18)` and `Damage("3d8", 8)` -- and the engine takes the level back
out of the attack and rescales the damage. A minion's flat number says so
with `kind=MINION`, and its single hit point is in the database like every
other number.

The conventions of the twelve levels below are kept: a **trait** is a row
that costs no action, has no target, and arms the watches that hold it for
the rest of the fight; a stat block printing no range at all means melee 1;
a printed "Range 10/20" is a normal range and a long one and the normal one
is what `Range` holds; a printed Requirement naming a weapon the engine has
no name for is left unwritten rather than gated on something nothing can
answer; and a helper written for an earlier level is imported rather than
copied.

Six things this file had to settle.

**Partial concealment is a number.** There is no concealment state --
`cover_between` measures two positions and nothing else -- and m333a0 grants
itself concealment against anything more than 3 squares off. A -2 to the
attacker's roll and a +2 to the defender's number are the same arithmetic,
and the defence context carries `attacker`, so the four modifiers sit on the
m333 and read the range from there. That is the whole of partial
concealment as the rules define it.

**"At least one of which must be a fire ray."** m195a2 fires up to two rays
at two different creatures with a constraint across the pair, which no
`Target` can express -- the body is called once per target and the two calls
cannot see each other. So the row is declared with no target and picks both
itself, the way every other row of that shape in the tree does.

**A breath weapon that prints no range.** m44a3 gives an attack bonus, a
damage line, a miss line and no range at all, so it takes the convention
every other rangeless row in this tree takes and is melee 1. Inventing a
blast for it would be inventing a printed line; `no_provoke` is declared,
because that sentence *is* printed.

**A recharge sentence naming another card's row.** m44a4 spells the m44's
own breath as `m43a4`, which belongs to a level-11 stat block. The row every
sentence plainly means is the one printed above it on this card, which is
how the level-11 dragons read the same slip.

**"Cannot use daily or encounter attack powers" is `c.forbid`, once per
row.** There is no switch for a whole usage class, so the victim's rows are
walked and each one that prints an attack and is not at-will is taken away
-- and every one of those holds is ended by the *one* save-ends hold that
also carries the burn, because the card prints one saving throw.

**Two printed damage types, one `Damage`.** Nothing here prints one, but
m161a3's miss line prints a weaker burn of a type its hit line also lays:
different targets, so they never meet, and where they would the
highest-only rule `c.ongoing` enforces is the answer.

Artillery first, then the minions, each group in ref order.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_07.brutes import _aura
from combat_engine.content.monsters.level_11.lurkers import (
    _breathe_again,
    _extra_against_the_unready,
    _frightful,
)
from combat_engine.content.monsters.level_13.soldiers import _burn_and_hold
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_CREATURE,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    FREE,
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
    AreaBurst,
    Attack,
    Bloodied,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    Damage,
    DamageApplied,
    DamageType,
    Dropped,
    Effect,
    Hit,
    Keyword,
    Melee,
    Ranged,
    Usage,
    When,
    World,
    ZoneEntered,
    power,
    use,
)
from combat_engine.engine.events import ZoneExited
from combat_engine.engine.monster_math import LIMITED, MINION
from combat_engine.engine.query import alive, distance_between, team
from combat_engine.engine.triggers import Trigger, about_me
from combat_engine.engine.zones import Zone

#: The four defences, for a printed bonus or penalty to all of them.
EVERY_DEFENCE = (AC, FORT, REF, WILL)


# ==========================================================================
# m161
# ==========================================================================


@power(
    "m161a0",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m161a0(c: Cast) -> None:
    """It marks a victim out and the spiders pile on.

    "Any spiders within sight" is asked of the creature's own type words,
    which is what `c.is_kind` reads -- and of sight rather than distance,
    because the printed line measures what the m161 can see. The m161 is not
    itself of that kind, so it never picks up its own bonus.

    The bonus is against *that enemy*, which is the attack context's
    `target`, rather than a flat +2 to everything -- a much heavier card
    than the one printed. Two of the same kind do not add, so a second hit
    on the same creature renews rather than doubles.
    """
    me, ref = c.me, c.ref

    def landed(ev: Hit) -> None:
        if ev.attacker != me or team(c.world, ev.target) is team(c.world, me):
            return
        victim = ev.target

        def at_that_one(ctx: dict[str, Any]) -> bool:
            return ctx.get("target") == victim

        for friend in sorted(c.within(20, side="ally")):
            if not c.is_kind("spider", on=friend) or not c.can_see(friend):
                continue
            c.bonus(
                "attack", 2, until=When.EONT, on=friend, kind="power",
                when=at_that_one,
            )

    c.watch(Hit, landed, until=When.ENCOUNTER, on=me, label=ref)


@power(
    "m161a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d6", 5),
)
def m161a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized(until=When.SAVE_ENDS)


@power(
    "m161a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.RANGED],
    attack=Attack(vs=REF, printed=18),
    damage=Damage("2d6", 4, dtype=DamageType.POISON),
)
def m161a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(10, DamageType.POISON)


@power(
    "m161a3",
    level=13,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=18),
    damage=Damage(
        "2d10", 5, dtype=DamageType.NECROTIC, kind=LIMITED, half_on_miss=True
    ),
)
def m161a3(c: Cast) -> None:
    """The hit's "save ends both" is one hold; the miss leaves a lighter burn
    on its own clock, which is what the card prints."""
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.hit()
        _burn_and_hold(
            c, victim, 10, DamageType.NECROTIC, conditions=(Condition.WEAKENED,)
        )
    else:
        c.hit(half=True)
        c.ongoing(5, DamageType.NECROTIC, on=victim)


@power(
    "m161a4",
    level=13,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=16),
    damage=Damage("3d6", 10, dtype=DamageType.POISON, kind=LIMITED, half_on_miss=True),
)
def m161a4(c: Cast) -> None:
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)


@power(
    "m161a5",
    level=13,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(1),
    target=NO_TARGET,
    keywords=[Keyword.ZONE],
)
def m161a5(c: Cast) -> None:
    """A cloud nobody can see through and nobody inside can see at all.

    `blocks_sight` is what `cover_between` reads and it applies to
    everybody; there is no way to exempt one creature from it, so the m161's
    own sight through its own cloud is noted rather than invented.

    The blinding is held per occupant and diffed by the two events that say
    who is standing in it, because a zone's own fields make squares rough or
    dark and carry no conditions. Ending the zone emits a `ZoneExited` for
    everybody inside, which is what takes the holds off.
    """
    me = c.me
    area = c.area()
    if not area:
        return
    fog = c.zone(area, label=c.ref, until=When.EONT, blocks_sight=True)
    held: dict[int, Effect] = {}

    def swallow(who: int) -> None:
        if who == me or who in held:
            return
        blinded = c.blinded(until=When.ENCOUNTER, on=who)
        if blinded is not None:
            held[who] = blinded

    def entered(ev: ZoneEntered) -> None:
        if ev.zone == fog:
            swallow(ev.actor)

    def left(ev: ZoneExited) -> None:
        blinded = held.pop(ev.actor, None) if ev.zone == fog else None
        if blinded is not None:
            c.world.effects.end(blinded, "out of the cloud")

    watches = (
        c.watch(ZoneEntered, entered, until=When.ENCOUNTER, on=me, label=f"{c.ref} in"),
        c.watch(ZoneExited, left, until=When.ENCOUNTER, on=me, label=f"{c.ref} out"),
    )
    zone = c.world.get(fog, Zone)
    if zone is not None and zone.effect is not None:
        for watch in watches:
            zone.effect.on_end.append(
                lambda w=watch: c.world.effects.end(w, "the cloud is gone")
            )
    for actor in c.world.zones.occupants(fog):
        swallow(actor)
    c.note("m161a5: the m161 sees through its own cloud")


# ==========================================================================
# m195
# ==========================================================================
#
# Elite, and it prints no row that acts twice, so it takes no second
# initiative count: an elite is two creatures' worth of hit points and
# experience before it is anything else.


def _ray(c: Cast, victim: int, vs: Any) -> bool:
    """One of m195a2's three rays, rolled at the printed +17.

    A second attack line cannot live in the header, so its printed bonus is
    trimmed by hand the way `Attack.bonus_for` trims the header's.
    """
    return bool(c.attack(c.world.scaling.trim(17, c.level), vs, on=victim))


@power(
    "m195a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d6"),
)
def m195a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means."""
    if c.strike():
        c.hit()


@power(
    "m195a1",
    level=13,
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(8),
    target=ONE_CREATURE,
)
def m195a1(c: Cast) -> None:
    """It picks a creature out and fire sticks to it.

    No attack roll and no damage: the weakness is the whole of the row.

    "Save ends both" is one saving throw, so the watch is hung on the
    vulnerability's own hold rather than given a clock of its own -- the
    victim rolls once and both halves go together.
    """
    me, ref, victim = c.me, c.ref, c.target
    if victim is None:
        return
    weakness = c.vulnerable(10, DamageType.FIRE, on=victim, until=When.SAVE_ENDS)
    if weakness is None:
        return

    def sticks(ev: DamageApplied) -> None:
        if ev.target == victim and ev.amount > 0 and ev.dtype is DamageType.FIRE:
            c.ongoing(5, DamageType.FIRE, on=victim)

    rider = c.watch(
        DamageApplied, sticks, until=When.ENCOUNTER, on=me, label=f"{ref} clinging"
    )
    weakness.on_end.append(lambda: c.world.effects.end(rider, "the oil burns off"))


@power(
    "m195a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(8),
    target=NO_TARGET,
    no_provoke=True,
)
def m195a2(c: Cast) -> None:
    """Up to two rays, at two different creatures, one of them fire.

    Declared with no target: the constraint runs *across* the pair -- "at
    least one of which must be a fire ray", "each power must target a
    different creature" -- and the body is called once per target, so the
    two calls could never see each other. The row picks both itself.

    The first is the fire ray, which is the one the printed line insists on;
    the second is optional, which is what "up to two" means, and may be any
    of the three.
    """
    foes = sorted(
        foe for foe in c.enemies() if c.distance(foe) <= 8 and alive(c.world, foe)
    )
    if not foes:
        return
    first = c.choose(foes, "m195a2: who the fire ray burns")
    if first is None:
        return
    if _ray(c, first, REF):
        c.damage("2d8", 6, dtype=DamageType.FIRE, on=first)
    rest = [foe for foe in foes if foe != first and alive(c.world, foe)]
    if not rest:
        return
    second = c.choose(rest, "m195a2: who the second ray takes", optional=True)
    if second is None:
        return
    picked = c.choose(["fire", "telekinesis", "fear"], "m195a2: which second ray")
    if picked == "telekinesis":
        if _ray(c, second, FORT):
            c.slide(4, on=second)
    elif picked == "fear":
        if _ray(c, second, WILL):
            c.flee(c.speed_of(second), on=second)
            c.penalty("attack", 2, on=second, until=When.SAVE_ENDS)
    elif _ray(c, second, REF):
        c.damage("2d8", 6, dtype=DamageType.FIRE, on=second)


_M195_BLED = "the m195 is first bloodied"
_M195_FELLED = "the m195 drops to 0 hit points"


@power(
    "m195a3",
    level=13,
    usage=AT_WILL,
    uses=2,
    action=FREE,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=17),
    damage=Damage("2d8", 6, dtype=DamageType.FIRE),
    trigger=f"{_M195_BLED} and again when {_M195_FELLED}",
    on=(
        Trigger(Bloodied, when=about_me, text=_M195_BLED),
        Trigger(Dropped, when=about_me, text=_M195_FELLED),
    ),
)
def m195a3(c: Cast) -> None:
    """It goes off twice: once when the shell cracks and once when it dies.

    Two declared triggers rather than one predicate reading both, because
    they are two printed moments and the card should show both. "First
    bloodied" needs no guard -- `Bloodied` is emitted on the crossing and
    nowhere else -- and a creature may answer its own downfall, which the
    dispatcher makes the exception for.
    """
    if c.strike():
        c.hit()


# ==========================================================================
# m225
# ==========================================================================


@power(
    "m225a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("3d8", 5, dtype=DamageType.PSYCHIC),
)
def m225a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m225a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=18),
    damage=Damage("3d8", 8, dtype=DamageType.PSYCHIC),
)
def m225a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m225a2",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(1, 20),
    target=EACH_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=18),
    damage=Damage("2d8", 8, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m225a2(c: Cast) -> None:
    """The burn and the silence are one printed sentence and one saving
    throw.

    There is no switch for "daily or encounter attack powers", so the
    victim's rows are walked and each one that prints an attack line and is
    not at-will is taken away by name. Every one of those holds is ended
    when the burn's hold ends, which is what keeps the two halves on one
    save.
    """
    from combat_engine.engine import Powers
    from combat_engine.engine.dsl import get

    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    hold = _burn_and_hold(c, victim, 10, DamageType.PSYCHIC)
    known = c.world.get(victim, Powers)
    if known is None:
        return
    barred = []
    for ref in known.all:
        p = get(ref)
        if p is None or p.usage is Usage.AT_WILL or p.attack is None:
            continue
        taken = c.forbid(ref, on=victim, until=When.ENCOUNTER)
        if taken is not None:
            barred.append(taken)

    def give_back() -> None:
        for eff in barred:
            if not eff.ended:
                c.world.effects.end(eff, "the silence lifts")

    hold.on_end.append(give_back)


@power(
    "m225a3",
    level=13,
    usage=ENCOUNTER,
    action=MOVE,
    reach=CloseBurst(10),
    target=NO_TARGET,
)
def m225a3(c: Cast) -> None:
    """Either it goes up, or it sends somebody else up.

    The fly speed is lent for the length of the move and taken back:
    `movement.mode_of` puts anything with the mode in the air the moment it
    moves, and a lent speed left behind would keep it there.

    Declared with no target because the two halves aim at different
    creatures, and which one happens is the m225's choice.
    """
    me = c.me
    mates = sorted(
        friend
        for friend in c.within(10, side="ally")
        if friend != me and alive(c.world, friend)
    )
    flier = me
    if mates and not c.may("fly itself", who=me):
        flier = c.choose(mates, "m225a3: which ally it lifts") or me
    lent = c.mode("fly", 5, until=When.EOT, on=flier)
    try:
        c.move(5, who=flier)
    finally:
        if lent is not None:
            c.world.effects.end(lent, "it comes down")


# ==========================================================================
# m333
# ==========================================================================


@power(
    "m333a0",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m333a0(c: Cast) -> None:
    """Hard to make out from any distance.

    There is no concealment state in the engine: `cover_between` measures
    two positions and nothing else, and `ignore_cover` is an argument to one
    roll. Partial concealment *is* a -2 to the attacker's roll, and a +2 to
    the defence is the same arithmetic from the other side -- so the four
    modifiers sit on the m333 and read the attacker out of the defence
    context, which carries it.

    Four separate modifiers, because the engine holds each defence
    separately and one named "all defenses" would be a bonus to nothing.
    """
    me = c.me

    def far_off(ctx: dict[str, Any]) -> bool:
        shooter = ctx.get("attacker")
        return shooter is not None and distance_between(c.world, me, shooter) > 3

    for defended in EVERY_DEFENCE:
        c.bonus(defended, 2, until=When.ENCOUNTER, on=me, kind="untyped", when=far_off)


@power(
    "m333a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("3d8", 4),
)
def m333a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m333a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.RANGED, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=20),
    damage=Damage("3d10", 6),
)
def m333a2(c: Cast) -> None:
    """The secondary is a second attack line against the same creature, and a
    second line's printed bonus is trimmed by hand the way
    `Attack.bonus_for` trims the header's."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    if c.attack(c.world.scaling.trim(18, c.level), FORT, on=victim):
        _burn_and_hold(
            c, victim, 5, DamageType.POISON, conditions=(Condition.DAZED,)
        )


# ==========================================================================
# m44
# ==========================================================================
#
# Solo, and it prints no row that acts twice, so it takes no second
# initiative count: splicing one in would be inventing a printed line.


@power(
    "m44a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d8", 6),
)
def m44a0(c: Cast) -> None:
    """The die of lightning is a second packet: the header holds one damage
    type and the blow itself is printed untyped."""
    if not c.strike():
        return
    c.hit()
    c.damage("1d6", dtype=DamageType.LIGHTNING)
    c.push(1)
    c.prone()


@power(
    "m44a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d6", 6),
)
def m44a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m44a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
)
def m44a2(c: Cast) -> None:
    """The lines it repeats are the rows that print them rather than copies,
    so the damage stays in one place."""
    for ref in ("m44a0", "m44a1", "m44a1"):
        use(c.world, c.me, ref, targets=[c.target], spend=False)


@power(
    "m44a3",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    no_provoke=True,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=18),
    damage=Damage(
        "2d12", 10, dtype=DamageType.LIGHTNING, kind=LIMITED, half_on_miss=True
    ),
)
def m44a3(c: Cast) -> None:
    """The card prints an attack bonus, a damage line, a miss line and no
    range at all, so it takes the convention every other rangeless row in
    this tree takes and is melee 1. `no_provoke` is declared because that
    sentence is printed; guessing a blast for it would not be."""
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)


_M44_BLED = "the m44 is first bloodied"


@power(
    "m44a4",
    level=13,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    no_provoke=True,
    keywords=[Keyword.LIGHTNING],
    trigger=_M44_BLED,
    on=Trigger(Bloodied, when=about_me, text=_M44_BLED),
)
def m44a4(c: Cast) -> None:
    """The card spells the breath as another stat block's id; the row every
    sentence plainly means is the one printed above it on this card."""
    _breathe_again(c, "m44a3")


@power(
    "m44a5",
    level=13,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=18),
)
def m44a5(c: Cast) -> None:
    """No damage at all: the stun is the whole of the hit, and the
    Aftereffect begins when it ends, whichever way it ended."""
    _frightful(c)


@power(
    "m44a6",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(3, 20),
    target=EACH_CREATURE,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=18),
    damage=Damage("2d6", 4, dtype=DamageType.LIGHTNING, half_on_miss=True),
)
def m44a6(c: Cast) -> None:
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)


# ==========================================================================
# m4817
# ==========================================================================


@power(
    "m4817a0",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4817a0(c: Cast) -> None:
    """Filed as a trait, and one. The printed line names no range kind, so
    every attack carries it, and whether the blow had the opening is read
    off the `Hit` -- a one-shot grant has already been spent by the time a
    second asking could be made."""
    _extra_against_the_unready(c, "2d6")


@power(
    "m4817a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("3d4", 9),
)
def m4817a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4817a2",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=20),
    damage=Damage("2d8", 7, kind=LIMITED),
)
def m4817a2(c: Cast) -> None:
    """The printed Requirement names the weapon m4817a3 is fired with, and a
    monster's gear is not modelled by name -- it is the same thing this row
    sweeps with, so the row is left usable rather than gated on something
    nothing can answer.

    A blast is not centred on the creature firing it, so `EACH_CREATURE`
    does not catch the m4817 in its own line of fire.
    """
    if c.strike():
        c.hit()
        c.push(1)


@power(
    "m4817a3",
    level=13,
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=20),
    damage=Damage("1d8", 5),
)
def m4817a3(c: Cast) -> None:
    """10/20 is a normal range and a long one, and `Range` holds one
    number."""
    if c.strike():
        c.hit()


def _its_own_turn(world: World, eid: int) -> bool:
    return world.turn == eid


@power(
    "m4817a4",
    level=13,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    requires=_its_own_turn,
    requires_text="the m4817 can use this only during its turn",
)
def m4817a4(c: Cast) -> None:
    """It throws itself forward and rolls for how well that goes.

    A free action with no printed Trigger is a thing a creature takes on its
    own turn, which is what `actions.legal` offers and what the Requirement
    says outright.

    The die is rolled now and held as a power bonus, because that is what
    "add the result as a power bonus to its attack rolls" is; and the
    opening it gives away is to everybody, which is `to="allies"` read from
    the other side -- there is no argument for "everyone", so the enemies
    who will actually swing at it are named by the relation one at a time.
    """
    me = c.me
    rolled = c.roll("1d6")
    c.bonus("attack", rolled, until=When.EONT, on=me, kind="power")
    c.grants_advantage(until=When.EONT, on=me, to="allies")
    for foe in sorted(c.enemies()):
        c.grants_advantage(until=When.EONT, on=me, to=foe)
    c.note(f"m4817a4: it swings at +{rolled} and leaves itself open")


# ==========================================================================
# The minions. A minion deals its printed number on a hit and its single hit
# point is in the database; `kind=MINION` is what says the number is flat
# because the creature is one, which is how it rescales.
# ==========================================================================


# --------------------------------------------------------------------------
# m1751
# --------------------------------------------------------------------------


@power(
    "m1751a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage(bonus=6, kind=MINION),
)
def m1751a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means."""
    if c.strike():
        c.hit()
        c.immobilized(until=When.SAVE_ENDS)


# --------------------------------------------------------------------------
# m2933
# --------------------------------------------------------------------------


@power(
    "m2933a0",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2933a0(c: Cast) -> None:
    """Four penalties per occupant, because "all defenses" is four numbers
    and the engine holds each separately -- one modifier named "all
    defenses" would be a penalty to nothing.

    The aura helper is the right one: the holds are carried for exactly as
    long as their owner stands inside.
    """
    me = c.me

    def eligible(who: int) -> bool:
        return who != me and who in c.enemies()

    def hold(who: int) -> Effect | None:
        taken = [
            c.penalty(defended, 2, on=who, until=When.ENCOUNTER, kind="untyped")
            for defended in EVERY_DEFENCE
        ]
        first = next((eff for eff in taken if eff is not None), None)
        for other in taken:
            if other is not None and other is not first and first is not None:
                first.on_end.append(
                    lambda o=other: c.world.effects.end(o, "out of the cloud")
                )
        return first

    _aura(c, 1, eligible, hold)


@power(
    "m2933a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=16),
    damage=Damage(bonus=10, kind=MINION),
)
def m2933a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2933a2",
    level=13,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m2933a2(c: Cast) -> None:
    """The printed Effect spells the creature's id as one belonging to a
    different stat block. This creature is the one it plainly means."""
    c.shift(4)
