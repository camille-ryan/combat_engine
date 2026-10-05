"""Monster abilities, level 12: the rest of the artillery, and one minion.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=REF,
printed=17)` and `Damage("2d8", 5)` -- and the engine takes the level back
out of the attack and rescales the damage. m5227 is filed here because it is
artillery first and a minion second, and `kind=MINION` is what says its flat
number is flat because the creature is one.

Filed beside `artillery.py` rather than appended to it: that file was written
by another batch and a tree-wide edit has cost one before.

The conventions of the eleven levels below are kept: a **trait** is a row
that costs no action, has no target, and arms the watches that hold it for
the rest of the fight; several rows the database files as standard actions
are plainly traits and are written as such; a stat block printing no range at
all means melee 1; a printed "Range 20/40" is a normal range and a long one
and the normal one is what `Range` holds; a printed "Effect (Immediate
Interrupt)" is `action=INTERRUPT` whatever the database's action column says;
a death throe is `FREE` and never `ActionType.NONE`, which is the spelling of
a trait and would go off as the fight began; and a helper written for an
earlier level is imported rather than copied.

Nine things this file had to settle.

**A printed critical line is the extra dice, not the total.** "1d6 + 6
damage (crit 3d6 + 12)" is the maximum of the ordinary line -- 12, which
`c.damage` already deals on a critical -- plus 3d6 rolled on top, and
`c.flat(c.roll(...))` is the way to add a die to a critical because
`c.damage` would maximise that too. m1105a1's printed constant is three
higher than the maximum of its own damage line; the extra dice are still
3d6 and that is what is written. See the report.

**"Chooses the damage type for each attack" cannot be said at the point of
use.** The header's `Damage` carries one `dtype` and `c.hit()` takes `on` and
`half` and nothing else, so m2044's five-way choice keeps the first printed
type in the header, carries all five as keywords, and names the gap.

**A status a card invents is a label, not a condition.** m1091's rows apply
one affliction and four other rows read it; it carries no mechanics of its
own, so it is one `Effect` under a shared label and `_M1091_STATUS` is the
only thing that spells it. The rows that add a real condition on top put it
on the *same* hold, because "X and immobilized (save ends both)" is one
saving throw.

**A three-stage saving-throw ladder is one hold.** "Slowed (save ends) /
first failed save: immobilized instead / second failed save: petrified"
escalates on the hold `escalate=` is attached to, and the swap goes through
`_refuse` and `_also` rather than by rewriting `eff.conditions` after the
handover -- which reads once as the effect is applied and once as it ends and
never in between. The petrified stage ends the hold outright: its printed
release conditions are not a saving throw.

**An escalating burn is the standing hold's number raised.** m5636a4 prints
10, then 15, then 20 on successive failures. `c.ongoing` is what applies it,
because ongoing damage of one type does not stack and that rule has to be
kept, and the hold it returns is handed the `escalate` callback afterwards.

**An aperture is a conjuration you aim through.** `c.cast_from` is the standing
form of "it can attack through it as though it were in that space", where
`c.strike(from_=)` is one swing. `speed=` is how far its maker may move it,
and the printed minor action is the gap: the engine's conjuration moves for a
move action.

**"Rolls initiative twice" is not `c.extra_turn`.** That one takes a count
handed to it; what is missing is any way to roll a second independent one,
which `c.second_initiative()` names across five levels already.

**An automatic saving throw is written onto the live `SavingThrow`.** It is a
`Decision` announced before it is acted on and `saved` is read back, so
m1003a7 answers it rather than trying to refuse the condition -- which is a
different rule and would stop the creature being dazed at all.

**A thrown weapon a monster has to go and pick up has nothing to pick up.**
A stat block carries no `Gear`, so m4130a1's retrieval clause is named rather
than approximated with a duration the card does not print.

Artillery in ref order, then the minion.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.content.monsters.level_03.controllers_sa import _also
from combat_engine.content.monsters.level_03.lurkers_sa import _restricted_to
from combat_engine.content.monsters.level_03.soldiers_sa import _secondary
from combat_engine.content.monsters.level_10.lurkers import EVERY_DEFENCE
from combat_engine.content.monsters.level_11.controllers import _held_and_softened
from combat_engine.content.monsters.level_12.artillery import _one_hold, _wilted
from combat_engine.content.monsters.level_12.brutes import _DULLED, _refuse
from combat_engine.content.monsters.level_12.brutes_sa import _rises_unless
from combat_engine.content.monsters.level_12.minions import _squares_moved_this_turn
from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    EACH_CREATURE,
    EACH_ENEMY,
    EACH_OTHER,
    ENCOUNTER,
    FORT,
    FREE,
    INTERRUPT,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    REF,
    STANDARD,
    WILL,
    ActionType,
    AreaBurst,
    Attack,
    AttackDeclared,
    AttackRolled,
    Bloodied,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    Conditions,
    Damage,
    DamageApplied,
    DamageType,
    Defences,
    Dropped,
    Effect,
    Hit,
    Keyword,
    Melee,
    Miss,
    Mod,
    Moved,
    Position,
    Ranged,
    SkillCheck,
    Square,
    TurnStart,
    UpTo,
    Usage,
    When,
    Window,
    World,
    both,
    by_melee,
    closed_on_me,
    enemy_within,
    get,
    power,
    targets_me,
    use,
)
from combat_engine.engine.events import AdjacencyGained, ConditionApplied, SavingThrow
from combat_engine.engine.monster_math import LIMITED, MINION
from combat_engine.engine.query import alive, distance_between, enemies, hidden_from
from combat_engine.engine.query import squares as squares_of
from combat_engine.engine.triggers import Trigger, about_me

#: How far a row that names a destination and no distance is allowed to look
#: for one. Several printed lines here say "the nearest square" and give no
#: number, so the search is bounded by something rather than by the board.
_NEARBY = 6


def _again(c: Cast, ref: str, times: int = 2, *, distinct: bool = False) -> None:
    """"It uses <row> N times", where the row reaches further than a sword.

    `_twice` a file over measures the span with `c.reach`, which answers for
    melee and says 1 for a bow -- so a ranged double attack found nobody. The
    span is read off the row's own `Range` instead. `distinct` is the printed
    "each attack against a different target".
    """
    declared = get(ref)
    span = declared.reach.size if declared is not None else 1
    taken: list[int] = []
    for _ in range(times):
        pool = [
            foe
            for foe in sorted(c.enemies())
            if alive(c.world, foe)
            and c.distance(foe) <= span
            and c.can_see(foe)
            and not (distinct and foe in taken)
        ]
        if not pool:
            return
        victim = c.target if c.target in pool else pool[0]
        taken.append(victim)
        use(c.world, c.me, ref, targets=[victim], spend=False)


def _enemy_starts_within(span: int) -> Callable[[World, int, Any], bool]:
    """"An enemy starts its turn within N squares of it."""

    def test(world: World, me: int, ev: Any) -> bool:
        who = getattr(ev, "actor", None)
        if who is None or who == me or getattr(ev, "ghost", False):
            return False
        return who in enemies(world, me) and distance_between(world, me, who) <= span

    return test


def _hit_me_since_my_last_turn(c: Cast, who: int) -> bool:
    """Has that creature hit this one since its previous turn began?

    Asked inside the gate rather than snapshotted when the minor action is
    spent: a monster spends one before being hit as often as after, and a set
    taken early is stale by the time the swing happens. The walk stops at the
    *second* of this creature's own turn beginnings, because the row is used
    during the first of them.
    """
    me, seen = c.me, 0
    for past in reversed(c.world.bus.log):
        if isinstance(past, TurnStart) and past.actor == me and not past.ghost:
            seen += 1
            if seen >= 2:
                return False
        if (
            isinstance(past, Hit)
            and getattr(past, "target", None) == me
            and past.attacker == who
        ):
            return True
    return False


def _free_square_near(c: Cast, who: int, *, beside: int | None = None) -> Square | None:
    """An empty square `who` fits in, optionally next to somebody.

    "Slides the target to a square adjacent to it" names a destination, which
    is what `to=` is for; no movement op will pick the square and an occupied
    one is simply refused.
    """
    from combat_engine.engine import footprint
    from combat_engine.engine.grid import spread

    pos = c.world.get(who, Position)
    if pos is None:
        return None
    want = spread(squares_of(c.world, beside), 1) if beside is not None else None
    for sq in sorted(spread(pos.squares, _NEARBY)):
        if want is not None and sq not in want:
            continue
        if all(
            c.world.grid.passable(part)
            and c.world.grid.occupant(part) in (None, who)
            for part in footprint(sq, pos.size)
        ):
            return sq
    return None


# ==========================================================================
# m1003 -- solo
# ==========================================================================


_M1003_APERTURE_CAP = 3

#: The apertures each m1003 has standing. `c.my_zones` lists auras and zones
#: as well as conjurations and a solo may be carrying both, so the ones this
#: row made are remembered by the row that made them.
_M1003_APERTURES: dict[int, list[int]] = {}


def _worst_vulnerability(c: Cast, who: int) -> DamageType:
    """The type that creature is most vulnerable to, or force if it is none.

    `Defences.vulnerable` is where `c.vulnerable` writes and where
    `resolve.deal_damage` reads, so it is the only record of the printed
    question. Ties go to the lowest-named type so the choice is repeatable.
    """
    defences = c.world.get(who, Defences)
    soft = {t: n for t, n in (defences.vulnerable if defences else {}).items() if n > 0}
    if not soft:
        return DamageType.FORCE
    worst = max(soft.values())
    return min((t for t, n in soft.items() if n == worst), key=lambda t: t.value)


@power(
    "m1003a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d6", 5),
)
def m1003a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1003a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE, Keyword.RANGED],
    attack=Attack(vs=REF, printed=16),
    damage=Damage("1d6", 7, dtype=DamageType.FORCE),
)
def m1003a1(c: Cast) -> None:
    """"Ongoing 5 variable damage", and the variable is the target's own worst
    weakness.

    "The damage type doesn't change once chosen" is what `c.ongoing` already
    gives: the type is fixed on the hold when it is laid, and the rule that
    only the highest burn of one type applies is enforced there too.
    """
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    c.ongoing(5, _worst_vulnerability(c, victim))


@power(
    "m1003a2",
    level=12,
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(5),
    target=NO_TARGET,
    keywords=[Keyword.CONJURATION],
    dropped=("c.grant_action(move_zone)",),
)
def m1003a2(c: Cast) -> None:
    """A conjuration it shoots through, and it may hold three of them.

    `c.cast_from` is the standing form of "it can attack through it as
    though it were in that space"; `c.strike(from_=)` is one swing and nothing
    held it. The sight is borrowed for the fight and falls back to the
    creature's own square whenever it has gone, which is the proviso
    the method already carries.

    `speed=4` is the printed four squares. The printed *cost* is a minor
    action and a conjuration moves for a move action, which is the clause
    named rather than approximated -- as is closing one for a free action,
    the same missing word. Over the cap the oldest one closes, which is
    what "can maintain up to three" has to mean when a fourth is opened.
    """
    standing = [
        p
        for p in _M1003_APERTURES.setdefault(c.me, [])
        if c.world.get(p, Position) is not None
    ]
    while len(standing) >= _M1003_APERTURE_CAP:
        c.dispel(standing.pop(0))
    made = c.conjure(
        at=c.origin, label=c.ref, until=When.SUSTAIN, sustain=MINOR, speed=4
    )
    if not made:
        return
    standing.append(made)
    _M1003_APERTURES[c.me] = standing
    c.cast_from(made, on=c.me, until=When.ENCOUNTER)


@power(
    "m1003a3",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.FORCE],
    attack=Attack(vs=FORT, printed=17),
    damage=Damage("2d6", 7, dtype=DamageType.FIRE, kind=LIMITED),
)
def m1003a3(c: Cast) -> None:
    """Two printed damage types and one `Damage`: the header keeps the first
    and both keywords carry the rest, which is the arrangement level 3
    settled.

    The card prints no range for the primary attack and no target line for
    the secondary at all. Melee 1 is what a stat block giving no range means,
    and the secondary is rolled against the same target -- which is what
    every other secondary on this level prints. `_secondary` takes the
    printed total back to a bonus the way the header's does. See the report.
    """
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    if _secondary(c, 17, REF, victim):
        c.damage("1d6", 7, dtype=DamageType.FIRE, on=victim)
        c.dazed(until=When.SAVE_ENDS, on=victim)


@power(
    "m1003a4",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=UpTo(2),
)
def m1003a4(c: Cast) -> None:
    """Two basic attacks, melee or ranged, and the pair of them matters.

    The two kinds are this creature's own m1003a0 and m1003a1, and which one
    is swung is decided by whether the target is in reach -- `c.basic` would
    pick one of them for the engine and could not say that two *different*
    ones landed. Both shots are rolled on the first target's pass, because
    "two attacks" is a count of swings rather than of targets: with one enemy
    on the board both go at it, and then both are the same kind and nothing
    is dazed, which is what the printed line says.
    """
    if not c.first:
        return
    shots = list(c.targets[:2])
    if len(shots) == 1:
        shots.append(shots[0])
    landed: dict[int, set[str]] = {}
    for victim in shots:
        ref = "m1003a0" if c.distance(victim) <= 2 else "m1003a1"
        if c.use_power(ref, on=victim, spend=False) and c.landed:
            landed.setdefault(victim, set()).add(ref)
    for victim, kinds in sorted(landed.items()):
        if len(kinds) > 1:
            c.dazed(until=When.SAVE_ENDS, on=victim)


@power(
    "m1003a5",
    level=12,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
)
def m1003a5(c: Cast) -> None:
    """A surge is named, so one is spent -- and a quarter of this creature's
    maximum is the number the card prints, so nothing is hand-written.

    Four separate modifiers: one "+2 to all defenses" written once would be a
    +2 to nothing. No type word is printed, so they are untyped.
    """
    c.surge(on=c.me)
    for defended in EVERY_DEFENCE:
        c.bonus(defended, 2, on=c.me, until=When.SONT)


@power(
    "m1003a6",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.second_initiative()", "c.extra_reaction()"),
)
def m1003a6(c: Cast) -> None:
    """The solo double turn, and neither half can be said.

    `c.extra_turn` splices a slot at a count handed to it; there is nothing
    that rolls a *second independent* initiative, which is the printed line
    and which five rows across four levels already name. "Its ability to take
    immediate actions refreshes on each of its turns" is the second gap: the
    budget carries one immediate action a round and nothing hands another
    back.
    """


@power(
    "m1003a7",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1003a7(c: Cast) -> None:
    """It always shrugs these off.

    Not `c.immune`: that one stops the condition landing at all, and the
    printed line is that the creature takes it and then saves. `SavingThrow`
    is a `Decision` announced before it is acted on and its `saved` is read
    back, so the answer is written onto the live event -- the same lever
    `c.unsave` uses from the other side.

    The hold is matched by `str(eff)`, which is what the event carries as
    `against`, and the charm half is read off the laying row's keywords the
    way every other "against charm effects" line is.
    """
    me = c.me

    def shrug(ev: SavingThrow) -> None:
        if ev.actor != me or ev.saved:
            return
        from combat_engine.engine.durations import keywords_of

        for eff in c.world.effects.of(me):
            if str(eff) != ev.against:
                continue
            if any(cond in _DULLED for cond in eff.conditions) or (
                Keyword.CHARM in keywords_of(eff.label)
            ):
                ev.saved = True
            return

    c.watch(SavingThrow, shrug, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m1003a8",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.threatens(from_=)",),
)
def m1003a8(c: Cast) -> None:
    """It threatens everything its reach covers, which is two squares.

    Threatening *through one of its own conjurations* is the clause that cannot
    be said:
    `c.threatens` sets how far, and there is nothing that says where from --
    a conjuration the creature shoots through opens no opportunity window
    around itself.
    """
    c.threatens(2, on=c.me)


# ==========================================================================
# m1091 -- elite
# ==========================================================================
#
# One affliction, five rows. It carries no mechanics of its own, so it is a
# label on a save-ends hold and the rows that read it ask for the label.


_M1091_STATUS = "m1091 status"
_M1091_REROLL = "a creature carrying m1091's affliction rolls an attack, a check or a save"


def _m1091_afflicted(c: Cast, who: int) -> bool:
    return any(eff.label == _M1091_STATUS for eff in c.world.effects.of(who))


def _m1091_afflict(c: Cast, who: int, *conditions: Condition) -> Effect | None:
    """The affliction, and whatever the printed line puts under the same save.

    One hold rather than two: "afflicted and immobilized (save ends both)" is
    one saving throw, and a second effect beside it would be two against one
    printed sentence. Where the creature is already carrying it the extra
    condition joins the standing hold for the same reason.
    """
    for eff in c.world.effects.of(who):
        if eff.label == _M1091_STATUS:
            for cond in conditions:
                _also(c, eff, cond)
            return eff
    return c.world.effects.apply(
        who, c.me, When.SAVE_ENDS, label=_M1091_STATUS, conditions=conditions
    )


def _m1091_rolled_by_the_afflicted(world: World, me: int, ev: Any) -> bool:
    """Whoever is rolling, when they are carrying the affliction.

    Three events, three names for the roller: `AttackRolled` says `attacker`
    and the other two say `actor`, which is why this is one predicate rather
    than `about_me` three times.
    """
    who = getattr(ev, "attacker", None)
    if who is None:
        who = getattr(ev, "actor", None)
    if who is None or who == me:
        return False
    return any(eff.label == _M1091_STATUS for eff in world.effects.of(who))


@power(
    "m1091a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d6", 5),
)
def m1091a0(c: Cast) -> None:
    victim = c.target
    if victim is not None and c.strike():
        c.hit()
        _m1091_afflict(c, victim)


@power(
    "m1091a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=NO_TARGET,
)
def m1091a1(c: Cast) -> None:
    """"Make two m1091a0 attacks", which is the row above and its reach.

    The card also carries a stray attack line of its own -- a bonus against
    no defence at all and a heavier damage expression -- which no printed
    double attack has. The sentence is what is written; the fragment is
    reported.
    """
    _again(c, "m1091a0")


@power(
    "m1091a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.RANGED],
    attack=Attack(vs=REF, printed=17),
    damage=Damage("2d6", 6, dtype=DamageType.POISON),
)
def m1091a2(c: Cast) -> None:
    victim = c.target
    if victim is not None and c.strike():
        c.hit()
        _m1091_afflict(c, victim)


@power(
    "m1091a3",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[Keyword.POISON, Keyword.RANGED],
)
def m1091a3(c: Cast) -> None:
    _again(c, "m1091a2")


@power(
    "m1091a4",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=17),
)
def m1091a4(c: Cast) -> None:
    """Only the humanoid and only the afflicted, and only one at a time.

    `Target` filters on side, count and size and not on what a creature is
    suffering or what kind of thing it is, so the chooser may hand this row
    somebody its own target line forbids -- and returning would throw the row
    away while a creature in range qualifies. `_restricted_to` redirects
    instead; `Target.kind` is the gap.

    "Can dominate only one creature at a time" is enforced by letting the
    earlier hold go, because the printed line is a limit on the m1091 and not
    a refusal of the new attack. No damage is printed, so nothing is dealt.
    """
    victim = _restricted_to(
        c, 10, lambda foe: c.is_kind("humanoid", foe) and _m1091_afflicted(c, foe)
    )
    if victim is None or not c.strike(on=victim):
        return
    for other in c.suffering(c.ref):
        for eff in list(c.world.effects.of(other)):
            if eff.label.startswith(c.ref):
                c.world.effects.end(eff, "it dominates only one creature at a time")
    c.condition(Condition.DOMINATED, until=When.SAVE_ENDS, on=victim)


@power(
    "m1091a5",
    level=12,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=Ranged(10),
    target=NO_TARGET,
    once_per_round=True,
    trigger=_M1091_REROLL,
    on=(
        Trigger(AttackRolled, when=_m1091_rolled_by_the_afflicted, text=_M1091_REROLL),
        Trigger(SkillCheck, when=_m1091_rolled_by_the_afflicted, text=_M1091_REROLL),
        Trigger(SavingThrow, when=_m1091_rolled_by_the_afflicted, text=_M1091_REROLL),
    ),
)
def m1091a5(c: Cast) -> None:
    """Three printed rolls, so three declared triggers: `on=` takes a
    sequence, and declaring one of the three would look finished.

    "The target must take the lower roll" is `keep="worst"` on each of the
    three rerolls, which is the printed instruction rather than a second roll
    offered as a choice. "Only once per round in total" is the header field,
    which is counted on the creature rather than on the victim -- which is
    exactly the distinction the printed parenthesis draws.
    """
    ev = c.trigger
    if isinstance(ev, AttackRolled):
        c.reroll_attack(keep="worst")
    elif isinstance(ev, SkillCheck):
        c.reroll_check(keep="worst")
    elif isinstance(ev, SavingThrow):
        c.reroll_save(keep="worst")


@power(
    "m1091a6",
    level=12,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(4, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.COLD],
    attack=Attack(vs=REF, printed=17),
    damage=Damage("2d6", 6, dtype=DamageType.COLD, kind=LIMITED),
)
def m1091a6(c: Cast) -> None:
    victim = c.target
    if victim is not None and c.strike():
        c.hit()
        _m1091_afflict(c, victim, Condition.IMMOBILIZED)


@power(
    "m1091a7",
    level=12,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.POISON],
    attack=Attack(vs=REF, printed=17),
    damage=Damage("2d6", 6, dtype=DamageType.POISON, kind=LIMITED),
)
def m1091a7(c: Cast) -> None:
    """"Affects enemies only" is printed, so the burst is `EACH_ENEMY` rather
    than everything standing in it."""
    victim = c.target
    if victim is not None and c.strike():
        c.hit()
        _m1091_afflict(c, victim)


@power(
    "m1091a8",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1091a8(c: Cast) -> None:
    """Two gates asked at the swing, not two numbers laid now.

    The damage half is narrower than the attack half -- it names the melee row
    specifically -- and `ctx["power"]` on the damage side is the ref of
    whatever rolled the blow, which is how a rider knows which row paid. No
    type word is printed in front of either bonus, so both are untyped.
    """
    me = c.me

    def afflicted(ctx: dict[str, Any]) -> bool:
        who = ctx.get("target")
        return who is not None and _m1091_afflicted(c, who)

    c.bonus("attack", 2, on=me, until=When.ENCOUNTER, when=afflicted)
    c.bonus(
        "damage",
        0,
        dice="2d6",
        on=me,
        until=When.ENCOUNTER,
        when=lambda ctx: afflicted(ctx) and ctx.get("power") == "m1091a0",
    )


@power(
    "m1091a9",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m1091a9(c: Cast) -> None:
    """A ritual's component cost is money spent out of a fight. Nothing on a
    board charges one, so the row is complete and deliberately inert."""


@power(
    "m1091a10",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1091a10(c: Cast) -> None:
    """Three squares is what the card prints, which is one further than its
    own melee row reaches. The printed number is the one written."""
    c.threatens(3, on=c.me)


# ==========================================================================
# m1099
# ==========================================================================


_M1099_SWUNG_AT = "an enemy makes a melee attack against the m1099"


@power(
    "m1099a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=19),
    damage=Damage("1d8", 3),
)
def m1099a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means."""
    if c.strike():
        c.hit()


@power(
    "m1099a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=19),
    damage=Damage("1d10", 5),
)
def m1099a1(c: Cast) -> None:
    """Range 20/40: the header carries the short range, which is the only one
    the engine measures."""
    if c.strike():
        c.hit()


@power(
    "m1099a2",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=22),
    damage=Damage("2d6", 5, kind=LIMITED),
    requires_text="the m1099 must be wielding its ranged weapon",
)
def m1099a2(c: Cast) -> None:
    """The printed Requirement is a piece of equipment, and a monster in this
    engine carries no `Gear` -- so it is carried as the text the card shows
    and not as a gate, which would refuse the row for a reason about the
    engine rather than about the board.

    The secondary is a second attack line against a different defence, so it
    cannot live in the header and its printed total is trimmed by hand.
    """
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    if _secondary(c, 20, FORT, victim):
        c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS, on=victim)


@power(
    "m1099a3",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(20),
    target=UpTo(3),
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=19),
    damage=Damage("1d10", 5, kind=LIMITED),
)
def m1099a3(c: Cast) -> None:
    """Three shots of the row above, each two worse.

    The header carries that row's own line rather than reaching for it through
    `use`, because `c.strike(plus=-2)` is the only way to say the printed
    penalty: nothing lends a row an attack modifier, and laying one on the
    creature would also soften anything else it swung this turn.

    Three swings whatever the board offers: with fewer than three enemies in
    range the spare shots go at the last of them, because the printed line
    counts attacks and not targets.
    """
    if not c.first:
        return
    picks = list(c.targets[:3])
    while picks and len(picks) < 3:
        picks.append(picks[-1])
    for victim in picks:
        if c.strike(on=victim, plus=-2):
            c.hit(on=victim)


@power(
    "m1099a4",
    level=12,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M1099_SWUNG_AT,
    on=Trigger(AttackDeclared, when=both(targets_me, by_melee), text=_M1099_SWUNG_AT),
)
def m1099a4(c: Cast) -> None:
    """It steps back and shoots.

    The printed Effect names a row belonging to another stat block; the
    sentence is plainly about this one, and the ranged attack it reaches for
    is this creature's own m1099a1. Declared as a reaction, so the step is
    taken after the blow has been answered -- which is also why the step is
    worth taking at all.
    """
    attacker = getattr(c.trigger, "attacker", None)
    c.shift(1)
    if attacker is not None:
        c.use_power("m1099a1", on=attacker, spend=False)


# ==========================================================================
# m1105 -- elite
# ==========================================================================
#
# Six rows print "Requirement: wand". A stat block carries no `Gear`, so the
# requirement is the text the card shows and never a gate.


_M1105_IMPLEMENT = "the m1105 must be wielding its implement"


@power(
    "m1105a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("1d10", 2, dtype=DamageType.NECROTIC),
)
def m1105a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1105a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.FORCE, Keyword.IMPLEMENT, Keyword.RANGED],
    attack=Attack(vs=REF, printed=19),
    damage=Damage("2d4", 3, dtype=DamageType.FORCE),
    requires_text=_M1105_IMPLEMENT,
)
def m1105a1(c: Cast) -> None:
    """The printed critical line is the extra dice on top of the maximum the
    ordinary line already deals on a crit, and `c.flat(c.roll(...))` is the
    way to add a rolled die to one -- `c.damage` would maximise it too."""
    if c.strike():
        c.hit()
        if c.crit:
            c.flat(c.roll("3d6"), dtype=DamageType.FORCE)


@power(
    "m1105a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR, Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=15),
    damage=Damage("2d6", 3, dtype=DamageType.PSYCHIC),
    requires_text=_M1105_IMPLEMENT,
)
def m1105a2(c: Cast) -> None:
    victim = c.target
    if victim is not None and c.strike():
        c.hit()
        _held_and_softened(c, victim, defences=2)


@power(
    "m1105a3",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=15),
    damage=Damage("2d8", 3, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m1105a3(c: Cast) -> None:
    """"Targets enemies" is printed, so the burst leaves its own side out."""
    if c.strike():
        c.hit()
        c.push(5)
        c.immobilized(until=When.SAVE_ENDS)


@power(
    "m1105a4",
    level=12,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_OTHER,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT, Keyword.RADIANT],
    attack=Attack(vs=WILL, printed=19),
    damage=Damage("1d6", 6, dtype=DamageType.RADIANT, kind=LIMITED),
    requires_text=_M1105_IMPLEMENT,
)
def m1105a4(c: Cast) -> None:
    """A blast with no target line catches everything standing in it, which is
    `EACH_OTHER` -- the creature using it is never in its own blast, and
    `EACH_CREATURE` is side "any" and would catch it."""
    if c.strike():
        c.hit()
        if c.crit:
            c.flat(c.roll("3d6"), dtype=DamageType.RADIANT)
        c.dazed(until=When.EONT)


@power(
    "m1105a5",
    level=12,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.FORCE, Keyword.IMPLEMENT, Keyword.RANGED],
    attack=Attack(vs=FORT, printed=19),
    damage=Damage("2d10", 6, dtype=DamageType.FORCE, kind=LIMITED),
    requires_text=_M1105_IMPLEMENT,
)
def m1105a5(c: Cast) -> None:
    if c.strike():
        c.hit()
        if c.crit:
            c.flat(c.roll("3d6"), dtype=DamageType.FORCE)
        c.push(3)
        c.prone()


@power(
    "m1105a6",
    level=12,
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[
        Keyword.ARCANE,
        Keyword.COLD,
        Keyword.CONJURATION,
        Keyword.IMPLEMENT,
        Keyword.RANGED,
    ],
    attack=Attack(vs=REF, printed=19),
    damage=Damage("2d8", 6, dtype=DamageType.COLD, kind=LIMITED),
    requires_text=_M1105_IMPLEMENT,
    dropped=("c.grant_action(conjuration_attack)",),
)
def m1105a6(c: Cast) -> None:
    """A conjuration that takes hold, and a sustain that keeps hurting.

    The grab is held by the conjuration rather than by its maker, which is
    what `by=` is for: the printed line is about being caught by the thing in
    the square, and the escape is made against it. `speed=6` is the printed
    six squares a move action buys.

    `c.on_sustain` is the payout half of the printed Sustain Minor; without it
    that sentence goes nowhere. Re-aiming it for a standard action is
    the clause named: nothing lets a body spend an action making a standing
    conjuration swing again, and the daily's single use is already gone.
    """
    victim = c.target
    shape = c.conjure(at=c.origin, label=c.ref, until=When.SUSTAIN, sustain=MINOR, speed=6)
    if victim is None or not c.strike(from_=shape or None):
        return
    c.hit()
    if c.crit:
        c.flat(c.roll("3d6"), dtype=DamageType.COLD)
    held = c.grab(on=victim, by=shape or None)
    if held is None:
        return

    def squeeze() -> None:
        if Condition.GRABBED in held.conditions and not held.ended:
            c.damage("1d8", 6, dtype=DamageType.COLD, on=victim)

    c.on_sustain(held, squeeze)


@power(
    "m1105a7",
    level=12,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.IMPLEMENT],
    requires_text=_M1105_IMPLEMENT,
)
def m1105a7(c: Cast) -> None:
    """"A single attack roll" is `once=True`: the modifier is spent on the next
    swing rather than carried for a turn. No type word is printed."""
    c.bonus("attack", 2, on=c.me, until=When.ENCOUNTER, once=True)


@power(
    "m1105a8",
    level=12,
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.ILLUSION],
    dropped=("c.invisible(when=)",),
)
def m1105a8(c: Cast) -> None:
    """"+2 power bonus to all defenses" is four modifiers, and the word the
    card prints in front of "bonus" is the type.

    Being unseeable only by whoever is five squares off or more cannot be
    said: `c.invisible` is held against one creature or against everybody and
    takes no gate, and the distance is re-asked every time somebody looks.
    """
    for defended in EVERY_DEFENCE:
        c.bonus(defended, 2, on=c.me, until=When.ENCOUNTER, kind="power")


# ==========================================================================
# m115831
# ==========================================================================
#
# This stat block and m5636 are the same creature in two printings. Both are
# written out: each has its own refs, and the rows differ in what they carry.


_M115831_NEARBY_START = "an enemy starts its turn within 2 squares of the m115831"


def _petrifying(c: Cast, victim: int) -> Effect | None:
    """Slowed, then immobilized instead, then stone.

    One hold and one saving throw. The swap goes through `_refuse` and
    `_also`, which take the condition off `Conditions` and put the next one
    on: rewriting `eff.conditions` after the handover reads to nobody --
    `Effects.apply` counts them in once and `Effects.end` counts them out
    once, and nothing re-reads the tuple in between.

    `escalate` runs on **every** failed save, so the stage is counted here.
    The last stage ends the hold outright, because the printed releases from
    being stone are not a saving throw and the row must not keep offering one.
    """
    stage = {"n": 0}

    def worse(eff: Effect) -> None:
        stage["n"] += 1
        if stage["n"] == 1:
            _refuse(c, victim, Condition.SLOWED)
            _also(c, eff, Condition.IMMOBILIZED)
        elif stage["n"] == 2:
            c.world.effects.end(eff, "turned to stone")
            c.condition(Condition.PETRIFIED, until=When.ENCOUNTER, on=victim)

    return c.condition(
        Condition.SLOWED, until=When.SAVE_ENDS, on=victim, escalate=worse
    )


@power(
    "m115831a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d6", 6, dtype=DamageType.POISON),
)
def m115831a0(c: Cast) -> None:
    """`c.penalty` takes no `kind` and that is the rule; a saving-throw
    penalty is keyed "save", which is what `durations` totals before a save
    is rolled."""
    if c.strike():
        c.hit()
        c.penalty("save", 2, until=When.EONT)


@power(
    "m115831a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(30),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=19),
    damage=Damage("1d10", 7),
)
def m115831a1(c: Cast) -> None:
    """The damage line prints no type -- only the burn and the keyword are
    poison -- so the header carries none. "Save ends both" is one hold."""
    victim = c.target
    if victim is not None and c.strike():
        c.hit()
        _held_and_softened(
            c,
            victim,
            conditions=(Condition.SLOWED,),
            ongoing=(5, DamageType.POISON),
        )


@power(
    "m115831a2",
    level=12,
    usage=AT_WILL,
    action=ActionType.OPPORTUNITY,
    reach=CloseBlast(2),
    target=ONE_CREATURE,
    trigger=_M115831_NEARBY_START,
    on=Trigger(
        TurnStart, when=_enemy_starts_within(2), text=_M115831_NEARBY_START
    ),
)
def m115831a2(c: Cast) -> None:
    """No attack roll is printed, so none is rolled and no damage is dealt.

    "The triggering enemy in the blast" is the one creature the row touches,
    and it is read off the trigger rather than off the target list: the
    chooser picks by side and reach and would happily hand over somebody
    else standing in the same blast.
    """
    victim = getattr(c.trigger, "actor", None) or c.target
    if victim is not None:
        _petrifying(c, victim)


# ==========================================================================
# m1609
# ==========================================================================


_M1609_VENOM = "m1609a5"


def _m1609_venom(c: Cast, victim: int) -> Effect | None:
    """The venom ladder: -2 to attacks, then weakened as well, then out cold.

    One hold, so one saving throw, and the modifier half rides on it rather
    than on an effect of its own. The last stage ends the hold: "until the end
    of the encounter" is not a save-ends duration and leaving the original
    standing would keep offering one.
    """
    stage = {"n": 0}

    def worse(eff: Effect) -> None:
        stage["n"] += 1
        if stage["n"] == 1:
            _also(c, eff, Condition.WEAKENED)
        elif stage["n"] == 2:
            c.world.effects.end(eff, "the venom finishes its work")
            c.condition(Condition.UNCONSCIOUS, until=When.ENCOUNTER, on=victim)

    hold = c.world.effects.apply(
        victim,
        c.me,
        When.SAVE_ENDS,
        label=_M1609_VENOM,
        mods=[(victim, Mod(what="attack", value=-2, kind="untyped", label=_M1609_VENOM))],
    )
    if hold is not None:
        hold.escalate = worse
    return hold


@power(
    "m1609a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d8", 5),
)
def m1609a0(c: Cast) -> None:
    """The secondary is a second attack line against a different defence, so
    it cannot live in the header and its printed total is trimmed by hand.
    What it carries is the row the card points at, used rather than copied."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    if _secondary(c, 17, FORT, victim):
        c.use_power(_M1609_VENOM, on=victim, spend=False)


@power(
    "m1609a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=19),
    damage=Damage("1d6", 5),
)
def m1609a1(c: Cast) -> None:
    """Range 10/20: the header carries the short range."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    if _secondary(c, 17, FORT, victim):
        c.use_power(_M1609_VENOM, on=victim, spend=False)


@power(
    "m1609a2",
    level=12,
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=17),
)
def m1609a2(c: Cast) -> None:
    """No damage is printed, so `c.hit` is never called and the header
    declares none.

    "Grants combat advantage to all attackers" with nobody named is the whole
    of the m1609's side, which is `to="team"`. The other half is two
    different senses: `c.no_cover` is concealment, and invisibility is
    answered by handing everyone on this side truesight *of that creature*,
    which is the one shape the engine has for "it cannot hide from you".
    """
    victim = c.target
    if victim is None or not c.strike():
        return
    c.grants_advantage(until=When.EONT, on=victim, to="team")
    c.no_cover(on=victim, until=When.EONT)
    for watcher in [c.me, *c.allies()]:
        c.truesight(of=victim, on=watcher, until=When.EONT)


@power(
    "m1609a3",
    level=12,
    usage=ENCOUNTER,
    uses=3,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.RANGED, Keyword.WEAPON],
)
def m1609a3(c: Cast) -> None:
    """Special ammunition: the ordinary shot, and a burst of fire on top.

    "The damage listed above" is this creature's own ranged row, used rather
    than copied so its numbers stay in one header. "It typically carries 3"
    is `uses=3`, which is the ammunition count rather than three separate
    rows.

    The extra damage reaches "any creatures adjacent to the target", which is
    everybody standing there and not only enemies.
    """
    victim = c.target
    if victim is None:
        return
    if not c.use_power("m1609a1", on=victim, spend=False) or not c.landed:
        return
    c.damage("1d6", 1, dtype=DamageType.FIRE, on=victim)
    for other in sorted(c.within(1, of=victim, side="any")):
        if other != victim and alive(c.world, other):
            c.damage("1d6", 1, dtype=DamageType.FIRE, on=other)


@power(
    "m1609a4",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1609a4(c: Cast) -> None:
    """A shot that misses does not give it away.

    `resolve.attack` clears `HIDDEN_FROM` for whoever swung, and it does so
    **after** `Hit` and `Miss` are announced -- so hiding again from a `Miss`
    watch is undone a few lines later, which is a row that looks finished and
    changes nothing. It was measured that way: seven watchers before the shot
    and none after.

    The window that runs later is `AttackDeclared`'s AFTER one.
    `Bus.emit(announced, roll)` runs the BEFORE subscribers, then the whole of
    the attack as its resolve callback -- the roll, the announcement and the
    give-away -- and only then the AFTER subscribers. So the set of who could
    not see it is taken in the BEFORE window, the outcome is read off the
    `Miss`, and the re-hiding is done in the AFTER window where it survives.

    An empty answer never overwrites a full one: a row that rolls a secondary
    attack declares twice, and by the second declaration the first swing has
    already given the creature away.
    """
    me = c.me
    was: dict[str, frozenset[int]] = {"unseeing": frozenset()}
    shot = {"missed": False}

    def aiming(ev: AttackDeclared) -> None:
        if ev.attacker != me:
            return
        unseeing = frozenset(hidden_from(c.world, me))
        if unseeing:
            was["unseeing"] = unseeing
        shot["missed"] = False

    def landed(ev: Hit) -> None:
        if ev.attacker == me:
            shot["missed"] = False
            was["unseeing"] = frozenset()

    def missed(ev: Miss) -> None:
        if ev.attacker != me:
            return
        swing = get(getattr(ev, "power", "") or "")
        shot["missed"] = swing is not None and swing.reach.kind == "ranged"

    def resettle(ev: AttackDeclared) -> None:
        if ev.attacker != me or not shot["missed"] or not was["unseeing"]:
            return
        for blind in sorted(was["unseeing"]):
            c.hide(from_=blind)
        shot["missed"] = False

    c.watch(
        AttackDeclared,
        aiming,
        until=When.ENCOUNTER,
        window=Window.BEFORE,
        on=me,
        label=f"{c.ref} aiming",
    )
    c.watch(Hit, landed, until=When.ENCOUNTER, on=me, label=f"{c.ref} landed")
    c.watch(Miss, missed, until=When.ENCOUNTER, on=me, label=f"{c.ref} missed")
    c.watch(
        AttackDeclared, resettle, until=When.ENCOUNTER, on=me, label=f"{c.ref} unseen"
    )


@power(
    "m1609a5",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
)
def m1609a5(c: Cast) -> None:
    """The venom's own card, which is what m1609a0 and m1609a1 point at.

    It prints no attack line of its own -- "a creature hit by a weapon coated
    in it takes..." is the sentence, and the hit is the other rows' -- so
    nothing is rolled here. `c.apply_poison` is the shape for a character who
    coats a blade and is no use to a stat block: a monster carries no `Gear`,
    so there is nothing in hand to coat and the method finds nothing.
    """
    victim = c.target
    if victim is not None:
        _m1609_venom(c, victim)


# ==========================================================================
# m1744 -- elite
# ==========================================================================


@power(
    "m1744a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d8", 3),
)
def m1744a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(2)


@power(
    "m1744a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=17),
    damage=Damage("2d8", 4, dtype=DamageType.PSYCHIC),
)
def m1744a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized(until=When.SAVE_ENDS)


@power(
    "m1744a2",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("1d8", 2, dtype=DamageType.POISON, kind=LIMITED),
)
def m1744a2(c: Cast) -> None:
    """"Ongoing 5 poison damage, a -2 penalty to Fortitude, and a -2 penalty
    to saving throws (save ends all)" is the sentence `_wilted` was written
    for a file over, and it is one hold so that it is one saving throw."""
    victim = c.target
    if victim is not None and c.strike():
        c.hit()
        _wilted(c, victim)


@power(
    "m1744a3",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(1, 20),
    target=EACH_ENEMY,
    keywords=[Keyword.THUNDER],
    attack=Attack(vs=FORT, printed=16),
    damage=Damage("2d10", 4, dtype=DamageType.THUNDER, kind=LIMITED, half_on_miss=True),
)
def m1744a3(c: Cast) -> None:
    """"Miss: half damage, and the target is not dazed" -- so the branch is
    written both ways, because the flag is declared data and no line of the
    engine reads it."""
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)
    else:
        c.hit(half=True)


# ==========================================================================
# m1785
# ==========================================================================


@power(
    "m1785a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d8", 5),
)
def m1785a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1785a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, 15),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=16),
    damage=Damage("2d6", 5),
)
def m1785a1(c: Cast) -> None:
    """"The creature in the origin square" is read off `c.origin`, which is
    the square the area was aimed at -- a Large creature standing under it
    counts, so the whole footprint is asked rather than one square."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    if c.origin is not None and c.origin in squares_of(c.world, victim):
        c.damage("1d6")


@power(
    "m1785a2",
    level=12,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(3),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=FORT, printed=16),
    damage=Damage("4d8", 3, kind=LIMITED),
)
def m1785a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(3)


@power(
    "m1785a3",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
)
def m1785a3(c: Cast) -> None:
    """It gets back up unless acid or fire put it down.

    `c.revives_unless` implements nothing -- its own docstring says so; it
    records the fact for the policy, which otherwise writes off anything at
    0 hit points. The watch pair is what stands the creature up, and the
    damage type comes off the `DamageApplied` immediately before the
    `Dropped` because `Dropped` says who struck the blow and not what with.
    """
    _rises_unless(c, 10, DamageType.ACID, DamageType.FIRE)


# ==========================================================================
# m2044 -- elite
# ==========================================================================
#
# Five printed damage types on three rows, chosen per attack. The header
# carries the first and the keywords carry all five; `c.hit` takes `on` and
# `half` and no type, which is the clause named on each of them.


_M2044_BLED = "the m2044 is first bloodied"
_M2044_STRUCK = "the m2044 is hit by a melee attack"

_M2044_TYPES = (
    DamageType.ACID,
    DamageType.COLD,
    DamageType.FIRE,
    DamageType.LIGHTNING,
    DamageType.POISON,
)


@power(
    "m2044a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=19),
    damage=Damage("1d8", 5),
)
def m2044a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2044a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[
        Keyword.ACID,
        Keyword.COLD,
        Keyword.FIRE,
        Keyword.LIGHTNING,
        Keyword.POISON,
        Keyword.RANGED,
    ],
    attack=Attack(vs=AC, printed=19),
    damage=Damage("2d6", 5, dtype=DamageType.ACID),
    dropped=("c.hit(dtype=)",),
)
def m2044a1(c: Cast) -> None:
    """One of five types, chosen per attack, and the header holds one.

    The damage expression is data so that it rescales, and `c.hit` has no way
    to be told which type this swing is -- so the first printed type stays in
    the header, all five ride as keywords, and the choice is the named gap.
    Dealing it by hand instead would mean writing the dice and the bonus into
    the body, which is exactly the number the database already holds.
    """
    if c.strike():
        c.hit()


@power(
    "m2044a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[
        Keyword.ACID,
        Keyword.COLD,
        Keyword.FIRE,
        Keyword.LIGHTNING,
        Keyword.POISON,
        Keyword.RANGED,
    ],
)
def m2044a2(c: Cast) -> None:
    _again(c, "m2044a1")


@power(
    "m2044a3",
    level=12,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=[
        Keyword.ACID,
        Keyword.COLD,
        Keyword.FIRE,
        Keyword.LIGHTNING,
        Keyword.POISON,
    ],
    attack=Attack(vs=REF, printed=17),
    damage=Damage("2d6", 5, dtype=DamageType.ACID, kind=LIMITED),
    dropped=("c.hit(dtype=)",),
)
def m2044a3(c: Cast) -> None:
    """"Ongoing 10 damage of the same type" follows the header's type, which is
    the first of the five -- so the burn and the blow agree, which is what the
    printed sentence asks for even though the pair cannot be chosen."""
    if c.strike():
        c.hit()
        c.ongoing(10, DamageType.ACID)


@power(
    "m2044a4",
    level=12,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[
        Keyword.ACID,
        Keyword.COLD,
        Keyword.FIRE,
        Keyword.LIGHTNING,
        Keyword.POISON,
    ],
    trigger=_M2044_BLED,
    on=Trigger(Bloodied, when=about_me, text=_M2044_BLED),
)
def m2044a4(c: Cast) -> None:
    """"First bloodied" needs no guard: `Bloodied` is emitted on the crossing
    and nowhere else. `c.restore_use` is the recharge half and the use is the
    other -- both printed, and the first is what makes the second possible
    when the row has already been spent."""
    c.restore_use("m2044a3")
    c.use_power("m2044a3")


@power(
    "m2044a5",
    level=12,
    usage=ENCOUNTER,
    action=REACTION,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.FIRE, Keyword.TELEPORTATION],
    attack=Attack(vs=REF, printed=17),
    damage=Damage("4d6", 5, dtype=DamageType.FIRE, kind=LIMITED),
    trigger=_M2044_STRUCK,
    on=Trigger(Hit, when=both(targets_me, by_melee), text=_M2044_STRUCK),
)
def m2044a5(c: Cast) -> None:
    """"Plus 1 additional square for each target he hits" is a count over the
    whole use, so every swing is rolled on the first target's pass and the
    teleport happens once -- a per-target body cannot know the total until
    the last of them."""
    if not c.first:
        return
    hits = 0
    for victim in c.targets:
        if c.strike(on=victim):
            c.hit(on=victim)
            hits += 1
    c.teleport(5 + hits)


@power(
    "m2044a6",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2044a6(c: Cast) -> None:
    """"Usable only while bloodied" is asked at the swing and not now.

    A `requires=` on a trait is read once, as `Encounter` arms it at the top
    of the fight -- when the creature is not bloodied -- and a row refused
    there is never armed again. So the Requirement is the gate on the
    modifier, which is re-read every time the clause might pay.
    """
    me = c.me
    c.bonus(
        "attack",
        1,
        on=me,
        until=When.ENCOUNTER,
        when=lambda ctx: c.bloodied(on=me),
    )


# ==========================================================================
# m2353
# ==========================================================================


_M2353_STRUCK = "the m2353 is hit by an attack"


@power(
    "m2353a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d8", 6),
)
def m2353a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(1)


@power(
    "m2353a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED],
    attack=Attack(vs=REF, printed=16),
    damage=Damage("1d8", 6),
)
def m2353a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)


@power(
    "m2353a2",
    level=12,
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_OTHER,
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("2d8", 6, kind=LIMITED),
)
def m2353a2(c: Cast) -> None:
    """"Aberrant creatures take half damage" is a property of the creature
    caught rather than of the attack, so it is asked of each one -- `half=True`
    on the same declared line, which is what keeps the number in the header."""
    if not c.strike():
        return
    if c.is_kind("aberrant"):
        c.hit(half=True)
    else:
        c.hit()
    c.dazed(until=When.SAVE_ENDS)


@power(
    "m2353a3",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
    trigger=_M2353_STRUCK,
    on=Trigger(Hit, when=targets_me, text=_M2353_STRUCK),
)
def m2353a3(c: Cast) -> None:
    """The printed Effect names a row belonging to another stat block; the
    sentence is plainly about this one. Printed as an immediate interrupt, so
    the blow is answered before it lands."""
    c.teleport(3)


# ==========================================================================
# m2354 -- elite
# ==========================================================================
#
# Four attack lines print a second bonus "against a bloodied target". The
# header carries the ordinary total and `c.strike(plus=1)` is the other,
# which is one number in one place rather than two headers.


_M2354_BLOODIED_EDGE = 1


def _m2354_plus(c: Cast) -> int:
    return _M2354_BLOODIED_EDGE if c.bloodied() else 0


@power(
    "m2354a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d4", 3),
)
def m2354a0(c: Cast) -> None:
    """The parenthesised bonus is a modifier on the roll, not a second attack
    line, so it rides as `plus=` and the header keeps the printed total."""
    if c.strike(plus=_m2354_plus(c)):
        c.hit()


@power(
    "m2354a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED],
    attack=Attack(vs=REF, printed=17),
    damage=Damage("2d6", 7),
)
def m2354a1(c: Cast) -> None:
    if c.strike(plus=_m2354_plus(c)):
        c.hit()


@power(
    "m2354a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=17),
    damage=Damage("4d6", 7, dtype=DamageType.NECROTIC),
    dropped=("SurgeSpent.cancel",),
)
def m2354a2(c: Cast) -> None:
    """"Can't use healing surges" is narrower than anything the engine has.

    `c.no_healing` refuses every kind of healing, which is a different and
    larger rule -- a leader's heal would stop landing too. A surge is
    announced as a plain `Event` rather than a `Decision`, so there is
    nothing to refuse, and the clause is named rather than widened.
    """
    if c.strike(plus=_m2354_plus(c)):
        c.hit()


@power(
    "m2354a3",
    level=12,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR, Keyword.THUNDER],
    attack=Attack(vs=FORT, printed=16),
    damage=Damage("4d6", 7, dtype=DamageType.THUNDER, kind=LIMITED),
)
def m2354a3(c: Cast) -> None:
    if c.strike(plus=_m2354_plus(c)):
        c.hit()
        c.push(4)


@power(
    "m2354a4",
    level=12,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2354a4(c: Cast) -> None:
    """A window the card leaves open, so it is asked at the swing.

    Taking the set of whoever had hit it when the minor action is spent is
    already stale if anybody hits in between -- and a monster spends a minor
    before being hit as often as after, so an empty set now is not a reason to
    do nothing. "+1 power bonus" carries the printed type word; "extra 5
    damage" carries none and is untyped. Both are `once=True`: the printed
    line is the *next* attack.
    """

    def hit_me(ctx: dict[str, Any]) -> bool:
        who = ctx.get("target")
        return who is not None and _hit_me_since_my_last_turn(c, who)

    c.bonus(
        "attack", 1, on=c.me, until=When.ENCOUNTER, kind="power", once=True, when=hit_me
    )
    c.bonus("damage", 5, on=c.me, until=When.ENCOUNTER, once=True, when=hit_me)


@power(
    "m2354a5",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
)
def m2354a5(c: Cast) -> None:
    """Two printed choices, and the fire is paid either way.

    Everybody standing next to *either end* is burned, and the neighbours are
    taken before the move: after it, the squares the two creatures were
    standing in are empty and the printed sentence is about who was beside
    them when it happened.
    """
    friends = [
        ally
        for ally in sorted(c.allies())
        if alive(c.world, ally) and c.distance(ally) <= 10
    ]
    partner = c.choose(friends, f"{c.ref}: who it changes places with") if friends else None
    scorched = set(c.within(1, side="any"))
    if partner is not None:
        scorched |= set(c.within(1, of=partner, side="any"))
        moved = c.swap(partner)
    else:
        moved = c.teleport(3)
    if not moved:
        return
    for victim in sorted(scorched):
        if victim != c.me and victim != partner and alive(c.world, victim):
            c.flat(5, dtype=DamageType.FIRE, on=victim)


# ==========================================================================
# m2553
# ==========================================================================


_M2553_STRUCK = "an enemy hits the m2553 with a melee attack"


@power(
    "m2553a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=AC, printed=19),
    damage=Damage("2d6", 7, dtype=DamageType.LIGHTNING),
)
def m2553a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2553a1",
    level=12,
    usage=ENCOUNTER,
    action=REACTION,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=17),
    damage=Damage("1d6", 8, dtype=DamageType.LIGHTNING, kind=LIMITED),
)
def m2553a1(c: Cast) -> None:
    """The burst catches everybody; the push and the stun are the triggering
    enemy's alone, and it is read off the trigger rather than off the target
    list."""
    if not c.strike():
        return
    c.hit()
    attacker = getattr(c.trigger, "attacker", None)
    if attacker is not None and c.target == attacker:
        c.push(1, on=attacker)
        c.stunned(until=When.EOTNT, on=attacker)


@power(
    "m2553a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.THUNDER],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("2d6", 8, dtype=DamageType.THUNDER),
)
def m2553a2(c: Cast) -> None:
    if c.strike():
        c.hit()


# ==========================================================================
# m2555
# ==========================================================================
#
# The same creature as m2867, printed again. Written out rather than reaching
# for those rows: each stat block's effects are filed under its own refs, and
# two copies on a board must each be found by their own owner.


_M2555_CLOSED = "an enemy moves adjacent to the m2555"
_M2555_BLED = "the m2555 is first bloodied"


@power(
    "m2555a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d6", 5),
)
def m2555a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2555a1",
    level=12,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=17),
    damage=Damage("1d8", 5, dtype=DamageType.LIGHTNING),
    trigger=_M2555_CLOSED,
    on=Trigger(
        AdjacencyGained, when=both(closed_on_me, enemy_within(1)), text=_M2555_CLOSED
    ),
)
def m2555a1(c: Cast) -> None:
    """Filed as a move action and printed as an immediate interrupt; the
    trigger line is what says which it is. `closed_on_me` is what keeps the
    row from answering its own approach -- the event is emitted mirrored, so
    both ends see it."""
    if c.strike():
        c.hit()


@power(
    "m2555a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING, Keyword.RANGED],
    attack=Attack(vs=REF, printed=19),
    damage=Damage("2d8", 5, dtype=DamageType.LIGHTNING),
)
def m2555a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2555a3",
    level=12,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("1d8", 5, dtype=DamageType.LIGHTNING, kind=LIMITED),
    trigger=_M2555_BLED,
    on=Trigger(Bloodied, when=about_me, text=_M2555_BLED),
)
def m2555a3(c: Cast) -> None:
    """Printed as a free action on a trigger, which is what it is written as:
    `ActionType.NONE` is the spelling of a trait and would go off at the top
    of the fight."""
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)


@power(
    "m2555a4",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("1d8", 5, dtype=DamageType.LIGHTNING),
    dropped=("actions.recharge(bonus=)",),
)
def m2555a4(c: Cast) -> None:
    """Everybody in the burst, its own side included -- which is what the
    clause about allies is there for, and an area burst within 10 is not a
    close area, so `EACH_CREATURE` is the right side here.

    The crowd is counted off the squares the burst covers rather than off the
    target list, because the printed line counts creatures.

    The recharge bonus cannot be written: `actions.recharge` rolls a d6
    against the number in the header and reads no modifier, so a +1 has
    nowhere to go -- and the printed cap at six is the same gap seen from the
    other end.
    """
    crowd = len(c.in_squares(c.area()))
    if not c.strike():
        return
    c.hit()
    if crowd:
        c.flat(crowd, dtype=DamageType.LIGHTNING)


# ==========================================================================
# m3120
# ==========================================================================


_M3120_FELLED = "the m3120 drops to 0 hit points"


@power(
    "m3120a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=19),
    damage=Damage("2d4", 5),
)
def m3120a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.shift(1)


@power(
    "m3120a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING, Keyword.RANGED],
    attack=Attack(vs=REF, printed=17),
    damage=Damage("1d8", 5),
)
def m3120a1(c: Cast) -> None:
    """It feeds on what it takes, so the heal is on the caster and not on
    `c.target`, which is where `c.heal` would otherwise aim."""
    if c.strike():
        c.hit()
        c.heal(5, on=c.me)


@power(
    "m3120a2",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(2, 20),
    target=EACH_ENEMY,
    keywords=[Keyword.HEALING],
    attack=Attack(vs=WILL, printed=17),
    damage=Damage("3d6", 5, kind=LIMITED),
)
def m3120a2(c: Cast) -> None:
    """It turns them on each other.

    `c.basic(who=)` names who *swings* and the victim still defaults to
    `c.target` -- which here is the creature being iterated, so the blow would
    land back on the thing that was slid. Both ends are named: the slid
    creature attacks, and its nearest reachable ally is what it hits.
    """
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    c.slide(2, on=victim)
    span = c.reach(on=victim)
    mates = sorted(
        (distance_between(c.world, victim, other), other)
        for other in c.enemies()
        if other != victim
        and alive(c.world, other)
        and distance_between(c.world, victim, other) <= span
    )
    if mates:
        c.basic(who=victim, on=mates[0][1])


@power(
    "m3120a3",
    level=12,
    usage=AT_WILL,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger=_M3120_FELLED,
    on=Trigger(Dropped, when=about_me, text=_M3120_FELLED),
)
def m3120a3(c: Cast) -> None:
    """A last swing as it goes down. A creature may answer its own downfall --
    the dispatcher makes the exception for exactly this shape -- and `FREE` is
    the window it belongs in, where `ActionType.NONE` would arm it as a trait
    at the top of the fight."""
    c.basic()


# ==========================================================================
# m5227 -- artillery, and a minion
# ==========================================================================


@power(
    "m5227a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=19),
    damage=Damage(bonus=7, kind=MINION),
)
def m5227a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5227a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=17),
    damage=Damage(bonus=8, dtype=DamageType.PSYCHIC, kind=MINION),
)
def m5227a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(1)


@power(
    "m5227a2",
    level=12,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5227a2(c: Cast) -> None:
    """"Must land at the end of this movement, or it falls" is the printed
    price of flying without hovering, and `c.fall` is what collects it --
    `c.height` is how far off the ground the creature still is once the move
    is done."""
    c.move(5, at="fly")
    if c.height() > 0:
        c.fall(on=c.me)


# ==========================================================================
# m5542 -- elite
# ==========================================================================


@power(
    "m5542a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("3d6", 10),
)
def m5542a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(2)


@power(
    "m5542a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED],
    attack=Attack(vs=WILL, printed=15),
    damage=Damage("3d6", 10),
)
def m5542a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized(until=When.SAVE_ENDS)


@power(
    "m5542a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=NO_TARGET,
)
def m5542a2(c: Cast) -> None:
    """"Each attack against a different target" is the printed restriction, so
    the second shot is refused the first one's victim rather than offered
    it."""
    _again(c, "m5542a1", distinct=True)


@power(
    "m5542a3",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("2d8", 8, dtype=DamageType.POISON, kind=LIMITED),
)
def m5542a3(c: Cast) -> None:
    """"Creatures in the blast", so it catches its own side too -- `EACH_OTHER`
    rather than `EACH_CREATURE`, which is side "any" and would also catch the
    creature doing it.

    "Save ends all" is one hold. `_wilted` is the neighbouring printing of
    this creature and carries a Fortitude penalty this one does not print, so
    the two modifiers are spelled out here instead.
    """
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    _one_hold(
        c,
        victim,
        ongoing=(5, DamageType.POISON),
        mods=[Mod(what="save", value=-2, kind="untyped", label=c.ref)],
    )


@power(
    "m5542a4",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(1, 20),
    target=EACH_CREATURE,
    keywords=[Keyword.THUNDER],
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("3d8", 9, dtype=DamageType.THUNDER, kind=LIMITED, half_on_miss=True),
)
def m5542a4(c: Cast) -> None:
    """"Creatures in the burst" on an area burst within 20, which is not a
    close area: `EACH_CREATURE` is right here and the user is not in it."""
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)
    else:
        c.hit(half=True)


# ==========================================================================
# m5636
# ==========================================================================
#
# The same creature as m115831 in a later printing, and it carries two rows
# that one does not.


_M5636_NEARBY_START = "an enemy starts its turn within 2 squares of the m5636"
_M5636_SHOT_HOME = "the m5636 hits an enemy with m5636a2"


def _m5636_shot_home(world: World, me: int, ev: Hit) -> bool:
    return ev.attacker == me and getattr(ev, "power", "") == "m5636a2"


@power(
    "m5636a0",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5636a0(c: Cast) -> None:
    """Moving far tires it.

    Counted off the log rather than out of a component: `Moved` is one step
    and nothing remembers a turn's worth of them, which is what
    `_squares_moved_this_turn` was written for a file over. Asked on each step
    rather than at the end of the turn, because the printed line is a toll on
    the fifth square and the weakness is meant to bite this turn.
    """
    me = c.me

    def tires(ev: Moved) -> None:
        if ev.actor != me or c.turn_of() != me:
            return
        if _squares_moved_this_turn(c) > 4 and not c.is_(Condition.WEAKENED, on=me):
            c.weakened(on=me, until=When.EONT)

    c.watch(Moved, tires, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m5636a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d6", 6, dtype=DamageType.POISON),
)
def m5636a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.penalty("save", 2, until=When.EONT)


@power(
    "m5636a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(30),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=19),
    damage=Damage("1d10", 7),
)
def m5636a2(c: Cast) -> None:
    victim = c.target
    if victim is not None and c.strike():
        c.hit()
        _held_and_softened(
            c,
            victim,
            conditions=(Condition.SLOWED,),
            ongoing=(5, DamageType.POISON),
        )


@power(
    "m5636a3",
    level=12,
    usage=AT_WILL,
    action=ActionType.OPPORTUNITY,
    reach=CloseBlast(2),
    target=ONE_CREATURE,
    trigger=_M5636_NEARBY_START,
    on=Trigger(TurnStart, when=_enemy_starts_within(2), text=_M5636_NEARBY_START),
)
def m5636a3(c: Cast) -> None:
    """No attack roll is printed, so none is rolled. The triggering enemy is
    read off the trigger, not off the target list."""
    victim = getattr(c.trigger, "actor", None) or c.target
    if victim is not None:
        _petrifying(c, victim)


@power(
    "m5636a4",
    level=12,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POISON],
    trigger=_M5636_SHOT_HOME,
    on=Trigger(Hit, when=_m5636_shot_home, text=_M5636_SHOT_HOME),
)
def m5636a4(c: Cast) -> None:
    """A burn that each failed save makes worse.

    `c.ongoing` is what lays it, because ongoing damage of one type does not
    stack and that rule lives there -- a weaker burn is refused and a stronger
    one supersedes. The ladder is hung on the hold it returns rather than
    passed to `c.ongoing`, which takes no `escalate`, and the number on the
    hold is what each tick re-reads.

    "The m5636 hits using its bow" is its own ranged row, which is the only
    one on the block with the weapon keyword and a range.
    """
    victim = getattr(c.trigger, "target", None)
    if victim is None:
        return
    burn = c.ongoing(10, DamageType.POISON, on=victim)
    if burn is None:
        return
    stage = {"n": 0}

    def worse(eff: Effect) -> None:
        stage["n"] += 1
        if eff.ongoing is None:
            return
        eff.ongoing = (15 if stage["n"] == 1 else 20, eff.ongoing[1])

    burn.escalate = worse


# ==========================================================================
# m5692
# ==========================================================================


_M5692_INSUBSTANTIAL = "the m5692 must be insubstantial"


@power(
    "m5692a0",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5692a0(c: Cast) -> None:
    """Two standing conditions, and phasing only while both hold.

    `c.phasing` takes no gate, so the trait watches the two boundaries that
    can change either answer -- a condition arriving or leaving, and the
    crossing of the half-hit-point line -- and puts phasing on or takes it off
    as they move. Asked once as the trait is armed as well, because a creature
    can begin a fight already bloodied and already insubstantial.
    """
    me = c.me
    held: list[Effect] = []

    def recheck(ev: Any = None) -> None:
        both_hold = c.bloodied(on=me) and c.is_(Condition.INSUBSTANTIAL, on=me)
        if both_hold and not held:
            standing = c.phasing(on=me, until=When.ENCOUNTER)
            if standing is not None:
                held.append(standing)
        elif not both_hold and held:
            c.world.effects.end(held.pop(), "no longer both bloodied and insubstantial")

    for event in (ConditionApplied, Bloodied, DamageApplied, TurnStart):
        c.watch(event, recheck, until=When.ENCOUNTER, on=me, label=c.ref)
    recheck()


@power(
    "m5692a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d6", 10),
)
def m5692a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5692a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(25),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=19),
    damage=Damage("2d12", 7),
)
def m5692a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5692a3",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD, Keyword.PSYCHIC, Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=FORT, printed=17),
    damage=Damage("2d12", 7, dtype=DamageType.PSYCHIC),
)
def m5692a3(c: Cast) -> None:
    """Two printed damage types and one `Damage`: the header keeps the first
    and both keywords carry the rest. Going insubstantial is the printed
    Effect and happens whether the shot lands or not."""
    if c.strike():
        c.hit()
    c.insubstantial(on=c.me, until=When.EONT)


@power(
    "m5692a4",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=REF, printed=17),
    damage=Damage("3d12", 7),
    requires=lambda world, eid: bool(
        (conds := world.get(eid, Conditions)) and conds.has(Condition.INSUBSTANTIAL)
    ),
    requires_text=_M5692_INSUBSTANTIAL,
)
def m5692a4(c: Cast) -> None:
    """A real Requirement about the board, so a real gate: this is a standard
    action and not a trait, so `usable` asks it each time the row is offered
    rather than once as the fight begins.

    The Effect ends it whether the shot landed or not, and `c.cure` is the
    route rather than reaching into whatever hold is carrying the condition.
    """
    if c.strike():
        c.hit()
    c.cure(Condition.INSUBSTANTIAL, on=c.me)


@power(
    "m5692a5",
    level=12,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
)
def m5692a5(c: Cast) -> None:
    c.teleport(3)
    c.insubstantial(on=c.me, until=When.EONT)
