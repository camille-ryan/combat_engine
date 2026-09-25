"""Cleric, level 1: a third batch, post-PHB1.

Judgement calls that recur here:

* **Two printed damage types** -- "cold and necrotic", "fire and radiant" --
  are one packet and `DamageType` holds one. Each is dealt as the *first* of
  the two printed, with both keywords on the header, which is the reading
  `paladin/level_3.py` settled.
* **The engine has no skill checks at all.** Three rows here are nothing but
  a bonus to one, so they are `out_of_combat=True` rather than an invented
  mechanic.
* **"A power bonus to all defenses"** is four modifiers, one per defence.
  They are different `what`s, so nothing collides.
* `p14249`'s "its next saving throw" is spent by hand. `once=` on a
  modifier is watched off the attack roll, the damage roll or the blow
  landing -- there is no branch for a save, and the else-branch would have
  spent this one on the target's next swing instead.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.features import CHANNEL_DIVINITY
from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    INTERRUPT,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_ALLY,
    ONE_CREATURE,
    ONE_OTHER_ALLY,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    WILL,
    WIS,
    Attack,
    AttackDeclared,
    Cast,
    CloseBurst,
    DamageType,
    Health,
    Hit,
    Keyword,
    Melee,
    MeleeOrRanged,
    Miss,
    SavingThrow,
    When,
    World,
    get,
    power,
    spread,
)
from combat_engine.engine.events import DamageRolled
from combat_engine.engine.query import adjacent, enemies, squares, team

DIVINE = [Keyword.DIVINE]
DIVINE_IMPLEMENT = [Keyword.DIVINE, Keyword.IMPLEMENT]
DIVINE_WEAPON = [Keyword.DIVINE, Keyword.WEAPON]

ALL_DEFENCES = (AC, FORT, REF, WILL)


@power(
    "p13939",
    level=1,
    cls="cleric",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.COLD, Keyword.NECROTIC],
    attack=Attack(WIS, vs=REF),
)
def p13939(c: Cast) -> None:
    """The Effect line lands whether the attack did or not, and `once` on a
    defence penalty is spent when the next blow lands or misses -- which is
    exactly "against the next attack made against it"."""
    if c.strike():
        c.damage("1d8", c.wis_mod, dtype=DamageType.COLD)
    for defence in ALL_DEFENCES:
        c.penalty(defence, 2, until=When.EONT, once=True)


@power(
    "p13940",
    level=1,
    cls="cleric",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(WIS, vs=WILL),
)
def p13940(c: Cast) -> None:
    if c.strike():
        c.damage("1d8", c.wis_mod, dtype=DamageType.PSYCHIC)
    if c.con_mod > 0:
        c.penalty("damage", c.con_mod, until=When.EONT)


@power(
    "p13941",
    level=1,
    cls="cleric",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=DIVINE,
)
def p13941(c: Cast) -> None:
    """Knowledge and nothing else: the printed Effect is what you learn, so
    the answer is reported rather than applied. Reported once for the whole
    burst, and reported even when it is empty -- learning that nobody is
    nearly down is the same power working."""
    if not c.first:
        return
    mark = c.surge_value()
    low = sorted(
        e
        for e in c.within(3, side="enemy")
        if c.bloodied(e) and (h := c.world.get(e, Health)) is not None and h.hp < mark
    )
    c.note(f"{c.ref}: below your healing surge value ({mark}): {low or 'nobody'}")


@power(
    "p13942",
    level=1,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE,
)
def p13942(c: Cast) -> None:
    """"On a hit or a miss" is two events and one latch, so both subscriptions
    hang off the one effect and share the flag.

    `c.flat` rather than a damage bonus: the printed line says the extra
    damage cannot benefit from bonuses to damage rolls, and a flat application
    is the one that reads none.
    """
    foe = c.target
    spent: list[int] = []

    def burst(ev: Hit | Miss) -> None:
        if ev.target != foe or spent:
            return
        spent.append(1)
        c.flat(c.roll("2d8"), on=foe)

    hold = c.watch(Hit, burst, until=When.EONT, on=c.me, label=c.ref)
    hold.subs.append(c.world.bus.on(Miss, burst, owner=c.me))


@power(
    "p13943",
    level=1,
    cls="cleric",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(2),
    target=ONE_ALLY,
    keywords=DIVINE,
    group=CHANNEL_DIVINITY,
)
def p13943(c: Cast) -> None:
    """"You or one ally", and the target must be bloodied -- a restriction the
    dispatcher's pick cannot honour, so the pool is gathered here."""
    bled = sorted(a for a in c.within(2, side="ally") if c.bloodied(a))
    if not bled:
        return
    who = c.choose(bled, "who is steadied")
    if who is not None:
        c.temp_hp(5, on=who)


@power(
    "p14231",
    level=1,
    cls="cleric",
    usage=ENCOUNTER,
    action=MOVE,
    reach=CloseBurst(1),
    target=ONE_OTHER_ALLY,
    keywords=[Keyword.DIVINE, Keyword.TELEPORTATION],
    group=CHANNEL_DIVINITY,
)
def p14231(c: Cast) -> None:
    """Both blink. The ally's destination is chosen from the caster's *new*
    neighbours, which is how "must end adjacent to the other" is kept without
    asking the decider a question it could answer wrongly."""
    friend = c.target
    if friend is None:
        return
    c.teleport(5)
    beside = sorted(
        sq
        for sq in spread({c.here}, 1)
        if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None
    )
    for sq in beside:
        if c.teleport(5, who=friend, to=sq):
            return


@power(
    "p14233",
    level=1,
    cls="cleric",
    usage=AT_WILL,
    action=STANDARD,
    reach=MeleeOrRanged(1, 10),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(WIS, vs=AC),
)
def p14233(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.wis_mod)
    who = c.choose(sorted(c.within(5, side="ally")), "who shifts")
    if who is not None:
        c.shift(1, who=who)


@power(
    "p14234",
    level=1,
    cls="cleric",
    usage=AT_WILL,
    action=STANDARD,
    reach=MeleeOrRanged(1, 10),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.FORCE, Keyword.RADIANT],
    attack=Attack(WIS, vs=AC),
)
def p14234(c: Cast) -> None:
    """Sheathing one weapon and drawing another is gear handling, which the
    engine does not model; the swing is the row."""
    c.note(f"{c.ref}: you may sheathe one weapon and draw another before the attack")
    if c.strike():
        c.damage(c.w(1), c.wis_mod, dtype=DamageType.FORCE)


@power(
    "p14235",
    level=1,
    cls="cleric",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=DIVINE,
    out_of_combat=True,
)
def p14235(c: Cast) -> None:
    """An aura whose whole content is a sense and a skill bonus, and the
    engine holds neither."""
    c.note(f"{c.ref}: aura 5 -- low-light vision and +2 to Perception, all encounter")


@power(
    "p14236",
    level=1,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=MeleeOrRanged(1, 10),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.FIRE, Keyword.RADIANT],
    attack=Attack(WIS, vs=AC),
)
def p14236(c: Cast) -> None:
    """Concealment is not a state the engine holds -- only hiding is, and the
    target is not hidden -- so the Effect line is a note. See the report."""
    if c.strike():
        c.damage(c.w(2), c.wis_mod, dtype=DamageType.FIRE)
    c.note(f"{c.ref}: {c.target} cannot benefit from concealment until the end of your next turn")


@power(
    "p14245",
    level=1,
    cls="cleric",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(3),
    target=NO_TARGET,
    keywords=DIVINE,
    out_of_combat=True,
    group=CHANNEL_DIVINITY,
)
def p14245(c: Cast) -> None:
    c.note(f"{c.ref}: +2 power bonus to each ally's next skill check in the burst")


@power(
    "p14246",
    level=1,
    cls="cleric",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(WIS, vs=AC),
)
def p14246(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.wis_mod)
    friends = sorted(a for a in c.within(5, side="ally") if a != c.me)
    if friends:
        who = c.choose(friends, "who gets the opening")
        c.grants_advantage(on=c.target, to=who, until=When.EONT)


@power(
    "p14247",
    level=1,
    cls="cleric",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.RADIANT, Keyword.THUNDER],
    attack=Attack(WIS, vs=AC),
)
def p14247(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.wis_mod, dtype=DamageType.RADIANT)
    c.penalty("attack", 2, until=When.EONT)


@power(
    "p14248",
    level=1,
    cls="cleric",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=CloseBurst(10),
    target=ONE_ALLY,
    keywords=DIVINE,
    trigger="you or one ally in the burst fails a skill check",
    out_of_combat=True,
)
def p14248(c: Cast) -> None:
    """Both halves of this row are skill checks -- the trigger and the
    payout -- and the engine has no such thing, so it is declared inert
    rather than given an approximate trigger that would never fire."""
    c.note(f"{c.ref}: the triggering creature adds {c.wis_mod} to the failed skill check")


@power(
    "p14249",
    level=1,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.PSYCHIC],
    attack=Attack(WIS, vs=AC),
)
def p14249(c: Cast) -> None:
    """The save penalty is spent by hand on the first saving throw the target
    rolls. `Effects.save` reads the modifier before announcing the throw, so
    ending the hold in the event's after-window still pays out on that one."""
    foe = c.target
    if c.strike():
        c.damage(c.w(2), c.wis_mod, dtype=DamageType.PSYCHIC)
    c.penalty("attack", 2, until=When.EONT)
    drop = c.penalty("save", 2, until=When.EONT)
    if drop is None:
        return

    def spend(ev: SavingThrow) -> None:
        if ev.actor == foe and not drop.ended:
            c.world.effects.end(drop, "used")

    drop.subs.append(c.world.bus.on(SavingThrow, spend, owner=c.me))


@power(
    "p14258",
    level=1,
    cls="cleric",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.RADIANT],
    attack=Attack(WIS, vs=AC),
)
def p14258(c: Cast) -> None:
    """"Hits you or any of your allies" -- the caster is named, so the gate is
    the whole side rather than the allies alone."""
    foe = c.target
    me = c.me
    if c.strike():
        c.damage(c.w(1), c.wis_mod, dtype=DamageType.RADIANT)
    if c.con_mod <= 0:
        return

    def backlash(ev: Hit) -> None:
        if ev.attacker != foe or team(c.world, ev.target) is not team(c.world, me):
            return
        c.flat(c.con_mod, dtype=DamageType.RADIANT, on=foe)

    c.watch(Hit, backlash, until=When.EONT, on=foe, once=True, label=c.ref)


@power(
    "p14259",
    level=1,
    cls="cleric",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.COLD, Keyword.RADIANT],
    attack=Attack(WIS, vs=AC),
)
def p14259(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.wis_mod, dtype=DamageType.COLD)
    for friend in c.within(5, side="ally"):
        c.bonus("save", 2, on=friend, until=When.SONT, kind="power")


@power(
    "p14260",
    level=1,
    cls="cleric",
    usage=DAILY,
    action=MINOR,
    reach=Melee(1),
    target=SELF,
    keywords=DIVINE,
)
def p14260(c: Cast) -> None:
    """A weapon is not an entity, so the enchantment is held on the wielder and
    reads the power off `DamageRolled.detail`: untyped damage from any weapon
    attack of the caster's comes out radiant. "Unless the damage already has a
    type" is the untyped test; which *weapon* dealt it cannot be asked.
    """
    me = c.me

    def gild(ev: DamageRolled) -> None:
        if ev.source != me or ev.dtype is not DamageType.UNTYPED:
            return
        p = get(ev.detail or "")
        if p is not None and Keyword.WEAPON in p.keywords:
            ev.dtype = DamageType.RADIANT

    c.watch(DamageRolled, gild, until=When.ENCOUNTER, on=me, label=c.ref)
    c.note(f"{c.ref}: the weapon sheds bright light and counts as silvered")


@power(
    "p14261",
    level=1,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.RADIANT],
    attack=Attack(WIS, vs=AC),
)
def p14261(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.wis_mod, dtype=DamageType.RADIANT)
    if c.con_mod <= 0:
        return
    who = c.choose(sorted(c.within(5, side="ally")), "who strikes harder")
    if who is not None:
        c.bonus("damage", c.con_mod, on=who, until=When.EONT, kind="power")


@power(
    "p14262",
    level=1,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=NO_TARGET,
    keywords=DIVINE,
    group=CHANNEL_DIVINITY,
)
def p14262(c: Cast) -> None:
    for friend in c.within(5, side="ally"):
        c.resist(5, DamageType.NECROTIC, until=When.EONT, on=friend)
    for foe in c.within(5, side="enemy"):
        c.vulnerable(5, DamageType.RADIANT, until=When.EONT, on=foe)


@power(
    "p14271",
    level=1,
    cls="cleric",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(WIS, vs=AC),
)
def p14271(c: Cast) -> None:
    """"One or more of your allies" -- not you, which is the difference from
    the sibling rows that say "you or any of your allies"."""
    foe = c.target
    me = c.me
    if c.strike():
        c.damage(c.w(1), c.wis_mod)
    if c.con_mod <= 0:
        return

    def sting(ev: AttackDeclared) -> None:
        if ev.target != me and team(c.world, ev.target) is team(c.world, me):
            c.flat(c.con_mod, on=foe)

    c.on_attack(sting, by=foe, until=When.SONT, once=True, label=c.ref)


@power(
    "p14272",
    level=1,
    cls="cleric",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(WIS, vs=AC),
)
def p14272(c: Cast) -> None:
    foe = c.target
    if c.strike():
        c.damage(c.w(1), c.wis_mod)
    beside = sorted(a for a in c.within(1, of=foe, side="ally") if a != c.me)
    if not beside:
        return
    who = c.choose(beside, "who is shielded")
    for defence in ALL_DEFENCES:
        c.bonus(defence, 1, on=who, until=When.EONT, kind="power")


def _at_an_enemy_of(c: Cast, friend: int) -> Any:
    """"Against an enemy": the gate reads the sides at the moment of the
    swing, so a bonus held over a turn cannot be spent on an ally."""
    mine = team(c.world, friend)

    def gate(ctx: dict[str, Any]) -> bool:
        foe = ctx.get("target")
        return foe is not None and team(c.world, foe) is not mine

    return gate


@power(
    "p14273",
    level=1,
    cls="cleric",
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(5),
    target=ONE_OTHER_ALLY,
    keywords=DIVINE,
)
def p14273(c: Cast) -> None:
    friend = c.target
    if friend is None:
        return
    c.bonus(
        "attack",
        4,
        on=friend,
        until=When.EONT,
        once=True,
        when=_at_an_enemy_of(c, friend),
    )


@power(
    "p14274",
    level=1,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.THUNDER],
    attack=Attack(WIS, vs=AC),
)
def p14274(c: Cast) -> None:
    """"Hits or misses" is two events off one hold. The reward is clocked by
    the ally who earned it, which is what `When.EOTNT` measures."""
    foe = c.target
    me = c.me
    if c.strike():
        c.damage(c.w(1), c.wis_mod, dtype=DamageType.THUNDER)

    def steady(ev: Hit | Miss) -> None:
        if ev.target != foe or ev.attacker == me:
            return
        if team(c.world, ev.attacker) is not team(c.world, me):
            return
        for defence in ALL_DEFENCES:
            c.bonus(defence, 2, on=ev.attacker, until=When.EOTNT, kind="power")

    hold = c.watch(Hit, steady, until=When.EONT, on=me, label=c.ref)
    hold.subs.append(c.world.bus.on(Miss, steady, owner=me))


def _next_to_an_enemy(world: World, eid: int) -> bool:
    return any(adjacent(world, eid, foe) for foe in enemies(world, eid))


def _both_flank(c: Cast, foe: int, me: int, friend: int) -> Any:
    def gate(ctx: dict[str, Any]) -> bool:
        if ctx.get("target") != foe or ctx.get("attacker") not in (me, friend):
            return False
        space = squares(c.world, foe)
        return any(
            c.world.grid.flanks(a, b, space)
            for a in squares(c.world, me)
            for b in squares(c.world, friend)
        )

    return gate


@power(
    "p14275",
    level=1,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(10),
    target=ONE_OTHER_ALLY,
    keywords=[Keyword.DIVINE, Keyword.TELEPORTATION],
    requires=_next_to_an_enemy,
    requires_text="you must be adjacent to an enemy",
    group=CHANNEL_DIVINITY,
)
def p14275(c: Cast) -> None:
    """The landing square is not a choice: the printed line says where the
    ally arrives, so the squares beside an adjacent enemy are tested against
    `Grid.flanks` from the caster's own space and the first that works is
    named outright. The bonus is gated on the pair still flanking, which is
    the printed "while you both flank it" rather than a flat +1."""
    friend = c.target
    if friend is None:
        return
    me = c.me
    for foe in sorted(c.within(1, side="enemy")):
        space = squares(c.world, foe)
        spots = sorted(
            sq
            for sq in spread(space, 1)
            if c.world.grid.passable(sq)
            and c.world.grid.occupant(sq) is None
            and any(c.world.grid.flanks(sq, here, space) for here in squares(c.world, me))
        )
        if not any(c.teleport(12, who=friend, to=sq) for sq in spots):
            continue
        gate = _both_flank(c, foe, me, friend)
        c.bonus("attack", 1, on=me, until=When.EONT, when=gate)
        c.bonus("attack", 1, on=friend, until=When.EONT, when=gate)
        return
