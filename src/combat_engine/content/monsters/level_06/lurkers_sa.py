"""Monster abilities, level 6 lurkers, second wave.

Seventeen stat blocks, sixty-eight rows. `lurkers.py` does not exist at this
level -- this is the first pass. Five blocks print no abilities at all and
have nothing to decorate: m102, m2929, m405, m5008, m674.

Conventions, inherited from the level-1 to level-5 sweeps:

* numbers load from `game.db` -- the attack line is written exactly as
  printed and the damage line goes in the header as data;
* a **trait** costs no action, has no target, and arms the watches that
  hold it, whatever the compendium's column claims;
* a printed range band such as "5/10" takes the normal (first) number;
* a close burst or blast whose card names no target set takes **enemies**,
  except where it says "creatures in the burst" outright;
* `half_on_miss=True` is card data only -- a Miss line is also written as
  `else: c.hit(half=True)`.

Lurkers lean on concealment, invisibility and combat-advantage riders, and
this file leans hard on `level_02..05/lurkers_sa.py`: `_edge_damage`,
`_recharge_when_using`, `_triggering_enemy`, `_vanish_until_it_swings`,
`_blind_to_me`, `_cannot_see_me_in_reach`, `_is_bloodied`, `_crit_line`,
`_disliked_my_roll`/`_DISLIKED_ROLL` and `_ridden_by`.

One name leak in the raw text, written around rather than copied, per
report: m999a2's "Veserabs" is this creature's own species name. It is
never written; the immunity it describes is matched by this row's own ref
instead.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_01.brutes_sa import _crit_line
from combat_engine.content.monsters.level_02.lurkers_sa import (
    _edge_damage,
    _recharge_when_using,
    _triggering_enemy,
)
from combat_engine.content.monsters.level_02.skirmishers_sa import _melee_only
from combat_engine.content.monsters.level_02.soldiers_sa import _ref_of
from combat_engine.content.monsters.level_03.skirmishers import (
    _is_bloodied,
    _vanish_until_it_swings,
)
from combat_engine.content.monsters.level_04.lurkers_sa import _ridden_by
from combat_engine.content.monsters.level_05.lurkers_sa import (
    _DISLIKED_ROLL,
    _disliked_my_roll,
)
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
    Effect,
    Keyword,
    Melee,
    MeleeOrRanged,
    Mod,
    Ranged,
    Size,
    Target,
    UpTo,
    Usage,
    When,
    Window,
    World,
    power,
    spread,
)
from combat_engine.engine.events import (
    AdjacencyGained,
    AttackRolled,
    Bloodied,
    DamageRolled,
    Dropped,
    Hit,
    TurnStart,
)
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import adjacent, team
from combat_engine.engine.triggers import Trigger, about_me, both, targets_me

# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------


def _physical(ctx: dict[str, Any]) -> bool:
    """"On melee and ranged attacks" -- a burst or blast does not qualify.
    For `c.bonus(when=)`, which hands the gate a context dict."""
    from combat_engine.engine import get

    row = get(ctx.get("power") or "")
    return row is not None and row.reach.kind in ("melee", "ranged")


def _physical_hit(world: World, me: int, ev: Any) -> bool:
    """The same question, shaped for a declared `Trigger`, which hands its
    predicate `(world, me, ev)` rather than a context dict."""
    from combat_engine.engine import get

    row = get(getattr(ev, "power", "") or "")
    return row is not None and row.reach.kind in ("melee", "ranged")


def _enemy_ended_adjacent(world: World, me: int, ev: Any) -> bool:
    """"Ends its movement adjacent to it." -- the same event two levels down
    uses for "an enemy moves adjacent"."""
    actor = getattr(ev, "actor", None)
    if actor is None or actor == me or team(world, actor) is team(world, me):
        return False
    return adjacent(world, actor, me)


def _splash_adjacent(c: Cast, amount: int, dtype: DamageType) -> None:
    """Everybody standing next to this creature, itself left out."""
    me = c.me
    for who in c.within(1, of=me, side="any"):
        if who != me:
            c.flat(amount, dtype=dtype, on=who)


# ==========================================================================
# m1504
# ==========================================================================


@power(
    "m1504a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 3),
)
def m1504a0(c: Cast) -> None:
    if c.strike():
        _crit_line(c, "1d8", 11)


@power(
    "m1504a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d4", 3),
)
def m1504a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1504a2",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(4, 10),
    target=NO_TARGET,
    keywords=[Keyword.ZONE],
    uses=1,
)
def m1504a2(c: Cast) -> None:
    """"Creatures with darkvision ignore this effect" has nowhere to go --
    there is no darkvision concept in this engine -- but the zone itself is
    exact."""
    area = spread({c.here}, 4)
    c.zone(area, blocks_sight=True, until=When.SUSTAIN, sustain=ActionType.MINOR, label=c.ref)


@power(
    "m1504a3",
    level=6,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(1),
    target=Target(side="enemy", everyone=True, label="enemies in the burst"),
    trigger="it is reduced to 0 hit points",
    on=Trigger(Dropped, about_me, "it is reduced to 0 hit points"),
)
def m1504a3(c: Cast) -> None:
    c.blinded(until=When.SAVE_ENDS)


@power(
    "m1504a4",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1504a4(c: Cast) -> None:
    _edge_damage(c)


@power(
    "m1504a5",
    level=6,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1504a5(c: Cast) -> None:
    me = c.me
    c.bonus(AC, 4, on=me, until=When.EOT, when=lambda ctx: bool(ctx.get("opportunity")))
    c.move(4)
    for foe in c.enemies():
        if c.adjacent_to(foe, me):
            c.gains_advantage(lambda _ctx: True, until=When.EONT, on=foe)


@power(
    "m1504a6",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
)
def m1504a6(c: Cast) -> None:
    c.invisible(until=When.EONT)


# ==========================================================================
# m1507
# ==========================================================================


@power(
    "m1507a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d6", 4),
)
def m1507a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1507a1",
    level=6,
    usage=ENCOUNTER,
    action=REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d6", 1, kind=LIMITED),
    trigger="an enemy moves or shifts into a square adjacent to it",
    on=Trigger(
        AdjacencyGained, _enemy_ended_adjacent,
        "an enemy moves or shifts into a square adjacent to it",
    ),
)
def m1507a1(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is not None and c.strike(on=foe):
        c.hit(on=foe)


@power(
    "m1507a2",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1507a2(c: Cast) -> None:
    c.bonus(
        "damage", 0, dice="2d6", on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: bool(ctx.get("advantage")),
    )


@power(
    "m1507a3",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
    requires=lambda world, eid: any(
        eff.label == "m1507a4" for eff in world.effects.of(eid)
    ),
    requires_text="it must be insubstantial from m1507a4",
)
def m1507a3(c: Cast) -> None:
    """"Can end this effect on its turn as a free action" is a minor manual
    off-switch and is left to the invisibility's own natural expiry, the
    same simplification several other self-dismissed veils already take."""
    _vanish_until_it_swings(c, When.EONT)


@power(
    "m1507a4",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    narrative=("skill:stealth",),
)
def m1507a4(c: Cast) -> None:
    """The +5 bonus to Stealth checks is a circumstance with no roll to
    attach to -- hiding here is checked off cover and concealment, never
    rolled, so a stealth check never happens for it to improve.

    `c.insubstantial` already halves damage *taken*, which is the
    ordinary meaning of the word and is unaffected by this card's own extra
    clause: half damage *dealt* as well, which needs its own watch over the
    creature's outgoing `DamageRolled`. A second, named hold marks that the
    form is up, for m1507a3's Requirement to read."""
    me = c.me
    c.insubstantial(on=me, until=When.EONT)
    held = c.effect("m1507a4", until=When.EONT, on=me)
    if held is None:
        return

    def halved(ev: DamageRolled) -> None:
        if ev.attacker == me:
            c.halve(ev)

    watch = c.watch(
        DamageRolled, halved, until=When.EONT, on=me, window=Window.BEFORE,
        label=f"{c.ref} half",
    )
    held.on_end.append(lambda: c.world.effects.end(watch, "form ended"))


# ==========================================================================
# m2779
# ==========================================================================


@power(
    "m2779a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d4", 3),
)
def m2779a0(c: Cast) -> None:
    if c.strike():
        _crit_line(c, "2d4", 11)


@power(
    "m2779a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d4"),
)
def m2779a1(c: Cast) -> None:
    """"Requires falchion" is an equipment prerequisite this engine does not
    track. The attack penalty and the burn are one printed sentence and one
    saving throw, so they are one held effect."""
    if c.strike():
        c.damage("2d4", 0)
        victim = c.target
        if victim is not None:
            mod = Mod(what="perception", value=-5, kind="untyped", label=c.ref)
            c.world.effects.apply(
                victim, c.me, When.SAVE_ENDS, label=f"{c.ref} hold",
                mods=[(victim, mod)], ongoing=(5, DamageType.POISON),
            )


@power(
    "m2779a2",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.HEALING, Keyword.WEAPON],
    requires=_is_bloodied,
    requires_text="it must be bloodied",
)
def m2779a2(c: Cast) -> None:
    c.basic()
    c.heal(14, on=c.me)


@power(
    "m2779a3",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("Attack(vs=)",),
)
def m2779a3(c: Cast) -> None:
    """Refused in play: switching which defence its own attack targets,
    conditioned on combat advantage, is not sayable -- `Attack.vs` is fixed
    at the row's own declaration, and that is the row's whole printed
    effect."""


@power(
    "m2779a4",
    level=6,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is hit by a melee or a ranged attack",
    on=Trigger(Hit, both(targets_me, _physical_hit), "it is hit by a melee or a ranged attack"),
    dropped=("c.cover()",),
)
def m2779a4(c: Cast) -> None:
    """There is no verb to grant cover against the triggering attack --
    `ignore_cover`/`no_cover` only ever take it away. The swap and the
    combat-advantage half are exact."""
    me = c.me
    attacker = getattr(c.trigger, "attacker", None)
    other = next(
        (a for a in c.allies() if a != me and c.adjacent(a) and a != attacker), None,
    )
    if other is None:
        return
    c.swap(other)
    c.gains_advantage(lambda _ctx: True, until=When.EONT, on=other)


# ==========================================================================
# m3312
# ==========================================================================


def _has_an_opening(world: World, eid: int) -> bool:
    from combat_engine.engine.query import enemies, has_combat_advantage

    return any(has_combat_advantage(world, eid, foe) for foe in enemies(world, eid))


@power(
    "m3312a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d4", 5),
)
def m3312a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.shift(1)


@power(
    "m3312a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("3d4", 5),
    requires=_has_an_opening,
    requires_text="it must have combat advantage against a target",
)
def m3312a1(c: Cast) -> None:
    """"Requires dagger" is equipment, not tracked."""
    victim = c.target
    if c.strike():
        c.hit()
        if victim is not None:
            c.condition(
                Condition.SLOWED, until=When.SAVE_ENDS, on=victim,
                ongoing=(5, DamageType.NECROTIC),
            )
    c.restore_use("m3312a2", on=c.me)


@power(
    "m3312a2",
    level=6,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m3312a2(c: Cast) -> None:
    c.conceal(total=True, until=When.EONT)
    c.insubstantial(until=When.EONT)


@power(
    "m3312a3",
    level=6,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
    out_of_combat=True,
)
def m3312a3(c: Cast) -> None:
    """Deliberately inert: a disguise with no combat reading."""


@power(
    "m3312a4",
    level=6,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_DISLIKED_ROLL,
    on=Trigger(AttackRolled, _disliked_my_roll, _DISLIKED_ROLL),
)
def m3312a4(c: Cast) -> None:
    c.reroll_attack(keep="new")


@power(
    "m3312a5",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3312a5(c: Cast) -> None:
    """Rough ground costs it nothing while it shifts, and nothing else.

    `when="shift"` is the narrowing every one of these cards prints and this
    verb could not say. It is spent in the *search*: a square of difficult
    terrain costs two, a shift is one, so without the exemption the square is
    never offered as a shift destination at all.
    """
    c.ignores_difficult(on=c.me, until=When.ENCOUNTER, when="shift")


# ==========================================================================
# m3557
# ==========================================================================


@power(
    "m3557a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=10),
    damage=Damage("2d6", 0, dtype=[DamageType.FIRE, DamageType.NECROTIC]),
)
def m3557a0(c: Cast) -> None:
    """Both types in the header, with the keywords the card prints.

    **The keyword list was empty**, which is the #423 half of #420 and the
    reason this row was one of three the type tally could not derive from
    keywords: nothing carried either word, so `policy/threat.py` -- which
    prices a row by unioning them -- saw an untyped blow.
    """
    if c.strike():
        c.hit()


@power(
    "m3557a1",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=Target(
        side="enemy", count=1,
        label="a living humanoid",
        kinds=frozenset({"humanoid"}),
        # "Living" is not a negative set. Excluding `construct` as well
        # refuses the 25 blocks that carry *both* `living` and `construct`,
        # which the card calls living; excluding only `undead` admits a
        # non-living construct. The exact test is "not undead, and not
        # construct unless it carries living", which no any-of negative can
        # say. This is the faithful half -- what the body asked before the
        # conversion -- and the exception is marked. #411.
        kinds_without=frozenset({"undead"}),
    ),
    attack=Attack(vs=WILL, printed=10),
    dropped=('c.leaves_the_grid()', "Target.living"),
)
def m3557a1(c: Cast) -> None:
    """"Enters the target's space and is removed from the map, reappearing
    adjacent when the domination ends" has no verb -- there is nothing to
    take a creature off the grid while it stays alive. The domination and
    the periodic burn are exact.

    The target line is two fields, not one: the type word is required and
    "living" is the absence of the two that deny it, so a humanoid of either
    is refused."""
    victim = c.target
    if victim is None or not c.strike(on=victim):
        return
    held = c.condition(Condition.DOMINATED, until=When.SAVE_ENDS, on=victim)
    if held is None:
        return

    def toll(ev: TurnStart) -> None:
        if ev.actor == victim and not ev.ghost and held in c.world.effects.of(victim):
            c.flat(5, dtypes=(DamageType.FIRE, DamageType.NECROTIC), on=victim)

    watch = c.watch(TurnStart, toll, until=When.SAVE_ENDS, on=c.me, label=f"{c.ref} grip")
    held.on_end.append(lambda: c.world.effects.end(watch, "no longer dominated"))


@power(
    "m3557a2",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.leash()",),
)
def m3557a2(c: Cast) -> None:
    """Refused in play: a leash to the thing anchoring the trap, and no ref
    names that anchor, so there is nothing to measure distance from.
    `c.leash` does not exist -- the same symbol a level-1 trap waited on."""


# ==========================================================================
# m4156
# ==========================================================================


@power(
    "m4156a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d10", 6),
)
def m4156a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4156a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 6),
)
def m4156a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4156a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=UpTo(3),
)
def m4156a2(c: Cast) -> None:
    """Two claws, one bite -- the three attacks share this row's target
    list in the order the card prints them."""
    ref = "m4156a0" if c.index < 2 else "m4156a1"
    c.use_power(ref, on=c.target)


@power(
    "m4156a3",
    level=6,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=Melee(2),
    target=NO_TARGET,
    trigger="an enemy moves adjacent to it",
    on=Trigger(AdjacencyGained, _enemy_ended_adjacent, "an enemy moves adjacent to it"),
)
def m4156a3(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is None:
        return
    if c.use_power("m4156a1", on=foe) and c.landed:
        c.grants_advantage(on=foe, until=When.SAVE_ENDS)


@power(
    "m4156a4",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("1d12", 4, dtype=DamageType.POISON, kind=LIMITED, half_on_miss=True),
)
def m4156a4(c: Cast) -> None:
    """"Save ends both" is approximated as two independent save-ends holds
    rather than one roll clearing both -- the custom-mod machinery for that
    bundles a numeric modifier with an ongoing burn, not an invisibility."""
    victim = c.target
    if c.strike():
        c.hit()
        if victim is not None:
            c.ongoing(5, DamageType.POISON, on=victim)
            c.invisible(to=victim, on=c.me, until=When.SAVE_ENDS)
    else:
        c.hit(half=True)


@power(
    "m4156a5",
    level=6,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is first bloodied",
    on=Trigger(Bloodied, about_me, "it is first bloodied"),
)
def m4156a5(c: Cast) -> None:
    from combat_engine.engine import Powers, use

    known = c.world.get(c.me, Powers)
    if known is None:
        return
    known.restore("m4156a4")
    use(c.world, c.me, "m4156a4")


@power(
    "m4156a6",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=9),
)
def m4156a6(c: Cast) -> None:
    victim = c.target
    if c.strike():
        held = c.stunned(until=When.EONT)
        if held is not None and victim is not None:
            held.on_end.append(
                lambda v=victim: c.penalty("attack", 2, on=v, until=When.SAVE_ENDS)
            )


@power(
    "m4156a7",
    level=6,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
    dropped=("c.mode(suspend=)",),
)
def m4156a7(c: Cast) -> None:
    """"Can't attack or fly" while in this form -- the fly half has no
    verb: `c.mode` only ever adds a speed, nothing suspends one already on
    the block. The rest of the form is exact, bounded to this creature's
    next turn rather than the card's own open-ended "until it returns"."""
    me, ref = c.me, c.ref
    held = [
        h
        for h in (
            c.no_basic(on=me, until=When.EONT),
            c.ignores_difficult(on=me, until=When.EONT),
            c.no_provoke(on=me, until=When.EONT),
            c.mode("climb", 6, on=me, until=When.EONT),
        )
        if h is not None
    ]
    c.shift(4)

    def returned() -> None:
        for foe in c.within(2, of=me, side="any"):
            if foe != me:
                c.gains_advantage(lambda _ctx: True, until=When.EONT, on=foe)

    anchor = c.effect(f"{ref} liquid", until=When.EONT, on=me)
    if anchor is not None:
        for h in held:
            anchor.on_end.append(lambda h=h: c.world.effects.end(h, "form ended"))
        anchor.on_end.append(returned)


@power(
    "m4156a8",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4156a8(c: Cast) -> None:
    _edge_damage(c)


# ==========================================================================
# m5942
# ==========================================================================


@power(
    "m5942a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d6", 2),
)
def m5942a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(2)


@power(
    "m5942a1",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_OTHER,
    keywords=[Keyword.FIRE, Keyword.FORCE, Keyword.IMPLEMENT],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("2d6", 6, dtype=[DamageType.FIRE, DamageType.FORCE], kind=LIMITED),
)
def m5942a1(c: Cast) -> None:
    _recharge_when_using(c, "m5942a2")
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.FIRE)


@power(
    "m5942a2",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.FIRE, Keyword.TELEPORTATION],
)
def m5942a2(c: Cast) -> None:
    _recharge_when_using(c, "m5942a1")
    _splash_adjacent(c, 5, DamageType.FIRE)
    _vanish_until_it_swings(c, When.EONT)
    c.teleport(5)


# ==========================================================================
# m5955
# ==========================================================================


@power(
    "m5955a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d4", 9),
)
def m5955a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5955a1",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
)
def m5955a1(c: Cast) -> None:
    me = c.me
    _vanish_until_it_swings(c, When.EONT)
    c.shift(3)

    def ambush(ev: Hit) -> None:
        if ev.attacker == me and ev.target is not None:
            c.flat(c.roll("2d8"), on=ev.target)
            c.dazed(on=ev.target, until=When.EONT)

    c.watch(Hit, ambush, until=When.EONT, on=me, once=True, label=f"{c.ref} ambush")


@power(
    "m5955a2",
    level=6,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(1),
    target=NO_TARGET,
    keywords=[Keyword.ZONE],
)
def m5955a2(c: Cast) -> None:
    from combat_engine.content.monsters.level_02.skirmishers_sa import _aura_holds

    me = c.me
    area = spread({c.here}, 1)
    zone = c.zone(area, blocks_sight=True, until=When.SONT, label=c.ref)

    def blind(who: int) -> Effect | None:
        return None if who == me else c.blinded(on=who, until=When.ENCOUNTER)

    _aura_holds(c, zone, blind)


# ==========================================================================
# m6408
# ==========================================================================


@power(
    "m6408a0",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6408a0(c: Cast) -> None:
    """"Lightly obscured to creatures outside the aura" is read as this
    creature having concealment against anyone attacking from outside it --
    the combat-relevant half of a sightline rule that otherwise touches
    every pair of squares through the aura, not only this one."""
    c.conceal(
        on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: not c.adjacent(ctx.get("attacker")),
    )


@power(
    "m6408a1",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6408a1(c: Cast) -> None:
    c.bonus(
        "damage", 0, dice="2d6", on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: bool(ctx.get("advantage")),
    )


@power(
    "m6408a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("3d6", 8),
)
def m6408a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6408a3",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("2d8", 5, dtype=DamageType.FIRE),
)
def m6408a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.FIRE)


@power(
    "m6408a4",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
)
def m6408a4(c: Cast) -> None:
    c.basic(on=c.target)


@power(
    "m6408a5",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_OTHER,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("2d8", 6, dtype=DamageType.FIRE, kind=LIMITED, half_on_miss=True),
    requires=_is_bloodied,
    requires_text="it must be bloodied",
)
def m6408a5(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(4)
    else:
        c.hit(half=True)
        c.push(1)


@power(
    "m6408a6",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.FIRE, Keyword.ILLUSION, Keyword.TELEPORTATION],
)
def m6408a6(c: Cast) -> None:
    _splash_adjacent(c, 5, DamageType.FIRE)
    _vanish_until_it_swings(c, When.EONT)
    c.teleport(10)


@power(
    "m6408a7",
    level=6,
    usage=AT_WILL,
    action=REACTION,
    reach=Ranged(20),
    target=NO_TARGET,
    trigger="an enemy within 20 squares hits it with an attack",
    on=Trigger(Hit, targets_me, "an enemy within 20 squares hits it with an attack"),
)
def m6408a7(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is None:
        return
    c.vulnerable(5, None, on=foe, until=When.EONT)
    c.basic(on=foe)


@power(
    "m6408a8",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PSYCHIC],
)
def m6408a8(c: Cast) -> None:
    me = c.me

    def dawn(ev: TurnStart) -> None:
        if ev.actor != me or ev.ghost:
            return
        bad = [e for e in list(c.world.effects.of(me)) if e.conditions or e.ongoing]
        if not bad:
            return
        for e in bad:
            c.world.effects.end(e, "m6408a8")
        c.flat(20, dtype=DamageType.PSYCHIC, on=me)

    c.watch(TurnStart, dawn, until=When.ENCOUNTER, on=me, label=f"{c.ref} purge")


# ==========================================================================
# m6500
# ==========================================================================


@power(
    "m6500a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d6", 7),
)
def m6500a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6500a1",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d6", 10, kind=LIMITED),
)
def m6500a1(c: Cast) -> None:
    _recharge_when_using(c, "m6500a2")
    if c.strike():
        c.hit()
        c.weakened(until=When.SAVE_ENDS)


@power(
    "m6500a2",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(5),
    target=Target(side="enemy", count=1, label="one creature in the burst"),
    keywords=[Keyword.POLYMORPH, Keyword.TELEPORTATION],
    attack=Attack(vs=WILL, printed=9),
    narrative=("skill:insight",),
)
def m6500a2(c: Cast) -> None:
    """Assuming the target's likeness is a disguise with no combat reading
    of its own -- the DC 28 Insight check it names is never rolled on a
    board that already knows what stands on it. The position swap is the
    real, mechanical half."""
    _recharge_when_using(c, "m6500a1")
    victim = c.target
    if victim is not None and c.strike(on=victim):
        c.swap(victim)


@power(
    "m6500a3",
    level=6,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
    out_of_combat=True,
)
def m6500a3(c: Cast) -> None:
    """Deliberately inert: a disguise with no combat reading."""


# ==========================================================================
# m6604
# ==========================================================================


@power(
    "m6604a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d6", 8),
)
def m6604a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6604a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=MeleeOrRanged(1, 10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d4", 8),
)
def m6604a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6604a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    keywords=[Keyword.WEAPON],
)
def m6604a2(c: Cast) -> None:
    c.basic(on=c.target)


@power(
    "m6604a3",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=Target(side="enemy", count=1, max_size=Size.MEDIUM, label="one Medium creature"),
    keywords=[Keyword.ILLUSION, Keyword.POLYMORPH],
)
def m6604a3(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    c.immobilized(on=victim, until=When.EONT)
    c.bonus(
        "damage", 0, dice="4d6", on=c.me, until=When.EONT, once=True,
        when=lambda ctx, v=victim: ctx.get("target") == v,
    )
    held = c.effect(f"{c.ref} disguise", until=When.EONT, on=c.me)
    if held is not None:
        held.victim = victim  # type: ignore[attr-defined]


@power(
    "m6604a4",
    level=6,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
    out_of_combat=True,
)
def m6604a4(c: Cast) -> None:
    """Deliberately inert: a disguise with no combat reading."""


@power(
    "m6604a5",
    level=6,
    usage=AT_WILL,
    once_per_round=True,
    action=MINOR,
    reach=CloseBurst(1),
    target=Target(side="enemy", count=1, label="one enemy in the burst"),
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=8),
)
def m6604a5(c: Cast) -> None:
    if c.strike():
        c.push(2)


@power(
    "m6604a6",
    level=6,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(5),
    target=Target(side="ally", count=2, label="one or two allies in the burst"),
    keywords=[Keyword.CHARM],
    trigger="it is first bloodied",
    on=Trigger(Bloodied, about_me, "it is first bloodied"),
)
def m6604a6(c: Cast) -> None:
    ally = c.target
    if ally is not None:
        c.shift(3, who=ally)
        c.basic(who=ally)


def _wearing_a_disguise(world: World, eid: int) -> bool:
    from combat_engine.engine.query import adjacent as _adj

    for eff in world.effects.of(eid):
        if eff.label == "m6604a3 disguise":
            victim = getattr(eff, "victim", None)
            return victim is not None and _adj(world, eid, victim)
    return False


@power(
    "m6604a7",
    level=6,
    usage=AT_WILL,
    action=ActionType.OPPORTUNITY,
    reach=PERSONAL,
    target=NO_TARGET,
    requires=_wearing_a_disguise,
    requires_text="it must be adjacent to an enemy affected by its m6604a3",
    trigger="a melee or ranged attack from an enemy unaffected by its m6604a3 targets it",
    on=Trigger(
        Hit, both(targets_me, _physical_hit),
        "a melee or ranged attack from an unaffected enemy targets it",
    ),
)
def m6604a7(c: Cast) -> None:
    for eff in c.world.effects.of(c.me):
        if eff.label == "m6604a3 disguise":
            victim = getattr(eff, "victim", None)
            if victim is not None:
                c.swap(victim)
                c.redirect(to=victim)
            return


# ==========================================================================
# m999
# ==========================================================================


@power(
    "m999a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d6", 5),
)
def m999a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m999a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d6", 5),
)
def m999a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m999a2",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(4),
    target=EACH_OTHER,
    keywords=[Keyword.POISON, Keyword.ZONE],
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("2d6", 3, dtype=DamageType.POISON, kind=LIMITED),
)
def m999a2(c: Cast) -> None:
    """The brief's "Veserabs are immune" names this creature's own species;
    written here as a ref match instead of the word, per the report."""
    me = c.me
    victim = c.target
    if c.strike():
        c.hit()
        if victim is not None and _ref_of(c, victim) != "m999":
            for defence in (AC, FORT, REF, WILL):
                c.penalty(defence, 2, on=victim, until=When.EONT)
    if c.first:
        area = spread({c.here}, 4)
        zone = c.zone(area, blocks_sight=True, until=When.ENCOUNTER, label=c.ref)

        def toll(ev: TurnStart) -> None:
            if ev.ghost or _ref_of(c, ev.actor) == "m999":
                return
            if ev.actor in c.world.zones.occupants(zone):
                c.flat(5, dtype=DamageType.POISON, on=ev.actor)

        c.watch(TurnStart, toll, until=When.ENCOUNTER, on=me, label=f"{c.ref} haze")


@power(
    "m999a3",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    charges=True,
)
def m999a3(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    c.charge_at(victim)
    for _ in range(2):
        c.use_power("m999a1", on=victim)
    c.shift(1)


@power(
    "m999a4",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.immune(from_power=)",),
)
def m999a4(c: Cast) -> None:
    """The resist half is exact. "Immune to the effects of its own m999a2"
    beyond the poison type -- the -2 to all defences -- has no verb: `c.immune`
    only ever takes conditions, never a power ref to exempt from.

    `_ridden_by`'s gate is re-checked on every one of this creature's own
    turns rather than declared as `requires=`: this is an `action=NONE`
    trait, armed once at the start of the fight, and a Requirement false
    then would be refused for the rest of it even once a rider mounts up
    mid-fight."""
    me = c.me

    def dawn(ev: TurnStart) -> None:
        if ev.actor != me or ev.ghost:
            return
        rider = c.rider()
        if rider is not None and _ridden_by(6)(c.world, me):
            c.resist(5, DamageType.POISON, on=rider, until=When.ENCOUNTER)

    c.watch(TurnStart, dawn, until=When.ENCOUNTER, on=me, label=f"{c.ref} saddle")


@power(
    "m999a5",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m999a5(c: Cast) -> None:
    c.bonus(
        "damage", 0, dice="1d6", on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: bool(ctx.get("advantage")) and _melee_only(ctx),
    )
