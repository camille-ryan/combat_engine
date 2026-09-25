"""Cleric, level 7: the encounter attacks printed after the first book.

`level_7.py` holds the four that came first; these are the rest.

Three notes apply across the batch.

**The shadow keyword does not exist.** `Keyword` has no member for it and
nothing reads one, so the rows printed with it are declared with the
keywords the engine has.

**A packet of two damage types.** "Lightning and thunder damage" and "cold
and radiant damage" are each one packet, and `DamageType` holds one type;
each is dealt as the first of the two printed rather than as two packets,
which would double it. `paladin/level_3.py` settled that reading.

**Compulsory opportunity attacks** -- two rows print one -- go through
`c.provoke`, which opens the window a controller answers. The engine never
decides what goes in one, so on a board with no policy installed these open
and nobody swings; that is the same limit `m3014a2` is listed for.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.engine import (
    AC,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    ONE_CREATURE,
    REACTION,
    REF,
    STANDARD,
    STR,
    WILL,
    WIS,
    Attack,
    AttackDeclared,
    Cast,
    CloseBurst,
    DamageType,
    Effect,
    Event,
    Gear,
    Health,
    Hit,
    Keyword,
    Melee,
    MeleeOrRanged,
    Miss,
    MoveEnd,
    Powers,
    Ranged,
    Trigger,
    TurnEnd,
    When,
    World,
    distance,
    get,
    power,
    spread,
)
from combat_engine.engine.events import MoveStart
from combat_engine.engine.query import (
    adjacent,
    distance_between,
    enemies,
    squares,
    team,
)

DIVINE_IMPLEMENT = [Keyword.DIVINE, Keyword.IMPLEMENT]
DIVINE_WEAPON = [Keyword.DIVINE, Keyword.WEAPON]


def _simple_weapon(world: World, eid: int) -> bool:
    """"You must use this power with a simple weapon."

    `Weapon` carries a group and a set of properties and **no category**, so
    nothing in the model is marked simple and this is false for everybody
    today. It is written as the property that would say so rather than as a
    guess at which groups are simple -- the mace group holds a military
    weapon too. See the report.
    """
    gear = world.get(eid, Gear)
    weapon = gear.main if gear else None
    return weapon is not None and "simple" in weapon.properties


def _a_bloodied_enemy(world: World, eid: int) -> bool:
    for foe in enemies(world, eid):
        health = world.get(foe, Health)
        if health is not None and health.bloodied:
            return True
    return False


def _flankers_from(c: Cast, stand: tuple[int, int], victim: int) -> list[int]:
    """Which allies would flank `victim` with somebody standing on `stand`.

    Written against a square rather than against the caster, because the row
    that needs it shifts first and wants to know where to shift *to*.
    `query.flanked_by` answers "is it flanked at all", which is a different
    question: this one has to name the partner.
    """
    world = c.world
    space = squares(world, victim)
    out = []
    for mate in c.allies():
        if mate == victim or not adjacent(world, mate, victim):
            continue
        if any(world.grid.flanks(stand, b, space) for b in squares(world, mate)):
            out.append(mate)
    return out


@power(
    "p12640",
    level=7,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[
        *DIVINE_WEAPON,
        Keyword.LIGHTNING,
        Keyword.TELEPORTATION,
        Keyword.THUNDER,
    ],
    attack=Attack(WIS, vs=AC),
    thrown_by_hand=True,
)
def p12640(c: Cast) -> None:
    """A ranged row whose Requirement is a *melee* weapon: that is exactly
    `thrown_by_hand`, which is also the gate `Power.can_branch` reads, so a
    second `requires=` saying the same thing would only hide it.

    The dice are the melee weapon's for the same reason, and `ranged=False`
    says so: `c.w` reaches for a crossbow on a ranged row otherwise.

    The teleport has no printed distance of its own -- it lands beside the
    target, wherever that is -- so the range handed to `c.teleport` is the
    gap actually being crossed rather than a number.
    """
    victim = c.target
    if c.strike():
        c.damage(c.w(2, ranged=False), c.wis_mod, dtype=DamageType.LIGHTNING)
    if victim is None:
        return
    landing = sorted(
        sq
        for sq in spread(squares(c.world, victim), 1)
        if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None
    )
    if not landing:
        return
    who = c.choose(sorted(c.within(5, side="ally")), "who steps in beside it")
    if who is None:
        return
    where = c.choose(landing, "where they arrive")
    if where is None:
        return
    gap = min(distance(sq, where) for sq in squares(c.world, who))
    c.teleport(gap, who=who, to=where)


@power(
    "p12653",
    level=7,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.RADIANT],
    attack=Attack(WIS, vs=AC),
)
def p12653(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.wis_mod, dtype=DamageType.RADIANT)
        c.blinded()


@power(
    "p13712",
    level=7,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(WIS, vs=FORT),
)
def p13712(c: Cast) -> None:
    """The fall is an Effect line, so it happens on a miss too."""
    if c.strike():
        c.damage(c.w(2), c.wis_mod)
    c.prone()


@power(
    "p13945",
    level=7,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.DIVINE, Keyword.HEALING, Keyword.NECROTIC],
    requires=_a_bloodied_enemy,
    requires_text="needs a bloodied enemy",
)
def p13945(c: Cast) -> None:
    """No attack roll at all: the damage simply lands on a bloodied enemy.

    "Bloodied" is a target filter with no header field, so it is declared as
    a Requirement -- is there such a creature at all -- and asked again of
    the one actually chosen.
    """
    victim = c.target
    if victim is None or not c.bloodied(victim):
        return
    c.damage(5, c.wis_mod, dtype=DamageType.NECROTIC)
    health = c.world.get(victim, Health)
    if health is None or health.hp > 0:
        return
    who = c.choose(sorted(c.within(5, side="ally")), "who spends a healing surge")
    if who is not None and c.may("spend a healing surge", who=who):
        c.surge(on=who)


@power(
    "p14238",
    level=7,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.CHARM, Keyword.RADIANT],
    attack=Attack(WIS, vs=WILL),
)
def p14238(c: Cast) -> None:
    """"Within its reach" is read as adjacency: a creature's threatened
    squares are a property of its weapon and `c.threatens` sets them for a
    row that says so, but nothing reads a third party's back out.
    """
    if not c.strike():
        return
    c.damage(c.w(1), c.wis_mod, dtype=DamageType.RADIANT)
    victim = c.target
    if victim is None:
        return
    c.cannot_attack(on=victim, against=c.me, until=When.EONT)

    def defend(ev: AttackDeclared) -> None:
        if ev.target != c.me or ev.attacker == victim:
            return
        if adjacent(c.world, victim, ev.attacker):
            c.provoke(victim, on=ev.attacker, why=c.ref)

    c.watch(
        AttackDeclared, defend, until=When.EONT, on=victim, label=f"{c.ref} compels"
    )


@power(
    "p14251",
    level=7,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.PSYCHIC],
    attack=Attack(WIS, vs=AC),
)
def p14251(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.wis_mod, dtype=DamageType.PSYCHIC)
        c.dazed()


@power(
    "p14264",
    level=7,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.COLD, Keyword.DIVINE, Keyword.RADIANT],
)
def p14264(c: Cast) -> None:
    """No attack roll: the burst arms each enemy in it and nothing else.

    "Hits or misses" is both outcomes of one attack, so the two watches
    share one latch. Armed separately they would pay twice over two
    attacks, where the printed line is spent by the first.
    """
    victim = c.target
    if victim is None:
        return
    spent: list[bool] = []

    def backlash(ev: Hit | Miss) -> None:
        if spent or ev.attacker != victim:
            return
        if ev.target != c.me and ev.target not in c.allies():
            return
        spent.append(True)
        c.flat(5 + c.wis_mod, dtype=DamageType.COLD, on=victim)

    hold = c.watch(Hit, backlash, until=When.EOTNT, on=victim, label=c.ref)
    hold.subs.append(c.world.bus.on(Miss, backlash, owner=c.me))


@power(
    "p14277",
    level=7,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.HEALING],
    attack=Attack(WIS, vs=AC),
)
def p14277(c: Cast) -> None:
    """The printed shift comes before the attack and is aimed rather than
    left to the decider. With no decider installed `c.shift` takes the
    lowest-sorted square, which on this row throws away both the flank the
    rest of the power is about and, half the time, the attack itself.
    """
    victim = c.target
    if victim is None:
        return
    _step_into_flank(c, victim)
    if not c.strike():
        return
    c.damage(c.w(2), c.wis_mod)
    mates = _flankers_from(c, c.here, victim)
    if not mates:
        return
    friend = c.choose(sorted(mates), "who spends a healing surge")
    if friend is None:
        return
    if c.may("spend a healing surge", who=friend):
        c.surge(on=friend)

    def gate(ctx: dict[str, Any]) -> bool:
        foe = ctx.get("target")
        return foe is not None and friend in _flankers_from(c, c.here, foe)

    for who in (c.me, friend):
        c.bonus("attack", 2, on=who, until=When.EONT, when=gate)


def _step_into_flank(c: Cast, victim: int) -> None:
    space = squares(c.world, victim)
    reach_of_it = spread(space, 1)
    options = [
        sq
        for sq in spread({c.here}, 1)
        if sq != c.here
        and sq in reach_of_it
        and c.world.grid.passable(sq)
        and c.world.grid.occupant(sq) is None
    ]
    better = sorted(sq for sq in options if _flankers_from(c, sq, victim))
    if better:
        c.shift(1, to=better[0])


@power(
    "p14301",
    level=7,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p14301(c: Cast) -> None:
    """The simple-weapon rider is `c.wielding("simple")`, which no weapon in
    the model answers yet; see `_simple_weapon`.

    The two bonuses are different `what`s, so they stack with each other,
    and both are gated on the attack being an opportunity one against this
    target -- `opportunity` and `target` are carried by both the attack and
    the damage context, which is the only reason one gate serves both.
    """
    if c.strike():
        c.damage(c.w(2), c.str_mod)
        if c.wielding("simple"):
            c.damage("1d6")
    victim = c.target
    if victim is None:
        return

    def shifted(ev: MoveEnd) -> None:
        if ev.actor == victim and ev.kind_ == "shift":
            c.provoke(c.me, on=victim, why=c.ref)

    def swung(ev: AttackDeclared) -> None:
        if ev.attacker == victim and ev.target != c.me:
            c.provoke(c.me, on=victim, why=c.ref)

    def gate(ctx: dict[str, Any]) -> bool:
        return bool(ctx.get("opportunity")) and ctx.get("target") == victim

    c.watch(MoveEnd, shifted, until=When.EONT, label=f"{c.ref} watches the shift")
    c.watch(AttackDeclared, swung, until=When.EONT, label=f"{c.ref} watches the swing")
    c.bonus("attack", 4, on=c.me, until=When.EONT, when=gate)
    c.bonus("damage", 4, on=c.me, until=When.EONT, when=gate)


@power(
    "p14302",
    level=7,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(STR, vs=AC, plus=1),
    requires=_simple_weapon,
    requires_text="needs a simple weapon",
)
def p14302(c: Cast) -> None:
    """The escalating bonus bumps the `Mod` objects it already applied
    rather than applying a fresh, larger one each time.

    Two bonuses of the same kind do not add -- the larger wins -- so
    re-applying would work, and would also leave four dead effects on every
    creature in the party. `Mod` is a plain mutable dataclass and `Mods.total`
    reads `value` when the roll is made, so raising it is the whole of it.
    """
    if c.strike():
        extra = 2 if c.wielding("two-handed") else 0
        c.damage(c.w(2), 2 + c.str_mod + extra)
    victim = c.target
    if victim is None:
        return

    def gate(ctx: dict[str, Any]) -> bool:
        return ctx.get("target") == victim

    held = []
    for who in [c.me, *c.allies()]:
        for what in ("attack", "damage"):
            effect = c.bonus(what, 1, on=who, until=When.EONT, when=gate)
            if effect is not None:
                held.extend(mod for _, mod in effect.mods)

    def louder(ev: Hit | Miss) -> None:
        if ev.attacker not in c.enemies():
            return
        near = ev.target == c.me or (
            ev.target in c.allies() and c.distance(ev.target) <= 3
        )
        if not near:
            return
        for mod in held:
            mod.value = min(5, mod.value + 1)

    hold = c.watch(Hit, louder, until=When.EONT, label=f"{c.ref} grows")
    hold.subs.append(c.world.bus.on(Miss, louder, owner=c.me))


@power(
    "p16423",
    level=7,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.CONJURATION, Keyword.PSYCHIC],
    attack=Attack(WIS, vs=AC),
)
def p16423(c: Cast) -> None:
    """"Grants combat advantage **while** adjacent to the spirit" is a hold
    that comes and goes, so it is re-read at the end of every move rather
    than applied once and left standing.

    The bite reads the move from both ends -- who was beside the spirit when
    the move began, and who is not when it stops -- because `MoveEnd` alone
    cannot say what the mover walked away from. Forced movement is not
    willing, so only a walk or a shift counts.
    """
    if c.strike():
        c.damage(c.w(2), c.wis_mod, dtype=DamageType.PSYCHIC)
    victim = c.target
    if victim is None:
        return
    room = sorted(
        sq
        for sq in spread(squares(c.world, victim), 1)
        if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None
    )
    where = c.choose(room, "where the spirit stands")
    if where is None:
        return
    spirit = c.conjure(where, label=c.ref, until=When.EONT, sustain=None)
    if not spirit:
        return
    hold: list[Effect] = []

    def reread() -> None:
        beside_it = c.adjacent_to(spirit, victim)
        if beside_it and not hold:
            granted = c.grants_advantage(on=victim, to="allies", until=When.EONT)
            if granted is not None:
                hold.append(granted)
        elif hold and not beside_it:
            c.world.effects.end(hold.pop(), "no longer beside the spirit")

    reread()
    struck: set[int] = set()
    beside: set[int] = set()

    def began(ev: MoveStart) -> None:
        if ev.kind_ in ("walk", "shift") and c.adjacent_to(spirit, ev.actor):
            beside.add(ev.actor)

    def ended(ev: MoveEnd) -> None:
        gone = ev.actor in beside and not c.adjacent_to(spirit, ev.actor)
        beside.discard(ev.actor)
        if gone and ev.actor not in struck and ev.actor in c.enemies():
            struck.add(ev.actor)
            c.flat(c.con_mod, dtype=DamageType.PSYCHIC, on=ev.actor)
        reread()

    c.watch(MoveStart, began, until=When.EONT, label=f"{c.ref} watches")
    c.watch(MoveEnd, ended, until=When.EONT, label=f"{c.ref} bites")


@power(
    "p3616",
    level=7,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.HEALING, Keyword.RADIANT],
    attack=Attack(WIS, vs=WILL),
)
def p3616(c: Cast) -> None:
    """The surge is the ally's, so the ally is asked. `once` on the watch is
    the printed "first time": it is spent by the hit that pays out, not by
    the first `Hit` of any shape to come past.
    """
    if not c.strike():
        return
    c.damage("2d8", c.wis_mod, dtype=DamageType.RADIANT)
    victim = c.target
    if victim is None:
        return

    def rewarded(ev: Hit) -> None:
        if ev.target != victim or ev.attacker not in c.allies():
            return
        if c.may("spend a healing surge", who=ev.attacker):
            c.surge(on=ev.attacker)

    c.watch(Hit, rewarded, until=When.EONT, once=True, label=c.ref)


@power(
    "p7093",
    level=7,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.LIGHTNING],
    attack=Attack(STR, vs=AC),
)
def p7093(c: Cast) -> None:
    if not c.strike():
        return
    c.damage(c.w(2), c.str_mod, dtype=DamageType.LIGHTNING)

    def arc(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor not in c.enemies():
            return
        friends = [f for f in c.within(5, side="ally") if f != c.me]
        if any(adjacent(c.world, f, ev.actor) for f in friends):
            c.flat(5, dtype=DamageType.LIGHTNING, on=ev.actor)

    c.watch(TurnEnd, arc, until=When.EONT, label=f"{c.ref} arcs")


@power(
    "p7094",
    level=7,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=DIVINE_IMPLEMENT,
    attack=Attack(WIS, vs=WILL),
)
def p7094(c: Cast) -> None:
    """No damage at all -- the whole Hit line is the daze and the penalty."""
    if not c.strike():
        return
    c.dazed()
    c.penalty("attack", c.cha_mod)
    for defence in (AC, FORT, REF, WILL):
        c.penalty(defence, c.cha_mod)


_ENEMY_HITS_US = "an enemy within 5 squares of you hits you or your ally"


def _enemy_hit_us(radius: int) -> Callable[[World, int, Event], bool]:
    """"An enemy within 5 squares hits you or your ally."

    No ready-made predicate says it: `enemy_within` reads the creature the
    event is *about*, which on a `Hit` answers the attacker's side but not
    who was struck, and the printed sentence needs both ends.
    """

    def check(world: World, me: int, ev: Event) -> bool:
        attacker = getattr(ev, "attacker", None)
        victim = getattr(ev, "target", None)
        if attacker is None or victim is None or attacker == me:
            return False
        if team(world, attacker) is team(world, me):
            return False
        if team(world, victim) is not team(world, me):
            return False
        return distance_between(world, me, attacker) <= radius

    return check


@power(
    "p7095",
    level=7,
    cls="cleric",
    usage=ENCOUNTER,
    action=REACTION,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=DIVINE_IMPLEMENT,
    attack=Attack(WIS, vs=FORT),
    trigger=_ENEMY_HITS_US,
    on=Trigger(Hit, when=_enemy_hit_us(5), text=_ENEMY_HITS_US),
)
def p7095(c: Cast) -> None:
    foe = getattr(c.trigger, "attacker", None) or c.target
    if foe is not None and c.strike(on=foe):
        c.blinded(on=foe)


@power(
    "p7096",
    level=7,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.HEALING],
    attack=Attack(STR, vs=WILL),
)
def p7096(c: Cast) -> None:
    """Ten flat hit points and no surge: the printed line spends nothing."""
    if not c.strike():
        return
    c.damage(c.w(2), c.str_mod)
    victim = c.target
    if victim is None:
        return
    spent: list[bool] = []

    def repaid(ev: Hit | Miss) -> None:
        if spent or ev.attacker != victim or ev.target not in c.allies():
            return
        near = sorted(f for f in c.within(5, of=victim, side="ally") if f != c.me)
        if not near:
            return
        spent.append(True)
        who = c.choose(near, "who is healed")
        if who is not None:
            c.heal(10, on=who)

    hold = c.watch(Hit, repaid, until=When.EONT, label=c.ref)
    hold.subs.append(c.world.bus.on(Miss, repaid, owner=c.me))


#: The `group` the later channels are declared under, which is also what
#: `usable` reads to enforce one of them per encounter.
_CHANNEL_GROUP = "channel divinity"


def _used_a_channel(c: Cast) -> bool:
    """"If you've used a Channel Divinity power this encounter."

    Read structurally rather than by naming rows. Two shapes answer to it:
    the later channels carry the printed group in their header, and the two
    the class starts with are its level-0 divine rows -- what
    `features/leaders.py` registers, from before the group existed.
    """
    powers = c.world.get(c.me, Powers)
    if powers is None:
        return False
    for ref in powers.spent:
        row = get(ref)
        if row is None:
            continue
        if row.group == _CHANNEL_GROUP:
            return True
        if row.level == 0 and row.cls == "cleric" and Keyword.DIVINE in row.keywords:
            return True
    return False


@power(
    "p9986",
    level=7,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.FIRE, Keyword.HEALING],
    attack=Attack(STR, vs=AC),
)
def p9986(c: Cast) -> None:
    if not c.strike():
        return
    c.damage(c.w(2), c.str_mod, dtype=DamageType.FIRE)
    if not _used_a_channel(c):
        c.grants_advantage(to="allies")
        c.slowed()
        return
    c.mark()
    near = sorted(f for f in c.within(5, side="ally") if f != c.me)
    who = c.choose(near, "who spends a healing surge") if near else None
    if who is not None and c.may("spend a healing surge", who=who):
        c.surge(on=who)
