"""Monster abilities, level 9: the controllers.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=WILL,
printed=12)` and `Damage("2d8", 4)` -- and the engine takes the level back
out of the attack and rescales the damage if a fight is being played on
another edition's maths.

A **blast or burst whose target line reads "creatures in the blast"** is
`EACH_CREATURE`; one that prints "enemies" is `EACH_ENEMY`. Both spellings
appear here and they are not the same row.

Six readings this file had to settle.

**Two rows print no range at all** -- the line is "+12 vs AC" and nothing
else. A weapon attack against AC is read as melee 1, which is what a stat
block giving no range means.

**"The target cannot attack the m323"** is `c.cannot_attack(against=...)`,
which refuses at the declaration so nothing is rolled and no rider fires.
Its three printed ways out -- somebody on the m323's side attacks the
victim, the m323 drops, the row is used again -- are none of them durations,
so they are watches hung on that hold's own subscriptions and go when it
goes.

**A row that redirects an attack** has to answer `AttackDeclared`: `vs` and
`target` are both read back off the event now, so an interrupt can move the
blow, and after the roll there is a result that would have to be thrown out.

**"Cannot regain hit points" inside a zone** is `Healed`, which is a
`Decision` and negotiable in `Window.BEFORE`. The listener hangs on the
zone's own effect rather than on `c.watch`, because `until=When.SUSTAIN` on
a watch makes a hold nobody can sustain -- only `c.zone`, `c.aura`,
`c.hazard` and `c.conjure` pass a cost -- and the zone's effect is what
already carries the encounter.

**"Each Failed Saving Throw"** is `Effect.escalate`, which runs on a failed
save; an Aftereffect is `on_end`, and the two are a turn apart. The burn and
the escalation are one effect, because the card prints one saving throw.

**A link that pays out when its maker is hurt** lives on the creature it was
forged with, on the m4940's own clock, and the watch that hurts the far end
hangs on it -- so using the row again or letting the turn come round takes
the payout away with the link.

Each stat block in ref order.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    FREE,
    INTERRUPT,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
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
    DamageType,
    Effect,
    Healed,
    Keyword,
    Melee,
    Powers,
    Ranged,
    UpTo,
    Usage,
    When,
    Window,
    World,
    get,
    power,
    use,
)
from combat_engine.engine.events import (
    AttackDeclared,
    DamageApplied,
    Dropped,
    Hit,
    Miss,
)
from combat_engine.engine.monster_math import LIMITED, MINION
from combat_engine.engine.query import adjacent, alive, creatures
from combat_engine.engine.triggers import Trigger, about_me, by_melee

#: The reaches a printed "a melee or a ranged attack" covers. A burst is
#: neither, which is the distinction the m323's interrupt turns on.
AIMED_KINDS = ("melee", "ranged")


def _bearing(world: World, source: int, label: str) -> list[int]:
    """Everybody carrying a live effect this creature laid under that label."""
    return sorted(
        eff.owner
        for eff in world.effects.live.values()
        if eff.source == source and eff.label == label and not eff.ended
    )


def _drop(c: Cast, label: str, why: str) -> None:
    """End every live effect this creature is holding up under that label."""
    for eff in list(c.world.effects.live.values()):
        if eff.source == c.me and eff.label == label and not eff.ended:
            c.world.effects.end(eff, why)


# ==========================================================================
# m2899
# ==========================================================================


@power(
    "m2899a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d8", 4),
)
def m2899a0(c: Cast) -> None:
    """Two expressions on one line and the header holds one, so the untyped
    half stays in the header and the fire is rolled here."""
    if c.strike():
        c.hit()
        c.damage("2d6", dtype=DamageType.FIRE)


@power(
    "m2899a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d6", 4),
)
def m2899a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2899a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=UpTo(2),
)
def m2899a2(c: Cast) -> None:
    """The printed Effect does not say whether the two land on one creature
    or two, so the header takes up to two and a single target is clawed
    twice. That is the only reading that loses nothing."""
    who = c.target
    if who is None:
        return
    for _ in range(2 if c.first and c.last else 1):
        if not alive(c.world, who):
            return
        use(c.world, c.me, "m2899a1", targets=[who], spend=False)


_M2899_STRUCK = "the m2899 is hit by a creature adjacent to it"


def _hit_from_beside(world: World, me: int, ev: Hit) -> bool:
    return ev.target == me and adjacent(world, me, ev.attacker)


@power(
    "m2899a3",
    level=9,
    usage=AT_WILL,
    action=REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=FORT, printed=13),
    trigger=_M2899_STRUCK,
    on=Trigger(Hit, when=_hit_from_beside, text=_M2899_STRUCK),
)
def m2899a3(c: Cast) -> None:
    """Declared with no target and aimed off the trigger: the dispatcher only
    points a row that takes one enemy, and this one is about whoever just
    landed a blow rather than about whoever is nearest.

    No damage line at all -- the shove and the burn are the whole of the hit.
    """
    who = getattr(c.trigger, "attacker", None)
    if who is None or not c.strike(on=who):
        return
    c.push(5, on=who)
    c.ongoing(5, DamageType.FIRE, on=who)


@power(
    "m2899a4",
    level=9,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("2d6", 5, dtype=DamageType.FIRE, kind=LIMITED, half_on_miss=True),
)
def m2899a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.weakened(until=When.SAVE_ENDS)
    else:
        c.hit(half=True)


_M2899_BLED = "the m2899 is first bloodied"


@power(
    "m2899a5",
    level=9,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
    trigger=_M2899_BLED,
    on=Trigger(Bloodied, when=about_me, text=_M2899_BLED),
)
def m2899a5(c: Cast) -> None:
    """"First bloodied" needs no guard: `Bloodied` is emitted on the crossing
    and nowhere else. The spec names the recharging row by an id belonging to
    another stat block; the row it plainly means is this one's own breath."""
    known = c.world.get(c.me, Powers)
    if known is not None:
        known.restore("m2899a4")
    use(c.world, c.me, "m2899a4")


@power(
    "m2899a6",
    level=9,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=11),
)
def m2899a6(c: Cast) -> None:
    """An aftereffect follows the first hold ending, whichever way it ended,
    so it hangs off that hold rather than on `escalate` -- which runs on a
    failed save and would never run at all for a hold on a turn clock."""
    if not c.strike():
        return
    victim = c.target
    hold = c.stunned(until=When.EONT, on=victim)
    if hold is not None:
        hold.on_end.append(
            lambda: c.penalty("attack", 2, until=When.SAVE_ENDS, on=victim)
        )


# ==========================================================================
# m323
# ==========================================================================


#: The hold m323a1 lays. `c.cannot_attack` labels its watch this way, and
#: two other rows have to find it: the interrupt that hides behind whoever
#: is carrying it, and the row itself, which replaces it.
_M323_KISS = "m323a1 cannot attack"


@power(
    "m323a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("3d6", 6),
)
def m323a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m323a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=12),
)
def m323a1(c: Cast) -> None:
    """No damage at all: being unable to raise a hand is the whole of the hit.

    None of the three printed ways out is a duration, so the hold runs to the
    end of the encounter and the three are watches hung on its own
    subscriptions -- they are torn down with it, which is what stops the
    second victim's charm from being broken by the first one's.

    "Uses this power again" is answered before the attack is rolled: the old
    charm lapses whether or not the new one lands, which is what the printed
    sentence says.

    The last printed clause -- what happens to it after the fight, and the
    kiss that renews it -- is out of combat entirely and is noted.
    """
    me = c.me
    _drop(c, _M323_KISS, "it kissed somebody else")
    if not c.strike():
        return
    victim = c.target
    hold = c.cannot_attack(on=victim, against=me, until=When.ENCOUNTER)
    if hold is None:
        return
    mine = {me, *c.allies()}

    def broken(ev: AttackDeclared) -> None:
        if ev.target == victim and ev.attacker in mine and not hold.ended:
            c.world.effects.end(hold, "its side struck the charmed creature")

    def fallen(ev: Dropped) -> None:
        if ev.actor == me and not hold.ended:
            c.world.effects.end(hold, "the m323 went down")

    hold.subs.append(c.world.bus.on(AttackDeclared, broken, owner=me))
    hold.subs.append(c.world.bus.on(Dropped, fallen, owner=me))
    c.note("m323a1: after the encounter the charm lasts while the kiss is renewed")


@power(
    "m323a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=12),
)
def m323a2(c: Cast) -> None:
    if c.strike():
        c.condition(Condition.DOMINATED, until=When.EONT)


@power(
    "m323a3",
    level=9,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
    out_of_combat=True,
)
def m323a3(c: Cast) -> None:
    """A disguise and nothing else: the shape carries no statistics, gates no
    other row, and the way through it is an Insight check, which the engine
    has no skills to roll. Deliberately inert rather than given an invented
    mechanic."""
    c.note("m323a3: appears as a Medium humanoid until it changes back")


_M323_AIMED = "a melee or ranged attack targets the m323 beside a creature it has charmed"


def _beside_its_charm(world: World, me: int, ev: AttackDeclared) -> bool:
    """Aimed at me, by a blow the printed line names, with a shield to hand.

    `AttackDeclared` rather than `Hit`: the redirect has to happen before the
    die is down, because after it there is a result that would have to be
    thrown out and rolled again against a different creature's defence.
    """
    if ev.target != me:
        return False
    p = get(ev.power)
    if p is None or p.reach.kind not in AIMED_KINDS:
        return False
    return any(adjacent(world, me, v) for v in _bearing(world, me, _M323_KISS))


@power(
    "m323a4",
    level=9,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.CHARM],
    trigger=_M323_AIMED,
    on=Trigger(AttackDeclared, when=_beside_its_charm, text=_M323_AIMED),
)
def m323a4(c: Cast) -> None:
    """The charmed creature takes the blow. Which one, when it has charmed
    more than one, is a choice the card does not make for it."""
    shields = [v for v in _bearing(c.world, c.me, _M323_KISS) if c.adjacent(v)]
    if not shields:
        return
    chosen = shields[0] if len(shields) == 1 else c.choose(shields, "m323a4: who takes it")
    if chosen is not None:
        c.redirect(to=chosen)


# ==========================================================================
# m4911
# ==========================================================================


@power(
    "m4911a0",
    level=9,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4911a0(c: Cast) -> None:
    """Adjacency is asked when the blow misses rather than when the trait
    arms: this creature is pushed about constantly and does not stay where it
    was standing."""
    me = c.me

    def backlash(ev: Miss) -> None:
        if ev.target != me or not by_melee(c.world, me, ev):
            return
        if adjacent(c.world, me, ev.attacker):
            c.flat(6, on=ev.attacker)

    c.watch(Miss, backlash, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m4911a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage(bonus=6, kind=MINION),
)
def m4911a1(c: Cast) -> None:
    """A minion's fixed damage. The step is printed on the hit, so a miss
    buys nothing."""
    if c.strike():
        c.hit()
        c.slide(1)


@power(
    "m4911a2",
    level=9,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=12),
    damage=Damage(bonus=4, dtype=DamageType.PSYCHIC, kind=MINION),
)
def m4911a2(c: Cast) -> None:
    """"Grants combat advantage" with nobody named is to everybody, and the
    clock is the victim's own next turn rather than the m4911's."""
    if c.strike():
        c.hit()
        c.grants_advantage(until=When.EOTNT, to="allies")


# ==========================================================================
# m4940
# ==========================================================================


#: The link m4940a4 forges. Two attack rows print "one creature affected by
#: this m4940's m4940a4" as their target line, which no `Target` can say, so
#: they read this instead.
_M4940_LINK = "m4940a4 link"


def _linked(c: Cast) -> list[int]:
    return _bearing(c.world, c.me, _M4940_LINK)


def _has_a_link(world: World, eid: int) -> bool:
    return bool(_bearing(world, eid, _M4940_LINK))


@power(
    "m4940a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d6", 7),
)
def m4940a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4940a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=12),
    damage=Damage("1d6", 4, dtype=DamageType.PSYCHIC),
    requires=_has_a_link,
    requires_text="the m4940 must have a creature linked",
)
def m4940a1(c: Cast) -> None:
    """The printed target is the linked creature, so the aim is narrowed here:
    the creature the dispatcher chose is usually not the one on the other end
    of the thread."""
    held = _linked(c)
    victim = c.target if c.target in held else next(iter(held), None)
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)
    c.dazed(until=When.SAVE_ENDS, on=victim)


@power(
    "m4940a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.DISEASE, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=12),
    damage=Damage("1d6", 4, dtype=DamageType.PSYCHIC),
    requires=_has_a_link,
    requires_text="the m4940 must have a creature linked",
)
def m4940a2(c: Cast) -> None:
    """The victim's swing is its own basic attack, at a creature the m4940
    picks -- which is `c.grant_attack`, the only thing that rolls for
    somebody other than the caster.

    The disease is a track that runs between fights and the engine holds no
    such thing, so it is noted rather than invented.
    """
    held = _linked(c)
    victim = c.target if c.target in held else next(iter(held), None)
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)
    prey = c.choose(
        sorted(who for who in creatures(c.world) if who != victim and alive(c.world, who)),
        "m4940a2: who it is made to attack",
    )
    if prey is not None:
        c.grant_attack(victim, on=prey)
    c.note("m4940a2: the target is exposed to the m4940's corruption")


@power(
    "m4940a3",
    level=9,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m4940a3(c: Cast) -> None:
    c.teleport(8)


@power(
    "m4940a4",
    level=9,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
)
def m4940a4(c: Cast) -> None:
    """The link is on the m4940's own clock -- "until the start of its next
    turn" -- and the payout hangs on the link's own subscriptions, so letting
    the turn come round or forging another takes the payout with it.

    No attack roll: the thread is simply spun.
    """
    me, victim = c.me, c.target
    if victim is None:
        return
    _drop(c, _M4940_LINK, "it forged another link")
    thread = c.world.effects.apply(victim, me, When.SONT, label=_M4940_LINK)

    def feedback(ev: DamageApplied) -> None:
        if ev.target != me or ev.amount <= 0 or thread.ended:
            return
        c.damage("1d10", 5, dtype=DamageType.PSYCHIC, on=victim)

    thread.subs.append(c.world.bus.on(DamageApplied, feedback, owner=me))


# ==========================================================================
# m5048
# ==========================================================================


@power(
    "m5048a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.WEAPON],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("2d6", 10, dtype=DamageType.NECROTIC),
)
def m5048a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(2)


@power(
    "m5048a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.NECROTIC],
    attack=Attack(vs=WILL, printed=13),
    damage=Damage("2d8", 4, dtype=DamageType.NECROTIC),
)
def m5048a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized(until=When.SAVE_ENDS)


@power(
    "m5048a2",
    level=9,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.FIRE],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("2d10", 10, dtype=DamageType.FIRE, kind=LIMITED),
)
def m5048a2(c: Cast) -> None:
    """The burn and what a failed save costs its neighbours are one effect:
    `escalate` runs on a failed save, which is the printed "Each Failed
    Saving Throw", where `on_end` is an aftereffect and a turn away.

    "Each ally within 3 squares of the target" is the *target's* side, which
    from here is the enemy pool -- and the victim itself is not its own ally.
    """
    if not c.strike():
        return
    c.hit()
    victim = c.target

    def splash(_eff: Effect) -> None:
        for friend in c.within(3, of=victim, side="enemy"):
            if friend != victim:
                c.flat(5, dtype=DamageType.FIRE, on=friend)

    c.condition(
        until=When.SAVE_ENDS,
        on=victim,
        ongoing=(5, DamageType.FIRE),
        escalate=splash,
    )


def _no_mending(c: Cast) -> None:
    """The zone m5048a3 leaves behind.

    `Healed` is announced before the hit points go on and is a `Decision`, so
    refusing it in `Window.BEFORE` is the seam "cannot regain hit points"
    wants -- as against clawing the surplus back afterwards, which comes to
    the right total and puts the wrong number in the log.

    The listener hangs on the zone's own effect rather than on `c.watch`:
    that is what carries it to the end of the encounter and takes it away
    when the zone goes.
    """
    ring = c.zone(c.area(), until=When.ENCOUNTER, label=c.ref)
    held = dict(c.world.zones.all()).get(ring)
    if held is None or held.effect is None:
        return
    me = c.me

    def stanch(ev: Healed) -> None:
        if ev.target in c.world.zones.occupants(ring) and ev.target in c.enemies():
            ev.cancel("the zone allows no healing")

    held.effect.subs.append(
        c.world.bus.on(Healed, stanch, window=Window.BEFORE, owner=me)
    )


@power(
    "m5048a3",
    level=9,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(3, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC, Keyword.ZONE],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("2d6", 5, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m5048a3(c: Cast) -> None:
    """The zone is the Effect line, so it goes up once for the whole use --
    `c.first` -- and whether or not anything was hit."""
    if c.first:
        _no_mending(c)
    if c.strike():
        c.hit()


@power(
    "m5048a4",
    level=9,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.IMPLEMENT],
    attack=Attack(vs=WILL, printed=13),
)
def m5048a4(c: Cast) -> None:
    """No damage line at all: the whole of the hit is the condition."""
    if c.strike():
        c.weakened(until=When.EONT)


# ==========================================================================
# m762
# ==========================================================================


@power(
    "m762a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d8", 1),
)
def m762a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means. Two expressions on one line, so the untyped half stays in the
    header and the necrotic is rolled here."""
    if c.strike():
        c.hit()
        c.damage("1d8", dtype=DamageType.NECROTIC)


@power(
    "m762a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=10),
    damage=Damage("1d8", 3, dtype=DamageType.FIRE),
)
def m762a1(c: Cast) -> None:
    """"Fire and necrotic damage" is one roll of two types and a header holds
    one, so the first printed type is kept and a creature resistant only to
    the other takes this in full. The same approximation the level below
    settled on.

    The ally's bonus is gated on who it is swinging at -- "against the
    target" -- and spends itself on the first roll that reads it, which is
    what `once` is for.
    """
    if not c.strike():
        return
    c.hit()
    victim = c.target
    friends = [a for a in sorted(c.allies()) if a != c.me and c.can_see(a)]
    if not friends:
        return
    friend = c.choose(friends, "m762a1: who is shown the opening")
    if friend is None:
        return

    def against_it(ctx: dict[str, Any]) -> bool:
        return ctx.get("target") == victim

    c.bonus(
        "attack", 2, until=When.ENCOUNTER, on=friend, when=against_it, once=True
    )


@power(
    "m762a2",
    level=9,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=10),
    damage=Damage("2d8", 3, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m762a2(c: Cast) -> None:
    """"Hit or Miss" is an Effect line under another name, so the guard goes
    up once for the whole use -- `c.first` -- whatever the rolls did.

    Who is sheltered is read off the burst's own squares rather than off a
    radius measured again, and the m762 is in its own burst.
    """
    if c.first:
        for friend in sorted({c.me, *c.in_squares(c.area(), side="ally")}):
            c.bonus(AC, 2, until=When.ENCOUNTER, on=friend, kind="power")
    if c.strike():
        c.hit()
        c.push(1)
