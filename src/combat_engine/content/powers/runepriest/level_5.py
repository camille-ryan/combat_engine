"""Runepriest, level 5."""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    DAILY,
    EACH_ENEMY,
    FORT,
    MINOR,
    ONE_CREATURE,
    STANDARD,
    STR,
    WILL,
    Attack,
    AttackDeclared,
    Cast,
    CloseBlast,
    DamageType,
    Hit,
    Keyword,
    Melee,
    UpTo,
    When,
    get,
    power,
)

DIVINE_WEAPON = [Keyword.DIVINE, Keyword.WEAPON]


@power(
    "p11386",
    level=5,
    cls="runepriest",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[*DIVINE_WEAPON, Keyword.RADIANT, Keyword.ZONE],
    attack=Attack(STR, vs=WILL),
)
def p11386(c: Cast) -> None:
    """The exit tax is written now, and the old note's reasoning was sound as
    far as it went: a zone was difficult for everybody or nobody, and
    difficult ground is worth one square where this card prints two.

    `extra_cost_on="leave"` is the half that needed the engine, and it is
    narrower than a price on the squares. Leaving is a step from inside to
    outside, so moving *within* the zone is free and only the way out is
    charged -- a creature that walks the length of it pays once, at the edge.
    `extra_cost_for="enemies"` leaves the caster's own side to walk out
    normally, which is the printed narrowing.

    No `difficult=` beside it: the tax replaces difficult's one square rather
    than adding to it, so laying both would charge the same 2 and read as if
    the row meant them to stack."""
    if c.strike():
        c.damage(c.w(2), c.str_mod, dtype=DamageType.RADIANT)
    else:
        c.half_damage(c.w(2), c.str_mod, dtype=DamageType.RADIANT)
    if not c.first:
        return
    zid = c.zone(
        c.area(), until=When.EONT, sustain=MINOR,
        extra_cost=2, extra_cost_on="leave", extra_cost_for="enemies",
    )

    def expose(ev: Any, z: int = zid) -> None:
        inside = c.world.zones.occupants(z)
        if ev.attacker not in c.enemies():
            return
        if ev.target in inside and ev.target in [c.me, *c.allies()]:
            c.grants_advantage(on=ev.attacker, until=When.SAVE_ENDS, to="team")

    c.watch(AttackDeclared, expose, until=When.EONT)


@power(
    "p11387",
    level=5,
    cls="runepriest",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(STR, vs=WILL),
)
def p11387(c: Cast) -> None:
    """**Both riders are written now, and "neither `c.grants_advantage`
    nor `c.vulnerable` takes a gate" was false** -- both take `when=`.
    #1341.

    The gate is the *shape* of the incoming attack, and the damage
    context carries no reach, so it is **looked up off the attacking
    row** -- the arrangement `monk/level_2.py`'s `_melee` already uses
    and whose docstring says why: "the damage context carries no
    `attacker` and no `ranged`, so the reach has to be looked up off the
    row".

    "Area attacks and ranged attacks" is three of the seven declared
    reach kinds -- `ranged`, `area_burst` and `wall`. `close_burst` and
    `close_blast` are deliberately **out**: a close attack is not an area
    attack in the printed rules, and folding them in would widen both
    riders onto every dragon's breath on the board.

    **"(save ends both)" is two holds on one clock, which is two saves
    rather than one**, because `c.vulnerable` takes no `onto=` to join an
    existing hold. Said rather than hidden: a target saving against one
    keeps the other, where the card ends both together.

    The Aftereffect hangs on the advantage hold's `on_end`, so it begins
    whichever way that one finished -- the same shape `p11305` uses.

    The Effect line -- enemies not granting cover against ranged attacks
    -- is still dropped, and that half of the old note was right: cover
    cannot be waived for one creature.
    """
    victim = c.target
    hit = c.strike()
    if hit:
        c.damage(c.w(2), c.str_mod)
    else:
        c.half_damage(c.w(2), c.str_mod)
    if victim is None:
        return

    def from_afar(ctx: dict) -> bool:
        swung = get(ctx.get("power") or "")
        reach = getattr(swung, "reach", None)
        return getattr(reach, "kind", "") in ("ranged", "area_burst", "wall")

    if not hit:
        c.grants_advantage(
            on=victim, to="team", until=When.EONT, when=from_afar
        )
        return
    exposed = c.grants_advantage(
        on=victim, to="team", until=When.SAVE_ENDS, when=from_afar
    )
    c.vulnerable(
        5, on=victim, until=When.SAVE_ENDS, when=from_afar
    )
    if exposed is not None:
        exposed.on_end.append(
            lambda: c.grants_advantage(
                on=victim, to="team", until=When.EONT, when=from_afar
            )
        )


@power(
    "p11388",
    level=5,
    cls="runepriest",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    keywords=[*DIVINE_WEAPON, Keyword.FIRE],
    attack=Attack(STR, vs=AC),
)
def p11388(c: Cast) -> None:
    """One target burns; two are tied together, which needs both ids at once
    -- `c.targets` is the whole list the body is walking. The hold is what
    the saving throw ends, so the link reads it rather than a duration."""
    if c.strike():
        c.damage(c.w(), c.str_mod, dtype=DamageType.FIRE)
    else:
        c.half_damage(c.w(), c.str_mod, dtype=DamageType.FIRE)
    if not c.last:
        return
    pair = tuple(t for t in c.targets if t is not None)
    if len(pair) < 2:
        c.ongoing(5, DamageType.FIRE)
        return
    for who in pair:
        c.effect("p11388", on=who, until=When.SAVE_ENDS)

    def link(ev: Any, tied: tuple[int, ...] = pair) -> None:
        burning = c.suffering("p11388")
        if ev.target not in tied or ev.target not in burning:
            return
        p = get(ev.power)
        if p is None or p.reach.kind not in ("melee", "ranged"):
            return
        for other in tied:
            if other != ev.target and other in burning:
                c.flat(5, dtype=DamageType.FIRE, on=other)

    c.watch(Hit, link, until=When.ENCOUNTER)


@power(
    "p11389",
    level=5,
    cls="runepriest",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.VARIES],
    attack=Attack(STR, vs=FORT),
)
def p11389(c: Cast) -> None:
    """The bonus grows by re-applying it larger: two bonuses of one kind do
    not add, the larger wins. It lives on the attackers, so it is the gate
    rather than the duration that ends it when the target saves."""
    victim = c.target
    kind = c.choose([DamageType.NECROTIC, DamageType.RADIANT], "which rune")
    kind = kind or DamageType.RADIANT
    if c.strike():
        c.damage(c.w(2), c.str_mod, dtype=kind)
    else:
        c.half_damage(c.w(2), c.str_mod, dtype=kind)
    if victim is None:
        return
    c.effect("p11389", until=When.SAVE_ENDS)
    side = [c.me, *c.allies()]

    def grant(size: int, v: int = victim) -> None:
        for who in side:
            c.bonus(
                "damage",
                size,
                on=who,
                until=When.ENCOUNTER,
                when=lambda ctx, t=v: ctx.get("target") == t
                and t in c.suffering("p11389"), kind="power")

    grant(2)
    step = [2]

    def sharpen(ev: Any, v: int = victim) -> None:
        if ev.target != v or ev.attacker not in side:
            return
        if v not in c.suffering("p11389"):
            return
        step[0] += 1
        grant(step[0])

    c.watch(Hit, sharpen, until=When.ENCOUNTER)
