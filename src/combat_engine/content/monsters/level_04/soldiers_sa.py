"""Monster abilities, level 4, soldiers.

Twenty-seven stat blocks, 108 rows. Nine more level 4 soldiers print no
ability at all -- m190, m199, m2912, m3021, m3041, m475, m4802, m4845, m5082's
neighbours m672 and m879, and m936's -- so there is nothing to decorate for
them and they are absent rather than skipped. (The full list of blocks with no
row: m190, m199, m2912, m3021, m3041, m475, m4802, m4845, m672, m879.)

The conventions are the ones `level_01` to `level_03` settled, and eighteen
shared shapes are imported rather than written again: a soldier's vocabulary is
the same at every level and a second copy of a predicate is a second thing to
get wrong.

What is decided here, once, for twenty-seven blocks:

* numbers load from `game.db`; the attack line is written exactly as printed
  (`Attack(vs=AC, printed=11)`) and the damage line goes in the header as data
  so an MM1 block can be rescaled to MM3 maths later;
* a **trait** costs no action, has no target, and arms the watches that hold it
  for the rest of the fight. Several rows here are *filed* as standard actions
  and are plainly traits -- "it can shift 1 square as a minor action" is not
  something a creature spends its turn on -- and those are written
  `action=ActionType.NONE` with the printed usage left alone;
* a printed range of "15/30" or "10/20" takes the **normal** range;
* a printed Requirement naming the creature's own kit -- a flail, a halberd, a
  reach weapon, a free hand -- is **not** a gate. `Gear` is empty on every
  monster, so a `c.wielding` test would be false in every fight rather than
  only on a bare board, which makes a working row look like a rule that never
  applies. #366.

The mark is the thing to get right three times over:

* `c.mark` and never `c.condition(Condition.MARKED, ...)`: only the first sets
  `Relation.MARKED_BY`, which is what every "an enemy marked by it" trigger
  reads;
* half of these blocks print the mark as an **Effect** rather than inside the
  Hit, so it is laid whether the swing landed or not;
* "until the end of its next turn" is `When.EONT` and "until the **start** of
  its next turn" is `When.SONT`; two blocks here print the second.

The rows that punish a marked enemy for looking elsewhere answer `PowerUsed`,
which fires once per use and carries the whole target list, rather than
`AttackDeclared`, which is announced once per target and would pay out twice
for one burst. The rows that punish it for *shifting* answer `MoveStart`,
because by `MoveEnd` the enemy has left and "adjacent to it" is false
precisely when the row should fire.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_01.artillery_sa import _prone_save
from combat_engine.content.monsters.level_02.lurkers_sa import (
    _reach_kind,
    _spreading_blow,
    _triggering_enemy,
    _twice,
)
from combat_engine.content.monsters.level_02.skirmishers_sa import _high_crit
from combat_engine.content.monsters.level_02.soldiers_sa import (
    _armed,
    _free_square_beside,
    _is_attack,
    _missed_me_in_melee,
    _recharge_when_bloodied,
    _ref_of,
    _save_ends_on_me,
)
from combat_engine.content.monsters.level_03.artillery_sa import _death_throe
from combat_engine.content.monsters.level_03.brutes_sa import _both_hit
from combat_engine.content.monsters.level_03.lurkers_sa import _restricted_to
from combat_engine.content.monsters.level_03.skirmishers_sa import (
    _reachable,
    _step_beside,
)
from combat_engine.content.monsters.level_03.soldiers_sa import (
    _crowding,
    _edge_when_mobbed,
    _mark_bites,
    _marked_adjacent_shifts,
)
from combat_engine.content.monsters.level_04.skirmishers_sa import _hauls_the_grabbed
from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    EACH_ALLY,
    EACH_ENEMY,
    EACH_OTHER,
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
    SELF,
    STANDARD,
    WILL,
    ActionType,
    Attack,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    Damage,
    DamageType,
    Effect,
    Keyword,
    Melee,
    Ranged,
    Relation,
    Stats,
    Target,
    UpTo,
    Usage,
    When,
    World,
    power,
)
from combat_engine.engine.events import (
    AttackDeclared,
    ConditionEnded,
    DamageApplied,
    Dropped,
    EffectApplied,
    Hit,
    Miss,
    MoveStart,
    PowerUsed,
    RelationSet,
    SavingThrow,
    TurnStart,
)
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import distance_between, enemies, flanked_by, team
from combat_engine.engine.triggers import Trigger, about_me

# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------


def _marked_in_reach(radius: int) -> Any:
    """"Targets a creature marked by it", as an entry gate, at any reach.

    `Target` filters on side, count, size and what is in hand and on nothing a
    creature is *suffering*, so the narrowing cannot live there; and a body that
    looks and returns is a standard action the policy spends on nothing.
    `dsl.usable` is handed `(world, eid)` and the caster is all it knows, so the
    question is asked from this end as well as in the body. #361.

    `_marked_by_me_in_reach` next door is this at reach 1 only, and two of the
    blocks here print reach 2.
    """

    def gate(world: World, eid: int) -> bool:
        return _reachable(
            world, eid, radius,
            lambda foe: world.relations.holds(Relation.MARKED_BY, eid, foe),
        )

    return gate


def _marked_adjacent_looks_away(world: World, me: int, ev: Any) -> bool:
    """"An adjacent enemy marked by it attacks a target other than it."

    `_marked_foe_looks_away` is this without the adjacency clause, which four
    blocks here print and which changes which creature the row may answer.
    """
    actor = getattr(ev, "actor", None)
    if actor is None or actor == me or not _is_attack(getattr(ev, "power", "")):
        return False
    if not world.relations.holds(Relation.MARKED_BY, me, actor):
        return False
    if distance_between(world, me, actor) > 1:
        return False
    return me not in getattr(ev, "targets", ())


def _adjacent_enemy_stood(world: World, me: int, ev: ConditionEnded) -> bool:
    """"An enemy adjacent to it stands up."

    Standing is not an event of its own: `actions` ends whatever holds the prone
    and the only trace is the `why` it passes, so that is what distinguishes
    getting up from a duration lapsing. Two blocks here print the line.
    """
    if ev.condition is not Condition.PRONE or ev.why != "stood up":
        return False
    if ev.target == me or ev.target not in enemies(world, me):
        return False
    return distance_between(world, me, ev.target) <= 1


def _hit_with(ref: str) -> Any:
    """"When it hits with <its own row>." The ref is the comparison a printed
    weapon name cannot be."""

    def landed(world: World, me: int, ev: Hit) -> bool:
        return getattr(ev, "attacker", None) == me and getattr(ev, "power", "") == ref

    return landed


def _mark_punishes(
    c: Cast,
    victim: int,
    amount: int,
    *,
    until: When,
    dtype: DamageType = DamageType.UNTYPED,
) -> None:
    """"While marked, the target takes N damage if it moves **or** makes an
    attack that does not include it."

    Two watches, because the sentence names two different things. `PowerUsed`
    answers the look-away -- it fires once per use and carries the whole target
    list, where `AttackDeclared` is announced once per target and would charge a
    burst once for every creature it caught. `MoveStart` answers the step, and a
    shove is not the target moving.
    """
    me, ref = c.me, c.ref

    def looked_away(ev: PowerUsed) -> None:
        if ev.actor != victim or not _is_attack(ev.power) or me in ev.targets:
            return
        c.flat(amount, dtype=dtype, on=victim)

    def stirred(ev: MoveStart) -> None:
        if getattr(ev, "actor", None) != victim:
            return
        if getattr(ev, "kind_", "") in ("push", "pull", "slide"):
            return
        c.flat(amount, dtype=dtype, on=victim)

    c.watch(PowerUsed, looked_away, until=until, on=me, label=f"{ref} away {victim}")
    c.watch(MoveStart, stirred, until=until, on=me, label=f"{ref} step {victim}")


def _ends_together(c: Cast, held: Effect | None, *mods: Effect | None) -> None:
    """"... (save ends both)", where one half is a condition and the other is a
    modifier.

    `c.penalty` lays an effect of its own with its own saving throw, so a card
    printing *one* save written as a condition plus three penalties grants four
    -- and the victim shakes off most of what the card calls one thing. The
    modifiers are held to the end of the encounter and lifted by the
    condition's own `on_end`, which fires for the save and for the clock alike.
    """
    live = [m for m in mods if m is not None]
    if held is None or not live:
        return

    def lift() -> None:
        for one in live:
            c.world.effects.end(one, "saved")

    held.on_end.append(lift)


def _starts_turn_in_aura(
    c: Cast,
    radius: int,
    amount: int,
    dtype: DamageType = DamageType.UNTYPED,
    *,
    then: Any = None,
) -> None:
    """An aura for the board to draw, and the toll taken at the top of a turn.

    `_ends_turn_in_aura` next door is the same shape at the other end of the
    turn. Who is inside is asked as the turn opens rather than kept as a list:
    the aura travels with the creature and a stored membership is stale the
    moment either of them moves.
    """
    me = c.me
    c.aura(radius, label=f"{c.ref} aura", until=When.ENCOUNTER, on=me)

    def toll(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == me:
            return
        if team(c.world, ev.actor) is team(c.world, me):
            return
        if distance_between(c.world, me, ev.actor) > radius:
            return
        c.flat(amount, dtype=dtype, on=ev.actor)
        if then is not None:
            then(ev.actor)

    c.watch(TurnStart, toll, until=When.ENCOUNTER, on=me, label=f"{c.ref} toll")


def _shifts_in_aura(c: Cast, radius: int, amount: int) -> None:
    """"Any enemy that shifts in the aura takes N damage."

    `MoveStart` and not `MoveEnd`: a shift out of the ring is the commonest one
    the line is for, and by the end of it the creature is no longer inside.
    """
    me = c.me
    c.aura(radius, label=f"{c.ref} aura", until=When.ENCOUNTER, on=me)

    def slipped(ev: MoveStart) -> None:
        foe = getattr(ev, "actor", None)
        if foe is None or foe == me or getattr(ev, "kind_", "") != "shift":
            return
        if team(c.world, foe) is team(c.world, me):
            return
        if distance_between(c.world, me, foe) > radius:
            return
        c.flat(amount, on=foe)

    c.watch(MoveStart, slipped, until=When.ENCOUNTER, on=me, label=f"{c.ref} ring")


def _recharge_while_nothing_held(c: Cast, held: Effect | None) -> None:
    """"Recharges if no creature is held by this power at the start of its turn."

    The 6+ stays in the header, because that is what `actions.recharge` rolls
    and what the card shows; this is the printed sentence on top of it, and the
    two only ever agree to make the row available sooner. Armed once -- the row
    is used again every time it recharges and a second watch under the same
    label would hand back two uses for one turn.
    """
    me, ref = c.me, c.ref
    label = f"{ref} recharge"
    if _armed(c, label):
        return

    def opened(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me:
            return
        if held is None or held.ended or held.id not in c.world.effects.live:
            c.restore_use(ref, on=me)

    c.watch(TurnStart, opened, until=When.ENCOUNTER, on=me, label=label)


def _unseen_until_it_stirs(c: Cast) -> None:
    """Unseen until it moves or attacks.

    `_vanish_until_it_swings` next door ends on the swing alone; this block
    prints the movement half as well, and a creature that has walked out of
    hiding and is still invisible is the whole of what the line forbids.
    """
    me = c.me
    hidden = c.invisible(on=me, until=When.ENCOUNTER)
    if hidden is None:
        return

    def show(ev: Any) -> None:
        who = getattr(ev, "attacker", None)
        if who is None:
            who = getattr(ev, "actor", None)
        if who == me:
            c.world.effects.end(hidden, "it moved or attacked")

    for event in (Hit, Miss, MoveStart):
        c.watch(event, show, until=When.ENCOUNTER, on=me, once=True, label=f"{c.ref} unseen")


def _from_a_trap(c: Cast, ctx: dict[str, Any]) -> bool:
    """"+2 to all defences against traps", read off the attacker in the context.

    `query.defence` is handed the attack context, so this is a gate rather than
    a watch armed and disarmed around every swing. `.get`, because not every
    lookup that reaches a defence carries an attacker.
    """
    who = ctx.get("attacker")
    return isinstance(who, int) and c.is_trap(who)


def _melee_blow(ctx: dict[str, Any]) -> bool:
    """Was the blow being looked up a melee one? Off the row, not the event."""
    return _reach_kind(str(ctx.get("power", ""))) == "melee"


def _ridden_by_fourth_level(world: World, eid: int) -> bool:
    """"While mounted by a friendly rider of 4th level or higher".

    **`targets`, not `sources`.** `Relations.set(RIDDEN_BY, mount, rider)` is the
    direction the engine stores -- `c.rider` and `c.mount` read exactly that way
    -- so a mount's riders are its `targets` and its `sources` are whatever *it*
    is riding, which is empty for a mount every time.

    Written here rather than imported because the level 4 skirmisher file's copy
    still asks `sources`, which is the inversion the level 2 and the level 4
    misc copies both carry a paragraph about having fixed. Reported rather than
    edited: that file is not this batch's to touch.
    """
    for rider in world.relations.targets(Relation.RIDDEN_BY, eid):
        stats = world.get(rider, Stats)
        if stats is not None and stats.level >= 4:
            return True
    return False


def _holding_fewer_than_two(world: World, eid: int) -> bool:
    """"If it has two creatures grabbed it cannot make claw attacks", as a gate."""
    return len(world.relations.targets(Relation.GRABBED_BY, eid)) < 2


def _holding_somebody(world: World, eid: int) -> bool:
    """"Each creature grabbed by it", as an entry gate -- a row whose every
    consequence is aimed at a captive is not usable while there is none, and
    UNUSED is the honest verdict where SILENT would read as a broken row."""
    return bool(world.relations.targets(Relation.GRABBED_BY, eid))


def _grabbing(c: Cast) -> list[int]:
    return c.grabbing()


# --------------------------------------------------------------------------
# m1133
# --------------------------------------------------------------------------


@power(
    "m1133a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d12", 3),
)
def m1133a0(c: Cast) -> None:
    """The printed critical, 1d12+18, is the line's own maximum plus an extra
    1d12, so it is a high-crit die rolled in the body: `c.damage` maxes its dice
    on a critical and a die written into the header would come out at its
    highest face every time."""
    if c.strike():
        c.hit()
        _high_crit(c, "1d12")
        victim = c.target
        if victim is not None:
            c.mark(on=victim, until=When.EONT)
            _mark_punishes(
                c, victim, 5, until=When.EONT, dtype=DamageType.RADIANT
            )


@power(
    "m1133a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 4),
)
def m1133a1(c: Cast) -> None:
    """The extract carries two damage lines for this row and they disagree: the
    **column** says 1d6+4, and the free text beside it says 1d12+3 with a
    critical, which is the block's other weapon leaking in -- the same line the
    row above prints verbatim. The column wins, because that is the number
    `cards.py` can check and the one a rescale reads. The mark is kept: it is in
    the printed text and the column carries no rider at all.

    One attack per target, which is what `UpTo(2)` and a per-target body are.
    """
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m1133a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.RADIANT, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d12", 3, dtype=DamageType.RADIANT),
)
def m1133a2(c: Cast) -> None:
    """"If it marked the target" is asked of the relation and not of a condition:
    a mark laid as a bare condition is invisible here, which is why every row on
    this block uses `c.mark`."""
    if c.strike():
        c.hit()
        _high_crit(c, "1d12")
        if c.marked(by=c.me):
            c.flat(2, dtype=DamageType.RADIANT)


@power(
    "m1133a3",
    level=4,
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(3),
    target=NO_TARGET,
    keywords=[Keyword.ZONE],
)
def m1133a3(c: Cast) -> None:
    """`c.grants_in` rather than a bonus with a duration: the printed line runs
    on the geometry -- it is held for as long as a creature stands inside -- and
    a clocked bonus cannot say that."""
    ring = c.zone(c.area(), label=c.ref, until=When.ENCOUNTER)
    c.grants_in(ring, AC, 1, side="team", kind="power")


@power(
    "m1133a4",
    level=4,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m1133a4(c: Cast) -> None:
    """"On his next attack this turn" is one blow and this turn only, so the
    modifier is spent on use and clocked to the end of the turn."""
    c.bonus("damage", c.str_mod, on=c.me, until=When.EOT, once=True)


@power(
    "m1133a5",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1133a5(c: Cast) -> None:
    """A trait, not the standard action the database files it as: neither half is
    something a creature spends its turn on."""
    c.resist_forced(1, on=c.me, until=When.ENCOUNTER)
    _prone_save(c)


# --------------------------------------------------------------------------
# m1924
# --------------------------------------------------------------------------


@power(
    "m1924a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=9),
    damage=Damage("1d8", 5),
)
def m1924a0(c: Cast) -> None:
    """No duration is printed on the hold, which is the stat-block shorthand for
    the default -- the end of the attacker's next turn."""
    if c.strike():
        c.hit()
        c.immobilized()


# --------------------------------------------------------------------------
# m1948
# --------------------------------------------------------------------------


@power(
    "m1948a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d6", 6),
)
def m1948a0(c: Cast) -> None:
    """The printed "requires a free hand" is not a gate: `Gear` is empty on every
    monster, so asking would make the row refuse itself in every fight. #366."""
    if c.strike():
        c.hit()
        c.grab()


@power(
    "m1948a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=Target(
        "enemy", 1,
        label="targets a creature it has grabbed",
        relation=Relation.GRABBED_BY,
    ),
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d10", 6),
)
def m1948a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)


@power(
    "m1948a2",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d6", 6, kind=LIMITED),
)
def m1948a2(c: Cast) -> None:
    """Two swings rolled here rather than two uses of the block's own claw: the
    -2 is a penalty on *these* rolls, and `c.use_power` has nowhere to carry it.
    `ONE_CREATURE`, because the rider only exists when both went to one."""
    landed = 0
    for _ in range(2):
        if c.strike(plus=-2):
            c.hit()
            landed += 1
    if landed == 2:
        c.grab()
        c.ongoing(5, until=When.SAVE_ENDS)


# --------------------------------------------------------------------------
# m2023
# --------------------------------------------------------------------------


@power(
    "m2023a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.DISEASE],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d6", 5),
    dropped=("c.contract(ref)",),
)
def m2023a0(c: Cast) -> None:
    """The burn is exact. The disease the first failed save hands over is a block
    of its own and nothing carries one, which is the named gap."""
    if c.strike():
        c.hit()
        c.ongoing(3, until=When.SAVE_ENDS)


# --------------------------------------------------------------------------
# m3130
# --------------------------------------------------------------------------


@power(
    "m3130a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("1d8", 2, dtype=DamageType.NECROTIC),
)
def m3130a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m3130a1",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=7),
    damage=Damage("2d6", 2, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m3130a1(c: Cast) -> None:
    """"Recharge when bloodied" on top of the die: the number stays in the header
    because that is what the card shows and what `actions.recharge` rolls, and
    the two only ever agree to make the row available sooner."""
    if c.strike():
        c.hit()
        c.dazed(until=When.EONT)
    if c.first:
        _recharge_when_bloodied(c)


# --------------------------------------------------------------------------
# m3531
# --------------------------------------------------------------------------


@power(
    "m3531a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d10", 5),
)
def m3531a0(c: Cast) -> None:
    """"An ally within line of sight" is asked of the board rather than of a
    radius: `c.can_see` is the printed clause and there is no distance in it."""
    if c.strike():
        c.hit()
        _high_crit(c, "2d6")
        mate = next((a for a in c.allies() if c.can_see(a)), None)
        if mate is not None:
            c.shift(1, who=mate)


@power(
    "m3531a1",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d10", 3, kind=LIMITED),
)
def m3531a1(c: Cast) -> None:
    """"Two allies" with no range on them at all, so the two nearest friends are
    the ones the sentence can mean."""
    if c.strike():
        c.hit()
        for mate in c.allies()[:2]:
            c.shift(1, who=mate)


@power(
    "m3531a2",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("2d6", 4, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m3531a2(c: Cast) -> None:
    """"Save ends both" is one saving throw, so the four penalties are hung on
    the slow's own lifetime instead of each getting a throw of its own."""
    if c.strike():
        c.hit()
        slowed = c.condition(Condition.SLOWED, until=When.SAVE_ENDS)
        _ends_together(
            c,
            slowed,
            c.penalty(AC, 2, until=When.ENCOUNTER),
            c.penalty(FORT, 2, until=When.ENCOUNTER),
            c.penalty(REF, 2, until=When.ENCOUNTER),
            c.penalty(WILL, 2, until=When.ENCOUNTER),
        )
    if c.first:
        for mate in c.in_squares(c.area(), side="ally"):
            if c.is_kind("undead", mate):
                c.slide(2, on=mate)
        _recharge_when_bloodied(c)


_M3531_LANDED = "it hits with its own weapon"


@power(
    "m3531a3",
    level=4,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M3531_LANDED,
    on=Trigger(Hit, _hit_with("m3531a0"), _M3531_LANDED),
)
def m3531a3(c: Cast) -> None:
    """The creature the daze lands on is the one the triggering blow struck, not
    a target of this row -- an immediate action with `NO_TARGET` has none."""
    victim = getattr(c.trigger, "target", None)
    if victim is not None:
        c.dazed(on=victim, until=When.EONT)


@power(
    "m3531a4",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3531a4(c: Cast) -> None:
    """"Loses a healing surge" is `c.spend_surge` aimed at the victim: a monster
    carries one per tier so a line of this shape has something to take.
    `c.had_advantage` reads the advantage off the blow -- asking the board again
    is too late, since a one-shot grant has already been spent."""
    me, ref = c.me, c.ref

    def landed(ev: Hit) -> None:
        if getattr(ev, "attacker", None) != me:
            return
        if not _melee_blow({"power": getattr(ev, "power", "")}):
            return
        if not c.had_advantage(ev):
            return
        victim = getattr(ev, "target", None)
        if victim is not None:
            c.spend_surge(on=victim)

    c.watch(Hit, landed, until=When.ENCOUNTER, on=me, label=f"{ref} toll")


_M3531_FALLS = "it drops to 0 hit points"


@power(
    "m3531a5",
    level=4,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M3531_FALLS,
    on=Trigger(Dropped, about_me, _M3531_FALLS),
)
def m3531a5(c: Cast) -> None:
    """`spend=False`: the burst it unleashes is a recharge row of its own and the
    printed line does not pay its cost twice."""
    c.use_power("m3531a2", spend=False)


_M3531_SADDLED = "it suffers an effect that a save can end"


@power(
    "m3531a6",
    level=4,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M3531_SADDLED,
    on=Trigger(EffectApplied, _save_ends_on_me, _M3531_SADDLED),
)
def m3531a6(c: Cast) -> None:
    """`EffectApplied` rather than `ConditionApplied`: an effect carrying nothing
    but ongoing damage announces no condition at all, and the printed line says
    "an effect"."""
    c.save(on=c.me, against=c.ref)


@power(
    "m3531a7",
    level=4,
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_ALLY,
    once_per_round=True,
)
def m3531a7(c: Cast) -> None:
    """`c.grant_attack` and not `c.basic`: the swing is somebody else's, and
    `c.strike` always rolls for the caster."""
    mate = c.target
    if mate is None:
        return
    foe = next((f for f in c.enemies() if c.adjacent_to(f, mate)), None)
    if foe is not None:
        c.grant_attack(mate, on=foe)


# --------------------------------------------------------------------------
# m3543
# --------------------------------------------------------------------------


@power(
    "m3543a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d10", 5),
)
def m3543a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m3543a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=Target(
        "enemy", 1,
        label="targets a creature it has marked",
        relation=Relation.MARKED_BY,
    ),
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d10", 5),
)
def m3543a1(c: Cast) -> None:
    """The printed weapon Requirement is not a gate (#366). The mark is now the
    target line itself, so the entry gate and the body's re-pick both came
    out."""
    if c.strike():
        c.hit()
        c.slide(2)
        if c.crit:
            c.prone()


@power(
    "m3543a2",
    level=4,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    dropped=("etl.monster.attack_defence()",),
)
def m3543a2(c: Cast) -> None:
    """The compendium prints this row's attack line with no defence at all --
    "+9 vs or (whichever is lower)" -- which is the 98-row extraction defect in
    #360. One is not invented here; the temporary hit points are the half that
    can be said."""
    c.temp_hp(10)


_M3543_FALLS = "it drops to 0 hit points"


@power(
    "m3543a3",
    level=4,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBlast(2),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d10", 5, kind=LIMITED),
    trigger=_M3543_FALLS,
    on=Trigger(Dropped, about_me, _M3543_FALLS),
)
def m3543a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(1)


@power(
    "m3543a4",
    level=4,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m3543a4(c: Cast) -> None:
    """"An enemy attacks it due to this movement" is an opportunity attack, which
    is a plain attribute on the attack events and exactly the question the
    sentence asks. The grant goes per enemy because `c.grants_advantage` names
    one beneficiary or one side and "grants combat advantage" means everybody."""
    me = c.me
    c.move(1)
    for foe in c.enemies():
        c.grants_advantage(on=me, to=foe, until=When.SONT)

    def opening(ev: AttackDeclared) -> None:
        if ev.target != me or not getattr(ev, "opportunity", False):
            return
        foe = ev.attacker
        swinger = me if c.distance(foe) <= 2 else next(
            (a for a in c.allies() if c.adjacent_to(a, foe)), None
        )
        if swinger is None:
            return
        c.grants_advantage(on=foe, to=swinger, until=When.EOT)
        c.grant_attack(swinger, on=foe)

    c.watch(
        AttackDeclared, opening, until=When.EOT, on=me, once=True,
        label=f"{c.ref} opening",
    )


@power(
    "m3543a5",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=CloseBurst(5),
    target=EACH_ALLY,
)
def m3543a5(c: Cast) -> None:
    """"+2, or +4 with combat advantage" is written as two mutually exclusive
    gates rather than as a +2 plus a gated +2: the second reading comes to +2
    forever for a typed bonus and to +6 for an untyped one, and neither is the
    card. `EACH_ALLY` puts the caster in the targeting path though `c.allies`
    leaves him out (#364), so he is skipped here."""
    mate = c.target
    if mate is None or mate == c.me:
        return
    if not c.shift(2, who=mate):
        return
    c.bonus(
        "damage", 2, on=mate, until=When.EOTNT, once=True,
        when=lambda ctx: not ctx.get("advantage"),
    )
    c.bonus(
        "damage", 4, on=mate, until=When.EOTNT, once=True,
        when=lambda ctx: bool(ctx.get("advantage")),
    )
    if c.first:
        _recharge_when_bloodied(c)


# --------------------------------------------------------------------------
# m3566
# --------------------------------------------------------------------------


@power(
    "m3566a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d10", 5),
)
def m3566a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


_M3566_LOOKS_AWAY = "an adjacent enemy it has marked shifts or attacks somebody else"


@power(
    "m3566a1",
    level=4,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d6", 2),
    trigger=_M3566_LOOKS_AWAY,
    on=(
        Trigger(MoveStart, _marked_adjacent_shifts, _M3566_LOOKS_AWAY),
        Trigger(PowerUsed, _marked_adjacent_looks_away, _M3566_LOOKS_AWAY),
    ),
)
def m3566a1(c: Cast) -> None:
    """Both halves of the printed trigger are declared: half of it looks
    finished and is wrong. The swing goes at whoever the event was about rather
    than at a target of this row's own."""
    foe = _triggering_enemy(c)
    if foe is None or c.distance(foe) > 1:
        return
    if c.strike(on=foe):
        c.hit(on=foe)
        c.slowed(on=foe, until=When.EONT)


@power(
    "m3566a2",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d10", 7, kind=LIMITED),
    dropped=("c.as_basic(charge=)",),
)
def m3566a2(c: Cast) -> None:
    """The Special -- "when charging it can use this in place of a melee basic
    attack" -- is the named gap: `c.as_basic` files a stand-in for a window and
    has no word for the charge's own."""
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m3566a3",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3566a3(c: Cast) -> None:
    """"Melee and ranged attacks" is everything that is not close or area, which
    is read off the row rather than off the blow. Who is standing beside the
    victim changes every time anybody walks, so it is a gate on the damage and
    not a bonus put on and taken off."""

    def mobbed(ctx: dict[str, Any]) -> bool:
        if _spreading_blow(ctx):
            return False
        return _crowding(c, ctx.get("target")) >= 2

    c.bonus("damage", 5, on=c.me, until=When.ENCOUNTER, when=mobbed)


# --------------------------------------------------------------------------
# m3770
# --------------------------------------------------------------------------


@power(
    "m3770a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d4", 5),
)
def m3770a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m3770a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d6", 5),
)
def m3770a1(c: Cast) -> None:
    """"Ranged 10/20" takes the normal range; the long one is a penalty the
    engine works out from the same number."""
    if c.strike():
        c.hit()


@power(
    "m3770a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=Target(
        "enemy", 1,
        label="targets an enemy it has marked",
        relation=Relation.MARKED_BY,
    ),
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d4", 5),
)
def m3770a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(3)


@power(
    "m3770a3",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ALLY,
    dropped=("Target.ident",),
)
def m3770a3(c: Cast) -> None:
    """The target line narrows to allies off this very stat block, counted by
    `Ident.ref` and marked `Target.ident` -- every creature in a fight may
    share a type word and the printed sentence is about this block, which is
    why this is not `Target.creature_kind`. `EACH_ALLY` counts the caster in
    though `c.allies` does not (#364), and a close burst does not catch its
    own user."""
    mate = c.target
    if mate is None or mate == c.me:
        return
    if _ref_of(c, mate) == _ref_of(c, c.me):
        c.shift(1, who=mate)


@power(
    "m3770a4",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.aid_another()",),
)
def m3770a4(c: Cast) -> None:
    """"+3 instead of +2 while flanking" is one extra point on top of the
    flanking the engine already grants, gated on the board rather than on a
    context key -- no modifier context carries "am I flanking". Aiding another
    is the named gap: nothing in a fight rolls it."""

    def flanking(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        return isinstance(victim, int) and flanked_by(c.world, victim, c.me)

    c.bonus("attack", 1, on=c.me, until=When.ENCOUNTER, when=flanking)


@power(
    "m3770a5",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m3770a5(c: Cast) -> None:
    """Finished and deliberately inert: the whole printed effect is an opposed
    pair of skill checks, and nothing on a board rolls either of them."""


# --------------------------------------------------------------------------
# m4117
# --------------------------------------------------------------------------


@power(
    "m4117a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d10", 4),
)
def m4117a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m4117a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 3),
)
def m4117a1(c: Cast) -> None:
    """A bare "15/30" is a thrown or ranged band; the normal range is the one
    written."""
    if c.strike():
        c.hit()


@power(
    "m4117a2",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d10", 4, kind=LIMITED),
)
def m4117a2(c: Cast) -> None:
    """"Requires a reach weapon" is not a gate -- the reach is already in the
    header and `Gear` is empty on every monster. #366."""
    if c.strike():
        c.hit()
        c.prone()


# --------------------------------------------------------------------------
# m4739
# --------------------------------------------------------------------------


@power(
    "m4739a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d10", 4),
)
def m4739a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m4739a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=UpTo(2),
    no_provoke=True,
)
def m4739a1(c: Cast) -> None:
    """The swing is the block's own slam, used rather than copied, so whatever
    that row does -- including the prone it prints -- happens here too.
    `c.landed` reads the borrowed row's result, which is what "if it hits with
    the first" asks."""
    victim = c.target
    if victim is None:
        return
    c.use_power("m4739a0", on=victim)
    if not c.landed:
        return
    if c.first:
        c.pull(1, on=victim)
    else:
        c.push(1, on=victim)


@power(
    "m4739a2",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4739a2(c: Cast) -> None:
    """`c.overrun` is the trample: `c.move` refuses an occupied square and
    reports nothing about what it passed. "Only once during this movement" is
    the set, and the slide at the end names its square because `c.slide` with a
    bare distance asks the controller for one."""
    struck: list[int] = []
    for who in c.overrun():
        if who in struck:
            continue
        struck.append(who)
        c.use_power("m4739a0", on=who)
    foe = next((f for f in c.enemies() if c.adjacent(f)), None)
    if foe is None:
        return
    sq = _free_square_beside(c, c.me)
    if sq is not None:
        c.slide(2, on=foe, to=sq)


@power(
    "m4739a3",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ZONE],
    dropped=("c.kill()",),
)
def m4739a3(c: Cast) -> None:
    """The ground it leaves behind is exact; the creature going to pieces to
    make it is the named gap, and paying it as damage is the wrong reading --
    "collapses" has no hit points in it. "Any nongoblin creature" is a type
    word, which `c.is_kind` answers, so it is a gate and not a second marker."""
    ring = c.zone({c.here}, label=c.ref, until=When.ENCOUNTER, difficult=True)

    def outsider(ctx: dict[str, Any]) -> bool:
        who = ctx.get("attacker")
        return isinstance(who, int) and not c.is_kind("goblin", who)

    c.grants_in(ring, "attack", -2, side="any", kind="untyped", when=outsider)


@power(
    "m4739a4",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4739a4(c: Cast) -> None:
    c.ignores_difficult(on=c.me)


# --------------------------------------------------------------------------
# m5082
# --------------------------------------------------------------------------


@power(
    "m5082a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 7),
    dropped=("c.grab(dc=)",),
)
def m5082a0(c: Cast) -> None:
    """The grab is laid; the printed escape DC has nowhere to go -- `c.escape`
    rolls against a number the grabber's own stats decide."""
    if c.strike():
        c.hit()
        c.grab()


@power(
    "m5082a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 5),
)
def m5082a1(c: Cast) -> None:
    """"1d8+5, or 2d8+5 against a target it is holding": the base stays in the
    header where a rescale can find it and the second die is rolled, because
    `c.damage` maxes its dice on a critical and a die added there would come out
    at its highest face every time."""
    if c.strike():
        c.hit()
        if c.target in _grabbing(c):
            c.flat(c.roll("1d8"))


@power(
    "m5082a2",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_OTHER,
    attack=Attack(vs=REF, printed=7),
    damage=Damage("2d8", 5, kind=LIMITED),
)
def m5082a2(c: Cast) -> None:
    """"Creatures in the burst" catches its own side too, which is what
    `EACH_CREATURE` says and `EACH_ENEMY` would not."""
    if c.strike():
        c.hit()
        c.slide(1)
        c.prone()


# --------------------------------------------------------------------------
# m5313
# --------------------------------------------------------------------------


@power(
    "m5313a0",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5313a0(c: Cast) -> None:
    """"Another of its own sort adjacent to the target" is counted by `Ident.ref`
    and not by a type word, which every creature in the fight may share."""
    _edge_when_mobbed(c, 1, ref=_ref_of(c, c.me))


@power(
    "m5313a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("1d8", 2, dtype=DamageType.NECROTIC),
)
def m5313a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


# --------------------------------------------------------------------------
# m5401
# --------------------------------------------------------------------------


@power(
    "m5401a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 5),
)
def m5401a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m5401a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 6, dtype=DamageType.FIRE),
)
def m5401a1(c: Cast) -> None:
    """The splash is measured from the creature struck and not from the caster,
    and it leaves the creature struck out -- it has already taken the blow."""
    if c.strike():
        c.hit()
        victim = c.target
        for foe in c.within(1, of=victim, side="enemy"):
            if foe != victim:
                c.flat(3, dtype=DamageType.FIRE, on=foe)


@power(
    "m5401a2",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=[Keyword.ACID, Keyword.IMPLEMENT],
    attack=Attack(vs=FORT, printed=7),
    damage=Damage("1d8", 6, dtype=DamageType.ACID, kind=LIMITED),
)
def m5401a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5401a3",
    level=4,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m5401a3(c: Cast) -> None:
    c.teleport(5)


_M5401_LOOKS_AWAY = "an adjacent enemy it has marked shifts or attacks somebody else"


@power(
    "m5401a4",
    level=4,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE, Keyword.TELEPORTATION],
    trigger=_M5401_LOOKS_AWAY,
    on=(
        Trigger(MoveStart, _marked_adjacent_shifts, _M5401_LOOKS_AWAY),
        Trigger(PowerUsed, _marked_adjacent_looks_away, _M5401_LOOKS_AWAY),
    ),
)
def m5401a4(c: Cast) -> None:
    """An interrupt, so the burn lands before the thing that provoked it
    resolves -- which is the printed window and not decoration."""
    foe = _triggering_enemy(c)
    if foe is not None:
        c.flat(5, dtype=DamageType.FIRE, on=foe)
    c.teleport(3)


# --------------------------------------------------------------------------
# m5411
# --------------------------------------------------------------------------


@power(
    "m5411a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d10", 7),
)
def m5411a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5411a1",
    level=4,
    usage=ENCOUNTER,
    uses=2,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d6", 7, kind=LIMITED),
)
def m5411a1(c: Cast) -> None:
    """"2/Encounter" is `uses=2` beside the encounter usage, not two rows."""
    if c.strike():
        c.hit()


@power(
    "m5411a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d10", 7),
)
def m5411a2(c: Cast) -> None:
    """"Before the attack" is an ordering and not a window: the shift is taken
    first, in the body, so an ally can step into reach of the swing that
    follows."""
    victim = c.target
    mate = next(
        (
            a
            for a in c.allies()
            if c.adjacent(a) or (victim is not None and c.adjacent_to(a, victim))
        ),
        None,
    )
    if mate is not None:
        c.shift(1, who=mate)
    if c.strike():
        c.hit()


@power(
    "m5411a3",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d10", 7, kind=LIMITED),
)
def m5411a3(c: Cast) -> None:
    """The Effect is laid whether the swing landed or not, which is what putting
    it outside the hit branch means. "Power bonus" is the word the card prints,
    so that is the `kind`."""
    if c.strike():
        c.hit()
    if c.first:
        for mate in c.within(1, side="ally"):
            c.bonus(AC, 2, on=mate, until=When.EONT, kind="power")
            c.immovable(on=mate, until=When.EONT)


@power(
    "m5411a4",
    level=4,
    usage=ENCOUNTER,
    action=MOVE,
    reach=Ranged(10),
    target=ONE_ALLY,
)
def m5411a4(c: Cast) -> None:
    """`c.extra_action` drops one action into the budget the turn is already
    spending, which is what "takes a move action as a free action" is.
    `c.grant_action` is the other thing -- it changes what an action buys -- and
    silently eats a word it does not know."""
    c.extra_action(MOVE, on=c.target)


@power(
    "m5411a5",
    level=4,
    usage=ENCOUNTER,
    uses=2,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    keywords=[Keyword.HEALING],
)
def m5411a5(c: Cast) -> None:
    """`c.surge` follows the target, because the printed line asks whose surge
    is being spent and it is not the leader's."""
    c.surge()


# --------------------------------------------------------------------------
# m5416
# --------------------------------------------------------------------------


@power(
    "m5416a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d8", 3),
)
def m5416a0(c: Cast) -> None:
    """"Until the **start** of its next turn" is `When.SONT` and not `EONT`; the
    two differ by a whole turn of the marked creature's."""
    if c.strike():
        c.hit()
        c.mark(until=When.SONT)


@power(
    "m5416a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=7),
    damage=Damage("2d8", 3),
)
def m5416a1(c: Cast) -> None:
    """Two separate sentences and so two separate effects: the fall is immediate
    and the slow carries its own saving throw."""
    if c.strike():
        c.hit()
        c.prone()
        c.slowed(until=When.SAVE_ENDS)


_M5416_STOOD = "an enemy adjacent to it stands up"


@power(
    "m5416a2",
    level=4,
    usage=AT_WILL,
    action=REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=9),
    trigger=_M5416_STOOD,
    on=Trigger(ConditionEnded, _adjacent_enemy_stood, _M5416_STOOD),
)
def m5416a2(c: Cast) -> None:
    """No damage line at all on this one -- the fall is the whole hit."""
    foe = getattr(c.trigger, "target", None)
    if foe is None or c.distance(foe) > 1:
        return
    if c.strike(on=foe):
        c.prone(on=foe)


# --------------------------------------------------------------------------
# m5429
# --------------------------------------------------------------------------


@power(
    "m5429a0",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    requires_text="while ridden by a friendly rider of 4th level or higher",
)
def m5429a0(c: Cast) -> None:
    """**No `requires=` on this trait, deliberately.** `turns.arm_traits_of`
    arms it through `dsl.use`, and `use` *does* call `usable` -- so a gate here
    does not merely go unread, it stops the trait arming at all, for the whole
    fight, on the strength of how the board happened to start. A mount is ridden
    partway through a fight as often as it starts that way, so the printed
    Requirement is asked live instead: `RelationSet` is the moment somebody
    climbs on, and whoever is already up there is handled at the end.

    `c.gains_advantage` names one beneficiary, so the grant is per rider; the
    level is read when it mounts, because that is when the printed Requirement is
    asked.
    """
    me = c.me

    def held(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        return isinstance(victim, int) and victim in _grabbing(c)

    def mount_up(rider: int) -> None:
        if _ridden_by_fourth_level(c.world, me):
            c.gains_advantage(held, until=When.ENCOUNTER, on=rider)

    def climbed(ev: RelationSet) -> None:
        # `set(RIDDEN_BY, mount, rider)`, so the mount is `source` and the
        # rider is `target` -- the direction `c.rider` reads back.
        if ev.kind_ is Relation.RIDDEN_BY and ev.source == me:
            mount_up(ev.target)

    c.watch(RelationSet, climbed, until=When.ENCOUNTER, on=me, label=f"{c.ref} saddle")
    already = c.rider()
    if already is not None:
        mount_up(already)


@power(
    "m5429a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d4", 0),
    dropped=("Target.only_grabbed",),
)
def m5429a1(c: Cast) -> None:
    """Both of the card's second numbers are the same question asked twice --
    +11 instead of +9 and 2d4+10 instead of 2d4 -- so the attack takes a `plus`
    and the damage takes a flat rider, and the base stays in the header.

    The printed target line is "one creature" and the narrowing is *conditional*:
    only while it holds somebody is it restricted to that one. `Target.relation`
    is unconditional, so declaring it here would refuse the row whenever nothing
    is grabbed -- which is the row's ordinary use -- so this is the same gap
    `m6346a2` names, and the swing is redirected in the body instead."""
    held = _grabbing(c)
    foe = c.target
    if held and foe not in held:
        foe = _restricted_to(c, 1, lambda f: f in held)
    if foe is None:
        return
    gripped = foe in held
    if c.strike(on=foe, plus=2 if gripped else 0):
        c.hit(on=foe)
        if gripped:
            c.flat(10, on=foe)
        c.grab(on=foe)


@power(
    "m5429a2",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=Target(
        "enemy", 1,
        label="targets a creature it has grabbed",
        relation=Relation.GRABBED_BY,
    ),
    keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=9),
    dropped=("c.aftereffect()",),
)
def m5429a2(c: Cast) -> None:
    """"Save ends both" is one effect carrying the slow and the burn, so the
    victim gets one throw and not two. The First Failed Saving Throw line is the
    one remaining gap: `escalate` runs on a failure but nothing routes the
    printed aftereffect through it."""
    if c.strike():
        c.condition(
            Condition.SLOWED, until=When.SAVE_ENDS,
            ongoing=(10, DamageType.POISON),
        )


# --------------------------------------------------------------------------
# m5436
# --------------------------------------------------------------------------


@power(
    "m5436a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d10", 7),
)
def m5436a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5436a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m5436a1(c: Cast) -> None:
    """`ONE_CREATURE` rather than `UpTo(2)`: the rider is the whole content of
    the row and only exists when both swings went to one creature."""
    if _both_hit(c, "m5436a0", "m5436a0"):
        c.prone()


_M5436_STOOD = "an enemy adjacent to it stands up"


@power(
    "m5436a2",
    level=4,
    usage=AT_WILL,
    action=REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=7),
    trigger=_M5436_STOOD,
    on=Trigger(ConditionEnded, _adjacent_enemy_stood, _M5436_STOOD),
)
def m5436a2(c: Cast) -> None:
    """"Shifts 3 squares to a square adjacent to the target" names a destination
    rather than a distance, and `c.shift` with a bare number asks the controller
    for one -- which on a quiet board walks the other way."""
    foe = getattr(c.trigger, "target", None)
    if foe is None or c.distance(foe) > 1:
        return
    if not c.strike(on=foe):
        return
    c.push(3, on=foe)
    sq = _step_beside(c, c.me, foe)
    if sq is not None:
        c.shift(3, to=sq)


_M5436_OPENS = "it starts its turn"


@power(
    "m5436a3",
    level=4,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5436_OPENS,
    on=Trigger(TurnStart, about_me, _M5436_OPENS),
)
def m5436a3(c: Cast) -> None:
    """Ending is not saving: none of the printed line rolls. The conditions are
    tried in the order the card names them and the save-ends sweep is the
    fallback, because an effect carrying nothing but ongoing damage names no
    condition for `carrying=` to match."""
    for condition in (
        Condition.DAZED,
        Condition.SLOWED,
        Condition.STUNNED,
        Condition.WEAKENED,
    ):
        if c.end_effect(on=c.me, carrying=condition, why=c.ref) is not None:
            return
    c.end_effect(on=c.me, save_ends=True, why=c.ref)


# --------------------------------------------------------------------------
# m5658
# --------------------------------------------------------------------------


@power(
    "m5658a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d8", 3, dtype=DamageType.FIRE),
)
def m5658a0(c: Cast) -> None:
    """The mark is printed as an **Effect**, so it is laid whether the swing
    landed or not. No adjacency clause on the sting, which is why the radius is
    wide rather than 1."""
    if c.strike():
        c.hit()
    victim = c.target
    if victim is None:
        return
    c.mark(on=victim, until=When.SONT)
    _mark_bites(
        c, victim, 5, radius=99, until=When.SONT, dtype=DamageType.FIRE
    )


@power(
    "m5658a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d4", 7, dtype=DamageType.FIRE),
)
def m5658a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


_M5658_FALLS = "it drops to 0 hit points"


@power(
    "m5658a2",
    level=4,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5658_FALLS,
    on=Trigger(Dropped, about_me, _M5658_FALLS),
)
def m5658a2(c: Cast) -> None:
    _death_throe(c)


# --------------------------------------------------------------------------
# m5669
# --------------------------------------------------------------------------


@power(
    "m5669a0",
    level=4,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5669a0(c: Cast) -> None:
    """"Has not yet acted during the encounter" is a fact about the initiative
    order and not about a creature, so the trait keeps the set itself: every
    `TurnStart` adds its actor and the gate asks whether the victim is in it.
    A ghost turn is not the creature acting."""
    acted: set[int] = set()

    def opened(ev: TurnStart) -> None:
        if not ev.ghost:
            acted.add(ev.actor)

    def untried(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        return isinstance(victim, int) and victim not in acted

    c.watch(TurnStart, opened, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} order")
    c.bonus(
        "damage", 0, dice="1d10", on=c.me, until=When.ENCOUNTER, when=untried
    )


@power(
    "m5669a1",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5669a1(c: Cast) -> None:
    """"It gains combat advantage against that enemy" is the enemy granting it,
    held as a relation naming one beneficiary rather than as a gate: the card
    names the creature that missed and nothing else about the circumstance."""
    me = c.me

    def missed(ev: Miss) -> None:
        if not _missed_me_in_melee(c.world, me, ev):
            return
        foe = getattr(ev, "attacker", None)
        if foe is not None:
            c.grants_advantage(on=foe, to=me, until=When.EONT)

    c.watch(Miss, missed, until=When.ENCOUNTER, on=me, label=f"{c.ref} riposte")


@power(
    "m5669a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 8),
)
def m5669a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5669a3",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d6", 5),
)
def m5669a3(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5669a4",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=7),
    damage=Damage("1d8", 8),
)
def m5669a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


# --------------------------------------------------------------------------
# m5755
# --------------------------------------------------------------------------


@power(
    "m5755a0",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5755a0(c: Cast) -> None:
    """`charge` is a key both modifier contexts carry, so this is a gate and not
    a pair of watches armed and disarmed around every run-in."""
    c.bonus(
        "damage", 3, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: bool(ctx.get("charge")),
    )


@power(
    "m5755a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d10", 7),
)
def m5755a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5755a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d6", 5),
)
def m5755a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


_M5755_LOOKS_AWAY = "an adjacent enemy it has marked attacks somebody else"


@power(
    "m5755a3",
    level=4,
    usage=AT_WILL,
    action=REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    damage=Damage("1d6", 3),
    trigger=_M5755_LOOKS_AWAY,
    on=Trigger(PowerUsed, _marked_adjacent_looks_away, _M5755_LOOKS_AWAY),
)
def m5755a3(c: Cast) -> None:
    """No attack roll printed: the damage simply lands, which is `c.hit` reading
    the header without a strike in front of it."""
    foe = _triggering_enemy(c)
    if foe is None or c.distance(foe) > 1:
        return
    c.hit(on=foe)
    c.prone(on=foe)


# --------------------------------------------------------------------------
# m5804
# --------------------------------------------------------------------------


@power(
    "m5804a0",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
)
def m5804a0(c: Cast) -> None:
    """"Cannot shift during that turn" is `When.SOTNT`: `EOT` is clocked on
    whoever laid the effect, so laid during the enemy's turn it would run to the
    *creature's own* turn end and hold for most of a round too long. `SOTNT` is
    clocked on the sufferer and ends as its next turn opens."""
    _starts_turn_in_aura(
        c, 1, 2, DamageType.FIRE,
        then=lambda foe: c.cannot_shift(on=foe, until=When.SOTNT),
    )


@power(
    "m5804a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 7),
)
def m5804a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5804a2",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=7),
    damage=Damage("1d6", 4, dtype=DamageType.FIRE, kind=LIMITED),
)
def m5804a2(c: Cast) -> None:
    """The pull names its square, because "to a square adjacent to it" is a
    destination and `c.pull` with a bare distance asks the controller. The
    printed recharge condition sits on top of the die rather than replacing
    it."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    held = c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS)
    sq = _free_square_beside(c, c.me)
    if sq is not None:
        c.pull(4, on=victim, to=sq)
    _recharge_while_nothing_held(c, held)


# --------------------------------------------------------------------------
# m6273
# --------------------------------------------------------------------------


@power(
    "m6273a0",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.LIGHTNING],
)
def m6273a0(c: Cast) -> None:
    """"Its sting" is the block's own lightning row, named by ref because a
    weapon's printed name is not available and would be a leak if it were.
    Watched on `DamageApplied`, which is damage that actually arrived."""
    me = c.me

    def shocked(ev: DamageApplied) -> None:
        if ev.target != me or ev.dtype is not DamageType.LIGHTNING:
            return
        c.bonus(
            "damage", 0, dice="2d6", dtype=DamageType.LIGHTNING, on=me,
            until=When.EONT,
            when=lambda ctx: ctx.get("power") == "m6273a3",
        )

    c.watch(DamageApplied, shocked, until=When.ENCOUNTER, on=me, label=f"{c.ref} charged")


@power(
    "m6273a1",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6273a1(c: Cast) -> None:
    """"Each time" and not once, so the watch is not `once=True`."""
    me = c.me

    def fed(ev: DamageApplied) -> None:
        if ev.target == me and ev.dtype is DamageType.FORCE:
            c.temp_hp(5, on=me)

    c.watch(DamageApplied, fed, until=When.ENCOUNTER, on=me, label=f"{c.ref} fed")


@power(
    "m6273a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d6", 4),
    dropped=("c.grab(dc=)",),
)
def m6273a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.grab()


@power(
    "m6273a3",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d6", 4),
)
def m6273a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.LIGHTNING, until=When.SAVE_ENDS)


# --------------------------------------------------------------------------
# m6346
# --------------------------------------------------------------------------


@power(
    "m6346a0",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6346a0(c: Cast) -> None:
    _shifts_in_aura(c, 1, 5)


@power(
    "m6346a1",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.sustain_grab()",),
)
def m6346a1(c: Cast) -> None:
    """`RelationSet` is the moment a grab is taken, and the grab relation names
    the grabber in `source`. Sustaining one is the named gap -- keeping a grab up
    is a minor action nothing announces."""
    me = c.me

    def seized(ev: RelationSet) -> None:
        if ev.kind_ is not Relation.GRABBED_BY or ev.target != me:
            return
        if ev.source in c.enemies():
            c.flat(5, on=ev.source)

    c.watch(RelationSet, seized, until=When.ENCOUNTER, on=me, label=f"{c.ref} thorns")


@power(
    "m6346a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d6", 5),
    dropped=("Target.only_grabbed", "c.grab(dc=)"),
)
def m6346a2(c: Cast) -> None:
    """"While it has a target grabbed it can bite only that target" is a target
    restriction with nowhere in `Target` to live -- a relation to the caster,
    so `Target.relation` -- and the swing is redirected to the creature it is
    holding rather than refused."""
    held = _grabbing(c)
    foe = c.target
    if held and foe not in held:
        foe = _restricted_to(c, 1, lambda f: f in held)
    if foe is None:
        return
    if c.strike(on=foe):
        c.hit(on=foe)
        c.grab(on=foe)


@power(
    "m6346a3",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MOVE,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=7),
    damage=Damage("2d8", 4, kind=LIMITED, half_on_miss=True),
)
def m6346a3(c: Cast) -> None:
    """The captive is dragged to a named square rather than a distance, and the
    trip gives it no opening -- which is the printed "does not provoke".

    **"The grab ends" is `c.cure`, not `end_effect(carrying=)`.** `carrying=`
    narrows to effects that *impose* the named condition, and `c.grab` lays a
    `Relation.GRABBED_BY` with no condition attached to the effect -- so the
    old spelling matched nothing, emitted nothing, and the printed Miss line
    did its half damage and never let go. Driven: `carrying=` changes neither
    the relation nor the condition and emits 0 events; `c.cure` clears both and
    emits 2. #407."""
    foe = c.target
    if c.strike():
        c.hit()
        c.move(c.speed_of())
        _hauls_the_grabbed(c, foe)
    else:
        c.hit(half=True)
        c.cure(Condition.GRABBED)
    if c.first:
        _recharge_when_bloodied(c)


_M6346_RIDER_HIT = "its rider hits an enemy with a melee attack"


def _my_rider_landed(world: World, me: int, ev: Hit) -> bool:
    """"Its rider hits an enemy with a melee attack."

    The mount's rider is a relation and not a side, so the attacker is compared
    against it directly -- and `targets`, not `sources`: the relation is stored
    `set(RIDDEN_BY, mount, rider)`. The reach comes off the row and not off
    anything the event carries.
    """
    who = getattr(ev, "attacker", None)
    victim = getattr(ev, "target", None)
    if who is None or victim is None:
        return False
    if who not in world.relations.targets(Relation.RIDDEN_BY, me):
        return False
    if _reach_kind(getattr(ev, "power", "")) != "melee":
        return False
    return victim in enemies(world, me)


@power(
    "m6346a4",
    level=4,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M6346_RIDER_HIT,
    on=Trigger(Hit, _my_rider_landed, _M6346_RIDER_HIT),
)
def m6346a4(c: Cast) -> None:
    victim = getattr(c.trigger, "target", None)
    if victim is not None:
        c.damage("1d6", on=victim)


# --------------------------------------------------------------------------
# m6600
# --------------------------------------------------------------------------


@power(
    "m6600a0",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6600a0(c: Cast) -> None:
    """Six gated modifiers rather than six laid and lifted by a `Bloodied`
    watch: the creature can be healed back above the line and a watch would
    leave the penalties standing."""
    me = c.me

    def hurt(_ctx: dict[str, Any]) -> bool:
        return c.bloodied(me)

    c.penalty("attack", 2, on=me, until=When.ENCOUNTER, when=hurt)
    c.penalty(AC, 2, on=me, until=When.ENCOUNTER, when=hurt)
    c.penalty(FORT, 2, on=me, until=When.ENCOUNTER, when=hurt)
    c.penalty(REF, 2, on=me, until=When.ENCOUNTER, when=hurt)
    c.penalty(WILL, 2, on=me, until=When.ENCOUNTER, when=hurt)
    c.bonus("damage", 5, on=me, until=When.ENCOUNTER, when=hurt)


@power(
    "m6600a1",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6600a1(c: Cast) -> None:
    """Underwater is a property of the encounter and not of anybody in it, and
    it is asked as the turn opens rather than once when the trait arms -- the
    answer is False in an ordinary fight and True in the one the line is for."""
    me = c.me

    def opened(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me or not c.terrain("aquatic"):
            return
        _unseen_until_it_stirs(c)

    c.watch(TurnStart, opened, until=When.ENCOUNTER, on=me, label=f"{c.ref} murk")


@power(
    "m6600a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 8),
    requires=_holding_fewer_than_two,
    requires_text="must not already have two creatures grabbed",
    dropped=("c.grab(dc=)",),
)
def m6600a2(c: Cast) -> None:
    """The Special is a Requirement in everything but name, so it is asked as an
    entry gate -- a body that looks and returns is a standard action the policy
    spends on nothing."""
    if len(_grabbing(c)) >= 2:
        return
    if c.strike():
        c.hit()
        c.grab()


@power(
    "m6600a3",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
)
def m6600a3(c: Cast) -> None:
    """`UpTo(2)` lets the two swings be spread; `_twice` adds the second when
    they were not, so a lone enemy is clawed twice by a card that says twice."""
    _twice(c, "m6600a2")


@power(
    "m6600a4",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
    attack=Attack(vs=FORT, printed=7),
    damage=Damage("4d8", 18, half_on_miss=True),
    requires=_holding_somebody,
    requires_text="targets each creature it has grabbed",
)
def m6600a4(c: Cast) -> None:
    """"Each creature grabbed by it" is a set the relation knows and `Target`
    cannot express at all, so the row takes no target of its own and swings once
    per captive."""
    for foe in _grabbing(c):
        if c.strike(on=foe):
            c.hit(on=foe)
        else:
            c.hit(on=foe, half=True)


# --------------------------------------------------------------------------
# m6636
# --------------------------------------------------------------------------


@power(
    "m6636a0",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("spec.stat_block()",),
)
def m6636a0(c: Cast) -> None:
    """The spec names the ring this trait reads by **this row's own ref**, so the
    block that would give its radius is not in the extract -- aura 1 is written
    and the radius is the named gap. The extra die is a gate on the damage, since
    whether the victim is inside changes every time anybody moves."""
    ring = f"{c.ref} aura"
    c.aura(1, label=ring, until=When.ENCOUNTER, on=c.me)

    def inside(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        return isinstance(victim, int) and c.in_my_aura(victim, label=ring)

    c.bonus("damage", 0, dice="1d6", on=c.me, until=When.ENCOUNTER, when=inside)


@power(
    "m6636a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 8),
)
def m6636a1(c: Cast) -> None:
    """"Until it attacks it or leaves the ring, or until the end of the
    encounter" is three endings and only the last is a `When`, so the slow is
    held to the encounter and the other two are watches that lift it."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    held = c.slowed(on=victim, until=When.ENCOUNTER)
    if held is None:
        return
    me, ref = c.me, c.ref

    def turned(ev: PowerUsed) -> None:
        if ev.actor == victim and _is_attack(ev.power) and me in ev.targets:
            c.world.effects.end(held, "it attacked")

    def walked(ev: MoveStart) -> None:
        if getattr(ev, "actor", None) != victim:
            return
        if distance_between(c.world, me, victim) > 1:
            c.world.effects.end(held, "it left the ring")

    c.watch(PowerUsed, turned, until=When.ENCOUNTER, on=me, once=True, label=f"{ref} {victim}")
    c.watch(MoveStart, walked, until=When.ENCOUNTER, on=me, once=True, label=f"{ref} out {victim}")


# --------------------------------------------------------------------------
# m936
# --------------------------------------------------------------------------


@power(
    "m936a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d4", 2),
)
def m936a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.pull(1)


@power(
    "m936a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("1d6", 2),
)
def m936a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, until=When.SAVE_ENDS)


@power(
    "m936a2",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("1d6", 3, kind=LIMITED),
    dropped=("spec.stat_block()",),
)
def m936a2(c: Cast) -> None:
    """"Until the target saves" is the target's clock and not the caster's, so
    the ban is held to the encounter and lifted by that creature's own
    successful throw. The aura the line also takes away is a block the extract
    does not carry, which is the named gap."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    c.stunned(on=victim, until=When.SAVE_ENDS)
    gone = c.forbid("m936a1", on=c.me, until=When.ENCOUNTER)
    if gone is None:
        return

    def threw(ev: SavingThrow) -> None:
        if ev.actor == victim and ev.saved:
            c.world.effects.end(gone, "the target saved")

    c.watch(
        SavingThrow, threw, until=When.ENCOUNTER, on=c.me, once=True,
        label=f"{c.ref} restored",
    )


@power(
    "m936a3",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    attack=Attack(vs=REF, printed=9),
    damage=Damage("2d6", 3, kind=LIMITED),
)
def m936a3(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m936a4",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m936a4(c: Cast) -> None:
    """A trait and not the minor action the database files it as: a cheaper shift
    is a standing line in the action menu, which `actions.legal` reads back, and
    not something a creature spends its turn switching on."""
    c.shift_as(MINOR, 1, on=c.me, until=When.ENCOUNTER)


@power(
    "m936a5",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m936a5(c: Cast) -> None:
    """`query.defence` is handed the attack context, so "against traps" is read
    off the attacker in the gate rather than by arming and disarming a bonus
    around every swing."""
    me = c.me
    c.bonus(AC, 2, on=me, until=When.ENCOUNTER, when=lambda ctx: _from_a_trap(c, ctx))
    c.bonus(FORT, 2, on=me, until=When.ENCOUNTER, when=lambda ctx: _from_a_trap(c, ctx))
    c.bonus(REF, 2, on=me, until=When.ENCOUNTER, when=lambda ctx: _from_a_trap(c, ctx))
    c.bonus(WILL, 2, on=me, until=When.ENCOUNTER, when=lambda ctx: _from_a_trap(c, ctx))
