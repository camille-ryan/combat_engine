"""Swordmage, level 5: the dailies.

Two engine notes earned here. Ongoing damage of one type does not stack, so
`p5747`'s splash hangs off the burn it already applied rather than trying to
lay a second one. And "the target's attacks deal half damage to your allies"
is narrower than `weakened`, which halves everything against everybody -- so
it is written on `DamageRolled`, where both ends of the blow are known.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DAILY,
    FORT,
    INT,
    ONE_CREATURE,
    REF,
    STANDARD,
    WILL,
    Attack,
    Cast,
    CloseBurst,
    DamageApplied,
    DamageRolled,
    DamageType,
    Keyword,
    Melee,
    Ranged,
    SavingThrow,
    UpTo,
    When,
    Window,
    power,
)

from . import beside

ARCANE_WEAPON = [Keyword.ARCANE, Keyword.WEAPON]
ARCANE_IMPLEMENT = [Keyword.ARCANE, Keyword.IMPLEMENT]

_ELEMENTS = [
    DamageType.ACID,
    DamageType.COLD,
    DamageType.FIRE,
    DamageType.LIGHTNING,
    DamageType.THUNDER,
]
_ALL_KINDS = [
    *_ELEMENTS,
    DamageType.FORCE,
    DamageType.NECROTIC,
    DamageType.POISON,
    DamageType.PSYCHIC,
    DamageType.RADIANT,
]


@power(
    "p10431",
    level=5,
    cls="swordmage",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(INT, vs=WILL),
)
def p10431(c: Cast) -> None:
    """Both the Aftereffect and the free blink hang on the saving throw,
    which is the one event that says the hold was shaken off."""
    victim = c.target
    me = c.me
    if c.strike():
        c.damage("2d8", c.int_mod, dtype=DamageType.PSYCHIC)
        c.immobilized(until=When.SAVE_ENDS)
        after = True
    else:
        c.half_damage("2d8", c.int_mod, dtype=DamageType.PSYCHIC)
        c.slowed(until=When.SAVE_ENDS)
        after = False

    def shaken(ev: SavingThrow) -> None:
        if ev.actor != victim:
            return
        if ev.saved and after:
            c.slowed(until=When.SAVE_ENDS, on=victim)
        if c.may("follow", who=me):
            spot = beside(c, victim)
            if spot is not None:
                c.teleport(10, who=me, to=spot)

    c.watch(SavingThrow, shaken, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "p3340",
    level=5,
    cls="swordmage",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*ARCANE_WEAPON, Keyword.COLD],
    attack=Attack(INT, vs=FORT),
)
def p3340(c: Cast) -> None:
    """"Moves adjacent to, or starts its turn adjacent to" with a once-a-turn
    latch is exactly what an aura with teeth already is."""
    if c.strike():
        c.damage(c.w(2), c.int_mod)
    ring = c.aura(1, on=c.target, until=When.ENCOUNTER, label=c.ref)
    c.burns(ring, "1d10", DamageType.COLD)


@power(
    "p3342",
    level=5,
    cls="swordmage",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=ARCANE_WEAPON,
    attack=Attack(INT, vs=AC),
)
def p3342(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(), c.int_mod)
    kind = c.choose(_ELEMENTS, "the wound opens to")
    if kind is not None:
        c.vulnerable(5, kind, until=When.ENCOUNTER)


@power(
    "p3343",
    level=5,
    cls="swordmage",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=UpTo(3),
    keywords=[*ARCANE_IMPLEMENT, Keyword.LIGHTNING],
    attack=Attack(INT, vs=REF),
)
def p3343(c: Cast) -> None:
    if c.strike():
        c.damage("1d8", c.int_mod)
        c.ongoing(5, DamageType.LIGHTNING)
    else:
        c.half_damage("1d8", c.int_mod)


@power(
    "p3922",
    level=5,
    cls="swordmage",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*ARCANE_WEAPON, Keyword.TELEPORTATION],
    attack=Attack(INT, vs=AC),
)
def p3922(c: Cast) -> None:
    """"You can teleport 10 squares as a move action" is a movement mode.
    The "must end adjacent to the target" leash has nothing behind it."""
    if c.strike():
        c.damage(c.w(2), c.int_mod)
    else:
        c.half_damage(c.w(2), c.int_mod)
    c.mode("teleport", 10, until=When.ENCOUNTER, on=c.me)


@power(
    "p4800",
    level=5,
    cls="swordmage",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FIRE],
    attack=Attack(INT, vs=FORT),
)
def p4800(c: Cast) -> None:
    """The mark lands either way, and marks in this engine already sit side
    by side rather than displacing one another."""
    if c.strike():
        c.damage("2d10", c.con_mod, dtype=DamageType.FIRE)
    c.mark(until=When.ENCOUNTER)


@power(
    "p5744",
    level=5,
    cls="swordmage",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=ARCANE_WEAPON,
    attack=Attack(INT, vs=AC),
)
def p5744(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(), c.int_mod)
    kind = c.choose(_ALL_KINDS, "the bargain is struck in")
    if kind is None:
        return
    c.vulnerable(5, kind, until=When.SAVE_ENDS)
    for mate in c.within(5, side="ally"):
        c.resist(5, kind, until=When.ENCOUNTER, on=mate)


@power(
    "p5745",
    level=5,
    cls="swordmage",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=ARCANE_WEAPON,
    attack=Attack(INT, vs=FORT),
)
def p5745(c: Cast) -> None:
    """`weakened` halves everything the creature does to anybody; the
    printed line halves only what reaches my side, so it is written on the
    roll, where the victim as well as the attacker is known."""
    if c.strike():
        c.damage(c.w(2), c.int_mod)
    victim = c.target
    mine = {c.me, *c.allies()}

    def soften(ev: DamageRolled) -> None:
        if ev.source == victim and ev.target in mine:
            ev.amount = ev.amount // 2

    c.watch(
        DamageRolled, soften, until=When.SAVE_ENDS, on=victim,
        window=Window.BEFORE, label=c.ref,
    )


@power(
    "p5746",
    level=5,
    cls="swordmage",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=ARCANE_WEAPON,
    attack=Attack(INT, vs=AC),
)
def p5746(c: Cast) -> None:
    """Flanking is combat advantage, which is a flat +2 -- written as a
    gated bonus because the printed condition (an ally adjacent to it) is
    checked at the moment of the swing, not now."""
    if c.strike():
        c.damage(c.w(2), c.int_mod)
    else:
        c.half_damage(c.w(2), c.int_mod)
    victim = c.target
    mine = c.allies()

    def flanking(ctx: dict) -> bool:
        if ctx.get("target") != victim:
            return False
        return any(c.adjacent_to(victim, w) for w in mine)

    c.bonus("attack", 2, on=c.me, until=When.ENCOUNTER, when=flanking)
    c.note(f"{c.ref}: the target can be pinpointed within 20 squares")


@power(
    "p5747",
    level=5,
    cls="swordmage",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*ARCANE_WEAPON, Keyword.FIRE],
    attack=Attack(INT, vs=AC),
)
def p5747(c: Cast) -> None:
    """The splash fires off the burn actually landing, so it stops when the
    burn is saved against and never fires if a stronger fire burn already
    standing refused this one."""
    if not c.strike():
        c.half_damage(c.w(2), c.int_mod)
        return
    c.damage(c.w(2), c.int_mod)
    burn = c.ongoing(5, DamageType.FIRE)
    if burn is None:
        return
    victim = c.target

    def splash(ev: DamageApplied) -> None:
        if ev.target != victim or ev.dtype is not DamageType.FIRE:
            return
        if "ongoing" not in ev.detail:
            return
        for foe in c.within(1, of=victim, side="enemy"):
            if foe != victim:
                c.flat(5, dtype=DamageType.FIRE, on=foe)

    rider = c.watch(
        DamageApplied, splash, until=When.ENCOUNTER, on=c.me, label=c.ref
    )
    burn.on_end.append(lambda: c.world.effects.end(rider, "the fire is out"))
