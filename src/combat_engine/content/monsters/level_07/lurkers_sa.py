"""Monster abilities, level 7, lurkers.

Twenty stat blocks, sixty-six rows. Four of the twenty print no ability at
all and have nothing to decorate: m451, m4905, m4922, m718.

Conventions, inherited from the level 1-6 lurker sweeps:

* numbers load from `game.db` -- the attack line is written exactly as
  printed and the damage line goes in the header as data;
* a **trait** costs no action, has no target, and arms the watches that
  hold it, whatever the compendium's column claims;
* a printed range band such as "5/10" takes the normal (first) number;
* a close burst or blast whose card names no target set takes **enemies**,
  except where it says "creatures in the burst" outright;
* `half_on_miss=True` is card data only -- a Miss line is also written as
  `else: c.hit(half=True)`.

Lurkers lean on concealment, invisibility and combat-advantage riders, and
this file leans hard on `level_01..06/lurkers_sa.py`: `_edge_damage`,
`_recharge_when_using`, `_triggering_enemy`, `_vanish_until_it_swings`,
`_secondary`, `_crit_line` and `_ridden_by`.

One name-shaped leak, written around rather than copied: m6077's own body
text names "m4791" where every other sentence on the card says "m6077" --
read as the same creature throughout, matched by `Ident.ref` and never by
the stray word. m963a4's "x0_27" is a ritual's own ref, not a name, and is
safe to read as what it is.

m1825a2/a3 are the one pair here that cannot be written at all: "use the
m5288 stat block instead of the m1825's" has no verb -- there is nothing
that swaps which block drives a creature mid-fight -- so both are `todo=`.
"""

from __future__ import annotations

from combat_engine.content.monsters.level_01.brutes_sa import _crit_line
from combat_engine.content.monsters.level_02.lurkers_sa import (
    _recharge_when_using,
    _triggering_enemy,
)
from combat_engine.content.monsters.level_02.skirmishers_sa import _melee_only
from combat_engine.content.monsters.level_02.soldiers_sa import _ref_of
from combat_engine.content.monsters.level_03.skirmishers import _vanish_until_it_swings
from combat_engine.content.monsters.level_03.soldiers_sa import _secondary
from combat_engine.engine import (
    AC,
    AT_WILL,
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
    STANDARD,
    WILL,
    ActionType,
    Attack,
    Cast,
    CloseBurst,
    Condition,
    Damage,
    DamageType,
    Effect,
    Keyword,
    Melee,
    Movement,
    Position,
    Ranged,
    UpTo,
    Usage,
    When,
    World,
    get,
    power,
    spread,
)
from combat_engine.engine.events import Bloodied, Dropped, Hit, Miss, Moved, TurnStart
from combat_engine.engine.monster_math import LIMITED, MINION
from combat_engine.engine.query import distance_between, has_combat_advantage, moving_as
from combat_engine.engine.triggers import Trigger, about_me

# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------


def _physical(ctx: dict) -> bool:
    """"Melee and ranged attacks" -- a burst or blast does not qualify."""
    row = get(str(ctx.get("power") or ""))
    return row is not None and row.reach.kind in ("melee", "ranged")


def _underground(world: World, eid: int) -> bool:
    return moving_as(world, eid, "burrow")


def _aboveground(world: World, eid: int) -> bool:
    return not _underground(world, eid)


# ==========================================================================
# m1076
# ==========================================================================


@power(
    "m1076a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d4", 5),
)
def m1076a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1076a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d8", 5),
)
def m1076a1(c: Cast) -> None:
    """The venom worsens on each failed save and keeps its ongoing burn
    through every stage, which is why "does not wake a sleeping creature"
    has nowhere to go wrong: nothing here ever wakes one up in the first
    place. "1 hour or until woken" is read as save-ends, the same
    simplification an open-ended real-time duration always takes."""
    victim = c.target
    if not c.strike():
        return
    c.hit()
    if victim is None or not _secondary(c, 10, FORT, victim):
        return
    stage = {"n": 0}

    def worsen(eff: Effect) -> None:
        stage["n"] += 1
        c.world.effects.end(eff, "the venom worsened")
        if stage["n"] == 1:
            c.condition(
                Condition.IMMOBILIZED, until=When.SAVE_ENDS, on=victim,
                ongoing=(5, DamageType.POISON), escalate=worsen,
            )
        else:
            c.condition(
                Condition.UNCONSCIOUS, until=When.SAVE_ENDS, on=victim,
                ongoing=(5, DamageType.POISON),
            )

    c.condition(
        Condition.SLOWED, until=When.SAVE_ENDS, on=victim,
        ongoing=(5, DamageType.POISON), escalate=worsen,
    )


@power(
    "m1076a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ILLUSION],
)
def m1076a2(c: Cast) -> None:
    _vanish_until_it_swings(c, When.EONT)


@power(
    "m1076a3",
    level=7,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="the m1076 is first bloodied",
    on=Trigger(Bloodied, about_me, "it is first bloodied"),
)
def m1076a3(c: Cast) -> None:
    c.use_power("m1076a2", on=c.me)


@power("m1076a4", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m1076a4(c: Cast) -> None:
    me = c.me

    def rider(ev: Hit) -> None:
        if ev.attacker != me or ev.target is None:
            return
        if c.is_(Condition.UNCONSCIOUS, on=ev.target) or c.is_(Condition.HELPLESS, on=ev.target):
            c.flat(c.roll("2d6"))
            c.ongoing(5, on=ev.target)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label=c.ref)


# ==========================================================================
# m115772
# ==========================================================================


@power(
    "m115772a0",
    level=7,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.CHARM, Keyword.PSYCHIC],
)
def m115772a0(c: Cast) -> None:
    me = c.me
    ring = c.aura(3, label=f"{c.ref} aura", until=When.ENCOUNTER, on=me)

    def toll(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == me or not c.bloodied(me):
            return
        if ev.actor not in c.world.zones.occupants(ring) or not c.can_see(to=ev.actor):
            return
        c.flat(5, dtype=DamageType.PSYCHIC, on=ev.actor)
        if c.is_(Condition.DAZED, on=ev.actor):
            mate = min(
                (f for f in c.enemies() if f != ev.actor),
                key=lambda f: distance_between(c.world, ev.actor, f), default=None,
            )
            if mate is not None:
                c.grant_attack(ev.actor, on=mate)

    c.watch(TurnStart, toll, until=When.ENCOUNTER, on=me, label=f"{c.ref} aura toll")


@power(
    "m115772a1", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET,
)
def m115772a1(c: Cast) -> None:
    me = c.me

    def rider(ev: Hit) -> None:
        if ev.attacker != me or ev.target is None:
            return
        count = len([f for f in c.enemies() if f != ev.target and c.adjacent_to(f, ev.target)])
        if count >= 2:
            c.flat(5, on=ev.target)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m115772a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("4d4", 5),
)
def m115772a2(c: Cast) -> None:
    victim = c.target
    if not c.strike():
        return
    if victim is not None and c.is_hidden(from_=victim):
        c.damage("6d4", 15)
    else:
        c.hit()


@power(
    "m115772a3",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    attack=Attack(vs=WILL, printed=10),
)
def m115772a3(c: Cast) -> None:
    victim = c.target
    if victim is None or c.is_hidden(from_=victim):
        return
    if c.strike():
        c.dazed(until=When.EONT)
    c.invisible(to=victim, on=c.me, until=When.EONT)


# ==========================================================================
# m1485
# ==========================================================================


@power(
    "m1485a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=10),
    damage=Damage("1d6", 1),
)
def m1485a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, on=c.target)


@power("m1485a1", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m1485a1(c: Cast) -> None:
    me = c.me

    def rider(ev: Hit) -> None:
        if ev.attacker != me or ev.target is None:
            return
        if has_combat_advantage(c.world, me, ev.target):
            c.blinded(on=ev.target, until=When.SAVE_ENDS)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label=c.ref)


# ==========================================================================
# m1496
# ==========================================================================


@power(
    "m1496a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d6", 5),
)
def m1496a0(c: Cast) -> None:
    if c.strike():
        c.hit()


def _has_an_opening(world: World, eid: int) -> bool:
    from combat_engine.engine.query import enemies

    return any(has_combat_advantage(world, eid, foe) for foe in enemies(world, eid))


@power(
    "m1496a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d6", 5),
    requires=_has_an_opening,
    requires_text="it must have combat advantage against a target",
)
def m1496a1(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    landed = 0
    for _ in range(2):
        if c.strike(on=victim):
            c.hit(on=victim)
            landed += 1
    if landed == 2:
        c.ongoing(5, on=victim)


@power(
    "m1496a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d4", 5),
)
def m1496a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1496a3",
    level=7,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(1),
    target=NO_TARGET,
    keywords=[Keyword.ZONE],
)
def m1496a3(c: Cast) -> None:
    from combat_engine.content.monsters.level_02.skirmishers_sa import _aura_holds

    me = c.me
    area = spread({c.here}, 1)
    zone = c.zone(area, blocks_sight=True, until=When.EONT, label=c.ref)

    def blind(who: int) -> Effect | None:
        return None if who == me else c.blinded(on=who, until=When.ENCOUNTER)

    _aura_holds(c, zone, blind)


@power("m1496a4", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m1496a4(c: Cast) -> None:
    c.bonus(
        "damage", 0, dice="1d6", on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: bool(ctx.get("advantage")) and _physical(ctx),
    )


@power("m1496a5", level=7, usage=AT_WILL, action=STANDARD, reach=PERSONAL, target=NO_TARGET)
def m1496a5(c: Cast) -> None:
    me = c.me
    c.bonus(AC, 4, on=me, until=When.EOT, when=lambda ctx: bool(ctx.get("opportunity")))
    c.move(4)
    for foe in c.enemies():
        if c.adjacent_to(foe, me):
            c.gains_advantage(lambda _ctx: True, until=When.EONT, on=foe)


@power(
    "m1496a6",
    level=7,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ILLUSION],
)
def m1496a6(c: Cast) -> None:
    c.invisible(until=When.EONT)


# ==========================================================================
# m1801
# ==========================================================================


@power(
    "m1801a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d6", 6),
)
def m1801a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1801a1",
    level=7,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=10),
)
def m1801a1(c: Cast) -> None:
    victim = c.target
    if victim is not None and c.strike():
        c.gains_advantage(lambda _ctx: True, until=When.EONT, on=victim)


@power(
    "m1801a2",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=10),
    damage=Damage("3d6", 8, kind=LIMITED),
)
def m1801a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, on=c.target)


@power(
    "m1801a3",
    level=7,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POLYMORPH],
    out_of_combat=True,
)
def m1801a3(c: Cast) -> None:
    """Deliberately inert: a disguise with no combat reading."""


@power("m1801a4", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m1801a4(c: Cast) -> None:
    c.bonus(
        "damage", 0, dice="2d6", on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: bool(ctx.get("advantage")),
    )


# ==========================================================================
# m1825
# ==========================================================================


@power(
    "m1825a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=10),
    damage=Damage("2d4", 7),
)
def m1825a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1825a1",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=10),
)
def m1825a1(c: Cast) -> None:
    """"Considered to be a statue for the purposes of the m1825a2 ability"
    is the exact clause `c.set_origin` names, for whichever other row
    reads it off this creature's own ref."""
    victim = c.target
    if victim is None or not c.strike():
        return
    stage = {"n": 0}

    def worsen(eff: Effect) -> None:
        stage["n"] += 1
        c.world.effects.end(eff, "the stone spread")
        if stage["n"] == 1:
            c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS, on=victim, escalate=worsen)
        else:
            c.condition(Condition.PETRIFIED, until=When.ENCOUNTER, on=victim)
            c.set_origin("statue", on=victim, until=When.ENCOUNTER)

    c.condition(Condition.SLOWED, until=When.SAVE_ENDS, on=victim, escalate=worsen)


@power(
    "m1825a2",
    level=7,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.become(ref=)",),
)
def m1825a2(c: Cast) -> None:
    """Refused in play: taking on another creature's entire stat block for
    the fight's duration -- swapping which block drives this eid, then
    swapping back -- has no verb. `c.swap` only trades two creatures'
    squares, never their identities."""


@power(
    "m1825a3",
    level=7,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.become(ref=)",),
)
def m1825a3(c: Cast) -> None:
    """Refused in play: fires only once the m1825 has actually taken on
    the m5288 block through m1825a2, which it cannot do -- see there."""


# ==========================================================================
# m1993
# ==========================================================================


@power(
    "m1993a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d10", 6),
)
def m1993a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1993a1",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("2d6", 9, kind=LIMITED),
)
def m1993a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS)


@power(
    "m1993a2",
    level=7,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.merge(move_only=)",),
)
def m1993a2(c: Cast) -> None:
    """"Can take only move actions while merged" has nowhere to go --
    `c.merge` grants a duration and nothing that narrows the action menu.
    The hiding, the resistance and the shift are exact."""
    c.merge(until=When.ENCOUNTER)
    c.resist(20, None, on=c.me, until=When.ENCOUNTER)
    c.shift(3)


# ==========================================================================
# m2614
# ==========================================================================


@power(
    "m2614a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d10", 5),
)
def m2614a0(c: Cast) -> None:
    if c.strike():
        c.hit()


def _adjacent_enemy_bloodied(world: World, me: int, ev: Bloodied) -> bool:
    from combat_engine.engine.query import enemies

    return ev.actor in enemies(world, me) and distance_between(world, me, ev.actor) <= 1


@power(
    "m2614a1",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=FREE,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d10", 8, kind=LIMITED),
    trigger="an adjacent enemy becomes bloodied",
    on=Trigger(Bloodied, _adjacent_enemy_bloodied, "an adjacent enemy becomes bloodied"),
)
def m2614a1(c: Cast) -> None:
    """"Save ends both" is two independent save-ends holds rather than one
    roll clearing both -- the shared-hold machinery bundles a numeric
    modifier or an ongoing burn with a condition, not a combat-advantage
    grant."""
    foe = _triggering_enemy(c)
    if foe is None or not c.strike(on=foe):
        return
    c.hit(on=foe)
    c.ongoing(10, on=foe)
    c.grants_advantage(on=foe, until=When.SAVE_ENDS)


@power(
    "m2614a2",
    level=7,
    usage=AT_WILL,
    once_per_round=True,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("1d6", 5),
)
def m2614a2(c: Cast) -> None:
    """"Can make a Stealth check to become hidden" is checked, not rolled --
    the engine has no opposed Stealth check, so this just hides, the way
    every such clause in the tree already reads."""
    if c.strike():
        c.hit()
        c.slide(2)
        c.prone()
    c.hide()


@power("m2614a3", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m2614a3(c: Cast) -> None:
    me = c.me

    def rider(ev: Hit) -> None:
        if ev.attacker != me or ev.target is None:
            return
        if c.is_hidden(from_=ev.target):
            c.blinded(on=ev.target, until=When.EONT)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m2614a4",
    level=7,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
)
def m2614a4(c: Cast) -> None:
    c.teleport(3)
    c.insubstantial(until=When.SONT)


def _not_bloodied(world: World, eid: int) -> bool:
    from combat_engine.engine.components import Health

    h = world.get(eid, Health)
    return not (h is not None and h.bloodied)


@power(
    "m2614a5",
    level=7,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ILLUSION],
    requires=_not_bloodied,
    requires_text="it must not be bloodied",
)
def m2614a5(c: Cast) -> None:
    c.invisible(until=When.EOT)
    c.move(c.speed_of())


# ==========================================================================
# m3782
# ==========================================================================


@power(
    "m3782a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d8", 6),
)
def m3782a0(c: Cast) -> None:
    if c.strike():
        _crit_line(c, "1d8", 14)


@power(
    "m3782a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d10", 5),
)
def m3782a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power("m3782a2", level=7, usage=AT_WILL, action=STANDARD, reach=Ranged(20), target=UpTo(2))
def m3782a2(c: Cast) -> None:
    c.use_power("m3782a1", on=c.target)


@power("m3782a3", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m3782a3(c: Cast) -> None:
    me = c.me

    def stay_hidden(ev: Miss) -> None:
        if ev.attacker != me:
            return
        row = get(ev.power or "")
        if row is not None and row.reach.kind == "ranged":
            c.hide()

    c.watch(Miss, stay_hidden, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m3782a4",
    level=7,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POLYMORPH],
    dropped=("c.phasing(porous=)",),
)
def m3782a4(c: Cast) -> None:
    """Entering a porous obstacle a solid one would block is the clause
    with nowhere to go -- `c.phasing` passes through creatures and solid
    terrain alike and has no narrower "only the porous kind" of its own.
    The insubstantial form, the hover and the sustain are exact."""
    me = c.me
    held = c.insubstantial(on=me, until=When.SUSTAIN)
    c.hover(8, on=me, until=When.SUSTAIN, sustain=STANDARD)
    phase = c.phasing(on=me, until=When.SUSTAIN)
    if held is not None:
        c.on_sustain(held, lambda: None)
    if phase is not None:
        c.on_sustain(phase, lambda: None)


@power(
    "m3782a5",
    level=7,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
)
def m3782a5(c: Cast) -> None:
    c.teleport(5)


# ==========================================================================
# m5324
# ==========================================================================


@power("m5324a0", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5324a0(c: Cast) -> None:
    c.bonus(
        "damage", 0, dice="1d6", on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: c.bloodied(on=ctx.get("target")),
    )


@power(
    "m5324a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d4", 4),
)
def m5324a1(c: Cast) -> None:
    victim = c.target
    if not c.strike():
        return
    c.hit()
    if victim is None:
        return
    if c.is_(Condition.DAZED, on=victim):
        c.ongoing(15, on=victim)
        for which in (AC, FORT, REF, WILL):
            c.penalty(which, 5, on=c.me, until=When.SONT)
    else:
        c.ongoing(5, on=victim)


@power(
    "m5324a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=10),
)
def m5324a2(c: Cast) -> None:
    """"Requires a bell" is equipment, not tracked, the same simplification
    every held-item prerequisite already gets."""
    if c.strike():
        c.pull(5)
        c.dazed(until=When.EONT)


# ==========================================================================
# m5560
# ==========================================================================


@power("m5560a0", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5560a0(c: Cast) -> None:
    me = c.me

    def dug(ev: Moved) -> None:
        if ev.actor != me:
            return
        pos = c.world.get(me, Position)
        squares_ = {s for s in (ev.from_, pos.square if pos else None) if s is not None}
        if squares_:
            c.zone(squares_, difficult=True, until=When.ENCOUNTER, label=c.ref)

    c.watch(Moved, dug, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m5560a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d10", 4),
)
def m5560a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5560a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    requires=_aboveground,
    requires_text="it must be aboveground",
)
def m5560a2(c: Cast) -> None:
    c.shift(1)
    mv = c.world.get(c.me, Movement)
    c.move(mv.modes.get("burrow", 0) if mv is not None else 0, at="burrow")


@power(
    "m5560a3",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    no_provoke=True,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("4d10", 8, kind=LIMITED),
    requires=_underground,
    requires_text="it must be underground",
)
def m5560a3(c: Cast) -> None:
    """The attack fires once, at the end of the whole move, rather than on
    the first square aboveground specifically -- the same simplification
    `c.overrun`'s own callers already take for a trampling move that hits
    partway through."""
    _recharge_when_using(c, "m5560a2")
    mv = c.world.get(c.me, Movement)
    c.move(mv.modes.get("burrow", 0) if mv is not None else 0, at="burrow")
    if mv is not None:
        mv.using = ""
    if c.strike():
        c.hit()


# ==========================================================================
# m5579
# ==========================================================================


@power(
    "m5579a0", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET,
    keywords=[Keyword.FEAR],
)
def m5579a0(c: Cast) -> None:
    me = c.me
    ring = c.aura(2, label=f"{c.ref} aura", until=When.ENCOUNTER, on=me)
    for foe in c.enemies():
        c.penalty(
            "save", 2, on=foe, until=When.ENCOUNTER,
            when=lambda ctx, f=foe: (
                f in c.world.zones.occupants(ring)
                and not c.is_kind("undead", on=f)
                and not c.is_kind("construct", on=f)
            ),
        )


@power(
    "m5579a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=11),
)
def m5579a1(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.ongoing(5, DamageType.NECROTIC, on=victim)
        c.slowed(until=When.EOTNT, on=victim)


# ==========================================================================
# m5735
# ==========================================================================


@power("m5735a0", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5735a0(c: Cast) -> None:
    me = c.me
    acted: set[int] = set()

    def mark(ev: TurnStart) -> None:
        if not ev.ghost:
            acted.add(ev.actor)

    c.watch(TurnStart, mark, until=When.ENCOUNTER, on=me, label=f"{c.ref} roll")
    c.bonus(
        "damage", 0, dice="1d10", on=me, until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("target") not in acted,
    )


@power(
    "m5735a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d6", 8),
)
def m5735a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5735a2",
    level=7,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=10),
    damage=Damage("3d6", 5, kind=LIMITED, half_on_miss=True),
)
def m5735a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.blinded(until=When.EONT)
    else:
        c.hit(half=True)


@power(
    "m5735a3", level=7, usage=AT_WILL, once_per_round=True, action=MOVE, reach=PERSONAL,
    target=NO_TARGET, keywords=[Keyword.ILLUSION],
)
def m5735a3(c: Cast) -> None:
    c.shift(1)
    c.move(c.speed_of())
    if all(c.distance(to=foe) >= 3 for foe in c.enemies()):
        _vanish_until_it_swings(c, When.SONT)


# ==========================================================================
# m6077
# ==========================================================================


@power("m6077a0", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m6077a0(c: Cast) -> None:
    c.bonus(AC, 2, on=c.me, until=When.ENCOUNTER, when=lambda ctx: bool(c.grabbing()))
    c.bonus(REF, 2, on=c.me, until=When.ENCOUNTER, when=lambda ctx: bool(c.grabbing()))


@power(
    "m6077a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("", 6, kind=MINION),
)
def m6077a1(c: Cast) -> None:
    """"The m4791" in the raw text names this creature's own kind
    ("m6077") under a mismatched ref -- read as itself throughout, per the
    module docstring. While already grabbing somebody it can only swing at
    that one and hits automatically; the collective drain pays out once a
    turn no matter how many of its kind are grabbing, off the lowest eid
    among them, the shape `m1033a1` settled two levels down. "Escape DC 16"
    has nowhere to go, the usual simplification."""
    me = c.me
    held = c.grabbing()
    victim = held[0] if held else c.target
    if victim is None:
        return
    if held:
        c.hit(on=victim)
    else:
        if not c.strike(on=victim):
            return
        c.hit(on=victim)
    c.grab(on=victim)

    def toll(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != victim:
            return
        grabbers = [w for w in c.grabbed_by(on=victim) if _ref_of(c, w) == "m6077"]
        if not grabbers or me != min(grabbers):
            return
        c.flat(len(grabbers), on=victim)

    c.watch(TurnStart, toll, until=When.ENCOUNTER, on=me, label=f"{c.ref} drain")


# ==========================================================================
# m946
# ==========================================================================


@power(
    "m946a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d6", 4),
)
def m946a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m946a1",
    level=7,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    attack=Attack(vs=REF, printed=10),
    damage=Damage("1d6", 4, kind=LIMITED),
)
def m946a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS)


@power("m946a2", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m946a2(c: Cast) -> None:
    c.bonus(
        "damage", 0, dice="2d6", on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: bool(ctx.get("advantage")) and _melee_only(ctx),
    )


@power(
    "m946a3", level=7, usage=AT_WILL, action=MINOR, reach=PERSONAL, target=NO_TARGET,
    keywords=[Keyword.ILLUSION],
)
def m946a3(c: Cast) -> None:
    if all(c.distance(to=foe) > 3 for foe in c.enemies()):
        c.invisible(until=When.EONT)


# ==========================================================================
# m963
# ==========================================================================


@power(
    "m963a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=10),
    damage=Damage("1d6", 6, dtype=DamageType.NECROTIC),
)
def m963a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.weakened(until=When.SAVE_ENDS)


@power(
    "m963a1",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR, Keyword.NECROTIC],
    attack=Attack(vs=WILL, printed=10),
)
def m963a1(c: Cast) -> None:
    if c.strike():
        c.push(3)
        c.dazed(until=When.SAVE_ENDS)


@power("m963a2", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m963a2(c: Cast) -> None:
    c.bonus(
        "damage", 0, dice="1d6", dtype=DamageType.NECROTIC, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: bool(ctx.get("advantage")),
    )


@power("m963a3", level=7, usage=ENCOUNTER, action=MOVE, reach=PERSONAL, target=NO_TARGET)
def m963a3(c: Cast) -> None:
    c.shift(6)


@power("m963a4", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m963a4(c: Cast) -> None:
    """The spawn is delayed to the start of this creature's own next turn,
    at the square the victim died in. "Raising the slain creature (using
    the x0_27 ritual) does not destroy the spawned m963" is a ritual's own
    ref, not a name -- and a ritual nothing here casts, so the exception it
    carves out has no combat consequence to test."""
    me = c.me
    pending: list = []

    def slain(ev: Dropped) -> None:
        if ev.source != me or ev.actor is None or not c.is_kind("humanoid", on=ev.actor):
            return
        pos = c.world.get(ev.actor, Position)
        if pos is not None:
            pending.append(pos.square)

    def rise(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me or not pending:
            return
        for square in pending:
            c.summon("m963", at=square)
        pending.clear()

    c.watch(Dropped, slain, until=When.ENCOUNTER, on=me, label=f"{c.ref} mark")
    c.watch(TurnStart, rise, until=When.ENCOUNTER, on=me, label=f"{c.ref} rise")
