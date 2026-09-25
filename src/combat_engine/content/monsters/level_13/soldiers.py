"""Monster abilities, level 13: the soldiers.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=AC,
printed=20)` and `Damage("2d6", 4)` -- and the engine takes the level back
out of the attack and rescales the damage if a fight is being played on
another edition's maths.

The conventions of the twelve levels below are kept: a row filed under an
action heading that is plainly a trait is declared `ActionType.NONE` and
armed once when the fight starts; a stat block printing no range at all
means melee 1; a printed "Range 10/20" is a normal range and a long one and
the normal one is what `Range` holds; a printed immediate action is that
action whatever the database's action column says; and a helper written for
an earlier level is imported rather than copied.

Seven things this file had to settle.

**A burn inside a "save ends both" hold has to obey the highest-only rule
by hand.** `c.ongoing` enforces it and `Effects.apply` does not, so
`_held_and_softened` -- which is the only way to get one saving throw for
two printed halves -- would happily lay a second poison beside a standing
one. m337a2 swings the same poisoned blade twice at one creature, which is
exactly the case the rule exists for, so `_burn_and_hold` here checks what
is standing first: a weaker burn is ended and replaced, a stronger one is
left alone and the hold carries the condition only.

**Escaping a grab is `RelationCleared`.** There is no escape action and no
escape event; a grab is `Relation.GRABBED_BY` and the relation going away
is the only moment that can be seen. m269a2 reads the kind and the grabber
off the event, which is exactly "an enemy grabbed by the m269 escapes" --
and it is the relation clearing for *any* reason, including the m269 being
knocked out, which is the one place this is wider than the printed line.

**"Moves or shifts away from it" is `AdjacencyLost`.** `MoveEnd` cannot say
it: the level-11 trick of reading the gap backwards works for a shift,
which is one square, and says nothing at all about a walk that began six
squares away. `AdjacencyLost` is emitted mirrored as the step that breaks
the adjacency lands, which is the sentence itself. Whose turn it is tells
the mover from the creature it left, because the event carries no `mover`
the way `AdjacencyGained` does -- and requiring the enemy's own turn also
keeps a shove by somebody else out, which "moves or shifts" already does.

**Legionnaires share one pool of hit points.** m2963a3 sums what its kind
are carrying, gives every one of them that total, and mirrors damage from
any of them onto the rest -- so each creature's own hit points *are* the
pool, bloodied is read off the pool, and they go down together because they
all reach zero on the same blow. The mirrored packet is dealt with
`from_attack=False`: it is the damage that already came off the pool, and
running it through resistance and weakened a second time would count both
twice. It arms once for the whole group, guarded by its own label.

**Two printed damage types, one `Damage`.** "Ongoing 10 fire and poison
damage" and "3d6 + 6 poison and psychic damage" are each one packet of two
types and a header holds one, so the first printed type is kept and a
creature resistant only to the other takes it in full -- the approximation
the levels below settled on for the same shape.

**Two elites and no second initiative count.** m2921 and m337 are both
elite and neither prints a row that acts twice, so neither takes
`c.extra_turn`: an elite is two creatures' worth of hit points and
experience before it is anything else, and splicing a turn for one would be
inventing a printed line.

**`Bloodied` about itself cannot fire on the audit board**, which halves the
caster before the fight starts. m2876a2 is such a row and reports UNUSED
however correct it is; it was driven by hand, at full health, to check.

Each stat block in ref order.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.content.monsters.level_03.controllers import _same_stock
from combat_engine.content.monsters.level_07.brutes import _aura
from combat_engine.content.monsters.level_08.brutes import (
    _has_hold,
    _holding,
)
from combat_engine.content.monsters.level_09.brutes import _put_beside, _volley
from combat_engine.content.monsters.level_11.controllers import _softened
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    FREE,
    INTERRUPT,
    MINOR,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    STANDARD,
    WILL,
    ActionType,
    Attack,
    AttackRolled,
    Bloodied,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    Damage,
    DamageApplied,
    DamageType,
    Effect,
    Health,
    Hit,
    Keyword,
    Melee,
    Ranged,
    Relation,
    Size,
    TurnEnd,
    TurnStart,
    UpTo,
    Usage,
    When,
    World,
    both,
    by_me,
    by_opportunity,
    power,
    targets_me,
    use,
)
from combat_engine.engine.events import AdjacencyLost, DamageRolled, RelationCleared
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import (
    alive,
    creatures,
    distance_between,
    is_,
    squares,
    team,
)
from combat_engine.engine.resolve import deal_damage
from combat_engine.engine.triggers import Trigger, about_me

#: "A Large or smaller target", which is everything up to and including the
#: m269's own size. `SMALL_ENOUGH` a few levels down stops at Medium.
LARGE_OR_SMALLER = (Size.TINY, Size.SMALL, Size.MEDIUM, Size.LARGE)


def _burn_and_hold(
    c: Cast,
    victim: int,
    amount: int,
    dtype: DamageType,
    *,
    conditions: tuple[Condition, ...] = (),
    attack: int = 0,
    escalate: Callable[[Effect], None] | None = None,
) -> Effect:
    """A "save ends both" hold whose burn obeys the highest-only rule.

    `c.ongoing` refuses a weaker burn of a type already standing and
    supersedes a stronger one; `Effects.apply` -- which is the only door to
    a hold carrying a burn *and* a condition on one saving throw -- does
    neither. So the check is made here: a weaker standing burn is ended, a
    stronger one is left where it is and this hold carries the rest of the
    printed line without a second burn beside it.
    """
    standing = [
        eff
        for eff in c.world.effects.of(victim)
        if eff.ongoing is not None and eff.ongoing[1] is dtype
    ]
    worst = max((eff.ongoing[0] for eff in standing), default=0)
    if worst >= amount:
        burn = None
    else:
        for eff in standing:
            c.world.effects.end(eff, "superseded by worse of the same type")
        burn = (amount, dtype)
    return c.world.effects.apply(
        victim,
        c.me,
        When.SAVE_ENDS,
        label=c.ref,
        conditions=conditions,
        ongoing=burn,
        mods=[(victim, m) for m in _softened(c, attack=attack)],
        escalate=escalate,
    )


def _shift_beside(c: Cast, victim: int, squares_: int) -> bool:
    """Shift up to `squares_` and finish next to that creature.

    `c.shift` with no `to` offers the decider every square in range, which
    is useless for a printed line that says where the step has to end. The
    level-11 version of this walks exactly one square; this one takes a
    distance, because m2921a3 prints two.
    """
    from combat_engine.engine.grid import distance

    me = c.me
    theirs = squares(c.world, victim)
    mine = squares(c.world, me)
    options = sorted(
        sq
        for sq in c.world.reachable_squares(me, squares_)
        if sq not in mine and min(distance(sq, t) for t in theirs) <= 1
    )
    if not options:
        return False
    return c.shift(
        squares_, to=c.world.decide(me, "shift", options, f"{c.ref}: staying with it")
    )


# ==========================================================================
# m269
# ==========================================================================


@power(
    "m269a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=AC, printed=20),
    damage=Damage("2d6", 4),
)
def m269a0(c: Cast) -> None:
    """It takes hold, and what it is holding cooks.

    Only the hold burns; the blow itself is printed untyped, so the header
    carries no damage type and the keyword line is what the fire is for.

    The ten a turn is hung on the grab rather than on the creature: it
    stops when the grab does, whichever way the grab ended, and asking the
    relation again each turn is what makes "a grabbed target" true only
    while it is.
    """
    me, victim = c.me, c.target
    if victim is None or not c.strike():
        return
    c.hit()
    if c.size_of(victim) not in LARGE_OR_SMALLER:
        return
    held = c.grab(on=victim)
    if held is None:
        return

    def cook(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me:
            return
        if c.world.relations.holds(Relation.GRABBED_BY, me, victim):
            c.flat(10, dtype=DamageType.FIRE, on=victim)

    burn = c.watch(TurnStart, cook, until=When.ENCOUNTER, on=me, label=f"{c.ref} burn")
    held.on_end.append(lambda: c.world.effects.end(burn, "it let go"))


@power(
    "m269a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.POISON],
    attack=Attack(vs=FORT, printed=18),
    damage=Damage("1d8", 4),
)
def m269a1(c: Cast) -> None:
    """"Ongoing 10 fire and poison damage" is one burn of two types and a
    hold carries one, so the first printed type is kept.

    "It can use this attack against a target it has grabbed" is a
    clarification rather than a rule here: a melee 1 row already reaches
    something the m269 is holding, and nothing in the engine takes the
    swing away for having hold of somebody.
    """
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    _burn_and_hold(
        c, victim, 10, DamageType.FIRE, conditions=(Condition.WEAKENED,)
    )


_M269_SLIPPED = "an enemy grabbed by the m269 escapes"


def _broke_my_grip(world: World, me: int, ev: RelationCleared) -> bool:
    return ev.kind_ is Relation.GRABBED_BY and ev.source == me


@power(
    "m269a2",
    level=13,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=Melee(1),
    target=NO_TARGET,
    trigger=_M269_SLIPPED,
    on=Trigger(RelationCleared, when=_broke_my_grip, text=_M269_SLIPPED),
)
def m269a2(c: Cast) -> None:
    """A parting bite at whatever wriggled loose.

    There is no escape action and no escape event: a grab is a relation,
    and the relation clearing is the only moment the engine can see. That
    makes the trigger slightly wider than the printed one -- the grab also
    clears when the m269 goes down -- and narrower in no way.

    Declared with no target and aimed off the event, because the dispatcher
    would point a one-enemy row at whoever is nearest rather than at the
    creature that just got away.
    """
    who = getattr(c.trigger, "target", None)
    if who is not None and alive(c.world, who):
        use(c.world, c.me, "m269a1", targets=[who], spend=False)


# ==========================================================================
# m279
# ==========================================================================


@power(
    "m279a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=20),
    damage=Damage("1d12", 7),
)
def m279a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.pull(1)


@power(
    "m279a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=UpTo(2),
)
def m279a1(c: Cast) -> None:
    """Two hooks, and a creature caught on both of them.

    The printed Effect does not say whether the two land on one creature or
    two, so the header takes up to two and a single target is struck twice
    -- the only reading under which "if both hooks hit the same target" can
    ever be true. `_volley` is the helper for that shape.

    The -2 is a modifier laid for the length of the swing rather than an
    argument, because the blows go through the row that prints them and
    `use` carries no penalty. Not `once=True`: the printed line puts it on
    both hooks.
    """
    victim = c.target
    if victim is None:
        return
    worse = c.penalty("attack", 2, on=c.me, until=When.EOT, kind="untyped")
    try:
        caught = _volley(c, "m279a0", victim)
    finally:
        if worse is not None:
            c.world.effects.end(worse, "the hooks are swung")
    if caught:
        c.damage("1d12", on=victim)
        c.grab(on=victim)


@power(
    "m279a2",
    level=13,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Melee(2),
    target=NO_TARGET,
    attack=Attack(vs=AC, printed=20),
    damage=Damage("1d8", 7),
    requires=_has_hold,
    requires_text="the m279 must be grabbing a creature",
)
def m279a2(c: Cast) -> None:
    """"Grabbed target only" is narrower than any `Target` can say, so the
    Requirement carries the caster's half and the body picks from what it
    is actually holding."""
    held = sorted(_holding(c.world, c.me))
    victim = c.choose(held, "m279a2: which of them it worries") if held else None
    if victim is not None and c.strike(on=victim):
        c.hit(on=victim)


@power(
    "m279a3",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=19),
    damage=Damage("2d12", 7, kind=LIMITED),
)
def m279a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(3)
        c.prone()


# ==========================================================================
# m2876
# ==========================================================================


@power(
    "m2876a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=20),
    damage=Damage("2d10", 3),
)
def m2876a0(c: Cast) -> None:
    """The temporary hit points go to one named ally, so they are chosen
    rather than spread: "one ally within 5 squares" is a pick and `c.choose`
    is how a row makes one."""
    if not c.strike():
        return
    c.hit()
    mates = sorted(friend for friend in c.within(5, side="ally") if friend != c.me)
    chosen = c.choose(mates, "m2876a0: which ally it steadies") if mates else None
    if chosen is not None:
        c.temp_hp(8, on=chosen)


@power(
    "m2876a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(3),
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d10", 3),
)
def m2876a1(c: Cast) -> None:
    if c.strike():
        c.hit()


_M2876_BLED = "the m2876 is first bloodied"


@power(
    "m2876a2",
    level=13,
    usage=ENCOUNTER,
    action=REACTION,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=18),
    damage=Damage(bonus=5, kind=LIMITED),
    trigger=_M2876_BLED,
    on=Trigger(Bloodied, when=about_me, text=_M2876_BLED),
)
def m2876a2(c: Cast) -> None:
    """A sweep as it takes the wound, and a rally if it lands twice.

    "First bloodied" needs no guard: `Bloodied` is emitted on the crossing
    and nowhere else.

    How many went down is counted off the holds this row laid rather than
    kept in a local, because the body is called once per target and
    `c.suffering` is the question "who is carrying something of mine" --
    exactly the two or more the printed line asks for. The tally is read on
    the last target, which is the first moment the whole sweep is resolved.
    """
    if c.strike():
        c.hit()
        c.prone()
    if not c.last or len(c.suffering(c.ref)) < 2:
        return
    for mate in sorted(c.within(5, side="ally")):
        if mate != c.me:
            c.temp_hp(10, on=mate)


@power(
    "m2876a3",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2876a3(c: Cast) -> None:
    """Filed as a standard action and plainly a trait.

    The attack context carries `opportunity`, which is the whole of the
    gate: keying on the ref instead would catch a standard-action basic and
    miss a creature whose opportunity attack is some other row.

    The step afterwards reads the same flag off the `Hit`, which carries it
    for exactly this reason.
    """
    me = c.me

    def seizing(ctx: dict[str, Any]) -> bool:
        return bool(ctx.get("opportunity"))

    c.bonus("attack", 3, until=When.ENCOUNTER, on=me, kind="power", when=seizing)

    def follow(ev: Hit) -> None:
        if ev.attacker == me and getattr(ev, "opportunity", False):
            c.shift(1)

    c.watch(Hit, follow, until=When.ENCOUNTER, on=me, label=c.ref)


# ==========================================================================
# m2921
# ==========================================================================


@power(
    "m2921a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=20),
    damage=Damage("2d10", 3),
)
def m2921a0(c: Cast) -> None:
    """The secondary is a second attack line, and a second line's printed
    bonus is trimmed by hand the way `Attack.bonus_for` trims the header's.
    """
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    if c.attack(c.world.scaling.trim(16, c.level), FORT, on=victim):
        _burn_and_hold(c, victim, 5, DamageType.POISON, attack=2)


@power(
    "m2921a1",
    level=13,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=CloseBurst(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.NECROTIC],
)
def m2921a1(c: Cast) -> None:
    """It names somebody, and the naming costs them if they look away.

    No attack roll and no damage line: the mark is the whole of the hit,
    and the ten is a consequence measured a turn later.

    The printed sentence spans a whole turn, so it is watched at three
    moments -- the turn opening, which is the only place the range it began
    at can be noted; any attack roll it makes, which is where "against the
    m2921" is answered; and the turn ending, which is when both halves are
    judged. Ten fire and necrotic is one packet of two types and the first
    printed one is kept.

    Cover and concealment are computed between two positions at the moment
    of the attack, and `ignore_cover` is an argument to one roll rather
    than a state a creature can be put into, so "gains no benefit from any
    concealment" is noted. See the report.
    """
    me, victim = c.me, c.target
    if victim is None:
        return
    c.mark(until=When.EONT, on=victim)
    c.note("m2921a1: the target gains no benefit from concealment")
    watched: dict[str, Any] = {"at": 0, "armed": False, "swung": False}

    def opened(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != victim:
            return
        watched["at"] = distance_between(c.world, me, victim)
        watched["armed"] = True
        watched["swung"] = False

    def aimed(ev: AttackRolled) -> None:
        if ev.attacker == victim and ev.target == me:
            watched["swung"] = True

    def closed(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor != victim or not watched["armed"]:
            return
        watched["armed"] = False
        away = distance_between(c.world, me, victim) > watched["at"]
        if away or not watched["swung"]:
            c.flat(10, dtype=DamageType.FIRE, on=victim)

    for event, fn, tag in (
        (TurnStart, opened, "turn"),
        (AttackRolled, aimed, "aim"),
        (TurnEnd, closed, "reckoning"),
    ):
        c.watch(event, fn, until=When.EOTNT, on=victim, label=f"{c.ref} {tag}")


@power(
    "m2921a2",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=CloseBurst(3),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d8", 4, kind=LIMITED),
)
def m2921a2(c: Cast) -> None:
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    _burn_and_hold(c, victim, 5, DamageType.POISON, attack=2)


_M2921_SLIPPED = "an enemy adjacent to the m2921 moves or shifts away from it"


def _left_my_side(world: World, me: int, ev: AdjacencyLost) -> bool:
    """An enemy that was standing next to me has moved out of reach.

    `MoveEnd` cannot say this. Reading the gap backwards works for a shift,
    which is one square, and says nothing about a walk that began six
    squares away -- so the event is the one the engine emits as the
    adjacency itself breaks.

    It is emitted mirrored and carries no `mover`, unlike `AdjacencyGained`,
    so whose turn it is tells the creature that left from the creature it
    left. That also keeps a shove by somebody else out, which "moves or
    shifts" wants anyway.
    """
    if ev.other != me or ev.actor == me:
        return False
    if world.turn != ev.actor:
        return False
    return team(world, ev.actor) is not team(world, me)


@power(
    "m2921a3",
    level=13,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M2921_SLIPPED,
    on=Trigger(AdjacencyLost, when=_left_my_side, text=_M2921_SLIPPED),
)
def m2921a3(c: Cast) -> None:
    """It follows, and if it had already named them it swings too.

    Declared with no target and aimed off the event: the row is about the
    creature that just walked away rather than whoever is nearest.

    The swing is free -- `use(..., spend=False)` -- because the printed line
    gives it away with the shift rather than charging a second action for
    it.
    """
    who = getattr(c.trigger, "actor", None)
    if who is None or not alive(c.world, who):
        return
    if not _shift_beside(c, who, 2):
        return
    if c.marked(on=who):
        use(c.world, c.me, "m2921a0", targets=[who], spend=False)


# ==========================================================================
# m2963
# ==========================================================================


#: The hold that is the merging, found by label because the engine has no
#: relation for one creature being inside another.
_M2963_MERGED = "m2963a2 merged"

#: The shared pool's marker. One of the group arms it and the rest read it
#: and stand down, so the sum is taken once however many are on the board.
_M2963_POOL = "m2963a3 pool"


@power(
    "m2963a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=19),
    damage=Damage("2d8", 6),
)
def m2963a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means."""
    if c.strike():
        c.hit()


@power(
    "m2963a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.RANGED],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d10", 6, dtype=DamageType.NECROTIC),
)
def m2963a1(c: Cast) -> None:
    """10/20 is a normal range and a long one, and `Range` holds one number,
    so the normal range is written."""
    if c.strike():
        c.hit()


@power(
    "m2963a2",
    level=13,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.RELIABLE, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=16),
    damage=Damage("2d8", 6, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m2963a2(c: Cast) -> None:
    """It steps inside the creature it has taken over.

    The deafness and the domination are one hold: applied separately the
    victim would get two saving throws against a thing the card prints as
    one.

    `Condition.REMOVED` is what the engine has for a creature that is on the
    board and not in the fight, which is the level-11 reading of the same
    sentence. It stops the m2963 acting; nothing stops it being targeted,
    so that half is noted. Coming back hangs on the hold's own ending rather
    than on a clock, because "when the target saves" is what the printed
    line measures and the square is chosen then rather than now.

    Reliable is a header keyword the engine already honours: a miss costs no
    use.

    The History bonus goes nowhere -- m2963a4 is not written, because the
    engine rolls no skill checks -- and is noted.
    """
    me, victim = c.me, c.target
    if victim is None or not c.strike():
        return
    c.hit()
    held = c.condition(
        Condition.DEAFENED, Condition.DOMINATED, until=When.SAVE_ENDS, on=victim
    )
    if held is None:
        return
    inside = c.world.effects.apply(
        me, me, When.ENCOUNTER, label=_M2963_MERGED,
        conditions=(Condition.REMOVED,),
    )

    def emerge() -> None:
        if not inside.ended:
            c.world.effects.end(inside, "the target shook it off")
        _put_beside(c, me, victim)

    held.on_end.append(emerge)
    c.note("m2963a2: while merged the m2963 cannot be attacked, and the target learns about it")


@power(
    "m2963a3",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2963a3(c: Cast) -> None:
    """One pool of hit points for the whole cohort.

    Each legionnaire is given the sum as its own maximum and its own
    current, so every creature's hit points *are* the pool: bloodied is read
    off it, a heal raises it, and they are all destroyed on the blow that
    empties it, which is the printed "simultaneously". Damage to any one of
    them is mirrored onto the rest, which is the sentence that makes them
    one total.

    The mirrored packet is dealt with `from_attack=False`: `ev.amount` is
    what already came off the pool, and putting it through resistance,
    vulnerability and weakened a second time would count each of those
    twice on a cohort that all carry the same ones.

    It arms once for the group, not once per legionnaire: every one of them
    holds the trait, and a second summing would take the sum of sums. The
    marker is this row's own hold, and the guard is that anybody already
    carries it.
    """
    me = c.me
    kin = sorted(
        other
        for other in creatures(c.world)
        if other == me or _same_stock(c.world, me, other)
    )
    if any(
        eff.label == _M2963_POOL for who in kin for eff in c.world.effects.of(who)
    ):
        return
    healths = [(who, c.world.get(who, Health)) for who in kin]
    pooled = [(who, h) for who, h in healths if h is not None]
    total = sum(h.max_hp for _, h in pooled)
    lost = sum(h.max_hp - h.hp for _, h in pooled)
    if total <= 0:
        return
    for _who, h in pooled:
        h.max_hp = total
        h.hp = max(0, total - lost)

    busy: list[int] = []

    def shared(ev: DamageApplied) -> None:
        if busy or ev.amount <= 0 or ev.target not in kin:
            return
        busy.append(1)
        try:
            for other in kin:
                if other != ev.target and alive(c.world, other):
                    deal_damage(
                        c.world, ev.source, other, ev.amount, ev.dtype,
                        f"{c.ref} (shared)", from_attack=False,
                    )
        finally:
            busy.clear()

    c.watch(DamageApplied, shared, until=When.ENCOUNTER, on=me, label=_M2963_POOL)


# ==========================================================================
# m337
# ==========================================================================


@power(
    "m337a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=20),
    damage=Damage("1d8", 8),
)
def m337a0(c: Cast) -> None:
    """The secondary is a second attack line, and a second line's printed
    bonus is trimmed by hand the way `Attack.bonus_for` trims the header's.
    """
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    if c.attack(c.world.scaling.trim(18, c.level), FORT, on=victim):
        _burn_and_hold(
            c, victim, 10, DamageType.POISON, conditions=(Condition.SLOWED,)
        )


@power(
    "m337a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.RANGED, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d10", 5),
)
def m337a1(c: Cast) -> None:
    """20/40 is a normal range and a long one, and `Range` holds one
    number."""
    if c.strike():
        c.hit()
        c.ongoing(10, DamageType.POISON)


@power(
    "m337a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON],
)
def m337a2(c: Cast) -> None:
    """Two swings of the row that prints the blade, and a rider on each.

    The line it repeats is the row that prints it rather than a copy, so the
    damage and the poison stay in one place -- and that is also why the two
    poisons landing on one creature do not add up: `_burn_and_hold` refuses
    the second.

    The extra dice cannot be a modifier -- a `Mod` carries a number -- so
    they ride on the `Hit` the swings emit, and dazed is asked at that
    moment rather than before the first blow.
    """
    me, ref, victim = c.me, c.ref, c.target
    if victim is None:
        return

    def harder(ev: Hit) -> None:
        if ev.attacker != me or ev.power != "m337a0":
            return
        if is_(c.world, ev.target, Condition.DAZED):
            c.damage("2d8", on=ev.target, detail=ref)

    rider = c.watch(Hit, harder, until=When.EOT, on=me, label=f"{ref} dazed")
    try:
        for _ in range(2):
            use(c.world, me, "m337a0", targets=[victim], spend=False)
    finally:
        c.world.effects.end(rider, "the blows are struck")


@power(
    "m337a3",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.GAZE, Keyword.POISON, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=19),
    damage=Damage("3d6", 6, dtype=DamageType.POISON),
)
def m337a3(c: Cast) -> None:
    """"Blind creatures are immune" is a gaze's own exemption and is asked
    of the target rather than declared, because a `Target` cannot say it.

    "Poison and psychic damage" is one roll of two types and a header holds
    one, so the first printed type is kept.

    The daze and the weakness are one hold: applied separately the victim
    would get two saving throws against one printed sentence.
    """
    if c.is_(Condition.BLINDED) or not c.strike():
        return
    c.hit()
    c.condition(Condition.DAZED, Condition.WEAKENED, until=When.SAVE_ENDS)


# ==========================================================================
# m4984
# ==========================================================================


@power(
    "m4984a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d6", 9),
)
def m4984a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m4984a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=16),
    damage=Damage("1d6", 5, dtype=DamageType.PSYCHIC),
)
def m4984a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.pull(5)


@power(
    "m4984a2",
    level=13,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=18),
)
def m4984a2(c: Cast) -> None:
    """No damage line: the hold is the whole of the hit."""
    if c.strike():
        c.immobilized(until=When.EONT)


_M4984_STRUCK = "an attack damages the m4984"


@power(
    "m4984a3",
    level=13,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M4984_STRUCK,
    on=Trigger(DamageRolled, when=targets_me, text=_M4984_STRUCK),
)
def m4984a3(c: Cast) -> None:
    """It gives, and half the blow goes through it.

    Declared `INTERRUPT` because the printed Effect says so, whatever the
    database's action column reads -- and the window is what makes it work:
    `DamageRolled` is announced before the packet is applied and its amount
    is read back, so halving it here is halving what lands.

    `c.insubstantial` is the other way to say this and is the wrong one: it
    is a duration, and the printed line answers one attack at a time.

    The note is not decoration. Nothing else this row does emits anything,
    because its whole content is a smaller number on somebody else's event,
    and a row that emits nothing is indistinguishable from one that was
    never written.
    """
    ev = c.trigger
    if ev is None or not hasattr(ev, "amount"):
        return
    ev.amount = ev.amount // 2
    c.note(f"m4984a3: it takes half the blow -- {ev.amount} gets through")


# ==========================================================================
# m666
# ==========================================================================


#: The four the m666 chooses between. Written out because the printed line
#: names four of the eleven and the choice is made per swing.
_M666_ELEMENTS = (
    DamageType.COLD,
    DamageType.FIRE,
    DamageType.LIGHTNING,
    DamageType.THUNDER,
)


@power(
    "m666a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[
        Keyword.WEAPON,
        Keyword.COLD,
        Keyword.FIRE,
        Keyword.LIGHTNING,
        Keyword.THUNDER,
    ],
    attack=Attack(vs=AC, printed=20),
    damage=Damage("1d10", 7),
)
def m666a0(c: Cast) -> None:
    """The die of element is a second packet rather than part of the header's,
    because the header holds one damage type and this one is chosen at the
    moment of the swing. The printed line carries all four keywords and the
    choice picks which of them the blow actually is.
    """
    if not c.strike():
        return
    c.hit()
    picked = c.choose(list(_M666_ELEMENTS), "m666a0: which element") or DamageType.FIRE
    c.damage("1d10", dtype=picked)


@power(
    "m666a1",
    level=13,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    keywords=[
        Keyword.WEAPON,
        Keyword.COLD,
        Keyword.FIRE,
        Keyword.LIGHTNING,
        Keyword.THUNDER,
    ],
)
def m666a1(c: Cast) -> None:
    """The line it repeats is the row that prints it rather than a copy, so
    the damage and the choice of element stay in one place. `UpTo(2)` is
    "two different targets": the target list never holds one twice."""
    use(c.world, c.me, "m666a0", targets=[c.target], spend=False)


_M666_SEIZED = "the m666 hits with an opportunity attack"


@power(
    "m666a2",
    level=13,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger=_M666_SEIZED,
    on=Trigger(Hit, when=both(by_me, by_opportunity), text=_M666_SEIZED),
)
def m666a2(c: Cast) -> None:
    """`by_opportunity` reads the flag the `Hit` carries, which is the only
    place the shape of the attack survives past the roll."""
    c.shift(2)


# ==========================================================================
# m81
# ==========================================================================


@power(
    "m81a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d4", 5),
)
def m81a0(c: Cast) -> None:
    """The mark and the burn are two printed clauses on two clocks -- one
    runs to the end of the m81's next turn and the other is save-ends -- so
    they are two holds, which is the one shape where that is right."""
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)
        c.ongoing(10)


@power(
    "m81a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d6", 5),
)
def m81a1(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means."""
    if c.strike():
        c.hit()


@power(
    "m81a2",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m81a2(c: Cast) -> None:
    """Filed as a standard action and plainly a trait.

    Two gated modifiers rather than one: the bonus is to every attack roll
    and the five is to melee damage only, and the damage context carries
    `target`, `power`, `opportunity` and `charge` and no attacker at all --
    so which sort of attack it is comes off the row's own reach.
    """
    me = c.me

    def bleeding(_ctx: dict[str, Any]) -> bool:
        return c.bloodied(on=me)

    def bleeding_in_reach(ctx: dict[str, Any]) -> bool:
        from combat_engine.engine.dsl import get

        if not c.bloodied(on=me):
            return False
        p = get(ctx.get("power") or "")
        return p is not None and p.reach.kind == "melee"

    c.bonus("attack", 2, until=When.ENCOUNTER, on=me, kind="untyped", when=bleeding)
    c.bonus(
        "damage", 5, until=When.ENCOUNTER, on=me, kind="untyped",
        when=bleeding_in_reach,
    )


@power(
    "m81a3",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m81a3(c: Cast) -> None:
    """Filed as a standard action and plainly a trait.

    The aura helper is the right one here: the bonus is carried for exactly
    as long as its owner stands beside the m81, and `ZoneEntered` and
    `ZoneExited` are the two moments it should go on and come off.
    """
    me = c.me

    def eligible(who: int) -> bool:
        return who != me and who in c.allies()

    def hold(who: int) -> Effect | None:
        return c.bonus(AC, 2, until=When.ENCOUNTER, on=who, kind="untyped")

    _aura(c, 1, eligible, hold)
