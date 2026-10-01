"""Racial powers, the second batch: 52 rows across twenty-odd race refs.

Five shapes account for nearly all of it.

**"Strength, Constitution, or Dexterity vs. Reflex."** The header names one
ability -- it is data, and the card prints one attack line -- and the body
pays the difference: `c.strike(plus=max(0, best - declared))` takes the best
of the printed choices without inventing a second `Attack`.

**"Any enemy that *ends* its turn in the zone."** `c.hazard` and `c.burns`
bite on entering and on *starting* a turn, which is the other printed
sentence and not this one. The two zones here that read "ends its turn"
watch `TurnEnd` themselves.

**Removed from play** is `Condition.REMOVED` plus a zone, not a new state;
the condition lapsing puts the caster back where it stood, which was inside
the burst.

**An interrupt cannot cancel a condition.** `ConditionApplied` is a plain
`Event`, announced *after* `Effects.apply` has installed the condition, so
the row that swaps a stun for a daze cures the stun rather than cancelling
it. `Triggers._shrugging` waives exactly the condition being applied, which
is why a stunned creature can still answer.

**Hidden from everyone but one creature** is `c.invisible(to=...)` once per
enemy, not `c.hide` -- `c.hide` has no way to leave somebody out.

Level 11 and 21 lines are paragon and out of scope throughout.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    CON,
    DAILY,
    EACH_ALLY,
    EACH_CREATURE,
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
    STANDARD,
    STR,
    WILL,
    ActionType,
    Attack,
    AttackDeclared,
    AttackRolled,
    Cast,
    CloseBurst,
    Condition,
    ConditionApplied,
    DamageRolled,
    DamageType,
    Died,
    Dropped,
    Hit,
    InitiativeRolled,
    Keyword,
    Melee,
    MoveEnd,
    MoveStart,
    PowerUsed,
    Ranged,
    Relation,
    RelationSet,
    Size,
    Trigger,
    TurnEnd,
    TurnStart,
    When,
    about_me,
    both,
    by_charge,
    by_me,
    distance,
    enemy_within,
    get,
    hits_me,
    power,
    spread,
    targets_me,
)

if TYPE_CHECKING:
    from combat_engine.engine import Square, World

#: `ConditionApplied.duration` is the printed word, not the enum. One row
#: has to re-apply a condition "for the effect's duration".
_HELD = {w.value: w for w in When}


def _best_of(c: Cast, *mods: int) -> int:
    """The best of the ability modifiers a card offers as a choice."""
    return max(mods)


# -- predicates the ready-made set does not cover ---------------------------


def _hit_me_bloodied(world: World, me: int, ev: Any) -> bool:
    """"You are hit by an attack while bloodied."""
    from combat_engine.engine.components import Health

    health = world.get(me, Health)
    return ev.target == me and health is not None and health.bloodied


def _dominate_or_stun(world: World, me: int, ev: ConditionApplied) -> bool:
    return ev.target == me and ev.condition is Condition.STUNNED


def _dominated_me(world: World, me: int, ev: RelationSet) -> bool:
    """The dominate half of the same line: a domination is a relation and
    is never announced as a condition."""
    return ev.target == me and ev.kind_ is Relation.DOMINATED_BY


def _leaving_my_flank(world: World, me: int, ev: MoveStart) -> bool:
    """An enemy I am flanking starts to move."""
    from combat_engine.engine.query import flanked_by, team

    if ev.actor == me or team(world, ev.actor) is team(world, me):
        return False
    return flanked_by(world, ev.actor, me)


def _walks_within_3(world: World, me: int, ev: MoveStart) -> bool:
    """"An enemy within 3 squares of you moves without shifting."""
    from combat_engine.engine.query import distance_between, team

    if ev.actor == me or ev.kind_ == "shift":
        return False
    if team(world, ev.actor) is team(world, me):
        return False
    return distance_between(world, me, ev.actor) <= 3


def _hurt_by_a_trap(world: World, me: int, ev: DamageRolled) -> bool:
    """Damaged by a trap or hazard, with somebody else standing beside me."""
    from combat_engine.engine.query import adjacent, creatures, is_trap

    if ev.target != me or ev.source is None or not is_trap(world, ev.source):
        return False
    return any(o != me and adjacent(world, me, o) for o in creatures(world))


def _anyone_drops_within_5(world: World, me: int, ev: Dropped) -> bool:
    from combat_engine.engine.query import distance_between

    return ev.actor != me and distance_between(world, me, ev.actor) <= 5


def _my_turn_hit(world: World, me: int, ev: Hit) -> bool:
    """"You hit with an attack **on your turn**."""
    return ev.attacker == me and world.turn == me


def _start_turn_helpless(world: World, me: int, ev: TurnStart) -> bool:
    from combat_engine.engine.components import Health

    if ev.actor != me:
        return False
    health = world.get(me, Health)
    if health is None or health.hp < 1:
        return False
    return any(
        _suffers(world, me, cond)
        for cond in (
            Condition.DAZED,
            Condition.DOMINATED,
            Condition.STUNNED,
            Condition.UNCONSCIOUS,
        )
    )


def _suffers(world: World, eid: int, cond: Condition) -> bool:
    from combat_engine.engine.components import Conditions

    conds = world.get(eid, Conditions)
    return conds is not None and conds.has(cond)


def _beside_a_creature(world: World, eid: int) -> bool:
    """The printed Requirement: you must be adjacent to a creature."""
    from combat_engine.engine.query import adjacent, creatures

    return any(o != eid and adjacent(world, eid, o) for o in creatures(world))


def _free_squares(c: Cast, area: Any) -> list[Square]:
    grid = c.world.grid
    return [
        sq
        for sq in sorted(area)
        if grid.inside(sq) and grid.passable(sq) and grid.occupant(sq) is None
    ]


# -- r1 ---------------------------------------------------------------------


@power(
    "p12577",
    level=0,
    cls="r1",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    attack=Attack(STR, vs=WILL, plus=2),
)
def p12577(c: Cast) -> None:
    """"Strength or Charisma" is paid as `plus`, so the header stays one line."""
    if c.strike(plus=max(0, c.cha_mod - c.str_mod)):
        c.penalty("attack", 2, until=When.EONT)
        c.grants_advantage(until=When.EONT)


@power(
    "p16380",
    level=2,
    cls="r1",
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(5),
    target=NO_TARGET,
    keywords=[Keyword.FEAR],
)
def p16380(c: Cast) -> None:
    """The target line is "affected by your p12577", which `c.suffering`
    answers by label -- every effect is labelled with the ref that laid it."""
    near = set(c.within(5, side="enemy"))
    caught = [foe for foe in c.suffering("p12577") if foe in near]
    foe = c.choose(caught, "which enemy")
    if foe is not None:
        c.dazed(until=When.SAVE_ENDS, on=foe)


# -- r2 ---------------------------------------------------------------------


@power(
    "p14385",
    level=10,
    cls="r2",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="an effect would dominate or stun you",
    on=(
        Trigger(ConditionApplied, _dominate_or_stun, "an effect stuns you"),
        Trigger(RelationSet, _dominated_me, "an effect dominates you"),
    ),
)
def p14385(c: Cast) -> None:
    """`ConditionApplied` is announced after the condition is installed, so
    this cures rather than cancels, then lays the daze for the same span."""
    ev = c.trigger
    c.cure(Condition.DOMINATED, Condition.STUNNED, on=c.me)
    c.dazed(until=_HELD.get(getattr(ev, "duration", ""), When.SAVE_ENDS), on=c.me)


# -- r3 ---------------------------------------------------------------------


@power(
    "p16038",
    level=2,
    cls="r3",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def p16038(c: Cast) -> None:
    """Detection and an Arcana check: nothing on the board changes."""


# -- r4 ---------------------------------------------------------------------


@power(
    "p1450",
    level=0,
    cls="r4",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="you make an attack roll and dislike the result",
    on=Trigger(AttackRolled, by_me, "you make an attack roll"),
)
def p1450(c: Cast) -> None:
    """"Use the second roll, even if it's lower" is `keep="new"`."""
    c.reroll_attack(keep="new")


@power(
    "p16042",
    level=2,
    cls="r4",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def p16042(c: Cast) -> None:
    """Advantage against one chosen creature, but only with a bow.

    The bow clause was dropped because a relation takes no attack-context gate.
    `c.gains_advantage` does, and it carries both halves: the creature is fixed
    when the power is used, the weapon is asked at the moment of the swing --
    which is right, because the character may be holding something else by
    then.

    Both bow groups, which is what the card names."""
    seen = [foe for foe in c.enemies() if c.can_see(foe)]
    foe = c.choose(seen, "which creature")
    if foe is None:
        return
    c.gains_advantage(
        lambda ctx: ctx["target"] == foe and c.wielding("bow"),
        until=When.EONT, on=c.me,
    )


# -- r5 ---------------------------------------------------------------------


@power(
    "p14393",
    level=10,
    cls="r5",
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="an enemy flanked by you moves out of the flanked position",
    on=Trigger(MoveStart, _leaving_my_flank, "an enemy you flank moves"),
    dropped=("MoveStart.to",),
)
def p14393(c: Cast) -> None:
    """`MoveStart` is the only window where the flank still exists to read,
    and `query.flanked_by` is what reads it -- the marker this replaces
    named a function that has never existed while that one always has, so
    "an ally who was **also** flanking" was approximated as "any adjacent
    ally" for nothing.

    What is still not askable is whether the move *leaves* the flank:
    `MoveStart` carries the mover and the kind of move and not where it is
    going, so the row fires whenever a flanked enemy moves."""
    from combat_engine.engine.query import flanked_by

    foe = c.trigger.actor
    mates = [mate for mate in c.allies() if flanked_by(c.world, foe, mate)]
    friend = c.choose(mates, "which ally")
    if friend is not None:
        c.grants_advantage(on=foe, to=friend, until=When.EONT)


# -- r6 ---------------------------------------------------------------------


@power(
    "p13689",
    level=0,
    cls="r6",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    dropped=("c.bonus('skill:any')",),
)
def p13689(c: Cast) -> None:
    """Four printed choices; the skill-check one has no key to be read off."""
    pick = c.choose(["save", "shift", "attack", "skill"], "which benefit")
    if pick == "save":
        c.save()
    elif pick == "shift":
        c.shift(2, who=c.target)
    elif pick == "attack":
        c.bonus("attack", 2, kind="power", until=When.EOTNT, once=True)


@power(
    "p14389",
    level=10,
    cls="r6",
    usage=ENCOUNTER,
    action=MOVE,
    reach=CloseBurst(1),
    target=ONE_ALLY,
    dropped=("c.shift(toward=)",),
)
def p14389(c: Cast) -> None:
    """"Must end adjacent to each other" is a constraint on the destination
    the decider picks, and there is no way to hand it one."""
    c.shift(6, who=c.target)
    if c.target != c.me:
        c.shift(6, who=c.me)


# -- r7 ---------------------------------------------------------------------


@power(
    "p14397",
    level=10,
    cls="r7",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="you hit with an attack on your turn",
    on=Trigger(Hit, _my_turn_hit, "you hit on your turn"),
)
def p14397(c: Cast) -> None:
    c.temp_hp(5, on=c.me)
    c.shift(max(1, c.speed_of() // 2))


# -- r8 ---------------------------------------------------------------------


@power(
    "p1628",
    level=0,
    cls="r8",
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(10),
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
    trigger="an enemy within 10 squares of you hits you",
    on=Trigger(Hit, hits_me, "an enemy hits you"),
)
def p1628(c: Cast) -> None:
    """The target is the triggering enemy, read off the event rather than
    chosen -- `target=NO_TARGET` so nothing else is offered."""
    c.damage("1d6", max(c.int_mod, c.cha_mod), dtype=DamageType.FIRE, on=c.trigger.attacker)


@power(
    "p16388",
    level=6,
    cls="r8",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.STANCE],
)
def p16388(c: Cast) -> None:
    """The gate asks the board rather than the context -- "no ally adjacent"
    is not a key any context carries, and it is true or false per roll."""
    c.stance()
    alone = lambda ctx: not c.within(1, of=c.me, side="ally")  # noqa: E731
    for defence in (AC, FORT, REF, WILL):
        c.bonus(defence, 2, kind="power", until=When.STANCE, on=c.me, when=alone)


# -- r14 --------------------------------------------------------------------


@power(
    "p2472",
    level=0,
    cls="r14",
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POLYMORPH],
    out_of_combat=True,
)
def p2472(c: Cast) -> None:
    """Appearance and a Bluff check. The statistics are explicitly unchanged."""


# -- r16 --------------------------------------------------------------------


@power(
    "p16034",
    level=6,
    cls="r16",
    usage=DAILY,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="you use p16033",
    on=Trigger(
        PowerUsed,
        lambda w, me, ev: ev.actor == me and ev.power == "p16033",
        "you use that racial power",
    ),
    dropped=("c.hover(across=)",),
)
def p16034(c: Cast) -> None:
    """Makes the levitation sustainable, which it is not on its own.

    The trigger used to name the power in prose with no ref behind it, so
    there was nothing for `Trigger(PowerUsed, ...)` to match. It is `p16033`.

    **The sustainable thing is the levitation itself**, not a separate
    "ability to sustain": `c.effect(sustain=)` is what a printed Sustain line
    costs, and `on_sustain` runs each time it is paid -- which is where the
    card's own Sustain Move clause goes, re-upping the hover to the end of
    the next turn. Without `sustain=` a `When.SUSTAIN` hold lapses after a
    round with nobody able to pay for it.

    The one square of horizontal drift has no verb, which is the marker
    `p16033` carries for the same clause.
    """
    held = c.effect(c.ref, until=When.SUSTAIN, on=c.me, sustain=MOVE)
    if held is None:
        return
    held.on_sustain.append(lambda: c.hover(3, on=c.me, until=When.EONT))


# -- r18 --------------------------------------------------------------------


@power(
    "p2475",
    level=0,
    cls="r18",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="you are hit by an attack",
    on=Trigger(Hit, targets_me, "you are hit by an attack"),
)
def p2475(c: Cast) -> None:
    for defence in (AC, FORT, REF, WILL):
        c.bonus(defence, 2, until=When.EONT, on=c.me)


# -- r21 --------------------------------------------------------------------


@power(
    "p16459",
    level=2,
    cls="r21",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    requires=_beside_a_creature,
    requires_text="adjacent to a creature",
)
def p16459(c: Cast) -> None:
    """The printed Requirement is asked of a creature on a board mid-fight,
    which is what `requires=` is for -- unlike a feat's prerequisite."""
    c.jump(c.speed_of())


@power(
    "p16462",
    level=6,
    cls="r21",
    usage=ENCOUNTER,
    action=MOVE,
    reach=Melee(1),
    target=ONE_CREATURE,
    dropped=("Target.min_size",),
)
def p16462(c: Cast) -> None:
    """Hidden from everyone *except* the target, so it is `c.invisible(to=)`
    once per enemy rather than `c.hide`, which cannot leave one out.

    Both printed ends are written rather than left to the clock.
    `AttackDeclared` and not `Hit`, because "immediately after you attack"
    is about the swing and not about whether it landed; and the shared
    square is re-checked whenever either creature finishes a move, which
    is the only way it can stop being shared."""
    from combat_engine.engine.components import Position

    me, foe = c.me, c.target
    c.shift(1, to=c.there, share=True)
    hidden = []
    for other in c.enemies():
        if other == foe:
            continue
        eff = c.invisible(to=other, on=me, until=When.EONT)
        if eff is not None:
            hidden.append(eff)
    if not hidden:
        return

    def lift(why: str) -> None:
        while hidden:
            c.end_effect(hidden.pop(), why=why)

    def swung(ev: AttackDeclared) -> None:
        if ev.attacker == me:
            lift("you attacked")

    def parted(ev: MoveEnd) -> None:
        if ev.actor not in (me, foe):
            return
        mine = c.world.get(me, Position)
        theirs = c.world.get(foe, Position)
        if mine is None or theirs is None or mine.square != theirs.square:
            lift("you no longer share a space")

    c.watch(AttackDeclared, swung, on=me, until=When.EONT, label=c.ref)
    c.watch(MoveEnd, parted, on=me, until=When.EONT, label=c.ref)


# -- r22 --------------------------------------------------------------------


@power(
    "p16636",
    level=10,
    cls="r22",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="an enemy within 3 squares of you moves without shifting",
    on=Trigger(MoveStart, _walks_within_3, "an enemy within 3 walks"),
)
def p16636(c: Cast) -> None:
    """`MoveStart`, because by `MoveEnd` the square beside the enemy is a
    different square and the interrupt window has closed."""
    from combat_engine.engine.query import squares

    foe = c.trigger.actor
    beside = spread(squares(c.world, foe), 1)
    here = c.here
    options = [sq for sq in _free_squares(c, beside) if distance(here, sq) <= 3]
    if options:
        c.shift(3, to=min(options, key=lambda sq: distance(here, sq)))
    c.mark(on=foe, until=When.EONT)


# -- r23 --------------------------------------------------------------------


@power(
    "p2479",
    level=0,
    cls="r23",
    usage=ENCOUNTER,
    action=MOVE,
    reach=CloseBurst(2),
    target=EACH_ALLY,
)
def p2479(c: Cast) -> None:
    c.shift(1, who=c.target)
    if c.first and c.me not in c.targets:
        c.shift(1, who=c.me)


@power(
    "p16465",
    level=2,
    cls="r23",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def p16465(c: Cast) -> None:
    """The marker this replaces said a sling is not a group the engine
    has. `w:sling` is a row in the weapon table with `sling` for its
    group, so "with this sling" is an ordinary test on what the blow was
    struck with, and `engine.basic.RANGED` is the ranged basic attack's
    own ref, which is the other half of the printed sentence.

    The latch is a local rather than `once=True` on the watch: a swing
    that is not a sling's must not spend the load."""
    from combat_engine.engine.basic import RANGED

    loaded = c.roll("1d6")
    spent = {"yet": False}

    def lands(ev: Hit) -> None:
        if spent["yet"] or ev.attacker != c.me or ev.power != RANGED:
            return
        weapon = c.struck_with(ev)
        if weapon is None or weapon.ref != "w:sling":
            return
        spent["yet"] = True
        if loaded <= 2:
            c.penalty("attack", 2, on=ev.target, until=When.EOTNT)
        elif loaded <= 4:
            c.ongoing(2, DamageType.FIRE, on=ev.target)
        else:
            c.immobilized(on=ev.target, until=When.EOTNT)

    c.watch(Hit, lands, until=When.EONT, on=c.me, label=f"{c.ref} shot")


@power(
    "p16468",
    level=10,
    cls="r23",
    usage=AT_WILL,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="a trap or hazard damages you while a nonminion is adjacent",
    on=Trigger(DamageRolled, _hurt_by_a_trap, "a trap damages you"),
)
def p16468(c: Cast) -> None:
    """`c.halve` returns what it took off, which is the other half to pass on."""
    ev = c.trigger
    passed = c.halve(ev)
    others = [o for o in c.within(1, of=c.me) if not c.is_kind("minion", o)]
    victim = c.choose(others, "who takes the other half")
    if victim is not None and passed > 0:
        c.flat(passed, dtype=ev.dtype, on=victim)


# -- r26 --------------------------------------------------------------------


@power(
    "p2482",
    level=0,
    cls="r26",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
)
def p2482(c: Cast) -> None:
    c.teleport(3)
    c.insubstantial(until=When.SONT, on=c.me)


# -- r28 --------------------------------------------------------------------


@power(
    "p2485",
    level=0,
    cls="r28",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
)
def p2485(c: Cast) -> None:
    amount = 3 + c.level // 2
    c.temp_hp(amount, on=c.me)
    c.save(on=c.me, against="ongoing")
    if c.bloodied(c.me):
        c.heal(amount, on=c.me)


# -- r33 --------------------------------------------------------------------


@power(
    "p10044",
    level=0,
    cls="r33",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="you take damage",
    on=Trigger(DamageRolled, targets_me, "you take damage"),
    todo=("c.floor_damage_dice()",),
)
def p10044(c: Cast) -> None:
    """The blow has been rolled to a single number by the time it is
    announced; the dice that made it are gone, so there is nothing to floor."""


@power(
    "p1767",
    level=0,
    cls="r33",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    attack=Attack(STR, vs=FORT, plus=2),
)
def p1767(c: Cast) -> None:
    """"Touching the ground" is left as it reads: a flying creature is not a
    thing the burst can currently be asked about.

    **The card deals no damage, and the die is still asked for.** f921 gives
    this power one, which is `c.change_dice` used to turn damage on rather
    than to raise it -- the default is the empty string, so a character
    without that feat rolls nothing, exactly as printed."""
    best = _best_of(c, c.str_mod, c.con_mod, c.dex_mod)
    if c.strike(plus=max(0, best - c.str_mod)):
        hurt = c.dice_for(c.ref, "")
        if hurt:
            c.damage(hurt, best)
        c.prone()


@power(
    "p1828",
    level=0,
    cls="r33",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def p1828(c: Cast) -> None:
    """The mode is lent for the turn so the pathfinder measures 8 rather than
    the ground speed; the float down is the absence of falling damage."""
    c.mode("fly", 8, until=When.EOT, on=c.me)
    c.move(8, at="fly")


@power(
    "p14073",
    level=0,
    cls="r33",
    usage=ENCOUNTER,
    action=REACTION,
    reach=CloseBurst(2),
    target=NO_TARGET,
    keywords=[Keyword.FIRE, Keyword.ZONE, Keyword.POLYMORPH],
    trigger="you take damage from an attack",
    on=Trigger(DamageRolled, targets_me, "you take damage"),
)
def p14073(c: Cast) -> None:
    """"Ends its turn in the zone" is `TurnEnd`, not `c.burns`, which bites
    on entering and on starting a turn. Coming back into play is the
    `REMOVED` condition lapsing, which leaves the caster in the burst."""
    area = c.area()
    zone = c.zone(area, label=c.ref, until=When.SONT)
    c.grants_in(zone, "concealment", 2, side="any", kind="concealment")
    c.condition(Condition.REMOVED, until=When.SONT, on=c.me)
    heat = _best_of(c, c.int_mod, c.wis_mod, c.cha_mod)

    def scorch(ev: TurnEnd) -> None:
        if ev.actor in c.in_squares(area, side="enemy"):
            c.flat(heat, dtype=DamageType.FIRE, on=ev.actor)

    c.watch(TurnEnd, scorch, until=When.SONT, on=c.me, label=f"{c.ref} burn")


@power(
    "p14076",
    level=0,
    cls="r33",
    usage=ENCOUNTER,
    action=REACTION,
    reach=CloseBurst(1),
    target=EACH_CREATURE,
    keywords=[Keyword.FIRE, Keyword.RADIANT],
    attack=Attack(STR, vs=REF, plus=2),
    trigger="you are hit by an attack while bloodied",
    on=Trigger(Hit, _hit_me_bloodied, "you are hit while bloodied"),
)
def p14076(c: Cast) -> None:
    """One blow of two types, which is `dtypes=`: a creature resisting
    only fire or only radiant takes all of it."""
    best = _best_of(c, c.str_mod, c.con_mod, c.dex_mod)
    if c.strike(plus=max(0, best - c.str_mod)):
        c.damage(0, best, dtypes=(DamageType.FIRE, DamageType.RADIANT))
        c.penalty("attack", 2, until=When.EOTNT)
        if c.bloodied():
            c.blinded(until=When.EOTNT)


# -- r36 --------------------------------------------------------------------


@power(
    "p6189",
    level=0,
    cls="r36",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="you hit an enemy with an attack",
    on=Trigger(Hit, by_me, "you hit an enemy"),
)
def p6189(c: Cast) -> None:
    """Which die is rolled turns on the triggering power's keywords."""
    ev = c.trigger
    hit_with = get(ev.power)
    weapon = hit_with is not None and Keyword.WEAPON in hit_with.keywords
    c.damage(c.w() if weapon else "1d8", on=ev.target)


@power(
    "p16384",
    level=6,
    cls="r36",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="you charge an enemy",
    on=Trigger(AttackDeclared, both(by_me, by_charge), "you charge an enemy"),
)
def p16384(c: Cast) -> None:
    """The marker this replaces said nothing counts who swung at you
    during the run in. `world.bus.log` is the tally, and the charge's own
    `MoveStart` is the boundary -- a charge is built as a walk and then an
    attack, so everything announced between that move starting and this
    declaration happened during the movement. Counted by attacker, since
    the card counts enemies and not blows.

    The bonus is laid in the `AttackDeclared` window, before the roll, and
    is gated on the use being a charge so the swing it pays for is the one
    the trigger named."""
    me = c.me
    c.temp_hp(c.str_mod, on=me)
    swung: set[int] = set()
    for ev in reversed(c.world.bus.log):
        if isinstance(ev, MoveStart | TurnStart) and ev.actor == me:
            break
        if isinstance(ev, AttackDeclared) and ev.target == me and ev.attacker != me:
            swung.add(ev.attacker)
    if swung:
        c.bonus("attack", len(swung), on=me, until=When.EOT, once=True,
                kind="power", when=lambda ctx: bool(ctx.get("charge")))


@power(
    "p16688",
    level=6,
    cls="r36",
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="you roll initiative",
    on=Trigger(InitiativeRolled, about_me, "you roll initiative"),
)
def p16688(c: Cast) -> None:
    """The roll has happened, so this moves the creature in the order by the
    difference between the two modifiers rather than changing the roll."""
    endurance = c.passive("endurance") - 10
    c.initiative(endurance - c.dex_mod, on=c.me)


# -- r38 --------------------------------------------------------------------


@power(
    "p5599",
    level=0,
    cls="r38",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(1),
    target=EACH_CREATURE,
    attack=Attack(STR, vs=REF, plus=2),
)
def p5599(c: Cast) -> None:
    """The die is asked for, not written in: f3786 raises it to a d8."""
    best = _best_of(c, c.str_mod, c.con_mod, c.dex_mod)
    if c.strike(plus=max(0, best - c.str_mod)):
        c.damage(c.dice_for(c.ref, "1d6"), best)


@power(
    "p16641",
    level=10,
    cls="r38",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Melee(1),
    target=NO_TARGET,
)
def p16641(c: Cast) -> None:
    """"Adjacent for movement purposes" is exactly `c.link`, which writes
    `Grid.links` and is read by the pathfinder and by nothing else."""
    from combat_engine.engine.components import Position

    doors = c.scenery(within=1)
    door = c.choose(doors, "which object")
    if door is None:
        return
    at = c.world.get(door, Position)
    if at is None:
        return
    far = [sq for sq in _free_squares(c, spread({at.square}, 20)) if sq != at.square]
    there = c.choose(far, "where it opens onto")
    if there is not None:
        c.link(at.square, there, until=When.EONT)


# -- r43 --------------------------------------------------------------------


@power(
    "p16543",
    level=2,
    cls="r43",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(3),
    target=EACH_ALLY,
    dropped=("c.shift(toward=)",),
)
def p16543(c: Cast) -> None:
    """"Must end closer to you" is a constraint on the square the decider
    picks and there is no way to hand it one."""
    if c.target != c.me:
        c.shift(2, who=c.target)


@power(
    "p16546",
    level=10,
    cls="r43",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL],
)
def p16546(c: Cast) -> None:
    """The altitude limit is left as it reads: the grid is flat."""
    c.mode("fly", c.speed_of(), until=When.ENCOUNTER, on=c.me)


# -- r44 --------------------------------------------------------------------


@power(
    "p7443",
    level=0,
    cls="r44",
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="an enemy within 2 squares of you moves on its turn",
    on=Trigger(MoveStart, enemy_within(2), "an enemy within 2 moves"),
)
def p7443(c: Cast) -> None:
    """`MoveStart`: the distance in the trigger is measured before the move,
    and by `MoveEnd` the enemy is somewhere else."""
    foe = c.trigger.actor
    c.shift(3)
    c.bonus(
        "damage", 0, dice="1d6", until=When.EONT, on=c.me,
        when=lambda ctx: ctx["target"] == foe,
    )
    c.ignore_cover(on=c.me, until=When.EONT)


# -- r47 --------------------------------------------------------------------


@power(
    "p8278",
    level=0,
    cls="r47",
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(5),
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC],
    trigger="a creature within 5 squares of you drops to 0 hit points",
    on=Trigger(Dropped, _anyone_drops_within_5, "a creature within 5 drops"),
)
def p8278(c: Cast) -> None:
    """"One creature of your choice that you hit" is the *next* one, which
    is `once=True`. The extra is necrotic and carries that type, which is
    what the three feats riding on this power read off it."""
    c.bonus(
        "damage", max(c.con_mod, c.cha_mod), dice="1d8",
        until=When.EONT, on=c.me, once=True, dtype=DamageType.NECROTIC,
    )


# -- r49 --------------------------------------------------------------------


@power(
    "p11052",
    level=0,
    cls="r49",
    usage=ENCOUNTER,
    action=MOVE,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.TELEPORTATION],
)
def p11052(c: Cast) -> None:
    c.grants_advantage(until=When.EONT)
    if c.last:
        c.teleport(max(1, c.speed_of() // 2))


# -- r51 --------------------------------------------------------------------


@power(
    "p16549",
    level=6,
    cls="r51",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PSIONIC],
)
def p16549(c: Cast) -> None:
    """The +5 is conditional on already having cover or concealment, and both
    are carried modifiers, so `c.total` is the question."""
    sheltered = c.total("concealment", c.me) or c.total("cover", c.me)
    c.check("stealth", bonus=5 if sheltered else 0)
    c.hide(until=When.ENCOUNTER)


@power(
    "p16552",
    level=10,
    cls="r51",
    usage=DAILY,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PSIONIC],
    trigger="you start your turn dazed, dominated, stunned or unconscious",
    on=Trigger(TurnStart, _start_turn_helpless, "you start your turn helpless"),
    dropped=("c.ignore_condition(sustain=)",),
)
def p16552(c: Cast) -> None:
    """Suppressed, not cured: the condition is still standing at the end of
    the turn, which is what the printed line says."""
    held = [
        cond
        for cond in (
            Condition.DAZED,
            Condition.DOMINATED,
            Condition.STUNNED,
            Condition.UNCONSCIOUS,
        )
        if c.is_(cond, c.me)
    ]
    if held:
        c.ignore_condition(*held, on=c.me, until=When.EOT)


# -- r52 --------------------------------------------------------------------


@power(
    "p14018",
    level=10,
    cls="r52",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(3),
    target=NO_TARGET,
    keywords=[Keyword.SHADOW, Keyword.NECROTIC, Keyword.CONJURATION],
)
def p14018(c: Cast) -> None:
    """Four conjurations, each with a footprint of 1 so "adjacent to one"
    reads off an aura. The bite is `TurnEnd` rather than `c.burns`, which is
    the entering-and-starting sentence."""
    made: list[int] = []
    for square in _free_squares(c, c.area())[:4]:
        shade = c.conjure(at=square, until=When.ENCOUNTER, sustain=None, speed=4)
        if not shade:
            continue
        made.append(shade)
        ring = c.aura(1, label=c.ref, until=When.ENCOUNTER, on=shade)
        c.grants_in(ring, "attack", -2, side="enemy", kind="untyped")

    def gnaw(ev: TurnEnd) -> None:
        if ev.actor in c.enemies() and any(c.adjacent_to(shade, ev.actor) for shade in made):
            c.flat(10, dtype=DamageType.NECROTIC, on=ev.actor)

    c.watch(TurnEnd, gnaw, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} gnaw")


# -- r53 --------------------------------------------------------------------


@power(
    "p14023",
    level=10,
    cls="r53",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.SHADOW, Keyword.POLYMORPH],
)
def p14023(c: Cast) -> None:
    """A polymorph, so `revert=MINOR` is the printed way out rather than a
    stance being replaced."""
    c.form(modes={"fly": c.speed_of()}, until=When.EONT, revert=MINOR)
    c.resize(Size.TINY, on=c.me, until=When.EONT)
    c.cannot_attack(on=c.me, until=When.EONT)
    for defence in (AC, FORT, REF, WILL):
        c.bonus(defence, 2, kind="power", until=When.EONT, on=c.me)


# -- r60 --------------------------------------------------------------------


@power(
    "p15829",
    level=0,
    cls="r60",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def p15829(c: Cast) -> None:
    """The first aspect is the enemies granting advantage, not the caster
    gaining a modifier, so it is laid on each of them."""
    pick = c.choose(["advantage", "resist"], "which aspect")
    if pick == "resist":
        c.resist(5, until=When.EONT, on=c.me)
        return
    for foe in c.enemies():
        if c.can_see(foe):
            c.grants_advantage(on=foe, to=c.me, until=When.EONT)


@power(
    "p15832",
    level=10,
    cls="r60",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def p15832(c: Cast) -> None:
    c.phasing(until=When.EONT, on=c.me)
    c.insubstantial(until=When.EONT, on=c.me)
    c.shift(2)


# -- r61 --------------------------------------------------------------------


@power(
    "p15837",
    level=2,
    cls="r61",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.ILLUSION],
)
def p15837(c: Cast) -> None:
    """A d6 decides which half of the card happens."""
    if c.is_(Condition.DEAFENED):
        return
    if c.roll("1d6") <= 3:
        c.slide(2)
    else:
        c.grants_advantage(until=When.EONT)


# -- r62 --------------------------------------------------------------------


@power(
    "p15842",
    level=0,
    cls="r62",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.CHARM],
    trigger="you hit an enemy with an attack",
    on=Trigger(Hit, by_me, "you hit an enemy"),
)
def p15842(c: Cast) -> None:
    foe = c.trigger.target
    c.slide(3, on=foe)
    c.grants_advantage(on=foe, to=c.me, until=When.EONT)


@power(
    "p15845",
    level=10,
    cls="r62",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.CHARM],
    todo=("Effect.keywords", "c.save_disadvantage()"),
)
def p15845(c: Cast) -> None:
    """The aura's whole content is a penalty on saves against charm effects.
    An effect carries no keywords, so which save is a charm save cannot be
    asked, and there is no way to make one roll twice and keep the lower."""


# -- r66 --------------------------------------------------------------------


@power(
    "p16471",
    level=2,
    cls="r66",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def p16471(c: Cast) -> None:
    """One skill standing in for another, out of combat by construction."""


@power(
    "p16474",
    level=6,
    cls="r66",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def p16474(c: Cast) -> None:
    c.resist(5, until=When.ENCOUNTER, on=c.me)


@power(
    "p16477",
    level=10,
    cls="r66",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
)
def p16477(c: Cast) -> None:
    """The stone Requirement is left as it reads -- `c.terrain` is a property
    of the whole encounter, not of the square underfoot."""
    c.teleport(10)


# -- r68 --------------------------------------------------------------------


@power(
    "p16656",
    level=0,
    cls="r68",
    usage=DAILY,
    action=REACTION,
    reach=CloseBurst(2),
    target=EACH_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(CON, vs=REF, plus=2),
    trigger="you die",
    on=Trigger(Died, about_me, "you die"),
)
def p16656(c: Cast) -> None:
    best = _best_of(c, c.str_mod, c.con_mod, c.dex_mod)
    if c.strike(plus=max(0, best - c.con_mod)):
        c.damage("1d8", c.con_mod, dtype=DamageType.ACID)
        c.ongoing(5, DamageType.ACID)


# -- r69 --------------------------------------------------------------------


@power(
    "p16659",
    level=6,
    cls="r69",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="you make an attack roll",
    on=Trigger(AttackRolled, by_me, "you make an attack roll"),
)
def p16659(c: Cast) -> None:
    """The total is already on the event; the lowest defence is asked of the
    board. `c.autohit` is the only thing that survives the recompute."""
    from combat_engine.engine.query import defence

    ev = c.trigger
    lowest = min(defence(c.world, ev.target, d) for d in (AC, FORT, REF, WILL))
    if ev.total >= lowest:
        c.autohit(ev)
