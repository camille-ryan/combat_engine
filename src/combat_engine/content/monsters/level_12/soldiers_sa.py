"""Monster abilities, level 12: the rest of the soldiers.

`soldiers.py` holds the six stat blocks that were already written; this is
the other forty. Numbers load from `game.db` -- the attack line goes in the
header as `Attack(vs=AC, printed=19)` and the damage line as
`Damage("2d8", 5)`, both exactly as printed, so the engine can take the
level term back out and rescale.

The conventions of the eleven levels below are kept: a row filed under an
action heading that is plainly a trait is `ActionType.NONE`; a stat block
printing no range means melee 1; a printed "Effect (Immediate Reaction)" is
a reaction whatever the action column says; and a helper written for an
earlier level is imported rather than copied.

Seven things this file had to settle.

**A printed "+N while bloodied" is sometimes a trait and sometimes not.**
m1564 prints a bloodied attack bonus on six rows *and* a seventh row that
is exactly that bonus, so the six bodies roll plainly and m1564a6 lays the
one racial +1. Two bonuses of the same kind do not add, so writing it in
both places would have come to +1 either way and looked like a working
aura. m2628, m3283 and m3815 print the same shape with no trait row beside
it, so there it rides on `c.strike(plus=)`.

**A high-crit line is an extra rolled die, not a bigger header.** m1564's
"crit 2d12+32" is the maximised 2d10+12 the engine already produces plus a
rolled 2d12, so it is `c.flat(c.roll("2d12"))` inside the crit branch --
`c.damage` would maximise that too.

**"Shifts 1 square closer" needs a destination.** `_step_toward` at level 1
picks it: of the eight squares one step away, whichever closes the gap most.

**A grab that bars the grabber's other attacks is three holds on one
clock.** m2530a1 and m2724a1 lay the grab, the burn and a `c.forbid`, and
hang the last two off the grab's `on_end`, so letting go releases all of it
in one place rather than three durations drifting apart.

**An "until it attacks me" clock is a watch, not a duration.** m1171a2,
m1178a2 and m3942a1 each print one; each holds its effect to the end of the
encounter and ends it from an `AttackDeclared` watch.

**Four stat blocks print a secondary attack line whose defence the
extraction lost** -- "+17 vs ; 2d6+5 damage." -- and in three of them the
sentence that matters survived intact beside it, so those three play whole.
The two where a line really went missing are named.

**Three briefs print a word that is not a ref.** m1590a2, m2628a3/a4 and
m2351a3 each carry one. None of it is written here -- not in a body, not in
a docstring -- and each is reported instead.

Each stat block in ref order.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_01.brutes_sa import _step_toward
from combat_engine.content.monsters.level_03.lurkers_sa import _restricted_to
from combat_engine.content.monsters.level_03.soldiers_sa import _secondary
from combat_engine.content.monsters.level_08.brutes import (
    SMALL_ENOUGH,
    _crowded,
    _has_hold,
    _holding,
    _is_bloodied,
    _melee_ctx,
)
from combat_engine.content.monsters.level_09.brutes import _volley
from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    EACH_ALLY,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    FREE,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REF,
    STANDARD,
    WILL,
    ActionType,
    AdjacencyLost,
    Attack,
    AttackDeclared,
    AttackRolled,
    Bloodied,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    Damage,
    DamageApplied,
    DamageRolled,
    DamageType,
    Dropped,
    Health,
    Hit,
    Keyword,
    Melee,
    Miss,
    MoveEnd,
    MoveStart,
    PowerUsed,
    Ranged,
    Relation,
    RelationSet,
    Size,
    TempHP,
    TurnEnd,
    TurnStart,
    UpTo,
    Usage,
    When,
    World,
    ZoneExited,
    about_me,
    both,
    by_me,
    by_melee,
    get,
    leaves_me_out,
    power,
    spread,
    targets_me,
)
from combat_engine.engine.components import Stats
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import (
    alive,
    distance_between,
    flanked_by,
    squares,
    team,
)
from combat_engine.engine.triggers import Trigger

#: "Large or smaller", which the push and swallow lines here gate on.
LARGE_OR_SMALLER = (Size.TINY, Size.SMALL, Size.MEDIUM, Size.LARGE)

#: The five types two 2/encounter rows answer with a resistance of their own.
ELEMENTS = (
    DamageType.ACID,
    DamageType.COLD,
    DamageType.FIRE,
    DamageType.LIGHTNING,
    DamageType.THUNDER,
)


# ==========================================================================
# shared helpers
# ==========================================================================


def _weapon_ctx(ctx: dict[str, Any]) -> bool:
    """Is the blow this modifier is being read for a weapon attack?

    Both contexts carry the row's ref and neither carries its keywords, so
    the row is looked up and asked. `_melee_ctx` at level 8 answers the
    reach half of the same question.
    """
    p = get(ctx.get("power") or "")
    return p is not None and Keyword.WEAPON in p.keywords


def _level_of(world: World, eid: int) -> int:
    stats = world.get(eid, Stats)
    return stats.level if stats is not None else 1


def _has_keyword_on(ref: str, word: Keyword) -> bool:
    """Does the row that rolled this blow carry that keyword?"""
    p = get(ref or "")
    return p is not None and word in p.keywords


def _shifting_neighbour(squares_: int, *, marked: bool) -> Any:
    """"An adjacent enemy shifts" -- optionally, one carrying my mark.

    `MoveStart` and not `MoveEnd`: by the time the move is over the enemy
    has gone and the adjacency the printed sentence turns on is already
    false, which is exactly when the row should fire. It is also the
    interrupt window an opportunity attack belongs in.
    """

    def check(world: World, me: int, ev: Any) -> bool:
        who = getattr(ev, "actor", None)
        if who is None or who == me or getattr(ev, "kind_", "") != "shift":
            return False
        if team(world, who) is team(world, me):
            return False
        if marked and not world.relations.holds(Relation.MARKED_BY, me, who):
            return False
        return distance_between(world, me, who) <= squares_

    return check


def _mark_swung_elsewhere(squares_: int = 0) -> Any:
    """Somebody carrying my mark is swinging, within the range the card prints.

    `leaves_me_out` is declared beside this rather than folded in: it reads
    `among`, the whole target list of the one use, which is the half a
    per-target announcement cannot answer on its own.
    """

    def check(world: World, me: int, ev: Any) -> bool:
        foe = getattr(ev, "attacker", None)
        if foe is None or foe == me:
            return False
        if not world.relations.holds(Relation.MARKED_BY, me, foe):
            return False
        return squares_ == 0 or distance_between(world, me, foe) <= squares_

    return check


def _swung_elsewhere_within(squares_: int) -> Any:
    """An enemy inside `squares_` is swinging at something. No mark asked."""

    def check(world: World, me: int, ev: Any) -> bool:
        foe = getattr(ev, "attacker", None)
        if foe is None or foe == me:
            return False
        if team(world, foe) is team(world, me):
            return False
        return distance_between(world, me, foe) <= squares_

    return check


def _struck_while_bloodied(world: World, me: int, ev: Any) -> bool:
    """Bloodied at the moment the blow landed. Paired with `targets_me` and
    `by_melee`, which say the rest of the printed trigger."""
    return _is_bloodied(world, me)


def _triggering_attacker(c: Cast) -> int | None:
    """Whoever swung, off the event being answered.

    The four attack events carry `attacker` and no `actor`, and a row about
    the creature that *swung* cannot read `c.target`: the dispatcher aims a
    single-enemy row at whoever the event was about, which on a `Hit` is the
    creature that was struck.
    """
    foe = getattr(c.trigger, "attacker", None)
    return foe if foe is not None and alive(c.world, foe) else None


def _triggering_mover(c: Cast) -> int | None:
    who = getattr(c.trigger, "actor", None)
    return who if who is not None and alive(c.world, who) else None


def _departed(c: Cast) -> int | None:
    """Whoever stepped out of reach. `AdjacencyLost` is mirrored, so either
    field may be the caster and the other one is the answer."""
    ev = c.trigger
    actor = getattr(ev, "actor", None)
    other = getattr(ev, "other", None)
    if actor is None or other is None:
        return None
    who = other if actor == c.me else actor
    return who if who != c.me and alive(c.world, who) else None


def _free_beside(c: Cast, anchor: int) -> list[Any]:
    """Empty squares next to a creature, for a slide that must end adjacent."""
    mine = set(squares(c.world, anchor))
    near = {sq for sq in spread(mine, 1) if sq not in mine}
    return sorted(sq for sq in near if not c.in_squares([sq]))


def _slide_to_my_side(c: Cast, victim: int, squares_: int) -> None:
    """"Slide the target to a square adjacent to it." The destination is named
    rather than left to the decider, which is free to slide it anywhere."""
    spots = _free_beside(c, c.me)
    if spots:
        c.slide(squares_, on=victim, to=spots[0])
    else:
        c.slide(squares_, on=victim)


def _hit_me_since_my_turn(c: Cast) -> set[int]:
    """Who has hit me since my last turn began.

    Asked *inside* the gate, when the swing happens, and never snapshotted
    when the action is spent: a monster spends a minor action before being
    hit as often as after, and a set taken early is stale the moment
    anybody lands a blow.
    """
    me = c.me
    seen: set[int] = set()
    for past in reversed(c.world.bus.log):
        if isinstance(past, TurnStart) and past.actor == me:
            break
        if isinstance(past, Hit) and past.target == me:
            seen.add(past.attacker)
    return seen


def _tally(c: Cast, refs: tuple[str, ...], victim: int) -> int:
    """Use each row in turn against one creature and count what landed.

    "If both attacks hit the same target" cannot be read off `use`, which
    reports whether a row could be used and not whether it landed, so the
    hits are counted off the bus for as long as this row is swinging.
    `_volley` at level 9 does this for two uses of one row; this takes two
    different ones, which is what a two-weapon line prints.
    """
    me = c.me
    landed: list[int] = []

    def mark(ev: Hit) -> None:
        if ev.attacker == me and ev.power in refs:
            landed.append(ev.target)

    counter = c.watch(Hit, mark, until=When.EOT, on=me, label=f"{c.ref} tally")
    try:
        for ref in refs:
            if not alive(c.world, victim):
                break
            c.use_power(ref, on=victim, spend=False)
    finally:
        c.world.effects.end(counter, "the attacks are done")
    return landed.count(victim)


def _opportunity_rider(c: Cast, apply: Any) -> None:
    """"A creature hit by its opportunity attack also suffers X."

    `Hit` does not declare `opportunity`; `resolve.attack` sets it as a
    plain attribute afterwards, so it is read with `getattr`.
    """
    me = c.me

    def landed(ev: Hit) -> None:
        if ev.attacker == me and getattr(ev, "opportunity", False):
            apply(ev.target)

    c.watch(Hit, landed, until=When.ENCOUNTER, on=me, label=f"{c.ref} opening")


def _rises_unless(c: Cast, hp: int, *types: DamageType) -> None:
    """Down but not out: back up at the top of its next turn, with `hp`.

    `c.revives_unless` implements nothing -- its own docstring says so -- it
    records the fact so the policy stops writing a body at 0 hit points off
    as finished. The watches below are what stands it up. `Dropped` says who
    struck the blow and not what with, so the damage type comes off the
    `DamageApplied` immediately before it; the same flag answers the printed
    "if an attack deals acid or fire damage while it lies there, it does not
    return".
    """
    me = c.me
    c.revives_unless(*types, on=me)
    state = {"burned": False, "down": False, "used": False}

    def took(ev: DamageApplied) -> None:
        if ev.target == me and set(types) & set(ev.types()):
            state["burned"] = True

    def fall(ev: Dropped) -> None:
        if ev.actor != me or state["burned"] or state["used"]:
            return
        state["used"] = True
        state["down"] = True
        state["burned"] = False
        c.condition(Condition.UNCONSCIOUS, until=When.SONT, on=me)

    def wake(ev: TurnStart) -> None:
        if ev.actor != me or not state["down"]:
            return
        state["down"] = False
        if not state["burned"]:
            c.reanimate(on=me, hp=hp)

    c.watch(DamageApplied, took, until=When.ENCOUNTER, on=me, label=f"{c.ref} burns")
    c.watch(Dropped, fall, until=When.ENCOUNTER, on=me, label=f"{c.ref} falls")
    c.watch(TurnStart, wake, until=When.ENCOUNTER, on=me, label=f"{c.ref} rises")


def _element_guard(c: Cast, amount: int) -> None:
    """"Resist N to the triggering damage type, until it uses this again."

    The previous grant is found by its label and ended, which is what
    "until it uses this power again" means and the whole reason the label is
    not `c.ref` alone.
    """
    me = c.me
    dtype = getattr(c.trigger, "dtype", None)
    if dtype is None or dtype not in ELEMENTS:
        return
    tag = f"{c.ref} guard"
    for old in list(c.world.effects.of(me)):
        if old.label == tag:
            c.world.effects.end(old, "a second use replaces it")
    held = c.resist(amount, dtype, until=When.ENCOUNTER, on=me)
    if held is not None:
        held.label = tag


def _took_an_element(world: World, me: int, ev: Any) -> bool:
    return getattr(ev, "target", None) == me and bool(set(ELEMENTS) & set(ev.types()))


# ==========================================================================
# m1073
# ==========================================================================


@power(
    "m1073a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d8", 8),
)
def m1073a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1073a1",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1073a1(c: Cast) -> None:
    """The rider's bonus, laid when somebody gets on rather than at arming.

    A Requirement on a trait is dangerous: `turns.arm_traits_of` arms every
    no-action row through `dsl.use`, so a gate that is false at the start of
    the fight refuses the row once and never arms it again -- and nobody is
    mounted when initiative is rolled. So the question is asked inside a
    `RelationSet` watch, which is the moment a mount acquires a rider, and
    again from the gate on each bonus, so dismounting takes it away.

    `kind="shield"` is the word the card prints and nothing else.
    """
    me = c.me

    def paragon(who: int) -> bool:
        return _level_of(c.world, who) >= 12

    def lift(who: int) -> None:
        def seated(_ctx: dict[str, Any]) -> bool:
            return c.rider() == who

        c.bonus(AC, 1, on=who, kind="shield", until=When.ENCOUNTER, when=seated)
        c.bonus(REF, 1, on=who, kind="shield", until=When.ENCOUNTER, when=seated)

    def mounted(ev: RelationSet) -> None:
        if ev.kind_ is Relation.RIDDEN_BY and ev.source == me and paragon(ev.target):
            lift(ev.target)

    already = c.rider()
    if already is not None and paragon(already):
        lift(already)
    c.watch(RelationSet, mounted, until=When.ENCOUNTER, on=me, label=f"{c.ref} mount")


# ==========================================================================
# m1100
# ==========================================================================


@power(
    "m1100a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=19),
    damage=Damage("1d10", 5),
)
def m1100a0(c: Cast) -> None:
    if c.strike():
        c.hit()


_M1100_LEFT = "an enemy leaves a square adjacent to the m1100"


def _neighbour_left(world: World, me: int, ev: AdjacencyLost) -> bool:
    """An enemy stopped being adjacent.

    `AdjacencyLost` is emitted twice, mirrored, so either field may be the
    caster. It carries `mover` now (#368), so a parting the m1100 caused
    itself by walking off no longer reads the same as one the enemy made --
    which was the one hole in this trigger.
    """
    if me not in (ev.actor, ev.other):
        return False
    foe = ev.other if ev.actor == me else ev.actor
    if getattr(ev, "mover", 0) != foe:
        return False
    return foe != me and team(world, foe) is not team(world, me)


@power(
    "m1100a1",
    level=12,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    trigger=_M1100_LEFT,
    on=Trigger(AdjacencyLost, when=_neighbour_left, text=_M1100_LEFT),
)
def m1100a1(c: Cast) -> None:
    """"Even if the enemy is shifting" is the whole point of the row, and the
    reason it answers `AdjacencyLost` rather than an opportunity window: a
    shift opens no window at all, so there would be nothing to answer.
    `c.basic` swings whatever this creature's basic attack actually is."""
    foe = _departed(c)
    if foe is not None:
        c.basic(on=foe)


_M1100_MISSED = "the m1100 misses with a melee attack"


@power(
    "m1100a2",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    trigger=_M1100_MISSED,
    on=Trigger(Miss, when=both(by_me, by_melee), text=_M1100_MISSED),
)
def m1100a2(c: Cast) -> None:
    """Another swing at the creature it just missed, through the row that
    prints the attack so its damage line stays in one place."""
    victim = getattr(c.trigger, "target", None)
    if victim is not None and alive(c.world, victim):
        c.use_power("m1100a0", on=victim, spend=False)


@power(
    "m1100a3",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1100a3(c: Cast) -> None:
    """Filed as a standard at-will and plainly a trait."""
    _opportunity_rider(c, lambda who: c.prone(on=who))


# ==========================================================================
# m1147
# ==========================================================================


@power(
    "m1147a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(3),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d12", 5),
)
def m1147a0(c: Cast) -> None:
    if c.strike():
        c.hit()


_M1147_BLOODIED = "the m1147 is first bloodied"


@power(
    "m1147a1",
    level=12,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(10),
    target=EACH_ENEMY,
    keywords=[Keyword.HEALING, Keyword.NECROTIC],
    trigger=_M1147_BLOODIED,
    on=Trigger(Bloodied, when=about_me, text=_M1147_BLOODIED),
    dropped=("compendium.attack_defence",),
)
def m1147a1(c: Cast) -> None:
    """The two sentences that survived intact, and the one that did not.

    The card's attack line reads "+17 vs ; 4d8+5" -- the defence is gone, so
    that half cannot be declared and is named rather than guessed. What
    plays is the rest, which rolls nothing: ten necrotic to every enemy in
    the burst and ten hit points back to its undead allies. The healing is a
    flat ten and not a surge; nothing printed spends one.
    """
    victim = c.target
    if victim is not None:
        c.flat(10, dtype=DamageType.NECROTIC, on=victim)
    if not c.first:
        return
    for mate in sorted(c.within(10, side="ally")):
        if c.is_kind("undead", on=mate):
            c.heal(10, on=mate)


@power(
    "m1147a2",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1147a2(c: Cast) -> None:
    """A second opening against whoever it just caught. `c.provoke` is the
    door into the window the engine already has; a controller answers it,
    which is what "it can make another opportunity attack" means."""
    me = c.me
    _opportunity_rider(c, lambda who: c.provoke(me, on=who, why=c.ref))


@power(
    "m1147a3",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1147a3(c: Cast) -> None:
    """Threatening reach, which is what "opportunity attacks against all
    enemies within its reach" is."""
    c.threatens(3, on=c.me, until=When.ENCOUNTER)


# ==========================================================================
# m1154
# ==========================================================================


@power(
    "m1154a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=19),
    damage=Damage("2d6", 7),
)
def m1154a0(c: Cast) -> None:
    """A save-ends mark, which is a relation on a save-ends clock rather than
    `Condition.MARKED`: `c.marked` reads the relation and a condition laid by
    hand would be invisible to it."""
    if c.strike():
        c.hit()
        c.mark(until=When.SAVE_ENDS)


@power(
    "m1154a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=19),
    damage=Damage("2d6", 7),
)
def m1154a1(c: Cast) -> None:
    """"Marked targets only" is a target line no `Target` can say, so the aim
    is narrowed here -- and redirected rather than thrown away where somebody
    else in reach qualifies."""
    victim = _restricted_to(c, 1, c.marked)
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)
    c.condition(
        Condition.IMMOBILIZED,
        until=When.SAVE_ENDS,
        on=victim,
        ongoing=(5, DamageType.UNTYPED),
    )


_M1154_STRUCK = "m1154 is hit by a melee attack"


@power(
    "m1154a2",
    level=12,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("1d10", 5, dtype=DamageType.LIGHTNING),
    trigger=_M1154_STRUCK,
    on=Trigger(Hit, when=both(targets_me, by_melee), text=_M1154_STRUCK),
)
def m1154a2(c: Cast) -> None:
    """The dispatcher aims a single-enemy row at whoever the event was about,
    so `c.target` is the creature that struck it."""
    if c.strike():
        c.hit()
        c.slowed(until=When.EONT)


_M1154_FELLED = "m1154 is reduced to 0 hit points"


@power(
    "m1154a3",
    level=12,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    attack=Attack(vs=WILL, printed=14),
    trigger=_M1154_FELLED,
    on=Trigger(Dropped, when=about_me, text=_M1154_FELLED),
)
def m1154a3(c: Cast) -> None:
    """A death throe, and the curse read as the one mechanic it names.

    "Cursed with domination" is the whole of the printed consequence, so it
    is both halves: a curse, which lasts the fight, and the domination the
    phrase names, on the save-ends clock a condition of that weight carries
    everywhere else in the tree. No damage line at all, so no `c.hit()`.
    """
    if c.strike():
        c.curse()
        c.condition(Condition.DOMINATED, until=When.SAVE_ENDS)


@power(
    "m1154a4",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1154a4(c: Cast) -> None:
    """An ally's burst gets a square wider while it stands near m1154.

    `c.widen_areas` is `c.bonus("blast_size", ...)` with the caster filled
    in, and the bonus is what carries a `when=` -- which this row needs,
    because "within 10 squares" is true at the moment of use and not at the
    moment the trait is armed. The gate reads `ctx["power"]`, which is the
    ref `dsl` measures the area for, so only the named row widens.

    The brief prints m1154a3 at burst 2 and then says this takes it from 1
    to 2, which cannot both be true; the declared area is left as printed
    and the sentence is implemented against it.
    """
    for mate in sorted(c.allies()):
        if mate == c.me:
            continue

        def near(ctx: dict[str, Any], who: int = mate) -> bool:
            return ctx.get("power") == "m1154a3" and c.distance(who) <= 10

        c.bonus("blast_size", 1, on=mate, until=When.ENCOUNTER, when=near)


@power(
    "m1154a5",
    level=12,
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1154a5(c: Cast) -> None:
    """Resistance to a kind of attack rather than a kind of damage, so the
    gate asks the row that rolled the blow whether it is a weapon one."""
    c.resist(10, until=When.EONT, on=c.me, when=_weapon_ctx)


@power(
    "m1154a6",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m1154a6(c: Cast) -> None:
    """Knowing where something is, anywhere on the world, is not a thing a
    board ever asks: there is no distance to a creature that is not in the
    fight. Deliberately inert rather than unwritten."""


# ==========================================================================
# m115830
# ==========================================================================


@power(
    "m115830a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d10", 4),
)
def m115830a0(c: Cast) -> None:
    """The mark is an Effect line, so it lands whether or not the blow did."""
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)
    c.mark(until=When.EONT)


@power(
    "m115830a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(30),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.RANGED, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d10", 9),
)
def m115830a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)


_M115830_SWUNG = (
    "an enemy marked by the m115830 makes an attack that does not include it"
)


@power(
    "m115830a2",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=CloseBlast(5),
    target=NO_TARGET,
    keywords=[Keyword.CHARM, Keyword.POISON, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=15),
    trigger=_M115830_SWUNG,
    on=Trigger(
        AttackDeclared,
        when=both(_mark_swung_elsewhere(), leaves_me_out),
        text=_M115830_SWUNG,
    ),
    dropped=("Damage(dtypes=)",),
)
def m115830a2(c: Cast) -> None:
    """Declared with no target and aimed by hand, because the printed line
    insists the blast include the triggering enemy.

    `c.add_target` adds to the use this one is nested *inside*, not to this
    one, so the only way to guarantee that creature is swung at is to walk
    the list here. A two-type damage line has nowhere to go in the header --
    `Damage` holds one `dtype` -- so it is rolled in the body and named.
    """
    foe = _triggering_attacker(c)
    if foe is None:
        return
    reached = [who for who in sorted(c.enemies()) if c.distance(who) <= 5]
    if foe not in reached:
        reached.append(foe)
    for who in reached:
        if not c.strike(on=who):
            continue
        c.damage(
            "2d6",
            3,
            dtypes=(DamageType.POISON, DamageType.PSYCHIC),
            on=who,
        )
        if who == foe:
            c.stunned(until=When.EOT, on=who)


# ==========================================================================
# m115903
# ==========================================================================


@power(
    "m115903a0",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m115903a0(c: Cast) -> None:
    """Regeneration written out rather than `c.regeneration`, because the
    printed line carries a suspension and nothing holds one: fire or acid
    switches it off for the following turn only. The tick reads a flag the
    damage watch sets and then clears, which is what "its next turn" means.
    """
    me = c.me
    burned = {"next": False}

    def took(ev: DamageApplied) -> None:
        if ev.target != me:
            return
        if {DamageType.FIRE, DamageType.ACID} & set(ev.types()):
            burned["next"] = True

    def tick(ev: TurnStart) -> None:
        if ev.actor != me or ev.ghost:
            return
        off, burned["next"] = burned["next"], False
        health = c.world.get(me, Health)
        if health is None or health.hp < 1:
            return
        if not off:
            c.heal(5, on=me)

    c.watch(DamageApplied, took, until=When.ENCOUNTER, on=me, label=f"{c.ref} burns")
    c.watch(TurnStart, tick, until=When.ENCOUNTER, on=me, label=f"{c.ref} regrows")


@power(
    "m115903a1",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
)
def m115903a1(c: Cast) -> None:
    """Fifteen back at the top of its next turn, unless acid or fire put it
    down -- or reached it while it lay there."""
    _rises_unless(c, 15, DamageType.ACID, DamageType.FIRE)


@power(
    "m115903a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d12", 8),
)
def m115903a2(c: Cast) -> None:
    """"If the attack bloodies the target" is two readings of the same
    creature, before and after, and not a condition the hit can be asked
    about afterwards alone -- something already bloodied must not set it off.
    A second use cannot bloody anything, so the repeat cannot recur.
    """
    victim = c.target
    if victim is None:
        return
    was = c.bloodied(on=victim)
    if c.strike():
        c.hit()
        if not was and c.bloodied(on=victim) and alive(c.world, victim):
            c.use_power("m115903a2", on=victim, spend=False)
    c.mark(until=When.EONT, on=victim)


@power(
    "m115903a3",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(2),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d12", 5),
)
def m115903a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


# ==========================================================================
# m1171
# ==========================================================================


def _mark_until_it_turns_on_me(c: Cast, victim: int, toll: int) -> None:
    """A mark that lasts the fight and bills the victim each round it looks
    elsewhere.

    Three parts: the mark, a `TurnEnd` watch that charges whoever did not
    swing at the caster, and a `Dropped` watch that lifts the whole thing
    when the caster falls -- which is the other half of the printed clock.
    """
    me = c.me
    held = c.mark(until=When.ENCOUNTER, on=victim)
    swung = {"at_me": False}

    def aimed(ev: AttackDeclared) -> None:
        if ev.attacker == victim and ev.target == me:
            swung["at_me"] = True

    def bill(ev: TurnEnd) -> None:
        if ev.actor != victim or ev.ghost:
            return
        if not swung["at_me"]:
            c.flat(toll, on=victim)
        swung["at_me"] = False

    def gone(ev: Dropped) -> None:
        if ev.actor == me and held is not None:
            c.world.effects.end(held, "the marker is down")

    c.watch(AttackDeclared, aimed, until=When.ENCOUNTER, on=me, label=f"{c.ref} watch")
    c.watch(TurnEnd, bill, until=When.ENCOUNTER, on=me, label=f"{c.ref} toll")
    c.watch(Dropped, gone, until=When.ENCOUNTER, on=me, label=f"{c.ref} ends")


@power(
    "m1171a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=19),
    damage=Damage("1d10", 8),
)
def m1171a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1171a1",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("3d8", 8, kind=LIMITED),
    requires_text="the m1171 must be wielding its longsword",
    dropped=("Power.action_alt",),
)
def m1171a1(c: Cast) -> None:
    """The blade is held in the wound, so it cannot swing while it holds.

    "Standard or opportunity action" is two action costs on one card and
    `Power.action` holds one, so the opportunity half is named. The ban runs
    on the same clock as the restraint, which is the printed duration for
    both.
    """
    if not c.strike():
        return
    c.hit()
    c.condition(Condition.RESTRAINED, until=When.EONT)
    c.forbid("m1171a0", on=c.me, until=When.EONT)


@power(
    "m1171a2",
    level=12,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
)
def m1171a2(c: Cast) -> None:
    """No attack roll: the mark is the whole of it."""
    victim = c.target
    if victim is not None:
        _mark_until_it_turns_on_me(c, victim, 6)


@power(
    "m1171a3",
    level=12,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
)
def m1171a3(c: Cast) -> None:
    c.teleport(5)


_M1171_ALLY_HURT = "an ally within 5 squares of the m1171 is damaged"


def _ally_damaged_within(squares_: int) -> Any:
    """Somebody on my side, inside the range, is about to take a blow.

    Declared on `DamageRolled` rather than `DamageApplied`: the printed line
    negates half the damage, and only an interrupt reaches a number that has
    been rolled and not yet dealt.
    """

    def check(world: World, me: int, ev: Any) -> bool:
        who = getattr(ev, "target", None)
        if who is None or who == me:
            return False
        if team(world, who) is not team(world, me):
            return False
        return distance_between(world, me, who) <= squares_

    return check


@power(
    "m1171a4",
    level=12,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=CloseBurst(5),
    target=NO_TARGET,
    trigger=_M1171_ALLY_HURT,
    on=Trigger(DamageRolled, when=_ally_damaged_within(5), text=_M1171_ALLY_HURT),
)
def m1171a4(c: Cast) -> None:
    """Half is negated and the m1171 takes the other half.

    An interrupt, not the reaction the action column names: the printed
    sentence takes points off a blow, and a reaction answers one that has
    already landed. `c.halve` returns what it took off, which is exactly the
    share to move across.
    """
    moved = c.halve(c.trigger)
    if moved > 0:
        c.flat(moved, on=c.me)


# ==========================================================================
# m1178
# ==========================================================================


@power(
    "m1178a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d8", 7),
)
def m1178a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1178a1",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("3d8", 7, kind=LIMITED),
    requires_text="m1178 must be wielding his longsword",
    dropped=("Power.action_alt",),
)
def m1178a1(c: Cast) -> None:
    """As m1171a1: the blade is held in the wound and the opportunity half of
    "standard or opportunity action" has nowhere to be declared."""
    if not c.strike():
        return
    c.hit()
    c.condition(Condition.RESTRAINED, until=When.EONT)
    c.forbid("m1178a0", on=c.me, until=When.EONT)


@power(
    "m1178a2",
    level=12,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
)
def m1178a2(c: Cast) -> None:
    victim = c.target
    if victim is not None:
        _mark_until_it_turns_on_me(c, victim, 4)


@power(
    "m1178a3",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
)
def m1178a3(c: Cast) -> None:
    """A wider critical range, and the healing it pays out.

    `c.bonus("crit_range", 1)` is the lever; the heal hangs off `Hit`, whose
    live `AttackResult` rides on the event as a plain attribute and is where
    "scores a critical hit" is actually answered.
    """
    me = c.me
    c.bonus("crit_range", 1, on=me, until=When.ENCOUNTER)

    def landed(ev: Hit) -> None:
        if ev.attacker != me or not ev.critical:
            return
        c.heal(6, on=me)
        for mate in sorted(c.within(5, side="ally")):
            if mate != me:
                c.heal(6, on=mate)

    c.watch(Hit, landed, until=When.ENCOUNTER, on=me, label=f"{c.ref} crit")


@power(
    "m1178a4",
    level=12,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
)
def m1178a4(c: Cast) -> None:
    c.teleport(5)


_M1178_ALLY_HURT = "an ally within 5 squares of m1178 is damaged"


@power(
    "m1178a5",
    level=12,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=CloseBurst(5),
    target=NO_TARGET,
    trigger=_M1178_ALLY_HURT,
    on=Trigger(DamageRolled, when=_ally_damaged_within(5), text=_M1178_ALLY_HURT),
)
def m1178a5(c: Cast) -> None:
    """As m1171a4: an interrupt, because half the blow is being taken off."""
    moved = c.halve(c.trigger)
    if moved > 0:
        c.flat(moved, on=c.me)


@power(
    "m1178a6",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1178a6(c: Cast) -> None:
    """Extra damage for the whole side, against whoever m1178 is flanking.

    Flanking is computed and not stored, so `query.flanked_by` is the only
    way to ask -- and it is asked inside the gate, where the answer is the
    one at the moment of the blow. `dice=` is how a bonus pays out in dice
    rather than a flat number.
    """
    me = c.me

    def flanked(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        return victim is not None and flanked_by(c.world, victim, me)

    for who in sorted({me, *c.allies()}):
        c.bonus(
            "damage", 0, dice="2d6", on=who, until=When.ENCOUNTER, when=flanked
        )


# ==========================================================================
# m1423
# ==========================================================================


@power(
    "m1423a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d8", 6),
)
def m1423a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(
            Condition.IMMOBILIZED,
            until=When.SAVE_ENDS,
            ongoing=(5, DamageType.UNTYPED),
        )


@power(
    "m1423a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d8", 6),
)
def m1423a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5)


@power(
    "m1423a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=UpTo(2),
)
def m1423a2(c: Cast) -> None:
    """One of each, through the rows that print them so the damage lines stay
    in one place. Armed once for the whole use: the pairing belongs to the
    row and not to each target."""
    if not c.first:
        return
    picked = c.targets[:2]
    c.use_power("m1423a0", on=picked[0], spend=False)
    if len(picked) > 1:
        c.use_power("m1423a1", on=picked[1], spend=False)


_M1423_MISSED = "an enemy misses the m1423 with a melee attack"


@power(
    "m1423a3",
    level=12,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M1423_MISSED,
    on=Trigger(Miss, when=both(targets_me, by_melee), text=_M1423_MISSED),
)
def m1423a3(c: Cast) -> None:
    """Declared with no target and aimed off the trigger, because the row is
    about the creature that swung and not the one that was swung at."""
    foe = _triggering_attacker(c)
    if foe is not None:
        c.use_power("m1423a1", on=foe, spend=False)


@power(
    "m1423a4",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.ACID],
    attack=Attack(vs=FORT, printed=16),
    damage=Damage("2d10", 4, dtype=DamageType.ACID, kind=LIMITED),
)
def m1423a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(2)
        c.condition(
            Condition.IMMOBILIZED,
            until=When.SAVE_ENDS,
            ongoing=(5, DamageType.ACID),
        )


_M1423_BLOODIED = "the m1423 is first bloodied"


@power(
    "m1423a5",
    level=12,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ACID],
    trigger=_M1423_BLOODIED,
    on=Trigger(Bloodied, when=about_me, text=_M1423_BLOODIED),
)
def m1423a5(c: Cast) -> None:
    """The recharge first and then the use, in that order: handing the use
    back before spending it is what "recharges, and uses it immediately"
    says, and `c.use_power` would otherwise find nothing to spend."""
    c.restore_use("m1423a4", on=c.me)
    c.use_power("m1423a4")


@power(
    "m1423a6",
    level=12,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=15),
    dropped=("c.aftereffect()",),
)
def m1423a6(c: Cast) -> None:
    """The stun plays. An Aftereffect fires when the save *succeeds* and the
    condition ends, which is the one moment nothing announces -- `escalate`
    is the opposite half and answers a save that failed."""
    if c.strike():
        c.stunned(until=When.EONT)


# ==========================================================================
# m1564
# ==========================================================================


def _high_crit(c: Cast, dice: str) -> None:
    """The extra die a high-crit line adds, rolled rather than maximised.

    `c.damage` maxes its dice on a critical, so an extra packet rolled
    inside the crit branch would come out maximum too. `c.flat(c.roll(...))`
    is the way to add a real roll.
    """
    if c.crit:
        c.flat(c.roll(dice))


@power(
    "m1564a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d10", 12),
)
def m1564a0(c: Cast) -> None:
    """The printed "+19 while bloodied" is m1564a6's racial +1 showing
    through, so it is not written here as well: two bonuses of the same kind
    do not add and it would have come to +1 either way."""
    if c.strike():
        c.hit()
        _high_crit(c, "2d12")


@power(
    "m1564a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MARTIAL, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d10", 12),
)
def m1564a1(c: Cast) -> None:
    """The vacated square is read before the shove, because afterwards there
    is nothing standing in it to ask about."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    _high_crit(c, "2d12")
    spot = c.there
    if c.size_of(on=victim) in LARGE_OR_SMALLER and c.push(1) and spot is not None:
        c.shift(1, to=spot)


@power(
    "m1564a2",
    level=12,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.MARTIAL, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=20),
    damage=Damage("1d10", 12, kind=LIMITED),
)
def m1564a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        _high_crit(c, "2d12")


@power(
    "m1564a3",
    level=12,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.MARTIAL, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d10", 12, kind=LIMITED),
)
def m1564a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        _high_crit(c, "2d12")


@power(
    "m1564a4",
    level=12,
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(1),
    target=EACH_ALLY,
    keywords=[Keyword.MARTIAL],
)
def m1564a4(c: Cast) -> None:
    """`kind="shield"` is the word the card prints."""
    c.bonus(AC, 2, kind="shield", until=When.ENCOUNTER)
    c.bonus(REF, 2, kind="shield", until=When.ENCOUNTER)


@power(
    "m1564a5",
    level=12,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.COLD],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("2d10", 2, dtype=DamageType.COLD, kind=LIMITED),
)
def m1564a5(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1564a6",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1564a6(c: Cast) -> None:
    """The one place the bloodied +1 is written. `kind="racial"` is the word
    the card prints, and the gate is asked at the moment of the swing rather
    than snapshotted: nobody is bloodied when a trait is armed."""

    def hurt(_ctx: dict[str, Any]) -> bool:
        return c.bloodied(on=c.me)

    c.bonus("attack", 1, on=c.me, kind="racial", until=When.ENCOUNTER, when=hurt)


# ==========================================================================
# m1590
# ==========================================================================


@power(
    "m1590a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d6", 6),
)
def m1590a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1590a1",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=16),
    damage=Damage("2d6", 6, kind=LIMITED),
)
def m1590a1(c: Cast) -> None:
    """The Secondary Attack has no ref of its own, so `_secondary` takes its
    printed total back to a bonus the way the header's `Attack(printed=)`
    does -- `scaling.trim` is the one place that knows how."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    c.pull(1)
    if _secondary(c, 16, FORT, victim):
        c.damage("2d6", 6, on=victim)
        c.push(3, on=victim)


_M1590_SLIPPED = "a bloodied enemy within 2 squares of m1590 moves or shifts"


def _bloodied_foe_moved(world: World, me: int, ev: Any) -> bool:
    """A bloodied enemy nearby is moving. `MoveEnd` carries `kind_`, and both
    a walk and a shift are printed, so the word is not filtered at all."""
    who = getattr(ev, "actor", None)
    if who is None or who == me:
        return False
    if team(world, who) is team(world, me):
        return False
    if not _is_bloodied(world, who):
        return False
    return distance_between(world, me, who) <= 2


@power(
    "m1590a2",
    level=12,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M1590_SLIPPED,
    on=Trigger(MoveEnd, when=_bloodied_foe_moved, text=_M1590_SLIPPED),
)
def m1590a2(c: Cast) -> None:
    """A reaction, as the printed line says, and so `MoveEnd` rather than
    `MoveStart`: it closes the gap after the enemy has opened one, which is
    a square that only exists once the move is over. `_step_toward` picks the
    destination, because `c.shift` would otherwise ask the decider and the
    decider owes the row nothing about direction."""
    who = _triggering_mover(c)
    if who is not None:
        _step_toward(c, who)


@power(
    "m1590a3",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1590a3(c: Cast) -> None:
    c.threatens(2, on=c.me, until=When.ENCOUNTER)


@power(
    "m1590a4",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
)
def m1590a4(c: Cast) -> None:
    """Ten back at the top of its next turn. "As a move action" is not a cost
    the engine owes a body at 0 hit points, and a creature that waits a round
    is one `threat_removed` has already written off."""
    _rises_unless(c, 10, DamageType.ACID, DamageType.FIRE)


# ==========================================================================
# m1617
# ==========================================================================


@power(
    "m1617a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=19),
    damage=Damage("1d8", 6, dtype=DamageType.NECROTIC),
)
def m1617a0(c: Cast) -> None:
    """"Loses a healing surge" is a surge spent for nothing, which is what
    `c.spend_surge` is -- and a monster spends one only where a row says so.
    This row says so about its victim."""
    if not c.strike():
        return
    c.hit()
    c.spend_surge()
    c.immobilized(until=When.SAVE_ENDS)


@power(
    "m1617a1",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING, Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=17),
    damage=Damage("3d6", 5, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m1617a1(c: Cast) -> None:
    """"Affects an immobilized target only" is a target line no `Target` can
    say, so the aim is narrowed here.

    The card spells the healing's beneficiary as another stat block's id; the
    creature every other sentence plainly means is this one, which is how the
    same mistake was read at m695a1.
    """
    victim = _restricted_to(c, 5, lambda who: c.is_(Condition.IMMOBILIZED, on=who))
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)
    c.heal(10, on=c.me)


# ==========================================================================
# m1830
# ==========================================================================


@power(
    "m1830a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=19),
    damage=Damage("2d6", 6),
)
def m1830a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m1830a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=19),
    damage=Damage("2d4", 6),
)
def m1830a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1830a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=FORT, printed=17),
    damage=Damage("2d6", 6),
)
def m1830a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


_M1830_SLIPPED = (
    "an enemy marked by the m1830 shifts out of a square adjacent to it"
)


@power(
    "m1830a3",
    level=12,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    trigger=_M1830_SLIPPED,
    on=Trigger(
        MoveStart,
        when=_shifting_neighbour(1, marked=True),
        text=_M1830_SLIPPED,
    ),
)
def m1830a3(c: Cast) -> None:
    """`MoveStart`, because by `MoveEnd` the enemy has left and the adjacency
    the printed sentence turns on is false precisely when the row should
    fire -- and an interrupt is the window that catches it in the square."""
    who = _triggering_mover(c)
    if who is not None:
        c.use_power("m1830a2", on=who, spend=False)


@power(
    "m1830a4",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1830a4(c: Cast) -> None:
    """`_crowded` leaves the caster out of the tally, which is what "two or
    more of its allies" counts. The melee half is read off the row that
    rolled the blow, because the ref is the one key both contexts carry."""
    me = c.me

    def hemmed(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        return (
            victim is not None
            and _melee_ctx(ctx)
            and _crowded(c, victim, 2)
        )

    c.bonus("damage", 10, on=me, until=When.ENCOUNTER, when=hemmed)


# ==========================================================================
# m1879
# ==========================================================================


@power(
    "m1879a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=19),
    damage=Damage("2d6", 7),
)
def m1879a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized(until=When.SAVE_ENDS)


@power(
    "m1879a1",
    level=12,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=19),
    damage=Damage("1d10", 8),
)
def m1879a1(c: Cast) -> None:
    """A ladder, and "instead" means the old rung comes off first.

    The target line -- dazed, immobilized or stunned -- is one no `Target`
    can say, so the aim is narrowed here. Leaving the old condition standing
    would hand the victim two saving throws against one printed step.
    """

    def held(who: int) -> bool:
        return any(
            c.is_(cond, on=who)
            for cond in (Condition.DAZED, Condition.IMMOBILIZED, Condition.STUNNED)
        )

    victim = _restricted_to(c, 1, held)
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)
    if c.is_(Condition.IMMOBILIZED, on=victim):
        c.cure(Condition.IMMOBILIZED, on=victim)
        c.dazed(until=When.SAVE_ENDS, on=victim)
    elif c.is_(Condition.DAZED, on=victim):
        c.cure(Condition.DAZED, on=victim)
        c.stunned(until=When.SAVE_ENDS, on=victim)


# ==========================================================================
# m2093
# ==========================================================================


@power(
    "m2093a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=19),
    damage=Damage("1d8", 6, dtype=DamageType.PSYCHIC),
)
def m2093a0(c: Cast) -> None:
    """A mark is a relation and a burn is an effect, so "save ends both" is
    two holds here: `c.mark` carries no ongoing damage and a hand-laid
    `Condition.MARKED` would be invisible to `c.marked`."""
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.PSYCHIC)
        c.mark(until=When.SAVE_ENDS)


@power(
    "m2093a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    keywords=[Keyword.PSYCHIC, Keyword.WEAPON],
)
def m2093a1(c: Cast) -> None:
    """Two basic attacks, each picking its own target: the printed line names
    none, and `c.basic` swings whatever this creature's basic actually is."""
    if not c.first:
        return
    picked = c.targets[:2]
    if len(picked) == 1:
        picked = picked * 2
    for victim in picked:
        c.basic(on=victim)


@power(
    "m2093a2",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=19),
    damage=Damage("1d8", 8, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m2093a2(c: Cast) -> None:
    """The burn, and the second burn it lays on whoever stands beside it.

    The neighbour's ten runs on the same clock as the victim's: both are one
    printed "save ends both", so the watch is ended when the burn is.
    """
    victim = _restricted_to(c, 1, c.marked)
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)
    burn = c.ongoing(10, DamageType.PSYCHIC, on=victim)

    def beside(ev: TurnStart) -> None:
        if ev.actor == victim or ev.ghost:
            return
        if team(c.world, ev.actor) is not team(c.world, victim):
            return
        if distance_between(c.world, ev.actor, victim) <= 1:
            c.flat(10, dtype=DamageType.PSYCHIC, on=ev.actor)

    watcher = c.watch(
        TurnStart, beside, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} spread"
    )
    if burn is not None:
        burn.on_end.append(lambda: c.world.effects.end(watcher, "the hold is over"))


@power(
    "m2093a3",
    level=12,
    usage=Usage.RECHARGE,
    recharge=0,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=19),
    damage=Damage("2d8", 8, kind=LIMITED),
)
def m2093a3(c: Cast) -> None:
    """Healing hurts it, and the recharge is the bloodying rather than a die.

    `recharge=0` because nothing is rolled for it; the use is handed back
    from a `Bloodied` watch armed here, which is the only place a recharge
    power's body ever runs. `PowerUsed` is announced before the body, which
    is the right moment: the question is whether the victim is a target of
    the use, and targets are chosen before the body.
    """
    me, victim = c.me, c.target
    if victim is None:
        return

    def recharged(ev: Bloodied) -> None:
        if ev.actor == me:
            c.restore_use(c.ref, on=me)

    c.watch(Bloodied, recharged, until=When.ENCOUNTER, on=me, once=True,
            label=f"{c.ref} recharge")
    if not c.strike():
        return
    c.hit()
    tag = c.effect(f"{c.ref} rot", until=When.SAVE_ENDS, on=victim)

    def healed(ev: PowerUsed) -> None:
        if victim in ev.targets and _has_keyword_on(ev.power, Keyword.HEALING):
            c.flat(10, dtype=DamageType.NECROTIC, on=victim)

    watcher = c.watch(
        PowerUsed, healed, until=When.ENCOUNTER, on=me, label=f"{c.ref} rebuke"
    )
    if tag is not None:
        tag.on_end.append(lambda: c.world.effects.end(watcher, "the hold is over"))


_M2093_ROLLED = "m2093 makes an attack roll"


@power(
    "m2093a4",
    level=12,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M2093_ROLLED,
    on=Trigger(AttackRolled, when=by_me, text=_M2093_ROLLED),
)
def m2093a4(c: Cast) -> None:
    """"It must use the second roll, even if it is lower" is `keep="new"`,
    which is the default and is spelled out because the card insists."""
    c.reroll_attack(keep="new")


@power(
    "m2093a5",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.ignores_difficult(when=)",),
)
def m2093a5(c: Cast) -> None:
    """Rough ground costs it nothing. "When he shifts" is the narrowing, and
    `c.ignores_difficult` carries no gate, so the exemption plays wider than
    printed and the missing parameter is named."""
    c.ignores_difficult(on=c.me, until=When.ENCOUNTER)


# ==========================================================================
# m2338
# ==========================================================================


def _held_fast(c: Cast, who: int) -> bool:
    """"Against an immobilized or restrained creature", the extra-damage gate
    three aberrant stat blocks print."""
    return c.is_(Condition.IMMOBILIZED, on=who) or c.is_(
        Condition.RESTRAINED, on=who
    )


@power(
    "m2338a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=19),
    damage=Damage("1d6", 6),
)
def m2338a0(c: Cast) -> None:
    """"Or 3d6+6 against a held creature" is a second expression, so the
    larger one is rolled in the body: the header holds the printed line and
    `c.hit` can only pay that one out."""
    victim = c.target
    if victim is None or not c.strike():
        return
    if _held_fast(c, victim):
        c.damage("3d6", 6)
    else:
        c.hit()


@power(
    "m2338a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    keywords=[Keyword.POISON],
)
def m2338a1(c: Cast) -> None:
    """Two claws, and the sting if both land on one creature.

    The card also carries a stray attack line whose defence the extraction
    lost; the sentence that matters survived beside it intact, so nothing is
    named. `_volley` counts the hits off the bus, because `use` reports
    whether a row could be used and not whether it landed.
    """
    victim = c.target
    if victim is None or not _volley(c, "m2338a0", victim):
        return
    if _secondary(c, 14, FORT, victim):
        c.immobilized(until=When.SAVE_ENDS, on=victim)


@power(
    "m2338a2",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2338a2(c: Cast) -> None:
    _opportunity_rider(c, lambda who: c.immobilized(until=When.EONT, on=who))


@power(
    "m2338a3",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("spec.monster_ref()",),
)
def m2338a3(c: Cast) -> None:
    """Immunity to one named trap's effect, and the brief gives no ref for
    the trap: the id in the sentence is this creature's own, substituted for
    a second stat block's. There is nothing to be immune *to* until that ref
    arrives, so the whole row waits on it."""


# ==========================================================================
# m2340
# ==========================================================================


@power(
    "m2340a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=19),
    damage=Damage("1d8", 7),
)
def m2340a0(c: Cast) -> None:
    victim = c.target
    if victim is None or not c.strike():
        return
    if c.is_(Condition.IMMOBILIZED, on=victim):
        c.damage("3d8", 7)
    else:
        c.hit()


@power(
    "m2340a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    keywords=[Keyword.POISON],
    dropped=("compendium.attack_defence",),
)
def m2340a1(c: Cast) -> None:
    """The two claws play. This card's Secondary Attack line lost its whole
    attack -- bonus and defence both, where its two siblings kept theirs --
    so the sting lands without a roll, which is more than the card grants,
    and the missing line is named rather than borrowed from a sibling."""
    victim = c.target
    if victim is not None and _volley(c, "m2340a0", victim):
        c.immobilized(until=When.SAVE_ENDS, on=victim)


@power(
    "m2340a2",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2340a2(c: Cast) -> None:
    _opportunity_rider(c, lambda who: c.immobilized(until=When.EONT, on=who))


# ==========================================================================
# m2351
# ==========================================================================


@power(
    "m2351a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=19),
    damage=Damage("1d8", 7),
)
def m2351a0(c: Cast) -> None:
    victim = c.target
    if victim is None or not c.strike():
        return
    if c.is_(Condition.IMMOBILIZED, on=victim):
        c.damage("3d8", 7)
    else:
        c.hit()


@power(
    "m2351a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    keywords=[Keyword.POISON],
)
def m2351a1(c: Cast) -> None:
    """The claws are this creature's own, whatever ref the brief's prose
    names: the sentence is printed on this card and the row it points at is
    the one above."""
    victim = c.target
    if victim is None or not _volley(c, "m2351a0", victim):
        return
    if _secondary(c, 17, FORT, victim):
        c.immobilized(until=When.SAVE_ENDS, on=victim)


@power(
    "m2351a2",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2351a2(c: Cast) -> None:
    _opportunity_rider(c, lambda who: c.immobilized(until=When.EONT, on=who))


@power(
    "m2351a3",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m2351a3(c: Cast) -> None:
    """The printed sentence places this creature in another one's household.
    Nothing on a board asks the question: `c.set_origin` exists for a type
    word an *effect* reads, and no effect reads whose servant something is.
    Deliberately inert rather than unwritten."""


# ==========================================================================
# m2530
# ==========================================================================


def _grab_that_binds(
    c: Cast, victim: int, burn: int, *bars: str
) -> None:
    """A grab, the burn it costs and the rows it takes away, on one clock.

    "Until it escapes" is not a duration the engine holds, so the two riders
    run to the end of the encounter and are ended from the grab's own
    `on_end` -- which is the moment the victim gets out, whatever ends it.
    Three separate durations would drift apart from each other instead.
    """
    hold = c.grab(on=victim)
    if hold is None:
        return
    rot = c.ongoing(burn, on=victim, until=When.ENCOUNTER)
    bans = [c.forbid(ref, on=c.me, until=When.ENCOUNTER) for ref in bars]

    def freed() -> None:
        for held in [rot, *bans]:
            if held is not None:
                c.world.effects.end(held, "the grab is over")

    hold.on_end.append(freed)


@power(
    "m2530a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=19),
    damage=Damage("2d6", 8),
)
def m2530a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2530a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=UpTo(2),
)
def m2530a1(c: Cast) -> None:
    """"The only melee attack it can make is a single claw against the
    grabbed target" is read as the double claw going away: the single one
    stays, which is what the sentence leaves it."""
    victim = c.target
    if victim is not None and _volley(c, "m2530a0", victim):
        _grab_that_binds(c, victim, 10, "m2530a1")


@power(
    "m2530a2",
    level=12,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.GAZE, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=15),
)
def m2530a2(c: Cast) -> None:
    """No damage line at all: the daze is the whole of the hit."""
    if c.strike():
        c.dazed(until=When.SAVE_ENDS)


# ==========================================================================
# m2541
# ==========================================================================


@power(
    "m2541a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=19),
    damage=Damage("1d10", 8),
)
def m2541a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m2541a1",
    level=12,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=19),
    damage=Damage("1d6", 6),
)
def m2541a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(2)


@power(
    "m2541a2",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d10", 6, kind=LIMITED),
    requires_text="m2541 must be wielding the weapon m2541a0 prints",
)
def m2541a2(c: Cast) -> None:
    """A shove, one mark, and whoever the shove delivers it to.

    "He can mark one of the targets he hits" goes to the first of them --
    the row has no other way to choose and leaving every one marked would be
    a sentence the card does not print. The ally's swing is granted after
    the push, so the adjacency is read where the victim ended up.
    """
    victim = c.target
    if victim is None or not c.can_see(victim) or not c.strike():
        return
    c.hit()
    c.push(2)
    if not c.marked(victim) and not any(c.marked(who) for who in c.targets):
        c.mark(until=When.EONT, on=victim)
    mate = next(
        (
            who
            for who in sorted(c.within(1, of=victim, side="ally"))
            if who != c.me
        ),
        None,
    )
    if mate is None:
        return
    if c.grant_attack(mate, on=victim, damage_bonus=3) and c.landed:
        c.prone(on=victim)


_M2541_SLIPPED = "a target marked by m2541 leaves a square adjacent to him"


def _marked_neighbour_left(world: World, me: int, ev: AdjacencyLost) -> bool:
    """`mover` is the creature that actually walked off (#368). Without it
    the m2541 stepping away from its own quarry read as the quarry
    slipping, which is the opposite of the printed sentence."""
    if me not in (ev.actor, ev.other):
        return False
    foe = ev.other if ev.actor == me else ev.actor
    if getattr(ev, "mover", 0) != foe:
        return False
    return foe != me and world.relations.holds(Relation.MARKED_BY, me, foe)


@power(
    "m2541a3",
    level=12,
    usage=AT_WILL,
    action=FREE,
    once_per_round=True,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M2541_SLIPPED,
    on=Trigger(AdjacencyLost, when=_marked_neighbour_left, text=_M2541_SLIPPED),
)
def m2541a3(c: Cast) -> None:
    """Him or one of his allies, so the choice is made rather than assumed."""
    me = c.me
    mates = sorted(mate for mate in c.allies() if mate != me)
    who = c.choose([me, *mates], f"{c.ref}: who shifts") if mates else me
    if who is not None:
        c.shift(2, who=who)


# ==========================================================================
# m2628
# ==========================================================================


def _opportunity_blow(ctx: dict[str, Any]) -> bool:
    """Both contexts carry `opportunity`, so this needs no lookup."""
    return bool(ctx.get("opportunity"))


@power(
    "m2628a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=AC, printed=19),
    damage=Damage("1d8", 6, dtype=DamageType.FIRE),
)
def m2628a0(c: Cast) -> None:
    """No trait row carries this creature's bloodied +1, so it rides on the
    swing. The -4 is a penalty gated on `opportunity`, which both contexts
    carry; it is a second hold beside the burn, because no one call takes a
    modifier and ongoing damage together."""
    if not c.strike(plus=1 if c.bloodied(on=c.me) else 0):
        return
    c.hit()
    c.ongoing(5, DamageType.FIRE)
    c.penalty("attack", 4, until=When.SAVE_ENDS, when=_opportunity_blow)


_M2628_STRUCK = "the m2628 is hit by a melee attack while bloodied"


@power(
    "m2628a1",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=17),
    damage=Damage("1d8", 6, dtype=DamageType.FIRE, kind=LIMITED),
    trigger=_M2628_STRUCK,
    on=Trigger(
        Hit,
        when=both(targets_me, by_melee, _struck_while_bloodied),
        text=_M2628_STRUCK,
    ),
)
def m2628a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2628a2",
    level=12,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(4),
    target=EACH_ENEMY,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=17),
    damage=Damage("3d8", 6, dtype=DamageType.FIRE, kind=LIMITED),
)
def m2628a2(c: Cast) -> None:
    """The bonus is the caster's and the saving throw is the victim's, so the
    clock and the modifier sit on different creatures: a bare tag holds the
    save-ends duration on the target and ends the bonus when it lapses."""
    victim = c.target
    if victim is None or not c.strike(plus=1 if c.bloodied(on=c.me) else 0):
        return
    c.hit()

    def at_him(ctx: dict[str, Any]) -> bool:
        return _opportunity_blow(ctx) and ctx.get("target") == victim

    tag = c.effect(f"{c.ref} opening", until=When.SAVE_ENDS, on=victim)
    boost = c.bonus("attack", 4, on=c.me, until=When.ENCOUNTER, when=at_him)
    if tag is not None and boost is not None:
        tag.on_end.append(lambda: c.world.effects.end(boost, "it saved"))


@power(
    "m2628a3",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2628a3(c: Cast) -> None:
    """Concealment costs it nothing against a bloodied creature.

    `c.ignore_cover` is the one verb and it covers cover as well as
    concealment, so the exemption plays a little wider than the printed
    sentence; the gate narrows it to the victim the card names.
    """

    def wounded(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        return victim is not None and c.bloodied(on=victim)

    c.ignore_cover(on=c.me, until=When.ENCOUNTER, when=wounded)


@power(
    "m2628a4",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2628a4(c: Cast) -> None:
    """"It ceases to be insubstantial and loses its phasing when bloodied" is
    the only sentence on the card that mentions either, so the trait is read
    as granting both and taking them away: a row that only removed them
    would have nothing to remove and would audit silent forever."""
    me = c.me
    thin = c.insubstantial(until=When.ENCOUNTER, on=me)
    through = c.phasing(until=When.ENCOUNTER, on=me)

    def hurt(ev: Bloodied) -> None:
        if ev.actor != me:
            return
        for held in (thin, through):
            if held is not None:
                c.world.effects.end(held, "it is bloodied")

    c.watch(Bloodied, hurt, until=When.ENCOUNTER, on=me, once=True,
            label=f"{c.ref} solidifies")


# ==========================================================================
# m2724
# ==========================================================================


@power(
    "m2724a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d6", 8),
)
def m2724a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2724a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=UpTo(2),
)
def m2724a1(c: Cast) -> None:
    """"It cannot make any other attacks while grabbing" is read as the two
    rows that are not the single claw going away: a creature with nothing at
    all left can never be answered, and the claw is what the sibling card
    spells out as the one thing that stays."""
    victim = c.target
    if victim is not None and _volley(c, "m2724a0", victim):
        _grab_that_binds(c, victim, 10, "m2724a1", "m2724a2")


@power(
    "m2724a2",
    level=12,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.GAZE, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=16),
)
def m2724a2(c: Cast) -> None:
    if c.strike():
        c.slide(5)
        c.dazed(until=When.SAVE_ENDS)


# ==========================================================================
# m3283
# ==========================================================================


def _plus_while_bloodied(c: Cast) -> int:
    return 1 if c.bloodied(on=c.me) else 0


@power(
    "m3283a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=19),
    damage=Damage("2d10", 5, dtype=DamageType.LIGHTNING),
)
def m3283a0(c: Cast) -> None:
    if c.strike(plus=_plus_while_bloodied(c)):
        c.hit()


@power(
    "m3283a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=19),
    damage=Damage("2d6", 5),
)
def m3283a1(c: Cast) -> None:
    if c.strike(plus=_plus_while_bloodied(c)):
        c.hit()


@power(
    "m3283a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=19),
    damage=Damage("2d6", 7),
)
def m3283a2(c: Cast) -> None:
    """Range 10/20: the header carries the short range, which is the only one
    `Range` holds and the one this shoots at without a penalty."""
    if c.strike(plus=_plus_while_bloodied(c)):
        c.hit()


@power(
    "m3283a3",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    requires_text="m3283 must be wielding both of her weapons",
)
def m3283a3(c: Cast) -> None:
    """One swing with each weapon, through the two rows that print them.

    `_tally` counts the hits off the bus for the two refs together, which is
    what "if both attacks hit the same target" needs and what `use` -- which
    reports only whether a row could be used -- cannot say.
    """
    victim = c.target
    if victim is None:
        return
    if _tally(c, ("m3283a0", "m3283a1"), victim) >= 2:
        c.push(2, on=victim)
        c.prone(on=victim)


@power(
    "m3283a4",
    level=12,
    usage=Usage.RECHARGE,
    recharge=0,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    requires_text="m3283 must be wielding both of her weapons",
)
def m3283a4(c: Cast) -> None:
    """Two different targets, one weapon each, and a slide on each hit.

    `recharge=0` because the printed recharge is the bloodying and not a
    die; the use is handed back from a `Bloodied` watch armed here, which is
    the only place this row's body ever runs.
    """
    if not c.first:
        return
    me = c.me

    def recharged(ev: Bloodied) -> None:
        if ev.actor == me:
            c.restore_use(c.ref, on=me)

    c.watch(Bloodied, recharged, until=When.ENCOUNTER, on=me, once=True,
            label=f"{c.ref} recharge")
    for ref, victim in zip(("m3283a0", "m3283a1"), c.targets[:2], strict=False):
        c.use_power(ref, on=victim, spend=False)
        if c.landed:
            c.slide(2, on=victim)


@power(
    "m3283a5",
    level=12,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=17),
    damage=Damage("2d6", 5, dtype=DamageType.LIGHTNING, kind=LIMITED),
)
def m3283a5(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3283a6",
    level=12,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(5),
    target=EACH_ALLY,
)
def m3283a6(c: Cast) -> None:
    """"Targets her and her allies" -- `EACH_ALLY` leaves the caster out, so
    she is handed hers once, on the first pass. "That can hear her" has no
    gate: nothing on a board is deaf to a shout, and `Condition.DEAFENED` is
    read by nothing that would narrow this.

    No type word is printed, so both bonuses are untyped.
    """
    c.bonus("attack", 2, until=When.EONT)
    c.bonus("damage", 2, until=When.EONT)
    if c.first:
        c.bonus("attack", 2, on=c.me, until=When.EONT)
        c.bonus("damage", 2, on=c.me, until=When.EONT)


# ==========================================================================
# m3765
# ==========================================================================


@power(
    "m3765a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=19),
    damage=Damage("2d8", 5),
)
def m3765a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m3765a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=17),
    damage=Damage("2d6", 7, dtype=DamageType.PSYCHIC),
)
def m3765a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m3765a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(2),
    keywords=[Keyword.PSYCHIC],
)
def m3765a2(c: Cast) -> None:
    """Either pairing, chosen rather than assumed: the card offers one of
    each or two of the melee row, and a target list picked before the body
    cannot express a choice between them. The range is the wider of the two,
    so the ranged half can be aimed at all."""
    if not c.first:
        return
    picked = c.targets[:2]
    if len(picked) == 1:
        picked = picked * 2
    second = c.choose(["m3765a0", "m3765a1"], f"{c.ref}: which second attack")
    c.use_power("m3765a0", on=picked[0], spend=False)
    c.use_power(second or "m3765a0", on=picked[1], spend=False)


_M3765_BLOODIED = "the m3765 is first bloodied"


@power(
    "m3765a3",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=15),
    damage=Damage("3d6", 10, dtype=DamageType.PSYCHIC, kind=LIMITED),
    trigger=_M3765_BLOODIED,
    on=Trigger(Bloodied, when=about_me, text=_M3765_BLOODIED),
)
def m3765a3(c: Cast) -> None:
    if c.strike():
        c.hit()


# ==========================================================================
# m3815
# ==========================================================================


@power(
    "m3815a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=19),
    damage=Damage("1d10", 5),
)
def m3815a0(c: Cast) -> None:
    """The +1 is against a bloodied *target*, so it is asked of the victim
    and not of the caster."""
    victim = c.target
    plus = 1 if victim is not None and c.bloodied(on=victim) else 0
    if c.strike(plus=plus):
        c.hit()


@power(
    "m3815a1",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=CloseBurst(1),
    target=ONE_CREATURE,
)
def m3815a1(c: Cast) -> None:
    """No attack roll: the mark is the whole of it, and the printed recharge
    is the mark's own end. `on_end` fires whenever the hold goes -- a save, a
    death, the end of the fight -- which is exactly "when no creature is
    marked by this power"."""
    me = c.me
    held = c.mark(until=When.SAVE_ENDS)
    if held is not None:
        held.on_end.append(lambda: c.restore_use(c.ref, on=me))


_M3815_SHIFTED = "a creature marked by the m3815 shifts"


def _my_mark_shifted(world: World, me: int, ev: Any) -> bool:
    who = getattr(ev, "actor", None)
    if who is None or who == me or getattr(ev, "kind_", "") != "shift":
        return False
    return world.relations.holds(Relation.MARKED_BY, me, who)


@power(
    "m3815a2",
    level=12,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE, Keyword.RADIANT],
    trigger=_M3815_SHIFTED,
    on=Trigger(MoveEnd, when=_my_mark_shifted, text=_M3815_SHIFTED),
    dropped=("Damage(dtypes=)",),
)
def m3815a2(c: Cast) -> None:
    """A free action rather than an interrupt, so `MoveEnd`: the shift is
    allowed to happen and then billed. A blow of two types has nowhere to go
    in the header, so it is rolled in the body and named."""
    who = _triggering_mover(c)
    if who is not None:
        c.damage(
            "2d6", dtypes=(DamageType.FIRE, DamageType.RADIANT), on=who
        )


@power(
    "m3815a3",
    level=12,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3815a3(c: Cast) -> None:
    """The window the card leaves open is asked inside the gate.

    "An enemy that hit it since its last turn" must be read when the swing
    happens: taken when the minor action is spent it is stale the moment
    anybody lands a blow, and returning on an empty set would make the row
    do nothing at all when used *before* being hit -- which is when a
    monster usually spends a minor action.

    "+1 power bonus" is typed; the five extra damage prints no type word and
    so is untyped.
    """
    me = c.me

    def struck_me(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        return victim is not None and victim in _hit_me_since_my_turn(c)

    c.bonus(
        "attack", 1, on=me, kind="power", until=When.EONT, once=True, when=struck_me
    )
    c.bonus("damage", 5, on=me, until=When.EONT, once=True, when=struck_me)


# ==========================================================================
# m3932
# ==========================================================================


@power(
    "m3932a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(3),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=19),
    damage=Damage("2d6", 5),
)
def m3932a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3932a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(3),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=AC, printed=19),
    damage=Damage("1d8", 5),
)
def m3932a1(c: Cast) -> None:
    """"Plus 1d8 lightning" is a second packet and not a second type on the
    first: resistance reads each blow on its own, which is what the printed
    line means by two sentences."""
    if c.strike():
        c.hit()
        c.damage("1d8", dtype=DamageType.LIGHTNING)


@power(
    "m3932a2",
    level=12,
    usage=Usage.RECHARGE,
    recharge=0,
    action=STANDARD,
    reach=Melee(3),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=17),
    damage=Damage("2d6", 5, kind=LIMITED),
    dropped=("c.swallowed()",),
)
def m3932a2(c: Cast) -> None:
    """Inside the creature, written as what the card says it costs.

    Grabbed and restrained is the half the engine has. The rest of being
    swallowed -- line of sight and effect only to the m3932, and nobody
    having either to the victim -- is what `c.swallowed` would be and
    nothing expresses any of it. "Escape ends" is no duration either, so the
    hold is the save-ends one the engine does have, and the release puts the
    victim down beside the m3932 and hands the use back, which is the
    printed recharge.
    """
    me = c.me
    victim = _restricted_to(
        c, 3, lambda who: c.size_of(on=who) in SMALL_ENOUGH
    )
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)
    c.grab(on=victim)
    hold = c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS, on=victim)

    def freed() -> None:
        spots = _free_beside(c, me)
        if spots:
            c.teleport(1, who=victim, to=spots[0])
        c.restore_use(c.ref, on=me)

    if hold is not None:
        hold.on_end.append(freed)


@power(
    "m3932a3",
    level=12,
    usage=AT_WILL,
    action=FREE,
    once_per_round=True,
    reach=PERSONAL,
    target=NO_TARGET,
    requires=_has_hold,
    requires_text="the m3932 must have a creature grabbed",
)
def m3932a3(c: Cast) -> None:
    """Five flat, with no attack rolled, and the only legal target is
    whatever it already has hold of."""
    prey = _holding(c.world, c.me)
    victim = c.choose(prey, f"{c.ref}: which of them") if prey else None
    if victim is not None:
        c.flat(5, on=victim)


@power(
    "m3932a4",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("3d8", 5, dtype=DamageType.LIGHTNING, kind=LIMITED,
                  half_on_miss=True),
)
def m3932a4(c: Cast) -> None:
    """`half_on_miss` is declared data that no line of the engine reads, so
    the Miss branch is written out as well."""
    if c.strike():
        c.hit()
        c.dazed(until=When.EONT)
    else:
        c.hit(half=True)


@power(
    "m3932a5",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("1d8", 5),
)
def m3932a5(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m3932a6",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3932a6(c: Cast) -> None:
    """Three turns a round, at the two counts beside its own.

    `c.extra_turn` splices a slot into the order and the order repeats, so
    the two calls are made once and hold for the fight. The printed counts
    are 30, 20 and 10; the first is its own rolled initiative, which the
    database gives it, so only the other two are spliced -- hand-writing 30
    would be writing down a number the roll owns.

    "It cannot delay or ready" is not a thing the engine offers to begin
    with, and "it can turn a standard into a move" is a budget swap no
    printed verb covers; neither costs the row anything it could have done.
    """
    c.extra_turn(20)
    c.extra_turn(10)


# ==========================================================================
# m3942
# ==========================================================================


@power(
    "m3942a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=19),
    damage=Damage("1d8", 5),
)
def m3942a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m3942a1",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=19),
    damage=Damage("2d8", 5, kind=LIMITED),
)
def m3942a1(c: Cast) -> None:
    """"Ongoing 5 until the target attacks the m3942" is not a duration, so
    the burn runs to the end of the encounter and an `AttackDeclared` watch
    lifts it the moment the victim turns on the caster."""
    me, victim = c.me, c.target
    if victim is None or not c.strike():
        return
    c.hit()
    burn = c.ongoing(5, until=When.ENCOUNTER)
    if burn is None:
        return

    def turned(ev: AttackDeclared) -> None:
        if ev.attacker == victim and ev.target == me:
            c.world.effects.end(burn, "it turned on the m3942")

    c.watch(AttackDeclared, turned, until=When.ENCOUNTER, on=me,
            label=f"{c.ref} burn")


@power(
    "m3942a2",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3942a2(c: Cast) -> None:
    """No type word is printed, so the bonus is untyped."""
    me = c.me

    def flanked(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        return (
            victim is not None and _melee_ctx(ctx) and _crowded(c, victim, 1)
        )

    c.bonus("attack", 2, on=me, until=When.ENCOUNTER, when=flanked)


@power(
    "m3942a3",
    level=12,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
)
def m3942a3(c: Cast) -> None:
    """`against="ongoing"` names which save-ends hold the throw is against;
    without it the save takes whichever it finds first, which may well be a
    daze when the row means the burn."""
    me = c.me
    c.temp_hp(10, on=me)
    c.save(on=me, against="ongoing")
    if c.bloodied(on=me):
        c.heal(10, on=me)


# ==========================================================================
# m4243
# ==========================================================================


@power(
    "m4243a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=19),
    damage=Damage("1d10", 5),
)
def m4243a0(c: Cast) -> None:
    """The mark is an Effect line, so it lands whether or not the blow did."""
    if c.strike():
        c.hit()
    c.mark(until=When.EONT)


@power(
    "m4243a1",
    level=12,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=19),
    damage=Damage("2d10", 5, kind=LIMITED),
)
def m4243a1(c: Cast) -> None:
    """The shift comes first, as printed, and only once for the whole use."""
    if c.first:
        c.shift(1)
    if c.strike():
        c.hit()
        c.immobilized(until=When.SAVE_ENDS)


@power(
    "m4243a2",
    level=12,
    usage=Usage.RECHARGE,
    recharge=0,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=WILL, printed=17),
    damage=Damage("1d8", 5, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m4243a2(c: Cast) -> None:
    """`recharge=0`: the printed recharge is a kill and not a die. `Dropped`
    carries `source`, so "when the m4243 reduces an enemy to 0 hit points"
    is one field and does not have to be re-derived off `DamageApplied`."""
    me = c.me

    def killed(ev: Dropped) -> None:
        if ev.source == me and ev.actor != me:
            c.restore_use(c.ref, on=me)

    c.watch(Dropped, killed, until=When.ENCOUNTER, on=me, label=f"{c.ref} recharge")
    if c.strike():
        c.hit()
        c.pull(5)


_M4243_BLOODIED = "the m4243 is first bloodied"


@power(
    "m4243a3",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=15),
    trigger=_M4243_BLOODIED,
    on=Trigger(Bloodied, when=about_me, text=_M4243_BLOODIED),
)
def m4243a3(c: Cast) -> None:
    """No damage line: the daze is the whole of the hit. "With line of sight
    to the m4243" is asked here, because a blast's target list is chosen on
    distance alone."""
    victim = c.target
    if victim is not None and c.can_see(victim) and c.strike():
        c.dazed(until=When.SAVE_ENDS)


_M4243_SWUNG = (
    "an enemy the m4243 has marked makes an attack that does not include it"
)


@power(
    "m4243a4",
    level=12,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC],
    trigger=_M4243_SWUNG,
    on=Trigger(
        AttackDeclared,
        when=both(_mark_swung_elsewhere(), leaves_me_out),
        text=_M4243_SWUNG,
    ),
)
def m4243a4(c: Cast) -> None:
    """Declared with no target and aimed off the trigger: the row is about
    the creature that *swung* and the dispatcher would point a single-enemy
    row at the one it swung at."""
    foe = _triggering_attacker(c)
    if foe is None:
        return
    c.flat(5, dtype=DamageType.NECROTIC, on=foe)
    for other in sorted(c.within(1, of=foe, side="enemy")):
        if other != foe:
            c.flat(5, dtype=DamageType.NECROTIC, on=other)


# ==========================================================================
# m4251
# ==========================================================================


@power(
    "m4251a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.RADIANT, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=19),
    damage=Damage("1d10", 9, dtype=DamageType.RADIANT),
)
def m4251a0(c: Cast) -> None:
    """An unqualified "the target is marked" runs to the end of the marker's
    next turn, which is what `When.EONT` is."""
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m4251a1",
    level=12,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.RADIANT, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=19),
    damage=Damage("1d10", 9, kind=LIMITED),
)
def m4251a1(c: Cast) -> None:
    """The burn saves off; the brand underneath it does not, and runs to the
    end of the fight as printed.

    "On a turn the target takes radiant damage" is once per turn, so the
    round the last one landed on is remembered -- several radiant blows in
    one turn are one immobilisation, not three.
    """
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    c.ongoing(10, DamageType.RADIANT)
    last = {"round": -1}

    def seared(ev: DamageApplied) -> None:
        if ev.target != victim or DamageType.RADIANT not in ev.types():
            return
        if last["round"] == c.world.round:
            return
        last["round"] = c.world.round
        c.immobilized(until=When.EOTNT, on=victim)

    c.watch(
        DamageApplied, seared, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} brand"
    )


@power(
    "m4251a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
)
def m4251a2(c: Cast) -> None:
    """"Two targets adjacent to him" -- `c.basic` takes `on=` explicitly,
    because `who` names the attacker and the victim would otherwise default
    to whichever target this call is for."""
    if not c.first:
        return
    for victim in c.targets[:2]:
        c.basic(on=victim)


@power(
    "m4251a3",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.RADIANT, Keyword.THUNDER],
    attack=Attack(vs=WILL, printed=17),
    dropped=("Damage(dtypes=)",),
)
def m4251a3(c: Cast) -> None:
    """A blow of two types has nowhere to go in the header -- `Damage` holds
    one `dtype` -- so it is rolled in the body and the gap is named."""
    if not c.strike():
        return
    c.damage("2d10", 3, dtypes=(DamageType.RADIANT, DamageType.THUNDER))
    c.dazed(until=When.SAVE_ENDS)


_M4251_SLIPPED = "a target marked by m4251 shifts"
_M4251_SWUNG = "a target marked by m4251 attacks without including him"


@power(
    "m4251a4",
    level=12,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=f"{_M4251_SLIPPED}, or {_M4251_SWUNG}",
    on=(
        Trigger(
            MoveStart,
            when=_shifting_neighbour(20, marked=True),
            text=_M4251_SLIPPED,
        ),
        Trigger(
            AttackDeclared,
            when=both(_mark_swung_elsewhere(), leaves_me_out),
            text=_M4251_SWUNG,
        ),
    ),
)
def m4251a4(c: Cast) -> None:
    """Both halves of the printed trigger are declared; declaring one would
    look finished and be half a row. The shift half carries no range on this
    card, so the reach given is the board's width rather than adjacency.

    `MoveStart` carries `actor` and `AttackDeclared` carries `attacker`, so
    the creature is read off whichever field the event has.
    """
    who = _triggering_mover(c) or _triggering_attacker(c)
    if who is None:
        return
    c.use_power("m4251a0", on=who, spend=False)
    if c.landed:
        c.prone(on=who)


# ==========================================================================
# m4752
# ==========================================================================


@power(
    "m4752a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(4),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=19),
    damage=Damage("2d8", 5),
)
def m4752a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m4752a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(4),
    target=UpTo(2),
)
def m4752a1(c: Cast) -> None:
    """Two swings, through the row that prints the attack. A single target is
    struck twice, which is the only reading that loses nothing."""
    victim = c.target
    if victim is not None:
        _volley(c, "m4752a0", victim)


@power(
    "m4752a2",
    level=12,
    usage=Usage.RECHARGE,
    recharge=0,
    action=STANDARD,
    reach=CloseBurst(3),
    target=UpTo(3),
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("3d6", 0, kind=LIMITED),
)
def m4752a2(c: Cast) -> None:
    """"One, two, or three enemies" is `UpTo(3)`. `recharge=0`: the printed
    recharge is the bloodying, handed back from a watch armed here."""
    me = c.me
    if c.first:

        def recharged(ev: Bloodied) -> None:
            if ev.actor == me:
                c.restore_use(c.ref, on=me)

        c.watch(Bloodied, recharged, until=When.ENCOUNTER, on=me, once=True,
                label=f"{c.ref} recharge")
    if c.strike():
        c.hit()
        c.condition(
            Condition.SLOWED,
            until=When.SAVE_ENDS,
            ongoing=(10, DamageType.POISON),
        )


@power(
    "m4752a3",
    level=12,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Melee(4),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=17),
)
def m4752a3(c: Cast) -> None:
    """No damage line: the slide and the fall are the whole of the hit."""
    if c.strike():
        c.slide(4)
        c.prone()


_M4752_STRUCK = "an enemy hits the m4752 with a melee attack"


@power(
    "m4752a4",
    level=12,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(4),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=19),
    trigger=_M4752_STRUCK,
    on=Trigger(Hit, when=both(targets_me, by_melee), text=_M4752_STRUCK),
)
def m4752a4(c: Cast) -> None:
    """No damage line: the vulnerability is the whole of the hit, and it runs
    to the end of the fight as printed rather than on a save."""
    if c.strike():
        c.vulnerable(5, DamageType.POISON, until=When.ENCOUNTER)


@power(
    "m4752a5",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4752a5(c: Cast) -> None:
    """No type word is printed, so the bonus is untyped."""
    c.bonus(AC, 4, on=c.me, until=When.ENCOUNTER, when=_opportunity_blow)


# ==========================================================================
# m5124
# ==========================================================================


@power(
    "m5124a0",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5124a0(c: Cast) -> None:
    c.cannot_be_flanked(on=c.me, until=When.ENCOUNTER)


@power(
    "m5124a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(3),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d8", 5),
)
def m5124a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5124a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(3),
    target=UpTo(2),
)
def m5124a2(c: Cast) -> None:
    """Four swings, "no more than twice against a single target", so the
    header takes up to two and each of them is struck twice -- which is the
    only reading under which "hit twice" can ever be true. `_volley` counts
    the hits off the bus for one ref at a time."""
    if not c.first:
        return
    for victim in c.targets[:2]:
        if _volley(c, "m5124a1", victim):
            c.grab(on=victim)


@power(
    "m5124a3",
    level=12,
    usage=AT_WILL,
    action=MOVE,
    reach=Melee(3),
    target=NO_TARGET,
    attack=Attack(vs=FORT, printed=15),
    dropped=("c.overrun(at=)",),
)
def m5124a3(c: Cast) -> None:
    """Under the ground, and under whoever is standing on it.

    `c.overrun` is the only verb that walks *through* occupied squares and
    says who was in them, which is exactly the printed "as it burrows
    beneath the space of a creature". What it cannot do is travel at a mode
    other than the walk speed, so the burrow speed the card names is the
    dropped half; the number itself is read off the creature rather than
    written down. "Avoiding opportunity attacks as it passes" is
    `c.no_provoke`, for the length of the move.
    """
    me = c.me
    c.moving_as("burrow")
    c.no_provoke(on=me, until=When.EOT)
    for who in c.overrun():
        if c.size_of(on=who) not in LARGE_OR_SMALLER:
            continue
        if c.strike(on=who):
            c.prone(on=who)


def _nothing_restrained(world: World, eid: int) -> bool:
    """The printed Requirement, read as a fact about the board rather than a
    standing gate: it is asked when the minor action is offered."""
    from combat_engine.engine.query import is_ as _is

    return not any(
        _is(world, who, Condition.RESTRAINED)
        for who in world.relations.targets(Relation.GRABBED_BY, eid)
    )


@power(
    "m5124a4",
    level=12,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Melee(3),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("2d8", 5),
    requires=_nothing_restrained,
    requires_text="the m5124 must not have a creature restrained",
    dropped=("c.carries()",),
)
def m5124a4(c: Cast) -> None:
    """Dragged inside it, and held there.

    `c.shares_space` is the half that plays: the m5124's squares stop being
    closed to anybody, which is what lets the victim be inside it at all.
    The other half -- the victim actually being carried, so that it travels
    when the m5124 does -- has no verb. A mount carries its rider and
    nothing carries a prisoner, so that is the one clause named; a
    `c.teleport` into the footprint was tried and the mover refuses it, so
    it is not left in the body to fail quietly.

    The damage, the restraint and the burn are exact.
    """
    me = c.me
    held = _holding(c.world, me)
    victim = c.target if c.target in held else next(iter(sorted(held)), None)
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)
    c.shares_space(on=me, until=When.ENCOUNTER)
    c.condition(
        Condition.RESTRAINED,
        until=When.SAVE_ENDS,
        on=victim,
        ongoing=(10, DamageType.UNTYPED),
    )


_M5124_BURNED = "the m5124 takes acid, cold, fire, lightning or thunder damage"


@power(
    "m5124a5",
    level=12,
    usage=ENCOUNTER,
    uses=2,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5124_BURNED,
    on=Trigger(DamageApplied, when=_took_an_element, text=_M5124_BURNED),
)
def m5124a5(c: Cast) -> None:
    """Two uses in the fight, which is `uses=2` and not two rows."""
    _element_guard(c, 15)


# ==========================================================================
# m5168
# ==========================================================================


@power(
    "m5168a0",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5168a0(c: Cast) -> None:
    c.cannot_be_flanked(on=c.me, until=When.ENCOUNTER)


@power(
    "m5168a1",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5168a1(c: Cast) -> None:
    """Full speed, no penalty and no opening given: those are exactly the
    three lines `conditions.RULES[Condition.SQUEEZING]` imposes, so ignoring
    the condition is the whole of the printed sentence rather than a third
    of it."""
    c.ignore_condition(Condition.SQUEEZING, on=c.me, until=When.ENCOUNTER)


@power(
    "m5168a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("3d6", 10, dtype=DamageType.ACID),
)
def m5168a2(c: Cast) -> None:
    """"Until the end of its next turn" is the *target's* clock, which is
    `When.EOTNT` and not `When.EONT`."""
    if c.strike():
        c.hit()
        c.immobilized(until=When.EOTNT)


@power(
    "m5168a3",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(6),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID, Keyword.RANGED],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d6", 10, dtype=DamageType.ACID),
)
def m5168a3(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5168a4",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(2),
    target=EACH_ENEMY,
    keywords=[Keyword.ACID, Keyword.FEAR, Keyword.PSYCHIC],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("2d6", 5, dtype=DamageType.ACID, kind=LIMITED),
)
def m5168a4(c: Cast) -> None:
    """The burn and the penalty are one printed "save ends both" and two
    holds here: no single call takes a modifier and ongoing damage."""
    if not c.strike():
        return
    c.hit()
    c.ongoing(10, DamageType.PSYCHIC)
    c.penalty("attack", 2, until=When.SAVE_ENDS)


@power(
    "m5168a5",
    level=12,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(0),
    target=NO_TARGET,
    keywords=[Keyword.ACID],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("2d6", 5, dtype=DamageType.ACID, kind=LIMITED),
)
def m5168a5(c: Cast) -> None:
    """Through them rather than round them: `c.overrun` is the only verb that
    enters an occupied square and reports who was in it, which is the whole
    of the printed Effect. The reach is melee 0, as printed: the victim is in
    the square the m5168 is standing in by the time it swings.
    """
    c.no_provoke(on=c.me, until=When.EOT)
    for who in c.overrun():
        if c.strike(on=who):
            c.hit(on=who)
            c.dazed(until=When.EOTNT, on=who)


# ==========================================================================
# m5171
# ==========================================================================


@power(
    "m5171a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("3d6", 6),
)
def m5171a0(c: Cast) -> None:
    """The Secondary Attack has no ref of its own, so its printed total goes
    through `_secondary`, which takes the level term back out the way the
    header's `Attack(printed=)` does."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    if _secondary(c, 15, FORT, victim):
        c.immobilized(until=When.EONT, on=victim)


@power(
    "m5171a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("3d8", 8),
)
def m5171a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5171a2",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    attack=Attack(vs=REF, printed=15),
    damage=Damage("2d10", 6, kind=LIMITED),
)
def m5171a2(c: Cast) -> None:
    """A grab that pays out when it is sustained.

    `c.grab` carries no sustain of its own, so a bare hold on the sustain
    clock is laid beside it and `c.on_sustain` hangs the damage off that --
    without the second call the payout half of the printed line goes
    nowhere.
    """
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    c.grab(on=victim)
    hold = c.effect(
        f"{c.ref} grip",
        until=When.SUSTAIN,
        on=victim,
        sustain=MINOR,
    )
    c.on_sustain(hold, lambda: c.damage("1d10", 4, on=victim))


_M5171_SLIPPED = "an enemy adjacent to the m5171 shifts"


@power(
    "m5171a3",
    level=12,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5171_SLIPPED,
    on=Trigger(
        MoveStart,
        when=_shifting_neighbour(1, marked=False),
        text=_M5171_SLIPPED,
    ),
)
def m5171a3(c: Cast) -> None:
    """`MoveStart`: by the time the shift is over the enemy is no longer
    adjacent, which is precisely when the row should fire."""
    c.shift(1)


_M5171_BURNED = "the m5171 takes acid, cold, fire, lightning or thunder damage"


@power(
    "m5171a4",
    level=12,
    usage=ENCOUNTER,
    uses=2,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5171_BURNED,
    on=Trigger(DamageApplied, when=_took_an_element, text=_M5171_BURNED),
)
def m5171a4(c: Cast) -> None:
    _element_guard(c, 10)


# ==========================================================================
# m5502
# ==========================================================================


@power(
    "m5502a0",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
)
def m5502a0(c: Cast) -> None:
    """`ZoneExited` is the only announcement of a creature leaving an aura,
    and it is the moment the toll is printed for. "Any enemy", so the side is
    asked: its own allies walk out for nothing."""
    me = c.me
    ring = c.aura(1, label=f"{c.ref} heat", until=When.ENCOUNTER, on=me)

    def left(ev: ZoneExited) -> None:
        if ev.zone != ring or ev.actor == me:
            return
        if team(c.world, ev.actor) is not team(c.world, me):
            c.flat(10, dtype=DamageType.FIRE, on=ev.actor)

    c.watch(ZoneExited, left, until=When.ENCOUNTER, on=me, label=f"{c.ref} toll")


@power(
    "m5502a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d6", 6),
)
def m5502a1(c: Cast) -> None:
    """"Plus 2d6 fire" is a second packet, so resistance reads each on its
    own -- which is what the card's two sentences mean."""
    if c.strike():
        c.hit()
        c.damage("2d6", dtype=DamageType.FIRE)


_M5502_SWUNG = (
    "an enemy inside the m5502's aura makes an attack that does not include it"
)


@power(
    "m5502a2",
    level=12,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("2d6", 6, dtype=DamageType.FIRE),
    trigger=_M5502_SWUNG,
    on=Trigger(
        AttackDeclared,
        when=both(_swung_elsewhere_within(1), leaves_me_out),
        text=_M5502_SWUNG,
    ),
)
def m5502a2(c: Cast) -> None:
    """"Inside its aura" is read as the aura's radius, because a module-level
    predicate is handed a world and no `Cast` and `c.in_my_aura` needs one.
    The dispatcher aims a single-enemy row at whoever the event was about,
    which on `AttackDeclared` is the creature that swung."""
    foe = _triggering_attacker(c)
    if foe is not None and c.strike(on=foe):
        c.hit(on=foe)


_M5502_BLOODIED = "the m5502 is first bloodied"


@power(
    "m5502a3",
    level=12,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("2d12", 7, dtype=DamageType.POISON, kind=LIMITED,
                  half_on_miss=True),
    trigger=_M5502_BLOODIED,
    on=Trigger(Bloodied, when=about_me, text=_M5502_BLOODIED),
    dropped=("c.no_surges()",),
)
def m5502a3(c: Cast) -> None:
    """Both damage branches play, and both clocks are laid.

    "Cannot spend healing surges" has no verb: `c.no_healing` stops healing
    outright, which is a wider sentence than the card prints, so the
    narrower one is named rather than approximated. `half_on_miss` is
    declared data nothing reads, so the Miss branch is written out.
    """
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)


# ==========================================================================
# m5528
# ==========================================================================


@power(
    "m5528a0",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5528a0(c: Cast) -> None:
    """"Melee attacks and weapon attacks" is either reach or keyword, so the
    gate asks both of the row that rolled the blow. `dice=` is how a bonus
    pays out in dice rather than a flat number."""
    me = c.me

    def wounded(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        if victim is None or not c.bloodied(on=victim):
            return False
        return _melee_ctx(ctx) or _weapon_ctx(ctx)

    c.bonus("damage", 0, dice="3d6", on=me, until=When.ENCOUNTER, when=wounded)


@power(
    "m5528a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d10", 9),
)
def m5528a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5528a2",
    level=12,
    usage=Usage.RECHARGE,
    recharge=0,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("3d6", 7, kind=LIMITED),
)
def m5528a2(c: Cast) -> None:
    """`recharge=0`: the printed recharge is the bloodying, handed back from
    a watch armed on the first pass of the burst."""
    me = c.me
    if c.first:

        def recharged(ev: Bloodied) -> None:
            if ev.actor == me:
                c.restore_use(c.ref, on=me)

        c.watch(Bloodied, recharged, until=When.ENCOUNTER, on=me, once=True,
                label=f"{c.ref} recharge")
    if c.strike():
        c.hit()
        c.condition(
            Condition.SLOWED,
            until=When.SAVE_ENDS,
            ongoing=(10, DamageType.UNTYPED),
        )


@power(
    "m5528a3",
    level=12,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("3d6", 10),
)
def m5528a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized(until=When.EONT)


@power(
    "m5528a4",
    level=12,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5528a4(c: Cast) -> None:
    """The window the card leaves open, asked inside the gate, and closed the
    moment he lands a blow.

    Both bonuses print the word "power", so both are typed. "Until he hits an
    enemy" is a watch rather than a duration: `once=True` on each modifier
    would end them one swing at a time, and the printed sentence ends both
    together on the first hit.
    """
    me = c.me

    def struck_me(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        return victim is not None and victim in _hit_me_since_my_turn(c)

    held = [
        c.bonus("attack", 1, on=me, kind="power", until=When.EONT, when=struck_me),
        c.bonus("damage", 4, on=me, kind="power", until=When.EONT, when=struck_me),
    ]

    def landed(ev: Hit) -> None:
        if ev.attacker != me:
            return
        for one in held:
            if one is not None:
                c.world.effects.end(one, "he hit somebody")

    c.watch(Hit, landed, until=When.EONT, on=me, once=True, label=f"{c.ref} spent")


# ==========================================================================
# m5640
# ==========================================================================

#: m5640a4 swings the row that pulls and the printed line says it does not
#: pull this time, so the row is told. A module-level set rather than an
#: effect: the two uses are nested inside one call stack and nothing has to
#: survive it.
_M5640_NO_PULL: set[int] = set()


@power(
    "m5640a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d4", 15),
)
def m5640a0(c: Cast) -> None:
    """"Can pull" is optional, so the decider is asked -- and m5640a4 uses
    this row with the pull suppressed, which is a printed exception rather
    than a choice."""
    if not c.strike():
        return
    c.hit()
    if c.me not in _M5640_NO_PULL and c.may("pull the target 1 square"):
        c.pull(1)


@power(
    "m5640a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d6", 8),
)
def m5640a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5640a2",
    level=12,
    usage=AT_WILL,
    action=MOVE,
    reach=CloseBurst(1),
    target=NO_TARGET,
)
def m5640a2(c: Cast) -> None:
    """Him and his neighbours, each one square. "The allies must end adjacent
    to him" is not a constraint `c.shift` takes -- the destination is the
    decider's -- and with a one-square step from an adjacent square most
    answers satisfy it anyway."""
    me = c.me
    c.shift(1)
    for mate in sorted(c.within(1, side="ally")):
        if mate != me:
            c.shift(1, who=mate)


@power(
    "m5640a3",
    level=12,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
    requires=_is_bloodied,
    requires_text="m5640 must be bloodied",
)
def m5640a3(c: Cast) -> None:
    """A bonus, a toll on whoever lingers, and a die that may switch both off.

    No type word is printed, so the AC bonus is untyped. The d20 is rolled at
    the top of each of his turns and ends everything on a 9 or lower, which
    is why the two holds are kept together and ended in one place.
    """
    me = c.me
    guard = c.bonus(AC, 2, on=me, until=When.ENCOUNTER)

    def scorch(ev: TurnEnd) -> None:
        if ev.actor == me or ev.ghost:
            return
        if team(c.world, ev.actor) is team(c.world, me):
            return
        if distance_between(c.world, me, ev.actor) <= 1:
            c.flat(10, dtype=DamageType.FIRE, on=ev.actor)

    ring = c.watch(TurnEnd, scorch, until=When.ENCOUNTER, on=me,
                   label=f"{c.ref} heat")

    def gutter(ev: TurnStart) -> None:
        if ev.actor != me or ev.ghost or c.roll("1d20") > 9:
            return
        for held in (guard, ring):
            if held is not None:
                c.world.effects.end(held, "it gutters out")

    c.watch(TurnStart, gutter, until=When.ENCOUNTER, on=me, label=f"{c.ref} fades")


_M5640_SWUNG = (
    "an enemy within 2 squares of m5640 uses an attack power that does not "
    "include him"
)


@power(
    "m5640a4",
    level=12,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5640_SWUNG,
    on=Trigger(
        AttackDeclared,
        when=both(_swung_elsewhere_within(2), leaves_me_out),
        text=_M5640_SWUNG,
    ),
)
def m5640a4(c: Cast) -> None:
    """An interrupt, so the -5 reaches a roll that has not been made yet.

    `once=True` on the penalty is what makes it the *triggering* attack's
    and not the next one's. The pull is suppressed through the flag beside
    m5640a0, which is the printed exception.
    """
    foe = _triggering_attacker(c)
    if foe is None:
        return
    me = c.me
    _M5640_NO_PULL.add(me)
    try:
        c.use_power("m5640a0", on=foe, spend=False)
    finally:
        _M5640_NO_PULL.discard(me)
    if c.landed:
        c.penalty("attack", 5, on=foe, until=When.EOT, once=True)


# ==========================================================================
# m5683
# ==========================================================================


@power(
    "m5683a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d10", 9),
)
def m5683a0(c: Cast) -> None:
    """The mark is an Effect line, so it lands whether or not the blow did."""
    if c.strike():
        c.hit()
    c.mark(until=When.EONT)


@power(
    "m5683a1",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("2d10", 9, kind=LIMITED),
)
def m5683a1(c: Cast) -> None:
    """"If the target is already marked by it" is read before the new mark is
    laid, because afterwards every target is. The slide is an Effect line and
    lands on a miss too."""
    victim = c.target
    if victim is None:
        return
    was = c.marked(victim)
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)
        if was:
            c.slowed(until=When.SAVE_ENDS)
    c.slide(1)


_M5683_SWUNG = (
    "an enemy within 5 squares of the m5683 and marked by it attacks without "
    "including it"
)


@power(
    "m5683a2",
    level=12,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=CloseBurst(5),
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC],
    trigger=_M5683_SWUNG,
    on=Trigger(
        AttackDeclared,
        when=both(_mark_swung_elsewhere(5), leaves_me_out),
        text=_M5683_SWUNG,
    ),
)
def m5683a2(c: Cast) -> None:
    """No attack roll: the ten and the temporary hit points are the whole of
    it. Declared with no target and aimed off the trigger, because the row is
    about the creature that swung."""
    foe = _triggering_attacker(c)
    if foe is None:
        return
    c.flat(10, dtype=DamageType.NECROTIC, on=foe)
    c.temp_hp(10, on=c.me)


_M5683_WARDED = "the m5683 gains temporary hit points"


@power(
    "m5683a3",
    level=12,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(10),
    target=NO_TARGET,
    trigger=_M5683_WARDED,
    on=Trigger(TempHP, when=targets_me, text=_M5683_WARDED),
    dropped=("c.temp_hp(remove=)",),
)
def m5683a3(c: Cast) -> None:
    """The ally's share is given; the caster's is not taken away.

    `TempHP` names its subject `target`, so `targets_me` is the predicate and
    `about_me` -- which reads `actor` and only `actor` -- would be false
    forever. Nothing takes temporary hit points *off* a creature, so the
    "transfers" half is named: the ally gains and the m5683 keeps.
    """
    amount = getattr(c.trigger, "amount", 0)
    if amount < 5:
        return
    share = 10 if amount >= 10 else 5
    mates = sorted(mate for mate in c.within(10, side="ally") if mate != c.me)
    mate = c.choose(mates, f"{c.ref}: who gets it") if mates else None
    if mate is not None:
        c.temp_hp(share, on=mate)


# ==========================================================================
# m6150
# ==========================================================================


@power(
    "m6150a0",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6150a0(c: Cast) -> None:
    """Five more from a blow that had the opening.

    "Did this attack have combat advantage" is read off the `Hit` -- asking
    `has_combat_advantage` again is too late, because a one-shot grant has
    already been spent. The five is laid as a one-shot damage bonus on the
    attacker rather than added to a roll, because `Hit` is announced before
    the damage is rolled and that is the only hook that reaches it.
    """
    me = c.me
    ring = c.aura(1, label=f"{c.ref} aura", until=When.ENCOUNTER, on=me)

    def landed(ev: Hit) -> None:
        victim = ev.target
        if victim == me or ev.attacker == me:
            return
        if team(c.world, victim) is team(c.world, me):
            return
        if victim not in c.world.zones.occupants(ring):
            return
        if c.had_advantage(ev):
            c.bonus("damage", 5, on=ev.attacker, until=When.EOT, once=True)

    c.watch(Hit, landed, until=When.ENCOUNTER, on=me, label=f"{c.ref} opening")


@power(
    "m6150a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d12", 7),
)
def m6150a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6150a2",
    level=12,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=CloseBurst(5),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=15),
)
def m6150a2(c: Cast) -> None:
    """No damage line: the opening is the whole of the hit.

    Two clocks on one sentence -- "until it hits the m6150" and "save ends"
    -- so the hold is the save-ends one and a `Hit` watch lifts it early.
    `to="team"` because the printed line grants the opening at large and the
    m6150's side is who stands to use it.
    """
    me, victim = c.me, c.target
    if victim is None or not c.strike():
        return
    open_ = c.grants_advantage(until=When.SAVE_ENDS, on=victim, to="team")
    if open_ is None:
        return

    def answered(ev: Hit) -> None:
        if ev.attacker == victim and ev.target == me:
            c.world.effects.end(open_, "it struck back")

    c.watch(Hit, answered, until=When.ENCOUNTER, on=me, label=f"{c.ref} answered")


# ==========================================================================
# m6229
# ==========================================================================


@power(
    "m6229a0",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6229a0(c: Cast) -> None:
    """Two ways to fall over, and the one creature the aura spares.

    "Willingly leaves" cannot be told from being shoved out: `ZoneExited`
    carries the zone and the creature and nothing about what moved it, so a
    push out of the aura knocks the victim down where the card would not.
    Noted rather than worked around; every other clause is exact, including
    the exemption for a marked enemy, which is read at the moment it matters
    rather than when the aura goes up.
    """
    me = c.me
    ring = c.aura(1, label=f"{c.ref} aura", until=When.ENCOUNTER, on=me)

    def subject(who: int) -> bool:
        if who == me or team(c.world, who) is team(c.world, me):
            return False
        return not c.marked(who)

    def left(ev: ZoneExited) -> None:
        if ev.zone == ring and subject(ev.actor):
            c.prone(on=ev.actor)

    def swung(ev: AttackDeclared) -> None:
        foe = ev.attacker
        if not subject(foe) or ev.target == me:
            return
        if foe in c.world.zones.occupants(ring):
            c.prone(on=foe)

    c.watch(ZoneExited, left, until=When.ENCOUNTER, on=me, label=f"{c.ref} out")
    c.watch(AttackDeclared, swung, until=When.ENCOUNTER, on=me,
            label=f"{c.ref} aside")


@power(
    "m6229a1",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    narrative=("skill:endurance",),
)
def m6229a1(c: Cast) -> None:
    """The aquatic bonus is exact. Breathing underwater is the other clause,
    and holding a breath is an endurance check nothing on a board ever rolls
    -- a fight is not timed in minutes -- so the bonus has nowhere to go and
    nothing is missing. No type word is printed, so the +2 is untyped."""

    def drowning(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        if victim is None or not c.terrain("aquatic"):
            return False
        return "aquatic" not in c.kinds_of(on=victim)

    c.bonus("attack", 2, on=c.me, until=When.ENCOUNTER, when=drowning)


@power(
    "m6229a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d8", 11),
)
def m6229a2(c: Cast) -> None:
    """"To another square adjacent to it" names the destination, so one is
    picked: left to the decider the slide could end anywhere."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    _slide_to_my_side(c, victim, 2)


@power(
    "m6229a3",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("2d10", 9, kind=LIMITED),
)
def m6229a3(c: Cast) -> None:
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    _slide_to_my_side(c, victim, 3)
    c.prone()


# ==========================================================================
# m6523
# ==========================================================================


@power(
    "m6523a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    requires_text="the m6523 must be in one of the two forms the card names",
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d8", 11),
    dropped=("c.in_form()",),
)
def m6523a0(c: Cast) -> None:
    """The swing and the choice play. The Requirement does not: `c.form`
    assumes a shape and nothing asks which one is being worn, so the gate is
    named. A `requires=` here would be worse than nothing -- on a row armed
    through `dsl.use` a gate that cannot be answered refuses it outright."""
    if not c.strike():
        return
    c.hit()
    if c.choose(["pull", "prone"], f"{c.ref}: which") == "prone":
        c.prone()
    else:
        c.pull(1)


@power(
    "m6523a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    requires_text="the m6523 must be in one of the two forms the card names",
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d8", 11),
)
def m6523a1(c: Cast) -> None:
    """The grab and its burn play. The printed escape DC has nowhere to go: a
    grab is a relation and the engine has no contest to put a number in.
    "Until the grab ends" is not a duration, so the burn runs to the end of
    the encounter and is lifted from the grab's own `on_end`."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    _grab_that_binds(c, victim, 10)


@power(
    "m6523a2",
    level=12,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POLYMORPH],
    dropped=("c.in_form()",),
)
def m6523a2(c: Cast) -> None:
    """A shape with no mechanical content of its own, which is what `c.form`
    holds; nothing can ask afterwards which of the three it is wearing, and
    that is the clause the two rows above wait on as well. "Until it uses
    this again" is the revert `c.form` already carries."""
    c.form(until=When.ENCOUNTER, revert=MINOR, label=f"{c.ref} shape")


_M6523_LOST = "an ally within 5 squares of the m6523 is killed by an enemy"


def _ally_killed_within(squares_: int) -> Any:
    def check(world: World, me: int, ev: Any) -> bool:
        who = getattr(ev, "actor", None)
        if who is None or who == me or not getattr(ev, "dead", False):
            return False
        if team(world, who) is not team(world, me):
            return False
        source = getattr(ev, "source", None)
        if source is None or team(world, source) is team(world, me):
            return False
        return distance_between(world, me, who) <= squares_

    return check


@power(
    "m6523a3",
    level=12,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(5),
    target=NO_TARGET,
    trigger=_M6523_LOST,
    on=Trigger(Dropped, when=_ally_killed_within(5), text=_M6523_LOST),
)
def m6523a3(c: Cast) -> None:
    """`Dropped` carries `dead` and `source`, so "killed by an enemy attack"
    is two fields on one event; `query.enemies` filters out the dead, so the
    killer's side is read off `team` directly.

    "Weapon damage rolls" is the narrowing, asked of the row that rolled the
    blow. No type word is printed, so the +5 is untyped.
    """
    me = c.me
    for mate in sorted({me, *c.within(5, side="ally")}):
        c.bonus("damage", 5, on=mate, until=When.EONT, when=_weapon_ctx)
