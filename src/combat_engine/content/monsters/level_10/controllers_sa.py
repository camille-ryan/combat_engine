"""Monster abilities, level 10, controllers -- the second sweep.

224 rows across 49 stat blocks, all of `scripts/spec.py --monsters 10 --role
controller`. `controllers.py` holds the earlier sweep of this level and is
untouched here. Seven of the 49 blocks print no abilities left to decorate
-- `m221`, `m336`, `m3042`, `m4774`, `m4783`, `m4785`, `m4877` -- they are
the earlier sweep's, in full.

Conventions, inherited from `level_09/controllers_sa.py` and this level's own
`controllers.py`:

* numbers load from `game.db`; the attack line is written exactly as
  printed and the damage line goes in the header as data;
* a **trait** is a row that costs no action, has no target, and arms the
  watches that hold it, whatever action the compendium's column claims;
* a card with no printed range at all is read `Melee(1)`;
* a close burst, blast or area burst whose card names no target set takes
  **enemies**; one that says "creatures in the burst" outright takes
  `EACH_CREATURE`;
* "Hit: X. Effect: Y" with the Effect on its own line is unconditional --
  it happens on a miss too;
* a blow of two printed types rolled once keeps the first in the header
  and the rest as keywords (`dropped=("Damage(dtypes=)",)`);
* "+N vs <defence>, no roll at all" -- a card with no attack line and no
  defence to roll against lays its conditions outright
  (`dropped=("etl.monster.attack_line()",)`), the established defect;
* "save ends both" is one `Effects.apply` call carrying every clause under
  one saving throw, never a condition plus a separately-timed penalty.

Three gaps confirmed absent from `scripts/vocab.py`, each named once and
reused by every row that needs it:

* **No primitive removes a creature from play and returns it later.**
  `m6109a3` is `todo=("c.remove_from_play()",)` for exactly the shape
  `level_09/controllers_sa.py` named for `m6092a2`.
* **No zone variant of `c.conceal`.** `m1089a3`, `m2507a3` and `m964a2` are
  `dropped=("c.conceal_in()",)`, the gap `level_09/controllers_sa.py` first
  named.
* **Nothing tracks how far a creature moved on its own turn.**
  `c.distance_moved()` would answer "moves more than half its speed" and
  "doesn't move at least 2 squares"; `m1780a1` and `m2507a3` both wait on
  it. Whether a creature moved *at all* is answerable (`Moved` fires or
  does not), and `m2546a4` uses exactly that instead of a distance.

Two printed names leaked through the extraction and are kept out of this
file entirely -- not quoted, not pointed at by a comment beyond this
notice: `m1039a3`'s burst heals creatures sharing m1039's own kind rather
than the plural word the card prints for them, and `m964a8`'s card names
its monster by its own proper name mid-sentence where every other row
reads "it". Both are flagged in the report; neither word appears below.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_02.controllers_sa import _swing_reach
from combat_engine.content.monsters.level_03.lurkers_sa import _restricted_to
from combat_engine.content.monsters.level_03.soldiers_sa import _secondary
from combat_engine.content.monsters.level_07.soldiers import _recharge_on
from combat_engine.content.monsters.level_10.controllers import (
    EVERY_DEFENCE,
    _my_implement_hit,
)
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_ALLY,
    EACH_CREATURE,
    EACH_ENEMY,
    EACH_OTHER,
    FORT,
    FREE,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_CREATURE,
    OPPORTUNITY,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    WILL,
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
    DamageType,
    Effect,
    Keyword,
    Melee,
    Mod,
    Ranged,
    Relation,
    SkillCheck,
    Team,
    UpTo,
    Usage,
    Wall,
    When,
    World,
    power,
    spread,
    would_hit_me,
)
from combat_engine.engine.components import Health, Ident, Position, Powers
from combat_engine.engine.events import (
    AdjacencyGained,
    AttackDeclared,
    DamageApplied,
    Dropped,
    Hit,
    Miss,
    Moved,
    OpportunityWindow,
    TurnEnd,
    TurnStart,
    ZoneEntered,
    ZoneExited,
)
from combat_engine.engine.grid import between
from combat_engine.engine.monster_math import LIMITED, MINION
from combat_engine.engine.query import adjacent, allies, distance_between, enemies
from combat_engine.engine.triggers import (
    Trigger,
    about_me,
    both,
    by_melee,
    enemy_within,
    targets_me,
)
from combat_engine.engine.zones import Zone

# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------


def _sunlit(c: Cast, amount: int) -> None:
    """ "Whenever it starts its turn in direct sunlight, it takes N radiant
    damage." `c.terrain` is the whole fight's, not any one square's, which
    is the established reading `level_10/artillery.py`'s m812a1 settled on.
    """
    me = c.me

    def dawn(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me or not c.terrain("sunlight"):
            return
        c.flat(amount, dtype=DamageType.RADIANT, on=me)

    c.watch(TurnStart, dawn, until=When.ENCOUNTER, on=me, label=f"{c.ref} sun")


def _hit_while_bloodied(world: World, me: int, ev: Any) -> bool:
    if getattr(ev, "target", None) != me:
        return False
    health = world.get(me, Health)
    return health is not None and health.bloodied


def _aura_penalty(c: Cast, radius: int, what: str, amount: int) -> None:
    """A standing enemy-only penalty bound to an aura's membership.

    Tied to `ZoneEntered`/`ZoneExited` rather than re-asked at the roll:
    the penalty has to be live the instant the enemy is inside, and gone
    the instant it steps out, which is what the card's "in the aura" means.
    """
    me = c.me
    aura = c.aura(radius, label=c.ref, on=me, until=When.ENCOUNTER)
    holds: dict[int, Effect] = {}

    def enter(ev: ZoneEntered) -> None:
        if ev.zone != aura or ev.actor in holds or ev.actor not in c.enemies():
            return
        hold = c.penalty(what, amount, on=ev.actor, until=When.ENCOUNTER)
        if hold is not None:
            holds[ev.actor] = hold

    def leave(ev: ZoneExited) -> None:
        hold = holds.pop(ev.actor, None)
        if hold is not None:
            c.world.effects.end(hold, "left the aura")

    c.watch(ZoneEntered, enter, until=When.ENCOUNTER, on=me, label=f"{c.ref} in")
    c.watch(ZoneExited, leave, until=When.ENCOUNTER, on=me, label=f"{c.ref} out")


# ==========================================================================
# m1039
# ==========================================================================


@power(
    "m1039a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.MELEE],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d6", 0),
)
def m1039a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.NECROTIC)


@power(
    "m1039a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR, Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=14),
    damage=Damage("2d6", 5, dtype=DamageType.PSYCHIC),
)
def m1039a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.penalty(WILL, 3, until=When.EONT)


@power(
    "m1039a2",
    level=10,
    usage=Usage.ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(2, within=15),
    target=EACH_ENEMY,
    keywords=[Keyword.ZONE, Keyword.AREA],
)
def m1039a2(c: Cast) -> None:
    """No "+X vs Y" survives for this one -- an Effect with nothing to
    roll, same as the daze/zone riders elsewhere in this sweep."""
    c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS)
    if not c.first:
        return
    area = frozenset(c.area())
    c.zone(area, until=When.ENCOUNTER, difficult=True, label=c.ref)

    def tick(ev: TurnEnd) -> None:
        if ev.actor in c.in_squares(area, side="any"):
            c.slowed(until=When.SAVE_ENDS, on=ev.actor)

    c.watch(TurnEnd, tick, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} zone")


@power(
    "m1039a3",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MOVE,
    reach=CloseBurst(2),
    target=EACH_ALLY,
    keywords=[Keyword.HEALING, Keyword.CLOSE],
)
def m1039a3(c: Cast) -> None:
    """The card names m1039's own kind by a word kept out of this file --
    read as its allies, in the burst."""
    ally = c.target
    if ally is not None:
        c.heal(10, on=ally)


@power(
    "m1039a4",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("etl.monster.trigger_text()",),
)
def m1039a4(c: Cast) -> None:
    """Names a power category with no referent in the spec and a creature
    ("the head") that resolves to nothing on this block -- the same
    extraction defect `level_09/controllers_sa.py` named for `m3617a3`."""


# ==========================================================================
# m1062
# ==========================================================================


@power(
    "m1062a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d12", 6),
)
def m1062a0(c: Cast) -> None:
    from combat_engine.content.monsters.level_03.brutes import NO_BIGGER_THAN_MEDIUM

    victim = c.target
    if c.strike():
        c.hit()
        if victim is not None and c.size_of(on=victim) in NO_BIGGER_THAN_MEDIUM:
            c.push(1)


@power(
    "m1062a1",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.CHARM, Keyword.SLEEP, Keyword.CLOSE],
    attack=Attack(vs=WILL, printed=13),
)
def m1062a1(c: Cast) -> None:
    _recharge_on(c, Bloodied, lambda ev: ev.actor == c.me)
    if c.strike():
        c.condition(
            Condition.DAZED,
            until=When.SAVE_ENDS,
            escalate=lambda eff: c.condition(
                Condition.UNCONSCIOUS, until=When.ENCOUNTER, on=eff.owner
            ),
        )


@power(
    "m1062a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING, Keyword.PSYCHIC, Keyword.MELEE],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d10", 5, dtype=DamageType.PSYCHIC),
)
def m1062a2(c: Cast) -> None:
    def unconscious_only(f: int) -> bool:
        return c.is_(Condition.UNCONSCIOUS, on=f)

    victim = _restricted_to(c, 1, unconscious_only)
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)
    c.heal(10, on=c.me)


@power(
    "m1062a3",
    level=10,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
    out_of_combat=True,
)
def m1062a3(c: Cast) -> None:
    c.note(f"{c.ref}: disguises itself as an elderly humanoid")


@power(
    "m1062a4",
    level=10,
    usage=Usage.ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POLYMORPH],
    dropped=("c.phasing(through=)",),
)
def m1062a4(c: Cast) -> None:
    """Insubstantial and hovering are both exact. Passing through a
    "porous obstacle" is narrower than `c.phasing`, which passes through
    anything solid -- nothing scopes it down to just doors and windows."""
    c.insubstantial(on=c.me, until=When.SUSTAIN)
    c.hover(8, on=c.me, until=When.SUSTAIN, sustain=STANDARD)


# ==========================================================================
# m1088
# ==========================================================================


@power(
    "m1088a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID, Keyword.MELEE],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d6", 6, dtype=DamageType.ACID),
)
def m1088a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.ACID)


@power(
    "m1088a1",
    level=10,
    usage=AT_WILL,
    once_per_round=True,
    action=FREE,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC, Keyword.CLOSE],
    attack=Attack(vs=WILL, printed=12),
)
def m1088a1(c: Cast) -> None:
    """Card names m221 mid-sentence where it means itself -- the same
    shape `level_08/controllers_sa.py` reports for `m1108a2`/`m2781a1`."""
    victim = c.target
    if victim is not None and c.is_(Condition.DEAFENED, on=victim):
        return
    if c.strike():
        c.dazed(until=When.EONT)


@power(
    "m1088a2",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.ACID, Keyword.CLOSE],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d6", 6, dtype=DamageType.ACID, kind=LIMITED),
)
def m1088a2(c: Cast) -> None:
    victim = c.target
    if victim is None or not c.is_(Condition.DAZED, on=victim):
        return
    if c.strike(on=victim):
        c.hit(on=victim)
        c.ongoing(5, DamageType.ACID, on=victim)


# ==========================================================================
# m1089
# ==========================================================================


@power(
    "m1089a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=17),
)
def m1089a0(c: Cast) -> None:
    if c.strike():
        c.grab()


@power(
    "m1089a1",
    level=10,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d6", 6),
)
def m1089a1(c: Cast) -> None:
    victim = _restricted_to(c, 1, lambda f: f in c.grabbing(of=c.me))
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)


@power(
    "m1089a2",
    level=10,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=FORT, printed=15),
)
def m1089a2(c: Cast) -> None:
    victim = _restricted_to(c, 1, lambda f: f in c.grabbing(of=c.me))
    if victim is None:
        return
    if c.strike(on=victim):
        c.pull(2, on=victim)


@power(
    "m1089a3",
    level=10,
    usage=Usage.ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.POISON, Keyword.CLOSE],
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("2d12", 4, dtype=DamageType.POISON, kind=LIMITED),
    dropped=("c.conceal_in()",),
)
def m1089a3(c: Cast) -> None:
    """The burn is exact. The aftereffect cloud's concealment has no
    zone-bound primitive -- see the module docstring."""
    if c.strike():
        c.hit()


@power(
    "m1089a4",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1089a4(c: Cast) -> None:
    c.threatens(2, until=When.ENCOUNTER)


# ==========================================================================
# m115911
# ==========================================================================


@power(
    "m115911a0",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.RADIANT],
)
def m115911a0(c: Cast) -> None:
    _sunlit(c, 5)


@power(
    "m115911a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("4d6", 4),
)
def m115911a1(c: Cast) -> None:
    if c.strike():
        c.hit()
    c.slide(3)


@power(
    "m115911a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING, Keyword.MELEE],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("3d10", 10),
)
def m115911a2(c: Cast) -> None:
    def helpless_enough(f: int) -> bool:
        return (
            c.is_(Condition.DAZED, on=f)
            or c.is_(Condition.DOMINATED, on=f)
            or c.is_(Condition.STUNNED, on=f)
            or c.is_(Condition.UNCONSCIOUS, on=f)
        )

    victim = _restricted_to(c, 1, helpless_enough)
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)
    c.heal(15, on=c.me)


@power(
    "m115911a3",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=13),
    damage=Damage("3d6", 4, dtype=DamageType.PSYCHIC),
)
def m115911a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.EONT)
    c.pull(3)


@power(
    "m115911a4",
    level=10,
    usage=Usage.ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ILLUSION],
    trigger="it takes damage while bloodied",
    on=Trigger(DamageApplied, _hit_while_bloodied, "it takes damage while bloodied"),
)
def m115911a4(c: Cast) -> None:
    me = c.me
    hold = c.invisible(on=me, until=When.ENCOUNTER)
    if hold is None:
        return

    def ends_on_attack(ev: AttackDeclared) -> None:
        if not hold.ended and ev.attacker == me:
            c.world.effects.end(hold, "it attacked")

    hold.subs.append(c.world.bus.on(AttackDeclared, ends_on_attack, owner=me))


# ==========================================================================
# m1163
# ==========================================================================


@power(
    "m1163a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d4", 6),
)
def m1163a0(c: Cast) -> None:
    for _ in range(2):
        if c.strike():
            c.hit()


@power(
    "m1163a1",
    level=10,
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(6),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d4", 6),
)
def m1163a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1163a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=14),
    damage=Damage("1d4", 6),
)
def m1163a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.grab()


@power(
    "m1163a3",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=14),
    damage=Damage("2d8", 5, half_on_miss=True),
)
def m1163a3(c: Cast) -> None:
    victim = _restricted_to(c, 1, lambda f: f in c.grabbing(of=c.me))
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)
    else:
        c.hit(on=victim, half=True)


@power(
    "m1163a4",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=14),
    damage=Damage("2d4", 6, kind=LIMITED),
)
def m1163a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(3)
        c.prone()
        c.stunned(until=When.EONT)


@power(
    "m1163a5",
    level=10,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d4", 6),
    trigger="an enemy misses it with a melee attack",
    on=Trigger(Miss, both(targets_me, by_melee), "an enemy misses it with a melee attack"),
)
def m1163a5(c: Cast) -> None:
    foe = getattr(c.trigger, "attacker", None)
    if foe is None or not c.strike(on=foe):
        return
    c.hit(on=foe)


@power(
    "m1163a6",
    level=10,
    usage=Usage.ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1163a6(c: Cast) -> None:
    c.bonus(
        "damage",
        0,
        on=c.me,
        until=When.ENCOUNTER,
        once=True,
        dice="1d6",
        when=lambda ctx: bool(ctx.get("advantage")),
    )


@power(
    "m1163a7",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m1163a7(c: Cast) -> None:
    c.note(f"{c.ref}: draws a weapon as a free action")


# ==========================================================================
# m1522
# ==========================================================================


@power(
    "m1522a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d4", 6),
)
def m1522a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1522a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(2, side="ally"),
    keywords=[Keyword.TELEPORTATION, Keyword.RANGED],
    damage=Damage("2d6", 5),
    dropped=("etl.monster.attack_line()",),
)
def m1522a1(c: Cast) -> None:
    """No defence survived extraction for this one -- the damage is laid
    outright, the same defect `level_08/controllers_sa.py` names for
    `m2245a0`. "The m1522 and one ally" is read off the target count: when
    only one ally is in range, m1522 itself swaps with it."""
    c.hit()
    if not c.last:
        return
    pair = list(c.targets)
    if len(pair) >= 2:
        c.swap(pair[1], who=pair[0])
    elif pair:
        c.swap(pair[0], who=c.me)


@power(
    "m1522a2",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_OTHER,
    keywords=[Keyword.TELEPORTATION, Keyword.CLOSE],
    attack=Attack(vs=REF, printed=14),
)
def m1522a2(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    ally = victim in c.allies()
    if ally or c.strike(on=victim):
        c.teleport(5, who=victim)


@power(
    "m1522a3",
    level=10,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
    trigger="a creature within 6 squares of it teleports",
    on=Trigger(
        Moved,
        lambda world, me, ev: ev.kind_ == "teleport" and distance_between(world, me, ev.actor) <= 6,
        "a creature within 6 squares of it teleports",
    ),
)
def m1522a3(c: Cast) -> None:
    ev = c.trigger
    squares = between({ev.from_}, {ev.to})
    c.teleport(squares, who=c.me)


# ==========================================================================
# m1567
# ==========================================================================


@power(
    "m1567a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d8", 0),
)
def m1567a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1567a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID, Keyword.RANGED],
    attack=Attack(vs=REF, printed=14),
    damage=Damage("2d4", 6, dtype=DamageType.ACID),
)
def m1567a1(c: Cast) -> None:
    victim = c.target
    if not c.strike():
        return
    c.hit()
    if victim is None:
        return
    for foe in c.within(1, of=victim, side="any"):
        if foe != victim:
            c.flat(5, dtype=DamageType.ACID, on=foe)


@power(
    "m1567a2",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(2, within=10),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR, Keyword.NECROTIC, Keyword.AREA],
    attack=Attack(vs=FORT, printed=14),
    dropped=("c.cannot_approach()",),
)
def m1567a2(c: Cast) -> None:
    """The burn and the restraint are exact. "Can't move closer to m1567"
    has no primitive -- nothing bounds a creature's own movement by
    direction relative to a point."""
    victim = c.target
    if not c.strike():
        return
    hold = c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS)
    if hold is not None and victim is not None:
        hold.on_end.append(lambda v=victim: c.ongoing(10, DamageType.NECROTIC, on=v))


@power(
    "m1567a3",
    level=10,
    usage=Usage.ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(20),
    target=EACH_ALLY,
)
def m1567a3(c: Cast) -> None:
    ally = c.target
    if ally is not None:
        c.grant_action("shift", FREE, squares_=2, on=ally)


# ==========================================================================
# m1757
# ==========================================================================


@power(
    "m1757a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d6", 2),
)
def m1757a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1757a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d8", 2),
)
def m1757a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.EONT)


@power(
    "m1757a2",
    level=10,
    usage=Usage.ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=CloseBurst(2),
    target=NO_TARGET,
    trigger="it is hit by a melee attack",
    on=Trigger(Hit, both(targets_me, by_melee), "it is hit by a melee attack"),
    attack=Attack(vs=REF, printed=14),
    damage=Damage("1d8", 2),
)
def m1757a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.UNTYPED)


@power(
    "m1757a3",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(2, within=10),
    target=EACH_ENEMY,
    keywords=[Keyword.AREA],
    attack=Attack(vs=REF, printed=14),
    damage=Damage("1d8", 3, kind=LIMITED),
)
def m1757a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.EONT)


# ==========================================================================
# m1780
# ==========================================================================


@power(
    "m1780a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d6", 4),
)
def m1780a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(3)


@power(
    "m1780a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=13),
    damage=Damage("1d8", 5, dtype=DamageType.PSYCHIC),
    dropped=("c.distance_moved()",),
)
def m1780a1(c: Cast) -> None:
    """The hit lands in full. Nothing tracks how far a creature moved on
    its own turn, so the "takes 2d6 if it didn't move 2 squares" clause
    cannot be asked -- see the module docstring."""
    victim = c.target
    if c.strike():
        c.hit()
        if victim is not None:
            c.effect(c.ref, until=When.SAVE_ENDS, on=victim)


@power(
    "m1780a2",
    level=10,
    usage=AT_WILL,
    action=MINOR,
    reach=CloseBurst(5),
    target=UpTo(2, side="ally"),
)
def m1780a2(c: Cast) -> None:
    ally = c.target
    if ally is not None:
        c.grant_action("shift", FREE, squares_=2, on=ally)


@power(
    "m1780a3",
    level=10,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="an enemy hits it with a melee attack",
    on=Trigger(Hit, both(targets_me, by_melee), "an enemy hits it with a melee attack"),
)
def m1780a3(c: Cast) -> None:
    pool = [a for a in c.allies() if c.distance(to=a) <= 5]
    ally = min(pool, key=lambda a: c.distance(to=a)) if pool else None
    if ally is not None:
        c.grant_action("shift", FREE, squares_=2, on=ally)


# ==========================================================================
# m2012
# ==========================================================================


@power(
    "m2012a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.MELEE],
    attack=Attack(vs=REF, printed=14),
    damage=Damage("2d6", 4, dtype=DamageType.PSYCHIC),
)
def m2012a0(c: Cast) -> None:
    victim = c.target
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)
    c.world.effects.apply(
        victim,
        c.me,
        When.SAVE_ENDS,
        label=c.ref,
        conditions=[Condition.SLOWED],
        mods=[(victim, Mod(what=WILL.value, value=-2, kind="untyped", label=c.ref))],
    )


@power(
    "m2012a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.GAZE, Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=14),
    damage=Damage("2d6", 4, dtype=DamageType.PSYCHIC),
)
def m2012a1(c: Cast) -> None:
    """ "The m2012 can dominate only one creature at a time" -- any older
    hold of this row's own label ends before the new one lands, the same
    arrangement `level_09/controllers_sa.py`'s `m1157a1` settled on."""
    victim = c.target
    if not c.strike():
        return
    c.hit()
    if victim is None or not _secondary(c, 13, WILL, victim):
        return
    label = f"{c.ref} dominated"
    for eff in list(c.world.effects.live.values()):
        if eff.label == label and eff.owner != victim and not eff.ended:
            c.world.effects.end(eff, "only one creature at a time")
    hold = c.condition(Condition.DOMINATED, until=When.SAVE_ENDS, on=victim)
    if hold is not None:
        hold.label = label
        hold.on_end.append(lambda v=victim: c.prone(on=v))


@power(
    "m2012a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(10),
    target=EACH_ENEMY,
    keywords=[Keyword.CHARM, Keyword.CLOSE],
    attack=Attack(vs=WILL, printed=14),
)
def m2012a2(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    if c.is_(Condition.DEAFENED, on=victim) or c.is_(Condition.DOMINATED, on=victim):
        return
    if not c.strike(on=victim):
        return
    c.push(3, on=victim)
    c.condition(Condition.SLOWED, until=When.SAVE_ENDS, on=victim)
    if c.first:
        hold = c.effect(f"{c.ref} sustain", until=When.SUSTAIN, sustain=MINOR, on=c.me)
        if hold is not None:

            def resustain() -> None:
                for v in c.suffering(c.ref):
                    c.push(3, on=v)

            c.on_sustain(hold, resustain)


@power(
    "m2012a3",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
)
def m2012a3(c: Cast) -> None:
    c.teleport(10, who=c.me)


@power(
    "m2012a4",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.reappear(after=)",),
)
def m2012a4(c: Cast) -> None:
    """Nothing schedules a return to the board thirty days after an
    encounter ends -- a timescale this engine has no clock for."""


# ==========================================================================
# m2507
# ==========================================================================


@power(
    "m2507a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.NECROTIC, Keyword.MELEE],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d8", 4, dtype=[DamageType.FIRE, DamageType.NECROTIC]),
)
def m2507a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2507a1",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=14),
    damage=Damage("2d8", 4, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m2507a1(c: Cast) -> None:
    victim = c.target
    if not c.strike():
        return
    c.hit()
    if victim is not None:
        c.sight_range(2, on=victim, until=When.SAVE_ENDS)


@power(
    "m2507a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.NECROTIC, Keyword.RANGED],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("1d8", 5, dtype=DamageType.NECROTIC),
)
def m2507a2(c: Cast) -> None:
    victim = c.target
    result = c.strike()
    if not result:
        return
    if c.crit:
        c.flat(c.roll("2d6") + 12, dtype=DamageType.NECROTIC)
    else:
        c.hit()
    if victim is None:
        return
    pool = [a for a in c.allies() if c.can_see(to=a)]
    ally = c.choose(pool, f"{c.ref}: who gets the bonus") if pool else None
    if ally is not None:
        c.bonus("attack", 2, on=ally, kind="power", until=When.EONT, once=True)


@power(
    "m2507a3",
    level=10,
    usage=Usage.ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC],
    dropped=("c.conceal_in()", "c.distance_moved()"),
)
def m2507a3(c: Cast) -> None:
    """The aura, its damage tick and ending it when m2507 uses `m2507a6`
    are all written. Its concealment has no zone-bound primitive, and
    nothing tracks how far she moves this turn -- see the module
    docstring for both."""
    me = c.me
    zone = c.aura(2, label=c.ref, on=me, until=When.SUSTAIN, sustain=MINOR)
    zc = c.world.get(zone, Zone)
    if zc is not None:
        zc.difficult = c.ref
    for friend in {me, *c.allies()}:
        c.ignores_difficult(c.ref, on=friend, until=When.ENCOUNTER)

    def tick(ev: Any) -> None:
        if ev.actor == me or ev.actor not in c.enemies() or not c.in_my_aura(ev.actor, label=c.ref):
            return
        c.flat(5, dtype=DamageType.NECROTIC, on=ev.actor)

    def ended_by_a6(ev: Any) -> None:
        if ev.actor != me or ev.power != "m2507a6":
            return
        zc2 = c.world.get(zone, Zone)
        if zc2 is not None and zc2.effect is not None:
            c.world.effects.end(zc2.effect, "m2507 used m2507a6")

    from combat_engine.engine.events import PowerUsed
    from combat_engine.engine.events import ZoneEntered as _ZE

    c.watch(_ZE, tick, until=When.SUSTAIN, on=me, label=f"{c.ref} enter")
    c.watch(TurnStart, tick, until=When.SUSTAIN, on=me, label=f"{c.ref} start")
    c.watch(PowerUsed, ended_by_a6, until=When.SUSTAIN, on=me, label=f"{c.ref} a6")


@power(
    "m2507a4",
    level=10,
    usage=Usage.DAILY,
    action=STANDARD,
    reach=Wall(5, 10),
    target=NO_TARGET,
    keywords=[Keyword.CONJURATION, Keyword.IMPLEMENT],
)
def m2507a4(c: Cast) -> None:
    zone = c.wall(5, hp=0, difficult=True, until=When.SUSTAIN, sustain=MINOR, label=c.ref)
    zc = c.world.get(zone, Zone)
    squares = frozenset(zc.squares) if zc is not None else frozenset()

    def tick(ev: Any) -> None:
        if ev.actor in c.in_squares(squares, side="any"):
            c.flat(c.roll("3d6") + 5, on=ev.actor)
            c.ongoing(5, DamageType.UNTYPED, on=ev.actor)

    from combat_engine.engine.events import ZoneEntered as _ZE

    c.watch(_ZE, tick, until=When.SUSTAIN, on=c.me, label=f"{c.ref} enter")
    c.watch(TurnStart, tick, until=When.SUSTAIN, on=c.me, label=f"{c.ref} start")


@power(
    "m2507a5",
    level=10,
    usage=Usage.ENCOUNTER,
    uses=2,
    once_per_round=True,
    action=MINOR,
    reach=CloseBurst(5),
    target=EACH_ALLY,
    keywords=[Keyword.HEALING, Keyword.CLOSE],
)
def m2507a5(c: Cast) -> None:
    ally = c.target
    if ally is not None and c.may("spend a healing surge", who=ally):
        c.spend_surge(on=ally)
        c.heal(c.roll("2d6") + 3, on=ally)


@power(
    "m2507a6",
    level=10,
    usage=Usage.ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
)
def m2507a6(c: Cast) -> None:
    c.teleport(3, who=c.me)
    c.insubstantial(on=c.me, until=When.SONT)


@power(
    "m2507a7",
    level=10,
    usage=Usage.ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
    trigger="m2507's attack drops an enemy to 0 hit points",
    on=Trigger(
        Dropped,
        lambda world, me, ev: ev.source == me,
        "m2507's attack drops an enemy to 0 hit points",
    ),
)
def m2507a7(c: Cast) -> None:
    foe = c.trigger.actor
    pool = [a for a in [c.me, *c.allies()] if distance_between(c.world, a, foe) <= 5]
    who = c.choose(pool, f"{c.ref}: who spends the surge") if pool else None
    if who is not None and c.may("spend a healing surge", who=who):
        c.spend_surge(on=who)
        c.heal(3, on=who)


# ==========================================================================
# m2546
# ==========================================================================


@power(
    "m2546a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d10", 5),
)
def m2546a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)


@power(
    "m2546a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d8", 5),
)
def m2546a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2546a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
)
def m2546a2(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    for _ in range(2):
        c.use_power("m2546a1", on=victim)


@power(
    "m2546a3",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
)
def m2546a3(c: Cast) -> None:
    """The flight is aimed at the creature the bite is for: "at any point
    during the move" has no finer unit than move-then-bite, so the move has
    to be the half that closes."""
    victim = c.target
    if victim is not None:
        c.no_provoke(from_=victim, on=c.me, until=When.EOT)
    c.move(12, who=c.me, toward=victim)
    if victim is not None:
        c.use_power("m2546a0", on=victim)


@power(
    "m2546a4",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=Ranged(2),
    target=NO_TARGET,
    attack=Attack(vs=REF, printed=13),
    damage=Damage("1d8", 5),
)
def m2546a4(c: Cast) -> None:
    """ "If an adjacent enemy does not move on its turn" -- tracked by
    whether `Moved` fired for it at all between its own `TurnStart` and
    `TurnEnd`, not by how far."""
    me = c.me
    moved: dict[int, bool] = {}

    def start(ev: TurnStart) -> None:
        moved[ev.actor] = False

    def step(ev: Moved) -> None:
        moved[ev.actor] = True

    def end(ev: TurnEnd) -> None:
        foe = ev.actor
        if foe == me or moved.get(foe, True) or not adjacent(c.world, me, foe):
            return
        if c.strike(on=foe):
            c.hit(on=foe)
            c.prone(on=foe)

    c.watch(TurnStart, start, until=When.ENCOUNTER, on=me, label=f"{c.ref} start")
    c.watch(Moved, step, until=When.ENCOUNTER, on=me, label=f"{c.ref} step")
    c.watch(TurnEnd, end, until=When.ENCOUNTER, on=me, label=f"{c.ref} end")


@power(
    "m2546a5",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.POISON, Keyword.CLOSE],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("1d10", 4, dtype=DamageType.POISON, kind=LIMITED),
)
def m2546a5(c: Cast) -> None:
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
    "m2546a6",
    level=10,
    usage=Usage.ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POISON],
    trigger="it is first bloodied",
    on=Trigger(Bloodied, about_me, "it is first bloodied"),
)
def m2546a6(c: Cast) -> None:
    c.restore_use("m2546a5", on=c.me)
    c.use_power("m2546a5")


@power(
    "m2546a7",
    level=10,
    usage=Usage.ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR, Keyword.CLOSE],
    attack=Attack(vs=WILL, printed=13),
)
def m2546a7(c: Cast) -> None:
    victim = c.target
    hold = c.stunned(until=When.EONT) if c.strike() else None
    if hold is not None and victim is not None:
        hold.on_end.append(lambda v=victim: c.penalty("attack", 2, on=v, until=When.SAVE_ENDS))


# ==========================================================================
# m3253
# ==========================================================================


@power(
    "m3253a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d8", 4),
)
def m3253a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.penalty("attack", 2, until=When.SAVE_ENDS)


@power(
    "m3253a1",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED],
    attack=Attack(vs=WILL, printed=14),
)
def m3253a1(c: Cast) -> None:
    victim = c.target
    if not c.strike():
        return
    c.stunned(until=When.EONT)
    if victim is None:
        return
    pool = sorted(
        (a for a in c.allies() if distance_between(c.world, a, victim) <= 5),
        key=lambda a: distance_between(c.world, a, victim),
    )
    for ally in pool[:2]:
        c.temp_hp(10, on=ally)


@power(
    "m3253a2",
    level=10,
    usage=Usage.ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.CHARM, Keyword.GAZE, Keyword.IMPLEMENT],
    attack=Attack(vs=WILL, printed=14),
)
def m3253a2(c: Cast) -> None:
    if c.strike():
        c.condition(
            Condition.DAZED,
            until=When.SAVE_ENDS,
            escalate=lambda eff: c.condition(
                Condition.DAZED, Condition.IMMOBILIZED, until=When.SAVE_ENDS, on=eff.owner
            ),
        )


@power(
    "m3253a3",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(2, within=10),
    target=EACH_ENEMY,
    keywords=[Keyword.FIRE, Keyword.IMPLEMENT, Keyword.RADIANT, Keyword.AREA],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("1d6", 3, dtype=[DamageType.FIRE, DamageType.RADIANT], half_on_miss=True),
)
def m3253a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.FIRE)
    else:
        c.hit(half=True)


@power(
    "m3253a4",
    level=10,
    usage=Usage.ENCOUNTER,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.IMPLEMENT],
    trigger="it is hit by an attack with at least one effect a save can end",
    on=Trigger(Hit, targets_me, "it is hit by an attack with at least one effect a save can end"),
    todo=("c.transfer(from_attack=)",),
)
def m3253a4(c: Cast) -> None:
    """Nothing reads "the effects this attack is about to lay" at the
    moment the interrupt fires -- they do not exist yet. `c.transfer`
    moves a live one, which is a later question than this card asks."""


@power(
    "m3253a5",
    level=10,
    usage=AT_WILL,
    once_per_round=True,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3253a5(c: Cast) -> None:
    mark = next(
        (e for e in c.world.effects.of(c.me) if Condition.MARKED in e.conditions and not e.ended),
        None,
    )
    if mark is None:
        return
    pool = [a for a in c.allies() if c.distance(to=a) <= 5 and c.can_see(to=a)]
    ally = c.choose(pool, f"{c.ref}: transfer the mark to which ally") if pool else None
    if ally is not None:
        c.transfer(mark, to=ally)


# ==========================================================================
# m3319
# ==========================================================================


@power(
    "m3319a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d4", 7),
)
def m3319a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3319a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(8),
    target=UpTo(2),
    keywords=[Keyword.NECROTIC, Keyword.RANGED],
    attack=Attack(vs=FORT, printed=14),
    damage=Damage("2d6", 5, dtype=DamageType.NECROTIC),
)
def m3319a1(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.hit()
        c.grants_advantage(on=victim, to="me", until=When.SAVE_ENDS)


@power(
    "m3319a2",
    level=10,
    usage=Usage.ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(2, within=10),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC, Keyword.ZONE, Keyword.AREA],
    attack=Attack(vs=REF, printed=14),
    damage=Damage("3d8", 5, dtype=DamageType.NECROTIC),
)
def m3319a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS)
    if not c.first:
        return
    area = frozenset(c.area())
    zone = c.zone(area, until=When.SUSTAIN, sustain=MINOR, difficult=True, label=c.ref)

    def tick(ev: TurnStart) -> None:
        if ev.actor in c.in_squares(area, side="any") and c.is_(Condition.IMMOBILIZED, on=ev.actor):
            c.flat(5, dtype=DamageType.NECROTIC, on=ev.actor)

    c.watch(TurnStart, tick, until=When.SUSTAIN, on=c.me, label=f"{c.ref} zone")
    zc = c.world.get(zone, Zone)
    hold = zc.effect if zc is not None else None
    if hold is None:
        return

    def resustain() -> None:
        for occ in c.world.zones.occupants(zone):
            if occ == c.me or c.is_(Condition.IMMOBILIZED, on=occ):
                continue
            if c.strike(on=occ):
                c.hit(on=occ)
                c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS, on=occ)

    c.on_sustain(hold, resustain)


@power(
    "m3319a3",
    level=10,
    usage=AT_WILL,
    action=MINOR,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    attack=Attack(vs=FORT, printed=14),
)
def m3319a3(c: Cast) -> None:
    if c.strike():
        c.push(3)


# ==========================================================================
# m3573
# ==========================================================================


@power(
    "m3573a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d10", 5),
)
def m3573a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3573a1",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("2d10", 10),
)
def m3573a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)


@power(
    "m3573a2",
    level=10,
    usage=AT_WILL,
    once_per_round=True,
    action=MINOR,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    attack=Attack(vs=REF, printed=14),
)
def m3573a2(c: Cast) -> None:
    victim = c.target
    if victim is None or not c.strike():
        return
    beneficiaries = [c.me, *c.allies()]
    c.world.effects.apply(
        victim,
        c.me,
        When.SAVE_ENDS,
        label=c.ref,
        conditions=[Condition.IMMOBILIZED],
        relations=[(Relation.GRANTS_CA_TO, victim, b) for b in beneficiaries],
    )


@power(
    "m3573a3",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.save_against_prone()",),
)
def m3573a3(c: Cast) -> None:
    """The one-square-less half of forced movement is exact. Nothing lets
    a creature roll a save to shrug off being knocked prone outright."""
    c.resist_forced(1, on=c.me, until=When.ENCOUNTER)


@power(
    "m3573a4",
    level=10,
    usage=Usage.ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    trigger="it is first bloodied",
    on=Trigger(Bloodied, about_me, "it is first bloodied"),
)
def m3573a4(c: Cast) -> None:
    c.restore_use("m3573a1", on=c.me)
    c.use_power("m3573a1")


# ==========================================================================
# m3676
# ==========================================================================


@power(
    "m3676a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.RADIANT, Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d8", 1),
)
def m3676a0(c: Cast) -> None:
    victim = c.target
    if not c.strike():
        return
    c.hit()
    if victim is None:
        return
    splashed = [victim]
    for foe in c.within(1, of=victim, side="enemy"):
        if foe != victim:
            c.flat(5, dtype=DamageType.RADIANT, on=foe)
            splashed.append(foe)
    pool = [a for a in c.allies() if c.distance(to=a) <= 5]
    ally = c.choose(pool, f"{c.ref}: who marks") if pool else None
    if ally is not None:
        for foe in splashed:
            c.mark(on=foe, by=ally, until=When.EONT)


@power(
    "m3676a1",
    level=10,
    usage=AT_WILL,
    once_per_round=True,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_CREATURE,
    keywords=[Keyword.RADIANT, Keyword.CLOSE],
    attack=Attack(vs=WILL, printed=14),
    damage=Damage("1d8", 1, dtype=DamageType.RADIANT),
)
def m3676a1(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.hit()
        c.grants_advantage(on=victim, to="team", until=When.EONT)


@power(
    "m3676a2",
    level=10,
    usage=Usage.ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING],
)
def m3676a2(c: Cast) -> None:
    ally = c.target
    if ally is not None and c.may("spend a healing surge", who=ally):
        c.spend_surge(on=ally)
        c.grant_action("shift", FREE, squares_=1, on=ally)


@power(
    "m3676a3",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(10),
    target=UpTo(3, side="ally"),
)
def m3676a3(c: Cast) -> None:
    ally = c.target
    if ally is None:
        return
    foes = [f for f in c.enemies() if adjacent(c.world, ally, f)]
    foe = c.choose(foes, f"{c.ref}: {ally}'s target") if foes else None
    if foe is None:
        return
    c.basic(who=ally, on=foe)
    if c.landed:
        c.prone(on=foe)


@power(
    "m3676a4",
    level=10,
    usage=Usage.ENCOUNTER,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=(
        "it makes an attack roll, a saving throw, a skill check, or an ability "
        "check and dislikes the result"
    ),
    on=[
        Trigger(
            AttackRolled,
            lambda world, me, ev: ev.attacker == me,
            "it makes an attack roll it dislikes",
        ),
        Trigger(
            SkillCheck, lambda world, me, ev: ev.actor == me, "it makes a skill check it dislikes"
        ),
    ],
    dropped=("SavingThrow.total", "c.boost_check(ability=)"),
)
def m3676a4(c: Cast) -> None:
    """Attack rolls and skill checks can both take the add-after-the-fact
    bonus. Saving throws have no mutable total to add to, and ability
    checks have no event of their own at all -- see the module docstring."""
    ev = c.trigger
    bonus = c.roll("1d6")
    if isinstance(ev, AttackRolled):
        ev.result.total += bonus
    elif isinstance(ev, SkillCheck):
        c.boost_check(bonus)


@power(
    "m3676a5",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3676a5(c: Cast) -> None:
    for defence in EVERY_DEFENCE:
        c.bonus(
            defence,
            1,
            on=c.me,
            until=When.ENCOUNTER,
            when=lambda ctx: c.bloodied(on=ctx.get("attacker")),
        )


# ==========================================================================
# m3788
# ==========================================================================


@power(
    "m3788a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d6", 6),
)
def m3788a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3788a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
)
def m3788a1(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    c.as_basic("m3788a1", until=When.ENCOUNTER, on=c.me)
    hits = 0
    for _ in range(2):
        c.use_power("m3788a0", on=victim)
        if c.landed:
            hits += 1
    if hits == 2:
        c.prone(on=victim)


@power(
    "m3788a2",
    level=10,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=Melee(1),
    target=NO_TARGET,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d6", 4),
    trigger="two or more enemies flank it",
    on=Trigger(AdjacencyGained, about_me, "two or more enemies flank it"),
)
def m3788a2(c: Cast) -> None:
    from combat_engine.engine.query import flanked_by

    me = c.me
    foe = next((f for f in c.enemies() if c.adjacent(to=f) and flanked_by(c.world, me, f)), None)
    if foe is None or not c.strike(on=foe):
        return
    c.hit(on=foe)
    c.push(2, on=foe)


@power(
    "m3788a3",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, within=12),
    target=EACH_ENEMY,
    keywords=[Keyword.LIGHTNING, Keyword.THUNDER, Keyword.AREA],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("1d8", 6, dtype=[DamageType.LIGHTNING, DamageType.THUNDER]),
)
def m3788a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(1)


@power(
    "m3788a4",
    level=10,
    usage=Usage.ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(2, within=12),
    target=EACH_ENEMY,
    damage=Damage("2d8", 5, half_on_miss=True),
    attack=Attack(vs=FORT, printed=12),
    dropped=("c.conceal_in()", "c.grant_action(move_zone)"),
)
def m3788a4(c: Cast) -> None:
    """The prone, blind and half-on-miss are exact; so is the re-attack on
    entering or starting a turn in the haboob. Its concealment has no
    zone-bound primitive, and nothing offers moving the zone as a
    chooseable move action -- both named in the module docstring. The
    LOS-limiting half is flavor with no separate mechanical reading on a
    board with no walls."""
    if c.strike():
        c.hit()
        c.condition(Condition.PRONE, Condition.BLINDED, until=When.SAVE_ENDS)
    else:
        c.hit(half=True)
    if not c.first:
        return
    area = frozenset(c.area())
    c.zone(area, until=When.SUSTAIN, sustain=MOVE, label=c.ref)

    def tick(ev: Any) -> None:
        foe = ev.actor
        if foe not in c.enemies() or foe not in c.in_squares(area, side="enemy"):
            return
        if c.strike(on=foe):
            c.hit(on=foe)
            c.condition(Condition.PRONE, Condition.BLINDED, until=When.SAVE_ENDS, on=foe)
        else:
            c.hit(on=foe, half=True)

    from combat_engine.engine.events import ZoneEntered as _ZE

    c.watch(_ZE, tick, until=When.SUSTAIN, on=c.me, label=f"{c.ref} enter")
    c.watch(TurnStart, tick, until=When.SUSTAIN, on=c.me, label=f"{c.ref} start")


@power(
    "m3788a5",
    level=10,
    usage=Usage.ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
)
def m3788a5(c: Cast) -> None:
    if c.may("spend a healing surge", who=c.me):
        c.spend_surge(on=c.me)
        c.heal(106, on=c.me)
    for defence in EVERY_DEFENCE:
        c.bonus(defence, 2, on=c.me, until=When.SONT)


@power(
    "m3788a6",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(3),
    target=NO_TARGET,
    todo=("etl.monster.summon_ref()",),
)
def m3788a6(c: Cast) -> None:
    """No ref names the songbird swarms this summons -- the same gap
    `level_09/controllers_sa.py` named for `m5626a6`."""


# ==========================================================================
# m4008
# ==========================================================================


@power(
    "m4008a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=21),
    damage=Damage("2d10", 5),
)
def m4008a0(c: Cast) -> None:
    victim = c.target
    if not c.strike():
        return
    c.hit()
    if victim is None:
        return
    choice = c.choose(["marked", "slowed"], f"{c.ref}: which")
    if choice == "slowed":
        c.slowed(until=When.EONT, on=victim)
    else:
        c.mark(on=victim, until=When.EONT)


@power(
    "m4008a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m4008a1(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    for _ in range(2):
        c.use_power("m4008a0", on=victim)


@power(
    "m4008a2",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=14),
    damage=Damage("3d10", 5),
    dropped=("etl.monster.summon_ref()",),
)
def m4008a2(c: Cast) -> None:
    """The damage lands. No ref names the viper swarm it spills."""
    if c.strike():
        c.hit()


@power(
    "m4008a3",
    level=10,
    usage=AT_WILL,
    once_per_round=True,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=WILL, printed=14),
)
def m4008a3(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.cannot_attack(on=victim, against=c.me, until=When.SAVE_ENDS)


@power(
    "m4008a4",
    level=10,
    usage=AT_WILL,
    action=OPPORTUNITY,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="an enemy starts its turn within 2 squares of it",
    on=Trigger(TurnStart, enemy_within(2), "an enemy starts its turn within 2 squares of it"),
)
def m4008a4(c: Cast) -> None:
    """"The triggering enemy must make a basic attack against one ally."

    The ally has to be one the *enemy* can hit. The trigger only says the
    enemy started its turn within 2 squares of the m4008, which says nothing
    about where anybody else is standing, so the chooser was free to pick an
    ally the forced swing could not have reached."""
    foe = c.trigger.actor
    span = _swing_reach(c, foe)
    pool = [a for a in c.allies() if distance_between(c.world, foe, a) <= span]
    ally = c.choose(pool, f"{c.ref}: {foe}'s target") if pool else None
    if ally is not None:
        c.basic(who=foe, on=ally)


@power(
    "m4008a5",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4008a5(c: Cast) -> None:
    me = c.me

    def splash(ev: Hit) -> None:
        if not by_melee(c.world, me, ev) or not adjacent(c.world, ev.target, me):
            return
        amount = 10 if c.bloodied(on=me) else 5
        c.flat(amount, dtype=DamageType.POISON, on=ev.target)

    c.watch(Hit, splash, until=When.ENCOUNTER, on=me, label=c.ref)


# ==========================================================================
# m5184
# ==========================================================================


@power(
    "m5184a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("", 9, kind=MINION),
)
def m5184a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5184a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=REF, printed=13),
)
def m5184a1(c: Cast) -> None:
    victim = c.target
    if victim is None or not c.strike(on=victim):
        return
    already = victim in c.grabbing(of=c.me)
    grabbed = c.grab(on=victim)
    if already and grabbed is not None:
        c.blinded(on=victim, until=When.ENCOUNTER)
        grabbed.on_end.append(lambda v=victim: c.cure(Condition.BLINDED, on=v))


# ==========================================================================
# m5192
# ==========================================================================


@power(
    "m5192a0",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PSYCHIC],
)
def m5192a0(c: Cast) -> None:
    me = c.me
    c.aura(3, label=c.ref, on=me, until=When.ENCOUNTER)
    negated_until = [-1]

    def hurt(ev: DamageApplied) -> None:
        if ev.target == me and ev.dtype == DamageType.RADIANT:
            negated_until[0] = c.world.round + 1

    def tick(ev: TurnStart) -> None:
        if c.world.round <= negated_until[0]:
            return
        if ev.actor == me or ev.actor not in c.enemies() or not c.in_my_aura(ev.actor, label=c.ref):
            return
        c.flat(5, dtype=DamageType.PSYCHIC, on=ev.actor)
        c.dazed(until=When.SONT, on=ev.actor)

    c.watch(DamageApplied, hurt, until=When.ENCOUNTER, on=me, label=f"{c.ref} radiant")
    c.watch(TurnStart, tick, until=When.ENCOUNTER, on=me, label=f"{c.ref} aura")


@power(
    "m5192a1",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5192a1(c: Cast) -> None:
    me = c.me
    queue: list[Any] = []

    def slain(ev: Dropped) -> None:
        if ev.source != me or ev.actor is None:
            return
        if "humanoid" not in c.kinds_of(on=ev.actor):
            return
        spot = c.world.get(ev.actor, Position)
        if spot is not None:
            queue.append(spot.square)

    def rise(ev: TurnStart) -> None:
        if ev.actor != me or not queue:
            return
        for spot in queue:
            c.summon("m5192", at=spot, team=Team.NEUTRAL)
        queue.clear()

    c.watch(Dropped, slain, until=When.ENCOUNTER, on=me, label=f"{c.ref} spawn")
    c.watch(TurnStart, rise, until=When.ENCOUNTER, on=me, label=f"{c.ref} rise")


@power(
    "m5192a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.MELEE],
    attack=Attack(vs=WILL, printed=13),
    damage=Damage("2d6", 10, dtype=DamageType.PSYCHIC),
)
def m5192a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.penalty(WILL, 2, until=When.SAVE_ENDS)


@power(
    "m5192a3",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.MELEE],
    attack=Attack(vs=WILL, printed=13),
    damage=Damage("3d6", 9, dtype=DamageType.PSYCHIC),
)
def m5192a3(c: Cast) -> None:
    """"The target moves its speed and makes a basic attack against its
    nearest ally."

    The ally is picked *before* the move, because `c.run_at` is what walks a
    creature into reach of a named one -- `c.move` hands its destinations to
    the decider unordered, so the victim was as likely to walk away. And the
    swing is still gated on reach afterwards: the move is "up to its speed"
    and may not close the gap at all, and nothing downstream of an explicit
    target measures it."""
    victim = c.target
    if not c.strike():
        return
    c.hit()
    if victim is None:
        return
    mate = min(
        (a for a in allies(c.world, victim) if a != victim),
        key=lambda a: (distance_between(c.world, victim, a), a),
        default=None,
    )
    if mate is None:
        return
    c.run_at(mate, who=victim)
    if distance_between(c.world, victim, mate) <= _swing_reach(c, victim):
        c.basic(who=victim, on=mate)


# ==========================================================================
# m5419
# ==========================================================================


@power(
    "m5419a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE, Keyword.MELEE],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("3d6", 7, dtype=DamageType.FORCE),
)
def m5419a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(1)


@power(
    "m5419a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE, Keyword.RANGED],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("3d6", 7, dtype=DamageType.FORCE),
)
def m5419a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(2)


@power(
    "m5419a2",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(2, within=10),
    target=EACH_CREATURE,
    keywords=[Keyword.FORCE, Keyword.AREA],
    attack=Attack(vs=REF, printed=14),
)
def m5419a2(c: Cast) -> None:
    victim = c.target
    if victim is None or not c.strike(on=victim):
        return
    c.world.effects.apply(
        victim,
        c.me,
        When.SAVE_ENDS,
        label=c.ref,
        conditions=[Condition.RESTRAINED],
        ongoing=(10, DamageType.FORCE),
    )


# ==========================================================================
# m5476
# ==========================================================================


@power(
    "m5476a0",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5476a0(c: Cast) -> None:
    c.ignores_difficult(on=c.me, until=When.ENCOUNTER)


@power(
    "m5476a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.MELEE],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("2d8", 9, dtype=DamageType.NECROTIC),
)
def m5476a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        for defence in EVERY_DEFENCE:
            c.penalty(defence, 2, until=When.EONT)


@power(
    "m5476a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(4),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=13),
    damage=Damage("1d10", 9),
)
def m5476a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(4)


@power(
    "m5476a3",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m5476a3(c: Cast) -> None:
    for _ in range(2):
        c.basic(on=c.target)


@power(
    "m5476a4",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_ENEMY,
    attack=Attack(vs=REF, printed=13),
    damage=Damage("3d10", 10),
)
def m5476a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS)


@power(
    "m5476a5",
    level=10,
    usage=Usage.ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(4, within=10),
    target=NO_TARGET,
    keywords=[Keyword.ILLUSION, Keyword.ZONE, Keyword.AREA],
    dropped=("c.grant_action(move_zone)",),
)
def m5476a5(c: Cast) -> None:
    """The zone, its exemption and the on-end slide are written. Nothing
    offers "move the zone" as a chooseable minor action later in the
    fight -- the symbol that does not resolve, per the module docstring."""
    area = frozenset(c.area())
    zone = c.zone(area, until=When.ENCOUNTER, difficult=True, label=c.ref)
    for friend in {c.me, *c.allies()}:
        c.ignores_difficult(c.ref, on=friend, until=When.ENCOUNTER)

    def tick(ev: TurnEnd) -> None:
        if ev.actor in c.in_squares(area, side="enemy"):
            c.slide(2, on=ev.actor)

    c.watch(TurnEnd, tick, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} zone")
    _ = zone


@power(
    "m5476a6",
    level=10,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
    out_of_combat=True,
)
def m5476a6(c: Cast) -> None:
    c.note(f"{c.ref}: disguises itself as a Medium humanoid")


# ==========================================================================
# m5606
# ==========================================================================


@power(
    "m5606a0",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PSYCHIC],
)
def m5606a0(c: Cast) -> None:
    me = c.me
    aura = c.aura(3, label=c.ref, on=me, until=When.ENCOUNTER)

    def tick(ev: TurnEnd) -> None:
        if not c.bloodied(on=me):
            return
        if ev.actor == me or ev.actor not in c.enemies() or not c.in_my_aura(ev.actor, label=c.ref):
            return
        c.flat(5, dtype=DamageType.PSYCHIC, on=ev.actor)
        c.slide(3, on=ev.actor)

    c.watch(TurnEnd, tick, until=When.ENCOUNTER, on=me, label=f"{c.ref} aura")
    _ = aura


@power(
    "m5606a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d8", 5),
)
def m5606a1(c: Cast) -> None:
    victim = c.target
    if not c.strike():
        return
    c.hit()
    pool = [f for f in c.enemies() if f != victim and c.distance(to=f) <= 3]
    foe = c.choose(pool, f"{c.ref}: who else takes psychic damage") if pool else None
    if foe is not None:
        c.flat(5, dtype=DamageType.PSYCHIC, on=foe)


@power(
    "m5606a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR, Keyword.IMPLEMENT, Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=13),
    damage=Damage("1d8", 5, dtype=DamageType.PSYCHIC),
    dropped=("c.cannot_opportunity()",),
)
def m5606a2(c: Cast) -> None:
    """The shift-lock lands. Nothing prevents a creature from *making* an
    opportunity attack -- `c.no_provoke` is the other side of that coin."""
    if c.strike():
        c.hit()
        c.cannot_shift(until=When.EONT)


@power(
    "m5606a3",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=13),
)
def m5606a3(c: Cast) -> None:
    victim = c.target
    _recharge_on(c, Miss, lambda ev: ev.attacker == c.me and ev.power == c.ref)
    if not c.strike():
        if victim is not None:
            c.flat(5, dtype=DamageType.PSYCHIC, on=victim)
        return
    hold = c.condition(Condition.DOMINATED, until=When.SAVE_ENDS)
    if hold is not None and victim is not None:
        hold.on_end.append(lambda v=victim: c.flat(5, dtype=DamageType.PSYCHIC, on=v))


@power(
    "m5606a4",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(2, within=10),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR, Keyword.IMPLEMENT, Keyword.PSYCHIC, Keyword.AREA],
    attack=Attack(vs=WILL, printed=13),
    damage=Damage("1d8", 5, dtype=DamageType.PSYCHIC),
)
def m5606a4(c: Cast) -> None:
    victim = c.target
    if not c.strike():
        return
    c.hit()
    if victim is None:
        return
    # Only creatures the victim's own basic attack can reach are offered:
    # "a creature m5606 chooses" is a choice among legal targets, and the
    # chooser was being handed the whole board because an explicit target
    # skips the reach check.
    span = _swing_reach(c, victim)
    pool = [
        f for f in c.enemies()
        if f != victim and distance_between(c.world, victim, f) <= span
    ]
    foe = c.choose(pool, f"{c.ref}: who {victim} attacks") if pool else None
    if foe is None:
        return
    c.basic(who=victim, on=foe)
    if c.landed:
        c.condition(Condition.STUNNED, until=When.SAVE_ENDS, on=foe)


@power(
    "m5606a5",
    level=10,
    usage=Usage.ENCOUNTER,
    action=FREE,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR, Keyword.IMPLEMENT, Keyword.PSYCHIC],
    trigger="m5606 is first bloodied",
    on=Trigger(Bloodied, about_me, "m5606 is first bloodied"),
    attack=Attack(vs=WILL, printed=13),
)
def m5606a5(c: Cast) -> None:
    if c.strike():
        c.dazed(until=When.SAVE_ENDS)
    if c.first:
        c.slowed(until=When.EONT, on=c.me)


@power(
    "m5606a6",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
    trigger="m5606 is hit by an attack",
    on=Trigger(Hit, targets_me, "m5606 is hit by an attack"),
)
def m5606a6(c: Cast) -> None:
    c.teleport(c.roll("1d8"), who=c.me)


# ==========================================================================
# m5631
# ==========================================================================


@power(
    "m5631a0",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5631a0(c: Cast) -> None:
    me = c.me
    c.aura(1, label=c.ref, on=me, until=When.ENCOUNTER)

    def tick(ev: TurnEnd) -> None:
        if ev.actor == me or ev.actor not in c.enemies() or not c.in_my_aura(ev.actor, label=c.ref):
            return
        c.slowed(until=When.EONT, on=ev.actor)

    c.watch(TurnEnd, tick, until=When.ENCOUNTER, on=me, label=f"{c.ref} aura")


@power(
    "m5631a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD, Keyword.MELEE],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("2d6", 8, dtype=DamageType.COLD),
)
def m5631a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(2)


@power(
    "m5631a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=UpTo(2),
    keywords=[Keyword.COLD, Keyword.IMPLEMENT, Keyword.RANGED],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("3d6", 8, dtype=DamageType.COLD),
)
def m5631a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized(until=When.EONT)


@power(
    "m5631a3",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD, Keyword.IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("3d8", 6, dtype=DamageType.COLD, half_on_miss=True),
)
def m5631a3(c: Cast) -> None:
    victim = c.target
    _recharge_on(c, Bloodied, lambda ev: ev.actor == c.me)
    if not c.strike():
        c.hit(half=True)
        if victim is not None:
            c.ongoing(5, DamageType.COLD, on=victim)
        return
    c.hit()
    if victim is None:
        return
    hold = c.world.effects.apply(
        victim,
        c.me,
        When.SAVE_ENDS,
        label=c.ref,
        relations=[(Relation.GRANTS_CA_TO, victim, c.me)],
        ongoing=(5, DamageType.COLD),
    )

    def nearby(ev: TurnStart) -> None:
        if hold.ended or ev.actor not in c.enemies() or not adjacent(c.world, ev.actor, victim):
            return
        c.flat(5, dtype=DamageType.COLD, on=ev.actor)

    hold.subs.append(c.world.bus.on(TurnStart, nearby, owner=c.me))


@power(
    "m5631a4",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=FREE,
    reach=CloseBurst(5),
    target=NO_TARGET,
    keywords=[Keyword.COLD, Keyword.CLOSE],
    trigger="an enemy within 5 squares of it hits it with an attack",
    on=Trigger(
        Hit,
        lambda world, me, ev: (
            ev.target == me
            and ev.attacker in enemies(world, me)
            and distance_between(world, me, ev.attacker) <= 5
        ),
        "an enemy within 5 squares of it hits it with an attack",
    ),
)
def m5631a4(c: Cast) -> None:
    _recharge_on(c, Bloodied, lambda ev: ev.actor == c.me)
    foe = c.trigger.attacker
    c.flat(10, dtype=DamageType.COLD, on=foe)
    c.push(2, on=foe)


# ==========================================================================
# m5661
# ==========================================================================


@power(
    "m5661a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d8", 9),
)
def m5661a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5661a1",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(5),
    target=UpTo(2),
    keywords=[Keyword.CHARM, Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=13),
    damage=Damage("2d10", 11, dtype=DamageType.PSYCHIC),
)
def m5661a1(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    c.condition(
        Condition.SLOWED,
        until=When.SAVE_ENDS,
        escalate=lambda eff: c.condition(
            Condition.IMMOBILIZED,
            until=When.SAVE_ENDS,
            on=eff.owner,
            escalate=lambda eff2: c.condition(
                Condition.DOMINATED, until=When.SAVE_ENDS, on=eff2.owner
            ),
        ),
    )


@power(
    "m5661a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, within=5),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC, Keyword.AREA],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("2d10", 7, dtype=DamageType.PSYCHIC),
)
def m5661a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(3)


@power(
    "m5661a3",
    level=10,
    usage=Usage.ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
)
def m5661a3(c: Cast) -> None:
    c.teleport(10, who=c.me)


@power(
    "m5661a4",
    level=10,
    usage=Usage.ENCOUNTER,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
    trigger="an enemy makes a melee or ranged attack against it, and an ally is adjacent to it",
    on=Trigger(
        AttackDeclared,
        targets_me,
        "an enemy makes a melee or ranged attack against it, and an ally is adjacent to it",
    ),
)
def m5661a4(c: Cast) -> None:
    me = c.me
    mate = next((a for a in c.allies() if c.adjacent(to=a)), None)
    if mate is None:
        return
    c.swap(mate, who=me)
    c.redirect(to=mate)


@power(
    "m5661a5",
    level=10,
    usage=Usage.ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it drops to 0 hit points",
    on=Trigger(Dropped, about_me, "it drops to 0 hit points"),
)
def m5661a5(c: Cast) -> None:
    c.extra_action(ActionType.STANDARD, on=c.me)


# ==========================================================================
# m5787
# ==========================================================================


@power(
    "m5787a0",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.transform(into=)",),
)
def m5787a0(c: Cast) -> None:
    """Nothing replaces a creature's whole stat block with a different
    one in place of killing it -- `c.reanimate` keeps the same entity's
    own numbers, which is not what "permanently becomes" asks for."""


@power(
    "m5787a1",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5787a1(c: Cast) -> None:
    c.ignores_difficult(on=c.me, until=When.ENCOUNTER)


@power(
    "m5787a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.MELEE],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("2d8", 9, dtype=DamageType.NECROTIC),
)
def m5787a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        for defence in EVERY_DEFENCE:
            c.penalty(defence, 2, until=When.EONT)


@power(
    "m5787a3",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(4),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=13),
    damage=Damage("1d10", 9),
)
def m5787a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(4)


@power(
    "m5787a4",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m5787a4(c: Cast) -> None:
    for _ in range(2):
        c.basic(on=c.target)


@power(
    "m5787a5",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=13),
    damage=Damage("2d10", 7, dtype=DamageType.PSYCHIC),
)
def m5787a5(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.hit()
        c.vulnerable(5, DamageType.PSYCHIC, until=When.EONT, on=victim)


@power(
    "m5787a6",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_ENEMY,
    attack=Attack(vs=REF, printed=13),
    damage=Damage("3d10", 10),
)
def m5787a6(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS)


@power(
    "m5787a7",
    level=10,
    usage=Usage.ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(4, within=10),
    target=NO_TARGET,
    keywords=[Keyword.ILLUSION, Keyword.ZONE, Keyword.AREA],
    dropped=("c.grant_action(move_zone)",),
)
def m5787a7(c: Cast) -> None:
    area = frozenset(c.area())
    zone = c.zone(area, until=When.ENCOUNTER, difficult=True, label=c.ref)
    for friend in {c.me, *c.allies()}:
        c.ignores_difficult(c.ref, on=friend, until=When.ENCOUNTER)

    def tick(ev: TurnEnd) -> None:
        if ev.actor in c.in_squares(area, side="enemy"):
            c.slide(2, on=ev.actor)

    c.watch(TurnEnd, tick, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} zone")
    _ = zone


@power(
    "m5787a8",
    level=10,
    usage=Usage.ENCOUNTER,
    action=MINOR,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
)
def m5787a8(c: Cast) -> None:
    pool = []
    for eid in c.allies():
        health = c.world.get(eid, Health)
        ident = c.world.get(eid, Ident)
        if health is None or ident is None or health.hp > 0:
            continue
        if ident.ref not in ("m5789", "m5788", "m5790"):
            continue
        if distance_between(c.world, c.me, eid) <= 10:
            pool.append(eid)
    chosen = c.choose(pool, f"{c.ref}: who returns to life") if pool else None
    if chosen is not None and c.reanimate(on=chosen, hp=1):
        c.spend_surge(on=chosen)


@power(
    "m5787a9",
    level=10,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
    out_of_combat=True,
)
def m5787a9(c: Cast) -> None:
    c.note(f"{c.ref}: disguises itself as a Medium humanoid")


# ==========================================================================
# m5814
# ==========================================================================


@power(
    "m5814a0",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5814a0(c: Cast) -> None:
    """Carries its grabbed creatures to wherever it ends its own move --
    an approximation of the printed geometry rather than a step-by-step
    replay of it."""
    me = c.me

    def drag(ev: Moved) -> None:
        if ev.actor != me:
            return
        for victim in c.grabbing(of=me):
            c.teleport(1, who=victim, to=ev.to)

    c.watch(Moved, drag, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m5814a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(4),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d10", 7),
)
def m5814a1(c: Cast) -> None:
    victim = _restricted_to(c, 4, lambda f: f not in c.grabbing(of=c.me))
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)


@power(
    "m5814a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(4),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=13),
    damage=Damage("2d10", 2),
)
def m5814a2(c: Cast) -> None:
    def small_and_free(f: int) -> bool:
        from combat_engine.content.monsters.level_03.brutes import NO_BIGGER_THAN_MEDIUM
        from combat_engine.engine import Size

        return f not in c.grabbing(of=c.me) and c.size_of(on=f) in (
            *NO_BIGGER_THAN_MEDIUM,
            Size.LARGE,
        )

    victim = _restricted_to(c, 4, small_and_free)
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)
    c.pull(3, on=victim)
    hold = c.grab(on=victim)
    if hold is not None:
        bleed = c.world.effects.apply(
            victim, c.me, When.ENCOUNTER, label=f"{c.ref} bleed", ongoing=(5, DamageType.UNTYPED)
        )
        hold.on_end.append(lambda b=bleed: c.world.effects.end(b, "the grab ended"))


@power(
    "m5814a3",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d8", 9),
)
def m5814a3(c: Cast) -> None:
    victim = _restricted_to(c, 1, lambda f: f in c.grabbing(of=c.me))
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)
        c.no_healing(on=victim, until=When.SONT)


@power(
    "m5814a4",
    level=10,
    usage=AT_WILL,
    once_per_round=True,
    action=MINOR,
    reach=CloseBurst(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.CLOSE],
    attack=Attack(vs=WILL, printed=13),
)
def m5814a4(c: Cast) -> None:
    if c.strike():
        c.pull(5)


@power(
    "m5814a5",
    level=10,
    usage=Usage.ENCOUNTER,
    action=MINOR,
    reach=AreaBurst(2, within=10),
    target=NO_TARGET,
    keywords=[Keyword.LIGHTNING, Keyword.THUNDER, Keyword.ZONE, Keyword.AREA],
)
def m5814a5(c: Cast) -> None:
    area = frozenset(c.area())
    zone = c.zone(area, until=When.SUSTAIN, sustain=MINOR, label=c.ref)

    def tick(ev: TurnEnd) -> None:
        if ev.actor in c.in_squares(area, side="any"):
            c.flat(10, dtype=DamageType.LIGHTNING, on=ev.actor)

    c.watch(TurnEnd, tick, until=When.SUSTAIN, on=c.me, label=f"{c.ref} zone")
    _ = zone


# ==========================================================================
# m5907
# ==========================================================================


@power(
    "m5907a0",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5907a0(c: Cast) -> None:
    me = c.me
    c.aura(1, label=c.ref, on=me, until=When.ENCOUNTER)

    def tick(ev: TurnEnd) -> None:
        if not c.in_my_aura(ev.actor, label=c.ref):
            return
        c.flat(5, on=ev.actor)

    c.watch(TurnEnd, tick, until=When.ENCOUNTER, on=me, label=f"{c.ref} aura")


@power(
    "m5907a1",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.substitute_condition()",),
)
def m5907a1(c: Cast) -> None:
    """Nothing intercepts an incoming condition and replaces it with a
    different one -- only immunity exists, which would refuse the
    daze too. Nothing else on `Cast` has anywhere to put this row's
    whole printed Effect, so it is refused rather than half-written."""


@power(
    "m5907a2",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5907a2(c: Cast) -> None:
    """Regeneration 20, switched off for a turn by acid or fire."""
    heals = c.regeneration(20, until=When.ENCOUNTER, on=c.me)
    c.suspend_when(
        heals, DamageApplied,
        lambda ev: ev.target == c.me
        and bool({DamageType.ACID, DamageType.FIRE} & {ev.dtype, *ev.dtypes}),
        for_=When.EONT,
    )


@power(
    "m5907a3",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d10", 7),
)
def m5907a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(2)


@power(
    "m5907a4",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
)
def m5907a4(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    hits = 0
    for _ in range(2):
        c.use_power("m5907a3", on=victim)
        if c.landed:
            hits += 1
    if hits == 2:
        c.weakened(until=When.EONT, on=victim)


@power(
    "m5907a5",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("2d10", 10),
)
def m5907a5(c: Cast) -> None:
    victim = c.target
    if not c.strike():
        return
    c.hit()
    c.pull(4)
    if victim is not None:
        c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS, on=victim)


@power(
    "m5907a6",
    level=10,
    usage=Usage.ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_CREATURE,
    keywords=[Keyword.POISON, Keyword.AREA],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("2d8", 3, dtype=DamageType.POISON, half_on_miss=True),
    dropped=("Condition.CANNOT_TELEPORT",),
)
def m5907a6(c: Cast) -> None:
    """The restrained-plus-ongoing half is exact. Nothing in the vocabulary
    says "cannot teleport" -- only "cannot shift" exists."""
    victim = c.target
    if c.strike():
        c.hit()
        if victim is not None:
            c.world.effects.apply(
                victim,
                c.me,
                When.SAVE_ENDS,
                label=c.ref,
                conditions=[Condition.RESTRAINED],
                ongoing=(10, DamageType.POISON),
            )
    else:
        c.hit(half=True)
        if victim is not None:
            c.world.effects.apply(
                victim,
                c.me,
                When.SAVE_ENDS,
                label=f"{c.ref} miss",
                conditions=[Condition.SLOWED],
                ongoing=(5, DamageType.POISON),
            )


@power(
    "m5907a7",
    level=10,
    usage=AT_WILL,
    action=OPPORTUNITY,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is damaged by an enemy attack",
    on=Trigger(DamageApplied, targets_me, "it is damaged by an enemy attack"),
)
def m5907a7(c: Cast) -> None:
    foe = c.trigger.source if getattr(c.trigger, "source", None) is not None else None
    c.use_power("m5907a3", on=foe) if foe is not None else None


# ==========================================================================
# m5980
# ==========================================================================


@power(
    "m5980a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD, Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("2d8", 9, dtype=DamageType.COLD),
)
def m5980a0(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.hit()
        c.push(2)
        if victim is not None:
            c.immobilized(until=When.EONT, on=victim)


@power(
    "m5980a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD, Keyword.IMPLEMENT, Keyword.RANGED],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("2d8", 9, dtype=DamageType.COLD),
)
def m5980a1(c: Cast) -> None:
    victim = c.target
    if not c.strike():
        return
    c.hit()
    if victim is None:
        return
    spot = c.world.get(victim, Position)
    if spot is None:
        return
    area = spread({spot.square}, 1)
    zone = c.zone(area, until=When.EONT, difficult=True, label=c.ref)
    _ = zone


@power(
    "m5980a2",
    level=10,
    usage=Usage.ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(2, within=5),
    target=EACH_ENEMY,
    keywords=[Keyword.COLD, Keyword.IMPLEMENT, Keyword.AREA],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("2d8", 9, dtype=DamageType.COLD, half_on_miss=True),
)
def m5980a2(c: Cast) -> None:
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)


@power(
    "m5980a3",
    level=10,
    usage=Usage.ENCOUNTER,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="an attack hits it",
    on=Trigger(AttackRolled, would_hit_me, "an attack hits it"),
)
def m5980a3(c: Cast) -> None:
    c.bonus(c.trigger.vs, 4, until=When.EONT, on=c.me, once=True)


@power(
    "m5980a4",
    level=10,
    usage=Usage.ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it hits an enemy with an implement attack",
    on=Trigger(
        Hit,
        when=lambda world, me, ev: _my_implement_hit(world, me, ev),
        text="it hits an enemy with an implement attack",
    ),
)
def m5980a4(c: Cast) -> None:
    c.maximise(on=c.me, ref=getattr(c.trigger, "power", ""), until=When.EOT)


# ==========================================================================
# m5987
# ==========================================================================


@power(
    "m5987a0",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.RADIANT],
)
def m5987a0(c: Cast) -> None:
    _sunlit(c, 5)


@power(
    "m5987a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("4d6", 4),
)
def m5987a1(c: Cast) -> None:
    if c.strike():
        c.hit()
    c.slide(3)


@power(
    "m5987a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING, Keyword.POISON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d10", 5),
)
def m5987a2(c: Cast) -> None:
    def helpless_enough(f: int) -> bool:
        return (
            c.is_(Condition.DAZED, on=f)
            or c.is_(Condition.DOMINATED, on=f)
            or c.is_(Condition.STUNNED, on=f)
            or c.is_(Condition.UNCONSCIOUS, on=f)
        )

    victim = _restricted_to(c, 1, helpless_enough)
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)
    c.ongoing(10, DamageType.POISON, on=victim)
    c.heal(15, on=c.me)


@power(
    "m5987a3",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=13),
    damage=Damage("3d6", 4, dtype=DamageType.PSYCHIC),
)
def m5987a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.EONT)
    c.pull(3)


@power(
    "m5987a4",
    level=10,
    usage=Usage.ENCOUNTER,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POLYMORPH],
    trigger="it takes damage while bloodied",
    on=Trigger(DamageApplied, _hit_while_bloodied, "it takes damage while bloodied"),
)
def m5987a4(c: Cast) -> None:
    me = c.me
    for defence in EVERY_DEFENCE:
        c.bonus(defence, 5, on=me, until=When.ENCOUNTER, kind="untyped")
    hold = c.bonus("speed", 2, on=me, until=When.ENCOUNTER)
    if hold is None:
        return

    def ends_on_attack(ev: AttackDeclared) -> None:
        if not hold.ended and ev.attacker == me:
            c.world.effects.end(hold, "it attacked")

    hold.subs.append(c.world.bus.on(AttackDeclared, ends_on_attack, owner=me))


# ==========================================================================
# m6070
# ==========================================================================


@power(
    "m6070a0",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6070a0(c: Cast) -> None:
    me = c.me

    def try_shed(ev: Any) -> None:
        mine = [
            e for e in c.world.effects.of(me) if e.owner == me and not e.ended and e.source != me
        ]
        if not mine:
            return
        eff = mine[0]
        if not c.save(bonus=0):
            return
        c.world.effects.end(eff, "m6070 shed it")
        foe = next((f for f in c.enemies() if c.adjacent(to=f)), None)
        if foe is not None:
            c.transfer(eff, to=foe)

    c.watch(TurnStart, try_shed, until=When.ENCOUNTER, on=me, label=f"{c.ref} start")
    c.watch(TurnEnd, try_shed, until=When.ENCOUNTER, on=me, label=f"{c.ref} end")


@power(
    "m6070a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.NECROTIC, Keyword.MELEE],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("3d6", 7, dtype=[DamageType.FIRE, DamageType.NECROTIC]),
)
def m6070a1(c: Cast) -> None:
    if c.strike():
        c.hit()
    c.slide(1)


@power(
    "m6070a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=UpTo(2),
    keywords=[Keyword.NECROTIC, Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=13),
    damage=Damage("3d6", 7, dtype=[DamageType.NECROTIC, DamageType.PSYCHIC]),
)
def m6070a2(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.hit()
        if victim is not None:
            c.sight_range(2, on=victim, until=When.SAVE_ENDS)


@power(
    "m6070a3",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=13),
    dropped=("Condition.weakened(unless=)",),
)
def m6070a3(c: Cast) -> None:
    """The chosen ally's duration bookkeeping is exact. Weakened cannot be
    scoped to "against anyone but the chosen ally" -- the condition
    applies or it does not, with no per-target gate."""
    victim = c.target
    _recharge_on(c, Miss, lambda ev: ev.attacker == c.me and ev.power == c.ref)
    if not c.strike():
        return
    pool = [a for a in c.allies() if not c.is_kind("elite", on=a) and not c.is_kind("solo", on=a)]
    chosen = c.choose(pool, f"{c.ref}: which ally") if pool else None
    if victim is None or chosen is None:
        return
    hold = c.weakened(until=When.ENCOUNTER, on=victim)
    if hold is None:
        return

    def ends_if_ally_drops(ev: Dropped) -> None:
        if not hold.ended and ev.actor == chosen:
            c.world.effects.end(hold, "the chosen ally dropped")

    hold.subs.append(c.world.bus.on(Dropped, ends_if_ally_drops, owner=c.me))


@power(
    "m6070a4",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC, Keyword.ZONE, Keyword.AREA],
)
def m6070a4(c: Cast) -> None:
    _recharge_on(c, Bloodied, lambda ev: ev.actor == c.me)
    area = frozenset(c.area())
    zone = c.zone(area, until=When.SUSTAIN, sustain=MINOR, difficult=True, label=c.ref)
    for friend in {c.me, *c.allies()}:
        c.ignores_difficult(c.ref, on=friend, until=When.ENCOUNTER)

    def tick(ev: Any) -> None:
        if ev.actor in c.in_squares(area, side="enemy"):
            c.flat(10, dtype=DamageType.NECROTIC, on=ev.actor)

    from combat_engine.engine.events import ZoneEntered as _ZE

    c.watch(_ZE, tick, until=When.SUSTAIN, on=c.me, label=f"{c.ref} enter")
    c.watch(TurnEnd, tick, until=When.SUSTAIN, on=c.me, label=f"{c.ref} end")
    _ = zone


@power(
    "m6070a5",
    level=10,
    usage=Usage.ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
)
def m6070a5(c: Cast) -> None:
    c.teleport(3, who=c.me)
    c.insubstantial(on=c.me, until=When.SONT)


@power(
    "m6070a6",
    level=10,
    usage=Usage.ENCOUNTER,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="an attack hits it while it is bloodied",
    on=Trigger(
        Hit,
        lambda world, me, ev: (
            ev.target == me and world.get(me, Health) is not None and world.get(me, Health).bloodied
        ),
        "an attack hits it while it is bloodied",
    ),
)
def m6070a6(c: Cast) -> None:
    c.restore_use("m6070a5", on=c.me)
    c.use_power("m6070a5")


# ==========================================================================
# m6109
# ==========================================================================


@power(
    "m6109a0",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.speed_while_squeezing()", "c.no_advantage(squeezing=)"),
)
def m6109a0(c: Cast) -> None:
    """Cancels the attack-roll half of squeezing's penalty while dim or
    dark. The speed half and the combat-advantage half have nothing to
    override -- `Condition.SQUEEZING` carries neither a speed modifier
    nor an advantage grant this can gate off."""
    c.bonus(
        "attack",
        5,
        on=c.me,
        kind="untyped",
        until=When.ENCOUNTER,
        when=lambda ctx: (
            c.is_(Condition.SQUEEZING, on=c.me)
            and (c.terrain("darkness") or c.terrain("dim light"))
        ),
    )


@power(
    "m6109a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d12", 5),
)
def m6109a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6109a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
)
def m6109a2(c: Cast) -> None:
    if c.grabbing(of=c.me):
        return
    victim = c.target
    if victim is None or not c.strike(on=victim):
        return
    hold = c.grab(on=victim)
    bleed = c.world.effects.apply(
        victim, c.me, When.ENCOUNTER, label=f"{c.ref} bleed", ongoing=(5, DamageType.UNTYPED)
    )
    if hold is not None:
        hold.on_end.append(
            lambda b=bleed, v=victim: (
                c.world.effects.end(b, "the grab ended"),
                c.penalty("attack", 2, on=v, until=When.SAVE_ENDS),
            )
        )


@power(
    "m6109a3",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=13),
    todo=("c.remove_from_play()",),
)
def m6109a3(c: Cast) -> None:
    """The whole printed Effect is removing the target from play --
    nothing on `Cast` takes a creature off the board and schedules its
    return, see the module docstring."""
    victim = _restricted_to(c, 1, lambda f: f in c.grabbing(of=c.me))
    if victim is not None:
        c.strike(on=victim)


@power(
    "m6109a4",
    level=10,
    usage=AT_WILL,
    once_per_round=True,
    action=MINOR,
    reach=Melee(3),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=13),
)
def m6109a4(c: Cast) -> None:
    """ "Once per turn as a free action, can pull up to 3" is collapsed
    into the grab landing with the first pull already spent -- a
    standing, repeatable free action has nothing to lend it a ref."""
    if c.grabbing(of=c.me):
        return
    victim = c.target
    if victim is None or not c.strike(on=victim):
        return
    c.grab(on=victim)
    c.pull(3, on=victim)


@power(
    "m6109a5",
    level=10,
    usage=Usage.ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6109a5(c: Cast) -> None:
    me = c.me
    c.threatens(5, until=When.ENCOUNTER)

    def flee(ev: OpportunityWindow) -> None:
        if ev.actor != me or getattr(ev, "why", "") != "moved away":
            return
        c.move(c.speed_of(), who=me)

    c.watch(OpportunityWindow, flee, until=When.ENCOUNTER, on=me, label=c.ref)


# ==========================================================================
# m6173
# ==========================================================================


@power(
    "m6173a0",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6173a0(c: Cast) -> None:
    _aura_penalty(c, 2, "save", 2)


@power(
    "m6173a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR, Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d8", 8),
)
def m6173a1(c: Cast) -> None:
    if c.strike():
        c.hit()
    c.slide(3)


@power(
    "m6173a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR, Keyword.IMPLEMENT, Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=13),
    damage=Damage("2d8", 10, dtype=DamageType.PSYCHIC),
)
def m6173a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(
            Condition.SLOWED,
            until=When.SAVE_ENDS,
            escalate=lambda eff: c.condition(
                Condition.IMMOBILIZED, until=When.SAVE_ENDS, on=eff.owner
            ),
        )


@power(
    "m6173a3",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR, Keyword.FORCE, Keyword.IMPLEMENT, Keyword.CLOSE],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("2d6", 10, dtype=DamageType.FORCE),
)
def m6173a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(3)
        c.prone()


# ==========================================================================
# m6175
# ==========================================================================


@power(
    "m6175a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("", 9, kind=MINION),
)
def m6175a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        if c.crit:
            c.grants_advantage(until=When.SAVE_ENDS)


@power(
    "m6175a1",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.IMPLEMENT],
    attack=Attack(vs=WILL, printed=13),
)
def m6175a1(c: Cast) -> None:
    victim = c.target
    _recharge_on(c, Miss, lambda ev: ev.attacker == c.me and ev.power == c.ref)
    if not c.strike() or victim is None:
        return
    c.slide(3)
    ally = next((a for a in c.allies() if adjacent(c.world, a, victim)), None)
    if ally is not None:
        c.basic(who=ally, on=victim)


# ==========================================================================
# m6180
# ==========================================================================


@power(
    "m6180a0",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6180a0(c: Cast) -> None:
    for ally in c.allies():
        if c.is_kind("beast", on=ally) and c.is_kind("natural", on=ally):
            c.gains_advantage(
                lambda ctx: c.adjacent(to=ctx.get("target")),
                on=ally,
                until=When.ENCOUNTER,
            )


@power(
    "m6180a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d8", 8),
)
def m6180a1(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.hit()
        if victim is not None and c.is_(Condition.PRONE, on=victim):
            c.flat(5, on=victim)
        c.push(2)


@power(
    "m6180a2",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(3),
    target=UpTo(2, side="ally"),
)
def m6180a2(c: Cast) -> None:
    ally = c.target
    if ally is None or not (c.is_kind("beast", on=ally) and c.is_kind("natural", on=ally)):
        return
    half = max(1, c.speed_of(who=ally) // 2)
    c.shift(half, who=ally)
    foe = next((f for f in c.enemies() if adjacent(c.world, ally, f)), None)
    if foe is not None:
        c.basic(who=ally, on=foe)


@power(
    "m6180a3",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d4", 3),
    dropped=("events.PowerRecharged",),
)
def m6180a3(c: Cast) -> None:
    """Recharges on its own die; nothing fires when a *different* row
    recharges, so the printed link to `m6180a2` is not kept in step."""
    if c.strike():
        c.hit()
        c.prone()


# ==========================================================================
# m6366
# ==========================================================================


@power(
    "m6366a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("3d6", 4, dtype=DamageType.FIRE),
)
def m6366a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(3)


@power(
    "m6366a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.THUNDER, Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d8", 9, dtype=DamageType.THUNDER),
)
def m6366a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(1)
        c.prone()


@power(
    "m6366a2",
    level=10,
    usage=Usage.ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is first bloodied",
    on=Trigger(Bloodied, about_me, "it is first bloodied"),
)
def m6366a2(c: Cast) -> None:
    c.bonus("attack", 2, on=c.me, until=When.EOT, once=True)
    c.bonus("damage", 2, on=c.me, until=When.EOT, once=True)
    foe = min(c.enemies(), key=lambda f: c.distance(to=f), default=None)
    if foe is not None:
        c.basic(on=foe)


@power(
    "m6366a3",
    level=10,
    usage=Usage.ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC],
    trigger="it hits with a melee basic attack",
)
def m6366a3(c: Cast) -> None:
    """ "With a melee basic attack" narrows which `Hit` counts; armed as a
    watch rather than a declared trigger because that narrowing needs the
    creature's own basic-attack ref, not a predicate `Trigger` can close
    over at import time."""
    me = c.me

    def basic_hit(ev: Hit) -> None:
        known = c.world.get(me, Powers)
        if ev.attacker != me or known is None or ev.power != known.basic:
            return
        c.ongoing(10, DamageType.NECROTIC, on=ev.target)
        c.note(f"{c.ref}: the ground nearby turns to black sand")

    c.watch(Hit, basic_hit, until=When.ENCOUNTER, on=me, label=c.ref)


# ==========================================================================
# m6422
# ==========================================================================


@power(
    "m6422a0",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6422a0(c: Cast) -> None:
    _sunlit(c, 10)


@power(
    "m6422a1",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6422a1(c: Cast) -> None:
    """Regeneration 10, switched off for a turn by radiant damage."""
    heals = c.regeneration(10, until=When.ENCOUNTER, on=c.me)
    c.suspend_when(
        heals, DamageApplied,
        lambda ev: ev.target == c.me
        and DamageType.RADIANT in {ev.dtype, *ev.dtypes},
        for_=When.EONT,
    )


@power(
    "m6422a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d6", 11),
)
def m6422a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6422a3",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING, Keyword.MELEE],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("2d12", 5),
)
def m6422a3(c: Cast) -> None:
    me = c.me
    _recharge_on(c, Bloodied, lambda ev: adjacent(c.world, me, ev.actor))
    victim = _restricted_to(
        c, 1, lambda f: c.is_(Condition.DAZED, on=f) or c.is_(Condition.DOMINATED, on=f)
    )
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)
    c.weakened(until=When.SAVE_ENDS, on=victim)
    c.heal(20, on=me)


@power(
    "m6422a4",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=13),
)
def m6422a4(c: Cast) -> None:
    if c.strike():
        c.condition(Condition.DOMINATED, until=When.SAVE_ENDS)


@power(
    "m6422a5",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(5),
    target=UpTo(2),
    keywords=[Keyword.CHARM],
)
def m6422a5(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    c.pull(99, on=victim, anchor=c.here)
    hits = 0
    for _ in range(2):
        c.use_power("m6422a2", on=victim)
        if c.landed:
            hits += 1
    if hits == 2:
        c.dazed(until=When.EONT, on=victim)


@power(
    "m6422a6",
    level=10,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POLYMORPH],
)
def m6422a6(c: Cast) -> None:
    me = c.me
    c.insubstantial(on=me, until=When.ENCOUNTER)
    hold = c.hover(12, on=me, until=When.ENCOUNTER)
    attack_lock = c.cannot_attack(on=me, against=me, until=When.ENCOUNTER)
    if hold is not None:
        c.endable(hold, cost=MINOR)
    _ = attack_lock


# ==========================================================================
# m6485
# ==========================================================================


@power(
    "m6485a0",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.CHARM],
)
def m6485a0(c: Cast) -> None:
    me = c.me
    aura = c.aura(2, label=c.ref, on=me, until=When.ENCOUNTER)
    holds: dict[int, Effect] = {}

    def enter(ev: ZoneEntered) -> None:
        if ev.zone != aura or ev.actor not in c.enemies() or ev.actor in holds:
            return
        if not any(
            distance_between(c.world, ev.actor, f) <= 10 for f in c.enemies() if f != ev.actor
        ):
            return
        hold = c.cannot_attack(on=ev.actor, against=me, until=When.ENCOUNTER)
        if hold is not None:
            holds[ev.actor] = hold

    def leave(ev: ZoneExited) -> None:
        hold = holds.pop(ev.actor, None)
        if hold is not None:
            c.world.effects.end(hold, "left the aura")

    c.watch(ZoneEntered, enter, until=When.ENCOUNTER, on=me, label=f"{c.ref} in")
    c.watch(ZoneExited, leave, until=When.ENCOUNTER, on=me, label=f"{c.ref} out")


@power(
    "m6485a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("3d8", 5),
)
def m6485a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6485a2",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.POISON, Keyword.CLOSE],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("2d8", 5),
)
def m6485a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.world.effects.apply(
            c.target,
            c.me,
            When.SAVE_ENDS,
            label=c.ref,
            ongoing=(10, DamageType.POISON),
            escalate=lambda eff: c.condition(Condition.SLOWED, until=When.SAVE_ENDS, on=eff.owner),
        )


@power(
    "m6485a3",
    level=10,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
    out_of_combat=True,
)
def m6485a3(c: Cast) -> None:
    c.note(f"{c.ref}: alters its form to appear as a Medium humanoid")


@power(
    "m6485a4",
    level=10,
    usage=AT_WILL,
    once_per_round=True,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.FIRE],
    attack=Attack(vs=WILL, printed=13),
    damage=Damage("2d8", 5, dtype=DamageType.FIRE),
)
def m6485a4(c: Cast) -> None:
    victim = c.target
    if not c.strike():
        return
    c.hit()
    if victim is None:
        return
    pool = [f for f in [c.me, *c.enemies(), *c.allies()] if f != victim]
    chosen = c.choose(pool, f"{c.ref}: {victim}'s target") if pool else None
    if chosen is not None:
        c.basic(who=victim, on=chosen)


# ==========================================================================
# m6692
# ==========================================================================


@power(
    "m6692a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.NECROTIC, Keyword.MELEE],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d4", 7),
    dropped=("c.no_save(while=)",),
)
def m6692a0(c: Cast) -> None:
    """The burn is exact. Nothing in the vocabulary stops a specific
    saving throw from being rolled while a condition holds -- "cannot
    save against the ongoing damage while adjacent" has nowhere to go."""
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.FIRE)


@power(
    "m6692a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE, Keyword.RANGED],
)
def m6692a1(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    c.world.effects.apply(
        victim,
        c.me,
        When.SAVE_ENDS,
        label=c.ref,
        conditions=[Condition.IMMOBILIZED],
        ongoing=(10, DamageType.FORCE),
    )


@power(
    "m6692a2",
    level=10,
    usage=Usage.ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="an enemy within 20 squares of it reduces it to 0 hit points or fewer",
    on=Trigger(
        Dropped, about_me, "an enemy within 20 squares of it reduces it to 0 hit points or fewer"
    ),
)
def m6692a2(c: Cast) -> None:
    foe = c.trigger.source
    if foe is not None and distance_between(c.world, c.me, foe) <= 20:
        c.penalty("save", 2, on=foe, until=When.ENCOUNTER)


# ==========================================================================
# m945
# ==========================================================================


@power(
    "m945a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d10", 2),
)
def m945a0(c: Cast) -> None:
    victim = c.target
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)
    c.world.effects.apply(
        victim,
        c.me,
        When.SAVE_ENDS,
        label=c.ref,
        conditions=[Condition.SLOWED],
        ongoing=(5, DamageType.POISON),
    )


@power(
    "m945a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ALLY,
)
def m945a1(c: Cast) -> None:
    ally = c.target
    if ally is not None:
        c.heal(5, on=ally)
        c.shift(3, who=ally)


@power(
    "m945a2",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.POISON, Keyword.CLOSE],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d4", 4, dtype=DamageType.POISON, kind=LIMITED),
)
def m945a2(c: Cast) -> None:
    victim = c.target
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)
    c.world.effects.apply(
        victim,
        c.me,
        When.SAVE_ENDS,
        label=c.ref,
        conditions=[Condition.DAZED],
        ongoing=(5, DamageType.POISON),
    )


# ==========================================================================
# m964
# ==========================================================================


@power(
    "m964a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.NECROTIC, Keyword.RANGED],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("2d4", 5, dtype=DamageType.NECROTIC),
)
def m964a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m964a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.IMPLEMENT, Keyword.NECROTIC, Keyword.CLOSE],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d8", 8, dtype=DamageType.NECROTIC),
)
def m964a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(1)


@power(
    "m964a2",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(2, within=10),
    target=EACH_ENEMY,
    keywords=[Keyword.COLD, Keyword.IMPLEMENT, Keyword.NECROTIC, Keyword.AREA],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("2d8", 8, dtype=[DamageType.COLD, DamageType.NECROTIC]),
    dropped=("c.conceal_in()",),
)
def m964a2(c: Cast) -> None:
    """The damage is exact. The lingering cloud's concealment has no
    zone-bound primitive -- see the module docstring. The damage tick to
    anyone starting a turn in the area is written."""
    if c.strike():
        c.hit()
    if not c.first:
        return
    area = frozenset(c.area())
    zone = c.zone(area, until=When.EONT, label=c.ref)

    def tick(ev: TurnStart) -> None:
        if ev.actor in c.in_squares(area, side="any"):
            c.flat(5, dtype=DamageType.COLD, on=ev.actor)

    hold_handle = c.watch(TurnStart, tick, until=When.EONT, on=c.me, label=f"{c.ref} zone")
    zc = c.world.get(zone, Zone)
    hold = zc.effect if zc is not None else None
    if hold is not None:
        c.endable(hold, cost=MINOR)
    _ = hold_handle


@power(
    "m964a3",
    level=10,
    usage=Usage.ENCOUNTER,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[
        Keyword.COLD,
        Keyword.CONJURATION,
        Keyword.IMPLEMENT,
        Keyword.NECROTIC,
        Keyword.RANGED,
    ],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("2d8", 8, dtype=[DamageType.COLD, DamageType.NECROTIC]),
)
def m964a3(c: Cast) -> None:
    victim = c.target
    if not c.strike():
        return
    c.hit()
    if victim is None:
        return
    hold = c.grab(on=victim)
    conjured = c.conjure(label=c.ref, until=When.SUSTAIN, sustain=MINOR)

    def resustain() -> None:
        if victim in c.grabbing(of=c.me):
            c.flat(c.roll("1d8") + 8, dtype=DamageType.COLD, on=victim)

    if hold is not None:
        c.on_sustain(hold, resustain)
    _ = conjured


@power(
    "m964a4",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
)
def m964a4(c: Cast) -> None:
    c.teleport(10, who=c.me)


@power(
    "m964a5",
    level=10,
    usage=Usage.ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m964a5(c: Cast) -> None:
    """Card names itself mid-sentence ("the r8") rather than saying "it" --
    read as self, the same shape `level_08/controllers_sa.py` reports for
    `m1108a2`/`m2781a1`."""
    from combat_engine.content.monsters.level_04.lurkers_sa import _hit_me_since_my_turn

    me = c.me

    def since_my_turn(victim: Any) -> bool:
        return victim is not None and victim in _hit_me_since_my_turn(c)

    c.bonus(
        "attack",
        1,
        on=me,
        kind="power",
        until=When.ENCOUNTER,
        once=True,
        when=lambda ctx: since_my_turn(ctx.get("target")),
    )

    def rider(ev: Hit) -> None:
        if ev.attacker == me and since_my_turn(ev.target):
            c.push(1, on=ev.target)

    c.on_attack(rider, by=me, until=When.ENCOUNTER, once=True, label=c.ref)


@power(
    "m964a6",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m964a6(c: Cast) -> None:
    c.bonus(
        "attack",
        1,
        on=c.me,
        kind="racial",
        until=When.ENCOUNTER,
        when=lambda ctx: c.bloodied(on=ctx.get("target")),
    )


@power(
    "m964a7",
    level=10,
    usage=Usage.DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m964a7(c: Cast) -> None:
    c.resist(10, None, on=c.me, until=When.SONT)


@power(
    "m964a8",
    level=10,
    usage=Usage.ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
)
def m964a8(c: Cast) -> None:
    """The card names m964 by its own proper name mid-sentence -- a
    second leak through the extraction, kept out of this file; see the
    module docstring."""
    if c.may("spend a healing surge", who=c.me):
        c.spend_surge(on=c.me)
        c.heal(50, on=c.me)
    for defence in EVERY_DEFENCE:
        c.bonus(defence, 2, on=c.me, until=When.SONT)
