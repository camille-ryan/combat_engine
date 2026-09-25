"""Paladin, level 1: the rows the later books added.

`level_1.py` was already three hundred lines, so these sit beside it rather
than in it. Nothing else distinguishes the two files -- a row's level is
what decides where it lives.

Two things recur here and are worth saying once.

**"Strength or Charisma vs. AC"** is one printed attack line offering two
abilities, not a two-branch range line, so `attack_alt` cannot carry it --
that is only read for a `MeleeOrRanged` reach. The header keeps the first
printed line for the card and `_str_or_cha` rolls whichever the character is
actually good at, which is the leg of the fork it took.

**The mark these books hand out** is `marks.burning_mark`; see that module.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    AT_WILL,
    CHA,
    DAILY,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    MINOR,
    ONE_CREATURE,
    REF,
    STANDARD,
    STR,
    WILL,
    Attack,
    Cast,
    CloseBurst,
    DamageType,
    Gear,
    Keyword,
    Melee,
    Position,
    Ranged,
    TurnStart,
    When,
    Window,
    World,
    ZoneEntered,
    by_melee,
    power,
)
from combat_engine.engine.events import AttackDeclared, Hit, MoveEnd
from combat_engine.engine.grid import distance, spread
from combat_engine.engine.query import adjacent, defence
from combat_engine.engine.query import squares as squares_of

from .marks import burning_mark

DIVINE_WEAPON = [Keyword.DIVINE, Keyword.WEAPON]
DIVINE_IMPLEMENT = [Keyword.DIVINE, Keyword.IMPLEMENT]


def _str_or_cha(c: Cast) -> tuple[int, int]:
    """The attack bonus and the damage modifier of the better of the two."""
    if c.cha_ > c.str_:
        return c.cha_, c.cha_mod
    return c.str_, c.str_mod


def _has_shield(world: World, eid: int) -> bool:
    """"Requirement: you must be using a shield"."""
    gear = world.get(eid, Gear)
    return gear is not None and gear.shield


@power(
    "p10246",
    level=1,
    cls="paladin",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.NECROTIC, Keyword.HEALING],
    attack=Attack(STR, vs=AC),
)
def p10246(c: Cast) -> None:
    if not c.strike():
        return
    c.damage(c.w(2), c.str_mod, dtype=DamageType.NECROTIC)
    # "You or an ally": the ally pool already has the caster in it.
    pool = c.within(5, side="ally")
    hurt = [a for a in pool if c.wounded(a)]
    who = c.choose(sorted(hurt or pool), "who is mended")
    if who is not None:
        c.heal(c.cha_mod, on=who)


@power(
    "p10247",
    level=1,
    cls="paladin",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[*DIVINE_IMPLEMENT, Keyword.COLD, Keyword.ZONE],
    attack=Attack(CHA, vs=FORT),
)
def p10247(c: Cast) -> None:
    """The zone slows rather than bites, so it is `c.zone` plus the pair of
    watchers `c.burns` uses for the same two moments -- entering it, and
    starting a turn in it. The errata'd duration is the one written.
    """
    if c.first:
        _chills(c, c.zone(c.area(), until=When.SUSTAIN, sustain=MINOR))
    if c.strike():
        c.damage("1d10", c.cha_mod, dtype=DamageType.COLD)
    else:
        c.half_damage("1d10", c.cha_mod, dtype=DamageType.COLD)


def _chills(c: Cast, zone: int) -> None:
    def chill(who: int) -> None:
        if who in c.enemies():
            c.slowed(on=who, until=When.EOTNT)

    def entered(ev: ZoneEntered) -> None:
        if ev.zone == zone:
            chill(ev.actor)

    def began(ev: TurnStart) -> None:
        if not ev.ghost and ev.actor in c.world.zones.occupants(zone):
            chill(ev.actor)

    held = dict(c.world.zones.all()).get(zone)
    subs = [
        c.world.bus.on(ZoneEntered, entered),
        c.world.bus.on(TurnStart, began),
    ]
    if held is not None and held.effect is not None:
        held.effect.subs.extend(subs)
    for who in c.world.zones.occupants(zone):
        chill(who)


@power(
    "p11048",
    level=1,
    cls="paladin",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p11048(c: Cast) -> None:
    """The follow-up hangs off the burn rather than off a clock: it lasts
    exactly as long as the ongoing damage this attack applied, which is what
    "while it is taking ongoing damage from this attack" reads.

    The Special line -- swinging this instead of a basic attack when
    charging -- has no header field and is not written; see the report.
    """
    victim = c.target
    if victim is None:
        return
    if not c.strike():
        c.half_damage(c.w(2), c.str_mod)
        c.push(1)
        return
    c.damage(c.w(2), c.str_mod)
    burn = c.ongoing(5)
    if burn is None:
        return
    me = c.me

    def follow(ev: Hit) -> None:
        if ev.attacker != me or ev.target != victim or burn.ended:
            return
        if not by_melee(c.world, me, ev) or not c.may("push and follow", who=me):
            return
        pos = c.world.get(victim, Position)
        vacated = pos.square if pos is not None else None
        if c.push(1, on=victim) and vacated is not None:
            c.shift(1, to=vacated)

    c.watch(Hit, follow, until=When.ENCOUNTER, on=me, label=f"{c.ref} follow")


@power(
    "p13575",
    level=1,
    cls="paladin",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.RADIANT],
    attack=Attack(STR, vs=AC),
)
def p13575(c: Cast) -> None:
    if not c.strike():
        return
    c.damage(c.w(1), c.str_mod, dtype=DamageType.RADIANT)
    friends = [a for a in c.within(5, side="ally") if a != c.me]
    if not friends:
        return
    who = c.choose(sorted(friends), "who is shielded")
    c.temp_hp(c.cha_mod + (5 if c.bloodied(who) else 0), on=who)


@power(
    "p13580",
    level=1,
    cls="paladin",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.RADIANT],
    attack=Attack(STR, vs=AC),
)
def p13580(c: Cast) -> None:
    """The miss line is a one-shot damage bonus gated to this target; the
    printed line names no duration, so it stands until the fight ends or it
    is spent.
    """
    victim = c.target
    if c.strike():
        bled = [a for a in c.within(5, side="ally") if a != c.me and c.bloodied(a)]
        c.damage(c.w(1), c.str_mod + (c.cha_mod if bled else 0), dtype=DamageType.RADIANT)
    else:
        c.bonus(
            "damage", 2, on=c.me, until=When.ENCOUNTER, once=True,
            when=lambda ctx: ctx.get("target") == victim,
        )


@power(
    "p13817",
    level=1,
    cls="paladin",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p13817(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.str_mod + min(8, 2 * len(c.within(1, side="enemy"))))


@power(
    "p13837",
    level=1,
    cls="paladin",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p13837(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.str_mod)
        c.temp_hp(c.cha_mod, on=c.me)


@power(
    "p13843",
    level=1,
    cls="paladin",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p13843(c: Cast) -> None:
    """Which enemy the advantage is against is not known yet, and combat
    advantage is worked out inside the roll -- so it is granted from the
    interrupt window of the next attack's `AttackDeclared`, which is the
    last moment it can be handed out and still be read.
    """
    if not c.strike():
        return
    c.damage(c.w(1), c.str_mod)
    me = c.me

    def offer(ev: AttackDeclared) -> None:
        if ev.attacker == me and ev.target not in (None, me):
            c.grants_advantage(on=ev.target, to=me, until=When.EOT)

    c.watch(
        AttackDeclared, offer, until=When.EONT, window=Window.BEFORE, on=me,
        once=True, label=f"{c.ref} opening",
    )


@power(
    "p3247",
    level=1,
    cls="paladin",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.RADIANT],
    attack=Attack(STR, vs=AC),
)
def p3247(c: Cast) -> None:
    bonus, mod = _str_or_cha(c)
    if c.attack(bonus, AC):
        c.damage(c.w(1), mod, dtype=DamageType.RADIANT)
        for d in (FORT, REF, WILL):
            c.bonus(d, c.wis_mod, on=c.me)


@power(
    "p3261",
    level=1,
    cls="paladin",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.HEALING],
    attack=Attack(CHA, vs=AC),
)
def p3261(c: Cast) -> None:
    """The healing is an Effect line: it lands whether the swing did or not."""
    if c.strike():
        c.damage(c.w(2), c.cha_mod)
    if c.first:
        for friend in c.within(2, side="ally"):
            if friend != c.me:
                c.heal(c.level // 2 + c.wis_mod, on=friend)


@power(
    "p3271",
    level=1,
    cls="paladin",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.RADIANT],
    attack=Attack(CHA, vs=AC),
)
def p3271(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(3), c.cha_mod, dtype=DamageType.RADIANT)
    else:
        c.half_damage(c.w(3), c.cha_mod, dtype=DamageType.RADIANT)
    if not c.first:
        return

    def dawn(ev: TurnStart) -> None:
        if not ev.ghost and ev.actor in c.enemies() and c.adjacent(ev.actor):
            burning_mark(c, on=ev.actor, until=When.EOT)

    c.watch(TurnStart, dawn, until=When.ENCOUNTER, on=c.me, label=c.ref)


@power(
    "p3272",
    level=1,
    cls="paladin",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.RELIABLE],
    attack=Attack(STR, vs=AC),
)
def p3272(c: Cast) -> None:
    """"Which can't be reduced in any way" has no spelling: the five goes
    through `deal_damage` like anything else, so a resistance would still
    read it. Left as it is rather than approximated.
    """
    if c.strike():
        c.damage(c.w(4), c.str_mod)
    if c.first:
        c.flat(5, on=c.me)


@power(
    "p3687",
    level=1,
    cls="paladin",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.RADIANT],
    attack=Attack(CHA, vs=AC),
)
def p3687(c: Cast) -> None:
    """The Special line -- this row may be used as a melee basic attack --
    has no header field; see the report."""
    if c.strike():
        c.damage(c.w(1), c.cha_mod, dtype=DamageType.RADIANT)
        c.bonus("save", 2, on=c.me, until=When.SONT)


@power(
    "p3689",
    level=1,
    cls="paladin",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(CHA, vs=AC),
)
def p3689(c: Cast) -> None:
    if not c.strike():
        return
    c.damage(c.w(2), c.cha_mod)
    for foe in sorted(c.within(3, side="enemy")):
        burning_mark(c, on=foe)


@power(
    "p7241",
    level=1,
    cls="paladin",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p7241(c: Cast) -> None:
    bonus, mod = _str_or_cha(c)
    if c.attack(bonus, AC):
        c.damage(c.w(1), mod)
        burning_mark(c)


@power(
    "p7243",
    level=1,
    cls="paladin",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.RADIANT],
    attack=Attack(CHA, vs=REF),
)
def p7243(c: Cast) -> None:
    if c.strike():
        c.damage("2d8", c.cha_mod, dtype=DamageType.RADIANT)
        c.penalty("attack", 2)


@power(
    "p7244",
    level=1,
    cls="paladin",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(STR, vs=FORT),
)
def p7244(c: Cast) -> None:
    """The shift is named, not chosen: "the nearest square adjacent to the
    target" is an instruction, and `c.shift` takes the square outright.
    """
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.damage(c.w(2), c.str_mod)
    c.push(max(0, c.wis_mod))
    theirs = squares_of(c.world, victim)
    beside = [
        sq
        for sq in spread(theirs, 1) - theirs
        if c.world.grid.inside(sq)
        and c.world.grid.passable(sq)
        and c.world.grid.occupant(sq) is None
    ]
    if beside:
        c.shift(1, to=min(beside, key=lambda sq: (distance(c.here, sq), sq)))


@power(
    "p7247",
    level=1,
    cls="paladin",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.FIRE, Keyword.RELIABLE],
    attack=Attack(STR, vs=FORT),
)
def p7247(c: Cast) -> None:
    """"Grants combat advantage to any ally adjacent to it" is asked per
    attack rather than fixed now: which allies are adjacent changes, and a
    relation set at this moment would freeze the answer. The watcher hangs
    on the burn, so one saving throw ends both halves, as printed.
    """
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.damage(c.w(2), c.str_mod, dtype=DamageType.FIRE)
    burn = c.ongoing(5, DamageType.FIRE)
    if burn is None:
        return
    me = c.me

    def opening(ev: AttackDeclared) -> None:
        if ev.target != victim or ev.attacker == me:
            return
        if ev.attacker in c.allies() and adjacent(c.world, ev.attacker, victim):
            c.grants_advantage(on=victim, to=ev.attacker, until=When.EOT)

    burn.subs.append(
        c.world.bus.on(AttackDeclared, opening, window=Window.BEFORE, owner=me)
    )


@power(
    "p7384",
    level=1,
    cls="paladin",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=_has_shield,
)
def p7384(c: Cast) -> None:
    if not c.strike():
        return
    c.damage(c.w(1), c.str_mod)
    friends = [a for a in c.within(1, side="ally") if a != c.me]
    if friends:
        c.resist(2, on=c.choose(sorted(friends), "who is covered"), until=When.EONT)


@power(
    "p7407",
    level=1,
    cls="paladin",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p7407(c: Cast) -> None:
    """Bloodied, the swing finds the softer of two defences, so the body
    rolls its own attack; the header keeps the printed line for the card.

    "Or until you move into a square not adjacent to the target" is a second
    ending on top of the duration, so it is a watch hung on the mark itself
    rather than a clock.
    """
    victim = c.target
    if victim is None:
        return
    vs = AC
    if c.bloodied(on=c.me) and defence(c.world, victim, WILL) < defence(c.world, victim, AC):
        vs = WILL
    if not c.attack(c.str_, vs):
        return
    c.damage(c.w(1), c.str_mod)
    held = c.mark()
    if held is None:
        return
    me = c.me

    def strayed(ev: MoveEnd) -> None:
        if ev.actor == me and not adjacent(c.world, me, victim):
            c.world.effects.end(held, "moved out of reach")

    held.subs.append(c.world.bus.on(MoveEnd, strayed, owner=me))


@power(
    "p8099",
    level=1,
    cls="paladin",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p8099(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(3), c.str_mod)
        for d in (AC, FORT, REF, WILL):
            c.penalty(d, 5, on=c.me)
