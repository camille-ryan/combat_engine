"""Barbarian, level 6: utility.

Mostly triggered, so mostly a matter of saying the printed Trigger in a form
the dispatcher can act on. Three of them name events nothing ready-made
answers -- "you start your turn subject to an effect a save can end", "you
are hit and damaged", "an enemy misses you" -- and those carry predicates
written here.

**Shaving damage.** Nothing on `Cast` takes a number off a blow in flight,
so the rows that print it reach for `DamageRolled.amount`, which is mutable
and is the one moment the number exists and has not yet come off anybody's
hit points. A row triggered on the `Hit` arms a one-shot listener in that
event's `Window.BEFORE` instead, because the hit is announced before the
damage is rolled.

**"A saving throw against an effect that immobilizes, restrains, or slows
you"** is a search of the live effects rather than a bare `c.save`: without
a label to aim at, `c.save` takes whichever save-ends effect it finds first,
which may well be a daze when the row means the hold.
"""

from __future__ import annotations

from combat_engine.engine import (
    DAILY,
    ENCOUNTER,
    FREE,
    INTERRUPT,
    MINOR,
    PERSONAL,
    REACTION,
    SELF,
    ActionType,
    Bloodied,
    Cast,
    Condition,
    Effect,
    Event,
    Hit,
    Keyword,
    Miss,
    Relation,
    Trigger,
    TurnStart,
    When,
    Window,
    World,
    about_me,
    by_me,
    get,
    hits_me,
    power,
)
from combat_engine.engine.events import DamageRolled, InitiativeRolled

from .rage import raging

PRIMAL = [Keyword.PRIMAL]

#: "Immobilizes, restrains, or slows you" -- the three the class keeps
#: naming together.
_PINNING = (Condition.IMMOBILIZED, Condition.RESTRAINED, Condition.SLOWED)

#: What holds a creature well enough that an escape attempt has something to
#: escape from, the reading `rogue/level_7.py` settled.
_HELD = (Condition.GRABBED, Condition.RESTRAINED)


def _pinned_by(world: World, eid: int) -> Effect | None:
    """The save-ends hold this row is offering a throw against."""
    for effect in world.effects.of(eid):
        if effect.when is When.SAVE_ENDS and any(
            card in _PINNING for card in effect.conditions
        ):
            return effect
    return None


def _escape(c: Cast) -> bool:
    """A grab is a relation held up by an effect, so ending the effect is the
    escape -- the reading `rogue/level_7.py` settled."""
    out = False
    for effect in list(c.world.effects.of(c.me)):
        caught = any(card in _HELD for card in effect.conditions)
        bound = any(
            kind is Relation.GRABBED_BY and target == c.me
            for kind, _source, target in effect.relations
        )
        if caught or bound:
            c.world.effects.end(effect, c.ref)
            out = True
    for grabber in c.world.relations.sources(Relation.GRABBED_BY, c.me):
        c.world.relations.clear(Relation.GRABBED_BY, grabber, c.me, c.ref)
        out = True
    return out


_START_HELD = "you start your turn held by an effect a save can end"
_HURT_BY_AN_ATTACK = "you are hit and damaged by an attack"
_ROLLED_INITIATIVE = "you roll initiative"
_I_MISSED = "you miss with an attack"
_MISSED_ME = "an enemy misses you with an attack"
_HIT_BY_AN_ENEMY = "you are hit by an enemy's attack"


def _starts_turn_held(world: World, me: int, ev: Event) -> bool:
    return (
        getattr(ev, "actor", None) == me
        and not getattr(ev, "ghost", False)
        and _pinned_by(world, me) is not None
    )


def _attack_damaged_me(world: World, me: int, ev: Event) -> bool:
    """Damage aimed at me that a declared row dealt: `targets_me` alone also
    answers ongoing damage and a hazard, and the line says "by an attack",
    which is read off `detail` -- the ref of whatever is dealing it."""
    return (
        getattr(ev, "target", None) == me
        and getattr(ev, "amount", 0) > 0
        and get(getattr(ev, "detail", "")) is not None
    )


def _enemy_missed_me(world: World, me: int, ev: Event) -> bool:
    from combat_engine.engine.query import team

    who = getattr(ev, "attacker", None)
    return (
        getattr(ev, "target", None) == me
        and who is not None
        and team(world, who) is not team(world, me)
    )


@power(
    "p14422",
    level=6,
    cls="barbarian",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PRIMAL, Keyword.STANCE],
)
def p14422(c: Cast) -> None:
    """"Bloodied enemies grant combat advantage" is not a thing that can be
    applied once: whoever is bloodied changes during the fight. So the
    enemies already bleeding are marked at once and a watcher marks the rest
    as they get there, and everything the stance laid down goes when it does.
    """
    me = c.me
    stance = c.stance(on=me, label=c.ref)
    laid: list[Effect] = []

    def expose(foe: int) -> None:
        held = c.grants_advantage(on=foe, to=me, until=When.ENCOUNTER)
        if held is not None:
            laid.append(held)

    for foe in c.enemies():
        if c.bloodied(foe):
            expose(foe)

    def answer(ev: Bloodied) -> None:
        if ev.actor in c.enemies():
            expose(ev.actor)

    watcher = c.watch(
        Bloodied, answer, until=When.ENCOUNTER, on=me, label=f"{c.ref} watch"
    )
    boon = c.bonus(
        "damage",
        4,
        on=me,
        until=When.ENCOUNTER,
        kind="power",
        when=lambda ctx: ctx.get("target") is not None and c.bloodied(ctx["target"]),
    )
    laid.extend(x for x in (watcher, boon) if x is not None)

    def drop() -> None:
        for held in laid:
            c.world.effects.end(held, "stance ended")

    stance.on_end.append(drop)


@power(
    "p14423",
    level=6,
    cls="barbarian",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL],
    trigger=_START_HELD,
    on=Trigger(TurnStart, when=_starts_turn_held, text=_START_HELD),
)
def p14423(c: Cast) -> None:
    held = _pinned_by(c.world, c.me)
    if held is not None:
        c.save(on=c.me, bonus=2, against=held.label)


@power(
    "p4834",
    level=6,
    cls="barbarian",
    usage=DAILY,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
    trigger=_ROLLED_INITIATIVE,
    on=Trigger(InitiativeRolled, when=about_me, text=_ROLLED_INITIATIVE),
)
def p4834(c: Cast) -> None:
    """The bonus to the initiative check itself is not written: the roll has
    been made and the creature placed in the order by the time the event
    carrying it is announced, and nothing re-reads a modifier afterwards --
    the reading `p10605` settled."""
    c.bonus("attack", 2, on=c.me, until=When.ENCOUNTER, kind="power", once=True)


@power(
    "p4886",
    level=6,
    cls="barbarian",
    usage=DAILY,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
    trigger=_HURT_BY_AN_ATTACK,
    on=Trigger(DamageRolled, when=_attack_damaged_me, text=_HURT_BY_AN_ATTACK),
)
def p4886(c: Cast) -> None:
    ev = c.trigger
    if ev is None:
        return
    ev.amount //= 2
    attacker = getattr(ev, "source", None)
    if attacker is not None:
        c.bonus(
            "attack",
            2,
            on=c.me,
            until=When.EONT,
            kind="power",
            when=lambda ctx: ctx.get("target") == attacker,
        )


@power(
    "p4911",
    level=6,
    cls="barbarian",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
)
def p4911(c: Cast) -> None:
    """"Either ... or" is a choice with only one live answer at a time: a
    creature that is grabbed or restrained escapes, and anything else takes
    the throw. The bonus to an escape attempt goes nowhere -- an escape is
    ending the hold rather than a roll -- so it is spent on the save."""
    if any(c.is_(card, on=c.me) for card in _HELD) and _escape(c):
        return
    held = _pinned_by(c.world, c.me)
    if held is not None:
        c.save(on=c.me, bonus=c.str_mod, against=held.label)


@power(
    "p4912",
    level=6,
    cls="barbarian",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
)
def p4912(c: Cast) -> None:
    c.mode("climb", c.speed_of(), until=When.EONT, on=c.me)


@power(
    "p4945",
    level=6,
    cls="barbarian",
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
    requires=raging,
    requires_text="must be raging",
    trigger=_I_MISSED,
    on=Trigger(Miss, when=by_me, text=_I_MISSED),
)
def p4945(c: Cast) -> None:
    """The engine looks at the outcome again after a free action answers a
    miss, so the reroll landing is announced as the `Hit` it became."""
    c.reroll_attack()


@power(
    "p4946",
    level=6,
    cls="barbarian",
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
    trigger=_MISSED_ME,
    on=Trigger(Miss, when=_enemy_missed_me, text=_MISSED_ME),
)
def p4946(c: Cast) -> None:
    """Printed Personal with a Target line naming the triggering enemy, which
    no header field holds: the enemy comes off the event."""
    foe = getattr(c.trigger, "attacker", None)
    if foe is None:
        return
    me = c.me
    c.penalty(
        "attack",
        c.cha_mod,
        on=foe,
        until=When.EOTNT,
        when=lambda ctx: ctx.get("target") == me,
    )


@power(
    "p5501",
    level=6,
    cls="barbarian",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
)
def p5501(c: Cast) -> None:
    """The enemies are counted after the step, which is what the printed
    order says and is the whole reason to take the step first."""
    if c.con_mod > 0:
        c.shift(c.con_mod)
    c.temp_hp(c.roll("1d10") + len(c.within(2, side="enemy")), on=c.me)


@power(
    "p7412",
    level=6,
    cls="barbarian",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
    trigger=_HIT_BY_AN_ENEMY,
    on=Trigger(Hit, when=hits_me, text=_HIT_BY_AN_ENEMY),
)
def p7412(c: Cast) -> None:
    """The hit is announced before the damage is rolled, so the reduction is
    a one-shot listener in the `Window.BEFORE` of `DamageRolled` rather than
    something done here. It is spent by hand: shaving a number emits nothing,
    and `c.watch(once=True)` reads whether the handler did anything off the
    log.
    """
    foe = getattr(c.trigger, "attacker", None)
    if foe is None:
        return
    me = c.me
    spared = c.con_mod
    hold: list[Effect] = []

    def soften(ev: DamageRolled) -> None:
        if hold and ev.source == foe and ev.target == me:
            ev.amount = max(0, ev.amount - spared)
            c.world.effects.end(hold.pop(), "used")

    watcher = c.watch(
        DamageRolled,
        soften,
        until=When.EOT,
        window=Window.BEFORE,
        on=me,
        label=f"{c.ref} guard",
    )
    hold.append(watcher)

    for what in ("attack", "damage"):
        c.bonus(
            what,
            2,
            on=me,
            until=When.EONT,
            kind="power",
            once=True,
            when=lambda ctx: ctx.get("target") == foe,
        )


@power(
    "p9572",
    level=6,
    cls="barbarian",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
)
def p9572(c: Cast) -> None:
    c.temp_hp(5 + c.con_mod, on=c.me)
