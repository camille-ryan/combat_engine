"""Skill powers for one skill: `cls` is the skill, not a class.

Ten rows, all Utility, at levels 2, 6 and 10. What the group has in common
is the body they are paid out of: eight of the ten spend, refuse or shrug
off something the character's own hit points and saving throws carry -- a
healing surge with nothing bought by it, an extra throw against what is
already standing, resistance laid on after the blow has landed.

Four of them are printed with no action at all or as an immediate, so every
printed Trigger here is declared with `on=`; `trigger=` alone is prose
nothing reads. `p11547` is the one that also needs a **window**: its throw
is printed "before you take the damage" and the ongoing tick is an
ordinary `TurnStart` listener, so the offer has to be made in
`Window.BEFORE` or the save arrives after the burn.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    DAILY,
    DEFENCES,
    EACH_ALLY,
    ENCOUNTER,
    INTERRUPT,
    MINOR,
    NO_TARGET,
    PERSONAL,
    REACTION,
    SELF,
    STANDARD,
    ActionType,
    Cast,
    CloseBurst,
    Condition,
    DamageType,
    Health,
    Keyword,
    Powers,
    Trigger,
    TurnStart,
    When,
    Window,
    World,
    get,
    power,
    targets_me,
)
from combat_engine.engine.events import (
    AttackDeclared,
    Bloodied,
    DamageApplied,
    Hit,
    SavingThrow,
)
from combat_engine.engine.query import (
    enemies,
    line_of_effect,
    taking_ongoing,
    unseen_by,
)

#: The tally `c.second_wind` and `actions.perform` spend the use under, and
#: the only record that it has been taken.
SECOND_WIND = "second-wind"


def _has_a_surge(world: World, eid: int) -> bool:
    """"Requirement: you must have at least one healing surge remaining."""
    health = world.get(eid, Health)
    return health is not None and health.surges > 0


def _second_wind_ready(world: World, eid: int) -> bool:
    """"Requirement: your second wind must be available for you to use."

    A creature with no `Powers` has taken none, so the Requirement is met --
    the same reading `c.second_wind` itself takes of a missing tally.
    """
    known = world.get(eid, Powers)
    return known is None or known.times(SECOND_WIND) == 0


def _sees_me(c: Cast, who: int) -> bool:
    """"Allies in the burst **that can see you**", asked from their side.

    `c.can_see` is the caster's question and this is the mirror of it, so
    the two halves are the same two readers: line of effect, and whether
    this creature is one of the ones I am hidden from.
    """
    return line_of_effect(c.world, who, c.me) and not unseen_by(
        c.world, who, c.me
    )


def _fear_attack(ctx: dict[str, Any]) -> bool:
    """Is the blow being rolled a fear one? `ctx["power"]` is the row."""
    row = get(str(ctx.get("power", "")))
    return row is not None and Keyword.FEAR in row.keywords


def _feared_me(world: World, me: int, ev: AttackDeclared) -> bool:
    """"You are the target of an enemy's fear effect."

    Narrowed to a fear **attack**, which is the only fear moment the engine
    announces with a power to read keywords off. See the row's docstring.
    """
    row = get(getattr(ev, "power", ""))
    return (
        getattr(ev, "target", None) == me
        and row is not None
        and Keyword.FEAR in row.keywords
        and getattr(ev, "attacker", None) in enemies(world, me)
    )


def _burning_at_turn_start(world: World, me: int, ev: TurnStart) -> bool:
    """"Your turn starts and you have ongoing damage."

    `query.taking_ongoing` is the reader, and it is asked here rather than
    off a label: a burn's own label is the printed amount, so matching the
    word would answer for whichever row happened to spell it.
    """
    return (
        getattr(ev, "actor", None) == me
        and not getattr(ev, "ghost", False)
        and taking_ongoing(world, me)
    )


def _my_saving_throw(world: World, me: int, ev: SavingThrow) -> bool:
    """"You are required to roll a saving throw" -- any of them, mine."""
    return getattr(ev, "actor", None) == me


def _attack_bloodied_me(world: World, me: int, ev: Bloodied) -> bool:
    """"An attack bloodies you."

    `Bloodied.source` is None when nothing struck the blow -- ongoing
    damage ticking the creature over the line -- which is exactly the case
    the printed word "attack" excludes.
    """
    return getattr(ev, "actor", None) == me and getattr(ev, "source", None) is not None


def _types_of(ev: DamageApplied) -> tuple[DamageType, ...]:
    """"Damage of a specific type or combination of types."

    `dtypes` is the whole type of a blow that is more than one and is empty
    for the ordinary single-type case, so the two have to be read in that
    order. Untyped is dropped: it is the absence of a type rather than one
    of them, and resistance to it is not a thing a card grants.
    """
    many = tuple(getattr(ev, "dtypes", ()) or ())
    one = getattr(ev, "dtype", None)
    types = many or ((one,) if one is not None else ())
    return tuple(t for t in types if t is not DamageType.UNTYPED)


def _typed_damage_to_me(world: World, me: int, ev: DamageApplied) -> bool:
    return (
        getattr(ev, "target", None) == me
        and getattr(ev, "amount", 0) > 0
        and bool(_types_of(ev))
    )


@power(
    "p12163",
    level=2,
    cls="endurance",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    requires=_has_a_surge,
    requires_text="you must have at least 1 healing surge",
)
def p12163(c: Cast) -> None:
    """"Every effect on you that a save can end", so the whole set rather
    than one of it: `c.save` takes whichever save-ends effect it finds first
    and returns, which is one throw where the card prints as many as there
    are effects. `Effects.of` has already built a list, so an effect ending
    under the loop does not disturb it.

    `c.spend_surge` is the surge that buys nothing -- the printed line is
    explicit that no hit points come back, which is what separates it from
    `c.surge`.
    """
    c.spend_surge(on=c.me)
    for effect in c.world.effects.of(c.me):
        if effect.when is When.SAVE_ENDS:
            c.world.effects.save(effect, granted_via=c.ref)


@power(
    "p13693",
    level=2,
    cls="endurance",
    usage=DAILY,
    action=INTERRUPT,
    reach=CloseBurst(10),
    target=NO_TARGET,
    trigger="you are the target of an enemy's fear effect",
    on=Trigger(
        AttackDeclared, _feared_me, "you are the target of an enemy's fear effect"
    ),
)
def p13693(c: Cast) -> None:
    """Two bonuses on two different clocks, and neither is the caster's.

    The defence half is gated rather than flat: "against fear effects" is a
    question about the blow being rolled, and `ctx["power"]` is the row, so
    the narrowing is read where every other gated defence is read. Laid from
    an interrupt, so it covers the triggering attack too -- `resolve.attack`
    re-reads the defence after announcing the roll.

    The attack half is kept "until the start of **its** next turn", which no
    `When` can say: `SOTNT` clocks on the creature the effect sits on, and
    these sit on allies while the printed clock is the triggering enemy. So
    it is laid to the end of the encounter and ended by a watch on that one
    creature's turn starting, which is the boundary the card names.

    `NO_TARGET` because the card prints no Target line, so every call here
    names who it is for.
    """
    foe = getattr(c.trigger, "attacker", None)
    crew = [c.me, *[f for f in c.within(10, side="ally") if _sees_me(c, f)]]
    aimed = [] if foe is None else [
        c.bonus(
            "attack", 2, on=who, until=When.ENCOUNTER, kind="power",
            when=lambda ctx, foe=foe: ctx.get("target") == foe,
        )
        for who in crew
    ]
    for who in crew:
        for defence in DEFENCES:
            c.bonus(
                defence, 2, on=who, until=When.ENCOUNTER, kind="power",
                when=_fear_attack,
            )

    if not aimed:
        return

    def its_turn(ev: TurnStart) -> None:
        if ev.actor != foe:
            return
        for held in aimed:
            if held is not None:
                c.world.effects.end(held, "start of its next turn")

    c.watch(TurnStart, its_turn, until=When.ENCOUNTER, once=True)


@power(
    "p9314",
    level=2,
    cls="endurance",
    usage=DAILY,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    trigger="you are hit by an attack",
    on=Trigger(Hit, targets_me, "you are hit by an attack"),
)
def p9314(c: Cast) -> None:
    """Resistance with no type is resistance to all damage, which is the
    printed line. An interrupt, so it is standing before the blow that
    triggered it is dealt."""
    c.resist(5 + c.con_mod, until=When.EONT, on=c.me)


@power(
    "p9315",
    level=2,
    cls="endurance",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ALLY,
    requires=_second_wind_ready,
    requires_text="your second wind must be available for you to use",
)
def p9315(c: Cast) -> None:
    """The second wind is the caster's and happens once, so it is behind
    `c.first`; the temporary hit points are per target.

    `cost=ActionType.NONE` because the standard action is the power's own --
    the second wind is not separately paid for, and `SecondWind.cost` is
    read by printed feats that turn on what it was taken as.
    """
    if c.first:
        c.second_wind(on=c.me, cost=ActionType.NONE)
    c.temp_hp(10 + c.con_mod, on=c.target)


@power(
    "p11546",
    level=6,
    cls="endurance",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.HEALING],
    dropped=("c.heal_check()",),
)
def p11546(c: Cast) -> None:
    """The Healing keyword is the difference from `p12163`: this surge pays
    out, so it is `c.surge` and not `c.spend_surge`.

    Dropped: the Special, which lets an adjacent ally spend a standard
    action on a DC 10 check to set this off instead. Nothing offers that
    check as an action in a fight, so no `SkillCheck` with that skill is
    ever announced -- the same absence `f1390` and `f3710` already wait on.
    The clause is also about who pays for *using* this row, which a body
    cannot reach: the body only runs once the row has been used.
    """
    c.surge(on=c.me)


@power(
    "p11547",
    level=6,
    cls="endurance",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    trigger="your turn starts and you have ongoing damage",
    on=Trigger(
        TurnStart,
        _burning_at_turn_start,
        "your turn starts and you have ongoing damage",
        window=Window.BEFORE,
    ),
)
def p11547(c: Cast) -> None:
    """"Before you take the damage" is the whole of the row, and it is the
    `window=` on the trigger rather than anything in here: `Effects` answers
    `TurnStart` at the default `Window.AFTER` and deals the burn there, so
    an offer made in the same window would arrive after it.

    `when_="early"` says which of the turn's throws this is, which is what a
    gate reading "saving throws made at the start of your turn" asks and
    what a row triggering on one reads off the event.
    """
    c.save(on=c.me, against="ongoing", when_="early")


@power(
    "p13694",
    level=6,
    cls="endurance",
    usage=DAILY,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    trigger="you are required to roll a saving throw",
    on=Trigger(
        SavingThrow, _my_saving_throw, "you are required to roll a saving throw"
    ),
)
def p13694(c: Cast) -> None:
    """`c.boost_roll`, not `c.bonus("save", ...)`: the throw in hand has
    already had its modifiers summed, so a modifier laid now is read by the
    *next* one. `SavingThrow` is announced before it is acted on, which is
    what makes the boost reach this throw.

    The printed type is a power bonus and a boost carries none, which costs
    nothing here: the bonus is spent on one throw at the moment it is
    rolled, so there is no second bonus of that type for it to fail to
    stack with.
    """
    c.boost_roll(4, kind="save")


@power(
    "p11548",
    level=10,
    cls="endurance",
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.HEALING],
    trigger="an attack bloodies you",
    on=Trigger(Bloodied, _attack_bloodied_me, "an attack bloodies you"),
)
def p11548(c: Cast) -> None:
    """A Healing surge that pays out. `Bloodied` carries whoever struck the
    blow, which is how the printed word "attack" is told from a burn
    ticking the creature over the line."""
    c.surge(on=c.me)


@power(
    "p13695",
    level=10,
    cls="endurance",
    usage=DAILY,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger="you take damage of a specific type or combination of types",
    on=Trigger(
        DamageApplied,
        _typed_damage_to_me,
        "you take damage of a specific type or combination of types",
    ),
)
def p13695(c: Cast) -> None:
    """"If you already have resistance to that type, the resistance
    increases by 5" is a delta, and `c.resist` refuses a weaker amount of a
    type already standing -- the highest applies. So the standing number is
    read first and the sum handed over, which comes to +5 either way.

    The paragon line is out of scope.
    """
    for dtype in _types_of(c.trigger):
        standing = c.resistances(on=c.me).get(dtype, 0)
        c.resist(standing + 5, dtype, until=When.ENCOUNTER, on=c.me)


@power(
    "p16519",
    level=10,
    cls="endurance",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    requires=_has_a_surge,
    requires_text="you must have at least one healing surge remaining",
)
def p16519(c: Cast) -> None:
    """"You lose a healing surge" buys nothing, so it is `c.spend_surge`.

    "You cannot be weakened" is the refusal rather than the cure: nothing is
    standing to strip, and `c.immune` is what keeps the condition from
    arriving for the rest of the fight.
    """
    c.spend_surge(on=c.me)
    c.immune(Condition.WEAKENED, until=When.ENCOUNTER, on=c.me)
    c.resist(10, until=When.ENCOUNTER, on=c.me)
