"""Monster abilities, level 10: the controllers.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=WILL,
printed=13)` and `Damage("2d6", 6)` -- and the engine takes the level back
out of the attack and rescales the damage if a fight is being played on
another edition's maths.

A **blast** whose target line reads "creatures in the blast" is
`EACH_CREATURE`: the caster is not standing in its own blast. A **burst** of
the same wording is `EACH_OTHER`, because it is centred on the caster and
`EACH_CREATURE` would catch it.

Six readings this file had to settle.

**"Difficult terrain for enemies"** is a zone's `difficult` field, which
applies to everybody, plus `c.ignores_difficult` handed to its own side --
the exemption is the only half of that sentence the engine can express, and
between them they come to the printed rule. The label the squares carry is
the row's ref, so nothing else's rough ground is exempted with it.

**"Save ends both" is one effect.** A burn and a defence penalty printed
under one saving throw go on as one `Effects.apply` carrying both the
`ongoing` and the `Mod`, rather than as an `ongoing` beside a `c.penalty`:
applied separately the victim rolls twice and can shake off half of a thing
the card prints as one.

**A chain of failed saves** is `escalate` calling `escalate`: the slow ends
and the immobilisation replaces it carrying the next step, and the last of
them carries none so it cannot run on. An Aftereffect is `on_end` and a turn
away, which is a different printed word.

**An enemy that moves away** is the opportunity window the engine already
opens -- `movement.step` opens one for every creature whose reach the mover
is leaving, and a shove, a shift and a teleport are all exempt, which is the
whole of the printed "willingly". What the engine did not have was a reach
wider than one square, and `c.threatens` is that; the m4785's trait installs
it, because a triggered row cannot arm anything before it is triggered.

**"An attack hits it"** answered by an interrupt is `AttackRolled` with
`would_hit_me`, not `Hit`: the defence is read again after that window
closes, which is the one moment a guard raised in answer can still turn the
blow aside.

**A creature that cannot see the m3042** is the hidden relation, pointed at
one watcher. `resolve.attack` clears that for whoever swung, which is the
Stealth rule and not what a save-ends hold means, so the relation is set
again as it is broken -- `_clocked_veil`'s arrangement, narrowed to one pair.

Each stat block in ref order.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_07.soldiers import _recharge_on
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_ALLY,
    EACH_CREATURE,
    EACH_ENEMY,
    EACH_OTHER,
    ENCOUNTER,
    FORT,
    FREE,
    INTERRUPT,
    MINOR,
    NO_TARGET,
    ONE_CREATURE,
    OPPORTUNITY,
    PERSONAL,
    REF,
    STANDARD,
    WILL,
    ActionType,
    AreaBurst,
    Attack,
    AttackRolled,
    Bloodied,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    Damage,
    DamageType,
    Defense,
    Effect,
    Keyword,
    Melee,
    Mod,
    OpportunityWindow,
    Ranged,
    Relation,
    SavingThrow,
    TurnEnd,
    TurnStart,
    Usage,
    When,
    World,
    power,
    spread,
    would_hit_me,
)
from combat_engine.engine.events import RelationCleared
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import adjacent, distance_between, is_, squares
from combat_engine.engine.triggers import Trigger
from combat_engine.engine.zones import Zone

#: The four defences, for a printed "a +4 bonus to all defenses".
EVERY_DEFENCE: tuple[Defense, ...] = (AC, FORT, REF, WILL)


def _rough_ring(c: Cast, radius: int) -> int:
    """An aura whose squares are difficult going for enemies.

    A zone's roughness is a property of the squares and applies to whoever
    walks in them, which is half the printed sentence. The other half is the
    exemption, and that the engine does hold: everybody on this creature's
    side ignores rough ground carrying **this row's** label, so nothing
    else's mud is waded through for free.
    """
    ring = c.aura(radius, until=When.ENCOUNTER, label=c.ref)
    zone = c.world.get(ring, Zone)
    if zone is not None:
        zone.difficult = c.ref
    for friend in sorted({c.me, *c.allies()}):
        c.ignores_difficult(c.ref, on=friend, until=When.ENCOUNTER)
    return ring


def _burning_and_softened(
    c: Cast, victim: int, amount: int, dtype: DamageType, defended: Defense
) -> Effect:
    """A burn and a defence penalty under one saving throw.

    Two of the m336's rows print "ongoing N and a -2 penalty to <defence>
    (save ends both)", and the two halves have to ride one effect: applied
    separately the victim gets two saving throws and can shake off half of
    what the card prints as one.
    """
    return c.world.effects.apply(
        victim,
        c.me,
        When.SAVE_ENDS,
        label=c.ref,
        ongoing=(amount, dtype),
        mods=[(victim, Mod(what=defended.value, value=-2, kind="untyped", label=c.ref))],
    )


# ==========================================================================
# m221
# ==========================================================================


@power(
    "m221a0",
    level=10,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m221a0(c: Cast) -> None:
    """The ground around it is hard going for anybody but its own."""
    _rough_ring(c, 3)


@power(
    "m221a1",
    level=10,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m221a1(c: Cast) -> None:
    c.cannot_be_flanked()


@power(
    "m221a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d6", 5),
)
def m221a2(c: Cast) -> None:
    """Only the burn is acid; the blow itself is printed untyped."""
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.ACID)


@power(
    "m221a3",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_OTHER,
    keywords=[Keyword.ACID],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d6", 5, kind=LIMITED),
)
def m221a3(c: Cast) -> None:
    """"Dazed creatures in the burst" is a target line no `Target` can say --
    one carries a side and a count and no condition -- so the burst takes
    everybody else caught in it and the steady ones are let past here.
    `EACH_OTHER` rather than `EACH_CREATURE`, which would include the m221
    standing at the centre of its own burst."""
    if not c.is_(Condition.DAZED):
        return
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.ACID)


_M221_STIRS = "the m221 starts its turn"


def _its_turn_began(world: World, me: int, ev: TurnStart) -> bool:
    return ev.actor == me and not ev.ghost


@power(
    "m221a4",
    level=10,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(5),
    target=EACH_OTHER,
    attack=Attack(vs=WILL, printed=13),
    trigger=_M221_STIRS,
    on=Trigger(TurnStart, when=_its_turn_began, text=_M221_STIRS),
)
def m221a4(c: Cast) -> None:
    """No damage line at all: the daze is the whole of the hit.

    "Nondeafened creatures" is another target line no `Target` can say, so
    the burst takes everybody else and the deaf are let past here.
    """
    if c.is_(Condition.DEAFENED):
        return
    if c.strike():
        c.dazed(until=When.EONT)


# ==========================================================================
# m3042
# ==========================================================================


@power(
    "m3042a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d8", 7),
)
def m3042a0(c: Cast) -> None:
    """"Save ends both" is one effect carrying the hold and the burn."""
    if c.strike():
        c.hit()
        c.condition(
            Condition.SLOWED, until=When.SAVE_ENDS, ongoing=(5, DamageType.POISON)
        )


@power(
    "m3042a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=13),
    damage=Damage("2d6", 10, dtype=DamageType.PSYCHIC),
)
def m3042a1(c: Cast) -> None:
    """Its victim can hardly bring itself to aim at the thing.

    The penalty is gated on who is being attacked rather than being a flat
    toll, which is what "attacks that include the m3042 as a target" means;
    the attack context carries the target and is asked as the roll is made.
    Built through `Effects.apply` rather than `c.penalty` because the printed
    line escalates, and `escalate` is not a `c.bonus` argument.

    "Cannot see the m3042" is the hidden relation pointed at one watcher.
    `resolve.attack` clears it for whoever swung -- the Stealth rule, and
    the wrong one for a hold that ends on a saving throw -- so the relation
    is set again as it is broken, which is the arrangement `_clocked_veil`
    settled on three levels down.
    """
    if not c.strike():
        return
    c.hit()
    me, victim = c.me, c.target
    if victim is None:
        return

    def including_it(ctx: dict[str, Any]) -> bool:
        return ctx.get("target") == me

    def unseen(eff: Effect) -> None:
        veil = c.invisible(to=victim, until=When.ENCOUNTER)
        if veil is None:
            return

        def broke(ev: RelationCleared) -> None:
            if ev.kind_ is not Relation.HIDDEN_FROM or ev.source != me:
                return
            if ev.target == victim and ev.why == "attacked":
                c.world.relations.set(Relation.HIDDEN_FROM, me, victim)

        watcher = c.watch(
            RelationCleared, broke, until=When.ENCOUNTER, on=me, label=f"{c.ref} unseen"
        )
        eff.on_end.append(lambda: c.world.effects.end(veil, "the target can see again"))
        eff.on_end.append(lambda: c.world.effects.end(watcher, "the charm ended"))

    c.world.effects.apply(
        victim,
        me,
        When.SAVE_ENDS,
        label=c.ref,
        mods=[
            (
                victim,
                Mod(
                    what="attack", value=-2, kind="untyped",
                    when=including_it, label=c.ref,
                ),
            )
        ],
        escalate=unseen,
    )


@power(
    "m3042a2",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=13),
    damage=Damage("2d8", 10, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m3042a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.SONT)


@power(
    "m3042a3",
    level=10,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(5),
    target=EACH_ALLY,
    keywords=[Keyword.CHARM],
)
def m3042a3(c: Cast) -> None:
    """It shakes its own out of whatever holds them.

    `EACH_ALLY` includes the caster -- "ally" is the side, and a creature is
    on its own side -- so the m3042 is let past here, which is what "allies
    in the burst" means. The saving throw is the target's own with the
    printed power bonus on top.
    """
    if c.target is None or c.target == c.me:
        return
    c.save(on=c.target, bonus=5)


# ==========================================================================
# m336
# ==========================================================================


@power(
    "m336a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d6", 5),
)
def m336a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means. Only the burn is poison."""
    if c.strike():
        c.hit()
        if c.target is not None:
            _burning_and_softened(c, c.target, 10, DamageType.POISON, FORT)


@power(
    "m336a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d10", 5),
)
def m336a1(c: Cast) -> None:
    """20/40 is a normal range and a long one, and `Range` holds one number,
    so the normal range is written -- the band it shoots in at no penalty,
    rather than a distance at a -2 the engine has no way to apply.

    The secondary is a second attack line, and a second line's printed bonus
    is trimmed by hand the way `Attack.bonus_for` trims the header's.
    """
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    if c.attack(c.world.scaling.trim(13, c.level), FORT, on=victim):
        _burning_and_softened(c, victim, 10, DamageType.POISON, FORT)


@power(
    "m336a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_CREATURE,
    keywords=[Keyword.GAZE],
    attack=Attack(vs=FORT, printed=14),
)
def m336a2(c: Cast) -> None:
    """Stone, one failed save at a time.

    No damage line: the stiffening is the whole of the hit. Each step ends
    the hold it worsens and replaces it with the next, and the last carries
    no escalation of its own so it cannot run on. "No save" is the encounter
    clock -- nothing the victim rolls will end it.

    "Blind creatures are immune" is not a target line any `Target` can say,
    so the blast takes everyone and the blind are let past here.
    """
    if c.is_(Condition.BLINDED):
        return

    def to_stone(eff: Effect) -> None:
        c.world.effects.end(eff, "worsened")
        c.condition(Condition.PETRIFIED, until=When.ENCOUNTER, on=eff.owner)

    def stiffen(eff: Effect) -> None:
        c.world.effects.end(eff, "worsened")
        c.condition(
            Condition.IMMOBILIZED, until=When.SAVE_ENDS, on=eff.owner, escalate=to_stone
        )

    if c.strike():
        c.condition(Condition.SLOWED, until=When.SAVE_ENDS, escalate=stiffen)


# ==========================================================================
# m4774
# ==========================================================================


@power(
    "m4774a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD, Keyword.WEAPON],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("2d8", 9, dtype=DamageType.COLD),
)
def m4774a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(2)
        c.immobilized(until=When.EONT)


@power(
    "m4774a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD, Keyword.IMPLEMENT],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("2d8", 9, dtype=DamageType.COLD),
)
def m4774a1(c: Cast) -> None:
    """The ice is laid where the target is standing when the blow lands,
    which is its whole footprint and the ring around it -- a zone rather
    than an aura, because it stays where it was poured."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    here = squares(c.world, victim)
    c.zone(spread(here, 1), label=c.ref, until=When.EONT, difficult=True)


@power(
    "m4774a2",
    level=10,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(2, 5),
    target=EACH_ENEMY,
    keywords=[Keyword.COLD, Keyword.IMPLEMENT],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("2d8", 9, dtype=DamageType.COLD, kind=LIMITED, half_on_miss=True),
)
def m4774a2(c: Cast) -> None:
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)


_M4774_AIMED = "an attack would hit the m4774"


@power(
    "m4774a3",
    level=10,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M4774_AIMED,
    on=Trigger(AttackRolled, when=would_hit_me, text=_M4774_AIMED),
)
def m4774a3(c: Cast) -> None:
    """The guard goes up between the die landing and the blow arriving.

    `AttackRolled` rather than `Hit`: `resolve.attack` reads the defence
    **again** once this window closes, which is the one moment a bonus
    raised in answer can still turn a hit into a miss. `would_hit_me` is the
    printed "an attack hits the m4774" asked at that moment.

    Four separate modifiers, so nothing is competing with anything, and each
    is spent on the blow it answers -- `once` on a defence bonus is spent by
    the `Hit` or the `Miss`, which is exactly "against the triggering
    attack".
    """
    for defended in EVERY_DEFENCE:
        c.bonus(defended, 4, until=When.EONT, on=c.me, once=True)


# ==========================================================================
# m4783
# ==========================================================================


@power(
    "m4783a0",
    level=10,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4783a0(c: Cast) -> None:
    _rough_ring(c, 3)


@power(
    "m4783a1",
    level=10,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4783a1(c: Cast) -> None:
    """Pinning it down only makes it angrier.

    Both halves are gated modifiers rather than effects put on and taken off,
    because what holds it changes constantly. The saving throw gate reads the
    effect being saved against -- `Effects.save` passes it in the context,
    which is the only way "saves against effects that immobilize or restrain"
    can tell one hold from another.

    Escaping a grab is not a roll the engine makes, so that third clause is
    noted rather than invented.
    """
    me = c.me

    def held_fast(_ctx: dict[str, Any]) -> bool:
        return is_(c.world, me, Condition.IMMOBILIZED) or is_(
            c.world, me, Condition.RESTRAINED
        )

    def against_a_hold(ctx: dict[str, Any]) -> bool:
        eff = ctx.get("effect")
        conditions = getattr(eff, "conditions", ())
        return any(
            cond in (Condition.IMMOBILIZED, Condition.RESTRAINED) for cond in conditions
        )

    c.bonus("attack", 2, until=When.ENCOUNTER, on=me, kind="untyped", when=held_fast)
    c.bonus("save", 2, until=When.ENCOUNTER, on=me, kind="untyped", when=against_a_hold)
    c.note("m4783a1: +2 to escape a grab while it is immobilized or restrained")


@power(
    "m4783a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(3),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("3d6", 8),
)
def m4783a2(c: Cast) -> None:
    """The rider is for a target that was already reeling, so the daze is
    asked before the blow rather than after it."""
    dazed = c.is_(Condition.DAZED)
    if c.strike():
        c.hit()
        if dazed:
            c.immobilized(until=When.SAVE_ENDS)


@power(
    "m4783a3",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(5),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=13),
    damage=Damage("2d6", 6, dtype=DamageType.PSYCHIC),
)
def m4783a3(c: Cast) -> None:
    """Come any closer and it takes hold.

    Measured at the end of the victim's next turn against where it was
    standing when the blow landed, which is what "ends its next turn closer"
    compares. The watch is hung on the m4783 and spent by the turn it is
    waiting for.
    """
    if not c.strike():
        return
    c.hit()
    me, victim = c.me, c.target
    if victim is None:
        return
    was = distance_between(c.world, me, victim)

    def measured(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor != victim:
            return
        if distance_between(c.world, me, victim) < was:
            c.dazed(until=When.SAVE_ENDS, on=victim)

    c.watch(TurnEnd, measured, until=When.EOTNT, on=me, once=True, label=f"{c.ref} closer")


@power(
    "m4783a4",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("2d6", 6, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m4783a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(2)
        c.dazed(until=When.SAVE_ENDS)


def _shackled(c: Cast, who: int, mate: int, amount: int) -> None:
    """One end of the m4783's chain.

    Each end is its own effect, because the card gives each enemy its own
    saving throw. The toll is taken at both ends of the turn, which is what
    the printed line says, and only while the two are apart -- so staying
    together is the way out until somebody saves.

    The Aftereffect is the same arrangement at half the damage, hung on this
    one's ending: `on_end` is an aftereffect, where `escalate` would be a
    failed save and a turn earlier.
    """
    hold = c.effect(f"{c.ref} shackled", until=When.SAVE_ENDS, on=who)
    if hold is None:
        return

    def bite(ev: Any) -> None:
        if ev.ghost or ev.actor != who or hold.ended:
            return
        if not adjacent(c.world, who, mate):
            c.flat(amount, dtype=DamageType.PSYCHIC, on=who)

    hold.subs.append(c.world.bus.on(TurnStart, bite, owner=c.me))
    hold.subs.append(c.world.bus.on(TurnEnd, bite, owner=c.me))
    if amount > 5:
        hold.on_end.append(lambda: _shackled(c, who, mate, 5))


@power(
    "m4783a5",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=CloseBurst(5),
    target=NO_TARGET,
    keywords=[Keyword.PSYCHIC],
)
def m4783a5(c: Cast) -> None:
    """Two enemies standing together, chained to each other.

    Declared with no target: the printed line picks a **pair** that are
    adjacent to one another, which no `Target` can express, so the pairs are
    gathered here and one is chosen.

    The printed recharge is a sentence on top of the die the database files,
    and the two only ever agree to make the row available sooner.
    """
    me = c.me
    _recharge_on(c, Bloodied, lambda ev: ev.actor == me)
    near = sorted(f for f in c.enemies() if c.distance(f) <= 5)
    pairs = [
        (a, b) for a in near for b in near if a < b and adjacent(c.world, a, b)
    ]
    chosen = c.choose(pairs, "m4783a5: which pair is shackled") if pairs else None
    if chosen is None:
        return
    first, second = chosen
    _shackled(c, first, second, 10)
    _shackled(c, second, first, 10)


# ==========================================================================
# m4785
# ==========================================================================


@power(
    "m4785a0",
    level=10,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4785a0(c: Cast) -> None:
    """Dying in its shadow costs the dying.

    A death saving throw is announced like any other and names itself in
    `against`, which is the only thing that tells one from an ordinary save.
    Half the bloodied value is a quarter of the maximum, which is what
    `c.surge_value` already computes.

    The threat range lives here too. Its printed opportunity row answers an
    enemy **within five squares** moving away, and the window that says so is
    the one `movement.step` opens -- which was a ring fixed at one square
    until `c.threatens` existed. A triggered row cannot arm anything before
    it is triggered, so the trait that runs at the start of the fight is
    where this has to go.
    """
    me, ring = c.me, c.aura(5, until=When.ENCOUNTER)
    c.threatens(5, until=When.ENCOUNTER)

    def toll(ev: SavingThrow) -> None:
        if ev.saved or ev.against != "death" or ev.actor == me:
            return
        if ev.actor in c.world.zones.occupants(ring):
            c.flat(c.surge_value(of=ev.actor), on=ev.actor)

    c.watch(SavingThrow, toll, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m4785a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d8", 9),
)
def m4785a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4785a2",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("2d6", 6, dtype=DamageType.POISON, kind=LIMITED),
)
def m4785a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)


_M4785_FLED = "an enemy within 5 squares of the m4785 willingly moves away from it"


def _slipped_away(world: World, me: int, ev: OpportunityWindow) -> bool:
    """The printed sentence, which the engine already spells out for itself.

    `movement.step` opens this window for a creature whose reach the mover is
    leaving, and a shift, a teleport and every kind of shove are exempt --
    which is the whole of "willingly moves away". The five squares are the
    m4785's threat range, installed by its trait.
    """
    return ev.actor == me and ev.why == "moved away"


@power(
    "m4785a3",
    level=10,
    usage=AT_WILL,
    action=OPPORTUNITY,
    reach=CloseBurst(10),
    target=NO_TARGET,
    keywords=[Keyword.CHARM, Keyword.NECROTIC],
    attack=Attack(vs=WILL, printed=13),
    damage=Damage(bonus=5, dtype=DamageType.NECROTIC),
    trigger=_M4785_FLED,
    on=Trigger(OpportunityWindow, when=_slipped_away, text=_M4785_FLED),
)
def m4785a3(c: Cast) -> None:
    """It will not let go.

    The window names the mover as `provoker` -- `actor` is the creature being
    offered the chance -- so the target is read off the trigger rather than
    left to the dispatcher, which aims at `actor` and would point this at the
    m4785 itself.

    The hold and the vulnerability are one effect, because the card prints
    one saving throw, and the aftereffect hangs on its ending.
    """
    who = getattr(c.trigger, "provoker", None)
    if who is None or not c.strike(on=who):
        return
    c.hit(on=who)
    hold = c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS, on=who)
    exposed = c.vulnerable(5, until=When.SAVE_ENDS, on=who)
    if hold is None:
        return
    if exposed is not None:
        hold.on_end.append(lambda: c.world.effects.end(exposed, "the hold ended"))
    hold.on_end.append(lambda: c.flat(10, dtype=DamageType.NECROTIC, on=who))


# ==========================================================================
# m4877
# ==========================================================================


@power(
    "m4877a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("3d6", 6),
)
def m4877a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4877a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=13),
    damage=Damage("2d6", 6, dtype=DamageType.PSYCHIC),
)
def m4877a1(c: Cast) -> None:
    """Being alone with it is what costs.

    Asked at the end of the victim's next turn, which is when the printed
    line asks, and of the victim's own side -- from here that is the enemy
    pool, and a creature is not its own ally.
    """
    if not c.strike():
        return
    c.hit()
    me, victim = c.me, c.target
    if victim is None:
        return

    def alone(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor != victim:
            return
        if any(f != victim for f in c.within(1, of=victim, side="enemy")):
            return
        c.flat(10, dtype=DamageType.PSYCHIC, on=victim)
        c.ongoing(10, DamageType.PSYCHIC, on=victim)

    c.watch(TurnEnd, alone, until=When.EOTNT, on=me, once=True, label=f"{c.ref} alone")


@power(
    "m4877a2",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=13),
    damage=Damage("2d6", 6, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m4877a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)
