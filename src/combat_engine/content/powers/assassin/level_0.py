"""Assassin, level 0: the class features and the weapon at-wills.

Two things recur and are worth saying once.

* **The weapons are not in the table.** Garrote, bola, blowgun, hand
  crossbow, shuriken and kusari-gama have no entry, so a `requires=` gate on
  them would be false forever and the row would never be offered. Those rows
  carry the printed line as `requires_text` and no gate; "light blade" is a
  real group and is gated properly.
* **Assassin poisons are items.** Every "if you deliver an assassin poison"
  clause is about a consumable smeared on the blade, which nothing models,
  so those sentences are dropped rather than approximated.

The shroud is a counter rather than a stack of effects: the count is the only
thing anything reads, and a count can be cleared in one line when the shrouds
are invoked, which a set of modifiers cannot.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    DEX,
    ENCOUNTER,
    FREE,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    ActionType,
    Attack,
    AttackRolled,
    Cast,
    CloseBurst,
    Condition,
    DamageType,
    Dropped,
    Effect,
    Event,
    Gear,
    Hit,
    Keyword,
    Melee,
    Miss,
    Ranged,
    Trigger,
    UpTo,
    When,
    World,
    both,
    by_me,
    get,
    power,
)
from combat_engine.engine.query import adjacent, creatures, distance_between

MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]

SHROUD_MAX = 4

#: (world, assassin) -> [watch armed]. The count lives on the creature as a
#: `Shrouds` component; this is only the once-per-fight arming flag, keyed on
#: the world so a second encounter arms its own watch.
_SHROUDS: dict[tuple[int, int], list[int]] = {}


def _light_blade(world: World, eid: int) -> bool:
    gear = world.get(eid, Gear)
    weapon = gear.main if gear is not None else None
    return weapon is not None and weapon.group == "light blade"


def _beside_a_creature(world: World, eid: int) -> bool:
    return any(who != eid and adjacent(world, eid, who) for who in creatures(world))


def _struck_with_a_weapon(squares: int) -> Callable[[World, int, Event], bool]:
    """Hit a creature within N squares of me, with something that is a
    weapon rather than an implement."""

    def check(world: World, me: int, ev: Event) -> bool:
        who = getattr(ev, "target", None)
        if who is None or distance_between(world, me, who) > squares:
            return False
        p = get(getattr(ev, "power", "") or "")
        return p is not None and Keyword.WEAPON in p.keywords

    return check


def _ends_on_my_attack(c: Cast, effects: list[Effect | None]) -> None:
    """"The form lasts until you make an attack roll", which no duration
    says: the effects are ended by hand off my own next roll."""

    def stop(ev: AttackRolled) -> None:
        if ev.attacker != c.me:
            return
        for eff in effects:
            if eff is not None:
                c.world.effects.end(eff)

    c.watch(AttackRolled, stop, until=When.EONT, on=c.me, label=f"{c.ref} ends")


def _killed_beside_me(world: World, me: int, ev: Event) -> bool:
    who = getattr(ev, "actor", None)
    return (
        getattr(ev, "source", None) == me and who is not None and adjacent(world, me, who)
    )


# -- the features ----------------------------------------------------------


@power(
    "p9400",
    level=0,
    cls="assassin",
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(10),
    target=ONE_CREATURE,
    keywords=[Keyword.SHADOW],
    once_per_round=True,
)
def p9400(c: Cast) -> None:
    """Invoking is armed once as a watch on my own attacks against whoever
    currently carries the shrouds: hit or miss the dice land, one die fewer
    on a miss, and the count clears. The printed "all or none" choice is
    always taken -- declining wins nothing and costs the shrouds nothing.

    The count itself is `c.shroud`/`c.shrouds`, so a later row reading "for
    each shroud on that enemy" has something to ask; it is cleared **after**
    the damage rather than before, so that question is still answerable from
    inside the blow the shrouds paid for."""
    victim = c.target
    if victim is None:
        return
    c.shroud(on=victim, cap=SHROUD_MAX)
    armed = _SHROUDS.setdefault((id(c.world), c.me), [0])
    if armed[0]:
        return
    armed[0] = 1
    per = 0 if c.level < 11 else (3 if c.level < 21 else 6)

    def invoke(ev: Any) -> None:
        if ev.attacker != c.me or c.shrouds(ev.target) <= 0:
            return
        count = c.shrouds(ev.target) - (1 if isinstance(ev, Miss) else 0)
        if count > 0:
            c.flat(c.roll(f"{count}d6") + count * per, on=ev.target)
        c.spend_shrouds()

    c.watch(Hit, invoke, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} shrouds")
    c.watch(Miss, invoke, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} shrouds")


@power(
    "p9401",
    level=0,
    cls="assassin",
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.SHADOW, Keyword.TELEPORTATION],
    requires=_beside_a_creature,
    requires_text="must be adjacent to a creature",
)
def p9401(c: Cast) -> None:
    """"To a square adjacent to a different creature" is a constraint on the
    destination and `c.teleport` has no way to carry one, so the square is
    left to the world's decider."""
    c.teleport(3 if c.level < 11 else (4 if c.level < 21 else 5))


@power(
    "p9402",
    level=0,
    cls="assassin",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.SHADOW],
)
def p9402(c: Cast) -> None:
    """The Stealth half is narrative. Sustain Minor is not written: the two
    effects run to the end of my next turn or until I attack, whichever the
    fight reaches first."""
    thin = c.insubstantial(until=When.EONT, on=c.me)
    weak = c.vulnerable(5, DamageType.RADIANT, until=When.EONT, on=c.me)
    _ends_on_my_attack(c, [thin, weak])


@power(
    "p13799",
    level=0,
    cls="assassin",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL],
    trigger="you hit a creature within 5 squares of you with a weapon attack",
    on=Trigger(
        Hit,
        both(by_me, _struck_with_a_weapon(5)),
        "you hit a creature within 5 squares of you with a weapon attack",
    ),
)
def p13799(c: Cast) -> None:
    """The victim is read off the triggering `Hit` rather than targeted: the
    row is Personal and the printed target is "the creature you hit"."""
    victim = getattr(c.trigger, "target", None)
    if victim is None:
        return
    dice = 1 + sum(c.level >= n for n in (3, 7, 13, 17, 23, 27))
    if c.is_(Condition.HELPLESS, on=victim):
        c.flat(dice * 10, on=victim)
    else:
        c.damage(f"{dice}d10", on=victim)


@power(
    "p14372",
    level=0,
    cls="assassin",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL],
    trigger="you hit a creature within 5 squares of you with a weapon attack",
    on=Trigger(
        Hit,
        both(by_me, _struck_with_a_weapon(5)),
        "you hit a creature within 5 squares of you with a weapon attack",
    ),
)
def p14372(c: Cast) -> None:
    victim = getattr(c.trigger, "target", None)
    if victim is None:
        return
    dice = 1 + (c.level >= 11) + (c.level >= 21)
    if c.is_(Condition.HELPLESS, on=victim):
        c.flat(dice * 10, on=victim)
    else:
        c.damage(f"{dice}d10", on=victim)


@power(
    "p14399",
    level=0,
    cls="assassin",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.SHADOW, Keyword.FIRE, Keyword.NECROTIC],
)
def p14399(c: Cast) -> None:
    """"Fire and necrotic damage" is one number of two types and `c.flat`
    takes one, so it lands as fire; dealing it twice would double the row.
    The free shroud that comes with the form is dropped -- it is a rule about
    another power's usage limit, not an effect."""
    amount = 5 if c.level < 11 else (10 if c.level < 21 else 15)
    armour = c.resist(amount, until=When.EONT, on=c.me)

    def retaliate(ev: Hit) -> None:
        p = get(getattr(ev, "power", "") or "")
        if ev.target != c.me or p is None or p.reach is None or p.reach.kind != "melee":
            return
        c.flat(amount, dtype=DamageType.FIRE, on=ev.attacker)

    watcher = c.watch(Hit, retaliate, until=When.EONT, on=c.me)
    _ends_on_my_attack(c, [armour, watcher])


# -- the weapon at-wills ----------------------------------------------------


@power(
    "p13793",
    level=0,
    cls="assassin",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=REF),
    requires_text="must use a garrote, against a creature you are hidden from",
)
def p13793(c: Cast) -> None:
    """The grab is held on a named effect rather than on `c.grab`, because
    only an effect can carry the printed Sustain Standard and its payout.
    "You cannot make other attacks" has no `Cast` method and is dropped;
    neither has "cannot speak", which is not a combat effect anyway."""
    c.shift(2)
    victim = c.target
    if victim is None or not c.strike():
        return
    c.damage(c.w(2), c.dex_mod)
    c.grab(on=victim)
    c.penalty(
        "attack",
        -2,
        until=When.EONT,
        on=victim,
        when=lambda ctx: ctx.get("target") == c.me,
    )
    hold = c.effect(f"{c.ref} garrote", until=When.SUSTAIN, on=victim, sustain=STANDARD)
    c.on_sustain(hold, lambda: c.damage(c.w(2), c.dex_mod, on=victim))


@power(
    "p13794",
    level=0,
    cls="assassin",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    requires_text="must use a dagger",
)
def p13794(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(), c.dex_mod)


@power(
    "p13795",
    level=0,
    cls="assassin",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
)
def p13795(c: Cast) -> None:
    """"Shift back to your starting position" names the square outright, so
    the square is remembered before the first shift and handed to `to=`."""
    start = c.here
    c.shift(1)
    if c.strike():
        c.damage(c.w())
        c.prone()
        c.shift(1, to=start)


@power(
    "p13796",
    level=0,
    cls="assassin",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=REF),
    requires_text="must use a bola",
)
def p13796(c: Cast) -> None:
    if c.strike():
        c.damage(c.w())
        c.prone()


@power(
    "p13797",
    level=0,
    cls="assassin",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=REF),
    requires_text="must use a blowgun",
)
def p13797(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(), c.dex_mod)


@power(
    "p13798",
    level=0,
    cls="assassin",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    no_provoke=True,
    requires_text="must use a hand crossbow",
)
def p13798(c: Cast) -> None:
    """Range 1 is what the entry prints, odd as it looks for a crossbow."""
    if c.strike():
        c.damage(c.w(), c.dex_mod)
    c.shift(2)


@power(
    "p13806",
    level=0,
    cls="assassin",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    requires=_light_blade,
    requires_text="needs a hand free and a light blade",
)
def p13806(c: Cast) -> None:
    """The escape penalty is dropped -- escaping a grab is rolled inside the
    engine and nothing can put a number on that one attempt. So is the
    clause letting a missed swing still spend the strike, which is a rule
    about another row's usage."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.damage(c.w())
    c.grab(on=victim)
    c.grants_advantage(until=When.EONT, on=victim, to="allies")
    hold = c.effect(f"{c.ref} hold", until=When.SUSTAIN, on=victim, sustain=MINOR)
    c.on_sustain(hold, lambda: c.grab(on=victim))


@power(
    "p15911",
    level=0,
    cls="assassin",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    requires_text="must use a short sword",
)
def p15911(c: Cast) -> None:
    """"If you have jumped, fallen, or flown this turn" has nothing to ask --
    none of the three is kept -- so the conditional combat advantage is
    dropped. The charge clause is a substitution rule, not an effect."""
    if c.strike():
        c.damage(c.w(), c.dex_mod)


@power(
    "p15912",
    level=0,
    cls="assassin",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(3),
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    requires_text="must use shuriken",
)
def p15912(c: Cast) -> None:
    if c.strike():
        c.damage(c.w())


@power(
    "p15913",
    level=0,
    cls="assassin",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=REF),
    requires_text="must use a kusari-gama",
)
def p15913(c: Cast) -> None:
    """The second end of the weapon is a secondary attack against the same
    creature, rolled by hand because the header holds one attack line."""
    if not c.strike():
        return
    c.damage(0, c.dex_mod)
    c.prone()
    c.shift(1)
    if c.attack(c.dex_, AC):
        c.damage(c.w())


@power(
    "p13813",
    level=0,
    cls="assassin",
    usage=ENCOUNTER,
    action=FREE,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.SHADOW],
    trigger="you kill an adjacent creature",
    on=Trigger(Dropped, _killed_beside_me, "you kill an adjacent creature"),
    out_of_combat=True,
)
def p13813(c: Cast) -> None:
    """The corpse is already off the board; trapping it in a trinket changes
    nothing in the fight, so the row is deliberately inert."""
    c.note(f"{c.ref}: the corpse is trapped in a small object you carry")
