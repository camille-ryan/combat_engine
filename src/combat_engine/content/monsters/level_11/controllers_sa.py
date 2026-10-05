"""Monster abilities, level 11: the controllers the first sweep left out.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack line goes in the header exactly as printed -- `Attack(vs=WILL,
printed=14)` -- and the damage line goes there as data, so the engine takes
the level back out of the one and can rescale the other.

The conventions of the eleven levels below are kept:

* a row filed under an action heading that is plainly a **trait** is
  `ActionType.NONE`, whatever the compendium's action column claims;
* a card with no printed range at all is **melee 1**;
* a blast or burst reading "creatures in the blast/burst" is
  `EACH_CREATURE`; one naming no target set at all takes **enemies**;
* `half_on_miss=True` is card data only, so the Miss line is written out as
  `else: c.hit(half=True)` as well;
* a blow of two damage types rolled once keeps the first in the header and is
  marked `dropped=("Damage(dtypes=)",)`; two separately named amounts are two
  packets and need no marker;
* a helper written for an earlier level is imported rather than copied, and
  the four written for `controllers.py` beside this file are imported too.

Eight readings this file had to settle.

**A parenthetical "(+17 while bloodied)" beside a printed attack total is the
creature's own trait showing through, not a second modifier.** m2615 prints
one on five rows and also prints the trait that causes it; writing both would
be +2. The trait is written, the parentheticals are not -- and two of the five
disagree with it anyway (m2615a3 repeats the base, m2615a4 goes *down* by
one), which is what settles that they are the card re-totalling rather than a
rule.

**"All creatures have concealment against the target"** is the opposite
direction from `c.conceal`, which gives concealment *to* a creature. Nothing
makes a creature's own attacks treat everybody as concealed, so that clause is
`dropped=("c.conceal(against=)",)`. m1505a1 six levels down marked the same
sentence `c.conceal_in()`, which is a *zone*-bounded grant and would not close
this gap when it lands -- see the report.

**Forest walk is `Movement.ignores`.** The engine has no movement mode called
that; what forest walk *does* is cross woodland's rough ground for nothing,
which is exactly the set `c.ignores_difficult` writes into. So m1565a2's
"every creature without forest walk" is asked there.

**Tangling roots have to start somewhere.** m1565a3 reads "create two squares
adjacent to other tangling roots" and no row on the card lays the first ones,
so with none on the board the row would be inert for the whole fight. The two
squares are seeded beside the m1565 itself when there are none yet; after that
the printed adjacency rule holds.

**An aftereffect is the hold's `on_end`.** It follows the hold going whichever
way it went, where a second save-ends effect laid now would start running
while the first was still on.

**"Until those temporary hit points are gone"** is a clock no duration says,
so the bonus stands to the end of the encounter and is *gated* on the bearer's
`Health.temp` instead -- read at the moment a blow is rolled, which is the
only moment the answer matters.

**A conjuration's own aura is where "adjacent to the sphere" is asked.**
`c.aura(radius, on=sphere)` follows anything with a `Position`, and
`Zones.refresh` takes the aura down when the sphere goes, so the two do not
have to be unwound by hand.

**A spawned creature needs a ref the extraction did not keep.** m3939a5 and
m1822a4 name their own ability id where a stat block or a creature belongs;
there is no row to summon and nothing to attack, so both are `todo=` against
the extraction rather than approximated.

Each stat block in ref order.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_07.brutes import (
    _aura,
    _crowded,
    _living,
    _melee_ctx,
)
from combat_engine.content.monsters.level_07.soldiers import _recharge_on
from combat_engine.content.monsters.level_08.skirmishers import _adjacent_foe
from combat_engine.content.monsters.level_09.brutes import _regenerates, _volley
from combat_engine.content.monsters.level_09.lurkers_sa import _restricted_to
from combat_engine.content.monsters.level_11.controllers import (
    EVERY_DEFENCE,
    _ends_its_turn_in,
    _softened,
)
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
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_ALLY,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    STANDARD,
    WILL,
    ActionPointSpent,
    ActionType,
    AreaBurst,
    Attack,
    AttackRolled,
    Bloodied,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    Damage,
    DamageApplied,
    DamageType,
    Dropped,
    Effect,
    Health,
    Hit,
    Ident,
    Keyword,
    Melee,
    Mod,
    Moved,
    MoveEnd,
    Movement,
    Position,
    Ranged,
    Relation,
    SavingThrow,
    Size,
    SkillCheck,
    Square,
    Target,
    TurnEnd,
    TurnStart,
    UpTo,
    Usage,
    When,
    World,
    footprint,
    power,
    spread,
)
from combat_engine.engine.dsl import get
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import alive, creatures, distance_between, squares
from combat_engine.engine.triggers import Trigger, by_me, targets_me
from combat_engine.engine.zones import Zone


def _at_zero(c: Cast, who: int) -> bool:
    """Is that creature at or below 0 hit points now?

    Asked after the blow rather than off `Dropped`, because the printed line
    is about the state the damage left behind and a creature already down is
    not dropped a second time.
    """
    health = c.world.get(who, Health)
    return health is not None and health.hp <= 0


def _temp_left(c: Cast, who: int) -> bool:
    health = c.world.get(who, Health)
    return health is not None and health.temp > 0


def _weapon_row(ctx: dict[str, Any]) -> bool:
    """Did the row behind this damage carry the weapon keyword?

    Neither context holds a keyword list; both hold the ref, and the keywords
    are declared data on the row, so the ref is what the question goes
    through.
    """
    p = get(str(ctx.get("power") or ""))
    return p is not None and Keyword.WEAPON in p.keywords


def _forest_walker(c: Cast, who: int) -> bool:
    """Has that creature forest walk?

    There is no such movement mode. What forest walk does is cross the rough
    ground woodland makes for nothing, which is the set `c.ignores_difficult`
    writes into -- so the blanket `"*"` counts too.
    """
    moves = c.world.get(who, Movement)
    return moves is not None and bool({"forest", "*"} & moves.ignores)


def _labelled_squares(c: Cast, label: str) -> set[Square]:
    """Every square the caster's zones under one label cover."""
    out: set[Square] = set()
    for _, zone in c.world.zones.all():
        if zone.owner == c.me and zone.label == label:
            out |= set(zone.squares)
    return out


def _step(a: Square, b: Square) -> int:
    """Squares between two squares, counted the way the grid counts them."""
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def _free_near(c: Cast, anchor: int, within: int) -> list[Square]:
    """Passable, unoccupied squares within `within` of that creature."""
    return sorted(
        sq
        for sq in spread(squares(c.world, anchor), within)
        if c.world.grid.passable(sq) and not c.in_squares({sq})
    )


def _toward_the_foe(c: Cast, pool: list[Square]) -> list[Square]:
    """The same squares, nearest an enemy first.

    A printed "any unoccupied space within N squares" names none of them and
    there is no `Target` to pick, so something has to order the pool; the
    lowest-sorted corner is a legal answer and a useless one.
    """
    foes = [sq for foe in c.enemies() for sq in squares(c.world, foe)]
    if not foes:
        return pool
    return sorted(pool, key=lambda sq: (min(_step(sq, f) for f in foes), sq))


def _damage_mirror(c: Cast, victim: int, hold: Effect) -> None:
    """"Attacks that deal damage to it deal equal damage to the target."

    Read off `DamageApplied`, which is the only event that says how much
    actually landed, and gated on the hold so it stops when the hold does.
    """
    me = c.me

    def share(ev: DamageApplied) -> None:
        if hold.ended or ev.target != me or ev.amount <= 0:
            return
        if alive(c.world, victim):
            c.flat(ev.amount, on=victim)

    hold.subs.append(c.world.bus.on(DamageApplied, share, owner=me))


# ==========================================================================
# m1031
# ==========================================================================


@power(
    "m1031a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d8", 4),
)
def m1031a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none means.

    The printed crit line *replaces* the damage and is part roll, so both
    halves are dealt by hand: `c.hit` would add the declared 1d8 on top, and
    `c.damage` inside a crit branch maxes its dice, which would turn the
    printed 2d6 into a flat 12 of its own. `c.flat(c.roll(...))` is the way to
    add a die to a critical.
    """
    if not c.strike():
        return
    victim = c.target
    if c.crit:
        c.flat(12)
        c.flat(c.roll("2d6"), dtype=DamageType.NECROTIC)
    else:
        c.hit()
    if victim is not None and _at_zero(c, victim):
        c.temp_hp(5, on=c.me)


@power(
    "m1031a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    attack=Attack(vs=WILL, printed=15),
    damage=Damage("2d6", 6),
)
def m1031a1(c: Cast) -> None:
    """The second bite is paid once for the turn it moves on, not per step:
    `Moved` fires for every square and the printed line names the turn.

    No duration is printed for the hold, so it runs to the end of this
    creature's next turn -- the engine's default and the shortest reading.
    """
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    bled: dict[int, int] = {}

    def slash(ev: Moved) -> None:
        if ev.actor != victim or c.world.turn != victim:
            return
        if bled.get(victim) == c.world.round:
            return
        bled[victim] = c.world.round
        c.damage("2d6", 4, on=victim)

    c.watch(Moved, slash, until=When.EONT, on=victim, label=c.ref)


@power(
    "m1031a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("2d6", 6),
)
def m1031a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(2)


@power(
    "m1031a3",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("2d6", 6, kind=LIMITED),
)
def m1031a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.blinded(until=When.SAVE_ENDS)


@power(
    "m1031a4",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1031a4(c: Cast) -> None:
    """A racial bonus, which is the word the card prints in front of "bonus"
    and the only thing `kind=` may be. Whether the victim is bloodied is asked
    as the swing is rolled, off the attack context's own target."""
    def bleeding(ctx: dict[str, Any]) -> bool:
        who = ctx.get("target")
        return who is not None and c.bloodied(who)

    c.bonus("attack", 1, on=c.me, until=When.ENCOUNTER, kind="racial", when=bleeding)


# ==========================================================================
# m115864
# ==========================================================================


@power(
    "m115864a0",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m115864a0(c: Cast) -> None:
    """"Living enemies" leaves out the lifeless type words, which is the only
    thing the engine has for the distinction."""
    me = c.me

    def eligible(who: int) -> bool:
        return who != me and who in c.enemies() and _living(c, who)

    _aura(
        c,
        2,
        eligible,
        lambda who: c.penalty("attack", 2, on=who, until=When.ENCOUNTER),
    )


@power(
    "m115864a1",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m115864a1(c: Cast) -> None:
    c.threatens(4, on=c.me, until=When.ENCOUNTER)


@power(
    "m115864a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(4),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("3d6", 9),
    dropped=("c.grab(dc=)",),
)
def m115864a2(c: Cast) -> None:
    """The grab lands; its printed escape DC does not. `c.escape` rolls
    against the grabber rather than against a number the card names."""
    if c.strike():
        c.hit()
        c.pull(3)
        c.grab()


@power(
    "m115864a3",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(2),
    target=EACH_OTHER,
    keywords=[Keyword.DISEASE, Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d6", 7),
    dropped=("c.contract(ref)",),
)
def m115864a3(c: Cast) -> None:
    """Two damage lines, one of them conditional, so the bigger one is rolled
    in the body: the header carries the plain line as the card prints it.

    The disease is dropped. It is contracted at the *end of the encounter*
    against a stat block id, and nothing carries a disease track.
    """
    if not c.strike():
        return
    victim = c.target
    if victim is not None and c.me in c.grabbed_by(on=victim):
        c.damage("2d6", 10, on=victim)
    else:
        c.hit()
    c.ongoing(5, DamageType.NECROTIC)


@power(
    "m115864a4",
    level=11,
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=14),
    damage=Damage("2d8", dtype=DamageType.PSYCHIC),
)
def m115864a4(c: Cast) -> None:
    """The second toll is read at the end of the victim's *next* turn, which
    is one named moment rather than a duration -- so the watch stands to the
    end of the fight and closes itself the first time that turn ends."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    me, settled = c.me, []

    def measured(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor != victim or settled:
            return
        settled.append(1)
        if distance_between(c.world, me, victim) > 1:
            c.flat(15, dtype=DamageType.PSYCHIC, on=victim)

    c.watch(TurnEnd, measured, until=When.ENCOUNTER, on=victim, label=c.ref)


_M115864_GRABBED = "an enemy hits it while it has a creature grabbed"


def _m115864_hit_while_holding(world: World, me: int, ev: Hit) -> bool:
    if ev.target != me or ev.attacker == me:
        return False
    return bool(world.relations.targets(Relation.GRABBED_BY, me))


@power(
    "m115864a5",
    level=11,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=Melee(1),
    target=NO_TARGET,
    attack=Attack(vs=FORT, printed=14),
    trigger=_M115864_GRABBED,
    on=Trigger(Hit, when=_m115864_hit_while_holding, text=_M115864_GRABBED),
)
def m115864a5(c: Cast) -> None:
    """Printed as an immediate interrupt and that is what it has to be: the
    blow is moved rather than stopped, and `c.redirect` moves the live result
    with the event so the damage follows it.

    The attack is rolled against the creature being used as a shield, which is
    the printed target line, and only a hit redirects.
    """
    held = sorted(c.grabbing())
    shield = c.choose(held, f"{c.ref}: which captive takes it") if held else None
    if shield is None:
        return
    if c.attack(c.world.scaling.trim(14, c.level), FORT, on=shield):
        c.redirect(to=shield)


# ==========================================================================
# m115868
# ==========================================================================


@power(
    "m115868a0",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m115868a0(c: Cast) -> None:
    """The toll is taken at the end of a turn, which is neither of the two
    moments `c.burns` covers, and the slide is part of the same sentence."""
    ring = c.aura(2, until=When.ENCOUNTER)

    def buffet(who: int) -> None:
        if who not in c.enemies():
            return
        c.flat(5, on=who)
        c.slide(2, on=who)

    _ends_its_turn_in(c, ring, buffet)


@power(
    "m115868a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("3d6", 8),
)
def m115868a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(2)
        c.prone()
    else:
        c.slide(1)


@power(
    "m115868a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
)
def m115868a2(c: Cast) -> None:
    """Two swings of the row that prints them, both at one creature, which is
    the printed line and the only reading under which "if both attacks hit"
    can be true."""
    victim = c.target
    if victim is not None and _volley(c, "m115868a1", victim):
        c.stunned(until=When.EONT, on=victim)


@power(
    "m115868a3",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=Target(side="enemy", count=1, label="stunned by it"),
    dropped=("Target.condition_by",),
)
def m115868a3(c: Cast) -> None:
    """No attack roll at all: the damage is the whole of it.

    `Target` filters on side, count and size and not on how a creature stands
    to the caster, so the restriction is enforced here and the row is aimed at
    somebody who qualifies rather than thrown away. The printed line is
    "stunned **by it**", which is `Target.relation` and not
    `Target.condition`; the filter below asks only the condition.
    """
    victim = _restricted_to(c, 1, lambda who: c.is_(Condition.STUNNED, on=who))
    if victim is not None:
        c.damage("4d10", 16, on=victim)


_M115868_BLED = "it is first bloodied"


@power(
    "m115868a4",
    level=11,
    usage=ENCOUNTER,
    action=REACTION,
    reach=CloseBlast(5),
    target=EACH_OTHER,
    attack=Attack(vs=FORT, printed=14),
    trigger=_M115868_BLED,
    on=Trigger(Bloodied, by_me, _M115868_BLED),
)
def m115868a4(c: Cast) -> None:
    """`Bloodied` carries `actor`, so the ready-made predicate is the one that
    reads it; `about_me` would be right here and wrong one row along, so the
    whole file uses the spelling that matches the event."""
    if c.strike():
        c.push(3)
        c.prone()
    else:
        c.push(1)


# ==========================================================================
# m1565
# ==========================================================================


_M1565_ROOTS = "m1565 tangling roots"


@power(
    "m1565a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d4", 6),
)
def m1565a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means."""
    if c.strike():
        c.hit()


@power(
    "m1565a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    attack=Attack(vs=REF, printed=13),
    damage=Damage("1d8", 4),
    dropped=("c.conceal(against=)",),
)
def m1565a1(c: Cast) -> None:
    """"Save ends both" is one effect carrying the burn.

    "All creatures have concealment against the target" is the other half and
    is the opposite direction from `c.conceal`: it makes the target's own
    attacks the hard ones to land, and no verb says that.
    """
    if c.strike():
        c.hit()
        c.condition(until=When.SAVE_ENDS, ongoing=(5, DamageType.UNTYPED))


@power(
    "m1565a2",
    level=11,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=PERSONAL,
    target=NO_TARGET,
    attack=Attack(vs=REF, printed=14),
)
def m1565a2(c: Cast) -> None:
    """Everyone standing in the roots, one attack each.

    No damage line: the restraint is the whole of a hit. The pool is the
    zone's squares rather than a burst, so the row declares no target and
    finds them itself.
    """
    rooted = _labelled_squares(c, _M1565_ROOTS)
    if not rooted:
        return
    for who in sorted(c.in_squares(rooted)):
        if who == c.me or not alive(c.world, who) or _forest_walker(c, who):
            continue
        if c.strike(on=who):
            c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS, on=who)


@power(
    "m1565a3",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ZONE],
)
def m1565a3(c: Cast) -> None:
    """Two more squares of roots, laid beside the ones already there.

    Nothing on this card lays the *first* roots, so with none on the board the
    row would never do anything for a whole fight. The seed is the ground
    beside the m1565 itself, and after that the printed adjacency holds.
    """
    rooted = _labelled_squares(c, _M1565_ROOTS)
    anchor = spread(rooted, 1) if rooted else spread(squares(c.world, c.me), 1)
    pool = sorted(
        sq for sq in anchor if sq not in rooted and c.world.grid.passable(sq)
    )
    picked: list[Square] = []
    for _ in range(2):
        left = [sq for sq in pool if sq not in picked]
        chosen = c.choose(left, f"{c.ref}: which square the roots take") if left else None
        if chosen is None:
            break
        picked.append(chosen)
    if picked:
        c.zone(picked, label=_M1565_ROOTS, until=When.ENCOUNTER, difficult=_M1565_ROOTS)


@power(
    "m1565a4",
    level=11,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m1565a4(c: Cast) -> None:
    """It steps out of one patch of roots and into another.

    The m1565 is Large, and the two things that catch a Large blink both do:
    `c.teleport` filters its candidates by the **whole footprint**, so a
    destination checked one square at a time is offered squares the creature
    cannot stand in; and it filters them by the number it is handed, so the
    distance is measured rather than capped at a guess. Its own squares count
    as clear, because it is the one leaving them.

    "At least one square of its space on roots" is what the anchor being
    rooted comes to, which is why the pool is the roots themselves.
    """
    me = c.me
    standing = c.world.get(me, Position)
    size = standing.size if standing is not None else Size.MEDIUM
    mine = set(squares(c.world, me))
    pool = [
        sq
        for sq in sorted(_labelled_squares(c, _M1565_ROOTS))
        if sq not in mine
        and all(
            c.world.grid.passable(part) and c.world.grid.occupant(part) in (None, me)
            for part in footprint(sq, size)
        )
    ]
    where = c.choose(pool, f"{c.ref}: where it comes up") if pool else None
    if where is not None:
        c.teleport(max((_step(sq, where) for sq in mine), default=1), to=where)


@power(
    "m1565a5",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1565a5(c: Cast) -> None:
    """The roots outlive it.

    Laid again rather than left standing: an aura would come down with its
    owner, and a plain zone the m1565 still owns is tidied with the rest of
    the fight's bookkeeping. A fresh zone over the same squares is what
    "remain difficult terrain" comes to, and it announces itself.
    """
    me = c.me

    def rot(ev: Dropped) -> None:
        if ev.actor != me:
            return
        rooted = sorted(_labelled_squares(c, _M1565_ROOTS))
        if rooted:
            c.zone(
                rooted,
                label=f"{c.ref} remains",
                until=When.ENCOUNTER,
                difficult=_M1565_ROOTS,
            )

    c.watch(Dropped, rot, until=When.ENCOUNTER, on=me, label=c.ref)


# ==========================================================================
# m1769
# ==========================================================================


@power(
    "m1769a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d8", 5),
)
def m1769a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.weakened(until=When.EONT)


@power(
    "m1769a1",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(10),
    target=EACH_ALLY,
    keywords=[Keyword.FIRE],
)
def m1769a1(c: Cast) -> None:
    """No attack roll: the grant is the whole of it.

    Neither damage context carries a keyword list, so "attacks with the weapon
    keyword" is asked through the ref the context does carry.
    """
    c.bonus(
        "damage",
        5,
        until=When.EONT,
        dtype=DamageType.FIRE,
        when=_weapon_row,
    )


@power(
    "m1769a2",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1769a2(c: Cast) -> None:
    """Two printed occasions, one payout.

    `Bloodied` carries `source` -- whoever crossed the line -- so the second
    occasion is that event and does not have to be re-derived off damage.
    """
    me = c.me

    def rally() -> None:
        c.temp_hp(10, on=me)
        for friend in c.within(5, of=me, side="ally"):
            c.temp_hp(10, on=friend)

    def struck(ev: Hit) -> None:
        if ev.attacker == me and ev.critical:
            rally()

    def bled(ev: Bloodied) -> None:
        if getattr(ev, "source", None) == me and ev.actor in c.enemies():
            rally()

    c.watch(Hit, struck, until=When.ENCOUNTER, on=me, label=f"{c.ref} crit")
    c.watch(Bloodied, bled, until=When.ENCOUNTER, on=me, label=f"{c.ref} blood")


# ==========================================================================
# m1822
# ==========================================================================


@power(
    "m1822a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("2d6", 5, dtype=DamageType.FIRE),
)
def m1822a0(c: Cast) -> None:
    """"While bloodied" with no subject is the creature's own health, the
    reading every stat block of this shape takes. The bigger line drops the
    word fire where the smaller one prints it; one blow does not change type
    because it got harder, so both are fire."""
    if not c.strike():
        return
    if c.bloodied(c.me):
        c.damage("2d6", 7, dtype=DamageType.FIRE)
    else:
        c.hit()


@power(
    "m1822a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=14),
    damage=Damage("4d8", 5),
)
def m1822a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.EONT)


@power(
    "m1822a2",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("4d8", 5, dtype=DamageType.FIRE, kind=LIMITED),
)
def m1822a2(c: Cast) -> None:
    if not c.strike():
        return
    if c.bloodied(c.me):
        c.damage("4d8", 7, dtype=DamageType.FIRE)
    else:
        c.hit()
    c.push(6)


@power(
    "m1822a3",
    level=11,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.FIRE, Keyword.PSYCHIC],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("3d10", 6, dtype=DamageType.FIRE, kind=LIMITED),
)
def m1822a3(c: Cast) -> None:
    """"Save ends both" is one effect carrying the burn and the daze."""
    if not c.strike():
        return
    c.hit()
    if c.target is not None:
        c.world.effects.apply(
            c.target,
            c.me,
            When.SAVE_ENDS,
            label=c.ref,
            conditions=(Condition.DAZED,),
            ongoing=(10, DamageType.PSYCHIC),
        )


@power(
    "m1822a4",
    level=11,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("etl.monster.ability_text()",),
)
def m1822a4(c: Cast) -> None:
    """The subject of the printed sentence did not survive extraction: the
    spec has a localisation token where a creature belongs, so there is
    nothing on the board for "makes one attack" to be about and no attack
    line of its own to roll."""


_M1822_CLOSED = "an enemy moves adjacent to it"


def _m1822_closed(world: World, me: int, ev: MoveEnd) -> bool:
    """Arrived next to it, which is a question about where the mover ended up.

    `MoveStart` fires before anything has moved, so adjacency there is the old
    answer; `MoveEnd` carries `kind_` and the finished position, which is what
    "moves adjacent to" asks.
    """
    from combat_engine.engine.query import enemies

    return ev.actor in enemies(world, me) and distance_between(world, me, ev.actor) <= 1


@power(
    "m1822a5",
    level=11,
    usage=AT_WILL,
    action=REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    trigger=_M1822_CLOSED,
    on=Trigger(MoveEnd, when=_m1822_closed, text=_M1822_CLOSED),
)
def m1822a5(c: Cast) -> None:
    """Filed as a move action and printed as an immediate reaction; the
    printed action line is the one written. The creature slid is the one that
    closed, which is the trigger's actor and not a target the row chose."""
    ev = c.trigger
    mover = getattr(ev, "actor", None)
    if mover is not None:
        c.slide(3, on=mover)


@power(
    "m1822a6",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1822a6(c: Cast) -> None:
    """The damage context carries no `ranged`, so "melee" is read off the
    row's own reach through the ref -- which is what `_melee_ctx` is for."""
    def hemmed(ctx: dict[str, Any]) -> bool:
        who = ctx.get("target")
        return who is not None and _melee_ctx(ctx) and _crowded(c, who, 2)

    c.bonus("damage", 5, on=c.me, until=When.ENCOUNTER, when=hemmed)


# ==========================================================================
# m1978
# ==========================================================================


@power(
    "m1978a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d8", 2),
)
def m1978a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1978a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("2d6", 7, dtype=DamageType.NECROTIC),
)
def m1978a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized(until=When.SAVE_ENDS)


@power(
    "m1978a2",
    level=11,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Melee(1),
    target=Target(side="enemy", count=1, label="immobilized"),
    keywords=[Keyword.HEALING, Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("1d8", 4, dtype=DamageType.NECROTIC),
    dropped=("Target.condition",),
)
def m1978a2(c: Cast) -> None:
    """"Loses a healing surge" is `c.spend_surge`, which spends one and gives
    nothing back for it -- the same door the printed line goes through."""
    victim = _restricted_to(c, 1, lambda who: c.is_(Condition.IMMOBILIZED, on=who))
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)
    c.spend_surge(on=victim)
    c.heal(5, on=c.me)


@power(
    "m1978a3",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(3),
    keywords=[Keyword.NECROTIC],
)
def m1978a3(c: Cast) -> None:
    """Three swings of the row that prints them.

    The card says three attacks and not three creatures, so a board with
    fewer than three enemies on it still gets three -- the reading that loses
    nothing, which is the one `_volley` settled on two levels down.
    """
    if not c.first:
        return
    picked = list(c.targets[:3])
    while picked and len(picked) < 3:
        picked.append(picked[0])
    for victim in picked:
        if alive(c.world, victim):
            c.use_power("m1978a1", on=victim, spend=False)


@power(
    "m1978a4",
    level=11,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
    out_of_combat=True,
)
def m1978a4(c: Cast) -> None:
    """Wearing a borrowed shape changes nothing a fight reads: size is the one
    mechanical half and the card lets it pick the size it already is."""
    c.note(f"{c.ref}: it looks like a Medium or Large humanoid until seen through")


@power(
    "m1978a5",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.kill()",),
)
def m1978a5(c: Cast) -> None:
    """Nothing kills outright. `c.coup_de_grace` finishes a helpless creature
    through an attack and the printed line is not an attack; dropping a
    creature to 0 is not death, which is the distinction the row turns on.
    The languages and the memories are not a combat clause at all."""


# ==========================================================================
# m2088
# ==========================================================================


@power(
    "m2088a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d6", 4),
)
def m2088a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2088a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.THUNDER],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("2d6", 6, dtype=DamageType.THUNDER),
)
def m2088a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2088a2",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.THUNDER],
    attack=Attack(vs=FORT, printed=14),
    damage=Damage("2d8", 5, dtype=DamageType.THUNDER, kind=LIMITED),
)
def m2088a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(3)


@power(
    "m2088a3",
    level=11,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.THUNDER],
    attack=Attack(vs=FORT, printed=14),
    damage=Damage("1d6", 3, dtype=DamageType.THUNDER, kind=LIMITED),
)
def m2088a3(c: Cast) -> None:
    """"First Failed Saving Throw" is `escalate`, which runs on a failed save
    and is handed the hold -- so the step ends the one it came from and lays
    the next. Two holds would be two saving throws against one sentence."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return

    def worsen(eff: Effect) -> None:
        c.world.effects.end(eff, "the ringing took it under")
        c.unconscious(until=When.SAVE_ENDS, on=victim)

    c.condition(Condition.DAZED, until=When.SAVE_ENDS, on=victim, escalate=worsen)


# ==========================================================================
# m2253
# ==========================================================================


@power(
    "m2253a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d8", 5),
)
def m2253a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)


@power(
    "m2253a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("2d8", 10, dtype=DamageType.NECROTIC),
)
def m2253a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized(until=When.SAVE_ENDS)


@power(
    "m2253a2",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    once_per_round=True,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=13),
    damage=Damage("3d8", 5, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m2253a2(c: Cast) -> None:
    """"Save ends both" is one effect carrying the two conditions."""
    if c.strike():
        c.hit()
        c.condition(
            Condition.DAZED, Condition.IMMOBILIZED, until=When.SAVE_ENDS
        )


@power(
    "m2253a3",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[Keyword.SUMMONING],
)
def m2253a3(c: Cast) -> None:
    """Five of another stat block's minions, put in the order as well as on
    the board -- which is what `c.summon` does and is the printed "take their
    turns immediately after".

    The printed recharge is a sentence on top of the die the database files,
    and it is this batch's last death that says it. Armed per use so the
    batch the listener counts is the batch that was just raised; the number
    stays in the header because that is what `actions.recharge` rolls.

    "Any unoccupied space within 10 squares" names no square, so the pool is
    sorted with the ones nearest an enemy first: `World.decide` is not asked
    here, and the lowest-sorted corner of the board is the difference between
    five minions in the fight and five standing in a field.
    """
    ref, me = c.ref, c.me
    raised: list[int] = []
    for where in _toward_the_foe(c, _free_near(c, me, 10))[:5]:
        eid = c.summon("m820", at=where)
        if eid:
            raised.append(eid)
    if not raised:
        return

    def dust(ev: Dropped) -> None:
        if ev.actor in raised and not any(alive(c.world, w) for w in raised):
            c.restore_use(ref)

    c.watch(Dropped, dust, until=When.ENCOUNTER, on=me, label=f"{ref} recharge")
    c.note(f"{ref}: the minions turn to dust at the end of the encounter")


# ==========================================================================
# m2295
# ==========================================================================


_M2295_SPHERE = "m2295a1 sphere"


def _m2295_sphere(world: World, eid: int) -> int | None:
    """The sphere m2295a1 left standing, if it is still on the board.

    A conjuration's `Ident.ref` is `c:<label>`, which is the only thing that
    says which row put it there. Written as a module function because a
    `requires=` gate is handed `(world, eid)` and no `Cast`.
    """
    for other, ident in world.each(Ident):
        if ident.ref == f"c:{_M2295_SPHERE}" and world.get(other, Position) is not None:
            return other
    return None


@power(
    "m2295a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d6", 5),
)
def m2295a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.NECROTIC)


@power(
    "m2295a1",
    level=11,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CONJURATION, Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("2d6", 5, dtype=DamageType.NECROTIC, kind=LIMITED),
    dropped=(
        "c.bonus('save:death')",
        "c.grant_action(move_zone)",
        "c.grant_action(standard)",
    ),
)
def m2295a1(c: Cast) -> None:
    """A sphere that swings, is sustained, and cannot be walked.

    `sustain=MINOR` with `until=SUSTAIN` is the printed minor and works. The
    other two printed actions do not. `conjure(speed=3)` records the distance
    on the sphere's own `Movement` and `c.move_zone` would carry it, but
    `actions.legal` never offers a move action spent on a conjuration -- the
    speed sits there unread. And `actions._granted` is only ever consulted for
    five words, so a standard action that makes the sphere attack again is
    carried and does nothing.

    "Adjacent to the sphere" is the sphere's own aura, which follows it when
    it moves and comes down with it. The toll is written out rather than
    handed to `c.burns`, because the printed line names one moment and
    `c.burns` bites at two.

    The square is the card's choice -- "an unoccupied square within range" --
    and it is put beside the creature the same sentence then attacks, because
    `c.conjure` left to itself lands next to the caster and the attack is
    against something *adjacent to the sphere*: a sphere set down ten squares
    from its victim makes the second half of the sentence false every time.

    The penalty to death saving throws is dropped: nothing holds a modifier
    the death save reads.
    """
    me = c.me
    victim = c.target
    beside = _free_near(c, victim, 1) if victim is not None else []
    sphere = c.conjure(
        at=beside[0] if beside else None,
        label=_M2295_SPHERE,
        until=When.SUSTAIN,
        sustain=MINOR,
        speed=3,
    )
    if not sphere:
        return
    ring = c.aura(1, on=sphere, label=f"{_M2295_SPHERE} reach", until=When.ENCOUNTER)

    def gnaw(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == me:
            return
        if ev.actor in c.world.zones.occupants(ring):
            c.damage("1d4", dtype=DamageType.NECROTIC, on=ev.actor)

    c.watch(TurnStart, gnaw, until=When.ENCOUNTER, on=me, label=_M2295_SPHERE)
    if victim is None or not c.adjacent_to(sphere, victim):
        return
    if c.strike(on=victim, from_=sphere):
        c.hit(on=victim)
        c.slide(1, on=victim)


@power(
    "m2295a2",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(3, 10),
    target=NO_TARGET,
    attack=Attack(vs=FORT, printed=15),
    requires=lambda world, eid: _m2295_sphere(world, eid) is not None,
    requires_text="the m2295a1 sphere must be on the board",
)
def m2295a2(c: Cast) -> None:
    """The burst is centred on the sphere rather than on a square the engine
    chose, so the row declares no target and gathers them itself; the pull is
    anchored on the sphere, which is what "toward the sphere" means.

    No damage line: the pull is the whole of a hit.
    """
    sphere = _m2295_sphere(c.world, c.me)
    if sphere is None:
        return
    anchor = c.world.get(sphere, Position)
    for who in sorted(c.within(3, of=sphere)):
        if who == c.me or not alive(c.world, who):
            continue
        if c.strike(on=who) and anchor is not None:
            c.pull(1, on=who, anchor=anchor.square)


@power(
    "m2295a3",
    level=11,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=CloseBlast(5),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("1d8", 3, dtype=DamageType.NECROTIC),
)
def m2295a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.NECROTIC)


# ==========================================================================
# m2543
# ==========================================================================


@power(
    "m2543a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d8", 4, dtype=DamageType.FIRE),
)
def m2543a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2543a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=14),
    damage=Damage("2d6", 6),
)
def m2543a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(3)


@power(
    "m2543a2",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_ENEMY,
    attack=Attack(vs=REF, printed=13),
    damage=Damage("2d8", 4, kind=LIMITED),
)
def m2543a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS)


@power(
    "m2543a3",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.ignores_hazards()",),
)
def m2543a3(c: Cast) -> None:
    """Crossing the stuff it lives in costs it nothing, which is a label the
    map and `c.zone(difficult=...)` both give their squares.

    "Takes no damage from contact with it" is the other half: a map feature
    that hurts whoever touches it is a hazard, and nothing exempts one
    creature from one.
    """
    c.ignores_difficult("blood", until=When.ENCOUNTER)


# ==========================================================================
# m2615
# ==========================================================================


@power(
    "m2615a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d10", 5),
)
def m2615a0(c: Cast) -> None:
    """The printed "(+17 while bloodied)" is m2615a5 showing through and is
    laid there, not here: two +1s would be +2."""
    if c.strike():
        c.hit()


@power(
    "m2615a1",
    level=11,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d10"),
)
def m2615a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(2)


@power(
    "m2615a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=UpTo(2),
    keywords=[Keyword.IMPLEMENT, Keyword.RADIANT],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("2d6", 3, dtype=DamageType.RADIANT),
)
def m2615a2(c: Cast) -> None:
    """The ally's half is printed once for the whole use, so it is guarded by
    `c.first`, and the choice between the two benefits is the card's "or"."""
    if c.strike():
        c.hit()
    if not c.first:
        return
    seen = sorted(f for f in c.allies() if c.can_see(f))
    friend = c.choose(seen, f"{c.ref}: which ally it steadies") if seen else None
    if friend is None:
        return
    if c.may("take 6 temporary hit points rather than a saving throw", who=friend):
        c.temp_hp(6, on=friend)
    else:
        c.save(on=friend)


@power(
    "m2615a3",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[
        Keyword.ACID,
        Keyword.COLD,
        Keyword.FIRE,
        Keyword.LIGHTNING,
        Keyword.POISON,
    ],
    attack=Attack(vs=REF, printed=14),
    damage=Damage("2d6", 4, dtype=DamageType.ACID),
    dropped=("Damage(dtypes=)",),
)
def m2615a3(c: Cast) -> None:
    """One blow of five types. The header holds one of them; the printed
    parenthetical repeats the base attack total rather than raising it, which
    is the card re-totalling and not a second modifier."""
    if c.strike():
        c.hit()


@power(
    "m2615a4",
    level=11,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(4),
    target=EACH_ENEMY,
    keywords=[
        Keyword.ACID,
        Keyword.COLD,
        Keyword.FIRE,
        Keyword.IMPLEMENT,
        Keyword.LIGHTNING,
        Keyword.POISON,
    ],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("3d10", 4, dtype=DamageType.ACID, kind=LIMITED),
    dropped=("Damage(dtypes=)",),
)
def m2615a4(c: Cast) -> None:
    """A burst against AC, which is unusual and is what the card prints. Its
    bloodied parenthetical is one *lower* than the base, which settles that
    the parentheticals on this stat block are not a rule."""
    if c.strike():
        c.hit()
        c.condition(Condition.SLOWED, until=When.SAVE_ENDS)


@power(
    "m2615a5",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2615a5(c: Cast) -> None:
    """A racial bonus -- the word the card prints before "bonus" -- gated on
    its own health, which is asked as each swing is rolled rather than taken
    once now."""
    c.bonus(
        "attack",
        1,
        on=c.me,
        until=When.ENCOUNTER,
        kind="racial",
        when=lambda _ctx: c.bloodied(c.me),
    )


# ==========================================================================
# m2788
# ==========================================================================


@power(
    "m2788a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.RADIANT],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("2d4", 5, dtype=DamageType.PSYCHIC),
    dropped=("Damage(dtypes=)", "c.cannot_attack(opportunity=)"),
)
def m2788a0(c: Cast) -> None:
    """Two clauses short of the card and both are narrowings.

    One blow of two types keeps the first in the header. And `c.cannot_attack`
    can bar every attack against one creature but not one *kind* of attack,
    which is what "cannot make opportunity attacks against it" asks -- barring
    the lot would take away the ordinary swing the card leaves alone.
    """
    if c.strike():
        c.hit()


@power(
    "m2788a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING, Keyword.RADIANT],
    attack=Attack(vs=WILL, printed=15),
    damage=Damage("1d8", 5, dtype=DamageType.LIGHTNING),
    dropped=("Damage(dtypes=)",),
)
def m2788a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.EONT)


@power(
    "m2788a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
)
def m2788a2(c: Cast) -> None:
    """Two swings, or a step and one swing.

    Declared with no target: the shift happens first on the second branch, so
    there is nobody to aim at until it has been taken.
    """
    both = "two attacks"
    pick = c.choose([both, "step away and swing once"], f"{c.ref}: how it fights")
    if pick == both:
        for _ in range(2):
            prey = _adjacent_foe(c, c.ref)
            if prey is None:
                break
            c.basic(on=prey)
        return
    c.shift(3)
    prey = _adjacent_foe(c, c.ref)
    if prey is not None:
        c.basic(on=prey)


@power(
    "m2788a3",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=FORT, printed=14),
    damage=Damage("3d6", 5, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m2788a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(3)
        c.prone()


_M2788_FAILING = "it would fail an attack roll, a saving throw or a check"


def _m2788_bad_attack(world: World, me: int, ev: AttackRolled) -> bool:
    result = getattr(ev, "result", None)
    return ev.attacker == me and result is not None and not result.hit


def _m2788_bad_save(world: World, me: int, ev: SavingThrow) -> bool:
    return ev.actor == me and not ev.saved


def _m2788_bad_check(world: World, me: int, ev: SkillCheck) -> bool:
    return ev.actor == me and not ev.success


@power(
    "m2788a4",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M2788_FAILING,
    on=(
        Trigger(AttackRolled, when=_m2788_bad_attack, text=_M2788_FAILING),
        Trigger(SavingThrow, when=_m2788_bad_save, text=_M2788_FAILING),
        Trigger(SkillCheck, when=_m2788_bad_check, text=_M2788_FAILING),
    ),
)
def m2788a4(c: Cast) -> None:
    """One printed sentence over three kinds of roll, so `on=` takes three
    triggers; declaring one of them would look finished and be a third right.

    An attack is raised on the live `AttackResult`, which `resolve.attack`
    re-reads after the window closes -- that is the only lever that still
    works once the die is down. A saving throw's own `saved` is read back, so
    the new total is compared there. A check has a verb of its own.
    """
    me = c.me
    _recharge_on(c, Bloodied, lambda ev: ev.actor == me)
    ev = c.trigger
    added = c.roll("1d6")
    if isinstance(ev, AttackRolled):
        result = getattr(ev, "result", None)
        if result is not None:
            result.total += added
            result.hit = result.total >= ev.defence
        return
    if isinstance(ev, SavingThrow):
        ev.saved = ev.natural + ev.bonus + added >= 10
        return
    if isinstance(ev, SkillCheck):
        c.boost_check(added)


# ==========================================================================
# m3246
# ==========================================================================


@power(
    "m3246a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d6", 5, dtype=DamageType.PSYCHIC),
)
def m3246a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.EONT)


@power(
    "m3246a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("2d6", 7, dtype=DamageType.PSYCHIC),
)
def m3246a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(2)


@power(
    "m3246a2",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=15),
    damage=Damage("3d8", 7, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m3246a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized(until=When.SAVE_ENDS)


@power(
    "m3246a3",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PSYCHIC],
)
def m3246a3(c: Cast) -> None:
    """The penalty is taken at the start of a turn and runs to the start of
    the next one, which is `SOTNT` -- the target's clock, not the caster's."""
    me = c.me
    ring = c.aura(2, until=When.ENCOUNTER)

    def cow(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == me or ev.actor not in c.enemies():
            return
        if ev.actor in c.world.zones.occupants(ring):
            c.penalty(WILL, 2, on=ev.actor, until=When.SOTNT)

    c.watch(TurnStart, cow, until=When.ENCOUNTER, on=me, label=c.ref)


# ==========================================================================
# m3274
# ==========================================================================


@power(
    "m3274a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d6", 7),
)
def m3274a0(c: Cast) -> None:
    """"Until it moves more than 5 squares away" is a clock no duration says,
    so the hold runs to the end of the fight and is torn down by the first
    step that puts the victim clear. Measured on `Moved`, which is the event
    that fires once the creature has actually got there."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    me = c.me
    exposed = c.vulnerable(5, DamageType.NECROTIC, until=When.ENCOUNTER, on=victim)
    if exposed is None:
        return

    def strolled(ev: Moved) -> None:
        if ev.actor != victim or exposed.ended:
            return
        if distance_between(c.world, me, victim) > 5:
            c.world.effects.end(exposed, "it got clear")

    exposed.subs.append(c.world.bus.on(Moved, strolled, owner=me))


@power(
    "m3274a1",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("1d10", 3, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m3274a1(c: Cast) -> None:
    """"Save ends both" is one effect carrying the burn and the slow."""
    if not c.strike():
        return
    c.hit()
    if c.target is not None:
        c.world.effects.apply(
            c.target,
            c.me,
            When.SAVE_ENDS,
            label=c.ref,
            conditions=(Condition.SLOWED,),
            ongoing=(5, DamageType.NECROTIC),
        )


@power(
    "m3274a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(3, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("2d10", 3, dtype=DamageType.NECROTIC),
)
def m3274a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized(until=When.SAVE_ENDS)


# ==========================================================================
# m3939
# ==========================================================================


@power(
    "m3939a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d6", 5),
)
def m3939a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3939a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=15),
    damage=Damage("1d8", 5),
)
def m3939a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.DOMINATED, until=When.SAVE_ENDS)


@power(
    "m3939a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
)
def m3939a2(c: Cast) -> None:
    """Two of one row or two of the other, which is the card's "either".

    The claw the sentence names is this creature's own melee line; a reach of
    20 is declared so the chooser can hand it a victim for the ranged branch,
    and the melee branch asks adjacency itself.
    """
    victim = c.target
    if victim is None:
        return
    reach = "two at range"
    pick = c.choose([reach, "two in reach"], f"{c.ref}: which pair")
    if pick == reach:
        for _ in range(2):
            if alive(c.world, victim):
                c.use_power("m3939a1", on=victim, spend=False)
        return
    for _ in range(2):
        prey = victim if c.adjacent(victim) else _adjacent_foe(c, c.ref)
        if prey is None:
            break
        c.use_power("m3939a0", on=prey, spend=False)


@power(
    "m3939a3",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    attack=Attack(vs=WILL, printed=13),
    damage=Damage("2d6", 5),
)
def m3939a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(3)
        c.dazed(until=When.SAVE_ENDS)


@power(
    "m3939a4",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    attack=Attack(vs=WILL, printed=13),
    damage=Damage("1d8", 5),
)
def m3939a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(2)
        c.immobilized(until=When.SAVE_ENDS)


@power(
    "m3939a5",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    once_per_round=True,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.SUMMONING],
    requires=lambda world, eid: bool(
        (h := world.get(eid, Health)) and h.hp * 2 <= h.max_hp
    ),
    requires_text="usable only while bloodied",
    todo=("etl.monster.summon_ref()",),
)
def m3939a5(c: Cast) -> None:
    """What it spawns is printed as this ability's own id, so the extraction
    kept no stat block for the thing arriving. `c.summon` wants a ref and
    there is none to give it."""


# ==========================================================================
# m4460
# ==========================================================================


_M4460_INSIDE = "m4460a1 inundated"


@power(
    "m4460a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.POISON],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("2d6", 3, dtype=DamageType.NECROTIC),
)
def m4460a0(c: Cast) -> None:
    """Two separately named amounts, so two packets rather than one blow of
    two types -- the poison is rolled on its own and needs no marker."""
    if c.strike():
        c.hit()
        c.damage("1d6", dtype=DamageType.POISON)


@power(
    "m4460a1",
    level=11,
    usage=ENCOUNTER,
    action=MINOR,
    reach=Melee(2),
    target=Target(side="enemy", count=1, label="bloodied"),
    keywords=[
        Keyword.CHARM,
        Keyword.NECROTIC,
        Keyword.POISON,
        Keyword.RELIABLE,
    ],
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("3d6", 6, dtype=DamageType.NECROTIC, kind=LIMITED),
    dropped=("Target.bloodied",),
)
def m4460a1(c: Cast) -> None:
    """It pours itself over somebody and the two of them share a square.

    `c.shares_space` is the standing property that lets anyone into a
    creature's square, which is the half the engine can say; the m4460 then
    steps in. The mirrored damage is read off `DamageApplied`, the only event
    that says how much actually landed.

    The Aftereffect is the hold's `on_end` -- it follows the hold going
    whichever way it went -- and the aftereffect's own ending is what moves
    the m4460 back out, which is the printed order.
    """
    me = c.me
    victim = _restricted_to(c, 2, lambda who: c.bloodied(who))
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)
    here = c.world.get(victim, Position)
    inside = c.world.effects.apply(
        victim,
        me,
        When.SAVE_ENDS,
        label=_M4460_INSIDE,
        conditions=(Condition.DOMINATED,),
        ongoing=(5, DamageType.POISON),
    )
    sharing = c.shares_space(on=victim, until=When.ENCOUNTER, difficult=False)
    if sharing is not None:
        inside.on_end.append(lambda: c.world.effects.end(sharing, "it drained away"))
    if here is not None:
        c.teleport(_step(c.here, here.square), to=here.square)
    _damage_mirror(c, victim, inside)

    def flows_out() -> None:
        free = _free_near(c, victim, 3)
        if free:
            c.teleport(_step(c.here, free[0]), to=free[0])

    def aftereffect() -> None:
        burn = c.ongoing(5, DamageType.POISON, on=victim)
        if burn is not None:
            burn.on_end.append(flows_out)

    inside.on_end.append(aftereffect)


@power(
    "m4460a2",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.POISON],
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("1d6", 2, dtype=DamageType.NECROTIC, kind=LIMITED),
    dropped=("c.conceal(against=)",),
)
def m4460a2(c: Cast) -> None:
    """"Recharges when bloodied" is a sentence on top of the die the database
    files, and the two only ever agree to make the row available sooner.

    "All creatures have concealment against the target" is the clause with no
    verb: `c.conceal` gives concealment *to* a creature and nothing makes a
    creature's own attacks treat everybody as concealed.
    """
    me = c.me
    _recharge_on(c, Bloodied, lambda ev: ev.actor == me)
    if not c.strike():
        return
    c.hit()
    c.ongoing(10, DamageType.POISON)


_M4460_STRUCK = "it is hit by an attack"


@power(
    "m4460a3",
    level=11,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC],
    trigger=_M4460_STRUCK,
    on=Trigger(Hit, targets_me, _M4460_STRUCK),
)
def m4460a3(c: Cast) -> None:
    """`Hit` carries `attacker` and `target` and no `actor`, so `targets_me`
    is the predicate that reads it. No attack roll: the splash lands."""
    c.flat(5, dtype=DamageType.NECROTIC)


@power(
    "m4460a4",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("2d6", 3, dtype=DamageType.NECROTIC, kind=LIMITED),
    dropped=("c.sustain_free()",),
)
def m4460a4(c: Cast) -> None:
    """The grab lands and the printed Sustain Free does not: a sustain is held
    at minor, move or standard and a free one is not a cost the sustain
    machinery takes, so the toll it pays out has nowhere to hang."""
    if c.strike():
        c.hit()
        c.grab()


@power(
    "m4460a5",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC, Keyword.POISON],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("1d6", 5, dtype=DamageType.NECROTIC),
    dropped=("Damage(dtypes=)",),
)
def m4460a5(c: Cast) -> None:
    """One blow of two types rolled once; the header holds the first."""
    if c.strike():
        c.hit()


# ==========================================================================
# m4488
# ==========================================================================


@power(
    "m4488a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d6", 4),
)
def m4488a0(c: Cast) -> None:
    """"A -2 penalty to all defenses" is four penalties, one per defence."""
    if not c.strike():
        return
    c.hit()
    for defended in EVERY_DEFENCE:
        c.penalty(defended, 2, until=When.EONT)


@power(
    "m4488a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(4),
    target=EACH_ENEMY,
    keywords=[Keyword.IMPLEMENT],
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("1d6", 2),
)
def m4488a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(2)


_M4488_SPENT = "an enemy within 5 squares spends an action point"


def _m4488_spent(world: World, me: int, ev: ActionPointSpent) -> bool:
    from combat_engine.engine.query import enemies

    return ev.actor in enemies(world, me) and distance_between(world, me, ev.actor) <= 5


@power(
    "m4488a2",
    level=11,
    usage=ENCOUNTER,
    action=REACTION,
    reach=CloseBurst(5),
    target=NO_TARGET,
    trigger=_M4488_SPENT,
    on=Trigger(ActionPointSpent, when=_m4488_spent, text=_M4488_SPENT),
    todo=("c.grant_action(standard)",),
)
def m4488a2(c: Cast) -> None:
    """"Takes a standard action as a free action" names no word
    `actions._granted` is ever read for -- it knows instinctive, command,
    stand, escape and shift -- so a sixth is carried and does nothing. The
    trigger itself is exact: `ActionPointSpent` names the spender."""


_M4488_LANDED = "it hits with an attack"


@power(
    "m4488a3",
    level=11,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M4488_LANDED,
    on=Trigger(Hit, by_me, _M4488_LANDED),
)
def m4488a3(c: Cast) -> None:
    """It pays in its own blood. "One target hit by the triggering attack" is
    read off the event rather than off `ev.targets`: an immediate action is
    aimed at nothing of its own, so the only trustworthy name is the one the
    trigger carries."""
    ev = c.trigger
    victim = getattr(ev, "target", None)
    if victim is None or not alive(c.world, victim):
        return
    c.flat(5, on=c.me)
    c.damage("3d6", on=victim)


# ==========================================================================
# m4603
# ==========================================================================


@power(
    "m4603a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("3d4", 4),
)
def m4603a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4603a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(5),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=15),
    damage=Damage("2d8", 4),
)
def m4603a1(c: Cast) -> None:
    """The die is rolled per hit, which is what a printed table on a hit
    means, and the two shorter holds run on the victim's own clock."""
    if not c.strike():
        return
    c.hit()
    rolled = c.roll("1d6")
    if rolled <= 3:
        c.prone()
    elif rolled <= 5:
        c.slowed(until=When.EOTNT)
    else:
        c.dazed(until=When.EOTNT)


@power(
    "m4603a2",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_ENEMY,
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("3d8", 5, kind=LIMITED),
)
def m4603a2(c: Cast) -> None:
    """The sixth result is two modifiers under one saving throw, which is one
    effect: `skill` is the blanket key `engine/skills.py` reads alongside the
    per-skill one, so "all skill checks" has somewhere to go."""
    if not c.strike():
        return
    c.hit()
    c.prone()
    victim = c.target
    if victim is None:
        return
    rolled = c.roll("1d6")
    if rolled <= 3:
        c.condition(Condition.SLOWED, until=When.SAVE_ENDS, on=victim)
    elif rolled == 4:
        c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS, on=victim)
    elif rolled == 5:
        c.condition(Condition.DAZED, until=When.SAVE_ENDS, on=victim)
    else:
        c.world.effects.apply(
            victim,
            c.me,
            When.SAVE_ENDS,
            label=c.ref,
            mods=[
                (victim, Mod(what="attack", value=-2, kind="untyped", label=c.ref)),
                (victim, Mod(what="skill", value=-2, kind="untyped", label=c.ref)),
            ],
        )


@power(
    "m4603a3",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4603a3(c: Cast) -> None:
    """A plain "+2 bonus" with no type word is untyped, so `kind=` is left
    off. The count is asked as a defence is read rather than taken now, which
    is what makes it follow the fight: `query.defence` passes whatever context
    it has to `Mods.total` and a gate that only looks at the board is true
    whenever it is true."""
    me = c.me

    def flanked_by_friends(_ctx: dict[str, Any]) -> bool:
        return len(c.within(5, of=me, side="ally")) >= 2

    for defended in EVERY_DEFENCE:
        c.bonus(
            defended, 2, on=me, until=When.ENCOUNTER, when=flanked_by_friends
        )


# ==========================================================================
# m4665
# ==========================================================================


@power(
    "m4665a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("2d8", 5, dtype=DamageType.ACID),
)
def m4665a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.ACID)


def _holds_nobody(world: World, eid: int) -> bool:
    """"Usable only when no creatures are engulfed."

    A fact that changes during a fight, so it is also asked in the body; a
    `requires=` on a *standard action* row is re-read every time the row is
    offered, which is where this one is safe.
    """
    return not world.relations.targets(Relation.GRABBED_BY, eid)


@power(
    "m4665a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=Target(side="enemy", count=1, max_size=Size.MEDIUM),
    keywords=[Keyword.ACID],
    attack=Attack(vs=REF, printed=15),
    requires=_holds_nobody,
    requires_text="usable only when nothing is engulfed",
    dropped=("c.engulf()",),
)
def m4665a1(c: Cast) -> None:
    """Swallowing somebody, as far as the engine holds it.

    The grab, the daze and the burn are exact, and so is the automatic hit
    against an immobilised creature. What `c.engulf` would add is the rest of
    one printed concept: the victim carried along when the ooze moves, no
    opening given to it, and a shift out of the square when the grab breaks.

    No damage line at all: the hold is the whole of a hit.
    """
    victim = c.target
    if victim is None:
        return
    held = c.is_(Condition.IMMOBILIZED, on=victim) or c.strike(on=victim)
    if not held:
        return
    c.pull(3, on=victim)
    grabbed = c.grab(on=victim)
    if grabbed is None:
        return
    swallowed = c.world.effects.apply(
        victim,
        c.me,
        When.ENCOUNTER,
        label=c.ref,
        conditions=(Condition.DAZED,),
        ongoing=(10, DamageType.ACID),
    )
    grabbed.on_end.append(
        lambda: c.world.effects.end(swallowed, "the grab ended")
    )


@power(
    "m4665a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("2d8", 9, dtype=DamageType.ACID),
)
def m4665a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.pull(3)


@power(
    "m4665a3",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.ACID, Keyword.ZONE],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("1d8", 5, dtype=DamageType.ACID, kind=LIMITED),
    dropped=("c.zone(exempt=)",),
)
def m4665a3(c: Cast) -> None:
    """The zone is laid on the first pass, because its Effect line is printed
    beside the attack rather than under a hit.

    Rough ground in a zone is rough for everybody; "difficult terrain for its
    enemies" needs the zone to know whose side to let past, and nothing does.
    """
    if c.first:
        c.zone(c.area(), label=c.ref, until=When.EONT, difficult=c.ref)
    if c.target is None or not c.strike():
        return
    c.hit()
    if c.target is not None:
        c.world.effects.apply(
            c.target,
            c.me,
            When.SAVE_ENDS,
            label=c.ref,
            conditions=(Condition.IMMOBILIZED,),
            ongoing=(5, DamageType.ACID),
        )


@power(
    "m4665a4",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
)
def m4665a4(c: Cast) -> None:
    """The type of a packet can only be read off `DamageApplied`, and
    `about_me` would be false here forever: that event names its subject
    `target`."""
    me = c.me

    def scald(ev: DamageApplied) -> None:
        if ev.target != me or ev.amount <= 0 or ev.dtype is not DamageType.FIRE:
            return
        for caught in sorted(c.grabbing()):
            c.flat(10, dtype=DamageType.FIRE, on=caught)

    c.watch(DamageApplied, scald, until=When.ENCOUNTER, on=me, label=c.ref)


# ==========================================================================
# m5525
# ==========================================================================


@power(
    "m5525a0",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5525a0(c: Cast) -> None:
    """"Allies within the aura" leaves the m5525 out, which is the printed
    word and what `side="ally"` means. A power bonus, because that is the word
    the card prints in front of "bonus"."""
    ring = c.aura(1, until=When.ENCOUNTER)
    c.grants_in(ring, "damage", 2, side="ally", kind="power")


@power(
    "m5525a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d8", 10),
)
def m5525a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.penalty("attack", 2, until=When.EONT)


@power(
    "m5525a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("4d4", 9),
)
def m5525a2(c: Cast) -> None:
    """A secondary attack against a different defence cannot live in the
    header, so its printed +16 is trimmed by hand the way `Attack.bonus_for`
    trims the header's. The temporary hit points belong to the secondary's own
    hit, which is where the card prints them."""
    victim = c.target
    if victim is None or not c.strike(on=victim):
        return
    c.prone(on=victim)
    if not c.attack(c.world.scaling.trim(16, c.level), AC, on=victim, as_="secondary"):
        return
    c.hit(on=victim)
    c.condition(Condition.DAZED, until=When.SAVE_ENDS, on=victim)
    for friend in c.allies():
        if c.can_see(friend) and not c.is_minion(on=friend):
            c.temp_hp(10, on=friend)


@power(
    "m5525a3",
    level=11,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=15),
)
def m5525a3(c: Cast) -> None:
    """No damage line: the haul and the opening are the whole of a hit."""
    if c.strike():
        c.pull(5)
        c.grants_advantage(until=When.EONT, to="team")


_M5525_BLED = "it is first bloodied"


@power(
    "m5525a4",
    level=11,
    usage=ENCOUNTER,
    action=REACTION,
    reach=CloseBurst(5),
    target=EACH_ALLY,
    trigger=_M5525_BLED,
    on=Trigger(Bloodied, by_me, _M5525_BLED),
)
def m5525a4(c: Cast) -> None:
    """A plain "+2 bonus" with no type word is untyped."""
    c.bonus("attack", 2, until=When.EONT)


# ==========================================================================
# m5550
# ==========================================================================


@power(
    "m5550a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d8", 10),
)
def m5550a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5550a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, 5),
    target=EACH_CREATURE,
    attack=Attack(vs=FORT, printed=14),
)
def m5550a1(c: Cast) -> None:
    """No damage line at all: the penalty is the whole of a hit, and the Miss
    line is the same penalty on a shorter clock.

    "First Failed Saving Throw" is `escalate`, handed the hold so the step can
    end the one it came from rather than laying a second saving throw beside
    it.
    """
    victim = c.target
    if victim is None:
        return
    if not c.strike(on=victim):
        c.penalty("attack", 2, on=victim, until=When.EONT)
        return

    def worsen(eff: Effect) -> None:
        c.world.effects.end(eff, "it went under")
        c.unconscious(until=When.SAVE_ENDS, on=victim)

    c.world.effects.apply(
        victim,
        c.me,
        When.SAVE_ENDS,
        label=c.ref,
        mods=[(victim, m) for m in _softened(c, attack=2)],
        escalate=worsen,
    )


# ==========================================================================
# m5820
# ==========================================================================


@power(
    "m5820a0",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5820a0(c: Cast) -> None:
    """Two clauses on one aura: a hold carried for as long as a creature is
    inside, and a toll taken at the end of a turn -- which is neither of the
    two moments `c.burns` covers."""
    me = c.me
    ring = _aura(
        c,
        2,
        lambda who: who != me and who in c.enemies(),
        lambda who: c.cannot_shift(on=who, until=When.ENCOUNTER),
    )

    def flail(who: int) -> None:
        if who in c.enemies():
            c.flat(5, on=who)

    _ends_its_turn_in(c, ring, flail)


@power(
    "m5820a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d10", 5),
)
def m5820a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(10, DamageType.FIRE)
        c.slide(3)


@power(
    "m5820a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.IMPLEMENT, Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=14),
    damage=Damage("2d6", 7, dtype=DamageType.FIRE),
    dropped=("Damage(dtypes=)",),
)
def m5820a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.EONT)


@power(
    "m5820a3",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.FIRE, Keyword.IMPLEMENT],
    attack=Attack(vs=REF, printed=14),
    damage=Damage("2d8", 5, kind=LIMITED, half_on_miss=True),
)
def m5820a3(c: Cast) -> None:
    """`half_on_miss` is card data and no line of the engine reads it, so the
    Miss branch is written out as well."""
    if not c.strike():
        c.hit(half=True)
        return
    c.hit()
    if c.target is not None:
        c.world.effects.apply(
            c.target,
            c.me,
            When.SAVE_ENDS,
            label=c.ref,
            conditions=(Condition.RESTRAINED,),
            ongoing=(10, DamageType.FIRE),
        )


@power(
    "m5820a4",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    keywords=[Keyword.FIRE],
)
def m5820a4(c: Cast) -> None:
    """"Until those temporary hit points are gone" is a clock no duration
    says, so the bonus stands to the end of the fight and is gated on the
    bearer's own `Health.temp` -- read as a blow is rolled, which is the only
    moment the answer matters.

    "Recharge when first bloodied" is a sentence on top of the die the
    database files.
    """
    me = c.me
    _recharge_on(c, Bloodied, lambda ev: ev.actor == me)
    friend = c.target
    if friend is None:
        return
    c.slide(3, on=friend)
    c.temp_hp(20, on=friend)

    def still_burning(ctx: dict[str, Any]) -> bool:
        return _temp_left(c, friend) and _melee_ctx(ctx)

    c.bonus(
        "damage",
        5,
        on=friend,
        until=When.ENCOUNTER,
        dtype=DamageType.FIRE,
        when=still_burning,
    )


_M5820_STRUCK = "an enemy within 3 squares hits it"


def _m5820_struck(world: World, me: int, ev: Hit) -> bool:
    from combat_engine.engine.query import enemies

    if ev.target != me or ev.attacker not in enemies(world, me):
        return False
    return distance_between(world, me, ev.attacker) <= 3


@power(
    "m5820a5",
    level=11,
    usage=AT_WILL,
    action=REACTION,
    reach=CloseBurst(3),
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=WILL, printed=14),
    damage=Damage("2d10", 7, dtype=DamageType.FIRE),
    trigger=_M5820_STRUCK,
    on=Trigger(Hit, when=_m5820_struck, text=_M5820_STRUCK),
)
def m5820a5(c: Cast) -> None:
    """The burst names the triggering enemy and nobody else, so the row
    declares no target of its own and aims itself off the trigger -- which is
    the name that can be trusted on an immediate action."""
    ev = c.trigger
    foe = getattr(ev, "attacker", None)
    if foe is None or not alive(c.world, foe):
        return
    if c.strike(on=foe):
        c.hit(on=foe)
        c.weakened(on=foe, until=When.EOTNT)


# ==========================================================================
# m5870
# ==========================================================================




@power(
    "m5870a0",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC, Keyword.PSYCHIC],
    dropped=("c.no_surges()",),
)
def m5870a0(c: Cast) -> None:
    """The toll and the temporary hit points are exact; a blow of two types is
    `c.flat(dtypes=)`, which takes a list where the header cannot.

    Barring healing surges is the clause with no verb: `c.no_healing` refuses
    *all* healing, which is a different rule, and `SurgeSpent` is a plain
    event with nothing to cancel.
    """
    me = c.me
    ring = c.aura(1, until=When.ENCOUNTER)

    def drain(who: int) -> None:
        if who not in c.enemies():
            return
        c.flat(
            10,
            dtypes=(DamageType.NECROTIC, DamageType.PSYCHIC),
            on=who,
        )
        c.temp_hp(5, on=me)

    _ends_its_turn_in(c, ring, drain)


@power(
    "m5870a1",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.insubstantial(except_=)",),
)
def m5870a1(c: Cast) -> None:
    """Half damage from everything, which is what insubstantial is, and the
    printed exceptions are what it cannot carry: `Condition.INSUBSTANTIAL` has
    one built-in exemption -- force, and only when the attacker's own row
    grants it -- where this card names three unconditionally.

    The suppression is exact and is the half worth having: a fire or radiant
    packet takes the hold off and the start of its next turn puts it back.
    """
    me = c.me

    def shroud() -> Effect | None:
        return c.insubstantial(on=me, until=When.ENCOUNTER)

    held: list[Effect | None] = [shroud()]

    def doused(ev: DamageApplied) -> None:
        if ev.target != me or ev.amount <= 0:
            return
        if ev.dtype not in (DamageType.FIRE, DamageType.RADIANT):
            return
        standing = held[0]
        if standing is not None and not standing.ended:
            c.world.effects.end(standing, "the light burned it off")
            held[0] = None

    def mended(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me:
            return
        if held[0] is None or held[0].ended:
            held[0] = shroud()

    c.watch(DamageApplied, doused, until=When.ENCOUNTER, on=me, label=f"{c.ref} out")
    c.watch(TurnStart, mended, until=When.ENCOUNTER, on=me, label=f"{c.ref} back")


@power(
    "m5870a2",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.move_through()",),
)
def m5870a2(c: Cast) -> None:
    """Both clauses are about where this creature may go, and the engine only
    says the opposite: `c.shares_space` lets everybody into *its* square,
    which is a different sentence, and `c.phasing` crosses solid rock, which
    is a larger one. Nothing lets one creature stand in another's space."""


@power(
    "m5870a3",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=14),
    damage=Damage("3d6", 9, dtype=DamageType.NECROTIC),
)
def m5870a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(2)


@power(
    "m5870a4",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[
        Keyword.CHARM,
        Keyword.GAZE,
        Keyword.NECROTIC,
        Keyword.PSYCHIC,
    ],
    attack=Attack(vs=WILL, printed=14),
)
def m5870a4(c: Cast) -> None:
    """No damage line on the hit: the domination is the whole of it, and the
    blow is the Aftereffect -- the hold's `on_end`, which follows it going
    whichever way it went.

    "Recharges when no creature is dominated by this power" is a sentence on
    top of the die, and it is the hold's own ending that announces it.
    """
    me, ref = c.me, c.ref
    _recharge_on(c, Dropped, lambda ev: not c.suffering(ref, by=me))
    victim = c.target
    if victim is None or not c.strike(on=victim):
        return
    held = c.world.effects.apply(
        victim, me, When.SAVE_ENDS, label=ref, conditions=(Condition.DOMINATED,)
    )
    held.on_end.append(
        lambda: c.damage(
            "2d8",
            10,
            dtypes=(DamageType.NECROTIC, DamageType.PSYCHIC),
            on=victim,
        )
    )


_M5870_BLED = "it is first bloodied"


@power(
    "m5870a5",
    level=11,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    attack=Attack(vs=FORT, printed=14),
    trigger=_M5870_BLED,
    on=Trigger(Bloodied, by_me, _M5870_BLED),
    dropped=("c.no_surges()",),
)
def m5870a5(c: Cast) -> None:
    """No damage line: the shove is the whole of a hit. Barring healing surges
    is the same gap m5870a0 has -- `c.no_healing` would refuse every kind of
    healing, which the card does not say."""
    if c.strike():
        c.push(3)


# ==========================================================================
# m5922
# ==========================================================================


@power(
    "m5922a0",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m5922a0(c: Cast) -> None:
    """Speaking without speaking changes nothing a fight reads: there is no
    communication in the engine to grant and no roll it bears on."""
    c.note(f"{c.ref}: it speaks mind to mind with anything within 10 squares")


@power(
    "m5922a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d8", 10),
)
def m5922a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(1)


@power(
    "m5922a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=14),
    damage=Damage("2d6", 12, dtype=DamageType.PSYCHIC),
)
def m5922a2(c: Cast) -> None:
    """Two steps of escalation, each handed the hold it replaces.

    The penalty is narrowed to attacks that include the m5922, which the
    attack context can be asked: it carries the target being swung at. The
    second step is printed "instead", so the penalty goes with it.
    """
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    me = c.me

    def aimed_at_me(ctx: dict[str, Any]) -> bool:
        return ctx.get("target") == me

    shy = Mod(what="attack", value=-2, kind="untyped", label=c.ref, when=aimed_at_me)

    def second(eff: Effect) -> None:
        c.world.effects.end(eff, "it gave in")
        c.condition(Condition.DOMINATED, until=When.SAVE_ENDS, on=victim)

    def first(eff: Effect) -> None:
        c.world.effects.end(eff, "the whispering got louder")
        c.world.effects.apply(
            victim,
            me,
            When.SAVE_ENDS,
            label=c.ref,
            conditions=(Condition.DAZED,),
            mods=[(victim, shy)],
            escalate=second,
        )

    c.world.effects.apply(
        victim,
        me,
        When.SAVE_ENDS,
        label=c.ref,
        mods=[(victim, shy)],
        escalate=first,
    )


@power(
    "m5922a3",
    level=11,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.CHARM, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=14),
    damage=Damage("3d8", 15, dtype=DamageType.PSYCHIC, kind=LIMITED, half_on_miss=True),
)
def m5922a3(c: Cast) -> None:
    """The Miss line carries a hold of its own as well as half the damage, so
    both halves are written out."""
    if c.strike():
        c.hit()
        c.immobilized(until=When.SAVE_ENDS)
    else:
        c.hit(half=True)
        c.condition(Condition.SLOWED, until=When.SAVE_ENDS)


@power(
    "m5922a4",
    level=11,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=14),
)
def m5922a4(c: Cast) -> None:
    """No damage line: the borrowed swing is the hit.

    The m5922 picks the mark, which is what "a creature of its choice" says,
    and the pool is whatever the victim can actually reach -- an attack
    granted against somebody across the room is not a swing. The refusal is
    the victim's, so it is asked of the victim.
    """
    if not c.strike():
        return
    victim = c.target
    if victim is None:
        return
    beside = sorted(
        w
        for w in creatures(c.world)
        if w != victim and alive(c.world, w) and distance_between(c.world, victim, w) <= 1
    )
    prey = c.choose(beside, f"{c.ref}: who the puppet swings at") if beside else None
    if prey is None or not c.may("make the attack rather than take 15", who=victim):
        c.flat(15, dtype=DamageType.PSYCHIC, on=victim)
        return
    c.grant_attack(victim, on=prey)


_M5922_BLED = "it is first bloodied"


@power(
    "m5922a5",
    level=11,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.ZONE],
    attack=Attack(vs=REF, printed=14),
    damage=Damage("2d10", 18, kind=LIMITED),
    trigger=_M5922_BLED,
    on=Trigger(Bloodied, by_me, _M5922_BLED),
)
def m5922a5(c: Cast) -> None:
    """The Effect line is printed beside the attack rather than under a hit,
    so the zone is laid on the first pass whether or not anybody was in it."""
    if c.first:
        c.zone(c.area(), label=c.ref, until=When.ENCOUNTER, difficult=c.ref)
    if c.target is None:
        return
    if c.strike():
        c.hit()
        c.condition(Condition.SLOWED, until=When.SAVE_ENDS)


# ==========================================================================
# m6181
# ==========================================================================


@power(
    "m6181a0",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6181a0(c: Cast) -> None:
    """Taken at the start of a turn and held to the start of the next one,
    which is the target's clock rather than the caster's."""
    me = c.me
    ring = c.aura(2, until=When.ENCOUNTER)

    def mire(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == me or ev.actor not in c.enemies():
            return
        if ev.actor in c.world.zones.occupants(ring):
            c.slowed(on=ev.actor, until=When.SOTNT)

    c.watch(TurnStart, mire, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m6181a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d10", 8),
)
def m6181a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6181a2",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=14),
)
def m6181a2(c: Cast) -> None:
    """No damage line: the burn and the daze are the whole of a hit, and "save
    ends both" makes them one effect."""
    if not c.strike():
        return
    if c.target is not None:
        c.world.effects.apply(
            c.target,
            c.me,
            When.SAVE_ENDS,
            label=c.ref,
            conditions=(Condition.DAZED,),
            ongoing=(15, DamageType.PSYCHIC),
        )


@power(
    "m6181a3",
    level=11,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=CloseBurst(2),
    target=Target(side="enemy", count=1, everyone=True, label="dazed"),
    keywords=[Keyword.CHARM],
    dropped=("Target.condition",),
)
def m6181a3(c: Cast) -> None:
    """No attack roll: the slide is the whole of it. `Target` cannot filter on
    what a creature is suffering -- `Target.condition` is the gap -- so the
    burst is narrowed here."""
    for who in sorted(c.within(2)):
        if who != c.me and c.is_(Condition.DAZED, on=who):
            c.slide(3, on=who)


@power(
    "m6181a4",
    level=11,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Melee(3),
    target=UpTo(2),
    attack=Attack(vs=FORT, printed=14),
)
def m6181a4(c: Cast) -> None:
    """No damage line: the slide is the whole of a hit, and the free swing is
    only bought by dragging somebody into reach -- asked after the slide,
    which is the printed order."""
    victim = c.target
    if victim is None or not c.strike(on=victim):
        return
    c.slide(3, on=victim)
    if c.adjacent(victim):
        c.use_power("m6181a1", on=victim, spend=False)


# ==========================================================================
# m6418
# ==========================================================================


_M6418_DOUSED = "m6418a0 suppressed"


@power(
    "m6418a0",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.silvered()",),
)
def m6418a0(c: Cast) -> None:
    """Regeneration, written out: the engine holds no such thing, and "has at
    least 1 hit point" is `hp > 0` rather than `alive`.

    The suppression has a door and nothing to knock on it: a weapon's metal
    is not a property any item carries, so no blow can be recognised as the
    silvered one the card names.
    """
    _regenerates(c, 10, _M6418_DOUSED)


@power(
    "m6418a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d10", 8),
)
def m6418a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6418a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=UpTo(2),
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d10", 4),
)
def m6418a2(c: Cast) -> None:
    """"If it targets only one creature it can attack that creature twice" is
    read off how many targets this use actually got, which is `c.targets`."""
    victim = c.target
    if victim is None:
        return
    for _ in range(2 if len(c.targets) == 1 else 1):
        if not alive(c.world, victim):
            break
        if c.strike(on=victim):
            c.hit(on=victim)
            c.prone(on=victim)


@power(
    "m6418a3",
    level=11,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FORCE],
    attack=Attack(vs=REF, printed=14),
    damage=Damage("4d10", 4, dtype=DamageType.FORCE, kind=LIMITED, half_on_miss=True),
)
def m6418a3(c: Cast) -> None:
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)


@power(
    "m6418a4",
    level=11,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
    out_of_combat=True,
)
def m6418a4(c: Cast) -> None:
    """Wearing somebody else's face changes nothing a fight reads: the shape
    is Medium either way, so no size, speed or defence moves, and the check
    that sees through it is not rolled on a board."""
    c.note(f"{c.ref}: it looks like some other Medium creature until it drops")


# ==========================================================================
# m965
# ==========================================================================


@power(
    "m965a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d6", 5, dtype=DamageType.NECROTIC),
)
def m965a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means."""
    if c.strike():
        c.hit()
        c.blinded(until=When.SAVE_ENDS)


@power(
    "m965a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("1d6", 5, dtype=DamageType.NECROTIC),
)
def m965a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.blinded(until=When.SAVE_ENDS)


@power(
    "m965a2",
    level=11,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC, Keyword.ZONE],
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("2d8", 3, dtype=DamageType.NECROTIC, kind=LIMITED),
    dropped=("c.conceal_in()",),
)
def m965a2(c: Cast) -> None:
    """A zone that is sustained and swings again each time it is sustained,
    which is `c.on_sustain` -- without it the payout half of the printed line
    goes nowhere.

    The repeat is written out rather than routed through `c.use_power` on this
    same row: re-entering the body would lay a second zone and a second
    `on_sustain` every time, and the printed line repeats *the attack*.

    A zone's own effect is on the `Zone`, not among the caster's -- its label
    there is `zone <label>` -- so it is read off the zone the call returned.

    The concealment the zone grants is the dropped clause: `c.cover_in` grants
    cover and nothing bounds a concealment grant to a zone's squares the way
    `c.grants_in` and `c.resist_in` bound theirs.
    """
    if c.first:
        area = c.area()
        zone = c.zone(area, label=c.ref, until=When.SUSTAIN, sustain=MINOR)
        standing = c.world.get(zone, Zone) if zone else None

        def again() -> None:
            for who in sorted(c.in_squares(area, side="enemy")):
                if alive(c.world, who) and c.strike(on=who):
                    c.hit(on=who)
                    c.push(3, on=who)

        if standing is not None:
            c.on_sustain(standing.effect, again)
    if c.target is None or not c.strike():
        return
    c.hit()
    c.push(3)


@power(
    "m965a3",
    level=11,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC, Keyword.TELEPORTATION],
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("3d6", 10, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m965a3(c: Cast) -> None:
    """"To a destination of its choice" is the m965 picking, which is what
    `c.teleport` with no `to` hands the decider -- the chooser is the caster
    and not the creature being moved."""
    if c.strike():
        c.hit()
        victim = c.target
        if victim is not None:
            c.teleport(3, who=victim)


@power(
    "m965a4",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m965a4(c: Cast) -> None:
    """"Did this attack have combat advantage" is read off the damage
    context, which carries `advantage`; asking the board again is too late
    because a one-shot grant has already been spent by then."""
    def with_an_opening(ctx: dict[str, Any]) -> bool:
        p = get(str(ctx.get("power") or ""))
        kind = p.reach_of(int(ctx.get("branch") or 0)).kind if p else ""
        return bool(ctx.get("advantage")) and kind in ("melee", "ranged")

    c.bonus(
        "damage", 0, on=c.me, until=When.ENCOUNTER, dice="1d6", when=with_an_opening
    )


@power(
    "m965a5",
    level=11,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m965a5(c: Cast) -> None:
    """Phasing first, then the walk: the step is the thing phasing is for."""
    c.phasing(until=When.EONT, on=c.me)
    c.move(4)
