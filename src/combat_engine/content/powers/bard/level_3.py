"""Bard, level 3: the encounter attacks.

Three of these target "one weapon", which the board has no notion of, so they
are aimed at the creature holding it -- `ONE_ALLY` at melee reach, which
includes the bard's own hand -- and the blessing is a one-shot watch on that
creature's next swing.
"""

from __future__ import annotations

from combat_engine.content.powers.bard._shared import free_near, square_of
from combat_engine.engine import *

ARCANE_IMPLEMENT = [Keyword.ARCANE, Keyword.IMPLEMENT]
ARCANE_WEAPON = [Keyword.ARCANE, Keyword.WEAPON]


def _ally_melee_missing(world: World, me: int, ev: Event) -> bool:
    """An ally's melee attack has been rolled and, as it stands, misses.

    Declared on `AttackRolled` rather than on `Miss`: the defence is read
    again once this window closes, so a penalty applied here still turns the
    swing into a hit, which is the whole of what the row is for. On `Miss`
    the comparison has already been made.
    """
    who = getattr(ev, "attacker", None)
    if who is None or who == me:
        return False
    if query.team(world, who) is not query.team(world, me):
        return False
    if not by_melee(world, me, ev):
        return False
    natural = getattr(ev, "natural", 0)
    if natural == 20:
        return False
    return natural == 1 or getattr(ev, "total", 0) < getattr(ev, "defence", 0)


@power(
    "p12513",
    level=3,
    cls="bard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.HEALING, Keyword.TELEPORTATION],
)
def p12513(c: Cast) -> None:
    """Whether the ally's charge landed is read off a `Hit` armed for the
    duration of the charge: `c.charge_at` says the swing happened, not that it
    connected, and `c.landed` is the bard's own last roll."""
    victim = c.target
    if victim is None:
        return
    mates = [a for a in c.within(10, side="ally") if a != c.me]
    pick = c.choose(mates, "which ally charges", optional=True)
    if pick is None:
        return
    landed: list[int] = []

    def seen(ev: Hit) -> None:
        if ev.attacker == pick and ev.target == victim:
            landed.append(1)

    watcher = c.watch(Hit, seen, until=When.EOT, on=c.me, label="p12513")
    c.charge_at(victim, who=pick)
    c.world.effects.end(watcher, "the charge is over")
    if not landed:
        return
    for mate in c.within(1, of=victim, side="ally"):
        if c.may("regain hit points rather than teleport", who=mate):
            c.heal(c.cha_mod, on=mate)
        else:
            c.teleport(1, who=mate)


@power(
    "p13789",
    level=3,
    cls="bard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*ARCANE_WEAPON, Keyword.PRIMAL],
    attack=Attack(CHA, vs=AC),
)
def p13789(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.cha_mod)
    ring = c.aura(2, until=When.EONT)
    for mate in c.allies():
        c.bonus(
            "attack", 1, on=mate, until=When.EONT,
            when=lambda ctx, w=mate: w in c.world.zones.occupants(ring), kind="power")
        c.bonus(
            "damage", 2, on=mate, until=When.EONT,
            when=lambda ctx, w=mate: w in c.world.zones.occupants(ring), kind="power")


@power(
    "p14458",
    level=3,
    cls="bard",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Melee(1),
    target=ONE_ALLY,
    keywords=[Keyword.ARCANE, Keyword.COLD],
)
def p14458(c: Cast) -> None:
    mate = c.target
    if mate is None:
        return

    def frost(ev: AttackRolled) -> None:
        if ev.attacker != mate:
            return
        c.slowed(on=ev.target, until=When.EOTNT)
        res = getattr(ev, "result", None)
        if res is not None and res.hit:
            c.damage("1d10", dtype=DamageType.COLD, on=ev.target)

    c.watch(AttackRolled, frost, until=When.EONT, on=mate, once=True, label="p14458")


@power(
    "p14459",
    level=3,
    cls="bard",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Melee(1),
    target=ONE_ALLY,
    keywords=[Keyword.ARCANE, Keyword.THUNDER],
)
def p14459(c: Cast) -> None:
    mate = c.target
    if mate is None:
        return

    def crack(ev: AttackRolled) -> None:
        if ev.attacker == mate:
            c.damage("2d6", dtype=DamageType.THUNDER, on=ev.target)

    c.watch(AttackRolled, crack, until=When.EONT, on=mate, once=True, label="p14459")


@power(
    "p14460",
    level=3,
    cls="bard",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Melee(1),
    target=ONE_ALLY,
    keywords=[Keyword.ARCANE],
)
def p14460(c: Cast) -> None:
    """"Attacks have combat advantage" is every enemy granting it to that one
    creature: the relation names a beneficiary, and there is no other side of
    it to set."""
    mate = c.target
    if mate is None:
        return
    c.bonus("damage", 2, on=mate, until=When.EONT, kind="power")
    for foe in c.enemies():
        c.grants_advantage(on=foe, to=mate, until=When.EONT)


@power(
    "p16509",
    level=3,
    cls="bard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC, Keyword.FEAR],
    attack=Attack(CHA, vs=WILL),
)
def p16509(c: Cast) -> None:
    if c.strike():
        c.damage("1d8", c.cha_mod, dtype=DamageType.PSYCHIC)
        c.penalty("attack", 2, until=When.EONT)


@power(
    "p2785",
    level=3,
    cls="bard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=ARCANE_WEAPON,
    attack=Attack(CHA, vs=AC),
)
def p2785(c: Cast) -> None:
    """The Constitution build is the printed Virtue of Valor line. `charge` is
    in the attack context, so "while charging" is a gate rather than a guess."""
    if not c.strike():
        return
    c.damage(c.w(2), c.cha_mod)
    swing = 1 + c.con_mod if c.build("f1s2") else 2
    for mate in c.within(5, side="ally"):
        if mate != c.me:
            c.bonus(
                "attack", swing, on=mate, until=When.EONT,
                when=lambda ctx: bool(ctx.get("charge")),
            )


@power(
    "p3080",
    level=3,
    cls="bard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10, by_weapon=True),
    target=ONE_CREATURE,
    keywords=[*ARCANE_WEAPON, Keyword.PSYCHIC],
    attack=Attack(CHA, vs=WILL),
)
def p3080(c: Cast) -> None:
    if not c.strike():
        return
    victim = c.target
    c.damage(c.w(2), c.cha_mod, dtype=DamageType.PSYCHIC)

    def topple(ev: Hit) -> None:
        if ev.target == victim:
            c.prone(on=victim)

    c.watch(Hit, topple, until=When.EONT, on=c.me, once=True, label="p3080")


@power(
    "p4991",
    level=3,
    cls="bard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=ARCANE_WEAPON,
    attack=Attack(CHA, vs=REF),
)
def p4991(c: Cast) -> None:
    if not c.strike():
        return
    victim = c.target
    c.damage(c.w(), c.cha_mod)
    extra = 1 + c.int_mod if c.build("f1s0") else 2
    for mate in c.within(5, side="ally"):
        if mate != c.me:
            c.bonus(
                "damage", extra, on=mate, until=When.EONT,
                when=lambda ctx: ctx.get("target") == victim,
            )


@power(
    "p4992",
    level=3,
    cls="bard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(CHA, vs=WILL),
)
def p4992(c: Cast) -> None:
    if not c.strike():
        return
    c.damage("2d6", c.cha_mod, dtype=DamageType.PSYCHIC)
    c.penalty("attack", 2, until=When.EONT)
    mates = [a for a in c.within(5, side="ally") if a != c.me]
    pick = c.choose(mates, "which ally makes a saving throw", optional=True)
    if pick is not None:
        c.save(on=pick)


@power(
    "p4993",
    level=3,
    cls="bard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FORCE],
    attack=Attack(CHA, vs=FORT),
)
def p4993(c: Cast) -> None:
    if not c.strike():
        return
    victim = c.target
    c.damage("1d10", c.cha_mod, dtype=DamageType.FORCE)
    mates = [a for a in c.within(20, side="ally") if a != c.me]
    pick = c.choose(mates, "which ally the target is slid beside", optional=True)
    spot = free_near(c, square_of(c, pick)) if pick is not None else None
    c.slide(5, on=victim, to=spot)


@power(
    "p5681",
    level=3,
    cls="bard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10, by_weapon=True),
    target=ONE_CREATURE,
    keywords=ARCANE_WEAPON,
    attack=Attack(CHA, vs=AC),
)
def p5681(c: Cast) -> None:
    """The damage reroll is left off: `DamageRolled` carries a total, not the
    dice that made it, so there is nothing to roll again."""
    if c.strike():
        c.damage(c.w(), c.cha_mod)


@power(
    "p5682",
    level=3,
    cls="bard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(CHA, vs=WILL),
)
def p5682(c: Cast) -> None:
    victim = c.target
    mates = [a for a in c.within(10, side="ally") if a != c.me]
    if c.strike():
        c.damage("1d6", c.cha_mod, dtype=DamageType.PSYCHIC)
        favoured = c.choose(mates, "which ally the target is exposed to")
        if favoured is not None:
            c.grants_advantage(on=victim, to=favoured, until=When.EONT)
    guarded = c.choose(mates, "which ally is harder to catch leaving")
    if guarded is not None:
        c.bonus(
            AC, 4, on=guarded, until=When.EONT,
            when=lambda ctx: bool(ctx.get("opportunity")),
        )


@power(
    "p5683",
    level=3,
    cls="bard",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=Ranged(10, by_weapon=True),
    target=ONE_CREATURE,
    keywords=ARCANE_WEAPON,
    attack=Attack(CHA, vs=REF),
    trigger="an ally misses with a melee attack",
    on=Trigger(AttackRolled, _ally_melee_missing, "an ally misses with a melee attack"),
)
def p5683(c: Cast) -> None:
    """Aimed at whoever the ally swung at, read off the trigger: the dispatcher
    points a single-enemy row at the creature the event is *about*, and here
    that is the ally, not the enemy. The Virtue of Prescience line wants a
    Wisdom build, which the bard's chassis does not offer."""
    victim = getattr(c.trigger, "target", None)
    if victim is None:
        return
    if c.strike(on=victim):
        c.damage(c.w(), c.cha_mod, on=victim)
    for which in (AC, FORT, REF, WILL):
        c.penalty(which, 4, on=victim, until=When.EOT)


@power(
    "p5684",
    level=3,
    cls="bard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.RADIANT],
    attack=Attack(CHA, vs=REF),
)
def p5684(c: Cast) -> None:
    """"Rolling twice and using the higher result" on a saving throw is two
    attempts: a save is pass or fail and the second only matters if the first
    failed."""
    if not c.strike():
        return
    victim = c.target
    c.damage("2d8", c.cha_mod, dtype=DamageType.RADIANT)
    for mate in c.within(1, of=victim, side="ally"):
        if not c.save(on=mate):
            c.save(on=mate)
