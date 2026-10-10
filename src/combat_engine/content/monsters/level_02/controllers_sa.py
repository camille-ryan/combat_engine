"""Monster abilities, level 2, controllers: the second sweep.

Twelve stat blocks whose rows were still undeclared. `controllers.py` holds the
first sweep of this level; the split is by *when* the work was done rather than
by what the creatures are, and the conventions are the ones the level 1 sweep
settled:

* numbers load from `game.db` -- the attack line is written exactly as printed
  (`Attack(vs=WILL, printed=5)`) and the damage line goes in the header as
  data, so an MM1 block can be rescaled to MM3 maths later;
* a **trait** is a row that costs no action, has no target, and arms the
  watches that hold it for the rest of the fight;
* a second attack line cannot live in the header, so its printed bonus goes
  through `world.scaling.trim` by hand -- which is exactly what
  `Attack(printed=)` does with the first one;
* a printed target restriction about what a creature is *suffering* or about
  what the attacker is holding is asked in the body, because `Target` filters
  on side and size and nothing else. `label=` records it for the card and the
  marker is whichever symbol names what the line asks -- `Target.ident` for one
  of its own kind. **"A creature the attacker has hold of" is no longer one of
  them**: `Target.relation` is a real field, so that line is the target line
  itself and carries no marker (#401);
* a row that recharges on a printed condition rather than on a die keeps the
  die in the header, because that is what `actions.recharge` rolls and what the
  card shows, and arms the condition on top of it.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_01.artillery_sa import _recharge_when_bloodied
from combat_engine.content.monsters.level_01.skirmishers import _ref_of
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_ALLY,
    EACH_CREATURE,
    EACH_ENEMY,
    EACH_OTHER,
    ENCOUNTER,
    FORT,
    FREE,
    INTERRUPT,
    MELEE,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    RANGED,
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
    Keyword,
    Melee,
    Powers,
    Ranged,
    Relation,
    Target,
    Usage,
    When,
    World,
    power,
)
from combat_engine.engine.dsl import get as _row_for
from combat_engine.engine.events import (
    AttackRolled,
    Bloodied,
    DamageApplied,
    Hit,
    Miss,
    TurnStart,
)
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import distance_between, enemies, team
from combat_engine.engine.triggers import Trigger, about_me, by_me, targets_me

# -- what the blocks in this file share -------------------------------------


def _holds_somebody(world: World, eid: int) -> bool:
    """"Targets a creature it is grabbing", as a Requirement.

    `query` has no grab helper at all -- `c.grabbing` lives on `Cast`, which a
    `requires=` gate has not got -- so the fighter's version is reused rather
    than rewritten. Without the gate the row is offered every turn, resolves
    against whoever is nearest and does nothing, which from the outside is a
    row written wrong.
    """
    from combat_engine.content.powers.fighter.holds import holds_somebody

    return holds_somebody(world, eid)


def _recharge_on_miss(c: Cast) -> None:
    """Put the row back up when it misses, which is what its card prints.

    The die stays in the header because that is what `actions.recharge` rolls;
    this is the printed sentence on top of it. Armed once -- a second watch
    under the same label would restore the use twice for one miss.
    """
    me, ref = c.me, c.ref
    label = f"{ref} recharge"
    if any(effect.label == label for effect in c.world.effects.of(me)):
        return

    def missed(ev: Miss) -> None:
        if ev.attacker == me and ev.power == ref:
            c.restore_use(ref, on=me)

    c.watch(Miss, missed, until=When.ENCOUNTER, on=me, label=label)


def _kin_within(c: Cast, radius: int, of: int) -> list[int]:
    """Creatures of the caster's own stat block standing near somebody.

    "Two or more <this creature> within 5 squares" is a count of a kind, and
    the only thing an author is given to compare is the ref, so that is what
    is compared. The caster counts itself in, which is why `side="team"`.
    """
    mine = _ref_of(c, c.me)
    return [w for w in c.within(radius, of=of, side="team") if _ref_of(c, w) == mine]


def _swing_reach(c: Cast, swinger: int, *, ranged: bool = False) -> int:
    """How far the creature being *told* to swing can actually reach.

    `c.reach()` and `c.distance()` both answer for the caster and for the row
    being cast, which on a forced-attack row is the charm that carries 10 or
    20 squares -- not the melee basic the victim is about to make. The swing's
    own row is `Powers.basic`, or the engine's `mba` for a creature that
    declares none, and `on=` measures the weapon in *that* creature's hands.

    The two lines are picked the same way `c.basic` picks them, deliberately:
    measuring one row and swinging another is how a reach-1 basic attack came
    to land at nine squares. `dsl.use`'s explicit-target arm applies no reach
    check of its own, so this is the only gate there is. #381.
    """
    known = c.world.get(swinger, Powers)
    if ranged:
        # `Powers.ranged` before the engine's generic bow, which is what
        # `Cast.basic` now picks too. Measuring `rba` while the swing used the
        # creature's own printed row is the mismatch the paragraph above warns
        # about, pointed at the ranged half. #397, #398.
        ref = (known.ranged if known else "") or RANGED
    else:
        ref = (known.basic if known else MELEE) or MELEE
    return c.reach(ref, on=swinger)


def _let_it_swing(c: Cast, ally: int) -> None:
    """"It shifts 1 square and makes a basic attack." The ally needs a victim
    of its own: the row's own target is wherever the burst was aimed and may be
    nowhere near whoever is being told to swing."""
    c.shift(1, who=ally)
    reachable = [foe for foe in c.enemies() if c.adjacent_to(foe, ally)]
    if reachable:
        c.basic(who=ally, on=reachable[0])


# --------------------------------------------------------------------------
# m1129
# --------------------------------------------------------------------------


@power(
    "m1129a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 1),
)
def m1129a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)


@power(
    "m1129a1",
    level=2,
    usage=Usage.RECHARGE,
    recharge=5,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(vs=FORT, printed=6),
)
def m1129a1(c: Cast) -> None:
    """The secondary is a burst centred on the primary target, so it is rolled
    once per creature standing in it -- the primary included, which is what a
    centred burst catches. Its printed +6 is trimmed by hand the way the
    header's is, or the row would ignore whatever scaling is in force."""
    foe = c.target
    if foe is None or not c.strike():
        return
    c.blinded(until=When.SAVE_ENDS)
    bonus = c.world.scaling.trim(6, c.level)
    for caught in c.within(1, of=foe):
        if c.attack(bonus, REF, on=caught):
            c.damage("1d6", 4, dtype=DamageType.ACID, on=caught)
            c.ongoing(2, DamageType.ACID, on=caught)


@power(
    "m1129a2",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=5),
    damage=Damage("1d4", 4),
)
def m1129a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.penalty("attack", 2, until=When.EONT)


# --------------------------------------------------------------------------
# m4455
# --------------------------------------------------------------------------


def _not_grabbing(world: World, eid: int) -> bool:
    return not _holds_somebody(world, eid)


@power(
    "m4455a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d8", 3),
    requires=_not_grabbing,
    requires_text="can hold only one creature at a time",
)
def m4455a0(c: Cast) -> None:
    """"One target at a time" is the Requirement rather than a release: nothing
    in the printed line lets go of whoever is already held."""
    if c.strike():
        c.hit()
        c.grab()


@power(
    "m4455a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=Target(
        side="enemy", count=1, label="a creature it is grabbing",
        relation=Relation.GRABBED_BY,
    ),
    attack=Attack(vs=FORT, printed=6),
    damage=Damage("1d8", 3),
)
def m4455a1(c: Cast) -> None:
    """"Sustains the grab" is the grab not ending, and a grab does not lapse on
    a clock here -- so the printed sentence is satisfied by re-setting the hold
    rather than by a duration."""
    if c.strike():
        c.hit()
        c.grab()


@power(
    "m4455a2",
    level=2,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m4455a2(c: Cast) -> None:
    """The shift comes first, because the square the held creature is slid to
    has to be adjacent to wherever the vine ended up."""
    c.shift(2)
    for held in c.grabbing():
        c.slide(2, on=held)


# --------------------------------------------------------------------------
# m4609
# --------------------------------------------------------------------------


@power(
    "m4609a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d4", 3),
)
def m4609a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4609a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD, Keyword.IMPLEMENT],
    attack=Attack(vs=FORT, printed=5),
    damage=Damage("1d10", 3, dtype=DamageType.COLD),
)
def m4609a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.EONT)


@power(
    "m4609a2",
    level=2,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(3),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=REF, printed=5),
    damage=Damage("1d8", 3, dtype=DamageType.POISON, kind=LIMITED),
)
def m4609a2(c: Cast) -> None:
    """The mark is laid *for* another creature, so it only happens when one of
    that kind is on the board -- the printed Effect draws something already
    present rather than putting it there, so nothing is summoned."""
    _recharge_on_miss(c)
    if not c.strike():
        return
    c.hit()
    drawn = [a for a in c.allies() if _ref_of(c, a) == "m2795"]
    if drawn:
        c.mark(until=When.SAVE_ENDS, by=drawn[0])


@power(
    "m4609a3",
    level=2,
    usage=Usage.RECHARGE,
    recharge=4,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.RADIANT],
    attack=Attack(vs=REF, printed=5),
    damage=Damage("1d8", 3, dtype=DamageType.RADIANT, kind=LIMITED),
)
def m4609a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.EONT)
    if c.first:
        inside = c.in_squares(c.area(), side="ally")
        if inside:
            _let_it_swing_without_moving(c, inside[0])


def _let_it_swing_without_moving(c: Cast, ally: int) -> None:
    """"One ally can make a melee basic attack as a free action" -- the swing
    only, with no step attached to it."""
    reachable = [foe for foe in c.enemies() if c.adjacent_to(foe, ally)]
    if reachable:
        c.basic(who=ally, on=reachable[0])


@power(
    "m4609a4",
    level=2,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m4609a4(c: Cast) -> None:
    c.shift(1)


# --------------------------------------------------------------------------
# m4681
# --------------------------------------------------------------------------


@power(
    "m4681a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d8", 5),
)
def m4681a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4681a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=6),
    damage=Damage("2d4", 4),
)
def m4681a1(c: Cast) -> None:
    """No range is printed where the next row prints its own, so this is read
    as the creature's melee attack."""
    if c.strike():
        c.hit()
        c.slowed(until=When.EONT)


@power(
    "m4681a2",
    level=2,
    usage=Usage.RECHARGE,
    recharge=4,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=4),
    damage=Damage("1d6", 6, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m4681a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


def _hit_with_either(world: World, me: int, ev: Any) -> bool:
    return (
        getattr(ev, "attacker", None) == me
        and getattr(ev, "power", "") in ("m4681a0", "m4681a1")
    )


@power(
    "m4681a3",
    level=2,
    usage=Usage.RECHARGE,
    recharge=0,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PSYCHIC],
    trigger="it hits with its staff or with m4681a1",
    on=Trigger(Hit, _hit_with_either, "it hits with its staff or with m4681a1"),
    recharge_when=Trigger(Bloodied, about_me,
        "when first bloodied"),
)
def m4681a3(c: Cast) -> None:
    """The extra damage goes on whoever the triggering attack hit, which is
    `ev.target` and not a target of this row -- a free action answering a hit
    has none of its own."""
    _recharge_when_bloodied(c)
    ev = c.trigger
    victim = getattr(ev, "target", None)
    if victim is not None:
        c.damage("1d8", dtype=DamageType.PSYCHIC, on=victim)


@power(
    "m4681a4",
    level=2,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    trigger="it is hit by an attack",
    on=Trigger(Hit, targets_me, "it is hit by an attack"),
)
def m4681a4(c: Cast) -> None:
    c.shift(2)


# --------------------------------------------------------------------------
# m4756
# --------------------------------------------------------------------------


@power(
    "m4756a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d8", 4),
)
def m4756a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4756a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d8", 5),
)
def m4756a1(c: Cast) -> None:
    """The slide is read off the roll rather than asked of the board again: a
    one-shot grant of combat advantage has already been spent by the time the
    attack is over."""
    result = c.strike()
    if result:
        c.hit()
        if result.advantage:
            c.slide(3)


@power(
    "m4756a2",
    level=2,
    usage=ENCOUNTER,
    uses=3,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON],
    dropped=("etl.monster.secondary_line()",),
)
def m4756a2(c: Cast) -> None:
    """The shortbow attack is the creature's own ranged row, run at this row's
    action cost so every rider that reads it still does. The secondary attack
    the card promises has no line at all in the extraction -- no bonus, no
    defence, no effect -- so it is named rather than invented."""
    c.use_power("m4756a1", on=c.target)


@power(
    "m4756a3",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=6),
)
def m4756a3(c: Cast) -> None:
    """"Save ends both" is one effect carrying both halves, so `ongoing=` on
    the condition rather than a second hold with a second saving throw."""
    if c.strike():
        c.condition(
            Condition.DAZED,
            until=When.SAVE_ENDS,
            ongoing=(3, DamageType.UNTYPED),
        )


@power(
    "m4756a4",
    level=2,
    usage=Usage.RECHARGE,
    recharge=5,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=6),
    damage=Damage("2d8", 2, kind=LIMITED),
)
def m4756a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized(until=When.SAVE_ENDS)


@power(
    "m4756a5",
    level=2,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it makes an attack roll",
    on=Trigger(AttackRolled, by_me, "it makes an attack roll"),
)
def m4756a5(c: Cast) -> None:
    """The card prints no Trigger line, and `c.reroll_attack` reads the roll off
    one -- there is nothing else on the board that holds a spent d20. So the
    sentence is declared against its own rolls, which is the only moment the
    printed permission can be exercised, and on `AttackRolled` rather than on
    `Hit`: a reroll is wanted for the swings that missed. `keep="new"` is "it
    must use the second roll, even if it is lower"."""
    c.reroll_attack(keep="new")


@power(
    "m4756a6",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4756a6(c: Cast) -> None:
    """Rough ground costs it nothing while it shifts, and nothing else.

    `when="shift"` is the narrowing every one of these cards prints and this
    verb could not say. It is spent in the *search*: a square of difficult
    terrain costs two, a shift is one, so without the exemption the square is
    never offered as a shift destination at all.
    """
    c.ignores_difficult(on=c.me, until=When.ENCOUNTER, when="shift")


# --------------------------------------------------------------------------
# m5075
# --------------------------------------------------------------------------

#: The label a lit ring is held under. Counted rather than stored, because
#: there is nowhere on a creature for a row to keep a number of its own and a
#: labelled hold is a thing `Effects` already carries, shows and clears.
_RING = "ring alight"


def _alight(c: Cast) -> int:
    return sum(1 for effect in c.world.effects.of(c.me) if _RING in effect.label)


@power(
    "m5075a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=REF, printed=6),
    damage=Damage("1d10", 3, dtype=DamageType.POISON),
)
def m5075a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5075a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=6),
    damage=Damage("1d6", 3, dtype=DamageType.NECROTIC),
)
def m5075a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.EONT)


@power(
    "m5075a2",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5075a2(c: Cast) -> None:
    """Five rings, dark to start, one lighting on each hit taken. The count is
    the whole content of the trait and the next row reads it, so it has to live
    somewhere both can see: a labelled hold per lit ring, which is countable,
    visible on the creature and cleared by the row that puts them all out."""
    me = c.me
    ref = c.ref

    def struck(ev: Hit) -> None:
        if ev.target != me:
            return
        lit = _alight(c)
        if lit < 5:
            c.effect(f"{ref} {_RING} {lit + 1}", until=When.ENCOUNTER, on=me)

    c.watch(Hit, struck, until=When.ENCOUNTER, on=me, label=f"{ref} rings")


@power(
    "m5075a3",
    level=2,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=CloseBurst(5),
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=6),
    damage=Damage("1d10", 3, dtype=DamageType.NECROTIC),
)
def m5075a3(c: Cast) -> None:
    """Three powers behind one card, so the choice is offered rather than
    assumed, and the row carries no target of its own: each branch picks what it
    needs. The header states the attack line of the one branch that has one so
    the card and the policy can read it, and that branch rolls it by hand --
    `c.strike` has no `c.target` to swing at under `NO_TARGET`.

    "All of her rings go dark" is a printed **can**, so it is a `c.may`. The
    withering branch's rider is `c.no_surges` (save ends), which exists now --
    and is deliberately not `c.no_healing`, which refuses a heal outright and
    is a stronger sentence than this card's. #386.
    """
    lit = _alight(c)
    dark = 5 - lit
    picked = c.choose(["the fire", "the warding", "the withering"], "which talisman")
    if picked == "the fire":
        for foe in c.within(5, side="enemy"):
            c.flat(dark, dtype=DamageType.FIRE, on=foe)
    elif picked == "the warding":
        c.resist(lit, until=When.SONT, on=c.me)
    else:
        reachable = [f for f in c.enemies() if distance_between(c.world, c.me, f) <= 20]
        victim = c.choose(reachable, "who withers") if reachable else None
        if victim is not None and c.attack(c.world.scaling.trim(6, c.level), FORT, on=victim):
            c.hit(on=victim)
            c.no_surges(on=victim, until=When.SAVE_ENDS)
    if lit and c.may("let the rings go dark"):
        for effect in list(c.world.effects.of(c.me)):
            if _RING in effect.label:
                c.world.effects.end(effect, c.ref)


# --------------------------------------------------------------------------
# m5285
# --------------------------------------------------------------------------


@power(
    "m5285a0",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5285a0(c: Cast) -> None:
    """Counted at the top of the enemy's turn rather than paired, because the
    set of creatures hemmed in by two of these is not knowable when the trait
    arms."""
    me = c.me

    def started(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == me:
            return
        if team(c.world, ev.actor) is team(c.world, me):
            return
        if len(_kin_within(c, 1, ev.actor)) >= 2:
            c.flat(2, on=ev.actor)

    c.watch(TurnStart, started, until=When.ENCOUNTER, on=me, label=f"{c.ref} press")


@power(
    "m5285a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d10", 5),
)
def m5285a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5285a2",
    level=2,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.FORCE, Keyword.ZONE],
    attack=Attack(vs=REF, printed=6),
    damage=Damage("1d10", 5, dtype=DamageType.FORCE, kind=LIMITED, half_on_miss=True),
)
def m5285a2(c: Cast) -> None:
    """"Enemies treat the zone as difficult terrain" is a difficult zone its own
    side walks through for nothing, which is `c.ignores_difficult_in` rather
    than a second zone."""
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)
    if c.first:
        ground = c.zone(c.area(), difficult=True, until=When.ENCOUNTER)
        c.ignores_difficult_in(ground, side="team")


@power(
    "m5285a3",
    level=2,
    usage=Usage.RECHARGE,
    recharge=0,
    action=STANDARD,
    reach=CloseBlast(5),
    target=Target(side="ally", everyone=True, label="each ally of its own kind"),
    dropped=("Target.ident",),
)
def m5285a3(c: Cast) -> None:
    """"Each <this creature> in the blast" is a target line about what a
    creature *is*, and `Target` filters on side and size only -- so the kind is
    asked in the body and recorded in the label."""
    _recharge_when_bloodied(c)
    ally = c.target
    if ally is not None and _ref_of(c, ally) == _ref_of(c, c.me):
        _let_it_swing(c, ally)


@power(
    "m5285a4",
    level=2,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(5),
    target=EACH_ALLY,
    trigger="it is first bloodied",
    on=Trigger(Bloodied, about_me, "it is first bloodied"),
)
def m5285a4(c: Cast) -> None:
    """`Bloodied` is emitted on the crossing and not again, so "first" needs no
    guard of its own."""
    ally = c.target
    if ally is not None:
        _let_it_swing(c, ally)


# --------------------------------------------------------------------------
# m5398
# --------------------------------------------------------------------------


@power(
    "m5398a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d8", 6),
)
def m5398a0(c: Cast) -> None:
    """The worse hold is chosen after the damage, because the blow is what may
    make the target bloodied and the card reads the state when the condition is
    applied."""
    if not c.strike():
        return
    c.hit()
    if c.bloodied() or c.is_(Condition.SLOWED):
        c.immobilized(until=When.EONT)
    else:
        c.slowed(until=When.EONT)


@power(
    "m5398a1",
    level=2,
    usage=Usage.RECHARGE,
    recharge=0,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.THUNDER],
    attack=Attack(vs=FORT, printed=5),
    damage=Damage("2d6", 3, dtype=DamageType.THUNDER, kind=LIMITED),
    recharge_when=Trigger(Bloodied, about_me,
        "when first bloodied"),
)
def m5398a1(c: Cast) -> None:
    _recharge_when_bloodied(c)
    if c.strike():
        c.hit()
        c.push(3)
        c.prone()


@power(
    "m5398a2",
    level=2,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=FORT, printed=5),
    damage=Damage("2d8", 4, dtype=DamageType.LIGHTNING, kind=LIMITED, half_on_miss=True),
)
def m5398a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.DAZED, until=When.SAVE_ENDS)
    else:
        c.hit(half=True)
        c.dazed(until=When.EONT)


@power(
    "m5398a3",
    level=2,
    usage=Usage.RECHARGE,
    recharge=5,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.TELEPORTATION],
    attack=Attack(vs=FORT, printed=5),
)
def m5398a3(c: Cast) -> None:
    """Two destinations on one card, so the swap is offered: itself, or any ally
    it can reach. `c.swap` moves both creatures through `movement.step`, so an
    aura notices the arrival."""
    foe = c.target
    if foe is None or not c.strike():
        return
    movers = [c.me, *c.within(5, side="ally")]
    who = c.choose(movers, "who changes places with the target") or c.me
    c.swap(foe, who=who)


# --------------------------------------------------------------------------
# m5431
# --------------------------------------------------------------------------


@power(
    "m5431a0",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5431a0(c: Cast) -> None:
    """An aura 1 for the board to draw, and the bite hung off `TurnStart` --
    the printed line is about *starting* a turn inside it, so entry and exit
    are not what it reads."""
    me = c.me
    c.aura(1, until=When.ENCOUNTER)

    def started(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == me:
            return
        if team(c.world, ev.actor) is team(c.world, me):
            return
        if c.in_my_aura(ev.actor):
            c.flat(4, on=ev.actor)
            c.slowed(until=When.SOTNT, on=ev.actor)

    c.watch(TurnStart, started, until=When.ENCOUNTER, on=me, label=f"{c.ref} aura")


def _by_hand(ctx: dict[str, Any]) -> bool:
    """Was the shove a melee or a ranged attack's doing?

    `movement._settle` hands the gate `{"how": push|pull|slide, "power": ref}`,
    so the reach has to be looked up off the row that did it -- the same lookup
    `triggers.by_melee` makes for the same reason.
    """
    row = _row_for(str(ctx.get("power", "")))
    return row is not None and row.reach_of(0).kind in ("melee", "ranged")


@power(
    "m5431a1",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.move_through()",),
)
def m5431a1(c: Cast) -> None:
    """A swarm's square is enterable by whoever likes and costs them, which is
    `c.shares_space` and not `c.shift(share=True)` -- that one is an argument to
    one move made by the mover. The immunity to shoves is narrowed to the
    attacks that print it rather than written as `c.immovable`, which would be a
    row stronger than its card. Squeezing through an opening is the clause with
    nowhere to go: the board has no apertures to fit through."""
    c.shares_space(difficult=True)
    c.resist_forced(99, when=_by_hand)


@power(
    "m5431a2",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=7),
    damage=Damage("2d6", 3),
)
def m5431a2(c: Cast) -> None:
    """Two damage lines on one hit, so the bigger one is rolled in the body:
    the header can only hold the one the card leads with."""
    if not c.strike():
        return
    if c.bloodied():
        c.damage("2d6", 5)
    else:
        c.hit()


def _beside_a_bloodied_enemy(world: World, eid: int) -> bool:
    return any(
        distance_between(world, eid, foe) <= 1 and _is_bloodied(world, foe)
        for foe in enemies(world, eid)
    )


def _is_bloodied(world: World, eid: int) -> bool:
    from combat_engine.engine import Health

    health = world.get(eid, Health)
    return health is not None and health.bloodied


@power(
    "m5431a3",
    level=2,
    usage=Usage.RECHARGE,
    recharge=0,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=5),
    damage=Damage("2d6", 4, dtype=DamageType.PSYCHIC, kind=LIMITED),
    requires=_beside_a_bloodied_enemy,
    requires_text="must be adjacent to a bloodied enemy",
)
def m5431a3(c: Cast) -> None:
    """The push is the target's own speed, read off the board rather than fixed:
    the card says so and the number differs per creature."""
    if c.first:
        me, ref = c.me, c.ref

        def bled(ev: Bloodied) -> None:
            if ev.source == me:
                c.restore_use(ref, on=me)

        c.watch(Bloodied, bled, until=When.ENCOUNTER, on=me, label=f"{ref} recharge")
    if c.strike():
        c.hit()
        c.push(c.speed_of(c.target))


# --------------------------------------------------------------------------
# m6006
# --------------------------------------------------------------------------


@power(
    "m6006a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 1),
)
def m6006a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6006a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE, Keyword.IMPLEMENT],
    damage=Damage(bonus=7, dtype=DamageType.FORCE),
)
def m6006a1(c: Cast) -> None:
    """No attack roll: the whole card is an Effect, so the damage is dealt
    rather than landed. It still belongs in the header as data."""
    c.hit()


@power(
    "m6006a2",
    level=2,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_OTHER,
    keywords=[Keyword.FIRE, Keyword.IMPLEMENT],
    attack=Attack(vs=REF, printed=6),
    damage=Damage("2d6", 5, dtype=DamageType.FIRE, kind=LIMITED, half_on_miss=True),
)
def m6006a2(c: Cast) -> None:
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)


@power(
    "m6006a3",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.COLD, Keyword.IMPLEMENT],
    attack=Attack(vs=REF, printed=6),
    damage=Damage("1d6", 5, dtype=DamageType.COLD),
)
def m6006a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(1)


@power(
    "m6006a4",
    level=2,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m6006a4(c: Cast) -> None:
    c.teleport(5)


@power(
    "m6006a5",
    level=2,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    trigger="an enemy hits it",
    on=Trigger(Hit, targets_me, "an enemy hits it"),
)
def m6006a5(c: Cast) -> None:
    """A power bonus, which is the word the card prints in front of "bonus" --
    two of the same kind do not add and the larger wins, so the type is not a
    guess."""
    c.bonus(AC, 4, kind="power", until=When.EONT, on=c.me)
    c.bonus(REF, 4, kind="power", until=When.EONT, on=c.me)


@power(
    "m6006a6",
    level=2,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="it starts its turn",
    on=Trigger(TurnStart, about_me, "it starts its turn"),
    dropped=("spec.weapon_ref()",),
)
def m6006a6(c: Cast) -> None:
    """A plain "+3 bonus" with no type word is untyped, so no `kind=`. `once=`
    is "a single attack roll". The narrowing to one implement cannot be said:
    a monster carries no named gear and the spec gives no ref for the one this
    card wants."""
    c.bonus("attack", 3, until=When.EOT, on=c.me, once=True)


# --------------------------------------------------------------------------
# m6106
# --------------------------------------------------------------------------


@power(
    "m6106a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD, Keyword.FIRE],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d8", 5, dtype=[DamageType.COLD, DamageType.FIRE]),
)
def m6106a0(c: Cast) -> None:
    """The blow is fire *and* cold -- one roll of two types, which resistance
    reads as a unit. `c.damage` takes `dtypes=` for exactly that and `Damage`
    does not, so keeping the number in the header where it can be rescaled
    costs the cold half of the type."""
    if c.strike():
        c.hit()
        c.condition(Condition.SLOWED, until=When.SAVE_ENDS)


@power(
    "m6106a1",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=CloseBurst(2),
    target=EACH_OTHER,
    keywords=[Keyword.FIRE, Keyword.FORCE],
    attack=Attack(vs=REF, printed=5),
    damage=Damage(
        "2d8",
        2,
        dtype=[DamageType.FIRE, DamageType.FORCE],
        kind=LIMITED,
        half_on_miss=True,
    ),
    trigger="it becomes bloodied",
    on=Trigger(Bloodied, about_me, "it becomes bloodied"),
)
def m6106a1(c: Cast) -> None:
    """Fire *and* force on one roll, as above: the header holds one type."""
    if c.strike():
        c.hit()
        c.push(2)
    else:
        c.hit(half=True)


# --------------------------------------------------------------------------
# m6531
# --------------------------------------------------------------------------


@power(
    "m6531a0",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m6531a0(c: Cast) -> None:
    """The whole printed benefit is rolling one skill twice. Nothing on a board
    rolls that skill, so the row is finished and deliberately inert rather than
    unwritten."""


@power(
    "m6531a1",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6531a1(c: Cast) -> None:
    """Half damage except force and psychic, switched off for a turn by psychic.

    Refused in play until now, and for the right reason: laying the condition
    bare would have made the creature halve force and psychic too, which is a
    row *stronger* than its card on a defensive trait, in every fight,
    invisibly. The exception had to exist before the row could be written at
    all -- so the switch clause, which was always sayable, had nothing to
    switch off.

    Psychic is in both lists: it is excepted from the halving *and* it takes
    the trait off. Force is only excepted.
    """
    shape = c.insubstantial(
        on=c.me, until=When.ENCOUNTER,
        except_=(DamageType.FORCE, DamageType.PSYCHIC),
    )
    c.suspend_when(
        shape, DamageApplied,
        lambda ev: ev.target == c.me and DamageType.PSYCHIC in ev.types(),
        for_=When.SONT,
    )


@power(
    "m6531a2",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.ignore_squeeze_penalty()",),
)
def m6531a2(c: Cast) -> None:
    """All three halves of this row are the squeezing penalties being lifted --
    the halved speed, the -5 to attacks and the advantage granted -- and
    `Condition.SQUEEZING` carries them with nothing to switch off."""


@power(
    "m6531a3",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=5),
    damage=Damage("2d6", 3, dtype=DamageType.PSYCHIC),
)
def m6531a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(1)


@power(
    "m6531a4",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[Keyword.ILLUSION],
    out_of_combat=True,
)
def m6531a4(c: Cast) -> None:
    """A noise from a square. Nothing on a board hears, so the row is finished
    and inert rather than unwritten -- and `out_of_combat` keeps the policy from
    being offered an at-will that does nothing every single turn."""


@power(
    "m6531a5",
    level=2,
    usage=Usage.RECHARGE,
    recharge=5,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=5),
    damage=Damage("1d4", 3, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m6531a5(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.DAZED, until=When.SAVE_ENDS)
