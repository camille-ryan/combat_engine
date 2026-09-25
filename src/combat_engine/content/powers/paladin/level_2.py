"""Paladin, level 2.

`p1288` steps in front of a blow aimed at somebody else. It is declared on
`DamageRolled` in the interrupt window, which is the one moment the number
exists and has not yet come off anybody -- `c.absorb` is what moves it.

`p3286` is the same sentence written the other way round: it is declared on
`AttackRolled`, because the printed trigger is being *hit* and the defence
is read again after that window closes, and it then arms a one-shot listener
that halves the damage when it arrives.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DAILY,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    INTERRUPT,
    MINOR,
    NO_TARGET,
    ONE_ALLY,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    WILL,
    AttackRolled,
    Cast,
    CloseBurst,
    DamageType,
    Defences,
    Defense,
    Effect,
    Event,
    Hit,
    Keyword,
    Melee,
    Trigger,
    When,
    Window,
    World,
    ZoneEntered,
    by_melee,
    by_ranged,
    get,
    power,
    would_hit_me,
)
from combat_engine.engine.events import DamageRolled, ZoneExited
from combat_engine.engine.query import adjacent, team

from .marks import burning_mark


@power(
    "p1255",
    level=2,
    cls="paladin",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(3),
    target=NO_TARGET,
    keywords=[Keyword.DIVINE, Keyword.IMPLEMENT, Keyword.ZONE],
)
def p1255(c: Cast) -> None:
    """The bonus belongs to standing in the zone, not to being caught in the
    burst, so it is applied on entry and taken away on exit -- the shape
    `c.burns` uses to deal damage for the same reason.

    Whoever is already inside gets it by hand: `c.zone` refreshes membership
    before it returns, so their `ZoneEntered` has been and gone by the time
    there is anything to subscribe.
    """
    me = c.me
    zone = c.zone(c.area(), until=When.ENCOUNTER)
    held = dict(c.world.zones.all()).get(zone)
    inside: dict[int, Effect] = {}

    def cover(who: int) -> None:
        if who != me and who not in c.allies():
            return
        if who in inside:
            return
        effect = c.bonus(AC, 1, on=who, until=When.ENCOUNTER, kind="power")
        if effect is not None:
            inside[who] = effect

    def uncover(who: int) -> None:
        effect = inside.pop(who, None)
        if effect is not None:
            c.world.effects.end(effect, "left the zone")

    def entered(ev: ZoneEntered) -> None:
        if ev.zone == zone:
            cover(ev.actor)

    def exited(ev: ZoneExited) -> None:
        if ev.zone == zone:
            uncover(ev.actor)

    def cleanup() -> None:
        for who in list(inside):
            uncover(who)

    subs = [
        c.world.bus.on(ZoneEntered, entered),
        c.world.bus.on(ZoneExited, exited),
    ]
    if held is not None and held.effect is not None:
        held.effect.subs.extend(subs)
        # The zone ending unsubscribes the pair above before it announces the
        # exits, so the bonuses have to be picked up here rather than there.
        held.effect.on_end.append(cleanup)
    for who in c.world.zones.occupants(zone):
        cover(who)


@power(
    "p1292",
    level=2,
    cls="paladin",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.DIVINE],
    out_of_combat=True,
)
def p1292(c: Cast) -> None:
    c.note("p1292: +4 power bonus to one social skill until the encounter ends")


@power(
    "p13557",
    level=2,
    cls="paladin",
    usage=DAILY,
    action=MINOR,
    reach=Melee(1),
    target=ONE_ALLY,
    keywords=[Keyword.DIVINE, Keyword.HEALING],
)
def p13557(c: Cast) -> None:
    """"Your healing surge value": `c.surge_value` reads the caster, which
    is the whole difference between this and the target's own."""
    if c.target is None:
        return
    c.heal(c.surge_value(), on=c.target)
    c.save(on=c.target)


@power(
    "p13818",
    level=2,
    cls="paladin",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.DIVINE],
)
def p13818(c: Cast) -> None:
    c.temp_hp(5, on=c.me)
    c.save(on=c.me)
    for d in (AC, FORT, REF, WILL):
        c.bonus(d, 2, on=c.me)


_ALLY_STRUCK = "an adjacent ally is hit by a melee or a ranged attack"


def _adjacent_ally_struck(world: World, me: int, ev: Event) -> bool:
    who = getattr(ev, "target", None)
    if who is None or who == me or getattr(ev, "amount", 0) <= 0:
        return False
    if team(world, who) is not team(world, me) or not adjacent(world, me, who):
        return False
    return by_melee(world, me, ev) or by_ranged(world, me, ev)


@power(
    "p1288",
    level=2,
    cls="paladin",
    usage=DAILY,
    action=INTERRUPT,
    reach=CloseBurst(1),
    target=NO_TARGET,
    keywords=[Keyword.DIVINE],
    trigger=_ALLY_STRUCK,
    on=Trigger(DamageRolled, when=_adjacent_ally_struck, text=_ALLY_STRUCK),
)
def p1288(c: Cast) -> None:
    """Declared on `DamageRolled` rather than on the printed `Hit`.

    "You are hit by the attack instead" has to happen while the number is
    still in flight: by the time a `Hit` is announced the roll has been
    judged and the only thing left to move is the damage, which is what
    `c.absorb` moves. The consequence is that an attack which hits for
    nothing at all is not stepped in front of -- there is nothing to take.
    """
    taken = c.absorb()
    if taken:
        c.note(f"p1288: {taken} taken in the ally's place")


_SOFT_DEFENCE = "an enemy hits your Fortitude, Reflex or Will"


def _hits_my_soft_defence(world: World, me: int, ev: Event) -> bool:
    return would_hit_me(world, me, ev) and getattr(ev, "vs", None) is not Defense.AC


@power(
    "p3286",
    level=2,
    cls="paladin",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.DIVINE],
    trigger=_SOFT_DEFENCE,
    on=Trigger(AttackRolled, when=_hits_my_soft_defence, text=_SOFT_DEFENCE),
)
def p3286(c: Cast) -> None:
    """The halving is latched by hand rather than with `once=True`: a
    listener that only edits the number in flight emits nothing, and `once`
    spends itself on whether the log grew.
    """
    foe = getattr(c.trigger, "attacker", None)
    if foe is None:
        return
    me, spent = c.me, []

    def halve(ev: DamageRolled) -> None:
        if spent or ev.source != foe or ev.target != me:
            return
        spent.append(True)
        ev.amount //= 2

    c.watch(
        DamageRolled, halve, until=When.EONT, window=Window.BEFORE, on=me,
        label=f"{c.ref} half damage",
    )
    burning_mark(c, on=foe, until=When.EOTNT)


def _weapon_power(ctx: dict) -> bool:
    p = get(ctx.get("power") or "")
    return p is not None and Keyword.WEAPON in p.keywords


@power(
    "p3727",
    level=2,
    cls="paladin",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.DIVINE, Keyword.RADIANT],
)
def p3727(c: Cast) -> None:
    """One weapon is the one in hand: `Gear` holds a grip rather than a
    named list to choose from, so "choose one weapon you are wielding" is
    every weapon attack the paladin makes.

    The extra die is a watcher rather than a damage modifier -- a modifier
    is a number and this is a roll -- and the widened crit range is gated on
    the target, which is read at the moment of the attack.
    """
    me = c.me

    def soft_to_radiant(ctx: dict) -> bool:
        defences = c.world.get(ctx.get("target"), Defences)
        return (
            _weapon_power(ctx)
            and defences is not None
            and defences.vulnerable.get(DamageType.RADIANT, 0) > 0
        )

    c.bonus("attack", 1, on=me, until=When.ENCOUNTER, kind="power", when=_weapon_power)
    c.bonus("crit_range", 2, on=me, until=When.ENCOUNTER, when=soft_to_radiant)

    def blaze(ev: Hit) -> None:
        if ev.attacker == me and _weapon_power({"power": ev.power}):
            c.flat(c.roll("1d6"), dtype=DamageType.RADIANT, on=ev.target)

    c.watch(Hit, blaze, until=When.ENCOUNTER, on=me, label=f"{c.ref} radiance")


@power(
    "p3745",
    level=2,
    cls="paladin",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Melee(1),
    target=ONE_ALLY,
    keywords=[Keyword.DIVINE],
)
def p3745(c: Cast) -> None:
    """Taking an effect over means ending it there and raising it here: an
    `Effect` is owned by one creature and cannot change hands.

    What comes across is the conditions, the burn and the saving throw
    modifier. Modifiers and relations keyed to the old holder do not -- they
    name a creature, and the one they name is no longer suffering this.
    """
    who = c.target
    if who is None:
        return
    saves = [e for e in c.world.effects.of(who) if e.when is When.SAVE_ENDS and not e.ended]
    if not saves:
        c.note(f"{c.ref}: nothing a save can end")
        return
    taken = c.choose(saves, "which effect do you take on")
    if taken is None:
        return
    c.world.effects.end(taken, "transferred")
    c.world.effects.apply(
        c.me,
        taken.source,
        When.SAVE_ENDS,
        label=taken.label,
        conditions=taken.conditions,
        ongoing=taken.ongoing,
        save_mod=taken.save_mod,
    )


@power(
    "p7248",
    level=2,
    cls="paladin",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.DIVINE],
)
def p7248(c: Cast) -> None:
    burning_mark(c)


@power(
    "p7249",
    level=2,
    cls="paladin",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.DIVINE],
)
def p7249(c: Cast) -> None:
    if c.spend_surge(on=c.me):
        c.temp_hp(c.surge_value(), on=c.me)
