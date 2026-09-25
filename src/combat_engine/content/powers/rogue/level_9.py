"""Rogue, level 9: the daily attacks. All three want a light blade.

`p1426` prints "save ends both" over a condition and a damage line, which is
one effect and one saving throw -- applying the two separately would let the
victim shake off half of a thing the book says is one, the trap
`fighter/level_5.py` records.

`p1032`'s standing arrangement fires in the `Window.BEFORE` half of
`AttackDeclared`, which is the only place a "before making a melee attack
against it" rider can happen: by the reaction window the blow has landed.

The rows printed in the later books follow below. Two of them are aimed at
a creature the rogue is hidden from, which is a target filter with no
header field: it is declared as the caster's Requirement -- is there such a
creature at all -- and checked again against each target in the body.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DAILY,
    DEX,
    EACH_ENEMY,
    FORT,
    INTERRUPT,
    ONE_CREATURE,
    REF,
    STANDARD,
    WILL,
    AreaBurst,
    Attack,
    AttackDeclared,
    AttackRolled,
    Cast,
    Condition,
    DamageApplied,
    DamageType,
    Gear,
    Keyword,
    Melee,
    MeleeOrRanged,
    Powers,
    Ranged,
    Relation,
    Trigger,
    Usage,
    When,
    Window,
    World,
    both,
    by_melee,
    distance,
    enemy_within,
    get,
    power,
    spread,
    would_hit_me,
)
from combat_engine.engine.events import AdjacencyGained
from combat_engine.engine.query import has_combat_advantage, hidden_from
from combat_engine.engine.query import squares as squares_of

MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]
MARTIAL_RANGED = [Keyword.MARTIAL, Keyword.WEAPON, Keyword.RANGED]

ROGUE_GROUPS = frozenset({"light blade", "crossbow", "sling"})
MISSILE_GROUPS = frozenset({"crossbow", "sling"})


def _light_blade(world: World, eid: int) -> bool:
    gear = world.get(eid, Gear)
    return bool(gear and gear.main and gear.main.is_light_blade)


def _rogue_weapon(world: World, eid: int) -> bool:
    gear = world.get(eid, Gear)
    return bool(gear and gear.main and gear.main.group in ROGUE_GROUPS)


def _rogue_missile(world: World, eid: int) -> bool:
    """"A crossbow, a light thrown weapon, or a sling" -- the reading
    `level_7.py` settled, since no weapon carries a thrown flag."""
    gear = world.get(eid, Gear)
    weapon = gear.main if gear else None
    if weapon is None:
        return False
    return weapon.group in MISSILE_GROUPS or (
        weapon.is_light_blade and weapon.ranged is not None
    )


def _is_hidden(world: World, eid: int) -> bool:
    return bool(hidden_from(world, eid))


def _herd(c: Cast, victim: int, squares_: int) -> None:
    """Slide the victim to another square beside the rogue, near enough that
    the printed distance covers it."""
    standing = squares_of(c.world, victim)
    room = sorted(
        sq
        for sq in spread({c.here}, 1) - {c.here}
        if sq not in standing
        and c.world.grid.passable(sq)
        and c.world.grid.occupant(sq) is None
        and min(distance(sq, s) for s in standing) <= squares_
    )
    where = c.choose(room, "where the blade steers it")
    if where is not None:
        c.slide(squares_, on=victim, to=where)


@power(
    "p1010",
    level=9,
    cls="rogue",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=FORT),
    requires=_light_blade,
    requires_text="needs a light blade",
)
def p1010(c: Cast) -> None:
    """"If the unconscious target takes any damage, this unconsciousness
    ends" -- a listener hung on the effect itself, so it goes when the sleep
    does rather than outliving it on a clock of its own. The blow that put
    the target under has already been dealt by then.
    """
    if not c.strike():
        c.half_damage(c.w(2), c.dex_mod)
        c.dazed()
        return
    c.damage(c.w(2), c.dex_mod)
    victim = c.target
    sleep = c.unconscious(until=When.SAVE_ENDS)
    if sleep is None or victim is None:
        return

    def roused(ev: DamageApplied) -> None:
        if ev.target == victim and ev.amount > 0:
            c.world.effects.end(sleep, "it took damage")

    sleep.subs.append(c.world.bus.on(DamageApplied, roused))


@power(
    "p1032",
    level=9,
    cls="rogue",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    requires=_light_blade,
    requires_text="needs a light blade",
)
def p1032(c: Cast) -> None:
    """The opening slide is part of the attack line, so it happens whether or
    not the swing lands, and it names its destination: a free slide of three
    would wander, and the printed line says the target ends in a different
    square adjacent to the rogue.

    The standing slide is aimed the same way. Handing it to the decider would
    as soon walk the target out of the reach of the blow it is setting up.
    """
    victim = c.target
    if victim is None:
        return
    _herd(c, victim, 3)
    if c.strike():
        c.damage(c.w(3), c.dex_mod)

    def before(ev: AttackDeclared) -> None:
        row = get(ev.power)
        if ev.attacker != c.me or ev.target != victim or not c.adjacent(victim):
            return
        if row is None or row.reach.kind != "melee":
            return
        if c.may("slide it a square", who=c.me):
            _herd(c, victim, 1)

    c.watch(
        AttackDeclared,
        before,
        until=When.ENCOUNTER,
        window=Window.BEFORE,
        label=c.ref,
    )


@power(
    "p1426",
    level=9,
    cls="rogue",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=FORT),
    requires=_light_blade,
    requires_text="needs a light blade",
)
def p1426(c: Cast) -> None:
    # The ongoing damage is the one place this row reads Strength.
    if not c.strike():
        c.half_damage(c.w(2), c.dex_mod)
        return
    c.damage(c.w(2), c.dex_mod)
    victim = c.target
    if victim is None:
        return
    c.world.effects.apply(
        victim,
        c.me,
        When.SAVE_ENDS,
        label=f"{c.ref} bleeding and open",
        ongoing=(5 + c.str_mod, DamageType.UNTYPED),
        relations=[(Relation.GRANTS_CA_TO, victim, c.me)],
    )


@power(
    "p10771",
    level=9,
    cls="rogue",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=REF),
    requires=_light_blade,
    requires_text="needs a light blade",
)
def p10771(c: Cast) -> None:
    """The Effect line is a move and a jump. A jump is not a thing the model
    does, so neither it nor the combat advantage it would have bought is
    here; what is left is the run."""
    if c.first:
        c.move(c.speed_of())
    if c.strike():
        c.damage(c.w(3), c.dex_mod)
    else:
        c.half_damage(c.w(3), c.dex_mod)


@power(
    "p10772",
    level=9,
    cls="rogue",
    usage=DAILY,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    requires=_is_hidden,
    requires_text="needs a creature you are hidden from",
)
def p10772(c: Cast) -> None:
    if c.target is None or not c.is_hidden(from_=c.target):
        return
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
        c.slide(2)
        c.vulnerable(5)
    else:
        c.half_damage(c.w(2), c.dex_mod)
        c.slide(1)


@power(
    "p10773",
    level=9,
    cls="rogue",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*MARTIAL_WEAPON, Keyword.RELIABLE],
    attack=Attack(DEX, vs=AC),
    requires=_light_blade,
    requires_text="needs a light blade",
)
def p10773(c: Cast) -> None:
    """Reliable is judged on `c.result` once the body is done, so the
    primary's outcome is put back afterwards: two secondary swings going
    wide is not the printed reason to hand the daily back."""
    victim = c.target
    primary = c.strike()
    if primary:
        c.damage(c.w(2), c.dex_mod)
    if victim is not None:
        for _ in range(2):
            if c.attack(c.dex_, AC, on=victim):
                c.damage(0, c.dex_mod, on=victim)
    c.result = primary


@power(
    "p10774",
    level=9,
    cls="rogue",
    usage=DAILY,
    action=INTERRUPT,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=REF),
    requires=_light_blade,
    requires_text="needs a light blade",
    trigger="an enemy adjacent to you hits you with a melee attack",
    on=Trigger(
        AttackRolled,
        both(would_hit_me, by_melee, enemy_within(1)),
        "an enemy adjacent to you hits you with a melee attack",
    ),
)
def p10774(c: Cast) -> None:
    """Raised on the roll, which is where the defence is read again, so the
    +4 reaches the very attack that triggered it. `once=True` spends each
    one when that blow lands or misses."""
    for wall in (AC, FORT, REF, WILL):
        c.bonus(wall, 4, on=c.me, until=When.EOT, once=True)
    if c.target is None:
        return
    c.grants_advantage()
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
    else:
        c.half_damage(c.w(2), c.dex_mod)
    c.prone()


@power(
    "p10775",
    level=9,
    cls="rogue",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=EACH_ENEMY,
    keywords=MARTIAL_RANGED,
    attack=Attack(DEX, vs=AC),
    requires=_is_hidden,
    requires_text="needs creatures you are hidden from",
)
def p10775(c: Cast) -> None:
    """Every target is taken on the first call. Attacking gives a hiding
    creature away for good -- `resolve.attack` clears the whole relation --
    so asking "am I hidden from this one" once per target would answer yes
    for the first and no for every other."""
    if not c.first:
        return
    for foe in sorted(f for f in c.targets if c.is_hidden(from_=f)):
        if c.strike(on=foe):
            c.damage(c.w(1), c.dex_mod, on=foe)
        else:
            c.half_damage(c.w(1), c.dex_mod, on=foe)


@power(
    "p2399",
    level=9,
    cls="rogue",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    requires=_light_blade,
    requires_text="needs a light blade",
)
def p2399(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
        c.push(1)
        c.immobilized(until=When.SAVE_ENDS)
    else:
        c.half_damage(c.w(2), c.dex_mod)
        c.immobilized(until=When.EOTNT)


@power(
    "p2908",
    level=9,
    cls="rogue",
    usage=DAILY,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    requires=_rogue_weapon,
    requires_text="needs a crossbow, a light blade or a sling",
)
def p2908(c: Cast) -> None:
    """"Has not taken an action during this encounter" is `ActionSpent`,
    which `Encounter.spend` is the one door to -- so the log answers it."""
    victim = c.target
    idle = victim is not None and not any(
        e.kind == "ActionSpent" and getattr(e, "actor", None) == victim
        for e in c.world.bus.log
    )
    if c.strike():
        c.damage(c.w(3), c.dex_mod)
        if idle:
            c.damage(c.w(1))
    else:
        c.half_damage(c.w(3), c.dex_mod)


@power(
    "p4491",
    level=9,
    cls="rogue",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=MARTIAL_RANGED,
    attack=Attack(DEX, vs=REF),
    requires=_rogue_missile,
    requires_text="needs a crossbow, a light thrown weapon or a sling",
)
def p4491(c: Cast) -> None:
    """"Save ends both" is one effect and one saving throw, twice over: the
    hold and the burn ride together, and the Aftereffect is the lighter pair
    hung on the first one's `on_end`."""
    victim = c.target
    if not c.strike():
        c.half_damage(c.w(1), c.dex_mod)
        c.slowed(until=When.SAVE_ENDS)
        return
    c.damage(c.w(1), c.dex_mod)
    if victim is None:
        return

    def afterwards() -> None:
        c.world.effects.apply(
            victim, c.me, When.SAVE_ENDS,
            label=f"{c.ref} aftereffect",
            conditions=(Condition.SLOWED,),
            ongoing=(5, DamageType.UNTYPED),
        )

    c.world.effects.apply(
        victim, c.me, When.SAVE_ENDS,
        label=f"{c.ref} slowed and bleeding",
        conditions=(Condition.SLOWED,),
        ongoing=(10, DamageType.UNTYPED),
        on_end=[afterwards],
    )


@power(
    "p4492",
    level=9,
    cls="rogue",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=MARTIAL_RANGED,
    attack=Attack(DEX, vs=REF),
    requires=_rogue_missile,
    requires_text="needs a crossbow, a light thrown weapon or a sling",
)
def p4492(c: Cast) -> None:
    if c.target is None or not c.can_see(c.target):
        return
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
    else:
        c.half_damage(c.w(2), c.dex_mod)


@power(
    "p4493",
    level=9,
    cls="rogue",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=WILL),
    requires=_light_blade,
    requires_text="needs a light blade",
)
def p4493(c: Cast) -> None:
    """The ally's swing is a melee basic, so only an ally that can reach the
    target after the slide is offered it."""
    victim = c.target
    if not c.strike():
        c.half_damage(c.w(2), c.dex_mod)
        return
    c.damage(c.w(2), c.dex_mod)
    if victim is None:
        return
    c.slide(2)
    able = sorted(mate for mate in c.allies() if c.adjacent_to(victim, mate))
    friend = c.choose(able, "who takes the opening") if able else None
    if friend is not None:
        c.grant_attack(friend, on=victim)


@power(
    "p4494",
    level=9,
    cls="rogue",
    usage=DAILY,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    requires=_rogue_weapon,
    requires_text="needs a crossbow, a light blade or a sling",
)
def p4494(c: Cast) -> None:
    """The mark is the ally's -- the relation names it -- but the clock is
    the rogue's, so the effect's source is the rogue and `When.SONT` reads
    the right turn."""
    victim = c.target
    if not c.strike():
        c.half_damage(c.w(3), c.dex_mod)
        return
    c.damage(c.w(3), c.dex_mod)
    if victim is None:
        return
    able = sorted(
        mate
        for mate in c.allies()
        if c.adjacent(mate) or c.adjacent_to(victim, mate)
    )
    friend = c.choose(able, "who claims it") if able else None
    if friend is not None:
        c.world.effects.apply(
            victim, c.me, When.SONT,
            label=f"{c.ref} mark",
            relations=[(Relation.MARKED_BY, friend, victim)],
        )


@power(
    "p4495",
    level=9,
    cls="rogue",
    usage=DAILY,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    requires=_rogue_weapon,
    requires_text="needs a crossbow, a light blade or a sling",
)
def p4495(c: Cast) -> None:
    """"Regain the use of" is `Powers.restore`, which is what spending one
    counts down. The printed line offers the two halves as alternatives, so
    where both are open the choice is asked."""
    victim = c.target
    powers = c.world.get(c.me, Powers)
    mine = [
        ref
        for ref in (powers.known if powers else [])
        if (row := get(ref)) is not None
        and row.usage is Usage.ENCOUNTER
        and row.attack is not None
    ]
    used = [ref for ref in mine if powers is not None and powers.times(ref) > 0]
    exhausted = bool(mine) and len(used) == len(mine)
    opening = victim is not None and has_combat_advantage(c.world, c.me, victim)
    landed = bool(c.strike())
    if landed:
        c.damage(c.w(2), c.dex_mod)
    if landed and opening and (
        not exhausted or c.may("press the advantage instead", who=c.me)
    ):
        c.damage(c.w(2))
    elif exhausted and powers is not None:
        back = c.choose(sorted(used), "which one you find you still have")
        if back is not None:
            powers.restore(back)


@power(
    "p4496",
    level=9,
    cls="rogue",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    requires=_light_blade,
    requires_text="needs a light blade",
)
def p4496(c: Cast) -> None:
    """"Each time the target enters a square adjacent to you" is
    `AdjacencyGained` with the target as the one that moved -- the rogue
    closing the gap itself is not the printed sentence."""
    victim = c.target
    if c.strike():
        c.damage(c.w(3), c.dex_mod)
        c.shift(c.cha_mod if c.cha_mod > 0 else 1)
    else:
        c.half_damage(c.w(3), c.dex_mod)
        c.shift(1)
    if victim is None:
        return

    def closed(ev: AdjacencyGained) -> None:
        arrived = ev.other == c.me and ev.actor == victim and ev.mover == victim
        if arrived and c.may("give ground", who=c.me):
            c.shift(1)

    c.watch(
        AdjacencyGained, closed, until=When.ENCOUNTER, on=c.me,
        label=f"{c.ref} gives ground",
    )


@power(
    "p4497",
    level=9,
    cls="rogue",
    usage=DAILY,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20),
    target=ONE_CREATURE,
    keywords=[*MARTIAL_WEAPON, Keyword.RELIABLE],
    attack=Attack(DEX, vs=REF),
    requires=_rogue_weapon,
    requires_text="needs a crossbow, a light blade or a sling",
)
def p4497(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(3), c.dex_mod)
        c.penalty("attack", 2, until=When.SAVE_ENDS)
