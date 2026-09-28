"""Fighter feats.

Three families, and two of them share one gap.

**"An attack granted by Combat Challenge."** Four rows turn on it, and
they are written now: a use carries `granted_by`/`granted_via`, so the
swing `p7419` hands the fighter is no longer indistinguishable from a
standard-action `mba`. `CHALLENGE` below is that ref.

**The invigorating keyword.** Four rows turn on a keyword the engine
does not have, and `Keyword` is read off the enum so the gap is exact.

**The weapon-group riders** -- a hammer, a flail, an axe or a pick -- are
writable, because `Gear` carries the group and `c.wielding` asks. The
save-narrowing half of two of them is writable too, now that the saving
throw's context carries the conditions and the ongoing damage it is
against.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    ENCOUNTER,
    FORT,
    PERSONAL,
    REF,
    SELF,
    WILL,
    ActionType,
    Cast,
    Condition,
    Dropped,
    Gear,
    Hit,
    SecondWind,
    Size,
    Trigger,
    When,
    about_me,
    power,
)
from combat_engine.engine.events import PowerResolved
from combat_engine.engine.query import enemies, holding, team

#: The conditions a hammer or a mace is printed as making stick.
_STICKY = ("dazed", "immobilized", "slowed", "stunned")


def _i_crit_in_melee(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    from combat_engine.engine.dsl import get

    p = get(ev.power)
    return (
        ev.attacker == me
        and ev.critical
        and p is not None
        and p.reach.kind == "melee"
    )


def _i_killed_in_melee(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return getattr(ev, "source", None) == me


def _holding(c: Cast, *groups: str) -> bool:
    """Is the caster swinging one of these weapon groups?"""
    return any(holding(c.world, c.me, g) for g in groups)


@power("f364", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f364(c: Cast) -> None:
    """A penalty to the saves against the four conditions this weapon's
    blows are printed as making stick. The saving throw's context carries
    the conditions the effect holds, which is what makes the narrowing
    sayable rather than a blanket penalty on every save.

    The weapon is checked when the trait arms rather than per save: what
    is in hand at the top of the fight is what the feat is about, and the
    save happens on somebody else's turn when `c.me` is not swinging.
    """
    if not _holding(c, "hammer", "mace"):
        return
    for foe in enemies(c.world, c.me):
        c.penalty(
            "save", 2, on=foe, until=When.ENCOUNTER,
            when=lambda ctx: any(
                str(x.value) in _STICKY for x in ctx.get("conditions", ())
            ),
        )


@power("f368", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you score a critical hit with a melee attack",
       on=Trigger(Hit, _i_crit_in_melee, "you crit in melee"))
def f368(c: Cast) -> None:
    """Against **that target's** attacks only, which the attack context
    reaches through `attacker`."""
    foe = c.trigger.target
    for defence in (AC, FORT, REF, WILL):
        c.bonus(
            defence, 2, on=c.me, until=When.EONT,
            when=lambda ctx: ctx.get("attacker") == foe,
        )


@power("f405", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you reduce an enemy to 0 hit points with a melee attack",
       on=Trigger(Dropped, _i_killed_in_melee, "you drop an enemy"))
def f405(c: Cast) -> None:
    c.bonus("save", 1, on=c.me, until=When.ENCOUNTER)


@power("f407", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f407(c: Cast) -> None:
    """A surprised enemy is one that has not had its first turn, which
    `Condition.SURPRISED` holds -- the surprise round put it there."""
    c.bonus(
        "damage", 4, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: (
            ctx.get("target") is not None
            and c.is_(Condition.SURPRISED, on=ctx["target"])
        ),
    )


@power("f416", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f416(c: Cast) -> None:
    """A charge against a target already giving you combat advantage. Both
    are keys the *attack* context carries; the damage context carries
    `charge` but not `advantage`, so the extra is a damage bonus gated on
    the charge and the advantage is read off the hit."""
    if not _holding(c, "light blade", "spear"):
        return
    c.bonus(
        "damage", c.roll(c.w(1)), on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("charge", False),
    )


@power("f772", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you knock an enemy prone with a flail",
       on=Trigger(PowerResolved, lambda w, me, ev: (
           ev.actor == me and ev.power != "f772"
       ), "you finish a power"))
def f772(c: Cast) -> None:
    """Only when the blow actually put the target down.

    On `PowerResolved` rather than `Hit` for the reason `f1827` in
    `defenders.py` spells out: `resolve.attack` emits `Hit` from inside
    the body, before the riders land, so a prone test there reads a
    creature that was already down rather than one this flail felled.
    

    **The predicate excludes this row's own ref.** Declared on
    `PowerResolved` with `ev.actor == me` alone, the row answers its
    *own* resolution -- firing is a power use, which resolves, which
    offers it again -- and the stack goes with it. The traceback
    surfaces inside `query.can_act`, so it reads as an engine fault
    rather than a content one. Any row triggered on any use or
    resolution by its own caster has this shape.
    """
    if not _holding(c, "flail"):
        return
    for foe in c.trigger.targets:
        if c.is_(Condition.PRONE, on=foe):
            c.slide(1, on=foe)


@power("f778", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f778(c: Cast) -> None:
    """Two blades of any mix. `Gear.two_weapon` is the printed question
    and already excludes a shield, which is the other half of it."""
    gear = c.world.get(c.me, Gear)
    if gear is None or not gear.two_weapon:
        return
    if all(w.group in ("light blade", "heavy blade") for w in gear.melee):
        c.bonus("damage", 1, on=c.me, until=When.ENCOUNTER)


@power("f782", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f782(c: Cast) -> None:
    """**Allies**, not you. A mark is a relation, so the gate asks whether
    the creature being hit is one this character marked."""
    me = c.me
    for friend in [a for a in team(c.world, me) if a != me]:
        c.bonus(
            "damage", 1, on=friend, until=When.ENCOUNTER,
            when=lambda ctx: (
                ctx.get("target") is not None
                and c.marked(on=ctx["target"], by=me)
            ),
        )


@power("f402", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f402(c: Cast) -> None:
    """Large or larger, and marked by you: two questions the attack
    context can answer between `target` and the relation table."""
    me = c.me
    big = (Size.LARGE, Size.HUGE, Size.GARGANTUAN)
    c.bonus(
        "attack", 1, on=me, until=When.ENCOUNTER,
        when=lambda ctx: (
            ctx.get("target") is not None
            and c.marked(on=ctx["target"], by=me)
            and c.size_of(ctx["target"]) in big
        ),
    )


# -- the family that was waiting on a granted swing -------------------------

#: **The row Combat Challenge's punishment is written as.** The feature
#: itself is the mark (`cf:fighter-weaponmaster-f1`, which is what these
#: prerequisites name); the swing it allows is `p7419`, and `p7419` is
#: what calls `c.basic` -- so that is the ref the grant is stamped with.
CHALLENGE = "p7419"


def _challenged(c: Cast, ev: Any) -> list[int]:
    """Who this use hit, if it was the swing Combat Challenge granted.

    Read off `PowerResolved` rather than `Hit`, because every clause
    here is "*if you hit*, then ..." and two of them happen after the
    damage: `Hit` is announced with the blow still in the air and the
    body has not paid out yet.
    """
    if ev.actor != c.me or ev.granted_by != c.me or ev.granted_via != CHALLENGE:
        return []
    return [roll.target for roll in ev.rolls if roll.hit]


def _granted_swing(c: Cast, ctx: dict[str, Any]) -> bool:
    """The modifier-context half of the same question."""
    return (
        ctx.get("granted_by") == c.me and ctx.get("granted_via") == CHALLENGE
    )


@power("f286", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f286(c: Cast) -> None:
    """A rider on the swing Combat Challenge grants.

    The Special line -- a shield must be equipped -- is asked when the
    swing lands rather than when the trait arms, because a fighter can
    put a shield down mid-fight and the printed condition is about the
    moment of the blow.
    """
    def punished(ev: Any) -> None:
        if not c.wielding("shield"):
            return
        for foe in _challenged(c, ev):
            c.penalty("attack", 2, on=foe, until=When.SONT)

    c.watch(PowerResolved, punished, until=When.ENCOUNTER, on=c.me,
            label=f"{c.ref} riposte rider")


@power("f300", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f300(c: Cast) -> None:
    """Constitution on the damage of the granted swing, two-handed only.

    A standing modifier rather than a rider on the hit: the printed line
    adds to the *damage roll*, so it has to be in the roll rather than a
    second packet after it. The grip is asked inside the gate, which is
    read at the moment the damage is rolled.
    """
    c.bonus(
        "damage", c.con_mod, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: _granted_swing(c, ctx) and c.wielding("two-handed"),
    )


@power("f306", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f306(c: Cast) -> None:
    """"After dealing damage" is why this waits for the use to resolve
    rather than answering the `Hit`, which fires before the body pays."""
    def shoved(ev: Any) -> None:
        if not c.wielding("shield"):
            return
        for foe in _challenged(c, ev):
            c.push(1, on=foe)

    c.watch(PowerResolved, shoved, until=When.ENCOUNTER, on=c.me,
            label=f"{c.ref} riposte push")


@power("f771", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f771(c: Cast) -> None:
    """Wisdom on both rolls of the granted swing. No type word is
    printed, so both are untyped."""
    gate = lambda ctx: _granted_swing(c, ctx)  # noqa: E731
    c.bonus("attack", c.wis_mod, on=c.me, until=When.ENCOUNTER, when=gate)
    c.bonus("damage", c.wis_mod, on=c.me, until=When.ENCOUNTER, when=gate)


@power("f755", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("Keyword.INVIGORATING",))
def f755(c: Cast) -> None:
    """Turns on a keyword the engine does not have. `Keyword` is read off
    the enum, so the gap is exact rather than a judgement."""


@power("f758", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("Keyword.INVIGORATING",))
def f758(c: Cast) -> None:
    """Same keyword, triggered by a racial power."""


@power("f774", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("Keyword.INVIGORATING", "TempHP.power"))
def f774(c: Cast) -> None:
    """Same keyword, raising the temporary hit points it pays.

    **Two symbols, not one.** Even with the keyword this could not be
    said: `resolve.temp_hp` consults `Mods` for nothing, so "+2 to the
    number of temporary hit points you gain" has no term to add to.
    Five rows want that second one.
    """


@power("f792", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("Keyword.INVIGORATING", "TempHP.power"))
def f792(c: Cast) -> None:
    """Same two gaps as f774, a smaller number."""


@power("f371", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use your second wind",
       on=Trigger(SecondWind, about_me, "you use your second wind"))
def f371(c: Cast) -> None:
    """"In addition to the normal bonus", so it stacks, and the card
    prints no type word, so it is untyped. Bloodied is asked of the world
    before the hit points come back, which is what `SecondWind` being
    announced first is for."""
    if not c.bloodied(on=c.me):
        return
    for what in (AC, FORT, REF, WILL):
        c.bonus(what, 1, on=c.me, until=When.EONT)


@power("f372", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use your second wind",
       on=Trigger(SecondWind, about_me, "you use your second wind"))
def f372(c: Cast) -> None:
    """Same reading as f371, on attack rolls."""
    if c.bloodied(on=c.me):
        c.bonus("attack", 1, on=c.me, until=When.EONT)


@power("f769", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f769(c: Cast) -> None:
    """Untyped ongoing damage from an axe or a pick. The saving throw's
    context carries whether the effect is ongoing and what type it is, so
    "no damage type" is a real question rather than an approximation."""
    if not _holding(c, "axe", "pick"):
        return
    for foe in enemies(c.world, c.me):
        c.penalty(
            "save", 2, on=foe, until=When.ENCOUNTER,
            when=lambda ctx: ctx.get("ongoing") and ctx.get("dtype") is None,
        )
