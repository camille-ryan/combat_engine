"""Monster abilities, level 8, controllers -- every block after the first 35.

137 rows, matching `scripts/spec.py --monsters 8 --role controller --offset 35`.
`controllers.py` holds the earlier sweep of this level and `controllers_sa.py`
the first half of this one's; neither is touched here. Seven of this half's
stat blocks (`m456`, `m4796`, `m4974`, `m4989`, `m5010`, `m657`, `m702`) print
no abilities at all and so appear here only as a heading-free absence, the
same convention `level_07/controllers_sa.py` settled.

Conventions, inherited from `level_06/controllers_sa.py` and `level_07/
controllers_sa.py`:

* numbers load from `game.db`; the attack line is written exactly as printed
  and the damage line goes in the header as data;
* a **trait** costs no action, has no target, and arms the watches that hold
  it, whatever the compendium's action column claims;
* a card with no printed range at all is read `Melee(1)` against AC, or at
  the reach the same creature's other ranged row prints against a non-AC
  defence;
* a close burst, blast or area whose card names no target set takes
  **enemies**; one that says "creatures in the burst" takes `EACH_CREATURE`;
* a recharge or encounter attack says `Damage(..., kind=LIMITED)`, a
  minion's flat damage `Damage("", n, kind=MINION)`;
* "First Failed Saving Throw" is `Effect.escalate`, set directly on the hold
  a call such as `c.condition` or `c.ongoing` hands back when the call
  itself takes no `escalate=`;
* "(save ends both)" pairing a burn with a condition or a numeric penalty is
  one `c.world.effects.apply` carrying both, not two calls -- two would be
  two saving throws for a card that prints one.

Four cards needed a judgement call written down rather than guessed at
silently:

* **`m5583a3` prints a name** -- the compendium's own extraction missed one.
  It is read as "it"/`m5583` throughout and named here, not the word, so the
  leak does not repeat itself; see the report.
* `m959a1`'s attack line reads "+12 vs ; 2d6+5 damage.. The m959 makes two
  slam attacks" -- read as two uses of `m959a0`, the way `_twice` already
  reads that shape elsewhere.
* `m959a4`'s burst prints "Burst within 10 squares" with no size; read as
  `AreaBurst(2, 10)`, matching the explicit size on `m959a5`'s identical
  phrasing for the same creature.
* `m952a1`'s effect line reads "each ally in surge can make a basic attack",
  which parses as "the burst" -- read that way, since nothing standing
  between "ally" and "can" survives as "surge" on any other card in the
  tree.

Five helpers are imported rather than written again.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_01.artillery_sa import _cheb
from combat_engine.content.monsters.level_02.artillery_sa import ALL_DEFENCES, _saves_off_prone
from combat_engine.content.monsters.level_02.controllers_sa import _swing_reach
from combat_engine.content.monsters.level_02.lurkers_sa import _twice
from combat_engine.content.monsters.level_03.brutes import NO_BIGGER_THAN_MEDIUM
from combat_engine.content.monsters.level_03.lurkers_sa import _restricted_to
from combat_engine.content.monsters.level_07.controllers import _rearms_when_bloodied
from combat_engine.content.monsters.level_07.controllers_sa import (
    _forbid_everything,
    _no_sight_past,
)
from combat_engine.content.monsters.level_07.minions_sa import _has_bell
from combat_engine.content.monsters.level_07.skirmishers_sa import _grabbed_tries_to_escape
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
    Keyword,
    Melee,
    Ranged,
    Relation,
    UpTo,
    Usage,
    When,
    Window,
    World,
    get,
    power,
    spread,
)
from combat_engine.engine.components import Defences, Gear, Health, Initiative, Movement
from combat_engine.engine.durations import keywords_of
from combat_engine.engine.events import (
    AttackDeclared,
    AttackRolled,
    Bloodied,
    ConditionApplied,
    DamageApplied,
    Dropped,
    ForcedMove,
    Hit,
    RelationCleared,
    SurgeSpent,
    TurnEnd,
    TurnStart,
    ZoneEntered,
    ZoneExited,
)
from combat_engine.engine.monster_math import LIMITED, MINION
from combat_engine.engine.query import (
    adjacent,
    allies,
    can_act,
    distance_between,
    enemies,
    has_combat_advantage,
    is_,
    squares,
    team,
)
from combat_engine.engine.triggers import (
    Trigger,
    about_me,
    both,
    by_melee,
    by_opportunity,
    targets_me,
)

# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------


def _has_scimitar(world: World, eid: int) -> bool:
    """A printed "must be wielding a scimitar", asked of `Gear` the way
    `_has_bell` asks about a bell."""
    gear = world.get(eid, Gear)
    weapon = gear.main if gear is not None else None
    return weapon is not None and (weapon.group == "scimitar" or "scimitar" in weapon.properties)


def _ongoing_amount(world: World, eid: int, dtype: DamageType) -> int:
    """The standing ongoing amount of one type, or 0. "Increases by N" reads
    this and adds, rather than laying a second burn `c.ongoing` would refuse
    or a stronger one that would needlessly supersede with the wrong total."""
    return next(
        (
            e.ongoing[0]
            for e in world.effects.of(eid)
            if e.ongoing and (tuple(e.ongoing_types) or (e.ongoing[1],)) == (dtype,)
        ),
        0,
    )


def _grief_stricken(c: Cast, victim: int | None) -> None:
    """Not a real `Condition` -- the card's own name for a dazed hold that
    also carries vulnerable 5 psychic, one save ending both. Shared by
    `m6075a2` and `m6075a4`, the only two rows that print it."""
    if victim is None:
        return
    hold = c.condition(Condition.DAZED, until=When.SAVE_ENDS, on=victim)
    if hold is None:
        return
    defences = c.world.get(victim, Defences) or c.world.add(victim, Defences())
    defences.vulnerable[DamageType.PSYCHIC] = defences.vulnerable.get(DamageType.PSYCHIC, 0) + 5

    def undo() -> None:
        left = defences.vulnerable.get(DamageType.PSYCHIC, 0) - 5
        if left > 0:
            defences.vulnerable[DamageType.PSYCHIC] = left
        else:
            defences.vulnerable.pop(DamageType.PSYCHIC, None)

    hold.on_end.append(undo)


# ==========================================================================
# m4451
# ==========================================================================


@power(
    "m4451a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d6", 4, dtype=DamageType.NECROTIC),
)
def m4451a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4451a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR, Keyword.IMPLEMENT, Keyword.RADIANT],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("1d6", 4, dtype=DamageType.RADIANT),
)
def m4451a1(c: Cast) -> None:
    """"If the target moves closer on its next turn" is read off `Moved`,
    the same shape `level_01/artillery_sa.py`'s `m4592a2` already uses for
    this exact printed line."""
    if not c.strike():
        return
    c.hit()
    victim, me = c.target, c.me
    if victim is None:
        return
    paid: dict[str, bool] = {}

    def closed(ev: Any) -> None:
        if paid.get("done") or ev.actor != victim:
            return
        if _cheb(ev.to, c.here) < _cheb(ev.from_, c.here):
            paid["done"] = True
            c.flat(c.roll("1d6") + 4, dtype=DamageType.RADIANT, on=victim)

    from combat_engine.engine.events import Moved

    c.watch(Moved, closed, until=When.EOTNT, on=me, label=f"{c.ref} {victim}")


@power(
    "m4451a2",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("2d8", 4, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m4451a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(4)


@power(
    "m4451a3",
    level=8,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=11),
    damage=Damage("1d10", dtype=DamageType.NECROTIC),
    trigger="it is reduced to 0 hit points",
    on=Trigger(Dropped, about_me, "it is reduced to 0 hit points"),
)
def m4451a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.PSYCHIC)


@power(
    "m4451a4",
    level=8,
    usage=AT_WILL,
    once_per_round=True,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.CHARM],
)
def m4451a4(c: Cast) -> None:
    """A curse on the nearest enemy, the same shape `m1120a2` already
    prints in `level_08/skirmishers_sa.py`, with the extra printed clause
    -- the cursed target is also slowed for a turn when hit."""
    near = min((f for f in c.enemies() if c.can_see(f)), key=c.distance, default=None)
    if near is not None:
        c.curse(on=near)
    me = c.me

    def rider(ev: Hit) -> None:
        if ev.attacker == me and c.cursed(on=ev.target):
            c.damage("1d6", on=ev.target, detail=c.ref)
            c.slowed(on=ev.target, until=When.EONT)

    if not any(e.label == c.ref for e in c.world.effects.of(me)):
        c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m4451a5",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4451a5(c: Cast) -> None:
    """An `r2` racial trait, not specific to this stat block: forced movement is
    one square short and a fall to prone can be shrugged off with a save.
    `_saves_off_prone` already carries the second half.

    The race is named by ref because naming it by word is a leak -- that word is
    `r2`'s printed name, and `leaks.py` reported this line."""
    c.resist_forced(on=c.me, until=When.ENCOUNTER)
    _saves_off_prone(c)


# ==========================================================================
# m5301
# ==========================================================================


@power(
    "m5301a0",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5301a0(c: Cast) -> None:
    """The damage bonus is a zone grant, gated on the target being
    bloodied. "Can hover" is a capability nothing in the engine enforces --
    no fly speed here is ever required to or it falls -- so granting it
    changes nothing detectable; it is still granted, to whoever already
    has a fly speed, now and as they arrive."""
    zone = c.aura(10, until=When.ENCOUNTER, label=c.ref)
    c.grants_in(
        zone, "damage", 4, side="ally", kind="power",
        when=lambda ctx: c.bloodied(on=ctx.get("target")),
    )

    def flies(who: int) -> bool:
        mv = c.world.get(who, Movement)
        return bool(mv and mv.modes.get("fly"))

    for ally in c.within(10, side="ally"):
        if flies(ally):
            c.hover(on=ally, until=When.ENCOUNTER)

    def entered(ev: ZoneEntered) -> None:
        if ev.zone == zone and flies(ev.actor):
            c.hover(on=ev.actor, until=When.ENCOUNTER)

    c.watch(ZoneEntered, entered, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} hover")


@power(
    "m5301a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("4d4", 6),
)
def m5301a1(c: Cast) -> None:
    def worsen(eff: Effect, v: int = 0) -> None:
        c.world.effects.end(eff, "worsened")
        c.prone(on=eff.owner)

    if c.strike():
        c.hit()
        c.condition(Condition.SLOWED, until=When.SAVE_ENDS, escalate=worsen)


@power(
    "m5301a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=12),
    damage=Damage("4d6", 2),
)
def m5301a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(3)


@power(
    "m5301a3",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=12),
    damage=Damage("4d8", 6, kind=LIMITED),
)
def m5301a3(c: Cast) -> None:
    """"Treats nonadjacent creatures as having concealment" is a penalty to
    the target's own attack rolls against anything not next to it, gated on
    the attack context's `target` -- not a blanket -2, and not `c.conceal`,
    which grants concealment *to* somebody rather than narrowing who they
    can see clearly."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    hold = c.penalty(
        "attack", 2, on=victim, until=When.SAVE_ENDS,
        when=lambda ctx, v=victim: distance_between(c.world, v, ctx.get("target")) > 1,
    )
    if hold is not None:
        def worsen(eff: Effect, v: int = victim) -> None:
            c.world.effects.end(eff, "worsened")
            c.blinded(on=v, until=When.EONT)

        hold.escalate = worsen


@power(
    "m5301a4",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("4d6", 2),
)
def m5301a4(c: Cast) -> None:
    if c.first:
        for mate in c.in_squares(c.area(), side="ally"):
            c.slide(2, on=mate)
    if c.strike():
        c.hit()
        c.slide(4)
        c.prone()


@power(
    "m5301a5",
    level=8,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m5301a5(c: Cast) -> None:
    c.shift(1)
    c.move(5, at="fly")


# ==========================================================================
# m5326
# ==========================================================================


@power(
    "m5326a0",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5326a0(c: Cast) -> None:
    c.bonus(
        "damage", 0, dice="1d6", on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: c.bloodied(on=ctx.get("target")),
    )


@power(
    "m5326a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d6", 5),
)
def m5326a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5)


@power(
    "m5326a2",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=12),
    damage=Damage("2d6", 5, dtype=DamageType.PSYCHIC, kind=LIMITED),
    requires=_has_bell,
    requires_text="the m5326 must be holding a bell",
    dropped=("Target.condition",),
)
def m5326a2(c: Cast) -> None:
    """"One creature able to take actions" is asked of the board, not the
    header; `_restricted_to` aims at one that qualifies in reach rather than
    throwing the row away. `Target.condition` is the gap: being able to act is
    the absence of the conditions that take a turn away.

    **The marker was missing and only the docstring carried the claim.** A gap
    argued in prose and declared nowhere is invisible to `blocked.py` and
    `todo.py` both -- it cannot be counted, ranked, or go red the day the
    symbol lands. Found when `Target.kind` was split and this row turned up
    naming a symbol it did not hold.
    """
    victim = _restricted_to(c, 10, lambda f: can_act(c.world, f))
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)
    c.slide(3, on=victim)
    rows = c.borrowed_rows(victim, at_will=True, melee=True) or c.borrowed_rows(
        victim, at_will=True, melee=False
    )
    mate = min(
        (a for a in allies(c.world, victim) if a != victim),
        key=lambda a: distance_between(c.world, victim, a), default=None,
    )
    if rows and mate is not None:
        c.use_power(rows[0], who=victim, on=mate)


@power(
    "m5326a3",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(3, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.CHARM, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=12),
    damage=Damage("2d6", 5, dtype=DamageType.PSYCHIC, kind=LIMITED),
    requires=_has_bell,
    requires_text="the m5326 must be holding a bell",
)
def m5326a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.pull(2, anchor=c.origin)
    if c.first:
        for mate in c.in_squares(c.area(), side="ally"):
            c.shift(1, who=mate)
            c.save(on=mate)


@power(
    "m5326a4",
    level=8,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(3),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=12),
    damage=Damage("2d6", 5, dtype=DamageType.PSYCHIC),
    requires=_has_bell,
    requires_text="the m5326 must be holding a bell",
)
def m5326a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.penalty(WILL, 2, until=When.EONT)


# ==========================================================================
# m5372
# ==========================================================================


@power(
    "m5372a0",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5372a0(c: Cast) -> None:
    for defence in ALL_DEFENCES:
        c.bonus(
            defence, 2, on=c.me, until=When.ENCOUNTER,
            when=lambda ctx: c.marked(on=c.me, by=ctx.get("attacker")),
        )


@power(
    "m5372a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("4d6", 3),
)
def m5372a1(c: Cast) -> None:
    """The card's own cross-reference, "it can use x_m5925a1 against the
    grabbed creature only", names a different stat block's power and is out
    of scope -- read as "it", not acted on."""
    if c.strike():
        c.hit()
        c.grab()


@power(
    "m5372a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(2),
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=12),
    damage=Damage("4d6", 5, dtype=DamageType.PSYCHIC),
)
def m5372a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(1)


@power(
    "m5372a3",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(3),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=12),
)
def m5372a3(c: Cast) -> None:
    if not c.strike():
        return

    def worsen(eff: Effect) -> None:
        grabbed = c.grabbing(of=c.me)
        if grabbed:
            c.flat(c.roll("2d6"), dtype=DamageType.PSYCHIC, on=grabbed[0])

    c.condition(Condition.DOMINATED, until=When.SAVE_ENDS, escalate=worsen)


@power(
    "m5372a4",
    level=8,
    usage=AT_WILL,
    once_per_round=True,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=12),
    damage=Damage("1d10", 5, dtype=DamageType.PSYCHIC),
    requires=lambda world, eid: bool(world.relations.targets(Relation.GRABBED_BY, eid)),
    requires_text="the m5372 must have a creature grabbed",
    dropped=("Target.relation",),
)
def m5372a4(c: Cast) -> None:
    grabbed = c.grabbing(of=c.me)
    victim = c.target if c.target in grabbed else next(iter(grabbed), None)
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)
    standing = _ongoing_amount(c.world, victim, DamageType.PSYCHIC)
    c.condition(
        Condition.DAZED, on=victim, until=When.SAVE_ENDS,
        ongoing=((standing + 5) if standing else 5, DamageType.PSYCHIC),
    )


@power(
    "m5372a5",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=ActionType.IMMEDIATE_REACTION,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.FORCE],
    attack=Attack(vs=FORT, printed=12),
    trigger="it is hit by a melee attack",
    on=Trigger(Hit, when=both(targets_me, by_melee), text="it is hit by a melee attack"),
)
def m5372a5(c: Cast) -> None:
    me = c.me

    def recharges(ev: Hit) -> None:
        if ev.attacker == me and ev.power == "m5372a4":
            c.restore_use(c.ref, on=me)

    c.watch(Hit, recharges, until=When.ENCOUNTER, on=me, label=f"{c.ref} recharge")
    if c.strike():
        c.push(3)
        c.penalty("attack", 2, until=When.EONT)


# ==========================================================================
# m5540
# ==========================================================================


@power(
    "m5540a0",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5540a0(c: Cast) -> None:
    zone = c.aura(5, until=When.ENCOUNTER, label=c.ref)
    me = c.me

    def sped(ev: TurnStart) -> None:
        if ev.ghost or ev.actor not in c.world.zones.occupants(zone):
            return
        if c.is_kind("undead", on=ev.actor) or team(c.world, ev.actor) is team(c.world, me):
            c.bonus("speed", 1, on=ev.actor, until=When.SONT)

    def surged(ev: SurgeSpent) -> None:
        if ev.actor in c.world.zones.occupants(zone) and team(c.world, ev.actor) is not team(
            c.world, me
        ):
            c.slowed(on=ev.actor, until=When.EONT)

    c.watch(TurnStart, sped, until=When.ENCOUNTER, on=me, label=f"{c.ref} speed")
    c.watch(SurgeSpent, surged, until=When.ENCOUNTER, on=me, label=f"{c.ref} surge")


@power(
    "m5540a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d6", 9),
)
def m5540a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5540a2",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.ZONE],
    attack=Attack(vs=REF, printed=12),
)
def m5540a2(c: Cast) -> None:
    if c.first:
        _rearms_when_bloodied(c)
    if c.strike():
        c.slide(2)
        c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS)


@power(
    "m5540a3",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(3, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d6", 0, kind=LIMITED),
    requires=lambda world, eid: bool(world.get(eid, Health)) and world.get(eid, Health).hp
    <= world.get(eid, Health).max_hp // 2,
    requires_text="the m5540 must be bloodied",
)
def m5540a3(c: Cast) -> None:
    if c.first:
        c.flat(10, on=c.me)
        c.forbid("m5540a4", on=c.me, until=When.ENCOUNTER)
    if c.strike():
        c.hit()
        c.damage("3d6", dtype=DamageType.FIRE)
        c.ongoing(5, DamageType.FIRE)


@power(
    "m5540a4",
    level=8,
    usage=AT_WILL,
    once_per_round=True,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=11),
)
def m5540a4(c: Cast) -> None:
    if c.strike():
        c.grants_advantage(until=When.SONT)


# ==========================================================================
# m5554
# ==========================================================================


@power(
    "m5554a0",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5554a0(c: Cast) -> None:
    zone = c.aura(5, until=When.ENCOUNTER, label=c.ref)
    c.grants_in(zone, "attack", -2, side="enemy", kind="untyped")
    c.grants_in(zone, "damage", 2, side="enemy", kind="untyped")
    c.grants_in(zone, "attack", 2, side="ally", kind="power")
    c.grants_in(zone, "damage", 2, side="ally", kind="power")


@power(
    "m5554a1",
    level=8,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5554a1(c: Cast) -> None:
    """A second initiative slot, the shape `level_10/soldiers.py`'s
    `m192a0` already uses. The immediate-action half is noted rather than
    written: `Encounter` already caps at one a round and one opportunity
    action per other creature's turn, and nothing here raises either."""
    init = c.world.get(c.me, Initiative)
    if init is not None:
        c.extra_turn(init.rolled + 10)
    c.note(f"{c.ref}: it may take two immediate actions a round, one between turns")


@power(
    "m5554a2",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5554a2(c: Cast) -> None:
    me = c.me

    def cleared(ev: TurnEnd) -> None:
        if ev.actor != me:
            return
        c.cure(Condition.DAZED, Condition.STUNNED, on=me)
        for eff in list(c.world.effects.of(me)):
            if Keyword.CHARM in keywords_of(eff.label):
                c.world.effects.end(eff, "shaken off")

    c.watch(TurnEnd, cleared, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m5554a3",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d8", 7),
)
def m5554a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m5554a4",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(5),
    target=ONE_CREATURE,
)
def m5554a4(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    mate = min((a for a in allies(c.world, victim) if a != victim), key=c.distance, default=None)
    if mate is None:
        return
    c.no_provoke(on=victim, until=When.EOT)
    c.charge_at(mate, who=victim)


# ==========================================================================
# m5575
# ==========================================================================


@power(
    "m5575a0",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FEAR],
)
def m5575a0(c: Cast) -> None:
    """"Living creatures" is read as enemies, since this creature's own
    side is undead; a mixed-undead board is out of scope."""
    zone = c.aura(5, until=When.ENCOUNTER, label=c.ref)
    c.grants_in(zone, "attack", -2, side="enemy", kind="untyped")


@power(
    "m5575a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d6", 5),
)
def m5575a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.grab()


_M5575A2_DOWN = (Condition.IMMOBILIZED, Condition.STUNNED, Condition.UNCONSCIOUS)


def _adjacent_and_down(world: World, eid: int) -> bool:
    return any(
        is_(world, f, cond) for f in enemies(world, eid) if adjacent(world, eid, f)
        for cond in _M5575A2_DOWN
    )


@power(
    "m5575a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("3d8", 5),
    requires=_adjacent_and_down,
    requires_text="targets an adjacent immobilized, stunned or unconscious creature",
    dropped=("Target.condition",),
)
def m5575a2(c: Cast) -> None:
    victim = _restricted_to(c, 1, lambda f: any(c.is_(cond, on=f) for cond in _M5575A2_DOWN))
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)
    c.dazed(until=When.SAVE_ENDS, on=victim)


@power(
    "m5575a3",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR, Keyword.THUNDER],
    attack=Attack(vs=WILL, printed=10),
    damage=Damage("4d6", 4, dtype=DamageType.THUNDER, kind=LIMITED),
)
def m5575a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(3)
        c.penalty("all defenses", 2, until=When.SAVE_ENDS)


@power(
    "m5575a4",
    level=8,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=Melee(1),
    target=NO_TARGET,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d8", 5),
    trigger="a creature it is grabbing attempts to escape",
    on=Trigger(
        __import__("combat_engine.engine.events", fromlist=["Escaped"]).Escaped,
        _grabbed_tries_to_escape,
        "a creature it is grabbing attempts to escape",
    ),
)
def m5575a4(c: Cast) -> None:
    victim = c.trigger.actor  # type: ignore[union-attr]
    if c.strike(on=victim):
        c.hit(on=victim)


# ==========================================================================
# m5583
# ==========================================================================


@power(
    "m5583a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("3d4", 3),
)
def m5583a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5583a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=12),
    damage=Damage("2d8", 3, dtype=DamageType.PSYCHIC),
)
def m5583a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(3)


@power(
    "m5583a2",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_CREATURE,
    attack=Attack(vs=REF, printed=10),
    damage=Damage("5d6", 3, kind=LIMITED),
)
def m5583a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized(until=When.EONT)


@power(
    "m5583a3",
    level=8,
    usage=AT_WILL,
    action=MINOR,
    reach=CloseBlast(2),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.HEALING],
    attack=Attack(vs=WILL, printed=13),
)
def m5583a3(c: Cast) -> None:
    """The card prints a name where every other row says "it" -- the
    compendium's own extraction missed one. Read as `m5583`, not the word;
    see the report. Mechanically identical to `m5582a5` in
    `level_08/soldiers_sa.py`: a forced swing with no choice this engine
    asks, and a mercy clause for the creature on the receiving end that
    hands a decision to a controlled creature nothing here asks either."""
    victim = c.target
    if victim is None or not c.strike(on=victim):
        return
    # "A creature of its choice" is still a creature the *victim* can hit: the
    # swing is a basic attack and nothing downstream of an explicit target
    # measures its reach, so the first enemy by entity id was swinging a
    # melee-1 basic at nine squares. Nearest inside the victim's own reach.
    span = _swing_reach(c, victim)
    foe = min(
        (f for f in c.enemies()
         if f != victim and distance_between(c.world, victim, f) <= span),
        key=lambda f: (distance_between(c.world, victim, f), f),
        default=None,
    )
    if foe is None:
        return
    landed = c.basic(on=foe, who=victim)
    if landed:
        c.temp_hp(10, on=victim)


@power(
    "m5583a4",
    level=8,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=Melee(1),
    target=NO_TARGET,
    trigger="a creature adjacent to it makes an opportunity attack against it",
    on=Trigger(
        AttackDeclared, when=both(targets_me, by_opportunity),
        text="a creature adjacent to it makes an opportunity attack against it",
    ),
)
def m5583a4(c: Cast) -> None:
    foe = getattr(c.trigger, "attacker", None)
    if foe is not None:
        c.use_power("m5583a0", on=foe, spend=False)


# ==========================================================================
# m5592
# ==========================================================================


@power(
    "m5592a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d8", 6),
)
def m5592a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m5592a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d6", 8),
)
def m5592a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5592a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=11),
)
def m5592a2(c: Cast) -> None:
    """"Non-deafened enemies" skips the deafened ones rather than
    redirecting -- a multi-target burst simply does not touch them, which
    is not the single-target "wrong creature" gap `_restricted_to` answers."""
    if c.is_(Condition.DEAFENED, on=c.target):
        return
    if c.strike():
        c.dazed(until=When.EONT)


@power(
    "m5592a3",
    level=8,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(5),
    target=EACH_ALLY,
)
def m5592a3(c: Cast) -> None:
    if c.is_(Condition.DEAFENED, on=c.target):
        return
    c.bonus("attack", 1, until=When.EONT)
    c.bonus("damage", 2, until=When.EONT)


@power(
    "m5592a4",
    level=8,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(5),
    target=EACH_ALLY,
)
def m5592a4(c: Cast) -> None:
    if c.is_(Condition.DEAFENED, on=c.target):
        return
    c.grant_action("shift", FREE, squares_=2)


@power(
    "m5592a5",
    level=8,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(5),
    target=EACH_ALLY,
)
def m5592a5(c: Cast) -> None:
    if c.is_(Condition.DEAFENED, on=c.target):
        return
    c.save()


# ==========================================================================
# m5617
# ==========================================================================


@power(
    "m5617a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d8", 7, dtype=DamageType.COLD),
)
def m5617a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5617a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=UpTo(2),
    keywords=[Keyword.COLD, Keyword.IMPLEMENT, Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d6", 5, dtype=DamageType.COLD),
)
def m5617a1(c: Cast) -> None:
    if not c.strike():
        return
    c.damage("2d6", 5, dtypes=(DamageType.COLD, DamageType.NECROTIC))
    c.slowed(until=When.EONT)


@power(
    "m5617a2",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=[Keyword.COLD, Keyword.IMPLEMENT],
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("4d6", 4, dtype=DamageType.COLD, kind=LIMITED),
)
def m5617a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.RESTRAINED, until=When.EONT)


@power(
    "m5617a3",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.COLD, Keyword.IMPLEMENT],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("4d6", 4, dtype=DamageType.COLD, kind=LIMITED, half_on_miss=True),
)
def m5617a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(3)
        c.prone()
    else:
        c.hit(half=True)
        c.slide(1)


# ==========================================================================
# m5678
# ==========================================================================


@power(
    "m5678a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d8", 7),
)
def m5678a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5678a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=11),
    damage=Damage("2d6", 4, dtype=DamageType.PSYCHIC),
)
def m5678a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.blinded(until=When.EONT)


@power(
    "m5678a2",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.FIRE, Keyword.IMPLEMENT],
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("2d6", 4, dtype=DamageType.FIRE, kind=LIMITED),
)
def m5678a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.FIRE)


@power(
    "m5678a3",
    level=8,
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(3),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d8", 3),
)
def m5678a3(c: Cast) -> None:
    """"Ongoing poison and a -2 penalty to attack rolls, save ends both" is
    one hold, not two -- the shape `level_06/brutes.py`'s `m881a1` already
    prints for the identical sentence."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    from combat_engine.engine import Mod

    c.world.effects.apply(
        victim, c.me, When.SAVE_ENDS, label=f"{c.ref} venom",
        ongoing=(5, DamageType.POISON),
        mods=[(victim, Mod(what="attack", value=-2, kind="untyped", label=c.ref))],
    )


@power(
    "m5678a4",
    level=8,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m5678a4(c: Cast) -> None:
    c.flat(5, on=c.me)
    choice = c.choose(["attack", "defenses", "shift"], "which effect")
    if choice == "attack":
        c.bonus("attack", 4, on=c.me, once=True, until=When.ENCOUNTER)
    elif choice == "defenses":
        for defence in ALL_DEFENCES:
            c.bonus(defence, 2, on=c.me, until=When.EONT)
    elif choice == "shift":
        c.shift(c.speed_of(c.me))


@power(
    "m5678a5",
    level=8,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.FIRE, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d8", 5, dtype=DamageType.FIRE, kind=LIMITED),
    trigger="a creature hits it with a melee attack",
    on=Trigger(Hit, when=both(targets_me, by_melee), text="a creature hits it with a melee attack"),
)
def m5678a5(c: Cast) -> None:
    foe = getattr(c.trigger, "attacker", None)
    if foe is not None and c.strike(on=foe):
        c.hit(on=foe)
        c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS, on=foe)
    c.shift(2)


# ==========================================================================
# m5757
# ==========================================================================


@power(
    "m5757a0",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5757a0(c: Cast) -> None:
    zone = c.aura(1, until=When.ENCOUNTER, label=c.ref)
    live: dict[int, Effect] = {}

    def apply_vuln(who: int) -> None:
        hold = c.vulnerable(5, DamageType.COLD, on=who, until=When.ENCOUNTER)
        if hold is not None:
            live[who] = hold

    for foe in c.within(1, side="enemy"):
        apply_vuln(foe)

    def entered(ev: ZoneEntered) -> None:
        if ev.zone == zone and ev.actor not in live and team(c.world, ev.actor) is not team(
            c.world, c.me
        ):
            apply_vuln(ev.actor)

    def exited(ev: ZoneExited) -> None:
        if ev.zone == zone and ev.actor in live:
            c.world.effects.end(live.pop(ev.actor), "left the aura")

    c.watch(ZoneEntered, entered, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} in")
    c.watch(ZoneExited, exited, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} out")


@power(
    "m5757a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("3d6", 3, dtype=DamageType.COLD),
)
def m5757a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(2)


@power(
    "m5757a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD, Keyword.IMPLEMENT, Keyword.RADIANT],
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("3d6", 6, dtype=DamageType.COLD),
)
def m5757a2(c: Cast) -> None:
    if not c.strike():
        return
    c.damage("3d6", 6, dtypes=(DamageType.COLD, DamageType.RADIANT))
    _no_sight_past(c, 3)


@power(
    "m5757a3",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_OTHER,
    keywords=[Keyword.COLD, Keyword.IMPLEMENT, Keyword.ZONE],
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("3d8", 5, dtype=DamageType.COLD, kind=LIMITED, half_on_miss=True),
)
def m5757a3(c: Cast) -> None:
    if c.first:
        c.zone(c.area(), difficult="ice walk", until=When.SUSTAIN, sustain=MINOR, label=c.ref)
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)


# ==========================================================================
# m5809
# ==========================================================================


@power(
    "m5809a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("", 6, kind=MINION),
)
def m5809a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5809a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD, Keyword.IMPLEMENT],
    attack=Attack(vs=REF, printed=11),
)
def m5809a1(c: Cast) -> None:
    if not c.strike():
        return
    c.prone()
    if c.crit:
        c.flat(6, dtype=DamageType.COLD)
        c.condition(Condition.IMMOBILIZED, until=When.EONT)


# ==========================================================================
# m5960
# ==========================================================================


@power(
    "m5960a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=11),
    damage=Damage("2d8", 7),
    requires=lambda world, eid: not world.relations.targets(Relation.GRABBED_BY, eid),
    requires_text="the m5960 must not have a creature grabbed",
)
def m5960a0(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    if c.is_(Condition.DAZED, on=victim) or c.is_(Condition.STUNNED, on=victim):
        def force(ev: AttackRolled) -> None:
            if ev.attacker == c.me and ev.target == victim:
                c.autohit(ev)

        c.watch(
            AttackRolled, force, until=When.EOT, on=c.me, once=True,
            window=Window.BEFORE, label=c.ref,
        )
    if c.strike():
        c.hit()
        c.grab()


@power(
    "m5960a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("3d10", 4),
    requires=lambda world, eid: bool(world.relations.targets(Relation.GRABBED_BY, eid)),
    requires_text="the m5960 must have a creature grabbed",
    dropped=("Target.relation",),
)
def m5960a1(c: Cast) -> None:
    """The thrall clause is caught inside the `Dropped` window
    `level_02/soldiers_sa.py`'s `m3533a3` already opens for a revival:
    `c.reanimate` stands it back up, at its bloodied value rather than a
    flat number, and `Condition.DOMINATED` is the control already in the
    tree -- no new mechanism for being controlled was needed. It falls for
    good when the m5960 does, forced through the ordinary damage pipeline
    rather than by hand-setting hit points."""
    grabbed = c.grabbing(of=c.me)
    victim = c.target if c.target in grabbed else next(iter(grabbed), None)
    if victim is None or not c.strike(on=victim):
        return
    me = c.me

    def rise(ev: Dropped) -> None:
        if ev.actor != victim or ev.source != me:
            return
        hp = c.world.get(victim, Health)
        half = hp.max_hp // 2 if hp is not None else 1
        c.reanimate(on=victim, hp=half)
        c.condition(Condition.DOMINATED, on=victim, until=When.ENCOUNTER)

        def thrall_falls(end_ev: Dropped) -> None:
            if end_ev.actor == me:
                c.flat(9999, on=victim)

        c.watch(Dropped, thrall_falls, until=When.ENCOUNTER, on=me, label=f"{c.ref} thrall")

    c.watch(Dropped, rise, until=When.ENCOUNTER, on=me, once=True, label=f"{c.ref} revive")
    c.hit(on=victim)
    held = c.condition(Condition.DAZED, on=victim, until=When.ENCOUNTER)
    if held is not None:
        def freed(ev: RelationCleared) -> None:
            if ev.kind_ is Relation.GRABBED_BY and ev.target == victim and ev.source == me:
                c.world.effects.end(held, "no longer grabbed")

        c.watch(RelationCleared, freed, until=When.ENCOUNTER, on=me, label=f"{c.ref} daze watch")


@power(
    "m5960a2",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.CHARM, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=11),
    damage=Damage("2d6", 5, dtype=DamageType.PSYCHIC, kind=LIMITED, half_on_miss=True),
)
def m5960a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        victim = c.target
        mate = min(
            (a for a in allies(c.world, victim) if a != victim),
            key=lambda a: distance_between(c.world, victim, a), default=None,
        )
        if mate is not None:
            c.basic(who=victim, on=mate)
    else:
        c.hit(half=True)


# ==========================================================================
# m5972
# ==========================================================================


@power(
    "m5972a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d8", 6),
)
def m5972a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        if c.may("slide the target 1 square"):
            c.slide(1)


@power(
    "m5972a1",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("2d8", 7, kind=LIMITED),
)
def m5972a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(6)
        c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS)
    else:
        c.slide(3)


@power(
    "m5972a2",
    level=8,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m5972a2(c: Cast) -> None:
    c.teleport(5)


@power(
    "m5972a3",
    level=8,
    usage=AT_WILL,
    once_per_round=True,
    action=MINOR,
    reach=CloseBlast(3),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=11),
)
def m5972a3(c: Cast) -> None:
    victim = c.target
    if victim is None or not c.strike(on=victim):
        return
    mate = next(
        (a for a in allies(c.world, victim) if a != victim and c.adjacent_to(a, victim)), None
    )
    if mate is not None:
        c.basic(who=victim, on=mate)


@power(
    "m5972a4",
    level=8,
    usage=ENCOUNTER,
    uses=4,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.draw_card()",),
)
def m5972a4(c: Cast) -> None:
    """Drawing a card and using "the power associated with it" names a deck
    this engine has no model for and no refs for the powers it would hold.
    Nothing here is sayable yet."""


# ==========================================================================
# m5977
# ==========================================================================


@power(
    "m5977a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d8", 7),
)
def m5977a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5977a1",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d6", 5, kind=LIMITED),
)
def m5977a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)


@power(
    "m5977a2",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=11),
)
def m5977a2(c: Cast) -> None:
    if c.strike():
        c.stunned(until=When.EONT)


@power(
    "m5977a3",
    level=8,
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_ALLY,
    keywords=[Keyword.HEALING],
)
def m5977a3(c: Cast) -> None:
    victim = c.target
    if victim is not None and c.spend_surge(on=victim):
        c.heal(c.surge_value(of=victim), on=victim)


# ==========================================================================
# m5985
# ==========================================================================


@power(
    "m5985a0",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5985a0(c: Cast) -> None:
    me = c.me

    def hurt(ev: DamageApplied) -> None:
        if ev.target == me and DamageType.RADIANT in ev.types():
            c.forbid("m5985a6", on=me, until=When.EONT)

    c.watch(DamageApplied, hurt, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m5985a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=UpTo(2),
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d8", 6, dtype=DamageType.NECROTIC),
)
def m5985a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5985a2",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING],
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("2d12", 10),
    dropped=("Target.grants_ca",),
)
def m5985a2(c: Cast) -> None:
    if c.first:
        me = c.me

        def recharges(ev: Bloodied) -> None:
            if distance_between(c.world, me, ev.actor) <= 1:
                c.restore_use(c.ref, on=me)

        c.watch(
            Bloodied, recharges, until=When.ENCOUNTER, on=me, once=True,
            label=f"{c.ref} recharge",
        )
    victim = _restricted_to(c, 2, lambda f: has_combat_advantage(c.world, c.me, f))
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)
    c.spend_surge(on=victim)
    c.weakened(until=When.SAVE_ENDS, on=victim)
    c.heal(42, on=c.me)


@power(
    "m5985a3",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=11),
    damage=Damage("3d8", 3, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m5985a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS)


@power(
    "m5985a4",
    level=8,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ILLUSION],
    out_of_combat=True,
)
def m5985a4(c: Cast) -> None:
    """Appearance only, disguised as a living Medium humanoid until it
    attacks or is hit -- no combat mechanic rides on the disguise itself,
    the same shape `level_06/controllers_sa.py`'s `m1985a2` already prints."""


@power(
    "m5985a5",
    level=8,
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=11),
)
def m5985a5(c: Cast) -> None:
    if c.strike():
        c.condition(Condition.DOMINATED, until=When.SAVE_ENDS)


@power(
    "m5985a6",
    level=8,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POLYMORPH],
    dropped=("c.insubstantial(except_=)",),
)
def m5985a6(c: Cast) -> None:
    """`c.insubstantial` halves every damage type; the printed exception
    for force has no lever yet -- the same gap `level_07/soldiers_sa.py`'s
    `m5791a1` already marks. Ends on its own next attack or on either
    condition landing on it, the shape `_vanish_until_struck` already uses
    in `level_04/lurkers_sa.py` for an ending with more than one close."""
    me = c.me
    shape = c.insubstantial(on=me, until=When.ENCOUNTER)
    if shape is None:
        return
    granted = (
        c.mode("fly", 8, until=When.ENCOUNTER, on=me),
        c.phasing(on=me, until=When.ENCOUNTER),
    )
    for held in granted:
        if held is not None:
            shape.on_end.append(lambda h=held: c.world.effects.end(h, "the form is over"))

    def swung(ev: AttackRolled) -> None:
        if ev.attacker == me:
            c.world.effects.end(shape, "it attacked")

    def worsened(ev: ConditionApplied) -> None:
        if ev.target == me and ev.condition in (Condition.STUNNED, Condition.UNCONSCIOUS):
            c.world.effects.end(shape, "it can no longer hold the shape")

    seen = c.watch(
        AttackRolled, swung, until=When.ENCOUNTER, on=me, once=True, label=f"{c.ref} swung"
    )
    broke = c.watch(
        ConditionApplied, worsened, until=When.ENCOUNTER, on=me, label=f"{c.ref} broken"
    )
    shape.on_end.append(lambda s=seen: c.world.effects.end(s, "no longer held"))
    shape.on_end.append(lambda s=broke: c.world.effects.end(s, "no longer held"))


# ==========================================================================
# m5988
# ==========================================================================


@power(
    "m5988a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=UpTo(2),
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d12", 3),
)
def m5988a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        if c.may("push the target 1 square") and c.size_of(on=c.target) in NO_BIGGER_THAN_MEDIUM:
            c.push(1)


@power(
    "m5988a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING, Keyword.PSYCHIC],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("3d10", 6, dtype=DamageType.PSYCHIC),
    requires=lambda world, eid: any(
        is_(world, f, Condition.UNCONSCIOUS) for f in enemies(world, eid) if adjacent(world, eid, f)
    ),
    requires_text="targets an adjacent unconscious creature",
    dropped=("Target.condition",),
)
def m5988a1(c: Cast) -> None:
    victim = _restricted_to(c, 1, lambda f: c.is_(Condition.UNCONSCIOUS, on=f))
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)
    c.heal(10, on=c.me)


@power(
    "m5988a2",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_OTHER,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=11),
)
def m5988a2(c: Cast) -> None:
    if c.first:
        _rearms_when_bloodied(c)

    def worsen(eff: Effect) -> None:
        c.world.effects.end(eff, "worsened")
        c.unconscious(until=When.SAVE_ENDS, on=eff.owner)

    if c.strike():
        c.condition(Condition.DAZED, until=When.SAVE_ENDS, escalate=worsen)


@power(
    "m5988a3",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
)
def m5988a3(c: Cast) -> None:
    """Sustain Standard is a `sustain_cost` on the effect, and neither
    `c.insubstantial` nor `c.mode` takes one -- the shape `m346a4` in
    `level_08/controllers.py` already applies directly for this reason."""
    shape = c.world.effects.apply(
        c.me, c.me, When.SUSTAIN, label=c.ref,
        conditions=[Condition.INSUBSTANTIAL], sustain_cost=STANDARD,
    )
    held = c.mode("fly", 8, until=When.ENCOUNTER, on=c.me)
    if held is not None:
        shape.on_end.append(lambda h=held: c.world.effects.end(h, "the form is over"))


@power(
    "m5988a4",
    level=8,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
    out_of_combat=True,
)
def m5988a4(c: Cast) -> None:
    """A disguise and nothing else; the way through it is an Insight check
    the engine has no skill roll for on this board."""


# ==========================================================================
# m5994
# ==========================================================================


@power(
    "m5994a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("3d4", 9),
)
def m5994a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5994a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("2d6", 5),
)
def m5994a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(3)
    else:
        c.push(1)


@power(
    "m5994a2",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    attack=Attack(vs=REF, printed=11),
)
def m5994a2(c: Cast) -> None:
    if c.strike():
        c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS, ongoing=(10, DamageType.UNTYPED))


@power(
    "m5994a3",
    level=8,
    usage=ENCOUNTER,
    action=MINOR,
    reach=AreaBurst(2, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR, Keyword.IMPLEMENT],
    attack=Attack(vs=WILL, printed=11),
)
def m5994a3(c: Cast) -> None:
    if c.strike():
        c.push(3)
        c.penalty("attack", 2, until=When.EONT)


# ==========================================================================
# m6026
# ==========================================================================


@power(
    "m6026a0",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6026a0(c: Cast) -> None:
    zone = c.aura(3, until=When.ENCOUNTER, label=c.ref)
    c.grants_in(zone, WILL, 2, side="ally", kind="power")
    c.grants_in(zone, "save", 2, side="ally", kind="power")


@power(
    "m6026a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d8", 7),
)
def m6026a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        if c.may("slide the target 1 square"):
            c.slide(1)


@power(
    "m6026a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.IMPLEMENT],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("2d8", 2, dtype=DamageType.FIRE),
)
def m6026a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.EONT)


@power(
    "m6026a3",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_OTHER,
    keywords=[Keyword.FEAR, Keyword.IMPLEMENT, Keyword.NECROTIC],
    attack=Attack(vs=WILL, printed=11),
    damage=Damage("2d8", 5, dtype=DamageType.NECROTIC, kind=LIMITED, half_on_miss=True),
    dropped=("c.cannot_approach()",),
)
def m6026a3(c: Cast) -> None:
    """"Cannot move closer to it willingly" has no method: `c.immovable` is
    about being shoved and `c.cannot_shift` about shifting, and neither
    forbids walking towards somebody -- the same gap `warlock/level_7_b.py`'s
    `p1872` already names."""
    if c.strike():
        c.hit()
        c.push(3)
    else:
        c.hit(half=True)
        c.push(2)


@power(
    "m6026a4",
    level=8,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="an enemy hits it with an attack",
    on=Trigger(Hit, when=targets_me, text="an enemy hits it with an attack"),
)
def m6026a4(c: Cast) -> None:
    """The bonus's clock is each ally's own next turn rather than the
    triggering enemy's -- `c.bonus`'s owner and clock are the same
    parameter, and there is no second one to split them with."""
    foe = getattr(c.trigger, "attacker", None)
    if foe is None:
        return
    for ally in c.allies():
        c.bonus(
            "attack", 2, on=ally, kind="power", until=When.EONT,
            when=lambda ctx, f=foe: ctx.get("target") == f,
        )


# ==========================================================================
# m6075
# ==========================================================================


@power(
    "m6075a0",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PSYCHIC],
)
def m6075a0(c: Cast) -> None:
    zone = c.aura(10, until=When.ENCOUNTER, label=c.ref)
    for defence in ALL_DEFENCES:
        c.grants_in(zone, defence, -2, side="enemy", kind="untyped")


@power(
    "m6075a1",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.insubstantial(except_=)",),
)
def m6075a1(c: Cast) -> None:
    me = c.me
    shape: dict[str, Effect | None] = {"eff": c.insubstantial(on=me, until=When.ENCOUNTER)}

    def hurt(ev: DamageApplied) -> None:
        if ev.target != me or DamageType.RADIANT not in ev.types() or shape["eff"] is None:
            return
        c.world.effects.end(shape["eff"], "radiant burned the shape away")
        shape["eff"] = None

        def restore(ev2: TurnEnd) -> None:
            if ev2.actor == me:
                shape["eff"] = c.insubstantial(on=me, until=When.ENCOUNTER)

        c.watch(TurnEnd, restore, until=When.ENCOUNTER, on=me, once=True, label=f"{c.ref} reforms")

    c.watch(DamageApplied, hurt, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m6075a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.PSYCHIC],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("2d8", 5, dtype=DamageType.PSYCHIC),
)
def m6075a2(c: Cast) -> None:
    if not c.strike():
        return
    c.damage("2d8", 5, dtypes=(DamageType.NECROTIC, DamageType.PSYCHIC))
    _grief_stricken(c, c.target)


@power(
    "m6075a3",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=12),
    damage=Damage("2d8", 5, dtype=DamageType.PSYCHIC),
)
def m6075a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.penalty("attack", 2, until=When.SAVE_ENDS)


@power(
    "m6075a4",
    level=8,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=11),
    damage=Damage("2d8", 5, dtype=DamageType.PSYCHIC),
    trigger="it is bloodied",
    on=Trigger(Bloodied, about_me, "it is bloodied"),
)
def m6075a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        _grief_stricken(c, c.target)


# ==========================================================================
# m6233
# ==========================================================================


@power(
    "m6233a0",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6233a0(c: Cast) -> None:
    zone = c.aura(2, until=When.ENCOUNTER, label=c.ref)
    live: dict[int, Effect] = {}

    def grant(who: int) -> None:
        if who in live:
            return
        hold = c.conceal(
            on=who, until=When.ENCOUNTER,
            when=lambda ctx, w=who: not c.adjacent_to(ctx.get("attacker"), w),
        )
        if hold is not None:
            live[who] = hold

    for who in (c.me, *c.within(2, side="ally")):
        grant(who)

    def entered(ev: ZoneEntered) -> None:
        if ev.zone == zone and team(c.world, ev.actor) is team(c.world, c.me):
            grant(ev.actor)

    def exited(ev: ZoneExited) -> None:
        if ev.zone == zone and ev.actor in live:
            c.world.effects.end(live.pop(ev.actor), "left the aura")

    c.watch(ZoneEntered, entered, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} in")
    c.watch(ZoneExited, exited, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} out")


@power(
    "m6233a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("2d6", 9),
)
def m6233a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(2)
        c.prone()
    else:
        if c.may("push the target 1 square"):
            c.push(1)


@power(
    "m6233a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    attack=Attack(vs=REF, printed=11),
    damage=Damage("2d6", 4),
)
def m6233a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        if c.may("knock the target prone instead of sliding it"):
            c.prone()
        else:
            c.slide(3)


@power(
    "m6233a3",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.LIGHTNING, Keyword.THUNDER, Keyword.ZONE],
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("2d6", 5, dtype=DamageType.LIGHTNING, kind=LIMITED),
    dropped=("c.zone(obscures=)",),
)
def m6233a3(c: Cast) -> None:
    """"Lightly obscured to creatures outside it" is one-directional and
    `Zone.blocks_sight` is not -- it blinds both ways, which `c.zone`'s own
    caution already warns against reaching for here. The damage-at-turn-end
    half is sayable and written: `c.burns` bites on entering or starting a
    turn, not on ending one, so this is a `TurnEnd` watch hung on the zone's
    own effect the way `level_08/controllers.py`'s `m4989a3` already does."""
    if c.first:
        ring = c.zone(c.area(), until=When.SUSTAIN, sustain=MINOR, label=c.ref)
        held = dict(c.world.zones.all()).get(ring)
        if held is not None and held.effect is not None:
            me = c.me

            def tug(ev: TurnEnd) -> None:
                if ev.ghost or ev.actor not in c.world.zones.occupants(ring):
                    return
                if team(c.world, ev.actor) is not team(c.world, me):
                    c.flat(5, dtypes=(DamageType.LIGHTNING, DamageType.THUNDER), on=ev.actor)

            held.effect.subs.append(c.world.bus.on(TurnEnd, tug, owner=me))
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)


@power(
    "m6233a4",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m6233a4(c: Cast) -> None:
    if c.first:
        _rearms_when_bloodied(c)
    c.move(c.speed_of(c.me) + 2, at="fly")
    c.invisible(on=c.me, until=When.EONT)


# ==========================================================================
# m6640
# ==========================================================================


@power(
    "m6640a0",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6640a0(c: Cast) -> None:
    ring = c.aura(1, until=When.ENCOUNTER, label=c.ref)
    held = dict(c.world.zones.all()).get(ring)
    if held is None or held.effect is None:
        return
    me = c.me

    def tug(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor not in c.world.zones.occupants(ring):
            return
        if team(c.world, ev.actor) is not team(c.world, me):
            c.flat(5, on=ev.actor)

    held.effect.subs.append(c.world.bus.on(TurnEnd, tug, owner=me))


@power(
    "m6640a1",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6640a1(c: Cast) -> None:
    c.ignores_difficult(on=c.me, until=When.ENCOUNTER)


@power(
    "m6640a2",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.squeeze_through()",),
)
def m6640a2(c: Cast) -> None:
    """Squeezing through any opening sized for one of the creatures it
    comprises has no reader -- there is no verb for a size-gated opening on
    this board. The rest is sayable: sharing a space, and resisting only
    the melee or ranged half of forced movement, which `ForcedMove.power`
    carries enough to tell from a burst."""
    me = c.me
    c.shares_space(on=me, until=When.ENCOUNTER)

    def refuse(ev: ForcedMove) -> None:
        if ev.target != me:
            return
        p = get(ev.power) if ev.power else None
        kind = p.reach_of(0).kind if p is not None else ""
        if kind in ("melee", "ranged"):
            ev.cancel("the swarm cannot be shoved by that")

    c.watch(ForcedMove, refuse, until=When.ENCOUNTER, window=Window.BEFORE, on=me, label=c.ref)


@power(
    "m6640a3",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    attack=Attack(vs=REF, printed=11),
    damage=Damage("1d12", 6),
)
def m6640a3(c: Cast) -> None:
    """"Then shift into the space the target vacated" is read as an
    ordinary shift rather than a reservation of that exact square, since
    the vacated square is the one the engine's own chooser almost always
    offers first."""
    if c.strike():
        c.hit()
        if c.may("slide the target 1 square"):
            c.slide(1)
            if c.may("shift into the vacated square", who=c.me):
                c.shift(1)


@power(
    "m6640a4",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6640a4(c: Cast) -> None:
    for _ in range(2):
        c.use_power("m6640a3", spend=False, again=True)


@power(
    "m6640a5",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("2d6", 6, kind=LIMITED),
)
def m6640a5(c: Cast) -> None:
    """"Shifts up to its speed to any square in the burst" is read as an
    ordinary shift of that distance -- constraining the destination to the
    burst's own squares is a spatial nicety the engine's chooser does not
    need steering for here."""
    if c.strike():
        c.condition(Condition.SLOWED, until=When.SAVE_ENDS, ongoing=(5, DamageType.UNTYPED))
    if c.first:
        c.shift(c.speed_of(c.me))


@power(
    "m6640a6",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it takes damage from a close or area attack",
    on=Trigger(
        Hit,
        when=lambda world, me, ev: getattr(ev, "target", None) == me
        and (lambda p: p is not None and p.reach_of(getattr(ev, "branch", 0)).kind
             in ("close_burst", "close_blast", "area_burst"))(get(getattr(ev, "power", "") or "")),
        text="it takes damage from a close or area attack",
    ),
)
def m6640a6(c: Cast) -> None:
    if c.first:
        _rearms_when_bloodied(c)

    def bitten(who: int) -> None:
        if team(c.world, who) is team(c.world, c.me):
            return

        def worsen(eff: Effect) -> None:
            c.world.effects.end(eff, "worsened")
            c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS, on=who)

        c.condition(
            Condition.SLOWED, until=When.SAVE_ENDS, on=who,
            ongoing=(5, DamageType.UNTYPED), escalate=worsen,
        )

    zone = c.zone(spread(squares(c.world, c.me), 2), until=When.EONT, label=c.ref)

    def entered(ev: ZoneEntered) -> None:
        if ev.zone == zone:
            bitten(ev.actor)

    def started(ev: TurnStart) -> None:
        if not ev.ghost and ev.actor in c.world.zones.occupants(zone):
            bitten(ev.actor)

    c.watch(ZoneEntered, entered, until=When.EONT, on=c.me, label=f"{c.ref} enter")
    c.watch(TurnStart, started, until=When.EONT, on=c.me, label=f"{c.ref} start")
    for foe in c.world.zones.occupants(zone):
        bitten(foe)


# ==========================================================================
# m822
# ==========================================================================


@power(
    "m822a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d6", 5),
)
def m822a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.NECROTIC)


@power(
    "m822a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("1d6", 5, dtype=DamageType.NECROTIC),
)
def m822a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.weakened(until=When.SAVE_ENDS)


@power(
    "m822a2",
    level=8,
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=12),
    requires=lambda world, eid: any(
        has_combat_advantage(world, eid, f) for f in enemies(world, eid)
    ),
    requires_text="the m822 must have combat advantage against the target",
    dropped=("Target.grants_ca",),
)
def m822a2(c: Cast) -> None:
    victim = _restricted_to(c, 10, lambda f: has_combat_advantage(c.world, c.me, f))
    if victim is None or not c.strike(on=victim):
        return
    c.half_healing(on=victim, until=When.EONT)


def _has_ongoing_necrotic(world: World, eid: int) -> bool:
    return any(
        e.ongoing and DamageType.NECROTIC in (tuple(e.ongoing_types) or (e.ongoing[1],))
        for e in world.effects.of(eid)
    )


@power(
    "m822a3",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=12),
    requires=_has_ongoing_necrotic,
    requires_text="the m822 must see a creature taking ongoing necrotic damage within 5 squares",
    dropped=("Target.ongoing",),
)
def m822a3(c: Cast) -> None:
    victim = _restricted_to(c, 5, lambda f: _has_ongoing_necrotic(c.world, f))
    if victim is None or not c.strike(on=victim):
        return
    c.condition(Condition.IMMOBILIZED, until=When.EONT, on=victim)


@power(
    "m822a4",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ALLY,
    keywords=[Keyword.HEALING],
)
def m822a4(c: Cast) -> None:
    if not c.is_kind("undead", on=c.target):
        return
    c.heal(5)
    c.grant_action("shift", ActionType.IMMEDIATE_REACTION, squares_=3)


# ==========================================================================
# m952
# ==========================================================================


@power(
    "m952a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d8", 6, dtype=DamageType.PSYCHIC),
)
def m952a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m952a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(10),
    target=EACH_ALLY,
)
def m952a1(c: Cast) -> None:
    if c.may("make a basic attack", who=c.target):
        c.basic(who=c.target)


@power(
    "m952a2",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d8", 6, dtype=DamageType.PSYCHIC, kind=LIMITED),
    requires=_has_scimitar,
    requires_text="the m952 must be wielding a scimitar",
)
def m952a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        _forbid_everything(c, c.target, until=When.SAVE_ENDS)


@power(
    "m952a3",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=12),
    damage=Damage("2d8", 6, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m952a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)


# ==========================================================================
# m959
# ==========================================================================


@power(
    "m959a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d8", 4),
)
def m959a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m959a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m959a1(c: Cast) -> None:
    _twice(c, "m959a0")


@power(
    "m959a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("2d6", 4, dtype=DamageType.NECROTIC),
)
def m959a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.weakened(until=When.SAVE_ENDS)


@power(
    "m959a3",
    level=8,
    usage=AT_WILL,
    once_per_round=True,
    action=MINOR,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.ARCANE, Keyword.FORCE],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("1d8", 4, dtype=DamageType.FORCE),
)
def m959a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(2)


@power(
    "m959a4",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.ARCANE, Keyword.COLD],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("2d8", 4, dtype=DamageType.COLD, kind=LIMITED),
)
def m959a4(c: Cast) -> None:
    if c.first:
        zone = c.zone(c.area(), until=When.EONT, label=c.ref)
        c.burns(zone, 4, DamageType.COLD)
    if c.strike():
        c.hit()


@power(
    "m959a5",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.ARCANE, Keyword.FORCE, Keyword.ZONE],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d6", 4, dtype=DamageType.FORCE),
    dropped=("c.grant_action(move_zone)",),
)
def m959a5(c: Cast) -> None:
    """"The m959 is immune to this effect" is the `TurnStart` gate skipping
    its own actor. "As a move action, it can move this zone 4 squares" is a
    standing option on every future turn and not part of this power's own
    resolution -- there is no second ref to carry it and no recognised word
    for `c.grant_action` to offer it through, so it is marked rather than
    silently left out."""
    if c.first:
        me = c.me
        zone = c.zone(c.area(), until=When.ENCOUNTER, label=c.ref)

        def tick(ev: TurnStart) -> None:
            if ev.ghost or ev.actor == me:
                return
            if ev.actor not in c.world.zones.occupants(zone):
                return
            if c.strike(on=ev.actor):
                c.hit(on=ev.actor)
                c.prone(on=ev.actor)

        c.watch(TurnStart, tick, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m959a6",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.ILLUSION],
)
def m959a6(c: Cast) -> None:
    c.invisible(on=c.me, until=When.EONT)
    c.move(6, at="fly")


# ==========================================================================
# m960
# ==========================================================================


@power(
    "m960a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d8", 3),
)
def m960a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.EONT)


@power(
    "m960a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("1d8", 5, dtype=DamageType.COLD),
)
def m960a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.IMMOBILIZED, until=When.EONT)


@power(
    "m960a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD, Keyword.TELEPORTATION],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("1d8", 5, dtype=DamageType.COLD),
)
def m960a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.teleport(3, who=c.target)


@power(
    "m960a3",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.COLD],
    attack=Attack(vs=WILL, printed=11),
    damage=Damage("2d6", 3, dtype=DamageType.COLD, kind=LIMITED),
)
def m960a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.blinded(until=When.EONT)


@power(
    "m960a4",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m960a4(c: Cast) -> None:
    me = c.me

    def stung(ev: Hit) -> None:
        if ev.target == me and by_melee(c.world, me, ev):
            c.slowed(on=ev.attacker, until=When.EONT)

    c.watch(Hit, stung, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m960a5",
    level=8,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m960a5(c: Cast) -> None:
    """"Any square in sight" has no fixed distance; read as 10 squares,
    matching the sight range this engine offers elsewhere by default."""
    if not c.terrain("icy"):
        return
    c.teleport(10)
