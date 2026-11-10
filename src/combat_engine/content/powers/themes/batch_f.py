"""Theme rows, batch F: fifteen themes, keyed by their alias refs.

Two attack lines recur and they are not the same problem.

**"Highest ability modifier"** is exact. `_best` computes it, the header
still names one ability so a policy can read a line without running the
body, and `_swing` carries the difference as `plus=`. No marker: nothing
is missing.

**"Primary ability"** is a fact about the *class* that took the theme, and
a theme does not know which class that was. The same stand-in is used --
right for most builds, generous for a few -- and every such row carries
`c.attack_ability()`, the symbol the tree already uses for it.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.content.powers.augment import augment
from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    DEX,
    EACH_CREATURE,
    EACH_ENEMY,
    EACH_OTHER,
    ENCOUNTER,
    FORT,
    FREE,
    INT,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_ALLY,
    ONE_CREATURE,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    STR,
    WILL,
    YOU_AND_EACH_ALLY,
    ActionType,
    AdjacencyGained,
    AreaBurst,
    Attack,
    AttackDeclared,
    AttackRolled,
    Bloodied,
    Cast,
    CheckDeclared,
    CloseBlast,
    CloseBurst,
    Condition,
    ConditionApplied,
    DamageApplied,
    DamageRolled,
    DamageType,
    Dropped,
    Effect,
    EnterSquare,
    Healed,
    Health,
    Hit,
    Ident,
    InitiativeRolled,
    Keyword,
    Melee,
    Moved,
    OpportunityWindow,
    Pick,
    Position,
    Powers,
    PowerUsed,
    Ranged,
    SavingThrow,
    Size,
    SkillCheck,
    Stats,
    Summoned,
    Target,
    Trigger,
    TurnEnd,
    TurnStart,
    When,
    Window,
    World,
    ZoneEntered,
    about_me,
    both,
    by_melee,
    by_ranged,
    closed_on_me,
    either,
    enemy_within,
    grid,
    hits_me,
    my_check,
    power,
    query,
)
from combat_engine.engine.dsl import REGISTRY
from combat_engine.engine.zones import Zone

#: "Primary ability modifier" -- see the module docstring.
PSIONIC = [Keyword.PSIONIC]
PSIONIC_IMPLEMENT = [Keyword.PSIONIC, Keyword.IMPLEMENT, Keyword.PSYCHIC]
ALL_DEFENCES = (AC, FORT, REF, WILL)
#: Every skill the engine has that a "knowledge check" can be.
KNOWLEDGE = ("arcana", "dungeoneering", "history", "nature", "religion")


def _best(c: Cast) -> int:
    """"Your highest ability modifier", and the stand-in for "your primary"."""
    return max(c.str_mod, c.con_mod, c.dex_mod, c.int_mod, c.wis_mod, c.cha_mod)


def _swing(c: Cast, **kw: Any) -> Any:
    """`c.strike` with the header's named ability corrected to the best one."""
    return c.strike(plus=_best(c) - c.attack_mod, **kw)


def _live(c: Cast, zid: int) -> bool:
    """Is that zone still on the board? A watch outlives the aura it guards."""
    return any(other == zid for other, _ in c.world.zones.all())


def _inside(c: Cast, zid: int, who: int) -> bool:
    return _live(c, zid) and who in c.world.zones.occupants(zid)


def _square(c: Cast, who: int) -> tuple[int, int] | None:
    pos = c.world.get(who, Position)
    return pos.square if pos is not None else None


def _free_beside(c: Cast) -> tuple[int, int] | None:
    for sq in grid.neighbours(c.here):
        if not c.in_squares([sq]):
            return sq
    return None


def _mine(c: Cast, who: int) -> bool:
    return query.team(c.world, who) is query.team(c.world, c.me)


def _aimed_at_me(c: Cast) -> Callable[[dict[str, Any]], bool]:
    return lambda ctx: ctx.get("target") == c.me


def _ends_with(c: Cast, shape: Effect, *holds: Effect | None) -> None:
    """Tie a while-in-this-shape benefit to the shape itself.

    `powers/vampire/__init__.py`'s helper, here for the same reason it is
    there: the printed clock on each clause is the shape, and the longest
    `until=` the engine has is the encounter -- so a hold laid bare
    survives changing back, and a creature that stepped out of a form kept
    what the form cost it.
    """
    for hold in holds:
        if hold is not None:
            shape.on_end.append(
                lambda h=hold: c.world.effects.end(h, "the shape ended")
            )


# -- x7_658 -----------------------------------------------------------------


def _me_or_ally_rolled(world: Any, me: int, ev: Any) -> bool:
    who = getattr(ev, "actor", None)
    if who is None:
        who = getattr(ev, "attacker", None)
    if who is None:
        return False
    if who == me:
        return True
    return (
        query.team(world, who) is query.team(world, me)
        and query.distance_between(world, me, who) <= 5
    )


def _ally_within_10(world: Any, me: int, ev: Any) -> bool:
    who = getattr(ev, "actor", None)
    if who is None or who == me:
        return False
    return (
        query.team(world, who) is query.team(world, me)
        and query.distance_between(world, me, who) <= 10
    )


@power(
    "p12244",
    level=0,
    cls="x7_658",
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(5),
    target=NO_TARGET,
    keywords=PSIONIC,
    trigger="you or an ally in the burst makes an attack roll, save or check",
    on=(
        Trigger(AttackRolled, _me_or_ally_rolled, "you or an ally makes an attack roll"),
        Trigger(SavingThrow, _me_or_ally_rolled, "you or an ally makes a saving throw"),
        Trigger(SkillCheck, _me_or_ally_rolled, "you or an ally makes a skill check"),
    ),
)
def p12244(c: Cast) -> None:
    """Three events for one printed sentence, and now one verb for all three.

    `c.boost_roll` dispatches on what triggered, so the `isinstance` branch
    that used to pay the skill-check third and drop the other two is gone --
    it was not a simplification but the whole of the gap. #495."""
    points = augment(c, 1)
    gain = c.roll("1d4") + 1 if points else 1
    c.boost_roll(gain)


@power(
    "p12245",
    level=2,
    cls="x7_658",
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=CloseBurst(1),
    target=ONE_ALLY,
    keywords=PSIONIC,
    trigger="you are hit by an attack",
    on=Trigger(Hit, hits_me, "you are hit by an attack"),
)
def p12245(c: Cast) -> None:
    """The swap, the redirection and the +2 are all three written.

    The +2 is laid on the comparison rather than as a modifier. An
    `IMMEDIATE_INTERRUPT` answers in `Window.BEFORE`, which on a `Hit` is
    inside `resolve.roll` and *before* its `confirm` callback -- so raising
    the defence the blow was measured against and recomputing the outcome
    turns a hit that cleared by one into a `Miss`, announced as one, with
    every rider on `Hit` skipped. A `c.bonus` cannot do it: the sum was
    taken when the die landed.

    The re-settling is `c.settle_attack()`, which is the door for exactly
    this -- a row that changed a number the outcome was judged from. Written
    out by hand it could not **un-crit** a hit its own +2 had pushed below
    the defence, so a critical that no longer reached the defence stayed a
    critical and dealt maximum damage. #868.

    What this row does **not** do is re-measure against the ally's own
    defences. `c.redirect` moves the live result deliberately without
    rolling again, which is the engine's standing simplification and not
    this clause -- the +2 is the clause, and it is exact.
    """
    ev = c.trigger
    mate = c.target
    if mate is None:
        return
    c.swap(mate)
    c.redirect(to=mate)
    result = getattr(ev, "result", None)
    if result is None:
        return
    result.target_defence += 2
    c.settle_attack()


@power(
    "p12246",
    level=3,
    cls="x7_658",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=PSIONIC_IMPLEMENT,
    attack=Attack(Pick.PRIMARY, vs=WILL),
)
def p12246(c: Cast) -> None:
    """The printed Requirement is a spend, not a gate on the board, so it is
    paid in the body rather than in `requires=`."""
    if c.first and not c.spend_points(2):
        return
    victim = c.target
    if not _swing(c):
        return
    c.damage("1d8", _best(c), dtype=DamageType.PSYCHIC)
    c.dazed(until=When.EONT)
    near = c.within(3, of=victim, side="ally")
    mate = c.choose(near, "who gains the bonus to damage") if near else None
    if mate is not None:
        c.bonus(
            "damage", 0, dice="1d6", on=mate, until=When.EONT,
            when=lambda ctx, v=victim: ctx.get("target") == v,
        )


@power(
    "p12247",
    level=5,
    cls="x7_658",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=PSIONIC_IMPLEMENT,
    attack=Attack(Pick.PRIMARY, vs=WILL),
)
def p12247(c: Cast) -> None:
    """One watch, not two: a second save-ends effect would give the victim a
    second throw for one printed sentence. "Bloodied by that damage" is read
    off the blow rather than off `Bloodied`, so the prone and the psychic
    damage stay one event."""
    victim = c.target
    if victim is None:
        return
    if _swing(c):
        c.damage("2d6", _best(c), dtype=DamageType.PSYCHIC)
    mine = _best(c)
    struck: dict[str, int] = {}

    def echo(ev: DamageApplied) -> None:
        foe = ev.target
        if foe == victim or foe not in c.enemies():
            return
        if query.distance_between(c.world, foe, victim) > 5:
            return
        if struck.get("round") == c.world.round:
            return
        struck["round"] = c.world.round
        c.flat(mine, dtype=DamageType.PSYCHIC, on=victim)
        health = c.world.get(foe, Health)
        if health is None:
            return
        half = health.max_hp // 2
        if health.hp <= half < health.hp + ev.amount:
            c.prone(on=victim)

    c.watch(DamageApplied, echo, until=When.SAVE_ENDS, on=victim, label=c.ref)


@power(
    "p12248",
    level=6,
    cls="x7_658",
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=CloseBurst(10),
    target=NO_TARGET,
    keywords=[Keyword.PSIONIC, Keyword.PSYCHIC],
    trigger="an ally in the burst makes a skill check or a saving throw",
    on=(
        Trigger(SkillCheck, _ally_within_10, "an ally makes a skill check"),
        Trigger(SavingThrow, _ally_within_10, "an ally makes a saving throw"),
    ),
)
def p12248(c: Cast) -> None:
    """"This power is not expended" is `c.restore_use`, paid only when the
    second roll misses, which is what the card charges for."""
    ev = c.trigger
    mate = getattr(ev, "actor", None)
    if mate is None:
        return
    if isinstance(ev, SkillCheck):
        c.reroll_check(keep="new")
        ok = bool(ev.success)
    else:
        ok = c.reroll_save()
    if not ok:
        c.flat(max(1, c.surge_value() // 2), dtype=DamageType.PSYCHIC, on=mate)
        c.restore_use(c.ref)


@power(
    "p12249",
    level=7,
    cls="x7_658",
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=PSIONIC_IMPLEMENT,
    attack=Attack(Pick.PRIMARY, vs=WILL),
)
def p12249(c: Cast) -> None:
    """The point cost is paid once for the use, on the first target."""
    if c.first and not c.spend_points(2):
        return
    victim = c.target
    if not _swing(c):
        return
    c.damage("2d6", _best(c), dtype=DamageType.PSYCHIC)
    c.slowed(until=When.EONT)
    for mate in c.in_squares(c.area(), side="ally"):
        c.bonus(
            "damage", 2, on=mate, until=When.EONT, kind="power",
            when=lambda ctx, v=victim: ctx.get("target") == v,
        )


@power(
    "p12250",
    level=9,
    cls="x7_658",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=PSIONIC_IMPLEMENT,
    attack=Attack(Pick.PRIMARY, vs=WILL),
)
def p12250(c: Cast) -> None:
    """The escalation watch is held for the encounter and gated on the daze
    still standing, rather than on a save-ends duration of its own -- two of
    those would be two saving throws for one printed effect."""
    victim = c.target
    if victim is None:
        return
    if _swing(c):
        c.damage("2d6", _best(c), dtype=DamageType.PSYCHIC)
    daze = c.dazed(on=victim, until=When.SAVE_ENDS)

    def worse(ev: Hit) -> None:
        if ev.target != victim or not c.is_(Condition.DAZED, on=victim):
            return
        c.end_effect(daze)
        c.stunned(on=victim, until=When.EONT)

    c.watch(Hit, worse, until=When.ENCOUNTER, once=True)


@power(
    "p12251",
    level=10,
    cls="x7_658",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_ALLY,
    keywords=PSIONIC,
)
def p12251(c: Cast) -> None:
    """Both halves. `c.spend_surge` is "spend a surge and gain nothing for
    it", which is exactly "the target loses a healing surge", and
    `c.regain_points` is the mirror the pool was missing.

    The old note had the diagnosis right and the conclusion wrong: it
    checked `c.transfer_points` and correctly refused it -- that moves
    points *out* of the caster's pool and returns 0 when the caster has
    none, the opposite direction. The missing verb was a self-targeting
    regain, which is what `c.regain_points` now is.

    The ally pays first, because the card is one sentence: an ally with no
    surge left means no points. The Level 23 line is paragon and out of
    scope.
    """
    mate = c.target
    if mate is None or not c.spend_surge(on=mate):
        return
    c.regain_points(2)


# -- x7_950 -----------------------------------------------------------------

ARCANE_IMPLEMENT = [Keyword.ARCANE, Keyword.IMPLEMENT]


@power(
    "p16093",
    level=0,
    cls="x7_950",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=[*ARCANE_IMPLEMENT, Keyword.COLD, Keyword.ELEMENTAL],
    attack=Attack(INT, vs=FORT),
)
def p16093(c: Cast) -> None:
    if not _swing(c):
        return
    c.damage("1d8", _best(c), dtype=DamageType.COLD)
    c.push(2)
    c.slowed(until=When.EONT)
    c.vulnerable(5, DamageType.COLD, until=When.EONT)


@power(
    "p16094",
    level=0,
    cls="x7_950",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FIRE, Keyword.THUNDER, Keyword.ZONE, Keyword.ELEMENTAL],
    attack=Attack(INT, vs=REF),
)
def p16094(c: Cast) -> None:
    """The zone bites on *ending* a turn in it, which `c.hazard` does not
    say -- that one is entering and starting -- so the watch is written out."""
    if c.first:
        zid = c.zone(c.area(), label=c.ref, until=When.EONT, difficult=True)

        def scorch(ev: TurnEnd) -> None:
            if _inside(c, zid, ev.actor):
                c.flat(5, dtype=DamageType.FIRE, on=ev.actor)

        c.watch(TurnEnd, scorch, until=When.EONT)
    if _swing(c):
        c.damage("1d6", _best(c), dtype=DamageType.THUNDER)
        c.prone()


@power(
    "p16095",
    level=2,
    cls="x7_950",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.ELEMENTAL],
)
def p16095(c: Cast) -> None:
    """"Each creature", as printed -- the caster is not excepted."""
    ring = c.aura(2, label=c.ref, until=When.SUSTAIN, sustain=MINOR)

    def chill(ev: TurnStart) -> None:
        who = ev.actor
        if not _inside(c, ring, who):
            return
        c.slowed(on=who, until=When.SOTNT)
        c.vulnerable(5, DamageType.COLD, on=who, until=When.SOTNT)
        c.penalty("attack", 2, on=who, until=When.SOTNT)

    c.watch(TurnStart, chill, until=When.ENCOUNTER)


@power(
    "p16096",
    level=2,
    cls="x7_950",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.FIRE, Keyword.ELEMENTAL],
)
def p16096(c: Cast) -> None:
    """"Willingly leaves" is asked of `Moved`, which is the only movement
    event carrying both where the creature came from and how it got there --
    a shove out of the aura is not a departure the card charges for."""
    ring = c.aura(2, label=c.ref, until=When.SUSTAIN, sustain=MINOR)
    held = c.world.get(ring, Zone)
    if held is not None:
        held.difficult = True
    c.ignores_difficult(on=c.me, until=When.ENCOUNTER)
    began: dict[int, int] = {}

    def note(ev: TurnStart) -> None:
        if _inside(c, ring, ev.actor):
            began[ev.actor] = c.distance(to=ev.actor)

    def retreat(ev: TurnEnd) -> None:
        who = ev.actor
        if who not in c.enemies() or not _inside(c, ring, who):
            return
        if c.distance(to=who) > began.get(who, 0):
            c.flat(5, dtype=DamageType.FIRE, on=who)

    def leaving(ev: Moved) -> None:
        if getattr(ev, "kind_", "") in ("push", "pull", "slide", "forced"):
            return
        if ev.actor not in c.enemies() or not _live(c, ring):
            return
        zone = c.world.get(ring, Zone)
        if zone is None:
            return
        if ev.from_ in zone.squares and ev.to not in zone.squares:
            c.flat(5, dtype=DamageType.FIRE, on=ev.actor)

    c.watch(TurnStart, note, until=When.ENCOUNTER)
    c.watch(TurnEnd, retreat, until=When.ENCOUNTER)
    c.watch(Moved, leaving, until=When.ENCOUNTER)


@power(
    "p16097",
    level=6,
    cls="x7_950",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(2),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.COLD, Keyword.ZONE, Keyword.ELEMENTAL],
)
def p16097(c: Cast) -> None:
    """The ice and the icicles are two things: a difficult zone, and three
    solid squares with a once-a-turn bite around each.

    Both markers were wrong, and the old body was **stronger than the
    card**. `f2700` is not a trait the engine lacks a word for -- it is
    `c.ignores_difficult("ice")`, which five rows already say, against a
    zone labelled `difficult="ice"`, which `sorcerer/level_6.py` already lays.
    So the exemption is automatic for anything that has it, and the caster's
    own exemption is narrowed to ice: written with no `kind` it waived every
    kind of rough going on the board for the whole fight.

    The extra square is the *shoved* creature's, not the shover's, so
    `c.forces` was the wrong side. `movement` settles a shove as
    `squares + forcing - forced`, so a negative `"forced"` on whoever is
    standing in the zone is the lengthening, and `c.grants_in` is what hangs
    it on the geometry and takes it back at the edge. (`movement`'s own note
    refuses a negative `"forced"` for "*your* pushes move 1 extra" -- that
    one is about the shover and is what `"forcing"` is for. This clause is
    about where the victim is standing, which is the key's own side.)"""
    area = c.area()
    zid = c.zone(area, label=c.ref, until=When.ENCOUNTER, difficult="ice")
    c.ignores_difficult("ice", on=c.me, until=When.ENCOUNTER)
    c.grants_in(zid, "forced", -1, side="any", kind="untyped")
    free = [sq for sq in sorted(area) if not c.in_squares([sq])][:3]
    for sq in free:
        c.wall(1, at=sq, solid=True, until=When.ENCOUNTER, label=c.ref)
    cold = {n for sq in free for n in grid.neighbours(sq)} | set(free)
    bitten: dict[int, int] = {}

    def bite(who: int) -> None:
        if who == c.me or bitten.get(who) == c.world.round:
            return
        bitten[who] = c.world.round
        c.flat(5, dtype=DamageType.COLD, on=who)

    def stepped(ev: EnterSquare) -> None:
        if ev.square in cold:
            bite(ev.actor)

    def lingered(ev: TurnEnd) -> None:
        if any(sq in cold for sq in query.squares(c.world, ev.actor)):
            bite(ev.actor)

    c.watch(EnterSquare, stepped, until=When.ENCOUNTER)
    c.watch(TurnEnd, lingered, until=When.ENCOUNTER)


@power(
    "p16098",
    level=6,
    cls="x7_950",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.FIRE, Keyword.ELEMENTAL],
)
def p16098(c: Cast) -> None:
    """All three clauses are laid again on each sustain, which is what
    "the effect persists until the end of your next turn" means for a set of
    one-turn modifiers."""

    def armour() -> None:
        c.resist(5, DamageType.FIRE, on=c.me, until=When.EONT)
        c.bonus(AC, 2, on=c.me, until=When.EONT, kind="power")
        c.bonus(FORT, 2, on=c.me, until=When.EONT, kind="power")

        def sear(ev: Hit) -> None:
            if ev.target == c.me and by_melee(c.world, c.me, ev):
                c.flat(5, dtype=DamageType.FIRE, on=ev.attacker)

        c.watch(Hit, sear, until=When.EONT)

    armour()
    c.on_sustain(c.effect(c.ref, until=When.SUSTAIN, on=c.me, sustain=MINOR), armour)


@power(
    "p16099",
    level=10,
    cls="x7_950",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(5),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.CONJURATION, Keyword.ELEMENTAL],
    dropped=("c.opportunity_from(square)",),
)
def p16099(c: Cast) -> None:
    """Three solid conjurations that move on a move action, which `speed=`
    already gives them, and a wall that is a wall for one side only.

    **The one-sided wall is the mover's permission, not the blocker's
    property.** `c.may_enter` (cast.py:5786) took a `when=` gate in #673
    and the context it is handed carries `mover` and `occupant`; a solid
    conjuration is indexed in `grid.occupants` by `place` (cast.py:5554),
    so it *is* the occupant the predicate is asked about.
    `movement._clear` consults it on the way past. `i591p1`
    (items/waist.py:711) is the worked sibling, with the same shape of gate.

    **`c.shares_space` on the guardians is the wrong verb and would widen
    the card.** It is read by `_can_stop` as well as by `_clear`, so it
    would let any creature *end* its move in a guardian's square, and
    `c.blocks_entry` does not take that back -- `_can_stop` never asks it.
    Granting the mover's side instead leaves `_can_stop` refusing everybody,
    which is what "move through" means: `i591p1`'s note settles that
    reading.

    **Granted per ally at cast time, which is an honest limit**, the same
    one `c.swap_sight` records: an ally that arrives afterwards is not
    covered. `When.ENCOUNTER` rather than `When.SUSTAIN` on the permission
    is deliberate -- `c.bonus` carries no `sustain_cost`, so a sustained
    modifier would lapse after one round and emit
    `durations._warn_sustainless`'s note. A permission naming eids that
    have been banished grants nothing, since nothing occupies their
    squares.

    **The remaining clause is the marker's, and this paragraph used to name
    a different symbol from the header.** It said the gap was
    `c.strike(from_=)` while `dropped=` says `c.opportunity_from(square)`;
    the header is the one that is right, because the window has to *open*
    before there is any swing to aim. Measured in `movement.step`:
    `watchers` is `before | _reachers`, `reach` is `_threat(world, other,
    eid)`, and every one of those reads `squares(world, other)` -- the
    watcher's own squares and nothing else. So a caster five squares back
    is not in `watchers` at all, and `c.bonus("reach", n)` is the wrong
    lever twice over (it widens from the caster's square, and
    `movement.threat_range` asks it with an empty context, which is
    `f2276`'s note).

    **And there is nothing on the event to read instead.**
    `OpportunityWindow` carries `actor`, `provoker`, `why`, `kind_` and
    `mode` -- no origin square, and `why` is `"moved away"` for a walk, a
    charge and a flight alike. `c.provoke` would open a window the caster
    cannot answer, since the swing still leaves from where he stands: a
    verb that nearly fits, paying the clause on the log while the attack
    is out of reach. So the symbol names one thing -- making a creature
    threaten, and swing, as though it occupied a square it does not.

    **Found while writing this and not fixed here**: each `c.conjure` gets
    its own effect carrying `sustain_cost=MINOR` (cast.py:5560), and
    `durations._sustain_by_default` spends a minor out of the budget per
    effect -- so of three guardians wanting a minor a round, one is kept and
    two lapse at the first turn end. That is a fault in every row conjuring
    more than one sustained thing, not in this clause, and closing it means
    one carrier governing three conjurations rather than three carriers."""
    spots = [sq for sq in sorted(c.area()) if not c.in_squares([sq])][:3]
    guards = tuple(
        eid
        for sq in spots
        if (
            eid := c.conjure(
                at=sq, label=c.ref, until=When.SUSTAIN, sustain=MINOR,
                speed=3, solid=True,
            )
        )
    )
    for friend in (c.me, *c.allies()):
        c.may_enter(
            when=lambda ctx, g=guards: ctx.get("occupant") in g,
            on=friend, until=When.ENCOUNTER,
        )


# -- x7_868 -----------------------------------------------------------------

PRIMAL_POLYMORPH = [Keyword.PRIMAL, Keyword.POLYMORPH]


@power(
    "p14192",
    level=0,
    cls="x7_868",
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL_POLYMORPH,
    once_per_round=True,
)
def p14192(c: Cast) -> None:
    """Tiny, unable to attack, climbing at half speed.

    The shift paid on changing *back* wanted no `on_revert=`: `c.form`
    hands its `Effect` back and already appends to that effect's `on_end`
    itself, for the movement modes it grants, so the reversion is a hook
    this row can reach. It over-fires in one way and only one -- the
    encounter clock ending the form also pays the shift -- which is a
    square at the end of a fight.

    **Every "while in rat form" clause now ends with the form, and three
    of them did not.** The size, the attack refusal and the Stealth bonus
    were laid at `until=When.ENCOUNTER` and nothing tied them to the
    shape, so a character taking the printed minor action to change back
    stayed Tiny and unable to attack for the rest of the fight. `revert=`
    is what makes that reachable and `p13860` is the sibling that does it
    right; `_ends_with` is that file's helper.

    **The equipment clause is written and the marker is gone, and the half
    with combat meaning is the exception list rather than the melding.**
    `c.form(keeps_gear=)` claimed `c.form` needed a parameter to say what
    happens to gear. It does not, because the two things the card takes
    away are each sayable today:

    * *shields* -- the benefit of a worn shield **is** its bonus to AC and
      Reflex, which `c.shield_bonus` reads and a pair of penalties
      forgoes. `f949` is the printed sibling for exactly that pair, and
      the penalties are gated on there being a shield for the reason its
      note gives: paying nothing would make this a free line for anybody.
    * *item powers* -- an item's own rows go into `Powers.known` while it
      is worn (`Magic.powers`), and an item row is one whose header says
      `cls="item"`, which is how `f1362b` already asks. `c.forbid`
      takes a row away without spending it, so it comes back with the
      shape. A **Property** is `action=NONE` and is not a power, so it is
      left alone -- the card's exception names powers and this one does not
      carry the druid card's wider "and the properties of weapons".

    What is left of the sentence is inventory bookkeeping with no combat
    consequence -- items in hand being dropped, worn gear not coming off,
    a container's contents out of reach -- which is the reading `p5032`
    and `f1857` already settled for the identical printed paragraph. No
    symbol, because there is nothing for one to wait for.
    """
    me = c.me
    shape = c.form(
        modes={"climb": max(1, c.speed_of(me) // 2)},
        until=When.ENCOUNTER,
        revert=MINOR,
        label=c.ref,
    )
    # Named, because `on_end` wants `() -> None` and `c.shift` answers with
    # whether it moved.
    def step_off() -> None:
        c.shift(1, who=me)

    shape.on_end.append(step_off)
    _ends_with(
        c,
        shape,
        c.resize(Size.TINY, on=me, until=When.ENCOUNTER),
        c.cannot_attack(on=me, until=When.ENCOUNTER),
        c.bonus("skill:stealth", 4, on=me, until=When.ENCOUNTER),
    )
    guard = c.shield_bonus()
    if guard:
        _ends_with(
            c,
            shape,
            c.penalty(AC, guard, on=me, until=When.ENCOUNTER),
            c.penalty(REF, guard, on=me, until=When.ENCOUNTER),
        )
    held = c.world.get(me, Powers)
    for ref in sorted(held.known if held is not None else ()):
        row = REGISTRY.get(ref)
        if row is None or row.cls != "item" or row.action is ActionType.NONE:
            continue
        _ends_with(c, shape, c.forbid(ref, on=me, until=When.ENCOUNTER))


@power(
    "p14193",
    level=0,
    cls="x7_868",
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL_POLYMORPH,
    once_per_round=True,
)
def p14193(c: Cast) -> None:
    """Hybrid form keeps every statistic, so the form itself lays nothing
    but the shape and the way out.

    **Two things here were false and this is a theme row, not an item.**

    The marker was `etl.item.inline_block()`, which is an item's page
    being cut at its second `<h1>` (#601) -- nothing to do with a theme
    card, and it put this row in a group of thirteen it shares no gap
    with. And the reason given, "that block has no ref of its own", is
    wrong: the ETL mints a `b` ref for a second card printed inside
    another entry and has for 154 powers. `p14193b` exists, with the full
    secondary attack in its spec, and simply had no content row. It does
    now, below.

    `name="hybrid"` is the other half. The form was laid with a `label`
    only, so `Shapes` stayed empty and `query.in_form` could not see it --
    the exact state #477 was built to end, and `p14193b`'s printed
    Requirement is the thing that asks.
    """
    c.form(until=When.ENCOUNTER, revert=MINOR, label=c.ref, name="hybrid")


def _in_hybrid(world: World, eid: int) -> bool:
    """The printed Requirement: `p14193` must be active.

    **Not `query.in_form`, and the first draft of this used it.** That
    reader is *permissive when nothing has been recorded*, deliberately
    and with its reasoning stated: a monster that has not changed shape is
    in whatever shape it was found in, its block does not say which, so a
    Requirement must not rule an attack out. Correct there and wrong here
    -- a character starts in humanoid form, always, and only `p14193` puts
    it in hybrid. Asked that way the gate answered **yes before the form
    was ever taken**, which is the silently-false shape this tree is
    organised against; `audit` happily exercised the row on a board where
    nobody had transformed.

    So it asks the question that *is* answerable: does a hold `p14193`
    laid still stand on this creature. Every effect carries the ref of
    the row that laid it, so the live list is the register --
    `feats.assassin_c._in_form` is the same read, kept local rather than
    imported across content files. A `requires=` gate gets
    `(world, eid)` and no `Cast`, so it reads `world.effects` directly.

    `p14193` still lays `name="hybrid"` as well, because that is what
    makes the form answerable to anything asking the *categorical*
    question, and that half was simply missing.
    """
    return any(eff.label.startswith("p14193")
               for eff in world.effects.of(eid))


@power(
    "p14193b",
    level=0,
    cls="x7_868",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PRIMAL],
    attack=Attack(ability=(STR, DEX), vs=AC, plus=4),
    requires=_in_hybrid,
    requires_text="you must be in hybrid form",
)
def p14193b(c: Cast) -> None:
    """The secondary attack printed under `p14193`, which had no row.

    The `+4` is in the header as `plus=`, because the card prints it as
    part of the attack line rather than as a bonus somebody grants -- so a
    policy can forecast the hit chance without running the row.

    **The damage is in the body and that is deliberate.** The card prints
    "Strength modifier or Dexterity modifier", the same choice as the
    attack line, and a header `Damage(bonus=)` takes one ability name --
    `_bonus_of` resolves exactly one. Writing either alone is the mistake
    `Attack.ability`'s own docstring records as worth up to four points on
    the wrong character. So the modifier is taken the way the attack takes
    it, as the better of the two, and this row is not rescalable. That is
    the honest limit `dsl.Damage` names for a body that computes.

    The `Level 21:` lines raising the bonus to +6 and the dice to 2d8 are
    out of scope here, as every paragon and epic step is.
    """
    if not c.strike():
        return
    c.damage("1d8", max(c.stats.mod(STR), c.stats.mod(DEX)))
    c.ongoing(5)


def _my_crit(world: Any, me: int, ev: Any) -> bool:
    return getattr(ev, "attacker", None) == me and bool(getattr(ev, "critical", False))


@power(
    "p14195",
    level=2,
    cls="x7_868",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.PRIMAL, Keyword.FEAR],
    trigger="you score a critical hit",
    on=Trigger(Hit, _my_crit, "you score a critical hit"),
)
def p14195(c: Cast) -> None:
    c.penalty("attack", 4, until=When.EONT, when=_aimed_at_me(c))


@power(
    "p14196",
    level=6,
    cls="x7_868",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PRIMAL],
    narrative=("skill:thievery",),
)
def p14196(c: Cast) -> None:
    """The Stealth half is exact, bonus and reroll both. Thievery is the
    other skill named and nothing on a board ever rolls one -- picking a
    lock is not a fight -- so that bonus has nowhere to go and no mechanism
    is missing behind it."""
    held = c.bonus("skill:stealth", 2, on=c.me, until=When.ENCOUNTER, kind="power")

    def again(ev: SkillCheck) -> None:
        if ev.actor != c.me or ev.skill != "stealth":
            return
        c.end_effect(held, on=c.me)
        c.trigger = ev
        c.reroll_check(keep="new", bonus=5)

    c.arm_trigger(SkillCheck, again, cost=FREE, until=When.ENCOUNTER, label=c.ref)


@power(
    "p14197",
    level=10,
    cls="x7_868",
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PRIMAL],
    trigger="you roll initiative",
    on=Trigger(InitiativeRolled, about_me, "you roll initiative"),
)
def p14197(c: Cast) -> None:
    """"Stand up or move" is one or the other and standing is only ever the
    answer when the fight opened with you down."""
    c.initiative(4, on=c.me)
    if c.is_(Condition.PRONE, on=c.me):
        c.grant_action("stand", FREE, on=c.me)
    else:
        c.move(c.speed_of(c.me), who=c.me)


# -- x7_857 -----------------------------------------------------------------

MARTIAL = [Keyword.MARTIAL]


def _ally_within_2_hit(world: Any, me: int, ev: Any) -> bool:
    who = getattr(ev, "target", None)
    if who is None or who == me:
        return False
    if query.team(world, who) is not query.team(world, me):
        return False
    return query.distance_between(world, me, who) <= 2


def _adjacent_ally_hit(world: Any, me: int, ev: Any) -> bool:
    who = getattr(ev, "target", None)
    if who is None or who == me:
        return False
    if query.team(world, who) is not query.team(world, me):
        return False
    return query.adjacent(world, me, who)


@power(
    "p14149",
    level=0,
    cls="x7_857",
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=CloseBurst(2),
    target=NO_TARGET,
    keywords=MARTIAL,
    trigger="an ally within 2 squares is hit and you are not a target",
    on=Trigger(Hit, _ally_within_2_hit, "an ally within 2 squares is hit"),
)
def p14149(c: Cast) -> None:
    """"After the attack is resolved" is a one-shot watch on the blow landing
    -- taking the swing here would put it before the attack it answers."""
    ev = c.trigger
    mate = getattr(ev, "target", None)
    foe = getattr(ev, "attacker", None)
    if mate is None or foe is None:
        return
    c.swap(mate)
    c.redirect(to=c.me)

    def riposte(hurt: DamageApplied) -> None:
        if hurt.target == c.me:
            c.basic(on=foe)

    c.watch(DamageApplied, riposte, until=When.EOT, once=True)


@power(
    "p14151",
    level=2,
    cls="x7_857",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(1),
    target=Target("team", 2),
    keywords=MARTIAL,
)
def p14151(c: Cast) -> None:
    """"You and one ally" is two targets from `"team"`, the side including
    the caster. The `"ally"` pool is the side *without* it -- the two spelled
    the same side until #364 and no longer do, so a target line that means to
    catch the caster has to say `"team"`."""
    for defence in ALL_DEFENCES:
        c.bonus(defence, 2, until=When.EONT, kind="power")
    c.no_advantage(on=c.target, until=When.EONT)


def _surprised_me(world: Any, me: int, ev: Any) -> bool:
    return ev.target == me and ev.condition is Condition.SURPRISED


@power(
    "p14152",
    level=6,
    cls="x7_857",
    usage=DAILY,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    trigger="you are surprised at the start of an encounter",
    on=Trigger(ConditionApplied, _surprised_me, "you are surprised"),
)
def p14152(c: Cast) -> None:
    """`targets_me` is not usable here: `ConditionApplied` names its subject
    `target`, and the condition has to be read as well."""
    c.cure(Condition.SURPRISED, on=c.me)


@power(
    "p14153",
    level=10,
    cls="x7_857",
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL, Keyword.HEALING],
    trigger="an adjacent ally is hit by an attack that does not include you",
    on=Trigger(Hit, _adjacent_ally_hit, "an adjacent ally is hit"),
)
def p14153(c: Cast) -> None:
    c.redirect(to=c.me)

    def paid(hurt: DamageApplied) -> None:
        if hurt.target == c.me:
            c.surge(on=c.me)

    c.watch(DamageApplied, paid, until=When.EOT, once=True)


# -- x7_870 -----------------------------------------------------------------

PRIMAL = [Keyword.PRIMAL]


@power(
    "p14201",
    level=0,
    cls="x7_870",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
)
def p14201(c: Cast) -> None:
    """Refused at the window rather than handed out as an immunity: the
    printed line takes the *attack* away from anybody standing inside, and
    `c.no_provoke` names one protected creature at a time."""
    ring = c.aura(2, label=c.ref, until=When.EONT)

    def shut(ev: OpportunityWindow) -> None:
        if ev.actor in c.enemies() and _inside(c, ring, ev.actor):
            ev.cancel("inside the aura")

    c.watch(OpportunityWindow, shut, until=When.EONT, window=Window.BEFORE)


@power(
    "p14202",
    level=2,
    cls="x7_870",
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
    trigger="you dislike a History, Nature or Religion check",
    on=Trigger(SkillCheck, my_check("history", "nature", "religion"), "your check"),
)
def p14202(c: Cast) -> None:
    """"Use the second result, even if it's lower" is `keep="new"`."""
    c.reroll_check(keep="new", bonus=5)


@power(
    "p14203",
    level=6,
    cls="x7_870",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
)
def p14203(c: Cast) -> None:
    """Athletics is a skill the engine rolls -- an escape, a bull rush --
    and the bare Strength check has a key of its own now, so both printed
    halves are laid."""
    c.bonus("skill:athletics", 4, on=c.me, until=When.ENCOUNTER, kind="power")
    c.bonus("ability:str", 4, on=c.me, until=When.ENCOUNTER, kind="power")


@power(
    "p14204",
    level=10,
    cls="x7_870",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(2),
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL, Keyword.ZONE],
    dropped=("c.no_healing(temp_hp=)",),
)
def p14204(c: Cast) -> None:
    """`Healed` is a `Decision` so the healing half is refused outright.
    `TempHP` is a plain notification announced after the points have landed,
    so the other half of the same sentence cannot be refused at all.

    **Re-pointed off `events.TempHP.cancel`, which was a one-row spelling
    of a gap two other rows were already waiting on.** `i3337p1` and
    `m5496a0` print the same clause and carry `c.no_healing(temp_hp=)`,
    and the engine change behind the two names is the same one:
    `resolve.temp_hp` writes `health.temp` and emits *afterwards*
    (`resolve.py:1730`), so there is no moment to refuse. The parameter
    cannot exist until the emit becomes a `Decision`, which is why
    pointing at the content-facing name does not report this row ready
    early.

    **Not `TempHP.swallowed`**, which `f3781` carries and which is the
    neighbouring gap rather than this one: that row is written and unpaid
    because the non-stacking `if amount <= health.temp: return` returns
    without announcing, so nothing on the bus tells "no pool offered" from
    "a pool offered and lost to a bigger one". Making the event refusable
    and making the losing pool observable are two changes, and a row
    waiting on one must not go green on the other. #1232 is the second of
    the two and says so in its title; this row is not on it.

    The zone-gated shape stays hand-written either way: `c.no_healing`
    takes no `when=`, so it cannot be narrowed to whoever is standing
    inside, and `_inside` is what the printed sentence asks."""
    zid = c.zone(c.area(), label=c.ref, until=When.ENCOUNTER)

    def deny(ev: Healed) -> None:
        if ev.target in c.enemies() and _inside(c, zid, ev.target):
            ev.cancel("inside the zone")

    def shelter(ev: TurnEnd) -> None:
        if _mine(c, ev.actor) and _inside(c, zid, ev.actor):
            c.temp_hp(5, on=ev.actor)

    c.watch(Healed, deny, until=When.ENCOUNTER, window=Window.BEFORE)
    c.watch(TurnEnd, shelter, until=When.ENCOUNTER)


# -- x7_916 -----------------------------------------------------------------

ARCANE = [Keyword.ARCANE]


def _guard_of(c: Cast) -> int | None:
    for eid in c.within(20, side="team"):
        ident = c.world.get(eid, Ident)
        if ident is not None and ident.ref == "x10_57":
            return eid
    return None


@power(
    "p15885",
    level=0,
    cls="x7_916",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(5),
    target=NO_TARGET,
    keywords=[*ARCANE, Keyword.SUMMONING],
)
def p15885(c: Cast) -> None:
    """`c.cast_from` is the printed "you make the roll using your
    statistics".

    **`x10_57` has a block now** (#459), so the `try`/`except KeyError` that
    guarded a missing row is gone -- the guard was hiding the gap, and a
    `KeyError` is what a genuinely absent ref should do. Its hit points are
    "your healing surge value" and its defences are the summoner's, which is
    what the block says and what `spawn_associate` reads.

    **"The guard lacks actions of its own" is the spawn, not a verb.**
    `c.no_turn(who)` asked for something `c.summon` was undoing one line
    later: `c.summon`'s own docstring says `loader.spawn` alone makes an
    entity that is not in the initiative order, and then it joins the
    encounter -- which is the half this card does not want. So the summon is
    `spawn_associate` directly, with no `join`, and nothing has to take a
    turn away afterwards. `Summoned` is announced by hand because `c.summon`
    was the only path that emitted it, and a row whose whole Effect is this
    would otherwise leave no trace in the log.

    Instinctive effects are unharmed by standing outside the order:
    `turns._uncommanded` runs at the **summoner's** turn end."""
    from combat_engine.content.loader import spawn_associate

    me = c.me
    here = query.squares(c.world, me)
    free = [
        sq
        for sq in sorted(grid.spread(here, 5) - here)
        if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None
    ]
    if not free:
        return
    guard = spawn_associate(c.world, "x10_57", free[0], of=me)
    c.world.bus.emit(Summoned(actor=me, summon=guard, ref=c.ref))
    c.cast_from(me, on=guard, until=When.ENCOUNTER)

    def toll(ev: Dropped) -> None:
        if ev.actor == guard:
            c.spend_surge(on=me)

    c.watch(Dropped, toll, until=When.ENCOUNTER, once=True)


@power(
    "p15886",
    level=2,
    cls="x7_916",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_ALLY,
    keywords=ARCANE,
)
def p15886(c: Cast) -> None:
    """The point only comes back if the ally actually spent one."""
    mate = c.target
    if mate is None:
        return
    if c.action_point(STANDARD, who=mate):
        c.grant_action_point(1, on=c.me)


@power(
    "p15887",
    level=6,
    cls="x7_916",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
)
def p15887(c: Cast) -> None:
    guard = _guard_of(c)
    c.move(c.speed_of(c.me) + 2, who=c.me)
    if guard is None:
        return
    c.move(c.speed_of(guard) + 2, who=guard)
    if c.adjacent(to=guard):
        value = c.surge_value()
        c.temp_hp(value, on=c.me)
        c.temp_hp(value, on=guard)


@power(
    "p15888",
    level=10,
    cls="x7_916",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_ALLY,
    keywords=ARCANE,
    dropped=("c.surge_from(who)",),
)
def p15888(c: Cast) -> None:
    """The trade is `c.give` with a body: a minor action the ally takes once,
    which spends one of the caster's levelled rows and hands the ally back an
    expended row of the same usage and level. Spending the ally's surges as
    though they were the caster's is a standing permission and there is no
    verb that lends a surge pool.

    **Measured rather than asserted, because "nothing can do it" is the
    marker shape that is usually wrong here.** The spend *is* visible and
    refusable -- `SurgeSpent` is a `Decision` and `resolve.spend_surge`
    returns `not spent.cancelled` -- so a watch could see every surge this
    caster pays. What no verb takes is a different *pool*:
    `resolve.spend_surge` decrements the actor's own `Health.surges` and
    names no alternative, and `c.surge`, `c.spend_surge`,
    `c.regain_surge`, `c.second_wind` and `diseases.lost_surges` are all
    about the creature in `on=`.

    So the emulation available today is two bookkeeping moves standing in
    for one -- `c.spend_surge(on=mate)` plus `c.regain_surge(on=c.me)` on
    every `SurgeSpent` -- and it is deliberately not written. It
    hand-writes state the engine derives; it reports the ally's pool as
    spent for nothing and the caster's as refunded, which is two `Note`s
    saying something that did not happen; and `c.regain_surge` is a bare
    `health.surges += count` against no ceiling, so a caster refunded
    above `Health.max_surges` would be handed a pool the extended rest
    never gave him. `c.surge_from(who)` is one gap and the right place for
    it is where the pool is read."""
    mate = c.target
    if mate is None:
        return

    def trade(who: int) -> None:
        ours = c.world.get(c.me, Powers)
        if ours is None:
            return
        spent = set(c.expended())
        mine = [
            ref
            for ref in ours.known
            if ref not in spent
            and REGISTRY.get(ref) is not None
            and REGISTRY[ref].usage in (ENCOUNTER, DAILY)
            and REGISTRY[ref].level > 0
        ]
        pick = c.choose(sorted(mine), "which of your rows to give up") if mine else None
        if pick is None:
            return
        c.expend_row(pick)
        want = REGISTRY[pick]
        back = sorted(
            ref
            for ref in c.expended(on=who)
            if REGISTRY.get(ref) is not None
            and REGISTRY[ref].usage == want.usage
            and REGISTRY[ref].level == want.level
        )
        if back:
            c.restore_use(back[0], on=who)

    c.give(fn=trade, on=mate, uses=1, cost=MINOR)


# -- x7_936 -----------------------------------------------------------------


def _felled_adjacent(world: Any, me: int, ev: Any) -> bool:
    return getattr(ev, "source", None) == me and query.adjacent(world, me, ev.actor)


def _ours_bloodied_nearby(world: Any, me: int, ev: Any) -> bool:
    foe = getattr(ev, "source", None)
    if foe is None or query.team(world, foe) is query.team(world, me):
        return False
    if query.team(world, ev.actor) is not query.team(world, me):
        return False
    return query.distance_between(world, me, foe) <= 5


def _low_roll(world: Any, me: int, ev: Any) -> bool:
    who = getattr(ev, "attacker", None)
    if who is None:
        who = getattr(ev, "actor", None)
    return who == me and 1 <= getattr(ev, "natural", 0) <= 3


@power(
    "p16005",
    level=0,
    cls="x7_936",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL, Keyword.FEAR],
    trigger="you bloody or drop an adjacent enemy",
    on=(
        Trigger(Bloodied, _felled_adjacent, "you bloody an adjacent enemy"),
        Trigger(Dropped, _felled_adjacent, "you drop an adjacent enemy"),
    ),
    dropped=("c.surrender()",),
)
def p16005(c: Cast) -> None:
    """Both halves of the trigger are declared -- `Bloodied` and `Dropped`
    each carry `source`. Forcing a beaten enemy to surrender is a second
    thing entirely: nothing takes a creature out of a fight that way.

    **The check half is already sayable and is deliberately not written.**
    `c.check("skill:intimidate", dc, against=foe)` is the roll, and the DC
    is the moderate band `combat_engine.dc` reads for the target's level --
    so a body could roll it today and then have nothing to do with the
    answer. A row that rolls for no consequence is worse than a dropped
    clause, because the roll shows up in the log as the clause working.

    **What `c.surrender()` has to decide is in the compendium, which is why
    the symbol is actionable rather than a placeholder.** `game.db`'s
    `skill_use` row for this skill prints the three halves a verb would
    need and prints **no DC at all** (`dc` is `NULL`): a bloodied creature
    is forced to surrender or cowed into some other action; it is explicitly
    not mind control, so it will not take an action that harms it
    immediately; and on a failure the same creature cannot be tried again
    for the rest of the encounter. Nothing in that is a condition the engine
    holds -- it is a standing refusal to attack, which is a `policy`
    question as much as an engine one. Read it before building the verb; the
    row above is the whole of what print settles."""
    held = [
        c.penalty("attack", 2, on=foe, until=When.ENCOUNTER, when=_aimed_at_me(c))
        for foe in c.enemies()
        if c.can_see(to=foe)
    ]

    def over(ev: Hit) -> None:
        if ev.target != c.me:
            return
        for effect in held:
            c.end_effect(effect)

    c.watch(Hit, over, until=When.ENCOUNTER, once=True)


@power(
    "p16006",
    level=2,
    cls="x7_936",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    trigger="you roll a natural 1, 2 or 3",
    on=(
        Trigger(AttackRolled, _low_roll, "a natural 1-3 on an attack roll"),
        Trigger(SkillCheck, _low_roll, "a natural 1-3 on a skill check"),
    ),
)
def p16006(c: Cast) -> None:
    if isinstance(c.trigger, SkillCheck):
        c.reroll_check(keep="new", bonus=c.cha_mod)
    else:
        c.reroll_attack(keep="new", bonus=c.cha_mod)


@power(
    "p16007",
    level=6,
    cls="x7_936",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL,
)
def p16007(c: Cast) -> None:
    """The chase is asked at `TurnEnd`, which is where the printed "ends its
    next turn" is decided; the damage bonus answers the *declaration*, so it
    is paid whether the enemy's swing lands or not."""
    victim = c.target
    if victim is None:
        return

    def closing(ev: TurnEnd) -> None:
        if ev.actor != victim or c.adjacent(to=victim):
            return
        where = _square(c, victim)
        if where is None:
            return
        for sq in grid.neighbours(where):
            if not c.in_squares([sq]):
                c.shift(c.speed_of(c.me), to=sq)
                return

    def provoked(ev: AttackDeclared) -> None:
        if ev.attacker != victim or ev.target != c.me:
            return
        c.bonus(
            "damage", 5, on=c.me, until=When.EONT, kind="power",
            when=lambda ctx: ctx.get("target") == victim,
        )

    c.watch(TurnEnd, closing, until=When.EOTNT, once=True)
    c.watch(AttackDeclared, provoked, until=When.EOTNT, once=True)


@power(
    "p16008",
    level=10,
    cls="x7_936",
    usage=DAILY,
    action=ActionType.IMMEDIATE_REACTION,
    reach=CloseBurst(5),
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL, Keyword.FEAR],
    trigger="you or an ally is bloodied by an enemy within 5 squares",
    on=Trigger(Bloodied, _ours_bloodied_nearby, "an enemy bloodies one of yours"),
)
def p16008(c: Cast) -> None:
    """The enemy comes off `Bloodied.source`, not off `ev.targets`: this row
    is `NO_TARGET` and never touched the creature it names."""
    foe = getattr(c.trigger, "source", None)
    if foe is None:
        return
    c.grants_advantage(on=foe, until=When.ENCOUNTER, to="team")

    def cowed(ev: Hit) -> None:
        if ev.attacker == c.me and ev.target == foe:
            c.penalty("attack", 2, on=foe, until=When.EOTNT)

    c.watch(Hit, cowed, until=When.ENCOUNTER)


# -- x7_947 -----------------------------------------------------------------


def _my_melee_roll(world: Any, me: int, ev: Any) -> bool:
    return getattr(ev, "attacker", None) == me and by_melee(world, me, ev)


@power(
    "p16081",
    level=0,
    cls="x7_947",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.WEAPON, Keyword.ELEMENTAL],
    trigger="you make a melee weapon attack roll",
    on=Trigger(AttackRolled, _my_melee_roll, "you make a melee attack roll"),
)
def p16081(c: Cast) -> None:
    """"Roll twice" is `keep="best"`.

    "If both attack rolls hit" is answerable and the marker said it was not:
    `AttackResult.rolls` keeps every face thrown, so the discarded one is
    still there after the reroll, and what the die is added to is
    `total - natural`. Each face is judged by the printed rule -- a 1 never
    hits and a 20 always does.

    The extra damage is a one-shot dice bonus rather than a rider on the
    `Hit`, because the damage sum is taken *after* this window: a modifier
    laid here is read by the very blow that provoked it. The paragon dice
    are out of scope."""
    result = getattr(c.trigger, "result", None)
    if result is None or not c.reroll_attack(keep="best"):
        return
    faces = result.rolls[-2:]
    rest = result.total - result.natural
    if len(faces) == 2 and all(
        face == 20 or (face != 1 and face + rest >= result.target_defence)
        for face in faces
    ):
        c.bonus("damage", 0, dice="1d8", on=c.me, until=When.EOT, once=True)


@power(
    "p16082",
    level=2,
    cls="x7_947",
    usage=DAILY,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.HEALING, Keyword.ELEMENTAL],
    trigger="you are bloodied by an attack",
    on=Trigger(Bloodied, about_me, "you are bloodied"),
)
def p16082(c: Cast) -> None:
    """`about_me` is right here -- `Bloodied` names its subject `actor`."""
    c.surge(on=c.me)
    c.bonus(AC, 2, on=c.me, until=When.EONT, kind="power")
    c.bonus(FORT, 2, on=c.me, until=When.EONT, kind="power")


def _melee_weapon(ctx: dict[str, Any]) -> bool:
    """"Melee weapon attacks", as a modifier gate. The row's own keywords
    say whether it is a weapon attack; the context says whether it was
    thrown."""
    row = REGISTRY.get(str(ctx.get("power") or ""))
    return (
        row is not None
        and Keyword.WEAPON in row.keywords
        and not ctx.get("ranged")
    )


@power(
    "p16083",
    level=6,
    cls="x7_947",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    todo=("etl.theme_feature",),
    keywords=[Keyword.ELEMENTAL],
)
def p16083(c: Cast) -> None:
    """The whole effect is resistance to all damage equal to the amount the
    `x7_947` level 5 feature grants, and the card never prints the number.

    **Re-pointed off `spec.feature_ref()`, whose premise is false.** That
    symbol says the brief handed over a printed name where a ref belongs,
    and this brief prints no name at all -- the clause reads
    `x7_947 level 5 feature`, with the theme already resolved to its alias
    ref. Nothing was being withheld, so there was nothing for `spec.py` to
    fix, and the row sat in a one-row spelling of the `spec.ref` family it
    does not belong to.

    **The gap is one directory further out: a theme's features are not
    imported.** Measured in `game.db` -- a theme appears in exactly one
    place, the `class` column of 510 power rows, and no table holds a theme
    feature at all. `etl/build.py`'s theme pass reads only the id and the
    name out of the source's theme table and the features sit unread in the
    same table's text column, which 104 of its 116 rows carry. So there is
    no ref to point at and no amount to read. That is the shape
    `etl.paragon_path` already names next door: `game.db` carries no paragon
    path either, and `f2263` drops the half of its clause that would have
    had to recognise one.

    `todo=` rather than `dropped=`, because the resistance *is* the effect:
    the bloodied clause only adds 2 to it, so with the number gone nothing
    plays.

    **A second gap sits behind the first and is named here rather than
    marked**, since a marker names one thing. Even with the feature
    imported, nothing reads *how much* another row grants -- the reading
    `c.damage_of(ref)`'s three rows want for damage, wanted for resistance.
    The import has to land first; there is nothing for a reader to read
    until it does."""


@power(
    "p16084",
    level=10,
    cls="x7_947",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.STANCE, Keyword.ELEMENTAL],
)
def p16084(c: Cast) -> None:
    """19-20 is `crit_range` 1; 18-20 would be 2.

    "Melee weapon attack" needed nothing from the attack context after all.
    The context carries `power`, and a weapon attack is one whose *row*
    declares `Keyword.WEAPON` -- which is how `fighter/level_0._weapon_power`
    has asked it all along, and which `mba` satisfies. `ranged` supplies the
    melee half."""
    c.stance(label=c.ref)
    c.bonus(
        "crit_range", 1, on=c.me, until=When.STANCE, when=_melee_weapon,
    )
    c.bonus(
        "attack", 2, on=c.me, until=When.STANCE, kind="power",
        when=lambda ctx: bool(ctx.get("opportunity")),
    )


# -- x7_978 -----------------------------------------------------------------


@power(
    "p16391",
    level=0,
    cls="x7_978",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.CHARM, Keyword.ELEMENTAL],
)
def p16391(c: Cast) -> None:
    """Narrowed to the two kinds of attack the card names, which is the half
    that was missing.

    The marker asked `AttackDeclared` for a reach it does not carry. It does
    not need to: the event carries the row's ref, and the row carries its
    `Range`, whose `kind` is `"melee"`, `"ranged"`, `"close_burst"`,
    `"close_blast"`, `"area_burst"` or `"wall"`. The old body used
    `c.cannot_attack`, which refuses everything -- a burst included -- so it
    was stronger than its card on every area power in the game.

    `c.cannot_attack` is itself nothing but a `Window.BEFORE` watch on
    `AttackDeclared` that cancels, and that is what is hand-rolled here with
    the two extra questions it takes no `when=` for. Level is asked at the
    swing rather than at the minor action, since it is a standing fact about
    the creature and a summoned reinforcement has to be covered too."""
    done: list[bool] = []
    mine = c.me

    def barred(ev: AttackDeclared) -> None:
        if done or ev.target != mine or ev.attacker == mine:
            return
        stats = c.world.get(ev.attacker, Stats)
        if stats is None or stats.level > c.level:
            return
        row = REGISTRY.get(ev.power)
        if row is not None and row.reach.kind in ("melee", "ranged"):
            ev.cancel("cannot be targeted by melee or ranged attacks")

    def spent(ev: AttackDeclared) -> None:
        if ev.attacker == mine:
            done.append(True)

    c.watch(AttackDeclared, barred, until=When.EONT, window=Window.BEFORE)
    c.watch(AttackDeclared, spent, until=When.EONT, once=True)


@power(
    "p16392",
    level=2,
    cls="x7_978",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[*ARCANE, Keyword.ELEMENTAL],
    trigger="you would make a Diplomacy or an Intimidate check",
    on=Trigger(
        CheckDeclared, my_check("diplomacy", "intimidate"),
        "one of those checks",
    ),
    narrative=("skill:diplomacy",),
)
def p16392(c: Cast) -> None:
    """*"You instead make an Arcana check with a +2 power bonus."*

    **`CheckDeclared`, so the `window=` override is gone.** The old shape
    wrote `ev.skill` on a `SkillCheck` and had to declare `Window.BEFORE`,
    because a free action is otherwise offered in the AFTER window where
    `finish` has already totalled the number -- correct, and one word from
    inert. `CheckDeclared` precedes the d20, so there is no window in which
    it is too late, and the swap is announced rather than being a silent
    field write.

    The bonus is laid **before** the substitution, and that ordering is the
    one load-bearing thing left here: `c.bonus` keys on `skill:arcana`, and
    the modifier total is read at resolve, so either order works today --
    but laying it first means the bonus is already standing when the check
    that reads it is built, which is the order the card reads in.

    The +2 stays a laid bonus rather than an addition to `ev.bonus`, because
    the card prints a *power* bonus and only a modifier carries a kind;
    `once=True` keeps it from paying out on a second arcana check this turn.

    `narrative=`: counting as sharing a language with the subject of the
    check is the other clause, and no board ever asks what language two
    creatures have in common, so there is no diplomacy circumstance for the
    waiver to narrow."""
    c.bonus("skill:arcana", 2, on=c.me, until=When.EOT, kind="power", once=True)
    c.substitute_check("arcana")


@power(
    "p16393",
    level=6,
    cls="x7_978",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
    narrative=("skill:diplomacy", "skill:intimidate"),
)
def p16393(c: Cast) -> None:
    """The Will bonus is exact and gated on standing in the aura. The other
    clause scales a Diplomacy and Intimidate bonus with how many allies are
    inside, and a board rolls neither check -- talking a guard round is not a
    fight -- so the scaling has nowhere to land and nothing is missing."""
    ring = c.aura(1, label=c.ref, until=When.ENCOUNTER)
    for mate in c.allies():
        c.bonus(
            WILL, 2, on=mate, until=When.ENCOUNTER, kind="power",
            when=lambda ctx, w=mate: _inside(c, ring, w),
        )


@power(
    "p16394",
    level=10,
    cls="x7_978",
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=CloseBurst(5),
    target=NO_TARGET,
    keywords=[Keyword.CHARM, Keyword.FIRE, Keyword.ELEMENTAL],
    trigger="an enemy within 5 squares hits you",
    on=Trigger(Hit, both(hits_me, enemy_within(5)), "an enemy within 5 hits you"),
)
def p16394(c: Cast) -> None:
    """The burn is paid only when the second roll still lands, so the live
    result is read back off the event rather than assumed."""
    foe = getattr(c.trigger, "attacker", None)
    if foe is None:
        return
    c.reroll_attack(keep="new")
    result = getattr(c.trigger, "result", None)
    if result is not None and result.hit:
        c.flat(5 + c.level // 2, dtype=DamageType.FIRE, on=foe)


# -- x7_988 -----------------------------------------------------------------

#: *"You must have `i390` on your person."* Mundane gear is not modelled,
#: so the Requirement never refuses the row. The three rows that print it
#: share one symbol, deliberately: it is one gap, and the three say the
#: same sentence.
#:
#: **Re-aimed off `c.carrying(ref)`.** That one arrived and is not this: it
#: reads the `Item` component, which is a thing a *power* made and handed
#: over, and a kit is ordinary equipment. `Gear` records weapons, a shield,
#: armour, worn magic and ammunition and has no slot for the rest, so there
#: is no ref to ask for -- and a printed Requirement is a `requires=` gate,
#: handed `(world, eid)`, which cannot call a `Cast` method at all.
#:
#: **And not `Gear.stowed`, which is the one field whose name invites the
#: mistake.** Checked: it is a set of *weapon* refs that are put away
#: rather than in hand -- `Gear.held` subtracts it and `Gear.wield`
#: discards from it -- so it records where a weapon is, not that a
#: non-weapon is carried. `dataclasses.fields(Gear)` lists 19 fields and
#: none of them is a list of ordinary kit.
#:
#: **The import landed and the marker moves back to the field.** #876 is
#: closed: `Category = 'Equipment'` is 233 rows in the same `Item` table,
#: every one at `LevelSort = 0`, which is the only reason the heroic band
#: dropped them. `game.db`'s `item` table is 1,877 -> 2,110 and `i390`
#: exists, so there is now something a carried-items list could hold.
#:
#: **What is still missing is the list, and it cannot land alone.** This
#: used to read "re-pointed off `Gear.carried`… adding the field first
#: would make this Requirement permanently unmeetable", and that is still
#: exactly right: an empty list refuses the Requirement for every
#: character, and these three play today with the clause dropped. A row
#: that plays without one restriction beats a row that never plays.
#:
#: So the field needs a *dealer* alongside it -- something that puts `i390`
#: in the hands of a character whose rows ask for it -- which is #877's
#: question about whether a dealt character carries ordinary kit. The
#: marker names the field because that is the thing a row reads; the
#: dealing is the half that makes it answer True.
def _carrying(ref: str) -> Callable[[Any, int], bool]:
    """"Requirement: you must have `<ref>` on your person".

    `Gear.carried` is the refs a creature has on it but neither wields nor
    wears, and it arrived with `#1233`'s ruling -- dealt characters now
    carry two consumables, so there is something for a carried-item
    requirement to be true *of*. Before that the field did not exist and
    these three rows named it as their gap.

    A `requires=` predicate rather than a body guard, which is the whole
    point: `dsl.usable` reads it, so the row is **not offered** when the
    item is absent. A guard inside the body would let the action be taken
    and then do nothing, which for an immediate reaction means spending the
    one interrupt a round allows.
    """

    def has(world: Any, eid: int) -> bool:
        from combat_engine.engine.components import Gear

        gear = world.get(eid, Gear)
        return gear is not None and ref in gear.carried

    return has


def _enemy_closed(world: Any, me: int, ev: Any) -> bool:
    if not closed_on_me(world, me, ev):
        return False
    return query.team(world, ev.mover) is not query.team(world, me)


def _within_5_of(spot: tuple[int, int]) -> set[tuple[int, int]]:
    return {
        (spot[0] + dx, spot[1] + dy)
        for dx in range(-5, 6)
        for dy in range(-5, 6)
    }


@power(
    "p16442",
    level=0,
    cls="x7_988",
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(INT, vs=REF, plus=2),
    trigger="an enemy enters a square adjacent to you",
    on=Trigger(AdjacencyGained, _enemy_closed, "an enemy moves adjacent to you"),
    requires=_carrying("i390"),
)
def p16442(c: Cast) -> None:
    """Aimed off `AdjacencyGained.mover` rather than off `ev.targets`: an
    immediate reaction picks its targets before it knows what set it off."""
    foe = getattr(c.trigger, "mover", None)
    if foe is None:
        return
    if c.strike(on=foe):
        c.damage("1d6", c.int_mod, on=foe)
    c.grants_advantage(on=foe, until=When.EONT, to="team")


@power(
    "p16443",
    level=2,
    cls="x7_988",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
    requires=_carrying("i390"),
)
def p16443(c: Cast) -> None:
    """The trap is a zone five squares across that springs on the first
    creature the caster cannot see.

    "The creature loses invisibility" is written now. The marker looked for
    a condition and there is none, because invisibility is a
    `Relation.HIDDEN_FROM` held by an effect `c.invisible` labels
    `"<ref> unseen"` -- so `c.end_effect(against=)`, which narrows by label
    fragment, is what takes it away."""
    spot = _free_beside(c)
    if spot is None:
        return
    field = c.zone(_within_5_of(spot), label=c.ref, until=When.ENCOUNTER)

    def sprung(ev: ZoneEntered) -> None:
        if ev.zone != field or ev.actor == c.me or c.can_see(to=ev.actor):
            return
        c.end_effect(on=ev.actor, against="unseen", why=f"{c.ref} revealed it")
        c.penalty("skill:stealth", 10, on=ev.actor, until=When.SAVE_ENDS)
        c.dispel(field)

    c.watch(ZoneEntered, sprung, until=When.ENCOUNTER, once=True)


@power(
    "p16444",
    level=6,
    cls="x7_988",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
    requires=_carrying("i390"),
)
def p16444(c: Cast) -> None:
    """One save-ends effect per creature, not two: the prone half is a watch
    held for the encounter and gated on the creature still granting combat
    advantage, so the card's single "save ends both" is one throw."""
    spot = _free_beside(c)
    if spot is None:
        return
    field = c.zone(_within_5_of(spot), label=c.ref, until=When.ENCOUNTER)
    caught: set[int] = set()

    def sprung(ev: ZoneEntered) -> None:
        if ev.zone != field or ev.actor not in c.enemies():
            return
        c.dispel(field)
        crowd = [ev.actor, *(o for o in c.within(1, of=ev.actor) if o != ev.actor)]
        caught.update(crowd)
        for one in crowd:
            c.grants_advantage(on=one, until=When.SAVE_ENDS, to="team")

    def topple(ev: Hit) -> None:
        if ev.target in caught and query.grants_ca(c.world, ev.target):
            c.prone(on=ev.target)

    c.watch(ZoneEntered, sprung, until=When.ENCOUNTER, once=True)
    c.watch(Hit, topple, until=When.ENCOUNTER)


def _trap_went_off_near(world: Any, me: int, ev: Any) -> bool:
    """A trap or a hazard going off within 5 squares.

    **A trap announces itself by attacking.** `terrain.arm` sets `sprung`
    and swings in the same breath, through `resolve.attack` with the trap
    itself as the attacker -- so `AttackDeclared` is the announcement, and
    it is a `Decision` emitted with the roll as its continuation, which is
    the window an interrupt is for. `query.is_trap` is what tells the
    swinger from a creature, and the tree already reads it exactly this
    way for the printed word "hazard" as well as "trap"
    (`skills/dungeoneering._trap_attacks_me`).

    Distance to the attacker rather than to the target, because the card's
    5 squares is measured from the thing that triggered.
    """
    attacker = getattr(ev, "attacker", None)
    return (
        attacker is not None
        and query.is_trap(world, attacker)
        and query.distance_between(world, me, attacker) <= 5
    )


@power(
    "p16445",
    level=10,
    cls="x7_988",
    usage=DAILY,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=CloseBurst(5),
    target=YOU_AND_EACH_ALLY,
    trigger="a hazard, object or trap within 5 squares of you triggers",
    on=Trigger(
        AttackDeclared, _trap_went_off_near, "a trap within 5 squares goes off",
    ),
)
def p16445(c: Cast) -> None:
    """**The marker was wrong and the row is writable.** It claimed
    `events.HazardTriggered` -- "nothing announces a trap going off" --
    and `p14166` is an interrupt declared on exactly this announcement and
    has been for a while: a trap on the board goes off by *attacking*, and
    `resolve.attack` names it as the attacker. That is the shape of
    general absence this tree keeps refuting, and the one-command check is
    a grep of `content/` for `is_trap`, which finds 47 call sites across 30
    files asking about a trap's swing.

    Two things the printed sentence says that the board cannot field, and
    neither is a missing clause:

    * an **object** triggering. `Scenery`'s own docstring draws the line --
      *"not a `Trap`, which attacks"* -- so an object is a thing that gets
      hit rather than one that swings, and there is nothing for the
      defence gate to match. Nothing is dropped: the clause covers a case
      the rules kernel does not have.
    * a **hazard** triggering, separately from a trap. `c.hazard` is a
      zone with teeth and its bite is `world.damage`, not an attack -- but
      `Trap`'s own docstring calls the component "a hazard rather than a
      creature", and `c.is_trap` is the reader every row printing the word
      "hazard" already uses. One reader for both words is the tree's
      settled reading, not an approximation made here.

    The shift is the target's own, so it carries `who=`: this is the row
    whose siblings in `content/CLAUDE.md` return False before they move
    when `on=`/`who=` is left off a clause about somebody else.

    The defence bonus is gated on the attacker in the modifier's context
    rather than spent on the triggering attack, because the card holds it
    for the encounter against every hazard and not just the one that set
    it off. `f377` is the same gate, written the same way, and guards the
    `None` case rather than letting `c.is_trap()` fall through to
    `c.target`."""
    who = c.target
    if who is None:
        return
    half = c.speed_of(who) // 2
    if half:
        c.shift(half, who=who)
    for defensive in ALL_DEFENCES:
        c.bonus(
            defensive, 2, on=who, until=When.ENCOUNTER, kind="power",
            when=lambda ctx: (
                ctx.get("attacker") is not None and c.is_trap(ctx["attacker"])
            ),
        )


# -- x7_1001 ----------------------------------------------------------------


def _damage_to_me(world: Any, me: int, ev: Any) -> bool:
    return ev.target == me


@power(
    "p16574",
    level=0,
    cls="x7_1001",
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    trigger="you take damage from an attack",
    on=Trigger(DamageRolled, _damage_to_me, "you take damage"),
)
def p16574(c: Cast) -> None:
    """Declared on `DamageRolled`, which is the window in which a number can
    still be taken off it; a `Hit` fires before the blow has been rolled."""
    c.reduce(5 + c.level)
    c.resist(5, on=c.me, until=When.SONT)


@power(
    "p16575",
    level=2,
    cls="x7_1001",
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=CloseBurst(2),
    target=ONE_ALLY,
    keywords=MARTIAL,
    trigger="you are hit by a melee or a ranged attack",
    on=Trigger(Hit, both(hits_me, either(by_melee, by_ranged)), "you are hit"),
)
def p16575(c: Cast) -> None:
    mate = c.target
    if mate is not None:
        c.redirect(to=mate)


@power(
    "p16576",
    level=6,
    cls="x7_1001",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    keywords=MARTIAL,
)
def p16576(c: Cast) -> None:
    """The vulnerability is the ally's and the attack bonus is the caster's,
    which is the whole trade the card prints."""
    if c.target is None:
        return
    c.vulnerable(2, until=When.EONT)
    c.bonus("attack", 2, on=c.me, until=When.EONT, kind="power")


@power(
    "p16577",
    level=10,
    cls="x7_1001",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(5),
    target=NO_TARGET,
    keywords=[Keyword.DIVINE],
)
def p16577(c: Cast) -> None:
    """Three printed options, offered in the card's order."""
    pick = c.choose(["martial", "healing", "p488"], "which favour")
    if pick == "martial":
        for foe in c.in_squares(c.area(), side="enemy"):
            c.grants_advantage(on=foe, until=When.EONT, to="team")
            c.penalty("attack", 4, on=foe, until=When.EONT)
    elif pick == "healing":
        c.surge(on=c.me)
        mates = c.in_squares(c.area(), side="ally")
        if mates:
            c.surge(on=mates[0])
    else:
        for one in [c.me, *c.in_squares(c.area(), side="ally")]:
            c.bonus("damage", 4, on=one, until=When.EONT, kind="power")


# -- x7_1013 ----------------------------------------------------------------


def _my_opportunity_hit(world: Any, me: int, ev: Any) -> bool:
    return getattr(ev, "attacker", None) == me and bool(
        getattr(ev, "opportunity", False)
    )


@power(
    "p16630",
    level=0,
    cls="x7_1013",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.SHADOW, Keyword.FEAR],
    trigger="you hit an enemy with an opportunity attack",
    on=Trigger(Hit, _my_opportunity_hit, "you hit with an opportunity attack"),
)
def p16630(c: Cast) -> None:
    """`Hit` does not declare `opportunity`; it rides as a plain attribute."""
    foe = getattr(c.trigger, "target", None)
    if foe is not None:
        c.immobilized(on=foe, until=When.EOTNT)


@power(
    "p16631",
    level=3,
    cls="x7_1013",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.SHADOW, Keyword.WEAPON, Keyword.FEAR],
    attack=Attack(STR, vs=AC),
)
def p16631(c: Cast) -> None:
    if _swing(c):
        c.damage(c.w(), _best(c))
        c.penalty(WILL, 2, until=When.EONT)


@power(
    "p16632",
    level=6,
    cls="x7_1013",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL, Keyword.SHADOW, Keyword.STANCE],
)
def p16632(c: Cast) -> None:
    c.stance(label=c.ref)

    def struck(ev: Hit) -> None:
        if ev.attacker != c.me or not by_melee(c.world, c.me, ev):
            return
        c.grants_advantage(on=ev.target, until=When.EONT, to="team")
        c.push(1, on=ev.target)

    c.watch(Hit, struck, until=When.STANCE)


@power(
    "p16633",
    level=10,
    cls="x7_1013",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.SHADOW, Keyword.STANCE],
)
def p16633(c: Cast) -> None:
    """`c.deals` was always the wrong door and `f3404`'s docstring says so:
    it overrides the whole type, where this card recolours only what a
    weapon attack left **untyped**. `DamageRolled.dtype` is the door --
    mutable, and `resolve.deal_damage` reads it back off the event after the
    emit -- which is where `f3404` and `i1431x1` both retype a blow.

    "Can change" is asked once, as the stance is taken, for the reason
    `f3404` gives: untyped damage is never resisted and necrotic often is,
    so a single answer is what keeps the stance meaning one thing for as
    long as it stands.
    """
    me = c.me
    c.stance(label=c.ref)
    c.phasing(on=me, until=When.STANCE)
    c.resist(10, DamageType.NECROTIC, on=me, until=When.STANCE)
    if not c.may("deal necrotic damage instead of untyped", who=me):
        return

    def recolour(ev: DamageRolled) -> None:
        if ev.source != me or ev.dtype is not DamageType.UNTYPED:
            return
        row = REGISTRY.get(str(ev.detail or ""))
        if row is not None and Keyword.WEAPON in row.keywords:
            ev.dtype = DamageType.NECROTIC

    c.watch(DamageRolled, recolour, on=me, until=When.STANCE,
            window=Window.BEFORE, label=f"{c.ref} necrotic")


# -- x7_867 -----------------------------------------------------------------


@power(
    "p14189",
    level=2,
    cls="x7_867",
    usage=DAILY,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.DIVINE],
    trigger="you are hit by an attack",
    on=Trigger(Hit, hits_me, "you are hit by an attack"),
)
def p14189(c: Cast) -> None:
    """The halving is armed as a one-shot on `DamageRolled`: the interrupt
    answers the hit, and on a `Hit` the blow has not been rolled, so `c.halve`
    there reads an amount of nothing. The save waits for the blow to land."""

    def soften(ev: DamageRolled) -> None:
        if ev.target == c.me:
            c.halve(ev)

    def after(ev: DamageApplied) -> None:
        if ev.target == c.me:
            c.save(on=c.me)

    c.watch(DamageRolled, soften, until=When.EOT, once=True, window=Window.BEFORE)
    c.watch(DamageApplied, after, until=When.EOT, once=True)


@power(
    "p14190",
    level=6,
    cls="x7_867",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.CHARM],
)
def p14190(c: Cast) -> None:
    """One save-ends effect for the printed "save ends both": the opportunity
    bar is held on the caster for the encounter and taken off with the other
    half, rather than giving the victim a second throw."""
    victim = c.target
    if victim is None:
        return
    held = [
        c.no_provoke(from_=victim, on=c.me, until=When.ENCOUNTER),
        c.grants_advantage(on=victim, until=When.SAVE_ENDS, to="me"),
    ]

    def broken(ev: AttackDeclared) -> None:
        if ev.attacker != c.me or ev.target != victim:
            return
        for effect in held:
            c.end_effect(effect)

    c.watch(AttackDeclared, broken, until=When.ENCOUNTER, once=True)


@power(
    "p14191",
    level=10,
    cls="x7_867",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL, Keyword.STANCE],
)
def p14191(c: Cast) -> None:
    """"Any cover or concealment" is both halves now.

    The marker said nothing read a carried concealment back. `query`
    has two readers for it: `concealment_of` is the modifier `c.conceal`
    lays -- its own note says "nothing read one until now" -- and
    `light_concealment` is the badly-lit square, which is a fact about the
    attacker as well as the target and so cannot be the same call. The
    printed rule is that they do not add, and this only asks whether any
    of the three is there at all."""
    c.stance(label=c.ref)
    me = c.me

    def sheltered(ctx: dict[str, Any]) -> bool:
        who = ctx.get("attacker")
        if who is None:
            return False
        return bool(
            query.cover_between(c.world, who, me)
            or query.concealment_of(c.world, me, ctx)
            or query.light_concealment(c.world, who, me)
        )

    for defence in ALL_DEFENCES:
        c.bonus(defence, 4, on=me, until=When.STANCE, kind="power", when=sheltered)
    # "You ignore difficult terrain when shifting" is `when=`: a kind of
    # move, not a sort of going. #598.
    c.ignores_difficult(when="shift", on=me, until=When.STANCE)


# -- x7_915 -----------------------------------------------------------------


@power(
    "p15881",
    level=2,
    cls="x7_915",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.HEALING],
)
def p15881(c: Cast) -> None:
    """The target is the caster's companion, which is asked of the board
    rather than picked -- a companion is not a legal target line."""
    pet = c.companion()
    if pet is not None:
        c.heal(c.surge_value(), on=pet)


@power(
    "p15882",
    level=6,
    cls="x7_915",
    usage=AT_WILL,
    action=MOVE,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=ARCANE,
)
def p15882(c: Cast) -> None:
    """One row, two directions: the card's recall is a second move action,
    which is a second use of this same at-will, so the body toggles.

    The marker said nothing puts a removed creature back. That was read off
    the phrase rather than off the engine: `Condition.REMOVED` is
    `Rules(cannot_act, cannot_move)` and takes nothing off the grid, so
    `c.cure` is the way back and the only thing left to say is where it
    stands. The teleport is `toward=c.me`, which ranks destinations by how
    close they are to me and refuses an occupied one -- "an unoccupied
    square adjacent to you", exactly."""
    pet = c.companion()
    if pet is None:
        return
    if c.is_(Condition.REMOVED, on=pet):
        c.cure(Condition.REMOVED, on=pet)
        c.teleport(max(1, c.distance(pet)), who=pet, toward=c.me)
    else:
        c.condition(Condition.REMOVED, on=pet, until=When.ENCOUNTER)


@power(
    "p15883",
    level=10,
    cls="x7_915",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.POLYMORPH],
)
def p15883(c: Cast) -> None:
    """The companion's aura is copied by radius off the live zone rather than
    guessed.

    The senses are copied too, which the marker said nothing could
    enumerate. `query.sees_in`'s own docstring is the authority on what a
    sense *is* here -- four `Mods` keys, where the value is the printed
    range and 0 means absent -- so `c.total` reads each one off the
    companion and the matching verb lays the same range on the caster.
    `UNLIMITED_SENSE` copies as itself, which is what "no printed range"
    already stores."""
    pet = c.companion()
    shape = c.form(
        modes={"walk": c.speed_of(pet)} if pet is not None else None,
        until=When.ENCOUNTER,
        revert=MINOR,
        label=c.ref,
    )
    if pet is not None:
        radius = 0
        for _zid, zone in c.world.zones.all():
            if zone.owner == pet and zone.aura:
                radius = zone.aura
        if radius:
            c.aura(radius, label=c.ref, on=c.me, until=When.ENCOUNTER)
        for sense, grant in (
            ("darkvision", c.darkvision),
            ("low_light", c.low_light),
            ("blindsight", c.blindsight),
            ("tremorsense", c.tremorsense),
        ):
            reach = c.total(sense, on=pet)
            if reach > 0:
                grant(reach, on=c.me, until=When.ENCOUNTER)

    def other(ev: PowerUsed) -> None:
        if ev.actor == c.me and ev.power != c.ref:
            c.end_effect(shape)

    c.watch(PowerUsed, other, until=When.ENCOUNTER, once=True)


# -- x7_1016 ----------------------------------------------------------------


@power(
    "p16668",
    level=2,
    cls="x7_1016",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you dislike an opposed Perception or Stealth check",
    on=Trigger(SkillCheck, my_check("perception", "stealth"), "one of those checks"),
)
def p16668(c: Cast) -> None:
    """"Use either result" is `keep="best"`.

    "Opposed by another creature" is askable and the marker said it was not:
    `SkillCheck.target` is who the check was made *against* and is None for
    the checks that are about a fact rather than a creature, which is the
    distinction the card draws. An unopposed Perception check is left
    alone, so the encounter use is not spent on one."""
    ev = c.trigger
    if ev is None or getattr(ev, "target", None) is None:
        return
    c.reroll_check(keep="best")


@power(
    "p16669",
    level=6,
    cls="x7_1016",
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you dislike an Insight, Perception, Streetwise or knowledge check",
    on=Trigger(
        SkillCheck,
        my_check("insight", "perception", "streetwise", *KNOWLEDGE),
        "one of those checks",
    ),
)
def p16669(c: Cast) -> None:
    """"As if you had rolled a 20" is arithmetic on the check that is already
    down: the difference goes on as a bonus and the total comes out right."""
    ev = c.trigger
    if isinstance(ev, SkillCheck):
        c.boost_check(20 - ev.natural)


@power(
    "p16670",
    level=10,
    cls="x7_1016",
    usage=DAILY,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
)
def p16670(c: Cast) -> None:
    """Both printed ways out are declared -- taking damage and swinging --
    so the bonus is not simply left standing for the encounter."""
    held = [
        c.bonus(f"skill:{skill}", 5, on=c.me, until=When.ENCOUNTER, kind="power")
        for skill in ("perception", "insight", *KNOWLEDGE)
    ]

    def over() -> None:
        for effect in held:
            c.end_effect(effect)

    def hurt(ev: DamageApplied) -> None:
        if ev.target == c.me:
            over()

    def swung(ev: AttackDeclared) -> None:
        if ev.attacker == c.me:
            over()

    c.watch(DamageApplied, hurt, until=When.ENCOUNTER, once=True)
    c.watch(AttackDeclared, swung, until=When.ENCOUNTER, once=True)
    # Blindsight 1, which is the printed range -- adjacent only, so it is a
    # much narrower sense than the skill bonuses beside it.
    held.append(c.blindsight(1, on=c.me, until=When.ENCOUNTER))
