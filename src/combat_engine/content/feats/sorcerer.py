"""Sorcerer feats.

Four of the six gate on the class's own at-wills, which is a keyword
question and therefore cheap. The two that are not turn on a source --
one of the class's build forks -- and both of those have a leg now:
`chargen.BUILDS["sorcerer"]` carries `wild` and `dragon`, and
`powers/sorcerer/souls.py` writes both in full and exports the two
things a rider on either needs, `soul_of` and `wear_soul`. So the
`cf:sorcerer-f0s1` / `f0s3` markers were naming rows that do not exist
for clauses that do.

The remaining gap is reach: one row rewrites a power's range for a
single use, which is header data the menu reads before anything runs.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.powers.sorcerer.souls import (
    ROLLED_TYPES,
    soul_of,
    soul_resist,
    wear_soul,
)
from combat_engine.engine import (
    AT_WILL,
    ENCOUNTER,
    PERSONAL,
    SELF,
    ActionType,
    Cast,
    DamageType,
    Effect,
    EffectApplied,
    Hit,
    PowerResolved,
    Trigger,
    When,
    power,
)
from combat_engine.engine.dsl import get
from combat_engine.engine.types import Usage

#: "Ranged and melee attack powers", as the reach kinds a header carries.
#: A melee-or-ranged line is a `melee` range with a `ranged` alternative,
#: so both halves of it are in this set either way.
_HAND = ("melee", "ranged")
#: "Area and close attack powers", the other half of the same split.
_SPREAD = ("close_burst", "close_blast", "area_burst", "wall")


def _my_at_will_hit(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    p = get(ev.power)
    return ev.attacker == me and p is not None and p.usage is Usage.AT_WILL


def _reach_in(kinds: tuple[str, ...]):  # noqa: ANN202
    """A modifier gate on what sort of row is being used.

    The damage context is the thin one and carries no `ranged`, so this
    is asked of the declared header -- which is what `AUTHORING.md` says
    to do and what makes the same helper serve an attack bonus too.
    """
    def gate(ctx: dict[str, Any]) -> bool:
        p = get(str(ctx.get("power") or ""))
        return p is not None and p.reach is not None and p.reach.kind in kinds

    return gate


def _at_will_hits(c: Cast, wanted: int, pay: Any) -> None:
    """Arm "you use a sorcerer at-will and hit exactly / at least N".

    `PowerResolved` is the moment: it says the use is **over** and
    carries `rolls`, every `AttackResult` it produced. `Hit` is per
    target and cannot count, which is what both of these rows were
    marked for.
    """
    me = c.me

    def resolved(ev: PowerResolved) -> None:
        if ev.actor != me or not ev.rolls:
            return
        p = get(ev.power)
        if p is None or p.cls != "sorcerer" or p.usage is not Usage.AT_WILL:
            return
        landed = sum(1 for r in ev.rolls if getattr(r, "hit", False))
        if (landed >= 2) if wanted >= 2 else (landed == 1):
            pay()

    c.watch(PowerResolved, resolved, until=When.ENCOUNTER, on=me, label=c.ref)


def _on_soul(c: Cast, pay: Any) -> None:
    """Run once the source has sworn itself to a type.

    Both this and the feature are traits, and `turns` arms them in the
    order `Powers.all` lists them -- which is not a guarantee either
    way. So the clause is run now if the source has already armed, and
    hung on the marker landing if it has not. Latched, because
    `wear_soul` lays a marker of its own and would otherwise re-enter.
    """
    done: list[bool] = []

    def once() -> None:
        if done or soul_of(c) is None:
            return
        done.append(True)
        pay()

    once()
    if not done:
        c.watch(
            EffectApplied, lambda ev: once(), until=When.ENCOUNTER,
            on=c.me, label=c.ref,
        )


@power("f998", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit with a sorcerer at-will attack power",
       on=Trigger(Hit, _my_at_will_hit, "you hit with an at-will"))
def f998(c: Cast) -> None:
    """Against **that** enemy only, until the end of your next turn."""
    foe = c.trigger.target
    c.bonus(
        "attack", 1, on=c.me, until=When.EONT,
        when=lambda ctx: ctx.get("target") == foe,
    )


@power("f1028", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.reach_of(power=)",))
def f1028(c: Cast) -> None:
    """Turns a ranged power into a melee one when cast through a named
    weapon group. A power's reach is header data, read before the body
    runs so the interface can draw it, and nothing rewrites it for one
    use -- the same gap the wizard's f1134 names from the other side."""


@power("f1138", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1138(c: Cast) -> None:
    """A damage bonus after an at-will hits two or more enemies.

    Re-read: the count was never needed *during* the use. The bonus is
    on later attacks, so it is taken at `PowerResolved`, which carries
    every roll the use made. A plain "+2 bonus" with no type word, so
    untyped.
    """
    _at_will_hits(
        c, 2,
        lambda: c.bonus(
            "damage", 2, on=c.me, until=When.EONT, when=_reach_in(_HAND)
        ),
    )


@power("f1155", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1155(c: Cast) -> None:
    """The other side of f1138: an attack bonus after an at-will hits
    exactly one, spent on area and close powers."""
    _at_will_hits(
        c, 1,
        lambda: c.bonus(
            "attack", 1, on=c.me, until=When.EONT, when=_reach_in(_SPREAD)
        ),
    )


@power("f1001", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1001(c: Cast) -> None:
    """Roll twice for the source's damage type and keep either result.

    Re-read: `cf:sorcerer-f0s3` has no row of its own because the source
    is written inside `cf:sorcerer-f0`, which forks on the `wild` leg
    and rolls a d10 across ten types. The roll is not reachable, but it
    does not have to be -- the type it settled on is, through `soul_of`,
    and `wear_soul` swears the source to another. So the second die is
    rolled here and the sorcerer keeps whichever it prefers, which is
    the printed sentence.
    """
    if not c.build("wild"):
        return

    def twice() -> None:
        standing = soul_of(c)
        fresh = ROLLED_TYPES[(c.roll("1d10") - 1) % len(ROLLED_TYPES)]
        if standing is None or fresh is standing:
            return
        if c.choose([standing, fresh], "which type the soul takes") is fresh:
            wear_soul(c, fresh)

    _on_soul(c, twice)


@power("f1008", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1008(c: Cast) -> None:
    """+2 to the resistance the other source grants.

    Re-read: resistances of a type do not add -- the highest applies --
    and that is what makes this writable rather than what blocked it.
    `soul_of` names the type the source swore to and `soul_resist` is
    the ladder it laid, so a resistance of that number plus two simply
    supersedes it. The paragon and epic steps are out of scope.

    The earlier one is ended when the source changes type mid-fight, or
    a swap would leave this feat resisting whatever the sorcerer used to
    be sworn to.
    """
    if not c.build("dragon"):
        return
    held: list[Effect] = []
    sworn: list[DamageType] = []

    def raise_it() -> None:
        # The guard is what keeps this out of its own watcher: laying a
        # resistance announces an `EffectApplied` of its own, and an
        # unconditional re-lay would answer itself forever.
        kind = soul_of(c)
        if kind is None or sworn[:1] == [kind]:
            return
        sworn[:] = [kind]
        for old in held:
            c.world.effects.end(old, c.ref)
        held.clear()
        fresh = c.resist(
            soul_resist(c.level) + 2, kind, on=c.me, until=When.ENCOUNTER
        )
        if fresh is not None:
            held.append(fresh)

    raise_it()
    c.watch(
        EffectApplied, lambda ev: raise_it(), until=When.ENCOUNTER,
        on=c.me, label=c.ref,
    )
