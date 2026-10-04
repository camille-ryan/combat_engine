"""Monster abilities, level 3, soldiers.

Forty-eight stat blocks, 170 rows. Nine more level 3 soldiers print no
ability at all -- m277, m2799, m291, m2979, m298, m3031, m416, m4851 and
m5032 -- so there is nothing to decorate for them and they are absent rather
than skipped.

The conventions are the ones `level_01` and `level_02` settled, and the
shared shapes are imported rather than written again: eleven helpers come
from the four level 3 files that landed before this one and from the two
earlier soldier batches, because a soldier's vocabulary is the same at every
level and a second copy of a predicate is a second thing to get wrong.

What is decided here, once, for forty-eight blocks:

* numbers load from `game.db` -- the attack line is written exactly as
  printed (`Attack(vs=AC, printed=8)`) and the damage line goes in the header
  as data, so an MM1 block can be rescaled to MM3 maths later;
* a **trait** is a row that costs no action, has no target, and arms the
  watches that hold it for the rest of the fight. `turns` uses every such row
  once at the start of the encounter. Several rows here are *filed* as
  standard actions and are plainly traits -- a standing bonus to AC is not
  something a creature spends its turn on -- and those are written
  `action=ActionType.NONE` with the printed usage left alone;
* a printed range of "15/30" takes the **normal** range;
* a printed Requirement naming the creature's own kit -- a shield, a bastard
  sword, a flail -- is **not** a gate. `Gear` is empty on every monster, so a
  `c.wielding` test is false in every fight rather than only on a bare board,
  which would make a working row look like a rule that never applies. #366.

A soldier's mark is the thing to get right three times over:

* half of these blocks print it as an **Effect** rather than inside the Hit,
  so it is laid whether the swing landed or not;
* "until the end of its next turn" is `When.EONT` and "until the **start** of
  its next turn" is `When.SONT`, and two blocks here print the second;
* the rows that punish a marked enemy for looking elsewhere answer
  `PowerUsed`, which fires once per use and carries the whole target list,
  rather than `AttackDeclared`, which is announced once per target and would
  pay out twice for one burst. The rows that punish it for *shifting* answer
  `MoveStart`, because by `MoveEnd` the enemy has left and "adjacent to it"
  is false precisely when the row should fire.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_01.soldiers_sa import _my_ward_attacked
from combat_engine.content.monsters.level_02.skirmishers_sa import (
    _aura_holds,
    _until_escape,
)
from combat_engine.content.monsters.level_02.soldiers_sa import (
    _aquatic_edge,
    _crit_drops_it,
    _holding_nobody,
    _is_attack,
    _marked_foe_looks_away,
    _pinned_enemy_in_reach,
    _ref_of,
    _save_ends_on_me,
    _square_of,
    _step_into_vacated,
)
from combat_engine.content.monsters.level_03.artillery_sa import _death_throe
from combat_engine.content.monsters.level_03.brutes_sa import _both_hit, _press
from combat_engine.content.monsters.level_03.lurkers_sa import _restricted_to
from combat_engine.content.monsters.level_03.skirmishers_sa import (
    _enemy_stepped_beside,
    _has_the_drop,
    _reachable,
    _recharge_when_bloodied,
    _shift_up_to,
    _shoved_by_hand,
    _step_beside,
    _while_bloodied,
)
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
    CloseBlast,
    CloseBurst,
    Condition,
    Damage,
    DamageType,
    Effect,
    Health,
    Keyword,
    Melee,
    Ranged,
    Relation,
    Size,
    Target,
    UpTo,
    Usage,
    When,
    World,
    power,
)
from combat_engine.engine.events import (
    AdjacencyGained,
    AttackDeclared,
    AttackRolled,
    Bloodied,
    ConditionApplied,
    Dropped,
    EffectApplied,
    ForcedMove,
    Hit,
    Miss,
    MoveStart,
    PowerUsed,
    TurnStart,
    ZoneExited,
)
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import (
    distance_between,
    has_combat_advantage,
    is_,
    team,
)
from combat_engine.engine.triggers import Trigger, about_me, both, by_me, by_melee, targets_me

#: Everything a shove-and-step row may legally push. "The target, if Large or
#: smaller" is a size restriction on the *push*, not on the targeting, so it
#: is read off the victim rather than written into `Target`.
_SHOVEABLE = (Size.TINY, Size.SMALL, Size.MEDIUM, Size.LARGE)

#: What "grabbed, restrained, or immobilized" means, as a set to test against.
_HELD = (Condition.GRABBED, Condition.RESTRAINED, Condition.IMMOBILIZED)

#: What "helpless or unconscious" means. `HELPLESS` is the general word and
#: `UNCONSCIOUS` is one way of being it; a card naming both means either.
_SENSELESS = (Condition.HELPLESS, Condition.UNCONSCIOUS)


# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------


def _opportunity(ctx: dict[str, Any]) -> bool:
    """Is the blow being looked up an opportunity attack?

    `opportunity` is in both modifier contexts for exactly this -- see
    `resolve.attack` -- so a rider on one is a gate and not a pair of watches
    armed and disarmed around every swing.
    """
    return bool(ctx.get("opportunity"))


def _opportunity_edge(c: Cast, bonus: int, dice: str) -> None:
    """"When making an opportunity attack it gains +N to the attack roll and
    deals an extra <dice> damage." Three blocks here print it verbatim.

    Two modifiers rather than one: the attack bonus and the extra die are
    read out of different contexts, and `dice=` is how a bonus carries a roll
    instead of a number.
    """
    c.bonus("attack", bonus, on=c.me, until=When.ENCOUNTER, when=_opportunity)
    c.bonus("damage", 0, dice=dice, on=c.me, until=When.ENCOUNTER, when=_opportunity)


def _slowing_aura(c: Cast, radius: int = 1) -> None:
    """"Any enemy that starts its turn in the aura is slowed until the start
    of its next turn." Three swarm-ish blocks here print it.

    Who is inside is asked as the turn opens rather than kept as a list: the
    aura travels with the creature and a stored membership is stale the moment
    either of them moves. `When.SOTNT` and not `SONT` -- "its next turn" is
    the enemy's, and the two differ by a whole round here.
    """
    me = c.me
    c.aura(radius, label=f"{c.ref} aura", until=When.ENCOUNTER, on=me)

    def clung(ev: TurnStart) -> None:
        if ev.actor == me or ev.ghost:
            return
        if team(c.world, ev.actor) is team(c.world, me):
            return
        if distance_between(c.world, me, ev.actor) > radius:
            return
        c.slowed(on=ev.actor, until=When.SOTNT)

    c.watch(TurnStart, clung, until=When.ENCOUNTER, on=me, label=f"{c.ref} slow")


def _mark_bites(
    c: Cast,
    victim: int,
    amount: int,
    *,
    radius: int,
    until: When,
    dtype: DamageType = DamageType.UNTYPED,
    then: Any = None,
) -> None:
    """"Until the end of its next turn, if **the target** is adjacent to it and
    attacks without including it, the target takes N damage."

    The narrower cousin of `_punish_looking_away`: that one watches every
    adjacent enemy for the rest of the fight, and this one watches the single
    creature this swing named, for one round. `PowerUsed` for the same reason
    -- it fires once per use and carries the whole target list, where
    `AttackDeclared` is announced once per target and would charge a burst
    once for every creature it caught.
    """
    me, ref = c.me, c.ref

    def sting(ev: PowerUsed) -> None:
        if ev.actor != victim or not _is_attack(ev.power):
            return
        if distance_between(c.world, me, victim) > radius or me in ev.targets:
            return
        c.flat(amount, dtype=dtype, on=victim)
        if then is not None:
            then(victim)

    c.watch(PowerUsed, sting, until=until, on=me, label=f"{ref} {victim}")


def _marked_adjacent_shifts(world: World, me: int, ev: Any) -> bool:
    """"An enemy adjacent to it and marked by it shifts."

    `MoveStart`: by `MoveEnd` the enemy has gone and `distance_between` is
    false precisely when the row should have fired.
    """
    actor = getattr(ev, "actor", None)
    if actor is None or actor == me or getattr(ev, "kind_", "") != "shift":
        return False
    if not world.relations.holds(Relation.MARKED_BY, me, actor):
        return False
    return distance_between(world, me, actor) <= 1


def _marked_shifts(world: World, me: int, ev: Any) -> bool:
    """"A creature marked by it shifts" -- no adjacency clause on this one."""
    actor = getattr(ev, "actor", None)
    if actor is None or actor == me or getattr(ev, "kind_", "") != "shift":
        return False
    return world.relations.holds(Relation.MARKED_BY, me, actor)


def _adjacent_enemy_shifts(world: World, me: int, ev: Any) -> bool:
    """"An enemy adjacent to it shifts." Marked or not."""
    actor = getattr(ev, "actor", None)
    if actor is None or actor == me or getattr(ev, "kind_", "") != "shift":
        return False
    if team(world, actor) is team(world, me):
        return False
    return distance_between(world, me, actor) <= 1


def _adjacent_foe_looks_away(world: World, me: int, ev: Any) -> bool:
    """"An enemy adjacent to it makes an attack that does not include it."

    The same shape as `_marked_foe_looks_away` with adjacency in place of the
    mark, which is what two blocks here print instead.
    """
    actor = getattr(ev, "actor", None)
    if actor is None or actor == me or not _is_attack(getattr(ev, "power", "")):
        return False
    if team(world, actor) is team(world, me):
        return False
    if distance_between(world, me, actor) > 1:
        return False
    return me not in getattr(ev, "targets", ())


def _my_captive_looks_away(world: World, me: int, ev: Any) -> bool:
    """"An enemy it is grabbing uses an attack power that does not include it."""
    actor = getattr(ev, "actor", None)
    if actor is None or not _is_attack(getattr(ev, "power", "")):
        return False
    if actor not in world.relations.targets(Relation.GRABBED_BY, me):
        return False
    return me not in getattr(ev, "targets", ())


def _attacks_me_with_advantage(world: World, me: int, ev: AttackDeclared) -> bool:
    """"An enemy attacks it and has combat advantage against it."

    Asked of the board at declaration, before the roll: `ev.result.advantage`
    is the right question *after* the fact and there is no result yet here,
    and the whole point of the row is to take the advantage away before it is
    counted.
    """
    if ev.target != me or ev.attacker == me:
        return False
    if team(world, ev.attacker) is team(world, me):
        return False
    return has_combat_advantage(world, ev.attacker, me)


def _ally_beside_hit(world: World, me: int, ev: Hit) -> bool:
    """"An ally adjacent to it is hit by an attack."""
    victim = getattr(ev, "target", None)
    if victim is None or victim == me:
        return False
    if team(world, victim) is not team(world, me):
        return False
    return distance_between(world, me, victim) <= 1


def _ally_beside_attacked_low(world: World, me: int, ev: AttackDeclared) -> bool:
    """"An adjacent ally is attacked against AC or Reflex."

    Declared on the **announcement** and not on the landing: an interrupt on
    `AttackDeclared` runs before the roll is judged, and that is the only
    window in which raising a defence can change the attack that provoked it.
    The printed "is hit" is the half that is dropped on the row below.
    """
    victim = ev.target
    if victim == me or team(world, victim) is not team(world, me):
        return False
    if ev.vs not in (AC, REF):
        return False
    return distance_between(world, me, victim) <= 1


def _ally_beside_first_bloodied(world: World, me: int, ev: Bloodied) -> bool:
    """"An ally adjacent to it is first bloodied." `Bloodied` is emitted once
    per creature, so "first" needs nothing said about it."""
    if ev.actor == me or team(world, ev.actor) is not team(world, me):
        return False
    return distance_between(world, me, ev.actor) <= 1


def _kin_ally_shoved(word: str) -> Any:
    """"An ally of its own sort within 5 squares is pushed, pulled or slid."

    `ForcedMove` names the creature being moved in `target` and carries no
    `actor` at all, so `about_me` is false on it forever and the subject is
    read by hand.
    """

    def shoved(world: World, me: int, ev: ForcedMove) -> bool:
        mate = ev.target
        if mate == me or team(world, mate) is not team(world, me):
            return False
        if word and not _is_kind(world, mate, word):
            return False
        return distance_between(world, me, mate) <= 5

    return shoved


def _is_kind(world: World, who: int, word: str) -> bool:
    """`Cast.is_kind` for a trigger predicate, which runs before any `Cast`
    exists. `Ident` carries only the ref, the book and the role -- the type
    words are on the stat block, which is what `is_kind` goes and reads."""
    return Cast(world=world, me=who, ref="").is_kind(word, on=who)


def _hit_me_from_within(radius: int) -> Any:
    """"An enemy within N squares of it hits it with an attack."

    `enemy_within` reads the event's `actor`, which an attack does not carry
    -- the attacker is in `attacker` -- so the distance is measured here.
    """

    def struck(world: World, me: int, ev: Hit) -> bool:
        who = getattr(ev, "attacker", None)
        if who is None or getattr(ev, "target", None) != me:
            return False
        if team(world, who) is team(world, me):
            return False
        return distance_between(world, me, who) <= radius

    return struck


def _marked_by_me_in_reach(world: World, eid: int) -> bool:
    """The printed target line "marked target only", as an entry gate.

    `Target` filters on side, count, size and what is in hand and on nothing a
    creature is *suffering*, so the narrowing cannot live there. `dsl.usable`
    is handed `(world, eid)` and the caster is all it knows, so the question
    has to be asked from this end as well as in the body. #361.
    """
    return _reachable(
        world, eid, 1, lambda foe: world.relations.holds(Relation.MARKED_BY, eid, foe)
    )


def _held_in_reach(world: World, eid: int) -> bool:
    """"Grabbed, restrained, or immobilized targets only", as an entry gate."""
    return _reachable(
        world, eid, 2, lambda foe: any(is_(world, foe, held) for held in _HELD)
    )


def _senseless_in_reach(world: World, eid: int) -> bool:
    """"Targets a helpless or unconscious creature", as an entry gate."""
    return _reachable(
        world, eid, 1, lambda foe: any(is_(world, foe, out) for out in _SENSELESS)
    )


def _slowed_in_reach(world: World, eid: int) -> bool:
    """"One slowed creature", as an entry gate."""
    return _reachable(world, eid, 1, lambda foe: is_(world, foe, Condition.SLOWED))


def _grabbed_by_me_in_reach(world: World, eid: int) -> bool:
    """"One creature grabbed by it", as an entry gate."""
    targets = world.relations.targets(Relation.GRABBED_BY, eid)
    return any(distance_between(world, eid, foe) <= 1 for foe in targets)


def _in_the_water_empty_handed(world: World, eid: int) -> bool:
    """"It must be in water at least 1 square deep, and must not have a
    creature grabbed."

    The terrain half is a property of the encounter rather than of anybody in
    it -- `c.terrain`'s store, read from this end because `requires=` is handed
    `(world, eid)` and no `Cast`. On a dry board the row is simply not offered,
    which is what the printed Requirement means.
    """
    wet = {"aquatic", "water"} & set(getattr(world, "terrain", frozenset()))
    return bool(wet) and _holding_nobody(world, eid)


def _shoveable(c: Cast, victim: int | None) -> bool:
    return victim is not None and c.size_of(on=victim) in _SHOVEABLE


def _shove_and_step(c: Cast, squares_: int = 1) -> None:
    """"It pushes the target 1 square and can then shift into the square the
    target vacated." Five blocks here print it.

    The square is named rather than left to the controller, which on a quiet
    board walks the other way; nothing happens when the shove failed.
    """
    victim = c.target
    if victim is None:
        return
    was = _square_of(c, victim)
    c.push(squares_, on=victim)
    _step_into_vacated(c, was)


def _crowding(c: Cast, victim: int | None) -> int:
    """How many of its allies are beside the victim -- a "+1 per ally" roll."""
    if victim is None:
        return 0
    return len([a for a in c.within(1, of=victim, side="ally") if a != c.me])


def _edge_when_mobbed(c: Cast, least: int, ref: str = "") -> None:
    """"It gains combat advantage against a target adjacent to N or more of
    its allies." `ref` narrows the count to its own sort where the card does.

    A gate rather than a standing bonus: who is beside the victim changes
    every time anybody moves, and `has_combat_advantage` is worked out from
    the board as the attack is rolled.
    """

    def outnumbered(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        if victim is None:
            return False
        beside = [a for a in c.within(1, of=victim, side="ally") if a != c.me]
        if ref:
            beside = [a for a in beside if _ref_of(c, a) == ref]
        return len(beside) >= least

    c.gains_advantage(outnumbered, until=When.ENCOUNTER, on=c.me)


def _shoulder_to_shoulder(c: Cast, bonus: int, *, ref: str = "", minion: bool = False) -> None:
    """"+N to AC while at least one ally is adjacent to it", with the two
    narrowings the cards here print: its own sort, and a minion.

    Gated rather than laid, because who is standing beside it changes every
    time anybody moves. Untyped: a stat block prints a bare "+2 bonus", and
    `kind=` is only ever the word the card prints.
    """

    def beside(_ctx: dict[str, Any]) -> bool:
        for mate in c.within(1, side="ally"):
            if ref and _ref_of(c, mate) != ref:
                continue
            if minion and not c.is_minion(mate):
                continue
            return True
        return False

    c.bonus(AC, bonus, on=c.me, until=When.ENCOUNTER, when=beside)


def _secondary(c: Cast, printed: int, vs: Any, victim: int) -> bool:
    """A Secondary Attack line, which has no ref of its own to live in.

    The printed total is taken back to a bonus the same way the header's
    `Attack(printed=)` is -- `scaling.trim` is the one place that knows how.
    """
    return bool(c.attack(c.world.scaling.trim(printed, c.level), vs, on=victim))


# --------------------------------------------------------------------------
# m1051
# --------------------------------------------------------------------------


@power(
    "m1051a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d10", 4),
)
def m1051a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1051a1",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1051a1(c: Cast) -> None:
    """The mark is printed as a trait on this block rather than inside the
    attack, so it is armed once and reads every hit the weapon lands. The
    swing it names is the block's own at-will, which is what "with his
    greatsword" can be compared against without a name."""
    me, ref = c.me, c.ref

    def landed(ev: Hit) -> None:
        if ev.attacker == me and ev.power == "m1051a0":
            c.mark(on=ev.target, until=When.EONT)

    c.watch(Hit, landed, until=When.ENCOUNTER, on=me, label=f"{ref} mark")


# --------------------------------------------------------------------------
# m1060
# --------------------------------------------------------------------------


@power(
    "m1060a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 2),
)
def m1060a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


_M1060_HIT_IN_MELEE = "it is hit by a melee attack"


@power(
    "m1060a1",
    level=3,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M1060_HIT_IN_MELEE,
    on=Trigger(Hit, both(targets_me, by_melee), _M1060_HIT_IN_MELEE),
)
def m1060a1(c: Cast) -> None:
    """The swing goes back at whoever landed the blow, which is what "make a
    basic attack" means on a row triggered by being hit."""
    killer = getattr(c.trigger, "attacker", None)
    if killer is not None and c.distance(killer) <= 1:
        c.basic(on=killer)


@power(
    "m1060a2",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1060a2(c: Cast) -> None:
    _opportunity_edge(c, 2, "1d6")


# --------------------------------------------------------------------------
# m1122
# --------------------------------------------------------------------------


@power(
    "m1122a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 5),
)
def m1122a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m1122a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=4),
    damage=Damage("1d10", 1),
)
def m1122a1(c: Cast) -> None:
    """"Ranged 20/40" takes the normal range; the long one is a penalty the
    engine applies from the same number."""
    if c.strike():
        c.hit()


@power(
    "m1122a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d8", 1),
)
def m1122a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1122a3",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 5),
)
def m1122a3(c: Cast) -> None:
    """"If Large or smaller" is read off the victim, not written into
    `Target`: the restriction is on what the shove may move and not on what
    the row may be aimed at, and a Huge creature is a legal target that
    simply does not budge. The printed shield Requirement is not a gate --
    `Gear` is empty on every monster. #366."""
    if not c.strike():
        return
    c.hit()
    if _shoveable(c, c.target):
        _shove_and_step(c)
    c.mark(until=When.EONT)


@power(
    "m1122a4",
    level=3,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d8", 5, kind=LIMITED),
)
def m1122a4(c: Cast) -> None:
    """"Marked and slowed" as two calls and not one `c.condition` carrying
    both: only `c.mark` sets the MARKED_BY relation, and every row that reads
    "an enemy marked by it" asks the relation and not the condition -- so a
    mark laid as a bare condition is one no reprisal row can ever see. Two
    effects cost nothing here because both run to a fixed clock; it would
    matter only for a save-ends pair, where it would buy the victim two
    saves."""
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)
        c.slowed(until=When.EONT)


_M1122_PRESSED = "an enemy attacks it with combat advantage"


@power(
    "m1122a5",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M1122_PRESSED,
    on=Trigger(AttackDeclared, _attacks_me_with_advantage, _M1122_PRESSED),
)
def m1122a5(c: Cast) -> None:
    """The advantage is worked out inside `query.has_combat_advantage` after
    the interrupt window closes, so a modifier laid here is read by the very
    attack that triggered the row -- which is the whole of "cancels the
    combat advantage she was about to grant". `c.no_advantage` defaults to the
    caster, which is right here."""
    c.no_advantage(until=When.EOT)


# --------------------------------------------------------------------------
# m1127
# --------------------------------------------------------------------------


@power(
    "m1127a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d4", 4),
)
def m1127a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1127a1",
    level=3,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
    requires=_while_bloodied,
    requires_text="usable only while bloodied",
)
def m1127a1(c: Cast) -> None:
    """The heal is a flat printed number and not a surge: a monster spends one
    only when its row says so, and this one says 11 hit points."""
    foe = next(iter(_press(c, 2)), None)
    if foe is not None:
        c.basic(on=foe)
    c.heal(11, on=c.me)


_M1127_SHOVED = "an ally of its own sort within 5 squares is forcibly moved"


@power(
    "m1127a2",
    level=3,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M1127_SHOVED,
    on=Trigger(ForcedMove, _kin_ally_shoved("orc"), _M1127_SHOVED),
)
def m1127a2(c: Cast) -> None:
    """Filed as a move action by the extractor and printed as an immediate
    reaction; the printed line wins. `ForcedMove` names the creature being
    moved in `target` and carries no `actor`, so the ally is read from there."""
    mate = getattr(c.trigger, "target", None)
    if mate is not None:
        c.slide(1, on=mate)


# --------------------------------------------------------------------------
# m1130
# --------------------------------------------------------------------------


@power(
    "m1130a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d10", 4),
)
def m1130a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m1130a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d10", 4),
)
def m1130a1(c: Cast) -> None:
    """The printed bastard-sword Requirement is not a gate: `Gear` is empty on
    every monster, so a `c.wielding` test is false in every fight. #366."""
    if not c.strike():
        return
    c.hit()
    _shove_and_step(c)
    c.mark(until=When.EONT)


_M1130_MATE_BLED = "an adjacent ally is first bloodied"


@power(
    "m1130a2",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d10", 4, kind=LIMITED),
    trigger=_M1130_MATE_BLED,
    on=Trigger(Bloodied, _ally_beside_first_bloodied, _M1130_MATE_BLED),
)
def m1130a2(c: Cast) -> None:
    """The card names no victim, so the swing goes at whatever is in reach --
    the one reading that is not a no-op on a board where the ally who bled is
    not the creature standing next to this one."""
    foe = next(iter(_press(c)), None)
    if foe is None:
        return
    was = _square_of(c, foe)
    if c.strike(on=foe):
        c.hit(on=foe)
        c.push(1, on=foe)
        _step_into_vacated(c, was)


@power(
    "m1130a3",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1130a3(c: Cast) -> None:
    """"+2 to saving throws against ongoing effects while adjacent to an
    ally." Both halves are in the gate: the save context carries `ongoing`,
    and who is standing beside it changes every time anybody moves."""

    def braced(ctx: dict[str, Any]) -> bool:
        return bool(ctx.get("ongoing")) and bool(c.within(1, side="ally"))

    c.bonus("save", 2, on=c.me, until=When.ENCOUNTER, when=braced)


# --------------------------------------------------------------------------
# m115726
# --------------------------------------------------------------------------


@power(
    "m115726a0",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.ignores_difficult(when=)",),
)
def m115726a0(c: Cast) -> None:
    """"Whenever it **shifts**" is the narrowing nothing can say: the
    difficult-terrain exemption is a standing property with no gate, so this
    creature walks through brambles as freely as it steps through them."""
    c.ignores_difficult(on=c.me, until=When.ENCOUNTER)


@power(
    "m115726a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d8", 7),
)
def m115726a1(c: Cast) -> None:
    """The mark is an **Effect**, so it is laid whether the swing landed."""
    if c.strike():
        c.hit()
    c.mark(until=When.EONT)


@power(
    "m115726a2",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d8", 7, kind=LIMITED, half_on_miss=True),
)
def m115726a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized(until=When.EONT)
    else:
        c.hit(half=True)
        c.slowed(until=When.EONT)


_M115726_ROLLED = "it makes an attack roll"


@power(
    "m115726a3",
    level=3,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M115726_ROLLED,
    on=Trigger(AttackRolled, by_me, _M115726_ROLLED),
)
def m115726a3(c: Cast) -> None:
    """"Uses the second result" is `keep="new"`, even when it is worse."""
    c.reroll_attack(keep="new")


_M115726_LOOKED_AWAY = "an adjacent enemy marked by it shifts or attacks without including it"


@power(
    "m115726a4",
    level=3,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d8", 7),
    trigger=_M115726_LOOKED_AWAY,
    on=(
        Trigger(MoveStart, _marked_adjacent_shifts, "an adjacent marked enemy shifts"),
        Trigger(PowerUsed, _marked_foe_looks_away, "a marked enemy attacks without it"),
    ),
)
def m115726a4(c: Cast) -> None:
    """One printed Trigger line naming two different events, so both are
    declared -- declaring half of it looks finished and is wrong. The
    immobilisation runs to the end of *the enemy's* turn, which is the turn
    this interrupt is resolving inside, so `When.EOT`."""
    foe = getattr(c.trigger, "actor", None)
    if foe is None or c.distance(foe) > 1:
        return
    if c.strike(on=foe):
        c.hit(on=foe)
        c.immobilized(on=foe, until=When.EOT)


# --------------------------------------------------------------------------
# m115786
# --------------------------------------------------------------------------


@power(
    "m115786a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d10", 5),
)
def m115786a0(c: Cast) -> None:
    """"Until the **start** of its next turn" is `When.SONT` and not `EONT`;
    the two differ by a whole turn and this block prints the shorter one."""
    if c.strike():
        c.hit()
        c.mark(until=When.SONT)


@power(
    "m115786a1",
    level=3,
    usage=AT_WILL,
    action=MOVE,
    reach=CloseBurst(1),
    target=Target(side="ally", everyone=True),
)
def m115786a1(c: Cast) -> None:
    """`EACH_ALLY` puts the caster in the targeting path even though
    `c.allies()` leaves it out (#364), which here is convenient: the printed
    line moves the creature *and* each ally, so the caster's own step is the
    pass where it is its own target. "The target must shift to a square
    adjacent to it" names a destination rather than a distance, and a target
    with no such square free simply does not move."""
    mate = c.target
    if mate is None:
        return
    if mate == c.me:
        c.shift(1)
        return
    sq = _step_beside(c, mate, c.me)
    if sq is not None:
        c.shift(1, who=mate, to=sq)
    if c.first and c.me not in c.targets:
        c.shift(1)


_M115786_MATE_HIT = "an adjacent ally is hit by an attack against AC or Reflex"


@power(
    "m115786a2",
    level=3,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=CloseBurst(1),
    target=NO_TARGET,
    trigger=_M115786_MATE_HIT,
    on=Trigger(AttackDeclared, _ally_beside_attacked_low, _M115786_MATE_HIT),
    dropped=("c.raise_defence(ev=)",),
)
def m115786a2(c: Cast) -> None:
    """"+2 to AC and Reflex against the triggering attack", answered one event
    earlier than the card prints it -- and the printed "is hit" is the dropped
    half rather than the mechanism.

    A defence is read into the comparison before `Hit` is announced, so a
    bonus laid there is a modifier for the *next* blow and silently nothing
    for this one. Cancelling the `Hit` instead does not work either:
    `resolve.attack` re-announces a cancelled outcome from `result.hit`, which
    is still True, so the hit comes back. `AttackDeclared` is the window, and
    the cost of using it is that this fires on blows that would have missed
    anyway -- a real cost, since an immediate action is one per round.
    """
    mate = getattr(c.trigger, "target", None)
    if mate is None:
        return
    c.bonus(AC, 2, on=mate, until=When.EOT)
    c.bonus(REF, 2, on=mate, until=When.EOT)


# --------------------------------------------------------------------------
# m115802
# --------------------------------------------------------------------------


@power(
    "m115802a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d10", 5),
)
def m115802a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m115802a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d8", 5),
)
def m115802a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m115802a2",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d10", 5, kind=LIMITED),
)
def m115802a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


_M115802_LOOKED_AWAY = "an enemy marked by it attacks without including it"


@power(
    "m115802a3",
    level=3,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=Melee(2),
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d10", 5),
    trigger=_M115802_LOOKED_AWAY,
    on=Trigger(PowerUsed, _marked_foe_looks_away, _M115802_LOOKED_AWAY),
)
def m115802a3(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    if foe is None or c.distance(foe) > 2:
        return
    if c.strike(on=foe):
        c.hit(on=foe)


# --------------------------------------------------------------------------
# m115818
# --------------------------------------------------------------------------


@power(
    "m115818a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d10", 5),
)
def m115818a0(c: Cast) -> None:
    if c.strike():
        c.hit()
    c.mark(until=When.EONT)


@power(
    "m115818a1",
    level=3,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=6),
    requires=_while_bloodied,
    requires_text="it must be bloodied",
)
def m115818a1(c: Cast) -> None:
    """No damage line at all -- the whole of the Hit is the fall."""
    if c.strike():
        c.prone()


_M115818_SHIFTED = "an enemy adjacent to it shifts"


@power(
    "m115818a2",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=Melee(1),
    target=NO_TARGET,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d10", 3, kind=LIMITED, half_on_miss=True),
    trigger=_M115818_SHIFTED,
    on=Trigger(MoveStart, _adjacent_enemy_shifts, _M115818_SHIFTED),
)
def m115818a2(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    if foe is None or c.distance(foe) > 1:
        return
    if c.strike(on=foe):
        c.hit(on=foe)
    else:
        c.hit(on=foe, half=True)


# --------------------------------------------------------------------------
# m115855
# --------------------------------------------------------------------------


@power(
    "m115855a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d10", 5),
)
def m115855a0(c: Cast) -> None:
    """"Or 1d10 + 10 with a charge attack" is the one case the header cannot
    hold on its own: two damage expressions picked between by `c.charge`, so
    the bigger one is rolled in the body and the ordinary one stays data."""
    if not c.strike():
        return
    if c.charge:
        c.damage("1d10", 10)
    else:
        c.hit()


@power(
    "m115855a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 5),
)
def m115855a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m115855a2",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d10", 5, kind=LIMITED),
)
def m115855a2(c: Cast) -> None:
    """The Effect is paid once for the whole burst, so it is guarded by
    `c.first`. `to=` on `c.grants_advantage` names one beneficiary and its
    words are side-relative -- "me", "ally", "team" -- and there is no word
    for "my enemies", so the relation is set once per enemy by id."""
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)
    if c.first:
        for foe in c.enemies():
            c.grants_advantage(on=c.me, until=When.SONT, to=foe)


_M115855_FELLED = "it drops to 0 hit points"


@power(
    "m115855a3",
    level=3,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M115855_FELLED,
    on=Trigger(Dropped, about_me, _M115855_FELLED),
)
def m115855a3(c: Cast) -> None:
    """"Takes a standard action" on the way down. `c.extra_action` cannot
    carry it: a creature at 0 hit points is refused by the ordinary "can it
    act?" gate, and nothing would ever be spent. `_death_throe` is the one
    route that hands the triggering event over, which is where `dsl.use`
    reads the exemption from -- so the action it takes is its own attack."""
    _death_throe(c)


# --------------------------------------------------------------------------
# m115927
# --------------------------------------------------------------------------


@power(
    "m115927a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d10", 6),
    requires=_holding_nobody,
    requires_text="it must not have a creature grabbed",
    dropped=("c.grab(dc=)",),
)
def m115927a0(c: Cast) -> None:
    """The printed escape DC is the dropped half: `c.grab` sets the hold and
    takes no number, so getting out of this one is as easy as any other."""
    if c.strike():
        c.hit()
        c.grab()


@power(
    "m115927a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    damage=Damage("2d8", 3),
    requires=_grabbed_by_me_in_reach,
    requires_text="it must have hold of a creature",
    dropped=("Target.kind",),
)
def m115927a1(c: Cast) -> None:
    """No attack line: the printed Effect simply deals the damage, which
    `c.hit` applies from the header whether or not anything was rolled.
    "One creature grabbed by it" is a target line `Target` cannot say, so the
    offer is gated by `requires=` and the victim chosen here. #361."""
    victim = _restricted_to(c, 1, lambda foe: foe in c.grabbing(of=c.me))
    if victim is not None:
        c.hit(on=victim)


# --------------------------------------------------------------------------
# m115937
# --------------------------------------------------------------------------


@power(
    "m115937a0",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m115937a0(c: Cast) -> None:
    _slowing_aura(c, 1)


@power(
    "m115937a1",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m115937a1(c: Cast) -> None:
    """Four clauses, and the last is already true of the grid. Sharing its
    square lives on the creature being entered rather than on the mover. The
    shove immunity is gated: `c.immovable` would refuse a push from anywhere
    and the printed line refuses only melee and ranged attacks, so it is a
    shortening large enough to swallow any of them with the reach read off
    the row that shoved. Squeezing through a narrow opening needs nothing --
    the smallest gap the grid has is one square, which this already fits."""
    c.shares_space(difficult=True)
    c.resist_forced(99, when=_shoved_by_hand)


@power(
    "m115937a2",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m115937a2(c: Cast) -> None:
    """`kind=` is the label a zone's difficult terrain carries, which is how
    one sort of rough ground is told from another."""
    c.ignores_difficult("web", on=c.me, until=When.ENCOUNTER)


@power(
    "m115937a3",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=REF, printed=6),
    damage=Damage("1d6", 3),
)
def m115937a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)


# --------------------------------------------------------------------------
# m1433
# --------------------------------------------------------------------------


@power(
    "m1433a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d6", 3),
)
def m1433a0(c: Cast) -> None:
    """"Save ends **both**" is one effect carrying the hold and the burn:
    applied separately the victim gets two saves and shakes off half of what
    the card calls one thing."""
    if c.strike():
        c.hit()
        c.condition(
            Condition.IMMOBILIZED, until=When.SAVE_ENDS, ongoing=(5, DamageType.UNTYPED)
        )


@power(
    "m1433a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d10", 3),
)
def m1433a1(c: Cast) -> None:
    """The extractor folded "it makes two claw attacks" into the claw's own
    row, so the row *is* the pair: `UpTo(2)` and a body run once per target
    is two claws, and the chooser may still send both at one creature."""
    if c.strike():
        c.hit()


@power(
    "m1433a2",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(4),
    target=EACH_ENEMY,
    attack=Attack(vs=FORT, printed=8),
    damage=Damage("1d6", 1, DamageType.ACID, kind=LIMITED),
)
def m1433a2(c: Cast) -> None:
    """"Recharges when first bloodied" is the printed sentence on top of the
    die the database filed; the two only ever agree to make the row available
    sooner."""
    if c.first:
        _recharge_when_bloodied(c)
    if c.strike():
        c.hit()
        c.push(2)
        c.ongoing(5, DamageType.ACID)


# --------------------------------------------------------------------------
# m2240
# --------------------------------------------------------------------------


@power(
    "m2240a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d10", 4),
)
def m2240a0(c: Cast) -> None:
    """Two calls rather than one `c.condition`: see m1122a4."""
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)
        c.slowed(until=When.EONT)


@power(
    "m2240a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d10", 4),
)
def m2240a1(c: Cast) -> None:
    """Two counts of the crowd around the victim, and they are the same
    count: "+1 per ally adjacent to the target" goes on the roll, and "if at
    least two enemies are adjacent to it" is read from the target's side of
    the board, which is this creature's own. Asked once as the swing is made
    rather than held as a modifier, because the printed sentence is about the
    moment of the blow."""
    victim = c.target
    beside = _crowding(c, victim)
    if not c.strike(plus=beside):
        return
    c.hit()
    if beside >= 2:
        c.cannot_shift(until=When.SAVE_ENDS)


@power(
    "m2240a2",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MOVE,
    reach=CloseBurst(5),
    target=Target(side="other_ally", everyone=True),
)
def m2240a2(c: Cast) -> None:
    """`side="other_ally"` and not `EACH_ALLY`: the card says "each ally" and
    the wider pool includes the caster, which would hand this creature its own
    bonus. "Its next attack roll" is `once=True` -- the modifier is spent by
    the first roll that reads it."""
    mate = c.target
    if mate is None:
        return
    c.bonus("attack", 2, on=mate, until=When.ENCOUNTER, kind="power", once=True)
    c.shift(1, who=mate)


_M2240_CAUGHT = "it suffers an effect that a save can end"


@power(
    "m2240a3",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M2240_CAUGHT,
    on=Trigger(EffectApplied, _save_ends_on_me, _M2240_CAUGHT),
)
def m2240a3(c: Cast) -> None:
    """`c.save` follows `c.target`, which is None on a `NO_TARGET` row, so it
    falls back to the caster -- which is who the printed line means."""
    c.save(on=c.me)


@power(
    "m2240a4",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2240a4(c: Cast) -> None:
    _shoulder_to_shoulder(c, 2, minion=True)


# --------------------------------------------------------------------------
# m3188
# --------------------------------------------------------------------------


@power(
    "m3188a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 4),
)
def m3188a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3188a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d8", 4),
    requires=_pinned_enemy_in_reach,
    requires_text="immobilized, stunned, or unconscious targets only",
    dropped=("Target.kind",),
)
def m3188a1(c: Cast) -> None:
    """"Immobilized, stunned, or unconscious targets only" is a target line
    `Target` cannot say, so the offer is gated and the victim chosen here --
    and where another creature in reach qualifies the row is aimed there
    rather than thrown away, which a bare return would have done. #361."""
    victim = _restricted_to(
        c,
        1,
        lambda foe: any(
            c.is_(held, foe)
            for held in (Condition.IMMOBILIZED, Condition.STUNNED, Condition.UNCONSCIOUS)
        ),
    )
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)
        c.ongoing(5, on=victim)


@power(
    "m3188a2",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    charges=True,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 4, kind=LIMITED),
)
def m3188a2(c: Cast) -> None:
    """A row whose printed Effect *is* the charge. `charges=True` is what
    makes `dsl.usable` measure the reach after the run; without it the row is
    refused whenever the target is further off than a sword, which is every
    situation a charge is for. `c.run_at` rather than `c.charge_at(c.ref)`:
    that one would spend this very row again to make the swing. The
    `c.as_basic` filing is how the engine's own charge action offers it, and
    that path does set the flag."""
    if c.first:
        c.as_basic(c.ref, window="charge", until=When.ENCOUNTER)
    victim = c.target
    if victim is None:
        return
    if not c.adjacent(victim):
        c.run_at(victim)
    if c.strike():
        c.hit()
        c.immobilized(until=When.SAVE_ENDS)


@power(
    "m3188a3",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3188a3(c: Cast) -> None:
    """Asked as the roll is looked up rather than armed on `Bloodied`: the
    creature can be healed back above the line, and a bonus laid once would
    never come off again."""
    me = c.me
    c.bonus(
        "damage", 2, on=me, until=When.ENCOUNTER, when=lambda _ctx: c.bloodied(on=me)
    )


# --------------------------------------------------------------------------
# m3215
# --------------------------------------------------------------------------


@power(
    "m3215a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d10", 4),
    dropped=("c.grab(dc=)",),
)
def m3215a0(c: Cast) -> None:
    """Three clauses after the damage, and two of them share one lifetime.
    "Until the grab ends" is not a `When`, so the burn and the ban on
    attacking are both hung on the encounter clock and lifted by the escape.
    The printed -2 to escape is the dropped half: `c.grab` takes no number."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    c.grab()
    _until_escape(c, victim, c.ongoing(10, until=When.ENCOUNTER))
    _until_escape(c, victim, c.cannot_attack(on=c.me, until=When.ENCOUNTER))


# --------------------------------------------------------------------------
# m3244
# --------------------------------------------------------------------------


@power(
    "m3244a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d10", 4),
)
def m3244a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m3244a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d10", 4),
)
def m3244a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(1)
        c.mark(until=When.EONT)


_M3244_FELLED = "it is reduced to 0 hit points"


@power(
    "m3244a2",
    level=3,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M3244_FELLED,
    on=Trigger(Dropped, about_me, _M3244_FELLED),
)
def m3244a2(c: Cast) -> None:
    _death_throe(c)


# --------------------------------------------------------------------------
# m3305
# --------------------------------------------------------------------------


@power(
    "m3305a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 5),
)
def m3305a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3305a1",
    level=3,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 5, kind=LIMITED),
)
def m3305a1(c: Cast) -> None:
    """"Shifts 3 squares to a space adjacent to the target" is a destination
    and not a distance: a bare `c.shift` asks the controller, which on a quiet
    board walks the other way."""
    victim = c.target
    if c.strike():
        c.hit()
    if victim is not None:
        _shift_up_to(c, 3, toward=victim)


@power(
    "m3305a2",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3305a2(c: Cast) -> None:
    """"Before or after" is one step, not two, and the step is taken after:
    `AttackDeclared` is announced once per target, so a before-step would
    walk twice for one burst, and `Hit`/`Miss` close the swing exactly once.
    Both outcomes are watched because the step is not conditional on landing."""
    me, ref = c.me, c.ref

    def step(ev: Any) -> None:
        if getattr(ev, "attacker", None) != me:
            return
        if not getattr(ev, "opportunity", False):
            return
        c.shift(1)

    c.watch(Hit, step, until=When.ENCOUNTER, on=me, label=f"{ref} step hit")
    c.watch(Miss, step, until=When.ENCOUNTER, on=me, label=f"{ref} step miss")


# --------------------------------------------------------------------------
# m3437
# --------------------------------------------------------------------------


@power(
    "m3437a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=REF, printed=8),
    damage=Damage("2d6", 3, DamageType.PSYCHIC),
)
def m3437a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3437a1",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=REF, printed=8),
    damage=Damage("2d6", 3, DamageType.PSYCHIC, kind=LIMITED),
)
def m3437a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m3437a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    requires=_senseless_in_reach,
    requires_text="targets a helpless or unconscious creature",
    dropped=("Defences.insubstantial", "c.lose_mode()", "Target.kind"),
)
def m3437a2(c: Cast) -> None:
    """The finisher works; the price it pays for it does not.

    `Defences` carries no insubstantial flag at all -- the database column
    does not exist -- so "it loses insubstantial" has nothing to take away,
    and writing `c.end_effect(carrying=INSUBSTANTIAL)` would have been a line
    that is false in every fight. Losing the fly speed is the second gap:
    `c.mode` only ever raises a speed (`max(speed, had)`), so there is no way
    to set one aside and put it back.

    `c.coup_de_grace` is the auto-critical rule itself and checks the
    helplessness again, which is why the kill is read off the body afterwards
    rather than from the method's answer."""
    victim = _restricted_to(
        c, 1, lambda foe: any(c.is_(out, foe) for out in _SENSELESS)
    )
    if victim is None:
        return
    c.coup_de_grace(on=victim)
    theirs = c.world.get(victim, Health)
    if theirs is None or theirs.hp <= 0:
        mine = c.world.get(c.me, Health)
        if mine is not None:
            c.heal(mine.max_hp, on=c.me)


# --------------------------------------------------------------------------
# m3525
# --------------------------------------------------------------------------


@power(
    "m3525a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d10", 3),
)
def m3525a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.grab()


@power(
    "m3525a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d10", 9),
    requires=_grabbed_by_me_in_reach,
    requires_text="usable only against a target it has grabbed",
    dropped=("Target.kind",),
)
def m3525a1(c: Cast) -> None:
    victim = _restricted_to(c, 1, lambda foe: foe in c.grabbing(of=c.me))
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)


_M3525_FELLED = "it drops to 0 hit points"


@power(
    "m3525a2",
    level=3,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M3525_FELLED,
    on=Trigger(Dropped, about_me, _M3525_FELLED),
    dropped=("etl.monster.attack_defence()",),
)
def m3525a2(c: Cast) -> None:
    """The bite on the way down is the whole of what plays. Its attack line
    extracted as a bonus against no defence at all -- "+8 vs or (whichever is
    lower)" -- which is a compendium defect and not a defence to invent, so
    the swing is the creature's own basic attack instead. #360."""
    _death_throe(c)


@power(
    "m3525a3",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3525a3(c: Cast) -> None:
    _crit_drops_it(c)


# --------------------------------------------------------------------------
# m3551
# --------------------------------------------------------------------------


@power(
    "m3551a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 2),
)
def m3551a0(c: Cast) -> None:
    """The printed "(crit 1d8 + 10)" is the weapon's critical column and not
    body code -- `engine/equipment.py` applies it."""
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m3551a1",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3551a1(c: Cast) -> None:
    _opportunity_edge(c, 2, "1d6")


# --------------------------------------------------------------------------
# m4248
# --------------------------------------------------------------------------


@power(
    "m4248a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 5),
)
def m4248a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m4248a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d4", 5),
)
def m4248a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4248a2",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 9, kind=LIMITED),
    requires=_has_the_drop,
    requires_text="it must have combat advantage against the target",
)
def m4248a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


_M4248_LANDED = "it hits with a melee attack"


@power(
    "m4248a3",
    level=3,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M4248_LANDED,
    on=Trigger(Hit, both(by_me, by_melee), _M4248_LANDED),
)
def m4248a3(c: Cast) -> None:
    """`to="team"` rather than the default `"me"`: the card says the target
    grants combat advantage full stop, and the useful reading of that on a
    board is this creature and everything on its side."""
    victim = getattr(c.trigger, "target", None)
    if victim is None:
        return
    c.damage("1d6", dtype=DamageType.RADIANT, on=victim)
    c.grants_advantage(on=victim, until=When.EONT, to="team")


_M4248_SHIFTED = "a creature marked by it shifts"


@power(
    "m4248a4",
    level=3,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 5),
    trigger=_M4248_SHIFTED,
    on=Trigger(MoveStart, _marked_shifts, _M4248_SHIFTED),
)
def m4248a4(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    if foe is None or c.distance(foe) > 1:
        return
    if c.strike(on=foe):
        c.hit(on=foe)
        c.prone(on=foe)


# --------------------------------------------------------------------------
# m4304
# --------------------------------------------------------------------------


@power(
    "m4304a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d6", 6),
)
def m4304a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4304a1",
    level=3,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d6", 7, kind=LIMITED),
    charges=True,
)
def m4304a1(c: Cast) -> None:
    """"Shifts 2 squares and attacks" -- the step is taken before the swing,
    and `charges=True` so the reach is measured after it rather than before,
    which is what makes the row offered against a creature two squares off."""
    victim = c.target
    if victim is not None:
        _shift_up_to(c, 2, toward=victim)
    if c.strike():
        c.hit()
        c.prone()


_M4304_MATE_HIT = "an adjacent ally is hit by a melee or ranged attack"


@power(
    "m4304a2",
    level=3,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=CloseBurst(1),
    target=NO_TARGET,
    trigger=_M4304_MATE_HIT,
    on=Trigger(Hit, _ally_beside_hit, _M4304_MATE_HIT),
)
def m4304a2(c: Cast) -> None:
    """Two halves of one sentence, in order: the places are swapped first, so
    that the blow lands where this creature now stands. `c.redirect` moves the
    live `AttackResult` as well as the event, which is what keeps the damage
    with the announcement."""
    mate = getattr(c.trigger, "target", None)
    if mate is None:
        return
    c.swap(mate)
    c.redirect(to=c.me)


@power(
    "m4304a3",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
)
def m4304a3(c: Cast) -> None:
    """Watched after the blow, so what is healed is whoever actually landed
    it; the heal goes to the *attacker*, which is the odd half of this card."""
    me = c.me

    def rewarded(ev: Hit) -> None:
        if ev.target == me and ev.critical:
            c.heal(5, on=ev.attacker)

    c.watch(Hit, rewarded, until=When.ENCOUNTER, on=me, label=f"{c.ref} boon")


# --------------------------------------------------------------------------
# m4389
# --------------------------------------------------------------------------


@power(
    "m4389a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 4, DamageType.PSYCHIC),
)
def m4389a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4389a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 4, DamageType.PSYCHIC),
)
def m4389a1(c: Cast) -> None:
    """"Roll a d4" is rolled and not chosen: the card gives the creature no
    say, and `c.choose` would hand the decision to the policy. The third
    branch is two operations -- the slide, then a swing the *victim* makes --
    and `c.grant_attack` is the half that hands somebody else the blow."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    roll = c.roll("1d4")
    if roll == 1:
        c.ongoing(5, DamageType.PSYCHIC, on=victim)
    elif roll == 2:
        c.vulnerable(5, DamageType.PSYCHIC, on=victim)
    elif roll == 3:
        c.slide(2, on=victim)
        mate = next((a for a in c.allies() if c.adjacent_to(a, victim)), None)
        if mate is not None:
            c.grant_attack(victim, on=mate)
    else:
        c.dazed(on=victim, until=When.SONT)


@power(
    "m4389a2",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.PSYCHIC],
)
def m4389a2(c: Cast) -> None:
    """Two uses of the block's own at-will, each at a different creature.
    `NO_TARGET` because the targets belong to the row being used twice, not to
    this one -- declaring `UpTo(2)` here would have the chooser pick them and
    then the body pick them again."""
    struck: set[int] = set()
    for _ in range(2):
        foe = next((f for f in _press(c) if f not in struck), None)
        if foe is None:
            return
        struck.add(foe)
        c.use_power("m4389a1", on=foe)


@power(
    "m4389a3",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=6),
    damage=Damage("", 5, DamageType.PSYCHIC, kind=LIMITED),
)
def m4389a3(c: Cast) -> None:
    """A flat 5 with no dice is a `Damage` with an empty expression and a
    bonus, which keeps the number in the header as data like any other."""
    if c.first:
        _recharge_when_bloodied(c)
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)


# --------------------------------------------------------------------------
# m4678
# --------------------------------------------------------------------------


@power(
    "m4678a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d10", 4),
)
def m4678a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


_M4678_LOOKED_AWAY = "a marked enemy attacks without including it"


@power(
    "m4678a1",
    level=3,
    usage=AT_WILL,
    action=ActionType.OPPORTUNITY,
    reach=Melee(2),
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d10", 4),
    trigger=_M4678_LOOKED_AWAY,
    on=Trigger(PowerUsed, _marked_foe_looks_away, _M4678_LOOKED_AWAY),
)
def m4678a1(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    if foe is None or c.distance(foe) > 2:
        return
    if c.strike(on=foe):
        c.hit(on=foe)
        c.immobilized(on=foe, until=When.EONT)


@power(
    "m4678a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d10", 8),
    requires=_held_in_reach,
    requires_text="grabbed, restrained, or immobilized targets only",
    dropped=("Target.kind",),
)
def m4678a2(c: Cast) -> None:
    """A blanket `skill` modifier applies to every check, which is what "a -2
    penalty to skill checks" is -- `skills.py` reads the bare key alongside
    the `skill:<name>` ones."""
    victim = _restricted_to(c, 2, lambda foe: any(c.is_(held, foe) for held in _HELD))
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)
        c.penalty("skill", 2, on=victim, until=When.EONT)
        c.penalty("save", 2, on=victim, until=When.EONT)


_M4678_BLED = "it is first bloodied"


@power(
    "m4678a3",
    level=3,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d10", 4, kind=LIMITED),
    trigger=_M4678_BLED,
    on=Trigger(Bloodied, about_me, _M4678_BLED),
)
def m4678a3(c: Cast) -> None:
    """Filed as a standard action with "when first bloodied" left in the
    keywords, which is a trigger and not a cost; `Bloodied` is emitted once
    per creature so "first" needs nothing said about it."""
    if c.strike():
        c.hit()
        c.push(2)


_M4678_CAUGHT = "it suffers an effect that a save can end"


@power(
    "m4678a4",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M4678_CAUGHT,
    on=Trigger(EffectApplied, _save_ends_on_me, _M4678_CAUGHT),
)
def m4678a4(c: Cast) -> None:
    c.save(on=c.me)


# --------------------------------------------------------------------------
# m4690
# --------------------------------------------------------------------------


@power(
    "m4690a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d8", 6),
)
def m4690a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4690a1",
    level=3,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d8", 7, kind=LIMITED),
)
def m4690a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m4690a2",
    level=3,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m4690a2(c: Cast) -> None:
    """The bonus is laid before the walk and gated on `opportunity`, which is
    a key the attack context carries and `query.defence` is handed -- so "+4
    to defences against opportunity attacks **this movement provokes**" is
    read by exactly the swings the walk draws and by nothing else."""
    for defence in (AC, FORT, REF, WILL):
        c.bonus(defence, 4, on=c.me, until=When.EOT, when=_opportunity)
    c.move(c.speed_of(c.me) + 4)


_M4690_LANDED = "it hits with an attack"


@power(
    "m4690a3",
    level=3,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M4690_LANDED,
    on=Trigger(Hit, by_me, _M4690_LANDED),
)
def m4690a3(c: Cast) -> None:
    victim = getattr(c.trigger, "target", None)
    if victim is not None:
        c.damage("1d8", on=victim)


@power(
    "m4690a4",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4690a4(c: Cast) -> None:
    """`once=True` on the watch is "the first time", and `Bloodied` is
    emitted once per creature anyway -- both halves say the same thing, which
    is cheap insurance against a creature healed back over the line."""
    me = c.me

    def bled(ev: Bloodied) -> None:
        if ev.actor == me:
            c.temp_hp(5, on=me)

    c.watch(Bloodied, bled, until=When.ENCOUNTER, on=me, once=True, label=f"{c.ref} grit")


# --------------------------------------------------------------------------
# m5067
# --------------------------------------------------------------------------


@power(
    "m5067a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("2d6", 4),
)
def m5067a0(c: Cast) -> None:
    """"First Failed Saving Throw: stunned **instead of** slowed" is
    `escalate=`, which runs on every failed save -- so the swap is guarded to
    happen once, and the slow is taken off as the stun goes on because the
    card says instead and not as well."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return

    def worsen(effect: Effect) -> None:
        c.world.effects.end(effect, "worsened")
        c.stunned(until=When.SAVE_ENDS, on=effect.owner)

    c.condition(Condition.SLOWED, until=When.SAVE_ENDS, on=victim, escalate=worsen)


@power(
    "m5067a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=6),
    damage=Damage("1d6", 4),
)
def m5067a1(c: Cast) -> None:
    """"Pulls the target up to 4 squares **to a square adjacent to it**" is a
    destination, so the square is named; without one the pull stops wherever
    the decider likes and the printed adjacency is a coincidence."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    sq = _step_beside(c, victim, c.me)
    if sq is not None:
        c.pull(4, on=victim, to=sq)
    else:
        c.pull(4, on=victim)
    c.immobilized(on=victim, until=When.SAVE_ENDS)


_M5067_CLOSED = "an enemy enters a square adjacent to it"


@power(
    "m5067a2",
    level=3,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
    attack=Attack(vs=WILL, printed=6),
    trigger=_M5067_CLOSED,
    on=Trigger(AdjacencyGained, _enemy_stepped_beside, _M5067_CLOSED),
)
def m5067a2(c: Cast) -> None:
    """No damage line: the whole of the Hit is the blink. `AdjacencyGained` is
    emitted mirrored, so the creature that moved is in `mover` and the one
    answering is in `actor`."""
    foe = getattr(c.trigger, "other", None)
    if foe is None:
        return
    if c.strike(on=foe):
        c.teleport(2, who=foe)


# --------------------------------------------------------------------------
# m5296
# --------------------------------------------------------------------------


@power(
    "m5296a0",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5296a0(c: Cast) -> None:
    _slowing_aura(c, 1)


@power(
    "m5296a1",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5296a1(c: Cast) -> None:
    """"It declares one creature to be its master", which is only ever read by
    the row below it -- "an enemy attacks its master".

    `c.guard` and not `c.bind`: `bind` sets MASTER_OF from *this* creature
    outwards, which is the wrong way round here, and the only thing the block
    does with the relation is defend the creature, which is what
    GUARDED_BY means. The choice is the nearest ally, because the card gives
    the creature the choice and the policy has nothing to make it with."""
    mate = min(c.allies(), key=lambda a: c.distance(a), default=None)
    if mate is not None:
        c.guard(on=mate)


@power(
    "m5296a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d8", 7),
)
def m5296a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5296a3",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d8", 3),
)
def m5296a3(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5296a4",
    level=3,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d8", 7, kind=LIMITED, half_on_miss=True),
)
def m5296a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(1)
        c.prone()
    else:
        c.hit(half=True)
        c.prone()


@power(
    "m5296a5",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d8", 7),
)
def m5296a5(c: Cast) -> None:
    """The Effect names **the target** and one round, not every adjacent
    enemy for the fight, so it is the narrow watch rather than
    `_punish_looking_away`."""
    if c.strike():
        c.hit()
    victim = c.target
    if victim is not None:
        _mark_bites(c, victim, 10, radius=1, until=When.EONT)


_M5296_WARD_STRUCK = "an enemy within 5 squares attacks the creature it guards"


def _ward_struck_from_within_five(world: World, me: int, ev: Any) -> bool:
    if not _my_ward_attacked(world, me, ev):
        return False
    return distance_between(world, me, getattr(ev, "attacker", me)) <= 5


@power(
    "m5296a6",
    level=3,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5296_WARD_STRUCK,
    on=Trigger(AttackDeclared, _ward_struck_from_within_five, _M5296_WARD_STRUCK),
)
def m5296a6(c: Cast) -> None:
    """`AttackDeclared` carries the attacker in `attacker` and the victim in
    `target`, which is why `_my_ward_attacked` reads both and `about_me` is no
    use here. The step is aimed at the attacker, or the swing that follows has
    nothing in reach."""
    foe = getattr(c.trigger, "attacker", None)
    if foe is None:
        return
    _shift_up_to(c, 4, toward=foe)
    if c.distance(foe) <= 1:
        c.use_power("m5296a2", on=foe)


# --------------------------------------------------------------------------
# m5321
# --------------------------------------------------------------------------


@power(
    "m5321a0",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5321a0(c: Cast) -> None:
    _slowing_aura(c, 1)


@power(
    "m5321a1",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5321a1(c: Cast) -> None:
    _edge_when_mobbed(c, 2)


@power(
    "m5321a2",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5321a2(c: Cast) -> None:
    c.shares_space(difficult=True)
    c.resist_forced(99, when=_shoved_by_hand)


@power(
    "m5321a3",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d6", 4),
)
def m5321a3(c: Cast) -> None:
    """Two damage expressions picked between by the victim's state, which is
    the one case the header cannot hold alone."""
    if not c.strike():
        return
    if c.is_(Condition.PRONE):
        c.damage("3d6", 4)
    else:
        c.hit()


@power(
    "m5321a4",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=8),
    damage=Damage("2d8", 4),
    requires=_slowed_in_reach,
    requires_text="one slowed creature",
    dropped=("Target.kind",),
)
def m5321a4(c: Cast) -> None:
    victim = _restricted_to(c, 1, lambda foe: c.is_(Condition.SLOWED, foe))
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)
        c.prone(on=victim)


# --------------------------------------------------------------------------
# m5427
# --------------------------------------------------------------------------


@power(
    "m5427a0",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.ignore_concealment()",),
)
def m5427a0(c: Cast) -> None:
    """Concealment is not cover: `c.ignore_cover` reads the cover table and
    nothing reads a concealment exemption, so the whole of this row waits on
    one verb and there is nothing to half-write."""


@power(
    "m5427a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d4", 5),
)
def m5427a1(c: Cast) -> None:
    """Three lifetimes on one card and two of them are the grab's. "Until the
    grab ends" is not a `When`, so both are hung on the encounter clock and
    lifted by the escape. The Secondary Attack has no ref of its own, so its
    printed total is taken back to a bonus with `scaling.trim` the way the
    header's would be."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    c.grab()
    _until_escape(
        c, victim, c.grants_advantage(on=victim, until=When.ENCOUNTER, to="team")
    )
    if _secondary(c, 8, FORT, victim):
        _until_escape(c, victim, c.ongoing(5, on=victim, until=When.ENCOUNTER))


@power(
    "m5427a2",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=8),
    damage=Damage("3d4", 7, kind=LIMITED),
    requires=_grabbed_by_me_in_reach,
    requires_text="one creature grabbed by it",
    dropped=("Target.kind",),
)
def m5427a2(c: Cast) -> None:
    """"Cannot stand up until the grab ends" is `Condition.PINNED` laid beside
    the prone -- which is what `c.prone(held=)` does, except that its `held`
    takes a `When` and the grab's end is not one, so the hold is laid by hand
    and lifted by the escape."""
    if c.first:
        _recharge_when_bloodied(c)
    victim = _restricted_to(c, 1, lambda foe: foe in c.grabbing(of=c.me))
    if victim is None:
        return
    if not c.strike(on=victim):
        return
    c.hit(on=victim)
    c.prone(on=victim)
    _until_escape(
        c, victim, c.condition(Condition.PINNED, until=When.ENCOUNTER, on=victim)
    )


# --------------------------------------------------------------------------
# m5489
# --------------------------------------------------------------------------


@power(
    "m5489a0",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5489a0(c: Cast) -> None:
    """"One or more **other** creatures of its own sort", so the count is
    narrowed to the stat block's own ref -- which is the only thing there is
    to compare when the card names a creature by name."""
    _edge_when_mobbed(c, 1, ref="m5489")


@power(
    "m5489a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d6", 4),
)
def m5489a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(1)
    c.mark(until=When.EONT)


_M5489_LOOKED_AWAY = "an enemy marked by it attacks without including it"


@power(
    "m5489a2",
    level=3,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5489_LOOKED_AWAY,
    on=Trigger(PowerUsed, _marked_foe_looks_away, _M5489_LOOKED_AWAY),
)
def m5489a2(c: Cast) -> None:
    """`c.use_power` leaves the borrowed row's attack in `c.result`, so
    `c.landed` answers the printed "if the attack hits" without this row
    declaring an attack line of its own."""
    foe = getattr(c.trigger, "actor", None)
    if foe is None or c.distance(foe) > 1:
        return
    c.use_power("m5489a1", on=foe)
    if c.landed:
        c.immobilized(on=foe, until=When.SAVE_ENDS)


_M5489_FELLED = "it drops to 0 hit points"


@power(
    "m5489a3",
    level=3,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5489_FELLED,
    on=Trigger(Dropped, about_me, _M5489_FELLED),
)
def m5489a3(c: Cast) -> None:
    """`bare=True` is a saving throw against nothing in particular, which is
    what this one is: there is no save-ends effect to shake off, only the
    falling. Standing back up on one hit point until the end of its next turn
    is `c.reanimate` and not a heal -- `_die` leaves the body an entity and
    only lifts it off the grid, so what the row needs is a square."""
    if c.save(on=c.me, bare=True):
        c.reanimate(on=c.me, hp=1, until=When.EONT)


# --------------------------------------------------------------------------
# m5534
# --------------------------------------------------------------------------


@power(
    "m5534a0",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POISON],
)
def m5534a0(c: Cast) -> None:
    """`opportunity` is a plain attribute set on `Hit` after the fact, so it
    is read with `getattr` and a default."""
    me = c.me

    def bit(ev: Hit) -> None:
        if ev.attacker == me and getattr(ev, "opportunity", False):
            c.immobilized(on=ev.target, until=When.EONT)

    c.watch(Hit, bit, until=When.ENCOUNTER, on=me, label=f"{c.ref} hold")


@power(
    "m5534a1",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5534a1(c: Cast) -> None:
    _aquatic_edge(c)


@power(
    "m5534a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d6", 4),
)
def m5534a2(c: Cast) -> None:
    if not c.strike():
        return
    if c.is_(Condition.IMMOBILIZED):
        c.damage("3d6", 6)
    else:
        c.hit()


@power(
    "m5534a3",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
)
def m5534a3(c: Cast) -> None:
    """"Uses claw twice" -- the same row twice at one creature, so that "if
    both attacks hit the same target" is a question that can be answered.
    `ONE_CREATURE` and not `UpTo(2)`: the rider is the whole content of the
    card and only exists when both swings went to one creature, so letting the
    chooser spread them would offer a line that can never pay out."""
    victim = c.target
    if victim is None:
        return
    if _both_hit(c, "m5534a2", "m5534a2") and _secondary(c, 7, FORT, victim):
        c.immobilized(on=victim, until=When.SAVE_ENDS)


# --------------------------------------------------------------------------
# m5749
# --------------------------------------------------------------------------


@power(
    "m5749a0",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("Target.kind",),
)
def m5749a0(c: Cast) -> None:
    """The aura's grants go to the whole of its side: `c.grants_in` filters on
    `side` and on nothing a creature *is*, so "drake allies" is the dropped
    half and every ally inside gets the resistance and the bonus. `kind=` is
    the word the card prints, which here is "power"."""
    ring = c.aura(1, label=f"{c.ref} aura", until=When.ENCOUNTER, on=c.me)
    c.resist_in(ring, 5, DamageType.FIRE, side="team")
    c.grants_in(ring, AC, 2, side="team", kind="power")


@power(
    "m5749a1",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
)
def m5749a1(c: Cast) -> None:
    """"Any creature", so no side is asked -- its own allies burn too.
    `ZoneExited` is the only announcement of a creature leaving an aura, and
    it is the moment the toll is printed for."""
    ring = c.aura(1, label=f"{c.ref} heat", until=When.ENCOUNTER, on=c.me)

    def left(ev: ZoneExited) -> None:
        if ev.zone == ring and ev.actor != c.me:
            c.flat(5, dtype=DamageType.FIRE, on=ev.actor)

    c.watch(ZoneExited, left, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} toll")


def _plus_one_on_the_wounded(c: Cast) -> int:
    """"It has a +1 bonus to hit a bloodied target." Asked as the swing is
    made rather than held as a modifier: the victim can be bloodied by the
    blow before this one, and a standing gate would be read against whoever
    the context happened to name."""
    victim = c.target
    return 1 if victim is not None and c.bloodied(on=victim) else 0


@power(
    "m5749a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d10", 6),
)
def m5749a2(c: Cast) -> None:
    if c.strike(plus=_plus_one_on_the_wounded(c)):
        c.hit()
    victim = c.target
    if victim is not None:
        _mark_bites(
            c, victim, 5, radius=99, until=When.EONT, dtype=DamageType.FIRE
        )


@power(
    "m5749a3",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.WEAPON],
    attack=Attack(vs=REF, printed=8),
    damage=Damage("1d10", 6, DamageType.FIRE),
)
def m5749a3(c: Cast) -> None:
    """"If it has combat advantage against the target" is read off the
    result: asking `has_combat_advantage` again is too late, because a
    one-shot grant has already been spent by the roll."""
    if not c.strike(plus=_plus_one_on_the_wounded(c)):
        return
    c.hit()
    result = c.result
    if result is not None and result.advantage:
        c.cannot_shift(until=When.EONT)


_M5749_STRUCK = "an enemy within 10 squares hits it"


@power(
    "m5749a4",
    level=3,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
    trigger=_M5749_STRUCK,
    on=Trigger(Hit, _hit_me_from_within(10), _M5749_STRUCK),
)
def m5749a4(c: Cast) -> None:
    foe = getattr(c.trigger, "attacker", None)
    if foe is not None:
        c.damage("1d6", 4, dtype=DamageType.FIRE, on=foe)


# --------------------------------------------------------------------------
# m5853
# --------------------------------------------------------------------------


@power(
    "m5853a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d10", 6),
)
def m5853a0(c: Cast) -> None:
    if c.strike():
        c.hit()
    c.mark(until=When.EONT)


@power(
    "m5853a1",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=6),
    damage=Damage("2d6", 5, kind=LIMITED, half_on_miss=True),
)
def m5853a1(c: Cast) -> None:
    """"Until the end of **its** next turn" is the target's turn, which is
    `When.EOTNT` -- `EONT` would be this creature's and a round out."""
    if c.first:
        _recharge_when_bloodied(c)
    if c.strike():
        c.hit()
        c.immobilized(until=When.EOTNT)
    else:
        c.hit(half=True)
        c.slowed(until=When.EOTNT)


_M5853_SHIFTED = "an adjacent enemy marked by it shifts"


@power(
    "m5853a2",
    level=3,
    usage=AT_WILL,
    action=ActionType.OPPORTUNITY,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5853_SHIFTED,
    on=Trigger(MoveStart, _marked_adjacent_shifts, _M5853_SHIFTED),
)
def m5853a2(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    if foe is not None and c.distance(foe) <= 1:
        c.use_power("m5853a0", on=foe)


# --------------------------------------------------------------------------
# m5866
# --------------------------------------------------------------------------


@power(
    "m5866a0",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5866a0(c: Cast) -> None:
    """A shortening and not an immunity: three squares off whatever the shove
    specified, from any source, which is exactly `c.resist_forced`."""
    c.resist_forced(3, on=c.me, until=When.ENCOUNTER)


@power(
    "m5866a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d8", 6, DamageType.POISON),
)
def m5866a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5866a2",
    level=3,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(3),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=6),
    once_per_round=True,
    dropped=("c.grab(dc=)",),
)
def m5866a2(c: Cast) -> None:
    """No damage line: the Hit is the haul and the hold. The printed escape
    DC is the dropped half -- `c.grab` takes no number."""
    if not c.strike():
        return
    victim = c.target
    if victim is None:
        return
    sq = _step_beside(c, victim, c.me)
    if sq is not None:
        c.pull(2, on=victim, to=sq)
    else:
        c.pull(2, on=victim)
    c.grab(on=victim)


_M5866_CAPTIVE_LOOKED_AWAY = "an enemy it is grabbing attacks without including it"


@power(
    "m5866a3",
    level=3,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(3),
    target=NO_TARGET,
    keywords=[Keyword.POISON],
    trigger=_M5866_CAPTIVE_LOOKED_AWAY,
    on=Trigger(PowerUsed, _my_captive_looks_away, _M5866_CAPTIVE_LOOKED_AWAY),
)
def m5866a3(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    if foe is not None:
        c.flat(5, dtype=DamageType.POISON, on=foe)


# --------------------------------------------------------------------------
# m5884
# --------------------------------------------------------------------------


@power(
    "m5884a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d6", 4),
)
def m5884a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5884a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=6),
    damage=Damage("2d6", 4),
    requires=_in_the_water_empty_handed,
    requires_text="it must be in water and must not have a creature grabbed",
    dropped=("c.grab(dc=)",),
)
def m5884a1(c: Cast) -> None:
    """The drowning check is a real roll and not narrative -- `c.check` makes
    it, and the damage it costs is read from the failure -- so it is armed as
    a watch on the victim's own turn and lifted by the escape."""
    if not c.strike():
        c.immobilized(until=When.EOTNT)
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    c.grab()

    def gasping(ev: TurnStart) -> None:
        if ev.actor != victim or ev.ghost:
            return
        if victim not in c.grabbing(of=c.me):
            return
        if not c.check("endurance", 13, who=victim):
            c.flat(10, on=victim)

    _until_escape(
        c,
        victim,
        c.watch(
            TurnStart, gasping, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} drown"
        ),
    )


# --------------------------------------------------------------------------
# m5947
# --------------------------------------------------------------------------


@power(
    "m5947a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d6", 4),
)
def m5947a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


_M5947_LOOKED_AWAY = "a creature marked by it attacks without including it"


@power(
    "m5947a1",
    level=3,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
    trigger=_M5947_LOOKED_AWAY,
    on=Trigger(PowerUsed, _marked_foe_looks_away, _M5947_LOOKED_AWAY),
)
def m5947a1(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    if foe is None:
        return
    c.flat(5, dtype=DamageType.FIRE, on=foe)
    c.slowed(on=foe, until=When.EOTNT)


# --------------------------------------------------------------------------
# m6043
# --------------------------------------------------------------------------


@power(
    "m6043a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d10", 5),
)
def m6043a0(c: Cast) -> None:
    if c.strike():
        c.hit()
    c.mark(until=When.EONT)


@power(
    "m6043a1",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d10", 5, kind=LIMITED),
)
def m6043a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m6043a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d8", 5),
)
def m6043a2(c: Cast) -> None:
    if c.strike():
        c.hit()


_M6043_LOOKED_AWAY = "an enemy marked by it attacks without including it"


@power(
    "m6043a3",
    level=3,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    trigger=_M6043_LOOKED_AWAY,
    on=Trigger(PowerUsed, _marked_foe_looks_away, _M6043_LOOKED_AWAY),
)
def m6043a3(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    if foe is not None and c.distance(foe) <= 2:
        c.basic(on=foe)


# --------------------------------------------------------------------------
# m6564
# --------------------------------------------------------------------------


@power(
    "m6564a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d6", 4),
)
def m6564a0(c: Cast) -> None:
    if c.strike():
        c.hit()


_M6564_LOOKED_AWAY = "an adjacent enemy attacks without including it"


@power(
    "m6564a1",
    level=3,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M6564_LOOKED_AWAY,
    on=Trigger(PowerUsed, _adjacent_foe_looks_away, _M6564_LOOKED_AWAY),
)
def m6564a1(c: Cast) -> None:
    """No mark on this block at all -- adjacency is the whole condition, which
    is why `_marked_foe_looks_away` is the wrong predicate here."""
    foe = getattr(c.trigger, "actor", None)
    if foe is not None and c.distance(foe) <= 1:
        c.use_power("m6564a0", on=foe)


# --------------------------------------------------------------------------
# m6626
# --------------------------------------------------------------------------


@power(
    "m6626a0",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FEAR, Keyword.PSYCHIC],
)
def m6626a0(c: Cast) -> None:
    """Two clauses on one aura. The ban on shifting is a condition that has to
    arrive and leave with the creature, so it is diffed by the zone --
    `ZoneEntered` and `ZoneExited` are exactly those two moments, and a
    membership list recomputed each turn would be stale the moment anybody
    moved. The toll is the ordinary looked-away watch with the aura asked at
    the moment of the attack."""
    me, ring = c.me, 1
    _aura_holds(
        c,
        c.aura(ring, label=f"{c.ref} aura", until=When.ENCOUNTER, on=me),
        lambda who: c.cannot_shift(on=who, until=When.ENCOUNTER),
    )

    def sting(ev: PowerUsed) -> None:
        if ev.actor == me or not _is_attack(ev.power) or me in ev.targets:
            return
        if not c.world.relations.holds(Relation.MARKED_BY, me, ev.actor):
            return
        if distance_between(c.world, me, ev.actor) > ring:
            return
        c.flat(5, dtype=DamageType.PSYCHIC, on=ev.actor)

    c.watch(PowerUsed, sting, until=When.ENCOUNTER, on=me, label=f"{c.ref} toll")


@power(
    "m6626a1",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6626a1(c: Cast) -> None:
    c.resist_forced(1, on=c.me, until=When.ENCOUNTER)


@power(
    "m6626a2",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6626a2(c: Cast) -> None:
    """"A saving throw to avoid falling prone." `ConditionApplied` is an
    `Event` and not a `Decision`, so it cannot be cancelled -- but prone lasts
    until the creature stands up and nothing else, so curing it in the same
    breath is the same board state as never having fallen. The saving throw is
    `bare=True`: there is no save-ends effect behind it, only the fall."""
    me = c.me

    def toppled(ev: ConditionApplied) -> None:
        if ev.target != me or ev.condition is not Condition.PRONE:
            return
        if c.save(on=me, bare=True, against=f"{c.ref} footing"):
            c.cure(Condition.PRONE, on=me)

    c.watch(
        ConditionApplied, toppled, until=When.ENCOUNTER, on=me, label=f"{c.ref} footing"
    )


@power(
    "m6626a3",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d10", 6),
)
def m6626a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        _shove_and_step(c)
    c.mark(until=When.EONT)


@power(
    "m6626a4",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=6),
    damage=Damage("1d6", 4, DamageType.PSYCHIC),
)
def m6626a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.pull(3)
    c.mark(until=When.EONT)


@power(
    "m6626a5",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
)
def m6626a5(c: Cast) -> None:
    """The reach is the *longer* of the two rows it uses, because the pull is
    what brings the victim inside the hammer's -- the order on the card is not
    decoration. `_both_hit` answers "if it hits the same target with both"."""
    if _both_hit(c, "m6626a4", "m6626a3"):
        c.prone()


# --------------------------------------------------------------------------
# m748
# --------------------------------------------------------------------------


@power(
    "m748a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 2),
)
def m748a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m748a1",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m748a1(c: Cast) -> None:
    _opportunity_edge(c, 2, "1d6")


# --------------------------------------------------------------------------
# m854
# --------------------------------------------------------------------------


@power(
    "m854a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 2),
)
def m854a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m854a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=8),
    damage=Damage("1d8", 2),
    requires=_marked_by_me_in_reach,
    requires_text="marked target only",
    dropped=("Target.kind",),
)
def m854a1(c: Cast) -> None:
    """"And is marked" on a row that may only be used against something it has
    already marked is a refresh, not a new condition -- the mark is laid again
    so the clock starts over."""
    victim = _restricted_to(c, 1, lambda foe: c.marked(on=foe, by=c.me))
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)
        c.ongoing(5, on=victim)
        c.mark(on=victim, until=When.EONT)


# --------------------------------------------------------------------------
# m857
# --------------------------------------------------------------------------


@power(
    "m857a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 4),
)
def m857a0(c: Cast) -> None:
    """`c.opportunity` is this use's own flag, which is the question the
    second sentence asks -- not whether some earlier swing was one."""
    if c.strike():
        c.hit()
        if c.opportunity:
            c.shift(1)


@power(
    "m857a1",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=CloseBurst(5),
    target=Target(side="other_ally", everyone=True),
    dropped=("etl.monster.attack_defence()",),
)
def m857a1(c: Cast) -> None:
    """The rally plays and the attack half does not. Its line extracted as
    "+8 vs ;" -- a bonus against no defence at all, which is a compendium
    defect and not a defence to invent, and the 2d10+3 has nothing to be
    rolled against. #360. What is left is the printed Effect, and it is the
    reason this is filed as a minor action."""
    mate = c.target
    if mate is not None:
        c.shift(3, who=mate)


@power(
    "m857a2",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m857a2(c: Cast) -> None:
    """Every ally gets a modifier gated on the one creature this blow landed
    on, rather than one modifier gated on "whoever it last hit": the card
    stacks a second victim's bonus beside the first, and a single mutable
    target would quietly move the old bonus onto the new creature."""
    me = c.me

    def landed(ev: Hit) -> None:
        if ev.attacker != me or team(c.world, ev.target) is team(c.world, me):
            return
        victim = ev.target
        for mate in c.allies():
            for what in ("attack", "damage"):
                c.bonus(
                    what, 2, on=mate, until=When.EONT,
                    when=lambda ctx, v=victim: ctx.get("target") == v,
                )

    c.watch(Hit, landed, until=When.ENCOUNTER, on=me, label=f"{c.ref} call")


_M857_CAUGHT = "it suffers an effect that a save can end"


@power(
    "m857a3",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M857_CAUGHT,
    on=Trigger(EffectApplied, _save_ends_on_me, _M857_CAUGHT),
)
def m857a3(c: Cast) -> None:
    c.save(on=c.me)


@power(
    "m857a4",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m857a4(c: Cast) -> None:
    _shoulder_to_shoulder(c, 2, ref="m857")


# --------------------------------------------------------------------------
# m861
# --------------------------------------------------------------------------


@power(
    "m861a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d10", 3),
)
def m861a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m861a1",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d10", 7, kind=LIMITED),
)
def m861a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(1)
        c.dazed(until=When.SAVE_ENDS)


@power(
    "m861a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 2),
)
def m861a2(c: Cast) -> None:
    if c.strike():
        c.hit()


# --------------------------------------------------------------------------
# m864
# --------------------------------------------------------------------------


@power(
    "m864a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d4", 4),
)
def m864a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m864a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=8),
    damage=Damage("1d8", 3),
)
def m864a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized(until=When.SAVE_ENDS)


_M864_SHIFTED = "an adjacent enemy shifts"


@power(
    "m864a2",
    level=3,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M864_SHIFTED,
    on=Trigger(MoveStart, _adjacent_enemy_shifts, _M864_SHIFTED),
)
def m864a2(c: Cast) -> None:
    c.shift(1)


# --------------------------------------------------------------------------
# m886
# --------------------------------------------------------------------------


@power(
    "m886a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d10", 2),
)
def m886a0(c: Cast) -> None:
    if c.strike():
        c.hit()


_M886_HIT_IN_MELEE = "it is hit by a melee attack"


@power(
    "m886a1",
    level=3,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d6", 2),
    trigger=_M886_HIT_IN_MELEE,
    on=Trigger(Hit, both(targets_me, by_melee), _M886_HIT_IN_MELEE),
)
def m886a1(c: Cast) -> None:
    """"If the attacker is within reach" is the printed condition and it is
    the whole reason the row has its own attack line rather than borrowing the
    basic: a melee attack can come from two squares away."""
    killer = getattr(c.trigger, "attacker", None)
    if killer is None or c.distance(killer) > 1:
        return
    if c.strike(on=killer):
        c.hit(on=killer)


@power(
    "m886a2",
    level=3,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    dropped=("c.attacked_this_round()",),
)
def m886a2(c: Cast) -> None:
    """"An enemy it has attacked **this round**" is the dropped half: nothing
    keeps a record of who a creature swung at, so the narrowing cannot be
    asked and any enemy in reach can be marked. `c.hit_this_turn()` is the
    nearest filed gap and is a different question twice over -- hit rather
    than attacked, turn rather than round."""
    c.mark(until=When.EONT)


@power(
    "m886a3",
    level=3,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.HEALING],
    once_per_round=True,
    requires=_while_bloodied,
    requires_text="usable only while bloodied",
)
def m886a3(c: Cast) -> None:
    c.heal(5, on=c.me)


# --------------------------------------------------------------------------
# m973
# --------------------------------------------------------------------------


@power(
    "m973a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d10", 6),
)
def m973a0(c: Cast) -> None:
    if c.strike():
        c.hit()
    c.mark(until=When.EONT)


@power(
    "m973a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d8", 7),
)
def m973a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m973a2",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d10", 11, kind=LIMITED),
)
def m973a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()
