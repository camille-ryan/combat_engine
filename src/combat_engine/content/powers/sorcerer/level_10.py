"""Sorcerer, level 10: utility.

Three rows here read state back that nothing else in the tree asks for.

**p3779** strips resistances and turns each of them into a vulnerability.
`Defences.resist` is a dict of type to amount, and `c.resist(-n, kind)` is
the mirror that takes one away and puts it back when the save lands --
which is why the row can be written at all without a `c.strip` method.

**p5860** raises every burn a creature is carrying. `Effects.of` lists them
and `Effect.ongoing` is the pair; a stronger burn of the same type
supersedes the standing one, which is exactly the printed arithmetic.

**p11834** reads the die off the `AttackResult` riding the `Miss`, not off
the power: `Miss` carries no face of its own.

Six rows of this level are left out; see the report and `docs/blocked.json`.
"""

from __future__ import annotations

from combat_engine.engine import (
    DAILY,
    EACH_ENEMY,
    ENCOUNTER,
    INTERRUPT,
    MINOR,
    MOVE,
    NO_TARGET,
    PERSONAL,
    REACTION,
    SELF,
    WILL,
    AttackDeclared,
    Cast,
    CloseBurst,
    DamageType,
    Defences,
    Effect,
    Event,
    Keyword,
    Miss,
    Trigger,
    When,
    World,
    ZoneEntered,
    get,
    hits_me,
    power,
)
from combat_engine.engine.events import DamageRolled, ZoneExited

ARCANE = [Keyword.ARCANE]

_HIT_BY_ANYTHING = "you are hit by an attack"
_HIT_ON_WILL = "an enemy hits you with an attack that targets Will"
_ELEMENT_LANDS = "you or an ally within 2 squares takes elemental damage"

#: The five types p16246 and p16248 name.
_ELEMENTS = (
    DamageType.ACID,
    DamageType.COLD,
    DamageType.FIRE,
    DamageType.LIGHTNING,
    DamageType.THUNDER,
)


def _aimed_at_my_will(world: World, me: int, ev: Event) -> bool:
    """"An attack that targets Will" -- read off the announcement, which is
    the only event carrying the defence being rolled against."""
    return hits_me(world, me, ev) and getattr(ev, "vs", None) is WILL


def _an_attack_hurt_me(world: World, me: int, ev: Event) -> bool:
    """"You are hit by an attack", read off the blow rather than the landing.

    `hits_me` is no use on `DamageRolled`: that event spells the dealer
    `source`, so the predicate looks for an `attacker` that is not there and
    is silently false. `detail` carrying a real row is what tells an attack
    apart from a burn or a hazard.
    """
    from combat_engine.engine.query import team

    who = getattr(ev, "source", None)
    return (
        getattr(ev, "target", None) == me
        and getattr(ev, "amount", 0) > 0
        and who is not None
        and who != me
        and team(world, who) is not team(world, me)
        and get(getattr(ev, "detail", "")) is not None
    )


def _element_near_me(world: World, me: int, ev: Event) -> bool:
    from combat_engine.engine.query import distance_between, team

    who = getattr(ev, "target", None)
    return (
        who is not None
        and getattr(ev, "amount", 0) > 0
        and getattr(ev, "dtype", None) in _ELEMENTS
        and team(world, who) is team(world, me)
        and distance_between(world, who, me) <= 2
    )


@power(
    "p11834",
    level=10,
    cls="sorcerer",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
)
def p11834(c: Cast) -> None:
    """One of the two always happens, so this is one standing watch with two
    arms rather than two gated bonuses -- which by the larger-wins rule would
    not have added up to either."""
    me = c.me

    def missed(ev: Miss) -> None:
        if ev.attacker != me or ev.target is None:
            return
        result = getattr(ev, "result", None)
        if result is None:
            return
        if result.natural % 2 == 0:
            c.slide(1, on=ev.target)
        else:
            c.bonus(
                "attack", 2, on=me, until=When.EONT, once=True,
                when=lambda ctx, foe=ev.target: ctx.get("target") == foe,
            )

    c.watch(Miss, missed, until=When.ENCOUNTER, on=me, label=f"{c.ref} rebounds")


@power(
    "p16245",
    level=10,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
)
def p16245(c: Cast) -> None:
    """Phasing is granted for the move and no longer -- `c.move` still has to
    stop somewhere legal, which is the printed "you immediately move to an
    unoccupied square nearest your entry point". The tremorsense has nothing
    to sense: sight is a line, not a sense list."""
    c.phasing(on=c.me, until=When.EOT)
    c.move(c.speed_of())


@power(
    "p16246",
    level=10,
    cls="sorcerer",
    usage=DAILY,
    action=INTERRUPT,
    reach=CloseBurst(2),
    target=NO_TARGET,
    keywords=ARCANE,
    trigger=_ELEMENT_LANDS,
    on=Trigger(DamageRolled, when=_element_near_me, text=_ELEMENT_LANDS),
)
def p16246(c: Cast) -> None:
    """Declared on `DamageRolled`, which is the only event that names the
    damage type while the blow is still landing -- and, being an interrupt,
    the resistance is in place before it is read back."""
    kind = getattr(c.trigger, "dtype", None)
    if kind not in _ELEMENTS:
        return
    for who in (c.me, *(f for f in c.allies() if c.distance(f) <= 2)):
        c.resist(10, kind, on=who, until=When.EONT)


@power(
    "p16248",
    level=10,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(10),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.ZONE],
)
def p16248(c: Cast) -> None:
    """Three squares, made as one zone: a zone is a set of squares and three
    of them behave exactly as three one-square zones would.

    The shelter is not a property a zone can carry, so it is handed out on
    arrival and taken away on departure -- `ZoneEntered` and `ZoneExited`
    are both announced, which is what makes that pair writable.
    """
    area = sorted(c.area())
    if not area:
        return
    kind = c.choose(list(_ELEMENTS), f"{c.ref}: which element it turns aside")
    picked = frozenset(area[:3])
    haven = c.zone(picked, label=c.ref, until=When.ENCOUNTER)
    held: dict[int, Effect] = {}

    def shelter(who: int) -> None:
        if who in held or who not in (c.me, *c.allies()):
            return
        got = c.resist(10, kind, on=who, until=When.ENCOUNTER)
        if got is not None:
            held[who] = got

    def expose(who: int) -> None:
        got = held.pop(who, None)
        if got is not None:
            c.world.effects.end(got, "left the zone")

    for who in c.in_squares(picked, side="ally"):
        shelter(who)

    c.watch(
        ZoneEntered,
        lambda ev: shelter(ev.actor) if ev.zone == haven else None,
        until=When.ENCOUNTER, on=c.me, label=f"{c.ref} shelters",
    )
    c.watch(
        ZoneExited,
        lambda ev: expose(ev.actor) if ev.zone == haven else None,
        until=When.ENCOUNTER, on=c.me, label=f"{c.ref} releases",
    )


@power(
    "p3059",
    level=10,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
    trigger=_HIT_BY_ANYTHING,
    on=Trigger(AttackDeclared, when=hits_me, text=_HIT_BY_ANYTHING),
)
def p3059(c: Cast) -> None:
    """Declared on the announcement so the halving is in place before the
    blow it answers -- an interrupt's whole point."""
    c.insubstantial(on=c.me, until=When.EONT)


@power(
    "p3779",
    level=10,
    cls="sorcerer",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=ARCANE,
)
def p3779(c: Cast) -> None:
    """A resistance is taken away by adding its negative, which `c.resist`
    puts back when the save lands -- so "save ends both" comes out of one
    duration on each half rather than needing a way to restore a number the
    row had thrown away."""
    victim = c.target
    if victim is None:
        return
    held = c.world.get(victim, Defences)
    if held is None:
        return
    for kind, amount in sorted(held.resist.items(), key=lambda kv: kv[0].value):
        if amount <= 0:
            continue
        c.resist(-amount, kind, on=victim, until=When.SAVE_ENDS)
        c.vulnerable(5, kind, on=victim, until=When.SAVE_ENDS)


@power(
    "p5283",
    level=10,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.TELEPORTATION],
    trigger=_HIT_BY_ANYTHING,
    on=Trigger(DamageRolled, when=_an_attack_hurt_me, text=_HIT_BY_ANYTHING),
)
def p5283(c: Cast) -> None:
    """The amount rides `DamageRolled` and is read back once the window
    closes, so halving it here is what "you take half damage from the
    attack" comes to."""
    ev = c.trigger
    if ev is not None:
        ev.amount = getattr(ev, "amount", 0) // 2
    c.teleport(c.cha_mod + c.dex_mod)


@power(
    "p5858",
    level=10,
    cls="sorcerer",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
)
def p5858(c: Cast) -> None:
    """"While you are bloodied" is a gate that closes over the caster rather
    than reading the modifier's context, which carries no such thing."""
    me = c.me

    def hurt(_ctx: dict) -> bool:
        return c.bloodied(me)

    c.bonus("attack", 1, on=me, until=When.ENCOUNTER, when=hurt)
    c.bonus("save", c.cha_mod, on=me, until=When.ENCOUNTER, when=hurt)


@power(
    "p5859",
    level=10,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
    trigger=_HIT_ON_WILL,
    on=Trigger(AttackDeclared, when=_aimed_at_my_will, text=_HIT_ON_WILL),
)
def p5859(c: Cast) -> None:
    c.bonus(WILL, 5, on=c.me, until=When.EONT, kind="untyped")
    foe = getattr(c.trigger, "attacker", None)
    if foe is not None:
        c.invisible(to=foe, on=c.me, until=When.EONT)


@power(
    "p5860",
    level=10,
    cls="sorcerer",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=ARCANE,
)
def p5860(c: Cast) -> None:
    """A burn of one type does not stack -- the highest applies -- so raising
    one is applying a stronger burn of the same type, which supersedes what
    is standing and leaves the saving throw where it was."""
    victim = c.target
    if victim is None:
        return
    standing = [
        e.ongoing for e in c.world.effects.of(victim) if e.ongoing is not None
    ]
    for amount, kind in standing:
        c.ongoing(amount + 10, kind, on=victim)
