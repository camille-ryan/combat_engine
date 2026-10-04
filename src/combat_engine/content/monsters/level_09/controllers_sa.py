"""Monster abilities, level 9, controllers -- the second sweep.

200 rows across 42 stat blocks, all of `scripts/spec.py --monsters 9 --role
controller`. `controllers.py` holds the earlier sweep of this level and is
untouched here. Six of the 42 blocks print no abilities left to decorate --
`m2899`, `m323`, `m4911`, `m4940`, `m5048`, `m762` -- they are the earlier
sweep's, in full.

Conventions, inherited from `level_08/controllers_sa.py` and this level's own
`controllers.py`:

* numbers load from `game.db`; the attack line is written exactly as
  printed and the damage line goes in the header as data;
* a **trait** is a row that costs no action, has no target, and arms the
  watches that hold it, whatever action the compendium's column claims;
* a card with no printed range at all is read `Melee(1)`, even against a
  non-AC defence, when the attack is weapon-flavoured;
* a close burst, blast or area burst whose card names no target set takes
  **enemies**; one that says "creatures in the burst" outright takes
  `EACH_CREATURE`, which is a real distinction this file has to keep --
  `m3287a1`'s header note in `level_08/controllers_sa.py` is where that
  reading first got settled;
* "Hit: X. Effect: Y" with the Effect on its own line is unconditional --
  it happens on a miss too, unlike a clause folded into the Hit sentence;
* "Aftereffect: ..." installs a new effect when the first one *ends*
  (`Effect.on_end`), where "Each Failed Saving Throw: ..." makes it worse on
  a failed save (`escalate=`). The two read differently and this file keeps
  them apart.

Four shapes repeat across otherwise-unrelated stat blocks and share small
helpers rather than being re-derived each time:

* `m115838`, `m5555` and `m6074` print the identical kit -- a charge-bonus
  aura, a slide-on-hit melee swing, a forced-charge ranged charm, a
  lightning/fire recharge bolt, and a punish-the-attacker reaction. One
  helper per clause, called from all three blocks' rows.
* "+2 power bonus while not bloodied" and "-4 to saving throws in the aura"
  read straight off `c.bonus`/`when=`, evaluated live at the roll, so no
  enter/exit bookkeeping is needed for them.
* A standing aura's radius is set by resizing `zone.aura` after
  `c.my_aura` makes it -- `Zones.refresh` re-cuts the squares from that
  field every tick, which is the mechanism and not a dead end.
* Forced movement is negotiated on `ForcedMove`, a `Decision` carrying
  `source`, `target`, `how` and `squares` -- `c.cancel()` on it voids the
  shove outright, which is what "ignores the forced movement" and
  "negates it against itself" both are.

Six gaps named here, each confirmed absent from `scripts/vocab.py`:

* **No primitive says "cannot willingly end its turn farther from me."**
  `m5941a1` and `m6484a3` both print exactly this leash and both are
  `dropped=("c.leash()",)` -- `c.cannot_shift` and `c.immovable` are the
  wrong half of the sentence, they hold the *mover* still rather than
  bound its distance to a point.
* **No zone variant of `c.conceal`.** `c.cover_in` exists and grants cover,
  not concealment; nothing bounds a concealment grant to a zone's squares
  the way `c.grants_in`/`c.resist_in`/`c.cover_in` do for their own grants.
  `m1121a2` and `m6061a3` are `dropped=("c.conceal_in()",)`.
* **No way to roll a second, independent initiative**, the exact gap
  `docs/AUTHORING.md` names: `c.extra_turn(at=)` wants a count handed to
  it, not a second roll. `m5719a0` is `todo=("c.second_initiative()",
  "c.extra_reaction()")` -- the row's second half, a dedicated budget for
  immediate actions between turns, has nothing to wait on either.
* **`c.forbid` takes a ref, not a usage category.** "Can't use encounter
  powers until the end of its next turn" cannot be said as a blanket ban;
  `m5719a5` is `dropped=("c.forbid(usage=)",)`.
* **Nothing removes a creature from play and returns it later.** `m6092a2`
  is `dropped=("c.remove_from_play()",)` for that half; the domination
  itself is written in full.
* **`m5626a6` and `m6095a6`** name creatures to summon by printed kind.
  `m6095a6`'s card names its own sibling ref (`m6092`) outright, so that one
  summons it directly. `m5626a6` offers a choice between two kinds of
  modron this brief gives no ref for, so it is
  `todo=("etl.monster.summon_ref()",)`.

Two rows read as self-referential in a way that cannot be resolved with
confidence rather than approximated: `m3617a3`'s trigger names a ref
(`m3617a5`) that is not a sibling's own shift-reaction in any coherent
reading, and `m5779a0`'s condition names its own ref as something another
creature "has." Both are `todo=("etl.monster.trigger_text()",)` -- a data
problem in the extraction, not a missing capability, the same shape as the
no-attack-line defect `level_08/controllers_sa.py` named with
`etl.monster.attack_line()`.

One number is printed implausibly and kept as printed rather than guessed:
`m6543a3`'s reach is `Melee 20`, beside a sibling row's `Melee 2` for the
same creature's claws. Written as given; flagged in the report.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_02.artillery_sa import ALL_DEFENCES
from combat_engine.content.monsters.level_03.lurkers_sa import _restricted_to
from combat_engine.content.monsters.level_03.soldiers_sa import _secondary
from combat_engine.content.monsters.level_04.lurkers_sa import _hit_me_since_my_turn
from combat_engine.content.monsters.level_08.controllers import (
    _free_squares_near,
    _hands_the_use_back,
    _rearms_when_bloodied,
)
from combat_engine.content.monsters.level_08.controllers_sa import (
    _enemy_closes_in,
    _forced_basic_against_own_side,
)
from combat_engine.content.monsters.level_09.controllers import _bearing
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_ALLY,
    EACH_CREATURE,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    FREE,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_ALLY,
    ONE_CREATURE,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    WILL,
    ActionType,
    AreaBurst,
    Attack,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    Damage,
    DamageType,
    Effect,
    Forced,
    Keyword,
    Melee,
    Ranged,
    Target,
    UpTo,
    Usage,
    When,
    World,
    get,
    power,
    spread,
)
from combat_engine.engine.components import Health, Powers, Stats
from combat_engine.engine.events import (
    AdjacencyGained,
    AttackDeclared,
    Bloodied,
    DamageApplied,
    DamageRolled,
    Dropped,
    ForcedMove,
    Healed,
    Hit,
    Miss,
    PowerUsed,
    SavingThrow,
    TurnEnd,
    TurnStart,
    ZoneEntered,
    ZoneExited,
)
from combat_engine.engine.monster_math import LIMITED, MINION
from combat_engine.engine.query import adjacent, allies, creatures, distance_between, enemies, team
from combat_engine.engine.query import squares as squares_of
from combat_engine.engine.triggers import Trigger, about_me, both, by_melee, targets_me
from combat_engine.engine.zones import Zone

# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------


def _charge_aura(c: Cast, radius: int) -> None:
    """ "Aura N. Any ally that starts its turn in the aura gains a +2 power
    bonus to attack rolls and damage rolls on attacks made as part of
    charges until the end of that ally's turn." -- printed identically on
    `m115838`, `m5555` and `m6074`.

    `c.my_aura` makes an aura of its default radius; `zone.aura` is the
    live field `Zones.refresh` re-cuts the squares from every tick, so
    setting it after creation is how the radius becomes the printed one.
    """
    zone = c.my_aura(label=c.ref)
    zc = c.world.get(zone, Zone)
    if zc is not None:
        zc.aura = radius
    me = c.me

    def tick(ev: TurnStart) -> None:
        ally = ev.actor
        if ally == me or ally not in c.allies() or not c.in_my_aura(ally, label=c.ref):
            return
        on_charge = lambda ctx: bool(ctx.get("charge"))  # noqa: E731
        c.bonus("attack", 2, on=ally, kind="power", until=When.EOT, when=on_charge)
        c.bonus("damage", 2, on=ally, kind="power", until=When.EOT, when=on_charge)

    c.watch(TurnStart, tick, until=When.ENCOUNTER, on=me, label=f"{c.ref} aura")


def _slide_strike(c: Cast) -> None:
    """ "Melee 2 (one creature); Hit: 2d4 + 10 damage, and it slides the
    target 2 squares. Miss: it can slide the target 1 square." -- the
    melee half of the shared kit."""
    victim = c.target
    if c.strike():
        c.hit()
        c.slide(2)
    elif victim is not None and c.may("slide the target 1 square", who=c.me):
        c.slide(1, on=victim)


def _charm_charge(c: Cast) -> None:
    """ "Ranged 10 (one creature); Hit: 1d6 + 4 psychic damage, and the
    target uses a free action to charge a creature of its choosing." --
    turning a charmed foe against its own side. `c.charge_at` is the
    primitive; `allies(world, victim)` is the pool to pick from."""
    victim = c.target
    if not c.strike():
        return
    c.hit()
    if victim is None:
        return
    pool = [a for a in allies(c.world, victim) if a != victim]
    if not pool:
        return
    foe = c.choose(pool, f"{c.ref}: who does it charge") or pool[0]
    c.charge_at(foe, who=victim)


def _lightning_bolt(c: Cast) -> None:
    """ "Ranged 20 (one creature); Hit: 2d10 + 5 lightning damage, and
    ongoing 5 fire damage and cannot shift (save ends both)." One effect
    carrying both, so one saving throw ends both halves."""
    if not c.strike():
        return
    victim = c.target
    c.hit()
    if victim is None:
        return
    c.world.effects.apply(
        victim,
        c.me,
        When.SAVE_ENDS,
        label=f"{c.ref} burn",
        ongoing=(5, DamageType.FIRE),
        conditions=[Condition.CANNOT_SHIFT],
    )


def _punish_adjacent_attacker(c: Cast) -> None:
    """ "Trigger: an enemy adjacent to it deals damage to it. Melee 1 (the
    triggering enemy); Hit: 1d6 + 4 damage, and it pushes the target up to
    3 squares." The reaction half of the shared kit."""
    foe = getattr(c.trigger, "actor", getattr(c.trigger, "source", None))
    if foe is None or not c.strike(on=foe):
        return
    c.hit(on=foe)
    c.push(3, on=foe)


def _adjacent_damages_me(world: World, me: int, ev: Any) -> bool:
    source = getattr(ev, "source", None)
    return getattr(ev, "target", None) == me and source is not None and adjacent(world, source, me)


def _shoved_me_within(radius: int) -> Any:
    def pred(world: World, me: int, ev: ForcedMove) -> bool:
        return (
            ev.target == me
            and ev.source in enemies(world, me)
            and distance_between(world, me, ev.source) <= radius
        )

    return pred


def _shoved_me(world: World, me: int, ev: ForcedMove) -> bool:
    return ev.target == me and ev.source in enemies(world, me)


_FORCED_MOVERS = {
    Forced.PUSH: "push",
    Forced.PULL: "pull",
    Forced.SLIDE: "slide",
}


# ==========================================================================
# m1086
# ==========================================================================


@power(
    "m1086a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d8", 4),
)
def m1086a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1086a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("2d6", 6, dtype=DamageType.PSYCHIC),
)
def m1086a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1086a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.RADIANT, Keyword.RANGED],
    attack=Attack(vs=FORT, printed=13),
)
def m1086a2(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.push(1)
        if victim is not None:
            c.blinded(until=When.EONT, on=victim)


@power(
    "m1086a3",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
)
def m1086a3(c: Cast) -> None:
    """ "Make two m1086a1 attacks, two m1086a2 attacks, or one of each" --
    the choice is the attacker's; one victim for the whole use, since the
    card names no second target."""
    victim = c.target
    if victim is None:
        return
    choice = c.choose(["two psychic", "two radiant", "one of each"], f"{c.ref}: which pair")
    if choice == "two psychic":
        for _ in range(2):
            c.use_power("m1086a1", on=victim)
    elif choice == "two radiant":
        for _ in range(2):
            c.use_power("m1086a2", on=victim)
    else:
        c.use_power("m1086a1", on=victim)
        c.use_power("m1086a2", on=victim)


@power(
    "m1086a4",
    level=9,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC, Keyword.CLOSE],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("2d8", 6, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m1086a4(c: Cast) -> None:
    """ "Restraining the target until the end of **its** next turn" -- the
    target's own turn, not m1086's, so `When.EOTNT` and not the `EONT`
    default."""
    if c.strike():
        c.hit()
        c.condition(Condition.RESTRAINED, until=When.EOTNT)


@power(
    "m1086a5",
    level=9,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED],
    attack=Attack(vs=WILL, printed=13),
)
def m1086a5(c: Cast) -> None:
    victim = c.target
    if not c.strike():
        return
    c.dazed(until=When.EONT)
    if victim is None:
        return
    if c.choose(["slide 4 squares", "knock prone"], f"{c.ref}: which") == "slide 4 squares":
        c.slide(4, on=victim)
    else:
        c.prone(on=victim)


@power(
    "m1086a6",
    level=9,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=CloseBurst(1),
    target=NO_TARGET,
    keywords=[Keyword.FEAR, Keyword.CLOSE],
    attack=Attack(vs=WILL, printed=13),
    trigger="an enemy moves to a square adjacent to it",
    on=Trigger(AdjacencyGained, _enemy_closes_in, "an enemy moves to a square adjacent to it"),
)
def m1086a6(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    if foe is None or not c.strike(on=foe):
        return
    c.push(4, on=foe)


@power(
    "m1086a7",
    level=9,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FEAR],
    trigger="it is first bloodied",
    on=Trigger(Bloodied, about_me, "it is first bloodied"),
)
def m1086a7(c: Cast) -> None:
    c.restore_use("m1086a6", on=c.me)
    c.use_power("m1086a6")


@power(
    "m1086a8",
    level=9,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POLYMORPH],
    trigger="it is first injured",
    on=Trigger(DamageApplied, targets_me, "it is first injured"),
)
def m1086a8(c: Cast) -> None:
    """ "Takes on a monstrous tentacled form; enemies take -1 to melee and
    ranged attacks against it until bloodied." Both of those defences roll
    against AC, so +1 AC until the threshold reads the same as the
    printed -1, and the hold ends itself early on `Bloodied`."""
    c.note(f"{c.ref}: takes on a grotesque tentacled form")
    hold = c.bonus(AC, 1, on=c.me, until=When.ENCOUNTER)
    if hold is None:
        return

    def ends(ev: Bloodied) -> None:
        if ev.actor == c.me and not hold.ended:
            c.world.effects.end(hold, "it is bloodied")

    hold.subs.append(c.world.bus.on(Bloodied, ends, owner=c.me))


# ==========================================================================
# m1121
# ==========================================================================


@power(
    "m1121a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d4", 3),
)
def m1121a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)


@power(
    "m1121a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.RANGED],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("1d6", 6, dtype=DamageType.NECROTIC),
)
def m1121a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.EONT)


@power(
    "m1121a2",
    level=9,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC, Keyword.AREA],
    attack=Attack(vs=FORT, printed=14),
    damage=Damage("2d8", 6, dtype=DamageType.NECROTIC, kind=LIMITED),
    dropped=("c.conceal_in()",),
)
def m1121a2(c: Cast) -> None:
    """A cloud appears regardless of the roll and lingers until m1121's
    next turn ends; its 6-damage tick and the concealment it grants are
    both unconditional on the Hit. The damage tick is written; the
    concealment has no zone-bound primitive -- see the module docstring."""
    if c.strike():
        c.hit()
    if not c.first:
        return
    area = frozenset(c.area())
    zone = c.zone(area, until=When.EONT, label=c.ref)

    def tick(ev: TurnStart) -> None:
        if ev.actor in c.in_squares(area, side="any"):
            c.flat(6, dtype=DamageType.NECROTIC, on=ev.actor)

    c.watch(TurnStart, tick, until=When.EONT, on=c.me, label=f"{c.ref} zone")
    _ = zone


@power(
    "m1121a3",
    level=9,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
)
def m1121a3(c: Cast) -> None:
    """ "Can turn invisible until the end of his next turn", sustain
    standard -- built directly on `Effects.apply` the way `c.invisible`
    is internally, with `When.SUSTAIN`/`sustain_cost` rather than
    `c.invisible`'s fixed `until`, since that method takes no sustain."""
    from combat_engine.engine import Relation

    me = c.me
    watchers = c.enemies()
    pairs = [(Relation.HIDDEN_FROM, me, w) for w in watchers]
    if not pairs:
        return
    c.world.effects.apply(
        me,
        me,
        When.SUSTAIN,
        label=f"{c.ref} unseen",
        relations=pairs,
        sustain_cost=STANDARD,
    )


# ==========================================================================
# m1157
# ==========================================================================


@power(
    "m1157a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d6", 6),
)
def m1157a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1157a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.MELEE],
    attack=Attack(vs=AC, printed=14),
)
def m1157a1(c: Cast) -> None:
    """On a hit, the secondary effect is the charm: the target cannot
    attack it, and interposes for it against melee or ranged attacks while
    adjacent. "Only one target at a time" ends any older hold of this
    row's own label before laying the new one."""
    if not c.strike():
        return
    victim = c.target
    if victim is None:
        return
    label = f"{c.ref} cannot attack"
    for eff in list(c.world.effects.live.values()):
        if eff.owner != victim and eff.label == label and eff.source == c.me and not eff.ended:
            c.world.effects.end(eff, "m1157 affects only one target at a time")
    hold = c.cannot_attack(on=victim, against=c.me, until=When.ENCOUNTER)
    if hold is None:
        return
    me = c.me

    def interpose(ev: AttackDeclared) -> None:
        if hold.ended or ev.attacker == victim or ev.target != me:
            return
        if c.adjacent(to=victim):
            c.redirect(to=victim)

    def ends_on_attack(ev: Hit) -> None:
        if hold.ended:
            return
        if ev.attacker in ({me} | set(c.allies())) and ev.target == victim:
            c.world.effects.end(hold, "m1157 or an ally attacked the target")

    hold.subs.append(c.world.bus.on(AttackDeclared, interpose, owner=me))
    hold.subs.append(c.world.bus.on(Hit, ends_on_attack, owner=me))


@power(
    "m1157a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=12),
)
def m1157a2(c: Cast) -> None:
    if c.strike():
        c.condition(Condition.DOMINATED, until=When.EONT)


@power(
    "m1157a3",
    level=9,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
    out_of_combat=True,
)
def m1157a3(c: Cast) -> None:
    c.note(f"{c.ref}: alters its form to appear as a Medium humanoid")


# ==========================================================================
# m115838
# ==========================================================================


@power(
    "m115838a0",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m115838a0(c: Cast) -> None:
    _charge_aura(c, 3)


@power(
    "m115838a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d4", 10),
)
def m115838a1(c: Cast) -> None:
    _slide_strike(c)


@power(
    "m115838a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=12),
    damage=Damage("1d6", 4, dtype=DamageType.PSYCHIC),
)
def m115838a2(c: Cast) -> None:
    _charm_charge(c)


@power(
    "m115838a3",
    level=9,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.LIGHTNING, Keyword.RANGED],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("2d10", 5, dtype=DamageType.LIGHTNING, kind=LIMITED),
)
def m115838a3(c: Cast) -> None:
    _lightning_bolt(c)


@power(
    "m115838a4",
    level=9,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("1d6", 4),
    trigger="an enemy adjacent to it deals damage to it",
    on=Trigger(DamageApplied, _adjacent_damages_me, "an enemy adjacent to it deals damage to it"),
)
def m115838a4(c: Cast) -> None:
    _punish_adjacent_attacker(c)


# ==========================================================================
# m1183
# ==========================================================================


@power(
    "m1183a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d8", 5),
)
def m1183a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1183a1",
    level=9,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING, Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("3d8", 5, dtype=DamageType.LIGHTNING, kind=LIMITED),
)
def m1183a1(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    c.slide(5)
    for foe in c.within(1, of=victim, side="enemy"):
        if foe != victim:
            c.flat(c.roll("1d8") + 5, dtype=DamageType.LIGHTNING, on=foe)


@power(
    "m1183a2",
    level=9,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.LIGHTNING, Keyword.AREA],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("2d10", 8, dtype=DamageType.LIGHTNING, kind=LIMITED),
)
def m1183a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(3)


@power(
    "m1183a3",
    level=9,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.LIGHTNING, Keyword.THUNDER],
)
def m1183a3(c: Cast) -> None:
    me = c.me
    hold = c.effect(c.ref, until=When.EONT, on=me)
    if hold is None:
        return

    def rider(ev: Hit) -> None:
        if hold.ended or ev.attacker != me:
            return
        p = get(ev.power)
        if p is None:
            return
        if Keyword.LIGHTNING in p.keywords:
            c.flat(c.roll("1d8"), dtype=DamageType.LIGHTNING, on=ev.target)
        elif Keyword.THUNDER in p.keywords:
            c.flat(c.roll("1d8"), dtype=DamageType.THUNDER, on=ev.target)

    hold.subs.append(c.world.bus.on(Hit, rider, owner=me))


@power(
    "m1183a4",
    level=9,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=Melee(1),
    target=NO_TARGET,
    trigger="it is hit by a melee attack",
    on=Trigger(Hit, both(targets_me, by_melee), "it is hit by a melee attack"),
)
def m1183a4(c: Cast) -> None:
    foe = getattr(c.trigger, "attacker", None)
    if foe is not None:
        c.push(5, on=foe)


# ==========================================================================
# m1585
# ==========================================================================


@power(
    "m1585a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d8", 2),
)
def m1585a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1585a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d4", 2),
)
def m1585a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1585a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.RANGED],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("1d6", 5, dtype=DamageType.POISON),
)
def m1585a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.weakened(until=When.SAVE_ENDS)


@power(
    "m1585a3",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.RANGED],
)
def m1585a3(c: Cast) -> None:
    victim = c.target
    if victim is not None:
        for _ in range(2):
            c.use_power("m1585a2", on=victim)


@power(
    "m1585a4",
    level=9,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.RANGED],
    attack=Attack(vs=FORT, printed=13),
)
def m1585a4(c: Cast) -> None:
    if c.strike():
        c.condition(Condition.SLOWED, until=When.SAVE_ENDS, ongoing=(5, DamageType.NECROTIC))


@power(
    "m1585a5",
    level=9,
    usage=Usage.RECHARGE,
    recharge=6,
    once_per_round=True,
    action=MINOR,
    reach=CloseBurst(10),
    target=EACH_ALLY,
)
def m1585a5(c: Cast) -> None:
    ally = c.target
    if ally is not None:
        c.bonus("speed", 5, on=ally, until=When.EONT)


@power(
    "m1585a6",
    level=9,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ALLY,
    keywords=[Keyword.HEALING, Keyword.CLOSE],
)
def m1585a6(c: Cast) -> None:
    ally = c.target
    if ally is not None and c.bloodied(on=ally):
        c.heal(15, on=ally)


# ==========================================================================
# m1906
# ==========================================================================


@power(
    "m1906a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.MELEE],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d8", 3),
)
def m1906a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.flat(10, dtype=DamageType.NECROTIC)


@power(
    "m1906a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.MELEE],
)
def m1906a1(c: Cast) -> None:
    chosen = c.target
    pool = sorted(
        (f for f in c.enemies() if f != chosen and c.distance(to=f) <= 2),
        key=lambda f: c.distance(to=f),
    )
    targets = ([chosen] if chosen is not None and c.distance(to=chosen) <= 2 else []) + pool
    for foe in targets[:3]:
        c.use_power("m1906a0", on=foe)


@power(
    "m1906a2",
    level=9,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED],
    attack=Attack(vs=WILL, printed=11),
)
def m1906a2(c: Cast) -> None:
    """ "Aftereffect: the target is slowed (save ends)" fires when the
    stun ends, not on a failed save -- `Effect.on_end`, not `escalate`."""
    victim = _restricted_to(c, 5, lambda f: c.bloodied(on=f))
    if victim is None or not c.strike(on=victim):
        return
    hold = c.condition(Condition.STUNNED, until=When.SAVE_ENDS, on=victim)
    if hold is not None:
        hold.on_end.append(lambda v=victim: c.slowed(until=When.SAVE_ENDS, on=v))


@power(
    "m1906a3",
    level=9,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(2),
    target=NO_TARGET,
    keywords=[Keyword.HEALING, Keyword.MELEE],
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("4d6", 6),
    trigger="a creature within 2 squares of it becomes bloodied",
    on=Trigger(
        Bloodied,
        lambda world, me, ev: distance_between(world, me, ev.actor) <= 2,
        "a creature within 2 squares of it becomes bloodied",
    ),
)
def m1906a3(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    if foe is None or not c.strike(on=foe):
        return
    c.hit(on=foe)
    c.weakened(until=When.SAVE_ENDS, on=foe)
    c.spend_surge(on=c.me)
    c.heal(103, on=c.me)


@power(
    "m1906a4",
    level=9,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC, Keyword.CLOSE],
    attack=Attack(vs=WILL, printed=11),
    damage=Damage("4d6", 6, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m1906a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)


@power(
    "m1906a5",
    level=9,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC],
    trigger="it is first bloodied",
    on=Trigger(Bloodied, about_me, "it is first bloodied"),
)
def m1906a5(c: Cast) -> None:
    c.restore_use("m1906a4", on=c.me)
    c.use_power("m1906a4")


# ==========================================================================
# m2063
# ==========================================================================


@power(
    "m2063a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE, Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("1d6", 5),
)
def m2063a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.flat(c.roll("1d6"), dtype=DamageType.FORCE)
        c.push(3)


@power(
    "m2063a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(12),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE, Keyword.RANGED],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("1d8", 5, dtype=DamageType.FORCE),
)
def m2063a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized(until=When.EONT)


@power(
    "m2063a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(12),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE, Keyword.RANGED],
)
def m2063a2(c: Cast) -> None:
    chosen = c.target
    pool = [f for f in c.enemies() if f != chosen]
    targets = ([chosen] if chosen is not None else []) + sorted(
        pool, key=lambda f: c.distance(to=f)
    )
    for foe in targets[:2]:
        c.use_power("m2063a1", on=foe)


@power(
    "m2063a3",
    level=9,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(1, 15),
    target=EACH_ENEMY,
    keywords=[Keyword.FORCE, Keyword.ZONE, Keyword.AREA],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("3d8", 5, dtype=DamageType.FORCE, kind=LIMITED),
)
def m2063a3(c: Cast) -> None:
    """Aftereffect: a difficult-terrain zone for m2063's enemies only --
    `c.ignores_difficult_in(side="team")` exempts the caster's own side
    from the blanket `difficult=True`."""
    if c.strike():
        c.hit()
    if not c.first:
        return
    zone = c.zone(c.area(), until=When.SUSTAIN, sustain=MINOR, difficult=True, label=c.ref)
    c.ignores_difficult_in(zone, side="team")
    area = frozenset(c.area())

    def tick(ev: TurnStart) -> None:
        if ev.actor in c.in_squares(area, side="enemy"):
            c.flat(5, dtype=DamageType.FORCE, on=ev.actor)

    c.watch(TurnStart, tick, until=When.EONT, on=c.me, label=f"{c.ref} zone")
    zc = c.world.get(zone, Zone)
    hold = zc.effect if zc is not None else None
    if hold is not None:
        c.endable(hold, cost=MINOR)


@power(
    "m2063a4",
    level=9,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FORCE],
    trigger="it is hit or missed by a melee attack",
    on=[
        Trigger(Hit, both(targets_me, by_melee), "it is hit by a melee attack"),
        Trigger(Miss, both(targets_me, by_melee), "it is missed by a melee attack"),
    ],
)
def m2063a4(c: Cast) -> None:
    foe = getattr(c.trigger, "attacker", None)
    if foe is not None:
        c.use_power("m2063a1", on=foe)


# ==========================================================================
# m2066
# ==========================================================================


@power(
    "m2066a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d8", 3),
)
def m2066a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2066a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.CHARM, Keyword.CLOSE],
    attack=Attack(vs=WILL, printed=15),
)
def m2066a1(c: Cast) -> None:
    """ "Special: Deafened creatures are immune" -- no roll at all against
    one, rather than a roll that cannot matter."""
    victim = c.target
    if victim is not None and c.is_(Condition.DEAFENED, on=victim):
        return
    if c.strike():
        c.pull(3)
        c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS)


@power(
    "m2066a2",
    level=9,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.THUNDER, Keyword.CLOSE],
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("1d6", 5, dtype=DamageType.THUNDER, kind=LIMITED),
)
def m2066a2(c: Cast) -> None:
    """The secondary burst has no ref of its own, the way `_two_rays`'s
    four rays do not. Driven entirely off `c.first` and `c.targets`, the
    way `_two_rays` is, rather than off the engine's own once-per-target
    dispatch: the primary hits have to all be known before the secondary
    burst can be centred on one of them."""
    if not c.first:
        return
    hits = []
    for victim in c.targets:
        if c.strike(on=victim):
            c.hit(on=victim)
            hits.append(victim)
    if not hits:
        return
    center = c.choose(hits, f"{c.ref}: who the secondary burst centres on") or hits[0]
    pivot = next(iter(squares_of(c.world, center)), None)
    if pivot is None:
        return
    for foe in c.in_squares(spread({pivot}, 1), side="enemy"):
        if _secondary(c, 15, FORT, foe):
            c.damage("1d6", 5, dtype=DamageType.THUNDER, on=foe)
            c.slide(3, on=foe)


@power(
    "m2066a3",
    level=9,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it drops to 0 hit points and is killed",
    on=Trigger(Dropped, about_me, "it drops to 0 hit points and is killed"),
)
def m2066a3(c: Cast) -> None:
    """"Remains standing" -- held at 1 hit point rather than dropping,
    gaining the undead origin (`c.set_origin`, written for exactly this
    sentence) for the duration. Actually dies, through the normal
    pipeline, at the end of its own next turn."""
    me = c.me
    health = c.world.get(me, Health)
    if health is not None:
        health.hp = 1
    c.set_origin("undead", on=me, until=When.EONT)

    def expire(ev: TurnEnd) -> None:
        if ev.actor == me and not ev.ghost:
            c.flat(999, on=me)

    c.watch(TurnEnd, expire, until=When.EONT, on=me, once=True, label=c.ref)


# ==========================================================================
# m2547
# ==========================================================================


@power(
    "m2547a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d8", 5),
)
def m2547a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)


@power(
    "m2547a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d8", 5),
)
def m2547a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2547a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
)
def m2547a2(c: Cast) -> None:
    """ "Makes two claw attacks. If she hits a single target with both
    claws, she makes a bite attack against the same target." Both claws
    at the one chosen victim -- the card's "a single target" is the
    read, not two separate swings that happen to land on the same one."""
    victim = c.target
    if victim is None:
        return
    hits = 0
    for _ in range(2):
        c.use_power("m2547a1", on=victim)
        if c.landed:
            hits += 1
    if hits == 2:
        c.use_power("m2547a0", on=victim)


@power(
    "m2547a3",
    level=9,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
)
def m2547a3(c: Cast) -> None:
    victim = c.target
    if victim is not None:
        c.no_provoke(from_=victim, on=c.me, until=When.EOT)
    c.move(12, who=c.me)
    if victim is not None:
        c.use_power("m2547a0", on=victim)


@power(
    "m2547a4",
    level=9,
    usage=AT_WILL,
    once_per_round=True,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.GAZE],
    attack=Attack(vs=WILL, printed=12),
)
def m2547a4(c: Cast) -> None:
    if c.strike():
        c.slide(2)


@power(
    "m2547a5",
    level=9,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.POISON, Keyword.CLOSE],
    attack=Attack(vs=FORT, printed=10),
    damage=Damage("4d6", 6, dtype=DamageType.POISON, kind=LIMITED),
)
def m2547a5(c: Cast) -> None:
    victim = c.target
    if not c.strike():
        return
    c.hit()
    hold = c.slowed(until=When.SAVE_ENDS)
    if hold is not None and victim is not None:
        hold.on_end.append(
            lambda v=victim: c.condition(
                Condition.SLOWED, Condition.WEAKENED, until=When.SAVE_ENDS, on=v
            )
        )


@power(
    "m2547a6",
    level=9,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POISON],
    trigger="it is first bloodied",
    on=Trigger(Bloodied, about_me, "it is first bloodied"),
)
def m2547a6(c: Cast) -> None:
    c.restore_use("m2547a5", on=c.me)
    c.use_power("m2547a5")


@power(
    "m2547a7",
    level=9,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR, Keyword.CLOSE],
    attack=Attack(vs=WILL, printed=10),
)
def m2547a7(c: Cast) -> None:
    victim = c.target
    hold = c.stunned(until=When.EONT) if c.strike() else None
    if hold is not None and victim is not None:
        hold.on_end.append(lambda v=victim: c.penalty("attack", 2, on=v, until=When.SAVE_ENDS))


# ==========================================================================
# m3474
# ==========================================================================


@power(
    "m3474a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d8", 6),
)
def m3474a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.grab()


@power(
    "m3474a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d10", 6),
)
def m3474a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(2)


@power(
    "m3474a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
)
def m3474a2(c: Cast) -> None:
    chosen = c.target
    pool = [f for f in c.enemies() if f != chosen]
    targets = ([chosen] if chosen is not None else []) + sorted(
        pool, key=lambda f: c.distance(to=f)
    )
    for foe in targets[:2]:
        c.use_power("m3474a1", on=foe)


@power(
    "m3474a3",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("1d8", 6),
)
def m3474a3(c: Cast) -> None:
    victim = _restricted_to(c, 2, lambda f: f in c.grabbing(of=c.me))
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)
        c.push(6, on=victim)
        c.prone(on=victim)
    else:
        c.push(2, on=victim)


@power(
    "m3474a4",
    level=9,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=CloseBurst(10),
    target=NO_TARGET,
    keywords=[Keyword.LIGHTNING, Keyword.CLOSE],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("1d8", 5, dtype=DamageType.LIGHTNING),
    trigger="it is hit by an attack",
    on=Trigger(Hit, targets_me, "it is hit by an attack"),
)
def m3474a4(c: Cast) -> None:
    foe = getattr(c.trigger, "attacker", None)
    if foe is None or not c.strike(on=foe):
        return
    c.hit(on=foe)
    c.push(2, on=foe)
    c.prone(on=foe)


@power(
    "m3474a5",
    level=9,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FORCE, Keyword.CLOSE],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("2d6", 5, dtype=DamageType.FORCE, kind=LIMITED),
)
def m3474a5(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.SLOWED, until=When.SAVE_ENDS)
        c.push(3)


@power(
    "m3474a6",
    level=9,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FORCE],
    trigger="it is first bloodied",
    on=Trigger(Bloodied, about_me, "it is first bloodied"),
)
def m3474a6(c: Cast) -> None:
    c.restore_use("m3474a5", on=c.me)
    c.use_power("m3474a5")


@power(
    "m3474a7",
    level=9,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.CHARM, Keyword.CLOSE],
    attack=Attack(vs=WILL, printed=11),
)
def m3474a7(c: Cast) -> None:
    if c.strike():
        c.condition(Condition.DOMINATED, until=When.EONT)
    else:
        c.dazed(until=When.EONT)


# ==========================================================================
# m3617
# ==========================================================================


@power(
    "m3617a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d6", 5),
)
def m3617a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3617a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("2d6", 7),
)
def m3617a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.blinded(until=When.SAVE_ENDS)


@power(
    "m3617a2",
    level=9,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED],
    attack=Attack(vs=WILL, printed=16),
)
def m3617a2(c: Cast) -> None:
    """ "The target takes 4d6 + 8 damage if it moves during its turn
    (save ends)" -- a standing threat hung on `MoveStart`, which fires
    before the step is taken and is where "if it moves" has to ask."""
    if not c.strike():
        return
    victim = c.target
    if victim is None:
        return
    hold = c.effect(c.ref, until=When.SAVE_ENDS, on=victim)
    if hold is None:
        return

    def moved(ev: Any) -> None:
        if hold.ended or ev.actor != victim:
            return
        c.flat(c.roll("4d6") + 8, on=victim)

    from combat_engine.engine.events import MoveStart

    hold.subs.append(c.world.bus.on(MoveStart, moved, owner=c.me))


@power(
    "m3617a3",
    level=9,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Ranged(10),
    target=NO_TARGET,
    todo=("etl.monster.trigger_text()",),
)
def m3617a3(c: Cast) -> None:
    """The printed trigger reads "when an ally uses m3617a5" -- a ref
    local to this stat block, which an ally cannot "use." No coherent
    reading of what this is actually gated on survived extraction, the
    same shape as `level_08/controllers_sa.py`'s `m2787a2` naming itself
    mid-sentence. Not written rather than guessed."""
    return


@power(
    "m3617a4",
    level=9,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(3, 10),
    target=EACH_ENEMY,
    dropped=("c.conceal_in()",),
)
def m3617a4(c: Cast) -> None:
    """ "Automatic hit" -- no roll, so the -2 penalty and the concealment
    are laid outright. The penalty is written; concealment bound to a
    zone has no primitive, see the module docstring."""
    if not c.first:
        return
    zone = c.zone(c.area(), until=When.SUSTAIN, sustain=MINOR, label=c.ref)
    c.grants_in(zone, "attack", -2, side="enemy", kind="untyped")
    zc = c.world.get(zone, Zone)
    hold = zc.effect if zc is not None else None

    def grow() -> None:
        c.move_zone(zone, 5)

    if hold is not None:
        c.on_sustain(hold, grow)


@power(
    "m3617a5",
    level=9,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is targeted by a melee attack",
    on=Trigger(AttackDeclared, both(targets_me, by_melee), "it is targeted by a melee attack"),
)
def m3617a5(c: Cast) -> None:
    c.shift(1)


@power(
    "m3617a6",
    level=9,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is targeted by a ranged attack",
    on=Trigger(
        AttackDeclared,
        lambda w, me, ev: ev.target == me and not by_melee(w, me, ev),
        "it is targeted by a ranged attack",
    ),
)
def m3617a6(c: Cast) -> None:
    candidates = [
        a
        for a in c.allies()
        if a != c.me and c.adjacent(to=a) and getattr(c.world.get(a, Stats), "level", 99) <= 12
    ]
    if not candidates:
        return
    ally = c.choose(candidates, f"{c.ref}: redirect to which ally") or candidates[0]
    c.redirect(to=ally)


@power(
    "m3617a7",
    level=9,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
    trigger="an ally within 5 squares is reduced to 0 hit points",
    on=Trigger(
        Dropped,
        lambda w, me, ev: ev.actor in allies(w, me) and distance_between(w, me, ev.actor) <= 5,
        "an ally within 5 squares is reduced to 0 hit points",
    ),
)
def m3617a7(c: Cast) -> None:
    c.heal(6, on=c.me)


# ==========================================================================
# m3983
# ==========================================================================


@power(
    "m3983a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d8", 3),
)
def m3983a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3983a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d8", 3),
)
def m3983a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m3983a2",
    level=9,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_ALLY,
)
def m3983a2(c: Cast) -> None:
    """Restricted to an undead or beast ally -- `Target` filters on side
    and count, not kind, so the restriction is asked here."""
    pool = [
        a
        for a in c.allies()
        if (c.is_kind("undead", on=a) or c.is_kind("beast", on=a)) and c.distance(to=a) <= 10
    ]
    chosen = c.target
    ally = chosen if chosen in pool else (pool[0] if pool else None)
    if ally is None:
        return
    # `c.basic(who=)` names the attacker; the victim still defaults to
    # `c.target`, which here is the ally itself. Named explicitly.
    foe = next((f for f in c.enemies() if c.adjacent_to(ally, f)), None)
    if foe is None:
        ranked = sorted(c.enemies(), key=lambda f: c.distance(to=f))
        foe = ranked[0] if ranked else None
    if foe is None:
        return
    c.basic(who=ally, on=foe)
    if c.landed:
        c.heal(10, on=ally)


@power(
    "m3983a3",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=13),
)
def m3983a3(c: Cast) -> None:
    if not c.strike():
        return
    c.slide(6)
    victim = c.target
    if victim is None:
        return
    nearby = [a for a in c.allies() if c.adjacent_to(victim, a)]
    if nearby:
        attacker = c.choose(nearby, f"{c.ref}: who gets the free attack") or nearby[0]
        c.basic(who=attacker, on=victim)


@power(
    "m3983a4",
    level=9,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is reduced to 0 hit points",
    on=Trigger(Dropped, about_me, "it is reduced to 0 hit points"),
)
def m3983a4(c: Cast) -> None:
    """Feigns death: falls prone with 10 hit points instead of dropping,
    and arms a one-shot interrupt for the first enemy to walk away from
    it without shifting."""
    me = c.me
    health = c.world.get(me, Health)
    if health is not None:
        health.hp = 10
    c.prone(on=me)

    from combat_engine.engine.events import MoveStart

    def leaves(ev: MoveStart) -> None:
        if ev.kind_ == "shift" or ev.actor not in enemies(c.world, me):
            return
        if not c.adjacent(to=ev.actor):
            return
        c.cure(Condition.PRONE, on=me)
        c.use_power("m3983a1", on=ev.actor)

    c.watch(MoveStart, leaves, until=When.ENCOUNTER, on=me, once=True, label=c.ref)


# ==========================================================================
# m4309
# ==========================================================================


@power(
    "m4309a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d6", 3),
)
def m4309a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4309a1",
    level=9,
    usage=AT_WILL,
    once_per_round=True,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=13),
    damage=Damage("2d8", 3, dtype=DamageType.PSYCHIC),
)
def m4309a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(5)


@power(
    "m4309a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING, Keyword.NECROTIC, Keyword.RANGED],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("2d8", 3, dtype=DamageType.NECROTIC),
)
def m4309a2(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    c.weakened(until=When.EONT)
    pool = [a for a in c.allies() if c.is_kind("undead", on=a) and c.distance(to=a) <= 5]
    if pool:
        who = c.choose(pool, f"{c.ref}: which undead ally heals") or pool[0]
        c.heal(5, on=who)


@power(
    "m4309a3",
    level=9,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.COLD, Keyword.HEALING, Keyword.AREA],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("4d6", 3, dtype=DamageType.COLD, kind=LIMITED),
)
def m4309a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.SAVE_ENDS)
    if c.first:
        pool = [
            a
            for a in c.allies()
            if c.is_kind("undead", on=a) and a in c.in_squares(c.area(), side="any")
        ]
        for who in pool:
            c.heal(5, on=who)


@power(
    "m4309a4",
    level=9,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m4309a4(c: Cast) -> None:
    me = c.me

    def paid_back(ctx: dict[str, Any]) -> bool:
        return ctx.get("target") in _hit_me_since_my_turn(c)

    # Untyped, both calls: the card prints a bare "+1 bonus" and "5 extra damage".
    c.bonus("attack", 1, on=me, until=When.ENCOUNTER, once=True, when=paid_back)
    c.bonus("damage", 5, on=me, until=When.ENCOUNTER, once=True, when=paid_back)


# ==========================================================================
# m4420
# ==========================================================================


@power(
    "m4420a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d4", 5),
)
def m4420a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.EONT)


@power(
    "m4420a1",
    level=9,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=Target(side="enemy", count=2),
    keywords=[Keyword.CHARM, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=13),
)
def m4420a1(c: Cast) -> None:
    if c.strike():
        c.condition(Condition.DOMINATED, until=When.SAVE_ENDS)


@power(
    "m4420a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
)
def m4420a2(c: Cast) -> None:
    pool = sorted(c.enemies(), key=lambda f: c.distance(to=f))
    if not pool:
        return
    first = pool[0]
    second = next((f for f in pool if f != first), None)
    c.use_power("m4420a3", on=first)
    if second is not None:
        c.use_power("m4420a4", on=second)


@power(
    "m4420a3",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ILLUSION, Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("1d8", 7, dtype=DamageType.PSYCHIC),
)
def m4420a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(1)


@power(
    "m4420a4",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.TELEPORTATION, Keyword.RANGED],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("1d8", 7),
)
def m4420a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.teleport(3, who=c.target)


# ==========================================================================
# m5098
# ==========================================================================


@power(
    "m5098a0",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m5098a0(c: Cast) -> None:
    """ "Begins combat occupying 1 square of water and cannot move" -- the
    stat block's own Speed 0, loaded from `game.db`, already says the
    second half; nothing is left for this row to add."""
    c.note(f"{c.ref}: starts the fight occupying a square of water")


@power(
    "m5098a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(4),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("", 8, kind=MINION),
)
def m5098a1(c: Cast) -> None:
    """Requirement: must not already have a creature grabbed -- asked in
    the body rather than as `requires=`, since there is only ever one
    grab to hold and the printed Requirement is this simple to re-check
    on every use."""
    if c.grabbing(of=c.me):
        return
    if c.strike():
        c.hit()
        c.grab()


@power(
    "m5098a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(4),
    target=NO_TARGET,
)
def m5098a2(c: Cast) -> None:
    victim = next(iter(c.grabbing(of=c.me)), None)
    if victim is None:
        return
    c.flat(8, on=victim)
    c.slide(2, on=victim)


# ==========================================================================
# m5417
# ==========================================================================


@power(
    "m5417a0",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5417a0(c: Cast) -> None:
    zone = c.my_aura(label=c.ref)
    zc = c.world.get(zone, Zone)
    if zc is not None:
        zc.aura = 2
    me = c.me

    def tick(ev: TurnStart) -> None:
        if (
            ev.actor != me
            and ev.actor in enemies(c.world, me)
            and c.in_my_aura(ev.actor, label=c.ref)
        ):
            c.slowed(until=When.SONT, on=ev.actor)

    c.watch(TurnStart, tick, until=When.ENCOUNTER, on=me, label=f"{c.ref} aura")


@power(
    "m5417a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d8", 8),
)
def m5417a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5417a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=13),
    damage=Damage("2d6", 10, dtype=DamageType.PSYCHIC),
)
def m5417a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.pull(3)


@power(
    "m5417a3",
    level=9,
    usage=Usage.RECHARGE,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.CHARM, Keyword.CLOSE],
    attack=Attack(vs=WILL, printed=13),
)
def m5417a3(c: Cast) -> None:
    if c.first:
        _rearms_when_bloodied(c)
    victim = _restricted_to(c, 2, lambda f: c.is_(Condition.SLOWED, on=f))
    if victim is None or not c.strike(on=victim):
        return
    c.condition(Condition.DOMINATED, until=When.EONT, on=victim)


# ==========================================================================
# m5555
# ==========================================================================


@power(
    "m5555a0",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5555a0(c: Cast) -> None:
    _charge_aura(c, 3)


@power(
    "m5555a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d4", 10),
)
def m5555a1(c: Cast) -> None:
    _slide_strike(c)


@power(
    "m5555a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=12),
    damage=Damage("1d6", 4, dtype=DamageType.PSYCHIC),
)
def m5555a2(c: Cast) -> None:
    _charm_charge(c)


@power(
    "m5555a3",
    level=9,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.LIGHTNING, Keyword.RANGED],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("2d10", 5, dtype=DamageType.LIGHTNING, kind=LIMITED),
)
def m5555a3(c: Cast) -> None:
    _lightning_bolt(c)


@power(
    "m5555a4",
    level=9,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("1d6", 4),
    trigger="an enemy adjacent to it deals damage to it",
    on=Trigger(DamageApplied, _adjacent_damages_me, "an enemy adjacent to it deals damage to it"),
)
def m5555a4(c: Cast) -> None:
    _punish_adjacent_attacker(c)


# ==========================================================================
# m5626
# ==========================================================================


@power(
    "m5626a0",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5626a0(c: Cast) -> None:
    c.cannot_be_flanked(on=c.me, until=When.ENCOUNTER)


@power(
    "m5626a1",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m5626a1(c: Cast) -> None:
    """ "An enemy cannot enter the m5626's space by any means" restates
    the base movement rule every destination square is already checked
    against (`c.world.grid.occupant(sq) is None`, used throughout this
    tree's own forced-movement and pathing helpers). Nothing is added."""
    c.note(f"{c.ref}: its space cannot be entered")


@power(
    "m5626a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d8", 8),
)
def m5626a2(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.hit()
        if victim is not None and c.may("slide the target 1 square", who=c.me):
            c.slide(1, on=victim)


@power(
    "m5626a3",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.FORCE, Keyword.CLOSE],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("2d8", 4, dtype=DamageType.FORCE),
)
def m5626a3(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.hit()
        c.slide(3)
    elif victim is not None and c.may("slide the target 1 square", who=c.me):
        c.slide(1, on=victim)


@power(
    "m5626a4",
    level=9,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(1, 5),
    target=EACH_ENEMY,
    keywords=[Keyword.FORCE, Keyword.AREA],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("2d8", 8, dtype=DamageType.FORCE, kind=LIMITED, half_on_miss=True),
)
def m5626a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS, ongoing=(5, DamageType.FORCE))
    else:
        c.hit(half=True)
        c.ongoing(5, DamageType.FORCE)


@power(
    "m5626a5",
    level=9,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=CloseBurst(10),
    target=NO_TARGET,
    keywords=[Keyword.CLOSE],
    attack=Attack(vs=REF, printed=12),
    trigger="an enemy within 10 squares pushes, pulls, or slides it",
    on=Trigger(
        ForcedMove, _shoved_me_within(10), "an enemy within 10 squares pushes, pulls, or slides it"
    ),
)
def m5626a5(c: Cast) -> None:
    ev = c.trigger
    foe = getattr(ev, "source", None)
    squares_ = getattr(ev, "squares", 0)
    c.cancel()
    if foe is None or not c.strike(on=foe):
        return
    c.slide(squares_, on=foe)


@power(
    "m5626a6",
    level=9,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it drops to 0 hit points",
    on=Trigger(Dropped, about_me, "it drops to 0 hit points"),
    todo=("etl.monster.summon_ref()",),
)
def m5626a6(c: Cast) -> None:
    """The printed Effect is entirely "either two [kind] or two [other
    kind] appear" -- a choice between two monster kinds this brief gives
    no ref for. The destruction itself is already what `Dropped` is;
    nothing else here is written without one."""
    return


# ==========================================================================
# m5655
# ==========================================================================


@power(
    "m5655a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d8", 8),
)
def m5655a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5655a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.NECROTIC, Keyword.RANGED],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("3d8", 5, dtype=DamageType.NECROTIC),
)
def m5655a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.EONT)


@power(
    "m5655a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5655a2(c: Cast) -> None:
    pool = [a for a in c.allies() if c.is_kind("animate", on=a) and c.can_see(to=a)]
    if not pool:
        return
    ally = c.choose(pool, f"{c.ref}: which animate attacks") or pool[0]
    # `who=` is the attacker; the victim still defaults to `c.target`,
    # which is `None` on this `NO_TARGET` row and would make the attack
    # not happen at all. Named explicitly.
    foe = next((f for f in c.enemies() if c.adjacent_to(ally, f)), None)
    if foe is None:
        ranked = sorted(c.enemies(), key=lambda f: c.distance(to=f))
        foe = ranked[0] if ranked else None
    if foe is not None:
        c.basic(who=ally, on=foe)


@power(
    "m5655a3",
    level=9,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(1, 5),
    target=EACH_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.NECROTIC, Keyword.AREA],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("2d10", 4, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m5655a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS, ongoing=(5, DamageType.NECROTIC))


@power(
    "m5655a4",
    level=9,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING, Keyword.NECROTIC],
    trigger="an enemy within 5 squares of it regains hit points",
    on=Trigger(
        Healed,
        lambda w, me, ev: ev.target in enemies(w, me) and distance_between(w, me, ev.target) <= 5,
        "an enemy within 5 squares of it regains hit points",
    ),
)
def m5655a4(c: Cast) -> None:
    foe = getattr(c.trigger, "target", None)
    if foe is None:
        return
    c.flat(c.roll("3d8") + 12, dtype=DamageType.NECROTIC, on=foe)
    c.heal(24, on=c.me)


# ==========================================================================
# m5719
# ==========================================================================


@power(
    "m5719a0",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.second_initiative()", "c.extra_reaction()"),
)
def m5719a0(c: Cast) -> None:
    """ "Makes two initiative checks and takes a full turn on each" wants
    a second, independent initiative roll -- `docs/AUTHORING.md` names
    this exact gap as `c.second_initiative()`. "Can take two immediate
    actions per round but only one between one turn and the next" is a
    second, separate budget nothing tracks either."""
    return


@power(
    "m5719a1",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5719a1(c: Cast) -> None:
    """ "Automatically ends any dazing, stunning, or charm effect on
    himself" at the end of each turn -- charm is a keyword, not a
    condition, and its printed shapes in this game always land as
    `DOMINATED`, which is what is cured alongside the two named
    conditions."""
    me = c.me

    def tick(ev: TurnEnd) -> None:
        if ev.actor == me and not ev.ghost:
            c.cure(Condition.DAZED, Condition.STUNNED, Condition.DOMINATED, on=me)

    c.watch(TurnEnd, tick, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m5719a2",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC, Keyword.PSYCHIC],
)
def m5719a2(c: Cast) -> None:
    me = c.me

    def rider(ev: Hit) -> None:
        if ev.target != me:
            return
        vs = getattr(ev, "vs", None)
        if vs == FORT:
            c.flat(c.roll("2d10"), dtype=DamageType.NECROTIC, on=ev.attacker)
        elif vs == WILL:
            c.flat(c.roll("2d10"), dtype=DamageType.PSYCHIC, on=ev.attacker)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m5719a3",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d8", 9),
)
def m5719a3(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5719a4",
    level=9,
    usage=Usage.RECHARGE,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR, Keyword.NECROTIC, Keyword.CLOSE],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("3d12", 0, dtype=DamageType.NECROTIC),
)
def m5719a4(c: Cast) -> None:
    if c.first:
        _hands_the_use_back(c, PowerUsed, lambda ev: ev.actor == c.me and ev.power == "m5719a5")
    if c.strike():
        c.hit()
    c.push(3)


@power(
    "m5719a5",
    level=9,
    usage=Usage.RECHARGE,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.IMPLEMENT, Keyword.PSYCHIC, Keyword.AREA],
    attack=Attack(vs=WILL, printed=12),
    damage=Damage("1d8", 7, dtype=DamageType.PSYCHIC, half_on_miss=True),
    dropped=("c.forbid(usage=)",),
)
def m5719a5(c: Cast) -> None:
    if c.first:
        _hands_the_use_back(c, PowerUsed, lambda ev: ev.actor == c.me and ev.power == "m5719a4")
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)


@power(
    "m5719a6",
    level=9,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.NECROTIC, Keyword.PSYCHIC, Keyword.TELEPORTATION],
)
def m5719a6(c: Cast) -> None:
    was = c.here
    left_adjacent = c.in_squares(spread({was}, 1) - {was}, side="enemy")
    c.teleport(5, who=c.me)
    for foe in left_adjacent:
        c.ongoing(10, DamageType.NECROTIC, dtypes=(DamageType.PSYCHIC,), on=foe)


# ==========================================================================
# m5721
# ==========================================================================


@power(
    "m5721a0",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5721a0(c: Cast) -> None:
    zone = c.my_aura(label=c.ref)
    zc = c.world.get(zone, Zone)
    if zc is not None:
        zc.aura = 2
    me = c.me

    def healed(ev: Healed) -> None:
        if ev.target in enemies(c.world, me) and c.in_my_aura(ev.target, label=c.ref):
            c.immobilized(until=When.EONT, on=ev.target)

    c.watch(Healed, healed, until=When.ENCOUNTER, on=me, label=f"{c.ref} aura")


@power(
    "m5721a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("3d6", 5, dtype=DamageType.NECROTIC),
)
def m5721a1(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.hit()
        if victim is not None and c.may("slide the target 1 square", who=c.me):
            c.slide(1, on=victim)


@power(
    "m5721a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.RANGED],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("2d8", 4, dtype=DamageType.NECROTIC),
)
def m5721a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.SLOWED, until=When.SAVE_ENDS, ongoing=(5, DamageType.NECROTIC))
    else:
        c.slowed(until=When.EONT)


@power(
    "m5721a3",
    level=9,
    usage=Usage.RECHARGE,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC, Keyword.CLOSE],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("3d8", 5, dtype=DamageType.NECROTIC),
)
def m5721a3(c: Cast) -> None:
    if c.first:
        _hands_the_use_back(
            c,
            SavingThrow,
            lambda ev: (
                not ev.saved
                and ev.against == "death"
                and ev.actor in enemies(c.world, c.me)
                and distance_between(c.world, c.me, ev.actor) <= 10
            ),
        )
        for ally in c.in_squares(c.area(), side="ally"):
            if c.may("slide 3 squares", who=ally):
                c.slide(3, on=ally)
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)


@power(
    "m5721a4",
    level=9,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m5721a4(c: Cast) -> None:
    c.teleport(3, who=c.me)
    c.insubstantial(on=c.me, until=When.SONT)


# ==========================================================================
# m5779
# ==========================================================================


@power(
    "m5779a0",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("etl.monster.trigger_text()",),
)
def m5779a0(c: Cast) -> None:
    """The printed condition is "adjacent to a creature that has
    m5779a0" -- its own ref, named as something another creature
    possesses. No reading of that survived extraction with confidence;
    the same shape as `m3617a3`."""
    return


@power(
    "m5779a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD, Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d4", 12, dtype=DamageType.COLD),
)
def m5779a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.EONT)


@power(
    "m5779a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.COLD, Keyword.IMPLEMENT, Keyword.CLOSE],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("2d6", 6, dtype=DamageType.COLD),
)
def m5779a2(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.hit()
        if victim is not None and c.may("slide the target 1 square", who=c.me):
            c.slide(1, on=victim)


@power(
    "m5779a3",
    level=9,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=NO_TARGET,
    keywords=[Keyword.ZONE, Keyword.AREA],
)
def m5779a3(c: Cast) -> None:
    area = frozenset(c.area())
    c.zone(area, until=When.SUSTAIN, sustain=MINOR, label=c.ref)

    def tick(ev: TurnEnd) -> None:
        if ev.actor in c.in_squares(area, side="any"):
            c.penalty("attack", 2, on=ev.actor, until=When.EONT)
            c.slowed(until=When.EONT, on=ev.actor)

    c.watch(TurnEnd, tick, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} zone")


@power(
    "m5779a4",
    level=9,
    usage=AT_WILL,
    once_per_round=True,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=12),
)
def m5779a4(c: Cast) -> None:
    victim = _restricted_to(c, 5, lambda f: c.is_(Condition.SLOWED, on=f))
    if victim is None or not c.strike(on=victim):
        return
    c.immobilized(until=When.EONT, on=victim)


# ==========================================================================
# m5941
# ==========================================================================


@power(
    "m5941a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.MELEE],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("3d6", 6, dtype=DamageType.PSYCHIC),
)
def m5941a0(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.hit()
        if victim is not None:
            c.slide(2, on=victim)


@power(
    "m5941a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.PSYCHIC, Keyword.MELEE],
    attack=Attack(vs=WILL, printed=12),
    dropped=("c.leash()",),
)
def m5941a1(c: Cast) -> None:
    """Cannot-attack-me and the ongoing burn are written; "cannot
    willingly end its turn farther away than where it started" has no
    primitive -- see the module docstring."""
    if not c.strike():
        return
    victim = c.target
    if victim is None:
        return
    c.ongoing(10, DamageType.FIRE, dtypes=(DamageType.PSYCHIC,), on=victim, until=When.SAVE_ENDS)
    hold = c.cannot_attack(on=victim, against=c.me, until=When.ENCOUNTER)
    if hold is None:
        return
    me = c.me

    def ends_on_attack(ev: Hit) -> None:
        if not hold.ended and ev.attacker == me and ev.target != victim:
            c.world.effects.end(hold, "it used the power against a different creature")

    hold.subs.append(c.world.bus.on(Hit, ends_on_attack, owner=me))


@power(
    "m5941a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=12),
)
def m5941a2(c: Cast) -> None:
    if c.strike():
        c.condition(Condition.DOMINATED, until=When.EONT)


@power(
    "m5941a3",
    level=9,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
    out_of_combat=True,
)
def m5941a3(c: Cast) -> None:
    c.note(f"{c.ref}: alters her form to appear as a Medium humanoid")


@power(
    "m5941a4",
    level=9,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=Ranged(5),
    target=NO_TARGET,
    keywords=[Keyword.CHARM, Keyword.TELEPORTATION],
    trigger=(
        "a melee or ranged attack targets it within 5 squares of a creature affected by m5941a1"
    ),
    on=Trigger(
        AttackDeclared,
        lambda w, me, ev: ev.target == me,
        "a melee or ranged attack targets it within 5 squares of a creature affected by m5941a1",
    ),
)
def m5941a4(c: Cast) -> None:
    victim = next(
        (
            v
            for v in _bearing(c.world, c.me, "m5941a1 cannot attack")
            if distance_between(c.world, c.me, v) <= 5
        ),
        None,
    )
    if victim is None:
        return
    c.swap(victim, who=c.me)
    c.redirect(to=victim)


# ==========================================================================
# m5948
# ==========================================================================


@power(
    "m5948a0",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m5948a0(c: Cast) -> None:
    """Crumbling to dust and reappearing in 1d10 days beside a phylactery
    is an epilogue past the end of any one encounter -- nothing a fight
    resolves."""
    c.note(f"{c.ref}: her body crumbles and later reforms near her phylactery")


@power(
    "m5948a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING, Keyword.NECROTIC, Keyword.MELEE],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("2d6", 5, dtype=DamageType.NECROTIC),
)
def m5948a1(c: Cast) -> None:
    if c.strike():
        dealt = c.hit()
        c.heal(dealt, on=c.me)


@power(
    "m5948a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(2),
    keywords=[Keyword.NECROTIC, Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("3d6", 6, dtype=DamageType.NECROTIC),
)
def m5948a2(c: Cast) -> None:
    victim = c.target
    if not c.strike():
        c.slowed(until=When.SAVE_ENDS)
        return
    c.damage("3d6", 6, dtype=DamageType.NECROTIC, dtypes=(DamageType.PSYCHIC,))

    def worse(eff: Effect) -> None:
        if victim is not None:
            c.slide(2, on=victim)

    c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS, on=victim, escalate=worse)


@power(
    "m5948a3",
    level=9,
    usage=Usage.RECHARGE,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.FIRE, Keyword.NECROTIC, Keyword.AREA],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("2d10", 8, dtype=DamageType.FIRE, half_on_miss=True),
    dropped=("Damage(dtypes=)",),
)
def m5948a3(c: Cast) -> None:
    """"Fire and necrotic damage" rolled once -- `Damage` keeps the first
    type in the header, which is what a rescale reads; the second type is
    carried as a keyword and is `dropped=` for the damage call itself."""
    if c.first:
        _rearms_when_bloodied(c)
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)


@power(
    "m5948a4",
    level=9,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m5948a4(c: Cast) -> None:
    c.teleport(5, who=c.me)


@power(
    "m5948a5",
    level=9,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    dropped=("c.forbid(usage=)",),
)
def m5948a5(c: Cast) -> None:
    """Insubstantial and phasing are written; "cannot take standard
    actions" has no action-category ban, the same gap `m5719a5` waits on
    -- reused rather than re-coined, since it is the identical missing
    capability."""
    me = c.me
    phase = c.phasing(on=me, until=When.ENCOUNTER)
    c.insubstantial(on=me, until=When.ENCOUNTER)
    if phase is not None:
        c.endable(phase, cost=FREE)


@power(
    "m5948a6",
    level=9,
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
)
def m5948a6(c: Cast) -> None:
    pool = []
    for eid in creatures(c.world):
        if eid == c.me:
            continue
        health = c.world.get(eid, Health)
        if health is None or health.hp > 0:
            continue
        if team(c.world, eid) != team(c.world, c.me):
            continue
        if c.is_minion(on=eid) or c.distance(to=eid) > 10:
            continue
        pool.append(eid)
    if not pool:
        return
    ally = c.choose(pool, f"{c.ref}: who gets raised") or pool[0]
    health = c.world.get(ally, Health)
    amount = max(1, health.max_hp // 4) if health is not None else 1
    if c.reanimate(on=ally, hp=amount, until=When.ENCOUNTER):
        c.resist(10, DamageType.NECROTIC, on=ally, until=When.ENCOUNTER)
        c.vulnerable(5, DamageType.RADIANT, on=ally, until=When.ENCOUNTER)


# ==========================================================================
# m5961
# ==========================================================================


@power(
    "m5961a0",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PSYCHIC],
)
def m5961a0(c: Cast) -> None:
    zone = c.my_aura(label=c.ref)
    zc = c.world.get(zone, Zone)
    if zc is not None:
        zc.aura = 3
    me = c.me
    holds: dict[int, Effect] = {}

    def entered(ev: ZoneEntered) -> None:
        if ev.zone == zone and ev.actor not in holds:
            hold = c.ignore_resistance(dtype=DamageType.PSYCHIC, on=ev.actor, until=When.ENCOUNTER)
            if hold is not None:
                holds[ev.actor] = hold

    def exited(ev: ZoneExited) -> None:
        hold = holds.pop(ev.actor, None)
        if hold is not None and not hold.ended:
            c.world.effects.end(hold, "left the aura")

    def tick(ev: TurnEnd) -> None:
        if ev.actor != me and c.in_my_aura(ev.actor, label=c.ref) and c.bloodied(on=me):
            c.flat(5, dtype=DamageType.PSYCHIC, on=ev.actor)

    c.watch(ZoneEntered, entered, until=When.ENCOUNTER, on=me, label=f"{c.ref} enter")
    c.watch(ZoneExited, exited, until=When.ENCOUNTER, on=me, label=f"{c.ref} exit")
    c.watch(TurnEnd, tick, until=When.ENCOUNTER, on=me, label=f"{c.ref} tick")


@power(
    "m5961a1",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m5961a1(c: Cast) -> None:
    c.note(f"{c.ref}: speaks telepathically to creatures within 20 squares")


@power(
    "m5961a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(3),
    target=ONE_CREATURE,
    keywords=[Keyword.TELEPORTATION, Keyword.MELEE],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d8", 8),
)
def m5961a2(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.hit()
        if victim is not None:
            c.teleport(2, who=victim)


@power(
    "m5961a3",
    level=9,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC, Keyword.CLOSE],
    attack=Attack(vs=WILL, printed=12),
    damage=Damage("2d8", 5, dtype=DamageType.PSYCHIC, kind=LIMITED, half_on_miss=True),
)
def m5961a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)
    else:
        c.hit(half=True)


@power(
    "m5961a4",
    level=9,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m5961a4(c: Cast) -> None:
    c.teleport(5, who=c.me)


@power(
    "m5961a5",
    level=9,
    usage=AT_WILL,
    once_per_round=True,
    action=MINOR,
    reach=Ranged(5),
    target=UpTo(2),
    keywords=[Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=12),
    damage=Damage("1d8", 3, dtype=DamageType.PSYCHIC),
)
def m5961a5(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.vulnerable(5, DamageType.PSYCHIC, until=When.EONT)


@power(
    "m5961a6",
    level=9,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="an enemy subjects it to forced movement",
    on=Trigger(ForcedMove, _shoved_me, "an enemy subjects it to forced movement"),
)
def m5961a6(c: Cast) -> None:
    ev = c.trigger
    foe = getattr(ev, "source", None)
    how = getattr(ev, "how", None)
    squares_ = getattr(ev, "squares", 0)
    c.cancel()
    if foe is None or how is None:
        return
    mover = {Forced.PUSH: c.push, Forced.PULL: c.pull, Forced.SLIDE: c.slide}.get(how)
    if mover is not None:
        mover(squares_, on=foe)


# ==========================================================================
# m6061
# ==========================================================================


@power(
    "m6061a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d4", 7),
)
def m6061a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6061a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.IMPLEMENT, Keyword.RANGED],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("2d8", 8, dtype=DamageType.FIRE),
)
def m6061a1(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.hit()
        if victim is not None and c.may("slide the target up to 3 squares", who=c.me):
            c.slide(3, on=victim)


@power(
    "m6061a2",
    level=9,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.FIRE, Keyword.IMPLEMENT, Keyword.ZONE, Keyword.AREA],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("4d6", 3, dtype=DamageType.FIRE, half_on_miss=True),
)
def m6061a2(c: Cast) -> None:
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)
    if not c.first:
        return
    zone = c.zone(c.area(), until=When.SUSTAIN, sustain=MINOR, label=c.ref)

    def tick(ev: TurnStart) -> None:
        zc = c.world.get(zone, Zone)
        if zc is not None and ev.actor in c.in_squares(zc.squares, side="enemy"):
            c.flat(5, dtype=DamageType.FIRE, on=ev.actor)

    c.watch(TurnStart, tick, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} zone")
    zc = c.world.get(zone, Zone)
    hold = zc.effect if zc is not None else None

    def grow() -> None:
        if c.roll("1d6") == 6 and zc is not None:
            zc.squares = frozenset(spread(zc.squares, 1))

    if hold is not None:
        c.on_sustain(hold, grow)


@power(
    "m6061a3",
    level=9,
    usage=ENCOUNTER,
    action=MOVE,
    reach=CloseBurst(1),
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION, Keyword.ZONE],
    dropped=("c.conceal_in()",),
)
def m6061a3(c: Cast) -> None:
    c.zone(c.area(), until=When.EONT, label=c.ref)
    c.teleport(8, who=c.me)


# ==========================================================================
# m6074
# ==========================================================================


@power(
    "m6074a0",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6074a0(c: Cast) -> None:
    _charge_aura(c, 3)


@power(
    "m6074a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d4", 10),
)
def m6074a1(c: Cast) -> None:
    _slide_strike(c)


@power(
    "m6074a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=12),
    damage=Damage("1d6", 4, dtype=DamageType.PSYCHIC),
)
def m6074a2(c: Cast) -> None:
    _charm_charge(c)


@power(
    "m6074a3",
    level=9,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.LIGHTNING, Keyword.RANGED],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("2d10", 5, dtype=DamageType.LIGHTNING, kind=LIMITED),
)
def m6074a3(c: Cast) -> None:
    _lightning_bolt(c)


@power(
    "m6074a4",
    level=9,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("1d6", 4),
    trigger="an enemy adjacent to it deals damage to it",
    on=Trigger(DamageApplied, _adjacent_damages_me, "an enemy adjacent to it deals damage to it"),
)
def m6074a4(c: Cast) -> None:
    _punish_adjacent_attacker(c)


# ==========================================================================
# m6092
# ==========================================================================


@power(
    "m6092a0",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6092a0(c: Cast) -> None:
    me = c.me
    grabbing = lambda ctx: bool(c.grabbing(of=me))  # noqa: E731
    for which in ALL_DEFENCES:
        c.bonus(which, 2, on=me, kind="power", until=When.ENCOUNTER, when=grabbing)


@power(
    "m6092a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("", 8, dtype=DamageType.POISON, kind=MINION),
)
def m6092a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.grab()


@power(
    "m6092a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.MELEE],
    attack=Attack(vs=FORT, printed=12),
    dropped=("c.remove_from_play()",),
)
def m6092a2(c: Cast) -> None:
    """Domination is written in full. "While dominated, the m6092 is
    removed from play [and reappears adjacent on the aftereffect]" has
    no primitive for taking a creature off the board and bringing it
    back -- see the module docstring."""
    victim = _restricted_to(
        c,
        1,
        lambda f: f in c.grabbing(of=c.me) and c.is_kind("humanoid", on=f),
    )
    if victim is None or not c.strike(on=victim):
        return
    c.condition(Condition.DOMINATED, until=When.SAVE_ENDS, on=victim)


# ==========================================================================
# m6095
# ==========================================================================


@power(
    "m6095a0",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PSYCHIC],
)
def m6095a0(c: Cast) -> None:
    zone = c.my_aura(label=c.ref)
    zc = c.world.get(zone, Zone)
    if zc is not None:
        zc.aura = 1
    me = c.me

    def rider(ev: DamageApplied) -> None:
        if ev.target != me or ev.dtype != DamageType.PSYCHIC:
            return
        for foe in enemies(c.world, me):
            if c.in_my_aura(foe, label=c.ref):
                c.flat(5, dtype=DamageType.PSYCHIC, on=foe)

    c.watch(DamageApplied, rider, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m6095a1",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6095a1(c: Cast) -> None:
    me = c.me

    def tick(ev: TurnStart) -> None:
        if ev.actor != me or ev.ghost:
            return
        for eff in list(c.world.effects.live.values()):
            if (
                eff.owner == me
                and not eff.ended
                and eff.when == When.SAVE_ENDS
                and (Condition.STUNNED in eff.conditions or Condition.DOMINATED in eff.conditions)
                and c.save(on=me)
            ):
                c.world.effects.end(eff, "saved against it")

    c.watch(TurnStart, tick, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m6095a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d10", 6, dtype=DamageType.POISON),
)
def m6095a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6095a3",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.LIGHTNING, Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("2d8", 8, dtype=DamageType.LIGHTNING),
    dropped=("Damage(dtypes=)",),
)
def m6095a3(c: Cast) -> None:
    """"Lightning and psychic damage" rolled once -- the second type is
    carried as a keyword, same shape as `m5948a3`."""
    if c.strike():
        c.hit()
        c.dazed(until=When.EOTNT)


@power(
    "m6095a4",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
)
def m6095a4(c: Cast) -> None:
    victim = c.target
    if victim is not None:
        c.use_power("m6095a3", on=victim)
        c.use_power("m6095a3", on=victim)


@power(
    "m6095a5",
    level=9,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.CHARM, Keyword.IMPLEMENT, Keyword.PSYCHIC, Keyword.AREA],
    attack=Attack(vs=WILL, printed=12),
    damage=Damage("3d6", 10, dtype=DamageType.PSYCHIC, kind=LIMITED, half_on_miss=True),
)
def m6095a5(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.hit()
        if victim is not None:
            _forced_basic_against_own_side(c, victim)
    else:
        c.hit(half=True)


@power(
    "m6095a6",
    level=9,
    usage=ENCOUNTER,
    action=MINOR,
    reach=AreaBurst(2, 10),
    target=NO_TARGET,
    keywords=[Keyword.PSYCHIC, Keyword.ZONE],
)
def m6095a6(c: Cast) -> None:
    area = frozenset(c.area())
    zone = c.zone(area, until=When.EONT, label=c.ref)

    def tick(ev: TurnEnd) -> None:
        if ev.actor in c.in_squares(area, side="enemy"):
            c.flat(5, dtype=DamageType.PSYCHIC, on=ev.actor)

    c.watch(TurnEnd, tick, until=When.EONT, on=c.me, label=f"{c.ref} zone")
    zc = c.world.get(zone, Zone)
    hold = zc.effect if zc is not None else None
    if hold is None:
        return

    def spawn() -> None:
        spots = [
            sq
            for sq in zc.squares
            if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None
        ]
        for sq in spots[:4]:
            c.summon("m6092", at=sq)

    hold.on_end.append(spawn)


@power(
    "m6095a7",
    level=9,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it drops below 1 hit point from an attack that does not deal psychic damage",
    on=Trigger(
        Dropped,
        lambda w, me, ev: ev.actor == me and _last_damage_not_psychic(w, me),
        "it drops below 1 hit point from an attack that does not deal psychic damage",
    ),
)
def m6095a7(c: Cast) -> None:
    spot = _free_squares_near(c, 1, 1)
    c.summon("m6092", at=(spot[0] if spot else None))


def _last_damage_not_psychic(world: World, me: int) -> bool:
    for logged in reversed(world.bus.log):
        if isinstance(logged, DamageApplied) and logged.target == me:
            return logged.dtype != DamageType.PSYCHIC
    return True


# ==========================================================================
# m6169
# ==========================================================================


@power(
    "m6169a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("3d6", 6),
)
def m6169a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6169a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.MELEE],
    attack=Attack(vs=WILL, printed=12),
)
def m6169a1(c: Cast) -> None:
    """ "Cannot attack m6169. Lasts until m6169 or an ally attacks the
    target, m6169 drops to 0 hit points, or m6169 uses this power
    again." The 24-hour kissing epilogue past the end of the encounter
    is out of scope, the way a `Level 11:` line is."""
    if not c.strike():
        return
    victim = c.target
    if victim is None:
        return
    label = f"{c.ref} cannot attack"
    for eff in list(c.world.effects.live.values()):
        if eff.owner != victim and eff.label == label and eff.source == c.me and not eff.ended:
            c.world.effects.end(eff, "m6169 can only hold one target at a time")
    hold = c.cannot_attack(on=victim, against=c.me, until=When.ENCOUNTER)
    if hold is None:
        return
    me = c.me

    def ends_on_attack(ev: Hit) -> None:
        if not hold.ended and ev.attacker in ({me} | set(c.allies())) and ev.target == victim:
            c.world.effects.end(hold, "m6169 or an ally attacked the target")

    hold.subs.append(c.world.bus.on(Hit, ends_on_attack, owner=me))


@power(
    "m6169a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=12),
)
def m6169a2(c: Cast) -> None:
    if c.strike():
        c.condition(Condition.DOMINATED, until=When.EONT)


@power(
    "m6169a3",
    level=9,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
    out_of_combat=True,
)
def m6169a3(c: Cast) -> None:
    c.note(f"{c.ref}: alters its form to appear as a Medium humanoid")


@power(
    "m6169a4",
    level=9,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.CHARM],
    trigger=(
        "a melee or ranged attack targets it while adjacent to a creature affected by m6169a1"
    ),
    on=Trigger(
        AttackDeclared,
        lambda w, me, ev: ev.target == me,
        "a melee or ranged attack targets it while adjacent to a creature affected by m6169a1",
    ),
)
def m6169a4(c: Cast) -> None:
    held = next(
        (v for v in _bearing(c.world, c.me, "m6169a1 cannot attack") if c.adjacent(to=v)),
        None,
    )
    if held is not None:
        c.redirect(to=held)


# ==========================================================================
# m6409
# ==========================================================================


@power(
    "m6409a0",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6409a0(c: Cast) -> None:
    zone = c.my_aura(label=c.ref)
    zc = c.world.get(zone, Zone)
    if zc is not None:
        zc.aura = 2
    me = c.me

    def rider(ev: SavingThrow) -> None:
        if ev.actor in enemies(c.world, me) and c.in_my_aura(ev.actor, label=c.ref):
            ev.bonus -= 4

    c.watch(SavingThrow, rider, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m6409a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.NECROTIC, Keyword.MELEE],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d6", 4),
)
def m6409a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.FIRE, dtypes=(DamageType.NECROTIC,))
    c.slide(2)


@power(
    "m6409a2",
    level=9,
    usage=Usage.RECHARGE,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.MELEE],
    attack=Attack(vs=WILL, printed=12),
)
def m6409a2(c: Cast) -> None:
    if not c.strike():
        return
    victim = c.target
    if victim is None:
        return
    hold = c.cannot_attack(on=victim, against=c.me, until=When.ENCOUNTER)
    if hold is None:
        return
    me = c.me
    known = c.world.get(me, Powers)

    def give_back() -> None:
        if known is not None:
            known.restore(c.ref)

    hold.on_end.append(give_back)

    def ends_on_attack(ev: Hit) -> None:
        if not hold.ended and ev.attacker in ({me} | set(c.allies())) and ev.target == victim:
            c.world.effects.end(hold, "m6409 or an ally attacked the target")

    hold.subs.append(c.world.bus.on(Hit, ends_on_attack, owner=me))


@power(
    "m6409a3",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.PSYCHIC, Keyword.CLOSE],
    attack=Attack(vs=WILL, printed=12),
)
def m6409a3(c: Cast) -> None:
    victim = _restricted_to(c, 10, lambda f: not c.is_(Condition.DEAFENED, on=f))
    if victim is None or not c.strike(on=victim):
        return
    choice = c.choose(
        ["dominated", "psychic damage and prone"], f"{c.ref}: what the target chooses"
    )
    if choice == "dominated":
        c.condition(Condition.DOMINATED, until=When.EONT, on=victim)
    else:
        c.damage("2d10", 10, dtype=DamageType.PSYCHIC, on=victim)
        c.prone(on=victim)


@power(
    "m6409a4",
    level=9,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m6409a4(c: Cast) -> None:
    c.teleport(5, who=c.me)
    foe = next((f for f in c.enemies() if c.adjacent(to=f)), None)
    if foe is not None:
        c.use_power("m6409a1", on=foe)


@power(
    "m6409a5",
    level=9,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
    out_of_combat=True,
)
def m6409a5(c: Cast) -> None:
    c.note(f"{c.ref}: alters her form to appear as a Medium humanoid")


@power(
    "m6409a6",
    level=9,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.CHARM],
    trigger=(
        "a melee or ranged attack targets it while adjacent to a creature dominated by it "
        "or affected by m6409a2"
    ),
    on=Trigger(
        AttackDeclared,
        lambda w, me, ev: ev.target == me,
        (
            "a melee or ranged attack targets it while adjacent to a creature dominated by "
            "it or affected by m6409a2"
        ),
    ),
)
def m6409a6(c: Cast) -> None:
    dominated = {
        eff.owner
        for eff in c.world.effects.live.values()
        if eff.source == c.me and not eff.ended and Condition.DOMINATED in eff.conditions
    }
    held = set(_bearing(c.world, c.me, "m6409a2 cannot attack"))
    pool = [v for v in dominated | held if c.adjacent(to=v)]
    if pool:
        c.redirect(to=pool[0])


# ==========================================================================
# m6477
# ==========================================================================


@power(
    "m6477a0",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6477a0(c: Cast) -> None:
    me = c.me

    def rider(ev: DamageRolled) -> None:
        if ev.target != me or ev.dtype in (DamageType.FORCE, DamageType.RADIANT):
            return
        c.halve(ev)

    c.watch(DamageRolled, rider, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m6477a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR, Keyword.NECROTIC, Keyword.MELEE],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("2d8", 7, dtype=DamageType.NECROTIC),
)
def m6477a1(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.hit()
        if victim is not None:
            c.slide(2, on=victim)


@power(
    "m6477a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR, Keyword.NECROTIC, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=12),
    damage=Damage("2d8", 7, dtype=DamageType.NECROTIC),
)
def m6477a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.grants_advantage(until=When.EONT)


@power(
    "m6477a3",
    level=9,
    usage=Usage.RECHARGE,
    action=STANDARD,
    reach=CloseBurst(5),
    target=Target(side="ally", count=2),
)
def m6477a3(c: Cast) -> None:
    ally = c.target
    if ally is None or not c.may("shift up to 5 squares and make a basic attack", who=ally):
        return
    c.shift(5, who=ally)
    # `who=` is the attacker; the victim still defaults to `c.target`,
    # which is the ally itself here. Named explicitly, off where the
    # shift actually landed.
    foe = next((f for f in c.enemies() if c.adjacent_to(ally, f)), None)
    if foe is None:
        ranked = sorted(c.enemies(), key=lambda f: c.distance(to=f))
        foe = ranked[0] if ranked else None
    if foe is not None:
        c.basic(who=ally, on=foe)


@power(
    "m6477a4",
    level=9,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR, Keyword.PSYCHIC, Keyword.CLOSE],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("3d6", 7, dtype=DamageType.PSYCHIC),
)
def m6477a4(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.hit()
        if victim is not None:
            c.flee(c.speed_of(victim), on=victim)


# ==========================================================================
# m6484
# ==========================================================================


@power(
    "m6484a0",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6484a0(c: Cast) -> None:
    me = c.me
    while_not_bloodied = lambda ctx: not c.bloodied(on=me)  # noqa: E731
    for which in ALL_DEFENCES:
        c.bonus(which, 2, on=me, until=When.ENCOUNTER, when=while_not_bloodied)


@power(
    "m6484a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=14),
)
def m6484a1(c: Cast) -> None:
    victim = c.target
    if c.strike() and victim is not None:
        c.immobilized(until=When.EOTNT, on=victim)


@power(
    "m6484a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.RADIANT, Keyword.RANGED],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("3d6", 7, dtype=DamageType.RADIANT),
)
def m6484a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6484a3",
    level=9,
    usage=Usage.RECHARGE,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.MELEE],
    attack=Attack(vs=WILL, printed=12),
    dropped=("c.leash()",),
)
def m6484a3(c: Cast) -> None:
    """Cannot-attack is written; "must use a move action to move as
    close to it as possible, each turn" is the same missing leash
    `m5941a1` waits on."""
    if not c.strike():
        return
    victim = c.target
    if victim is None:
        return
    hold = c.cannot_attack(on=victim, against=c.me, until=When.ENCOUNTER)
    if hold is None:
        return
    me = c.me
    known = c.world.get(me, Powers)

    def give_back() -> None:
        if known is not None:
            known.restore(c.ref)

    hold.on_end.append(give_back)

    def ends_on_attack(ev: Hit) -> None:
        if not hold.ended and ev.attacker in ({me} | set(c.allies())) and ev.target == victim:
            c.world.effects.end(hold, "m6484 or an ally attacked the target")

    hold.subs.append(c.world.bus.on(Hit, ends_on_attack, owner=me))


@power(
    "m6484a4",
    level=9,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
    out_of_combat=True,
)
def m6484a4(c: Cast) -> None:
    c.note(f"{c.ref}: alters its form to appear as a Medium humanoid")


@power(
    "m6484a5",
    level=9,
    usage=ENCOUNTER,
    action=MINOR,
    reach=Melee(1),
    target=Target(side="ally", count=1),
)
def m6484a5(c: Cast) -> None:
    ally = c.target
    if ally is None:
        return
    c.temp_hp(10, on=ally)
    candidates = [
        e
        for e in c.world.effects.live.values()
        if e.owner == ally and not e.ended and e.when == When.SAVE_ENDS
    ]
    if candidates:
        which = c.choose(candidates, f"{c.ref}: which effect to end") or candidates[0]
        c.end_effect(which, on=ally)


# ==========================================================================
# m6486
# ==========================================================================


@power(
    "m6486a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d10", 10),
)
def m6486a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6486a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.MELEE],
    attack=Attack(vs=WILL, printed=13),
)
def m6486a1(c: Cast) -> None:
    """ "Cannot attack m6486 or a creature within 5 squares she
    designates" -- the designated creature is optional; when offered,
    the hold is laid twice, once per protected creature."""
    if not c.strike():
        return
    victim = c.target
    if victim is None:
        return
    designee = c.choose(
        [c.me] + [a for a in c.allies() if a != c.me and c.distance(to=a) <= 5],
        f"{c.ref}: who the target cannot attack",
        optional=True,
    )
    me = c.me
    holds = [c.cannot_attack(on=victim, against=me, until=When.ENCOUNTER)]
    if designee is not None and designee != me:
        holds.append(c.cannot_attack(on=victim, against=designee, until=When.ENCOUNTER))
    for hold in holds:
        if hold is None:
            continue

        def ends_on_attack(ev: Hit, hold: Effect = hold) -> None:
            if not hold.ended and ev.attacker in ({me} | set(c.allies())) and ev.target == victim:
                c.world.effects.end(hold, "m6486 or an ally attacked the target")

        hold.subs.append(c.world.bus.on(Hit, ends_on_attack, owner=me))


@power(
    "m6486a2",
    level=9,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=13),
)
def m6486a2(c: Cast) -> None:
    if c.strike():
        c.condition(Condition.DOMINATED, until=When.SAVE_ENDS)


@power(
    "m6486a3",
    level=9,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
    out_of_combat=True,
)
def m6486a3(c: Cast) -> None:
    c.note(f"{c.ref}: alters its form to appear as a Medium humanoid")


# ==========================================================================
# m6543
# ==========================================================================


@power(
    "m6543a0",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m6543a0(c: Cast) -> None:
    """Passing itself off as an ordinary tree against a DC 25 Insight
    check, while it doesn't move, is the whole printed Effect -- no
    other clause here is a fight, so the row is inert outright rather
    than `narrative=` beside a combat half that doesn't exist."""
    c.note(f"{c.ref}: passes itself off as an ordinary tree while it does not move")


@power(
    "m6543a1",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6543a1(c: Cast) -> None:
    me = c.me

    def rider(ev: DamageApplied) -> None:
        if ev.target == me and ev.dtype == DamageType.FIRE:
            c.ongoing(5, DamageType.FIRE, on=me)

    c.watch(DamageApplied, rider, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m6543a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d6", 10),
)
def m6543a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(1)


@power(
    "m6543a3",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(20),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d6", 10),
)
def m6543a3(c: Cast) -> None:
    """Printed reach is `Melee 20`, beside `m6543a2`'s `Melee 2` for the
    same creature's claws -- kept as printed rather than guessed at;
    flagged in the report."""
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m6543a4",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6543a4(c: Cast) -> None:
    """Animates a living tree with its own statistics -- summoned as
    another copy of itself, the same reading the board's own fixture
    note uses for "a copy of the caster." Capped at two standing
    servants via the master/servant relation."""
    if len(c.servants()) >= 2:
        return
    spot = _free_squares_near(c, 10, 1)
    if not spot:
        return
    tree = c.summon("m6543", at=spot[0])
    c.bind(on=tree)
