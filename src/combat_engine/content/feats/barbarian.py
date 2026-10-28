"""Barbarian feats.

`Keyword.RAGE` does not exist -- `docs/blocked.json` records
`cf:barbarian-rage` waiting on it -- so "while raging" is not a state
anything can ask about. Three rows here want it and name it exactly,
and for the third it is the *only* thing still missing.

The rest are ordinary triggers, or a class-feature ref nobody declares.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.powers.barbarian.rage import in_rage
from combat_engine.engine import (
    AT_WILL,
    ENCOUNTER,
    PERSONAL,
    SELF,
    ActionType,
    Cast,
    DamageApplied,
    DamageType,
    Dropped,
    Hit,
    PowerUsed,
    SurgeSpent,
    Trigger,
    When,
    about_me,
    power,
)
from combat_engine.engine.query import allies


@power("f454", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you reduce an enemy to 0 hit points",
       on=Trigger(Dropped, lambda w, me, ev: (
           getattr(ev, "source", None) == me
       ), "you drop an enemy"))
def f454(c: Cast) -> None:
    """A **weapon** damage bonus, so it is gated on the power carrying
    the weapon keyword rather than left open -- the card says weapon and
    a barbarian's rage rows are not all of them."""
    from combat_engine.engine import Keyword
    from combat_engine.engine.dsl import get

    c.bonus(
        "damage", 2, on=c.me, until=When.EONT, kind="feat",
        when=lambda ctx: (
            (p := get(ctx.get("power", ""))) is not None
            and Keyword.WEAPON in p.keywords
        ),
    )


def _i_bloodied_it(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    """Did *this* blow of mine take the target across half?

    **`Bloodied` carries `actor` and nothing else.** This row was
    declared on it with a predicate reading `ev.source`, which no
    `Bloodied` has ever had -- so the predicate was False forever and
    the row was inert from the day it was written. A `getattr` with a
    default is what hid it.

    `DamageApplied` carries `source`, `amount` and the hit points left
    *after* the blow, which is everything the question needs: the
    crossing is `hp` at or under half where `hp + amount` was above it.
    Five item rows carry `Bloodied.source` as a marker for the same gap
    and the same derivation would close all of them.
    """
    from combat_engine.engine import Health

    if ev.source != me:
        return False
    health = world.get(ev.target, Health)
    if health is None:
        return False
    half = health.max_hp // 2
    return ev.hp <= half < ev.hp + ev.amount


@power("f1826", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you bloody an enemy",
       on=Trigger(DamageApplied, _i_bloodied_it, "you bloody an enemy"))
def f1826(c: Cast) -> None:
    """"You **or** an ally" is a choice the scorer cannot weigh, so the
    bonus is laid on everybody -- each one is spent by its own next
    attack against that enemy, which comes to the same thing when only
    one of them takes the swing."""
    me, foe = c.me, c.trigger.target
    for who in [me, *(a for a in allies(c.world, me) if a != me)]:
        c.bonus(
            "damage", c.cha_mod, on=who, until=When.ENCOUNTER, once=True,
            when=lambda ctx: ctx.get("target") == foe,
        )


@power("f593", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f593(c: Cast) -> None:
    """+1 to damage rolls while raging, +2 at 11th and +3 at 21st.

    **It was never blocked.** `rage.raging()` has answered "are you raging"
    since the module was written -- see the note on `RAGE` above. The gate
    is asked per attack rather than once at arming, because a rage can end
    mid-fight and the bonus goes with it. #503.
    """
    c.bonus(
        "damage", 1 + (c.level >= 11) + (c.level >= 21),
        on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: in_rage(c),
    )


@power("f1720", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you spend a healing surge",
       on=Trigger(SurgeSpent, about_me, "you spend a healing surge"))
def f1720(c: Cast) -> None:
    """Charisma modifier in extra radiant damage on your next melee attack,
    after spending a surge while raging.

    **Neither half was missing and the row said both were.** Its docstring
    claimed the rage gate did not exist -- `rage.in_rage()` has answered it
    all along -- and when that was corrected I re-pointed it to
    `events.SurgeSpent`, which `todo.py` reported as existing on the very
    next run. It is emitted from every site that decrements a surge, by
    design.

    Written as a one-shot watcher rather than a `c.bonus`, because the extra
    damage has a **type** the card names and a damage bonus carries none.
    #503.
    """
    if not in_rage(c):
        return
    me = c.me

    def rider(ev: Hit) -> None:
        # `ev.ctx`, not `ev.result.ctx`: the context rides on the **event**
        # as a plain attribute (#495), and `AttackResult` has no such field --
        # `lint.py` caught that this would have raised the moment the row ran.
        if ev.attacker != me or (getattr(ev, "ctx", None) or {}).get("ranged"):
            return
        c.flat(c.cha_mod, dtype=DamageType.RADIANT, on=ev.target)

    c.watch(Hit, rider, until=When.EONT, on=me, once=True,
            label=f"{c.ref} radiant")


@power("f1009", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("cf:barbarian-f1s0",))
def f1009(c: Cast) -> None:
    """Raises the temporary hit points one class-feature option pays.

    **The benefit is written and the symbol now names something else.**
    The old note said the option was "named in prose with no ref", which
    stopped being the blocker twice over: `resolve.temp_hp` reads a
    `temp_hp` term off the receiver, so there is a number to add to, and
    `TempHP.power` names the row that paid -- which is what the gate reads
    out of the context. `f1855` is the same move on a racial trait.

    A modifier rather than a watcher, for `f1855`'s reason: the
    non-stacking rule is applied *after* the term, so a watcher raising
    `ev.amount` would already have lost to a standing pool.

    **The gate names `cf:barbarian-f1`, not the option the card prints.**
    No row carries `cf:barbarian-f1s0`; the option's body is written inline
    on `cf:barbarian-f1`'s `rageblood` leg, so `cf:barbarian-f1` is the ref
    that rides the `TempHP` this card is about. It is exact rather than
    merely close, because that row's other leg `c.forbid`s and returns
    before reaching its only `c.temp_hp` -- so a pool paid under that ref
    *is* this option's. It stops being exact the day the feature pays
    temporary hit points on a second leg.

    **Dropped: the feat cannot be dealt.** Its printed prerequisite is
    `{"ref": "cf:barbarian-f1s0"}`, and `chargen.meets` answers that
    against the character's dealt list, which carries `f1s1`..`f1s3` and
    never `f1s0` -- because no row declares it. The mechanism works: with
    the ref present `meets` returns True. So the body is complete and what
    is still owed is the option's own row, which is `primal_shadow.py`'s
    ruling and `docs/blocked.json`'s `cf:barbarian-might-rest`, not a
    clause here. `dropped=` rather than `todo=` because the row plays if it
    is ever held, and `legal_feats` refuses a `todo=` row outright.

    Untyped: the card prints no word in front of a bonus, and the belt
    property that raises the same pool prints none either -- untyped
    modifiers add, which is what both cards say.
    """
    c.bonus("temp_hp", 5, on=c.me, until=When.ENCOUNTER,
            when=lambda ctx: ctx.get("power") == "cf:barbarian-f1")


@power("f1010", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1010(c: Cast) -> None:
    """Grows one named power's burst by a modifier, and pays weapon damage,
    both while raging. Written; the marker named a hold that was not one.

    **"`c.widen_areas` has no way to name one row" was the last blocker
    standing here, and it is false.** Three stacked re-point notes had
    worked the row down to exactly that sentence, and the route it
    proposed -- lay the modifier on the `PowerUsed` that announces the
    power, held to the end of that turn -- is more machinery than the
    card needs.

    `c.widen_areas` takes no `when=`, but it is one line over
    `c.bonus("blast_size", ...)`, and **`c.bonus` has always taken a
    gate**. `dsl._stretched` says so in its own docstring -- *"`ctx`
    carries the row being measured, so 'the range of your **arcane**
    powers' is a gate on the modifier rather than a blanket stretch"* --
    and measuring it confirms the ctx is `{"power": ..., "kind":
    "close_burst"}`. So the narrowing to one row is a gate on the
    modifier, and nothing had to be built. `f2705` is the same move on
    `c.reroll_ones`, which also exposes no `when=`.

    Asked **per read, not at arming**, which is `f593`'s reason and holds
    here twice over: a rage can end mid-fight, and the burst is measured
    every time the menu is drawn.

    The damage half is `f454`'s shape -- a **weapon** damage bonus is
    gated on the used power carrying the keyword, because "a barbarian's
    rage rows are not all of them" -- and it is armed off `PowerUsed`
    rather than laid standing, since the card gives it once per use and
    holds it past that power's own resolution.
    """
    from combat_engine.engine import Keyword
    from combat_engine.engine.dsl import get

    me = c.me

    #: The one row this feat names. Both halves hang on it.
    roar = "p4932"

    c.bonus(
        "blast_size", c.cha_mod, on=me, until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("power") == roar and in_rage(c),
    )

    def paid(ev: PowerUsed) -> None:
        if ev.actor != me or ev.power != roar or not in_rage(c):
            return
        c.bonus(
            "damage", 2, on=me, until=When.EONT, kind="power",
            when=lambda ctx: (
                (p := get(ctx.get("power", ""))) is not None
                and Keyword.WEAPON in p.keywords
            ),
        )

    c.watch(PowerUsed, paid, until=When.ENCOUNTER, on=me, label=c.ref)
