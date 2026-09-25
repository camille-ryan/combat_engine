"""Fighter, level 6: the utilities the later books added.

Nothing here rolls an attack.

**"No Action" has no window.** `triggers.WINDOW_OF` maps interrupt, reaction,
opportunity and free actions to a bus window and has no entry for
`ActionType.NONE`, so a row declared with it is never offered. The half
dozen "No Action" rows here are written as the window each actually needs:
an interrupt where the triggering event has to be changed, a free action
where it does not. That is in the report.

**Skill and race prerequisites** are entry conditions on taking the power
rather than on using it, and the engine holds neither, so they are not
gates here.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    DAILY,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    FREE,
    INTERRUPT,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_ALLY,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    WILL,
    AttackRolled,
    Cast,
    CloseBurst,
    Condition,
    ConditionApplied,
    Healed,
    Keyword,
    Melee,
    MoveEnd,
    SavingThrow,
    Trigger,
    TurnStart,
    When,
    Window,
    World,
    about_me,
    by_melee,
    power,
)
from combat_engine.engine.events import AttackDeclared, DamageRolled, Hit, Miss
from combat_engine.engine.query import adjacent, allies, defence, team
from combat_engine.engine.query import squares as squares_of

from .footwork import aura_ring, close_by_shift, stand
from .grips import has_shield

MARTIAL = [Keyword.MARTIAL]

_SAVE_SHAKES = (Condition.IMMOBILIZED, Condition.SLOWED, Condition.WEAKENED)


def _somebody_is_dying(world: World, eid: int) -> bool:
    """"Target: one dying ally."

    A narrowing of the Target line the header cannot hold, so it is asked as
    the caster's own condition of use -- is there such an ally at all -- and
    checked again against the chosen one in the body.
    """
    from combat_engine.engine.query import adjacent as beside
    from combat_engine.engine.query import is_

    return any(
        beside(world, eid, friend) and is_(world, friend, Condition.DYING)
        for friend in allies(world, eid)
    )


def _healed_by_an_ally(world: World, me: int, ev: Any) -> bool:
    who = getattr(ev, "source", None)
    return (
        getattr(ev, "target", None) == me
        and who is not None
        and who != me
        and who in allies(world, me)
    )


def _missed_me_in_melee(world: World, me: int, ev: Any) -> bool:
    return getattr(ev, "target", None) == me and by_melee(world, me, ev)


def _melee_hit_me(world: World, me: int, ev: Any) -> bool:
    return getattr(ev, "target", None) == me and by_melee(world, me, ev)


def _would_land_in_melee(world: World, me: int, ev: Any) -> bool:
    result = getattr(ev, "result", None)
    return (
        getattr(ev, "target", None) == me
        and bool(result and result.hit)
        and by_melee(world, me, ev)
    )


def _hit_me_with_anything(world: World, me: int, ev: Any) -> bool:
    return getattr(ev, "target", None) == me


def _stuck_at_dawn(world: World, me: int, ev: Any) -> bool:
    """"You start your turn immobilized, slowed or weakened by a save-ends
    effect" -- the effect has to be one a save can reach, or there is
    nothing for the row to roll against."""
    if getattr(ev, "actor", None) != me or getattr(ev, "ghost", False):
        return False
    return any(
        effect.when is When.SAVE_ENDS
        and any(card in _SAVE_SHAKES for card in effect.conditions)
        for effect in world.effects.of(me)
    )


def _shot_at_my_friend(world: World, me: int, ev: Any) -> bool:
    """"One enemy in the burst makes an attack roll against an ally you can
    see" -- the burst is the header's, so only the sides are asked here."""
    from combat_engine.engine.query import line_of_effect

    attacker = getattr(ev, "attacker", None)
    struck = getattr(ev, "target", None)
    if attacker is None or struck is None or team(world, attacker) is team(world, me):
        return False
    return struck != me and struck in allies(world, me) and line_of_effect(world, me, struck)


_HEALED_BY_AN_ALLY = "an ally heals you"
_MISSED_ME_IN_MELEE = "an enemy misses you with a melee attack"
_MELEE_HIT_ME = "an enemy hits you with a melee attack"
_CLOSE_HIT_ME = "an enemy hits you with a close or a melee attack"
_ANY_HIT_ME = "an enemy hits you with an attack"
_A_SAVE_I_DISLIKE = "you make a saving throw and dislike the result"
_STUCK_AT_DAWN = "you start your turn held, slowed or weakened by something a save can end"
_SHOT_AT_MY_FRIEND = "an enemy near you rolls an attack against an ally you can see"


# -- stances ----------------------------------------------------------------


@power(
    "p10335",
    level=6,
    cls="fighter",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL, Keyword.STANCE],
)
def p10335(c: Cast) -> None:
    """The errata'd text: five off an adjacent ally's damage, and five onto
    the fighter, every time and not at choice.

    "This damage cannot be reduced or redirected in any way" has no spelling
    -- the five goes through `deal_damage` like anything else -- and is left
    as it is rather than approximated; see the report.
    """
    me = c.me
    stance = c.stance(label=c.ref)

    def shoulder(ev: DamageRolled) -> None:
        if ev.target == me or ev.amount <= 0 or ev.target not in allies(c.world, me):
            return
        if not adjacent(c.world, me, ev.target):
            return
        spared = min(5, ev.amount)
        ev.amount -= spared
        c.flat(5, on=me)

    held = c.watch(
        DamageRolled, shoulder, until=When.ENCOUNTER, window=Window.BEFORE, on=me,
        label=c.ref,
    )
    stance.on_end.append(lambda: c.world.effects.end(held, "stance ended"))


@power(
    "p10499",
    level=6,
    cls="fighter",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL, Keyword.STANCE],
)
def p10499(c: Cast) -> None:
    """Swinging at the fighter is what gets you marked, so the mark is hung
    off the declaration rather than off the outcome."""
    me = c.me
    stance = c.stance(label=c.ref)

    def call_out(ev: AttackDeclared) -> None:
        if ev.target == me and ev.attacker != me and by_melee(c.world, me, ev):
            c.mark(on=ev.attacker, until=When.EOTNT)

    held = c.watch(
        AttackDeclared, call_out, until=When.ENCOUNTER, window=Window.BEFORE, on=me,
        label=c.ref,
    )
    stance.on_end.append(lambda: c.world.effects.end(held, "stance ended"))


@power(
    "p12195",
    level=6,
    cls="fighter",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL, Keyword.STANCE],
    requires=has_shield,
    requires_text="needs a shield",
)
def p12195(c: Cast) -> None:
    """"Enemies take -2 to Fortitude while adjacent to you" is a standing
    condition on a moving ring, so it is an aura with `ZoneEntered` and
    `ZoneExited` putting the penalty on and taking it off -- `p1442`'s
    arrangement."""
    stance = c.stance(label=c.ref)
    aura_ring(
        c, stance, side="enemy",
        give=lambda who: [c.penalty(FORT, 2, on=who, until=When.ENCOUNTER)],
    )


@power(
    "p2230",
    level=6,
    cls="fighter",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL, Keyword.STANCE],
)
def p2230(c: Cast) -> None:
    """Unshakeable. Forced movement is shortened by the held modifier
    `c.resist_forced` keeps; being knocked down is refused at the moment the
    condition is applied, which is the only place it can be seen."""
    me = c.me
    stance = c.stance(label=c.ref)

    def refuse(ev: ConditionApplied) -> None:
        # `Effects.apply` adds the condition and *then* announces it, so
        # cancelling the event has nowhere to go. The hold that put the
        # fighter down is ended instead, in the same window -- nothing gets
        # a turn in between, so the fighter is never actually prone.
        if ev.target != me or ev.condition is not Condition.PRONE:
            return
        for effect in list(c.world.effects.of(me)):
            if Condition.PRONE in effect.conditions:
                c.world.effects.end(effect, c.ref)

    riders = [
        c.resist_forced(1, on=me, until=When.ENCOUNTER),
        c.watch(
            ConditionApplied, refuse, until=When.ENCOUNTER, on=me,
            label=f"{c.ref} footing",
        ),
    ]
    for rider in riders:
        if rider is not None:
            stance.on_end.append(lambda r=rider: c.world.effects.end(r, "stance ended"))


@power(
    "p4329",
    level=6,
    cls="fighter",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL, Keyword.STANCE],
    requires=has_shield,
    requires_text="needs a shield",
)
def p4329(c: Cast) -> None:
    """The fighter pays one off its own guard and hands two to whoever
    stands beside it. The dragonborn line is a race the engine does not
    have; see the report."""
    me = c.me
    stance = c.stance(label=c.ref)
    for guard in (AC, REF):
        rider = c.penalty(guard, 1, on=me, until=When.ENCOUNTER)
        if rider is not None:
            stance.on_end.append(lambda r=rider: c.world.effects.end(r, "stance ended"))
    aura_ring(
        c, stance, side="ally",
        give=lambda who: [
            c.bonus(AC, 2, on=who, until=When.ENCOUNTER),
            c.bonus(REF, 2, on=who, until=When.ENCOUNTER),
        ],
    )


# -- minor actions ----------------------------------------------------------


@power(
    "p12673",
    level=6,
    cls="fighter",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(3),
    target=ONE_CREATURE,
    keywords=MARTIAL,
)
def p12673(c: Cast) -> None:
    """"Whose Will is equal to or lower than 12 + your level" is a narrowing
    of the Target line the header cannot hold, so it is asked here. Hindering
    terrain is not something the grid names; see the report."""
    victim = c.target
    if victim is None or defence(c.world, victim, WILL) > 12 + c.level:
        return
    c.pull(2)


@power(
    "p12675",
    level=6,
    cls="fighter",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Melee(1),
    target=ONE_ALLY,
    keywords=MARTIAL,
)
def p12675(c: Cast) -> None:
    c.save()


@power(
    "p12698",
    level=6,
    cls="fighter",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Melee(1),
    target=ONE_ALLY,
    keywords=[Keyword.MARTIAL, Keyword.HEALING],
    requires=_somebody_is_dying,
    requires_text="needs a dying ally beside you",
)
def p12698(c: Cast) -> None:
    """"One dying ally" is a narrowing the Target line cannot hold, so the
    state is asked here -- and standing up is ending whatever put the
    creature down, which is what `actions.perform` does for the move action.
    """
    who = c.target
    if who is None or not c.is_(Condition.DYING, on=who):
        return
    if c.may("spend a surge", who=who):
        c.surge(on=who)
        stand(c, who)


@power(
    "p12850",
    level=6,
    cls="fighter",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=MARTIAL,
)
def p12850(c: Cast) -> None:
    c.mark(until=When.EONT)
    if c.first and c.dex_mod > 0:
        c.resist(c.dex_mod, on=c.me, until=When.EONT)


@power(
    "p2238",
    level=6,
    cls="fighter",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    out_of_combat=True,
)
def p2238(c: Cast) -> None:
    """Athletics and Strength checks, and the engine rolls neither."""


@power(
    "p7395",
    level=6,
    cls="fighter",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=MARTIAL,
)
def p7395(c: Cast) -> None:
    """The temporary hit points count the whole burst, so they are taken
    once rather than once per target."""
    if not c.can_see():
        return
    c.mark(until=When.EONT)
    if c.first:
        caught = len([f for f in c.in_squares(c.area(), side="enemy") if c.can_see(f)])
        c.temp_hp(c.con_mod + caught, on=c.me)


@power(
    "p9997",
    level=6,
    cls="fighter",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(1),
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL, Keyword.ZONE],
)
def p9997(c: Cast) -> None:
    """The errata'd text: a daily, taken as a minor action.

    The opening is handed out from each attack's declaration rather than
    fixed now -- who is standing in the zone changes, and a relation set at
    this moment would freeze the answer.
    """
    me = c.me
    area = c.area()
    zone = c.zone(area, label=c.ref, until=When.ENCOUNTER)

    def offer(ev: AttackDeclared) -> None:
        if ev.attacker != me:
            return
        if ev.target in c.world.zones.occupants(zone):
            c.grants_advantage(on=ev.target, to=me, until=When.EOT)

    def wandered(ev: MoveEnd) -> None:
        if ev.actor == me and not (squares_of(c.world, me) & area):
            c.world.zones.end(zone, "left the zone")

    c.watch(
        AttackDeclared, offer, until=When.ENCOUNTER, window=Window.BEFORE, on=me,
        label=f"{c.ref} opening",
    )
    c.watch(MoveEnd, wandered, until=When.ENCOUNTER, on=me, label=f"{c.ref} anchor")


# -- move actions -----------------------------------------------------------


@power(
    "p12676",
    level=6,
    cls="fighter",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
)
def p12676(c: Cast) -> None:
    c.move(c.speed_of() + max(0, c.con_mod))


@power(
    "p12700",
    level=6,
    cls="fighter",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
)
def p12700(c: Cast) -> None:
    """"Against opportunity attacks" is a gate the attack context can answer:
    it carries `opportunity` for exactly this."""
    for guard in (AC, FORT, REF, WILL):
        c.bonus(
            guard, 5, on=c.me, until=When.EOT,
            when=lambda ctx: bool(ctx.get("opportunity")),
        )
    c.move(c.speed_of())


@power(
    "p4327",
    level=6,
    cls="fighter",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
)
def p4327(c: Cast) -> None:
    from combat_engine.engine import Gear

    gear = c.world.get(c.me, Gear)
    heavy = gear is not None and gear.armour in ("scale", "plate")
    close_by_shift(c, 2 if heavy else 3)


# -- answering something ----------------------------------------------------


@power(
    "p10498",
    level=6,
    cls="fighter",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    trigger=_CLOSE_HIT_ME,
    on=Trigger(AttackRolled, _would_land_in_melee, _CLOSE_HIT_ME),
)
def p10498(c: Cast) -> None:
    """The defence the attack is actually aimed at, which the event names --
    the engine re-reads it once this window closes, so raising it here is
    what turns the blow aside."""
    guard = getattr(c.trigger, "vs", AC)
    c.bonus(guard, max(1, c.dex_mod), on=c.me, until=When.EOT, once=True)


@power(
    "p10500",
    level=6,
    cls="fighter",
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    trigger=_HEALED_BY_AN_ALLY,
    on=Trigger(Healed, _healed_by_an_ally, _HEALED_BY_AN_ALLY),
)
def p10500(c: Cast) -> None:
    if stand(c, c.me):
        c.shift(1)
    else:
        c.shift(3)


@power(
    "p10501",
    level=6,
    cls="fighter",
    usage=ENCOUNTER,
    action=REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL,
    trigger=_MISSED_ME_IN_MELEE,
    on=Trigger(Miss, _missed_me_in_melee, _MISSED_ME_IN_MELEE),
)
def p10501(c: Cast) -> None:
    c.penalty("attack", 2, until=When.EOTNT)
    for guard in (AC, FORT, REF, WILL):
        c.penalty(guard, 2, until=When.EOTNT)


@power(
    "p12674",
    level=6,
    cls="fighter",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    trigger=_A_SAVE_I_DISLIKE,
    on=Trigger(SavingThrow, about_me, _A_SAVE_I_DISLIKE),
)
def p12674(c: Cast) -> None:
    """`SavingThrow` is announced before it is acted on and its outcome is
    read back off the event, which is what makes a reroll possible at all --
    `c.unsave` uses the same door. The second result stands, good or bad.
    """
    ev = c.trigger
    if ev is None:
        return
    ev.natural = c.roll("1d20")
    ev.saved = ev.natural + ev.bonus >= 10
    c.note(f"{c.ref}: rerolled to {ev.natural}")


@power(
    "p12699",
    level=6,
    cls="fighter",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    trigger=_STUCK_AT_DAWN,
    on=Trigger(TurnStart, _stuck_at_dawn, _STUCK_AT_DAWN),
)
def p12699(c: Cast) -> None:
    """The save has to be aimed: `c.save` takes whichever save-ends effect
    it finds first, and the printed line names three conditions."""
    for effect in c.world.effects.of(c.me):
        if effect.when is When.SAVE_ENDS and any(
            card in _SAVE_SHAKES for card in effect.conditions
        ):
            effect.save_mod += 5
            c.world.effects.save(effect)
            return


@power(
    "p12701",
    level=6,
    cls="fighter",
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    trigger=_MELEE_HIT_ME,
    on=Trigger(Hit, _melee_hit_me, _MELEE_HIT_ME),
)
def p12701(c: Cast) -> None:
    foe = getattr(c.trigger, "attacker", None)
    if foe is None:
        return
    for guard in (AC, FORT, REF, WILL):
        c.bonus(
            guard, 2, on=c.me, until=When.EOTNT,
            when=lambda ctx: ctx.get("attacker") == foe,
        )


@power(
    "p13776",
    level=6,
    cls="fighter",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=CloseBurst(3),
    target=ONE_CREATURE,
    keywords=[Keyword.MARTIAL, Keyword.ARCANE, Keyword.CHARM],
    trigger=_SHOT_AT_MY_FRIEND,
    on=Trigger(AttackRolled, _shot_at_my_friend, _SHOT_AT_MY_FRIEND),
)
def p13776(c: Cast) -> None:
    """The penalty goes on the roll's own total, which the engine re-reads
    after this window; whether it then misses is read off the same result."""
    ev = c.trigger
    result = getattr(ev, "result", None)
    foe = getattr(ev, "attacker", None)
    if result is None or foe is None:
        return
    result.total -= 2
    # Whether it then misses is not known yet: the engine re-reads the
    # defence and recomputes the outcome once this window closes. So the
    # second half waits for the `Miss` that says so.
    struck = getattr(ev, "target", None)

    def if_it_missed(missed: Miss) -> None:
        if missed.attacker == foe and missed.target == struck:
            c.pull(1, on=foe)

    c.watch(Miss, if_it_missed, until=When.EOT, on=c.me, once=True, label=f"{c.ref} recoil")


@power(
    "p4328",
    level=6,
    cls="fighter",
    usage=DAILY,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    trigger=_ANY_HIT_ME,
    on=Trigger(Hit, _hit_me_with_anything, _ANY_HIT_ME),
)
def p4328(c: Cast) -> None:
    foe = getattr(c.trigger, "attacker", None)
    if foe is not None:
        c.bonus(
            "attack", 2, on=c.me, until=When.ENCOUNTER,
            when=lambda ctx: ctx.get("target") == foe,
        )
