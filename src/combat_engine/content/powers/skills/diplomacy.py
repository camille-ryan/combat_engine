"""Skill powers for diplomacy: seven utilities at levels 2, 6 and 10.

What the group has in common is that the benefit is **somebody else's**:
five of the seven hand a bonus, a heal or a rescue to an ally, so almost
nothing here is written `on=c.me`. The two rerolls are the exceptions and
both answer a check of the character's own.

Two rows print "Requirement: you must be taking a short rest" and nothing
in the engine can be asked whether a creature is resting -- `turns.
short_rest` is a call and leaves no state -- so both carry the same
`dropped=` symbol. Their payouts are written and play.

`cls` is the skill and not a class, which is the module's own convention;
see `__init__.py`.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    DAILY,
    EACH_ALLY,
    ENCOUNTER,
    FORT,
    FREE,
    INTERRUPT,
    MINOR,
    ONE_ALLY,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    WILL,
    Ability,
    Cast,
    CloseBurst,
    Keyword,
    Ranged,
    Target,
    Trigger,
    When,
    by_melee,
    my_check,
    power,
)
from combat_engine.engine.components import Stats
from combat_engine.engine.events import AttackDeclared, Healed, Hit, SkillCheck, SurgeSpent
from combat_engine.engine.query import adjacent, bloodied, distance_between, team

#: The lowest Intelligence score p11541's target line allows.
_BRIGHT = 5

_DISLIKED = "you make a diplomacy check and dislike the result"
_RESTING = "you must be taking a short rest"


def _struck_a_bloodied_ally(world: Any, me: int, ev: Any) -> bool:
    """An enemy within 3 swinging in melee at my bloodied adjacent ally.

    Written out rather than built from combinators: `targets_me` asks about
    the wrong creature here, and `enemy_within` cannot also say anything
    about the victim. `AttackDeclared` carries `attacker` and `target` and
    no `actor`, so `about_me` would be false forever.
    """
    attacker = getattr(ev, "attacker", None)
    victim = getattr(ev, "target", None)
    if attacker is None or victim is None or victim == me:
        return False
    if team(world, attacker) is team(world, me):
        return False
    if team(world, victim) is not team(world, me):
        return False
    if distance_between(world, me, attacker) > 3:
        return False
    return (
        adjacent(world, me, victim)
        and bloodied(world, victim)
        and by_melee(world, me, ev)
    )


def _nonhostile_enough(c: Cast, reach: int) -> int | None:
    """The target p11541's line allows, choosing one where the engine did not.

    `Target` filters on side and count and not on an ability score, so the
    chooser can hand this row a creature the card forbids. Preferring the
    pick and falling back to another in reach is `_restricted_to`'s shape;
    this one walks allies, since "nonhostile" is the side the engine has
    for a creature that is not fighting you.
    """

    def bright(who: int) -> bool:
        stats = c.world.get(who, Stats)
        return stats is not None and stats.score(Ability.INT) >= _BRIGHT

    who = c.target
    if who is not None and bright(who) and c.distance(who) <= reach:
        return who
    return next((a for a in c.within(reach, side="ally") if bright(a)), None)


@power(
    "p12830",
    level=2,
    cls="diplomacy",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger=_DISLIKED,
    on=Trigger(SkillCheck, my_check("diplomacy"), _DISLIKED),
)
def p12830(c: Cast) -> None:
    """"Whichever result you prefer" is `keep="best"`. Deciding before the
    result is announced is the free action's own window and needs nothing
    said in the body.
    """
    c.reroll_check(keep="best")


@power(
    "p9307",
    level=2,
    cls="diplomacy",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ALLY,
    requires_text=_RESTING,
    dropped=("query.resting()",),
)
def p9307(c: Cast) -> None:
    """"One or more healing surges" is one payout, not one per surge, so the
    watch is `once=True` per target.

    `c.bonus("surge_value", ...)` was the other candidate and is the wrong
    shape: it would pay again on every surge, and on every surge spent
    outside the rest as well.

    The Requirement is the dropped half -- nothing can be asked whether a
    creature is resting, so the row is offered where the card forbids it.
    """
    ally = c.target
    if ally is None:
        return
    extra = c.cha_mod

    def paid(ev: SurgeSpent) -> None:
        if ev.actor == ally:
            c.heal(extra, on=ally)

    c.watch(SurgeSpent, paid, on=ally, until=When.ENCOUNTER, once=True)


@power(
    "p11540",
    level=6,
    cls="diplomacy",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ALLY,
    requires_text=_RESTING,
    dropped=("query.resting()",),
)
def p11540(c: Cast) -> None:
    """"+1 bonus" with no type word in front of it is untyped, so `kind=` is
    left off both calls.

    "While not bloodied" is read off the creature at the moment the
    modifier is totalled rather than from the context, which carries no
    such key. `When.ENCOUNTER` laid between fights is the printed "until
    the end of the next encounter".

    The Requirement is the dropped half, as `p9307`'s is.
    """
    ally = c.target
    if ally is None:
        return

    def whole(_ctx: dict[str, Any]) -> bool:
        return not bloodied(c.world, ally)

    c.bonus("attack", 1, on=ally, until=When.ENCOUNTER, when=whole)
    c.bonus("save", 1, on=ally, until=When.ENCOUNTER, when=whole)


@power(
    "p9309",
    level=6,
    cls="diplomacy",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger=_DISLIKED,
    on=Trigger(SkillCheck, my_check("diplomacy"), _DISLIKED),
)
def p9309(c: Cast) -> None:
    """"Use either result" is `keep="best"`, the same clause `p12830` prints
    at level 2; these are two cards and not one row.
    """
    c.reroll_check(keep="best")


@power(
    "p11541",
    level=10,
    cls="diplomacy",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_ALLY,
)
def p11541(c: Cast) -> None:
    """One effect on the blanket `skill` key gated to the two named skills
    and to this creature, which is what "against the target" narrows to --
    `skills.modifier` puts the creature a check was made against in the
    context as `target`.
    """
    who = _nonhostile_enough(c, 5)
    if who is None:
        return
    c.bonus(
        "skill",
        5,
        on=c.me,
        kind="power",
        until=When.ENCOUNTER,
        when=lambda ctx: (
            ctx.get("skill") in ("bluff", "diplomacy") and ctx.get("target") == who
        ),
    )


@power(
    "p11542",
    level=10,
    cls="diplomacy",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=CloseBurst(3),
    # **Declared, not inherited.** The card prints a Target line -- the
    # triggering enemy -- and `ONE_CREATURE` is the module-level singleton
    # `Power.target` already defaults to, so naming it reads as *no header
    # written* rather than as an enemy chosen on purpose.
    # `scorecard._heal_reach` tells the two apart by identity and counts
    # this row among the healing rows with a missing target line, which is
    # a content fault it exists to surface. Same value, stated.
    target=Target("enemy", 1),
    keywords=[Keyword.CHARM],
    trigger=(
        "an enemy within 3 squares of you makes a melee attack roll "
        "against your bloodied ally adjacent to you"
    ),
    on=Trigger(
        AttackDeclared,
        _struck_a_bloodied_ally,
        "an enemy within 3 squares of you makes a melee attack roll "
        "against your bloodied ally adjacent to you",
    ),
)
def p11542(c: Cast) -> None:
    """An interrupt that moves the blow rather than stopping it, which is
    `c.redirect`. The ally is read off the trigger and not off `c.target`:
    the target line names the *enemy*.

    The temporary hit points are owed only if the attack then hits, so they
    wait on the `Hit` the redirected swing announces.
    """
    ally = getattr(c.trigger, "target", None)
    if ally is None or not c.redirect(to=c.me):
        return
    extra = c.cha_mod

    def landed(ev: Hit) -> None:
        if ev.target == c.me:
            c.temp_hp(extra, on=ally)

    c.watch(Hit, landed, until=When.EOT, once=True)


@power(
    "p9310",
    level=10,
    cls="diplomacy",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(5),
    target=Target("team", 1, bloodied=True),
)
def p9310(c: Cast) -> None:
    """"Or until the target is no longer bloodied" ends the hold rather than
    suspending it, so it is a `Healed` watch and not a `when=` gate --
    nothing but a heal takes a creature back over its half.

    `c.no_provoke` with no `from_` is "does not provoke at all", which is
    what "its movement does not provoke opportunity attacks" says.
    """
    who = c.target
    if who is None:
        return
    held = [c.no_provoke(on=who, until=When.EONT)]
    for defence in (AC, FORT, REF, WILL):
        held.append(c.bonus(defence, 4, on=who, kind="power", until=When.EONT))

    def mended(ev: Healed) -> None:
        if ev.target != who or bloodied(c.world, who):
            return
        for eff in held:
            if eff is not None:
                c.world.effects.end(eff, "no longer bloodied")

    c.watch(Healed, mended, until=When.EONT)
