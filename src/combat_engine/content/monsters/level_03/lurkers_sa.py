"""Monster abilities, level 3, lurkers: the second sweep.

Seventeen of the twenty-five stat blocks in this role print rows; the other
eight print none at all and have nothing to decorate. Two of the seventeen are
solos and one is an elite, so the file runs long for its count.

The conventions are the ones the level 1 and 2 sweeps settled, and four of
them do most of the work here:

* **numbers load from `game.db`** -- the attack line is written exactly as
  printed (`Attack(vs=AC, printed=8)`) and the damage line goes in the header
  as data so an MM1 block can be rescaled later. A row with a *second*
  damage expression -- "1d6 + 4, or 4d6 + 8 if it was hidden" -- keeps the
  plain one in the header and writes the other branch out, because one
  expression cannot say both;
* **combat advantage is read off the roll**, never asked of the board
  afterwards: `resolve.attack` clears `HIDDEN_FROM` the moment the attack is
  over, which is exactly the creature a lurker's rider is written for;
* **a row that answers its own Trigger declares `target=NO_TARGET`** and aims
  at the creature the trigger names. `ONE_CREATURE` would let the engine pick
  somebody the card never mentions;
* **a printed target restriction about what a creature is suffering** is
  asked in the body, recorded in `label=`, and marked for the gap it actually
  has -- `Target.relation` for "grabbed by it" or "cannot see it",
  `Target.condition` for a condition, `Target.ongoing` for ongoing damage --
  because `Target` filters on side and size and nothing else.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.content.monsters.level_01.artillery_sa import _sure_footed_shift
from combat_engine.content.monsters.level_02.lurkers_sa import (
    _edge_damage,
    _is_adjacent,
    _melee_blow,
    _reach_kind,
    _triggering_enemy,
)
from combat_engine.content.monsters.level_02.skirmishers import _conceal, _had_advantage
from combat_engine.content.monsters.level_03.skirmishers import (
    _free_square_beside,
    _is_bloodied,
    _not_grabbing,
    _poisoned,
    _recharge_on,
    _vanish_until_it_swings,
)
from combat_engine.content.monsters.level_03.skirmishers_sa import _while_bloodied
from combat_engine.content.powers.fighter.holds import release
from combat_engine.engine import (
    AC,
    AT_WILL,
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
    AreaBurst,
    Attack,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    Cover,
    Damage,
    DamageType,
    Keyword,
    Melee,
    Ranged,
    Relation,
    Square,
    Target,
    UpTo,
    Usage,
    When,
    World,
    power,
    spread,
)
from combat_engine.engine.events import (
    AttackDeclared,
    AttackRolled,
    Bloodied,
    DamageApplied,
    Escaped,
    Hit,
    Miss,
    TurnEnd,
    TurnStart,
)
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import (
    cover_between,
    moving_as,
    squares,
)
from combat_engine.engine.triggers import Trigger, about_me, both, by_melee, by_ranged, targets_me

# -- what the blocks in this file share -------------------------------------


def _repeat(c: Cast, ref: str, times: int) -> None:
    """"It makes two claw attacks", for any number of swings.

    `UpTo(n)` lets the chooser spread them and the rest are added when it did
    not, so a lone enemy is not clawed once by a card that says twice.
    """
    c.use_power(ref, on=c.target)
    if c.last:
        for _ in range(max(0, times - len(c.targets))):
            c.use_power(ref, on=c.target)


def _watch_its_turn(
    c: Cast, settle: Callable[[bool, Square | None], None]
) -> None:
    """Call `settle(attacked, started_at)` at the end of each of its own turns.

    Two blocks here print "ends a turn in which it did not attack", and the
    only place that can be known is a latch set by the attack roll and read at
    `TurnEnd` -- nothing on the turn events says what the creature did. The
    square it began in is kept for the other half of one of the two cards,
    "moves at least 3 squares from its starting position".
    """
    me = c.me
    state: dict[str, Any] = {"swung": False, "from": c.here}

    def began(ev: TurnStart) -> None:
        if ev.actor == me and not ev.ghost:
            state["swung"] = False
            state["from"] = c.here

    def swung(ev: AttackRolled) -> None:
        if ev.attacker == me:
            state["swung"] = True

    def ended(ev: TurnEnd) -> None:
        if ev.actor == me and not ev.ghost:
            settle(bool(state["swung"]), state["from"])

    label = f"{c.ref} turn"
    c.watch(TurnStart, began, until=When.ENCOUNTER, on=me, label=label)
    c.watch(AttackRolled, swung, until=When.ENCOUNTER, on=me, label=label)
    c.watch(TurnEnd, ended, until=When.ENCOUNTER, on=me, label=label)


def _slip_out_of_sight(c: Cast, until: When) -> None:
    """Hide from every enemy whose line to the creature is broken.

    `_conceal` is the same walk but holds until the end of the encounter;
    these two cards both name a duration, so the relation is set here with it.
    """
    for foe in c.enemies():
        if not c.is_hidden(from_=foe) and cover_between(c.world, foe, c.me) is not Cover.NONE:
            c.hide(from_=foe, until=until)


def _lingering_field(c: Cast, amount: int, *, until: When) -> int:
    """A patch of ground that burns whoever is in it **or beside it**.

    `c.hazard` holds the entering and the starting-inside halves and the
    once-per-turn latch. The ring outside it is a second watch, because a
    zone pays out for its own squares and "adjacent to the area" is not one
    of them.
    """
    area = frozenset(c.area())
    zone = c.hazard(area, amount, until=until, blocks_sight=True)
    ring = spread(area, 1) - area
    me, ref = c.me, c.ref

    def at_the_top(ev: TurnStart) -> None:
        who = ev.actor
        if ev.ghost or who == me or not ring & squares(c.world, who):
            return
        c.flat(amount, on=who)

    c.watch(TurnStart, at_the_top, until=until, on=me, label=f"{ref} ring")
    return zone


def _grabbed_by_me(c: Cast) -> Callable[[dict[str, Any]], bool]:
    """"While the target remains grabbed", as the gate a modifier is read
    through -- whom it holds changes between one attack and the next, so this
    cannot be a plain duration."""
    me = c.me

    def gate(_ctx: dict[str, Any]) -> bool:
        return bool(c.grabbing(of=me))

    return gate


def _restricted_to(c: Cast, reach: int, test: Callable[[int], bool]) -> int | None:
    """The target the printed line allows, choosing one where the engine did not.

    `Target` filters on side, count and size and not on what a creature is
    suffering, so the chooser may hand a row somebody its own target line
    forbids. The restriction is enforced here -- and where another creature in
    reach *does* qualify the row is aimed there rather than thrown away, which
    is what the filter would have done. The gap is named per row -- it is
    `Target.relation`, `Target.condition`, `Target.bloodied`,
    `Target.creature_kind`, `Target.ongoing` or `Target.ident` -- because one
    symbol standing for all six could not go green correctly for any of them.

    **The first branch used to skip the reach test.** It returned the chooser's
    pick on the strength of `test` alone, while the fallback below checks
    `c.distance(f) <= reach` -- so a target handed in from outside
    `candidates()` was accepted at any distance, which is #381's path exactly.
    `candidates()` normally guarantees reach, so this only bit a row fired with
    an explicit target or one where something moved between the offer and the
    body. One line, and about 160 rows call this.
    """
    foe = c.target
    if foe is not None and test(foe) and c.distance(foe) <= reach:
        return foe
    return next((f for f in c.enemies() if test(f) and c.distance(f) <= reach), None)


def _my_captive_escaped(world: World, me: int, ev: Any) -> bool:
    """`Escaped` names the struggling creature in `actor` and the grabber in
    `holder`, and is emitted for a failed attempt too -- so a row about *its*
    grabs gates on both fields and not on `actor`."""
    return getattr(ev, "holder", None) == me and bool(getattr(ev, "success", False))


def _stepped_from(c: Cast, was: Square | None) -> int:
    """How far the creature actually moved, for a card that pulls "the same
    number of squares"."""
    if was is None:
        return 0
    here = c.here
    return max(abs(here[0] - was[0]), abs(here[1] - was[1]))


# --------------------------------------------------------------------------
# m115799
# --------------------------------------------------------------------------


@power(
    "m115799a0",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m115799a0(c: Cast) -> None:
    """`opportunity` is in the defence context for exactly this sentence, so
    the bonus is one gated modifier rather than a watch on every swing."""
    c.bonus(AC, 2, on=c.me, until=When.ENCOUNTER, when=lambda ctx: bool(ctx.get("opportunity")))


@power(
    "m115799a1",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m115799a1(c: Cast) -> None:
    """Hidden per creature, not concealed: the card says "from that creature",
    and cover is a fact about two positions, both of which move. There is no
    Stealth check to roll -- the printed line lowers what hiding requires and
    what is left to say is the consequence."""

    def settle(swung: bool, _was: Square | None) -> None:
        if not swung:
            _slip_out_of_sight(c, When.EONT)

    _watch_its_turn(c, settle)


@power(
    "m115799a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 4),
)
def m115799a2(c: Cast) -> None:
    """"Was hidden from the target **when it attacked**" has to be asked before
    the swing: the attack is what gives it away, and by the time there is a hit
    to read the relation has already been cleared."""
    foe = c.target
    unseen = foe is not None and c.is_hidden(from_=foe)
    if c.strike():
        if unseen:
            c.damage("4d6", 8)
        else:
            c.hit()


@power(
    "m115799a3",
    level=3,
    usage=AT_WILL,
    action=MINOR,
    reach=AreaBurst(1, 10),
    target=NO_TARGET,
    keywords=[Keyword.ZONE],
)
def m115799a3(c: Cast) -> None:
    """The zone is laid; what is dropped is the *level* of obscurity. "Lightly
    obscured" is concealment for whoever is inside, and `c.zone` has terrain
    that blocks sight outright or terrain that does nothing in between."""
    c.zone(c.area(), label=c.ref, until=When.EONT, obscured="dim")


# --------------------------------------------------------------------------
# m1418
# --------------------------------------------------------------------------


@power(
    "m1418a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 4),
)
def m1418a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1418a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d6", 4),
)
def m1418a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1418a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=UpTo(2),
)
def m1418a2(c: Cast) -> None:
    """`c.use_power` runs the claw at this row's action cost, so the pair are
    the *same* attacks the creature makes on its own and every rider that reads
    one still fires."""
    _repeat(c, "m1418a1", 2)


@power(
    "m1418a3",
    level=3,
    usage=AT_WILL,
    action=REACTION,
    reach=Ranged(20),
    target=NO_TARGET,
    attack=Attack(vs=REF, printed=6),
    damage=Damage("1d6", 1),
    trigger="an enemy attacks it with a ranged attack",
    on=Trigger(
        AttackDeclared,
        both(targets_me, by_ranged),
        "an enemy attacks it with a ranged attack",
    ),
)
def m1418a3(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is not None and c.strike(on=foe):
        c.hit(on=foe)
        c.blinded(until=When.EONT, on=foe)


@power(
    "m1418a4",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_OTHER,
    keywords=[Keyword.ZONE],
    attack=Attack(vs=FORT, printed=6),
    damage=Damage("2d8", 2, kind=LIMITED),
    dropped=("c.zone(exempt=)",),
)
def m1418a4(c: Cast) -> None:
    """What is dropped is the exemption: the cloud blocks line of sight for
    every creature **except this one**, and `c.zone(blocks_sight=)` is terrain
    that blinds both sides with nothing to carve out."""
    if c.first:
        _lingering_field(c, 5, until=When.EONT)
    if c.strike():
        c.hit()


@power(
    "m1418a5",
    level=3,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is first bloodied",
    on=Trigger(Bloodied, about_me, "it is first bloodied"),
)
def m1418a5(c: Cast) -> None:
    """Hands the recharge row a use back and spends it immediately, which is
    both printed clauses. `c.use_power` runs it at this row's cost."""
    c.restore_use("m1418a4", on=c.me)
    c.use_power("m1418a4")


@power(
    "m1418a6",
    level=3,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=6),
    dropped=("c.aftereffect()",),
)
def m1418a6(c: Cast) -> None:
    """The stun is exact. The aftereffect -- a second, lesser effect that lands
    when the first one ends -- has nothing to hang from: an effect's end is not
    an event a row can answer and `Effect.on_end` is not reachable from a save."""
    if c.strike():
        c.stunned(until=When.EONT)


@power(
    "m1418a7",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POLYMORPH],
    damage=Damage("1d6", 4, kind=LIMITED),
)
def m1418a7(c: Cast) -> None:
    """`c.overrun` is the only op that walks *through* occupied squares and
    says who was in them; `c.move` refuses one and reports nothing. The printed
    word is "shifts", so the step provokes where the card would not -- the
    alternative is a row that never touches anybody, which is what the whole
    sentence is about."""
    for who in c.overrun():
        c.hit(on=who)
        c.blinded(until=When.SAVE_ENDS, on=who)


@power(
    "m1418a8",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1418a8(c: Cast) -> None:
    """Held as a gated damage modifier, so it reads the advantage off the blow
    being dealt rather than asking the board once it is over."""
    _edge_damage(c)


# --------------------------------------------------------------------------
# m3118
# --------------------------------------------------------------------------


def _was_burrowing(world: World, eid: int) -> bool:
    """"Use only after it emerges after burrowing." `moving_as` is what the
    creature is doing *now*, held past the end of the move, so the turn it
    comes up out of the ground is the turn this is true."""
    return moving_as(world, eid, "burrow")


@power(
    "m3118a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d8", 4),
)
def m3118a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3118a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d8", 5),
    requires=_was_burrowing,
    requires_text="usable only after it comes up out of the ground",
)
def m3118a1(c: Cast) -> None:
    if c.strike():
        c.hit()


# --------------------------------------------------------------------------
# m3190
# --------------------------------------------------------------------------


@power(
    "m3190a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(0),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD, Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=6),
    damage=Damage("1d6", 3, dtype=DamageType.NECROTIC),
)
def m3190a0(c: Cast) -> None:
    """Reach 0 is the printed number and is written as such: an insubstantial
    thing of this size attacks whatever shares its square, and `Melee(1)`
    would hand it a square of reach the card does not give it."""
    if c.strike():
        c.hit()
        c.slowed(until=When.EOTNT)


@power(
    "m3190a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_OTHER,
    keywords=[Keyword.COLD],
    attack=Attack(vs=FORT, printed=4),
    damage=Damage("1d6", 3, dtype=DamageType.COLD),
)
def m3190a1(c: Cast) -> None:
    """`EACH_CREATURE` and not `EACH_ENEMY`: this burst prints no "targets
    enemies" line, so it catches whatever is standing in it."""
    if c.strike():
        c.hit()
        c.vulnerable(3, DamageType.COLD, until=When.SAVE_ENDS)


@power(
    "m3190a2",
    level=3,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
)
def m3190a2(c: Cast) -> None:
    _vanish_until_it_swings(c, When.EONT)


# --------------------------------------------------------------------------
# m3327
# --------------------------------------------------------------------------


@power(
    "m3327a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 4),
)
def m3327a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3327a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(3),
)
def m3327a1(c: Cast) -> None:
    _repeat(c, "m3327a0", 3)


@power(
    "m3327a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_OTHER,
    attack=Attack(vs=FORT, printed=4),
    requires=_while_bloodied,
    requires_text="usable only while it is bloodied",
)
def m3327a2(c: Cast) -> None:
    """"Save ends both" is one effect carrying the condition and the burn, not
    two -- written as two they would be shaken off separately."""
    if c.strike():
        c.condition(
            Condition.RESTRAINED,
            until=When.SAVE_ENDS,
            ongoing=(5, DamageType.UNTYPED),
        )


@power(
    "m3327a3",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_OTHER,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d6", 2),
    requires=_while_bloodied,
    requires_text="usable only while it is bloodied",
)
def m3327a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(1)


@power(
    "m3327a4",
    level=3,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
    attack=Attack(vs=REF, printed=6),
    damage=Damage("1d6", 4),
    trigger="it is hit by a melee attack",
    on=Trigger(Hit, both(targets_me, by_melee), "it is hit by a melee attack"),
)
def m3327a4(c: Cast) -> None:
    """An interrupt that does not cancel: the card strikes back and leaves,
    and the blow it was answering still lands."""
    foe = _triggering_enemy(c)
    if foe is not None and c.strike(on=foe):
        c.hit(on=foe)
    c.teleport(3)


# --------------------------------------------------------------------------
# m3553
# --------------------------------------------------------------------------


def _vanish_until_touched(c: Cast, until: When) -> None:
    """Unseen until it attacks **or until something lands on it**.

    The second half is why this is not `_vanish_until_it_swings`: that one
    watches the roll it makes, and this card also ends on a roll made against
    it. Both watches are torn down with the veil so a second vanishing does
    not inherit the first one's listeners.
    """
    veil = c.invisible(until=until)
    if veil is None:
        return
    me = c.me

    def swung(ev: AttackRolled) -> None:
        if ev.attacker == me:
            c.world.effects.end(veil, "it attacked")

    def struck(ev: Hit) -> None:
        if ev.target == me:
            c.world.effects.end(veil, "it was hit")

    seen = c.watch(AttackRolled, swung, until=until, on=me, label=c.ref)
    found = c.watch(Hit, struck, until=until, on=me, label=c.ref)
    veil.on_end.append(lambda: c.world.effects.end(seen, "no longer unseen"))
    veil.on_end.append(lambda: c.world.effects.end(found, "no longer unseen"))


@power(
    "m3553a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=6),
    damage=Damage("1d6", 4, dtype=DamageType.NECROTIC),
)
def m3553a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3553a1",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.FORCE],
    attack=Attack(vs=WILL, printed=6),
    damage=Damage("2d6", 4, dtype=DamageType.FORCE, kind=LIMITED),
)
def m3553a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(1)


@power(
    "m3553a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
)
def m3553a2(c: Cast) -> None:
    """No duration is printed at all, so the veil is held to the end of the
    encounter and the two printed ends -- its own attack, or an attack landing
    on it -- are the only things that lift it."""
    _vanish_until_touched(c, When.ENCOUNTER)


# --------------------------------------------------------------------------
# m4680
# --------------------------------------------------------------------------


@power(
    "m4680a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 3),
)
def m4680a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4680a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 3),
)
def m4680a1(c: Cast) -> None:
    """A printed "5/10" takes the **normal** range, so the creature throws
    inside the band where it has no penalty."""
    if c.strike():
        c.hit()


@power(
    "m4680a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=FORT, printed=6),
    damage=Damage("1d6", 3),
    requires_text="must be wielding its handaxe",
    dropped=("etl.monster.weapon()",),
)
def m4680a2(c: Cast) -> None:
    """The grab and the advantage it grants are exact; the Requirement is what
    is dropped. `c.wielding` exists and a monster has nothing for it to read --
    the database gives a stat block no inventory -- so the printed weapon
    cannot be asked about and the row is offered unconditionally.

    The advantage is gated rather than given a duration, because "while
    grabbed" ends when the hold does and no `When` says that.
    """
    if c.strike():
        c.hit()
        c.grab()
        c.grants_advantage(
            until=When.ENCOUNTER, to=c.me, when=_grabbed_by_me(c)
        )


@power(
    "m4680a3",
    level=3,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is hit by a melee or a ranged attack",
    on=Trigger(Hit, targets_me, "it is hit by a melee or a ranged attack"),
)
def m4680a3(c: Cast) -> None:
    """`c.pass_on` moves the whole blow onto somebody else, which is the one
    printed sentence here -- the captive takes it instead."""
    victim = next(iter(c.grabbing(of=c.me)), None)
    if victim is not None:
        c.pass_on(c.trigger, to=victim)


@power(
    "m4680a4",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4680a4(c: Cast) -> None:
    """A rider with two halves, so it is a watch on the hit rather than a
    gated damage modifier: a modifier can add the die and cannot shove."""
    me, ref = c.me, c.ref

    def rider(ev: Hit) -> None:
        if ev.attacker != me or not _had_advantage(ev):
            return
        c.damage("1d6", on=ev.target, detail=ref)
        c.push(2, on=ev.target)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label=ref)


# --------------------------------------------------------------------------
# m4685
# --------------------------------------------------------------------------


@power(
    "m4685a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d8", 5),
)
def m4685a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4685a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=6),
    damage=Damage("1d6", 2),
)
def m4685a1(c: Cast) -> None:
    """"Pulls the target the same number of squares" is measured, not assumed:
    the shift may be refused or cut short, and a pull of the creature's whole
    speed from a step it never took is a different card."""
    if not c.strike():
        return
    c.hit()
    was = c.here
    c.shift(c.speed_of())
    stepped = _stepped_from(c, was)
    if stepped:
        c.pull(stepped)
    c.grab()
    for d in (AC, REF):
        c.bonus(d, 4, on=c.me, until=When.ENCOUNTER, when=_grabbed_by_me(c))


@power(
    "m4685a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=Target(
        label="grabbed targets only",
        relation=Relation.GRABBED_BY,
    ),
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d8", 5),
)
def m4685a2(c: Cast) -> None:
    """"A creature it is grabbing" is the target line now, so the `requires=`
    gate and the body's re-pick both came out: an empty pool makes `_can_land`
    false, which is the refusal the gate was spelling by hand.

    "The grab ends" is this creature letting go, and it used to be written as
    `c.end_effect` over `c.grabbed_by`, which returns **holder ids and not
    effects** -- so the line raised on `int.ended` the moment it was reached.
    `holds.release` is the spelling that works. #401.
    """
    if c.strike():
        c.hit()
        release(c, c.target)


@power(
    "m4685a3",
    level=3,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="a creature escapes its grab",
    on=Trigger(Escaped, _my_captive_escaped, "a creature escapes its grab"),
)
def m4685a3(c: Cast) -> None:
    c.shift(max(1, c.speed_of() // 2))


# --------------------------------------------------------------------------
# m4736
# --------------------------------------------------------------------------


@power(
    "m4736a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=5),
    damage=Damage("1d10", 3),
)
def m4736a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4736a1",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=AreaBurst(2, 10),
    target=NO_TARGET,
    keywords=[Keyword.ZONE],
    dropped=("c.zone(exempt=)",),
)
def m4736a1(c: Cast) -> None:
    """The darkness is laid and blocks sight, which is most of the card. What
    is dropped is "for all enemies": the creature is blind in this and the
    whole point is that it is not."""
    c.zone(c.area(), label=c.ref, until=When.EONT, blocks_sight=True)


@power(
    "m4736a2",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4736a2(c: Cast) -> None:
    _edge_damage(c)


@power(
    "m4736a3",
    level=3,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="a melee attack misses it",
    on=Trigger(Miss, both(targets_me, by_melee), "a melee attack misses it"),
)
def m4736a3(c: Cast) -> None:
    c.shift(1)


@power(
    "m4736a4",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    )
def m4736a4(c: Cast) -> None:
    """Borrowing a nearby ally's special senses -- *any* of them it has.

    Written against `c.has_sense`, which is the reader this needed: granting
    a sense and asking whether somebody else has one are different jobs, and
    only the first had a verb. The guess I wrote before that reader existed
    granted both unconditionally and `audit` caught it firing 48 times and
    doing nothing on a board with no such ally.

    It lends nothing when no ally is near, which is the card and is why this
    row can be silent on a board that fields the creature alone."""
    for mate in c.within(5, side="ally"):
        for sense in ("blindsight", "darkvision"):
            if c.has_sense(sense, on=mate):
                getattr(c, sense)()


# --------------------------------------------------------------------------
# m5073
# --------------------------------------------------------------------------

#: The label the scattered form is held under, so the row that gathers it back
#: up can find it and the Requirement can ask whether it is on.
_M5073_SCATTERED = "m5073 scattered"


def _is_scattered(world: World, eid: int) -> bool:
    return any(e.label == _M5073_SCATTERED for e in world.effects.of(eid))


@power(
    "m5073a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d10", 3, dtype=DamageType.FIRE),
)
def m5073a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5073a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_OTHER,
    attack=Attack(vs=FORT, printed=6),
    damage=Damage("2d6", 3),
)
def m5073a1(c: Cast) -> None:
    """The three parts of the new form hang off one labelled hold, so the row
    that reverses it has a single thing to end -- `c.insubstantial` and the
    rest carry no label of their own to find them by."""
    if c.strike():
        c.hit()
    if not c.first:
        return
    hold = c.effect(_M5073_SCATTERED, until=When.EONT, on=c.me)
    if hold is None:
        return
    parts = [
        c.insubstantial(on=c.me, until=When.EONT),
        c.weakened(on=c.me, until=When.EONT),
        c.mode("fly", c.speed_of(), on=c.me, until=When.EONT),
    ]
    for part in parts:
        if part is not None:
            hold.on_end.append(
                lambda bit=part: c.world.effects.end(bit, "it gathered itself up")
            )
    c.forbid("m5073a2", on=c.me, until=When.EOT)


@power(
    "m5073a2",
    level=3,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    requires=_is_scattered,
    requires_text="usable only while it is scattered",
)
def m5073a2(c: Cast) -> None:
    for hold in list(c.world.effects.of(c.me)):
        if hold.label == _M5073_SCATTERED:
            c.end_effect(hold, why=c.ref)
    c.forbid("m5073a1", on=c.me, until=When.EOT)


# --------------------------------------------------------------------------
# m5286
# --------------------------------------------------------------------------


@power(
    "m5286a0",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5286a0(c: Cast) -> None:
    """Asked of the effect table through the damage context's `target`: the
    printed clause is about what the victim is carrying and says nothing about
    where the poison came from."""
    c.bonus(
        "damage", 2, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: _poisoned(c, ctx.get("target")),
    )


@power(
    "m5286a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 2),
)
def m5286a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)


@power(
    "m5286a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=Target(
        label="one creature taking ongoing poison damage",
        ongoing_types=frozenset({DamageType.POISON}),
    ),
    attack=Attack(vs=FORT, printed=6),
    damage=Damage("1d6", 3),
)
def m5286a2(c: Cast) -> None:
    """The `requires=` gate said the same thing the target line now says, so
    it came out with the body's re-pick: an empty pool refuses the row by
    itself. #401."""
    if c.strike():
        c.hit()
        c.blinded(until=When.SAVE_ENDS)


@power(
    "m5286a3",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=Target(
        label="one creature that cannot see it",
        relation=Relation.HIDDEN_FROM,
    ),
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d6", 3),
)
def m5286a3(c: Cast) -> None:
    """"Cannot see the creature" is two states and both are asked now.

    The target line routes through `query.unseen_by`, which since #406 reads
    `Rules.blind` -- so the hiding half and the blindness half are one question.
    That matters here more than anywhere: this stat block blinds enemies two rows
    up expressly to set this row up, and until the flag had a reader the
    combination its page is built around was refused."""
    if c.strike():
        c.hit()


# --------------------------------------------------------------------------
# m5366
# --------------------------------------------------------------------------


@power(
    "m5366a0",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5366a0(c: Cast) -> None:
    """Read off the roll's advantage rather than the relation: attacking clears
    `HIDDEN_FROM`, and a creature it was hidden from is precisely the one the
    bonus is for."""
    c.bonus(
        "damage", 3, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: bool(ctx.get("advantage")),
    )


@power(
    "m5366a1",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5366a1(c: Cast) -> None:
    """"When it shifts", and only when it shifts -- a plain exemption would let
    it walk through rough ground for nothing too."""
    _sure_footed_shift(c)


@power(
    "m5366a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage(bonus=5, kind="minion"),
)
def m5366a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5366a3",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(6),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage(bonus=5, kind="minion"),
)
def m5366a3(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5366a4",
    level=3,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m5366a4(c: Cast) -> None:
    """"An automatic check result of 25" is a check that cannot fail against
    anything at this level, so what is left to say is the outcome: wherever it
    could try, it has."""
    c.move(2)
    _conceal(c)


# --------------------------------------------------------------------------
# m5648
# --------------------------------------------------------------------------


@power(
    "m5648a0",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m5648a0(c: Cast) -> None:
    """Thievery at ten squares. Nothing on a board rolls one, so the whole
    trait is deliberately inert rather than a clause that is missing."""


@power(
    "m5648a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d6", 4),
)
def m5648a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5648a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=Target(
        label="one creature grabbed by it",
        relation=Relation.GRABBED_BY,
    ),
    attack=Attack(vs=REF, printed=6),
    damage=Damage("4d6", 8, half_on_miss=True),
)
def m5648a2(c: Cast) -> None:
    """`half_on_miss` on the header is data for the card; the miss line is
    `c.hit(half=True)`, which rolls the expression and halves it."""
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)


@power(
    "m5648a3",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.TELEPORTATION],
    attack=Attack(vs=REF, printed=6),
    requires=_not_grabbing,
    requires_text="must have no creature grabbed",
    dropped=("c.grab_reach()",),
)
def m5648a3(c: Cast) -> None:
    """The blind is tied to the hold rather than given a duration of its own:
    "until the grab ends" is not a `When`, and `Effect.on_end` is.

    Two clauses are dropped and they are different gaps -- the printed escape
    DC, which `c.grab` neither takes nor rolls, and the two squares the hold
    reaches, where `Relation.GRABBED_BY` means adjacent and nothing else.
    """
    foe = c.target
    if foe is None or not c.strike():
        return
    where = _free_square_beside(c, c.me)
    if where is not None:
        c.teleport(2, who=foe, to=where)
    hold = c.grab(on=foe, dc=13)
    blind = c.blinded(on=foe, until=When.ENCOUNTER)
    if hold is not None and blind is not None:
        hold.on_end.append(lambda: c.world.effects.end(blind, "the grab ended"))


@power(
    "m5648a4",
    level=3,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m5648a4(c: Cast) -> None:
    c.teleport(3)


@power(
    "m5648a5",
    level=3,
    usage=ENCOUNTER,
    action=REACTION,
    reach=Melee(2),
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
    damage=Damage("1d8", 5, kind=LIMITED),
    trigger="a creature escapes its grab",
    on=Trigger(Escaped, _my_captive_escaped, "a creature escapes its grab"),
)
def m5648a5(c: Cast) -> None:
    """No attack roll is printed -- "the target takes 1d8 + 5 damage" -- so the
    header carries the expression and `c.hit` applies it without one."""
    foe = _triggering_enemy(c)
    if foe is not None:
        c.hit(on=foe)
    c.teleport(3)


# --------------------------------------------------------------------------
# m5940
# --------------------------------------------------------------------------


@power(
    "m5940a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d6", 4),
)
def m5940a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5940a1",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.ILLUSION, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=6),
    damage=Damage("2d6", 4, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m5940a1(c: Cast) -> None:
    """Three clauses hang off the one effect, which is why it is held rather
    than laid and forgotten: the invisibility, the extra die against the one
    creature that can see it, and the recharge all end when it does.

    "Recharge when the power misses" is the printed line on top of the die the
    database files, and the two only ever agree to bring the row back sooner.
    """
    me, ref = c.me, c.ref
    _recharge_on(c, Miss, lambda ev: ev.attacker == me and ev.power == ref)
    foe = c.target
    if foe is None:
        return
    if not c.strike():
        c.conceal(on=me, until=When.EONT)
        return
    c.hit()
    bound = c.grants_advantage(on=foe, to="team", until=When.SAVE_ENDS)
    if bound is None:
        return
    veils = [
        veil
        for other in c.enemies()
        if other != foe and (veil := c.invisible(to=other, on=me, until=When.ENCOUNTER))
    ]
    sharper = c.bonus(
        "damage", 0, dice="1d6", on=me, until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("target") == foe and ctx.get("power") == "m5940a0",
    )
    for held in (*veils, sharper):
        if held is not None:
            bound.on_end.append(
                lambda bit=held: c.world.effects.end(bit, "the hold ended")
            )
    bound.on_end.append(lambda: c.restore_use(ref, on=me))


@power(
    "m5940a2",
    level=3,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=6),
    damage=Damage("1d8", 4, dtype=DamageType.PSYCHIC, kind=LIMITED, half_on_miss=True),
)
def m5940a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(2)
    else:
        c.hit(half=True)
        c.push(1)


# --------------------------------------------------------------------------
# m6570
# --------------------------------------------------------------------------


@power(
    "m6570a0",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6570a0(c: Cast) -> None:
    """The advantage relation names **one** beneficiary, so a card reading "all
    melee attacks against it" is that relation once per enemy, each gated on
    the swing being a melee one. Manipulating objects is not a board operation
    and there is nothing to take away."""
    c.no_basic(on=c.me)
    for foe in c.enemies():
        c.grants_advantage(on=c.me, to=foe, until=When.ENCOUNTER, when=_melee_blow)


@power(
    "m6570a1",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m6570a1(c: Cast) -> None:
    """A Perception check to tell it from furniture, made once before the fight
    starts. Everything on a board is already known to be a creature, so the
    whole trait is inert rather than a clause that is missing."""


@power(
    "m6570a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("spec.stat_block()",),
)
def m6570a2(c: Cast) -> None:
    """It brings a second creature onto the board and the spec does not say
    which: the entry names a stat block that has no ref anywhere in the brief,
    so `c.summon` has nothing to be handed. The leash, the initiative slot and
    the cap of three are all sayable; the creature is not."""


@power(
    "m6570a3",
    level=3,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m6570a3(c: Cast) -> None:
    """It pays for its own step. A speed of 0 is in the database, which is what
    makes a one-square shift the whole of this creature's movement."""
    c.shift(1)
    c.damage("1d6", on=c.me)


# --------------------------------------------------------------------------
# m6649
# --------------------------------------------------------------------------


def _by_storm(world: World, me: int, ev: Any) -> bool:
    """Lightning or thunder, landing on this creature."""
    return getattr(ev, "target", None) == me and getattr(ev, "dtype", None) in (
        DamageType.LIGHTNING,
        DamageType.THUNDER,
    )


@power(
    "m6649a0",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6649a0(c: Cast) -> None:
    """An aura whose whole content is a modifier read per attacker, so the aura
    is declared for the board to draw and the concealment is a gated
    `c.conceal` -- `aura 1` is "adjacent", which is what the gate asks."""
    c.aura(1, label=c.ref, on=c.me, until=When.ENCOUNTER)
    c.conceal(
        on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: _is_adjacent(c, ctx.get("attacker")),
    )


@power(
    "m6649a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 4),
)
def m6649a1(c: Cast) -> None:
    """"1d6 + 4 damage **plus** 1d8 cold" is two blows of different types, so
    the second one cannot ride in the header's single expression."""
    if c.strike():
        c.hit()
        c.damage("1d8", dtype=DamageType.COLD)


@power(
    "m6649a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d4", 4),
)
def m6649a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.LIGHTNING)


@power(
    "m6649a3",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    requires=_is_bloodied,
    requires_text="it must be bloodied",
)
def m6649a3(c: Cast) -> None:
    """Both of its melee lines in one action. `c.use_power` runs each at this
    row's cost, so every rider that reads one of them still fires."""
    c.use_power("m6649a1", on=c.target)
    if c.last:
        c.use_power("m6649a2", on=c.target)


@power(
    "m6649a4",
    level=3,
    usage=AT_WILL,
    action=OPPORTUNITY,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it takes lightning or thunder damage",
    on=Trigger(DamageApplied, _by_storm, "it takes lightning or thunder damage"),
)
def m6649a4(c: Cast) -> None:
    c.insubstantial(on=c.me, until=When.EONT)
    c.shift(c.speed_of())


# --------------------------------------------------------------------------
# m867
# --------------------------------------------------------------------------


@power(
    "m867a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d8", 2),
)
def m867a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m867a1",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m867a1(c: Cast) -> None:
    """Narrowed to melee by the reach of whatever rolled the blow -- the hit
    carries no shape of its own, so the row it names is asked."""
    me, ref = c.me, c.ref

    def rider(ev: Hit) -> None:
        if ev.attacker != me or not _had_advantage(ev):
            return
        if _reach_kind(ev.power) != "melee":
            return
        c.damage("1d6", on=ev.target, detail=ref)
        c.blinded(on=ev.target, until=When.SAVE_ENDS)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label=ref)


@power(
    "m867a2",
    level=3,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is the target of a melee attack",
    on=Trigger(
        AttackDeclared, both(targets_me, by_melee), "it is the target of a melee attack"
    ),
)
def m867a2(c: Cast) -> None:
    """The advantage is laid before the swing and only until the end of this
    turn: it is a one-off for the counter and not a standing state."""
    foe = _triggering_enemy(c)
    if foe is None:
        return
    c.grants_advantage(on=foe, to=c.me, until=When.EOT)
    c.basic(on=foe)
    c.shift(1)


@power(
    "m867a3",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m867a3(c: Cast) -> None:
    """Either half of the printed condition is enough, so both are asked at the
    end of the turn: the distance is measured from where the turn began, which
    is the only place that number can come from."""

    def settle(swung: bool, was: Square | None) -> None:
        if not swung or _stepped_from(c, was) >= 3:
            c.conceal(on=c.me, until=When.EONT)

    _watch_its_turn(c, settle)
