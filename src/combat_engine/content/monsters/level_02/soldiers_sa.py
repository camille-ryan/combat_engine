"""Monster abilities, level 2, soldiers.

Twenty stat blocks, 82 rows. Six more level 2 soldiers print no ability at
all -- m300, m3028, m3101, m4862, m5025 and m77 -- so there is nothing to
decorate for them and they are absent rather than skipped.

The conventions are the ones `level_01/soldiers_sa.py` settled and they are
kept unchanged:

* numbers load from `game.db` -- the attack line is written exactly as
  printed (`Attack(vs=AC, printed=8)`) and the damage line goes in the header
  as data, so an MM1 block can be rescaled to MM3 maths later;
* a **trait** is a row that costs no action, has no target, and arms the
  watches that hold it for the rest of the fight. `turns` uses every such row
  once at the start of the encounter, which is what makes a watch armed in
  one of these bodies true from round 1. Several rows here are *filed* as
  standard actions and are plainly traits -- a standing bonus to AC is not
  something a creature spends its turn on -- and those are written
  `action=ActionType.NONE` with the printed usage left alone;
* a printed range of "15/30" takes the **normal** range;
* a printed Requirement naming the creature's own kit -- a shield, a
  scimitar, a free claw -- is not a gate. A monster's equipment is in its
  stat block and does not change mid-fight the way a character's hands do.

A soldier's mark is the thing to get right twice over. Half of these blocks
print it as an **Effect** rather than inside the Hit, so it is laid whether
the swing landed or not; and the rows that punish a marked enemy for looking
elsewhere answer `PowerUsed`, which fires once per use and carries the whole
target list, rather than `AttackDeclared`, which is announced once per target
and would pay out twice for one burst.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    AT_WILL,
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
    SELF,
    STANDARD,
    WILL,
    ActionType,
    Attack,
    Cast,
    CloseBurst,
    Condition,
    Damage,
    DamageType,
    Event,
    Ident,
    Keyword,
    Melee,
    Position,
    Ranged,
    Relation,
    Square,
    Target,
    UpTo,
    Usage,
    When,
    World,
    get,
    power,
)
from combat_engine.engine.events import (
    ActionPointSpent,
    AttackDeclared,
    Bloodied,
    DamageApplied,
    Dropped,
    EffectApplied,
    Hit,
    Miss,
    Moved,
    PowerUsed,
    SurgeSpent,
    TurnStart,
)
from combat_engine.engine.grid import distance as square_distance
from combat_engine.engine.grid import neighbours
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import distance_between, enemies, is_, team
from combat_engine.engine.triggers import Trigger, about_me, by_keyword, by_melee

# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------


def _ref_of(c: Cast, who: int) -> str:
    """Which stat block a creature is, so "another of its kind" can ask."""
    ident = c.world.get(who, Ident)
    return ident.ref if ident else ""


def _is_attack(ref: str) -> bool:
    row = get(ref)
    return row is not None and row.is_attack


def _square_of(c: Cast, who: int | None) -> Square | None:
    pos = c.world.get(who, Position) if who is not None else None
    return pos.square if pos else None


def _step_into_vacated(c: Cast, was: Square | None) -> None:
    """Follow the shove into the square the target just left.

    `c.shift` with a bare distance asks the controller for a destination,
    which on a quiet board walks the other way -- and the printed sentence
    names the square, so it is passed as one. Nothing happens when the shove
    failed and the square is still occupied.
    """
    if was is None:
        return
    if c.world.grid.passable(was) and c.world.grid.occupant(was) is None:
        c.shift(1, to=was)


def _free_square_beside(c: Cast, who: int) -> Square | None:
    """Somewhere empty next to that creature, for a row that names one."""
    here = _square_of(c, who)
    if here is None:
        return None
    for sq in neighbours(here):
        if (
            c.world.grid.inside(sq)
            and c.world.grid.passable(sq)
            and c.world.grid.occupant(sq) is None
        ):
            return sq
    return None


def _armed(c: Cast, label: str) -> bool:
    """Is a watch with this label already standing on the caster?

    An at-will row that arms a lasting rider is used again and again, and a
    second copy of the rider pays out twice for one printed sentence.
    """
    return any(effect.label == label for effect in c.world.effects.of(c.me))


def _braver_shoulder_to_shoulder(c: Cast, bonus: int = 2) -> None:
    """"+2 to AC while at least one ally is adjacent to it."

    Who is standing beside it changes every time anybody moves, so this is a
    gated modifier asked as the defence is looked up rather than a bonus put
    on and taken off by a pair of watches. Untyped: a stat block prints a
    bare "+2 bonus", and `kind=` is only ever the word the card prints.
    """
    me = c.me
    c.bonus(
        AC, bonus, on=me, until=When.ENCOUNTER,
        when=lambda ctx: bool(c.within(1, side="ally")),
    )


def _aquatic_edge(c: Cast) -> None:
    """The half of an underwater creature's trait that has anything to model.

    Breathing underwater costs nothing in a fight -- nothing here drowns --
    so what is left is the bonus, and `c.terrain` is asked inside the gate
    rather than once when the trait is armed, because it answers False in an
    ordinary fight and True in the one the line is for.
    """

    def against_a_landlubber(ctx: dict[str, Any]) -> bool:
        # `.get`, not `[...]`: not every context that asks about an attack
        # bonus carries a target.
        victim = ctx.get("target")
        return (
            c.terrain("aquatic")
            and victim is not None
            and not c.is_kind("aquatic", victim)
        )

    c.bonus(
        "attack", 2, on=c.me, until=When.ENCOUNTER, when=against_a_landlubber
    )
    c.note(f"{c.ref}: it can breathe underwater")


def _crit_drops_it(c: Cast) -> None:
    """"Any critical hit to it drops it to 0 hit points."

    `c.kill` and not `c.flat`, which is what this used to be and what the
    old note here argued against itself about. The card says "reduced to 0
    hit points" with no condition, and damage equal to the creature's
    remaining hit points is absorbed by temporary hit points and stopped
    outright by resist-all -- so the trait failed on exactly the creature
    that had been given either. `c.kill` writes the hit points and then goes
    out through `resolve._check_down`, so the fall still announces itself the
    one way everything else does.

    `critical=True` is passed on because `Dropped` carries it, and the rows
    printing "reduced to 0 hit points **but not by a critical hit**" are the
    mirror of this one -- a fall that lied about its cause would arm them.
    """
    me, ref = c.me, c.ref

    def shattered(ev: Hit) -> None:
        if ev.target == me and ev.critical:
            c.kill(on=me, critical=True)

    c.watch(Hit, shattered, until=When.ENCOUNTER, on=me, label=f"{ref} brittle")


def _save_ends_on_me(world: World, me: int, ev: Event) -> bool:
    """`EffectApplied` rather than `ConditionApplied`: the printed line says
    "an effect a save can end", and an effect carrying nothing but ongoing
    damage announces no condition at all. Its subject is named `target`, so
    `about_me` would be false forever here."""
    return getattr(ev, "target", None) == me and bool(getattr(ev, "save_ends", False))


def _marked_foe_looks_away(world: World, me: int, ev: Any) -> bool:
    """"An enemy marked by it makes an attack that does not include it."""
    actor = getattr(ev, "actor", None)
    if actor is None or actor == me:
        return False
    if not world.relations.holds(Relation.MARKED_BY, me, actor):
        return False
    if not _is_attack(getattr(ev, "power", "")):
        return False
    return me not in getattr(ev, "targets", ())


def _recharge_when_bloodied(c: Cast) -> None:
    """Put this row back up when the printed line says so, not only on a die.

    The database files a plain 6+ for "Recharge when first bloodied". The
    number stays in the header, because that is what `actions.recharge` rolls
    and what the card shows; this is the printed sentence on top of it, and
    the two only ever agree to make the row available sooner.
    """
    me, ref = c.me, c.ref

    def bled(ev: Any) -> None:
        if getattr(ev, "actor", None) == me:
            c.restore_use(ref, on=me)

    from combat_engine.engine.events import Bloodied

    c.watch(
        Bloodied, bled, until=When.ENCOUNTER, on=me, once=True,
        label=f"{ref} recharge",
    )


def _prone_enemy_in_reach(world: World, eid: int) -> bool:
    """The printed target line "an adjacent prone creature", as an entry gate.

    `Target` filters on side, count, size and what is in hand, and on nothing
    a creature is *suffering*, so the narrowing cannot live there. A body that
    looks and returns is a standard action the policy spends on nothing, and
    `dsl.usable` is handed `(world, eid)` and the caster is all it knows -- so
    the question has to be asked from this end as well as in the body.
    """
    return any(
        distance_between(world, eid, foe) <= 1 and is_(world, foe, Condition.PRONE)
        for foe in enemies(world, eid)
    )


_HELPLESS = (Condition.IMMOBILIZED, Condition.STUNNED, Condition.UNCONSCIOUS)


def _holding_nobody(world: World, eid: int) -> bool:
    return not world.relations.targets(Relation.GRABBED_BY, eid)


def _holding_somebody(world: World, eid: int) -> bool:
    return bool(world.relations.targets(Relation.GRABBED_BY, eid))


# --------------------------------------------------------------------------
# m1107
# --------------------------------------------------------------------------


@power(
    "m1107a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d10", 4),
    dropped=("etl.monster.forced_distance()",),
)
def m1107a0(c: Cast) -> None:
    """The pull has no distance in the compendium -- "and the target is
    pulled", with the number gone -- so it is left out rather than guessed at.
    Everything else plays: the branch is read before the swing, because the
    reach is 2 and the extra die is for a creature that was *already* next to
    it, which pulling would have made true of everybody.
    """
    was_adjacent = c.adjacent(c.target)
    if c.strike():
        c.hit()
        if was_adjacent:
            c.damage("1d6")


@power(
    "m1107a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=6),
    damage=Damage("1d6", 4),
)
def m1107a1(c: Cast) -> None:
    """The brief printed no range for this one; the card's own reach column
    says 2, which is what `cards.py` compares against."""
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m1107a2",
    level=2,
    usage=Usage.RECHARGE,
    recharge=5,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 4, kind=LIMITED),
)
def m1107a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1107a3",
    level=2,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(1),
    target=Target(
        "enemy", 1,
        label="One adjacent prone creature",
        conditions=frozenset({Condition.PRONE}),
    ),
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d6", 4),
)
def m1107a3(c: Cast) -> None:
    """"An adjacent prone target" is the target line itself now. The entry gate
    and the body's check both came out: an empty pool keeps the row off the
    menu, from one place rather than three. The reach line is what makes it
    adjacent."""
    if c.strike():
        c.hit()


_M1107_HELD = "it suffers an effect that a save can end"


@power(
    "m1107a4",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M1107_HELD,
    on=Trigger(EffectApplied, _save_ends_on_me, _M1107_HELD),
)
def m1107a4(c: Cast) -> None:
    """"Against the triggering effect" is what `against=` picks: without it
    `c.save` takes whichever save-ends hold it finds first, which on a
    creature already burning is the wrong one. The label is read off the
    trigger rather than guessed."""
    label = getattr(c.trigger, "label", "")
    c.save(on=c.me, against=label)


@power(
    "m1107a5",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1107a5(c: Cast) -> None:
    """Filed as a standard action and plainly a trait."""
    _braver_shoulder_to_shoulder(c)


# --------------------------------------------------------------------------
# m1112
# --------------------------------------------------------------------------


@power(
    "m1112a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 2),
)
def m1112a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1112a1",
    level=2,
    usage=Usage.RECHARGE,
    recharge=5,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d8", 5, kind=LIMITED),
)
def m1112a1(c: Cast) -> None:
    """The mark is inside the Hit here, so a miss lays none."""
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m1112a2",
    level=2,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m1112a2(c: Cast) -> None:
    c.teleport(5)


# --------------------------------------------------------------------------
# m1654
# --------------------------------------------------------------------------


@power(
    "m1654a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d8", 3),
)
def m1654a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1654a1",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1654a1(c: Cast) -> None:
    """A guard's bonus, measured from the thing it is guarding.

    The printed sentence names the creature twice -- "within 5 squares of the
    m1654" -- because the compendium has collapsed the guarded thing's name
    into the guard's own. What it means is its master, which is the relation
    `c.master` reads, and the distance is asked as each defence is looked up
    rather than once: the creature is expected to leave the ring and come
    back, which is the rest of the paragraph.

    That rest -- how far it chases and when it gives up -- is a choice, not a
    rule, and belongs to the policy rather than to this row.
    """
    me = c.me

    def near_its_charge(ctx: dict[str, Any]) -> bool:
        keeper = c.master()
        return keeper is not None and distance_between(c.world, me, keeper) <= 5

    for defence in (AC, FORT, REF, WILL):
        c.bonus(defence, 1, on=me, until=When.ENCOUNTER, when=near_its_charge)


@power(
    "m1654a2",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1654a2(c: Cast) -> None:
    """"Before or after the attack" -- after is taken, which is the half that
    needs no window of its own: `AttackDeclared` carries `opportunity` as a
    plain attribute and the default `Window.AFTER` lands once the swing has
    resolved."""
    me, ref = c.me, c.ref

    def sidestep(ev: AttackDeclared) -> None:
        if ev.attacker != me or not getattr(ev, "opportunity", False):
            return
        c.shift(1, who=me)

    c.watch(
        AttackDeclared, sidestep, until=When.ENCOUNTER, on=me,
        label=f"{ref} footwork",
    )


# --------------------------------------------------------------------------
# m1656
# --------------------------------------------------------------------------


@power(
    "m1656a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 3),
)
def m1656a0(c: Cast) -> None:
    """Whether the target was slowed is read *before* the swing, or this row
    pays its own rider: the slow it lays would make the branch true for
    everybody it ever hit. The base damage is untyped, as printed -- only the
    extra die is cold."""
    was_slowed = c.is_(Condition.SLOWED)
    if c.strike():
        c.hit()
        if was_slowed:
            c.damage("1d6", dtype=DamageType.COLD)
        c.slowed(until=When.SAVE_ENDS)


@power(
    "m1656a1",
    level=2,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD],
    attack=Attack(vs=FORT, printed=7),
)
def m1656a1(c: Cast) -> None:
    """No damage line at all, which is the whole of the printed Hit."""
    if c.strike():
        c.immobilized(until=When.SAVE_ENDS)


# --------------------------------------------------------------------------
# m3533
# --------------------------------------------------------------------------


@power(
    "m3533a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d8", 5),
)
def m3533a0(c: Cast) -> None:
    """The printed critical line is what `c.damage` already does with maxed
    dice plus the weapon's own rider, so there is nothing to write for it."""
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


_M3533_HELD = "it suffers an effect that a save can end"


@power(
    "m3533a1",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M3533_HELD,
    on=Trigger(EffectApplied, _save_ends_on_me, _M3533_HELD),
)
def m3533a1(c: Cast) -> None:
    label = getattr(c.trigger, "label", "")
    c.save(on=c.me, against=label)


@power(
    "m3533a2",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3533a2(c: Cast) -> None:
    """Filed as a standard encounter power and plainly a trait: the usage is
    left as printed, and a trait is armed once at the start of the fight, so
    one use is all it ever takes."""
    _braver_shoulder_to_shoulder(c)


@power(
    "m3533a3",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
)
def m3533a3(c: Cast) -> None:
    """It gets back up unless radiant put it down, and only once.

    `Dropped` says who struck the blow and not what with, so the damage type
    is taken off the `DamageApplied` immediately before it -- which is the
    blow that crossed the line, and the only one that can be. The rise is
    taken inside the same window rather than deferred to its next turn as a
    move action: nothing in the engine owes a corpse an action, and a body
    that waits a round is a body `threat_removed` has already written off.

    `c.revives_unless` is the declaration that makes the policy stop treating
    it as finished; the watch below is what actually stands it up. The second
    clause -- destroyed if it takes a critical hit afterwards, or on the
    second trigger -- needs nothing of its own: `used` refuses a second rise,
    and m3533a4 turns any critical into a drop.
    """
    me = c.me
    c.revives_unless(DamageType.RADIANT, on=me)
    last: dict[str, bool] = {"radiant": False}
    risen: dict[str, int] = {"count": 0}

    def took(ev: DamageApplied) -> None:
        if ev.target == me:
            last["radiant"] = DamageType.RADIANT in ev.types()

    def rise(ev: Dropped) -> None:
        if ev.actor != me or last["radiant"] or risen["count"]:
            return
        risen["count"] += 1
        c.reanimate(on=me, hp=5)

    c.watch(DamageApplied, took, until=When.ENCOUNTER, on=me, label=f"{c.ref} last blow")
    c.watch(Dropped, rise, until=When.ENCOUNTER, on=me, label=f"{c.ref} rises")


@power(
    "m3533a4",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3533a4(c: Cast) -> None:
    _crit_drops_it(c)


# --------------------------------------------------------------------------
# m3537
# --------------------------------------------------------------------------


@power(
    "m3537a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d4", 3),
)
def m3537a0(c: Cast) -> None:
    """The free follow-up is the other row, used at this row's cost."""
    victim = c.target
    if c.strike():
        c.hit()
        if c.crit and victim is not None:
            c.use_power("m3537a1", on=victim, spend=False)


@power(
    "m3537a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=7),
    damage=Damage("1d4", 3),
)
def m3537a1(c: Cast) -> None:
    """"Any escape attempt must target its Fortitude rather than its Reflex"
    is `grab_vs_fort`, which `escape.attempt` reads off the *grabber*: a
    positive value there measures every escape from this creature against
    Fortitude, which is the printed sentence exactly."""
    if c.strike():
        c.hit()
        c.grab()
        c.bonus("grab_vs_fort", 1, on=c.me, until=When.ENCOUNTER)


@power(
    "m3537a2",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=Target(
        "enemy", 1,
        label="One immobilized, stunned or unconscious creature",
        conditions=frozenset(_HELPLESS),
    ),
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d6", 3),
)
def m3537a2(c: Cast) -> None:
    """A target line narrowed by what the creature is suffering, which is now a
    field: the entry gate and the body's re-check both came out, because an
    empty pool is the same refusal from one place instead of three."""
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)


@power(
    "m3537a3",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3537a3(c: Cast) -> None:
    _crit_drops_it(c)


# --------------------------------------------------------------------------
# m3771
# --------------------------------------------------------------------------


@power(
    "m3771a0",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3771a0(c: Cast) -> None:
    _aquatic_edge(c)


@power(
    "m3771a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=7),
    damage=Damage("2d4", 4),
)
def m3771a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3771a2",
    level=2,
    usage=Usage.RECHARGE,
    recharge=0,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING],
    attack=Attack(vs=FORT, printed=5),
    damage=Damage("2d4", 4, kind=LIMITED),
)
def m3771a2(c: Cast) -> None:
    """The printed recharge is a condition, not a die, and it is exact: the
    row comes back at the start of any turn on which it is holding nobody.
    The 6+ stays in the header because that is what `actions.recharge` rolls
    and what the card shows; the two only ever agree to offer it sooner.

    Sustain Standard has a payout as well as a clock, so `c.on_sustain`
    carries it -- without that half the squeeze does nothing and the vine
    heals nothing, and the row looks finished. The escape DC is the dropped
    clause: `c.grab` takes no number.
    """
    me, ref = c.me, c.ref
    victim = c.target
    if not c.strike():
        return
    c.hit()
    c.grab(dc=13)
    if victim is None:
        return
    squeeze = c.effect(f"{ref} squeeze", until=When.SUSTAIN, on=victim, sustain=STANDARD)

    def crush() -> None:
        c.damage("2d8", 4, on=victim)
        c.heal(5, on=me)

    c.on_sustain(squeeze, crush)

    if _armed(c, f"{ref} recharge"):
        return

    def loosened(ev: TurnStart) -> None:
        if ev.actor == me and not c.grabbing(of=me):
            c.restore_use(ref, on=me)

    c.watch(
        TurnStart, loosened, until=When.ENCOUNTER, on=me, label=f"{ref} recharge"
    )


@power(
    "m3771a3",
    level=2,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3771a3(c: Cast) -> None:
    """The step comes first and the drag after, which is the printed order and
    the reason the pull is only one square: by then the grabbed creature is
    two away and one square brings it back alongside."""
    c.shift(1)
    for held in c.grabbing(of=c.me):
        c.pull(1, on=held)


# --------------------------------------------------------------------------
# m4114
# --------------------------------------------------------------------------


@power(
    "m4114a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 3),
)
def m4114a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(1)


@power(
    "m4114a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d6", 3),
)
def m4114a1(c: Cast) -> None:
    """"10/20" takes the normal range."""
    if c.strike():
        c.hit()


@power(
    "m4114a2",
    level=2,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=7),
    damage=Damage("1d8", 4, kind=LIMITED),
)
def m4114a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


_M4114_MISSED = "it is missed by a melee attack"


def _missed_me_in_melee(world: World, me: int, ev: Event) -> bool:
    return getattr(ev, "target", None) == me and by_melee(world, me, ev)


@power(
    "m4114a3",
    level=2,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M4114_MISSED,
    on=Trigger(Miss, _missed_me_in_melee, _M4114_MISSED),
)
def m4114a3(c: Cast) -> None:
    c.shift(1)


# --------------------------------------------------------------------------
# m4197
# --------------------------------------------------------------------------


@power(
    "m4197a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 5),
)
def m4197a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m4197a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    charges=True,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d8", 5),
)
def m4197a1(c: Cast) -> None:
    """A row whose printed Effect *is* the charge.

    `charges=True` is what makes `dsl.usable` measure the reach after the
    run; without it the row is refused whenever the target is further off
    than a sword, which is every situation a charge is for. `c.run_at`
    rather than `c.charge_at(c.ref)`: that one would spend this very row
    again to make the swing, and the in-flight guard refuses it. The cost is
    that the attack is not flagged as a charge when the row is used directly
    -- `c.as_basic(window="charge")` is filed so the engine's own charge
    action offers it too, and that path does set the flag.
    """
    if c.first:
        c.as_basic(c.ref, window="charge", until=When.ENCOUNTER)
    victim = c.target
    if victim is None:
        return
    c.ignores_difficult(on=c.me, until=When.EOT)
    if not c.adjacent(victim):
        c.run_at(victim)
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


_M4197_FELLED = "it drops to 0 hit points"


@power(
    "m4197a2",
    level=2,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POLYMORPH],
    attack=Attack(vs=REF, printed=7),
    trigger=_M4197_FELLED,
    on=Trigger(Dropped, lambda w, me, ev: getattr(ev, "actor", None) == me, _M4197_FELLED),
    dropped=("Dropped.power",),
)
def m4197a2(c: Cast) -> None:
    """It turns to stone where it fell, and the stone lasts the fight.

    "If it was reduced to 0 by a melee attack using a weapon" cannot be
    asked: `Dropped` carries who struck the blow and not what struck it. So
    the narrowing taken instead is adjacency -- whoever felled it and is
    standing next to the statue -- and the weapon half is the dropped clause.

    The weapon being stuck in the stone needs nothing of its own: `c.disarm`
    takes it out of the wielder's hands, and picking it back up costs an
    action whether it is in a statue or on the floor.
    """
    here = _square_of(c, c.me)
    if here is not None:
        statue = c.zone({here}, until=When.ENCOUNTER, difficult=True, label=f"{c.ref} statue")
        c.cover_in(statue, side="any")
    killer = getattr(c.trigger, "source", None)
    if killer is None or not c.adjacent(killer):
        return
    if c.strike(on=killer):
        c.disarm(on=killer)


# --------------------------------------------------------------------------
# m4593
# --------------------------------------------------------------------------


@power(
    "m4593a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 4),
)
def m4593a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4593a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 4),
)
def m4593a1(c: Cast) -> None:
    """"She can use this in place of a melee basic attack when charging or
    using m4593a4" is `c.as_basic`, filed with no window so both grants pick
    it up. This creature has no trait row to arm it from, so it is filed on
    first use -- which makes the substitution available from the second use
    onward rather than the first, the one way this row differs from its
    card."""
    if c.first:
        c.as_basic(c.ref, until=When.ENCOUNTER)
    if c.strike():
        c.hit()
        c.immobilized(until=When.EONT)


@power(
    "m4593a2",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(3),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.LIGHTNING],
    attack=Attack(vs=FORT, printed=7),
    damage=Damage("1d6", 6),
)
def m4593a2(c: Cast) -> None:
    """`c.pull` already drags the target toward the caster, which is what "to
    a square adjacent to her" names; three squares is enough to close the
    whole printed range."""
    if c.strike():
        c.hit()
        c.pull(3)


@power(
    "m4593a3",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.IMPLEMENT, Keyword.FORCE],
    attack=Attack(vs=REF, printed=7),
    damage=Damage("1d6", 6, dtype=DamageType.FORCE),
)
def m4593a3(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4593a4",
    level=2,
    usage=AT_WILL,
    action=MINOR,
    reach=CloseBurst(2),
    target=ONE_CREATURE,
    keywords=[Keyword.TELEPORTATION],
)
def m4593a4(c: Cast) -> None:
    """One mark at a time, and a reaction that costs what a reaction costs.

    "Until she uses this power on another creature" is not a duration the
    engine has, so the previous mark is ended by hand and this one is laid
    for the encounter. The marks are found by label, which is what `c.mark`
    writes, so an ordinary mark from another row is left alone.

    The punishment half is `c.arm_trigger` rather than `c.watch`: the printed
    line is an immediate reaction, and `Encounter.spend` is what makes it once
    a round and not while dazed. It is armed once -- a second copy would
    teleport her twice for one swing.
    """
    me, ref = c.me, c.ref
    victim = c.target
    if victim is None:
        return
    for old in list(c.world.relations.targets(Relation.MARKED_BY, me)):
        if old == victim:
            continue
        for eff in list(c.world.effects.of(old)):
            if eff.label == f"{ref} mark":
                c.world.effects.end(eff, ref)
    c.mark(until=When.ENCOUNTER)

    if _armed(c, f"{ref} riposte"):
        return

    def landed_elsewhere(ev: Hit) -> bool:
        foe = ev.attacker
        if foe == me or not c.world.relations.holds(Relation.MARKED_BY, me, foe):
            return False
        if ev.target == me:
            return False
        return distance_between(c.world, me, foe) <= 10

    def close_in(ev: Hit) -> None:
        spot = _free_square_beside(c, ev.attacker)
        if spot is not None:
            c.teleport(10, who=me, to=spot)
        c.basic(on=ev.attacker)

    c.arm_trigger(
        Hit, close_in, when=landed_elsewhere,
        cost=ActionType.IMMEDIATE_REACTION, until=When.ENCOUNTER, on=me,
        label=f"{ref} riposte",
    )


@power(
    "m4593a5",
    level=2,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(1),
    target=Target(
        side="enemy", count=99, everyone=True, label="Each enemy in the burst on the ground"
    ),
    attack=Attack(vs=FORT, printed=7),
)
def m4593a5(c: Cast) -> None:
    """"Enemies in the burst touching the ground" is a target line about where
    the creature is rather than which side it is on, so it is a label and a
    check in the body -- `c.height` answers it in full and the burst takes
    everyone in it anyway, so nothing is missing and the row carries no
    marker. No entry gate: the row is a minor action against everything in
    reach and is worth taking even if one flier is exempt."""
    victim = c.target
    if victim is None or c.height(on=victim) > 0:
        return
    if c.strike():
        c.prone()


@power(
    "m4593a6",
    level=2,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4593a6(c: Cast) -> None:
    """A save taken on her own turn, not in answer to anything -- so there is
    no trigger and no "triggering effect" to name, and `c.save` takes the
    first save-ends hold it finds."""
    c.save(on=c.me)


# --------------------------------------------------------------------------
# m4595
# --------------------------------------------------------------------------


@power(
    "m4595a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=5),
    damage=Damage("1d6", 2, dtype=DamageType.PSYCHIC),
)
def m4595a0(c: Cast) -> None:
    """"Grants combat advantage" with no "to" names every attacker, and the
    widest thing `c.grants_advantage` can say is `to="team"` -- this creature
    and its allies. The difference is the target's own side, which never
    attacks it, so the two come to the same fight."""
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)
        c.grants_advantage(until=When.EONT, to="team")


# --------------------------------------------------------------------------
# m4619
# --------------------------------------------------------------------------


@power(
    "m4619a0",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4619a0(c: Cast) -> None:
    """Two bonuses out of one sentence, both gated on adjacency rather than
    armed and disarmed by watches: who is standing beside whom changes every
    time anybody moves. The outward half is laid on each ally of the named
    kind once, and each copy asks about its own holder."""
    me = c.me
    c.bonus(
        AC, 2, on=me, until=When.ENCOUNTER,
        when=lambda ctx: bool(c.within(1, side="ally")),
    )
    for friend in c.allies():
        if not c.is_kind("goblin", friend):
            continue
        c.bonus(
            AC, 1, on=friend, until=When.ENCOUNTER,
            when=lambda ctx, who=friend: c.adjacent(who),
        )


@power(
    "m4619a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d8", 4),
)
def m4619a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4619a2",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 5),
)
def m4619a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4619a3",
    level=2,
    usage=AT_WILL,
    action=MINOR,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.CHARM],
)
def m4619a3(c: Cast) -> None:
    """An Effect with no attack roll: every enemy in the burst is marked."""
    c.mark(until=When.EONT)


_M4619_STRUCK = "it is hit by an attack while mounted"


def _hit_me_while_mounted(world: World, me: int, ev: Event) -> bool:
    if getattr(ev, "target", None) != me:
        return False
    return bool(world.relations.sources(Relation.RIDDEN_BY, me))


@power(
    "m4619a4",
    level=2,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M4619_STRUCK,
    on=Trigger(Hit, _hit_me_while_mounted, _M4619_STRUCK),
)
def m4619a4(c: Cast) -> None:
    """`c.redirect` moves the live result with the event, so the damage lands
    on the mount rather than on the announcement alone. Filed as a free
    action by the compendium and printed as an immediate interrupt, which is
    the window that can still move the blow."""
    beast = c.mount()
    if beast is not None:
        c.redirect(to=beast)


_M4619_RODE_PAST = "its mount leaves a square adjacent to an enemy while charging"


def _mount_rode_past_an_enemy(world: World, me: int, ev: Event) -> bool:
    beasts = world.relations.sources(Relation.RIDDEN_BY, me)
    if getattr(ev, "actor", None) not in beasts:
        return False
    if getattr(ev, "kind_", "") != "charge":
        return False
    was = getattr(ev, "from_", None)
    if was is None:
        return False
    return any(
        any(square_distance(was, sq) <= 1 for sq in world.grid.squares_of(foe))
        for foe in enemies(world, me)
    )


@power(
    "m4619a5",
    level=2,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    once_per_round=True,
    trigger=_M4619_RODE_PAST,
    on=Trigger(Moved, _mount_rode_past_an_enemy, _M4619_RODE_PAST),
)
def m4619a5(c: Cast) -> None:
    """`Moved` and not `MoveStart` or `MoveEnd`: it is the only one of the
    three that carries `from_`, and "leaves a square adjacent to an enemy"
    is a question about where the mount came from. The enemy is found the
    same way the predicate found it, so the swing goes to the one the row is
    about and not to whoever is nearest now."""
    was = getattr(c.trigger, "from_", None)
    if was is None:
        return
    for foe in c.enemies():
        if any(square_distance(was, sq) <= 1 for sq in c.world.grid.squares_of(foe)):
            c.basic(on=foe)
            return


# --------------------------------------------------------------------------
# m4689
# --------------------------------------------------------------------------


@power(
    "m4689a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 5),
)
def m4689a0(c: Cast) -> None:
    """The mark is printed as the Effect, so it is laid on a miss too."""
    if c.strike():
        c.hit()
    c.mark(until=When.EONT)


@power(
    "m4689a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 5),
)
def m4689a1(c: Cast) -> None:
    was = _square_of(c, c.target)
    if c.strike():
        c.hit()
        if c.push(1):
            _step_into_vacated(c, was)


@power(
    "m4689a2",
    level=2,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("3d6", 5, kind=LIMITED),
)
def m4689a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4689a3",
    level=2,
    usage=ENCOUNTER,
    action=MOVE,
    reach=CloseBurst(3),
    target=Target(side="ally", count=1, label="One willing ally in the burst"),
)
def m4689a3(c: Cast) -> None:
    """No range is printed, so the slide bounds it: a creature that can be
    slid two squares and end up next to this one started at most three away,
    and a close burst 3 is that statement. "Willing" is what makes the target
    line `side="ally"` rather than any creature at all."""
    friend = c.target
    if friend is None:
        return
    spot = _free_square_beside(c, c.me)
    if spot is not None:
        c.slide(2, on=friend, to=spot)


# --------------------------------------------------------------------------
# m5307
# --------------------------------------------------------------------------


@power(
    "m5307a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("2d4", 5),
)
def m5307a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5307a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d8", 5),
    requires=_holding_nobody,
    requires_text="it must not have a creature grabbed",
)
def m5307a1(c: Cast) -> None:
    """A printed Requirement about the creature's *own* state is a `requires=`
    gate and nothing else -- it is asked of `(world, eid)` before the row is
    offered, which is where a Requirement belongs."""
    if c.strike():
        c.hit()
        c.grab(dc=13)


@power(
    "m5307a2",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=Target(
        side="enemy", count=1, label="One creature grabbed by it",
        relation=Relation.GRABBED_BY,
    ),
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("3d4", 5),
)
def m5307a2(c: Cast) -> None:
    """The caster-side gate came out with the body's re-pick: an empty pool
    already refuses the row, so "it must have a creature grabbed" was the same
    sentence said a second way."""
    if c.strike():
        c.hit()
        c.ongoing(5)


# --------------------------------------------------------------------------
# m5439
# --------------------------------------------------------------------------

#: The damage line all three of this block's attacks share, written once so
#: the rider below cannot drift from the headers it is copying.
_M5439_BLOW = ("2d6", 3)


def _its_own_kind(c: Cast, who: int) -> bool:
    return _ref_of(c, who) == "m5439"


def _reprisal(c: Cast, victim: int) -> None:
    """"Each time the target attacks an enemy that is not one of these, it
    takes damage as though it had been hit by this attack."

    `PowerUsed` rather than `AttackDeclared`: an attack is announced once per
    target, so a burst would have paid this out once for every creature it
    caught. `c.as_though_hit_by` is the verb the sentence sounds like and is
    the wrong one here -- it reruns this row's whole body, which would arm a
    second copy of this rider and swing again, so the blow is dealt directly
    off the shared damage line instead.
    """
    me, ref = c.me, c.ref
    label = f"{ref} reprisal on {victim}"
    if _armed(c, label):
        return

    def sting(ev: PowerUsed) -> None:
        if ev.actor != victim or not _is_attack(ev.power):
            return
        if any(_its_own_kind(c, who) for who in ev.targets):
            return
        dice, bonus = _M5439_BLOW
        c.damage(dice, bonus, on=victim)

    c.watch(PowerUsed, sting, until=When.EONT, on=me, label=label)


@power(
    "m5439a0",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5439a0(c: Cast) -> None:
    """Shifting out of the aura provokes, which it otherwise never does.

    Two judgements. `Moved` carries `from_`, so "out of this aura" is measured
    against where the creature started rather than guessed at `MoveStart`,
    when nothing has happened yet. And only a **shift** is provoked here: a
    walk out of an adjacent square already opens a window of its own, and
    provoking again would have given this creature two swings for one step.

    "Starts its turn adjacent" is remembered at `TurnStart`, because by the
    time the move is announced the creature may have come from anywhere.
    """
    me = c.me
    c.aura(1, label=f"{c.ref} aura", until=When.ENCOUNTER, on=me)
    stood: set[int] = set()

    def roll_call(ev: TurnStart) -> None:
        stood.clear()
        if ev.actor != me and c.distance(ev.actor) <= 1:
            stood.add(ev.actor)

    def slipped(ev: Moved) -> None:
        if ev.actor not in stood or getattr(ev, "kind_", "") != "shift":
            return
        if team(c.world, ev.actor) is team(c.world, me):
            return
        if c.distance(ev.actor) <= 1:
            return
        stood.discard(ev.actor)
        c.provoke(me, on=ev.actor, why=c.ref)

    c.watch(TurnStart, roll_call, until=When.ENCOUNTER, on=me, label=f"{c.ref} watch")
    c.watch(Moved, slipped, until=When.ENCOUNTER, on=me, label=f"{c.ref} aura exit")


@power(
    "m5439a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage(*_M5439_BLOW),
)
def m5439a1(c: Cast) -> None:
    """The rider is printed as the Effect, so it is armed on a miss too."""
    victim = c.target
    if c.strike():
        c.hit()
    if victim is not None:
        _reprisal(c, victim)


@power(
    "m5439a2",
    level=2,
    usage=Usage.RECHARGE,
    recharge=5,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage(*_M5439_BLOW, kind=LIMITED),
)
def m5439a2(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.hit()
    if victim is not None:
        _reprisal(c, victim)


@power(
    "m5439a3",
    level=2,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage(*_M5439_BLOW, kind=LIMITED, half_on_miss=True),
)
def m5439a3(c: Cast) -> None:
    """The burn is printed on both branches, so it is laid outside the if."""
    victim = c.target
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)
    c.ongoing(5)
    if victim is not None:
        _reprisal(c, victim)


_M5439_CAUGHT = "it is hit by a close or area attack that also targets an ally"

_SPREADING = ("close_burst", "close_blast", "area_burst")


def _caught_with_an_ally(world: World, me: int, ev: Event) -> bool:
    if getattr(ev, "target", None) != me:
        return False
    row = get(getattr(ev, "power", "") or "")
    if row is None or row.reach_of(getattr(ev, "branch", 0)).kind not in _SPREADING:
        return False
    mine = team(world, me)
    return any(
        who != me and team(world, who) is mine
        for who in getattr(ev, "among", ())
    )


@power(
    "m5439a4",
    level=2,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5439_CAUGHT,
    on=Trigger(Hit, _caught_with_an_ally, _M5439_CAUGHT),
    dropped=("Hit.area",),
)
def m5439a4(c: Cast) -> None:
    """The shift plays; "if it ends outside the area, the attack does not hit
    it" does not. Nothing on an attack event says which squares the attack
    covered -- `among` names the creatures it caught and not the ground -- so
    the escape cannot be tested and the blow is not cancelled. The row is
    still worth having: a soldier pulled out of a blast is where it wants to
    be."""
    c.shift(c.speed_of(c.me))


# --------------------------------------------------------------------------
# m5537
# --------------------------------------------------------------------------


@power(
    "m5537a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 2),
)
def m5537a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)


_M5537_BURNED = "a creature takes damage from its ongoing poison"


def _my_poison_ticked(world: World, me: int, ev: Event) -> bool:
    """The burn, and not the bite that laid it.

    `durations._on_turn_start` deals ongoing damage with the effect's own
    `str()` as the detail, so the row's ref is not on the event; the three
    facts that are -- the source, the type, and the word the label starts
    with -- name this creature's poison and nothing else it does.
    """
    if getattr(ev, "source", None) != me:
        return False
    if DamageType.POISON not in getattr(ev, "types", lambda: ())():
        return False
    return "ongoing" in getattr(ev, "detail", "")


@power(
    "m5537a1",
    level=2,
    usage=AT_WILL,
    action=ActionType.OPPORTUNITY,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=5),
    damage=Damage("2d6", 1),
    trigger=_M5537_BURNED,
    on=Trigger(DamageApplied, _my_poison_ticked, _M5537_BURNED),
)
def m5537a1(c: Cast) -> None:
    """"Save ends both" is one effect carrying the daze and the burn, not two:
    `c.condition(..., ongoing=)` is the one save the printed line means, and a
    separate `c.ongoing` would have asked for a second."""
    foe = getattr(c.trigger, "target", None)
    if foe is None or c.distance(foe) > 1:
        return
    if c.strike(on=foe):
        c.hit(on=foe)
        c.condition(
            Condition.DAZED, until=When.SAVE_ENDS, on=foe,
            ongoing=(5, DamageType.NECROTIC),
        )


# --------------------------------------------------------------------------
# m6032
# --------------------------------------------------------------------------


@power(
    "m6032a0",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POISON],
)
def m6032a0(c: Cast) -> None:
    """`SurgeSpent` is emitted from every site that decrements a pool, which
    is the only way "spends a healing surge in this aura" can be seen happen
    at all. The aura is asked at the moment of spending rather than tracked,
    so a creature that walks in and out is right either way."""
    me, label = c.me, f"{c.ref} aura"
    c.aura(2, label=label, until=When.ENCOUNTER, on=me)

    def drained(ev: SurgeSpent) -> None:
        if ev.actor == me or team(c.world, ev.actor) is team(c.world, me):
            return
        if c.in_my_aura(ev.actor, label=label):
            c.weakened(on=ev.actor, until=When.EOTNT)

    c.watch(SurgeSpent, drained, until=When.ENCOUNTER, on=me, label=f"{c.ref} watch")


@power(
    "m6032a1",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6032a1(c: Cast) -> None:
    _aquatic_edge(c)


@power(
    "m6032a2",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
)
def m6032a2(c: Cast) -> None:
    """A trait that pays the *attacker*, so `on=` is named: `c.heal` follows
    `c.target`, and this row has none."""
    me = c.me

    def rewarded(ev: Hit) -> None:
        if ev.target == me and ev.critical:
            c.heal(4, on=ev.attacker)

    c.watch(Hit, rewarded, until=When.ENCOUNTER, on=me, label=f"{c.ref} spines")


@power(
    "m6032a3",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6032a3(c: Cast) -> None:
    """Two words, said twice: `c.ignores_difficult` takes one label a call and
    the printed line names two sorts of ground."""
    c.ignores_difficult("mud", on=c.me, until=When.ENCOUNTER)
    c.ignores_difficult("water", on=c.me, until=When.ENCOUNTER)


@power(
    "m6032a4",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d8", 5),
)
def m6032a4(c: Cast) -> None:
    """The mark is printed as the Effect, so it is laid on a miss too."""
    if c.strike():
        c.hit()
    c.mark(until=When.EONT)


@power(
    "m6032a5",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d8", 2),
)
def m6032a5(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6032a6",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    charges=True,
    attack=Attack(vs=AC, printed=7),
    damage=Damage("2d8", 2),
)
def m6032a6(c: Cast) -> None:
    """The same shape as m4197a1: `charges=True` so the row is offered at
    charging range, `c.run_at` rather than `c.charge_at(c.ref)` -- which
    would spend this row again to make its own swing -- and
    `c.as_basic(window="charge")` filed so the engine's own charge action
    offers it as the substitute the card describes."""
    if c.first:
        c.as_basic(c.ref, window="charge", until=When.ENCOUNTER)
    victim = c.target
    if victim is None:
        return
    if not c.adjacent(victim):
        c.run_at(victim)
    if c.strike():
        c.hit()
    c.mark(until=When.EONT)


@power(
    "m6032a7",
    level=2,
    usage=Usage.RECHARGE,
    recharge=0,
    action=MINOR,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    attack=Attack(vs=WILL, printed=5),
)
def m6032a7(c: Cast) -> None:
    """No damage line -- the whole Hit is the drag. The printed recharge is a
    condition rather than a die and is laid on top of the filed 6+, the way
    "recharge when first bloodied" is."""
    me, ref = c.me, c.ref
    if c.strike():
        c.pull(4)
    if c.first and not _armed(c, f"{ref} recharge"):

        def spent(ev: ActionPointSpent) -> None:
            if ev.actor == me:
                c.restore_use(ref, on=me)

        c.watch(
            ActionPointSpent, spent, until=When.ENCOUNTER, on=me,
            label=f"{ref} recharge",
        )


_M6032_LOOKED_AWAY = "an enemy marked by it attacks without including it"


@power(
    "m6032a8",
    level=2,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d8", 5, half_on_miss=True),
    trigger=_M6032_LOOKED_AWAY,
    on=Trigger(PowerUsed, _marked_foe_looks_away, _M6032_LOOKED_AWAY),
)
def m6032a8(c: Cast) -> None:
    """Half damage on a miss, which is a printed Miss line and not a guess."""
    foe = getattr(c.trigger, "actor", None)
    if foe is None or c.distance(foe) > 1:
        return
    if c.strike(on=foe):
        c.hit(on=foe)
    else:
        c.hit(on=foe, half=True)


# --------------------------------------------------------------------------
# m6272
# --------------------------------------------------------------------------


@power(
    "m6272a0",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.immune_power()",),
)
def m6272a0(c: Cast) -> None:
    """Immunity to four *named rows*, chosen when the creature was built, and
    the rows turning into temporary hit points instead. Nothing can say
    either half: `c.immune` takes conditions, `c.resist` takes damage types,
    and neither takes a ref. The whole row waits on one verb, so it is a
    `todo` and is refused in play rather than half-resolving."""


@power(
    "m6272a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d10", 5),
)
def m6272a1(c: Cast) -> None:
    """"It can choose to deal fire damage instead" is a choice, so it is asked
    rather than decided here. `c.deals` is an override and speaks for
    `Keyword.WEAPON` rows, which this is, and it is laid for the turn only --
    the choice is per swing. The header stays untyped because that is what
    the card prints as the default."""
    if c.choose([False, True], "deal fire damage instead?"):
        c.deals(DamageType.FIRE, until=When.EOT, on=c.me)
    if c.strike():
        c.hit()


@power(
    "m6272a2",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("2d8"),
)
def m6272a2(c: Cast) -> None:
    """No damage bonus printed, which is a bare 2d8."""
    if c.strike():
        c.hit()


_M6272_LANDED = "an enemy is hit by its attack"


def _my_blow_landed_on_an_enemy(world: World, me: int, ev: Event) -> bool:
    if getattr(ev, "attacker", None) != me:
        return False
    victim = getattr(ev, "target", None)
    return victim is not None and team(world, victim) is not team(world, me)


@power(
    "m6272a3",
    level=2,
    usage=Usage.RECHARGE,
    recharge=0,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE, Keyword.TELEPORTATION],
    trigger=_M6272_LANDED,
    on=Trigger(Hit, _my_blow_landed_on_an_enemy, _M6272_LANDED),
    recharge_when=Trigger(Bloodied, about_me,
        "when first bloodied"),
)
def m6272a3(c: Cast) -> None:
    """Both creatures move and the second one's destination is named, so it is
    passed as a square: a bare distance asks the controller where to go, and
    "ends this movement adjacent to the m6272" is not a choice. The caster
    jumps first, or the square computed for the enemy is beside where it used
    to be standing."""
    foe = getattr(c.trigger, "target", None)
    if foe is None:
        return
    c.damage("2d6", dtype=DamageType.FIRE, on=foe)
    c.teleport(10, who=c.me)
    spot = _free_square_beside(c, c.me)
    if spot is not None:
        c.teleport(10, who=foe, to=spot)
    _recharge_when_bloodied(c)


# --------------------------------------------------------------------------
# m6506
# --------------------------------------------------------------------------


@power(
    "m6506a0",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6506a0(c: Cast) -> None:
    """Its weapon reaches 2, and without this the opportunity window is the
    ring of one every creature has: a reach weapon deliberately does *not*
    widen it, so the trait that says otherwise has to be written."""
    c.threatens(2, on=c.me, until=When.ENCOUNTER)


@power(
    "m6506a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d10", 5),
)
def m6506a1(c: Cast) -> None:
    """The mark is printed as the Effect, so it is laid on a miss too."""
    if c.strike():
        c.hit()
    c.mark(until=When.EONT)


@power(
    "m6506a2",
    level=2,
    usage=Usage.RECHARGE,
    recharge=0,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d10", 5, kind=LIMITED),
    recharge_when=Trigger(Bloodied, about_me,
        "when first bloodied"),
)
def m6506a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()
    if c.first:
        _recharge_when_bloodied(c)


_M6506_LOOKED_AWAY = "an enemy within 2 squares and marked by it attacks elsewhere"


@power(
    "m6506a3",
    level=2,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    trigger=_M6506_LOOKED_AWAY,
    on=Trigger(PowerUsed, _marked_foe_looks_away, _M6506_LOOKED_AWAY),
)
def m6506a3(c: Cast) -> None:
    """"It uses m6506a1 against the triggering enemy" is `c.use_power`, which
    puts the whole of that row -- its attack line, its mark -- on the board
    at this row's cost. The distance is tested here rather than in the
    predicate, which is shared with blocks that reach further."""
    foe = getattr(c.trigger, "actor", None)
    if foe is None or c.distance(foe) > 2:
        return
    c.use_power("m6506a1", on=foe, spend=False)


_M6506_SPELLED = "an arcane attack hits it"


@power(
    "m6506a4",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M6506_SPELLED,
    on=Trigger(
        Hit,
        lambda w, me, ev: getattr(ev, "target", None) == me
        and by_keyword(Keyword.ARCANE)(w, me, ev),
        _M6506_SPELLED,
    ),
)
def m6506a4(c: Cast) -> None:
    c.temp_hp(10, on=c.me)


# --------------------------------------------------------------------------
# m859
# --------------------------------------------------------------------------


@power(
    "m859a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d8", 3),
)
def m859a0(c: Cast) -> None:
    if c.strike():
        c.hit()


_M859_WARD_STRUCK = "an adjacent foe attacks one of the m499 it guards"


def _struck_at_what_it_guards(world: World, me: int, ev: Event) -> bool:
    """The ward is named by stat block, not by relation.

    The printed line protects a particular kind of creature rather than
    whichever one this is standing next to, so `Ident.ref` is the question
    and `Relation.GUARDED_BY` -- which nothing sets up for this block -- is
    not.
    """
    attacker = getattr(ev, "attacker", None)
    victim = getattr(ev, "target", None)
    if attacker is None or victim is None or attacker == me:
        return False
    if team(world, attacker) is team(world, me):
        return False
    if distance_between(world, me, attacker) > 1:
        return False
    ident = world.get(victim, Ident)
    return ident is not None and ident.ref == "m499"


@power(
    "m859a1",
    level=2,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=Melee(1),
    target=NO_TARGET,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 3),
    trigger=_M859_WARD_STRUCK,
    on=Trigger(AttackDeclared, _struck_at_what_it_guards, _M859_WARD_STRUCK),
)
def m859a1(c: Cast) -> None:
    """An interrupt resolves before the roll it answers, which is the one
    window in which a penalty "to the triggering attack" can still be read.
    `once=True` so the -4 is spent on that swing and nothing later."""
    foe = getattr(c.trigger, "attacker", None)
    if foe is None:
        return
    if c.strike(on=foe):
        c.hit(on=foe)
    c.penalty("attack", 4, on=foe, until=When.EOT, once=True)
