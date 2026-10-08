"""Theme powers, fourteen themes.

`cls` is the theme's alias ref, the way a racial row is keyed by the race.

Two things run through the whole batch.

**"Primary ability vs. <defence>".** A theme never learns which class took
it, so its attack line names no ability and `Attack` needs one or a printed
bonus. Where the attack is the whole row that is a `todo=`; where the row
also has an Effect that stands on its own -- the conjurations, mostly -- the
Effect is written and the attack half is a `dropped=`. `c.best_ability()` is
the same hole for the rows that print "highest ability modifier", which is a
different sentence and already has its own group.

**Stances and conjurations.** A conjuration that pays out when dismissed is
`c.conjure` plus a holder effect made endable: `c.endable(hold, MINOR,
then=...)` is the printed "as a minor action you can dismiss it to ...", and
the aura around the conjuration is what "while adjacent to it" reads.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    ANY_CREATURE,
    AT_WILL,
    DAILY,
    DEFENCES,
    EACH_OTHER,
    ENCOUNTER,
    FREE,
    INTERRUPT,
    MELEE,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_ALLY,
    ONE_CREATURE,
    PERSONAL,
    RANGED,
    REACTION,
    REF,
    SELF,
    STANDARD,
    WILL,
    Ability,
    ActionType,
    Attack,
    Cast,
    CloseBurst,
    Condition,
    DamageType,
    Health,
    Keyword,
    Melee,
    Pick,
    Ranged,
    Trigger,
    Usage,
    When,
    World,
    about_me,
    both,
    by_me,
    by_melee,
    by_ranged,
    get,
    power,
    query,
    targets_me,
    would_hit_me,
)
from combat_engine.engine.components import Companion, Conjuration, Position
from combat_engine.engine.events import (
    AdjacencyGained,
    AttackRolled,
    Bloodied,
    DamageApplied,
    DamageRolled,
    Hit,
    InitiativeRolled,
    Miss,
    PowerResolved,
    SavingThrow,
    SurgeSpent,
    TurnEnd,
)
from combat_engine.engine.grid import spread

X7_654 = "x7_654"
X7_676 = "x7_676"
X7_850 = "x7_850"
X7_855 = "x7_855"
X7_864 = "x7_864"
X7_887 = "x7_887"
X7_927 = "x7_927"
X7_945 = "x7_945"
X7_974 = "x7_974"
X7_986 = "x7_986"
X7_994 = "x7_994"
X7_1008 = "x7_1008"
X7_1010 = "x7_1010"
X7_1022 = "x7_1022"

PRIMAL_CONJ = [Keyword.PRIMAL, Keyword.CONJURATION]
PRIMAL_IMPL_CONJ = [Keyword.PRIMAL, Keyword.IMPLEMENT, Keyword.CONJURATION]

#: The theme's attack line is "Primary ability vs. X" and a theme does not
#: know which class took it.
PRIMARY = ("c.ability_for(ref)",)


def _bloodied(world: World, eid: int) -> bool:
    health = world.get(eid, Health)
    return health is not None and health.hp * 2 <= health.max_hp


def _minion_within(world: World, eid: int, reach: int) -> bool:
    """"Your animal minion must be within N squares of you." """
    for other in query.creatures(world):
        pet = world.get(other, Companion)
        if pet is not None and pet.owner == eid:
            return query.distance_between(world, eid, other) <= reach
    return False


def _at_will_weapon(ref: str) -> bool:
    """A basic attack, or an at-will weapon attack power."""
    if ref in (MELEE, RANGED):
        return True
    p = get(ref)
    return p is not None and p.usage is Usage.AT_WILL and Keyword.WEAPON in p.keywords


def _weapon_attack(ref: str) -> bool:
    """A melee or ranged weapon attack power."""
    if ref in (MELEE, RANGED):
        return True
    p = get(ref)
    if p is None or Keyword.WEAPON not in p.keywords or p.attack_of(0) is None:
        return False
    return p.reach_of(0).kind in ("melee", "ranged")


def _by_attack(ref: str) -> bool:
    """Did an attack deal this, rather than a burn or an ongoing?"""
    p = get(ref)
    return p is not None and p.attack_of(0) is not None


def _defences(c: Cast, value: int, *, until: When, on: int | None = None) -> None:
    """"A +N power bonus to all defenses" -- all four, not just AC."""
    who = c.me if on is None else on
    for defence in DEFENCES:
        c.bonus(defence, value, kind="power", on=who, until=until)


def _primary(c: Cast) -> int:
    """"Primary ability vs. X" as an attack bonus, for a **secondary** attack.

    A row whose own action is the attack says this in its header --
    `Attack(Pick.PRIMARY, ...)`, and then `c.attack_mod` follows whatever it
    resolved to. The x7_654 rows print their attack inside an Effect, as
    something the caster spends a *later* standard action on, so there is no
    header line for it to be and the pair is joined up here: `c.primary` says
    which ability, and the per-ability property is the whole bonus with half
    level, proficiency and enhancement already in it.
    """
    return {
        Ability.STR: c.str_,
        Ability.CON: c.con_,
        Ability.DEX: c.dex_,
        Ability.INT: c.int_,
        Ability.WIS: c.wis_,
        Ability.CHA: c.cha_,
    }[c.primary]


# -- x7_654: conjured elementals ---------------------------------------------


@power(
    "p11804",
    level=0,
    cls=X7_654,
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(5),
    target=NO_TARGET,
    keywords=PRIMAL_IMPL_CONJ,
)
def p11804(c: Cast) -> None:
    """A spirit with a defence aura, and a standard action that spends it on
    one swing.

    The dismissal is `c.endable` with a `STANDARD` cost -- the same shape
    `p11807` uses for its minor -- so the option appears on the caster's card
    and the payout is the attack. `from_=spirit` is what makes it a melee 1
    from the spirit's square while the numbers stay the caster's.

    The -2 is untyped: the card prints "a -2 penalty" with no type word, so it
    must not go through `_defences`, which lays a *power* bonus.
    """
    spirit = c.conjure(until=When.ENCOUNTER, sustain=None)
    ring = c.aura(1, on=spirit, until=When.ENCOUNTER, label=c.ref)
    for defence in DEFENCES:
        c.grants_in(ring, defence, 1, side="team", kind="power")
    hold = c.effect(c.ref, until=When.ENCOUNTER, on=c.me)

    def dismiss() -> None:
        near = sorted(c.within(1, of=spirit, side="enemy"))
        foe = c.choose(near, "who to strike from it") if near else None
        if foe is not None and c.attack(_primary(c), REF, on=foe, from_=spirit):
            c.damage("1d10", c.primary_mod, on=foe)
            c.penalty("attack", 2, on=foe, until=When.EONT)
            for defence in DEFENCES:
                c.penalty(defence, 2, on=foe, until=When.EONT)
        c.dispel(spirit)

    c.endable(hold, STANDARD, then=dismiss)


@power(
    "p11807",
    level=2,
    cls=X7_654,
    usage=DAILY,
    action=MINOR,
    reach=Ranged(5),
    target=NO_TARGET,
    keywords=PRIMAL_CONJ,
)
def p11807(c: Cast) -> None:
    """The dismissal is a holder effect made endable for a minor action --
    ending it is what pays the temporary hit points out and banishes the
    conjuration."""
    spirit = c.conjure(until=When.ENCOUNTER, sustain=None)
    ring = c.aura(1, on=spirit, until=When.ENCOUNTER, label=c.ref)
    for defence in DEFENCES:
        c.grants_in(ring, defence, 1, side="team", kind="power")
    hold = c.effect(c.ref, until=When.ENCOUNTER, on=c.me)

    def dismiss() -> None:
        amount = 5 + c.level // 2
        c.temp_hp(amount, on=c.me)
        for ally in c.within(1, of=spirit, side="ally"):
            c.temp_hp(amount, on=ally)
        c.dispel(spirit)

    c.endable(hold, MINOR, then=dismiss)


@power(
    "p11808",
    level=3,
    cls=X7_654,
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(5),
    target=NO_TARGET,
    keywords=PRIMAL_IMPL_CONJ,
)
def p11808(c: Cast) -> None:
    """"Enemies grant combat advantage while adjacent to it" is written now.

    It is geometry rather than a duration -- the question has to be re-asked
    as creatures move in and out -- and that is exactly what
    `c.grants_advantage(when=)` is: a gated modifier that
    `query.has_combat_advantage` reads with the attack context, rather than a
    relation, which carries no predicate. `ctx["target"]` is the creature
    being asked about, so the gate is `c.adjacent_to(spirit, that creature)`.

    Laid once per live enemy, which is what the relation's arity forces. An
    enemy that arrives *after* this is cast is not covered -- the card says
    "enemies", not "these enemies" -- and that is a smaller miss than the
    whole clause was.

    **And the dismissal is written.** "As a standard action, you can dismiss it
    and make a close burst 1 attack centred on its square" is `c.endable` with a
    `then=` -- the offer is `Effect.drop_cost`, which `actions.legal` hands to
    whoever conjured it, and `drop_then` is a payout that runs for a deliberate
    dismissal and for nothing else. Not for the clock, which is right: the card
    pays for *choosing*, and a spirit that simply expires attacks nobody.

    The burst is centred on the spirit's square, **captured when it is
    conjured**, and that is correct here rather than lazy: `drop_then` runs
    *after* the effect ends, the effect's `on_end` despawns the conjuration, so
    by the time the payout runs there is no entity left to measure from. This
    spirit is conjured with no `speed`, so it cannot be moved and its square at
    dismissal is the square it was made on.
    
    A conjuration that *can* be walked would need the live square and there is
    nowhere to read it from at that moment -- noted in #296 rather than worked
    around, because no row in the tree wants it yet.

    `c.ability_for()` is the damage line's "+ ability modifier", which is the
    thing `PRIMARY` was asking for and which exists. See #296.
    """
    spirit = c.conjure(until=When.EONT, sustain=None)
    c.aura(1, on=spirit, until=When.EONT, label=c.ref)

    where = c.world.get(spirit, Position).square

    def dismissed() -> None:
        near = spread({where}, 1)
        for foe in sorted(f for f in c.enemies()
                          if (at := c.world.get(f, Position)) is not None
                          and at.squares & near):
            # Longhand, because this row declares no attack line and should not:
            # casting it conjures and attacks nobody, and the swing belongs to the
            # dismissal. `c.ability_for()` is the card's "Primary ability", which
            # falls back to the best modifier on the sheet for a row with no
            # declared line -- which is what Primary means.
            if c.attack(c.attack_with(c.ability_for()), REF, on=foe):
                c.damage("1d10", c.mod(c.ability_for()), on=foe)
                # `c.cannot_shift` bars a shift and leaves being shoved alone, which is
                # what "the target can't shift" says -- `c.immobilized` would stop
                # it walking too.
                c.cannot_shift(on=foe, until=When.EONT)

    conj = c.world.get(spirit, Conjuration)
    if conj is not None:
        c.endable(c.world.effects.live.get(conj.effect), STANDARD, then=dismissed)

    def beside(ctx: dict[str, Any]) -> bool:
        who = ctx.get("target")
        return who is not None and c.adjacent_to(spirit, who)

    for foe in c.enemies():
        c.grants_advantage(on=foe, until=When.EONT, to="team", when=beside)


@power(
    "p11811",
    level=5,
    cls=X7_654,
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=PRIMAL_CONJ,
    dropped=("c.grants_in(dice=)",),
)
def p11811(c: Cast) -> None:
    """The attack bonus is written. The "+1d6 to damage rolls on melee
    attacks" half wants a rolled modifier on a zone.

    **One marker now, not two.** The gate half arrived -- `c.grants_in` takes
    `when=` and narrowing to melee is a lambda -- but a gate on a bonus that
    cannot be rolled buys nothing, so the whole clause still waits on `dice=`.
    Two symbols for one clause meant this row would have reported ready when
    only the useless half of it landed."""
    made: list[int] = []
    for _ in range(4):
        elemental = c.conjure(until=When.ENCOUNTER, sustain=None)
        if not elemental:
            continue
        made.append(elemental)
        ring = c.aura(1, on=elemental, until=When.ENCOUNTER, label=c.ref)
        c.grants_in(ring, "attack", 1, side="ally", kind="power")
    hold = c.effect(c.ref, until=When.ENCOUNTER, on=c.me)

    def dismiss() -> None:
        for elemental in list(made):
            near = c.within(1, of=elemental, side="ally")
            if not near:
                continue
            made.remove(elemental)
            c.dispel(elemental)
            c.grant_attack(near[0])
            return

    c.endable(hold, MINOR, then=dismiss)


@power(
    "p11814",
    level=6,
    cls=X7_654,
    usage=DAILY,
    action=MINOR,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=PRIMAL_CONJ,
)
def p11814(c: Cast) -> None:
    """`speed=1` is the printed "you can move the elemental 1 square"; the
    engine spends a move action on it rather than the free window the card
    opens at the start of your turn, which is the only difference."""
    elemental = c.conjure(until=When.ENCOUNTER, sustain=None, speed=1)

    def shove(ev: TurnEnd) -> None:
        if ev.actor != elemental and c.adjacent_to(elemental, ev.actor):
            c.push(1, on=ev.actor, by=elemental)

    c.watch(TurnEnd, shove, until=When.ENCOUNTER, on=c.me)
    hold = c.effect(c.ref, until=When.ENCOUNTER, on=c.me)

    def dismiss() -> None:
        near = c.within(1, of=elemental, side="ally")
        if near:
            c.shift(5, who=near[0])
        c.dispel(elemental)

    c.endable(hold, MINOR, then=dismiss)


@power(
    "p11815",
    level=7,
    cls=X7_654,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=PRIMAL_IMPL_CONJ,
)
def p11815(c: Cast) -> None:
    """An elemental with an attack aura, spent on one swing that drags its
    target back to it.

    "2 damage for each bloodied ally with line of sight to the elemental" is
    counted at the moment the swing lands rather than when the elemental was
    conjured, which is what the card asks and is why it is inside `strike`.
    `query.sees_through` is the sight question asked of somebody other than
    the caster -- `c.can_see` only ever answers for the caster.

    The slide names its square rather than a distance, because "3 squares **to
    a square adjacent to the elemental**" is a destination and `c.slide`
    takes one.
    """
    elemental = c.conjure(until=When.EONT, sustain=None)
    ring = c.aura(1, on=elemental, until=When.EONT, label=c.ref)
    c.grants_in(ring, "attack", 1, side="team", kind="power")
    hold = c.effect(c.ref, until=When.EONT, on=c.me)

    def strike() -> None:
        near = sorted(c.within(1, of=elemental, side="enemy"))
        foe = c.choose(near, "who to strike from it") if near else None
        if foe is not None and c.attack(_primary(c), WILL, on=foe, from_=elemental):
            watching = sum(
                1
                for ally in c.within(20, side="team")
                if c.bloodied(on=ally)
                and query.sees_through(c.world, ally, elemental)
            )
            c.damage("2d8", c.primary_mod + 2 * watching, on=foe)
            beside = sorted(
                sq
                for sq in spread(query.squares(c.world, elemental), 1)
                if sq not in query.squares(c.world, elemental)
            )
            if beside:
                c.slide(3, on=foe, to=beside[0])
        c.dispel(elemental)

    c.endable(hold, STANDARD, then=strike)


@power(
    "p11818",
    level=9,
    cls=X7_654,
    usage=DAILY,
    action=MINOR,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=PRIMAL_IMPL_CONJ,
)
def p11818(c: Cast) -> None:
    """Four elementals, and one standard action that swings from every one of
    them still standing.

    **No damage on a hit at this level.** The card's Hit line is the restrain
    and the burn; the dice only arrive on the Level 19 and 29 lines, which are
    out of scope. Writing `2d6` here would be a paragon number in a heroic
    row.

    "One, two, three, or four creatures, each adjacent to at least one
    tortured elemental" is one target per elemental, chosen when the action is
    spent -- so it is a loop over the elementals rather than a `target=` on
    the header, which would have to name its creatures before any of them
    stood.

    An elemental is removed on a hit and stays on a miss, which is what makes
    this spendable four times over a fight.
    """
    standing = [c.conjure(until=When.ENCOUNTER, sustain=None) for _ in range(4)]
    hold = c.effect(c.ref, until=When.ENCOUNTER, on=c.me)

    def swing() -> None:
        for elemental in list(standing):
            near = sorted(c.within(1, of=elemental, side="enemy"))
            foe = c.choose(near, "who this one strikes") if near else None
            if foe is None:
                continue
            if c.attack(_primary(c), REF, on=foe, from_=elemental):
                c.condition(Condition.RESTRAINED, on=foe, until=When.SAVE_ENDS)
                c.ongoing(5, on=foe)
                standing.remove(elemental)
                c.dispel(elemental)
            else:
                c.slide(1, on=foe)
                c.slide(1, on=elemental)

    c.endable(hold, STANDARD, then=swing)


@power(
    "p11821",
    level=10,
    cls=X7_654,
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL, Keyword.HEALING, Keyword.CONJURATION],
)
def p11821(c: Cast) -> None:
    """An elemental that pays extra on a surge spent beside it, and can be
    spent to catch a dying ally.

    `SurgeSpent` is the event, and its docstring says why it exists: three
    places decremented a surge silently, so "when a creature spends a healing
    surge in this aura" could never see it. Adjacency is asked when the surge
    is spent rather than when the elemental was conjured.

    "Regains additional hit points" is healing and not temporary hit points,
    so it is `c.heal` -- the surge itself has already been paid out by
    whatever spent it.
    """
    elemental = c.conjure(until=When.ENCOUNTER, sustain=None)
    c.aura(1, on=elemental, until=When.ENCOUNTER, label=c.ref)
    hold = c.effect(c.ref, until=When.ENCOUNTER, on=c.me)

    def extra(ev: SurgeSpent) -> None:
        if hold is None or hold.ended or c.primary_mod <= 0:
            return
        # `side="team"` is the caster **and** allies, which is exactly "you
        # and each ally"; `"ally"` leaves the caster out and the card does not.
        if ev.actor not in c.within(1, of=elemental, side="team"):
            return
        c.heal(c.primary_mod, on=ev.actor)

    c.watch(SurgeSpent, extra, until=When.ENCOUNTER, on=c.me)

    def rescue(ev: SavingThrow) -> None:
        if ev.saved or ev.actor == c.me or hold is None or hold.ended:
            return
        if not c.is_(Condition.DYING, on=ev.actor) or not c.can_see(ev.actor):
            return
        c.surge(on=ev.actor)
        _defences(c, 4, until=When.SOTNT, on=ev.actor)
        c.dispel(elemental)
        c.end_effect(hold)

    c.watch(SavingThrow, rescue, until=When.ENCOUNTER, on=c.me)


# -- x7_676: the critical-hit psion ------------------------------------------


@power(
    "p12375",
    level=0,
    cls=X7_676,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(Pick.PRIMARY, vs=REF),
)
def p12375(c: Cast) -> None:
    """Psychic damage, and a wider critical range against that creature.

    **The modifier sits on the caster, not the target.** "*Your* attacks
    against the target" is a fact about your rolls, and `resolve.attack` reads
    `crit_range` off the attacker -- laid on the target it would be consulted
    by nothing. The narrowing is the attack context's `target`.

    18-20 is `crit_range` 2: `resolve.attack` computes the floor as
    `20 - crit_range`.
    """
    if not c.strike():
        return
    c.damage("1d8", c.attack_mod, dtype=DamageType.PSYCHIC)
    foe = c.target
    if foe is None:
        return
    c.bonus(
        "crit_range",
        2,
        on=c.me,
        until=When.EONT,
        when=lambda ctx: ctx.get("target") == foe,
    )


@power(
    "p12376",
    level=2,
    cls=X7_676,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PSIONIC],
)
def p12376(c: Cast) -> None:
    """Defences, and temporary hit points the first critical pays for.

    "If you score a critical hit" is one payment, not one per critical, so the
    watcher spends itself.
    """
    _defences(c, 2, until=When.EONT)
    paid = [False]

    def crit(ev: Hit) -> None:
        if paid[0] or ev.attacker != c.me or not ev.critical:
            return
        paid[0] = True
        c.temp_hp(5 + c.primary_mod, on=c.me)

    c.watch(Hit, crit, until=When.EONT, on=c.me)


@power(
    "p12377",
    level=3,
    cls=X7_676,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[
        Keyword.PSIONIC,
        Keyword.IMPLEMENT,
        Keyword.PSYCHIC,
        Keyword.FIRE,
    ],
    attack=Attack(Pick.PRIMARY, vs=REF),
)
def p12377(c: Cast) -> None:
    """Psychic damage, and a critical sets the target and its neighbours
    burning.

    Read off `c.result` rather than watched on `Hit`: the question is about
    *this* attack, which the cast is still holding, and a watcher would also
    answer for the next one.
    """
    if not c.strike():
        return
    c.damage("2d6", c.attack_mod, dtype=DamageType.PSYCHIC)
    foe = c.target
    if foe is None or not getattr(c.result, "critical", False):
        return
    c.ongoing(5, DamageType.FIRE, on=foe)
    for other in c.within(1, of=foe, side="enemy"):
        if other != foe:
            c.ongoing(5, DamageType.FIRE, on=other)


@power(
    "p12378",
    level=5,
    cls=X7_676,
    usage=DAILY,
    action=REACTION,
    reach=CloseBurst(2),
    target=EACH_OTHER,
    keywords=[
        Keyword.PSIONIC,
        Keyword.IMPLEMENT,
        Keyword.PSYCHIC,
        Keyword.FORCE,
    ],
    trigger="an enemy in the burst damages you with an attack",
    on=Trigger(DamageApplied, targets_me, "an enemy damages you with an attack"),
    attack=Attack(Pick.PRIMARY, vs=WILL),
)
def p12378(c: Cast) -> None:
    """A burst answering whoever hurt you, and a bonus each critical renews.

    Re-laying the bonus one point larger is what extends it: two power
    bonuses do not add and the larger wins, so the printed escalation is the
    same call with a bigger number rather than a delta.

    The Effect is under `c.first` now that the header declares targets -- the
    body runs once per creature in the burst, and the bonus is one bonus.
    """
    if c.first:
        step = [2]
        _defences(c, step[0], until=When.EONT)

        def sharpen(ev: Hit) -> None:
            if ev.attacker != c.me or not ev.critical:
                return
            step[0] += 1
            _defences(c, step[0], until=When.EONT)
            for foe in c.enemies():
                if c.distance(foe) <= 5:
                    c.flat(5, dtype=DamageType.PSYCHIC, on=foe)

        c.watch(Hit, sharpen, until=When.ENCOUNTER, on=c.me)
    if c.strike():
        c.damage("2d8", c.attack_mod, dtype=DamageType.FORCE)
        c.push(2)
    else:
        c.half_damage("2d8", c.attack_mod, dtype=DamageType.FORCE)


@power(
    "p12379",
    level=6,
    cls=X7_676,
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PSIONIC, Keyword.STANCE],
)
def p12379(c: Cast) -> None:
    """Resistance of one kind does not stack -- the highest applies -- so
    the escalation is the running total handed over again, not a delta."""
    c.stance(label=c.ref)
    held = [5]
    seen = [-1]
    c.resist(held[0], until=When.STANCE, on=c.me)

    def harden(ev: Hit) -> None:
        if ev.attacker != c.me or not ev.critical or held[0] >= 10:
            return
        if seen[0] == c.world.round:
            return
        seen[0] = c.world.round
        held[0] += 1
        c.resist(held[0], until=When.STANCE, on=c.me)

    c.watch(Hit, harden, until=When.STANCE, on=c.me)


@power(
    "p12380",
    level=7,
    cls=X7_676,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(Pick.PRIMARY, vs=WILL),
)
def p12380(c: Cast) -> None:
    """Psychic damage, and more of it plus a daze on a critical.

    `c.flat` and not a bigger `c.damage`: "takes 10 extra psychic damage" is a
    fixed amount, and `c.damage` maxes its dice on a critical -- which this
    roll already was.
    """
    if not c.strike():
        return
    c.damage("2d8", c.attack_mod, dtype=DamageType.PSYCHIC)
    if getattr(c.result, "critical", False):
        c.flat(10, dtype=DamageType.PSYCHIC)
        c.dazed(until=When.EONT)


@power(
    "p12381",
    level=9,
    cls=X7_676,
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(Pick.PRIMARY, vs=WILL),
)
def p12381(c: Cast) -> None:
    """A burn that punishes failing to shake it off, and a daze on any
    critical while it holds.

    The Effect applies whether or not the attack landed, so the strike is
    asked for the Hit line alone and the rest is laid either way.
    """
    victim = c.target
    if c.strike():
        c.damage("1d8", c.attack_mod, dtype=DamageType.PSYCHIC)
    burn = c.ongoing(5, DamageType.PSYCHIC, on=victim)

    def failed(ev: SavingThrow) -> None:
        if ev.actor != victim or ev.saved or burn is None or burn.ended:
            return
        c.flat(ev.natural + ev.bonus, dtype=DamageType.PSYCHIC, on=victim)

    def rattle(ev: Hit) -> None:
        if ev.attacker != c.me or not ev.critical or burn is None or burn.ended:
            return
        c.dazed(on=victim, until=When.EONT)

    c.watch(SavingThrow, failed, until=When.ENCOUNTER, on=c.me)
    c.watch(Hit, rattle, until=When.ENCOUNTER, on=c.me)


@power(
    "p12382",
    level=10,
    cls=X7_676,
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PSIONIC, Keyword.PSYCHIC, Keyword.STANCE],
)
def p12382(c: Cast) -> None:
    """"Damaged by an attack" is read off `DamageApplied.detail` -- the row
    that dealt it -- rather than off the source alone, so a burn or an
    ongoing does not pay the thorns out."""
    worn = c.stance(label=c.ref)

    def thorns(ev: DamageApplied) -> None:
        if ev.target != c.me or ev.source == c.me or ev.amount <= 0:
            return
        if not _by_attack(ev.detail):
            return
        c.flat(5, dtype=DamageType.PSYCHIC, on=ev.source)

    def spend(ev: Hit) -> None:
        if ev.attacker != c.me or not ev.critical or worn.ended:
            return
        c.end_effect(worn)
        c.flat(10, dtype=DamageType.PSYCHIC, on=ev.target)

    c.watch(DamageApplied, thorns, until=When.STANCE, on=c.me)
    c.watch(Hit, spend, until=When.STANCE, on=c.me)


# -- x7_850: the animal minion -----------------------------------------------


@power(
    "p14099",
    level=0,
    cls=X7_850,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_CREATURE,
    keywords=[Keyword.MARTIAL],
    requires=lambda world, eid: _minion_within(world, eid, 5),
    requires_text="your animal minion must be within 5 squares of you",
)
def p14099(c: Cast) -> None:
    """The Requirement is a board question asked afresh each round, so it is
    `requires=` rather than a gate inside the body."""
    c.grants_advantage(on=c.target, to="me", until=When.EOT)


@power(
    "p14100",
    level=2,
    cls=X7_850,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(10),
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL],
    requires=lambda world, eid: _minion_within(world, eid, 10),
    requires_text="your animal minion must be in the burst",
)
def p14100(c: Cast) -> None:
    """"Any action it is physically capable of performing" is a DM ruling.
    The two the engine can spend are the move and the minion's own attack
    line, and `c.command` rolls the second from the minion's numbers."""
    pet = c.companion()
    if pet is None:
        return
    c.move_companion(c.speed_of(pet))
    near = c.within(1, of=pet, side="enemy")
    if near:
        c.command(pet, on=near[0])


def _flanking_arrival(world: World, me: int, ev: object) -> bool:
    """An enemy steps into a square from which it flanks me, with my minion
    beside me. `AdjacencyGained` is where the mover has arrived, so the
    flank is a real question by the time this is asked."""
    mover = getattr(ev, "mover", 0)
    if mover in (0, me) or getattr(ev, "other", None) not in (me, mover):
        return False
    if not query.flanked_by(world, me, mover):
        return False
    return _minion_within(world, me, 1)


@power(
    "p14102",
    level=6,
    cls=X7_850,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PRIMAL],
    trigger=(
        "an enemy enters a square adjacent to you where it flanks you, "
        "and your animal minion is adjacent to you"
    ),
    on=Trigger(
        AdjacencyGained,
        _flanking_arrival,
        "an enemy moves adjacent to you and flanks you",
    ),
)
def p14102(c: Cast) -> None:
    c.cannot_be_flanked(on=c.me, until=When.EONT)
    _defences(c, 2, until=When.EONT)


@power(
    "p14103",
    level=10,
    cls=X7_850,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(100),
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL],
    requires=lambda world, eid: _minion_within(world, eid, 100),
    requires_text="you must have an animal minion",
    narrative=("skill:perception",),
)
def p14103(c: Cast) -> None:
    """Directing the minion is the combat half and is written, sustained.
    Sharing its senses is the other clause: the narrowing is "what the
    minion can see from where it stands", and a board rolls Perception only
    from the creature whose turn it is, so there is nowhere for a borrowed
    set of senses to be read and nothing is missing. Ranged 1 mile is off
    any board; 100 squares is the same thing in practice."""
    pet = c.companion()
    if pet is None:
        return
    hold = c.effect(c.ref, until=When.SUSTAIN, sustain=STANDARD, on=c.me)

    def direct() -> None:
        standing = c.companion()
        if standing is None:
            return
        c.move_companion(c.speed_of(standing))
        near = c.within(1, of=standing, side="enemy")
        if near:
            c.command(standing, on=near[0])

    direct()
    c.on_sustain(hold, direct)


# -- x7_855: the fortune teller ----------------------------------------------


@power(
    "p14141",
    level=0,
    cls=X7_855,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_ALLY,
    keywords=[Keyword.ARCANE],
    todo=("c.boost_roll()",),
)
def p14141(c: Cast) -> None:
    """Three recorded results standing in for the next three d20 rolls of
    three different kinds -- attack, save, skill -- spent in the order they
    come. Only attack rolls can carry a modifier at all."""


@power(
    "p14142",
    level=2,
    cls=X7_855,
    usage=DAILY,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE],
    dropped=("c.see_from(square)",),
)
def p14142(c: Cast) -> None:
    """The darkvision is written now and lasts as long as the card says.

    Still dropped: seeing *from* a chosen spot 20 squares away, with no line
    of sight to it. That is a second vantage point, and every sight question
    in the engine measures from the creature's own squares -- so it is a real
    missing clause rather than flavour, and `narrative=` would be a lie about
    it. One row wants it, which is below the threshold #468 sets, so it is
    named and left."""
    c.darkvision(until=When.EONT)


@power(
    "p14143",
    level=6,
    cls=X7_855,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE],
    trigger="you are hit by an attack",
    on=Trigger(AttackRolled, would_hit_me, "you are hit by an attack"),
)
def p14143(c: Cast) -> None:
    """An interrupt on `AttackRolled`: the defence is read again once this
    window closes, so the bonus can still turn the blow aside, which is what
    an interrupt against a hit is for. The shift is "after the attack is
    resolved", so it is granted rather than taken here."""
    _defences(c, 2, until=When.EONT)
    c.grant_action("shift", FREE, on=c.me, until=When.EOT)


@power(
    "p14144",
    level=10,
    cls=X7_855,
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE],
)
def p14144(c: Cast) -> None:
    hold = c.effect(c.ref, until=When.SUSTAIN, sustain=MINOR, on=c.me)

    def look() -> None:
        c.see_invisible(on=c.me, until=When.EONT)
        c.bonus("skill:insight", 5, kind="power", on=c.me, until=When.EONT)
        c.bonus("skill:perception", 5, kind="power", on=c.me, until=When.EONT)

    look()
    c.on_sustain(hold, look)


# -- x7_864: the scout -------------------------------------------------------


@power(
    "p14175",
    level=0,
    cls=X7_864,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
    trigger=(
        "when using a basic attack or an at-will weapon attack power, "
        "you hit an enemy that is granting combat advantage to you"
    ),
    on=Trigger(Hit, by_me, "you hit an enemy"),
)
def p14175(c: Cast) -> None:
    """"Granting combat advantage to you" is `ev.result.advantage` read off
    the hit -- asking the board again is too late, a one-shot grant has
    already been spent."""
    ev = c.trigger
    if not c.had_advantage(ev) or not _at_will_weapon(ev.power):
        return
    c.dazed(on=ev.target, until=When.EONT)


@power(
    "p14176",
    level=2,
    cls=X7_864,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL],
    dropped=("c.ignore_run_penalty()",),
)
def p14176(c: Cast) -> None:
    """The speed is exact. Running is a real action kind and grants combat
    advantage in `actions.legal`, but nothing can waive that one grant --
    `c.no_advantage` shuts every branch, which is a much larger sentence --
    and the attack penalty for running is modelled nowhere at all."""
    c.bonus("speed", 2, kind="power", on=c.me, until=When.EOT)


@power(
    "p14177",
    level=6,
    cls=X7_864,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL],
    dropped=("c.cover_from()",),
)
def p14177(c: Cast) -> None:
    """The hide itself is `c.hide`; what is missing is the test the card
    gates it on -- whether the square you stopped in gives partial cover or
    partial concealment -- so the free Stealth check has no condition."""
    c.shift(1, who=c.me)
    c.move(c.speed_of(c.me), who=c.me)


@power(
    "p14178",
    level=10,
    cls=X7_864,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL],
    trigger="you roll initiative at the start of an encounter and are not surprised",
    on=Trigger(InitiativeRolled, about_me, "you roll initiative"),
)
def p14178(c: Cast) -> None:
    """`c.bonus` cannot say this: the initiative bonus is read before the
    d20 and this row answers a roll that has already happened, so it moves
    the creatures in the order instead."""
    if c.is_(Condition.SURPRISED, on=c.me):
        return
    c.initiative(5, on=c.me)
    for ally in c.allies():
        c.initiative(5, on=ally)


# -- x7_887: the shadow ------------------------------------------------------


@power(
    "p14326",
    level=0,
    cls=X7_887,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.SHADOW],
    trigger=(
        "when using a melee or ranged weapon attack power, you hit a "
        "creature that is granting combat advantage to you"
    ),
    on=Trigger(Hit, by_me, "you hit a creature"),
)
def p14326(c: Cast) -> None:
    ev = c.trigger
    if not c.had_advantage(ev) or not _weapon_attack(ev.power):
        return
    c.weakened(on=ev.target, until=When.EONT)
    c.shift(2, who=c.me)


@power(
    "p14327",
    level=2,
    cls=X7_887,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM],
)
def p14327(c: Cast) -> None:
    """"The next creature to attack the target" is `once=True`, which spends
    the grant on the first attack roll against it rather than on the first
    time a policy thinks about one."""
    c.grants_advantage(on=c.target, to="team", until=When.EONT, once=True)


@power(
    "p14328",
    level=6,
    cls=X7_887,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.SHADOW],
)
def p14328(c: Cast) -> None:
    c.insubstantial(on=c.me, until=When.SONT)
    speed = c.speed_of(c.me)
    c.mode("fly", speed, until=When.EOT, on=c.me)
    c.move(speed, who=c.me)


@power(
    "p14329",
    level=10,
    cls=X7_887,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.CHARM],
    trigger="you make a Diplomacy check or an Intimidate check",
    out_of_combat=True,
)
def p14329(c: Cast) -> None:
    """Neither Diplomacy nor Intimidate is rolled on a board, so the whole
    printed Effect is inert in a fight -- finished, not unwritten."""


# -- x7_927: the flesh warper ------------------------------------------------


@power(
    "p15953",
    level=0,
    cls=X7_927,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ANY_CREATURE,
    keywords=[Keyword.SHADOW, Keyword.IMPLEMENT, Keyword.FEAR],
    todo=("c.retarget_defence()",),
)
def p15953(c: Cast) -> None:
    """One hole, and the row is nothing without it: a single attack roll
    compared against Fortitude, Reflex **and** Will, each with its own Hit
    line. Nothing re-aims a roll that has already been made at a second
    defence.

    **`c.ability_for(ref)` is off the marker and was never the hold.** The
    caster's choice of Intelligence, Wisdom or Charisma is `c.choose` plus
    `c.rolls_with`, both of which exist -- `ability_for` *reads* which
    ability a line rolls and choosing is a different question. So the ability
    half is one line whenever the row has an attack to hang it on, and the
    marker now names only what is missing."""


@power(
    "p15954",
    level=2,
    cls=X7_927,
    usage=DAILY,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_ALLY,
    keywords=[Keyword.SHADOW, Keyword.STANCE],
)
def p15954(c: Cast) -> None:
    """The stance is the *target's*, so everything here is aimed with `on=`.
    "Grants combat advantage" names no beneficiary, and the relation names
    one creature at a time, so it is laid once per enemy."""
    ally = c.target
    c.stance(on=ally, conditions=(Condition.SLOWED,), label=c.ref)
    c.bonus("attack", 2, kind="power", on=ally, until=When.STANCE)
    c.bonus("damage", 4, kind="power", on=ally, until=When.STANCE)
    for foe in c.enemies():
        c.grants_advantage(on=ally, to=foe, until=When.STANCE)


_ELEMENTS = (
    DamageType.ACID,
    DamageType.COLD,
    DamageType.FIRE,
    DamageType.LIGHTNING,
    DamageType.THUNDER,
)


def _ally_burned_nearby(world: World, me: int, ev: object) -> bool:
    """An ally -- not me -- within 5 takes damage of one of five types.
    `DamageRolled` names its subject `target`, so `ally_within` is false on
    it forever: that one reads `actor` and falls through to the attacker."""
    who = getattr(ev, "target", None)
    if who is None or who == me:
        return False
    if query.team(world, who) is not query.team(world, me):
        return False
    if getattr(ev, "dtype", None) not in _ELEMENTS:
        return False
    return query.distance_between(world, me, who) <= 5


@power(
    "p15955",
    level=6,
    cls=X7_927,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=CloseBurst(5),
    target=NO_TARGET,
    keywords=[Keyword.SHADOW],
    trigger=(
        "an ally within 5 squares of you takes acid, cold, fire, lightning, "
        "or thunder damage"
    ),
    on=Trigger(DamageRolled, _ally_burned_nearby, "an ally nearby takes elemental damage"),
)
def p15955(c: Cast) -> None:
    """`DamageRolled` and not `DamageApplied`: an interrupt has to lay the
    resistance while the number is still rolled and unspent."""
    ev = c.trigger
    who = ev.target
    c.resist(10, ev.dtype, on=who, until=When.EONT)
    for near in c.within(1, of=who):
        if near != who:
            c.flat(5, dtype=ev.dtype, on=near)


@power(
    "p15956",
    level=10,
    cls=X7_927,
    usage=DAILY,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.SHADOW],
    trigger="you hit an enemy that has resistance to your attack's damage type",
    on=Trigger(DamageRolled, by_me, "you damage an enemy"),
)
def p15956(c: Cast) -> None:
    """`c.resistances` is the reader this needs: the vulnerability equals
    the resistance that was lost, so the number has to be seen before the
    delta is handed over. A negative `c.resist` with a save-ends duration
    takes it off and puts the standing figure back on the save, which is
    the printed "save ends both"."""
    ev = c.trigger
    held = c.resistances(on=ev.target).get(ev.dtype, 0)
    if held <= 0:
        return
    c.resist(-held, ev.dtype, on=ev.target, until=When.SAVE_ENDS)
    c.vulnerable(held, ev.dtype, on=ev.target)


# -- x7_945: the elemental initiate ------------------------------------------


@power(
    "p16065",
    level=0,
    cls=X7_945,
    usage=ENCOUNTER,
    action=REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.ELEMENTAL, Keyword.WEAPON],
    trigger="an adjacent enemy misses you with a melee attack",
    on=Trigger(Miss, both(targets_me, by_melee), "an adjacent enemy misses you"),
    todo=("c.best_ability()",),
)
def p16065(c: Cast) -> None:
    """"Highest ability modifier vs. Reflex" -- the whole row is the attack
    and its riders, so there is nothing to keep without it."""


@power(
    "p16066",
    level=2,
    cls=X7_945,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PSIONIC, Keyword.ELEMENTAL],
    dropped=("c.no_advantage(cause=)",),
)
def p16066(c: Cast) -> None:
    """The shift and the defences are exact.

    "Climbing or balancing doesn't cause you to grant combat advantage" waives
    **one cause** of a grant and leaves the others standing. Re-aimed off
    `c.grants_advantage(when=)`, which exists now and is the wrong direction
    twice over: this row takes advantage away rather than giving it, and the
    verb that takes it away is `c.no_advantage`, which shuts every cause at
    once. What is missing is a way to name which cause."""
    c.ignores_difficult(on=c.me, until=When.EOT)
    c.shift(3, who=c.me)
    _defences(c, 2, until=When.EONT)


@power(
    "p16067",
    level=6,
    cls=X7_945,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ANY_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.ELEMENTAL, Keyword.HEALING],
)
def p16067(c: Cast) -> None:
    """"One poison, dazing, or stunning effect" is one of the three, so the
    poison is only looked for when neither condition was there to cure."""
    if c.may("spend a healing surge"):
        c.surge(on=c.target, bonus=c.roll("1d6"))
    if not c.cure(Condition.DAZED, Condition.STUNNED, on=c.target):
        c.end_effect(on=c.target, against="poison")


@power(
    "p16068",
    level=10,
    cls=X7_945,
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PSIONIC, Keyword.ELEMENTAL, Keyword.STANCE],
)
def p16068(c: Cast) -> None:
    """The allies' half is geometry -- "while adjacent to you" -- so it is
    an aura carrying the modifier rather than a duration on each of them.
    `side="ally"` leaves the caster out, who has the bonus already."""
    c.stance(label=c.ref)
    c.shift_as(MINOR, 1, on=c.me, until=When.STANCE)
    _defences(c, 2, until=When.STANCE)
    ring = c.aura(1, on=c.me, until=When.STANCE, label=c.ref)
    for defence in DEFENCES:
        c.grants_in(ring, defence, 2, side="ally", kind="power")


# -- x7_974: the careful mage ------------------------------------------------


@power(
    "p16370",
    level=0,
    cls=X7_974,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE],
)
def p16370(c: Cast) -> None:
    """Ranged and area **arcane** powers only, which is narrower than what this
    row used to lay.

    It laid the bare `c.no_provoke`, i.e. "you provoke nothing at all" -- a row
    **stronger than its card**, which is the one direction never to guess in.
    The verb takes a `when=` now.

    **The gate only has to test the keyword.** "Ranged and area" needs no test
    at all: `Power.provokes_on` opens this window for `ranged`, `area_burst` and
    `wall` and nothing else, so a window that exists is already one of those.
    Checking the shape again would be a second copy of that rule, free to drift.

    `ctx["why"]` is the window's own reason, `"<ref> is a ranged power"`, so the
    row that provoked is its first token.
    """
    def arcane_ranged(ctx: dict[str, Any]) -> bool:
        row = get(str(ctx.get("why", "")).split(" ", 1)[0])
        return row is not None and Keyword.ARCANE in row.keywords

    c.no_provoke(on=c.me, until=When.EONT, when=arcane_ranged)


@power(
    "p16371",
    level=2,
    cls=X7_974,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE],
)
def p16371(c: Cast) -> None:
    """Penalties carry no type, which is the rule, so `c.penalty` takes no
    `kind=`. The gate reads `target` off the attack context, which carries
    it."""
    friends = frozenset(c.allies())
    c.penalty(
        "attack",
        4,
        on=c.me,
        until=When.EONT,
        when=lambda ctx: ctx["target"] in friends,
    )


def _arcane_power(ref: str) -> bool:
    p = get(ref)
    return p is not None and Keyword.ARCANE in p.keywords


@power(
    "p16372",
    level=6,
    cls=X7_974,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(2),
    target=ONE_ALLY,
    keywords=[Keyword.ARCANE],
    dropped=("c.resist_from()",),
)
def p16372(c: Cast) -> None:
    """The damage context carries `power` but no attacker, so "your arcane
    powers" can only be narrowed to arcane ones -- an ally caught by a
    second wizard's fireball is spared as well."""
    c.resist(
        1000,
        on=c.target,
        until=When.EONT,
        when=lambda ctx: _arcane_power(ctx["power"]),
    )


@power(
    "p16373",
    level=10,
    cls=X7_974,
    usage=DAILY,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
    trigger="you roll damage for an arcane attack power and dislike the result",
    on=Trigger(DamageRolled, by_me, "you roll damage"),
    todo=("c.reroll_damage_dice()",),
)
def p16373(c: Cast) -> None:
    """"As many of the damage dice as you like, and you must use the second
    result" -- `c.reroll_damage` is the other sentence, roll twice and keep
    the higher, and using it here would be a strictly better power."""


# -- x7_986: the underdark hand ----------------------------------------------


@power(
    "p16433",
    level=0,
    cls=X7_986,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL],
    trigger="you make a Dungeoneering check and dislike the result",
    out_of_combat=True,
)
def p16433(c: Cast) -> None:
    """Dungeoneering is never rolled on a board, so there is no check here
    for the reroll to reach."""


@power(
    "p16434",
    level=2,
    cls=X7_986,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL],
    todo=("c.cover_from()",),
)
def p16434(c: Cast) -> None:
    """Both halves hang on the cover: nothing grants partial cover from a
    piece of terrain, and the second clause fires only while you have it, so
    writing the second alone would be a rider that is never true."""


@power(
    "p16435",
    level=6,
    cls=X7_986,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL],
    trigger=(
        "you fail an Acrobatics, Athletics, Endurance, or Perception check "
        "while underground"
    ),
    todo=("c.substitute_check()",),
)
def p16435(c: Cast) -> None:
    """Not a reroll: a different skill is rolled and its result stands in
    for the failed one. `c.reroll_check` re-rolls the same skill."""


@power(
    "p16436",
    level=10,
    cls=X7_986,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL],
    trigger="you take damage from a trap, a hazard, or a fall",
    on=Trigger(DamageRolled, targets_me, "you take damage"),
    dropped=("c.is_hazard()", "Fell.damage"),
)
def p16436(c: Cast) -> None:
    """The trap third is written. A hazard's damage arrives from whoever
    made the zone and is indistinguishable from an attack's, and a fall
    announces `Fell` with no damage number on it."""
    ev = c.trigger
    if not c.is_trap(ev.source):
        return
    c.reduce(5 + c.level // 2, ev)


# -- x7_994: the beast form --------------------------------------------------


@power(
    "p16535",
    level=0,
    cls=X7_994,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
    dropped=("Keyword.BEAST_FORM",),
)
def p16535(c: Cast) -> None:
    """The form and the printed alternative -- end it as a minor action and
    shift 1 -- are written as one way out, so `revert=None` and the shift
    rides on `c.endable`.

    The secondary at-will attack is `p16535b`, declared below: it had no ref
    of its own until `parse_extra` ran for theme powers, and "Highest ability
    modifier + 3 vs. AC" is `Pick.HIGHEST` in its header rather than the
    `c.best_ability()` this row was waiting on."""
    shape = c.form(until=When.ENCOUNTER, revert=None, label=c.ref)
    c.endable(shape, MINOR, then=lambda: c.shift(1, who=c.me))
    c.low_light(until=When.ENCOUNTER)


@power(
    "p16535b",
    level=0,
    cls=X7_994,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(Pick.HIGHEST, plus=3, vs=AC),
    dropped=("Keyword.BEAST_FORM",),
)
def p16535b(c: Cast) -> None:
    """The attack the form unlocks -- the second card inside p16535's entry.

    Declared for the same reason as `p16525b`: p16538's trigger tests
    `ev.power == "p16535b"`, and until this row existed nothing could ever
    cast it, so the trigger was unreachable rather than merely unused.

    "Highest ability modifier + 3 vs. AC" is the printed line, which is
    `Pick.HIGHEST` and was the `c.best_ability()` marker on the parent.
    """
    if not c.strike():
        return
    c.damage("1d10", c.mod(c.ability_for()))


@power(
    "p16537",
    level=2,
    cls=X7_994,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.HEALING],
    requires=_bloodied,
    requires_text="you must have started this turn bloodied",
    dropped=("c.in_form()",),
)
def p16537(c: Cast) -> None:
    """Both benefits are printed "while you are in beast form" and nothing
    reads whether a creature is; the regeneration's own bloodied gate is
    written. The Requirement is "started this turn bloodied" and the gate
    asks whether you are bloodied now, which differs only for a creature
    healed out of it mid-turn."""
    c.bonus("speed", 1, on=c.me, until=When.ENCOUNTER)
    c.regeneration(2, until=When.ENCOUNTER, on=c.me, while_bloodied=True)


@power(
    "p16538",
    level=6,
    cls=X7_994,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=(
        "you hit an enemy with p16535's secondary power, and the enemy is "
        "adjacent to at least one of your allies"
    ),
    on=Trigger(Hit, by_me, "you hit an enemy"),
)
def p16538(c: Cast) -> None:
    """The secondary card has a ref now, so the trigger has something to test.

    `p16535b` is the second card printed inside p16535's own entry. It was
    parsed all along and never reached the database, because only the class
    pass asked for extras and this is a theme power -- so `ev.power` had
    nothing to be compared against and the row could not be written.

    Both halves of the printed trigger are checked here rather than in the
    predicate: `by_me` narrows to hits I made, and the ally's adjacency is a
    question about the *victim's* neighbours, which the predicate's signature
    cannot ask."""
    ev = c.trigger
    if getattr(ev, "power", "") != "p16535b":
        return
    if not any(c.adjacent_to(friend, ev.target) for friend in c.allies()):
        return
    c.prone(on=ev.target)


def _hit_while_bloodied(world: World, me: int, ev: object) -> bool:
    if getattr(ev, "target", None) != me:
        return False
    return _bloodied(world, me)


@power(
    "p16539",
    level=10,
    cls=X7_994,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.STANCE],
    trigger="an attack bloodies you, or you are hit while bloodied",
    on=(
        Trigger(Bloodied, about_me, "an attack bloodies you"),
        Trigger(Hit, _hit_while_bloodied, "you are hit while bloodied"),
    ),
    dropped=("Keyword.BEAST_FORM", "c.in_form()", "c.provoke(allies=)"),
)
def p16539(c: Cast) -> None:
    """Both printed triggers are declared -- half of an "or" declared looks
    finished and is not. The stance runs "until you are no longer bloodied",
    which no duration says; `When.STANCE` is the nearest, and it holds until
    something else replaces it. The extra 1d6 is on beast form powers, and
    "your allies provoke opportunity attacks from you" turns the side test
    in the opportunity window around, which nothing can ask for."""
    c.stance(label=c.ref)
    c.bonus("attack", 2, kind="power", on=c.me, until=When.STANCE)


# -- x7_1010: the trickster --------------------------------------------------


@power(
    "p16619",
    level=0,
    cls=X7_1010,
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM],
    dropped=("c.best_ability()", "c.cannot_speak()"),
)
def p16619(c: Cast) -> None:
    """A named hold so the thing can be seen and saved against. What it
    should stop -- speech, and any effect delivered by it -- is not a
    condition the engine has, and the attack is "highest ability modifier"
    besides."""
    c.effect(c.ref, until=When.SAVE_ENDS, on=c.target)


@power(
    "p16620",
    level=2,
    cls=X7_1010,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    trigger="you are hit by a ranged attack",
    on=Trigger(
        AttackRolled, both(would_hit_me, by_ranged), "you are hit by a ranged attack"
    ),
)
def p16620(c: Cast) -> None:
    """"A random creature (including yourself)" -- the caster goes in the
    pool, so the row can and sometimes does do nothing at all."""
    pool = [c.me, *c.within(3, of=c.me)]
    if len(pool) < 2:
        return
    c.redirect(to=pool[c.roll(len(pool)) - 1])


@power(
    "p16621",
    level=6,
    cls=X7_1010,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you roll a d20 and dislike the result",
    todo=("c.boost_roll()",),
)
def p16621(c: Cast) -> None:
    """Any d20 roll at all -- attack, save, skill, ability check -- and only
    attack rolls can carry a modifier, so there is nothing to lay it on."""


@power(
    "p16622",
    level=10,
    cls=X7_1010,
    usage=DAILY,
    action=FREE,
    reach=CloseBurst(20),
    target=NO_TARGET,
    trigger="you roll initiative and dislike the result",
    on=Trigger(InitiativeRolled, about_me, "you roll initiative"),
)
def p16622(c: Cast) -> None:
    """The reroll comes first and the two modifiers are applied to the new
    count, which is the printed order.

    The latch is load-bearing: `c.reroll_initiative` announces another
    `InitiativeRolled`, which is this row's own trigger, so without it the
    row answers itself once per creature it has just rerolled -- twenty-four
    firings on an eight-creature board."""
    if c.suffering(c.ref, include_self=True):
        return
    c.effect(c.ref, until=When.ENCOUNTER, on=c.me)
    mine = [c.me, *c.allies()]
    foes = c.enemies()
    for who in (*mine, *foes):
        c.reroll_initiative(on=who)
    for who in mine:
        c.initiative(4, on=who)
    for foe in foes:
        c.initiative(-4, on=foe)


# -- x7_1022: the bravo ------------------------------------------------------


@power(
    "p16695",
    level=0,
    cls=X7_1022,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    requires=_bloodied,
    requires_text="you must be bloodied",
)
def p16695(c: Cast) -> None:
    """`c.use_power` leaves the borrowed row's attack in `c.result`, so
    `c.landed` is the printed "if you hit" without re-rolling anything."""
    rows = c.borrowed_rows(c.me)
    if not rows:
        return
    ref = c.choose(rows)
    if ref is None:
        return
    c.use_power(ref, on=c.target)
    if c.landed:
        c.damage("2d6")
    else:
        c.damage("1d6", on=c.me)


@power(
    "p16696",
    level=2,
    cls=X7_1022,
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.STANCE],
)
def p16696(c: Cast) -> None:
    """Advantage against any enemy standing next to one of your allies.

    **Asked per swing, not fixed when the stance is taken.** It used to lay the
    relation on whoever qualified at that moment, which is the printed line for
    one instant and wrong from the next -- allies and enemies both move, and a
    stance lasts until it ends. The relation has no gate to re-ask with;
    `c.gains_advantage` is asked every time advantage is computed.

    `c.allies()` is read inside the gate rather than closed over for the same
    reason: an ally can drop, and a corpse is nobody to stand beside."""
    c.stance(label=c.ref)
    c.gains_advantage(
        lambda ctx: any(c.adjacent_to(ctx["target"], ally) for ally in c.allies()),
        until=When.STANCE, on=c.me,
    )


@power(
    "p16697",
    level=6,
    cls=X7_1022,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_CREATURE,
)
def p16697(c: Cast) -> None:
    """The card prints no DC; the opposed number is the target's passive
    Insight, which is what `c.passive` is for rather than inventing one."""
    if c.check("bluff", c.passive("insight", of=c.target)):
        c.grants_advantage(on=c.target, to="me", until=When.EOT)
        c.no_provoke(from_=c.target, on=c.me, until=When.EONT)


@power(
    "p16698",
    level=10,
    cls=X7_1022,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you are bloodied by an attack",
    on=Trigger(Bloodied, about_me, "you are bloodied by an attack"),
)
def p16698(c: Cast) -> None:
    """This one names Charisma outright, so the temporary hit points are a
    number rather than a hole."""
    _defences(c, 1, until=When.ENCOUNTER)
    c.bonus("save", 1, kind="power", on=c.me, until=When.ENCOUNTER)
    amount = 3 + c.cha_mod

    def missed(ev: Miss) -> None:
        if ev.target == c.me:
            c.temp_hp(amount, on=c.me)

    def saved(ev: SavingThrow) -> None:
        if ev.actor == c.me and ev.saved:
            c.temp_hp(amount, on=c.me)

    c.watch(Miss, missed, until=When.ENCOUNTER, on=c.me)
    c.watch(SavingThrow, saved, until=When.ENCOUNTER, on=c.me)


# -- x7_1008: the stoic ------------------------------------------------------


@power(
    "p16613",
    level=2,
    cls=X7_1008,
    usage=ENCOUNTER,
    action=MINOR,
    reach=Melee(1),
    target=ONE_ALLY,
    todo=("c.effects_on()",),
)
def p16613(c: Cast) -> None:
    """`c.transfer` moves a live hold intact and is the second half of this
    row; the first half is picking which hold, and nothing reads the effects
    standing on a creature. `c.end_effect(save_ends=True)` finds one and
    destroys it, which is the wrong operation."""


@power(
    "p16614",
    level=6,
    cls=X7_1008,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    trigger="an enemy hits you with an attack",
    on=Trigger(AttackRolled, would_hit_me, "an enemy hits you with an attack"),
)
def p16614(c: Cast) -> None:
    """The gate reads `attacker`, which the attack context carries and the
    damage context does not -- a defence is read during the attack, so this
    is the right side of the line."""
    foe = c.trigger.attacker
    for defence in DEFENCES:
        c.bonus(
            defence,
            2,
            kind="power",
            on=c.me,
            until=When.EONT,
            when=lambda ctx: ctx["attacker"] == foe,
        )


@power(
    "p16615",
    level=10,
    cls=X7_1008,
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.STANCE],
)
def p16615(c: Cast) -> None:
    """`PowerResolved` and not `PowerUsed`: the latter is announced above
    the body, so a row would already count as used by the time its own
    attack roll read this gate and the bonus would never apply once."""
    spent: set[str] = set()

    def note(ev: PowerResolved) -> None:
        if ev.actor == c.me:
            spent.add(ev.power)

    c.watch(PowerResolved, note, until=When.STANCE, on=c.me)
    c.bonus(
        "attack",
        2,
        kind="power",
        on=c.me,
        until=When.STANCE,
        when=lambda ctx: ctx["power"] not in spent,
    )
