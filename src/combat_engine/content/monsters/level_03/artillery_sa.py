"""Monster abilities, level 3, artillery: the second sweep.

Thirty stat blocks whose rows were still undeclared. `artillery.py` holds the
first sweep of this level and is not touched here; the split is by *when* the
work was done rather than by what the creatures are, and the conventions are
the ones the level-1 and level-2 sweeps settled:

* numbers load from `game.db` -- the attack line is written exactly as
  printed (`Attack(vs=AC, printed=8)`) and the damage line goes in the header
  as data, so an MM1 block can be rescaled to MM3 maths later;
* a **trait** is a row that costs no action, has no target, and arms the
  watches that hold it for the rest of the fight;
* a printed range of "20/40" takes the **normal** range, so the creature
  shoots inside the band where it has no penalty;
* a card that prints no range at all is melee 1;
* a blow of two damage types keeps the **first** in the header and carries
  the rest as keywords, which is what one `Damage` can say;
* a close burst or blast whose card names no target set takes **enemies**,
  except where the card says "creatures in the burst" outright;
* a minion's flat damage says so with `kind=MINION`, a recharge or encounter
  attack with `kind=LIMITED`.

Eight helpers are imported rather than copied -- from the level-1 and level-2
artillery sweeps, from `level_02/skirmishers.py` and from
`level_11/controllers.py`. Four printed sentences in this batch are word for
word ones those files already hold, and `_ends_its_turn_in` is the zone clause
`c.burns` does not cover.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_01.artillery_sa import (
    _any_enemy_suffering,
    _is_bloodied,
    _recharge_when_bloodied,
)
from combat_engine.content.monsters.level_01.skirmishers import _ref_of
from combat_engine.content.monsters.level_02.artillery_sa import (
    _extra_against_advantage,
    _minor_shift,
    _saves_off_prone,
    _trap_shield,
)
from combat_engine.content.monsters.level_02.skirmishers import (
    _still_hidden_on_a_miss,
)
from combat_engine.content.monsters.level_08.skirmishers import _adjacent_foe
from combat_engine.content.monsters.level_11.controllers import _ends_its_turn_in
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_CREATURE,
    EACH_ENEMY,
    EACH_OTHER,
    ENCOUNTER,
    FORT,
    FREE,
    INTERRUPT,
    MINOR,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
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
    Ranged,
    Target,
    UpTo,
    Usage,
    When,
    power,
)
from combat_engine.engine.basic import MELEE
from combat_engine.engine.components import Powers
from combat_engine.engine.dsl import use
from combat_engine.engine.events import (
    AttackRolled,
    Bloodied,
    Dropped,
    Hit,
    Moved,
    SurgeSpent,
    TurnStart,
)
from combat_engine.engine.monster_math import LIMITED, MINION
from combat_engine.engine.query import distance_between, team
from combat_engine.engine.triggers import (
    Trigger,
    about_me,
    both,
    by_me,
    by_melee,
    hits_me,
    would_hit_me,
)

#: The five types a chromatic breath is ever one of. The card says "a chosen
#: type", so the choice is made in the body and the header's damage stays
#: untyped -- the shape `m4759a3` settled one sweep down.
DRAGON_ELEMENTS = (
    DamageType.ACID,
    DamageType.COLD,
    DamageType.FIRE,
    DamageType.LIGHTNING,
    DamageType.POISON,
)

_RALLY = "allies of its own sort in the burst"
_I_AM_HIT = "an enemy's attack would hit it"


def _rally(c: Cast, kin: str, word: str = "") -> None:
    """"Allies of its own sort in the burst gain 5 temporary hit points and
    can shift 1 square." Four blocks in this batch print it.

    The restriction is on what the ally *is*, and `Target` filters on side,
    count, size and what is in hand -- so the burst takes every ally and the
    sort is asked here, with `dropped=("Target.kind",)` on each row saying
    that the offer itself is not narrowed. The side is `other_ally` and not
    `ally`: the latter's pool includes the caster, which reads as "you or one
    ally" and is wrong for a card that says only "allies". `word` is the printed creature-type
    word where the card gives one; where the card names the stat block
    instead, its ref is the only thing there is to compare.
    """
    mate = c.target
    if mate is None:
        return
    if _ref_of(c, mate) != kin and not (word and c.is_kind(word, on=mate)):
        return
    c.temp_hp(5, on=mate)
    c.shift(1, who=mate)


def _vs_opportunity(c: Cast, value: int) -> None:
    """"A +2 bonus to AC against opportunity attacks."

    `opportunity` is a key the attack context carries and `query.defence` is
    handed that same context, so this is a gate rather than a watch armed and
    disarmed around every swing.
    """
    c.bonus(
        AC, value, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: bool(ctx.get("opportunity")),
    )


def _includes_an_ally(c: Cast) -> bool:
    """Did this one use of the row catch one of its own side as well?

    `c.targets` is the whole target list of this use, so the question the
    card asks -- "+2 to the attack if it includes at least one ally" -- is
    asked of the set rather than of the creature currently being rolled
    against, and comes out the same for every one of them.
    """
    mine = set(c.allies())
    return any(who in mine for who in c.targets)


def _breath_element(c: Cast) -> DamageType:
    """"Damage of a chosen type", chosen once for the whole use."""
    return c.choose(list(DRAGON_ELEMENTS), f"{c.ref}: which element") or DamageType.FIRE


def _death_throe(c: Cast) -> None:
    """A basic attack on the way down, at whatever is standing next to it.

    **`c.basic` cannot carry this one.** It calls `dsl.use` without the
    triggering event, and `use` derives "this is a death throe" from exactly
    that event -- so the swing was refused by the ordinary "can it act?" gate
    every time, silently, which is the gate a death throe exists to be exempt
    from. Driven through the same door with `c.trigger` handed over, which is
    the only route that carries the exemption. `Powers.basic` is read rather
    than assumed, because a monster points it at one of its own rows.
    """
    foe = _adjacent_foe(c, c.ref)
    if foe is None:
        return
    known = c.world.get(c.me, Powers)
    use(
        c.world, c.me, (known.basic if known else "") or MELEE,
        targets=[foe], spend=False, trigger=c.trigger,
        granted_by=c.me, granted_via=c.ref,
    )


# --------------------------------------------------------------------------
# m1020
# --------------------------------------------------------------------------


@power(
    "m1020a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d8", 4),
)
def m1020a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1020a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d6", 2, dtype=DamageType.FIRE),
)
def m1020a1(c: Cast) -> None:
    if c.strike():
        c.hit()


# --------------------------------------------------------------------------
# m115816
# --------------------------------------------------------------------------


@power(
    "m115816a0",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m115816a0(c: Cast) -> None:
    """Ranged only -- the card narrows the exemption to a missed shot, so a
    melee swing from hiding gives the creature away as it always would."""
    _still_hidden_on_a_miss(c, ("ranged",))


@power(
    "m115816a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage(bonus=5, kind=MINION),
)
def m115816a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m115816a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage(bonus=5, dtype=DamageType.POISON, kind=MINION),
)
def m115816a2(c: Cast) -> None:
    """The critical rider is a condition rather than extra dice, so it is read
    off `c.crit` after the blow rather than written into the damage line."""
    if c.strike():
        c.hit()
        if c.crit:
            c.unconscious()


# --------------------------------------------------------------------------
# m1160
# --------------------------------------------------------------------------


@power(
    "m1160a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d8", 2),
)
def m1160a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1160a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d10", 4),
)
def m1160a1(c: Cast) -> None:
    """"Its next ranged attack against the same target" is a one-shot gated on
    two keys the attack context carries, `ranged` and `target`. `once=True`
    spends it on the shot that actually reads it, which is the only way "next"
    can be said: a plain bonus would ride every arrow for the round."""
    foe = c.target
    if foe is None or not c.strike():
        return
    c.hit()
    mates = c.within(5, side="ally")
    if not mates:
        return
    mate = c.choose(sorted(mates), f"{c.ref}: which ally takes the shot") or mates[0]
    c.bonus(
        "attack", 2, on=mate, until=When.ENCOUNTER, once=True,
        when=lambda ctx: bool(ctx.get("ranged")) and ctx.get("target") == foe,
    )


@power(
    "m1160a2",
    level=3,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is first bloodied",
    on=Trigger(Bloodied, about_me, "it is bloodied"),
)
def m1160a2(c: Cast) -> None:
    """"A saving throw against any ongoing effects it might be suffering" is
    every save-ends hold on it, one throw each -- `Effects.save` rolls,
    announces and ends, so a success really lifts the effect. The list is
    copied first because a successful throw mutates it."""
    me = c.me
    for eff in list(c.world.effects.of(me)):
        if eff.when is When.SAVE_ENDS:
            c.world.effects.save(eff)


# --------------------------------------------------------------------------
# m1222
# --------------------------------------------------------------------------


@power(
    "m1222a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d8"),
)
def m1222a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1222a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(vs=REF, printed=6),
    damage=Damage("1d10", 3, dtype=DamageType.ACID),
)
def m1222a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1222a2",
    level=3,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(10),
    target=Target("other_ally", 99, everyone=True, label=_RALLY),
    dropped=("Target.kind",),
)
def m1222a2(c: Cast) -> None:
    """The card names its own stat block, so the sort is the ref."""
    _rally(c, "m1222")


@power(
    "m1222a3",
    level=3,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.ACID],
    attack=Attack(vs=FORT, printed=6),
    damage=Damage("1d10", 3, dtype=DamageType.ACID, kind=LIMITED, half_on_miss=True),
)
def m1222a3(c: Cast) -> None:
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)


@power(
    "m1222a4",
    level=3,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m1222a4(c: Cast) -> None:
    _minor_shift(c)


# --------------------------------------------------------------------------
# m3326
# --------------------------------------------------------------------------


@power(
    "m3326a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d6", 2),
)
def m3326a0(c: Cast) -> None:
    """Two blows of different types out of one swing: the weapon dice are the
    header's data and the necrotic die is its own, so a resistance to one does
    not eat the other."""
    if c.strike():
        c.hit()
        c.damage("1d6", dtype=DamageType.NECROTIC)
        c.temp_hp(5, on=c.me)


@power(
    "m3326a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=8),
    damage=Damage("1d10", 4, dtype=DamageType.NECROTIC),
)
def m3326a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.weakened()


@power(
    "m3326a2",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=6),
    damage=Damage("2d8", dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m3326a2(c: Cast) -> None:
    """The Effect half reaches allies, who are not targets -- "affects
    enemies" is the whole target line -- so it is asked of the burst's squares
    from the first target, which is the only place it runs once."""
    if c.first:
        for mate in c.in_squares(c.area(), side="ally"):
            if c.is_kind("undead", on=mate):
                c.temp_hp(5, on=mate)
                c.shift(1, who=mate)
    if c.strike():
        c.hit()


@power(
    "m3326a3",
    level=3,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is reduced to 0 hit points",
    on=Trigger(Dropped, about_me, "it is reduced to 0 hit points"),
)
def m3326a3(c: Cast) -> None:
    _death_throe(c)


# --------------------------------------------------------------------------
# m3330
# --------------------------------------------------------------------------


@power(
    "m3330a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d6", 3),
)
def m3330a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3330a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d10", 4),
)
def m3330a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3330a2",
    level=3,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it hits an enemy",
    on=Trigger(Hit, by_me, "it hits an enemy"),
)
def m3330a2(c: Cast) -> None:
    """The card names the two weapons rather than the two rows, and this block
    has exactly one melee attack and one ranged one -- so the thrown axe is
    `m3330a0` and the bow is `m3330a1`, read off the triggering event's own
    ref. `PowerUsed` would have answered the wrong question: the extra damage
    rides the blow that landed, not the declaration."""
    ev = c.trigger
    victim = getattr(ev, "target", None)
    if victim is None or team(c.world, victim) is team(c.world, c.me):
        return
    dice = "1d10" if getattr(ev, "power", "") == "m3330a1" else "1d6"
    c.damage(dice, on=victim)


# --------------------------------------------------------------------------
# m3331
# --------------------------------------------------------------------------


@power(
    "m3331a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 2),
)
def m3331a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3331a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(2),
    keywords=[Keyword.LIGHTNING, Keyword.NECROTIC, Keyword.WEAPON],
    attack=Attack(vs=FORT, printed=8),
    damage=Damage("2d6", 3, dtype=DamageType.LIGHTNING),
)
def m3331a1(c: Cast) -> None:
    """Lightning *and* necrotic on one blow: the header keeps the first and
    the keywords carry the pair."""
    if c.strike():
        c.hit()
        c.weakened()


@power(
    "m3331a2",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(10),
    target=Target("other_ally", 99, everyone=True),
    keywords=[Keyword.NECROTIC],
)
def m3331a2(c: Cast) -> None:
    """`c.basic` needs both halves named: `who` is the ally doing the swinging
    and `on` is who it swings at, and leaving `on` off aims the ally's attack
    at `c.target` -- which here *is* the ally."""
    mate = c.target
    if mate is None:
        return
    foes = sorted(c.enemies(), key=lambda f: distance_between(c.world, mate, f))
    if foes:
        c.basic(who=mate, on=foes[0])
    c.flat(5, dtype=DamageType.NECROTIC, on=mate)


# --------------------------------------------------------------------------
# m3541
# --------------------------------------------------------------------------


@power(
    "m3541a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d10", 3),
)
def m3541a0(c: Cast) -> None:
    """Three in the header and the difference flat on top, so the card's first
    number stays the data an MM3 rescale reads."""
    if c.strike():
        c.hit()
        if c.bloodied(on=c.me):
            c.flat(2)


@power(
    "m3541a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d10", 4),
)
def m3541a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        if c.bloodied(on=c.me):
            c.flat(2)


@power(
    "m3541a2",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3541a2(c: Cast) -> None:
    """"Two or more of its allies adjacent to it" is asked of the board inside
    the gate rather than once when the trait arms: the pack moves, and a count
    taken at the start of the fight is wrong by the second round. Allies and
    not the creature itself, which the card counts separately."""

    def mobbed(ctx: dict[str, Any]) -> bool:
        foe = ctx.get("target")
        if foe is None:
            return False
        return sum(1 for mate in c.allies() if c.adjacent_to(mate, foe)) >= 2

    c.bonus("damage", 5, on=c.me, until=When.ENCOUNTER, when=mobbed)


# --------------------------------------------------------------------------
# m3975
# --------------------------------------------------------------------------


@power(
    "m3975a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 2),
)
def m3975a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.damage("1d6", dtype=DamageType.NECROTIC)


@power(
    "m3975a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=8),
    damage=Damage("1d10", 4, dtype=DamageType.NECROTIC),
)
def m3975a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.weakened()


@power(
    "m3975a2",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=6),
    damage=Damage("1d12", 3, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m3975a2(c: Cast) -> None:
    """"Toward the burst's origin square" is `anchor=c.origin` -- the square
    the area was aimed at, which is what a pull measures against."""
    if c.strike():
        c.hit()
        c.pull(1, anchor=c.origin)


@power(
    "m3975a3",
    level=3,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it drops to 0 hit points",
    on=Trigger(Dropped, about_me, "it drops to 0 hit points"),
)
def m3975a3(c: Cast) -> None:
    """The printed Requirement names the weapon on its own stat block, so it
    is satisfied by construction and there is nothing to gate: a monster
    carries what its card says it carries."""
    _death_throe(c)


# --------------------------------------------------------------------------
# m4227
# --------------------------------------------------------------------------


@power(
    "m4227a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d6", 3),
)
def m4227a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4227a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d10", 3),
)
def m4227a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4227a2",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    group="m4227 volley",
)
def m4227a2(c: Cast) -> None:
    """Two shots of the row above rather than a copy of its numbers, so one
    attack line is stated once. "Within 5 squares of each other" picks the
    second target instead of filtering the offer -- a body that gated and then
    returned would be a row that does nothing, which is what a wrong row looks
    like. The 50% is a real coin: the card hands the machine's aim to chance,
    and `c.roll` is the board's own die."""
    first = c.target
    if first is None:
        return
    c.use_power("m4227a1", on=first, spend=False)
    mates = c.within(5, of=first, side="ally")
    if mates and c.roll("1d2") == 1:
        c.use_power("m4227a1", on=sorted(mates)[0], spend=False)
        return
    pool = sorted(foe for foe in c.within(5, of=first, side="enemy") if foe != first)
    if pool:
        second = c.choose(pool, f"{c.ref}: the second shot") or pool[0]
        c.use_power("m4227a1", on=second, spend=False)


@power(
    "m4227a3",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4227a3(c: Cast) -> None:
    """The spec names the recharged power by a ref that is a *stat block*, not
    a power on this one -- an extraction slip. This creature has exactly one
    recharge row, `m4227a2`, so that is what is put back up, and the printed
    sentence is otherwise exact: the start of its own turn, an enemy within 2
    squares."""
    me = c.me

    def at_the_top(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me:
            return
        if c.within(2, side="enemy"):
            c.restore_use("m4227a2", on=me)

    c.watch(TurnStart, at_the_top, until=When.ENCOUNTER, on=me, label=f"{c.ref} rewind")


# --------------------------------------------------------------------------
# m4297
# --------------------------------------------------------------------------


@power(
    "m4297a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d6", 3),
)
def m4297a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4297a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD],
    attack=Attack(vs=REF, printed=8),
    damage=Damage("1d10", 3, dtype=DamageType.COLD),
)
def m4297a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.SAVE_ENDS)


@power(
    "m4297a2",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=FORT, printed=8),
    damage=Damage("1d10", 3, dtype=DamageType.LIGHTNING, kind=LIMITED),
)
def m4297a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)


@power(
    "m4297a3",
    level=3,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_I_AM_HIT,
    on=Trigger(AttackRolled, would_hit_me, _I_AM_HIT),
)
def m4297a3(c: Cast) -> None:
    """**The spec carries no Trigger line for this row at all** -- only the
    action cost. An immediate interrupt that raises two defences has one
    sentence it can be answering, and `AttackRolled` is the window where
    raising them still changes the outcome: `resolve.attack` reads the defence
    again after that emit. Said in the report as a gap in the extraction
    rather than left inert, which is what no `on=` would have meant."""
    c.bonus(AC, 4, on=c.me, until=When.EONT)
    c.bonus(REF, 4, on=c.me, until=When.EONT)


# --------------------------------------------------------------------------
# m4513
# --------------------------------------------------------------------------


@power(
    "m4513a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d8"),
)
def m4513a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4513a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=6),
    damage=Damage("1d10", 3, dtype=DamageType.FIRE),
)
def m4513a1(c: Cast) -> None:
    """The card prints no range on this line, so melee 1 by the convention.
    Three sibling blocks print the same attack at Ranged 10, which is noted
    rather than acted on -- a range nobody printed is not one to invent."""
    if c.strike():
        c.hit()


@power(
    "m4513a2",
    level=3,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(10),
    target=Target("other_ally", 99, everyone=True, label=_RALLY),
    dropped=("Target.kind",),
)
def m4513a2(c: Cast) -> None:
    _rally(c, "m4513")


@power(
    "m4513a3",
    level=3,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=FORT, printed=6),
    damage=Damage("10d3", 3, dtype=DamageType.FIRE, kind=LIMITED, half_on_miss=True),
)
def m4513a3(c: Cast) -> None:
    """The damage line is written exactly as printed. Ten dice of three on a
    level-3 blast is far above its siblings' and reads like a transposition,
    but the printed number is the one the card has and guessing at it is not
    this file's job."""
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)


@power(
    "m4513a4",
    level=3,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m4513a4(c: Cast) -> None:
    _minor_shift(c)


@power(
    "m4513a5",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4513a5(c: Cast) -> None:
    _trap_shield(c)


# --------------------------------------------------------------------------
# m5063
# --------------------------------------------------------------------------


@power(
    "m5063a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 6),
)
def m5063a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed()


@power(
    "m5063a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=Target("enemy", 1, label="a slowed creature"),
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=FORT, printed=8),
    damage=Damage("1d8", 6),
    requires=_any_enemy_suffering(Condition.SLOWED),
    requires_text="only against a slowed creature",
    dropped=("Target.kind",),
)
def m5063a1(c: Cast) -> None:
    """The target line restricts by what the creature is suffering, which
    `Target` cannot filter on -- so the `requires=` decides whether the row is
    offered at all and the body checks the one it was aimed at. The printed
    damage line names no type; the keyword is the card's."""
    if not c.is_(Condition.SLOWED):
        return
    if c.strike():
        c.hit()
        c.dazed(until=When.EOTNT)


@power(
    "m5063a2",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(1, 20),
    target=EACH_ENEMY,
    attack=Attack(vs=REF, printed=8),
    damage=Damage("1d8", 6, kind=LIMITED),
)
def m5063a2(c: Cast) -> None:
    """"Save ends both" is one throw for two things, so the burn and the slow
    are one effect rather than two rolled against separately."""
    if c.strike():
        c.hit()
        c.condition(
            Condition.SLOWED, until=When.SAVE_ENDS, ongoing=(5, DamageType.UNTYPED)
        )


# --------------------------------------------------------------------------
# m5070
# --------------------------------------------------------------------------


@power(
    "m5070a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage(bonus=3, dtype=DamageType.FIRE, kind=MINION),
)
def m5070a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5070a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=6),
    damage=Damage(bonus=4, dtype=DamageType.FIRE, kind=MINION),
)
def m5070a1(c: Cast) -> None:
    if c.strike():
        c.hit()


# --------------------------------------------------------------------------
# m5072
# --------------------------------------------------------------------------


@power(
    "m5072a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 3, dtype=DamageType.FIRE),
)
def m5072a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5072a1",
    level=3,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=FORT, printed=8),
    damage=Damage("1d6", 4, dtype=DamageType.FIRE, kind=LIMITED),
)
def m5072a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(2)


@power(
    "m5072a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, 20),
    target=EACH_ENEMY,
    keywords=[Keyword.FIRE, Keyword.ZONE],
    attack=Attack(vs=FORT, printed=8),
    damage=Damage("1d10", 3),
)
def m5072a2(c: Cast) -> None:
    """"Ends its turn in the zone" is the one zone clause `c.burns` does not
    cover -- that one bites on entering and on starting a turn. The Effect is
    laid from the first target, because it happens once however many creatures
    the burst caught, and the printed damage line names no type even though
    the zone's does."""
    if c.first:
        here = c.zone(c.area(), until=When.EONT, label=c.ref)
        _ends_its_turn_in(c, here, lambda who: c.flat(5, dtype=DamageType.FIRE, on=who))
    if c.strike():
        c.hit()


# --------------------------------------------------------------------------
# m5305
# --------------------------------------------------------------------------


@power(
    "m5305a0",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5305a0(c: Cast) -> None:
    _vs_opportunity(c, 2)


@power(
    "m5305a1",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5305a1(c: Cast) -> None:
    _extra_against_advantage(c, "1d6")


@power(
    "m5305a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 2),
)
def m5305a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5305a3",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=8),
    damage=Damage("1d10", 3, dtype=DamageType.PSYCHIC),
)
def m5305a3(c: Cast) -> None:
    """"Grants combat advantage" with nobody named is the whole side, so
    `to="team"` rather than the method's default of the caster alone."""
    if c.strike():
        c.hit()
        c.grants_advantage(until=When.SONT, to="team")


# --------------------------------------------------------------------------
# m5394
# --------------------------------------------------------------------------


@power(
    "m5394a0",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5394a0(c: Cast) -> None:
    _vs_opportunity(c, 2)


@power(
    "m5394a1",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5394a1(c: Cast) -> None:
    _extra_against_advantage(c, "1d6")


@power(
    "m5394a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d6", 2),
)
def m5394a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5394a3",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=8),
    damage=Damage("2d8", 3, dtype=DamageType.PSYCHIC),
)
def m5394a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.grants_advantage(until=When.SONT, to="team")


# --------------------------------------------------------------------------
# m5754
# --------------------------------------------------------------------------


@power(
    "m5754a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 6),
)
def m5754a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5754a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(vs=REF, printed=8),
    damage=Damage("1d10", 6, dtype=DamageType.ACID),
)
def m5754a1(c: Cast) -> None:
    """The two riders are an **Effect**, so they land whether the shot hit or
    not, and the "instead" is read first: a creature already slowed is dazed
    and is not slowed again."""
    if c.strike():
        c.hit()
    if c.is_(Condition.SLOWED):
        c.dazed(until=When.SAVE_ENDS)
    elif c.bloodied():
        c.slowed(until=When.EOTNT)


# --------------------------------------------------------------------------
# m5802
# --------------------------------------------------------------------------


@power(
    "m5802a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 5),
)
def m5802a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5802a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=8),
    damage=Damage("2d6", 4, dtype=DamageType.FIRE),
)
def m5802a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(
            Condition.SLOWED, until=When.SAVE_ENDS, ongoing=(2, DamageType.FIRE)
        )


@power(
    "m5802a2",
    level=3,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(1),
    target=EACH_OTHER,
    keywords=[Keyword.FIRE, Keyword.ZONE],
    attack=Attack(vs=FORT, printed=6),
    damage=Damage("1d6", 4, dtype=DamageType.FIRE, kind=LIMITED),
    dropped=("c.conceal_in()",),
)
def m5802a2(c: Cast) -> None:
    """Three of the zone's four clauses land: it lasts the encounter, it is
    difficult terrain, and it burns whatever ends its turn inside. The partial
    concealment for a creature entirely within it is the missing one -- nothing
    holds concealment per zone rather than per creature."""
    if c.first:
        here = c.zone(c.area(), until=When.ENCOUNTER, difficult=True, label=c.ref)
        _ends_its_turn_in(c, here, lambda who: c.flat(2, dtype=DamageType.FIRE, on=who))
    if c.strike():
        c.hit()


# --------------------------------------------------------------------------
# m5992
# --------------------------------------------------------------------------


@power(
    "m5992a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage(bonus=5, kind=MINION),
)
def m5992a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5992a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage(bonus=5, kind=MINION),
)
def m5992a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.SAVE_ENDS)


# --------------------------------------------------------------------------
# m6031
# --------------------------------------------------------------------------


@power(
    "m6031a0",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POISON],
)
def m6031a0(c: Cast) -> None:
    """`SurgeSpent` is emitted from every site that decrements a surge, which
    is the only place "spends a healing surge within the aura" can be seen.
    The aura is read at that moment rather than at the start of the turn."""
    c.aura(2, until=When.ENCOUNTER, label=c.ref)
    me = c.me

    def spent(ev: SurgeSpent) -> None:
        who = ev.actor
        if who == me or team(c.world, who) is team(c.world, me):
            return
        if c.in_my_aura(who, label=c.ref):
            c.weakened(on=who, until=When.EOTNT)

    c.watch(SurgeSpent, spent, until=When.ENCOUNTER, on=me, label=f"{c.ref} aura")


@power(
    "m6031a1",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6031a1(c: Cast) -> None:
    """`c.terrain` is a property of the encounter, not of anybody in it, so
    "in aquatic combat" is asked there -- without it the bonus would be live
    in every dry fight. Breathing underwater is the swim speed the database
    already carries and nothing else, so there is nothing to lay for it."""

    def submerged(ctx: dict[str, Any]) -> bool:
        foe = ctx.get("target")
        if foe is None or not c.terrain("aquatic"):
            return False
        return not c.is_kind("aquatic", on=foe)

    c.bonus("attack", 2, on=c.me, until=When.ENCOUNTER, when=submerged)


@power(
    "m6031a2",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
)
def m6031a2(c: Cast) -> None:
    """The boon goes to whoever landed the critical, so it is read off the
    `Hit` rather than asked of the board afterwards."""
    me = c.me

    def struck(ev: Hit) -> None:
        if ev.target == me and ev.critical:
            c.heal(5, on=ev.attacker)

    c.watch(Hit, struck, until=When.ENCOUNTER, on=me, label=f"{c.ref} boon")


@power(
    "m6031a3",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6031a3(c: Cast) -> None:
    """Said twice, once per printed word: `Movement.ignores` holds the sorts
    of rough ground a creature is exempt from, and the exemption here is two
    sorts and not all of them."""
    c.ignores_difficult("mud")
    c.ignores_difficult("shallow water")


@power(
    "m6031a4",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d8", 3),
)
def m6031a4(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6031a5",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=WILL, printed=8),
    damage=Damage("1d10", 4, dtype=DamageType.POISON),
)
def m6031a5(c: Cast) -> None:
    """"All creatures adjacent to the target" is `side="other"` -- everyone
    but whoever the circle is centred on, its own side included, which is what
    the card says and not what `side="enemy"` would have said."""
    if not c.strike():
        return
    c.hit()
    for who in c.within(1, of=c.target, side="other"):
        c.flat(3, dtype=DamageType.POISON, on=who)


@power(
    "m6031a6",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=[Keyword.COLD, Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=8),
    damage=Damage("2d6", 4, dtype=DamageType.COLD),
)
def m6031a6(c: Cast) -> None:
    """The second attack line is the same roll two points better when the
    blast catches one of its own, and `c.targets` is the whole target list of
    this use -- so the question is asked of the set and comes out the same for
    every creature in it. The header keeps the printed 8."""
    if c.strike(plus=2 if _includes_an_ally(c) else 0):
        c.hit()
        c.dazed()


@power(
    "m6031a7",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.FIRE, Keyword.THUNDER],
    attack=Attack(vs=REF, printed=6),
    damage=Damage("2d10", 4, dtype=DamageType.FIRE, kind=LIMITED, half_on_miss=True),
)
def m6031a7(c: Cast) -> None:
    if c.strike(plus=2 if _includes_an_ally(c) else 0):
        c.hit()
    else:
        c.hit(half=True)


# --------------------------------------------------------------------------
# m6041
# --------------------------------------------------------------------------


@power(
    "m6041a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage(bonus=5, kind=MINION),
)
def m6041a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6041a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage(bonus=5, kind=MINION),
)
def m6041a1(c: Cast) -> None:
    """"If it leaves its space" is any step at all, forced ones included, so
    the watch is on `Moved` rather than on a shift or a walk. The latch is a
    flag and not `once=True`: `once` spends the watch on the first movement by
    *anybody*, which is almost never this creature's victim."""
    foe = c.target
    if foe is None or not c.strike():
        return
    c.hit()
    paid: list[bool] = []

    def stirred(ev: Moved) -> None:
        if ev.actor == foe and not paid:
            paid.append(True)
            c.flat(2, on=foe)

    c.watch(Moved, stirred, until=When.SONT, on=c.me, label=f"{c.ref} parting shot")


# --------------------------------------------------------------------------
# m6270
# --------------------------------------------------------------------------


@power(
    "m6270a0",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6270a0(c: Cast) -> None:
    """`c.grants_in` hangs the modifier on the aura's own effect, so it dies
    with the aura. "Allies in the aura" leaves the creature itself out, which
    is what `side="ally"` means here as it does on `c.within`."""
    ring = c.aura(2, until=When.ENCOUNTER, label=c.ref)
    c.grants_in(ring, "save", 2, side="ally", kind="power")


@power(
    "m6270a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d4", 4),
)
def m6270a1(c: Cast) -> None:
    """Four in the header and the difference flat on top. The advantage is
    read off the result the swing returned, not asked of the board again: a
    one-shot grant has already been spent by then."""
    if c.strike():
        c.hit()
        if c.result is not None and c.result.advantage:
            c.flat(4)


@power(
    "m6270a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d4", 4),
)
def m6270a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        if c.result is not None and c.result.advantage:
            c.flat(4)


@power(
    "m6270a3",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("3d4", 8, kind=LIMITED),
)
def m6270a3(c: Cast) -> None:
    """The printed Effect runs before the attack, in that order: the shift,
    then the advantage, then the shot. "A target of her choice" is taken to be
    the one she then shoots -- the row has one target and nothing else on the
    card points the grant anywhere else."""
    foe = c.target
    if foe is None:
        return
    c.shift(c.speed_of())
    c.grants_advantage(on=foe, to=c.me, until=When.EONT)
    if c.strike():
        c.hit()


@power(
    "m6270a4",
    level=3,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="an enemy hits it with an attack",
    on=Trigger(AttackRolled, would_hit_me, "an enemy's attack would hit it"),
)
def m6270a4(c: Cast) -> None:
    """Declared on `AttackRolled` rather than on `Hit`, which is where a
    reroll still decides anything: `resolve.attack` recomputes the hit from the
    result after that window closes. `keep="new"` is the printed "must use the
    new result", even when it is worse."""
    c.reroll_attack(keep="new")


# --------------------------------------------------------------------------
# m6622
# --------------------------------------------------------------------------


@power(
    "m6622a0",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6622a0(c: Cast) -> None:
    c.resist_forced(1)


@power(
    "m6622a1",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6622a1(c: Cast) -> None:
    _saves_off_prone(c)


@power(
    "m6622a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d10"),
)
def m6622a2(c: Cast) -> None:
    """Two blows of different types out of one swing, so the fire is its own
    call rather than folded into the header's dice."""
    if c.strike():
        c.hit()
        c.damage("1d6", 2, dtype=DamageType.FIRE)


@power(
    "m6622a3",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=7),
    damage=Damage("1d12", 4, dtype=DamageType.LIGHTNING),
)
def m6622a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.grants_advantage(until=When.EONT, to="team")


@power(
    "m6622a4",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    attack=Attack(vs=FORT, printed=6),
    damage=Damage("1d12", 4, kind=LIMITED),
)
def m6622a4(c: Cast) -> None:
    """"Recharge when first bloodied" on top of the die the database files:
    the two only ever agree to put the row back sooner. The Effect is one step
    for one creature however many the burst caught, so it runs from the last
    target -- after the slides the Hit line owes."""
    if c.first:
        _recharge_when_bloodied(c)
    if c.strike():
        c.hit()
        c.slide(2)
        c.prone()
    if c.last:
        steppers = sorted({c.me, *c.within(1, side="ally")})
        who = c.choose(steppers, f"{c.ref}: who steps") or c.me
        c.slide(1, on=who)


# --------------------------------------------------------------------------
# m770
# --------------------------------------------------------------------------


@power(
    "m770a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d6", 4),
)
def m770a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m770a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d10", 4),
)
def m770a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m770a2",
    level=3,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(20),
    target=UpTo(2),
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d10", 4, kind=LIMITED),
)
def m770a2(c: Cast) -> None:
    """The damage line reads "each", so the row has more than one target and
    the count is not printed -- two is the smallest set that makes the word
    mean anything, and the ref'd weapon is on its own stat block so the
    Requirement is satisfied by construction."""
    if c.strike():
        c.hit()


@power(
    "m770a3",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m770a3(c: Cast) -> None:
    """"The closest enemy" is a comparison and not a creature, so ties count:
    two enemies at the same distance are both the closest, which is what the
    printed line means and what picking a single minimum would have got
    wrong."""
    me = c.me

    def nearest(ctx: dict[str, Any]) -> bool:
        foe = ctx.get("target")
        if foe is None or not ctx.get("ranged"):
            return False
        foes = c.enemies()
        if foe not in foes:
            return False
        gaps = [distance_between(c.world, me, other) for other in foes]
        return distance_between(c.world, me, foe) == min(gaps)

    c.bonus("attack", 1, on=me, until=When.ENCOUNTER, when=nearest)


# --------------------------------------------------------------------------
# m852
# --------------------------------------------------------------------------


@power(
    "m852a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 3),
)
def m852a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m852a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d10", 4),
)
def m852a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m852a2",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=REF, printed=8),
    damage=Damage("1d8", 3, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m852a2(c: Cast) -> None:
    """The card prints no range on this line, so melee 1 by the convention."""
    if c.strike():
        c.hit()
        c.slide(1)
        c.dazed()


@power(
    "m852a3",
    level=3,
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=8),
    damage=Damage("2d10", 4, kind=LIMITED),
)
def m852a3(c: Cast) -> None:
    """"Until the end of the encounter" rather than a round, and the grant is
    to this creature alone -- the card names it."""
    if c.strike():
        c.hit()
        c.grants_advantage(until=When.ENCOUNTER, to=c.me)


@power(
    "m852a4",
    level=3,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
    out_of_combat=True,
)
def m852a4(c: Cast) -> None:
    """The whole printed effect is looking like somebody else. Nothing on a
    board reads a creature's appearance, so the row is finished and
    deliberately inert rather than unwritten -- and `out_of_combat` also keeps
    the policy from taking a minor action that does nothing every turn."""


# --------------------------------------------------------------------------
# m887
# --------------------------------------------------------------------------


@power(
    "m887a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d4", 1),
)
def m887a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m887a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=10),
    damage=Damage("1d6", 2),
)
def m887a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m887a2",
    level=3,
    usage=AT_WILL,
    action=REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d6", 1),
    trigger="it is hit by a melee attack",
    on=Trigger(Hit, both(hits_me, by_melee), "it is hit by a melee attack"),
)
def m887a2(c: Cast) -> None:
    """The bite goes at whoever swung, which is read off the trigger rather
    than taken from `c.target`: an immediate action's declared target is
    chosen by the dispatcher and need not be the creature that hit it. "If the
    attacker is within reach" is the adjacency check, because a reach weapon
    can hit from further off than this can bite back."""
    foe = getattr(c.trigger, "attacker", None)
    if foe is None or not c.adjacent(foe):
        return
    if c.strike(on=foe):
        c.hit(on=foe)


@power(
    "m887a3",
    level=3,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.HEALING],
    once_per_round=True,
    requires=_is_bloodied,
    requires_text="usable only while bloodied",
)
def m887a3(c: Cast) -> None:
    """A flat number and not a surge: a monster's surge is a quarter of its
    maximum, and the card names five hit points."""
    c.heal(5, on=c.me)


# --------------------------------------------------------------------------
# m906
# --------------------------------------------------------------------------


@power(
    "m906a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 3),
)
def m906a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m906a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=6),
    damage=Damage("1d10", 3),
)
def m906a1(c: Cast) -> None:
    """"Damage of a chosen type" is a choice made at the table, so the header's
    damage line stays untyped -- it is the data a rescale reads -- and the body
    deals the typed version instead of calling `c.hit`, so nothing lands
    twice."""
    if c.strike():
        c.damage("1d10", 3, dtype=_breath_element(c))


@power(
    "m906a2",
    level=3,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(10),
    target=Target("other_ally", 99, everyone=True, label=_RALLY),
    dropped=("Target.kind",),
)
def m906a2(c: Cast) -> None:
    """This card names a creature-type word rather than its own stat block, so
    any ally of that type counts -- and the creature's own kin do by ref,
    whether the database carries the word for them or not."""
    _rally(c, "m906", "kobold")


@power(
    "m906a3",
    level=3,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    attack=Attack(vs=FORT, printed=6),
    damage=Damage("3d6", 3, kind=LIMITED, half_on_miss=True),
)
def m906a3(c: Cast) -> None:
    """One type for the whole blast, chosen once and then applied to every
    creature in it -- so the loop runs from the first target rather than asking
    again per target and dealing three different kinds of damage out of one
    printed sentence."""
    if not c.first:
        return
    element = _breath_element(c)
    for foe in list(c.targets):
        if c.strike(on=foe):
            c.damage("3d6", 3, dtype=element, on=foe)
        else:
            c.half_damage("3d6", 3, dtype=element, on=foe)


@power(
    "m906a4",
    level=3,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m906a4(c: Cast) -> None:
    _minor_shift(c)


@power(
    "m906a5",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m906a5(c: Cast) -> None:
    _trap_shield(c)


# --------------------------------------------------------------------------
# m913
# --------------------------------------------------------------------------


@power(
    "m913a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d8"),
)
def m913a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m913a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD],
    attack=Attack(vs=REF, printed=6),
    damage=Damage("1d10", 3, dtype=DamageType.COLD),
)
def m913a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m913a2",
    level=3,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(10),
    target=Target("other_ally", 99, everyone=True, label=_RALLY),
    dropped=("Target.kind",),
)
def m913a2(c: Cast) -> None:
    _rally(c, "m913")


@power(
    "m913a3",
    level=3,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.COLD],
    attack=Attack(vs=FORT, printed=6),
    damage=Damage("1d10", 3, dtype=DamageType.COLD, kind=LIMITED, half_on_miss=True),
)
def m913a3(c: Cast) -> None:
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)


@power(
    "m913a4",
    level=3,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m913a4(c: Cast) -> None:
    _minor_shift(c)


@power(
    "m913a5",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m913a5(c: Cast) -> None:
    _trap_shield(c)


# --------------------------------------------------------------------------
# m935
# --------------------------------------------------------------------------


@power(
    "m935a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 3),
)
def m935a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m935a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d6", 3),
)
def m935a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m935a2",
    level=3,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=REF, printed=8),
    damage=Damage("1d8", 2, kind=LIMITED, half_on_miss=True),
)
def m935a2(c: Cast) -> None:
    """A miss is its own pair of clauses, lighter in both halves. "Save ends
    both" either way, so each is one effect carrying the burn rather than two
    rolled against separately."""
    if c.strike():
        c.hit()
        c.condition(
            Condition.DAZED, until=When.SAVE_ENDS, ongoing=(5, DamageType.POISON)
        )
    else:
        c.hit(half=True)
        c.condition(
            Condition.SLOWED, until=When.SAVE_ENDS, ongoing=(2, DamageType.POISON)
        )


@power(
    "m935a3",
    level=3,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m935a3(c: Cast) -> None:
    _minor_shift(c)


@power(
    "m935a4",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m935a4(c: Cast) -> None:
    _trap_shield(c)
