"""Monster abilities, level 5, artillery.

Twenty-six stat blocks, seventy-three rows. `artillery.py` holds the earlier
sweep of this level and is not touched here; the split is by *when* the work
was done rather than by what the creatures are. Eight of the twenty-six print no
abilities at all and so have nothing to decorate.

Conventions, all inherited from the level-1 to level-4 sweeps:

* numbers load from `game.db` -- the attack line is written exactly as printed
  (`Attack(vs=AC, printed=10)`) and the damage line goes in the header as data,
  so an MM1 block can be rescaled to MM3 maths later;
* a **trait** is a row that costs no action, has no target, and arms the
  watches that hold it, whatever action the compendium's column claims;
* a printed range band of "20/40" takes the **normal** range;
* a card that prints no range at all is melee 1;
* a close burst or blast whose card names no target set takes **enemies**,
  except where the card says "creatures in the burst" outright;
* a blow of two types rolled once keeps the **first** in the header and carries
  the rest as keywords, which is all one `Damage` can say
  (`dropped=("Damage(dtypes=)",)`); a blow whose type is *chosen* keeps the
  header untyped -- that is the data a rescale reads -- and the body deals the
  typed version instead of calling `c.hit`;
* "+10 vs AC, or +11 against a bloodied target" keeps the printed total in the
  header and adds the difference with `c.strike(plus=)`, so the rescale still
  has one number to read;
* a recharge or encounter attack says `Damage(..., kind=LIMITED)`, a minion's
  flat damage `Damage("", n, kind=MINION)`.

Nine helpers and one constant are imported rather than written again. The nine
written here are shapes this batch is the first to need: a hold whose modifier
and burn end on **one** saving throw, a spotter's bonus to somebody else's next
shot at the same target, and the two-ray multi-attack whose four rays have no
refs of their own and so have to live inside the row that names them.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_01.artillery_sa import _beside_kin
from combat_engine.content.monsters.level_02.artillery_sa import (
    ALL_DEFENCES,
    _saves_off_prone,
)
from combat_engine.content.monsters.level_02.controllers_sa import (
    _let_it_swing_without_moving,
)
from combat_engine.content.monsters.level_02.lurkers_sa import _triggering_enemy
from combat_engine.content.monsters.level_02.skirmishers_sa import _melee_only
from combat_engine.content.monsters.level_02.soldiers_sa import (
    _missed_me_in_melee,
    _save_ends_on_me,
)
from combat_engine.content.monsters.level_03.brutes_sa import _enemy_closed_on_me
from combat_engine.content.monsters.level_03.soldiers_sa import _secondary
from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
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
    Mod,
    Ranged,
    Target,
    UpTo,
    Usage,
    When,
    World,
    power,
    spread,
)
from combat_engine.engine.events import (
    AdjacencyGained,
    AttackDeclared,
    Dropped,
    EffectApplied,
    Hit,
    Miss,
    TurnStart,
)
from combat_engine.engine.monster_math import LIMITED, MINION
from combat_engine.engine.query import distance_between, team
from combat_engine.engine.triggers import Trigger, about_me, targets_me, would_hit_me

# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------

_RAYS = ("1", "2", "3", "4")


def _one_save_for_both(
    c: Cast,
    what: str,
    value: int,
    amount: int,
    dtype: DamageType,
    *,
    on: int | None = None,
) -> Effect | None:
    """"A -2 penalty to attack rolls **and** ongoing 5 poison damage (save
    ends both)."

    One effect carrying the modifier and the burn, because that is what makes
    one saving throw end both: `c.penalty` beside `c.ongoing` builds two
    effects and hands the victim two throws against one printed sentence, and
    it shakes off half of what the card calls one thing. `Effects.apply` takes
    `mods=` and `ongoing=` together, which is the door `c.condition` already
    uses for the condition-plus-burn version of the same shape.
    """
    victim = on if on is not None else c.target
    if victim is None:
        return None
    mod = Mod(what=what, value=-value, kind="untyped", label=c.ref)
    return c.world.effects.apply(
        victim,
        c.me,
        When.SAVE_ENDS,
        label=f"{c.ref} {what}-{value}",
        mods=[(victim, mod)],
        ongoing=(amount, dtype),
    )


def _spot_for_an_ally(c: Cast, victim: int | None, bonus: int, radius: int) -> None:
    """"It grants an ally within N squares a +2 bonus to its **next ranged**
    attack roll against the same target."

    `once=True` is the "next" -- the bonus ends on the first attack that could
    use it -- and the gate is both halves of the narrowing: the roll has to be
    ranged, which the attack context carries, and it has to be aimed at the
    creature this row just shot. Laid on one ally rather than all of them,
    because the card grants it once.
    """
    if victim is None:
        return
    mate = next((a for a in c.allies() if distance_between(c.world, c.me, a) <= radius), None)
    if mate is None:
        return
    c.bonus(
        "attack",
        bonus,
        on=mate,
        until=When.ENCOUNTER,
        once=True,
        when=lambda ctx: bool(ctx.get("ranged")) and ctx.get("target") == victim,
    )


def _two_rays(c: Cast, fire: tuple[str, int], exhaust: tuple[str, int]) -> None:
    """"It uses two <ray> powers from the list below. Each must target a
    different creature."

    The four rays print their own attack and damage lines and have **no refs of
    their own**, so there is nowhere else for them to live: they are written
    here and rolled with `_secondary`, which takes a printed total back to a
    bonus the way the header's `Attack(printed=)` does. The choice is offered
    rather than decided, and a ray already spent is taken out of the list --
    "each must target a different creature" is the printed reason the two uses
    cannot be the same ray at the same victim.

    Guarded on `c.first` and driven off `c.targets`: the body runs once per
    target and the pairing of rays to victims is a fact about the whole use.
    """
    if not c.first:
        return
    left = list(_RAYS)
    for victim in c.targets[:2]:
        if not left:
            return
        pick = c.choose(left, f"{c.ref}: which ray") or left[0]
        left.remove(pick)
        if pick == "1":
            if _secondary(c, 10, REF, victim):
                c.damage(fire[0], fire[1], dtype=DamageType.FIRE, on=victim)
        elif pick == "2":
            if _secondary(c, 10, FORT, victim):
                c.damage(
                    exhaust[0], exhaust[1], dtype=DamageType.NECROTIC, on=victim
                )
                c.condition(Condition.WEAKENED, until=When.SAVE_ENDS, on=victim)
        elif pick == "3":
            if _secondary(c, 10, FORT, victim):
                _sleep(c, victim)
        elif _secondary(c, 10, FORT, victim):
            c.slide(4, on=victim)


def _sleep(c: Cast, victim: int) -> None:
    """"Slowed (save ends). First Failed Saving Throw: the target is knocked
    unconscious instead of slowed (save ends)."

    `escalate=` is called on a failed throw, and the replacement is a fresh
    hold rather than a condition added to the standing one, because the card
    says *instead of*: the slow has to come off or the creature is both at
    once. The second hold escalates no further -- the card names one step.
    """

    def worsen(eff: Effect) -> None:
        c.world.effects.end(eff, "it fell asleep")
        c.condition(Condition.UNCONSCIOUS, until=When.SAVE_ENDS, on=victim)

    c.condition(Condition.SLOWED, until=When.SAVE_ENDS, on=victim, escalate=worsen)


def _splash(c: Cast, amount: int, dtype: DamageType, *, radius: int = 1) -> list[int]:
    """Whoever is standing close to the creature this row just shot, the target
    itself left out -- the "each creature adjacent to the target also takes N"
    clause. Returns them so a caller that also shoves them can."""
    victim = c.target
    if victim is None:
        return []
    caught = [
        who
        for who in c.within(radius, of=victim, side="any")
        if who != victim and who != c.me
    ]
    for who in caught:
        c.flat(amount, dtype=dtype, on=who)
    return caught


def _unwarded(c: Cast, who: int) -> bool:
    """"Each **nonfey or nonshadow** creature" -- the two origin words two of
    these swarms spare their own kind by."""
    return not (c.is_kind("fey", on=who) or c.is_kind("shadow", on=who))


def _shot_me_from_afar(radius: int = 0) -> Any:
    """"An enemy within N squares hits it with a **ranged or an area**
    attack." `radius=0` is a card that names no distance at all.

    `_by_close_or_area` is the neighbouring sentence and counts a close burst
    while leaving a bow out, which is the opposite of what is wanted here; the
    reach kinds are read off the row that struck rather than guessed.
    """
    from combat_engine.engine import get

    def check(world: World, me: int, ev: Any) -> bool:
        attacker = getattr(ev, "attacker", None)
        if getattr(ev, "target", None) != me or attacker is None:
            return False
        if team(world, attacker) is team(world, me):
            return False
        if radius and distance_between(world, me, attacker) > radius:
            return False
        row = get(getattr(ev, "power", "") or "")
        return row is not None and row.reach.kind in ("ranged", "area_burst")

    return check


def _bloodied_edge(c: Cast) -> int:
    """"+10 vs AC, or +11 vs AC against a bloodied target." The printed total
    stays in the header and this is the one point of difference."""
    return 1 if c.target is not None and c.bloodied() else 0


def _ally_fights_hotter(c: Cast, mate: int, amount: int) -> None:
    """"Until the end of its next turn, that ally deals 5 extra fire damage
    with its melee attacks, and any enemy that hits that ally with a melee
    attack takes 5 fire damage."

    Two separate things, laid on two separate owners. The extra damage is a
    gated typed rider -- `dtype=` so it meets a fire resistance on its own
    terms, rather than quietly turning the ally's sword into a brand -- and the
    retaliation is a watch, because there is nothing on the *attacker* to lay
    it on until one swings.
    """
    c.bonus(
        "damage",
        amount,
        on=mate,
        until=When.EONT,
        dtype=DamageType.FIRE,
        when=_melee_only,
    )

    def burned(ev: Hit) -> None:
        from combat_engine.engine import get

        if ev.target != mate or ev.attacker == mate:
            return
        row = get(getattr(ev, "power", "") or "")
        if row is not None and row.reach.kind == "melee":
            c.flat(amount, dtype=DamageType.FIRE, on=ev.attacker)

    c.watch(Hit, burned, until=When.EONT, on=mate, label=f"{c.ref} brand")


# ==========================================================================
# m115709
# ==========================================================================


@power(
    "m115709a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d10", 5),
)
def m115709a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m115709a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d8", 8),
)
def m115709a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m115709a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_ALLY,
)
def m115709a2(c: Cast) -> None:
    """The ally needs a victim of its own -- this row has no target but the
    ally, and the swing is the whole printed Effect."""
    if c.target is not None:
        _let_it_swing_without_moving(c, c.target)


@power(
    "m115709a3",
    level=5,
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(3),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d8", 4, dtype=DamageType.POISON, kind=LIMITED),
)
def m115709a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        _one_save_for_both(c, "attack", 2, 5, DamageType.POISON)


# ==========================================================================
# m1501
# ==========================================================================


@power(
    "m1501a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d8", 3),
)
def m1501a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1501a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d10", 5),
)
def m1501a1(c: Cast) -> None:
    """The spotting half is granted whether or not the shot landed: the card
    hangs it on the attack and not on the hit."""
    landed = bool(c.strike())
    if landed:
        c.hit()
    _spot_for_an_ally(c, c.target, 2, 5)


@power(
    "m1501a2",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d10", 5, kind=LIMITED),
)
def m1501a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized(until=When.SAVE_ENDS)


@power(
    "m1501a3",
    level=5,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it suffers an effect that a save can end",
    on=Trigger(EffectApplied, _save_ends_on_me, "an effect a save can end lands on it"),
)
def m1501a3(c: Cast) -> None:
    """The throw is made against the effect just applied, which is the most
    recent save-ends hold on it -- `EffectApplied` names the label and the
    duration and not the effect object, so it is found by walking what is
    standing. `Effects.save` rolls, announces and ends, so a success really
    does shake it off and a failure leaves it in place."""
    for eff in sorted(c.world.effects.of(c.me), key=lambda e: -e.id):
        if eff.when is When.SAVE_ENDS:
            c.world.effects.save(eff)
            return


@power(
    "m1501a4",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1501a4(c: Cast) -> None:
    """A trait, whatever the compendium's action column says. Gated rather than
    laid and lifted: who is standing beside it changes every time anybody
    moves, and concealment switched on once would never come off."""
    c.conceal(on=c.me, until=When.ENCOUNTER, when=lambda _ctx: _beside_kin(c, "m1501"))


# ==========================================================================
# m2293
# ==========================================================================


@power(
    "m2293a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d4", 6),
)
def m2293a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2293a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=10),
    damage=Damage("1d6", 6, dtype=DamageType.NECROTIC),
)
def m2293a1(c: Cast) -> None:
    """"Grants combat advantage to **all** enemies" is `to="team"` read from
    the victim's end: this creature's side is who the victim's enemies are."""
    if c.strike():
        c.hit()
        c.grants_advantage(to="team", until=When.SAVE_ENDS)


@power(
    "m2293a2",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=8),
    damage=Damage("1d6", 6, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m2293a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.vulnerable(5, DamageType.NECROTIC, until=When.SAVE_ENDS)


@power(
    "m2293a3",
    level=5,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=8),
)
def m2293a3(c: Cast) -> None:
    """No damage line at all -- the whole of the hit is the grant and the run.
    `c.flee` is the "safest route away" half: it picks the destination by
    distance from this creature rather than leaving it to the decider, which on
    a quiet board would walk the victim nowhere."""
    if c.strike():
        c.grants_advantage(to="team", until=When.SAVE_ENDS)
        victim = c.target
        if victim is not None:
            c.flee(c.speed_of(victim), on=victim)


# ==========================================================================
# m3550
# ==========================================================================


@power(
    "m3550a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d4", 1),
)
def m3550a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.NECROTIC)


@power(
    "m3550a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=10),
    damage=Damage("2d4", 2, dtype=DamageType.NECROTIC),
)
def m3550a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.NECROTIC)


# ==========================================================================
# m4013
# ==========================================================================


@power(
    "m4013a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d4"),
)
def m4013a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4013a1",
    level=5,
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_CREATURE,
    attack=Attack(vs=WILL, printed=10),
)
def m4013a1(c: Cast) -> None:
    if c.strike():
        c.immobilized(until=When.EONT)


@power(
    "m4013a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(8),
    target=UpTo(2),
    no_provoke=True,
)
def m4013a2(c: Cast) -> None:
    """The row's own card prints no attack and no damage -- all four of those
    lines belong to the rays -- so nothing is declared in the header but the
    range the rays share and the printed exemption from opportunity attacks."""
    _two_rays(c, ("2d6", 4), ("1d8", 4))


# ==========================================================================
# m4199
# ==========================================================================


@power(
    "m4199a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d6", 7),
)
def m4199a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4199a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=10),
    damage=Damage("1d8", 4, dtype=DamageType.LIGHTNING),
)
def m4199a1(c: Cast) -> None:
    """"All creatures adjacent to the target", so its own side is caught too --
    `side="any"`, with the target itself left out because it has already been
    paid. The slide is a square each, away from nowhere in particular, so the
    destination goes through the decider."""
    if c.strike():
        c.hit()
        for who in _splash(c, 5, DamageType.LIGHTNING):
            c.slide(1, on=who)


@power(
    "m4199a2",
    level=5,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    attack=Attack(vs=REF, printed=10),
    damage=Damage("2d10", 4, half_on_miss=True),
    trigger="it drops to 0 hit points",
    on=Trigger(Dropped, about_me, "it drops"),
)
def m4199a2(c: Cast) -> None:
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)


@power(
    "m4199a3",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(2, 20),
    target=EACH_ENEMY,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=10),
    damage=Damage("2d8", 4, dtype=DamageType.LIGHTNING, kind=LIMITED, half_on_miss=True),
)
def m4199a3(c: Cast) -> None:
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)


# ==========================================================================
# m4417
# ==========================================================================


@power(
    "m4417a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d6", 5),
)
def m4417a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4417a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=10),
    damage=Damage("1d10", 5, dtype=DamageType.POISON),
)
def m4417a1(c: Cast) -> None:
    """The splash spares its own sort by **origin word** rather than by side:
    a fey or shadow creature on the other team is spared too, which is what the
    card says and not what a `side="enemy"` sweep would do."""
    if c.strike():
        c.hit()
        victim = c.target
        if victim is not None:
            for who in c.within(1, of=victim, side="any"):
                if who != victim and who != c.me and _unwarded(c, who):
                    c.flat(5, dtype=DamageType.POISON, on=who)


@power(
    "m4417a2",
    level=5,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(2),
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC, Keyword.ZONE],
    trigger="it drops to 0 hit points",
    on=Trigger(Dropped, about_me, "it drops"),
)
def m4417a2(c: Cast) -> None:
    """A zone and a toll, not an attack: the card rolls nothing. The toll is
    asked at the top of each turn rather than kept as a membership list,
    because the zone stays where the swarm fell and creatures walk in and out
    of it for the rest of the fight."""
    area = spread({c.here}, 2)
    c.zone(area, difficult=True, until=When.ENCOUNTER, label=c.ref)
    squares_ = frozenset(area)
    me = c.me

    def toll(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == me:
            return
        if ev.actor in c.in_squares(squares_, side="any") and _unwarded(c, ev.actor):
            c.flat(5, dtype=DamageType.NECROTIC, on=ev.actor)

    c.watch(TurnStart, toll, until=When.ENCOUNTER, on=me, label=f"{c.ref} slime")


# ==========================================================================
# m5306
# ==========================================================================


@power(
    "m5306a0",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5306a0(c: Cast) -> None:
    c.resist_forced(1, on=c.me)


@power(
    "m5306a1",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5306a1(c: Cast) -> None:
    _saves_off_prone(c)


@power(
    "m5306a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d8", 3, dtype=DamageType.FIRE),
)
def m5306a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5306a3",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.RADIANT],
    attack=Attack(vs=REF, printed=10),
    damage=Damage("1d10", 4, dtype=DamageType.RADIANT),
)
def m5306a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.penalty("attack", 2, until=When.SONT)


@power(
    "m5306a4",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_ALLY,
    keywords=[Keyword.FIRE, Keyword.HEALING],
)
def m5306a4(c: Cast) -> None:
    mate = c.target
    if mate is None:
        return
    c.heal(10, on=mate)
    _ally_fights_hotter(c, mate, 5)


# ==========================================================================
# m5359
# ==========================================================================


@power(
    "m5359a0",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5359a0(c: Cast) -> None:
    c.resist_forced(1, on=c.me)


@power(
    "m5359a1",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5359a1(c: Cast) -> None:
    _saves_off_prone(c)


@power(
    "m5359a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 5, dtype=DamageType.FIRE),
)
def m5359a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5359a3",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.RADIANT],
    attack=Attack(vs=REF, printed=10),
    damage=Damage("1d10", 8, dtype=DamageType.RADIANT),
)
def m5359a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.penalty("attack", 2, until=When.SONT)


@power(
    "m5359a4",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_ALLY,
    keywords=[Keyword.FIRE, Keyword.HEALING],
)
def m5359a4(c: Cast) -> None:
    mate = c.target
    if mate is None:
        return
    c.heal(10, on=mate)
    _ally_fights_hotter(c, mate, 5)


# ==========================================================================
# m5438
# ==========================================================================


@power(
    "m5438a0",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5438a0(c: Cast) -> None:
    c.cannot_be_flanked(on=c.me)


@power(
    "m5438a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d4", 5),
)
def m5438a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5438a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(8),
    target=UpTo(2),
    no_provoke=True,
)
def m5438a2(c: Cast) -> None:
    _two_rays(c, ("2d6", 6), ("1d8", 4))


@power(
    "m5438a3",
    level=5,
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_CREATURE,
    attack=Attack(vs=WILL, printed=10),
)
def m5438a3(c: Cast) -> None:
    if c.strike():
        c.immobilized(until=When.EONT)


# ==========================================================================
# m5445
# ==========================================================================


@power(
    "m5445a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 8),
)
def m5445a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5445a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.THUNDER],
    attack=Attack(vs=REF, printed=10),
    damage=Damage("2d6", 6, dtype=DamageType.THUNDER),
)
def m5445a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.DEAFENED, until=When.SAVE_ENDS)


@power(
    "m5445a2",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=[Keyword.THUNDER],
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("2d6", 8, dtype=DamageType.THUNDER, kind=LIMITED, half_on_miss=True),
)
def m5445a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.EONT)
    else:
        c.hit(half=True)


@power(
    "m5445a3",
    level=5,
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(10),
    target=Target(side="ally", count=1, label="kobold ally"),
    dropped=("Target.creature_kind",),
)
def m5445a3(c: Cast) -> None:
    """The printed line narrows to an ally of one type word within 10 squares.
    `Target` filters on side and size and nothing else, so the kind is asked
    here -- against the compendium row, which is why the gap is
    `Target.creature_kind` and not a condition -- and the row redirects to
    somebody who qualifies rather than returning: the printed line is about
    which ally, not about whether the row happens."""
    mate = c.target
    if mate is not None and not c.is_kind("kobold", on=mate):
        mate = next(
            (
                a
                for a in c.allies()
                if c.is_kind("kobold", on=a) and distance_between(c.world, c.me, a) <= 10
            ),
            None,
        )
    if mate is None:
        return
    c.temp_hp(5, on=mate)
    c.shift(1, who=mate)


@power(
    "m5445a4",
    level=5,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m5445a4(c: Cast) -> None:
    c.shift(1)


# ==========================================================================
# m5886
# ==========================================================================


@power(
    "m5886a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d6", 5),
)
def m5886a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5886a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING, Keyword.RADIANT],
    attack=Attack(vs=REF, printed=10),
    damage=Damage("1d8", 4, dtype=DamageType.LIGHTNING),
    dropped=("Damage(dtypes=)",),
)
def m5886a1(c: Cast) -> None:
    """One roll of two types, which is all one `Damage` can say -- the first
    stays in the header as the data a rescale reads and the second rides as a
    keyword. The splash is a second, single-typed blow and needs no marker."""
    if c.strike():
        c.hit()
        victim = c.target
        if victim is not None:
            for foe in c.enemies():
                if foe != victim and distance_between(c.world, foe, victim) <= 2:
                    c.flat(5, dtype=DamageType.LIGHTNING, on=foe)


@power(
    "m5886a2",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(2, 20),
    target=EACH_CREATURE,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=10),
    damage=Damage("1d8", 4, dtype=DamageType.LIGHTNING, kind=LIMITED, half_on_miss=True),
)
def m5886a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.LIGHTNING)
    else:
        c.hit(half=True)


@power(
    "m5886a3",
    level=5,
    usage=AT_WILL,
    action=REACTION,
    reach=CloseBurst(10),
    target=NO_TARGET,
    keywords=[Keyword.LIGHTNING, Keyword.RADIANT],
    trigger="an enemy within 20 squares hits it with a ranged or an area attack",
    on=Trigger(Hit, _shot_me_from_afar(20), "it is shot from a distance"),
)
def m5886a3(c: Cast) -> None:
    """One blow of two types, dealt flat because the card names no roll;
    `dtypes=` is the body's way of saying what one `Damage` header cannot, so
    there is nothing missing here. The target is the triggering enemy and not
    whoever the burst caught -- the card says so, and an immediate reaction's
    own target list is routinely empty."""
    foe = _triggering_enemy(c)
    if foe is not None:
        c.flat(
            5,
            dtypes=(DamageType.LIGHTNING, DamageType.RADIANT),
            on=foe,
        )


# ==========================================================================
# m5893
# ==========================================================================


@power(
    "m5893a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d6", 10),
)
def m5893a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5893a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=UpTo(2),
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d10", 5),
)
def m5893a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5893a2",
    level=5,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    no_provoke=True,
    trigger="an enemy enters a square adjacent to it",
    on=Trigger(AdjacencyGained, _enemy_closed_on_me, "an enemy closes on it"),
)
def m5893a2(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is not None:
        c.basic(on=foe, ranged=True)


# ==========================================================================
# m5958
# ==========================================================================


@power(
    "m5958a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d6", 4),
)
def m5958a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5958a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT],
    attack=Attack(vs=REF, printed=10),
    damage=Damage("3d4", 3),
)
def m5958a1(c: Cast) -> None:
    """The type is chosen at the table, so the header's damage line stays
    untyped -- that is the data a rescale reads -- and the body deals the typed
    version instead of calling `c.hit`, so nothing lands twice. The splash is
    the *same* choice and not a second one."""
    if not c.strike():
        return
    element = (
        c.choose(
            [DamageType.FIRE, DamageType.NECROTIC, DamageType.RADIANT],
            f"{c.ref}: which element",
        )
        or DamageType.FIRE
    )
    c.damage("3d4", 3, dtype=element)
    victim = c.target
    if victim is not None:
        near = [
            who
            for who in c.within(1, of=victim, side="any")
            if who != victim and who != c.me
        ]
        if near:
            c.flat(3, dtype=element, on=near[0])


@power(
    "m5958a2",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.FORCE, Keyword.IMPLEMENT],
    attack=Attack(vs=FORT, printed=10),
    damage=Damage("1d10", 5, dtype=DamageType.FORCE, kind=LIMITED, half_on_miss=True),
)
def m5958a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()
    else:
        c.hit(half=True)


@power(
    "m5958a3",
    level=5,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m5958a3(c: Cast) -> None:
    c.teleport(5)


# ==========================================================================
# m5993
# ==========================================================================


@power(
    "m5993a0",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5993a0(c: Cast) -> None:
    """"It does not provoke opportunity attacks by climbing." Gated on what the
    creature is doing *now* rather than on what it can do: `Movement.modes`
    only ever said a climb was possible, and the exemption is only owed while
    one is under way."""
    c.no_provoke(
        on=c.me,
        until=When.ENCOUNTER,
        when=lambda _ctx: c.moving_as("climb", on=c.me),
    )


@power(
    "m5993a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("", 6, kind=MINION),
)
def m5993a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5993a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("", 6, kind=MINION),
)
def m5993a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5993a3",
    level=5,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is missed by a melee attack",
    on=Trigger(Miss, _missed_me_in_melee, "a melee attack misses it"),
)
def m5993a3(c: Cast) -> None:
    """"Shifts **or** climbs up to half its speed": a climb is a mode of the
    same step rather than a second kind of move, and the shift is the half the
    board can always offer, so the step is spent as one and the shot follows
    whether or not it moved."""
    c.shift(max(1, c.speed_of() // 2))
    c.use_power("m5993a2")


# ==========================================================================
# m6042
# ==========================================================================


@power(
    "m6042a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d4", 5),
)
def m6042a0(c: Cast) -> None:
    if c.strike(plus=_bloodied_edge(c)):
        c.hit()


@power(
    "m6042a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=10),
    damage=Damage("2d6", 6, dtype=DamageType.FIRE),
)
def m6042a1(c: Cast) -> None:
    if c.strike(plus=_bloodied_edge(c)):
        c.hit()


@power(
    "m6042a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.ILLUSION, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=10),
    damage=Damage("1d6", 4, dtype=DamageType.PSYCHIC),
)
def m6042a2(c: Cast) -> None:
    """The bloodied bonus is asked per target, which is what a burst's
    once-per-target body is for: one creature in it may be bloodied and
    another not."""
    if c.strike(plus=_bloodied_edge(c)):
        c.hit()
        c.ongoing(5, DamageType.PSYCHIC)


@power(
    "m6042a3",
    level=5,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
    trigger="an enemy enters a square adjacent to it",
    on=Trigger(AdjacencyGained, _enemy_closed_on_me, "an enemy closes on it"),
)
def m6042a3(c: Cast) -> None:
    c.teleport(5)


@power(
    "m6042a4",
    level=5,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
    trigger="it is hit by an enemy's attack",
    on=Trigger(Hit, targets_me, "an attack lands on it"),
)
def m6042a4(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is not None and foe in c.enemies():
        c.damage("1d6", 3, dtype=DamageType.FIRE, on=foe)


# ==========================================================================
# m853
# ==========================================================================


@power(
    "m853a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6"),
)
def m853a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m853a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE, Keyword.IMPLEMENT],
    attack=Attack(vs=REF, printed=10),
    damage=Damage("2d4", 4, dtype=DamageType.FORCE),
)
def m853a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m853a2",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(2),
    keywords=[Keyword.COLD, Keyword.IMPLEMENT],
    attack=Attack(vs=REF, printed=10),
    damage=Damage("1d10", 4, dtype=DamageType.COLD, kind=LIMITED),
)
def m853a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized(until=When.EONT)


@power(
    "m853a3",
    level=5,
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(3, 20),
    target=EACH_ENEMY,
    keywords=[Keyword.FIRE, Keyword.IMPLEMENT],
    attack=Attack(vs=REF, printed=10),
    damage=Damage("3d6", 4, dtype=DamageType.FIRE, kind=LIMITED, half_on_miss=True),
)
def m853a3(c: Cast) -> None:
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)


@power(
    "m853a4",
    level=5,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    trigger="an attack would hit it",
    on=Trigger(AttackDeclared, would_hit_me, "an attack would hit it"),
)
def m853a4(c: Cast) -> None:
    """An interrupt, so the bonus is laid before the roll is compared and can
    turn the blow it answers into a miss -- which is the printed point of
    putting it in that window rather than in a reaction's."""
    for which in ALL_DEFENCES:
        c.bonus(which, 1, on=c.me, until=When.EONT)


# ==========================================================================
# m914
# ==========================================================================


@power(
    "m914a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=5),
    damage=Damage("1d8"),
)
def m914a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m914a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE],
    attack=Attack(vs=REF, printed=8),
    damage=Damage("2d4", 4, dtype=DamageType.FORCE),
)
def m914a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m914a2",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(3),
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=8),
    damage=Damage("1d6", 4, dtype=DamageType.LIGHTNING, kind=LIMITED),
)
def m914a2(c: Cast) -> None:
    """"A separate attack against 3 different targets" is three rolls at three
    creatures, which is what a body called once per target already is."""
    if c.strike():
        c.hit()


@power(
    "m914a3",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.THUNDER],
    attack=Attack(vs=FORT, printed=8),
    damage=Damage("1d8", 4, dtype=DamageType.THUNDER, kind=LIMITED),
)
def m914a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)
