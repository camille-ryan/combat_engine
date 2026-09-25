"""Barbarian, level 10: utility. Ten rows, three of them stances.

Six print a Trigger and all six are declared. Four needed a predicate
written here: "you start your turn subject to a dazing or dominating
effect", "you are subjected to a dazing or a stunning effect", "you bloody
an enemy or reduce it to 0 hit points", and "you miss with an attack while
raging" are each about the state of the board as well as the event.

**Shrugging a condition off.** Three rows do it and the engine has no verb
for it, so `_shed` and `_strip` are here. A condition lives in two places at
once -- a count on `Conditions`, and the tuple on whichever `Effect` imposed
it -- and a relational one (dominated) lives in the relation table instead.
Taking it off one and not the others leaves either a condition nothing will
ever clear or an effect that clears a condition twice. `_shed` ends the
whole effect, which is "you end the triggering effect"; `_strip` takes the
one condition out and leaves the rest of the effect standing, which is what
an immunity to being dazed does.

The eleventh row of the level is left out; see the report.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DAILY,
    ENCOUNTER,
    FORT,
    FREE,
    INTERRUPT,
    MINOR,
    MOVE,
    PERSONAL,
    REF,
    SELF,
    WILL,
    ActionType,
    Bloodied,
    Cast,
    CloseBurst,
    Condition,
    ConditionApplied,
    Conditions,
    Dropped,
    Event,
    Hit,
    Keyword,
    Miss,
    Relation,
    Target,
    Trigger,
    TurnEnd,
    TurnStart,
    Usage,
    When,
    World,
    get,
    power,
    targets_me,
)
from combat_engine.engine.events import ConditionEnded, EffectApplied, ForcedMove
from combat_engine.engine.query import team

from .rage import held_by, raging

PRIMAL = [Keyword.PRIMAL]

#: How far back a predicate looks for the blow that caused what it answers.
#: `Bloodied` and `Dropped` are emitted from inside `deal_damage`, a handful
#: of events after the `DamageApplied` that did it.
_RECENT = 40


def _carriers(world: World, who: int, cond: Condition) -> list:
    return [e for e in world.effects.of(who) if cond in e.conditions]


def _unbind(world: World, who: int, cond: Condition) -> None:
    """A relational condition is held in the relation table, not on an effect."""
    if cond is Condition.DOMINATED:
        for boss in world.relations.sources(Relation.DOMINATED_BY, who):
            world.relations.clear(Relation.DOMINATED_BY, boss, who, "shrugged off")


def _shed(world: World, who: int, cond: Condition) -> bool:
    """End every effect imposing that condition. "You end the effect"."""
    conds = world.get(who, Conditions)
    if conds is None or not conds.has(cond):
        return False
    _unbind(world, who, cond)
    for eff in _carriers(world, who, cond):
        world.effects.end(eff, "shrugged off")
    if conds.has(cond):
        conds.counts.pop(cond, None)
        world.bus.emit(ConditionEnded(target=who, condition=cond, why="shrugged off"))
    return True


def _strip(world: World, who: int, cond: Condition) -> bool:
    """Take one condition off and leave the effect carrying it standing."""
    conds = world.get(who, Conditions)
    if conds is None or not conds.has(cond):
        return False
    _unbind(world, who, cond)
    for eff in _carriers(world, who, cond):
        eff.conditions = tuple(x for x in eff.conditions if x is not cond)
        conds.remove(cond)
    if conds.has(cond):
        conds.counts.pop(cond, None)
    world.bus.emit(ConditionEnded(target=who, condition=cond, why="shrugged off"))
    return True


def _struck_by(world: World, me: int, ev: Event) -> bool:
    """Did *this* creature deal the blow the event is announcing?

    `Bloodied` and `Dropped` carry only who it happened to. The blow itself
    is the nearest `DamageApplied` behind them.
    """
    who = getattr(ev, "actor", None)
    if who is None or who == me or team(world, who) is team(world, me):
        return False
    start = max(0, ev.seq - _RECENT)
    for past in reversed(world.bus.log[start:max(0, ev.seq)]):
        if past.kind == "DamageApplied" and getattr(past, "target", None) == who:
            return getattr(past, "source", None) == me
    return False


def _felled_an_enemy(c: Cast) -> bool:
    """"If you have reduced an enemy to 0 hit points during this turn"."""
    log = c.world.bus.log
    start = 0
    for i in range(len(log) - 1, -1, -1):
        e = log[i]
        if e.kind == "TurnStart" and getattr(e, "actor", None) == c.me:
            start = i
            break
    mine = {
        e.target for e in log[start:]
        if e.kind == "DamageApplied" and getattr(e, "source", None) == c.me
    }
    return any(
        e.kind == "Dropped"
        and getattr(e, "actor", None) in mine
        and team(c.world, e.actor) is not team(c.world, c.me)
        for e in log[start:]
    )


def _in_melee(ctx: dict) -> bool:
    """"Melee attack rolls and melee damage rolls". The damage context has no
    `ranged` key, so both halves read the reach off the row instead."""
    p = get(ctx.get("power", "") or "")
    return p is not None and p.reach_of(ctx.get("branch", 0)).kind == "melee"


_HELD_AT_THE_START = "you start your turn subject to a dazing or dominating effect"


def _starts_turn_held(world: World, me: int, ev: Event) -> bool:
    if getattr(ev, "actor", None) != me or getattr(ev, "ghost", False):
        return False
    conds = world.get(me, Conditions)
    return conds is not None and (
        conds.has(Condition.DAZED) or conds.has(Condition.DOMINATED)
    )


@power(
    "p14429",
    level=10,
    cls="barbarian",
    usage=DAILY,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
    trigger=_HELD_AT_THE_START,
    on=Trigger(TurnStart, when=_starts_turn_held, text=_HELD_AT_THE_START),
)
def p14429(c: Cast) -> None:
    """The immunity is a watcher that strips rather than a flag that refuses:
    `ConditionApplied` is a notification, not a proposal, and by the time it
    is announced the count is already on the creature."""
    me = c.me
    for cond in (Condition.DAZED, Condition.DOMINATED):
        _shed(c.world, me, cond)

    def ward(ev: ConditionApplied) -> None:
        if ev.target == me and ev.condition in (Condition.DAZED, Condition.DOMINATED):
            _strip(c.world, me, ev.condition)

    c.watch(ConditionApplied, ward, until=When.EONT, on=me, label=f"{c.ref} unshakeable")


_SHOVED = "you are pulled, pushed, or slid"


@power(
    "p4839",
    level=10,
    cls="barbarian",
    usage=DAILY,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=[*PRIMAL, Keyword.STANCE],
    trigger=_SHOVED,
    on=Trigger(ForcedMove, when=targets_me, text=_SHOVED),
)
def p4839(c: Cast) -> None:
    """`c.immovable` is the standing half word for word -- a `ForcedMove`
    listener that refuses -- and it is clocked on the encounter and taken
    down by the stance, because a second stance-clocked effect confuses
    `Effects.stance_of`."""
    c.cancel()
    stance = c.stance(on=c.me, label=c.ref)
    held_by(c, stance, c.immovable(until=When.ENCOUNTER, on=c.me))


@power(
    "p4840",
    level=10,
    cls="barbarian",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
)
def p4840(c: Cast) -> None:
    """A mark is a relation rather than a condition of its own, so ending it
    means ending whatever effect is holding the relation up -- clearing the
    relation alone leaves an effect that will clear it again later."""
    me = c.me
    c.temp_hp(c.level // 2 + c.con_mod, on=me)
    for eff in list(c.world.effects.of(me)):
        if any(k is Relation.MARKED_BY and t == me for k, _s, t in eff.relations):
            c.world.effects.end(eff, c.ref)
    for other in c.world.relations.sources(Relation.MARKED_BY, me):
        c.world.relations.clear(Relation.MARKED_BY, other, me, c.ref)


@power(
    "p4889",
    level=10,
    cls="barbarian",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[*PRIMAL, Keyword.STANCE],
)
def p4889(c: Cast) -> None:
    me = c.me
    stance = c.stance(on=me, label=c.ref)
    held = [c.penalty(d, 2, on=me, until=When.ENCOUNTER) for d in (AC, FORT, REF, WILL)]
    held.append(c.bonus("attack", 1, on=me, until=When.ENCOUNTER, kind="power"))
    held_by(c, stance, *held)


_DAZED_OR_STUNNED = "you are subjected to a dazing or a stunning effect"


def _landing_on(world: World, me: int, ev: Event) -> object | None:
    """The effect this `EffectApplied` is announcing, before it has bitten.

    `Effects.apply` puts the effect in `live` and announces it, and only then
    adds its conditions -- so this is the one window in which a creature is
    being stunned and is not yet stunned. It matters: a stunned creature may
    take no immediate action, so a row declared on `ConditionApplied` is
    refused by the very condition it exists to answer.
    """
    if getattr(ev, "target", None) != me:
        return None
    mine = [
        e
        for e in world.effects.live.values()
        if e.owner == me and not e.ended and e.label == getattr(ev, "label", "")
    ]
    return max(mine, key=lambda e: e.id, default=None)


def _dazing_or_stunning(world: World, me: int, ev: Event) -> bool:
    landing = _landing_on(world, me, ev)
    return landing is not None and bool(
        {Condition.DAZED, Condition.STUNNED} & set(landing.conditions)
    )


@power(
    "p4913",
    level=10,
    cls="barbarian",
    usage=DAILY,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
    trigger=_DAZED_OR_STUNNED,
    on=Trigger(EffectApplied, when=_dazing_or_stunning, text=_DAZED_OR_STUNNED),
)
def p4913(c: Cast) -> None:
    """Declared on `EffectApplied` rather than on `ConditionApplied`, and
    that is the whole trick: a stunned creature may take no immediate
    action, so by the time the condition is announced the barbarian can no
    longer answer it. `EffectApplied` is emitted a few lines earlier, while
    the effect is live and its conditions have not been handed over yet --
    so the stun is taken off the effect before it ever lands.

    Rewriting the effect rather than applying a fresh daze keeps the printed
    duration: "you are dazed instead" is the same effect wearing a lighter
    condition, and a save-ends stun turned into a one-turn daze would be a
    different power. Everything else the effect carries is left alone.
    """
    landing = _landing_on(c.world, c.me, c.trigger)
    if landing is None:
        return
    left = [x for x in landing.conditions if x not in (Condition.DAZED, Condition.STUNNED)]
    if Condition.STUNNED in landing.conditions:
        left.append(Condition.DAZED)
    landing.conditions = tuple(left)
    c.note(f"{c.ref}: {'dazed instead' if Condition.DAZED in left else 'shrugged off'}")


@power(
    "p4917",
    level=10,
    cls="barbarian",
    usage=ENCOUNTER,
    action=MOVE,
    reach=CloseBurst(5),
    target=Target(
        "other_ally", 99, everyone=True,
        label="One ally in the burst, or each ally in the burst if you have "
              "reduced an enemy to 0 hit points during this turn",
    ),
    keywords=PRIMAL,
)
def p4917(c: Cast) -> None:
    """Declared as "each ally" and narrowed in the body: how many targets a
    row takes is a header field, and this one's count is decided by what has
    already happened this turn. The whole row runs on `c.first` for that
    reason -- the choice of *which* ally cannot be made once per target.
    """
    if not c.first:
        return
    pool = [t for t in c.targets if t != c.me]
    if pool and not _felled_an_enemy(c):
        pick = c.choose(sorted(pool), f"{c.ref}: which ally is moved")
        pool = [pick] if pick is not None else []
    for who in pool:
        c.slide(2, on=who)
    c.shift(3, who=c.me)


_WENT_DOWN = "you drop to 0 hit points or fewer and do not die"


def _dropped_alive(world: World, me: int, ev: Event) -> bool:
    return getattr(ev, "actor", None) == me and not getattr(ev, "dead", False)


@power(
    "p4951",
    level=10,
    cls="barbarian",
    usage=DAILY,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
    trigger=_WENT_DOWN,
    on=Trigger(Dropped, when=_dropped_alive, text=_WENT_DOWN),
)
def p4951(c: Cast) -> None:
    """Armed before the fall rather than undoing it after. `_check_down`
    applies unconscious, prone and dying together, in one effect, *after*
    the `Dropped` this interrupts -- so the watcher is standing ready and
    takes the one condition back off as it lands. Prone and dying stay,
    which is what the printed line leaves alone.

    "The end of your **next** turn" skips the turn in progress when the
    barbarian drops on its own -- the same latch `Effects.apply` puts on an
    `EONT` duration, written out because a watcher has no clock of its own.
    """
    me = c.me
    mine = [c.world.turn == me]

    def awake(ev: ConditionApplied) -> None:
        if ev.target == me and ev.condition is Condition.UNCONSCIOUS:
            _strip(c.world, me, Condition.UNCONSCIOUS)

    watching = c.watch(
        ConditionApplied, awake, until=When.EONT, on=me, label=f"{c.ref} still standing"
    )
    _strip(c.world, me, Condition.UNCONSCIOUS)

    def fade(ev: TurnEnd) -> None:
        if ev.actor != me:
            return
        if mine[0]:
            mine[0] = False
            return
        c.world.effects.end(watching, "the reprieve ran out")
        if c.is_(Condition.DYING, on=me):
            c.condition(Condition.UNCONSCIOUS, on=me, until=When.ENCOUNTER)

    c.watch(TurnEnd, fade, until=When.EONT, on=me, once=True, label=f"{c.ref} then it falls")


@power(
    "p4952",
    level=10,
    cls="barbarian",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[*PRIMAL, Keyword.STANCE],
)
def p4952(c: Cast) -> None:
    me = c.me
    stance = c.stance(on=me, label=c.ref)

    def bite(ev: Hit) -> None:
        p = get(ev.power)
        if ev.attacker != me or p is None or p.usage is not Usage.AT_WILL:
            return
        if c.cha_mod > 0:
            c.flat(c.cha_mod, on=ev.target)

    held_by(c, stance, c.watch(Hit, bite, until=When.ENCOUNTER, on=me, label=f"{c.ref} fury"))


_FELLED_OR_BLOODIED = "you bloody an enemy or reduce it to 0 hit points"


@power(
    "p9579",
    level=10,
    cls="barbarian",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
    trigger=_FELLED_OR_BLOODIED,
    on=[
        Trigger(Bloodied, when=_struck_by, text="you bloody an enemy"),
        Trigger(Dropped, when=_struck_by, text="you reduce an enemy to 0 hit points"),
    ],
)
def p9579(c: Cast) -> None:
    """Says so when there is nothing to shake off, the way `p3752` does: a
    saving throw against nothing is not a roll, and silence reads as a row
    that was never written."""
    me = c.me
    if any(e.when is When.SAVE_ENDS and not e.ended for e in c.world.effects.of(me)):
        c.save(on=me, bonus=max(1, c.cha_mod))
    else:
        c.note(f"{c.ref}: nothing a save can end")


_MISSED_RAGING = "you miss with an attack while raging"


def _missed_while_raging(world: World, me: int, ev: Event) -> bool:
    return getattr(ev, "attacker", None) == me and raging(world, me)


@power(
    "p9580",
    level=10,
    cls="barbarian",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
    trigger=_MISSED_RAGING,
    on=Trigger(Miss, when=_missed_while_raging, text=_MISSED_RAGING),
)
def p9580(c: Cast) -> None:
    c.bonus("attack", 2, on=c.me, until=When.EONT, kind="power", when=_in_melee)
    c.bonus("damage", 2, on=c.me, until=When.EONT, kind="power", when=_in_melee)
