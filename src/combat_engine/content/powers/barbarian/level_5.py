"""Barbarian, level 5: the daily attacks.

Almost every row here is a rage, and they all have the same shape: swing,
then `enter(c)` for the stance and a watcher clocked on the encounter and
handed to `held_by`, so the rider dies with the rage rather than carrying a
`When.STANCE` duration of its own -- the arrangement `rage.py` sets out and
`p1436` settled for the fighter.

**Where a rage rider cannot be said.** Two rows print a clause the engine
has nothing to hang on: a repeatable granted action with no id of its own,
and a rewrite of a class feature that is not modelled. The rest of each row
-- the attack and the rage itself, which is what "you must be raging" reads
-- is real and is written; the clause is named in the report. A row whose
*whole* Effect is such a clause is left out entirely instead, which is why
two of the printed fifteen are not here.

The `c.first`/`c.last` choice is not cosmetic for a burst: the Effect line
is printed after the attack, so a rage whose rider would change this very
power's damage is entered on `c.last`.
"""

from __future__ import annotations

from combat_engine.content.powers.fighter.grips import reach_weapon, two_handed
from combat_engine.engine import (
    AC,
    DAILY,
    EACH_ENEMY,
    ONE_CREATURE,
    REF,
    STANDARD,
    STR,
    Attack,
    Bloodied,
    Cast,
    CloseBurst,
    Condition,
    DamageType,
    Dropped,
    Hit,
    Keyword,
    Melee,
    Miss,
    TurnStart,
    UpTo,
    Usage,
    When,
    Window,
    World,
    both,
    by_melee,
    get,
    hits_me,
    power,
)
from combat_engine.engine.query import distance_between

from .rage import enter, held_by

PRIMAL_WEAPON = [Keyword.PRIMAL, Keyword.WEAPON]

#: What "a melee or close weapon power" covers, for the riders that name it.
_HANDS_ON = ("melee", "close_burst", "close_blast")

#: "Immobilized, restrained, or prone", which one rage pays extra against.
_CAUGHT = (Condition.IMMOBILIZED, Condition.RESTRAINED, Condition.PRONE)


def _two_handed_reach(world: World, eid: int) -> bool:
    """"Requirement: You must be wielding a two-handed reach weapon" -- the
    two printed gates the fighter already owns, asked together."""
    return two_handed(world, eid) and reach_weapon(world, eid)


@power(
    "p10059",
    level=5,
    cls="barbarian",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p10059(c: Cast) -> None:
    """The rage's rider is a *granted action* -- a shift of its own, taken as
    a minor action, for as long as the rage runs -- and nothing declares an
    action a creature may take repeatedly without a row to point
    `c.grant_row` at. The rage itself is written, since that is what every
    "while you are raging" line in the class reads; the shift is in the
    report.
    """
    if c.strike():
        c.damage(c.w(3), c.str_mod)
    else:
        c.half_damage(c.w(3), c.str_mod)
    enter(c)


@power(
    "p10066",
    level=5,
    cls="barbarian",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p10066(c: Cast) -> None:
    """"Until the end of your next turn or until the rage ends, whichever is
    longer" is the rage: a rage runs to the end of the encounter, which is
    never shorter than the end of your next turn. So the watcher is clocked
    the way every other rage rider is.
    """
    if c.strike():
        c.damage(c.w(3), c.str_mod)
    else:
        c.half_damage(c.w(3), c.str_mod)
    me = c.me
    stance = enter(c)

    def answer(ev: Hit) -> None:
        if ev.target != me or ev.attacker not in c.enemies():
            return
        for who in c.within(5, side="other"):
            c.flat(c.str_mod, dtype=DamageType.THUNDER, on=who)

    watcher = c.watch(Hit, answer, until=When.ENCOUNTER, on=me, label=f"{c.ref} rage")
    held_by(c, stance, watcher)


@power(
    "p11563",
    level=5,
    cls="barbarian",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=_two_handed_reach,
    requires_text="needs a two-handed reach weapon",
)
def p11563(c: Cast) -> None:
    """"Each enemy you can see and is not adjacent to you" narrows the Target
    line in a way the header cannot hold, so it is a guard in the body.

    The rage is entered on the last target rather than the first: its rider
    is a bonus to damage against anything two squares off, which is exactly
    what this burst is hitting, and the printed Effect comes after the
    attack.
    """
    foe = c.target
    if foe is not None and c.can_see(foe) and not c.adjacent(foe):
        if c.strike():
            c.damage(c.w(1), c.str_mod + c.con_mod)
        else:
            c.half_damage(c.w(1), c.str_mod + c.con_mod)
    if not c.last:
        return
    me = c.me
    reward = c.con_mod

    def at_arms_length(ctx: dict) -> bool:
        p = get(ctx.get("power", ""))
        if p is None or Keyword.WEAPON not in p.keywords:
            return False
        if p.reach.kind not in _HANDS_ON:
            return False
        who = ctx.get("target")
        return who is not None and distance_between(c.world, me, who) >= 2

    stance = enter(c)
    boon = c.bonus(
        "damage",
        reward,
        on=me,
        until=When.ENCOUNTER,
        kind="power",
        when=at_arms_length,
    )
    held_by(c, stance, boon)


@power(
    "p13772",
    level=5,
    cls="barbarian",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_WEAPON, Keyword.FIRE],
    attack=Attack(STR, vs=REF),
)
def p13772(c: Cast) -> None:
    """"Save ends both" is one hold carrying the burn and the condition, so
    one throw answers the pair; the Aftereffect hangs on that hold's
    `on_end`, which follows it going whichever way it went.
    """
    victim = c.target
    if c.strike():
        c.damage(c.w(1), c.str_mod)
        held = c.condition(
            Condition.IMMOBILIZED,
            until=When.SAVE_ENDS,
            ongoing=(5, DamageType.FIRE),
        )
        if held is not None and victim is not None:
            held.on_end.append(lambda: c.prone(on=victim))
    else:
        c.half_damage(c.w(1), c.str_mod)
        c.prone()

    me = c.me
    stance = enter(c)

    def on_the_floor(ctx: dict) -> bool:
        who = ctx.get("target")
        return who is not None and any(c.is_(card, on=who) for card in _CAUGHT)

    boon = c.bonus(
        "damage", 5, on=me, until=When.ENCOUNTER, kind="untyped", when=on_the_floor
    )
    held_by(c, stance, boon)


@power(
    "p14421",
    level=5,
    cls="barbarian",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p14421(c: Cast) -> None:
    """The step is taken after the first swing whether or not a second one
    follows -- the printed Effect names the first attack, not the second
    target."""
    if c.strike():
        c.damage(c.w(3), c.str_mod)
    else:
        c.half_damage(c.w(3), c.str_mod)
    if c.first:
        c.shift(c.speed_of())


@power(
    "p4831",
    level=5,
    cls="barbarian",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_WEAPON, Keyword.COLD],
    attack=Attack(STR, vs=AC),
)
def p4831(c: Cast) -> None:
    """The free swing is the target's to take, so it is asked for rather than
    assumed, and the extra die rides only on a hit -- a miss deals half of
    the printed damage line and the rider is not part of it.
    """
    foe = c.target
    opened = False
    if foe is not None and c.may("make a melee basic attack against you", who=foe):
        opened = c.grant_attack(foe, on=c.me)

    if c.strike():
        c.damage(c.w(3), c.str_mod, dtype=DamageType.COLD)
        if opened:
            c.damage(c.w(1), dtype=DamageType.COLD)
    else:
        c.half_damage(c.w(3), c.str_mod, dtype=DamageType.COLD)

    me = c.me
    bite = 3 + c.con_mod
    stance = enter(c)

    def frost(ev: Hit) -> None:
        if both(hits_me, by_melee)(c.world, me, ev):
            c.flat(bite, dtype=DamageType.COLD, on=ev.attacker)

    watcher = c.watch(Hit, frost, until=When.ENCOUNTER, on=me, label=f"{c.ref} rage")
    held_by(c, stance, watcher)


@power(
    "p4832",
    level=5,
    cls="barbarian",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_WEAPON, Keyword.THUNDER],
    attack=Attack(STR, vs=AC),
)
def p4832(c: Cast) -> None:
    """The free-action attack printed beneath this one carries no id of its
    own, so there is no row to declare and no ref for `c.grant_row`; it is a
    deliberate attack rather than a reaction, so it is not armed here either.
    Named in the report.
    """
    if c.strike():
        c.damage(c.w(2), c.str_mod, dtype=DamageType.THUNDER)
        c.dazed(until=When.SAVE_ENDS)
    else:
        c.half_damage(c.w(2), c.str_mod, dtype=DamageType.THUNDER)
    enter(c)


@power(
    "p4943",
    level=5,
    cls="barbarian",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_WEAPON, Keyword.FIRE, Keyword.HEALING],
    attack=Attack(STR, vs=AC),
)
def p4943(c: Cast) -> None:
    """Regeneration is not something the engine holds, so it is written out
    as healing at the start of each of your turns -- and unconditionally,
    since this row prints no "while bloodied" clause.

    The surge is an interrupt on dropping, so it is armed in the
    `Window.BEFORE` of `Dropped` and spends itself on its first payout.
    """
    if c.strike():
        c.damage(c.w(2), c.str_mod, dtype=DamageType.FIRE)
        c.ongoing(5, DamageType.FIRE)
    else:
        c.half_damage(c.w(2), c.str_mod, dtype=DamageType.FIRE)

    me = c.me
    stance = enter(c)

    def regenerate(ev: TurnStart) -> None:
        if ev.actor == me and not ev.ghost and c.wounded(me):
            c.heal(3, on=me)

    def rally(ev: Dropped) -> None:
        if ev.actor == me and c.may("spend a healing surge", who=me):
            c.surge(on=me)

    healing = c.watch(
        TurnStart, regenerate, until=When.ENCOUNTER, on=me, label=f"{c.ref} rage"
    )
    rescue = c.watch(
        Dropped,
        rally,
        until=When.ENCOUNTER,
        window=Window.BEFORE,
        on=me,
        once=True,
        label=f"{c.ref} last stand",
    )
    held_by(c, stance, healing, rescue)


@power(
    "p4944",
    level=5,
    cls="barbarian",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[*PRIMAL_WEAPON, Keyword.LIGHTNING],
    attack=Attack(STR, vs=AC),
)
def p4944(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.str_mod, dtype=DamageType.LIGHTNING)
    else:
        c.half_damage(c.w(2), c.str_mod, dtype=DamageType.LIGHTNING)
    if not c.first:
        return
    me = c.me
    stance = enter(c)

    def storm(ev: TurnStart) -> None:
        if ev.actor != me or ev.ghost:
            return
        for foe in c.within(1, side="enemy"):
            c.flat(3, dtype=DamageType.LIGHTNING, on=foe)

    watcher = c.watch(
        TurnStart, storm, until=When.ENCOUNTER, on=me, label=f"{c.ref} rage"
    )
    held_by(c, stance, watcher)


@power(
    "p7394",
    level=5,
    cls="barbarian",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p7394(c: Cast) -> None:
    """The swing the rider grants is an immediate reaction, which is a thing
    the holder may decline, so it is asked for; the bonus is not optional and
    is taken either way.
    """
    if c.strike():
        c.damage(c.w(3), c.str_mod)
    else:
        c.half_damage(c.w(3), c.str_mod)

    me = c.me
    stance = enter(c)

    def answer(ev: Bloodied) -> None:
        if ev.actor == me or ev.actor not in c.within(5, side="ally"):
            return
        c.bonus("attack", 2, on=me, until=When.EONT, kind="power")
        beside = [foe for foe in c.enemies() if c.adjacent(foe)]
        if not beside or not c.may("make a melee basic attack", who=me):
            return
        victim = c.choose(beside, f"{c.ref}: who the free swing answers")
        if victim is not None:
            c.basic(on=victim)

    watcher = c.watch(
        Bloodied, answer, until=When.ENCOUNTER, on=me, label=f"{c.ref} rage"
    )
    held_by(c, stance, watcher)


@power(
    "p9568",
    level=5,
    cls="barbarian",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p9568(c: Cast) -> None:
    """Both halves are measured at the start of the turn and last until the
    end of it, so the set of enemies is taken once and the damage bonus is
    gated on that set rather than re-asked when the blow lands."""
    if c.strike():
        c.damage(c.w(2), c.str_mod)
    else:
        c.half_damage(c.w(2), c.str_mod)

    me = c.me
    reward = c.cha_mod
    stance = enter(c)

    def rouse(ev: TurnStart) -> None:
        if ev.actor != me or ev.ghost:
            return
        beside = set(c.within(1, side="enemy"))
        if not beside:
            return
        for foe in sorted(beside):
            c.grants_advantage(on=foe, to=me, until=When.EOT)
        c.bonus(
            "damage",
            reward,
            on=me,
            until=When.EOT,
            kind="power",
            when=lambda ctx: ctx.get("target") in beside,
        )

    watcher = c.watch(
        TurnStart, rouse, until=When.ENCOUNTER, on=me, label=f"{c.ref} rage"
    )
    held_by(c, stance, watcher)


@power(
    "p9569",
    level=5,
    cls="barbarian",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p9569(c: Cast) -> None:
    """"The first time ... each turn" is two watchers rather than a round
    counter: one clears the latch at the start of each of your turns, the
    other pays out and sets it. The rage is entered on the last target so
    that this power's own hits are not what spends the first one.
    """
    if c.strike():
        c.damage(c.w(1), c.str_mod)
    c.ongoing(5)
    if not c.last:
        return

    me = c.me
    reward = c.str_mod
    spent: list[bool] = []
    stance = enter(c)

    def fresh(ev: TurnStart) -> None:
        if ev.actor == me and not ev.ghost:
            spent.clear()

    def shockwave(ev: Hit) -> None:
        if spent or ev.attacker != me or ev.target not in c.enemies():
            return
        p = get(ev.power)
        if p is None or Keyword.PRIMAL not in p.keywords:
            return
        if p.reach_of(getattr(ev, "branch", 0)).kind != "melee":
            return
        spent.append(True)
        for foe in c.within(1, side="enemy"):
            c.flat(reward, on=foe)

    latch = c.watch(TurnStart, fresh, until=When.ENCOUNTER, on=me, label=f"{c.ref} turn")
    watcher = c.watch(Hit, shockwave, until=When.ENCOUNTER, on=me, label=f"{c.ref} rage")
    held_by(c, stance, latch, watcher)


@power(
    "p9570",
    level=5,
    cls="barbarian",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p9570(c: Cast) -> None:
    """The rage's rider rewrites what a class feature does when it fires, and
    the feature is not modelled -- there is no row and no event announcing
    it, so there is nothing to answer. The attack and the rage are written;
    the rider is in the report.
    """
    if c.strike():
        c.damage(c.w(2), c.str_mod)
        c.push(1)
    else:
        c.half_damage(c.w(2), c.str_mod)
    enter(c)


@power(
    "p9571",
    level=5,
    cls="barbarian",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p9571(c: Cast) -> None:
    """"Any creature" is not "any enemy": the rider pays out on whatever the
    missed swing was aimed at."""
    if c.strike():
        c.damage(c.w(2), c.str_mod)
    else:
        c.half_damage(c.w(2), c.str_mod)

    me = c.me
    stance = enter(c)

    def consolation(ev: Miss) -> None:
        if ev.attacker != me:
            return
        p = get(ev.power)
        if p is None or p.usage is not Usage.AT_WILL:
            return
        if p.reach_of(getattr(ev, "branch", 0)).kind != "melee":
            return
        c.damage(c.w(1), on=ev.target)

    watcher = c.watch(Miss, consolation, until=When.ENCOUNTER, on=me, label=f"{c.ref} rage")
    held_by(c, stance, watcher)
