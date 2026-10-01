"""Theme powers, batch C: fourteen themes.

Two phrases run through the whole batch and neither is in the engine.

**"Primary ability vs. AC."** A theme does not know which class took it, so
its attack line names no ability at all. `Attack` needs one or a printed
number, so the header names Strength and the roll carries the difference to
the character's largest modifier as `plus=` -- the shape `general_k` settled
on for "your highest ability modifier". For *primary* that stand-in is right
for most builds and generous for a few, so those rows carry
`c.attack_ability()` the way `f3248` does.

**"Highest ability modifier"** is exact, not a stand-in: `_best` is what the
card says. Those rows carry no marker for it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    EACH_ALLY,
    EACH_CREATURE,
    EACH_ENEMY,
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
    STR,
    WILL,
    ActionType,
    AreaBurst,
    Attack,
    AttackDeclared,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    ConditionApplied,
    DamageRolled,
    DamageType,
    Dropped,
    Healed,
    Health,
    Hit,
    Keyword,
    Melee,
    MeleeOrRanged,
    Miss,
    Moved,
    Pick,
    PowerUsed,
    Ranged,
    SavingThrow,
    SkillCheck,
    Target,
    Trigger,
    TurnEnd,
    TurnStart,
    When,
    ally_within,
    both,
    by_me,
    by_melee,
    by_ranged,
    check_failed,
    either,
    enemy_within,
    leaves_me_out,
    my_check,
    power,
    query,
    targets_me,
)

if TYPE_CHECKING:
    from combat_engine.engine.ecs import World

#: "Primary ability" is a fact about the class that took the theme, and
#: nothing names one. The largest modifier stands in.
#: A target line with a restriction `Target` cannot hold -- "granting combat
#: advantage to you", "of your size or smaller", "adjacent to your familiar".
FILTER = ("Target.filter()",)

ONE_OTHER_ALLY = Target("other_ally", 1)
ANY_CREATURE = Target("any", 1)


def _best(c: Cast) -> int:
    """The character's largest ability modifier. The header names one
    ability, so the roll carries the difference as `plus=`."""
    return max(
        c.str_mod, c.con_mod, c.dex_mod, c.int_mod, c.wis_mod, c.cha_mod
    )


def _lonely(c: Cast) -> bool:
    """"While you are not adjacent to any of your allies." `side="ally"`
    leaves the caster out, which is what the sentence asks about."""
    return not c.within(1, side="ally")


def _lonely_now(world: World, eid: int) -> bool:
    """The same question from a trigger or a `requires=`, which get no
    `Cast`."""
    return not any(
        query.adjacent(world, eid, friend) for friend in query.allies(world, eid)
    )


_SOCIAL = my_check("bluff", "diplomacy", "intimidate", "streetwise")


def _is_social(world: World, me: int, ev: Any) -> bool:
    """One of the four skills the card names, whoever rolled it."""
    return getattr(ev, "skill", "") in (
        "bluff", "diplomacy", "intimidate", "streetwise",
    )


# ---------------------------------------------------------------- x7_643 --
# Every attack prints "either you do this, or your allies do that". The
# choice is a real one and `c.choose` is where it goes; a headless run takes
# the first option, which is the half that acts on the caster.


@power("p11778", level=0, cls="x7_643", usage=ENCOUNTER, action=STANDARD,
       reach=MeleeOrRanged(1, by_weapon=True), target=ONE_CREATURE,
       keywords=[Keyword.MARTIAL, Keyword.WEAPON],
       attack=Attack(Pick.PRIMARY, vs=AC))
def p11778(c: Cast) -> None:
    if not c.strike(plus=_best(c) - c.attack_mod):
        return
    c.damage(c.w(), _best(c))
    if c.choose(["you shift 4", "each ally within 5 shifts 2"]) == "you shift 4":
        c.shift(4, who=c.me)
        return
    for friend in c.within(5, side="ally"):
        c.shift(2, who=friend)


@power("p11781", level=2, cls="x7_643", usage=ENCOUNTER, action=FREE,
       reach=CloseBurst(5), target=NO_TARGET, keywords=[Keyword.MARTIAL],
       trigger="you or an ally in the burst dislikes a social skill check",
       on=Trigger(
           SkillCheck,
           both(either(_SOCIAL, ally_within(5)), _is_social),
           "you or an ally in the burst makes a social check",
       ))
def p11781(c: Cast) -> None:
    """Two printings of one clause: your own check is raised after the die
    is down, an ally's is rolled again. `c.boost_check` is the first and
    `c.reroll_check` the second, and which applies is who rolled.

    `ally_within` leaves the caster out by design, so it cannot carry "you
    or an ally" on its own -- the caster's own half is `my_check`, and
    without it the `c.me` branch below would never have run."""
    if getattr(c.trigger, "actor", None) == c.me:
        c.boost_check(3)
    else:
        c.reroll_check(keep="best")


@power("p11782", level=3, cls="x7_643", usage=ENCOUNTER, action=STANDARD,
       reach=MeleeOrRanged(1, by_weapon=True), target=ONE_CREATURE,
       keywords=[Keyword.MARTIAL, Keyword.WEAPON],
       attack=Attack(Pick.PRIMARY, vs=AC))
def p11782(c: Cast) -> None:
    """The Effect line runs whether or not the attack landed."""
    if c.strike(plus=_best(c) - c.attack_mod):
        c.damage(c.w(2), _best(c))
        c.slowed()
    if c.choose(["you shift your speed", "each ally within 2 shifts half"]) \
            == "you shift your speed":
        c.shift(c.speed_of(c.me), who=c.me)
        return
    for friend in c.within(2, side="ally"):
        c.shift(c.speed_of(friend) // 2, who=friend)


@power("p11786", level=5, cls="x7_643", usage=DAILY, action=STANDARD,
       reach=MeleeOrRanged(1, by_weapon=True), target=ONE_CREATURE,
       keywords=[Keyword.MARTIAL, Keyword.WEAPON, Keyword.RELIABLE],
       attack=Attack(Pick.PRIMARY, vs=AC))
def p11786(c: Cast) -> None:
    foe = c.target
    if not c.strike(plus=_best(c) - c.attack_mod):
        return
    c.damage(c.w(2), _best(c))
    c.dazed(until=When.SAVE_ENDS)
    if c.choose(["you attack it", "two allies each attack"]) == "you attack it":
        c.basic(on=foe)
        return
    others = [e for e in c.enemies() if e != foe]
    for friend in c.within(5, side="ally")[:2]:
        if others:
            c.grant_attack(friend, on=others.pop(0))


@power("p11789", level=6, cls="x7_643", usage=ENCOUNTER, action=REACTION,
       reach=CloseBurst(2), target=NO_TARGET, keywords=[Keyword.MARTIAL],
       trigger="an enemy in the burst you can see misses you with a melee attack",
       on=Trigger(Miss, both(targets_me, enemy_within(2), by_melee),
                  "an enemy within 2 misses you with a melee attack"))
def p11789(c: Cast) -> None:
    foe = getattr(c.trigger, "attacker", None)
    if foe is None:
        return
    c.grants_advantage(on=foe, to="team", until=When.EOTNT)
    if c.choose(["you shift 2", "each ally in the burst shifts 1"]) == "you shift 2":
        c.shift(2, who=c.me)
        return
    for friend in c.within(2, side="ally"):
        c.shift(1, who=friend)


@power("p11790", level=7, cls="x7_643", usage=ENCOUNTER, action=STANDARD,
       reach=MeleeOrRanged(1, by_weapon=True), target=ONE_CREATURE,
       keywords=[Keyword.MARTIAL, Keyword.WEAPON],
       attack=Attack(Pick.PRIMARY, vs=AC),
       dropped=("c.provokes(when=)",))
def p11790(c: Cast) -> None:
    """The second branch of the either/or -- "the target provokes
    opportunity attacks when shifting or making melee attacks" -- is the
    inverse of `c.no_provoke(when=)` and there is no verb for it, so only
    the +4 branch is written and the choice is not offered."""
    foe = c.target
    if not c.strike(plus=_best(c) - c.attack_mod):
        return
    c.damage(c.w(), _best(c))
    victims = [w for w in c.within(1, of=foe) if w != foe]
    if victims:
        c.grant_attack(foe, on=c.choose(victims, "whom it swings at"))
    c.bonus(AC, 4, kind="power", on=c.me, until=When.EONT)


@power("p11793", level=9, cls="x7_643", usage=DAILY, action=STANDARD,
       reach=MeleeOrRanged(1, by_weapon=True), target=ONE_CREATURE,
       keywords=[Keyword.MARTIAL, Keyword.WEAPON],
       attack=Attack(Pick.PRIMARY, vs=AC))
def p11793(c: Cast) -> None:
    """"Cannot shift" is `c.rooted`, not `c.immobilized` -- it still walks.

    The Effect is geometry rather than a clock, so the +4 is laid for the
    encounter behind a gate that asks the board whether the caster is still
    adjacent when the blow lands."""
    foe = c.target
    if c.strike(plus=_best(c) - c.attack_mod):
        c.damage(c.w(2), _best(c))
        c.rooted(until=When.SAVE_ENDS)
    else:
        c.half_damage(c.w(2), _best(c))
    if c.choose(["you gain +4 to defences", "it grants combat advantage"]) \
            == "you gain +4 to defences":
        for d in (AC, FORT, REF, WILL):
            c.bonus(d, 4, kind="power", on=c.me, until=When.ENCOUNTER,
                    when=lambda ctx: c.adjacent(foe))
        return
    c.grants_advantage(on=foe, to="me", until=When.ENCOUNTER)


@power("p11796", level=10, cls="x7_643", usage=ENCOUNTER, action=INTERRUPT,
       reach=CloseBurst(1), target=ONE_ALLY, keywords=[Keyword.MARTIAL],
       trigger="you are hit by an attack",
       on=Trigger(Hit, targets_me, "you are hit by an attack"))
def p11796(c: Cast) -> None:
    """`ONE_ALLY` is "you or one ally" -- the pool includes the caster -- so
    the two printed halves are one target line and a test on who was
    picked."""
    if c.target == c.me:
        c.spend_surge(on=c.me)
        c.temp_hp(c.surge_value(of=c.me), on=c.me)
    else:
        c.redirect(to=c.target)


# ---------------------------------------------------------------- x7_673 --
# Everything here turns on standing apart from the party.


@power("p12360", level=0, cls="x7_673", usage=ENCOUNTER, action=STANDARD,
       reach=MeleeOrRanged(1, by_weapon=True), target=ONE_CREATURE,
       keywords=[Keyword.PRIMAL, Keyword.WEAPON],
       attack=Attack(Pick.PRIMARY, vs=AC))
def p12360(c: Cast) -> None:
    """"Before or after the attack" is a choice with no consequence the
    board can tell apart once the swing is at melee reach, so the shift is
    taken first. The extra damage reads the roll's own `advantage`; asking
    the board again would be too late."""
    if _lonely(c):
        c.shift(1, who=c.me)
    res = c.strike(plus=_best(c) - c.attack_mod)
    if res:
        c.damage(c.w(), _best(c) * (2 if res.advantage else 1))


@power("p12361", level=2, cls="x7_673", usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF, keywords=[Keyword.PRIMAL],
       trigger="you start your turn while not adjacent to any of your allies",
       on=Trigger(
           TurnStart,
           both(lambda w, me, ev: getattr(ev, "actor", None) == me,
                lambda w, me, ev: _lonely_now(w, me)),
           "you start your turn away from your allies",
       ))
def p12361(c: Cast) -> None:
    """"You do not expend this power" is `c.restore_use`: the use has
    already been spent by the time the body runs."""
    if not c.save(on=c.me, bonus=c.primary_mod):
        c.restore_use(c.ref)


@power("p12362", level=3, cls="x7_673", usage=ENCOUNTER, action=STANDARD,
       reach=MeleeOrRanged(1, by_weapon=True), target=ONE_CREATURE,
       keywords=[Keyword.PRIMAL, Keyword.WEAPON],
       attack=Attack(Pick.PRIMARY, vs=AC))
def p12362(c: Cast) -> None:
    foe = c.target
    apart = _lonely(c) and not c.within(1, of=foe, side="ally")
    if c.strike(plus=_best(c) - c.attack_mod,
                advantage=True if apart else None):
        c.damage(c.w(2), _best(c))
        c.grants_advantage(on=foe, to="me")


@power("p12363", level=5, cls="x7_673", usage=DAILY, action=STANDARD,
       reach=MeleeOrRanged(1, by_weapon=True), target=ONE_CREATURE,
       keywords=[Keyword.PRIMAL, Keyword.WEAPON],
       attack=Attack(Pick.PRIMARY, vs=AC),
       dropped=("c.shift(toward=)", "c.ignores_difficult(when=)"))
def p12363(c: Cast) -> None:
    """The free shift is laid as a watch on the caster's own turn start.
    Two clauses of it have nowhere to go: the shift must end closer to the
    target, and it alone ignores difficult terrain -- laying
    `c.ignores_difficult` for the turn would exempt the whole of it."""
    foe = c.target
    if c.strike(plus=_best(c) - c.attack_mod):
        c.damage(c.w(2), _best(c))
    else:
        c.half_damage(c.w(2), _best(c))

    def prowl(ev: Any) -> None:
        if ev.actor != c.me or c.adjacent(foe) or not _lonely(c):
            return
        c.shift(c.primary_mod, who=c.me)

    c.watch(TurnStart, prowl, until=When.ENCOUNTER, on=c.me)


@power("p12364", level=6, cls="x7_673", usage=ENCOUNTER, action=REACTION,
       reach=PERSONAL, target=NO_TARGET, keywords=[Keyword.PRIMAL],
       trigger="an enemy hits you while you are not adjacent to any ally",
       on=Trigger(
           Hit,
           both(targets_me, lambda w, me, ev: _lonely_now(w, me)),
           "an enemy hits you while you stand apart",
       ))
def p12364(c: Cast) -> None:
    foe = getattr(c.trigger, "attacker", None)
    c.shift(c.primary_mod, who=c.me)
    if foe is not None:
        c.grants_advantage(on=foe, to="me")


@power("p12365", level=7, cls="x7_673", usage=ENCOUNTER, action=STANDARD,
       reach=MeleeOrRanged(1, by_weapon=True), target=ONE_CREATURE,
       keywords=[Keyword.PRIMAL, Keyword.WEAPON],
       attack=Attack(Pick.PRIMARY, vs=AC))
def p12365(c: Cast) -> None:
    """"Doesn't move at least 2 squares" is counted off `Moved`, which is
    the only one of the three movement events carrying `from_`; the
    distance is the length of the line between the two squares. The payout
    is hung on the target's `TurnEnd` and fires once."""
    foe = c.target
    if not c.strike(plus=_best(c) - c.attack_mod):
        return
    c.damage(c.w(), _best(c))
    walked = [0]
    spent = []

    def step(ev: Any) -> None:
        if ev.actor == foe:
            walked[0] += max(1, len(c.line(ev.from_, ev.to)) - 1)

    def settle(ev: Any) -> None:
        if ev.actor != foe or spent:
            return
        spent.append(1)
        if walked[0] < 2:
            c.flat(5 + _best(c), on=foe)

    c.watch(Moved, step, until=When.ENCOUNTER, on=c.me)
    c.watch(TurnEnd, settle, until=When.ENCOUNTER, on=c.me)


@power("p12366", level=9, cls="x7_673", usage=DAILY, action=STANDARD,
       reach=Melee(1), target=ONE_CREATURE,
       keywords=[Keyword.PRIMAL, Keyword.WEAPON],
       attack=Attack(Pick.PRIMARY, vs=AC))
def p12366(c: Cast) -> None:
    """The penalty is the number of hits, so it is counted and laid once
    rather than stacked per swing -- two of a kind would not add anyway."""
    swings = 3 if _lonely(c) else 2
    landed = 0
    for _ in range(swings):
        if c.strike(plus=_best(c) - c.attack_mod):
            landed += 1
            c.damage(0, 5 + _best(c))
        else:
            c.half_damage(0, 5 + _best(c))
    if landed:
        c.penalty("attack", landed, until=When.SAVE_ENDS)


@power("p12367", level=10, cls="x7_673", usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF,
       keywords=[Keyword.PRIMAL, Keyword.STANCE])
def p12367(c: Cast) -> None:
    """The stance ends itself from a watch on the caster's own turn end,
    which is where the printed condition is checked."""
    held = c.stance(on=c.me)
    c.resist(7, until=When.STANCE, on=c.me)

    def check(ev: Any) -> None:
        if ev.actor == c.me and not _lonely(c):
            c.end_effect(held, on=c.me)

    c.watch(TurnEnd, check, until=When.STANCE, on=c.me)


# --------------------------------------------------------------- x7_1000 --


@power("p16569", level=0, cls="x7_1000", usage=ENCOUNTER, action=MINOR,
       reach=Melee(1), target=ONE_CREATURE, keywords=[Keyword.MARTIAL])
def p16569(c: Cast) -> None:
    """A bare "grants combat advantage" names no beneficiary, so it is the
    whole side -- `to="team"`, which puts the caster in."""
    c.grants_advantage(to="team", until=When.EOT)


@power("p16570", level=0, cls="x7_1000", usage=ENCOUNTER, action=STANDARD,
       reach=Ranged(10), target=ONE_CREATURE,
       keywords=[Keyword.MARTIAL, Keyword.FEAR])
def p16570(c: Cast) -> None:
    """The hold ends itself when the caster attacks the target, watched on
    `AttackDeclared` so it is gone before that attack resolves."""
    foe = c.target
    held = c.cannot_attack(against=c.me, until=When.EONT)

    def broken(ev: Any) -> None:
        if ev.attacker == c.me and ev.target == foe:
            c.end_effect(held, on=foe)

    c.watch(AttackDeclared, broken, until=When.EONT, on=c.me)


@power("p16571", level=2, cls="x7_1000", usage=AT_WILL, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=[Keyword.ARCANE],
       out_of_combat=True)
def p16571(c: Cast) -> None:
    """Folding a carried object into a ring and back. Nothing on a board
    reads what a creature is carrying for this, and the ring has no combat
    consequence of its own -- a finished row that does nothing."""


@power("p16572", level=6, cls="x7_1000", usage=ENCOUNTER, action=INTERRUPT,
       reach=CloseBurst(5), target=NO_TARGET, keywords=[Keyword.ARCANE],
       trigger="a creature hits you with a melee or a ranged attack",
       on=Trigger(Hit, both(targets_me, either(by_melee, by_ranged)),
                  "a creature hits you with a melee or ranged attack"),
       dropped=("c.darkvision()",))
def p16572(c: Cast) -> None:
    """The narrow half is written and the wide half waits on darkvision
    being a thing a creature can be asked about."""
    foe = getattr(c.trigger, "attacker", None)
    if foe is None:
        return
    c.penalty("attack", 2, on=foe, until=When.EONT,
              when=lambda ctx: ctx["target"] == c.me)


@power("p16573", level=10, cls="x7_1000", usage=ENCOUNTER, action=MOVE,
       reach=Ranged(5), target=ANY_CREATURE,
       keywords=[Keyword.ARCANE, Keyword.TELEPORTATION], dropped=FILTER)
def p16573(c: Cast) -> None:
    """"Of your size or smaller" is relative to the caster and `max_size`
    holds an absolute category, so the restriction is not in the header."""
    foe = c.target
    c.swap(foe)
    if foe in c.enemies():
        c.grants_advantage(on=foe, to="team", until=When.EOT)


# ---------------------------------------------------------------- x7_861 --


@power("p14163", level=0, cls="x7_861", usage=ENCOUNTER, action=MOVE,
       reach=PERSONAL, target=SELF, keywords=[Keyword.PRIMAL])
def p14163(c: Cast) -> None:
    """"+2 bonus" with no type word is untyped. Every gate here asks the board
    each time rather than snapshotting where anybody was standing -- this row
    is about who is in rough ground, and that changes on everybody's turn.

    The combat-advantage clause reads the **target's** square, which is why it
    waited: it is not a condition on any one enemy, so there was nowhere to lay
    it. `c.gains_advantage` holds it on the caster and is asked per swing."""
    c.ignores_difficult(on=c.me, until=When.EONT)
    c.move(c.speed_of(c.me), who=c.me)
    for d in (AC, REF):
        c.bonus(d, 2, on=c.me, until=When.EONT,
                when=lambda ctx: c.here in c.world.difficult())
    c.gains_advantage(
        lambda ctx: bool(query.squares(c.world, ctx["target"]) & c.world.difficult()),
        until=When.EONT, on=c.me,
    )


@power("p14164", level=2, cls="x7_861", usage=ENCOUNTER, action=MOVE,
       reach=PERSONAL, target=SELF, keywords=[Keyword.PRIMAL],
       narrative=("skill:athletics", "skill:acrobatics"))
def p14164(c: Cast) -> None:
    """The move is the combat half. The rest is a bonus to Athletics
    *to jump* and Acrobatics *to balance or reduce falling damage*, plus a
    running start on a jump -- none of which is rolled on a board, so an
    unnarrowed bonus would be wider than the card and a marker would name a
    mechanism nobody would ever build."""
    c.move(c.speed_of(c.me) + 2, who=c.me)


@power("p14165", level=6, cls="x7_861", usage=ENCOUNTER, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=[Keyword.PRIMAL],
       narrative=("skill:perception",))
def p14165(c: Cast) -> None:
    """The long-range clause is exact, and the advantage is narrowed by the
    *shape* of the power rather than by anything about the target.

    That narrowing is what waited: combat advantage was computed from the pair
    of creatures with no power in it at all. `ca_ctx` carries the ref now.
    "Area attack powers" is `area_burst` and `wall` -- the two kinds the card's
    word covers. Spelt out rather than matched on a prefix, because `Range`'s
    kinds are `close_burst` and `area_burst` and a test for "area" would be
    exactly as wrong either way round.

    The Perception bonus stays narrative -- it is narrowed to spotting hidden
    things, which a board never asks for."""
    c.ignores_long_range(on=c.me, until=When.EONT)

    from combat_engine.engine.dsl import get

    def shot_or_area(ctx: dict[str, Any]) -> bool:
        row = get(ctx.get("power", ""))
        return row is not None and row.reach.kind in ("ranged", "area_burst", "wall")

    c.gains_advantage(shot_or_area, until=When.EONT, on=c.me)


@power("p14166", level=10, cls="x7_861", usage=ENCOUNTER, action=INTERRUPT,
       reach=PERSONAL, target=SELF, keywords=[Keyword.PRIMAL],
       trigger="a trap attacks you",
       on=Trigger(
           AttackDeclared,
           both(targets_me,
                lambda w, me, ev: query.is_trap(w, ev.attacker)),
           "a trap attacks you",
       ))
def p14166(c: Cast) -> None:
    """The bonus is against that trap's attack and nothing else, so it is
    gated on the attacker in the context rather than spent with `once`."""
    trap = getattr(c.trigger, "attacker", None)
    c.shift(2, who=c.me)
    for d in (AC, REF):
        c.bonus(d, 4, kind="power", on=c.me, until=When.EOT,
                when=lambda ctx: ctx["attacker"] == trap)


# ---------------------------------------------------------------- x7_875 --


@power("p14217", level=0, cls="x7_875", usage=ENCOUNTER, action=MINOR,
       reach=CloseBurst(2), target=EACH_CREATURE,
       keywords=[Keyword.ARCANE, Keyword.FIRE, Keyword.ZONE])
def p14217(c: Cast) -> None:
    """No attack roll: the damage is dealt outright. The zone is one thing
    for the whole power, so it is laid on the first target."""
    c.flat(5, dtype=DamageType.FIRE)
    if not c.first:
        return
    zone = c.zone(c.area(), until=When.EONT)
    c.grants_in(zone, "attack", -2, side="enemy", kind="untyped")
    for d in (AC, FORT, REF, WILL):
        c.grants_in(zone, d, -2, side="enemy", kind="untyped")


@power("p14218", level=2, cls="x7_875", usage=DAILY, action=REACTION,
       reach=CloseBurst(5), target=NO_TARGET,
       keywords=[Keyword.ARCANE, Keyword.FIRE],
       trigger="an enemy within 5 squares of you hits you",
       on=Trigger(Hit, both(targets_me, enemy_within(5)),
                  "an enemy within 5 squares hits you"))
def p14218(c: Cast) -> None:
    """The die is rolled once for the effect, not once per creature. The
    class-feature clause is asked with `c.knows`, so a character without
    it simply adds nothing."""
    foe = getattr(c.trigger, "attacker", None)
    if foe is None:
        return
    extra = c.int_mod if c.knows("cf:warlock-f1s3") else 0
    burn = c.roll("1d6") + extra
    for who in c.within(1, of=foe):
        if who != foe:
            c.flat(burn, dtype=DamageType.FIRE, on=who)


@power("p14219", level=6, cls="x7_875", usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF,
       keywords=[Keyword.ARCANE, Keyword.FIRE, Keyword.STANCE],
       narrative=("skill:stealth",))
def p14219(c: Cast) -> None:
    """"If you already have fire resistance, increase it by 5" is a delta,
    because resistances of one type do not stack -- the larger wins -- so
    the row hands over the finished number.

    The Stealth half is a bonus while concealed, and no board rolls a
    Stealth check for hiding in shadow, so it has nowhere to go."""
    c.stance(on=c.me)
    have = c.resistances(on=c.me).get(DamageType.FIRE, 0)
    c.resist(have + 5 if have else 5, DamageType.FIRE, until=When.STANCE,
             on=c.me,
             when=lambda ctx: int(query.concealment_of(c.world, c.me, ctx)) > 0)
    if not c.knows("cf:warlock-f1s3"):
        return

    def boon(ev: Any) -> None:
        if ev.actor == c.me and ev.power == "cf:warlock-f4":
            c.bonus("damage", 4, kind="power", on=c.me, until=When.EONT,
                    dtype=DamageType.FIRE)

    c.watch(PowerUsed, boon, until=When.STANCE, on=c.me)


@power("p14220", level=10, cls="x7_875", usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF,
       keywords=[Keyword.ARCANE, Keyword.POLYMORPH],
       dropped=("c.no_surges()", "c.flat(unpreventable=)"))
def p14220(c: Cast) -> None:
    """Everything hangs on one sustained hold so the whole form ends
    together. Two clauses are short: nothing bars spending a healing surge
    while still allowing other healing, and the self-damage is printed as
    unpreventable, which `c.flat` cannot say."""
    held = c.effect(c.ref, until=When.SUSTAIN, on=c.me, sustain=MINOR)
    c.bonus(AC, 2, kind="power", on=c.me, until=When.SUSTAIN)
    c.mode("fly", c.speed_of(c.me), until=When.SUSTAIN, on=c.me)
    have = c.resistances(on=c.me).get(DamageType.FIRE, 0)
    c.resist(have + 5 if have else 5 + c.level, DamageType.FIRE,
             until=When.SUSTAIN, on=c.me)
    swung: list[int] = []

    def saw(ev: Any) -> None:
        if ev.attacker == c.me:
            swung.append(1)

    def settle(ev: Any) -> None:
        if ev.actor != c.me:
            return
        if not swung:
            c.flat(c.level, on=c.me)
        swung.clear()

    c.watch(AttackDeclared, saw, until=When.SUSTAIN, on=c.me)
    c.watch(TurnEnd, settle, until=When.SUSTAIN, on=c.me)
    if c.knows("cf:warlock-f1s3"):
        c.on_sustain(held, lambda: c.temp_hp(10, on=c.me))


# ---------------------------------------------------------------- x7_924 --


@power("p15940", level=0, cls="x7_924", usage=ENCOUNTER, action=STANDARD,
       reach=Melee(1), target=ONE_CREATURE, keywords=[Keyword.MARTIAL],
       attack=Attack(STR, vs=REF, plus=3), dropped=FILTER)
def p15940(c: Cast) -> None:
    """"Highest ability modifier" is exact rather than a stand-in, so the
    only marker here is the target line: `Target` has no filter for
    "granting combat advantage to you"."""
    foe = c.target
    if c.strike(plus=_best(c) - c.attack_mod):
        c.prone()
    friends = [a for a in c.within(1, of=foe, side="ally") if a != c.me]
    if friends:
        c.grant_attack(c.choose(friends, "who swings"), on=foe)


@power("p15941", level=2, cls="x7_924", usage=ENCOUNTER, action=REACTION,
       reach=PERSONAL, target=SELF, keywords=[Keyword.MARTIAL],
       trigger="an ally within 5 squares of you falls unconscious",
       on=Trigger(Dropped, ally_within(5),
                  "an ally within 5 squares falls unconscious"),
       dropped=("c.shift(toward=)",))
def p15941(c: Cast) -> None:
    """"You must end the move farther from your ally" is a direction on a
    move and nothing takes one."""
    c.shift(1, who=c.me)
    c.move(c.speed_of(c.me) + 2, who=c.me)


@power("p15942", level=6, cls="x7_924", usage=ENCOUNTER, action=INTERRUPT,
       reach=Melee(1), target=ONE_OTHER_ALLY, keywords=[Keyword.MARTIAL],
       trigger="an enemy hits you with a melee or a ranged attack",
       on=Trigger(Hit, both(targets_me, either(by_melee, by_ranged)),
                  "an enemy hits you with a melee or ranged attack"))
def p15942(c: Cast) -> None:
    """`to=` names one beneficiary, so "you and the target" is two grants."""
    ally = c.target
    c.redirect(to=ally)
    foe = getattr(c.trigger, "attacker", None)
    if foe is None:
        return
    c.grants_advantage(on=foe, to="me")
    c.grants_advantage(on=foe, to=ally)


@power("p15943", level=10, cls="x7_924", usage=ENCOUNTER, action=MINOR,
       reach=Melee(1), target=ONE_OTHER_ALLY,
       keywords=[Keyword.MARTIAL, Keyword.HEALING])
def p15943(c: Cast) -> None:
    """The ally *loses* the surge rather than spending it, so it is
    `c.spend_surge` and not `c.surge`; nobody is healed by it. The caster's
    own hit points come back from the caster's own surge value."""
    ally = c.target
    if not c.spend_surge(on=ally):
        c.flat(c.surge_value(of=ally), on=ally)
    c.heal(c.surge_value(of=c.me), on=c.me)


# ---------------------------------------------------------------- x7_942 --


@power("p16052", level=0, cls="x7_942", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       keywords=[Keyword.DIVINE, Keyword.FIRE, Keyword.FEAR],
       trigger="you hit an enemy with an attack",
       on=Trigger(Hit, by_me, "you hit an enemy with an attack"))
def p16052(c: Cast) -> None:
    """The penalty is only against attacks that include the caster, which
    is a gate on the attack context's `target`."""
    foe = getattr(c.trigger, "target", None)
    if foe is None or foe not in c.enemies():
        return
    c.flat(1 + _best(c), dtype=DamageType.FIRE, on=foe)
    c.penalty("attack", 2, on=foe, until=When.SONT,
              when=lambda ctx: ctx["target"] == c.me)


@power("p16053", level=2, cls="x7_942", usage=DAILY, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, keywords=[Keyword.DIVINE],
       trigger="you grant an ally a power bonus or a healing surge",
       todo=("EffectApplied.mods", "SurgeSpent.source"))
def p16053(c: Cast) -> None:
    """**Re-aimed off `EffectApplied.kind`.** `Event.kind` is a property on
    the base class returning the event's own type name, so that marker read
    as arrived on every event there is while the gap stayed wide open: the
    announcement carries a source, a target, a duration and a label, and
    nothing about the modifiers the effect holds -- so "a **power** bonus"
    cannot be told from any other kind. `SurgeSpent` still names only who
    spent, not who enabled it. Neither half of the printed trigger can be
    declared, so the row cannot fire at all and the working Effect below it
    has nothing to hang on."""


@power("p16054", level=6, cls="x7_942", usage=ENCOUNTER, action=MINOR,
       reach=CloseBurst(1), target=EACH_ENEMY,
       keywords=[Keyword.DIVINE, Keyword.CHARM])
def p16054(c: Cast) -> None:
    """"A single Bluff check" compared against every target, so the whole
    power is resolved on the first call rather than rolled once each."""
    if not c.first:
        return
    told = c.check("bluff")
    for foe in c.targets:
        if told.total > c.passive("insight", of=foe):
            c.grants_advantage(on=foe, to="me")


@power("p16055", level=10, cls="x7_942", usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF,
       keywords=[Keyword.DIVINE, Keyword.FEAR, Keyword.POLYMORPH],
       dropped=("c.darkvision()",))
def p16055(c: Cast) -> None:
    c.form(until=When.ENCOUNTER, label=c.ref)
    c.resist(10, DamageType.FIRE, until=When.ENCOUNTER, on=c.me)
    for d in (FORT, WILL):
        c.bonus(d, 2, kind="power", on=c.me, until=When.ENCOUNTER)
    for foe in c.enemies():
        if c.can_see(foe):
            c.penalty("attack", 2, on=foe, until=When.EONT)


# ---------------------------------------------------------------- x7_951 --


@power("p16109", level=0, cls="x7_951", usage=ENCOUNTER, action=STANDARD,
       reach=CloseBlast(3), target=EACH_CREATURE,
       keywords=[Keyword.ELEMENTAL], attack=Attack(STR, vs=FORT, plus=2))
def p16109(c: Cast) -> None:
    """The printed +2 is in the header; `plus=` carries only the step from
    the named ability to the largest one."""
    if c.strike(plus=_best(c) - c.attack_mod):
        c.damage("1d6", _best(c))
        c.prone()


@power("p16110", level=2, cls="x7_951", usage=DAILY, action=MINOR,
       reach=Melee(1), target=ONE_ALLY,
       keywords=[Keyword.ELEMENTAL, Keyword.HEALING],
       dropped=("c.aura(difficult=)",))
def p16110(c: Cast) -> None:
    """The rough ground follows the target, so it is an aura rather than a
    patch of zone -- and `c.aura` takes no terrain. A static `c.zone` would
    be right only until the target moved."""
    who = c.target
    if c.may("spend a healing surge", who=who):
        c.surge(on=who)
    for d in (AC, FORT, REF, WILL):
        c.bonus(d, 2, kind="power", on=who, until=When.EONT)


@power("p16111", level=6, cls="x7_951", usage=ENCOUNTER, action=MINOR,
       reach=PERSONAL, target=SELF,
       keywords=[Keyword.ELEMENTAL, Keyword.POLYMORPH], out_of_combat=True)
def p16111(c: Cast) -> None:
    """A disguise: the card says outright that the statistics do not
    change, and the only roll it names is somebody's Insight against the
    ruse. Nothing in a fight is different -- a finished row that does
    nothing."""


@power("p16112", level=10, cls="x7_951", usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=[Keyword.ELEMENTAL],
       dropped=("query.flanked()", "c.spread_advantage()"))
def p16112(c: Cast) -> None:
    """The aura is real and both riders on it are not.

    The first asks whether *every* member inside is flanked, which needs the
    question asked of a creature rather than of an attacker-target pair.

    The second is re-aimed off `c.grants_advantage(when=)`. That verb exists
    now and is not this: the card does not narrow a grant, it **copies** one --
    an enemy already granting advantage to any member of the aura grants it to
    all of them. The condition being copied is whatever `has_combat_advantage`
    happened to answer for somebody else, which nothing can ask on another
    creature's behalf and then re-publish."""
    c.aura(5, until=When.ENCOUNTER, on=c.me)


# ---------------------------------------------------------------- x7_982 --


@power("p16407", level=0, cls="x7_982", usage=ENCOUNTER, action=MOVE,
       reach=PERSONAL, target=SELF, keywords=[Keyword.ARCANE])
def p16407(c: Cast) -> None:
    """Adjacency is read *after* the caster's move, which is what "at the
    end of this movement" means."""
    c.move(c.speed_of(c.me), who=c.me)
    for friend in c.within(1, side="ally"):
        c.move(c.speed_of(friend), who=friend)


@power("p16408", level=2, cls="x7_982", usage=ENCOUNTER, action=INTERRUPT,
       reach=PERSONAL, target=SELF, keywords=[Keyword.ARCANE],
       trigger="you are stunned or dominated while you have a healing surge",
       on=Trigger(
           ConditionApplied,
           both(targets_me,
                lambda w, me, ev: ev.condition in
                (Condition.STUNNED, Condition.DOMINATED),
                lambda w, me, ev: getattr(
                    w.get(me, Health), "surges", 0) > 0),
           "you are stunned or dominated and have a surge left",
       ), dropped=("ConditionApplied.cancel",))
def p16408(c: Cast) -> None:
    """`ConditionApplied` is a plain announcement rather than a `Decision`,
    so an interrupt cannot refuse it and "instead of suffering the
    triggering effect" has to be undone rather than prevented. Curing it on
    the spot is the nearest thing; a rider reading "when you become
    stunned" would still have fired."""
    c.spend_surge(on=c.me)
    c.cure(Condition.STUNNED, Condition.DOMINATED, on=c.me)
    c.dazed(until=When.SAVE_ENDS, on=c.me)


@power("p16409", level=6, cls="x7_982", usage=ENCOUNTER, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=[Keyword.ARCANE])
def p16409(c: Cast) -> None:
    c.extra_action(MOVE, on=c.me)


@power("p16410", level=10, cls="x7_982", usage=DAILY, action=INTERRUPT,
       reach=PERSONAL, target=SELF, keywords=[Keyword.ARCANE],
       trigger="you are damaged by an attack",
       on=Trigger(DamageRolled, targets_me, "you are damaged by an attack"))
def p16410(c: Cast) -> None:
    """"Your next turn" counts one turn end forward when the blow lands on
    the caster's own turn, and fires on the very next one otherwise."""
    held = getattr(c.trigger, "amount", 0)
    kind = getattr(c.trigger, "dtype", DamageType.UNTYPED)
    c.reduce(held)
    skip = [1 if c.turn_of() == c.me else 0]
    spent: list[int] = []

    def later(ev: Any) -> None:
        if ev.actor != c.me or spent:
            return
        if skip[0]:
            skip[0] = 0
            return
        spent.append(1)
        c.flat(held, dtype=kind, on=c.me)

    c.watch(TurnEnd, later, until=When.ENCOUNTER, on=c.me)


# ---------------------------------------------------------------- x7_991 --


def _far_from_allies(world: World, eid: int) -> bool:
    """"You must be at least 5 squares away from your allies." A character
    with no allies on the board meets it."""
    return all(
        query.distance_between(world, eid, friend) >= 5
        for friend in query.allies(world, eid)
    )


@power("p16454", level=0, cls="x7_991", usage=ENCOUNTER, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=[Keyword.MARTIAL],
       requires=_far_from_allies,
       requires_text="must be at least 5 squares away from your allies")
def p16454(c: Cast) -> None:
    c.bonus("attack", 2, kind="power", on=c.me, until=When.EONT)
    for d in (AC, FORT, REF, WILL):
        c.bonus(d, 2, kind="power", on=c.me, until=When.EONT)


@power("p16455", level=2, cls="x7_991", usage=ENCOUNTER,
       action=ActionType.NONE, reach=PERSONAL, target=SELF,
       keywords=[Keyword.MARTIAL],
       trigger="you miss with an attack or fail a check or a saving throw",
       on=(Trigger(Miss, by_me, "you miss with an attack roll"),
           Trigger(SkillCheck, both(my_check(), check_failed),
                   "you fail a skill check"),
           Trigger(SavingThrow,
                   both(lambda w, me, ev: getattr(ev, "actor", None) == me,
                        lambda w, me, ev: not ev.saved),
                   "you fail a saving throw")),
       todo=("c.on_reroll()",))
def p16455(c: Cast) -> None:
    """The whole Effect is a reroll held over a window and spent on some
    *later* roll of the character's choosing. `c.reroll_check` and
    `c.reroll_attack` both act on the roll being answered, which is
    exactly the one the card excludes."""


@power("p16456", level=6, cls="x7_991", usage=ENCOUNTER, action=REACTION,
       reach=PERSONAL, target=SELF,
       keywords=[Keyword.MARTIAL, Keyword.HEALING],
       trigger="an ally within 5 squares is healed and you are not",
       on=Trigger(Healed, both(ally_within(5), leaves_me_out),
                  "an ally within 5 squares is healed without you"))
def p16456(c: Cast) -> None:
    c.surge(on=c.me)


def _by_close_or_area(world: World, me: int, ev: Any) -> bool:
    """"A close or area attack" -- read off the row that swung, the way
    `by_melee` reads it."""
    from combat_engine.engine.dsl import get

    p = get(getattr(ev, "power", "") or "")
    if p is None:
        return False
    return p.reach_of(getattr(ev, "branch", 0)).kind in (
        "close_burst", "close_blast", "area_burst",
    )


@power("p16457", level=10, cls="x7_991", usage=ENCOUNTER, action=INTERRUPT,
       reach=PERSONAL, target=SELF, keywords=[Keyword.MARTIAL],
       trigger="you are hit by a close or area attack",
       on=Trigger(Hit, both(targets_me, _by_close_or_area),
                  "you are hit by a close or area attack"))
def p16457(c: Cast) -> None:
    c.shift(c.speed_of(c.me), who=c.me)


# --------------------------------------------------------------- x7_1004 --


@power("p16588", level=0, cls="x7_1004", usage=ENCOUNTER, action=MINOR,
       reach=AreaBurst(1, 10), target=EACH_CREATURE,
       keywords=[Keyword.ARCANE, Keyword.IMPLEMENT, Keyword.ACID],
       attack=Attack(STR, vs=FORT))
def p16588(c: Cast) -> None:
    if c.strike(plus=_best(c) - c.attack_mod):
        c.damage(0, _best(c), dtype=DamageType.ACID)
        c.slowed()


@power("p16589", level=2, cls="x7_1004", usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=[Keyword.ARCANE],
       out_of_combat=True)
def p16589(c: Cast) -> None:
    """Thievery, and Strength checks to force open or break wooden and
    metal objects. A board rolls neither -- doors and locks are not on it
    -- so the whole printed Effect is deliberately inert."""


@power("p16590", level=6, cls="x7_1004", usage=ENCOUNTER, action=MINOR,
       reach=CloseBurst(2), target=NO_TARGET,
       keywords=[Keyword.ARCANE, Keyword.ZONE],
       dropped=("c.grant_action(move)",))
def p16590(c: Cast) -> None:
    """"Difficult for your enemies" is the zone being rough plus the
    caster's side exempted inside it; `c.ignores_difficult` alone would
    exempt them everywhere. The free hop between two squares of the zone is
    an action `actions.legal` does not know, and a word it does not know is
    carried, costs nothing and does nothing."""
    zone = c.zone(c.area(), difficult=True, until=When.EONT)
    c.ignores_difficult_in(zone, side="team")


@power("p16591", level=10, cls="x7_1004", usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=[Keyword.ARCANE],
       todo=("c.tremorsense()",))
def p16591(c: Cast) -> None:
    """The whole Effect is one sense the engine has not got.
    `c.truesight` and `c.see_invisible` are a different question -- seeing
    what is hidden from sight -- and granting one of those instead would be
    a row that reads finished and is not the printed rule."""


# --------------------------------------------------------------- x7_1018 --


@power("p16675", level=0, cls="x7_1018", usage=ENCOUNTER, action=MOVE,
       reach=PERSONAL, target=SELF)
def p16675(c: Cast) -> None:
    """The Stealth check is gated on actually having cover or concealment
    at the end of the shift, which is asked of the board rather than
    assumed -- `query.cover_between` needs somebody to measure from, so the
    check is against whoever can still see the caster."""
    c.shift(c.speed_of(c.me), who=c.me)
    watchers = c.enemies()
    if not watchers:
        return
    hidden = all(
        int(query.cover_between(c.world, foe, c.me)) > 0
        or int(query.concealment_of(c.world, c.me)) > 0
        for foe in watchers
    )
    if hidden and c.check("stealth"):
        c.hide(until=When.ENCOUNTER)


@power("p16676", level=2, cls="x7_1018", usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=SELF,
       trigger="you dislike a Bluff, Insight, Perception or Stealth check",
       on=Trigger(SkillCheck,
                  my_check("bluff", "insight", "perception", "stealth"),
                  "you make one of four checks and dislike the result"))
def p16676(c: Cast) -> None:
    c.reroll_check(keep="best")


def _two_adjacent(world: World, eid: int) -> bool:
    """"At least two creatures must be within 1 square of you.\""""
    return sum(
        1
        for other in query.creatures(world)
        if other != eid and query.adjacent(world, eid, other)
    ) >= 2


@power("p16677", level=6, cls="x7_1018", usage=ENCOUNTER, action=MINOR,
       reach=PERSONAL, target=SELF, requires=_two_adjacent,
       requires_text="at least two creatures within 1 square that can see and hear you",
       dropped=("c.move_through()",))
def p16677(c: Cast) -> None:
    """One Bluff check against the best passive Insight adjacent, because
    beating one creature beats all of them. The rider on the theme's own
    move -- shifting through enemy spaces -- has no verb."""
    near = [w for w in c.within(1) if w != c.me]
    if not near:
        return
    told = c.check("bluff")
    if any(told.total > c.passive("insight", of=w) for w in near):
        c.hide(until=When.ENCOUNTER)


@power("p16678", level=10, cls="x7_1018", usage=DAILY, action=STANDARD,
       reach=PERSONAL, target=SELF, todo=("c.on_reroll()",))
def p16678(c: Cast) -> None:
    """"Roll twice and take the higher" standing over a whole encounter is
    not `c.reroll_check`, which answers one settled roll. Perfect recall is
    the other clause and has no combat half at all, so there is nothing
    here that plays."""


# ---------------------------------------------------------------- x7_889 --
# All three are the Fortune Card deck, which the engine has no model of:
# no hand, no draw, no discard, and no card types to branch on.

FORTUNE = ("c.draw()",)


@power("p14363", level=2, cls="x7_889", usage=ENCOUNTER, action=MINOR,
       reach=PERSONAL, target=SELF, todo=FORTUNE)
def p14363(c: Cast) -> None:
    """Draw two, keep one. There is no deck to draw from."""


@power("p14364", level=6, cls="x7_889", usage=DAILY, action=MINOR,
       reach=CloseBurst(5), target=EACH_ALLY, todo=FORTUNE)
def p14364(c: Cast) -> None:
    """Three different effects depending on which sort of card was
    discarded, and nothing knows a card's sort -- or that one was
    discarded, which is also the Requirement."""


@power("p14365", level=10, cls="x7_889", usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, todo=FORTUNE)
def p14365(c: Cast) -> None:
    """Draw three and raise the hand limit for the encounter."""


# ---------------------------------------------------------------- x7_999 --


@power("p16566", level=2, cls="x7_999", usage=ENCOUNTER, action=MINOR,
       reach=Melee(1), target=ONE_OTHER_ALLY, keywords=[Keyword.DIVINE],
       dropped=FILTER)
def p16566(c: Cast) -> None:
    """The temporary hit points arrive either way -- the card says so for
    the no-surge branch too. "Adjacent to your familiar" is a second reach
    the target line cannot hold."""
    ally = c.target
    if not c.spend_surge(on=ally):
        c.flat(c.surge_value(of=ally), on=ally)
    c.temp_hp(c.surge_value(of=ally), on=c.me)


@power("p16567", level=6, cls="x7_999", usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF,
       keywords=[Keyword.DIVINE, Keyword.FEAR, Keyword.ILLUSION])
def p16567(c: Cast) -> None:
    """`c.cannot_attack` bars one named creature at a time, so the printed
    "enemies cannot attack you or your familiar" is a pair of holds per
    enemy."""
    pet = c.familiar()
    for foe in c.enemies():
        c.cannot_attack(on=foe, against=c.me, until=When.SONT)
        if pet is not None:
            c.cannot_attack(on=foe, against=pet, until=When.SONT)


@power("p16568", level=10, cls="x7_999", usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF,
       keywords=[Keyword.DIVINE, Keyword.POLYMORPH],
       dropped=("c.reach_of(power=)",))
def p16568(c: Cast) -> None:
    """"Change between forms as a minor action" is `revert=`, which is what
    that argument is for. Longer melee reach is written as the opportunity
    threat only: nothing widens the reach a melee row is *used* at."""
    c.form(until=When.ENCOUNTER, revert=MINOR, label=c.ref)
    c.bonus(WILL, 2, kind="power", on=c.me, until=When.ENCOUNTER)
    c.threatens(2, on=c.me, until=When.ENCOUNTER)
