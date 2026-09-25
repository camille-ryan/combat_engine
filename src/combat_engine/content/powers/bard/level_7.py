"""Bard, level 7: the encounter attacks that answer somebody else's turn.

Three of them are immediate actions aimed at the creature the trigger names
rather than at a header target, so the bodies read `c.trigger`: the dispatcher
only redirects a single-**enemy** row, and "the triggering ally" is the other
half of that sentence.
"""

from __future__ import annotations

from combat_engine.content.powers.bard._shared import free_near, square_of
from combat_engine.engine import *

ARCANE_IMPLEMENT = [Keyword.ARCANE, Keyword.IMPLEMENT]
ARCANE_WEAPON = [Keyword.ARCANE, Keyword.WEAPON]


def _ally_hits_enemy(world: World, me: int, ev: Event) -> bool:
    """One of my allies has landed a blow on an enemy within 10 squares."""
    who = getattr(ev, "attacker", None)
    foe = getattr(ev, "target", None)
    if who is None or foe is None or who == me:
        return False
    mine = query.team(world, me)
    if query.team(world, who) is not mine or query.team(world, foe) is mine:
        return False
    return query.distance_between(world, me, foe) <= 10


def _enemy_hits_ally(world: World, me: int, ev: Event) -> bool:
    who = getattr(ev, "attacker", None)
    mate = getattr(ev, "target", None)
    if who is None or mate is None or mate == me:
        return False
    mine = query.team(world, me)
    if query.team(world, mate) is not mine or query.team(world, who) is mine:
        return False
    return query.distance_between(world, me, mate) <= 10


def _idle_ally(world: World, me: int, ev: Event) -> bool:
    """An ally within 10 finished its turn without swinging at anything.

    Read back off the bus log to the turn's own start: nothing records "has
    attacked this turn", and a row that fired whether or not the ally had
    already acted would be a different card.
    """
    who = getattr(ev, "actor", None)
    if who is None or who == me or getattr(ev, "ghost", False):
        return False
    if query.team(world, who) is not query.team(world, me):
        return False
    if query.distance_between(world, me, who) > 10:
        return False
    for past in reversed(world.bus.log):
        if isinstance(past, TurnStart) and past.actor == who:
            return True
        if isinstance(past, AttackDeclared) and past.attacker == who:
            return False
    return True


@power(
    "p12516",
    level=7,
    cls="bard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=UpTo(3),
    keywords=[*ARCANE_IMPLEMENT, Keyword.THUNDER, Keyword.TELEPORTATION],
    attack=Attack(CHA, vs=FORT),
)
def p12516(c: Cast) -> None:
    if not c.strike():
        return
    victim = c.target
    c.damage("1d10", c.cha_mod, dtype=DamageType.THUNDER)
    mates = [a for a in c.within(10, side="ally") if a != c.me]
    pick = c.choose(mates, "which ally is pulled to the target", optional=True)
    if pick is None:
        return
    spot = free_near(c, square_of(c, victim))
    if spot is None or not c.teleport(20, who=pick, to=spot):
        return
    c.bonus(
        "attack", 3, on=pick, until=When.EONT, once=True,
        when=lambda ctx: ctx.get("target") == victim,
    )


@power(
    "p13446",
    level=7,
    cls="bard",
    usage=ENCOUNTER,
    action=REACTION,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(CHA, vs=WILL),
    trigger="an enemy within range misses with an attack",
    on=Trigger(Miss, enemy_within(10), "an enemy within 10 squares misses"),
)
def p13446(c: Cast) -> None:
    """The secondary attack is rolled per enemy with `c.strike(on=...)`, which
    uses the header's attack line for each. "That can hear you" is not a thing
    the board models, so every enemy within 2 is caught."""
    primary = c.target
    if primary is None:
        return
    c.penalty("attack", 2, on=primary, until=When.EOT)
    for foe in c.within(2, of=primary, side="enemy"):
        if c.strike(on=foe):
            c.grants_advantage(on=foe, to="allies", until=When.EOTNT)
            c.flat(c.int_mod, dtype=DamageType.PSYCHIC, on=primary)


@power(
    "p13790",
    level=7,
    cls="bard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=MeleeOrRanged(1, 10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_WEAPON, Keyword.COLD, Keyword.CONJURATION, Keyword.PRIMAL],
    attack=Attack(CHA, vs=REF),
)
def p13790(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.damage(c.w(2), c.cha_mod, dtype=DamageType.COLD)
    spot = free_near(c, square_of(c, victim))
    if spot is None:
        return
    spirit = c.conjure(at=spot, until=When.EONT, sustain=None, aura=1)
    if not spirit:
        return

    def bite(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor not in c.enemies():
            return
        if c.adjacent_to(spirit, ev.actor):
            c.flat(5, dtype=DamageType.COLD, on=ev.actor)
            c.slide(1, on=ev.actor)

    c.watch(TurnEnd, bite, until=When.EONT, on=c.me, label="p13790")


@power(
    "p14466",
    level=7,
    cls="bard",
    usage=ENCOUNTER,
    action=REACTION,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE],
    trigger="an enemy within 10 squares of you is hit by your ally's attack",
    on=Trigger(Hit, _ally_hits_enemy, "an ally hits an enemy within 10 squares"),
)
def p14466(c: Cast) -> None:
    """Aimed off the trigger: the dispatcher points a single-enemy row at the
    creature the event is about, and on a `Hit` that is the ally who swung."""
    foe = getattr(c.trigger, "target", None)
    if foe is not None:
        c.damage("1d12", on=foe)


@power(
    "p14467",
    level=7,
    cls="bard",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
    trigger="an ally within 10 squares of you is hit by an enemy's attack",
    on=Trigger(Hit, _enemy_hits_ally, "an ally within 10 squares is hit"),
)
def p14467(c: Cast) -> None:
    """The extra 1d8 is rolled up front and handed over as a flat damage bonus
    for the one swing: `c.grant_attack` takes a number, and a die rolled now
    is the same die rolled then."""
    mate = getattr(c.trigger, "target", None)
    foe = getattr(c.trigger, "attacker", None)
    if mate is None or foe is None:
        return
    c.grant_attack(mate, on=foe, damage_bonus=c.roll("1d8"))


@power(
    "p14468",
    level=7,
    cls="bard",
    usage=ENCOUNTER,
    action=REACTION,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
    trigger="an ally within 10 squares of you ends its turn without having attacked",
    on=Trigger(TurnEnd, _idle_ally, "an ally ends its turn without having attacked"),
)
def p14468(c: Cast) -> None:
    """"Even if dominated or stunned" is dropped: `c.grant_attack` and
    `c.charge_at` both go through the usual act gate and there is no way past
    it."""
    mate = getattr(c.trigger, "actor", None)
    if mate is None:
        return
    foes = c.enemies()
    if not foes:
        return
    mark = c.choose(foes, "who the ally goes after")
    if mark is None:
        return
    extra = c.roll("1d10")
    if c.may("charge rather than swing from where it stands", who=mate):
        c.charge_at(mark, who=mate)
    else:
        c.grant_attack(mate, on=mark, damage_bonus=extra)


@power(
    "p2369",
    level=7,
    cls="bard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(CHA, vs=WILL),
)
def p2369(c: Cast) -> None:
    if not c.strike():
        return
    victim = c.target
    c.damage("2d6", c.cha_mod, dtype=DamageType.PSYCHIC)
    mates = [c.me, *[a for a in c.within(10, side="ally") if a != c.me]]
    pick = c.choose(mates, "who the target loses sight of")
    if pick is not None:
        c.invisible(to=victim, on=pick, until=When.EONT)


@power(
    "p2376",
    level=7,
    cls="bard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.NECROTIC],
    attack=Attack(CHA, vs=REF),
)
def p2376(c: Cast) -> None:
    """Two separate one-shots, one on the target's roll and one on the ally's,
    both taken on the announcement while the outcome is still open."""
    if not c.strike():
        return
    victim = c.target
    c.damage("1d8", c.cha_mod, dtype=DamageType.NECROTIC)
    mates = [a for a in c.within(5, side="ally") if a != c.me]
    keeper = c.choose(mates, "whose roll you may stand in for", optional=True)
    theirs: list[int] = []
    ours: list[int] = []

    def swap(ev: AttackRolled) -> None:
        res = getattr(ev, "result", None)
        if res is None:
            return
        if not theirs and ev.attacker == victim:
            theirs.append(1)
        elif keeper is not None and not ours and ev.attacker == keeper and ev.target == victim:
            ours.append(1)
        else:
            return
        if not c.may("replace that attack roll with your own", who=c.me):
            return
        face = c.roll("1d20")
        res.total += face - res.natural
        res.natural = face

    c.watch(AttackRolled, swap, until=When.EONT, on=c.me, label="p2376")
