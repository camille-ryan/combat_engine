"""Cleric, level 1: the rows the later books added, fourth batch.

Four things recur here and are worth saying once.

**"You must use this power with a simple weapon"** and its softer cousin
"if you're wielding a simple weapon, the attack deals 1d6 extra" both ask a
question the gear table cannot answer: `chargen`'s weapons carry a group and
a handful of properties, and nothing anywhere says simple or military. So
`_simple` asks for the property that ought to be there, which makes the two
Requirement rows unusable and the two riders unpaid until one word is added
to the weapon table. Writing a group list instead would be a guess, and a
wrong one -- simple-ness is per weapon, not per group.

**A bonus that is "while adjacent to you" or "while within the zone"** is
membership, not a one-off: `_hold_while_inside` puts the hold on at
`ZoneEntered` and takes it off at `ZoneExited`, and gives it the zone's own
duration so nothing has to be unwound when the zone expires.

**Neither shadow row carries its printed shadow keyword**: `Keyword` has no
such word, the same reading `level_10_b.py` settled.

**p7080's weapon stands in the cleric's own space.** `Grid.place` refuses a
second occupant, which is exactly right here -- the conjuration shares the
square rather than taking one -- and it is why "when you move, the weapon
moves with you" needs no arranging: its swings are rolled from `c.me`.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    MINOR,
    ONE_CREATURE,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    STR,
    WILL,
    WIS,
    Attack,
    Cast,
    CloseBlast,
    CloseBurst,
    DamageType,
    Effect,
    Gear,
    Keyword,
    Melee,
    Ranged,
    Relation,
    TurnStart,
    When,
    Window,
    World,
    ZoneEntered,
    distance,
    get,
    power,
    spread,
)
from combat_engine.engine.components import Conjuration
from combat_engine.engine.events import (
    AttackDeclared,
    AttackRolled,
    DamageRolled,
    Hit,
    MoveEnd,
    ZoneExited,
)
from combat_engine.engine.query import adjacent, defence

DIVINE_WEAPON = [Keyword.DIVINE, Keyword.WEAPON]
DIVINE_IMPLEMENT = [Keyword.DIVINE, Keyword.IMPLEMENT]
DEFENCES = (AC, FORT, REF, WILL)


def _simple(world: World, eid: int) -> bool:
    """"A simple weapon" -- the word the gear table does not have yet.

    Asked of the wielded weapon's properties rather than its group: in the
    printed rules simple-ness is a property of the weapon and two weapons of
    one group can differ. See the module docstring.
    """
    gear = world.get(eid, Gear)
    weapon = gear.main if gear is not None else None
    return weapon is not None and "simple" in weapon.properties


def _two_handed(c: Cast) -> int:
    """"If you're wielding your weapon with both hands, +2 to the damage roll"."""
    return 2 if c.wielding("two-handed") else 0


def _hold_while_inside(
    c: Cast,
    zone: int,
    until: When,
    eligible: Callable[[int], bool],
    hold: Callable[[int], Iterable[Effect | None]],
) -> None:
    """Whoever stands in `zone` carries a hold for as long as they do.

    The holds are given the zone's own duration, so the only thing that has
    to be undone by hand is somebody walking out of it.
    """
    held: dict[int, list[Effect]] = {}

    def take(who: int) -> None:
        if who in held or not eligible(who):
            return
        held[who] = [e for e in hold(who) if e is not None]

    def drop(who: int) -> None:
        for effect in held.pop(who, []):
            c.world.effects.end(effect, "stepped out")

    def entered(ev: ZoneEntered) -> None:
        if ev.zone == zone:
            take(ev.actor)

    def exited(ev: ZoneExited) -> None:
        if ev.zone == zone:
            drop(ev.actor)

    c.watch(ZoneEntered, entered, until=until, label=f"{c.ref} in")
    c.watch(ZoneExited, exited, until=until, label=f"{c.ref} out")
    for who in c.world.zones.occupants(zone):
        take(who)


@power(
    "p14295",
    level=1,
    cls="cleric",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(STR, vs=AC, plus=1),
    requires=_simple,
    requires_text="needs a simple weapon",
)
def p14295(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), 2 + c.str_mod + _two_handed(c))


@power(
    "p14296",
    level=1,
    cls="cleric",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p14296(c: Cast) -> None:
    """The guard is an aura, because "while adjacent to you" is membership."""
    if c.strike():
        c.damage(c.w(1), c.str_mod)
        if _simple(c.world, c.me):
            c.damage("1d6")
    ring = c.aura(1, label=c.ref, until=When.EONT)
    friends = set(c.allies())
    _hold_while_inside(
        c,
        ring,
        When.EONT,
        lambda who: who in friends,
        lambda who: [
            c.bonus(d, 2, on=who, until=When.EONT, kind="power") for d in DEFENCES
        ],
    )


@power(
    "p14297",
    level=1,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(STR, vs=AC, plus=1),
    requires=_simple,
    requires_text="needs a simple weapon",
)
def p14297(c: Cast) -> None:
    """"Against the target's lowest defence" is `AttackDeclared.vs` rewritten.

    In the `Window.BEFORE` half: `resolve.attack` reads the field back when
    it rolls, and the roll happens between the two windows.
    """
    if c.strike():
        c.damage(c.w(2), 2 + c.str_mod + _two_handed(c))
    victim = c.target
    if victim is None:
        return
    swingers = {c.me, *c.within(3, side="ally")}

    def aim(ev: AttackDeclared) -> None:
        if ev.target != victim or ev.attacker not in swingers:
            return
        ev.vs = min(DEFENCES, key=lambda d: defence(c.world, victim, d))

    c.watch(
        AttackDeclared, aim, until=When.EONT, window=Window.BEFORE,
        on=c.me, label=f"{c.ref} opening",
    )


@power(
    "p14298",
    level=1,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p14298(c: Cast) -> None:
    """The halving is latched by hand: a listener that only edits a number in
    flight emits nothing, and `once` spends itself on whether the log grew."""
    if c.strike():
        c.damage(c.w(2), c.str_mod)
        if _simple(c.world, c.me):
            c.damage("1d6")
    victim, spent = c.target, []

    def halve(ev: DamageRolled) -> None:
        if spent or ev.source != victim:
            return
        spent.append(True)
        ev.amount //= 2

    c.watch(
        DamageRolled, halve, until=When.EONT, window=Window.BEFORE,
        on=c.me, label=f"{c.ref} half damage",
    )


@power(
    "p16418",
    level=1,
    cls="cleric",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.DIVINE],
    out_of_combat=True,
)
def p16418(c: Cast) -> None:
    c.note("p16418: +2 to your next Intimidate check before your next turn ends")


@power(
    "p16419",
    level=1,
    cls="cleric",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.FEAR],
    attack=Attack(WIS, vs=AC),
)
def p16419(c: Cast) -> None:
    """The printed Special is a note about what the row may stand in for when
    charging, not a row whose Effect is a charge: no `charges=True`."""
    if c.strike():
        c.damage(c.w(1), c.wis_mod)
        c.prone()


@power(
    "p16420",
    level=1,
    cls="cleric",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.FEAR],
    attack=Attack(WIS, vs=WILL),
)
def p16420(c: Cast) -> None:
    """"Must end adjacent to the target" narrows the shift to the squares that
    qualify, so the ally simply cannot take it when none of them is reachable."""
    if c.strike():
        c.damage(c.w(1), c.wis_mod)
        c.push(1)
    victim = c.target
    beside = [a for a in c.within(1, side="ally") if a != c.me]
    if victim is None or not beside:
        return
    friend = c.choose(beside, f"{c.ref}: who steps in")
    if friend is None:
        return
    spots = [
        sq for sq in c.world.reachable_squares(friend, 2) if distance(sq, c.there) <= 1
    ]
    if spots:
        c.shift(2, who=friend, to=c.choose(sorted(spots), f"{c.ref}: where it lands"))


@power(
    "p16421",
    level=1,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.FEAR, Keyword.PSYCHIC],
    attack=Attack(WIS, vs=AC),
)
def p16421(c: Cast) -> None:
    """"Willingly enters" is `MoveEnd`: forced movement goes through
    `movement.forced` and never emits one, so nothing has to be enumerated.

    The weapon dice are printed untyped -- only the rider is psychic.
    """
    if not c.strike():
        return
    c.damage(c.w(2), c.wis_mod)
    c.push(1)
    victim, mine, burnt = c.target, [c.me, *c.allies()], []

    def stepped(ev: MoveEnd) -> None:
        if burnt or ev.actor != victim or ev.kind_ == "forced":
            return
        if not any(adjacent(c.world, who, victim) for who in mine):
            return
        burnt.append(True)
        c.flat(5, dtype=DamageType.PSYCHIC, on=victim)

    c.watch(MoveEnd, stepped, until=When.EONT, label=f"{c.ref} step")


def _str_or_wis(c: Cast) -> int:
    """"Strength or Wisdom": the better of the two, and one printed attack
    line rather than a two-branch range, so `attack_alt` cannot carry it --
    the same reading `paladin/level_1_b.py` settled. The header keeps the
    first printed ability for the card."""
    return max(c.str_, c.wis_)


@power(
    "p16510",
    level=1,
    cls="cleric",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.NECROTIC, Keyword.POISON],
    attack=Attack(STR, vs=FORT),
)
def p16510(c: Cast) -> None:
    """"Save ends both" is one effect and one saving throw, so the burn and
    the combat advantage are applied together rather than side by side."""
    if c.attack(_str_or_wis(c), FORT):
        victim = c.target
        c.damage("2d8", c.wis_mod, dtype=DamageType.NECROTIC)
        c.world.effects.apply(
            victim,
            c.me,
            When.SAVE_ENDS,
            label=c.ref,
            ongoing=(5, DamageType.POISON),
            relations=[
                (Relation.GRANTS_CA_TO, victim, b) for b in (c.me, *c.allies())
            ],
        )
    else:
        c.half_damage("2d8", c.wis_mod, dtype=DamageType.NECROTIC)
        c.grants_advantage(to="allies", until=When.SAVE_ENDS)


@power(
    "p3432",
    level=1,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.CONJURATION, Keyword.RADIANT],
    attack=Attack(WIS, vs=REF),
)
def p3432(c: Cast) -> None:
    """A real conjuration: it occupies its square, which is the printed line.

    "Allies can move through it as if it were an ally" is the half that has
    nowhere to go -- a conjuration blocks everyone equally -- and it costs
    the allies a little rather than gaining them anything, so the row is
    written without it.
    """
    if not c.strike():
        return
    c.damage("2d8", c.wis_mod, dtype=DamageType.RADIANT)
    free = [
        sq
        for sq in sorted(spread({c.there}, 1) - {c.there})
        if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None
    ]
    where = c.choose(free, f"{c.ref}: where it stands") if free else None
    if where is None:
        return
    pillar = c.conjure(where, label=c.ref, until=When.EONT, sustain=None)
    if not pillar:
        return
    ring = c.aura(1, label=c.ref, until=When.EONT, on=pillar)
    friends = set(c.allies())
    _hold_while_inside(
        c,
        ring,
        When.EONT,
        lambda who: who in friends,
        lambda who: [
            c.bonus(d, 2, on=who, until=When.EONT, kind="power") for d in DEFENCES
        ],
    )


@power(
    "p3585",
    level=1,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=DIVINE_IMPLEMENT,
    attack=Attack(WIS, vs=WILL),
)
def p3585(c: Cast) -> None:
    if not c.strike():
        return
    amount = 1 + c.cha_mod
    c.penalty("attack", amount, until=When.EONT)
    for d in DEFENCES:
        c.penalty(d, amount, until=When.EONT)


@power(
    "p7072",
    level=1,
    cls="cleric",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.HEALING],
    attack=Attack(STR, vs=AC),
)
def p7072(c: Cast) -> None:
    """"The next ally who hits" -- the cleric's own blows do not spend it,
    and the latch is held by hand because the payout is a heal on somebody
    the trigger names rather than on whoever the hold sits on."""
    if not c.strike():
        return
    c.damage(c.w(1), c.str_mod)
    victim, gift, paid = c.target, c.cha_mod, []

    def reward(ev: Hit) -> None:
        if paid or ev.target != victim or ev.attacker not in c.allies():
            return
        paid.append(True)
        c.heal(gift, on=ev.attacker)

    c.watch(Hit, reward, until=When.EONT, label=f"{c.ref} reward")


@power(
    "p7073",
    level=1,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=DIVINE_IMPLEMENT,
    attack=Attack(WIS, vs=WILL),
)
def p7073(c: Cast) -> None:
    """The temporary hit points are paid for attacking, not for hitting, so
    the watch is on the roll rather than on the `Hit`."""
    if not c.strike():
        return
    victim, gift = c.target, c.wis_mod
    c.vulnerable(gift, until=When.EONT)

    def paid(ev: AttackRolled) -> None:
        if ev.target == victim and ev.attacker in c.allies():
            c.temp_hp(gift, on=ev.attacker)

    c.watch(AttackRolled, paid, until=When.EONT, label=f"{c.ref} tithe")


@power(
    "p7075",
    level=1,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.RADIANT],
    attack=Attack(STR, vs=AC),
)
def p7075(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.str_mod, dtype=DamageType.RADIANT)
        c.grants_advantage(to="allies", until=When.EONT)


@power(
    "p7076",
    level=1,
    cls="cleric",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.RADIANT],
    attack=Attack(WIS, vs=REF),
)
def p7076(c: Cast) -> None:
    """The penalty is an Effect line, so it lands whether or not the bolt did."""
    if c.strike():
        c.damage("3d6", c.wis_mod, dtype=DamageType.RADIANT)
    c.penalty("damage", 5 + c.cha_mod, until=When.EONT)


@power(
    "p7077",
    level=1,
    cls="cleric",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[*DIVINE_IMPLEMENT, Keyword.ZONE],
    attack=Attack(WIS, vs=WILL),
)
def p7077(c: Cast) -> None:
    """The zone bites only at the start of a turn spent in it -- no clause
    about entering -- so `TurnStart` is the whole of it."""
    if c.strike():
        c.dazed(until=When.SAVE_ENDS)
    if not c.first:
        return
    zone = c.zone(c.area(), label=c.ref, until=When.EONT)

    def began(ev: TurnStart) -> None:
        if ev.ghost or ev.actor not in c.enemies():
            return
        if ev.actor in c.world.zones.occupants(zone):
            c.penalty("attack", 2, on=ev.actor, until=When.EOTNT)

    c.watch(TurnStart, began, until=When.EONT, label=f"{c.ref} glare")


@power(
    "p7078",
    level=1,
    cls="cleric",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[*DIVINE_IMPLEMENT, Keyword.FEAR],
    attack=Attack(WIS, vs=WILL),
)
def p7078(c: Cast) -> None:
    if c.strike():
        c.push(3)
        c.prone()
    if c.first:
        # A blast does not cover the caster's own square, and the printed
        # line names the caster anyway.
        for friend in {c.me, *c.in_squares(c.area(), side="ally")}:
            c.resist(5, until=When.EONT, on=friend)


@power(
    "p7079",
    level=1,
    cls="cleric",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[*DIVINE_WEAPON, Keyword.FORCE],
    attack=Attack(STR, vs=REF),
)
def p7079(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.str_mod, dtype=DamageType.FORCE)
        c.prone()
    else:
        c.half_damage(c.w(1), c.str_mod, dtype=DamageType.FORCE)
    if not c.first:
        return
    who = c.choose(
        sorted({c.me, *c.within(5, side="ally")}), f"{c.ref}: who is shielded"
    )
    if who is None:
        return
    for d in (AC, REF):
        c.bonus(d, 3, on=who, until=When.ENCOUNTER, kind="shield")
    c.note(
        f"{c.ref}: as a minor action you could move the shield to yourself or a "
        "different ally within 5 -- moving a standing bonus is not expressible"
    )


@power(
    "p7080",
    level=1,
    cls="cleric",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.CONJURATION, Keyword.FIRE],
    attack=Attack(STR, vs=REF),
)
def p7080(c: Cast) -> None:
    """The weapon shares the cleric's square, so its swings are rolled from
    his: see the module docstring on why that is also the whole of "when you
    move, the weapon moves with you"."""
    weapon = c.conjure(c.here, label=c.ref, until=When.SUSTAIN, sustain=MINOR)
    if c.strike():
        c.damage(c.w(1), c.str_mod, dtype=DamageType.FIRE)
        c.penalty("attack", 2, until=When.EONT)

    def again() -> None:
        foes = [f for f in c.enemies() if c.adjacent(f)]
        victim = c.choose(sorted(foes), f"{c.ref}: what it strikes") if foes else None
        if victim is not None and c.attack(c.str_, REF, on=victim):
            c.damage(c.w(1), dtype=DamageType.FIRE, on=victim)

    conj = c.world.get(weapon, Conjuration) if weapon else None
    c.on_sustain(c.world.effects.live.get(conj.effect) if conj else None, again)


@power(
    "p7381",
    level=1,
    cls="cleric",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p7381(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.str_mod)
    beside = [a for a in c.within(1, side="ally") if a != c.me]
    if beside:
        c.temp_hp(c.wis_mod, on=c.choose(beside, f"{c.ref}: who is bolstered"))


@power(
    "p7408",
    level=1,
    cls="cleric",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(WIS, vs=WILL),
)
def p7408(c: Cast) -> None:
    """"The bonus increases to +3" is a +3, not a second +1: two power
    bonuses of the same kind do not add, the larger one wins."""
    if not c.strike():
        return
    c.damage("1d8", c.wis_mod, dtype=DamageType.PSYCHIC)
    victim, me = c.target, c.me

    def against(ctx: dict) -> bool:
        return ctx.get("target") == victim

    def give(value: int) -> None:
        for friend in c.allies():
            c.bonus(
                "attack", value, on=friend, until=When.EONT,
                kind="power", when=against,
            )

    give(1)

    def stung(ev: AttackDeclared) -> None:
        if ev.attacker == victim and ev.target == me:
            give(3)

    c.watch(
        AttackDeclared, stung, until=When.EONT, on=c.me,
        once=True, label=f"{c.ref} spite",
    )


@power(
    "p7887",
    level=1,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.RADIANT, Keyword.ZONE],
    attack=Attack(STR, vs=AC),
)
def p7887(c: Cast) -> None:
    """The zone is a close burst 2 around the cleric, not the row's own melee
    reach, so its squares are measured rather than taken from `c.area()`."""
    if not c.strike():
        return
    c.damage(c.w(1), c.str_mod, dtype=DamageType.RADIANT)
    zone = c.zone(spread({c.here}, 2), label=c.ref, until=When.EONT)
    mine = {c.me, *c.allies()}
    _hold_while_inside(
        c,
        zone,
        When.EONT,
        lambda who: who in mine,
        lambda who: [c.bonus(AC, 2, on=who, until=When.EONT, kind="power")],
    )


@power(
    "p8286",
    level=1,
    cls="cleric",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.HEALING],
    attack=Attack(WIS, vs=REF, plus=2),
)
def p8286(c: Cast) -> None:
    if not c.strike():
        return
    victim, gift, paid = c.target, 2 + c.cha_mod, []
    for d in DEFENCES:
        c.penalty(d, 2, until=When.EONT)

    def reward(ev: Hit) -> None:
        if paid or ev.target != victim or ev.attacker not in c.allies():
            return
        paid.append(True)
        c.heal(gift, on=ev.attacker)

    c.watch(Hit, reward, until=When.EONT, label=f"{c.ref} reward")


def _healing_row_this_turn(c: Cast) -> bool:
    """Has this caster used a healing row since its turn began?

    The printed condition names one particular row, and the name is the one
    thing this project may not resolve, so the nearest thing that can be
    said is the mechanical one: a row of the caster's own carrying the
    healing keyword, this turn. See the report.
    """
    for ev in reversed(c.world.bus.log):
        if ev.kind == "TurnStart" and getattr(ev, "actor", None) == c.me:
            return False
        if ev.kind != "PowerUsed" or getattr(ev, "actor", None) != c.me:
            continue
        p = get(getattr(ev, "power", ""))
        if p is not None and Keyword.HEALING in p.keywords:
            return True
    return False


@power(
    "p9981",
    level=1,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.FIRE, Keyword.RADIANT],
    attack=Attack(WIS, vs=REF),
)
def p9981(c: Cast) -> None:
    if not c.strike():
        return
    c.damage("2d8", c.wis_mod, dtype=DamageType.FIRE)
    if _healing_row_this_turn(c):
        c.damage(c.cha_mod, dtype=DamageType.RADIANT)
    for d in DEFENCES:
        c.penalty(d, 2, until=When.EONT)
