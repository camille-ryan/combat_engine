"""Druid feats, the second batch.

`druid.py` holds the first six and this one runs on the same rail:
`in_beast_form` is imported from `content/powers/druid/forms.py` rather
than re-derived, because that is the version the form itself uses.

Two shapes recur. The first is a standing modifier gated on the shape,
asked per roll -- a druid changes shape mid-fight, so arming the gate
once would freeze it. The second is a rider on one of the three beast
form at-wills, `p5036`, `p5037` and `p5038`, each of which is a ref.

Those three want care about *when*. `Hit` is announced from inside
`c.strike`, so a row answering it resolves before the rider the power
itself applies -- before the slow, before the slide. Two rows here
therefore answer the hit by arming a one-shot watch on what the body
goes on to emit, which is the only order in which "instead of slowing"
and "after you slide it" mean what they print.

The gaps are mostly the printed second sentence of a skill feat: an
escape attempt, a bull rush, crawling, low-light vision and reach are
each one method the tree does not have, and the skill bonus beside them
is a build-time number.

`usage=AT_WILL` throughout. Nothing here prints a once-per-encounter
limit, and `triggers._answers` asks `usable` every time it offers a row,
so `ENCOUNTER` would turn "whenever you hit with p5036" into "once a
fight" -- which is what these rows did before they were driven by hand.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.powers.druid.forms import in_beast_form
from combat_engine.engine import (
    AT_WILL,
    PERSONAL,
    SELF,
    ActionType,
    Cast,
    Condition,
    Hit,
    Trigger,
    When,
    power,
)
from combat_engine.engine.events import (
    AttackRolled,
    ConditionApplied,
    DamageApplied,
    Moved,
    PowerUsed,
    RoundStart,
)
from combat_engine.engine.query import allies, team
from combat_engine.engine.triggers import both, by_charge, by_me, by_melee, targets_me

#: Second wind is an action rather than a power, as `defenders.py` says.
SECOND_WIND = ("c.on_second_wind()",)
#: Shoving somebody, which nothing in the tree does.
BULL_RUSH = ("c.bull_rush()",)


def _hit_with(ref: str):  # noqa: ANN202
    def when(world, me: int, ev: Any) -> bool:  # noqa: ANN001
        return ev.attacker == me and ev.power == ref

    return when


def _again_this_round(c: Cast) -> bool:
    """Has this row already answered something this round?

    `once_per_round=` is read by the action menu and not by the trigger
    dispatcher, so a printed "once per round" on a reaction is counted
    here. `dsl.use` stamps a `PowerUsed` above the body, so this firing
    is already in the log and a second one means there was an earlier.
    """
    seen = 0
    for ev in reversed(c.world.bus.log):
        if isinstance(ev, RoundStart):
            break
        if isinstance(ev, PowerUsed) and ev.actor == c.me and ev.power == c.ref:
            seen += 1
    return seen > 1


# -- standing modifiers, gated on the shape ---------------------------------


@power("f1829", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("resolve.dmg_ctx.advantage",))
def f1829(c: Cast) -> None:
    """The same printed sentence as f555 on a different prerequisite, and
    the same half is dropped: the damage context carries no `advantage`,
    only the attack context does, so gating on it would be silently
    false."""
    me = c.me
    c.bonus(
        "damage", 2, on=me, until=When.ENCOUNTER,
        when=lambda ctx: in_beast_form(c.world, me),
    )


@power("f1852", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1852(c: Cast) -> None:
    """The speed half is a real modifier, not decoration: `query.speed`
    is handed `{"charge": True}` by the three places that measure a
    charge's run and nothing else, which is exactly this gate."""
    me = c.me

    def charging(ctx: dict[str, Any]) -> bool:
        return in_beast_form(c.world, me) and bool(ctx.get("charge", False))

    c.bonus("speed", 2, on=me, until=When.ENCOUNTER, when=charging)
    c.bonus("damage", 1, on=me, until=When.ENCOUNTER, when=charging)


@power("f1883", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1883(c: Cast) -> None:
    """The attack context carries `opportunity`, so the gate is per
    attack; adjacency is asked there too, because both the druid and the
    ally move. The set of allies is fixed when the trait is armed, which
    is what every standing aura in the tree does."""
    me = c.me

    def opportune(ctx: dict[str, Any]) -> bool:
        return in_beast_form(c.world, me) and bool(ctx.get("opportunity", False))

    c.bonus("attack", 2, on=me, until=When.ENCOUNTER, kind="feat", when=opportune)
    for friend in [a for a in allies(c.world, me) if a != me]:
        c.bonus(
            "attack", 2, on=friend, until=When.ENCOUNTER, kind="feat",
            when=lambda ctx, f=friend: opportune(ctx) and c.adjacent_to(me, f),
        )


@power("f2207", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2207(c: Cast) -> None:
    """Both gates are about the caster rather than the roll, so neither
    reads the context -- which is what lets the damage half work at all,
    the damage context being the thin one. No type word is printed."""
    me = c.me

    def hurt_and_shaped(ctx: dict[str, Any]) -> bool:
        return in_beast_form(c.world, me) and c.bloodied(on=me)

    c.bonus("attack", 1, on=me, until=When.ENCOUNTER, when=hurt_and_shaped)
    c.bonus("damage", 1, on=me, until=When.ENCOUNTER, when=hurt_and_shaped)


@power("f2278", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.run()",))
def f2278(c: Cast) -> None:
    """The charge half works; the run half is dropped, because there is
    no run action -- `actions.legal` offers a walk, a shift, a charge and
    the standard menu, which is the gap the avenger's f2165 named."""
    me = c.me
    c.bonus(
        "speed", 4, on=me, until=When.ENCOUNTER, kind="feat",
        when=lambda ctx: (
            in_beast_form(c.world, me)
            and c.bloodied(on=me)
            and bool(ctx.get("charge", False))
        ),
    )


# -- riders on the beast form at-wills --------------------------------------


@power("f2184", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit with p5037",
       on=Trigger(Hit, _hit_with("p5037"), "you hit with that power"))
def f2184(c: Cast) -> None:
    """`p5037` already grants combat advantage to the druid's side, but
    only to the next attacker; this widens it to every attack for the
    duration, which is the same `to="allies"` without `once`."""
    c.grants_advantage(on=c.trigger.target, until=When.EONT, to="allies")


@power("f2185", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit with p5036",
       on=Trigger(Hit, _hit_with("p5036"), "you hit with that power"))
def f2185(c: Cast) -> None:
    """"Instead of slowing" has to wait for the slow.

    `Hit` is announced from inside `c.strike`, so this body runs before
    `p5036` reaches its own rider -- taking the slow off here would take
    off nothing and the power would then apply it. So the swap is armed
    as a one-shot watch on the condition landing.

    The ending clause is a watch of its own: nothing else notices that
    two creatures have stopped being adjacent, and either of them moving
    is the moment it can become true.
    """
    me, foe = c.me, c.trigger.target
    if foe is None or not c.may("immobilise instead of slowing"):
        return

    def swap(ev: ConditionApplied) -> None:
        if ev.target != foe or ev.source != me or ev.condition is not Condition.SLOWED:
            return
        c.cure(Condition.SLOWED, on=foe)
        held = c.immobilized(on=foe, until=When.EONT)
        if held is None:
            return

        def apart(moved: Moved) -> None:
            if moved.actor in (me, foe) and not held.ended and not c.adjacent_to(me, foe):
                c.world.effects.end(held, "no longer adjacent")

        c.watch(Moved, apart, until=When.EONT, on=me, label=f"{c.ref} apart")

    c.watch(ConditionApplied, swap, until=When.EOT, on=me, once=True, label=c.ref)


@power("f2186", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit with p5038",
       on=Trigger(Hit, _hit_with("p5038"), "you hit with that power"))
def f2186(c: Cast) -> None:
    """"Into the space occupied by your target" means the square it has
    just left, and `Moved.from_` is the only place that is written down.
    Same ordering as f2185: the slide has not happened when the hit is
    announced, so the shift is armed rather than taken."""
    foe = c.trigger.target
    if foe is None:
        return

    def follow(ev: Moved) -> None:
        if ev.actor == foe:
            c.shift(1, to=ev.from_)

    c.watch(Moved, follow, until=When.EOT, on=c.me, once=True, label=c.ref)


# -- answering what happens to you ------------------------------------------


@power("f1872", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="an enemy damages you with a melee attack",
       on=Trigger(DamageApplied, both(targets_me, by_melee),
                  "an enemy damages you in melee"))
def f1872(c: Cast) -> None:
    """`DamageApplied.detail` carries the ref, which is what lets
    `by_melee` find a reach on a damage event at all. The printed "once
    per round" is counted rather than declared -- see
    `_again_this_round`."""
    me = c.me
    foe = c.trigger.source
    if foe == me or not in_beast_form(c.world, me):
        return
    if team(c.world, foe) is team(c.world, me) or _again_this_round(c):
        return
    c.grants_advantage(on=foe, until=When.EONT)


@power("f2283", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you make a charge attack",
       on=Trigger(AttackRolled, both(by_me, by_charge), "you charge"))
def f2283(c: Cast) -> None:
    """Declared on the roll rather than on the hit, because the printed
    line is "after making a charge attack" and a miss is one."""
    if in_beast_form(c.world, c.me):
        c.move(2, who=c.me)


# -- the inventory clause, which has no combat consequence ------------------


@power("f1857", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f1857(c: Cast) -> None:
    """What happens to what the druid is carrying when the shape
    changes. `p5032`'s own docstring already says the equipment clauses
    are bookkeeping with no combat consequence, and this one only makes
    them kinder -- the sentence that would matter, that a shield's
    benefit is still lost, is what the engine does anyway."""


# -- the second sentence of a skill feat ------------------------------------


@power("f2276", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.reach_bonus()",))
def f2276(c: Cast) -> None:
    """A square of extra reach on melee basic attacks while shaped and
    bloodied. Reach is read off the weapon and `c.threatens` only widens
    the opportunity window, which is a different question. The skill
    bonus beside it is a build-time number."""


@power("f2277", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.low_light()",))
def f2277(c: Cast) -> None:
    """Low-light vision while shaped. Nothing models the dark by degrees,
    which is the symbol f194 named."""


@power("f2279", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.escape()",))
def f2279(c: Cast) -> None:
    """Damage to whatever fails to get out of this druid's grip.
    `c.grabbing` lists who is held; there is no escape attempt to fail,
    which seven item blocks also want."""


@power("f2280", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=BULL_RUSH)
def f2280(c: Cast) -> None:
    """Slides rather than pushes on a shove. There is no shove."""


@power("f1884", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=BULL_RUSH)
def f1884(c: Cast) -> None:
    """An attack bonus to a shove, and a shove against any size. Same
    gap as f2280 and f419."""


@power("f2282", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.crawl()",))
def f2282(c: Cast) -> None:
    """No opening given by crawling. `c.no_provoke` says the second half
    and `Condition.PRONE` is real, but crawling is not a move the engine
    has -- a prone creature walks at half speed and nothing calls it
    anything."""


@power("f2281", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=SECOND_WIND)
def f2281(c: Cast) -> None:
    """A shift on taking a second wind while shaped. The shape is
    readable; second wind is an action and announces nothing."""


@power("f2284", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.on_second_wind()", "c.total_defence()"))
def f2284(c: Cast) -> None:
    """Resistance after either of two actions, and neither is a power:
    second wind announces nothing and total defence is not an action the
    menu offers at all."""


# -- powers chosen somewhere else -------------------------------------------


@power("f1876", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.summoned_by_me()", "c.on_instinctive()"))
def f1876(c: Cast) -> None:
    """An attack bonus for a summon acting on its own. `c.instinctive`
    sets one going, but the attack it makes is announced as an ordinary
    attack by an ordinary creature -- nothing records that the action was
    instinctive, and nothing keeps a list of whose summons are whose."""


@power("f2033", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.recast(no_provoke=)",))
def f2033(c: Cast) -> None:
    """Uses another feat's granted card while shaped, for a cheaper
    action and without giving an opening. `c.recast` says the cheaper
    action and the card is a ref -- what is missing is the no-provoke,
    which `Power.no_provoke` is header data for and cannot be lent to
    one use."""


@power("f2880", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("chargen.race_choice()",))
def f2880(c: Cast) -> None:
    """Gives a racial trait's chosen power the printed keyword this
    package gates on. `forms.beast_row` reads that keyword off the row's
    `requires=`, so it could be granted -- but nothing records which
    power the trait was pointed at, the same gap f604 named."""
