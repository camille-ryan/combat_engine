"""Runepriest, level 9."""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    AREA_OR_CLOSE,
    DAILY,
    EACH_ENEMY,
    FORT,
    MINOR,
    ONE_CREATURE,
    REF,
    STANDARD,
    STR,
    WILL,
    Attack,
    Cast,
    CloseBlast,
    DamageType,
    Hit,
    Keyword,
    Melee,
    TurnStart,
    When,
    Window,
    ZoneEntered,
    get,
    power,
)

DIVINE_WEAPON = [Keyword.DIVINE, Keyword.WEAPON]
DEFENCES = (AC, FORT, REF, WILL)


@power(
    "p11399",
    level=9,
    cls="runepriest",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p11399(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.damage(c.w(2), c.str_mod)
    else:
        c.half_damage(c.w(2), c.str_mod)
    if victim is None:
        return

    def rush(ev: Any, v: int = victim) -> None:
        if ev.ghost or ev.actor not in c.allies():
            return
        if not c.adjacent_to(v, ev.actor):
            return
        if c.may("swing at it for free", who=ev.actor):
            c.basic(who=ev.actor, on=v)

    c.watch(TurnStart, rush, until=When.EONT)


@power(
    "p11400",
    level=9,
    cls="runepriest",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.VARIES],
    attack=Attack(STR, vs=FORT),
)
def p11400(c: Cast) -> None:
    """The second half of this row is `p11400b`, and it took the alternate
    attack line with it. The Effect line is two holds: one on the caster,
    which is that row's Requirement, and one on the primary target, which is
    the origin square the printed line names."""
    victim = c.target
    kind = c.choose([DamageType.NECROTIC, DamageType.RADIANT], "which rune")
    kind = kind or DamageType.RADIANT
    if c.strike():
        c.damage(c.w(2), c.str_mod, dtype=kind)
    else:
        c.half_damage(c.w(2), c.str_mod, dtype=kind)
    if victim is None:
        return
    c.effect(c.ref, on=c.me, until=When.ENCOUNTER)
    c.effect(f"{c.ref} origin", on=victim, until=When.ENCOUNTER)


@power(
    "p11402",
    level=9,
    cls="runepriest",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p11402(c: Cast) -> None:
    """**The Effect is written now, and the reason it was dropped was
    false.** The note said "`c.autohit` has no counterpart". It has one:
    `c.hit_becomes(False)`, whose docstring is about this exact
    asymmetry -- *"the attack misses, or it lands after all"*, with
    `hit=True` named as "the `forced` half".

    Three things the printed line needs, and all three were already
    answerable:

    * **"included as a target of"** is a membership test on
      `Hit.among`, "everybody this one attack is aimed at, for a burst or
      a blast" -- not an `attacker`/`target` comparison.
      `skills/insight.py` records the same reading.
    * **"a close or an area attack"** is `AREA_OR_CLOSE`, which this file
      already imports and already uses eight rows below, with a comment
      saying why a hand-written tuple was wrong.
    * **`Window.BEFORE`**, which is the part that would have failed
      silently. `hit_becomes` works by setting `result.hit` so that
      `resolve.attack`'s `confirm` callback turns the announcement into a
      real `Miss` -- so a listener in the default AFTER window runs once
      `confirm` has already read it and changes nothing.

    It misses the caster and allies and leaves the blow on the target
    alone, which is what "misses you and your allies" says."""
    victim = c.target
    if c.strike():
        c.damage(c.w(3), c.str_mod)
    else:
        c.half_damage(c.w(3), c.str_mod)
    if victim is None or not c.first:
        return
    me = c.me

    def spared(ev: Hit) -> None:
        if victim not in getattr(ev, "among", ()) or ev.target == victim:
            return
        if ev.target != me and ev.target not in c.allies():
            return
        dealt = get(getattr(ev, "power", ""))
        if dealt is None or dealt.reach.kind not in AREA_OR_CLOSE:
            return
        c.hit_becomes(False, ev=ev)

    c.watch(Hit, spared, until=When.ENCOUNTER, on=me, window=Window.BEFORE)


@power(
    "p11403",
    level=9,
    cls="runepriest",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[*DIVINE_WEAPON, Keyword.RADIANT, Keyword.ZONE],
    attack=Attack(STR, vs=FORT),
)
def p11403(c: Cast) -> None:
    """**The zone's resist is written now.** The old note said `c.resist`
    "cannot be gated on the shape of the attack coming in", and its
    `when=` is handed the damage context with `power` in it -- so the
    incoming row's `reach.kind` is readable, which is how four other rows
    already ask this question. #1341.

    Not `c.resist_in`, which is the near miss: that gives everyone in the
    zone a flat resistance and takes no `when`, where this card resists
    **only close and area attacks**. A flat version would shrug off every
    arrow as well, which is a stronger card than the one printed.

    Both halves are read live, so stepping out of the zone drops the
    resistance -- unlike the AC bonus beside it, which is handed out on
    entry and runs its own duration.
    """
    if c.strike():
        c.damage(c.w(), c.str_mod, dtype=DamageType.RADIANT)
        c.push(4)
    else:
        c.half_damage(c.w(), c.str_mod, dtype=DamageType.RADIANT)
        c.push(1)
    if not c.first:
        return
    area = c.area()
    zid = c.zone(area, until=When.EONT, sustain=MINOR)
    def shielded(ctx: dict[str, Any], who: int, z: int = zid) -> bool:
        """A close or area attack, landing on somebody still in the zone."""
        if who not in c.world.zones.occupants(z):
            return False
        dealt = get(ctx.get("power") or "")
        # `AREA_OR_CLOSE` and not a hand-written tuple: mine omitted
        # `"wall"`, which is an area attack by the same printed rule.
        # `lint.py` caught it -- seventeen files already import this.
        return dealt is not None and dealt.reach.kind in AREA_OR_CLOSE

    for who in [c.me, *c.in_squares(area, side="ally")]:
        c.bonus(AC, 2, on=who, until=When.EONT, kind="power")
        c.resist(
            5, None, on=who, until=When.EONT,
            when=lambda ctx, w=who: shielded(ctx, w),
        )

    def ward(ev: Any, z: int = zid) -> None:
        if ev.zone == z and ev.actor in [c.me, *c.allies()]:
            c.bonus(AC, 2, on=ev.actor, until=When.EONT, kind="power")
            c.resist(
                5, None, on=ev.actor, until=When.EONT,
                when=lambda ctx, w=ev.actor: shielded(ctx, w),
            )

    c.watch(ZoneEntered, ward, until=When.EONT)


@power(
    "p15992",
    level=9,
    cls="runepriest",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[*DIVINE_WEAPON, Keyword.LIGHTNING],
    attack=Attack(STR, vs=WILL),
)
def p15992(c: Cast) -> None:
    """The Effect line is not conditional on the hit, so it is applied to
    every target. The hold is what the saving throw ends; the watch reads it
    each time rather than carrying a duration of its own."""
    victim = c.target
    if c.strike():
        c.damage(c.w(2), c.str_mod)
    else:
        c.half_damage(c.w(2), c.str_mod)
    if victim is None:
        return
    c.effect("p15992", until=When.SAVE_ENDS)

    def jolt(ev: Any, v: int = victim) -> None:
        if v in c.suffering("p15992"):
            c.flat(5, dtype=DamageType.LIGHTNING, on=v)

    c.on_attack(jolt, by=victim, until=When.ENCOUNTER)


@power(
    "p16499",
    level=9,
    cls="runepriest",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p16499(c: Cast) -> None:
    """The aura's bonus is handed out on entry and to whoever is already
    standing in it, and runs the aura's duration."""
    if c.strike():
        c.damage(c.w(3), c.str_mod)
    if not c.first:
        return
    ring = c.aura(1, until=When.EONT)
    for ally in c.within(1, side="ally"):
        for defence in DEFENCES:
            c.bonus(defence, 2, on=ally, until=When.EONT, kind="power")

    def ward(ev: Any, z: int = ring) -> None:
        if ev.zone != z or ev.actor not in c.allies():
            return
        for defence in DEFENCES:
            c.bonus(defence, 2, on=ev.actor, until=When.EONT, kind="power")

    c.watch(ZoneEntered, ward, until=When.EONT)
