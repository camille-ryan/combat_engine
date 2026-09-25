"""Avenger, level 5: daily attacks.

Almost every row here is an attack with an Effect line that outlives it, so
the shape repeats: swing, then arm a watcher on the caster and leave it to
the encounter. Watchers are clocked `on=c.me` throughout -- `Cast._who(None)`
falls to `c.target`, and a hold about the avenger that lives on the creature
it just hit dies with that creature.

`p11039`'s duration ("until you do not make an attack against the target on
your turn") is the only one measured by something other than a clock: the
rounds the avenger pressed the attack are recorded as they happen, and the
whole arrangement is taken down at the end of the first of its turns that
is not in that set.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    DAILY,
    FORT,
    ONE_CREATURE,
    REF,
    STANDARD,
    WILL,
    WIS,
    Attack,
    AttackDeclared,
    AttackRolled,
    Cast,
    DamageType,
    Dropped,
    Hit,
    Keyword,
    Melee,
    Miss,
    Mod,
    MoveEnd,
    Ranged,
    Relation,
    SavingThrow,
    TurnEnd,
    TurnStart,
    When,
    Window,
    get,
    power,
)

from .oath import better_of_two, sworn

DIVINE_WEAPON = [Keyword.DIVINE, Keyword.WEAPON]
DIVINE_IMPLEMENT = [Keyword.DIVINE, Keyword.IMPLEMENT]

_DEFENCES = (AC, FORT, REF, WILL)


def _divine(ctx: dict[str, Any]) -> bool:
    """"Against divine attack powers", read off the row doing the attacking."""
    p = get(ctx.get("power") or "")
    return p is not None and Keyword.DIVINE in p.keywords


@power(
    "p10083",
    level=5,
    cls="avenger",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.NECROTIC],
    attack=Attack(WIS, vs=FORT),
)
def p10083(c: Cast) -> None:
    """The penalty is laid once per turn, not once per swing.

    A save penalty is untyped and untyped penalties stack, so an enemy that
    attacked three times would be at -6 on one saving throw. The round it
    was last charged for is remembered instead.
    """
    victim = c.target
    if c.strike():
        c.damage(c.w(2), c.wis_mod, dtype=DamageType.NECROTIC)
    else:
        c.half_damage(c.w(2), c.wis_mod, dtype=DamageType.NECROTIC)
    if victim is None:
        return
    charged: set[int] = set()

    def falter(ev: AttackDeclared) -> None:
        if ev.attacker != victim or c.turn_of() != victim:
            return
        if c.world.round in charged:
            return
        charged.add(c.world.round)
        c.penalty("save", 2, on=victim, until=When.EOT)

    c.watch(
        AttackDeclared, falter, until=When.ENCOUNTER, on=c.me,
        label=f"{c.ref} faltering",
    )


@power(
    "p10404",
    level=5,
    cls="avenger",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.RADIANT],
    attack=Attack(WIS, vs=WILL),
)
def p10404(c: Cast) -> None:
    """"Your oath of enmity target" narrows which creature may be chosen
    rather than naming a different one, and the header carries no field for
    that -- so the row takes one enemy the ordinary way and the narrowing is
    in the report, which is `fighter/level_1_c.py`'s arrangement.

    The four defence penalties are one effect: "save ends" on a line naming
    all defences is one saving throw, and four calls to `c.penalty` would be
    four.

    The standing half re-reads who is sworn each time a die lands, and only
    fires on a non-melee attack -- the oath's own watcher already covers the
    melee case, and both raising the die would be best of three.
    """
    victim = c.target
    if victim is None:
        return
    me = c.me

    def shaken(until: When) -> None:
        c.world.effects.apply(
            victim,
            me,
            until,
            label=f"{c.ref} defences-2 vs divine",
            mods=[
                (victim, Mod(what=d.value, value=-2, kind="untyped",
                             when=_divine, label=c.ref))
                for d in _DEFENCES
            ],
        )

    if c.strike(on=victim):
        c.damage("3d8", c.wis_mod, dtype=DamageType.RADIANT, on=victim)
        shaken(When.SAVE_ENDS)
    else:
        c.half_damage("3d8", c.wis_mod, dtype=DamageType.RADIANT, on=victim)
        shaken(When.EONT)

    def at_range(ev: AttackRolled) -> None:
        if ev.attacker != me or not sworn(c.world, me, ev.target):
            return
        p = get(ev.power or "")
        if p is None or p.cls != "avenger" or Keyword.IMPLEMENT not in p.keywords:
            return
        if p.reach_of(getattr(ev, "branch", 0)).kind == "melee":
            return
        if any(f != ev.target and c.adjacent(f) for f in c.enemies()):
            return
        better_of_two(c, ev)

    c.watch(
        AttackRolled, at_range, until=When.ENCOUNTER, on=me,
        label=f"{c.ref} sworn at range",
    )


@power(
    "p11039",
    level=5,
    cls="avenger",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.LIGHTNING, Keyword.THUNDER],
    attack=Attack(WIS, vs=AC),
)
def p11039(c: Cast) -> None:
    """The round of this use counts as pressing the attack, so the storm
    survives to the avenger's next turn rather than lapsing at the end of
    the one it was cast on.
    """
    victim = c.target
    if c.strike():
        c.damage(c.w(2), c.wis_mod, dtype=DamageType.LIGHTNING)
    else:
        c.half_damage(c.w(2), c.wis_mod, dtype=DamageType.LIGHTNING)
    if victim is None or not c.first:
        return
    me, amount = c.me, c.wis_mod
    pressed = {c.world.round}

    def sting(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor == victim or ev.actor not in c.enemies():
            return
        if c.adjacent(ev.actor) or c.adjacent_to(victim, ev.actor):
            c.flat(amount, dtype=DamageType.THUNDER, on=ev.actor)

    def noted(ev: AttackDeclared) -> None:
        if ev.attacker == me and ev.target == victim:
            pressed.add(c.world.round)

    held = [
        c.watch(TurnEnd, sting, until=When.ENCOUNTER, on=me, label=f"{c.ref} storm"),
        c.watch(
            AttackDeclared, noted, until=When.ENCOUNTER, on=me,
            label=f"{c.ref} pressing",
        ),
    ]

    def lapse(ev: TurnEnd) -> None:
        if ev.actor != me or c.world.round in pressed:
            return
        for effect in [*held, clock]:
            c.world.effects.end(effect, "the pursuit lapsed")

    clock = c.watch(TurnEnd, lapse, until=When.ENCOUNTER, on=me, label=f"{c.ref} clock")


@power(
    "p2919",
    level=5,
    cls="avenger",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.ILLUSION],
    attack=Attack(WIS, vs=AC),
)
def p2919(c: Cast) -> None:
    """The save-ends hold sits on the *target*, not on the avenger.

    `c.invisible` puts its effect on whoever is unseen, and a save-ends
    duration is rolled by whoever carries the effect -- so written that way
    the avenger would be rolling to lose its own concealment. The relation
    is the same one either way; only the owner of the hold differs.

    Attacking clears `HIDDEN_FROM` for whoever swung, which is the engine's
    rule and not this row's, so the trick ends at the avenger's next swing
    whatever the save says.
    """
    victim = c.target
    if c.strike():
        c.damage(c.w(2), c.wis_mod)
    else:
        c.half_damage(c.w(2), c.wis_mod)
    if victim is None:
        return

    def briefly() -> None:
        c.invisible(to=victim, on=c.me, until=When.EONT)

    if c.landed:
        c.world.effects.apply(
            victim,
            c.me,
            When.SAVE_ENDS,
            label=f"{c.ref} unseen",
            relations=[(Relation.HIDDEN_FROM, c.me, victim)],
            on_end=[briefly],
        )
    else:
        briefly()


@power(
    "p2920",
    level=5,
    cls="avenger",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.RADIANT],
    attack=Attack(WIS, vs=REF),
)
def p2920(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.damage("2d10", c.wis_mod, dtype=DamageType.RADIANT)
        if victim is not None:
            _sear(c, victim, "1d6", after="1d4")
    else:
        c.half_damage("2d10", c.wis_mod, dtype=DamageType.RADIANT)
        if victim is not None:
            _sear(c, victim, "1d4")


def _sear(c: Cast, victim: int, dice: str, after: str = "") -> None:
    """A rolled extra die on every divine hit, held by a saving throw.

    The die is rolled rather than added as a damage modifier: a modifier is
    a number and this is a die, and it has to land on the *same* blow, so it
    goes in the `Hit` window before the body rolls its own damage.
    """
    me = c.me

    def again() -> None:
        if after:
            _sear(c, victim, after)

    hold = c.world.effects.apply(
        victim, me, When.SAVE_ENDS, label=f"{c.ref} searing {dice}", on_end=[again]
    )

    def bite(ev: Hit) -> None:
        if ev.attacker != me or ev.target != victim:
            return
        p = get(ev.power or "")
        if p is not None and Keyword.DIVINE in p.keywords:
            c.flat(c.roll(dice), dtype=DamageType.RADIANT, on=victim)

    hold.subs.append(c.world.bus.on(Hit, bite, owner=me))


@power(
    "p3599",
    level=5,
    cls="avenger",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.RADIANT],
    attack=Attack(WIS, vs=AC),
)
def p3599(c: Cast) -> None:
    """Cover is worked out from two positions at the moment of the attack
    and is not a state anything can hold, so the first half of the Effect
    line is noted rather than approximated; `ignore_cover` is a flag on one
    swing and this is a standing condition on the creature.
    """
    victim = c.target
    if c.strike():
        c.damage(c.w(2), c.wis_mod, dtype=DamageType.RADIANT)
    else:
        c.half_damage(c.w(2), c.wis_mod, dtype=DamageType.RADIANT)
    if victim is None:
        return
    c.effect(f"{c.ref} exposed", until=When.SAVE_ENDS, on=victim)
    c.note(f"{c.ref}: {victim} draws no cover or concealment against you short of superior")
    c.bonus(
        "attack", 1, on=c.me, until=When.ENCOUNTER, kind="untyped",
        when=lambda ctx: ctx.get("target") == victim,
    )


@power(
    "p3629",
    level=5,
    cls="avenger",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.RADIANT],
    attack=Attack(WIS, vs=FORT),
)
def p3629(c: Cast) -> None:
    """The penalty is a head count taken at the moment of the save, so it is
    written on the `SavingThrow` event rather than as a held modifier: a
    `Mod` carries one number and this one changes as the allies move.

    `SavingThrow` announces its outcome before acting on it and reads it
    back, which is the door the recount goes through.
    """
    victim = c.target
    if c.strike():
        c.damage("1d10", c.wis_mod, dtype=DamageType.RADIANT)
        burn = c.ongoing(10, DamageType.RADIANT)
    else:
        c.half_damage("1d10", c.wis_mod, dtype=DamageType.RADIANT)
        burn = c.ongoing(5, DamageType.RADIANT)
    if victim is None or burn is None:
        return

    def crowd(ev: SavingThrow) -> None:
        if ev.actor != victim:
            return
        pressing = sum(1 for friend in c.allies() if c.adjacent_to(victim, friend))
        if pressing:
            ev.bonus -= pressing
            ev.saved = ev.natural + ev.bonus >= 10

    burn.subs.append(
        c.world.bus.on(SavingThrow, crowd, window=Window.BEFORE, owner=c.me)
    )


@power(
    "p5340",
    level=5,
    cls="avenger",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(WIS, vs=AC),
)
def p5340(c: Cast) -> None:
    """Three printed openings on one saving throw, so all three watchers
    hang off the single hold rather than carrying durations of their own.

    "Shifts" is `MoveEnd`, which says what kind of move it was; `MoveStart`
    fires before the creature has gone anywhere.
    """
    victim = c.target
    if c.strike():
        c.damage(c.w(2), c.wis_mod)
    else:
        c.half_damage(c.w(2), c.wis_mod)
    if victim is None:
        return
    me = c.me
    hold = c.effect(f"{c.ref} open guard", until=When.SAVE_ENDS, on=victim)
    if hold is None:
        return

    def swung(ev: Hit | Miss) -> None:
        if ev.attacker == victim and ev.target == me:
            c.provoke(me, on=victim, why=c.ref)

    def stepped(ev: MoveEnd) -> None:
        if ev.actor == victim and ev.kind_ == "shift":
            c.provoke(me, on=victim, why=c.ref)

    for kind, fn in ((Hit, swung), (Miss, swung), (MoveEnd, stepped)):
        hold.subs.append(c.world.bus.on(kind, fn, owner=me))


@power(
    "p6933",
    level=5,
    cls="avenger",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.NECROTIC],
    attack=Attack(WIS, vs=AC),
)
def p6933(c: Cast) -> None:
    """The surge is an Effect line, so it is offered whether the swing
    landed or not -- which on a miss is a bad bargain and still what the
    row prints.
    """
    if c.strike():
        c.damage(c.w(2), c.wis_mod)
    else:
        c.half_damage(c.w(2), c.wis_mod)
    if c.may("lose a healing surge", who=c.me) and c.spend_surge(on=c.me):
        c.damage(c.w(2), dtype=DamageType.NECROTIC)


@power(
    "p7001",
    level=5,
    cls="avenger",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.FIRE],
    attack=Attack(WIS, vs=AC),
)
def p7001(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.wis_mod)
    c.ongoing(5, DamageType.FIRE)


@power(
    "p7002",
    level=5,
    cls="avenger",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.FEAR],
    attack=Attack(WIS, vs=AC),
)
def p7002(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(3), c.wis_mod)
    else:
        c.half_damage(c.w(3), c.wis_mod)
    if not c.first:
        return

    def cow(ev: TurnStart) -> None:
        if ev.ghost or ev.actor not in c.enemies() or not c.adjacent(ev.actor):
            return
        c.penalty(AC, 2, on=ev.actor, until=When.EOTNT)

    c.watch(TurnStart, cow, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} dread")


@power(
    "p7003",
    level=5,
    cls="avenger",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(WIS, vs=AC),
)
def p7003(c: Cast) -> None:
    """Who is sworn against is asked as each turn ends rather than closed
    over: the oath moves, and the exemption moves with it.
    """
    if c.strike():
        c.damage(c.w(2), c.wis_mod)
    else:
        c.half_damage(c.w(2), c.wis_mod)
    if not c.first:
        return
    me = c.me

    def expose(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor not in c.enemies() or sworn(c.world, me, ev.actor):
            return
        if c.adjacent(ev.actor):
            c.vulnerable(5, until=When.EONT, on=ev.actor)

    c.watch(TurnEnd, expose, until=When.ENCOUNTER, on=me, label=f"{c.ref} laid open")


@power(
    "p7004",
    level=5,
    cls="avenger",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(WIS, vs=AC),
)
def p7004(c: Cast) -> None:
    """`Dropped` rather than `query.enemies`: that filters out the dead, and
    by the time this fires the creature it is asking about is one of them.
    `sworn` reads the hold directly and does not care.
    """
    if c.strike():
        c.damage(c.w(3), c.wis_mod)
    else:
        c.half_damage(c.w(3), c.wis_mod)
    if not c.first:
        return
    me = c.me

    def slip(ev: Dropped) -> None:
        if sworn(c.world, me, ev.actor) and c.may("shift away", who=me):
            c.shift(max(1, c.dex_mod), who=me)

    c.watch(Dropped, slip, until=When.ENCOUNTER, on=me, label=f"{c.ref} on the kill")
