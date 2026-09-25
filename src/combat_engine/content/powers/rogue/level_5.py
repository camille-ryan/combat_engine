"""Rogue, level 5: the daily attacks.

Two want a light blade at reach 1. The third prints "Melee or Ranged weapon"
over the rogue's own three weapon groups and is `MeleeOrRanged`; Dexterity
attacks on either branch, so there is no second attack line and what differs
is the range, the weapon rolled and whether firing provokes.

Both standing arrangements are Effect lines, so they are armed whether or
not the opening swing landed, and both run to the end of the encounter.

The rows printed in the later books follow below. An **Aftereffect** is a
second hold that begins when the first one ends, which is `on_end` on the
effect rather than `escalate` -- that one runs on a *failed* save.
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
    REACTION,
    REF,
    STANDARD,
    WILL,
    Attack,
    Cast,
    CloseBurst,
    Condition,
    ConditionApplied,
    DamageApplied,
    Gear,
    Hit,
    Keyword,
    Melee,
    MeleeOrRanged,
    Moved,
    MoveEnd,
    Powers,
    Relation,
    Trigger,
    TurnEnd,
    When,
    World,
    both,
    by_melee,
    distance,
    hits_me,
    power,
    spread,
)
from combat_engine.engine.events import AttackDeclared, MoveStart
from combat_engine.engine.query import allies as allies_of
from combat_engine.engine.query import hidden_from
from combat_engine.engine.query import squares as squares_of

MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]

ROGUE_GROUPS = frozenset({"light blade", "crossbow", "sling"})


def _light_blade(world: World, eid: int) -> bool:
    gear = world.get(eid, Gear)
    return bool(gear and gear.main and gear.main.is_light_blade)


def _rogue_weapon(world: World, eid: int) -> bool:
    gear = world.get(eid, Gear)
    return bool(gear and gear.main and gear.main.group in ROGUE_GROUPS)


@power(
    "p543",
    level=5,
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
def p543(c: Cast) -> None:
    """"Immediately after attacking you" is the reaction window of
    `AttackDeclared`, which the whole attack resolves inside -- so a listener
    there runs after the blow has landed, not before it is rolled.

    The shift is a printed *can*, so it is asked rather than taken.
    """
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
    victim = c.target
    if victim is None:
        return

    def retort(ev: AttackDeclared) -> None:
        if ev.target != c.me:
            return
        c.flat(c.dex_mod, on=victim)
        if c.may("shift a square", who=c.me):
            c.shift(1)

    c.on_attack(retort, by=victim, until=When.ENCOUNTER, label="p543")


@power(
    "p981",
    level=5,
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
def p981(c: Cast) -> None:
    # The ongoing damage is the one place this row reads Strength.
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
        c.ongoing(5 + c.str_mod)
    else:
        c.half_damage(c.w(2), c.dex_mod)


@power(
    "p999",
    level=5,
    cls="rogue",
    usage=DAILY,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=FORT),
    requires=_rogue_weapon,
    requires_text="needs a crossbow, a light blade or a sling",
)
def p999(c: Cast) -> None:
    """The arrangement counts squares rather than measuring the two ends of
    the move: a walk that doubles back covers ground the finishing square
    does not show, and "moves more than half its speed" is about the going.

    One action's worth of it, so the tally opens at `MoveStart` and closes at
    `MoveEnd`; being shoved is not the target moving with an action of its
    own, so only a walk counts, and only on its own turn.
    """
    victim = c.target
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
        c.prone()
    else:
        c.half_damage(c.w(2), c.dex_mod)
    if victim is None:
        return

    walking = False
    steps = 0

    def began(ev: MoveStart) -> None:
        nonlocal walking, steps
        if ev.actor == victim:
            walking, steps = ev.kind_ == "walk", 0

    def stepped(ev: Moved) -> None:
        nonlocal steps
        if ev.actor == victim:
            steps += 1

    def ended(ev: MoveEnd) -> None:
        nonlocal walking, steps
        if ev.actor != victim:
            return
        far, was_walking = steps, walking
        walking, steps = False, 0
        if was_walking and c.turn_of() == victim and far * 2 > c.speed_of(victim):
            c.prone(on=victim)

    c.watch(MoveStart, began, until=When.ENCOUNTER, label="p999 sets off")
    c.watch(Moved, stepped, until=When.ENCOUNTER, label="p999 counts")
    c.watch(MoveEnd, ended, until=When.ENCOUNTER, label="p999 stops")


def _gap(c: Cast, victim: int, square: tuple[int, int]) -> int:
    """How far that square is from the creature, footprint and all."""
    return min(distance(square, sq) for sq in squares_of(c.world, victim))


def _step_closer(c: Cast, victim: int) -> None:
    """"You can shift 1 square toward the target." A shift handed to the
    decider would as soon step away, so the options are filtered first."""
    gap = _gap(c, victim, c.here)
    room = sorted(
        sq for sq in c.world.reachable_squares(c.me, 1) if _gap(c, victim, sq) < gap
    )
    if room and c.may("step after it", who=c.me):
        c.shift(to=room[0])


@power(
    "p10171",
    level=5,
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
def p10171(c: Cast) -> None:
    """The hold and the opening are one effect, because the printed line
    ends both together -- "this effect ends if the target ends its turn and
    you are not adjacent to it". The watch hangs on that effect, so it goes
    when the hold does.
    """
    victim = c.target
    if victim is None:
        return
    if not c.strike():
        c.half_damage(c.w(2), c.dex_mod)
        c.world.effects.apply(
            victim, c.me, When.EONT,
            label=f"{c.ref} pinned and open",
            conditions=(Condition.IMMOBILIZED,),
            relations=[(Relation.GRANTS_CA_TO, victim, c.me)],
        )
        return
    c.damage(c.w(2), c.dex_mod)
    hold = c.world.effects.apply(
        victim, c.me, When.ENCOUNTER,
        label=f"{c.ref} pinned and open",
        conditions=(Condition.IMMOBILIZED,),
        relations=[(Relation.GRANTS_CA_TO, victim, c.me)],
    )

    def slipped(ev: TurnEnd) -> None:
        if ev.actor == victim and not c.adjacent(victim):
            c.world.effects.end(hold, "you were not adjacent")

    hold.subs.append(c.world.bus.on(TurnEnd, slipped, owner=c.me))


@power(
    "p10756",
    level=5,
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
def p10756(c: Cast) -> None:
    """The slide names its destination -- a square beside one of the
    target's own allies -- so it is aimed rather than handed to the decider,
    which would as soon throw it somewhere empty."""
    victim = c.target
    if c.strike():
        c.damage(c.w(3), c.dex_mod)
    if victim is None:
        return
    friends = allies_of(c.world, victim)
    standing = squares_of(c.world, victim)
    beside: set[tuple[int, int]] = set()
    for mate in friends:
        beside |= spread(squares_of(c.world, mate), 1)
    room = sorted(
        sq
        for sq in beside - standing
        if c.world.grid.passable(sq)
        and c.world.grid.occupant(sq) is None
        and _gap(c, victim, sq) <= 5
    )
    if room:
        where = c.choose(room, "where it is thrown")
        if where is not None:
            c.slide(5, to=where)
    c.prone()
    for mate in friends:
        if c.adjacent_to(victim, mate):
            c.prone(on=mate)


@power(
    "p10757",
    level=5,
    cls="rogue",
    usage=DAILY,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=FORT),
    requires=_rogue_weapon,
    requires_text="needs a crossbow, a light blade or a sling",
)
def p10757(c: Cast) -> None:
    """The ongoing damage is "equal to any Sneak Attack damage you deal with
    this attack", and the model has no sneak attack -- so it is nothing, and
    what is left is the two damage lines."""
    if c.strike():
        c.damage(c.w(1), c.dex_mod)
    c.damage(c.w(1), c.dex_mod)


@power(
    "p10758",
    level=5,
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
def p10758(c: Cast) -> None:
    """"You do not expend this power" is `Powers.unuse`, the door the
    Reliable keyword goes through. The Aftereffect hangs on the first hold's
    `on_end`, so it begins when that hold goes, whichever way it went.
    """
    victim = c.target
    unseen = victim is not None and c.is_hidden(from_=victim)
    if not c.strike():
        if unseen:
            powers = c.world.get(c.me, Powers)
            if powers is not None:
                powers.unuse(c.ref)
        return
    c.damage(c.w(2), c.dex_mod)
    if victim is None:
        return

    def afterwards() -> None:
        def bite(ev: DamageApplied) -> None:
            if ev.source == c.me and ev.target == victim and ev.amount > 0:
                c.penalty("attack", 2, on=victim, until=When.EONT)
                c.rooted(on=victim, until=When.EONT)

        c.watch(
            DamageApplied, bite, until=When.ENCOUNTER, on=c.me,
            label=f"{c.ref} aftereffect",
        )

    c.world.effects.apply(
        victim, c.me, When.EONT,
        label=f"{c.ref} blinded and rooted",
        conditions=(Condition.BLINDED, Condition.ROOTED),
        on_end=[afterwards],
    )


@power(
    "p10759",
    level=5,
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
def p10759(c: Cast) -> None:
    """"Knocked prone and cannot stand up (save ends)" is two clocks on one
    creature, which is what `held=` is for."""
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
    c.prone(held=When.SAVE_ENDS)


@power(
    "p10760",
    level=5,
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
def p10760(c: Cast) -> None:
    victim = c.target
    if c.first and victim is not None and c.is_hidden(from_=victim) and c.int_mod > 0:
        unseeing = sorted(hidden_from(c.world, c.me))
        c.shift(c.int_mod)
        for watcher in unseeing:
            c.hide(from_=watcher)
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
        if c.int_mod > 0:
            c.shift(c.int_mod)
    else:
        c.half_damage(c.w(2), c.dex_mod)


@power(
    "p10761",
    level=5,
    cls="rogue",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=WILL),
)
def p10761(c: Cast) -> None:
    """"Against your attacks" is a gate on the attacker, which the defence
    context carries."""
    victim, me = c.target, c.me
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
        until = When.ENCOUNTER
    else:
        c.half_damage(c.w(2), c.dex_mod)
        until = When.SAVE_ENDS
    if victim is None:
        return

    def mine(ctx: dict) -> bool:
        return ctx.get("attacker") == me

    for wall in (AC, FORT, REF, WILL):
        c.penalty(wall, 3, on=victim, until=until, when=mine)


@power(
    "p2266",
    level=5,
    cls="rogue",
    usage=DAILY,
    action=REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    requires=_light_blade,
    requires_text="needs a light blade",
    trigger="an enemy makes a melee attack against you",
    on=Trigger(
        AttackDeclared,
        both(hits_me, by_melee),
        "an enemy makes a melee attack against you",
    ),
)
def p2266(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
    if c.target is not None:
        c.grants_advantage(to="allies")


@power(
    "p2286",
    level=5,
    cls="rogue",
    usage=DAILY,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20),
    target=ONE_CREATURE,
    keywords=[*MARTIAL_WEAPON, Keyword.FEAR],
    attack=Attack(DEX, vs=WILL),
    requires=_rogue_weapon,
    requires_text="needs a crossbow, a light blade or a sling",
)
def p2286(c: Cast) -> None:
    """The target moves under its own power, avoiding what it can, which is
    `c.flee` rather than a push -- and the difference is that it provokes."""
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
        c.flee(c.cha_mod)
    else:
        c.flee(1)


@power(
    "p2521",
    level=5,
    cls="rogue",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=REF),
    requires=_light_blade,
    requires_text="needs a light blade",
)
def p2521(c: Cast) -> None:
    if c.target is None or not c.can_see(c.target):
        return
    if c.strike():
        c.damage(c.w(1), c.dex_mod)
    c.prone()


@power(
    "p4480",
    level=5,
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
def p4480(c: Cast) -> None:
    """Two attacks against one creature, each with its own push and step."""
    victim = c.target
    if victim is None:
        return
    landed = 0
    for _ in range(2):
        if c.strike():
            landed += 1
            c.damage(c.w(1), c.dex_mod)
        else:
            c.half_damage(c.w(1), c.dex_mod)
        c.push(1)
        _step_closer(c, victim)
    if landed == 2:
        c.prone()


@power(
    "p4481",
    level=5,
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
def p4481(c: Cast) -> None:
    """The standing arrangement is an Effect line, so a miss leaves it
    behind, and it is armed after the opening swing so that swing does not
    pay twice."""
    victim = c.target
    fresh = victim is not None and not c.bloodied(victim)
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
        if fresh:
            c.damage(c.w(1))
        c.slowed(until=When.SAVE_ENDS)
    if victim is None:
        return

    def again(ev: Hit) -> None:
        if ev.attacker == c.me and ev.target == victim:
            c.slowed(on=victim, until=When.SAVE_ENDS)

    c.watch(Hit, again, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} slows again")


@power(
    "p4482",
    level=5,
    cls="rogue",
    usage=DAILY,
    action=INTERRUPT,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    requires=_light_blade,
    requires_text="needs a light blade",
    trigger="an enemy attacks you",
    on=Trigger(AttackDeclared, hits_me, "an enemy attacks you"),
)
def p4482(c: Cast) -> None:
    """An interrupt runs before the triggering attack is rolled, so the two
    negations are armed rather than undone: the condition is ended the
    moment that attack applies it, and the shortening is a standing
    `resist_forced` for the rest of the turn.
    """
    me = c.me
    attacker = getattr(c.trigger, "attacker", None)

    def undo(ev: ConditionApplied) -> None:
        if ev.target != me or ev.source != attacker:
            return
        if ev.condition not in (Condition.PRONE, Condition.SLOWED):
            return
        for effect in list(c.world.effects.of(me)):
            if ev.condition in effect.conditions and effect.source == attacker:
                c.world.effects.end(effect, c.ref)

    c.watch(
        ConditionApplied, undo, until=When.EOT, on=c.me, label=f"{c.ref} negates"
    )
    c.resist_forced(c.dex_mod, on=c.me, until=When.EOT)
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
    else:
        c.half_damage(c.w(2), c.dex_mod)
