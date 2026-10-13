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
       reach=PERSONAL, target=SELF, todo=("cf:barbarian-f1s0",))
def f1009(c: Cast) -> None:
    """Raises the temporary hit points a class feature pays. Named in
    prose with no ref."""


@power("f1010", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.recast(area=)",))
def f1010(c: Cast) -> None:
    """Grows a named power's burst and pays a damage bonus, both while
    raging.

    Growing the burst is no longer the gap. `c.widen_areas` lays a
    `blast_size` modifier and `dsl._stretched` reads it, so
    "becomes a close burst 5 + your Charisma modifier instead of a close
    burst 5" is `c.widen_areas(c.cha_mod)` -- the old note here said the
    area was header data nothing could rewrite, which stopped being true
    when that verb landed. The marker followed the note and named
    `c.widen_area()`, a verb that has never existed under that spelling.

    What still blocks it is the condition both halves hang on: rage is
    not a state anything holds, so writing either half would pay out
    whether the barbarian is raging or not.

    One caveat for the day rage arrives: `c.widen_areas` is a modifier on
    the caster with no way to name one row, so the narrowing to `p4932`
    would have to come from the duration -- laid on the `PowerUsed` that
    announces it, which fires before the body, and held to the end of
    that turn.
    

    **Re-pointed: the rage gate was never the hold.** `rage.in_rage()`
    answers it. What is left is rewriting the named row's burst from 5 to
    "5 + your Charisma modifier" -- reach is header data the menu reads
    before anything runs, which is `c.recast(reach=)`, the symbol `f287`
    and `f601` already carry.
    

    **Re-pointed off `c.recast(reach=)`, which was one symbol over two
    mechanisms.** This row rewrites a *named row's area* -- its size or
    its shape. `c.widen_areas` lays a `blast_size` modifier and
    `dsl._stretched` reads it, so growing every burst this caster throws
    is already sayable; what is not is naming **one** row, which is what
    all of these cards do. The other five rows on the old symbol wanted
    melee-as-ranged, which is a different rewrite -- see
    `c.recast(as_ranged=)`.
    """
