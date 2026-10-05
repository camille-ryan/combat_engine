"""Monster abilities, level 1, controllers: the second sweep.

Five stat blocks whose rows were still undeclared -- two ooze minions, an
elite leader, a solo and a tiny fey. `controllers.py` holds the first sweep of
this level; the split is by *when* the work was done rather than by what the
creatures are, and the conventions are the ones that file settled:

* numbers load from `game.db` -- the attack line is written exactly as
  printed (`Attack(vs=WILL, printed=5)`) and the damage line goes in the
  header as data, so an MM1 block can be rescaled to MM3 maths later;
* a **trait** is a row that costs no action, has no target, and arms the
  watches that hold it for the rest of the fight;
* a printed target restriction that is about what a creature is *suffering*
  -- "an immobilized creature", "a dazed creature", "an enemy grabbed by it"
  -- is asked in the body, because `Target` filters on side and size and
  nothing else. `label=` records it for the card, and the gap is named for what
  the line actually asks: `Target.condition` for "an immobilized creature",
  `Target.ident` where the line narrows to a stat block. **"An enemy grabbed
  by it" is no longer one of them** -- `Target.relation` is a real field now,
  so that line is the target line itself and carries no marker (#401);
* a row that recharges on a printed condition rather than on a die keeps the
  die in the header, because that is what `actions.recharge` rolls and what
  the card shows, and arms the condition on top of it.
"""

from __future__ import annotations

from combat_engine.content.monsters.level_01.artillery_sa import (
    _any_enemy_suffering,
    _cheb,
)
from combat_engine.content.monsters.level_01.skirmishers import _ref_of
from combat_engine.content.monsters.level_02.skirmishers import _hides_with_cover
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_ALLY,
    EACH_ENEMY,
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
    STANDARD,
    WILL,
    ActionType,
    Attack,
    Cast,
    CloseBurst,
    Condition,
    Damage,
    DamageType,
    Keyword,
    Melee,
    Ranged,
    Relation,
    Target,
    UpTo,
    Usage,
    When,
    power,
)
from combat_engine.engine.events import (
    Bloodied,
    DamageApplied,
    Dropped,
    Miss,
    Moved,
    MoveEnd,
)
from combat_engine.engine.monster_math import LIMITED, MINION
from combat_engine.engine.triggers import Trigger, about_me, enemy_within, targets_me

#: The stat block this one spawns and commands. The card's own sentence gives
#: no id for it; the row that orders one about does, and it is the only thing
#: in either sentence that names a creature.
_SPAWN = "m5867"


def _mirror_images(c: Cast, bonus: int, step: int) -> None:
    """A power bonus to AC that each miss wears down by one image.

    Ended and re-applied rather than edited in place: two bonuses of the same
    `kind` do not stack and the larger wins, so laying three separate `+2`s
    would come to `+2` forever and look exactly like a working defence. The
    watch outlives the hold it manages, which is why it is armed against the
    encounter rather than off the bonus's own duration.
    """
    me, ref = c.me, c.ref
    held = [c.bonus(AC, bonus, kind="power", until=When.ENCOUNTER, on=me)]
    left = [bonus]

    def faded(ev: Miss) -> None:
        if ev.target != me or held[0] is None:
            return
        c.world.effects.end(held[0], ref)
        left[0] -= step
        held[0] = (
            c.bonus(AC, left[0], kind="power", until=When.ENCOUNTER, on=me)
            if left[0] > 0
            else None
        )

    c.watch(Miss, faded, until=When.ENCOUNTER, on=me, label=f"{ref} images")


# --------------------------------------------------------------------------
# m4452
# --------------------------------------------------------------------------


def _not_grabbing(world: object, eid: int) -> bool:
    """Is this creature holding nobody?

    `holds_somebody` is the same question the later fighter books keep asking,
    already written for a `requires=` gate -- which is why it takes a `World`
    and an eid rather than a `Cast`. Reused rather than rewritten.

    The first version of this imported `query.grabbing`, which does not exist:
    `query` has no grab helper at all, only `Cast` does. The audit caught it as
    an `ImportError` rather than as a wrong answer, which is the lucky half of
    that mistake.
    """
    from combat_engine.content.powers.fighter.holds import holds_somebody

    return not holds_somebody(world, eid)  # type: ignore[arg-type]


def _has_a_hold(world: object, eid: int) -> bool:
    """The other half of the same question, for the follow-up that needs one.

    Asked as a Requirement as well as in the body: without it the row is
    offered every turn, resolves against whoever happens to be nearest and does
    nothing at all, which is indistinguishable from a wrong row.
    """
    from combat_engine.content.powers.fighter.holds import holds_somebody

    return bool(holds_somebody(world, eid))  # type: ignore[arg-type]


@power(
    "m4452a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage(bonus=4, kind=MINION),
    requires=_not_grabbing,
    requires_text="must not be grabbing an enemy",
)
def m4452a0(c: Cast) -> None:
    """"Pulled adjacent" is a pull of whatever the gap happens to be, not of a
    fixed number -- reach 2 means the gap is one or two."""
    if not c.strike():
        return
    c.hit()
    c.grab()
    c.pull(max(0, c.distance() - 1))


@power(
    "m4452a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=Target(
        side="enemy", count=1, label="enemy grabbed by it",
        relation=Relation.GRABBED_BY,
    ),
    attack=Attack(vs=FORT, printed=5),
    damage=Damage(bonus=2, kind=MINION),
)
def m4452a1(c: Cast) -> None:
    """The shift comes before the slide, because the square the target is slid
    to has to be adjacent to wherever the creature ended up."""
    if not c.strike():
        return
    c.hit()
    c.shift(1)
    c.slide(1)


@power(
    "m4452a2",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4452a2(c: Cast) -> None:
    c.ignores_difficult()


# --------------------------------------------------------------------------
# m4453
# --------------------------------------------------------------------------


@power(
    "m4453a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(vs=FORT, printed=4),
    damage=Damage(bonus=3, dtype=DamageType.ACID, kind=MINION),
)
def m4453a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(2)


@power(
    "m4453a1",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4453a1(c: Cast) -> None:
    c.ignores_difficult()


# --------------------------------------------------------------------------
# m4760
# --------------------------------------------------------------------------


@power(
    "m4760a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(3),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=5),
    damage=Damage("1d6", 3),
)
def m4760a0(c: Cast) -> None:
    """Two at a time is the printed ceiling, so the grab is skipped rather than
    the attack refused when both hands are full."""
    if not c.strike():
        return
    c.hit()
    if len(c.grabbing()) < 2:
        c.grab()


@power(
    "m4760a1",
    level=1,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Melee(10),
    target=Target(side="other_ally", count=1, label=f"{_SPAWN} ally"),
    dropped=("Target.ident",),
)
def m4760a1(c: Cast) -> None:
    """`c.grant_attack` rather than `c.basic`, because the +2 and the swing are
    one printed clause and a bonus laid afterwards is read by the next attack
    instead of by this one. Which stat block the ally has to be off is recorded
    in `label=` and is the gap: it is counted by `Ident.ref` and `Target` has
    nowhere to ask it, so the symbol is `Target.ident`."""
    friend = c.target
    if friend is None:
        return
    reachable = [f for f in c.enemies() if c.adjacent_to(f, friend)]
    if not reachable:
        return
    victim = c.choose(reachable, "who the ally swings at") or reachable[0]
    c.grant_attack(friend, on=victim, attack_bonus=2)


@power(
    "m4760a2",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(10),
    target=UpTo(2, "any"),
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=5),
    damage=Damage("1d6", 3, dtype=DamageType.PSYCHIC),
)
def m4760a2(c: Cast) -> None:
    """"One or two creatures", not enemies: the card names no side."""
    if c.strike():
        c.hit()
        c.dazed(until=When.EONT)


@power(
    "m4760a3",
    level=1,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=5),
    damage=Damage("1d6", 3, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m4760a3(c: Cast) -> None:
    """The printed recharge is "when it has none of its spawn left", which is
    asked of the board whenever anything drops; the 6+ in the header is what
    the database files and the two only ever agree to make the row available
    sooner.

    "A creature the m4760 chooses" is the chooser, not the target, so the
    options are gathered round the creature being commanded and the decision is
    this one's.
    """
    me, ref = c.me, c.ref

    def counted(ev: Dropped) -> None:
        if not any(_ref_of(c, a) == _SPAWN for a in c.allies()):
            c.restore_use(ref, on=me)

    c.watch(Dropped, counted, until=When.ENCOUNTER, on=me, label=f"{ref} recharge")
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    nearby = [x for x in c.within(1, of=victim) if x != victim]
    if nearby:
        chosen = c.choose(nearby, "who it is made to swing at") or nearby[0]
        c.grant_attack(victim, on=chosen)


@power(
    "m4760a4",
    level=1,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=CloseBurst(5),
    target=NO_TARGET,
    keywords=[Keyword.SUMMONING],
)
def m4760a4(c: Cast) -> None:
    """Four at most, and six alive at most, so the loop counts both ceilings
    rather than minting a fixed four. `c.summon` is the verb that puts a
    creature on the board **and** in the initiative order, which is how every
    summon in the tree is written."""
    standing = sum(1 for a in c.allies() if _ref_of(c, a) == _SPAWN)
    made = 0
    for square in sorted(c.area()):
        if made >= 4 or standing + made >= 6:
            break
        if not c.world.grid.passable(square):
            continue
        if c.world.grid.occupant(square) is not None:
            continue
        if c.summon(_SPAWN, at=square):
            made += 1


@power(
    "m4760a5",
    level=1,
    usage=Usage.RECHARGE,
    action=FREE,
    reach=CloseBurst(10),
    target=EACH_ALLY,
    trigger="it is damaged by an attack",
    on=Trigger(DamageApplied, targets_me, "it is damaged"),
)
def m4760a5(c: Cast) -> None:
    """No die in the header, deliberately: the card prints a condition and no
    6+, so the only route back is the watch below, and a number here would
    hand the row back on a roll the card never offers.

    Minions are left out, which the target line says and `Target` cannot.
    """
    me, ref = c.me, c.ref

    def fell(ev: Dropped) -> None:
        if _ref_of(c, ev.actor) == "m3101":
            c.restore_use(ref, on=me)

    if c.first:
        c.watch(Dropped, fell, until=When.ENCOUNTER, on=me, label=f"{ref} recharge")
    if c.is_minion():
        return
    c.temp_hp(10)
    c.bonus("attack", 1, until=When.EONT)


@power(
    "m4760a6",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4760a6(c: Cast) -> None:
    """Asked inside the gate rather than once when the trait arms: the creature
    is not bloodied at the start of the fight and a bonus fixed then would
    never arrive."""
    c.bonus(
        "damage", 4, until=When.ENCOUNTER, on=c.me,
        when=lambda ctx: c.bloodied(c.me),
    )


@power(
    "m4760a7",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4760a7(c: Cast) -> None:
    c.threatens(3)


# --------------------------------------------------------------------------
# m5423
# --------------------------------------------------------------------------


@power(
    "m5423a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d6", 5),
)
def m5423a0(c: Cast) -> None:
    """The Effect is before the attack and it is the creature's own step, so it
    happens whether anything is hit."""
    if c.first:
        c.shift(1)
    if c.strike():
        c.hit()


@power(
    "m5423a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage("2d6", 5),
)
def m5423a1(c: Cast) -> None:
    """The slide is the Effect and lands before the roll, so it drags the
    target into reach rather than rewarding a hit."""
    c.slide(1)
    if c.strike():
        c.hit()


@power(
    "m5423a2",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5423a2(c: Cast) -> None:
    """Both rows used at this one's action cost, each picking its own target
    exactly as it would on an ordinary turn -- which is what `c.use_power`
    with no `on` is for, and what "uses both" means on a card that names no
    target of its own."""
    c.use_power("m5423a0")
    c.use_power("m5423a1")


@power(
    "m5423a3",
    level=1,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR, Keyword.ILLUSION],
    attack=Attack(vs=WILL, printed=4),
)
def m5423a3(c: Cast) -> None:
    """No damage at all -- the whole of the hit is the two holds, which is why
    there is no damage line in the header to apply."""
    if c.strike():
        c.dazed(until=When.EONT)
        c.slowed(until=When.EONT)


@power(
    "m5423a4",
    level=1,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Ranged(10),
    target=Target(side="enemy", count=2, label="dazed creature"),
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=4),
    damage=Damage("1d6", 5, dtype=DamageType.PSYCHIC),
    requires=_any_enemy_suffering(Condition.DAZED),
    requires_text="must have a dazed creature to aim at",
    dropped=("Target.condition",),
)
def m5423a4(c: Cast) -> None:
    """The restriction is asked in the body, since `Target` filters on side and
    size and not on what a creature is suffering; the loss is that the action
    menu offers the row against anybody."""
    if not c.is_(Condition.DAZED):
        return
    if c.strike():
        c.hit()
        c.immobilized(until=When.EONT)
        c.penalty("attack", 2, until=When.EONT)


@power(
    "m5423a5",
    level=1,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=Melee(2),
    target=NO_TARGET,
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d8", 5),
    trigger="an enemy moves without teleporting to a square within 2 squares of it",
    on=Trigger(
        MoveEnd,
        lambda world, me, ev: (
            getattr(ev, "kind_", "") != "teleport" and enemy_within(2)(world, me, ev)
        ),
        "an enemy moves into reach",
    ),
)
def m5423a5(c: Cast) -> None:
    """`MoveEnd`, not `MoveStart`, because the printed condition is about where
    the enemy has *arrived*: a reaction declared on the start of the move
    resolves where nothing has happened yet and the square two away is still
    empty. The cost in the header is the printed interrupt either way."""
    foe = getattr(c.trigger, "actor", None)
    if foe is None:
        return
    if c.strike(on=foe):
        c.hit(on=foe)
        c.prone(on=foe)


@power(
    "m5423a6",
    level=1,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it first becomes bloodied",
    on=Trigger(Bloodied, about_me, "it is bloodied"),
)
def m5423a6(c: Cast) -> None:
    """`c.restore_use` then `c.use_power`: the card hands the burst back and
    fires it in one free action, and spending the restored use is what makes
    the row cost something afterwards."""
    c.restore_use("m5423a3", on=c.me)
    c.use_power("m5423a3")


# --------------------------------------------------------------------------
# m6552
# --------------------------------------------------------------------------


@power(
    "m6552a0",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6552a0(c: Cast) -> None:
    """The printed line lowers what hiding *requires*. There is no requirement
    in the engine to lower and no check to roll, so what is left that can be
    said is the consequence: wherever it could try, it has, asked again at the
    top of each of its own turns."""
    _hides_with_cover(c)


@power(
    "m6552a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d6", 6),
)
def m6552a1(c: Cast) -> None:
    """Read off the roll that just happened rather than asked of the board
    again: a one-shot grant of combat advantage has already been spent by the
    time the hit is announced."""
    if not c.strike():
        return
    if c.result is not None and c.result.advantage:
        c.damage("2d6", 6)
    else:
        c.hit()
    c.slide(1)


@power(
    "m6552a2",
    level=1,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
)
def m6552a2(c: Cast) -> None:
    c.teleport(10)


@power(
    "m6552a3",
    level=1,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=4),
)
def m6552a3(c: Cast) -> None:
    """"Moves more than half its speed" is counted a step at a time off
    `Moved`, the only movement event carrying both ends of a step, and the
    tally belongs to one round -- the printed sentence is about a move, not
    about the whole fight, so it resets when the round does rather than
    accumulating until the target happens to have walked six squares in total.

    One watch, so there is one saving throw, which is what "(save ends)" says.
    """
    if not c.strike():
        return
    victim = c.target
    if victim is None:
        return
    tally = {"round": -1, "squares": 0}

    def stepped(ev: Moved) -> None:
        if ev.actor != victim:
            return
        if tally["round"] != c.world.round:
            tally["round"] = c.world.round
            tally["squares"] = 0
        tally["squares"] += _cheb(ev.from_, ev.to)
        if tally["squares"] > max(1, c.speed_of(victim) // 2):
            tally["squares"] = 0
            c.prone(on=victim)

    c.watch(
        Moved, stepped, until=When.SAVE_ENDS, on=victim, label=f"{c.ref} unsteady",
    )


@power(
    "m6552a4",
    level=1,
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ILLUSION],
    out_of_combat=True,
)
def m6552a4(c: Cast) -> None:
    """A noise from somewhere else, and an Insight check to disbelieve it. No
    attack, no hold, no movement -- nothing in a fight turns on where a sound
    came from, so this is deliberately inert rather than unwritten."""


@power(
    "m6552a5",
    level=1,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ILLUSION],
)
def m6552a5(c: Cast) -> None:
    """"Otherwise the effect lasts for 1 hour" is the encounter, which is
    shorter than an hour in every fight there is."""
    _mirror_images(c, 6, 2)
