"""Battlemind, level 10."""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    ENCOUNTER,
    FORT,
    INTERRUPT,
    MINOR,
    ONE_ALLY,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    WILL,
    Cast,
    DamageApplied,
    DamageRolled,
    DamageType,
    Hit,
    Keyword,
    Melee,
    Ranged,
    Trigger,
    When,
    ally_within,
    get,
    power,
    targets_me,
)
from combat_engine.engine.components import Conjuration

from . import PSIONIC


def _weapon_attack(ctx: dict[str, Any]) -> bool:
    """"Your weapon attacks". The damage context carries the row that dealt
    it as `power`, which is where the keywords are."""
    p = get(ctx.get("power") or "")
    return p is not None and Keyword.WEAPON in p.keywords


@power(
    "p11175",
    dropped=("c.grant_action_row()",),
    level=10,
    cls="battlemind",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PSIONIC, Keyword.TELEPORTATION, Keyword.POLYMORPH],
)
def p11175(c: Cast) -> None:
    """The move-action teleport is a power in its own right and `c.grant_row`
    needs a ref to grant, so it is dropped."""
    c.resist(5, until=When.ENCOUNTER)


@power(
    "p11176",
    level=10,
    cls="battlemind",
    usage=DAILY,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=PSIONIC,
    trigger="you take damage from an attack",
    on=Trigger(DamageRolled, targets_me, "you take damage from an attack"),
)
def p11176(c: Cast) -> None:
    """`DamageRolled` is a proposal and refusing it is exactly "the damage is
    reduced to 0" -- everything else the attack does has already happened or
    happens after, which is the printed "subject to all other effects"."""
    c.cancel()


@power(
    "p12428",
    level=10,
    cls="battlemind",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PSIONIC,
)
def p12428(c: Cast) -> None:
    """**The four damage types are written now.** The old note said "a
    modifier carries a number and not a type"; `c.bonus` takes `dtype`,
    and its docstring is about this exact family -- "the difference
    between '+2 damage' and '2 extra fire damage'... every one of them
    used to roll untyped: the points went past a fire resistance that
    should have stopped them". A **sequence** is "one rider of several
    types", which is what this card's four are. #1341.

    `c.vulnerable` really is the wrong end of it, and that half of the old
    note stands: this is about what the blow *is*, not about what the
    target suffers extra from.

    What this carries and what it does not: the Charisma rider now meets
    cold, fire, lightning and thunder defences on its own terms. The
    power's own damage "stays whatever type the power was", per the same
    docstring -- so a target resistant to fire takes less of the rider and
    the weapon damage is untouched. The printed line reads as typing the
    whole blow; typing the rider is the part the engine can say, and it is
    the part that meets a resistance.
    """
    c.bonus(
        "damage", c.cha_mod, on=c.me, until=When.EONT, when=_weapon_attack,
        dtype=(
            DamageType.COLD, DamageType.FIRE,
            DamageType.LIGHTNING, DamageType.THUNDER,
        ),
    )


@power(
    "p13060",
    level=10,
    cls="battlemind",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PSIONIC,
)
def p13060(c: Cast) -> None:
    """Printed as a minor action on one weapon, which is not a target the
    header can name, so it lands on the wielder. The brutal 1 property is
    dropped -- nothing rerolls low damage dice. The critical rider is the
    half that can be said, and `c.flat(c.roll(...))` is how an extra die is
    added inside a critical without being maximised."""
    def crit(ev: Hit) -> None:
        if ev.attacker == c.me and ev.critical:
            c.flat(c.roll("1d10"), on=ev.target)

    c.watch(Hit, crit, until=When.ENCOUNTER, on=c.me)


@power(
    "p13061",
    level=10,
    cls="battlemind",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PSIONIC, Keyword.STANCE],
)
def p13061(c: Cast) -> None:
    """Walls and ceilings are a climb speed equal to the walking one, which is
    what "without having to climb" comes to on a grid."""
    c.stance()
    c.mode("climb", c.speed_of(), until=When.ENCOUNTER)


@power(
    "p13062",
    level=10,
    cls="battlemind",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PSIONIC,
)
def p13062(c: Cast) -> None:
    """The Perception bonus is not a combat effect."""
    c.cannot_be_flanked(on=c.me, until=When.ENCOUNTER)


@power(
    "p2639",
    level=10,
    cls="battlemind",
    usage=AT_WILL,
    action=REACTION,
    reach=Melee(1),
    target=ONE_ALLY,
    keywords=PSIONIC,
    trigger="an adjacent ally takes damage",
    on=Trigger(DamageApplied, ally_within(1), "an adjacent ally takes damage"),
)
def p2639(c: Cast) -> None:
    """The ally to slide is the one the event was about; the dispatcher only
    aims a triggered row at an *enemy*, so it is read off `c.trigger`."""
    ev = c.trigger
    hurt = getattr(ev, "target", None) if ev is not None else None
    c.slide(1, on=hurt if hurt is not None else c.target)


@power(
    "p2640",
    level=10,
    cls="battlemind",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(5),
    target=SELF,
    keywords=[Keyword.PSIONIC, Keyword.ILLUSION, Keyword.CONJURATION],
)
def p2640(c: Cast) -> None:
    """The +4 is written flat rather than gated on "an attack that doesn't
    include both you and the duplicate": the defence context names one
    target and not a power's whole target list, so the gate would be silently
    false. That makes this row stronger than printed.

    **"The duplicate disappears if a melee or a ranged attack deals any
    damage to it" is written now.** The old note said "a conjuration has
    no hit points to lose", which is true and is not what the clause
    needs: it turns on *damage being dealt*, not on hit points running
    out. A `DamageApplied` watch aimed at the duplicate ends the
    conjuration's own effect, which is how `seeker`'s `banish` takes one
    off the board. #1341.

    "A melee or a ranged attack" rather than any damage at all, read off
    the power's reach, so an area burst that catches the duplicate leaves
    it standing -- which is the printed distinction and the reason this is
    not simply "any damage".

    **Verified at the handler rather than through the board, because the
    board cannot aim an attack at a conjuration.** A foe's basic, used
    with `targets=[duplicate]`, resolves to nothing at all -- no
    `AttackDeclared`, no `Hit` -- for the reason `p4381`'s docstring
    gives about companions: a conjuration "is nobody's enemy or ally in
    the targeting sense". So the four arms were driven by emitting the
    `DamageApplied` the clause watches:

        detail "mba"      pops it
        detail "rba"      pops it
        detail "p3034"    leaves it standing   (an area burst)
        no detail         leaves it standing

    All four, because a handler that pops on everything is
    indistinguishable from a correct one from the melee side.
    """
    double = c.conjure(label=c.ref, until=When.ENCOUNTER, sustain=None, speed=5)
    for defence in (AC, FORT, REF, WILL):
        c.bonus(defence, 4, on=c.me, until=When.ENCOUNTER, kind="power")
    if not double:
        return

    def popped(ev: DamageApplied) -> None:
        if ev.target != double or ev.amount <= 0:
            return
        # **`ev.detail`, because `DamageApplied` has no `power` field** --
        # its fields are source, target, amount, dtype, absorbed, hp,
        # detail, dtypes, resisted. `detail` carries the ref, or `"mba"` /
        # `"rba"` for a basic attack, which is where the reach comes from.
        hit_by = get(ev.detail) if ev.detail else None
        kind = (
            hit_by.reach.kind if hit_by is not None
            else {"mba": "melee", "rba": "ranged"}.get(ev.detail or "", "")
        )
        if kind not in ("melee", "ranged"):
            return
        conj = c.world.get(double, Conjuration)
        held = (
            c.world.effects.live.get(conj.effect)
            if conj is not None and conj.effect is not None
            else None
        )
        if held is not None:
            c.world.effects.end(held, "a blow landed on the duplicate")

    c.watch(DamageApplied, popped, until=When.ENCOUNTER, on=c.me,
            label=f"{c.ref} pops")
