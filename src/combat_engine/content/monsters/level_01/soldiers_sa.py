"""Monster abilities, level 1, soldiers: the second sweep.

Seven stat blocks whose rows were still undeclared. The conventions are the
ones `level_01/skirmishers.py` settled and they are kept unchanged:

* numbers load from `game.db` -- the attack line is written exactly as printed
  (`Attack(vs=AC, printed=6)`) and the damage line goes in the header as data,
  so an MM1 block can be rescaled to MM3 maths later;
* a **trait** is a row that costs no action, has no target, and arms the
  watches that hold it for the rest of the fight. `turns` uses every such row
  once at the start of the encounter, which is what makes a watch armed in one
  of these bodies true from round 1;
* a printed range of "15/30" takes the **normal** range, so the creature
  shoots inside the band where it has no penalty.

A soldier's mark is the thing to get right twice over. It is printed as an
**Effect** on three of these rows, not as part of the Hit, so it is laid
whether the swing landed or not -- and the rows that punish a marked enemy for
looking elsewhere answer `PowerUsed`, which carries the whole target list,
rather than `AttackDeclared`, which is announced once per target and would pay
out twice for one burst.
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
    NO_TARGET,
    ONE_ALLY,
    ONE_CREATURE,
    PERSONAL,
    REF,
    STANDARD,
    WILL,
    ActionType,
    Attack,
    Cast,
    CloseBurst,
    Condition,
    Damage,
    DamageType,
    Health,
    Ident,
    Keyword,
    Melee,
    Position,
    Ranged,
    Relation,
    Square,
    Usage,
    When,
    World,
    get,
    power,
)
from combat_engine.engine.events import (
    AttackDeclared,
    ConditionApplied,
    Escaped,
    Hit,
    MoveStart,
    PowerUsed,
    TurnStart,
)
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import distance_between, enemies, team
from combat_engine.engine.triggers import Trigger

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


def _bloodied(world: World, eid: int) -> bool:
    hp = world.get(eid, Health)
    return hp is not None and 0 < hp.hp <= hp.max_hp // 2


def _bloodied_in_reach(world: World, eid: int) -> bool:
    """The printed target line "one bloodied creature", as an entry gate.

    `Target` has no field for it, and a body that looks and returns is a
    standard action the policy spends on nothing. `dsl.usable` is handed
    `(world, eid)` and the caster is all it knows, so the question has to be
    asked from this end.
    """
    return any(
        distance_between(world, eid, foe) <= 1 and _bloodied(world, foe)
        for foe in enemies(world, eid)
    )


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


def _punish_looking_away(c: Cast, amount: int, *, radius: int) -> None:
    """An adjacent enemy that swings at anybody else takes it.

    `PowerUsed` rather than `AttackDeclared`: an attack is announced once per
    target, so a burst that happened to leave the soldier out would have paid
    this out once for every creature it caught. `PowerUsed` fires once per use
    and carries the whole target list, which is what "does not include it" is
    actually asking.
    """
    me, ref = c.me, c.ref

    def sting(ev: PowerUsed) -> None:
        if ev.actor == me or not _is_attack(ev.power):
            return
        if team(c.world, ev.actor) is team(c.world, me):
            return
        if distance_between(c.world, me, ev.actor) > radius:
            return
        if me in ev.targets:
            return
        c.flat(amount, on=ev.actor)

    c.watch(PowerUsed, sting, until=When.ENCOUNTER, on=me, label=f"{ref} reprisal")


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


def _marked_foe_moves(world: World, me: int, ev: Any) -> bool:
    """"An enemy marked by it moves away from it."

    `MoveStart`, not `MoveEnd`: by the end of the move the enemy has gone and
    "away from it" can no longer be measured against where it stood when the
    row should have fired. The distance it is leaving from is read here.
    """
    actor = getattr(ev, "actor", None)
    if actor is None or actor == me:
        return False
    if getattr(ev, "kind_", "") in ("push", "pull", "slide"):
        return False
    return world.relations.holds(Relation.MARKED_BY, me, actor)


def _crit_landed_on_me(world: World, me: int, ev: Any) -> bool:
    return getattr(ev, "target", None) == me and bool(getattr(ev, "critical", False))


def _my_ward_attacked(world: World, me: int, ev: Any) -> bool:
    """"An enemy attacks the creature this one is shielding."""
    actor = getattr(ev, "attacker", None)
    victim = getattr(ev, "target", None)
    if actor is None or victim is None or actor == me:
        return False
    if team(world, actor) is team(world, me):
        return False
    return world.relations.holds(Relation.GUARDED_BY, me, victim)


# --------------------------------------------------------------------------
# m115714
# --------------------------------------------------------------------------


@power(
    "m115714a0",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m115714a0(c: Cast) -> None:
    """One square off every shove, for the whole fight."""
    c.resist_forced(1, on=c.me, until=When.ENCOUNTER)


@power(
    "m115714a1",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m115714a1(c: Cast) -> None:
    """A save against being knocked down, taken as the hold lands.

    `Effects.apply` installs the condition and *then* announces it, so there
    is no event to cancel; the hold that put the creature down is ended
    instead, inside the same window, and nothing gets a turn in between. The
    save is rolled bare -- it is the printed saving throw and not a save
    against a standing effect.
    """
    me = c.me

    def shrug(ev: ConditionApplied) -> None:
        if ev.target != me or ev.condition is not Condition.PRONE:
            return
        if not c.save(on=me, bare=True):
            return
        for effect in list(c.world.effects.of(me)):
            if Condition.PRONE in effect.conditions:
                c.world.effects.end(effect, c.ref)

    c.watch(ConditionApplied, shrug, until=When.ENCOUNTER, on=me, label=f"{c.ref} footing")


@power(
    "m115714a2",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d10", 3),
)
def m115714a2(c: Cast) -> None:
    """The mark is printed as the Effect, so it is laid on a miss too."""
    victim = c.target
    pos = c.world.get(victim, Position) if victim is not None else None
    was = pos.square if pos else None
    if c.strike():
        c.hit()
        if c.push(1):
            _step_into_vacated(c, was)
    c.mark(until=When.EONT)


@power(
    "m115714a3",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d6", 4),
)
def m115714a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m115714a4",
    level=1,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
)
def m115714a4(c: Cast) -> None:
    """Both of its at-wills in one action, the ranged half taken for free.

    The melee half is named by the weapon rather than by a ref, and the melee
    at-will is the row that swings it. The waiver is laid before the second
    use and not after, because it has to be standing when the shot is taken.
    """
    c.use_power("m115714a2")
    c.no_provoke(on=c.me, until=When.EOT)
    c.use_power("m115714a3")


# --------------------------------------------------------------------------
# m3324
# --------------------------------------------------------------------------


@power(
    "m3324a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d8", 3),
)
def m3324a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m3324a1",
    level=1,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=5),
    damage=Damage("2d4", 1, kind=LIMITED),
)
def m3324a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3324a2",
    level=1,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d8", 7, kind=LIMITED),
)
def m3324a2(c: Cast) -> None:
    """The ally's bonus is spent on one roll and only against this target.

    `once=True` is "its **next** attack roll" and the gate is "against the
    target", so a swing at anybody else in the window leaves it standing.
    `kind="power"` is the word the card prints in front of "bonus".
    """
    if not c.strike():
        return
    c.hit()
    victim = c.target
    mate = next(
        (a for a in c.allies() if a != c.me and c.distance(a) <= 5),
        None,
    )
    if mate is None or victim is None:
        return

    def at_that_one(ctx: dict[str, Any]) -> bool:
        return ctx.get("target") == victim

    c.bonus(
        "attack", 2, on=mate, kind="power", until=When.EONT,
        once=True, when=at_that_one,
    )


# --------------------------------------------------------------------------
# m4613
# --------------------------------------------------------------------------


@power(
    "m4613a0",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4613a0(c: Cast) -> None:
    """Anything beside it that swings at it gets 3 back.

    Read off `AttackDeclared` rather than `PowerUsed`: this one is "attacks
    **it**", so a burst that catches it is one qualifying attack and the
    per-target announcement is the right grain. The round guard stops a
    multi-target attack that names it twice paying out twice.
    """
    me, ref = c.me, c.ref
    seen: dict[str, int] = {}

    def bite_back(ev: AttackDeclared) -> None:
        if ev.target != me or ev.attacker == me:
            return
        if team(c.world, ev.attacker) is team(c.world, me):
            return
        if distance_between(c.world, me, ev.attacker) > 1:
            return
        if seen.get(ev.power) == c.world.round:
            return
        seen[ev.power] = c.world.round
        c.flat(3, on=ev.attacker)

    c.watch(AttackDeclared, bite_back, until=When.ENCOUNTER, on=me, label=f"{ref} thorns")


@power(
    "m4613a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage("2d6", 2),
)
def m4613a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


_M4613_LOOKED_AWAY = "an adjacent enemy marked by it attacks somebody else"


@power(
    "m4613a2",
    level=1,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    attack=Attack(vs=REF, printed=6),
    damage=Damage("2d6", 2),
    trigger=_M4613_LOOKED_AWAY,
    on=Trigger(PowerUsed, _marked_foe_looks_away, _M4613_LOOKED_AWAY),
)
def m4613a2(c: Cast) -> None:
    """Adjacency is tested here rather than in the predicate: the trigger is
    shared with another block that reaches further, and this one prints
    "adjacent"."""
    foe = getattr(c.trigger, "actor", None)
    if foe is None or c.distance(foe) > 1:
        return
    if c.strike(on=foe):
        c.hit(on=foe)
        c.prone(on=foe)


# --------------------------------------------------------------------------
# m4682
# --------------------------------------------------------------------------


@power(
    "m4682a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d10", 3),
)
def m4682a0(c: Cast) -> None:
    if c.strike():
        c.hit()


_M4682_WARD_STRUCK = "an enemy attacks the ally it is shielding"


@power(
    "m4682a1",
    level=1,
    usage=AT_WILL,
    action=ActionType.OPPORTUNITY,
    reach=Melee(1),
    target=NO_TARGET,
    attack=Attack(vs=FORT, printed=6),
    damage=Damage("1d6", 3),
    trigger=_M4682_WARD_STRUCK,
    on=Trigger(AttackDeclared, _my_ward_attacked, _M4682_WARD_STRUCK),
)
def m4682a1(c: Cast) -> None:
    """An opportunity action resolves in the BEFORE window, so the penalty is
    standing when the triggering roll is made. `once=True` spends it on that
    roll and nothing later."""
    foe = getattr(c.trigger, "attacker", None)
    if foe is None:
        return
    if c.strike(on=foe):
        c.hit(on=foe)
    c.penalty("attack", 3, on=foe, until=When.EOT, once=True)


@power(
    "m4682a2",
    level=1,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d10", 3, kind=LIMITED, half_on_miss=True),
)
def m4682a2(c: Cast) -> None:
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)


@power(
    "m4682a3",
    level=1,
    usage=AT_WILL,
    action=FREE,
    once_per_round=True,
    reach=Melee(1),
    target=ONE_ALLY,
    uses=1,
)
def m4682a3(c: Cast) -> None:
    """A standing promise rather than a one-off gift of hit points.

    The temporary hit points are paid at the *start of the ally's turn* and
    only while it is still beside the dwarf, so the row arms a watch rather
    than calling `c.temp_hp` now. "Or until it uses this power again" is the
    previous watch and relation ended by hand, both labelled off this ref so
    one sweep takes the pair -- and it is what `uses=1` cannot say, because
    the row is at-will.

    `c.guard` is laid as well as the watch: the dwarf's opportunity row reads
    "the ally it is shielding" off that relation and had nothing else to ask.
    """
    mate = c.target
    if mate is None:
        return
    me, ref = c.me, c.ref
    for effect in list(c.world.effects.live.values()):
        if effect.source == me and effect.label.startswith(ref):
            c.world.effects.end(effect, "it used the power again")
    for held in c.guarding():
        c.world.relations.clear(Relation.GUARDED_BY, me, held, ref)

    def top_up(ev: TurnStart) -> None:
        if ev.actor != mate or ev.ghost:
            return
        if distance_between(c.world, me, mate) <= 1:
            c.temp_hp(4, on=mate)

    c.guard(on=mate)
    c.watch(TurnStart, top_up, until=When.ENCOUNTER, on=me, label=f"{ref} shield")


# --------------------------------------------------------------------------
# m5397
# --------------------------------------------------------------------------


@power(
    "m5397a0",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5397a0(c: Cast) -> None:
    """Steadier with one of its own kind beside it.

    Asked at the moment a defence is read rather than once when the trait
    arms: both creatures move, and a membership worked out now would be stale
    the first time either of them took a step. Untyped -- a stat block prints
    a bare "+2 bonus" and a *racial* bonus is a player-race idea.
    """
    me, mine = c.me, _ref_of(c, c.me)

    def kin_beside(ctx: dict[str, Any]) -> bool:
        return any(
            mate != me
            and _ref_of(c, mate) == mine
            and distance_between(c.world, me, mate) <= 1
            for mate in c.allies()
        )

    c.bonus(AC, 2, on=me, until=When.ENCOUNTER, when=kin_beside)
    c.bonus(WILL, 2, on=me, until=When.ENCOUNTER, when=kin_beside)


@power(
    "m5397a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d8", 5),
)
def m5397a1(c: Cast) -> None:
    """The Miss line marks a bloodied target anyway, which is the whole of it."""
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)
    elif c.bloodied():
        c.mark(until=When.EONT)


@power(
    "m5397a2",
    level=1,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=FORT, printed=2),
    damage=Damage("2d6", 3, dtype=DamageType.LIGHTNING, kind=LIMITED),
)
def m5397a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.pull(2)


_M5397_LOOKED_AWAY = "an enemy marked by it moves, or attacks somebody else"


@power(
    "m5397a3",
    level=1,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=CloseBurst(5),
    target=NO_TARGET,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=6),
    damage=Damage("", 10, dtype=DamageType.LIGHTNING),
    trigger=_M5397_LOOKED_AWAY,
    on=(
        Trigger(MoveStart, _marked_foe_moves, "an enemy marked by it moves"),
        Trigger(PowerUsed, _marked_foe_looks_away, "a marked enemy attacks somebody else"),
    ),
)
def m5397a3(c: Cast) -> None:
    """Two printed triggers, so both are declared -- half of an "or" declared
    alone looks finished and fires for one sentence only."""
    foe = getattr(c.trigger, "actor", None)
    if foe is None or c.distance(foe) > 5:
        return
    if c.strike(on=foe):
        c.hit(on=foe)


# --------------------------------------------------------------------------
# m5499
# --------------------------------------------------------------------------


@power(
    "m5499a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage("2d6", 2),
)
def m5499a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.grab()


@power(
    "m5499a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage("2d6", 2),
    requires=_bloodied_in_reach,
    requires_text="there must be a bloodied creature within reach",
)
def m5499a1(c: Cast) -> None:
    """The failed-escape toll is read off `Escaped`, which is emitted for a
    loss as well as a win -- `holder` is the grabber, so the watch gates on
    that and not on `actor`, which is the creature struggling."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    me, ref = c.me, c.ref
    c.grab()
    c.penalty("escape", 4, on=victim)

    def toll(ev: Escaped) -> None:
        if ev.holder == me and ev.actor == victim and not ev.success:
            c.flat(5, on=victim)

    c.watch(Escaped, toll, until=When.ENCOUNTER, on=me, label=f"{ref} hold")


_M5499_CRIT = "a creature scores a critical hit against it"


@power(
    "m5499a2",
    level=1,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5499_CRIT,
    on=Trigger(Hit, _crit_landed_on_me, _M5499_CRIT),
)
def m5499a2(c: Cast) -> None:
    """"Drops to 0 hit points" is whatever it has left, dealt to it.

    A free action answers the `Hit` in the AFTER window, so the critical's own
    damage has already come off and what remains is the rest. Not `c.damage`:
    there are no dice and nothing should rescale.
    """
    hp = c.world.get(c.me, Health)
    if hp is not None and hp.hp > 0:
        c.flat(hp.hp, on=c.me)


# --------------------------------------------------------------------------
# m5801
# --------------------------------------------------------------------------


@power(
    "m5801a0",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5801a0(c: Cast) -> None:
    """An aura 1 for the board to draw, and the reprisal hung off `PowerUsed`."""
    c.aura(1, until=When.ENCOUNTER)
    _punish_looking_away(c, 3, radius=1)


@power(
    "m5801a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d8", 3),
)
def m5801a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5801a2",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d8", 3),
)
def m5801a2(c: Cast) -> None:
    victim = c.target
    pos = c.world.get(victim, Position) if victim is not None else None
    was = pos.square if pos else None
    if c.strike():
        c.hit()
        if c.push(1):
            _step_into_vacated(c, was)


@power(
    "m5801a3",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d8", 1),
)
def m5801a3(c: Cast) -> None:
    if c.strike():
        c.hit()
