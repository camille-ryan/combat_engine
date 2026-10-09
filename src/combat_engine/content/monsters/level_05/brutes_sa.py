"""Monster abilities, level 5, brutes.

Fifty stat blocks, a hundred and nine rows. `brutes.py` holds the earlier sweep
of this level and is not touched here; the split is by *when* the work was done.
Twelve of the fifty print no abilities at all and so have nothing to decorate.

Conventions, all inherited from the level-1 to level-4 sweeps:

* numbers load from `game.db` -- the attack line is written exactly as printed
  and the damage line goes in the header as data, so an MM1 block can be
  rescaled to MM3 maths later;
* a **trait** costs no action, has no target, and arms what holds it, whatever
  action the compendium's column claims for it;
* a card that prints no range at all is melee 1; "Reach 2" is `Melee(2)`;
* a printed band of "5/10" takes the short number;
* a close burst whose card names no target set takes **enemies**, except where
  it says "creatures in the burst" outright;
* `Damage(..., kind=LIMITED)` for a recharge or encounter attack, `kind=MINION`
  for a minion's fixed damage;
* **`half_on_miss=True` is card data and nothing in the engine reads it**, so a
  Miss line is also written as `else: c.hit(half=True)`. A row that declares the
  flag and nothing else silently drops its Miss clause.

Five blocks here are **mounts**. "While mounted by a friendly rider of 5th level
or higher" is `_ridden_by_fifth_level`, which reads
`relations.targets(RIDDEN_BY, mount)` -- `sources` is the other direction and is
empty for a mount every time. It is written as a `requires=` *and* asked again in
the body, because `turns.arm_traits_of` never calls `usable` and so a trait's
header gate is read by nothing.

Twenty-two helpers are imported rather than written again. The sixteen written
here are the shapes this batch is the first to need: a swim-speed gate, two
damage riders read off the target's state, an aura that penalises whoever is
standing in it, a trample whose attack line survived, a mount's grant to its
rider, a burn whose backlash ends on the same saving throw, and six predicates.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_01.artillery_sa import _recharge_when_bloodied
from combat_engine.content.monsters.level_01.brutes_sa import (
    _crit_line,
    _felled_by_a_crit,
)
from combat_engine.content.monsters.level_01.skirmishers import _ref_of
from combat_engine.content.monsters.level_02.artillery_sa import _saves_off_prone
from combat_engine.content.monsters.level_02.lurkers_sa import _triggering_enemy
from combat_engine.content.monsters.level_02.skirmishers_sa import _ends_turn_in_aura
from combat_engine.content.monsters.level_02.soldiers_sa import (
    _aquatic_edge,
    _crit_drops_it,
    _square_of,
)
from combat_engine.content.monsters.level_03.artillery_sa import _death_throe
from combat_engine.content.monsters.level_03.brutes import _squeezes_freely
from combat_engine.content.monsters.level_03.brutes_sa import (
    _both_hit,
    _press,
    _recharge_and_fire,
)
from combat_engine.content.monsters.level_03.lurkers_sa import _repeat
from combat_engine.content.monsters.level_03.soldiers_sa import (
    _crowding,
    _edge_when_mobbed,
    _secondary,
)
from combat_engine.content.monsters.level_04.misc_sa import _ridden_by_fifth_level
from combat_engine.content.monsters.level_05.artillery_sa import _shot_me_from_afar
from combat_engine.engine import (
    AC,
    ANY,
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
    Keyword,
    Melee,
    Movement,
    Ranged,
    Size,
    Target,
    Usage,
    When,
    World,
    power,
    spread,
)
from combat_engine.engine.events import (
    Bloodied,
    DamageApplied,
    DamageRolled,
    Dropped,
    Hit,
    InitiativeRolled,
    PowerUsed,
    SurgeSpent,
    TurnStart,
)
from combat_engine.engine.monster_math import LIMITED, MINION
from combat_engine.engine.query import distance_between, team
from combat_engine.engine.triggers import Trigger, about_me, by_me, targets_me

# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------


def _cannot_swim(c: Cast, who: int) -> bool:
    """"A creature without a swim speed", which is the printed narrowing and
    not "a nonaquatic creature".

    `Movement.modes` is the right question here for once: the card asks what the
    creature *can* do rather than what it is doing, and a landlubber in the
    water has no swim mode at all.
    """
    mv = c.world.get(who, Movement)
    return mv is None or not mv.modes.get("swim")


def _in_water_against_a_walker(c: Cast) -> Any:
    """"While in water, a +2 bonus to attack rolls against creatures without a
    swim speed."

    `c.terrain` is asked inside the gate rather than once when the trait is
    armed, because it is False in an ordinary fight and True in the one the line
    is for -- and a trait is armed at the top of every fight.
    """

    def gate(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        return c.terrain("aquatic") and victim is not None and _cannot_swim(c, victim)

    return gate


def _against_the_state(c: Cast, condition: Condition) -> Any:
    """"An extra 2d6 damage to prone creatures" -- the target's state read off
    the blow being dealt rather than armed and disarmed by a pair of watches,
    because the creature stands back up and a rider laid once would never come
    off."""

    def gate(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        return victim is not None and c.is_(condition, on=victim)

    return gate


def _against_the_wounded(c: Cast) -> Any:
    """"+2 to attack rolls and +4 to damage rolls against bloodied
    creatures.""" ""

    def gate(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        return victim is not None and c.bloodied(on=victim)

    return gate


def _aura_penalty(c: Cast, radius: int, what: str, value: int) -> None:
    """An aura for the board to draw, and the penalty whoever stands in it takes.

    The modifier is laid on the creatures and gated on the distance rather than
    kept as a membership list: the aura travels with its owner and a stored list
    is stale the moment either of them moves. Untyped, because a stat block
    prints a bare "-1 penalty" and `kind=` is only ever the word the card
    prints.
    """
    me = c.me
    c.aura(radius, label=f"{c.ref} aura", until=When.ENCOUNTER, on=me)
    for foe in c.enemies():
        c.penalty(
            what,
            value,
            on=foe,
            until=When.ENCOUNTER,
            when=lambda _ctx, f=foe: distance_between(c.world, me, f) <= radius,
        )


def _trample(c: Cast) -> None:
    """"It can move up to its speed and enter enemies' spaces; when it enters an
    enemy's space it makes a trample attack."

    `c.overrun` is the walk through occupied squares and it reports who was
    crossed, which is the only way the attack half can know its victims --
    `c.move` refuses an occupied square and says nothing about the path. The
    attack is this row's own header, aimed by hand with `on=`.
    """
    for caught in c.overrun():
        if c.strike(on=caught):
            c.hit(on=caught)
            c.prone(on=caught)


def _mount_grants(c: Cast, what: str, value: int, *, dice: str = "") -> None:
    """A mount's standing grant to whoever is up: "the rider gains ...".

    Asked again in the body because a trait's `requires=` is read by nothing,
    and laid on the rider rather than the mount -- `c.bonus` follows
    `c.target`, which a trait has none of.
    """
    rider = c.rider()
    if rider is None or not _ridden_by_fifth_level(c.world, c.me):
        return
    c.bonus(
        what,
        value,
        on=rider,
        until=When.ENCOUNTER,
        dice=dice,
        when=lambda ctx: bool(ctx.get("charge")),
    )


def _burn_and_backlash(c: Cast, amount: int, dtype: DamageType, victim: int) -> None:
    """"Ongoing 5 psychic damage, and whenever it uses a daily or an encounter
    power it takes 5 psychic damage (save ends **both**)."

    One saving throw has to end both halves, and only one of them is an effect:
    the burn is the hold and the backlash is a watch, so the watch asks whether
    the hold is still standing instead of carrying a clock of its own. A watch
    hung on `When.SAVE_ENDS` would be a second save-ends effect and would hand
    the victim a second throw against one printed sentence.
    """
    from combat_engine.engine import get

    hold = c.ongoing(amount, dtype, on=victim)
    if hold is None:
        return

    def spent(ev: PowerUsed) -> None:
        if ev.actor != victim or hold not in c.world.effects.of(victim):
            return
        row = get(ev.power or "")
        if row is not None and row.usage in (Usage.DAILY, Usage.ENCOUNTER):
            c.flat(amount, dtype=dtype, on=victim)

    c.watch(
        PowerUsed, spent, until=When.ENCOUNTER, on=victim, label=f"{c.ref} backlash"
    )


def _kin_within(c: Cast, ref: str, radius: int) -> int | None:
    """One off the same stat block, standing within reach of the caster."""
    return next(
        (
            a
            for a in c.allies()
            if _ref_of(c, a) == ref and distance_between(c.world, c.me, a) <= radius
        ),
        None,
    )


def _hurt_with_kin_near(ref: str, radius: int) -> Any:
    """"When it is hit by an attack while a <kin> ally is within N squares."

    Declared on `DamageRolled` rather than `Hit`: the row halves the blow, and
    by the time `Hit` has been announced there is still a number to change but
    `c.halve` reads `amount`, which only `DamageRolled` carries.
    """

    from combat_engine.engine.components import Ident
    from combat_engine.engine.query import allies as _allies

    def check(world: World, me: int, ev: Any) -> bool:
        if getattr(ev, "target", None) != me:
            return False
        for mate in _allies(world, me):
            ident = world.get(mate, Ident)
            if (
                ident is not None
                and ident.ref == ref
                and distance_between(world, me, mate) <= radius
            ):
                return True
        return False

    return check


def _ally_struck_within_six(world: World, me: int, ev: Any) -> bool:
    """"An enemy hits the ally it shields with a melee or a ranged attack while
    that ally is within 6 squares of it."

    The reach kinds are read off the row that struck rather than guessed, and the
    two sides are checked separately: the creature hit has to be on this one and
    whoever swung has to be on the other.
    """
    from combat_engine.engine import get

    victim = getattr(ev, "target", None)
    attacker = getattr(ev, "attacker", None)
    if victim is None or attacker is None or victim == me:
        return False
    if team(world, victim) is not team(world, me):
        return False
    if team(world, attacker) is team(world, me):
        return False
    if distance_between(world, me, victim) > 6:
        return False
    row = get(getattr(ev, "power", "") or "")
    return row is not None and row.reach.kind in ("melee", "ranged")


def _psychic_hurt_me(world: World, me: int, ev: Any) -> bool:
    """"When an enemy deals psychic damage to it." `DamageApplied` is where the
    type of a blow is finally known -- the roll may be resisted away."""
    if getattr(ev, "target", None) != me:
        return False
    source = getattr(ev, "source", None)
    if source is None or team(world, source) is team(world, me):
        return False
    return getattr(ev, "dtype", None) is DamageType.PSYCHIC


def _my_rider_surged(world: World, me: int, ev: SurgeSpent) -> bool:
    """"When a friendly rider of 5th level or higher spends a healing surge."""
    if not _ridden_by_fifth_level(world, me):
        return False
    from combat_engine.engine import Relation

    return ev.actor in world.relations.targets(Relation.RIDDEN_BY, me)


def _i_charged(world: World, me: int, ev: Any) -> bool:
    """"When it charges an enemy." Read off the attack the charge rolled, which
    is the one event that carries the flag and names the victim."""
    return getattr(ev, "attacker", None) == me and bool(getattr(ev, "charge", False))


def _holds_a_large_or_smaller(world: World, eid: int) -> bool:
    """The printed Requirement, asked with only `(world, eid)` to work from.

    **`Size.order`, not the enum itself.** `Size` is a `StrEnum`, so a bare
    `<=` compares the words: "huge" sorts below "large" and a creature too big
    to throw would have qualified. `dsl` enforces `Target(max_size=)` through
    `.order` for the same reason.
    """
    from combat_engine.engine import Position, Relation

    cap = Size.LARGE.order
    for held in world.relations.targets(Relation.GRABBED_BY, eid):
        pos = world.get(held, Position)
        if (pos.size if pos else Size.MEDIUM).order <= cap:
            return True
    return False


# ==========================================================================
# m1028
# ==========================================================================


@power(
    "m1028a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d6", 6),
)
def m1028a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1028a1",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    requires=_ridden_by_fifth_level,
    requires_text="while mounted by a friendly rider of 5th level or higher",
)
def m1028a1(c: Cast) -> None:
    """The header's gate is written because it is what the card shows and what
    makes `audit.py` say UNUSED rather than SILENT -- and asked again here
    because `turns.arm_traits_of` never calls `usable`, so a trait armed with
    nobody up would otherwise hand a resistance to nothing."""
    rider = c.rider()
    if rider is None or not _ridden_by_fifth_level(c.world, c.me):
        return
    c.resist(10, DamageType.NECROTIC, on=rider, until=When.ENCOUNTER)


# ==========================================================================
# m1068
# ==========================================================================


@power(
    "m1068a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d8", 4),
)
def m1068a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1068a1",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    requires=_ridden_by_fifth_level,
    requires_text="while mounted by a friendly rider of 5th level or higher",
)
def m1068a1(c: Cast) -> None:
    """Two grants, both to the rider. The extra die is rolled afresh each time
    the modifier is read rather than added as a flat number, which is what
    `dice=` is for; the aquatic half is the same sentence the mount prints about
    itself on its own trait."""
    rider = c.rider()
    if rider is None or not _ridden_by_fifth_level(c.world, c.me):
        return
    _mount_grants(c, "damage", 0, dice="1d10")
    c.bonus(
        "attack", 2, on=rider, until=When.ENCOUNTER, when=_in_water_against_a_walker(c)
    )


@power(
    "m1068a2",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1068a2(c: Cast) -> None:
    c.bonus(
        "attack", 2, on=c.me, until=When.ENCOUNTER, when=_in_water_against_a_walker(c)
    )


# ==========================================================================
# m115747
# ==========================================================================


@power(
    "m115747a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("3d8", 4),
)
def m115747a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m115747a1",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("3d8", 6, kind=LIMITED),
)
def m115747a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5)


# ==========================================================================
# m115924
# ==========================================================================


@power(
    "m115924a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("", 8, kind=MINION),
)
def m115924a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m115924a1",
    level=5,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="it is reduced to 0 hit points, but not by a critical hit",
    on=Trigger(Dropped, about_me, "it drops"),
)
def m115924a1(c: Cast) -> None:
    """"But not by a critical hit" is asked in the body, not in the predicate:
    `Dropped` carries who struck the blow and not how, so the swing is read off
    the log -- the last `Hit` on this creature is the one that felled it.

    `c.reanimate` rather than a heal: the minion is dead by the time this runs,
    and healing a corpse does nothing. One hit point is the printed number."""
    if _felled_by_a_crit(c):
        return
    if c.roll("1d20") >= 15:
        c.reanimate(on=c.me, hp=1)


# ==========================================================================
# m115925
# ==========================================================================


@power(
    "m115925a0",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m115925a0(c: Cast) -> None:
    """"At the start of the m115925's turn", so the watch reads its own turn
    and not the victim's -- the two differ by most of a round."""
    me = c.me

    def crush(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me:
            return
        for held in c.grabbing():
            c.damage("1d8", 5, on=held)

    c.watch(TurnStart, crush, until=When.ENCOUNTER, on=me, label=f"{c.ref} crush")


@power(
    "m115925a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d8", 7),
)
def m115925a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m115925a2",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m115925a2(c: Cast) -> None:
    """"Uses claw twice against the same target", so `ONE_CREATURE` and two
    uses of the named row rather than `UpTo(2)` -- the rider only ever pays out
    when both swings went to one creature. The printed escape DC has nowhere to
    live; the grab itself does."""
    _recharge_when_bloodied(c)
    victim = c.target
    if victim is None:
        return
    landed = 0
    for _ in range(2):
        c.use_power("m115925a1", on=victim)
        if c.landed:
            landed += 1
    if landed:
        c.prone(on=victim)
        if len(c.grabbing()) < 2:
            c.grab(on=victim, dc=15)


# ==========================================================================
# m115932
# ==========================================================================


@power(
    "m115932a0",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m115932a0(c: Cast) -> None:
    _aquatic_edge(c)


@power(
    "m115932a1",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m115932a1(c: Cast) -> None:
    gate = _against_the_wounded(c)
    c.bonus("attack", 2, on=c.me, until=When.ENCOUNTER, when=gate)
    c.bonus("damage", 4, on=c.me, until=When.ENCOUNTER, when=gate)


@power(
    "m115932a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d8", 7),
)
def m115932a2(c: Cast) -> None:
    if c.strike():
        c.hit()


# ==========================================================================
# m1499
# ==========================================================================


@power(
    "m1499a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d10", 3),
)
def m1499a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1499a1",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
)
def m1499a1(c: Cast) -> None:
    """The row's own attack line did not survive extraction -- "+6 vs ;" with no
    defence -- but nothing is lost by it: the printed content is "it makes a
    <m1499a0> attack; on a hit the target is also pushed 1 square and knocked
    prone", so the named row rolls and this one hangs the riders on it."""
    victim = c.target
    if victim is None:
        return
    c.use_power("m1499a0", on=victim)
    if c.landed:
        c.push(1, on=victim)
        c.prone(on=victim)


# ==========================================================================
# m1681
# ==========================================================================


@power(
    "m1681a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d6", 4),
)
def m1681a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m1681a1",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1681a1(c: Cast) -> None:
    c.bonus(
        "damage",
        0,
        dice="2d6",
        on=c.me,
        until=When.ENCOUNTER,
        when=_against_the_state(c, Condition.PRONE),
    )


# ==========================================================================
# m2231
# ==========================================================================


@power(
    "m2231a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d8", 4),
)
def m2231a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2231a1",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=6),
)
def m2231a1(c: Cast) -> None:
    """No damage line at all -- the whole of the hit is the blind and the burn,
    and they are one effect so that one saving throw ends both. Laid separately
    the victim gets two throws and shakes off half of what the card calls one
    thing."""
    if c.strike():
        c.condition(
            Condition.BLINDED,
            until=When.SAVE_ENDS,
            ongoing=(5, DamageType.NECROTIC),
        )


# ==========================================================================
# m2333
# ==========================================================================


@power(
    "m2333a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d6", 3),
)
def m2333a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2333a1",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2333a1(c: Cast) -> None:
    """One card printing both halves of what two other blocks here print as two
    separate traits."""
    c.resist_forced(1, on=c.me)
    _saves_off_prone(c)


# ==========================================================================
# m3216
# ==========================================================================


@power(
    "m3216a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=8),
    damage=Damage("1d8", 3),
)
def m3216a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.NECROTIC)


@power(
    "m3216a1",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=8),
    damage=Damage("1d8", 3, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m3216a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.EONT)


@power(
    "m3216a2",
    level=5,
    usage=AT_WILL,
    action=REACTION,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=8),
    damage=Damage("1d8", 3, dtype=DamageType.NECROTIC),
    trigger="it is hit by an attack",
    on=Trigger(Hit, targets_me, "an attack lands on it"),
)
def m3216a2(c: Cast) -> None:
    """The release is once per use and not once per creature caught in the
    burst, so it is guarded on `c.first`. `c.summon` puts the thing on the
    board **and** in the initiative order; `loader.spawn` alone would leave it
    standing there with no turn of its own."""
    if c.strike():
        c.hit()
    if c.first:
        c.summon("m4744")


# ==========================================================================
# m3218
# ==========================================================================


@power(
    "m3218a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 3),
)
def m3218a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.NECROTIC)


@power(
    "m3218a1",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 3, kind=LIMITED),
)
def m3218a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.NECROTIC)
        c.slide(2)
        c.prone()


@power(
    "m3218a2",
    level=5,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Melee(1),
    target=Target(
        side="enemy", count=1,
        label="a prone creature",
        conditions=frozenset({Condition.PRONE}),
    ),
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 3, dtype=DamageType.NECROTIC),
)
def m3218a2(c: Cast) -> None:
    """"Targets a prone creature" is `Target.conditions`, so the chooser is
    only ever handed a prone creature and the row is not offered when there is
    none in reach."""
    if c.strike():
        c.hit()


# ==========================================================================
# m3232
# ==========================================================================


@power(
    "m3232a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d8", 9),
)
def m3232a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3232a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
    attack=Attack(vs=ANY, printed=6),
    damage=Damage("1d8", 6),
)
def m3232a1(c: Cast) -> None:
    """`NO_TARGET` for `m3781a1`'s reason -- the victims are whoever the walk
    crossed, and are not known until it has happened.

    **The defence was never missing; this row was marked as though it were.**
    It carried `dropped=("compendium.attack_defence",)`, which says the card
    does not state one. The card states `+6 vs Any`: the attack lands if it
    would land on any defence, and `Defense.ANY` is the member that says so
    (`query.defence` resolves it to the lowest of the four, level and
    modifiers included). A source marker on an engine gap. #360."""
    _trample(c)


@power(
    "m3232a2",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    requires=_ridden_by_fifth_level,
    requires_text="while mounted by a friendly rider of 5th level or higher",
)
def m3232a2(c: Cast) -> None:
    _mount_grants(c, "damage", 6)


@power(
    "m3232a3",
    level=5,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="a friendly rider of 5th level or higher spends a healing surge",
    on=Trigger(SurgeSpent, _my_rider_surged, "its rider spends a healing surge"),
)
def m3232a3(c: Cast) -> None:
    """"Temporary hit points equal to the rider's healing surge value", so the
    number is read off the rider and not off this creature -- `c.surge_value`
    defaults to the caster, which here is the wrong side of the saddle."""
    rider = c.rider()
    if rider is not None:
        c.temp_hp(c.surge_value(of=rider), on=c.me)


# ==========================================================================
# m3527
# ==========================================================================


@power(
    "m3527a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d4", 3),
)
def m3527a0(c: Cast) -> None:
    """"Crit 2d4 + 11" **replaces** the damage rather than adding to it, and it
    is a roll -- so it is paid flat, past the engine's own rule that a critical
    maxes the declared dice."""
    if c.strike():
        _crit_line(c, "2d4", 11)
        c.ongoing(5)


@power(
    "m3527a1",
    level=5,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d4", 3),
    trigger="it is first bloodied, and again when it drops to 0 hit points",
    on=(
        Trigger(Bloodied, about_me, "it is first bloodied"),
        Trigger(Dropped, about_me, "it drops"),
    ),
)
def m3527a1(c: Cast) -> None:
    """Two printed triggers, so two declared ones -- declaring half of this
    looks finished and fires on one of the two moments the card names. The
    weapon Requirement is not asked: a monster carries no `Gear` for a row to
    read, and the blow is the one the block's own basic attack prints."""
    if c.strike():
        _crit_line(c, "2d4", 11)
        c.ongoing(5)


@power(
    "m3527a2",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
)
def m3527a2(c: Cast) -> None:
    me = c.me

    def feasted(ev: Hit) -> None:
        if ev.attacker == me and ev.critical:
            c.heal(5, on=me)

    c.watch(Hit, feasted, until=When.ENCOUNTER, on=me, label=f"{c.ref} feast")


# ==========================================================================
# m3639
# ==========================================================================


@power(
    "m3639a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d6", 3),
)
def m3639a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3639a1",
    level=5,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it drops to 0 hit points",
    on=Trigger(Dropped, about_me, "it drops"),
    dropped=("etl.monster.ability_text()",),
)
def m3639a1(c: Cast) -> None:
    """Half of this card did not survive extraction: the attack line lost its
    defence and the damage expression was overwritten by a monster ref, so
    there is no number left to pay and none is invented. The sentence that came
    through whole is the swing on the way down, and `_death_throe` is the one
    route that carries the exemption from the "can it act?" gate -- `c.basic`
    drops the triggering event and the swing is refused every time."""
    _death_throe(c)


@power(
    "m3639a2",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.kill()",),
)
def m3639a2(c: Cast) -> None:
    """"Any critical hit reduces it to 0 hit points instantly" is paid as damage
    equal to whatever it has left, so the fall announces itself the way every
    other fall does. That is right about the common case and wrong about a
    creature with temporary hit points or resist-all, which is the half the
    marker names."""
    _crit_drops_it(c)


# ==========================================================================
# m3773
# ==========================================================================


@power(
    "m3773a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("", 6, dtype=DamageType.FIRE, kind=MINION),
)
def m3773a0(c: Cast) -> None:
    if c.strike():
        c.hit()


# ==========================================================================
# m3781
# ==========================================================================


@power(
    "m3781a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 6),
)
def m3781a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3781a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
    attack=Attack(vs=REF, printed=6),
    damage=Damage("1d6", 7),
)
def m3781a1(c: Cast) -> None:
    """`NO_TARGET`, because the victims are whoever the walk crossed and are not
    known until it has happened -- a target list chosen before the body would be
    measured from where the creature started."""
    _trample(c)


@power(
    "m3781a2",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    requires=_ridden_by_fifth_level,
    requires_text="while mounted by a friendly rider of 5th level or higher",
)
def m3781a2(c: Cast) -> None:
    _mount_grants(c, "damage", 5)


# ==========================================================================
# m4002
# ==========================================================================


@power(
    "m4002a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.POISON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d4", 3),
)
def m4002a0(c: Cast) -> None:
    """The burn is one blow of two types, which `c.ongoing(dtypes=)` says
    exactly -- it is resisted only as far as the victim resists both."""
    if c.strike():
        c.hit()
        c.ongoing(5, dtypes=(DamageType.POISON, DamageType.NECROTIC))


@power(
    "m4002a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d8", 3),
)
def m4002a1(c: Cast) -> None:
    """"1d8+3 **plus** 5 poison damage" is two blows rolled once each, so the
    second is its own typed payment and needs no marker."""
    if c.strike():
        _crit_line(c, "1d8", 11)
        c.flat(5, dtype=DamageType.POISON)


@power(
    "m4002a2",
    level=5,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC, Keyword.POISON],
    attack=Attack(vs=REF, printed=8),
    damage=Damage("2d6", 3, dtype=[DamageType.NECROTIC, DamageType.POISON]),
    trigger="it is first bloodied, and again when it drops to 0 hit points",
    on=(
        Trigger(Bloodied, about_me, "it is first bloodied"),
        Trigger(Dropped, about_me, "it drops"),
    ),
)
def m4002a2(c: Cast) -> None:
    if c.strike():
        c.hit()


# ==========================================================================
# m4180
# ==========================================================================


@power(
    "m4180a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d8", 4, dtype=DamageType.LIGHTNING),
)
def m4180a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4180a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d6", 6),
)
def m4180a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4180a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m4180a2(c: Cast) -> None:
    """`ONE_CREATURE` rather than `UpTo(2)`: the whole content of the card is a
    rider that only exists when both swings went to one creature, so letting the
    chooser spread them would offer a line that can never pay out."""
    if _both_hit(c, "m4180a0", "m4180a1"):
        c.prone()


@power(
    "m4180a3",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=6),
    damage=Damage("2d6", 6, dtype=DamageType.LIGHTNING, kind=LIMITED),
)
def m4180a3(c: Cast) -> None:
    """The secondary attack is once per use and fires only if the blast landed
    on somebody, so the tally is kept across the per-target calls by reading the
    log of this use rather than a module-level flag. Its own line prints a total
    and no ref, so `_secondary` takes it back to a bonus the way the header's
    `Attack(printed=)` does."""
    _recharge_when_bloodied(c)
    if c.strike():
        c.hit()
    if not c.last:
        return
    caught = [who for who in c.targets if c.world.bus.log and _was_hit(c, who)]
    if not caught:
        return
    spare = next(
        (
            foe
            for foe in c.enemies()
            if foe not in c.targets and distance_between(c.world, c.me, foe) <= 5
        ),
        None,
    )
    if spare is not None and _secondary(c, 6, REF, spare):
        c.damage("1d6", 6, dtype=DamageType.LIGHTNING, on=spare)
        c.push(1, on=spare)


def _was_hit(c: Cast, who: int) -> bool:
    """Did this use's blast land on that creature? Read off the log, because the
    body is called once per target and has nowhere of its own to keep a tally
    that a second use would not inherit."""
    for ev in reversed(c.world.bus.log):
        if isinstance(ev, PowerUsed) and ev.power == c.ref:
            return False
        if isinstance(ev, Hit) and ev.power == c.ref and ev.target == who:
            return True
    return False


# ==========================================================================
# m4189
# ==========================================================================


@power(
    "m4189a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d8", 4),
)
def m4189a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4189a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 4),
)
def m4189a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4189a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
)
def m4189a2(c: Cast) -> None:
    """"A claw attack against **each** enemy adjacent to it" is the smaller of
    this block's two melee rows once per neighbour, so the burst picks the
    victims and the named row rolls each swing."""
    c.use_power("m4189a1", on=c.target)


@power(
    "m4189a3",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(4),
    target=EACH_ENEMY,
    keywords=[Keyword.COLD],
    attack=Attack(vs=REF, printed=6),
    damage=Damage("1d6", 5, dtype=DamageType.COLD, kind=LIMITED),
)
def m4189a3(c: Cast) -> None:
    """"Vulnerable 5 to **all** damage" is `c.vulnerable` with no type at
    all -- a type would narrow a line that names none."""
    _recharge_when_bloodied(c)
    if c.strike():
        c.hit()
        c.vulnerable(5, until=When.SAVE_ENDS)


# ==========================================================================
# m4416
# ==========================================================================


@power(
    "m4416a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d10", 4),
)
def m4416a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)


@power(
    "m4416a1",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=6),
    damage=Damage("2d8", 4, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m4416a1(c: Cast) -> None:
    _recharge_when_bloodied(c)
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.NECROTIC)


@power(
    "m4416a2",
    level=5,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is hit by an attack while an ally of its own sort is within 5 squares",
    on=Trigger(
        DamageRolled,
        _hurt_with_kin_near("m4416", 5),
        "it is hurt with one of its own nearby",
    ),
)
def m4416a2(c: Cast) -> None:
    """Declared on `DamageRolled` rather than `Hit`: the number has to still be
    changeable, and `Hit` does not carry one. `c.halve` reports how much it took
    off, which is exactly the amount the ally is handed -- "the same amount" is
    the half that was spared and not half of what is left."""
    mate = _kin_within(c, "m4416", 5)
    spared = c.halve()
    if mate is not None and spared > 0:
        c.flat(spared, on=mate)


# ==========================================================================
# m5086
# ==========================================================================


@power(
    "m5086a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 12),
)
def m5086a0(c: Cast) -> None:
    if c.strike():
        c.hit()


# ==========================================================================
# m5319
# ==========================================================================


@power(
    "m5319a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d6", 3),
)
def m5319a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5319a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 4),
)
def m5319a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5319a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m5319a2(c: Cast) -> None:
    """"Whether or not it moves" -- the walk is offered and the two swings
    happen either way, so the move is spent first and nothing hangs on whether
    it got anywhere."""
    c.move(c.speed_of())
    if _both_hit(c, "m5319a0", "m5319a1"):
        c.prone()


@power(
    "m5319a3",
    level=5,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    requires=_ridden_by_fifth_level,
    requires_text="while mounted by a friendly rider of 5th level or higher",
    trigger="it charges an enemy while a friendly rider of 5th level or higher is up",
    on=Trigger(Hit, _i_charged, "it charges"),
)
def m5319a3(c: Cast) -> None:
    """"Against the target of the charge", which is the creature the triggering
    attack named and not whoever this row chose -- an immediate action's own
    target list is routinely empty."""
    rider = c.rider()
    victim = getattr(c.trigger, "target", None)
    if rider is not None and victim is not None:
        c.basic(who=rider, on=victim)


# ==========================================================================
# m5322
# ==========================================================================


@power(
    "m5322a0",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5322a0(c: Cast) -> None:
    _edge_when_mobbed(c, 1)


@power(
    "m5322a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("3d8", 5),
)
def m5322a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5322a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("3d6", 3),
)
def m5322a2(c: Cast) -> None:
    """The bigger die against a prone target replaces the header's line rather
    than adding to it, so it is paid instead of `c.hit` and the header keeps the
    smaller expression as the data a rescale reads."""
    if not c.strike():
        return
    victim = c.target
    if victim is not None and c.is_(Condition.PRONE, on=victim):
        c.damage("4d6", 4)
    else:
        c.hit()
    c.ongoing(5, DamageType.POISON)


@power(
    "m5322a3",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=6),
)
def m5322a3(c: Cast) -> None:
    """"One enemy in the burst", so one target and not the whole ring. The pull
    is the entire hit -- the card rolls no damage."""
    if c.strike():
        c.pull(3)


@power(
    "m5322a4",
    level=5,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    charges=True,
    no_provoke=True,
    trigger="an enemy deals psychic damage to it",
    on=Trigger(DamageApplied, _psychic_hurt_me, "psychic damage reaches it"),
)
def m5322a4(c: Cast) -> None:
    """`charges=True` because the printed Effect *is* a charge: without it the
    engine measures a sword's reach before the run and refuses the row whenever
    the victim is further off, which is every situation a charge is for."""
    foe = _triggering_enemy(c)
    if foe is not None:
        c.charge_at(foe)


# ==========================================================================
# m5383
# ==========================================================================


@power(
    "m5383a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d8", 7),
)
def m5383a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5383a1",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d12", 7, kind=LIMITED),
)
def m5383a1(c: Cast) -> None:
    """The bloodied rider is read off the board rather than off the blow: it is
    a fact about the creature and not about the attack, and the extra die is
    rolled rather than declared so the critical rule does not max it."""
    if not c.strike():
        return
    c.hit()
    c.prone()
    victim = c.target
    if victim is not None and c.bloodied(on=victim):
        c.flat(c.roll("1d12"))
        c.dazed(until=When.SAVE_ENDS)


@power(
    "m5383a2",
    level=5,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5383a2(c: Cast) -> None:
    """The flight is lent for the length of the move: the block has no fly mode
    of its own and `c.move(at="fly")` measures the mode."""
    c.mode("fly", 5, until=When.EOT, on=c.me)
    c.move(5, at="fly")


@power(
    "m5383a3",
    level=5,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=FORT, printed=5),
    damage=Damage("2d6", 3, dtype=DamageType.PSYCHIC, kind=LIMITED),
    trigger="it drops to 0 hit points",
    on=Trigger(Dropped, about_me, "it drops"),
)
def m5383a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        victim = c.target
        if victim is not None:
            _burn_and_backlash(c, 5, DamageType.PSYCHIC, victim)


# ==========================================================================
# m5410
# ==========================================================================


@power(
    "m5410a0",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5410a0(c: Cast) -> None:
    _aquatic_edge(c)


@power(
    "m5410a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("", 5, kind=MINION),
)
def m5410a1(c: Cast) -> None:
    """It steps back *before* it hauls, which is the printed order and the whole
    point: the pull is "to a square adjacent to it", so the square it wants the
    victim in is the one it has just left."""
    if not c.strike():
        return
    c.hit()
    was = c.here
    c.shift(1)
    victim = c.target
    if victim is not None:
        c.pull(1, on=victim, to=was)


# ==========================================================================
# m5662
# ==========================================================================


@power(
    "m5662a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d10", 5),
)
def m5662a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5662a1",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(2),
    target=NO_TARGET,
    charges=True,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d10", 5, kind=LIMITED, half_on_miss=True),
)
def m5662a1(c: Cast) -> None:
    """`NO_TARGET`, because the burst is measured from where the charge *ends*.
    A declared `EACH_ENEMY` is chosen before the body runs, so every enemy the
    charge was aimed at would be out of the ring and the row would spend itself
    on nobody. `c.strike(on=)` still rolls the header's own attack and damage,
    so none of the card's data moves into the body."""
    nearest = min(c.enemies(), key=c.distance, default=None)
    if nearest is not None:
        c.run_at(nearest)
    for foe in _press(c, 2):
        if c.strike(on=foe):
            c.hit(on=foe)
            c.push(1, on=foe)
            c.prone(on=foe)
        else:
            c.hit(on=foe, half=True)


@power(
    "m5662a2",
    level=5,
    usage=AT_WILL,
    action=FREE,
    once_per_round=True,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it bloodies an enemy",
    on=Trigger(Bloodied, by_me, "it bloodies an enemy"),
)
def m5662a2(c: Cast) -> None:
    """`Bloodied` carries `source`, so `by_me` is the whole of "it bloodies an
    enemy" and the line does not have to be routed off `DamageApplied` and
    re-derive the half-hit-point threshold by hand."""
    victim = getattr(c.trigger, "actor", None)
    if victim is not None:
        c.use_power("m5662a0", on=victim)


@power(
    "m5662a3",
    level=5,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it drops to 0 hit points",
    on=Trigger(Dropped, about_me, "it drops"),
)
def m5662a3(c: Cast) -> None:
    _recharge_and_fire(c, "m5662a1")


# ==========================================================================
# m5663
# ==========================================================================


@power(
    "m5663a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d10", 5),
)
def m5663a0(c: Cast) -> None:
    """Two riders on one swing: a bigger die against a prone target, which
    replaces the header's line, and a prone of its own on a critical. The
    critical branch cannot also take the bigger die -- the target was not prone
    when the blow was declared."""
    if not c.strike():
        return
    victim = c.target
    if victim is not None and c.is_(Condition.PRONE, on=victim):
        c.damage("3d10", 5)
    else:
        c.hit()
    if c.crit:
        c.prone()


@power(
    "m5663a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m5663a1(c: Cast) -> None:
    _repeat(c, "m5663a0", 2)


@power(
    "m5663a2",
    level=5,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="an enemy hits it with a ranged or an area attack",
    on=Trigger(Hit, _shot_me_from_afar(), "it is shot from a distance"),
)
def m5663a2(c: Cast) -> None:
    """The swing is a melee one and the shooter may be well out of reach, which
    is the printed line: `c.use_power` refuses it rather than inventing a
    range."""
    foe = _triggering_enemy(c)
    if foe is not None:
        c.use_power("m5663a0", on=foe)


# ==========================================================================
# m5668
# ==========================================================================


@power(
    "m5668a0",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FEAR],
)
def m5668a0(c: Cast) -> None:
    _aura_penalty(c, 1, "attack", 1)


@power(
    "m5668a1",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5668a1(c: Cast) -> None:
    """No level gate on this one -- the card says "its rider" and nothing about
    how experienced. The move is offered when the rider's place in the order is
    decided, which `InitiativeRolled` is announced for."""
    me = c.me

    def rolled(ev: InitiativeRolled) -> None:
        if ev.actor == c.rider():
            c.move(max(1, c.speed_of() // 2))

    c.watch(
        InitiativeRolled, rolled, until=When.ENCOUNTER, on=me, label=f"{c.ref} off"
    )


@power(
    "m5668a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d10", 5),
)
def m5668a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5)


# ==========================================================================
# m5790
# ==========================================================================


@power(
    "m5790a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("", 6, kind=MINION),
)
def m5790a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5790a1",
    level=5,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="an enemy hits the ally it shields while that ally is within 6 squares",
    on=Trigger(Hit, _ally_struck_within_six, "the ally it shields is hit"),
    dropped=("spec.monster_ref()",),
)
def m5790a1(c: Cast) -> None:
    """The card names **which** ally by name, and a name has no ref in the spec,
    so the row takes the one it is set to guard and falls back to whichever ally
    was struck -- the marker names the missing half. Everything else is exact:
    an interrupt, so the swap happens before the blow lands, and `c.redirect`
    moves the live result rather than rolling again."""
    ally = getattr(c.trigger, "target", None)
    if ally is None:
        return
    was = _square_of(c, ally)
    c.shift(1, who=ally)
    if was is not None and c.shift(c.speed_of(), to=was):
        c.redirect(to=c.me)


# ==========================================================================
# m5855
# ==========================================================================


@power(
    "m5855a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d8", 7),
)
def m5855a0(c: Cast) -> None:
    """"Or 3d8 + 7 **while it is bloodied**" is a fact about the attacker, so it
    is asked of `c.me` -- `c.bloodied` follows the target and would read the
    wrong creature."""
    if not c.strike():
        return
    if c.bloodied(on=c.me):
        c.damage("3d8", 7)
    else:
        c.hit()


@power(
    "m5855a1",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=FORT, printed=8),
    damage=Damage("3d12", 5, kind=LIMITED),
)
def m5855a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()
        if c.crit:
            c.ongoing(5)


@power(
    "m5855a2",
    level=5,
    usage=ENCOUNTER,
    action=REACTION,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d12", 3, kind=LIMITED, half_on_miss=True),
    trigger="it first becomes bloodied",
    on=Trigger(Bloodied, about_me, "it is first bloodied"),
)
def m5855a2(c: Cast) -> None:
    """The Effect line is separate from the Hit line, so the shove is paid
    whether the blow landed or not."""
    if c.strike():
        c.hit()
        c.prone()
    else:
        c.hit(half=True)
    c.push(1)


# ==========================================================================
# m5868
# ==========================================================================


@power(
    "m5868a0",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5868a0(c: Cast) -> None:
    _ends_turn_in_aura(c, 1, 3)


@power(
    "m5868a1",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5868a1(c: Cast) -> None:
    c.immovable(on=c.me, until=When.ENCOUNTER)


@power(
    "m5868a2",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5868a2(c: Cast) -> None:
    """Two sentences, two mechanisms: sharing a square is a standing property of
    the swarm, and squeezing freely is the waiver of everything
    `Condition.SQUEEZING` is."""
    c.shares_space(on=c.me, difficult=True)
    _squeezes_freely(c)


@power(
    "m5868a3",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d6", 8, dtype=DamageType.POISON),
)
def m5868a3(c: Cast) -> None:
    if c.strike():
        c.hit()


# ==========================================================================
# m5924
# ==========================================================================


@power(
    "m5924a0",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5924a0(c: Cast) -> None:
    c.ignores_difficult(on=c.me)


@power(
    "m5924a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("", 8, kind=MINION),
)
def m5924a1(c: Cast) -> None:
    if not c.strike():
        return
    victim = c.target
    if victim is not None and c.bloodied(on=victim):
        c.flat(10)
    else:
        c.hit()


@power(
    "m5924a2",
    level=5,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(1),
    target=EACH_OTHER,
    attack=Attack(vs=REF, printed=8),
    trigger="it drops to 0 hit points",
    on=Trigger(Dropped, about_me, "it drops"),
)
def m5924a2(c: Cast) -> None:
    """No damage at all -- the blind is the whole of the hit. "Until the end of
    **its** next turn" is the victim's turn, which is `EOTNT`."""
    if c.strike():
        c.blinded(until=When.EOTNT)


# ==========================================================================
# m5937
# ==========================================================================


@power(
    "m5937a0",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.aura(difficult=)",),
)
def m5937a0(c: Cast) -> None:
    """Two sentences about one aura. The grant plays: it is laid on each enemy
    and gated on the distance, because the aura travels with the creature and a
    stored membership list is stale the moment either of them moves. Difficult
    terrain inside an aura is the half with nowhere to live -- `c.zone` takes
    `difficult=` and an aura does not, and a zone would stay where it was made."""
    me = c.me
    c.aura(2, label=f"{c.ref} aura", until=When.ENCOUNTER, on=me)
    for foe in c.enemies():
        c.grants_advantage(
            on=foe,
            to="team",
            until=When.ENCOUNTER,
            when=lambda _ctx, f=foe: distance_between(c.world, me, f) <= 2,
        )


@power(
    "m5937a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d10", 5),
)
def m5937a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m5937a2",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    attack=Attack(vs=REF, printed=8),
    damage=Damage("2d6", 5, kind=LIMITED, half_on_miss=True),
)
def m5937a2(c: Cast) -> None:
    _recharge_when_bloodied(c)
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)
    else:
        c.hit(half=True)


# ==========================================================================
# m5951
# ==========================================================================


@power(
    "m5951a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(3),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d8", 7),
)
def m5951a0(c: Cast) -> None:
    """"If it has no creature grabbed" is asked of the board rather than
    assumed: the row is used again and again and the second grab is the one the
    card refuses."""
    if c.strike():
        c.hit()
        if not c.grabbing():
            c.grab(dc=15)


@power(
    "m5951a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(3),
    target=ONE_CREATURE,
)
def m5951a1(c: Cast) -> None:
    _repeat(c, "m5951a0", 2)


@power(
    "m5951a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=Target(side="enemy", count=1, max_size=Size.LARGE),
    attack=Attack(vs=REF, printed=8),
    damage=Damage("2d8", 7, half_on_miss=True),
    requires=_holds_a_large_or_smaller,
    requires_text="it must have a Large or smaller creature grabbed",
)
def m5951a2(c: Cast) -> None:
    """The creature in its fist is the ammunition, so both take the blow and the
    grab ends either way -- that is an Effect line and not a Hit one. "Falls
    prone in the target's space" is a real distance to travel, so it is slid
    exactly that far rather than being given an invented number; on a miss it
    lands beside instead, which is the square it is already nearest."""
    victim = c.target
    held = next(
        (w for w in c.grabbing() if c.size_of(on=w).order <= Size.LARGE.order), None
    )
    if victim is None or held is None:
        return
    was = _square_of(c, victim)
    gap = distance_between(c.world, held, victim)
    if c.strike():
        c.hit()
        c.hit(on=held)
        c.push(1, on=victim)
        c.prone(on=victim)
        if was is not None:
            c.slide(gap, on=held, to=was)
    else:
        c.hit(half=True)
        c.hit(on=held, half=True)
        c.slide(max(0, gap - 1), on=held)
    c.prone(on=held)
    c.escape(on=held, auto=True)


@power(
    "m5951a3",
    level=5,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(1),
    target=EACH_OTHER,
    attack=Attack(vs=REF, printed=8),
    damage=Damage("3d10", 8, kind=LIMITED),
    trigger="it drops to 0 hit points",
    on=Trigger(Dropped, about_me, "it drops"),
)
def m5951a3(c: Cast) -> None:
    """"It is destroyed" needs nothing said: it is already at 0 hit points and a
    construct does not get back up. The rubble is a zone, laid once for the
    whole use and including the square the thing fell in."""
    if c.strike():
        c.hit()
    if c.first:
        c.zone(spread({c.here}, 1), difficult=True, until=When.ENCOUNTER, label=c.ref)


# ==========================================================================
# m6549
# ==========================================================================


@power(
    "m6549a0",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6549a0(c: Cast) -> None:
    c.resist_forced(1, on=c.me)


@power(
    "m6549a1",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6549a1(c: Cast) -> None:
    _saves_off_prone(c)


@power(
    "m6549a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("", 7, kind=MINION),
)
def m6549a2(c: Cast) -> None:
    """Who is beside the victim is counted at the swing rather than held as a
    modifier: it changes every time anybody moves."""
    if not c.strike():
        return
    if _crowding(c, c.target) >= 1:
        c.flat(10)
    else:
        c.hit()


# ==========================================================================
# m883
# ==========================================================================


@power(
    "m883a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("", 4, kind=MINION),
)
def m883a0(c: Cast) -> None:
    if c.strike():
        c.hit()


# ==========================================================================
# m917
# ==========================================================================


@power(
    "m917a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d12", 4),
)
def m917a0(c: Cast) -> None:
    if c.strike():
        _crit_line(c, "1d12", 16)


@power(
    "m917a1",
    level=5,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is first bloodied",
    on=Trigger(Bloodied, about_me, "it is first bloodied"),
)
def m917a1(c: Cast) -> None:
    """The card's own attack line did not survive extraction -- "+6 vs ;" with
    no defence -- and nothing is lost by it, because the sentence that came
    through is "it makes a melee basic attack with a +5 bonus to the attack roll
    and deals an extra 1d6 damage on a hit". Both riders are one-shot and laid
    before the swing: a bonus laid afterwards is read by the *next* attack."""
    foe = next(iter(_press(c, 1)), None)
    if foe is None:
        return
    c.bonus("attack", 5, on=c.me, until=When.EOT, once=True)
    c.bonus("damage", 0, dice="1d6", on=c.me, until=When.EOT, once=True)
    c.basic(on=foe)


@power(
    "m917a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d6", 3),
)
def m917a2(c: Cast) -> None:
    if c.strike():
        c.hit()
