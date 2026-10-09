"""Monster abilities, level 5, soldiers.

Forty-one stat blocks, 152 rows. Eight of the forty-one print no ability at
all (m157, m169, m247, m274, m2928, m4801, m4993, m729) and have nothing to
decorate. Unlike the other roles at this level there is no earlier
`soldiers.py` sweep to split from -- this is the first pass over the role at
this level, so every helper below is written here rather than inherited from
a sibling file at this level; the ones that already existed at levels 1-4 are
imported instead of copied.

Conventions, inherited from the level 1-4 soldier sweeps and the rest of this
week's level 5 wave:

* numbers load from `game.db`; the attack line is `Attack(vs=AC, printed=N)`
  exactly as the card prints it, and the damage line goes in the header as
  data so an MM1 block can be rescaled to MM3 maths later;
* a **trait** costs no action, has no target, and arms whatever holds it for
  the rest of the fight, whatever the compendium's action column claims --
  several rows here are filed as "standard" and are plainly traits;
* a printed range of "15/30" or "5/10" takes the normal number; a card with
  no range at all is melee 1;
* `c.mark`, never `c.condition(Condition.MARKED, ...)` -- only the first sets
  `Relation.MARKED_BY`, which every "marked by it" trigger reads;
* a printed Requirement naming the creature's own kit (a longsword, a shield,
  a broadsword, a falchion) is not a gate -- `Gear` is empty on every
  monster, so asking would refuse a working row in every fight (#366);
* "save ends both" pairs a condition with a modifier or a second condition in
  **one** effect wherever `c.condition` can say both at once; where it
  cannot (a mark plus a burn, a slow plus an aftereffect) the pieces are
  tied together by hand so one throw ends all of them;
* "Aftereffect: a penalty (save ends)" following a timed stun is
  `dropped=("c.aftereffect()",)`, the symbol eight rows across the tree
  already wait on -- `Effect.on_end` also fires when the encounter itself
  ends, which is not what "when the save succeeds" means, and one symbol
  should serve all eight rather than each inventing its own near miss.

Two stat blocks here print a fragment of a name that the extraction did not
finish stripping -- a leftover title-cased word sitting beside the ref in
running prose. Neither word appears anywhere below; every reference to
either creature is written against its own ref, read as "it".
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_02.artillery_sa import ALL_DEFENCES
from combat_engine.content.monsters.level_02.lurkers_sa import (
    _reach_kind,
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
    _square_of,
)
from combat_engine.content.monsters.level_03.brutes_sa import _recharge_and_fire
from combat_engine.content.monsters.level_03.skirmishers_sa import _reachable
from combat_engine.content.monsters.level_03.soldiers_sa import (
    _adjacent_foe_looks_away,
    _marked_shifts,
    _shove_and_step,
    _shoveable,
)
from combat_engine.engine import (
    AC,
    AT_WILL,
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
    OPPORTUNITY,
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
    Ident,
    Keyword,
    Melee,
    Ranged,
    Relation,
    Target,
    UpTo,
    Usage,
    When,
    Window,
    World,
    power,
)
from combat_engine.engine.events import (
    AttackRolled,
    Bloodied,
    DamageApplied,
    Dropped,
    EffectApplied,
    Hit,
    Miss,
    Moved,
    MoveStart,
    OpportunityWindow,
    PowerUsed,
    RelationSet,
    TurnStart,
)
from combat_engine.engine.grid import distance as square_distance
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import creatures, distance_between, flanked_by, is_, team
from combat_engine.engine.triggers import Trigger, about_me, targets_me

# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------

#: "An immobilized, stunned, or unconscious creature" -- m3977a1's entry and
#: redirect test, the same three `_pinned_enemy_in_reach` already names.
_IMMOBILE_STUNNED_OUT = (Condition.IMMOBILIZED, Condition.STUNNED, Condition.UNCONSCIOUS)

#: "A dazed, stunned, or unconscious creature" -- one word different from the
#: set above, so it is its own tuple rather than a near-miss reuse of it.
_DAZED_STUNNED_OUT = (Condition.DAZED, Condition.STUNNED, Condition.UNCONSCIOUS)

#: "Immobilized, restrained, stunned, or unconscious" -- m5681a3's own four,
#: one more than either tuple above.
_HELPLESS_FOUR = (
    Condition.IMMOBILIZED,
    Condition.RESTRAINED,
    Condition.STUNNED,
    Condition.UNCONSCIOUS,
)


def _helpless_in_reach(radius: int) -> Any:
    def gate(world: World, eid: int) -> bool:
        return _reachable(
            world, eid, radius, lambda foe: any(is_(world, foe, c_) for c_ in _HELPLESS_FOUR)
        )

    return gate


def _shifts_after_an_opportunity_hit(c: Cast) -> None:
    """"If it hits with an opportunity attack, it can shift 1 square." Three
    reprints of the same creature print this verbatim; `c.opportunity` is
    this use's own flag and needs no watch to ask again."""
    if c.strike():
        c.hit()
        if c.opportunity:
            c.shift(1)


def _rallies_when_it_hits(c: Cast) -> None:
    """"When its melee attack hits an enemy, allies gain a +2 bonus to
    attack rolls and damage rolls against that enemy until the end of its
    next turn." Three reprints of the same creature print this verbatim."""
    me, ref = c.me, c.ref

    def rallied(ev: Hit) -> None:
        if ev.attacker != me or _reach_kind(getattr(ev, "power", "") or "") != "melee":
            return
        victim = ev.target
        for mate in c.allies():
            if mate == me:
                continue
            c.bonus(
                "attack", 2, on=mate, until=When.EONT,
                when=lambda ctx, v=victim: ctx.get("target") == v,
            )
            c.bonus(
                "damage", 2, on=mate, until=When.EONT,
                when=lambda ctx, v=victim: ctx.get("target") == v,
            )

    c.watch(Hit, rallied, until=When.ENCOUNTER, on=me, label=f"{ref} rally")


def _bonus_beside_kin(c: Cast, amount: int, *which: Any) -> None:
    """"+N to <defences> while at least one ally of its own kind is
    adjacent to it." Counted by `Ident.ref`, because every creature in a
    fight may share a type word and the printed sentence is about this
    stat block."""
    mine = _ref_of(c, c.me)

    def beside(ctx: dict[str, Any]) -> bool:
        return any(_ref_of(c, w) == mine for w in c.within(1, side="ally") if w != c.me)

    for defence in which:
        c.bonus(defence, amount, on=c.me, until=When.ENCOUNTER, when=beside)


def _allies_shift(c: Cast, squares_: int) -> None:
    """"Allies in the burst shift N squares." Shared by three reprints."""
    mate = c.target
    if mate is not None:
        c.shift(squares_, who=mate)


def _mark_and_burn(
    c: Cast, victim: int, amount: int, dtype: DamageType = DamageType.UNTYPED
) -> None:
    """"Marked, and takes ongoing N damage (save ends both)." `c.condition`
    combines a condition with ongoing damage under one save, but a mark is a
    relation and not a `Condition` -- only `c.mark` sets `Relation.MARKED_BY`
    -- so the burn carries the one save and the mark is ended alongside it
    rather than running its own."""
    held = c.ongoing(amount, dtype, on=victim, until=When.SAVE_ENDS)
    tag = c.mark(on=victim, until=When.ENCOUNTER)
    if held is not None and tag is not None:
        held.on_end.append(lambda: c.world.effects.end(tag, "saved"))


def _toll_per_square_away(c: Cast, victim: int) -> Effect:
    """"Takes 2 necrotic damage for each square it moves away from it each
    turn." Measured on `Moved`, the only one of the three movement events
    that carries both the square left and the word for how -- `from_` and
    `kind_` together are what "how far did it actually get from me" needs."""
    me, ref = c.me, c.ref

    def stepped(ev: Moved) -> None:
        if ev.actor != victim or ev.kind_ not in ("walk", "shift"):
            return
        here = _square_of(c, victim)
        anchor = _square_of(c, me)
        if here is None or anchor is None or ev.from_ is None:
            return
        delta = square_distance(here, anchor) - square_distance(ev.from_, anchor)
        if delta > 0:
            c.flat(2 * delta, dtype=DamageType.NECROTIC, on=victim)

    return c.watch(Moved, stepped, until=When.ENCOUNTER, on=me, label=f"{ref} toll {victim}")


def _held_by_me(c: Cast, *conditions: Condition) -> Effect | None:
    """The standing effect of its own that carries one of these conditions
    on some enemy -- "a creature immobilized or stunned by it", read off
    `Effect.source` and `Effect.conditions` rather than guessed from the
    board, since nothing tracks "who imposed this" except the effect that
    did."""
    for who in c.enemies():
        for eff in c.world.effects.of(who):
            if eff.source == c.me and any(cnd in eff.conditions for cnd in conditions):
                return eff
    return None


def _m4741_within(radius: int) -> Any:
    """"While within N squares of a [brute]" -- an entry gate naming another
    stat block's ref rather than a type word, so it is asked by walking every
    creature on the board rather than `enemies`/`allies`: the other creature
    may be on either side."""

    def gate(world: World, eid: int) -> bool:
        for other in creatures(world):
            ident = world.get(other, Ident)
            if (
                ident is not None
                and ident.ref == "m4741"
                and distance_between(world, eid, other) <= radius
            ):
                return True
        return False

    return gate


def _marked_adjacent_departs(world: World, me: int, ev: Any) -> bool:
    """"An adjacent enemy it has marked would move or shift" / "a marked
    enemy leaves an adjacent square, even if it is shifting." No `kind_`
    filter at all -- unlike the ordinary mark-punish shapes, two cards this
    wave explicitly spend the word "shifting" to say the usual exemption
    does not apply here."""
    actor = getattr(ev, "actor", None)
    if actor is None or actor == me or getattr(ev, "kind_", "") in ("push", "pull", "slide"):
        return False
    return world.relations.holds(Relation.MARKED_BY, me, actor)


def _adjacent_enemy_moves(world: World, me: int, ev: Any) -> bool:
    """"An adjacent enemy moves or shifts" -- unmarked, unlike the shape
    above, and still excluding a shove: "moves or shifts" is what the
    creature chooses to do, not what is done to it."""
    actor = getattr(ev, "actor", None)
    if actor is None or actor == me or team(world, actor) is team(world, me):
        return False
    if getattr(ev, "kind_", "") in ("push", "pull", "slide"):
        return False
    return distance_between(world, me, actor) <= 1


def _moved_to_flank_me(world: World, me: int, ev: Any) -> bool:
    """"An enemy moves to a position where it flanks it." The position only
    exists once the move is finished, so this is the one mark-punish shape in
    the file that reads `MoveEnd` rather than `MoveStart`."""
    actor = getattr(ev, "actor", None)
    if actor is None or actor == me or team(world, actor) is team(world, me):
        return False
    return flanked_by(world, me, actor)


def _my_opportunity(world: World, me: int, ev: OpportunityWindow) -> bool:
    """`OpportunityWindow.actor` is whoever may answer it, not whoever is
    leaving -- the mirror image of the mark-punish shapes above, where `me`
    is the subject and not the mover. The engine already declines to open
    this window for a shift (`movement._SAFE`), so a plain "leaves a square
    adjacent to it" with no "even if shifting" clause belongs here and not
    on `_marked_adjacent_departs`."""
    return getattr(ev, "actor", None) == me


def _hit_me_rolled(world: World, me: int, ev: AttackRolled) -> bool:
    """"It is hit by an attack," asked at the one window that can still
    change the outcome: `ev.result.hit` before the blow resolves."""
    if getattr(ev, "target", None) != me:
        return False
    result = getattr(ev, "result", None)
    return bool(result) and getattr(result, "hit", False)


def _marked_me_from_afar(radius: int) -> Any:
    """"An enemy within N squares of it marks it." Marking is a relation,
    not a condition, so the trigger is `RelationSet` rather than anything
    that watches conditions -- `kind_` names which relation and `source` is
    whoever just set it."""

    def gate(world: World, me: int, ev: RelationSet) -> bool:
        if ev.kind_ is not Relation.MARKED_BY or ev.target != me:
            return False
        actor = ev.source
        if actor is None or actor == me or team(world, actor) is team(world, me):
            return False
        return distance_between(world, me, actor) <= radius

    return gate


def _any_foe_looks_away(world: World, me: int, ev: Any) -> bool:
    """"An enemy makes an attack that does not include it" -- any enemy, not
    only one it has marked, which is the one difference from the mark-punish
    shape this would otherwise be."""
    actor = getattr(ev, "actor", None)
    if actor is None or actor == me or team(world, actor) is team(world, me):
        return False
    if not _is_attack(getattr(ev, "power", "")):
        return False
    return me not in getattr(ev, "targets", ())


def _grabbing(c: Cast) -> list[int]:
    return c.grabbing()


def _holding_nobody(world: World, eid: int) -> bool:
    return not world.relations.targets(Relation.GRABBED_BY, eid)


def _rises_unless(c: Cast, hp: int, *types: DamageType) -> None:
    """"Does not die, and instead returns with N hit points" -- declared for
    the scorer via `c.revives_unless`, which **implements nothing by
    itself** (its own docstring says so): the watch below is what actually
    stands it back up, reading the killing blow's type off the
    `DamageApplied` immediately before the `Dropped` it caused. Both cards
    this wave delay the return to "the start of its next turn"; that is
    approximated as immediate here, since nothing in the tree revives on a
    delay and a creature purged from initiative the moment it drops would
    never reach the turn it was waiting for."""
    me = c.me
    c.revives_unless(*types, on=me)
    last: dict[str, bool] = {"barred": False}

    def took(ev: DamageApplied) -> None:
        if ev.target == me:
            last["barred"] = any(t in ev.types() for t in types)

    def rise(ev: Dropped) -> None:
        if ev.actor == me and not last["barred"]:
            c.reanimate(on=me, hp=hp, until=When.EONT)

    c.watch(DamageApplied, took, until=When.ENCOUNTER, on=me, label=f"{c.ref} last blow")
    c.watch(Dropped, rise, until=When.ENCOUNTER, on=me, once=True, label=f"{c.ref} rises")


def _current_scorn(c: Cast) -> int | None:
    """Which creature is presently the object of its scorn, read off the
    marker effect's own label rather than a closure, so a standing bonus
    armed once still reads the live designation every time it is asked."""
    prefix = f"{c.ref} scorn:"
    for eff in c.world.effects.of(c.me):
        if eff.label.startswith(prefix):
            try:
                return int(eff.label[len(prefix):])
            except ValueError:
                return None
    return None


# ==========================================================================
# m1024
# ==========================================================================


@power(
    "m1024a0",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1024a0(c: Cast) -> None:
    """"While adjacent to an ally" changes every time anybody moves, so it is
    a gate read live rather than a bonus laid once."""
    c.cannot_be_flanked(
        on=c.me, until=When.ENCOUNTER, when=lambda ctx: bool(c.within(1, side="ally"))
    )


@power(
    "m1024a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d8", 4),
)
def m1024a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m1024a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d8", 4),
)
def m1024a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1024a3",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=Target(
        "enemy", 1,
        label="targets a creature it has marked",
        relation=Relation.MARKED_BY,
    ),
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d8", 7),
)
def m1024a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.SAVE_ENDS)


@power(
    "m1024a4",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d8", 4),
)
def m1024a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        if _shoveable(c, c.target):
            _shove_and_step(c)


# ==========================================================================
# m1110
# ==========================================================================


@power(
    "m1110a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d10", 4),
)
def m1110a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1110a1",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.THUNDER],
    attack=Attack(vs=FORT, printed=10),
    damage=Damage("1d10", 5, dtype=DamageType.THUNDER, kind=LIMITED),
)
def m1110a1(c: Cast) -> None:
    """"In place of a melee basic attack when charging" and "...when it uses
    its own immediate reaction" are the same offer made twice -- `c.as_basic`
    with the default window answers every melee basic attack, charge
    included, which is one call rather than two."""
    c.as_basic("m1110a1")
    if c.strike():
        c.hit()
        c.push(2)


@power(
    "m1110a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(3),
    target=ONE_CREATURE,
    keywords=[Keyword.TELEPORTATION],
    attack=Attack(vs=FORT, printed=10),
    damage=Damage("1d6", 5),
)
def m1110a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        victim = c.target
        if victim is None:
            return
        sq = _free_square_beside(c, c.me)
        if sq is not None:
            c.pull(c.distance(victim), on=victim, to=sq)


@power(
    "m1110a3",
    level=5,
    usage=AT_WILL,
    action=MINOR,
    reach=CloseBurst(2),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE],
)
def m1110a3(c: Cast) -> None:
    """The mark and the teleport-strike it arms are one printed power with
    no ref of its own for the reaction half, so the watch is armed from here.
    "Hits with an attack that does not include it" is read as the hit
    landing on somebody other than it; `_armed` keeps a second use of this
    row from doubling the reaction."""
    victim = c.target
    if victim is None:
        return
    c.mark(on=victim, until=When.ENCOUNTER)
    me, ref = c.me, c.ref
    label = f"{ref} teleport strike"
    if _armed(c, label):
        return

    def looked_away(ev: Hit) -> None:
        foe = ev.attacker
        if foe == me or ev.target == me:
            return
        if not c.world.relations.holds(Relation.MARKED_BY, me, foe):
            return
        if distance_between(c.world, me, foe) > 10:
            return
        sq = _free_square_beside(c, foe)
        if sq is None:
            return
        c.teleport(10, to=sq)
        c.basic(on=foe)

    c.watch(Hit, looked_away, until=When.ENCOUNTER, on=me, label=label)


@power(
    "m1110a4",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.FORCE],
    attack=Attack(vs=REF, printed=10),
    damage=Damage("1d6", 5, dtype=DamageType.FORCE),
)
def m1110a4(c: Cast) -> None:
    if c.strike():
        c.hit()


# ==========================================================================
# m1113
# ==========================================================================


@power(
    "m1113a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d8", 3),
)
def m1113a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1113a1",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("3d8", 5, kind=LIMITED),
)
def m1113a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m1113a2",
    level=5,
    usage=AT_WILL,
    action=MINOR,
    reach=CloseBurst(10),
    target=ONE_ALLY,
)
def m1113a2(c: Cast) -> None:
    """"Makes an immediate saving throw against one effect that a save can
    end" -- the most recent save-ends hold standing on the ally, the same
    read as a creature rolling against its own."""
    mate = c.target
    if mate is None:
        return
    for eff in sorted(c.world.effects.of(mate), key=lambda e: -e.id):
        if eff.when is When.SAVE_ENDS:
            c.world.effects.save(eff)
            return


@power(
    "m1113a3",
    level=5,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m1113a3(c: Cast) -> None:
    c.teleport(5)


# ==========================================================================
# m1138
# ==========================================================================


@power(
    "m1138a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d4", 7),
)
def m1138a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1138a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d4", 7),
)
def m1138a1(c: Cast) -> None:
    """The printed Requirement naming its own falchion is not a gate (#366).
    "Shift 1 and make a secondary attack" is read as a second target: the
    reposition is what puts a different creature in reach for the follow-up,
    so the secondary swing goes at the nearest other enemy once it has
    moved, which is the only creature "secondary" can sensibly mean here."""
    victim = c.target
    landed = bool(c.strike())
    if landed:
        c.hit()
    if not landed:
        return
    c.shift(1)
    second = next((f for f in c.enemies() if f != victim and c.distance(f) <= 2), None)
    if second is not None and c.attack(c.world.scaling.trim(12, c.level), AC, on=second):
        c.damage("4d4", 7, on=second)


@power(
    "m1138a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("2d4", 7),
)
def m1138a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1138a3",
    level=5,
    usage=AT_WILL,
    action=MINOR,
    reach=CloseBlast(5),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR, Keyword.HEALING],
)
def m1138a3(c: Cast) -> None:
    """"Can designate only one target as the object of its scorn at a time"
    is a re-arm rather than a stack: the old designation is cleared and a new
    marker names the current one, which the single standing bonus (armed
    once, below) reads live. The heal-on-kill is `Dropped.source`, the same
    field `Bloodied` carries for "whenever it bloodies an enemy"."""
    me, ref = c.me, c.ref
    victim = c.target
    if victim is None:
        return
    for eff in list(c.world.effects.of(me)):
        if eff.label.startswith(f"{ref} scorn:"):
            c.world.effects.end(eff, "re-designated")
    c.effect(f"{ref} scorn:{victim}", until=When.ENCOUNTER, on=me)
    label = f"{ref} scorn bonus"
    if _armed(c, label):
        return
    def scorned(ctx: dict[str, Any]) -> bool:
        if ctx.get("target") != _current_scorn(c):
            return False
        return _reach_kind(str(ctx.get("power", ""))) == "melee"

    c.bonus("damage", 0, dice="2d4", on=me, until=When.ENCOUNTER, when=scorned)

    def finished(ev: Dropped) -> None:
        if ev.source == me and ev.actor == _current_scorn(c):
            c.heal(34, on=me)

    c.watch(Dropped, finished, until=When.ENCOUNTER, on=me, label=label)


@power(
    "m1138a4",
    level=5,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(1),
    target=ONE_ALLY,
    dropped=("Target.creature_kind", "Target.ident"),
)
def m1138a4(c: Cast) -> None:
    """"One orc or [it]" has no symbol in `Target`, so the kind is checked
    here and the row redirects to a qualifying ally in reach rather than
    doing nothing."""
    mine = _ref_of(c, c.me)
    mate = c.target
    if mate is not None and not (c.is_kind("orc", on=mate) or _ref_of(c, mate) == mine):
        mate = next(
            (
                a for a in c.allies()
                if c.distance(a) <= 1 and (c.is_kind("orc", on=a) or _ref_of(c, a) == mine)
            ),
            None,
        )
    if mate is None:
        return
    c.bonus("attack", 2, on=mate, until=When.EONT, once=True)


# ==========================================================================
# m115890
# ==========================================================================


@power(
    "m115890a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 8),
)
def m115890a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EOTNT)


@power(
    "m115890a1",
    level=5,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=Melee(1),
    target=NO_TARGET,
    attack=Attack(vs=REF, printed=10),
    trigger="an enemy marked by it shifts",
    on=Trigger(MoveStart, _marked_shifts, "an enemy marked by it shifts"),
)
def m115890a1(c: Cast) -> None:
    """"Falls prone, and it uses longsword against it" -- the printed follow
    up is the block's own basic attack, used rather than copied."""
    foe = _triggering_enemy(c)
    if foe is None:
        return
    if c.strike(on=foe):
        c.prone(on=foe)
        c.use_power("m115890a0", on=foe)


@power(
    "m115890a2",
    level=5,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(10),
    target=NO_TARGET,
    trigger="an enemy hits it",
    on=Trigger(Hit, targets_me, "an enemy hits it"),
)
def m115890a2(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is not None and foe in c.enemies():
        c.mark(on=foe, until=When.EOTNT)


# ==========================================================================
# m1403
# ==========================================================================


@power(
    "m1403a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 5),
)
def m1403a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS, ongoing=(5, DamageType.UNTYPED))


@power(
    "m1403a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d6", 5),
)
def m1403a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5)


@power(
    "m1403a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=UpTo(2),
)
def m1403a2(c: Cast) -> None:
    """"A claw attack against one target and a [bite] attack against
    another" is this row's own per-target body, claw for the first and the
    named second row for the other."""
    if c.first:
        c.use_power("m1403a0", on=c.target)
    else:
        c.use_power("m1403a1", on=c.target)


@power(
    "m1403a3",
    level=5,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is missed by a melee attack",
    on=Trigger(Miss, _missed_me_in_melee, "it is missed by a melee attack"),
)
def m1403a3(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is not None:
        c.use_power("m1403a1", on=foe)


@power(
    "m1403a4",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.ACID],
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("1d10", 3, dtype=DamageType.ACID, kind=LIMITED),
)
def m1403a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(2)
        c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS, ongoing=(5, DamageType.ACID))


@power(
    "m1403a5",
    level=5,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ACID],
    trigger="it is first bloodied",
    on=Trigger(Bloodied, about_me, "it is first bloodied"),
)
def m1403a5(c: Cast) -> None:
    _recharge_and_fire(c, "m1403a4")


@power(
    "m1403a6",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=8),
)
def m1403a6(c: Cast) -> None:
    """The stun plays. The Aftereffect -- a penalty that follows once the
    stun itself ends -- has no hold to hang on; see the module docstring."""
    if c.strike():
        victim = c.target
        held = c.stunned(until=When.EONT)
        c.aftereffect(held, lambda: c.penalty("attack", 2, until=When.SAVE_ENDS, on=victim))

# ==========================================================================
# m1422
# ==========================================================================


@power(
    "m1422a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 5),
)
def m1422a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS, ongoing=(5, DamageType.UNTYPED))


@power(
    "m1422a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d6", 5),
)
def m1422a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5)


@power(
    "m1422a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=UpTo(2),
)
def m1422a2(c: Cast) -> None:
    if c.first:
        c.use_power("m1422a0", on=c.target)
    else:
        c.use_power("m1422a1", on=c.target)


@power(
    "m1422a3",
    level=5,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is missed by a melee attack",
    on=Trigger(Miss, _missed_me_in_melee, "it is missed by a melee attack"),
)
def m1422a3(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is not None:
        c.use_power("m1422a1", on=foe)


@power(
    "m1422a4",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.ACID],
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("1d10", 3, dtype=DamageType.ACID, kind=LIMITED),
)
def m1422a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(2)
        c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS, ongoing=(5, DamageType.ACID))


@power(
    "m1422a5",
    level=5,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ACID],
    trigger="it is first bloodied",
    on=Trigger(Bloodied, about_me, "it is first bloodied"),
)
def m1422a5(c: Cast) -> None:
    _recharge_and_fire(c, "m1422a4")


@power(
    "m1422a6",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=8),
)
def m1422a6(c: Cast) -> None:
    if c.strike():
        victim = c.target
        held = c.stunned(until=When.EONT)
        c.aftereffect(held, lambda: c.penalty("attack", 2, until=When.SAVE_ENDS, on=victim))

# ==========================================================================
# m1436
# ==========================================================================


@power(
    "m1436a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d6", 6, dtype=DamageType.FIRE),
)
def m1436a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1436a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d6", 6),
)
def m1436a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1436a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
)
def m1436a2(c: Cast) -> None:
    _twice(c, "m1436a1")


@power(
    "m1436a3",
    level=5,
    usage=ENCOUNTER,
    action=REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    attack=Attack(vs=REF, printed=11),
    damage=Damage("1d10", 6, kind=LIMITED),
    trigger="an enemy moves to a position where it flanks it",
    on=Trigger(Moved, _moved_to_flank_me, "an enemy moves to a position where it flanks it"),
)
def m1436a3(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is None:
        return
    if c.strike(on=foe):
        c.hit(on=foe)
        c.push(1, on=foe)


@power(
    "m1436a4",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("1d10", 4, dtype=DamageType.FIRE, kind=LIMITED, half_on_miss=True),
)
def m1436a4(c: Cast) -> None:
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)
    if c.first:
        _recharge_when_bloodied(c)


# ==========================================================================
# m1877
# ==========================================================================


@power(
    "m1877a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d8", 5),
)
def m1877a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1877a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=10),
)
def m1877a1(c: Cast) -> None:
    if c.strike():
        c.grab()
        victim = c.target
        if victim is not None:
            c.penalty("escape", 5, on=victim)


@power(
    "m1877a2",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1877a2(c: Cast) -> None:
    _rises_unless(c, 10, DamageType.FIRE, DamageType.RADIANT)


@power(
    "m1877a3",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.kill()",),
)
def m1877a3(c: Cast) -> None:
    """"A critical hit reduces it to 0" is approximated as damage equal to
    its current hit points -- `c.flat` goes through resistance and temporary
    hit points, where a true kill would not, which is the named gap sixteen
    other rows already carry under this symbol."""
    me, ref = c.me, c.ref

    def shattered(ev: Hit) -> None:
        if ev.target != me or not ev.critical:
            return
        from combat_engine.engine import Health

        body = c.world.get(me, Health)
        if body is not None and body.hp > 0:
            c.flat(body.hp, on=me)

    c.watch(Hit, shattered, until=When.ENCOUNTER, on=me, label=f"{ref} brittle")


# ==========================================================================
# m3193
# ==========================================================================


@power(
    "m3193a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d10", 4),
)
def m3193a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m3193a1",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.RADIANT],
    attack=Attack(vs=WILL, printed=7),
    damage=Damage("2d10", 2, dtype=DamageType.RADIANT, kind=LIMITED, half_on_miss=True),
)
def m3193a1(c: Cast) -> None:
    """"Targets undead" is narrower than the burst's own `EACH_ENEMY`, so a
    creature that is not undead is simply never rolled against."""
    victim = c.target
    if victim is None or not c.is_kind("undead", on=victim):
        return
    if c.strike():
        c.hit()
        c.push(3)
        c.condition(Condition.IMMOBILIZED, until=When.EONT)
    else:
        c.hit(half=True)


@power(
    "m3193a2",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    once_per_round=True,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=11),
)
def m3193a2(c: Cast) -> None:
    if c.strike():
        c.slide(1)
        c.condition(Condition.WEAKENED, until=When.SAVE_ENDS)


@power(
    "m3193a3",
    level=5,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Melee(1),
    target=ONE_ALLY,
    keywords=[Keyword.HEALING],
)
def m3193a3(c: Cast) -> None:
    mate = c.target
    if mate is None:
        return
    c.spend_surge(on=mate)
    c.heal(c.surge_value(of=mate), on=mate)
    c.condition(Condition.WEAKENED, on=mate, until=When.EONT)


# ==========================================================================
# m3236
# ==========================================================================


@power(
    "m3236a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d8", 5),
)
def m3236a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m3236a1",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d8", 5, kind=LIMITED),
)
def m3236a1(c: Cast) -> None:
    """The printed Requirement naming its own longsword is not a gate
    (#366)."""
    if c.strike():
        c.hit()
        c.temp_hp(5, on=c.me)


@power(
    "m3236a2",
    level=5,
    usage=AT_WILL,
    action=REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    attack=Attack(vs=FORT, printed=10),
    damage=Damage("1d6", 5),
    trigger="an adjacent enemy moves or shifts",
    on=Trigger(MoveStart, _adjacent_enemy_moves, "an adjacent enemy moves or shifts"),
)
def m3236a2(c: Cast) -> None:
    """The printed Requirement naming its own shield is not a gate (#366).
    "Ends its move action" has no verb yet -- `c.halt(on=)` is the gap one
    other row already waits on."""
    foe = _triggering_enemy(c)
    if foe is None:
        return
    if c.strike(on=foe):
        c.hit(on=foe)
        c.push(1, on=foe)


@power(
    "m3236a3",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3236a3(c: Cast) -> None:
    """The printed Requirement naming its own shield is not a gate (#366)."""
    _bonus_beside_kin(c, 2, AC, REF)


# ==========================================================================
# m3306
# ==========================================================================


@power(
    "m3306a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d8", 5),
)
def m3306a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)
        victim = c.target
        mate = next(
            (
                a for a in c.allies()
                if a != c.me and victim is not None and c.adjacent_to(a, victim)
            ),
            None,
        )
        if mate is not None:
            c.heal(3, on=mate)


@power(
    "m3306a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d6", 5),
)
def m3306a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)
        victim = c.target
        mate = next(
            (
                a for a in c.allies()
                if a != c.me and victim is not None and c.adjacent_to(a, victim)
            ),
            None,
        )
        if mate is not None:
            c.heal(3, on=mate)


@power(
    "m3306a2",
    level=5,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(1),
    target=EACH_ALLY,
)
def m3306a2(c: Cast) -> None:
    mate = c.target
    if mate is None:
        return
    for which in ALL_DEFENCES:
        c.bonus(which, 2, on=mate, until=When.EONT)


@power(
    "m3306a3",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3306a3(c: Cast) -> None:
    c.bonus(
        AC, 2, on=c.me, until=When.ENCOUNTER, kind="racial",
        when=lambda ctx: bool(ctx.get("opportunity")),
    )


@power(
    "m3306a4",
    level=5,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is hit by an attack",
    on=Trigger(AttackRolled, _hit_me_rolled, "it is hit by an attack"),
)
def m3306a4(c: Cast) -> None:
    c.reroll_attack(keep="new")


# ==========================================================================
# m3316
# ==========================================================================


@power(
    "m3316a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d10", 4),
)
def m3316a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.SONT)


@power(
    "m3316a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d6", 4),
)
def m3316a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3316a2",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("2d8", 4, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m3316a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS)


@power(
    "m3316a3",
    level=5,
    usage=AT_WILL,
    action=REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    trigger="a marked enemy leaves an adjacent square, even if it is shifting",
    on=Trigger(MoveStart, _marked_adjacent_departs, "a marked enemy leaves an adjacent square"),
)
def m3316a3(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is not None:
        c.basic(on=foe)


# ==========================================================================
# m3500
# ==========================================================================


@power(
    "m3500a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(3),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d6", 4),
)
def m3500a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m3500a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(3),
    target=Target(
        "enemy", 1,
        label="targets a creature it has marked",
        relation=Relation.MARKED_BY,
    ),
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d10", 4, dtype=DamageType.NECROTIC),
)
def m3500a1(c: Cast) -> None:
    """"And marked" on a row only usable against something it has already marked
    is a refresh, so the mark is laid again and the clock starts over."""
    if c.strike():
        c.hit()
        c.condition(Condition.DAZED, until=When.EONT)
        c.mark(until=When.EONT)


@power(
    "m3500a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(3),
    target=Target(
        "enemy", 1,
        label="targets a dazed, stunned, or unconscious creature",
        conditions=frozenset(_DAZED_STUNNED_OUT),
    ),
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d8", 4, dtype=DamageType.NECROTIC),
)
def m3500a2(c: Cast) -> None:
    """The three conditions are the target line itself now. The `requires=`
    gate and the body's re-pick both came out: an empty pool already makes the
    row unusable, which is the refusal the gate was spelling by hand. #401."""
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.NECROTIC)


@power(
    "m3500a3",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("Budget.opportunity_turn",),
)
def m3500a3(c: Cast) -> None:
    """"Can make opportunity attacks against all enemies in reach that it has
    marked" lifts the one-opportunity-attack-per-turn budget for every one of
    them; nothing here can waive `Budget.opportunity_turn`, so the whole
    printed benefit -- more than the ordinary single opportunity attack --
    has nowhere to land."""


# ==========================================================================
# m3638
# ==========================================================================


@power(
    "m3638a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d10", 5),
)
def m3638a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m3638a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=Target(
        "enemy", 1,
        label="targets a creature it has marked",
        relation=Relation.MARKED_BY,
    ),
    keywords=[Keyword.NECROTIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d10", 5, dtype=DamageType.NECROTIC),
)
def m3638a1(c: Cast) -> None:
    """"2 necrotic damage for each square it moves away each turn (save ends
    both)" ties the per-square toll to the slow's own save: one throw ends
    both, which is what the card means by "both" when neither half is a
    `Condition` that `c.condition` can hold alongside the other."""
    foe = c.target
    if c.strike():
        c.hit()
        held = c.slowed(until=When.SAVE_ENDS)
        if held is not None:
            toll = _toll_per_square_away(c, foe)
            held.on_end.append(lambda: c.world.effects.end(toll, "saved"))


@power(
    "m3638a2",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d10", 5, kind=LIMITED),
)
def m3638a2(c: Cast) -> None:
    """The printed Requirement naming its own broadsword is not a gate
    (#366). "Can instead ignore these effects" is the target's own choice,
    which is what `c.may` asks of whoever it is about rather than the
    caster."""
    if c.strike():
        c.hit()
        victim = c.target
        if victim is None:
            return
        if c.may("ignore being pushed and knocked prone", who=victim, default=False):
            c.grants_advantage(on=victim, to="team", until=When.EONT)
        else:
            c.push(2, on=victim)
            c.prone(on=victim)


@power(
    "m3638a3",
    level=5,
    usage=AT_WILL,
    action=REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    trigger="it drops to 0 hit points",
    on=Trigger(Dropped, about_me, "it drops to 0 hit points"),
)
def m3638a3(c: Cast) -> None:
    """The printed Requirement naming its own broadsword is not a gate
    (#366)."""
    foe = next((f for f in c.enemies() if c.adjacent(f)), None)
    if foe is not None:
        c.basic(on=foe)


# ==========================================================================
# m3827
# ==========================================================================


@power(
    "m3827a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d8", 5),
)
def m3827a0(c: Cast) -> None:
    _shifts_after_an_opportunity_hit(c)


@power(
    "m3827a1",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=CloseBurst(5),
    target=EACH_ALLY,
)
def m3827a1(c: Cast) -> None:
    _allies_shift(c, 3)


@power(
    "m3827a2",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m3827a2(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    c.basic(on=victim)
    if c.landed:
        _mark_and_burn(c, victim, 5)


@power(
    "m3827a3",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3827a3(c: Cast) -> None:
    _rallies_when_it_hits(c)


@power(
    "m3827a4",
    level=5,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is subjected to an effect that a save can end",
    on=Trigger(EffectApplied, _save_ends_on_me, "it is subjected to an effect that a save can end"),
)
def m3827a4(c: Cast) -> None:
    c.save(on=c.me)


@power(
    "m3827a5",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.theme()",),
)
def m3827a5(c: Cast) -> None:
    """The devil-adjacency half is exact. "Or any creature with [a named
    theme]" has no verb -- nothing in the `Cast` surface asks what theme a
    creature took at character build."""
    for which in ALL_DEFENCES:
        c.bonus(
            which, 2, on=c.me, until=When.ENCOUNTER,
            when=lambda ctx: any(c.is_kind("devil", on=w) for w in c.within(1, side="ally")),
        )


# ==========================================================================
# m3977
# ==========================================================================


@power(
    "m3977a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d6", 4),
)
def m3977a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS)


@power(
    "m3977a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=Target(
        "enemy", 1,
        label="targets an immobilized, stunned, or unconscious creature",
        conditions=frozenset(_IMMOBILE_STUNNED_OUT),
    ),
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d6", 4),
)
def m3977a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.DAZED, until=When.SAVE_ENDS, ongoing=(5, DamageType.UNTYPED))


@power(
    "m3977a2",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3977a2(c: Cast) -> None:
    """Rough ground costs it nothing while it shifts, and nothing else.

    `when="shift"` is the narrowing every one of these cards prints and this
    verb could not say. It is spent in the *search*: a square of difficult
    terrain costs two, a shift is one, so without the exemption the square is
    never offered as a shift destination at all.
    """
    c.ignores_difficult(on=c.me, until=When.ENCOUNTER, when="shift")


# ==========================================================================
# m4177
# ==========================================================================


@power(
    "m4177a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.THUNDER],
    attack=Attack(vs=REF, printed=10),
    damage=Damage("1d6", 5),
)
def m4177a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.damage("1d6", dtype=DamageType.THUNDER)


@power(
    "m4177a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=10),
    damage=Damage("1d8", 5),
)
def m4177a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4177a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
)
def m4177a2(c: Cast) -> None:
    _twice(c, "m4177a1")


@power(
    "m4177a3",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(4),
    target=EACH_ENEMY,
    keywords=[Keyword.THUNDER],
    attack=Attack(vs=FORT, printed=8),
    damage=Damage("3d6", 4, dtype=DamageType.THUNDER, kind=LIMITED),
)
def m4177a3(c: Cast) -> None:
    if c.strike():
        c.hit()
    if c.first:
        _recharge_when_bloodied(c)


# ==========================================================================
# m4740
# ==========================================================================


@power(
    "m4740a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d8", 6),
)
def m4740a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        _high_crit(c, "1d12")
        c.mark(until=When.EONT)


@power(
    "m4740a1",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=Target(
        "enemy", 1,
        label="targets a creature it has marked",
        relation=Relation.MARKED_BY,
    ),
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=FORT, printed=8),
    damage=Damage("1d8", 6, kind=LIMITED),
)
def m4740a1(c: Cast) -> None:
    """Slowed and weakened under one save, then a Fortitude penalty after.

    One `c.condition` call carries both conditions, so the card's "save ends
    both" gets the single throw it prints, and the Aftereffect hangs off that
    one hold.
    """
    victim = c.target
    if c.strike():
        c.hit()
        held = c.condition(
            Condition.SLOWED, Condition.WEAKENED, until=When.SAVE_ENDS
        )
        c.aftereffect(held, lambda: c.penalty(FORT, 2, until=When.EONT, on=victim))


@power(
    "m4740a2",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=10),
    damage=Damage("3d8", 4, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m4740a2(c: Cast) -> None:
    """"Targets non-aberrant creatures" -- an aberrant creature in the burst
    is simply never rolled against."""
    victim = c.target
    if victim is None or c.is_kind("aberrant", on=victim):
        return
    if c.strike():
        c.hit()


@power(
    "m4740a3",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    requires=_m4741_within(5),
    requires_text="while within 5 squares of a m4741",
)
def m4740a3(c: Cast) -> None:
    """"Characters do not earn experience for killing [these] summoned this
    way" is a scoring note with no combat meaning and is not modelled. The
    spawn, its placement beside the m4741, its immediate basic attack and its
    extra turn are."""
    anchor = next(
        (
            w for w in creatures(c.world)
            if (ident := c.world.get(w, Ident)) is not None
            and ident.ref == "m4741"
            and c.distance(w) <= 5
        ),
        None,
    )
    if anchor is None:
        return
    sq = _free_square_beside(c, anchor)
    if sq is None:
        return
    spawned = c.summon("m4742", at=sq)
    if not spawned:
        return
    foe = next((f for f in c.enemies() if distance_between(c.world, spawned, f) <= 10), None)
    if foe is not None:
        c.basic(who=spawned, on=foe)
    c.extra_turn(at=spawned)


@power(
    "m4740a4",
    level=5,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is missed by a melee attack",
    on=Trigger(Miss, _missed_me_in_melee, "it is missed by a melee attack"),
)
def m4740a4(c: Cast) -> None:
    c.shift(1)


# ==========================================================================
# m5083
# ==========================================================================


@power(
    "m5083a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d6", 5),
)
def m5083a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5083a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d6", 5),
)
def m5083a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5083a2",
    level=5,
    usage=Usage.RECHARGE,
    recharge=5,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d6", 8, kind=LIMITED),
)
def m5083a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)
    if c.first:
        _recharge_when_bloodied(c)


@power(
    "m5083a3",
    level=5,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it drops to 0 hit points",
    on=Trigger(Dropped, about_me, "it drops to 0 hit points"),
)
def m5083a3(c: Cast) -> None:
    c.grant_action_point(1, on=c.me)


# ==========================================================================
# m5361
# ==========================================================================


@power(
    "m5361a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d10", 2),
)
def m5361a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m5361a1",
    level=5,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m5361a1(c: Cast) -> None:
    c.teleport(5)


@power(
    "m5361a2",
    level=5,
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.ILLUSION, Keyword.PSYCHIC, Keyword.WEAPON],
    attack=Attack(vs=WILL, printed=8),
    damage=Damage("2d6", 4, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m5361a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.BLINDED, until=When.EONT)
        c.condition(Condition.SLOWED, until=When.SAVE_ENDS)


# ==========================================================================
# m5407
# ==========================================================================


@power(
    "m5407a0",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5407a0(c: Cast) -> None:
    me = c.me
    c.aura(1, label=f"{c.ref} aura", until=When.ENCOUNTER, on=me)

    def tagged(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == me or team(c.world, ev.actor) is team(c.world, me):
            return
        if distance_between(c.world, me, ev.actor) > 1:
            return
        c.mark(on=ev.actor, until=When.SONT)

    c.watch(TurnStart, tagged, until=When.ENCOUNTER, on=me, label=f"{c.ref} mark")


@power(
    "m5407a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d10", 4),
)
def m5407a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5407a2",
    level=5,
    usage=ENCOUNTER,
    uses=2,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d10", 4, kind=LIMITED),
)
def m5407a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(3)


@power(
    "m5407a3",
    level=5,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(1),
    target=EACH_OTHER,
    attack=Attack(vs=REF, printed=8),
    damage=Damage("1d6", 4, kind=LIMITED),
)
def m5407a3(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5407a4",
    level=5,
    usage=AT_WILL,
    action=FREE,
    reach=Melee(1),
    target=NO_TARGET,
    attack=Attack(vs=REF, printed=8),
    trigger="an adjacent enemy it has marked would move or shift",
    on=Trigger(
        MoveStart, _marked_adjacent_departs, "an adjacent enemy it has marked would move or shift"
    ),
)
def m5407a4(c: Cast) -> None:
    """Requirement: its own close-burst row must be unexpended -- checked in
    the body rather than as `requires=`, since the question is about a
    *different* row's charges and not a fact `dsl.usable` can ask of this one
    at arming time.

    The printed attack line was missing from this header and the body still
    called `c.strike()`, which raises without one. Two instruments disagreed
    about it for a reason worth keeping: this trigger wants a marked adjacent
    enemy leaving *and* the burst unexpended, which `audit.py`'s board never
    arranges, so the row reported unusable and the raise sat latent until
    `scorecard` played a whole fight and reached it. A row that cannot be
    provoked is not a row that is known to work."""
    if "m5407a3" in c.expended():
        return
    foe = _triggering_enemy(c)
    if foe is None or c.distance(foe) > 1:
        return
    if c.strike(on=foe):
        c.flat(5, on=foe)
        c.condition(Condition.SLOWED, until=When.EOT, on=foe)


# ==========================================================================
# m5446
# ==========================================================================


@power(
    "m5446a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.THUNDER],
    attack=Attack(vs=REF, printed=8),
    damage=Damage("1d6", 6),
)
def m5446a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.damage("1d6", dtype=DamageType.THUNDER)


@power(
    "m5446a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=8),
    damage=Damage("1d8", 9),
)
def m5446a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5446a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
)
def m5446a2(c: Cast) -> None:
    _twice(c, "m5446a1")


@power(
    "m5446a3",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(4),
    target=EACH_ENEMY,
    keywords=[Keyword.THUNDER],
    attack=Attack(vs=FORT, printed=8),
    damage=Damage("3d6", 4, dtype=DamageType.THUNDER, kind=LIMITED),
)
def m5446a3(c: Cast) -> None:
    if c.strike():
        c.hit()
    if c.first:
        _recharge_when_bloodied(c)


# ==========================================================================
# m5681
# ==========================================================================


@power(
    "m5681a0",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5681a0(c: Cast) -> None:
    me = c.me

    def shook(ev: DamageApplied) -> None:
        if getattr(ev, "target", None) != me:
            return
        if getattr(ev, "dtype", None) != DamageType.RADIANT and DamageType.RADIANT not in (
            getattr(ev, "dtypes", None) or ()
        ):
            return
        eff = _held_by_me(c, Condition.IMMOBILIZED, Condition.STUNNED)
        if eff is not None:
            c.world.effects.save(eff)

    c.watch(DamageApplied, shook, until=When.ENCOUNTER, on=me, label=f"{c.ref} ward")


@power(
    "m5681a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d6", 6),
)
def m5681a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS)


@power(
    "m5681a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
)
def m5681a2(c: Cast) -> None:
    _twice(c, "m5681a1")


@power(
    "m5681a3",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=Target(
        "enemy", 1,
        label="one immobilized, restrained, stunned, or unconscious creature",
        conditions=frozenset(_HELPLESS_FOUR),
    ),
    attack=Attack(vs=AC, printed=10),
    damage=Damage("4d6", 6),
)
def m5681a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.STUNNED, until=When.SAVE_ENDS)


@power(
    "m5681a4",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="an enemy adjacent to it uses an attack power that does not include it",
    on=Trigger(
        PowerUsed, _adjacent_foe_looks_away,
        "an enemy adjacent to it uses an attack power that does not include it",
    ),
)
def m5681a4(c: Cast) -> None:
    """"Uses [its hold attack] against the triggering enemy, even if that
    enemy is not held" -- `c.use_power` runs the named row's body directly,
    which is what lets this bypass that row's own target restriction."""
    foe = _triggering_enemy(c)
    if foe is not None:
        c.use_power("m5681a3", on=foe)
    if c.first:
        _recharge_when_bloodied(c)


# ==========================================================================
# m5800
# ==========================================================================


@power(
    "m5800a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d10", 8),
)
def m5800a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5800a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d10", 7),
)
def m5800a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        victim = c.target
        if victim is None:
            return
        c.grants_advantage(on=victim, to="team", until=When.EONT)
        mate = next(
            (a for a in c.allies() if a != c.me and distance_between(c.world, a, victim) <= 5),
            None,
        )
        if mate is not None:
            c.grant_attack(mate, on=victim)


@power(
    "m5800a2",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=8),
    damage=Damage("2d6", 5, dtype=DamageType.FIRE, kind=LIMITED),
)
def m5800a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.DAZED, until=When.SAVE_ENDS)
    if c.first:
        for mate in c.in_squares(c.area(), side="ally"):
            c.temp_hp(5, on=mate)


@power(
    "m5800a3",
    level=5,
    usage=AT_WILL,
    action=OPPORTUNITY,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=9),
    trigger="an enemy leaves a square adjacent to it",
    on=Trigger(OpportunityWindow, _my_opportunity, "an enemy leaves a square adjacent to it"),
)
def m5800a3(c: Cast) -> None:
    foe = getattr(c.trigger, "provoker", None)
    if foe is None:
        return
    if c.strike(on=foe):
        c.prone(on=foe)


# ==========================================================================
# m5887
# ==========================================================================


@power(
    "m5887a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d6", 6),
)
def m5887a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.SLOWED, until=When.EOTNT)
        c.mark(until=When.EOTNT)


@power(
    "m5887a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=8),
    damage=Damage("1d6", 6),
)
def m5887a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m5887a2",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(2),
    target=UpTo(2),
)
def m5887a2(c: Cast) -> None:
    if c.first:
        c.use_power("m5887a0", on=c.target)
    else:
        c.use_power("m5887a1", on=c.target)


@power(
    "m5887a3",
    level=5,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(5),
    target=NO_TARGET,
    trigger="an enemy within 5 squares of it marks it",
    on=Trigger(RelationSet, _marked_me_from_afar(5), "an enemy within 5 squares of it marks it"),
)
def m5887a3(c: Cast) -> None:
    foe = getattr(c.trigger, "source", None)
    if foe is not None:
        c.mark(on=foe, until=When.EOTNT)


# ==========================================================================
# m6040
# ==========================================================================


@power(
    "m6040a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d10", 5),
)
def m6040a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6040a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d10", 5),
)
def m6040a1(c: Cast) -> None:
    """"Before the attack" is an ordering, not a window -- the shift happens
    first in the body, so the ally can step into reach of the swing that
    follows."""
    victim = c.target
    mate = next(
        (
            a for a in c.allies()
            if a != c.me and (c.adjacent(a) or (victim is not None and c.adjacent_to(a, victim)))
        ),
        None,
    )
    if mate is not None:
        c.shift(1, who=mate)
    if c.strike():
        c.hit()


@power(
    "m6040a2",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d10", 5, kind=LIMITED),
)
def m6040a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        victim = c.target
        if victim is None:
            return
        mate = next(
            (a for a in c.allies() if a != c.me and distance_between(c.world, a, c.me) <= 5),
            None,
        )
        if mate is not None:
            c.bonus(
                "damage", 4, on=mate, until=When.EONT,
                when=lambda ctx, v=victim: ctx.get("target") == v,
            )


@power(
    "m6040a3",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FIRE, Keyword.HEALING],
    attack=Attack(vs=REF, printed=8),
    damage=Damage("2d6", 5, dtype=DamageType.FIRE, kind=LIMITED),
)
def m6040a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.DAZED, until=When.SAVE_ENDS)
    if c.first:
        for mate in c.in_squares(c.area(), side="ally"):
            c.heal(10, on=mate)
        _recharge_when_bloodied(c)


@power(
    "m6040a4",
    level=5,
    usage=AT_WILL,
    action=REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=FORT, printed=8),
    damage=Damage("1d10", 6),
    trigger="an enemy misses it with an attack",
    on=Trigger(Miss, targets_me, "an enemy misses it with an attack"),
)
def m6040a4(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is None:
        return
    if c.strike(on=foe):
        c.hit(on=foe)
        c.prone(on=foe)


# ==========================================================================
# m6512
# ==========================================================================


@power(
    "m6512a0",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6512a0(c: Cast) -> None:
    """Regeneration 5, switched off for a turn by fire or acid."""
    heals = c.regeneration(5, until=When.ENCOUNTER, on=c.me)
    c.suspend_when(
        heals, DamageApplied,
        lambda ev: ev.target == c.me
        and bool({DamageType.FIRE, DamageType.ACID} & {ev.dtype, *ev.dtypes}),
        for_=When.EONT,
    )


@power(
    "m6512a1",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
)
def m6512a1(c: Cast) -> None:
    _rises_unless(c, 15, DamageType.FIRE, DamageType.ACID)


@power(
    "m6512a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d6", 6),
)
def m6512a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS)


@power(
    "m6512a3",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d10", 7),
)
def m6512a3(c: Cast) -> None:
    if c.strike():
        if c.is_(Condition.IMMOBILIZED, on=c.target):
            c.damage("2d10", 7)
        else:
            c.hit()


@power(
    "m6512a4",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
)
def m6512a4(c: Cast) -> None:
    if c.first:
        c.use_power("m6512a2", on=c.target)
    else:
        c.use_power("m6512a3", on=c.target)


@power(
    "m6512a5",
    level=5,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="an enemy makes an attack that does not include it",
    on=Trigger(PowerUsed, _any_foe_looks_away, "an enemy makes an attack that does not include it"),
)
def m6512a5(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is None:
        return
    mate = min(
        (a for a in c.enemies() if a != foe),
        key=lambda a: distance_between(c.world, foe, a),
        default=None,
    )
    if mate is None:
        return
    if c.adjacent(mate):
        c.basic(on=mate)
    else:
        c.charge_at(mate)


@power(
    "m6512a6",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is subjected to an effect that a save can end",
    on=Trigger(EffectApplied, _save_ends_on_me, "it is subjected to an effect that a save can end"),
)
def m6512a6(c: Cast) -> None:
    c.save(on=c.me)
    if c.first:
        _recharge_when_bloodied(c)


# ==========================================================================
# m6572
# ==========================================================================


@power(
    "m6572a0",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6572a0(c: Cast) -> None:
    """Read in the `BEFORE` window so `c.halve` can shave points off the
    blow before it lands, and the grabbed creature takes exactly what was
    shaved off -- "an equal amount"."""
    me = c.me

    def shared(ev: DamageApplied) -> None:
        if ev.target != me or _holding_nobody(c.world, me):
            return
        victim = next(iter(_grabbing(c)), None)
        amount = c.halve(ev)
        if victim is not None and amount > 0:
            c.flat(amount, on=victim)

    c.watch(
        DamageApplied, shared, until=When.ENCOUNTER, on=me,
        window=Window.BEFORE, label=f"{c.ref} shared pain",
    )


@power(
    "m6572a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 5),
)
def m6572a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6572a2",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=7),
    dropped=("c.conceal(except_for=)",),
)
def m6572a2(c: Cast) -> None:
    """"No creature other than it has line of sight to the grabbed target"
    has no verb -- `c.conceal(except_for=)` is the gap. The grab, the
    blind-and-restrain, the burn, tying them to the grab's own end, and the
    "recharges when it has no creature grabbed" clock are all exact."""
    me, ref = c.me, c.ref
    held = c.grab()
    if held is not None:
        body = c.condition(
            Condition.BLINDED, Condition.RESTRAINED, until=When.ENCOUNTER,
            ongoing=(10, DamageType.UNTYPED),
        )
        if body is not None:
            held.on_end.append(lambda: c.world.effects.end(body, "no longer grabbed"))
    label = f"{ref} recharge"
    if not _armed(c, label):

        def opened(ev: TurnStart) -> None:
            if ev.ghost or ev.actor != me:
                return
            if _holding_nobody(c.world, me):
                c.restore_use(ref, on=me)

        c.watch(TurnStart, opened, until=When.ENCOUNTER, on=me, label=label)


# ==========================================================================
# m6605
# ==========================================================================


@power(
    "m6605a0",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.can_hear()",),
)
def m6605a0(c: Cast) -> None:
    """"Can see **or hear** it" -- there is no hearing-distance verb, so the
    gate below is sight alone, which under-grants an ally who could hear it
    around a corner but not see it."""
    me = c.me
    c.aura(5, label=f"{c.ref} aura", until=When.ENCOUNTER, on=me)
    for mate in c.allies():
        if mate == me:
            continue
        for which in ALL_DEFENCES:
            c.bonus(
                which, 2, on=mate, until=When.ENCOUNTER, kind="power",
                when=lambda ctx, m=mate: distance_between(c.world, me, m) <= 5 and c.can_see(m),
            )


@power(
    "m6605a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d8", 4),
)
def m6605a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        _high_crit(c, "1d8")
        victim = c.target
        if victim is None:
            return
        me = c.me

        def aimed(ctx: dict[str, Any], v: int = victim) -> bool:
            return ctx.get("target") == v

        effects = [
            c.bonus(what, 2, on=mate, until=When.EONT, kind="power", when=aimed)
            for mate in c.allies() if mate != me
            for what in ("attack", "damage")
        ]

        def retaliated(ev: Hit) -> None:
            if ev.attacker != victim or ev.target != me:
                return
            for eff in effects:
                if eff is not None:
                    c.world.effects.end(eff, "it struck back")

        c.watch(Hit, retaliated, until=When.EONT, on=me, label=f"{c.ref} rally {victim}")


@power(
    "m6605a2",
    level=5,
    usage=AT_WILL,
    once_per_round=True,
    action=MINOR,
    reach=CloseBurst(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=8),
)
def m6605a2(c: Cast) -> None:
    if c.strike():
        c.push(1)


@power(
    "m6605a3",
    level=5,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is subjected to an effect that a save can end",
    on=Trigger(EffectApplied, _save_ends_on_me, "it is subjected to an effect that a save can end"),
)
def m6605a3(c: Cast) -> None:
    c.save(on=c.me)


# ==========================================================================
# m819
# ==========================================================================


@power(
    "m819a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d8", 5),
)
def m819a0(c: Cast) -> None:
    _shifts_after_an_opportunity_hit(c)


@power(
    "m819a1",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=CloseBurst(5),
    target=EACH_ALLY,
)
def m819a1(c: Cast) -> None:
    _allies_shift(c, 3)


@power(
    "m819a2",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m819a2(c: Cast) -> None:
    _rallies_when_it_hits(c)


@power(
    "m819a3",
    level=5,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is subjected to an effect that a save can end",
    on=Trigger(EffectApplied, _save_ends_on_me, "it is subjected to an effect that a save can end"),
)
def m819a3(c: Cast) -> None:
    c.save(on=c.me)


@power(
    "m819a4",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m819a4(c: Cast) -> None:
    _bonus_beside_kin(c, 2, AC)


# ==========================================================================
# m892
# ==========================================================================


@power(
    "m892a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d8", 5),
)
def m892a0(c: Cast) -> None:
    _shifts_after_an_opportunity_hit(c)


@power(
    "m892a1",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=CloseBurst(5),
    target=EACH_ALLY,
)
def m892a1(c: Cast) -> None:
    _allies_shift(c, 3)


@power(
    "m892a2",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m892a2(c: Cast) -> None:
    _rallies_when_it_hits(c)


@power(
    "m892a3",
    level=5,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is subjected to an effect that a save can end",
    on=Trigger(EffectApplied, _save_ends_on_me, "it is subjected to an effect that a save can end"),
)
def m892a3(c: Cast) -> None:
    c.save(on=c.me)


@power(
    "m892a4",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m892a4(c: Cast) -> None:
    _bonus_beside_kin(c, 2, AC)


# ==========================================================================
# m931
# ==========================================================================


@power(
    "m931a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d8", 5),
)
def m931a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m931a1",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=CloseBurst(2),
    target=EACH_ALLY,
)
def m931a1(c: Cast) -> None:
    """"Each [its own kind] ally in the burst" -- counted by `Ident.ref`,
    since any ally in the burst may share a type word with it."""
    mate = c.target
    if mate is None or mate == c.me or _ref_of(c, mate) != _ref_of(c, c.me):
        return
    c.bonus("attack", 4, on=mate, until=When.ENCOUNTER, once=True)


@power(
    "m931a2",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d8", 5, kind=LIMITED),
)
def m931a2(c: Cast) -> None:
    """Immobilized, and a slow that follows once the immobilize ends."""
    victim = c.target
    if c.strike():
        c.hit()
        held = c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS)
        c.aftereffect(held, lambda: c.slowed(until=When.SAVE_ENDS, on=victim))


@power(
    "m931a3",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=10),
    damage=Damage("1d8", kind=LIMITED),
)
def m931a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.STUNNED, until=When.SAVE_ENDS)


@power(
    "m931a4",
    level=5,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m931a4(c: Cast) -> None:
    c.shift(1)


@power(
    "m931a5",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m931a5(c: Cast) -> None:
    def from_a_trap(ctx: dict[str, Any]) -> bool:
        who = ctx.get("attacker")
        return isinstance(who, int) and c.is_trap(who)

    for which in ALL_DEFENCES:
        c.bonus(which, 2, on=c.me, until=When.ENCOUNTER, when=from_a_trap)
