"""Monster abilities, level 9, soldiers -- second sweep.

41 stat blocks, 192 rows. `level_09/soldiers.py` holds the earlier sweep of
this level and is not touched here; its helpers are imported where a shape
repeats. `m80`, `m2988`, `m3063`, `m3095`, `m4846`, `m4975`, `m5050`, `m659`
and `m731` printed every row they have in that earlier file, so none of them
appear below.

Conventions kept from every level below this one:

* numbers load from `game.db` -- the attack line is `Attack(vs=AC,
  printed=N)` exactly as printed, and the damage line is header data so an
  MM1 block can be rescaled to MM3 maths later;
* a trait costs no action, has no target, and arms once at the start of the
  fight, whatever the compendium's action column claims;
* a printed Requirement naming the creature's own kit (a shield, a
  broadsword, a lance) is not a gate (#366) and is left off;
* "until the end of **its** next turn" -- naming the target rather than the
  attacker by name -- is `When.EOTNT`, not the usual `EONT`. Two marks and
  one immobilize in this brief are written this way on purpose; every other
  mark here names the attacker and stays `EONT`. "Until the **start** of"
  is `SONT` (the attacker's turn) or `SOTNT` (the target's), by the same
  rule, and both appear once.
* a close burst or blast naming no target set takes **enemies**, and only
  "creatures in the burst/blast" written outright takes everyone.

Three gaps this file is the first to need, confirmed absent before marking:

* **No fact asks "did this creature just charge."** `by_charge` reads an
  *event* after the fact; a `requires=` gate only ever gets `(world, eid)`
  and nothing on the bus. `query.charged(world, eid)` is the missing
  symbol. m3249a5.
* **No parameter narrows `c.cannot_attack` to opportunity attacks only.**
  It bars everything the named creature might do, which is wider than
  "cannot make opportunity attacks against it." m4005a0.
* **No parameter narrows `c.no_healing` to healing surges.** It blocks
  every route back to full, wider than "cannot spend a healing surge."
  m5877a0.

Two more are old gaps this brief hits again, under the markers already in
the tree for them: `c.grab(dc=)` (no escape DC) and `Condition.DISEASED`
(no disease track at all).
"""

from __future__ import annotations

from combat_engine.content.monsters.level_02.artillery_sa import ALL_DEFENCES
from combat_engine.content.monsters.level_02.soldiers_sa import (
    _armed,
    _free_square_beside,
    _is_attack,
    _prone_enemy_in_reach,
    _recharge_when_bloodied,
    _ref_of,
    _square_of,
)
from combat_engine.content.monsters.level_03.lurkers_sa import _restricted_to
from combat_engine.content.monsters.level_03.soldiers_sa import (
    _adjacent_foe_looks_away,
    _marked_shifts,
    _secondary,
)
from combat_engine.content.monsters.level_07.lurkers import _shift_beside
from combat_engine.content.monsters.level_07.soldiers import _aura, _hands_free, _holding
from combat_engine.content.monsters.level_07.soldiers_sa import (
    _marked_by_me_looks_away,
    _marked_within_looks_away,
    _marked_within_moves_away,
)
from combat_engine.content.monsters.level_08.soldiers_sa import _slain_rises_as
from combat_engine.content.monsters.level_09.soldiers import _floored, _refuses_the_shove
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
    Health,
    Keyword,
    Melee,
    MeleeOrRanged,
    Mod,
    Ranged,
    Relation,
    Size,
    Target,
    UpTo,
    Usage,
    When,
    Window,
    World,
    get,
    power,
    spread,
)
from combat_engine.engine.events import (
    AttackDeclared,
    AttackRolled,
    Bloodied,
    ConditionApplied,
    DamageApplied,
    DamageRolled,
    Dropped,
    Hit,
    MoveEnd,
    MoveStart,
    PowerUsed,
    RelationCleared,
    SurgeSpent,
    TurnEnd,
    TurnStart,
    ZoneEntered,
)
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import distance_between, flanked_by, team
from combat_engine.engine.triggers import (
    Trigger,
    about_me,
    by_me,
    by_melee,
    targets_me,
    would_hit_me,
)

#: The five elements a handful of these blocks let their victim, or their
#: own choice of damage, land in.
_FIVE_ELEMENTS = (
    DamageType.ACID,
    DamageType.COLD,
    DamageType.FIRE,
    DamageType.LIGHTNING,
    DamageType.THUNDER,
)


def _targeted_by_melee(world: World, me: int, ev: AttackDeclared) -> bool:
    """"It is targeted by a melee attack." `AttackDeclared` names the
    subject `target`, not `actor` -- `about_me` would be false forever."""
    return getattr(ev, "target", None) == me and by_melee(world, me, ev)


def _opp_or_immediate_melee(world: World, me: int, ev: Hit) -> bool:
    """"When hit by an opportunity attack or an immediate-action melee
    attack." An opportunity attack is `ActionType.OPPORTUNITY`; the other
    two immediate kinds cover the rest of the sentence."""
    if getattr(ev, "target", None) != me:
        return False
    row = get(ev.power)
    if row is None or row.reach is None or row.reach.kind != "melee":
        return False
    return row.action in (
        ActionType.OPPORTUNITY,
        ActionType.IMMEDIATE_INTERRUPT,
        ActionType.IMMEDIATE_REACTION,
    )


def _looked_away_in_aura(radius: int):  # noqa: ANN202
    """"An enemy in the aura makes an attack that doesn't include it" --
    with no mark required, unlike the level-7 helper this is beside."""

    def gate(world: World, me: int, ev: PowerUsed) -> bool:
        actor = getattr(ev, "actor", None)
        if actor is None or actor == me or not _is_attack(ev.power):
            return False
        if team(world, actor) is team(world, me):
            return False
        if me in getattr(ev, "targets", ()):
            return False
        return distance_between(world, me, actor) <= radius

    return gate


def _entered_flank_with_me(world: World, me: int, ev: MoveEnd) -> bool:
    """"An enemy moves into a position flanking it." Asked after the move,
    which is the only moment "flanking" is ever true."""
    actor = getattr(ev, "actor", None)
    if actor is None or actor == me or team(world, actor) is team(world, me):
        return False
    return flanked_by(world, me, actor)


# ==========================================================================
# m1111
# ==========================================================================


@power(
    "m1111a0", level=9, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, attack=Attack(vs=AC, printed=16), damage=Damage("1d8", 7),
)
def m1111a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark()


@power(
    "m1111a1", level=9, usage=Usage.RECHARGE, recharge=5, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, attack=Attack(vs=AC, printed=16), damage=Damage("2d8", 7, kind=LIMITED),
)
def m1111a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(3)


@power(
    "m1111a2", level=9, usage=AT_WILL, action=INTERRUPT, reach=Melee(1), target=NO_TARGET,
    attack=Attack(vs=FORT, printed=14), damage=Damage("1d6", 5),
    trigger="it is hit by a melee attack",
    on=Trigger(Hit, _targeted_by_melee, "it is hit by a melee attack"),
)
def m1111a2(c: Cast) -> None:
    attacker = getattr(c.trigger, "attacker", None)
    if attacker is not None and c.strike(on=attacker):
        c.hit(on=attacker)
    for which in (AC, REF):
        c.bonus(which, 2, on=c.me, until=When.EONT)


@power(
    "m1111a3", level=9, usage=ENCOUNTER, action=MOVE, reach=PERSONAL, target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m1111a3(c: Cast) -> None:
    c.teleport(5)


@power(
    "m1111a4", level=9, usage=ENCOUNTER, action=REACTION, reach=PERSONAL, target=SELF,
    trigger="an enemy moves into a position flanking it",
    on=Trigger(MoveEnd, _entered_flank_with_me, "an enemy moves into a position flanking it"),
)
def m1111a4(c: Cast) -> None:
    c.teleport(5)


# ==========================================================================
# m1144
# ==========================================================================


@power(
    "m1144a0", level=9, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.NECROTIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15), damage=Damage("1d8", 5),
)
def m1144a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.spend_surge()
        c.immobilized(until=When.SAVE_ENDS)


def _an_immobilized_enemy_m1144(world: World, eid: int) -> bool:
    from combat_engine.engine.query import enemies, is_

    return any(
        is_(world, foe, Condition.IMMOBILIZED) and distance_between(world, eid, foe) <= 5
        for foe in enemies(world, eid)
    )


@power(
    "m1144a1", level=9, usage=Usage.RECHARGE, recharge=5, action=STANDARD, reach=Ranged(5),
    target=NO_TARGET, keywords=[Keyword.HEALING, Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("2d8", 5, dtype=DamageType.NECROTIC, kind=LIMITED),
    requires=_an_immobilized_enemy_m1144,
    requires_text="an immobilized creature must be within 5 squares",
)
def m1144a1(c: Cast) -> None:
    """"The m80 regains 10 hit points" names a different block's id for
    itself -- the same ref-shaped misprint AUTHORING already logs."""
    held = sorted(
        foe for foe in c.enemies() if c.is_(Condition.IMMOBILIZED, on=foe) and c.distance(foe) <= 5
    )
    victim = c.choose(held, "m1144a1: which held creature") if held else None
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)
        c.heal(10, on=c.me)


# ==========================================================================
# m115867
# ==========================================================================


@power(
    "m115867a0", level=9, usage=AT_WILL, action=STANDARD, reach=Melee(2),
    target=ONE_CREATURE, attack=Attack(vs=AC, printed=14), damage=Damage("2d8", 8),
)
def m115867a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m115867a1", level=9, usage=Usage.RECHARGE, recharge=5, action=STANDARD, reach=CloseBurst(2),
    target=EACH_OTHER, keywords=[Keyword.THUNDER],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("4d6", 5, dtype=DamageType.THUNDER, kind=LIMITED),
)
def m115867a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m115867a2", level=9, usage=AT_WILL, action=OPPORTUNITY, reach=Melee(1), target=NO_TARGET,
    attack=Attack(vs=AC, printed=14), damage=Damage("2d8", 8),
    trigger="an adjacent enemy makes an attack that does not include it",
    on=Trigger(PowerUsed, _adjacent_foe_looks_away, "an adjacent enemy attacks without it"),
)
def m115867a2(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    if foe is None:
        return
    if c.strike(on=foe):
        c.hit(on=foe)
    else:
        c.flat(5, on=foe)


# ==========================================================================
# m1177
# ==========================================================================


@power(
    "m1177a0", level=9, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, attack=Attack(vs=AC, printed=15), damage=Damage("1d10", 6),
)
def m1177a0(c: Cast) -> None:
    """The escape DC is the grab's own, worked out from the creature rather
    than printed on the card, so the hold is all there is to write."""
    if c.strike():
        c.hit()
        c.grab()


@power(
    "m1177a1", level=9, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=Target(
        side="enemy", count=1, label="creature grabbed by it",
        relation=Relation.GRABBED_BY,
    ),
    attack=Attack(vs=FORT, printed=13), damage=Damage("2d6", 12),
)
def m1177a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.EONT)


@power(
    "m1177a2", level=9, usage=AT_WILL, action=INTERRUPT, reach=PERSONAL, target=NO_TARGET,
    attack=Attack(vs=WILL, printed=11),
    trigger="it is targeted by a melee attack",
    on=Trigger(AttackDeclared, _targeted_by_melee, "it is targeted by a melee attack"),
)
def m1177a2(c: Cast) -> None:
    """"The attacker must target a different creature or end its attack" --
    written as ending it outright, the stronger of the two choices and the
    one with no creature-picker to drive."""
    attacker = getattr(c.trigger, "attacker", None)
    if attacker is not None and c.strike(on=attacker):
        c.cancel()


@power(
    "m1177a3", level=9, usage=Usage.RECHARGE, recharge=6, action=STANDARD, reach=Ranged(10),
    target=ONE_CREATURE, attack=Attack(vs=WILL, printed=11),
    # The card prints no Hit damage -- the clause is a pull and a daze --
    # so this is flat zero, and flat is an empty dice string. "0" is
    # truthy, so it would reach `rng.roll` and raise the moment anything
    # called `c.hit()`.
    damage=Damage("", 0, kind=LIMITED),
)
def m1177a3(c: Cast) -> None:
    if c.strike():
        c.pull(5)
        c.dazed(until=When.SAVE_ENDS)


@power(
    "m1177a4", level=9, usage=ENCOUNTER, action=MOVE, reach=PERSONAL, target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m1177a4(c: Cast) -> None:
    c.teleport(3)


# ==========================================================================
# m1794
# ==========================================================================


@power(
    "m1794a0", level=9, usage=AT_WILL, action=STANDARD, reach=Melee(2),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16), damage=Damage("2d4", 6),
)
def m1794a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(1)


@power(
    "m1794a1", level=9, usage=ENCOUNTER, action=STANDARD, reach=Ranged(5),
    target=ONE_CREATURE, keywords=[Keyword.CONJURATION, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16), damage=Damage("3d10", 5, kind=LIMITED),
)
def m1794a1(c: Cast) -> None:
    """The duplicates are real creatures under this one's own ref, each
    making one melee basic attack; `World.despawn` is what takes the
    unchosen ones back off the board at the end of the turn, not a killing
    blow -- the same verb the level-10 sweep settled on for exactly this
    shape."""
    me = c.me
    if c.strike():
        c.hit()
    if not c.first:
        return
    here = _square_of(c, me)
    if here is None:
        return
    ref = _ref_of(c, me)
    dups: list[int] = []
    for sq in sorted(spread({here}, 5)):
        if len(dups) >= 4:
            break
        if sq == here or not c.world.grid.passable(sq) or c.world.grid.occupant(sq) is not None:
            continue
        dup = c.summon(ref, at=sq)
        if dup:
            dups.append(dup)
    for fighter in (me, *dups):
        c.basic(who=fighter)

    def cull(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor != me:
            return
        keep = c.choose([me, *dups], "m1794a1: which remains") or me
        for fighter in (me, *dups):
            if fighter != keep and c.world.get(fighter, Health) is not None:
                c.world.despawn(fighter)

    c.watch(TurnEnd, cull, until=When.EOT, on=me, once=True, label=f"{c.ref} cull")


@power(
    "m1794a2", level=9, usage=AT_WILL, action=FREE, reach=CloseBurst(1), target=EACH_OTHER,
    keywords=[Keyword.ACID], attack=Attack(vs=REF, printed=14),
    damage=Damage("2d6", 4, dtype=DamageType.ACID, half_on_miss=True),
    trigger="it drops to 0 hit points",
    on=Trigger(Dropped, about_me, "it drops to 0 hit points"),
)
def m1794a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.blinded(until=When.SOTNT)
    else:
        c.hit(half=True)


@power(
    "m1794a3", level=9, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET,
)
def m1794a3(c: Cast) -> None:
    """A self-drain tied to a health band, not a saveable burn -- `c.ongoing`
    is the wrong door, since nothing here is ending it with a throw. A watch
    on its own `TurnStart` is the printed clock."""
    me = c.me

    def bleed(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me or not c.bloodied(me):
            return
        c.flat(5, on=me)

    c.watch(TurnStart, bleed, until=When.ENCOUNTER, on=me, label=c.ref)


# ==========================================================================
# m1817
# ==========================================================================


@power(
    "m1817a0", level=9, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, attack=Attack(vs=AC, printed=16), damage=Damage("2d6", 6),
)
def m1817a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1817a1", level=9, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=14), damage=Damage("1d10", 9, dtype=DamageType.PSYCHIC),
)
def m1817a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1817a2", level=9, usage=ENCOUNTER, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=14), damage=Damage("2d8", 9, kind=LIMITED),
)
def m1817a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.damage("1d8", 0, dtype=DamageType.PSYCHIC)
        c.vulnerable(10, DamageType.PSYCHIC, until=When.EONT)


@power(
    "m1817a3", level=9, usage=ENCOUNTER, action=INTERRUPT, reach=PERSONAL, target=SELF,
    trigger="it would be hit by an attack",
    on=Trigger(AttackDeclared, would_hit_me, "it would be hit by an attack"),
)
def m1817a3(c: Cast) -> None:
    for which in ALL_DEFENCES:
        c.bonus(which, 2, on=c.me, until=When.EONT)


@power(
    "m1817a4", level=9, usage=ENCOUNTER, action=REACTION, reach=PERSONAL, target=SELF,
    trigger="it takes damage",
    on=Trigger(DamageApplied, targets_me, "it takes damage"),
)
def m1817a4(c: Cast) -> None:
    c.insubstantial(until=When.EONT)


# ==========================================================================
# m1827
# ==========================================================================


@power(
    "m1827a0", level=9, usage=AT_WILL, action=STANDARD, reach=Melee(2),
    target=ONE_CREATURE, attack=Attack(vs=AC, printed=16), damage=Damage("2d6", 5),
)
def m1827a0(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.hit()
        c.slide(2)
        if victim is not None:
            for mate in c.allies():
                if mate != c.me and c.adjacent_to(victim, mate):
                    c.grant_attack(mate, on=victim)


def _ally_hit_in_melee(world: World, me: int, ev: Hit) -> bool:
    actor = getattr(ev, "attacker", None)
    if actor is None or actor == me or team(world, actor) is not team(world, me):
        return False
    return by_melee(world, me, ev) and distance_between(world, me, actor) <= 3


@power(
    "m1827a1", level=9, usage=AT_WILL, action=REACTION, reach=PERSONAL, target=SELF,
    trigger="an ally within 3 squares hits an enemy with a melee attack",
    on=Trigger(Hit, _ally_hit_in_melee, "an ally within 3 squares hits with a melee attack"),
)
def m1827a1(c: Cast) -> None:
    foe = getattr(c.trigger, "target", None)
    if foe is None:
        return
    _shift_beside(c, foe, 5)
    c.use_power("m1827a0", on=foe, spend=False)


@power("m1827a2", level=9, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m1827a2(c: Cast) -> None:
    c.threatens(2)


@power("m1827a3", level=9, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m1827a3(c: Cast) -> None:
    def surrounded(ctx: dict) -> bool:
        if ctx.get("ranged"):
            return False
        victim = ctx.get("target")
        if victim is None:
            return False
        return sum(1 for a in c.allies() if c.adjacent_to(victim, a)) >= 2

    c.bonus("damage", 5, on=c.me, until=When.ENCOUNTER, when=surrounded)


# ==========================================================================
# m1915
# ==========================================================================


@power(
    "m1915a0", level=9, usage=AT_WILL, action=STANDARD, reach=Melee(2),
    target=ONE_CREATURE, keywords=[Keyword.FIRE, Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=16), damage=Damage("2d6", 6, dtype=DamageType.NECROTIC),
)
def m1915a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.FIRE)


@power(
    "m1915a1", level=9, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.FIRE, Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d8", 6, dtype=[DamageType.FIRE, DamageType.NECROTIC]),
)
def m1915a1(c: Cast) -> None:
    """One roll of two types, which is all one `Damage` can say -- fire
    stays in the header as the data a rescale reads, necrotic rides as a
    keyword."""
    if c.strike():
        c.hit()
        c.grab()


@power(
    "m1915a2", level=9, usage=AT_WILL, action=FREE, once_per_round=True, reach=Melee(1),
    target=Target(
        side="enemy", count=1, label="creature grabbed by it",
        relation=Relation.GRABBED_BY,
    ),
)
def m1915a2(c: Cast) -> None:
    """No attack roll: the printed Effect simply deals the damage."""
    c.damage("2d6", 6)


def _enemy_dropped_nearby(world: World, me: int, ev: Dropped) -> bool:
    actor = getattr(ev, "actor", None)
    return (
        actor is not None
        and actor != me
        and team(world, actor) is not team(world, me)
        and distance_between(world, me, actor) <= 2
    )


@power(
    "m1915a3", level=9, usage=AT_WILL, action=FREE, reach=PERSONAL, target=NO_TARGET,
    trigger="an enemy within 2 squares of it is reduced to 0 hit points or fewer",
    on=Trigger(Dropped, _enemy_dropped_nearby, "an enemy within 2 squares drops to 0"),
)
def m1915a3(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    if foe is not None:
        c.use_power("m1915a0", on=foe, spend=False)


@power(
    "m1915a4", level=9, usage=AT_WILL, action=FREE, reach=CloseBurst(3), target=EACH_ENEMY,
    keywords=[Keyword.FIRE, Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("2d6", 0, dtype=DamageType.FIRE, half_on_miss=True),
    trigger="it is first bloodied, and again when it drops to 0 hit points",
    on=[
        Trigger(Bloodied, about_me, "it is first bloodied"),
        Trigger(Dropped, about_me, "it drops to 0 hit points"),
    ],
)
def m1915a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.damage("2d6", 0, dtype=DamageType.NECROTIC)
    else:
        c.hit(half=True)
        c.half_damage("2d6", 0, dtype=DamageType.NECROTIC)


@power(
    "m1915a5", level=9, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET,
    out_of_combat=True,
)
def m1915a5(c: Cast) -> None:
    """A day-later rejuvenation and a ritual that forestalls it -- nothing
    a single encounter ever resolves, so there is no combat half for this
    to sit beside."""


# ==========================================================================
# m1949
# ==========================================================================


@power(
    "m1949a0", level=9, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, attack=Attack(vs=AC, printed=16), damage=Damage("2d6", 5),
    requires=_hands_free, requires_text="it must not be grabbing a creature",
)
def m1949a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.grab()


@power(
    "m1949a1", level=9, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=Target(
        side="enemy", count=1, label="creature grabbed by it",
        relation=Relation.GRABBED_BY,
    ),
    attack=Attack(vs=AC, printed=16), damage=Damage("1d10", 7),
)
def m1949a1(c: Cast) -> None:
    """The target line names a sibling id for itself -- the same ref-shaped
    misprint logged elsewhere in this tree, so the relation is read outward
    from this creature like every other."""
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)


@power(
    "m1949a2", level=9, usage=Usage.RECHARGE, recharge=4, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, attack=Attack(vs=AC, printed=16), damage=Damage("2d6", 5, kind=LIMITED),
)
def m1949a2(c: Cast) -> None:
    """Two claws at -2 each, reusing the printed total rather than the
    header's own `c.hit` -- the -2 is arithmetic a plain `c.strike()` can't
    carry."""
    victim = c.target
    if victim is None:
        return
    hits = 0
    for _ in range(2):
        if c.strike(on=victim, plus=-2):
            c.damage("2d6", 5, on=victim)
            hits += 1
    if hits >= 2:
        c.grab(on=victim)
        c.ongoing(5, on=victim)


@power(
    "m1949a3", level=9, usage=ENCOUNTER, action=STANDARD, reach=CloseBurst(2), target=EACH_ENEMY,
    keywords=[Keyword.FEAR], attack=Attack(vs=WILL, printed=14),
)
def m1949a3(c: Cast) -> None:
    if c.strike():
        c.stunned(until=When.EONT)


# ==========================================================================
# m1982
# ==========================================================================


@power(
    "m1982a0", level=9, usage=AT_WILL, action=STANDARD, reach=Melee(3),
    target=ONE_CREATURE, keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=14), damage=Damage("2d8", 4, dtype=DamageType.NECROTIC),
)
def m1982a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.grab()
        if c.crit:
            c.spend_surge()


@power(
    "m1982a1", level=9, usage=Usage.RECHARGE, recharge=5, action=MINOR, reach=CloseBurst(3),
    target=EACH_ENEMY, keywords=[Keyword.NECROTIC], attack=Attack(vs=FORT, printed=14),
)
def m1982a1(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    spot = _free_square_beside(c, c.me)
    if c.strike(on=victim):
        if spot is not None:
            c.pull(10, on=victim, to=spot)
        c.grab(on=victim)


@power(
    "m1982a2", level=9, usage=AT_WILL, action=MINOR, once_per_round=True, reach=PERSONAL,
    target=NO_TARGET,
)
def m1982a2(c: Cast) -> None:
    for victim in _holding(c):
        c.spend_surge(on=victim)


@power("m1982a3", level=9, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m1982a3(c: Cast) -> None:
    """"Can sustain a grab as a free action" has nothing to write: a grab in
    this engine already costs nothing to keep from one turn to the next --
    `c.grab` applies an `ENCOUNTER`-long hold with no action to renew. This
    row is correctly silent."""


# ==========================================================================
# m2003
# ==========================================================================


@power(
    "m2003a0", level=9, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, attack=Attack(vs=AC, printed=16), damage=Damage("1d6", 6),
)
def m2003a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.EONT)


@power(
    "m2003a1", level=9, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.PSYCHIC],
)
def m2003a1(c: Cast) -> None:
    """The printed attack line is garbled (a blank defence) and the real
    mechanic is two uses of the claw against one target, so no attack or
    damage is declared here -- both rolls are m2003a0's own."""
    victim = c.target
    if victim is None:
        return
    hits = 0
    for _ in range(2):
        c.use_power("m2003a0", on=victim, spend=False)
        if c.landed:
            hits += 1
    if hits >= 2:
        c.ongoing(5, DamageType.PSYCHIC, on=victim)
        c.mark(on=victim)


@power(
    "m2003a2", level=9, usage=AT_WILL, action=MINOR, once_per_round=True, reach=CloseBurst(3),
    target=Target(
        side="enemy", count=1, label="creature marked by it",
        relation=Relation.MARKED_BY,
    ),
    attack=Attack(vs=WILL, printed=14),
)
def m2003a2(c: Cast) -> None:
    if c.strike():
        c.condition(Condition.DOMINATED, until=When.EONT)


# ==========================================================================
# m2015
# ==========================================================================


@power("m2015a0", level=9, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m2015a0(c: Cast) -> None:
    me = c.me
    ring = c.aura(3, until=When.ENCOUNTER)

    def gnaw(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == me or ev.actor not in c.enemies():
            return
        if ev.actor not in c.world.zones.occupants(ring):
            return
        c.flat(5, dtype=DamageType.FORCE, on=ev.actor)
        c.pull(1, on=ev.actor)

    c.watch(TurnStart, gnaw, until=When.ENCOUNTER, on=me, label=c.ref)


@power("m2015a1", level=9, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m2015a1(c: Cast) -> None:
    me = c.me
    active = [True]

    def halved(ev: DamageRolled) -> None:
        if ev.target != me or not active[0] or DamageType.FORCE in ev.types():
            return
        ev.amount -= ev.amount // 2

    def shaken(ev: DamageApplied) -> None:
        if ev.target == me and DamageType.FORCE in ev.types():
            active[0] = False

    def recovers(ev: TurnStart) -> None:
        if not ev.ghost and ev.actor == me:
            active[0] = True

    c.watch(
        DamageRolled, halved, until=When.ENCOUNTER, on=me, window=Window.BEFORE,
        label=f"{c.ref} half",
    )
    c.watch(DamageApplied, shaken, until=When.ENCOUNTER, on=me, label=f"{c.ref} shaken")
    c.watch(TurnStart, recovers, until=When.ENCOUNTER, on=me, label=f"{c.ref} recovers")


@power("m2015a2", level=9, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m2015a2(c: Cast) -> None:
    me = c.me
    active = [True]

    def regen(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me or not active[0]:
            return
        if c.world.get(me, Health) is not None and c.world.get(me, Health).hp >= 1:
            c.heal(5, on=me)

    def shaken(ev: DamageApplied) -> None:
        if ev.target == me and DamageType.RADIANT in ev.types():
            active[0] = False

    def recovers(ev: TurnStart) -> None:
        if not ev.ghost and ev.actor == me:
            active[0] = True

    c.watch(TurnStart, regen, until=When.ENCOUNTER, on=me, label=f"{c.ref} regen")
    c.watch(DamageApplied, shaken, until=When.ENCOUNTER, on=me, label=f"{c.ref} shaken")
    c.watch(TurnStart, recovers, until=When.ENCOUNTER, on=me, label=f"{c.ref} recovers")


@power("m2015a3", level=9, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m2015a3(c: Cast) -> None:
    """"Free-willed" is not modelled -- the risen copy stands on its
    killer's own side, the approximation this shape always takes."""
    _slain_rises_as(c, "m2015", lambda who: c.is_kind("humanoid", on=who))


@power(
    "m2015a4", level=9, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.FORCE],
    attack=Attack(vs=FORT, printed=12), damage=Damage("2d8", 6, dtype=DamageType.FORCE),
)
def m2015a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.EONT)


@power(
    "m2015a5", level=9, usage=ENCOUNTER, action=STANDARD, reach=Melee(2),
    target=ONE_CREATURE, keywords=[Keyword.FORCE],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("3d6", 3, dtype=DamageType.FORCE, kind=LIMITED, half_on_miss=True),
)
def m2015a5(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS, ongoing=(10, DamageType.FORCE))
        c.shift(1)
    else:
        c.hit(half=True)


@power(
    "m2015a6", level=9, usage=ENCOUNTER, action=MOVE, reach=PERSONAL, target=SELF,
)
def m2015a6(c: Cast) -> None:
    c.shift(6)


@power(
    "m2015a7", level=9, usage=ENCOUNTER, action=FREE, reach=CloseBurst(5), target=EACH_ENEMY,
    keywords=[Keyword.FORCE, Keyword.TELEPORTATION],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("2d8", 6, dtype=DamageType.FORCE, half_on_miss=True),
    trigger="it drops to 0 hit points",
    on=Trigger(Dropped, about_me, "it drops to 0 hit points"),
)
def m2015a7(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.hit()
        if victim is not None:
            c.teleport(5, who=victim)
            c.prone(on=victim)
    else:
        c.hit(half=True)


# ==========================================================================
# m2078
# ==========================================================================


@power(
    "m2078a0", level=9, usage=AT_WILL, action=STANDARD, reach=Melee(2),
    target=ONE_CREATURE, keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=15), damage=Damage("3d8", 5),
)
def m2078a0(c: Cast) -> None:
    """"Slowed and -2 to attack rolls (save ends both)" is one combined
    save-ends hold, the shape `_one_save_for_both` already settled for a
    modifier beside a burn -- here beside a condition instead."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    mod = Mod(what="attack", value=-2, kind="untyped", label=c.ref)
    c.world.effects.apply(
        victim, c.me, When.SAVE_ENDS, label=f"{c.ref} hex",
        conditions=[Condition.SLOWED], mods=[(victim, mod)],
    )


@power(
    "m2078a1", level=9, usage=AT_WILL, action=STANDARD, reach=Melee(2),
    target=ONE_CREATURE, attack=Attack(vs=FORT, printed=14), damage=Damage("2d8", 5),
    requires=_hands_free, requires_text="it must not already be grabbing a creature",
)
def m2078a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.grab()


@power(
    "m2078a2", level=9, usage=AT_WILL, action=MINOR, once_per_round=True,
    target=Target(
        side="enemy", count=1, label="grabbed targets only",
        relation=Relation.GRABBED_BY,
    ),
    reach=Melee(2), keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=14), damage=Damage("1d8", 5),
)
def m2078a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.stunned(until=When.SAVE_ENDS)


# ==========================================================================
# m3249
# ==========================================================================


@power(
    "m3249a0", level=9, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17), damage=Damage("1d10", 6),
)
def m3249a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark()


@power(
    "m3249a1", level=9, usage=AT_WILL, action=MINOR, once_per_round=True, reach=Melee(1),
    target=ONE_CREATURE, attack=Attack(vs=REF, printed=15), damage=Damage("1d8", 4),
)
def m3249a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m3249a2", level=9, usage=ENCOUNTER, action=FREE, reach=Melee(1), target=NO_TARGET,
    attack=Attack(vs=AC, printed=17), damage=Damage("3d10", 4, kind=LIMITED),
    trigger="it is hit by an opportunity attack or an immediate-action melee attack",
    on=Trigger(Hit, _opp_or_immediate_melee, "hit by an opportunity or immediate melee attack"),
)
def m3249a2(c: Cast) -> None:
    attacker = getattr(c.trigger, "attacker", None)
    if attacker is not None and c.strike(on=attacker):
        c.hit(on=attacker)


@power(
    "m3249a3", level=9, usage=ENCOUNTER, action=FREE, reach=PERSONAL, target=NO_TARGET,
    trigger="it hits an enemy",
    on=Trigger(Hit, by_me, "it hits an enemy"),
)
def m3249a3(c: Cast) -> None:
    victim = getattr(c.trigger, "target", None)
    if victim is None:
        return
    extra = "1d8" if getattr(c.trigger, "power", "") == "m3249a1" else "1d10"
    c.flat(c.roll(extra), on=victim)


@power(
    "m3249a4", level=9, usage=ENCOUNTER, action=FREE, reach=PERSONAL, target=SELF,
    trigger="it is first bloodied",
    on=Trigger(Bloodied, about_me, "it is first bloodied"),
)
def m3249a4(c: Cast) -> None:
    c.temp_hp(5)


@power(
    "m3249a5", level=9, usage=AT_WILL, action=STANDARD, reach=PERSONAL, target=NO_TARGET,
    dropped=("query.charged(world, eid)",),
)
def m3249a5(c: Cast) -> None:
    """"Usable after it charges" cannot be asked from a `requires=` gate --
    nothing persists the fact that this creature's last action was a
    charge, only the live `c.charge` on the use in flight. The grant itself
    plays regardless of when it is offered."""
    near = sorted((a for a in c.allies() if a != c.me and c.distance(a) <= 10), key=c.distance)
    mate = c.choose(near, "m3249a5: which ally charges") if near else None
    if mate is None:
        return
    c.no_provoke(on=mate, until=When.EOT)
    c.command(mate, charge=True)


# ==========================================================================
# m3288
# ==========================================================================


@power(
    "m3288a0", level=9, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16), damage=Damage("1d8", 8),
)
def m3288a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark()


@power(
    "m3288a1", level=9, usage=AT_WILL, action=STANDARD, reach=Ranged(15),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16), damage=Damage("1d8", 8),
)
def m3288a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark()


@power(
    "m3288a2", level=9, usage=AT_WILL, action=STANDARD, reach=Melee(1), target=NO_TARGET,
    charges=True,
)
def m3288a2(c: Cast) -> None:
    """Both rapier swings are m3288a0's own line, so no attack or damage is
    declared here; the charge is what the printed line adds."""
    near = sorted(c.enemies(), key=c.distance)
    victim = c.choose(near, "m3288a2: which enemy it charges") if near else None
    if victim is None:
        return
    if not c.adjacent(victim):
        c.run_at(victim)
    for _ in range(2):
        c.use_power("m3288a0", on=victim, spend=False)


@power("m3288a3", level=9, usage=AT_WILL, action=STANDARD, reach=Melee(1), target=UpTo(2))
def m3288a3(c: Cast) -> None:
    if not c.first:
        return
    for victim in c.targets[:2]:
        c.use_power("m3288a0", on=victim, spend=False)


@power(
    "m3288a4", level=9, usage=ENCOUNTER, action=STANDARD, reach=Ranged(15),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=FORT, printed=16), damage=Damage("3d8", 5, kind=LIMITED),
)
def m3288a4(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.hit()
        c.mark()
        if victim is not None:
            for other in list(c.world.relations.targets(Relation.MARKED_BY, victim)):
                c.cure(Condition.MARKED, on=other)


@power("m3288a5", level=9, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m3288a5(c: Cast) -> None:
    me = c.me

    def linger(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor != me:
            return
        for foe in list(c.world.relations.targets(Relation.MARKED_BY, me)):
            if c.adjacent_to(foe, me):
                c.mark(on=foe)

    c.watch(TurnEnd, linger, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m3288a6", level=9, usage=ENCOUNTER, action=FREE, reach=PERSONAL, target=NO_TARGET,
)
def m3288a6(c: Cast) -> None:
    c.reroll_attack(keep="new")


@power(
    "m3288a7", level=9, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET,
)
def m3288a7(c: Cast) -> None:
    """Rough ground costs her nothing while she shifts, and nothing else.

    `when="shift"` is the narrowing every one of these cards prints and this
    verb could not say. It is spent in the *search*: a square of difficult
    terrain costs two, a shift is one, so without the exemption the square is
    never offered as a shift destination at all.
    """
    c.ignores_difficult(on=c.me, until=When.ENCOUNTER, when="shift")


@power(
    "m3288a8", level=9, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET,
    todo=("c.grant_trait(mount)",),
)
def m3288a8(c: Cast) -> None:
    """Bestows her own sure-footedness on whatever she is riding.

    **Re-pointed.** a7 works now, so the reason this is empty has changed:
    what is missing is a mount. Nothing on the board records that one
    creature is riding another, so there is no second creature to lay the
    trait on and no event that would say when it changes.
    """


# ==========================================================================
# m3448
# ==========================================================================


@power(
    "m3448a0", level=9, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, attack=Attack(vs=AC, printed=16), damage=Damage("1d10", 5),
)
def m3448a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark()


@power(
    "m3448a1", level=9, usage=ENCOUNTER, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.RELIABLE],
    attack=Attack(vs=REF, printed=12),
    dropped=("etl.monster.item_identity()",),
)
def m3448a1(c: Cast) -> None:
    """"The rusting item is destroyed" has nowhere to land: `c.destroy`
    already takes a `weapon=` to hand it when `Gear` is empty, but nothing
    says *which* item the target is carrying -- there is no data naming it,
    on the target's side exactly as #366 found on the caster's. The attack
    roll is real; the effect is not."""
    victim = c.target
    if victim is not None:
        c.strike(on=victim)
        c.destroy(on=victim)


@power(
    "m3448a2", level=9, usage=Usage.RECHARGE, recharge=6, action=MINOR, reach=CloseBurst(1),
    target=EACH_OTHER, attack=Attack(vs=WILL, printed=12),
)
def m3448a2(c: Cast) -> None:
    if c.strike():
        c.penalty("attack", 2, until=When.SAVE_ENDS)
        c.immobilized(until=When.SAVE_ENDS)


def _fear_attack(ev: AttackRolled) -> bool:
    row = get(ev.power)
    return row is not None and Keyword.FEAR in row.keywords


@power("m3448a3", level=9, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m3448a3(c: Cast) -> None:
    me = c.me

    def shrug(ev: AttackRolled) -> None:
        if getattr(ev, "target", None) != me or not _fear_attack(ev):
            return
        ev.result.natural = 1
        ev.result.total = -100
        c.flat(5, dtype=DamageType.PSYCHIC, on=ev.attacker)
        c.flat(5, dtype=DamageType.PSYCHIC, on=me)

    c.watch(AttackRolled, shrug, until=When.ENCOUNTER, on=me, window=Window.BEFORE, label=c.ref)


@power(
    "m3448a4", level=9, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET,
    out_of_combat=True,
)
def m3448a4(c: Cast) -> None:
    """Treasure bookkeeping -- what a destroyed item's residuum is worth and
    where it ends up afterwards -- has no combat meaning, so there is no
    half of this to write."""


# ==========================================================================
# m3592
# ==========================================================================


@power(
    "m3592a0", level=9, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16), damage=Damage("1d12", 5),
)
def m3592a0(c: Cast) -> None:
    """The printed crit line -- max die plus the static bonus -- is already
    what `c.hit` does on a crit; there is nothing extra to add."""
    if c.strike():
        c.hit()
        c.mark()


@power(
    "m3592a1", level=9, usage=AT_WILL, action=REACTION, reach=Melee(1), target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    trigger="an ally moves into a flank with it",
    on=Trigger(MoveEnd, _entered_flank_with_me, "an ally moves into a flank with it"),
)
def m3592a1(c: Cast) -> None:
    """Flanking asked generally rather than naming the exact partner --
    whoever just moved adjacent to an enemy this creature also flanks is
    close enough to "a flank with it" to count."""
    actor = getattr(c.trigger, "actor", None)
    if actor is None:
        return
    foe = next(
        (f for f in c.enemies() if c.adjacent_to(f, actor) and flanked_by(c.world, f, c.me)), None
    )
    if foe is not None:
        c.basic(on=foe)


@power(
    "m3592a2", level=9, usage=ENCOUNTER, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, attack=Attack(vs=AC, printed=15), damage=Damage("2d12", 5, kind=LIMITED),
)
def m3592a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.heal(48)


@power(
    "m3592a3", level=9, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17), damage=Damage("1d12", 5),
)
def m3592a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EOTNT)
        c.push(1)


@power(
    "m3592a4", level=9, usage=Usage.RECHARGE, recharge=5, action=MINOR, reach=CloseBlast(5),
    target=EACH_ALLY,
)
def m3592a4(c: Cast) -> None:
    mate = c.target
    near = sorted(c.enemies(), key=lambda f: distance_between(c.world, mate, f))
    if near:
        c.basic(who=mate, on=near[0])


# ==========================================================================
# m3748
# ==========================================================================


@power(
    "m3748a0", level=9, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16), damage=Damage("1d10", 5),
)
def m3748a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EOTNT)


@power(
    "m3748a1", level=9, usage=AT_WILL, action=STANDARD, reach=Ranged(20),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16), damage=Damage("1d10", 4),
)
def m3748a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3748a2", level=9, usage=Usage.RECHARGE, recharge=6, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=14),
    damage=Damage("2d10", 6, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m3748a2(c: Cast) -> None:
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    mods = [
        (victim, Mod(what=d.value, value=-2, kind="untyped", label=c.ref)) for d in ALL_DEFENCES
    ]
    c.world.effects.apply(
        victim, c.me, When.SAVE_ENDS, label=f"{c.ref} penalty", mods=mods,
    )


@power(
    "m3748a3", level=9, usage=ENCOUNTER, action=STANDARD, reach=CloseBurst(20), target=EACH_ALLY,
    keywords=[Keyword.WEAPON, Keyword.HEALING],
)
def m3748a3(c: Cast) -> None:
    """"Within line of sight" has no verb beside distance, so a wide burst
    stands in for it -- the judgement every row of this shape in this tree
    has already made."""
    mate = c.target
    near = sorted(c.enemies(), key=lambda f: distance_between(c.world, mate, f))
    if near:
        c.basic(who=mate, on=near[0])
    c.heal(10, on=mate)


# ==========================================================================
# m3988
# ==========================================================================


@power(
    "m3988a0", level=9, usage=AT_WILL, action=STANDARD, reach=Melee(3),
    target=ONE_CREATURE, attack=Attack(vs=AC, printed=15), damage=Damage("1d8", 6),
)
def m3988a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.pull(2)
        c.grab()


@power(
    "m3988a1", level=9, usage=AT_WILL, action=STANDARD, reach=Melee(2),
    target=ONE_CREATURE, keywords=[Keyword.DISEASE],
    attack=Attack(vs=REF, printed=13), damage=Damage("1d6", 4),
    dropped=("Condition.DISEASED",),
)
def m3988a1(c: Cast) -> None:
    """There is no disease track in this engine at all -- the whole
    exposure clause has nowhere to go."""
    if c.strike():
        c.hit()
        c.ongoing(5)


@power("m3988a2", level=9, usage=AT_WILL, action=STANDARD, reach=PERSONAL, target=NO_TARGET)
def m3988a2(c: Cast) -> None:
    """`c.basic` with no `on=` falls back to `c.target`, which this row has
    none of -- an enemy has to be named by hand."""
    near = sorted(c.enemies(), key=c.distance)
    foe = near[0] if near else None
    if foe is not None:
        for _ in range(2):
            c.basic(on=foe)


@power(
    "m3988a3", level=9, usage=AT_WILL, action=STANDARD, reach=Melee(2),
    target=Target(
        side="enemy", count=1, label="creature grabbed by it",
        relation=Relation.GRABBED_BY,
    ),
    attack=Attack(vs=AC, printed=15), damage=Damage("2d10", 6),
    dropped=("Condition.DISEASED",),
)
def m3988a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(10)


@power("m3988a4", level=9, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m3988a4(c: Cast) -> None:
    me = c.me

    def choose(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me:
            return
        pick = c.choose(
            ["heal", "defenses", "attack", "resist"], "m3988a4: which benefit"
        ) or "heal"
        if pick == "heal":
            c.heal(10, on=me)
        elif pick == "defenses":
            for d in ALL_DEFENCES:
                c.bonus(d, 2, on=me, until=When.EONT)
        elif pick == "attack":
            c.bonus("attack", 2, on=me, until=When.EONT)
            c.bonus("damage", 2, on=me, until=When.EONT)
        else:
            element = c.choose(list(_FIVE_ELEMENTS), "m3988a4: which element") or DamageType.ACID
            c.resist(20, element, on=me, until=When.EONT)

    c.watch(TurnStart, choose, until=When.ENCOUNTER, on=me, label=c.ref)


# ==========================================================================
# m3998
# ==========================================================================


@power(
    "m3998a0", level=9, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16), damage=Damage("1d12", 6),
)
def m3998a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark()


@power(
    "m3998a1", level=9, usage=AT_WILL, action=STANDARD, reach=Ranged(20),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15), damage=Damage("1d10", 3),
)
def m3998a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3998a2", level=9, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=Target(
        side="enemy", count=1, label="creature marked by it",
        relation=Relation.MARKED_BY,
    ),
    keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16), damage=Damage("1d12", 6),
)
def m3998a2(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.hit()
    if _secondary(c, 14, FORT, victim):
        c.condition(Condition.WEAKENED, Condition.SLOWED, until=When.SAVE_ENDS, on=victim)


@power("m3998a3", level=9, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m3998a3(c: Cast) -> None:
    me = c.me

    def shrouded(ctx: dict) -> bool:
        attacker = ctx.get("attacker")
        return attacker is not None and distance_between(c.world, me, attacker) > 3

    c.conceal(on=me, until=When.ENCOUNTER, when=shrouded)


# ==========================================================================
# m4004
# ==========================================================================


@power(
    "m4004a0", level=9, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.NECROTIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15), damage=Damage("1d8", 2),
)
def m4004a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.flat(5, dtype=DamageType.NECROTIC)


@power(
    "m4004a1", level=9, usage=ENCOUNTER, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.NECROTIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15), damage=Damage("2d8", 7, dtype=DamageType.NECROTIC),
)
def m4004a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m4004a2", level=9, usage=Usage.RECHARGE, recharge=5, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.NECROTIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d8", 5, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m4004a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.NECROTIC)


@power(
    "m4004a3", level=9, usage=AT_WILL, action=MINOR, reach=Melee(1), target=ONE_CREATURE,
    dropped=("etl.monster.vulnerable_amount()",),
)
def m4004a3(c: Cast) -> None:
    """The vulnerability is printed with no number at all -- a data gap,
    the same shape `etl.monster.forced_distance()` already names for a
    missing distance. The second clause, which carries its own number,
    plays."""
    victim = c.target
    if victim is None:
        return
    me = c.me

    def ouch(ev: DamageApplied) -> None:
        if ev.target != victim or DamageType.NECROTIC not in ev.types():
            return
        c.immobilized(until=When.SAVE_ENDS, on=victim)

    c.watch(DamageApplied, ouch, until=When.EONT, on=me, label=f"{c.ref} {victim}")


# ==========================================================================
# m4005
# ==========================================================================


@power(
    "m4005a0", level=9, usage=AT_WILL, action=MINOR, reach=Melee(1), target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16), damage=Damage("2d6", 7),
    dropped=("c.cannot_attack(opportunity=)",),
)
def m4005a0(c: Cast) -> None:
    """"Cannot make opportunity attacks against it" is narrower than
    `c.cannot_attack`, which bars everything -- there is no opportunity-only
    form. The grab and the targeting narrowing both play."""

    def not_already_held(who: int) -> bool:
        return who not in c.world.relations.targets(Relation.GRABBED_BY, c.me)

    victim = _restricted_to(c, 1, not_already_held)
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)
    c.grab(on=victim)


@power(
    "m4005a1", level=9, usage=AT_WILL, action=MINOR, reach=Melee(1),
    target=Target(
        side="enemy", count=1, label="creature grabbed by it",
        relation=Relation.GRABBED_BY,
    ),
    attack=Attack(vs=FORT, printed=10),
    # Flat zero, and flat is an empty dice string. This one *did* call
    # `c.hit()` and raised in play.
    damage=Damage("", 0),
    dropped=("c.cannot_attack(opportunity=)", "c.sight_range(only=)"),
)
def m4005a1(c: Cast) -> None:
    """Pulled into its own square, restrained, and burning until the hold
    ends -- tracked by hand rather than given a save-ends duration this
    engine does not have. "No line of sight but to the swarm" and "cannot
    make opportunity attacks" both have no verb; see the report. The cap
    of one creature at a time is left ungated for the same reason the a0
    cap is approximated rather than modelled square by square."""
    victim = c.target
    if not c.strike():
        return
    c.hit()
    me = c.me
    ongoing = c.world.effects.apply(
        victim, me, When.ENCOUNTER, label=f"{c.ref} swallowed",
        conditions=[Condition.RESTRAINED], ongoing=(10, DamageType.UNTYPED),
    )

    def freed(ev: RelationCleared) -> None:
        if ev.kind_ is Relation.GRABBED_BY and ev.source == me and ev.target == victim:
            c.world.effects.end(ongoing, "the grab ends")

    c.watch(RelationCleared, freed, until=When.ENCOUNTER, on=me, label=f"{c.ref} {victim}")


@power("m4005a2", level=9, usage=AT_WILL, action=FREE, reach=CloseBurst(2), target=EACH_ENEMY,
       keywords=[Keyword.POISON], attack=Attack(vs=FORT, printed=10),
       damage=Damage("3d8", 5, dtype=DamageType.POISON),
       trigger="it drops to 0 hit points",
       on=Trigger(Dropped, about_me, "it drops to 0 hit points"))
def m4005a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power("m4005a3", level=9, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m4005a3(c: Cast) -> None:
    me = c.me

    def extra(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me or not c.bloodied(me):
            return
        c.extra_action(cost=MINOR, on=me)

    c.watch(TurnStart, extra, until=When.ENCOUNTER, on=me, label=c.ref)


@power("m4005a4", level=9, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m4005a4(c: Cast) -> None:
    """Both halves are already true without a line of code: a grab here
    costs nothing to keep (m1982a3 settles the same question), and nothing
    in this engine ends a grab merely because the grabber moved while
    staying adjacent."""


# ==========================================================================
# m4122
# ==========================================================================


@power(
    "m4122a0", level=9, usage=AT_WILL, action=STANDARD, reach=Melee(2),
    target=ONE_CREATURE, keywords=[Keyword.ACID],
    attack=Attack(vs=AC, printed=16), damage=Damage("1d10", 6),
)
def m4122a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.damage("1d6", 0, dtype=DamageType.ACID)


@power(
    "m4122a1", level=9, usage=AT_WILL, action=STANDARD, reach=Melee(2),
    target=ONE_CREATURE, attack=Attack(vs=AC, printed=16), damage=Damage("1d8", 6),
)
def m4122a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark()


@power(
    "m4122a2", level=9, usage=AT_WILL, action=STANDARD, reach=Ranged(10),
    target=ONE_CREATURE, attack=Attack(vs=AC, printed=14), damage=Damage("2d6", 5),
)
def m4122a2(c: Cast) -> None:
    """"Usable only while a wall is within reach" is its own kit's
    surroundings, not the creature's, and `c.scenery` has no "wall" word in
    this tree's maps -- left ungated rather than refused everywhere."""
    if c.strike():
        c.hit()


@power(
    "m4122a3", level=9, usage=AT_WILL, action=STANDARD, reach=Melee(2), target=UpTo(2),
)
def m4122a3(c: Cast) -> None:
    """Two claws and a bite, or a bite and a thrown stone -- the choice the
    card offers, driven by `c.may` rather than decided."""
    if not c.first:
        return
    rows = (
        ("m4122a0", "m4122a0", "m4122a1")
        if c.may("make two claw attacks and a bite")
        else ("m4122a1", "m4122a2")
    )
    for ref, victim in zip(rows, c.targets[: len(rows)], strict=False):
        c.use_power(ref, on=victim, spend=False)


@power(
    "m4122a4", level=9, usage=Usage.RECHARGE, recharge=0, action=STANDARD, reach=CloseBlast(5),
    target=EACH_ENEMY, keywords=[Keyword.ACID],
    attack=Attack(vs=FORT, printed=14),
    damage=Damage("2d8", 4, dtype=DamageType.ACID, kind=LIMITED),
)
def m4122a4(c: Cast) -> None:
    """Recharges when one of its own summoned spirits drops, not on a die --
    the level-8 sweep settled this exact shape for a different creature's
    companion."""
    me = c.me
    if c.first and not _armed(c, f"{c.ref} recharge"):
        def spirit_fell(ev: Dropped) -> None:
            if _ref_of(c, ev.actor) == "m4123":
                c.restore_use(c.ref, on=me)

        c.watch(Dropped, spirit_fell, until=When.ENCOUNTER, on=me, label=f"{c.ref} recharge")
    if c.strike():
        c.hit()
        spot = next(iter(sorted(c.area())), None)
        if spot is not None:
            c.summon("m4123", at=spot)


@power(
    "m4122a5", level=9, usage=ENCOUNTER, action=FREE, reach=PERSONAL, target=NO_TARGET,
    trigger="it is first bloodied",
    on=Trigger(Bloodied, about_me, "it is first bloodied"),
)
def m4122a5(c: Cast) -> None:
    c.restore_use("m4122a4")
    c.use_power("m4122a4", spend=False)


@power(
    "m4122a6", level=9, usage=ENCOUNTER, action=STANDARD, reach=CloseBurst(5), target=EACH_ENEMY,
    keywords=[Keyword.FEAR], attack=Attack(vs=WILL, printed=14),
)
def m4122a6(c: Cast) -> None:
    if c.strike():
        held = c.stunned(until=When.EONT)
        victim = c.target
        if held is not None and victim is not None:
            held.on_end.append(lambda v=victim: c.penalty("attack", 2, on=v, until=When.SAVE_ENDS))


# ==========================================================================
# m4475
# ==========================================================================


@power(
    "m4475a0", level=9, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16), damage=Damage("1d10", 6),
)
def m4475a0(c: Cast) -> None:
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()

    def worsen(eff: Effect) -> None:
        c.world.effects.end(eff, "the poison spreads")
        c.condition(
            Condition.SLOWED, until=When.SAVE_ENDS, on=victim, ongoing=(5, DamageType.POISON)
        )

    c.condition(
        Condition.MARKED, Condition.SLOWED, until=When.SAVE_ENDS, on=victim, escalate=worsen
    )


@power(
    "m4475a1", level=9, usage=AT_WILL, action=STANDARD, reach=MeleeOrRanged(1, 5),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16), damage=Damage("2d6", 3),
)
def m4475a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power("m4475a2", level=9, usage=AT_WILL, action=STANDARD, reach=Melee(1), target=UpTo(2))
def m4475a2(c: Cast) -> None:
    if not c.first:
        return
    landed = []
    for ref, victim in zip(("m4475a0", "m4475a1"), c.targets[:2], strict=False):
        c.use_power(ref, on=victim, spend=False)
        if c.landed:
            landed.append(victim)
    for victim in landed:
        c.slide(1, on=victim)


@power(
    "m4475a3", level=9, usage=AT_WILL, action=OPPORTUNITY, reach=Melee(1), target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16), damage=Damage("1d10", 6),
    trigger="an enemy marked by it leaves a square adjacent to it or attacks without it",
    on=[
        Trigger(MoveStart, _marked_within_moves_away(1), "a marked enemy leaves adjacent"),
        Trigger(PowerUsed, _marked_by_me_looks_away, "a marked enemy attacks without it"),
    ],
)
def m4475a3(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    if foe is not None and c.strike(on=foe):
        c.hit(on=foe)


@power("m4475a4", level=9, usage=AT_WILL, action=MOVE, reach=PERSONAL, target=SELF)
def m4475a4(c: Cast) -> None:
    near = sorted(c.enemies(), key=c.distance)
    foe = near[0] if near else None
    if foe is not None:
        _shift_beside(c, foe, 2)


@power("m4475a5", level=9, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m4475a5(c: Cast) -> None:
    c.resist_forced(1)
    me = c.me

    def shrug(ev: ConditionApplied) -> None:
        if not _floored(c.world, me, ev):
            return
        for held in list(c.world.effects.of(me)):
            if Condition.PRONE in held.conditions:
                c.world.effects.save(held)
                return

    c.watch(ConditionApplied, shrug, until=When.ENCOUNTER, on=me, label=c.ref)


# ==========================================================================
# m5327
# ==========================================================================


@power("m5327a0", level=9, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5327a0(c: Cast) -> None:
    c.threatens(2)


@power(
    "m5327a1", level=9, usage=AT_WILL, action=STANDARD, reach=Melee(2),
    target=ONE_CREATURE, attack=Attack(vs=AC, printed=14), damage=Damage("2d10", 6),
)
def m5327a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark()


@power(
    "m5327a2", level=9, usage=AT_WILL, action=STANDARD, reach=Ranged(5),
    target=ONE_CREATURE, keywords=[Keyword.ACID],
    attack=Attack(vs=REF, printed=12), damage=Damage("1d8", 3, dtype=DamageType.ACID),
)
def m5327a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.SLOWED, until=When.SAVE_ENDS, ongoing=(5, DamageType.ACID))


@power(
    "m5327a3", level=9, usage=Usage.RECHARGE, recharge=5, action=STANDARD, reach=Melee(2),
    target=UpTo(2), attack=Attack(vs=AC, printed=14), damage=Damage("2d10", 6, kind=LIMITED),
)
def m5327a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m5327a4", level=9, usage=Usage.RECHARGE, recharge=0, action=INTERRUPT, reach=PERSONAL,
    target=NO_TARGET,
    trigger="an enemy marked by it and within 3 squares moves away from it",
    on=Trigger(MoveStart, _marked_within_moves_away(3), "a marked enemy moves away within 3"),
    dropped=("Usage.RECHARGE(when=)",),
)
def m5327a4(c: Cast) -> None:
    """Recharges when first bloodied, the exact phrase `_recharge_when_bloodied`
    already settles. Armed once from inside the reaction itself -- its own
    `once=True` on the `Bloodied` watch is what keeps a second use from
    arming a second copy."""
    _recharge_when_bloodied(c)
    foe = getattr(c.trigger, "actor", None)
    if foe is not None:
        c.slide(3, on=foe, to=_free_square_beside(c, c.me))


# ==========================================================================
# m5375
# ==========================================================================


@power(
    "m5375a0", level=9, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET,
    keywords=[Keyword.COLD, Keyword.FEAR],
)
def m5375a0(c: Cast) -> None:
    me = c.me
    _aura(c, 1, lambda who: who != me and who in c.enemies(),
          lambda who: c.cannot_shift(on=who, until=When.ENCOUNTER))

    def scorched(ev: PowerUsed) -> None:
        if _marked_within_looks_away(1)(c.world, me, ev):
            c.flat(5, dtype=DamageType.COLD, on=ev.actor)

    c.watch(PowerUsed, scorched, until=When.ENCOUNTER, on=me, label=f"{c.ref} burn")


@power(
    "m5375a1", level=9, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.COLD],
    attack=Attack(vs=AC, printed=14), damage=Damage("3d6", 7, dtype=DamageType.COLD),
)
def m5375a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5375a2", level=9, usage=AT_WILL, action=MINOR, once_per_round=True, reach=CloseBurst(3),
    target=Target(side="enemy", count=1, label="one enemy in the burst"),
    keywords=[Keyword.CHARM], attack=Attack(vs=WILL, printed=12),
)
def m5375a2(c: Cast) -> None:
    if c.strike():
        c.pull(2)
        c.mark()


# ==========================================================================
# m5604
# ==========================================================================


@power("m5604a0", level=9, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5604a0(c: Cast) -> None:
    me = c.me

    def banner(who: int) -> Effect | None:
        return c.world.effects.apply(
            who, me, When.ENCOUNTER, label=f"{c.ref} banner",
            mods=[
                (who, Mod(what="attack", value=1, kind="untyped", label=c.ref)),
                (who, Mod(what="save", value=2, kind="untyped", label=c.ref)),
            ],
        )

    _aura(c, 5, lambda who: who != me and who in c.allies(), banner)


@power(
    "m5604a1", level=9, usage=AT_WILL, action=STANDARD, reach=Melee(2),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14), damage=Damage("1d10", 5),
)
def m5604a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized(until=When.SONT)


@power(
    "m5604a2", level=9, usage=AT_WILL, action=STANDARD, reach=Melee(3),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14), damage=Damage("1d10", 5),
)
def m5604a2(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.hit()
        c.pull(2)
        if victim is not None and getattr(c.result, "advantage", False):
            c.prone(on=victim)


@power(
    "m5604a3", level=9, usage=ENCOUNTER, action=STANDARD, reach=CloseBlast(3), target=EACH_ENEMY,
    keywords=[Keyword.FEAR, Keyword.IMPLEMENT],
    attack=Attack(vs=REF, printed=12), damage=Damage("1d10", 5),
    dropped=("c.no_walk(from_=)",),
)
def m5604a3(c: Cast) -> None:
    """"Cannot move away from m5604" is directional in a way `c.no_walk`
    is not -- that bars every walk, not only ones that increase distance
    from one named creature. The penalty half plays."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    mod = Mod(what="attack", value=-2, kind="untyped", label=c.ref)
    c.world.effects.apply(
        victim, c.me, When.SAVE_ENDS, label=f"{c.ref} dread", mods=[(victim, mod)]
    )


def _an_immobilized_enemy_m5604(world: World, eid: int) -> bool:
    from combat_engine.engine.query import enemies, is_

    return any(
        is_(world, foe, Condition.IMMOBILIZED) and distance_between(world, eid, foe) <= 5
        for foe in enemies(world, eid)
    )


@power(
    "m5604a4", level=9, usage=AT_WILL, action=MINOR, once_per_round=True, reach=Ranged(5),
    target=NO_TARGET, keywords=[Keyword.FEAR, Keyword.IMPLEMENT],
    attack=Attack(vs=WILL, printed=14),
    requires=_an_immobilized_enemy_m5604,
    requires_text="an immobilized creature must be within 5 squares",
)
def m5604a4(c: Cast) -> None:
    held = [
        foe for foe in c.enemies() if c.is_(Condition.IMMOBILIZED, on=foe) and c.distance(foe) <= 5
    ]
    victim = c.choose(held, "m5604a4: which immobilized creature") if held else None
    if victim is None or not c.strike(on=victim):
        return
    # The printed Hit line is the condition and no damage at all, so there is
    # nothing to declare and `c.hit()` -- which raises without a damage line --
    # was never the right call. `m1815a4` is the same shape: strike, then the
    # consequence.
    me = c.me
    insane = c.effect(f"{c.ref} insane", until=When.SAVE_ENDS, on=victim)

    def roll(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != victim or insane not in c.world.effects.of(victim):
            return
        if c.roll("1d6") % 2 == 1:
            c.condition(Condition.DOMINATED, until=When.SOTNT, on=victim)

    c.watch(TurnStart, roll, until=When.SAVE_ENDS, on=me, label=f"{c.ref} {victim}")


# ==========================================================================
# m5613
# ==========================================================================


@power("m5613a0", level=9, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5613a0(c: Cast) -> None:
    me = c.me

    def retaliate(ev: PowerUsed) -> None:
        if _looked_away_in_aura(2)(c.world, me, ev):
            c.flat(10, on=ev.actor)

    c.watch(PowerUsed, retaliate, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m5613a1", level=9, usage=AT_WILL, action=STANDARD, reach=Melee(2),
    target=ONE_CREATURE, attack=Attack(vs=AC, printed=14), damage=Damage("3d6", 6),
)
def m5613a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(2)


@power(
    "m5613a2", level=9, usage=Usage.RECHARGE, recharge=4, action=STANDARD, reach=CloseBlast(3),
    target=EACH_ENEMY, keywords=[Keyword.DISEASE, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14), damage=Damage("2d12", 6, kind=LIMITED),
    dropped=("Condition.DISEASED",),
)
def m5613a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5613a3", level=9, usage=ENCOUNTER, uses=2, action=FREE, reach=PERSONAL, target=NO_TARGET,
    trigger="it takes acid, cold, fire, lightning, or thunder damage",
    on=Trigger(DamageApplied, targets_me, "it takes one of those five damage types"),
)
def m5613a3(c: Cast) -> None:
    """"Until the end of the encounter or until it uses this again" is
    nearly moot at `uses=2`: the only way to reuse it is a second
    triggering damage type, and the two resists simply stand side by
    side -- never more generous than the printed line, since a hold is
    never taken off early."""
    dealt = next((t for t in _FIVE_ELEMENTS if t in c.trigger.types()), None)
    if dealt is not None:
        c.resist(5, dealt, on=c.me, until=When.ENCOUNTER)


# ==========================================================================
# m5620
# ==========================================================================


@power(
    "m5620a0", level=9, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14), damage=Damage("2d10", 6),
)
def m5620a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power("m5620a1", level=9, usage=AT_WILL, action=STANDARD, reach=Melee(1), target=UpTo(2))
def m5620a1(c: Cast) -> None:
    if not c.first:
        return
    for victim in c.targets[:2]:
        c.use_power("m5620a0", on=victim, spend=False)


@power(
    "m5620a2", level=9, usage=ENCOUNTER, action=STANDARD, reach=Melee(1), target=ONE_CREATURE,
)
def m5620a2(c: Cast) -> None:
    victim = c.target
    me = c.me
    if victim is not None:
        c.use_power("m5620a0", on=victim, spend=False)
    for mate in c.allies():
        if mate == me or c.distance(mate) > 5:
            continue
        c.shift(2, who=mate)
        near = sorted(c.enemies(), key=lambda f: distance_between(c.world, mate, f))
        if near:
            c.basic(who=mate, on=near[0])


@power(
    "m5620a3", level=9, usage=Usage.RECHARGE, recharge=5, action=MINOR, reach=CloseBurst(3),
    target=EACH_ALLY,
)
def m5620a3(c: Cast) -> None:
    c.bonus("damage", 5, on=c.target, until=When.EONT, kind="power")


@power(
    "m5620a4", level=9, usage=AT_WILL, action=FREE, reach=Melee(1), target=NO_TARGET,
    trigger="an adjacent enemy uses an attack power that doesn't include it",
    on=Trigger(PowerUsed, _adjacent_foe_looks_away, "an adjacent enemy attacks without it"),
)
def m5620a4(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    if foe is not None:
        c.flat(12, on=foe)


# ==========================================================================
# m5654
# ==========================================================================


@power("m5654a0", level=9, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5654a0(c: Cast) -> None:
    me = c.me

    def shaken(ev: DamageApplied) -> None:
        if ev.target == me and DamageType.THUNDER in ev.types():
            c.slowed(until=When.SAVE_ENDS, on=me)

    c.watch(DamageApplied, shaken, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m5654a1", level=9, usage=AT_WILL, action=STANDARD, reach=Melee(2),
    target=ONE_CREATURE, attack=Attack(vs=AC, printed=14), damage=Damage("2d10", 6),
    requires=lambda world, eid: len(world.relations.targets(Relation.GRABBED_BY, eid)) < 4,
    requires_text="it cannot already be grabbing its full capacity",
)
def m5654a1(c: Cast) -> None:
    """The cap by size -- one Large or four Medium-or-smaller -- is
    approximated as a flat four; nothing here tracks a held creature's own
    size against a grabber's remaining capacity."""
    victim = c.target
    plus = 2 if victim is not None and c.is_(Condition.IMMOBILIZED, on=victim) else 0
    if c.strike(plus=plus):
        c.hit()
        c.grab(dc=20)


@power("m5654a2", level=9, usage=AT_WILL, action=STANDARD, reach=Melee(2), target=UpTo(2))
def m5654a2(c: Cast) -> None:
    if not c.first:
        return
    for victim in c.targets[:2]:
        c.use_power("m5654a1", on=victim, spend=False)


@power(
    "m5654a3", level=9, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=Target(
        side="enemy", count=1, label="Large or smaller creature grabbed by it",
        relation=Relation.GRABBED_BY, max_size=Size.LARGE,
    ),
    attack=Attack(vs=REF, printed=12), damage=Damage("4d10", 12),
)
def m5654a3(c: Cast) -> None:
    """The printed size cap goes in the header beside the relation: both are
    halves of one target line, and the cap was the half the old label did
    not say."""
    victim = c.target
    if not c.strike():
        return
    c.hit()
    me = c.me
    held_eff = c.world.effects.apply(
        victim, me, When.SAVE_ENDS, label=f"{c.ref} swallow", conditions=[Condition.RESTRAINED],
        ongoing=(10, DamageType.UNTYPED),
    )

    def freed() -> None:
        spot = _free_square_beside(c, me)
        if spot is not None:
            c.teleport(1, who=victim, to=spot)

    held_eff.on_end.append(freed)


@power(
    "m5654a4", level=9, usage=ENCOUNTER, action=STANDARD, reach=Melee(0),
    target=NO_TARGET, attack=Attack(vs=REF, printed=12), damage=Damage("3d12", 6),
)
def m5654a4(c: Cast) -> None:
    for foe in c.overrun():
        if c.strike(on=foe):
            c.hit(on=foe)
            c.prone(on=foe)


@power(
    "m5654a5", level=9, usage=Usage.RECHARGE, recharge=5, action=MINOR, reach=CloseBlast(3),
    target=EACH_OTHER, attack=Attack(vs=FORT, printed=12),
)
def m5654a5(c: Cast) -> None:
    if c.strike():
        c.immobilized(until=When.SAVE_ENDS)


# ==========================================================================
# m5785
# ==========================================================================

#: The one label this creature's beast form wears, so the toggle and the
#: gates on the other rows agree about which shape is standing.
_M5785_BEAST = "m5785 beast form"


def _m5785_beast_form(world: World, eid: int) -> bool:
    return any(e.label == _M5785_BEAST for e in world.effects.of(eid))


def _m5785_humanoid_form(world: World, eid: int) -> bool:
    return not _m5785_beast_form(world, eid)


@power(
    "m5785a0", level=9, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET,
)
def m5785a0(c: Cast) -> None:
    """Rough ground costs it nothing while it shifts, and nothing else.

    `when="shift"` is the narrowing every one of these cards prints and this
    verb could not say. It is spent in the *search*: a square of difficult
    terrain costs two, a shift is one, so without the exemption the square is
    never offered as a shift destination at all.
    """
    c.ignores_difficult(on=c.me, until=When.ENCOUNTER, when="shift")


@power(
    "m5785a1", level=9, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, attack=Attack(vs=AC, printed=14), damage=Damage("2d8", 8),
    requires=_m5785_beast_form, requires_text="it must be in beast form",
)
def m5785a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.EONT)


@power(
    "m5785a2", level=9, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14), damage=Damage("2d8", 8),
    requires=_m5785_humanoid_form, requires_text="it must be in humanoid form",
)
def m5785a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5785a3", level=9, usage=Usage.RECHARGE, recharge=0, action=STANDARD, reach=CloseBurst(1),
    target=EACH_ENEMY, attack=Attack(vs=REF, printed=12),
    damage=Damage("2d8", 8, kind=LIMITED, half_on_miss=True),
    requires=_m5785_beast_form, requires_text="it must be in beast form",
    dropped=("Usage.RECHARGE(when=)",),
)
def m5785a3(c: Cast) -> None:
    """Recharges when first bloodied, `_recharge_when_bloodied`'s shape."""
    _recharge_when_bloodied(c)
    if c.strike():
        c.hit()
        c.prone()
    else:
        c.hit(half=True)
        c.prone()


@power(
    "m5785a4", level=9, usage=ENCOUNTER, action=MOVE, reach=PERSONAL, target=SELF,
    requires=_m5785_beast_form, requires_text="it must be in beast form",
)
def m5785a4(c: Cast) -> None:
    near = sorted(c.enemies(), key=c.distance)
    foe = near[0] if near else None
    if foe is not None:
        _shift_beside(c, foe, c.speed_of())
    # "a +2 power bonus to attack rolls", in those words.
    c.bonus("attack", 2, on=c.me, kind="power", until=When.EOT)


@power(
    "m5785a5", level=9, usage=AT_WILL, action=MINOR, reach=PERSONAL, target=NO_TARGET,
    keywords=[Keyword.POLYMORPH],
)
def m5785a5(c: Cast) -> None:
    me = c.me
    if _m5785_beast_form(c.world, me):
        for eff in list(c.world.effects.of(me)):
            if eff.label == _M5785_BEAST:
                c.world.effects.end(eff, "shifts back")
        return
    c.form(until=When.ENCOUNTER, revert=MINOR, label=_M5785_BEAST)


# ==========================================================================
# m5877
# ==========================================================================


@power(
    "m5877a0", level=9, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET,
    keywords=[Keyword.COLD, Keyword.NECROTIC],
)
def m5877a0(c: Cast) -> None:
    """"Enemies can't spend healing surges in the aura."

    The same card as `m5870a0` two levels up, and written the same way: one
    watcher for the whole region rather than a refusal laid on each
    creature, because the printed line is about whoever is standing in it
    when they try -- including somebody who walked in after this armed.

    **It was marked under a different spelling**, `c.no_healing(surges_only=)`,
    where its twin said `c.no_surges()`. One need under two symbols, so
    clearing one of them left this row invisible to `blocked.py`'s group --
    the failure the root file's "a marker names one gap" rule is about,
    seen from the other side. #386.
    """
    me = c.me
    ring = c.aura(1, until=When.ENCOUNTER)

    def barred(ev: SurgeSpent) -> None:
        if ev.actor in c.enemies() and ev.actor in c.world.zones.occupants(ring):
            ev.cancel("inside the aura")

    c.watch(
        SurgeSpent, barred, until=When.ENCOUNTER, on=me,
        window=Window.BEFORE, label=f"{c.ref} no surges",
    )

    def bite(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor == me or ev.actor not in c.enemies():
            return
        if ev.actor not in c.world.zones.occupants(ring):
            return
        c.flat(5, dtypes=(DamageType.COLD, DamageType.NECROTIC), on=ev.actor)
        c.temp_hp(5, on=me)

    c.watch(TurnEnd, bite, until=When.ENCOUNTER, on=me, label=c.ref)


@power("m5877a1", level=9, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5877a1(c: Cast) -> None:
    me = c.me
    active = [True]

    def halved(ev: DamageRolled) -> None:
        exempt = {DamageType.FIRE, DamageType.FORCE, DamageType.RADIANT}
        if ev.target != me or not active[0] or exempt & ev.types():
            return
        ev.amount -= ev.amount // 2

    def shaken(ev: DamageApplied) -> None:
        if ev.target == me and {DamageType.FIRE, DamageType.RADIANT} & ev.types():
            active[0] = False

    def recovers(ev: TurnStart) -> None:
        if not ev.ghost and ev.actor == me:
            active[0] = True

    c.watch(
        DamageRolled, halved, until=When.ENCOUNTER, on=me, window=Window.BEFORE,
        label=f"{c.ref} half",
    )
    c.watch(DamageApplied, shaken, until=When.ENCOUNTER, on=me, label=f"{c.ref} shaken")
    c.watch(TurnStart, recovers, until=When.ENCOUNTER, on=me, label=f"{c.ref} recovers")


@power("m5877a2", level=9, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5877a2(c: Cast) -> None:
    """"Openings of any size" has no verb beside `c.phasing`, which is the
    closest real approximation of moving through what would otherwise
    block it -- entering another creature's space."""
    c.phasing(on=c.me, until=When.ENCOUNTER)


@power(
    "m5877a3", level=9, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.COLD, Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("3d6", 7, dtype=[DamageType.COLD, DamageType.NECROTIC]),
)
def m5877a3(c: Cast) -> None:
    """One roll of two types, which is all one `Damage` header can say --
    cold stays there as the data a rescale reads, and the body deals the
    real two-typed version instead of calling `c.hit`."""
    if c.strike():
        c.damage("3d6", 7, dtypes=(DamageType.COLD, DamageType.NECROTIC))
        c.slowed(until=When.EONT)


@power(
    "m5877a4", level=9, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.COLD, Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("3d6", 7, dtype=[DamageType.COLD, DamageType.NECROTIC]),
)
def m5877a4(c: Cast) -> None:
    if c.strike():
        c.damage("3d6", 7, dtypes=(DamageType.COLD, DamageType.NECROTIC))
        c.immobilized(until=When.EONT)


# ==========================================================================
# m5894
# ==========================================================================


@power(
    "m5894a0", level=9, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, attack=Attack(vs=AC, printed=14), damage=Damage("2d6", 9),
)
def m5894a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5894a1", level=9, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, attack=Attack(vs=AC, printed=14), damage=Damage("2d6", 4),
)
def m5894a1(c: Cast) -> None:
    """"Without darkvision" is a fact nothing in this engine tracks, so the
    darkness blinds **every** creature standing in it rather than singling
    out the ones that would be spared -- the stronger reading, and the
    only one with a fact to check."""
    victim = c.target
    if c.strike():
        c.hit()
        c.mark()
    if victim is None:
        return
    sq = _square_of(c, victim)
    if sq is None:
        return
    zone = c.zone({sq}, until=When.EONT, blocks_sight=True, label=f"{c.ref} dark")

    def shrouded(ev: ZoneEntered) -> None:
        if ev.zone == zone:
            c.blinded(until=When.EONT, on=ev.actor)

    c.watch(ZoneEntered, shrouded, until=When.EONT, label=f"{c.ref} shroud")
    c.blinded(until=When.EONT, on=victim)


def _marked_moved_away(world: World, me: int, ev: MoveEnd) -> bool:
    actor = getattr(ev, "actor", None)
    if actor is None or actor == me:
        return False
    if not world.relations.holds(Relation.MARKED_BY, me, actor):
        return False
    return distance_between(world, me, actor) > 1


@power(
    "m5894a2", level=9, usage=AT_WILL, action=REACTION, reach=PERSONAL, target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
    trigger="an enemy adjacent to and marked by it moves to a square not adjacent",
    on=Trigger(MoveEnd, _marked_moved_away, "a marked adjacent enemy moves away"),
)
def m5894a2(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    if foe is None:
        return
    spot = _free_square_beside(c, foe)
    if spot is not None:
        c.teleport(10, to=spot)
    c.use_power("m5894a0", on=foe, spend=False)


@power(
    "m5894a3", level=9, usage=ENCOUNTER, action=FREE, reach=CloseBurst(1), target=EACH_OTHER,
    keywords=[Keyword.RADIANT],
    attack=Attack(vs=REF, printed=12), damage=Damage("2d6", 6, dtype=DamageType.RADIANT),
    trigger="it drops to 0 hit points",
    on=Trigger(Dropped, about_me, "it drops to 0 hit points"),
)
def m5894a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.blinded(until=When.EOTNT)


# ==========================================================================
# m5904
# ==========================================================================


@power("m5904a0", level=9, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5904a0(c: Cast) -> None:
    me = c.me
    ring = c.aura(1, until=When.ENCOUNTER)

    def mire(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == me or ev.actor not in c.enemies():
            return
        if ev.actor in c.world.zones.occupants(ring):
            c.slowed(until=When.SOTNT, on=ev.actor)

    c.watch(TurnStart, mire, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m5904a1", level=9, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14), damage=Damage("2d8", 3),
)
def m5904a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.flat(5, dtype=DamageType.POISON)
    c.mark()


@power(
    "m5904a2", level=9, usage=AT_WILL, action=STANDARD, reach=Ranged(15),
    target=ONE_CREATURE, keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14), damage=Damage("1d10", 7),
)
def m5904a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)


# ==========================================================================
# m5926
# ==========================================================================


@power("m5926a0", level=9, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5926a0(c: Cast) -> None:
    c.ignores_difficult()


@power(
    "m5926a1", level=9, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, attack=Attack(vs=AC, printed=14), damage=Damage("1d10", 8),
)
def m5926a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m5926a2", level=9, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, attack=Attack(vs=AC, printed=14), damage=Damage("1d10", 6),
    requires=_prone_enemy_in_reach, requires_text="an adjacent enemy must be prone",
)
def m5926a2(c: Cast) -> None:
    victim = c.target
    if victim is None or not c.is_(Condition.PRONE, victim):
        return
    if c.strike():
        c.hit()
        c.ongoing(10)


@power(
    "m5926a3", level=9, usage=AT_WILL, action=REACTION, reach=Melee(1), target=NO_TARGET,
    trigger="an adjacent enemy makes an attack power that doesn't include it",
    on=Trigger(PowerUsed, _adjacent_foe_looks_away, "an adjacent enemy attacks without it"),
)
def m5926a3(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    if foe is not None:
        c.use_power("m5926a1", on=foe, spend=False)


# ==========================================================================
# m5962
# ==========================================================================


@power(
    "m5962a0", level=9, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.FIRE, Keyword.PSYCHIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("3d6", 6, dtype=[DamageType.FIRE, DamageType.PSYCHIC]),
)
def m5962a0(c: Cast) -> None:
    if c.strike():
        c.damage("3d6", 6, dtypes=(DamageType.FIRE, DamageType.PSYCHIC))
    c.mark()


@power(
    "m5962a1", level=9, usage=ENCOUNTER, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.FIRE, Keyword.PSYCHIC, Keyword.ZONE],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("3d10", 5, dtype=[DamageType.FIRE, DamageType.PSYCHIC], half_on_miss=True),
)
def m5962a1(c: Cast) -> None:
    """"Difficult terrain for good creatures" has no alignment this engine
    tracks -- read as difficult for everyone, which is wider than printed
    but the only reading with a fact behind it."""
    victim = c.target
    if c.strike():
        c.damage("3d10", 5, dtypes=(DamageType.FIRE, DamageType.PSYCHIC))
    else:
        c.half_damage("3d10", 5, dtypes=(DamageType.FIRE, DamageType.PSYCHIC))
    if victim is None:
        return
    here = _square_of(c, victim)
    if here is None:
        return
    zone = c.zone(spread({here}, 1), until=When.ENCOUNTER, difficult=True, label=f"{c.ref} char")

    def scorch(ev: TurnEnd) -> None:
        if ev.actor in c.world.zones.occupants(zone):
            c.flat(5, dtype=DamageType.FIRE, on=ev.actor)

    def scorch_in(ev: ZoneEntered) -> None:
        if ev.zone == zone:
            c.flat(5, dtype=DamageType.FIRE, on=ev.actor)

    c.watch(TurnEnd, scorch, until=When.ENCOUNTER, label=f"{c.ref} end")
    c.watch(ZoneEntered, scorch_in, until=When.ENCOUNTER, label=f"{c.ref} enter")


@power(
    "m5962a2", level=9, usage=ENCOUNTER, action=STANDARD, reach=Ranged(3),
    target=ONE_CREATURE, keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=14), damage=Damage("1d8", 8),
)
def m5962a2(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.hit()
        if victim is not None:
            c.condition(
                Condition.MARKED, until=When.SAVE_ENDS, on=victim, ongoing=(5, DamageType.POISON)
            )


@power(
    "m5962a3", level=9, usage=AT_WILL, action=MINOR, once_per_round=True, reach=Ranged(5),
    target=Target(
        side="enemy", count=1, label="creature marked by it",
        relation=Relation.MARKED_BY,
    ),
    attack=Attack(vs=WILL, printed=12),
)
def m5962a3(c: Cast) -> None:
    if c.strike():
        c.slide(3)


# ==========================================================================
# m6093
# ==========================================================================


@power(
    "m6093a0", level=9, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET,
    keywords=[Keyword.PSYCHIC],
)
def m6093a0(c: Cast) -> None:
    me = c.me

    def shared(ev: DamageApplied) -> None:
        if ev.target != me or DamageType.PSYCHIC not in ev.types():
            return
        for foe in c.within(1, side="enemy"):
            c.flat(5, dtype=DamageType.PSYCHIC, on=foe)

    c.watch(DamageApplied, shared, until=When.ENCOUNTER, on=me, label=c.ref)


@power("m6093a1", level=9, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m6093a1(c: Cast) -> None:
    me = c.me

    def shrug(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me:
            return
        for held in list(c.world.effects.of(me)):
            if Condition.STUNNED in held.conditions or Condition.DOMINATED in held.conditions:
                c.world.effects.save(held)

    c.watch(TurnStart, shrug, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m6093a2", level=9, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14), damage=Damage("2d8", 8),
)
def m6093a2(c: Cast) -> None:
    if c.strike():
        c.hit()
    c.mark()


@power(
    "m6093a3", level=9, usage=AT_WILL, action=OPPORTUNITY, reach=Melee(1), target=NO_TARGET,
    trigger="an enemy marked by it shifts or attacks without including it",
    on=[
        Trigger(MoveStart, _marked_shifts, "a marked enemy shifts"),
        Trigger(PowerUsed, _marked_by_me_looks_away, "a marked enemy attacks without it"),
    ],
)
def m6093a3(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    if foe is not None:
        c.use_power("m6093a2", on=foe, spend=False)


@power(
    "m6093a4", level=9, usage=ENCOUNTER, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET,
)
def m6093a4(c: Cast) -> None:
    """The last blow is remembered the way `m3533a3` already does -- so
    "from an attack that does not deal psychic damage" can be asked at the
    `Dropped`, which says who struck and not what with."""
    me = c.me
    last_psychic = [False]

    def took(ev: DamageApplied) -> None:
        if ev.target == me:
            last_psychic[0] = DamageType.PSYCHIC in ev.types()

    def rise(ev: Dropped) -> None:
        if ev.actor != me or last_psychic[0]:
            return
        here = _square_of(c, me)
        if here is not None:
            c.summon("m6092", at=here)

    c.watch(DamageApplied, took, until=When.ENCOUNTER, on=me, label=f"{c.ref} last blow")
    c.watch(Dropped, rise, until=When.ENCOUNTER, on=me, label=f"{c.ref} rise")


# ==========================================================================
# m6113
# ==========================================================================


@power(
    "m6113a0", level=9, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET,
    todo=("c.grabbing(auto_share=)",),
)
def m6113a0(c: Cast) -> None:
    """A standing licence for every future move this creature makes to
    drag along whatever it is grabbing, plus a bonus to the check for
    doing so. `c.shift(share=True)` already lets one *call* bring a
    grabbed creature along; nothing makes every future call do it without
    being told, and no check is rolled here for any of this tree's grabs
    to begin with. Nothing plays."""


@power(
    "m6113a1", level=9, usage=AT_WILL, action=STANDARD, reach=Melee(3),
    target=ONE_CREATURE, attack=Attack(vs=REF, printed=12), damage=Damage("2d8", 3),
)
def m6113a1(c: Cast) -> None:
    """The ongoing damage lasts "until the grab ends," not a save -- ended
    by hand when the relation clears rather than given a duration this
    engine does not have."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    c.grab(dc=17)
    me = c.me
    held = c.world.effects.apply(
        victim, me, When.ENCOUNTER, label=f"{c.ref} grip", ongoing=(5, DamageType.UNTYPED)
    )

    def freed(ev: RelationCleared) -> None:
        if ev.kind_ is Relation.GRABBED_BY and ev.source == me and ev.target == victim:
            c.world.effects.end(held, "the grab ends")

    c.watch(RelationCleared, freed, until=When.ENCOUNTER, on=me, label=f"{c.ref} {victim}")


@power("m6113a2", level=9, usage=AT_WILL, action=STANDARD, reach=Melee(3), target=UpTo(2))
def m6113a2(c: Cast) -> None:
    if not c.first:
        return
    for victim in c.targets[:2]:
        c.use_power("m6113a1", on=victim, spend=False)


@power(
    "m6113a3", level=9, usage=Usage.RECHARGE, recharge=0, action=STANDARD, reach=Melee(3),
    target=Target(
        side="enemy", count=1, label="creature it is grabbing",
        relation=Relation.GRABBED_BY,
    ),
    keywords=[Keyword.ACID], attack=Attack(vs=FORT, printed=12),
    damage=Damage("4d8", 12, kind=LIMITED),
    dropped=("c.swallow(dc=)",),
)
def m6113a3(c: Cast) -> None:
    """Recharges when the swallow ends -- the exact moment it releases
    whoever it is holding -- rather than on a die.

    **Re-aimed off `c.grab(dc=)`, which this row does not do.** The card reads
    "the grab ends, and the target is swallowed (escape DC 17)", so the printed
    DC is the swallow's, not a grab's -- and this body *clears* `GRABBED_BY`
    before laying the swallow as a `Condition.REMOVED` on a `SAVE_ENDS` clock.
    When `c.grab(dc=)` landed, the other 57 rows in that group took their
    printed number and this one would have gone green on a verb it never calls.

    A swallow ends on a saving throw here, not on an escape check, so there is
    no contest for 17 to be the DC of. The missing piece is an escape *action*
    against a removed-from-play effect, which is a different mechanism from a
    grab and wants its own symbol.
    """
    victim = c.target
    if not c.strike():
        return
    c.hit()
    c.world.relations.clear(Relation.GRABBED_BY, c.me, victim, c.ref)
    me = c.me
    swallowed = c.world.effects.apply(
        victim, me, When.SAVE_ENDS, label=f"{c.ref} swallowed",
        conditions=[Condition.REMOVED], ongoing=(10, DamageType.ACID),
    )

    def freed() -> None:
        spot = _free_square_beside(c, me)
        if spot is not None:
            c.teleport(1, who=victim, to=spot)
        c.restore_use(c.ref, on=me)

    swallowed.on_end.append(freed)


@power(
    "m6113a4", level=9, usage=AT_WILL, action=MINOR, once_per_round=True, reach=CloseBurst(5),
    target=EACH_ENEMY, keywords=[Keyword.CHARM], attack=Attack(vs=WILL, printed=12),
)
def m6113a4(c: Cast) -> None:
    if c.strike():
        c.pull(4)


@power(
    "m6113a5", level=9, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET,
    keywords=[Keyword.ILLUSION], out_of_combat=True,
)
def m6113a5(c: Cast) -> None:
    """A disguise and the check to see through it -- no roll this engine
    makes, and the appearance changes nothing about how it fights."""


# ==========================================================================
# m6375
# ==========================================================================


@power("m6375a0", level=9, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m6375a0(c: Cast) -> None:
    me = c.me

    def snare(who: int) -> Effect | None:
        c.grants_advantage(on=who, until=When.ENCOUNTER)
        return c.grab(on=who)

    _aura(c, 1, lambda who: who != me and who in c.enemies(), snare)


@power("m6375a1", level=9, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m6375a1(c: Cast) -> None:
    """Squeezing through an opening sized for one of its own component
    creatures has no verb beside the two that do play."""
    c.shares_space(difficult=True)
    _refuses_the_shove(c)


@power(
    "m6375a2", level=9, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, attack=Attack(vs=AC, printed=14), damage=Damage("2d8", 8),
)
def m6375a2(c: Cast) -> None:
    if c.strike():
        c.hit()


# ==========================================================================
# m6441
# ==========================================================================


@power(
    "m6441a0", level=9, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14), damage=Damage("1d12", 11),
)
def m6441a0(c: Cast) -> None:
    if c.strike():
        c.hit()
    c.mark()


@power("m6441a1", level=9, usage=AT_WILL, action=STANDARD, reach=Melee(1), target=ONE_CREATURE)
def m6441a1(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    hits = 0
    for _ in range(2):
        c.use_power("m6441a0", on=victim, spend=False)
        if c.landed:
            hits += 1
    if hits >= 2:
        c.prone(on=victim)


@power(
    "m6441a2", level=9, usage=ENCOUNTER, action=MINOR, reach=PERSONAL, target=SELF,
    keywords=[Keyword.HEALING],
)
def m6441a2(c: Cast) -> None:
    me = c.me
    c.temp_hp(10, on=me)
    held = next((e for e in c.world.effects.of(me) if e.ongoing is not None), None)
    if held is not None:
        c.world.effects.save(held)
    if c.bloodied(me):
        c.heal(10, on=me)


@power(
    "m6441a3", level=9, usage=AT_WILL, action=INTERRUPT, reach=Melee(1), target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14), damage=Damage("1d12", 11),
    trigger="an adjacent enemy marked by it attacks without including it",
    on=Trigger(
        PowerUsed, _marked_within_looks_away(1), "a marked adjacent enemy attacks without it"
    ),
)
def m6441a3(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    if foe is not None and c.strike(on=foe):
        c.hit(on=foe)
        c.weakened(until=When.EOT, on=foe)


# ==========================================================================
# m6442
# ==========================================================================


@power(
    "m6442a0", level=9, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14), damage=Damage("2d10", 6),
)
def m6442a0(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.hit()
        body = c.world.get(victim, Health) if victim is not None else None
        if body is not None:
            body.temp = 0
    c.mark()


@power(
    "m6442a1", level=9, usage=AT_WILL, action=STANDARD, reach=Ranged(15),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14), damage=Damage("1d10", 10),
)
def m6442a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6442a2", level=9, usage=ENCOUNTER, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14), damage=Damage("2d10", 10, kind=LIMITED),
)
def m6442a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()
        c.condition(Condition.IMMOBILIZED, Condition.PINNED, until=When.SAVE_ENDS)


@power("m6442a3", level=9, usage=AT_WILL, action=MOVE, reach=PERSONAL, target=NO_TARGET)
def m6442a3(c: Cast) -> None:
    me = c.me
    c.penalty(AC, 2, on=me, until=When.EOT)
    mate = next((a for a in c.allies() if a != me and c.adjacent(a)), None)
    if mate is not None:
        c.temp_hp(5, on=mate)

