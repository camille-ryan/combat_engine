"""Monster abilities, level 12: the soldiers.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=AC,
printed=17)` and `Damage("2d10", 8)` -- and the engine takes the level back
out of the attack and rescales the damage if a fight is being played on
another edition's maths.

The conventions of the eleven levels below are kept: a row filed under an
action heading that is plainly a trait is declared `ActionType.NONE`; a stat
block that prints no range at all means melee 1; a printed "Effect
(Immediate Reaction)" is a reaction whatever the database's action column
says; and a helper written for an earlier level is imported rather than
copied.

Four things this file had to settle.

**A mark whose penalty is -4 is a second -2, not a replacement.** The
ordinary -2 is computed inside `resolve.attack` from the `MARKED_BY`
relation and is not a modifier anything can reach, so m226a0 lays an
ordinary mark and an extra -2 beside it on the same clock. The gate reads
`ctx["target"]`, which is the nearest thing the attack context carries to
the engine's own test: `among` -- the whole target list of one power use --
is not in the context, so a burst that catches the m226 as well as somebody
else pays this extra -2 where the engine's own would not apply. Noted on the
row.

**Two elites and no second initiative slot printed.** Neither m460 nor
m4784 prints one, so neither takes `c.extra_turn`: what they print instead
is a minor action they may take once a round, and `once_per_round=True` is
the field for that.

**A leader's healing is its own line, and a monster spends a surge only
where a row says so.** m695a0 prints "the target loses a healing surge",
which is `c.spend_surge` on the victim -- a surge spent for nothing, which
is what the printed sentence is -- and m695a1 heals a flat ten rather than
spending anything.

**Petrification is the end of a chain, not a third saving throw.** m438a1's
two failed saves are `escalate` steps, each ending the hold it came from, so
the victim never carries two of these and never gets two saving throws
against one gaze. Stone carries no escalation of its own and runs to the end
of the fight, because nothing printed lifts it.

Each stat block in ref order.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_08.brutes import (
    SMALL_ENOUGH,
    _has_hold,
    _holding,
    _is_bloodied,
)
from combat_engine.content.monsters.level_08.lurkers import _appear_beside
from combat_engine.content.monsters.level_09.brutes import _volley
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_CREATURE,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    STANDARD,
    WILL,
    ActionType,
    Attack,
    AttackDeclared,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    Damage,
    DamageType,
    Effect,
    Hit,
    Keyword,
    Melee,
    MoveEnd,
    Ranged,
    Relation,
    UpTo,
    Usage,
    When,
    World,
    by_melee,
    leaves_me_out,
    power,
    use,
)
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import alive, distance_between, team
from combat_engine.engine.triggers import Trigger, both, targets_me


def _fly_up_to(c: Cast, who: int, squares_: int) -> int:
    """Lend a flight for one move and take it back, for whoever is flying.

    `_flies` at level 11 does this for the caster and nobody else, and the
    printed line here offers the move to an ally instead. The mode is lent
    rather than assumed: `movement.mode_of` puts anything with one in the
    air the moment it moves, and `settle` would otherwise keep finding it
    there after the move is over.
    """
    lent = c.mode("fly", squares_, until=When.EOT, on=who)
    try:
        return c.move(squares_, who=who)
    finally:
        if lent is not None:
            c.world.effects.end(lent, "it lands")


def _slowed_to_stone(c: Cast, victim: int) -> None:
    """Slowed, then immobilized, then stone: one chain, one saving throw.

    `escalate` runs on a *failed* save and is handed the effect, so each
    step ends the hold it came from before laying the next. Two holds would
    be two saving throws against one printed gaze, and the last step carries
    no escalation of its own -- "no save" is where the chain stops.
    """

    def stone(eff: Effect) -> None:
        c.world.effects.end(eff, "worsened")
        c.condition(Condition.PETRIFIED, until=When.ENCOUNTER, on=eff.owner)

    def stiffen(eff: Effect) -> None:
        c.world.effects.end(eff, "worsened")
        c.condition(
            Condition.IMMOBILIZED, until=When.SAVE_ENDS, on=eff.owner, escalate=stone
        )

    c.condition(Condition.SLOWED, until=When.SAVE_ENDS, on=victim, escalate=stiffen)


# ==========================================================================
# m226
# ==========================================================================


@power(
    "m226a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d10", 8, dtype=DamageType.PSYCHIC),
)
def m226a0(c: Cast) -> None:
    """The heavier mark, and more against something that cannot move.

    The extra 3d6 is its own packet rather than a bigger header line,
    because it is conditional and the header is data that gets rescaled.
    Whether the victim is immobilized is asked before the blow: nothing in
    the hit changes it, but the reading that matters is the one at the
    moment of the attack.

    "-4 instead of the normal -2" is the ordinary mark plus a second -2 on
    the same clock: the engine's own penalty is computed inside
    `resolve.attack` from the relation and is not a modifier any row can
    reach. The gate reads `ctx["target"]`, which is as close as the attack
    context comes to the engine's own test -- `among`, the whole target list
    of one power use, is not in the context -- so a burst that catches the
    m226 as well as somebody else pays this extra -2 where the engine's own
    would not.
    """
    me, victim = c.me, c.target
    if victim is None:
        return
    held = c.is_(Condition.IMMOBILIZED, on=victim)
    if c.strike():
        c.hit()
        if held:
            c.damage("3d6", dtype=DamageType.PSYCHIC)
    c.mark(until=When.EONT, on=victim)

    def not_at_me(ctx: dict[str, Any]) -> bool:
        return ctx.get("target") != me

    c.penalty("attack", 2, until=When.EONT, on=victim, when=not_at_me)


@power(
    "m226a1",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=15),
)
def m226a1(c: Cast) -> None:
    """No damage line: the hold is the whole of the hit.

    "One Medium or smaller creature" is a target line no `Target` can say --
    one carries a side and a count -- so the aim is narrowed here rather
    than left to `_auto_targets`, which would pick the nearest and miss the
    point of the row.
    """
    victim = c.target
    if victim is None or c.size_of(victim) not in SMALL_ENOUGH:
        victim = c.choose(
            [
                foe
                for foe in sorted(c.enemies())
                if c.distance(foe) <= 5 and c.size_of(foe) in SMALL_ENOUGH
            ],
            "m226a1: which creature",
        )
    if victim is not None and c.strike(on=victim):
        c.immobilized(until=When.SAVE_ENDS, on=victim)


@power(
    "m226a2",
    level=12,
    usage=ENCOUNTER,
    action=MOVE,
    reach=CloseBurst(10),
    target=NO_TARGET,
)
def m226a2(c: Cast) -> None:
    """Either it flies or it sends somebody else up.

    Declared with no target, because the printed line is a choice between a
    move of its own and a move it hands to an ally, and a target list chosen
    before the body runs cannot express that. This creature has no fly speed
    of its own and neither need its ally, so the mode is lent for the length
    of the move and taken back.
    """
    me = c.me
    mates = sorted(mate for mate in c.allies() if c.distance(mate) <= 10)
    lift = c.choose([me, *mates], "m226a2: who flies") if mates else me
    if lift is not None:
        _fly_up_to(c, lift, 5)


# ==========================================================================
# m438
# ==========================================================================


@power(
    "m438a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d8", 5),
)
def m438a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means."""
    if c.strike():
        c.hit()


@power(
    "m438a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.GAZE],
    attack=Attack(vs=FORT, printed=17),
)
def m438a1(c: Cast) -> None:
    """No damage line at all: the chain of holds is the whole of the hit."""
    victim = c.target
    if victim is not None and c.strike():
        _slowed_to_stone(c, victim)


# ==========================================================================
# m460
# ==========================================================================


def _not_holding(world: World, eid: int) -> bool:
    """The printed Requirement: nothing in its jaws at the moment."""
    return not _has_hold(world, eid)


@power(
    "m460a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("3d6", 10),
    requires=_not_holding,
    requires_text="the m460 must not have a creature grabbed",
)
def m460a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m460a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=UpTo(2),
)
def m460a1(c: Cast) -> None:
    """Two uses of the row that prints the attack, so its damage line stays
    in one place.

    The printed Effect does not say whether the two land on one creature or
    two, so the header takes up to two and a single target is bitten twice
    -- the only reading under which "if both attacks hit the same target"
    can ever be true. `_volley` counts the hits off the bus, because `use`
    reports whether a row could be used and not whether it landed.

    The printed escape DC has nowhere to go: a grab is a relation and the
    engine has no contest to put a number in.
    """
    victim = c.target
    if victim is not None and _volley(c, "m460a0", victim):
        c.grab(on=victim)


@power(
    "m460a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=NO_TARGET,
    requires=_has_hold,
    requires_text="the m460 must have a creature grabbed",
)
def m460a2(c: Cast) -> None:
    """Forty flat, with no attack rolled: the printed line rolls none, and
    the only legal target is whatever it already has hold of."""
    prey = _holding(c.world, c.me)
    victim = c.choose(prey, "m460a2: which of them it crushes") if prey else None
    if victim is not None:
        c.flat(40, on=victim)


@power(
    "m460a3",
    level=12,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=CloseBlast(5),
    target=EACH_CREATURE,
    attack=Attack(vs=WILL, printed=15),
)
def m460a3(c: Cast) -> None:
    """No damage line: the shove and the daze are the whole of the hit.

    "Creatures in the blast" is everybody, friend as well as foe, which is
    what `EACH_CREATURE` says and what `EACH_ENEMY` would quietly narrow.
    """
    if c.strike():
        c.slide(5)
        c.dazed(until=When.EONT)


# ==========================================================================
# m4784
# ==========================================================================


_M4784_SWUNG_ELSEWHERE = (
    "an enemy marked by the m4784 and within 5 squares of it attacks without "
    "including it"
)


def _my_mark_swung_elsewhere(world: World, me: int, ev: AttackDeclared) -> bool:
    """Somebody carrying my mark is swinging at something that is not me.

    The mark is read off the relation rather than off `c.marked`, which
    needs a `Cast`. `leaves_me_out` is declared beside this rather than
    folded in, because it reads `among` -- the whole target list of the one
    power use -- and that is the half of the printed sentence a per-target
    announcement cannot answer on its own.
    """
    if ev.attacker == me:
        return False
    if not world.relations.holds(Relation.MARKED_BY, me, ev.attacker):
        return False
    return distance_between(world, me, ev.attacker) <= 5


@power(
    "m4784a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d8", 11, dtype=DamageType.FIRE),
)
def m4784a0(c: Cast) -> None:
    """The mark is an Effect line, so it lands whether or not the blow
    did."""
    if c.strike():
        c.hit()
    c.mark(until=When.EONT)


@power(
    "m4784a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
    requires=_is_bloodied,
    requires_text="the m4784 must be bloodied",
)
def m4784a1(c: Cast) -> None:
    """Both swings, each picking its own target: the printed line names
    none, and after the first blow the second is rarely worth aiming at the
    same creature. The row that prints the attack is used rather than
    copied, so its damage stays in one place."""
    for _ in range(2):
        use(c.world, c.me, "m4784a0", spend=False)


def _unbloodied(world: World, eid: int) -> bool:
    return not _is_bloodied(world, eid)


@power(
    "m4784a2",
    level=12,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=15),
    requires=_unbloodied,
    requires_text="the m4784 must not be bloodied",
)
def m4784a2(c: Cast) -> None:
    """"One enemy marked by the m4784" is a target line no `Target` can say,
    so the aim is narrowed here."""
    victim = c.target
    if victim is None or not c.marked(victim):
        victim = c.choose(
            [foe for foe in sorted(c.enemies()) if c.distance(foe) <= 5 and c.marked(foe)],
            "m4784a2: which of its marked enemies",
        )
    if victim is not None and c.strike(on=victim):
        c.condition(Condition.DOMINATED, until=When.EONT, on=victim)


@power(
    "m4784a3",
    level=12,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=CloseBurst(3),
    target=ONE_CREATURE,
)
def m4784a3(c: Cast) -> None:
    """No attack roll: the mark and the vulnerability are an Effect line.

    "One creature" rather than one enemy -- the printed line names a
    creature, and a devil marking its own is its own business -- but the
    burst's target list already comes back enemy-first, so nothing is
    narrowed here.
    """
    victim = c.target
    if victim is None:
        return
    c.mark(until=When.EONT, on=victim)
    c.vulnerable(10, DamageType.FIRE, until=When.EONT, on=victim)


@power(
    "m4784a4",
    level=12,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M4784_SWUNG_ELSEWHERE,
    on=Trigger(
        AttackDeclared,
        when=both(_my_mark_swung_elsewhere, leaves_me_out),
        text=_M4784_SWUNG_ELSEWHERE,
    ),
)
def m4784a4(c: Cast) -> None:
    """It appears beside whoever looked away, and swings.

    Declared with no target and aimed off the trigger: the dispatcher points
    a single-enemy row at whoever the event was about, and this row is about
    the creature that *swung* rather than the one it swung at. A reaction,
    not an interrupt: the printed Effect line answers the attack rather than
    stopping it, and the blow it answers has already been declared.
    """
    foe = getattr(c.trigger, "attacker", None)
    if foe is None or not alive(c.world, foe):
        return
    _appear_beside(c, foe)
    use(c.world, c.me, "m4784a0", targets=[foe], spend=False)


# ==========================================================================
# m4960
# ==========================================================================


_M4960_STRUCK = "an enemy hits the m4960 with a melee attack"
_M4960_SLIPPED = "an enemy marked by the m4960 and adjacent to it shifts"


def _marked_neighbour_shifted(world: World, me: int, ev: MoveEnd) -> bool:
    """One of my marked enemies, who was beside me, just shifted.

    `MoveEnd` rather than `MoveStart`, which fires before the first step and
    so answers about a square the creature has not left. Having *been*
    adjacent is read from the distance it covered: a shift is one square, so
    anything now two away or closer was beside me when it started.
    """
    if ev.kind_ != "shift" or ev.actor == me:
        return False
    if team(world, ev.actor) is team(world, me):
        return False
    if not world.relations.holds(Relation.MARKED_BY, me, ev.actor):
        return False
    return distance_between(world, me, ev.actor) <= 2


@power(
    "m4960a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("3d6", 8),
)
def m4960a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m4960a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d6", 4),
)
def m4960a1(c: Cast) -> None:
    """Range 10/20: the header carries the short range, which is the only
    one `Range` holds and the one this can shoot at without a penalty."""
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m4960a2",
    level=12,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=19),
    damage=Damage("1d8", 4),
    trigger=_M4960_STRUCK,
    on=Trigger(Hit, when=both(targets_me, by_melee), text=_M4960_STRUCK),
)
def m4960a2(c: Cast) -> None:
    """The dispatcher aims a single-enemy row at whoever the event was
    about, so `c.target` is the creature that struck it."""
    if c.strike():
        c.hit()


@power(
    "m4960a3",
    level=12,
    usage=AT_WILL,
    action=ActionType.OPPORTUNITY,
    reach=Melee(1),
    target=NO_TARGET,
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("2d6", 4),
    trigger=_M4960_SLIPPED,
    on=Trigger(MoveEnd, when=_marked_neighbour_shifted, text=_M4960_SLIPPED),
)
def m4960a3(c: Cast) -> None:
    """Declared with no target and aimed off the trigger: `MoveEnd` is about
    the creature that moved, and the dispatcher only points a row that takes
    one enemy."""
    who = getattr(c.trigger, "actor", None)
    if who is None or not alive(c.world, who):
        return
    if c.strike(on=who):
        c.hit(on=who)
        c.prone(on=who)


# ==========================================================================
# m695
# ==========================================================================


@power(
    "m695a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d8", 7, dtype=DamageType.NECROTIC),
)
def m695a0(c: Cast) -> None:
    """"Loses a healing surge" is a surge spent for nothing, which is what
    `c.spend_surge` is; a monster spends one only where a row says so, and
    this row says so about its victim.

    The immobilisation and the weakness are one hold carrying both
    conditions -- applied separately the victim would shake off half of a
    thing the card ends in one breath -- and they run to the end of the
    *target's* next turn, which is what the printed clock names.
    """
    if not c.strike():
        return
    c.hit()
    c.spend_surge()
    c.condition(Condition.IMMOBILIZED, Condition.WEAKENED, until=When.EOTNT)


def _pinned_enemy(world: World, eid: int) -> bool:
    """Is there an immobilized enemy in range at all?

    The printed target line rather than a printed Requirement, declared as
    one because it is the whole of what makes the row usable: with nobody
    held there is no legal target, and a row that is offered and then finds
    nobody is indistinguishable from one written wrong.
    """
    from combat_engine.engine.query import enemies, is_

    return any(
        distance_between(world, eid, foe) <= 5 and is_(world, foe, Condition.IMMOBILIZED)
        for foe in enemies(world, eid)
    )


@power(
    "m695a1",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING, Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("2d6", 18, dtype=DamageType.NECROTIC, kind=LIMITED),
    requires=_pinned_enemy,
    requires_text="an immobilized enemy must be within 5 squares",
)
def m695a1(c: Cast) -> None:
    """It drains what it pinned and passes the life around.

    "One immobilized creature" is a target line no `Target` can say, so the
    aim is narrowed here. The card spells the healing's beneficiary as
    another stat block's id; the creature every other sentence plainly means
    is this one, so it heals itself and its undead allies within 2. A flat
    ten, not a surge: nothing printed spends one.
    """
    me = c.me
    victim = c.target
    if victim is None or not c.is_(Condition.IMMOBILIZED, on=victim):
        victim = c.choose(
            [
                foe
                for foe in sorted(c.enemies())
                if c.distance(foe) <= 5 and c.is_(Condition.IMMOBILIZED, on=foe)
            ],
            "m695a1: which immobilized creature",
        )
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)
    c.heal(10, on=me)
    for mate in sorted(c.within(2, side="ally")):
        if mate != me and c.is_kind("undead", on=mate):
            c.heal(10, on=mate)
