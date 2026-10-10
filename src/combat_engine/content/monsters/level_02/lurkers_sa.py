"""Monster abilities, level 2, lurkers: the second sweep.

Fifteen stat blocks whose rows were still undeclared -- three of them elite,
and two of those are the same creature extracted twice under different refs, so
their rows are written twice and deliberately read the same.

The conventions are the ones the level 1 sweep settled, and three of them earn
their keep repeatedly here:

* a second attack line cannot live in the header, so its printed bonus goes
  through `world.scaling.trim` by hand -- what `Attack(printed=)` does with the
  first one;
* a row that answers its own Trigger declares `target=NO_TARGET` and aims at
  the creature the trigger names. Declaring `ONE_CREATURE` instead would let
  the engine pick somebody the card never mentions, and the body would still
  have to find the triggering enemy;
* a printed target restriction about what a creature is *suffering*, or about
  what the attacker is holding, is asked in the body: `Target` filters on side
  and size and nothing else. `label=` records it and the marker names the gap
  the line has -- `Target.relation` for "a creature it is grabbing".
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_01 import settle
from combat_engine.content.monsters.level_01.artillery_sa import (
    _any_enemy_suffering,
    _recharge_when_bloodied,
)
from combat_engine.content.monsters.level_01.skirmishers import _ref_of
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_OTHER,
    ENCOUNTER,
    FORT,
    FREE,
    INTERRUPT,
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
    Condition,
    Damage,
    DamageApplied,
    DamageType,
    Health,
    Keyword,
    Melee,
    MeleeOrRanged,
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
from combat_engine.engine.dsl import get as _row_for
from combat_engine.engine.events import (
    AttackDeclared,
    Bloodied,
    Dropped,
    Hit,
    Miss,
    PowerUsed,
    TurnEnd,
    TurnStart,
)
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import (
    Cover,
    alive,
    cover_between,
    distance_between,
    enemies,
    has_combat_advantage,
    team,
)
from combat_engine.engine.triggers import (
    Trigger,
    about_me,
    both,
    by_melee,
    by_power,
    by_ranged,
    enemy_within,
    targets_me,
)

# -- what the blocks in this file share -------------------------------------

#: Every reach that makes an attack a close or an area one.
_SPREADING = ("close_burst", "close_blast", "area_burst")


def _reach_kind(ref: str) -> str:
    """Which sort of reach a row has, looked up off the registry.

    `triggers.by_melee` makes the same lookup for the same reason: the kind of
    attack lives on the power and not on anything the event carries.
    """
    row = _row_for(ref or "")
    return row.reach_of(0).kind if row is not None else ""


def _holds_somebody(world: World, eid: int) -> bool:
    """"Grabbed target only", as a Requirement. `query` has no grab helper --
    `c.grabbing` is on `Cast`, which a gate has not got -- so the fighter's
    version is reused rather than rewritten."""
    from combat_engine.content.powers.fighter.holds import holds_somebody

    return holds_somebody(world, eid)


def _has_an_opening(world: World, eid: int) -> bool:
    """A printed "Requirement: combat advantage", asked of the board. A gate is
    handed the caster and no target, so the nearest thing it can say is that
    there is somebody this creature is getting the better of."""
    return any(has_combat_advantage(world, eid, foe) for foe in enemies(world, eid))


def _twice(c: Cast, ref: str) -> None:
    """"It makes two claw attacks." Two swings even against one creature.

    `UpTo(2)` lets the chooser spread them, and the second swing is added when
    it did not -- without that, a lone enemy was clawed once by a card that
    says twice.
    """
    c.use_power(ref, on=c.target)
    if c.last and len(c.targets) < 2:
        c.use_power(ref, on=c.target)


def _edge_damage(c: Cast) -> None:
    """"Deals 1d6 extra damage against a target it has combat advantage
    against." Held as a gated damage modifier, so it reads the advantage off
    the blow being dealt rather than asking the board afterwards."""
    c.bonus(
        "damage", 0, dice="1d6", on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: bool(ctx.get("advantage")),
    )


def _recharge_when_using(c: Cast, other: str) -> None:
    """Put this row back up when the creature uses the row its card names.

    The die stays in the header, because that is what `actions.recharge` rolls
    and what the card shows. Armed once: a second watch under the same label
    would hand back two uses for one trigger.
    """
    me, ref = c.me, c.ref
    label = f"{ref} recharge"
    if any(effect.label == label for effect in c.world.effects.of(me)):
        return

    def used(ev: PowerUsed) -> None:
        if ev.actor == me and ev.power == other:
            c.restore_use(ref, on=me)

    c.watch(PowerUsed, used, until=When.ENCOUNTER, on=me, label=label)


def _kin_within(c: Cast, radius: int, of: int) -> list[int]:
    mine = _ref_of(c, c.me)
    return [w for w in c.within(radius, of=of, side="team") if _ref_of(c, w) == mine]


def _triggering_enemy(c: Cast) -> int | None:
    """Whoever the event being answered is about. `PowerUsed.targets` is not
    this and is not a stand-in for it -- a `NO_TARGET` reaction has none."""
    ev = c.trigger
    if ev is None:
        return None
    who = getattr(ev, "attacker", None)
    return who if who is not None else getattr(ev, "actor", None)


# --------------------------------------------------------------------------
# m1430
# --------------------------------------------------------------------------


@power(
    "m1430a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 3),
)
def m1430a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.ACID)


@power(
    "m1430a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d4", 3),
)
def m1430a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1430a2",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
)
def m1430a2(c: Cast) -> None:
    """`c.use_power` runs the claw at this row's action cost, so the printed
    pair are the *same* attacks the creature makes on its own and every rider
    that reads one still fires."""
    _twice(c, "m1430a1")


@power(
    "m1430a3",
    level=2,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(2),
    target=NO_TARGET,
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 4),
    trigger="an enemy misses it with a melee attack",
    on=Trigger(Miss, both(targets_me, by_melee), "an enemy misses it with a melee attack"),
)
def m1430a3(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is not None and c.strike(on=foe):
        c.hit(on=foe)
        c.push(1, on=foe)


@power(
    "m1430a4",
    level=2,
    usage=Usage.RECHARGE,
    recharge=0,
    action=STANDARD,
    reach=CloseBlast(4),
    target=EACH_OTHER,
    keywords=[Keyword.ACID],
    attack=Attack(vs=REF, printed=6),
    damage=Damage("1d12", 3, dtype=DamageType.ACID, kind=LIMITED),
    recharge_when=Trigger(Bloodied, about_me,
        "when first bloodied"),
)
def m1430a4(c: Cast) -> None:
    """"Save ends both" is two holds here rather than one: `c.ongoing` carries a
    saving throw of its own and nothing attaches a defence penalty to somebody
    else's effect. Two saves instead of one is the only divergence."""
    _recharge_when_bloodied(c)
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.ACID)
        c.penalty(AC, 4, until=When.SAVE_ENDS)


# --------------------------------------------------------------------------
# m1432
# --------------------------------------------------------------------------


@power(
    "m1432a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d8", 4),
)
def m1432a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1432a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 4),
)
def m1432a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1432a2",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
)
def m1432a2(c: Cast) -> None:
    _twice(c, "m1432a1")


@power(
    "m1432a3",
    level=2,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Ranged(10),
    target=NO_TARGET,
    attack=Attack(vs=REF, printed=6),
    damage=Damage("1d6", 1),
    trigger="an enemy targets it with a ranged attack",
    on=Trigger(
        AttackDeclared,
        both(targets_me, by_ranged),
        "an enemy targets it with a ranged attack",
    ),
)
def m1432a3(c: Cast) -> None:
    """Declared on `AttackDeclared` and not on `Hit`, because the printed line
    is "targets" and not "hits" -- it answers the aim, whatever comes of it."""
    foe = _triggering_enemy(c)
    if foe is not None and c.strike(on=foe):
        c.hit(on=foe)
        c.blinded(until=When.EONT, on=foe)


@power(
    "m1432a4",
    level=2,
    usage=Usage.RECHARGE,
    recharge=0,
    action=STANDARD,
    reach=CloseBlast(4),
    target=EACH_OTHER,
    attack=Attack(vs=FORT, printed=6),
    damage=Damage("2d8", 2, kind=LIMITED),
    recharge_when=Trigger(Bloodied, about_me,
        "when first bloodied"),
)
def m1432a4(c: Cast) -> None:
    _recharge_when_bloodied(c)
    if c.strike():
        c.hit()
        c.blinded(until=When.SAVE_ENDS)


@power(
    "m1432a5",
    level=2,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POLYMORPH],
    damage=Damage("1d6", 4, kind=LIMITED),
)
def m1432a5(c: Cast) -> None:
    """A move through occupied squares that bites whatever it passes is
    `c.overrun`: `c.move` refuses an occupied square and reports nothing about
    what it went through, so the printed line could not be written at all. With
    no destination it takes the line that catches the most, which is the whole
    point of the row."""
    for caught in c.overrun():
        c.hit(on=caught)
        c.blinded(until=When.SAVE_ENDS, on=caught)


@power(
    "m1432a6",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1432a6(c: Cast) -> None:
    _edge_damage(c)


# --------------------------------------------------------------------------
# m1513
# --------------------------------------------------------------------------


def _is_adjacent(c: Cast, who: object) -> bool:
    return isinstance(who, int) and distance_between(c.world, c.me, who) <= 1


@power(
    "m1513a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d8", 3),
)
def m1513a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1513a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(vs=REF, printed=5),
    damage=Damage("2d4", 0, dtype=DamageType.ACID),
)
def m1513a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1513a2",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1513a2(c: Cast) -> None:
    """Total concealment, but only against the enemies the card names, so it is
    a gated `c.conceal` rather than `c.hide`: being hidden is a relation that
    attacking breaks, and this is a standing -5 that survives the swing.

    Asked again at the top of each of its own turns, because the condition the
    card sets is "starts its turn with cover" and cover is a fact about two
    positions, both of which move.
    """
    me = c.me

    def arm() -> None:
        covered = any(
            cover_between(c.world, foe, me) is not Cover.NONE for foe in c.enemies()
        )
        if covered:
            c.conceal(
                total=True, until=When.EONT, on=me,
                when=lambda ctx: not _is_adjacent(c, ctx.get("attacker")),
            )

    arm()

    def each_turn(ev: TurnStart) -> None:
        if ev.actor == me and not ev.ghost:
            arm()

    c.watch(TurnStart, each_turn, until=When.ENCOUNTER, on=me, label=f"{c.ref} unseen")


@power(
    "m1513a3",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1513a3(c: Cast) -> None:
    _edge_damage(c)


# --------------------------------------------------------------------------
# m1653
# --------------------------------------------------------------------------


@power(
    "m1653a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=3),
    damage=Damage("1d6", 0),
)
def m1653a0(c: Cast) -> None:
    """The secondary is a second roll against a different defence, so it cannot
    live in the header; its printed +2 is trimmed by hand the way
    `Attack.bonus_for` trims the header's."""
    if not c.strike():
        return
    c.hit()
    if c.attack(c.world.scaling.trim(2, c.level), FORT):
        c.slowed(until=When.SAVE_ENDS)


@power(
    "m1653a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=REF, printed=5),
    damage=Damage("1d6", 3, dtype=DamageType.PSYCHIC),
)
def m1653a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.DAZED, until=When.SAVE_ENDS)


@power(
    "m1653a2",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1653a2(c: Cast) -> None:
    """Gated on the distance to whoever is being swung at, read out of the
    attack's own context -- the set of creatures within 5 squares is not
    knowable when the trait arms."""
    c.bonus(
        "attack", 4, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: isinstance(ctx.get("target"), int)
        and distance_between(c.world, c.me, ctx["target"]) <= 5,
    )


@power(
    "m1653a3",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ILLUSION],
    todo=("c.invisible(when=)",),
)
def m1653a3(c: Cast) -> None:
    """The whole of this row is a condition on *who* cannot see it, and it has
    to be asked afresh every time somebody looks: `c.invisible` sets a relation
    against a named creature and takes no gate, so writing it bare would hide
    the creature from a daze that has already ended."""


def _targeted_by_hand(world: World, me: int, ev: Any) -> bool:
    return targets_me(world, me, ev) and (
        by_melee(world, me, ev) or by_ranged(world, me, ev)
    )


@power(
    "m1653a4",
    level=2,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=Melee(1),
    target=NO_TARGET,
    attack=Attack(vs=WILL, printed=4),
    trigger="it is targeted by a melee or a ranged attack",
    on=Trigger(
        AttackDeclared, _targeted_by_hand, "it is targeted by a melee or a ranged attack"
    ),
)
def m1653a4(c: Cast) -> None:
    """An interrupt, which is the only window that can move a blow: `c.redirect`
    rewrites the attack's target and the live result with it, so the damage
    lands on whoever was chosen rather than on the creature that was spared."""
    foe = _triggering_enemy(c)
    if foe is None or not c.strike(on=foe):
        return
    nearby = [w for w in c.within(1) if w != c.me]
    instead = c.choose(nearby, "who the attack hits instead") if nearby else None
    if instead is not None:
        c.redirect(to=instead)


# --------------------------------------------------------------------------
# m3441
# --------------------------------------------------------------------------


@power(
    "m3441a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=REF, printed=5),
    damage=Damage("1d6", 4, dtype=DamageType.PSYCHIC),
)
def m3441a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3441a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=REF, printed=5),
    damage=Damage("1d4", 3, dtype=DamageType.PSYCHIC),
)
def m3441a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3441a2",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3441a2(c: Cast) -> None:
    """"A target granting combat advantage to it" is the same question off the
    other end, and the blow's own context answers both the same way."""
    _edge_damage(c)


@power(
    "m3441a3",
    level=2,
    usage=Usage.RECHARGE,
    recharge=5,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.HEALING],
)
def m3441a3(c: Cast) -> None:
    """Insubstantial is dropped rather than suppressed -- it is a condition
    something granted, so the hold that carries it is ended and a second hold
    puts it back when the printed duration runs out."""
    me, ref = c.me, c.ref
    for effect in list(c.world.effects.of(me)):
        if Condition.INSUBSTANTIAL in effect.conditions:
            c.world.effects.end(effect, ref)
    solid = c.effect(f"{ref} solid", until=When.EONT, on=me)
    if solid is not None:
        solid.on_end.append(lambda: c.insubstantial(until=When.ENCOUNTER, on=me))

    def stung(ev: Hit) -> None:
        if ev.target != me or ev.attacker == me:
            return
        c.flat(5, dtype=DamageType.PSYCHIC, on=ev.attacker)
        for kin in _kin_within(c, 5, me):
            c.heal(5, on=kin)

    c.watch(Hit, stung, until=When.EONT, on=me, label=f"{ref} reprisal")


@power(
    "m3441a4",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=Target("any", 1, label="one helpless or unconscious creature"),
    keywords=[Keyword.HEALING],
    requires=_any_enemy_suffering(Condition.HELPLESS, Condition.UNCONSCIOUS),
    requires_text="something must be helpless or unconscious",
    dropped=("c.coup_de_grace(ref=)",),
)
def m3441a4(c: Cast) -> None:
    """The printed target restriction lives in the `Target` label and in the
    Requirement: `coup_de_grace` is the thing that enforces it, refusing outright
    for anything not actually helpless. "Regains all of its hit points" is
    whatever it is currently down, read off `c.missing`."""
    settle(c)
    if c.coup_de_grace() and not alive(c.world, c.target):
        c.heal(c.missing(on=c.me), on=c.me)


# --------------------------------------------------------------------------
# m3519
# --------------------------------------------------------------------------


@power(
    "m3519a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d8", 1),
    dropped=("c.restrict_action()", "c.aura_effect()"),
)
def m3519a0(c: Cast) -> None:
    """The hold and the two defences it buys are the playable half, and both are
    gated on still holding somebody rather than fixed when the row resolves.

    Two clauses have nowhere to go: "it can claw only the grabbed target"
    narrows what the creature may choose rather than barring one creature, and
    "that target takes 6 damage instead of 2 from the aura" edits a *different*
    block's aura from here.
    """
    if not c.strike():
        return
    c.hit()
    c.grab()
    for defence in (AC, REF):
        c.bonus(
            defence, 2, on=c.me, until=When.ENCOUNTER,
            when=lambda ctx: bool(c.grabbing()),
        )


# --------------------------------------------------------------------------
# m4299
# --------------------------------------------------------------------------


@power(
    "m4299a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 3),
)
def m4299a0(c: Cast) -> None:
    """"1d6 + 9 on a critical hit" is the ordinary critical and not a rider:
    `c.damage` maxes its dice, so 6 and the +3 come to exactly 9. Nothing to
    write."""
    if c.strike():
        c.hit()


@power(
    "m4299a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    keywords=[Keyword.WEAPON],
)
def m4299a1(c: Cast) -> None:
    _twice(c, "m4299a0")


@power(
    "m4299a2",
    level=2,
    usage=Usage.RECHARGE,
    recharge=5,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d10", 3, kind=LIMITED),
    trigger="it is hit by a melee attack",
    on=Trigger(Hit, both(targets_me, by_melee), "it is hit by a melee attack"),
)
def m4299a2(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is not None and c.strike(on=foe):
        c.hit(on=foe)
        c.condition(Condition.DAZED, until=When.SAVE_ENDS, on=foe)


@power(
    "m4299a3",
    level=2,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=Target(side="enemy", everyone=True),
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=5),
    damage=Damage("2d6", 3, kind=LIMITED),
)
def m4299a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.SLOWED, until=When.SAVE_ENDS)


# --------------------------------------------------------------------------
# m4388
# --------------------------------------------------------------------------


@power(
    "m4388a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 3),
)
def m4388a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4388a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    requires=_has_an_opening,
    requires_text="requires combat advantage",
)
def m4388a1(c: Cast) -> None:
    """Both swings are the creature's own claw, run at this row's cost, and the
    grab turns on both of them landing -- so each outcome is read off
    `c.landed` as it happens rather than counted afterwards."""
    foe = c.target
    if foe is None:
        return
    landed = 0
    for _ in range(2):
        c.use_power("m4388a0", on=foe)
        if c.landed:
            landed += 1
    if landed == 2:
        c.grab(on=foe)


@power(
    "m4388a2",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=Target(
        side="enemy",
        count=1,
        label="grabbed target only",
        relation=Relation.GRABBED_BY,
    ),
    attack=Attack(vs=FORT, printed=5),
    damage=Damage("2d6", 3),
)
def m4388a2(c: Cast) -> None:
    """The printed restriction is the target line. An empty pool already makes
    `_can_land` false, so the `requires=` gate that spelled the same refusal
    by hand came out with the body's re-check. #401."""
    if c.strike():
        c.hit()


@power(
    "m4388a3",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.on_grab_attack()",),
)
def m4388a3(c: Cast) -> None:
    """The whole of this row is a bonus to the roll that drags a held creature
    about, and nothing announces that roll for a modifier to find."""


# --------------------------------------------------------------------------
# m4506
# --------------------------------------------------------------------------


@power(
    "m4506a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d8", 4),
)
def m4506a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4506a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 4),
)
def m4506a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4506a2",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
)
def m4506a2(c: Cast) -> None:
    _twice(c, "m4506a1")


@power(
    "m4506a3",
    level=2,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Ranged(10),
    target=NO_TARGET,
    attack=Attack(vs=REF, printed=6),
    damage=Damage("1d6", 1),
    trigger="an enemy targets it with a ranged attack",
    on=Trigger(
        AttackDeclared,
        both(targets_me, by_ranged),
        "an enemy targets it with a ranged attack",
    ),
)
def m4506a3(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is not None and c.strike(on=foe):
        c.hit(on=foe)
        c.blinded(until=When.EONT, on=foe)


@power(
    "m4506a4",
    level=2,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(4),
    target=EACH_OTHER,
    attack=Attack(vs=FORT, printed=6),
    damage=Damage("2d8", 2, kind=LIMITED),
)
def m4506a4(c: Cast) -> None:
    """The card says encounter where the twin block of this creature says
    recharge, and this one is written as its own card prints it. The printed
    "recharges when first bloodied" is armed on top: `c.restore_use` hands back
    an encounter use as readily as a recharge one."""
    _recharge_when_bloodied(c)
    if c.strike():
        c.hit()
        c.blinded(until=When.SAVE_ENDS)


@power(
    "m4506a5",
    level=2,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POLYMORPH],
    damage=Damage("1d6", 4, kind=LIMITED),
)
def m4506a5(c: Cast) -> None:
    for caught in c.overrun():
        c.hit(on=caught)
        c.blinded(until=When.SAVE_ENDS, on=caught)


@power(
    "m4506a6",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4506a6(c: Cast) -> None:
    _edge_damage(c)


# --------------------------------------------------------------------------
# m5281
# --------------------------------------------------------------------------


def _melee_blow(ctx: dict[str, Any]) -> bool:
    return _reach_kind(str(ctx.get("power", ""))) == "melee"


@power(
    "m5281a0",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC],
)
def m5281a0(c: Cast) -> None:
    """An aura 1 for the board to draw, and the bite hung off `TurnEnd` -- the
    printed line is about *ending* a turn beside it."""
    me = c.me
    c.aura(1, until=When.ENCOUNTER)

    def lingered(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor == me:
            return
        if team(c.world, ev.actor) is team(c.world, me):
            return
        if c.in_my_aura(ev.actor):
            c.flat(5, dtype=DamageType.NECROTIC, on=ev.actor)

    c.watch(TurnEnd, lingered, until=When.ENCOUNTER, on=me, label=f"{c.ref} aura")


@power(
    "m5281a1",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.hide(despite_cover=)",),
)
def m5281a1(c: Cast) -> None:
    """The whole of this row is a hidden creature *keeping* a hiding place it
    has stopped qualifying for. Being unseen here is a relation that the loss of
    cover ends, with nothing to hold it open.

    **Re-pointed off `c.stay_hidden()`**, which was the wrong symbol twice
    over: it is shared with a row about re-hiding after a missed attack, and
    that need turned out to be met by a *window* rather than a verb -- the
    `AttackDeclared` AFTER window, see `f1396`. So nothing would ever have
    arrived under that name and `todo.py` could not say so, because it fires
    when a named symbol appears. This row waits on something else entirely:
    hiddenness surviving the loss of cover. #390."""


@power(
    "m5281a2",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d4", 3),
)
def m5281a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5281a3",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d4", 3),
)
def m5281a3(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5281a4",
    level=2,
    usage=Usage.RECHARGE,
    recharge=4,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m5281a4(c: Cast) -> None:
    """A plain "+5 bonus" with no type word is untyped, so no `kind=`. The extra
    damage is `once=True` -- "the first melee attack" -- and gated on the reach
    of whatever rolls it."""
    for defence in (AC, FORT, REF, WILL):
        c.bonus(defence, 5, on=c.me, until=When.EONT)
    c.bonus("damage", 10, on=c.me, until=When.EONT, once=True, when=_melee_blow)


def _missed_my_fortitude(world: World, me: int, ev: Any) -> bool:
    return getattr(ev, "target", None) == me and getattr(ev, "vs", None) is FORT


@power(
    "m5281a5",
    level=2,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="an attack against its Fortitude misses it",
    on=Trigger(Miss, _missed_my_fortitude, "an attack against its Fortitude misses it"),
)
def m5281a5(c: Cast) -> None:
    """`vs` is a plain attribute `resolve.attack` rides on the outcome events,
    so the defence the attack went against is read with `getattr`."""
    c.temp_hp(5, on=c.me)


# --------------------------------------------------------------------------
# m5440
# --------------------------------------------------------------------------


@power(
    "m5440a0",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5440a0(c: Cast) -> None:
    """`c.resist_in` rather than a resistance laid on each ally: membership of
    an aura changes every time somebody walks, and resistance lives on
    `Defences` where a zone modifier cannot reach it."""
    ring = c.aura(10, until=When.ENCOUNTER)
    for dtype in (
        DamageType.ACID,
        DamageType.COLD,
        DamageType.FIRE,
        DamageType.LIGHTNING,
        DamageType.THUNDER,
    ):
        c.resist_in(ring, 5, dtype, side="ally")


@power(
    "m5440a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=MeleeOrRanged(1, 5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("2d6", 0, half_on_miss=True),
)
def m5440a1(c: Cast) -> None:
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)


@power(
    "m5440a2",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM],
)
def m5440a2(c: Cast) -> None:
    """The diversion is written as a watch rather than as `c.redirect`, which
    reads the event off `c.trigger` and this row is not answering one. Declared
    in the `BEFORE` window, because by `AFTER` the blow has landed on the wrong
    creature.

    Only melee and ranged attacks are moved, which is what the card says: a
    burst that catches the creature is not diverted.
    """
    chosen = c.target
    if chosen is None:
        return
    me = c.me

    def diverted(ev: AttackDeclared) -> None:
        if ev.target != me or _reach_kind(ev.power) not in ("melee", "ranged"):
            return
        ev.target = chosen
        result = getattr(ev, "result", None)
        if result is not None:
            result.target = chosen

    c.watch(
        AttackDeclared, diverted, until=When.EONT, on=me,
        window=Window.BEFORE, label=f"{c.ref} diversion",
    )
    c.bonus(
        "damage", 0, dice="2d6", on=me, until=When.EONT,
        when=lambda ctx: ctx.get("target") == chosen,
    )


@power(
    "m5440a3",
    level=2,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
    out_of_combat=True,
)
def m5440a3(c: Cast) -> None:
    """The whole printed effect is looking like somebody else. Nothing on a
    board reads a creature's appearance, and the row is finished and
    deliberately inert rather than unwritten -- `out_of_combat` also keeps the
    policy from being offered a minor action that does nothing every turn."""


def _spread_over_an_ally(world: World, me: int, ev: Any) -> bool:
    if getattr(ev, "target", None) != me:
        return False
    if _reach_kind(getattr(ev, "power", "")) not in _SPREADING:
        return False
    among = getattr(ev, "among", ())
    return any(w != me and team(world, w) is team(world, me) for w in among)


@power(
    "m5440a4",
    level=2,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    trigger="a close or area attack hits it and one of its allies",
    on=Trigger(
        Hit, _spread_over_an_ally, "a close or area attack hits it and one of its allies"
    ),
    dropped=("Hit.origin",),
)
def m5440a4(c: Cast) -> None:
    """The shift is the playable half, and the trigger's "also includes one of
    its allies" is answered off `ev.among` -- the whole target list of the one
    use, which rides on the event as a plain attribute.

    What cannot be asked is whether the shift ended outside the triggering
    attack's area. `dsl.area_of` will compute any power's squares, but it needs
    the origin the area was aimed at and no outcome event carries one -- so the
    `c.cancel()` that clause licenses is not taken.
    """
    c.shift(c.speed_of(c.me))


# --------------------------------------------------------------------------
# m5746
# --------------------------------------------------------------------------

#: Laid at the top of a turn begun in the creature's other shape, which is the
#: only thing the doubled damage can read: the shape itself has been left by
#: the time the attack is made, since it cannot attack from inside it.
_MISTED = "began its turn shapeless"


def _misted(c: Cast) -> bool:
    return any(_MISTED in effect.label for effect in c.world.effects.of(c.me))


@power(
    "m5746a0",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5746a0(c: Cast) -> None:
    """"Whenever it deals damage to an enemy **granting combat advantage to
    it**, that enemy cannot spend healing surges (save ends)."

    The third trait of this shape in the tree -- `m1763a3` and `m2515a3` are
    the other two -- and the only one with no weapon named, so it fires on
    any damage this creature deals rather than on one row's.

    `DamageApplied` and not `Hit`: the card says *deals damage*, and a hit
    reduced to nothing deals none. Combat advantage is asked **live at the
    blow**, because a stored answer is wrong the moment an ally steps away
    from a flank -- `features/strikers.py` states that reasoning.

    `c.no_surges` rather than `c.no_healing`, which refuses every sort of
    healing and would take away a leader's word too. #386.
    """
    me = c.me

    def withers(ev: DamageApplied) -> None:
        if ev.source != me or ev.amount <= 0:
            return
        if has_combat_advantage(c.world, me, ev.target):
            c.no_surges(on=ev.target, until=When.SAVE_ENDS)

    c.watch(DamageApplied, withers, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m5746a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 7, dtype=DamageType.NECROTIC),
)
def m5746a1(c: Cast) -> None:
    """The +1 against a bloodied target is part of the attack line, so it goes
    into the roll as `plus=` rather than being laid as a standing modifier that
    the next attack would read too."""
    if c.strike(plus=1 if c.bloodied() else 0):
        c.hit()


@power(
    "m5746a2",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.WEAPON],
    attack=Attack(vs=REF, printed=6),
    damage=Damage("1d6", 7, dtype=DamageType.NECROTIC, half_on_miss=True),
)
def m5746a2(c: Cast) -> None:
    """"Double damage" is the blow dealt again rather than dice rolled twice, so
    the number `c.hit` returns is what is added -- rolling a second time would
    be a different and wider spread."""
    foe = c.target
    if not c.strike(plus=1 if c.bloodied() else 0):
        c.hit(half=True)
        return
    dealt = c.hit()
    if _misted(c) and dealt:
        c.flat(dealt, dtype=DamageType.NECROTIC, on=foe)


@power(
    "m5746a3",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    dropped=("c.untargetable()", "c.ignore_squeeze_penalty()"),
)
def m5746a3(c: Cast) -> None:
    """A polymorph rather than a stance -- it is in the shape and may step out
    of it -- so `revert` is what leaving costs. Everything the shape installs is
    tied to the form's own hold, or the bans would outlive it.

    "Cannot be attacked" has no expression: nothing bars a creature from being
    a target. Nor has moving at full speed while squeezing.
    """
    me, ref = c.me, c.ref
    shape = c.form(until=When.ENCOUNTER, revert=FREE, label=f"{ref} shapeless")
    for held in (
        c.cannot_attack(on=me, until=When.ENCOUNTER),
        c.no_healing(on=me, until=When.ENCOUNTER),
        c.shares_space(difficult=True),
    ):
        if held is not None:
            shape.on_end.append(lambda h=held: c.world.effects.end(h, "form ended"))

    def dawn(ev: TurnStart) -> None:
        if ev.actor == me and not ev.ghost and shape in c.world.effects.of(me):
            c.effect(f"{ref} {_MISTED}", until=When.EOT, on=me)

    c.watch(TurnStart, dawn, until=When.ENCOUNTER, on=me, label=f"{ref} dawn")


@power(
    "m5746a4",
    level=2,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it drops to 0 hit points",
    on=Trigger(Dropped, about_me, "it drops to 0 hit points"),
)
def m5746a4(c: Cast) -> None:
    """One healing surge leaves an enemy's pool and heals nobody.

    `c.spend_surge(on=)` is exactly that -- "Spend a surge and gain nothing for
    it", written for the paladin's touch where the payer and the healed are
    different creatures. This row was marked `todo=("c.lose_surge()",)` on the
    reasoning that `c.regain_surge` refuses a negative count, which is true and
    was the wrong verb to look at: it is a death throe refused in play for want
    of a method that has existed all along.

    `todo.py` could not catch it either -- its staleness check matches the
    symbol a marker names, and the name invented here is not the name of the
    thing that exists.
    """
    # "One enemy that it can see" -- the row has no target line of its own, so
    # the choice is made here. Nearest first, which is the convention the
    # auto-targeter uses and the only ordering available without asking.
    seen = [who for who in c.enemies() if c.can_see(who)]
    if not seen:
        return
    seen.sort(key=lambda who: c.distance(who))
    c.spend_surge(on=seen[0])


@power(
    "m5746a5",
    level=2,
    usage=ENCOUNTER,
    action=FREE,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
    damage=Damage("1d6", 3, dtype=DamageType.FIRE, kind=LIMITED),
    trigger="an enemy within 10 squares hits it",
    on=Trigger(
        Hit, both(targets_me, enemy_within(10)), "an enemy within 10 squares hits it"
    ),
)
def m5746a5(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is not None:
        c.hit(on=foe)


# --------------------------------------------------------------------------
# m5848
# --------------------------------------------------------------------------


def _has_been_hurt(world: World, eid: int) -> bool:
    health = world.get(eid, Health)
    return health is not None and health.hp < health.max_hp


def _is_prone(world: World, eid: int) -> bool:
    from combat_engine.engine.query import is_

    return is_(world, eid, Condition.PRONE)


def _spreading_blow(ctx: dict[str, Any]) -> bool:
    return _reach_kind(str(ctx.get("power", ""))) in _SPREADING


@power(
    "m5848a0",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5848a0(c: Cast) -> None:
    """Counted off the attack's own context rather than paired when the trait
    arms: who is standing next to one of its friends changes every time anybody
    walks."""
    c.gains_advantage(
        lambda ctx: isinstance(ctx.get("target"), int)
        and any(c.adjacent_to(ctx["target"], mate) for mate in c.allies()),
        until=When.ENCOUNTER,
        on=c.me,
    )


@power(
    "m5848a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 4),
)
def m5848a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5848a2",
    level=2,
    usage=Usage.RECHARGE,
    recharge=0,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.CHARM],
    requires=_has_been_hurt,
    requires_text="must have taken damage this encounter",
    dropped=("c.untargetable()",),
)
def m5848a2(c: Cast) -> None:
    """A plain "+5 power bonus" against close and area attacks only, so the
    bonus is gated on the reach of whatever rolls it.

    "Enemies think it is dead and cannot attack it without an Insight check"
    is the clause with nowhere to go: nothing bars a creature from being a
    target, and a check that unlocks one would need that first.
    """
    _recharge_when_using(c, "m5848a3")
    c.prone(on=c.me)
    for defence in (AC, FORT, REF, WILL):
        c.bonus(
            defence, 5, on=c.me, until=When.SONT, kind="power", when=_spreading_blow
        )


@power(
    "m5848a3",
    level=2,
    usage=Usage.RECHARGE,
    recharge=0,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 4),
    requires=_is_prone,
    requires_text="must be prone",
    recharge_when=Trigger(PowerUsed, by_power("m5848a2"),
                          "when it uses m5848a2"),
)
def m5848a3(c: Cast) -> None:
    """The header copies the sword's own line so the card and the policy can
    read what three swings come to. "Each of these attacks deals half damage on
    a miss" is why the swings are rolled here rather than borrowed: the row they
    belong to has no half-on-miss line of its own."""
    _recharge_when_using(c, "m5848a2")
    c.cure(Condition.PRONE, on=c.me)
    c.shift(3)
    for _ in range(3):
        if c.strike():
            c.hit()
        else:
            c.hit(half=True)


@power(
    "m5848a4",
    level=2,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    trigger="it drops to 0 hit points",
    on=Trigger(Dropped, about_me, "it drops to 0 hit points"),
)
def m5848a4(c: Cast) -> None:
    """"Instead has 1 hit point" is however far under one it ended up, so it is
    measured rather than assumed."""
    health = c.world.get(c.me, Health)
    if health is not None and health.hp < 1:
        c.heal(1 - health.hp, on=c.me)
    c.cure(Condition.PRONE, on=c.me)
    c.shift(3)


# --------------------------------------------------------------------------
# m5867
# --------------------------------------------------------------------------


@power(
    "m5867a0",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5867a0(c: Cast) -> None:
    c.resist_forced(3)


@power(
    "m5867a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 7, dtype=DamageType.POISON),
)
def m5867a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5867a2",
    level=2,
    usage=Usage.RECHARGE,
    recharge=0,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("2d6", 8, dtype=DamageType.POISON, kind=LIMITED, half_on_miss=True),
    dropped=("Usage.RECHARGE(when=)",),
)
def m5867a2(c: Cast) -> None:
    _recharge_when_using(c, "m5867a3")
    if c.strike():
        c.hit()
        c.weakened(until=When.SAVE_ENDS)
    else:
        c.hit(half=True)
        c.weakened(until=When.EOTNT)


@power(
    "m5867a3",
    level=2,
    usage=Usage.RECHARGE,
    recharge=0,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
    recharge_when=Trigger(PowerUsed, by_power("m5867a2"),
                          "when it uses m5867a2"),
)
def m5867a3(c: Cast) -> None:
    _recharge_when_using(c, "m5867a2")
    c.invisible(until=When.SONT, on=c.me)


# --------------------------------------------------------------------------
# m6554
# --------------------------------------------------------------------------


@power(
    "m6554a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d8", 5),
)
def m6554a0(c: Cast) -> None:
    """Asked *before* the swing: `resolve.attack` gives a hidden creature away
    the moment it attacks, so a body that strikes and then asks whether it was
    seen gets "yes" every time -- which is exactly the creature this line is
    written for."""
    foe = c.target
    unseen = foe is not None and c.is_hidden(from_=foe)
    if c.strike():
        if unseen:
            c.damage("2d8", 10)
        else:
            c.hit()


@power(
    "m6554a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
)
def m6554a1(c: Cast) -> None:
    """A real check against a real number: the target's passive perception,
    which is what it notices unbidden, rather than an invented DC."""
    foe = c.target
    if foe is not None and c.check("stealth", c.passive("perception", of=foe)):
        c.hide(from_=foe)


@power(
    "m6554a2",
    level=2,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
)
def m6554a2(c: Cast) -> None:
    """"Until it hits or misses with an attack" needs nothing written:
    `resolve.attack` ends the hold for whoever swung. The clock is the other
    half of the printed line."""
    c.invisible(until=When.EONT, on=c.me)
