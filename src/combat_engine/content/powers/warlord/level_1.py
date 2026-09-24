"""Warlord, level 1.

The warlord spends its turn making somebody else's turn better, so most of
these bodies are a `c.choose` for which friend benefits followed by a bonus,
a shift or a heal aimed at them with `on=`.

Three printed lines have no vocabulary here and are marked with `c.note`
rather than approximated: granting an ally an attack, granting an ally an
opportunity attack, and a conditional "cannot shift".
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    ENCOUNTER,
    FORT,
    ONE_CREATURE,
    REF,
    STANDARD,
    STR,
    WILL,
    Attack,
    Cast,
    Keyword,
    Melee,
    When,
    power,
)
from combat_engine.engine.events import Hit

MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]


def _beside(c: Cast, foe: int | None) -> list[int]:
    """Allies adjacent to you or to the target, which is the warlord's pool.

    `c.within(..., side="ally")` counts the caster, and every printed line
    that uses this phrase says "an ally", so the caster comes back out.
    """
    near = set(c.within(1, side="ally"))
    if foe is not None:
        near |= set(c.within(1, of=foe, side="ally"))
    return sorted(near - {c.me})


# -- at-will ---------------------------------------------------------------


@power(
    "p1061",
    level=1,
    cls="warlord",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
)
def p1061(c: Cast) -> None:
    """No attack of your own: the whole power is an ally's free attack.

    Nothing in `Cast` makes another creature attack, so this records what
    would happen instead of pretending something did.
    """
    foe = c.target
    helpers = [a for a in c.within(1, of=foe, side="ally") if a != c.me]
    who = c.choose(helpers, "which ally strikes")
    name = f"ally {who}" if who is not None else "an ally"
    c.note(
        f"p1061: {name} would make a melee basic attack against {foe} as a free action, "
        f"with {c.int_mod:+d} damage -- granting an ally an attack is not expressible"
    )


@power(
    "p1063",
    level=1,
    cls="warlord",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p1063(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.str_mod)
    # The Effect line lands hit or miss. The trigger is armable, but what it
    # would fire -- an ally's opportunity attack -- is not.
    c.note(
        f"p1063: if {c.target} shifts before the start of your next turn it would provoke "
        "an opportunity attack from an ally of your choice -- not expressible"
    )


@power(
    "p315",
    level=1,
    cls="warlord",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=FORT),
)
def p315(c: Cast) -> None:
    """No weapon dice at all -- you point, and a friend takes the shot."""
    if c.strike():
        c.damage(0, c.str_mod)
        foe = c.target
        helpers = _beside(c, foe)
        if not helpers:
            return
        friend = c.choose(helpers, "who gets the opening")
        against = lambda ctx: ctx.get("target") == foe  # noqa: E731
        c.bonus("attack", c.cha_mod, on=friend, until=When.EOTNT, when=against, once=True)
        c.bonus("damage", c.cha_mod, on=friend, until=When.EOTNT, when=against, once=True)


@power(
    "p620",
    level=1,
    cls="warlord",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p620(c: Cast) -> None:
    """The Special line comes first: a friend steps, then you swing."""
    helpers = _beside(c, c.target)
    if helpers:
        c.shift(1, who=c.choose(helpers, "who steps before the blow"))
    if c.strike():
        c.damage(c.w(1), c.str_mod)


# -- encounter --------------------------------------------------------------


@power(
    "p1064",
    level=1,
    cls="warlord",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p1064(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.str_mod)
        foe = c.target
        helpers = _beside(c, foe)
        if not helpers:
            return
        friend = c.choose(helpers, "who gets the guard")
        # "against the target's attacks": a defence mod is gated on who is
        # attacking, which is what the attacker sees in `ctx`.
        # One build makes this 1 + Charisma; `c.build(...)` can say which
        # now, so the rider is expressible where the printed +2 was all
        # this could say before.
        c.bonus(AC, 2, on=friend, when=lambda ctx: ctx.get("attacker") == foe)


@power(
    "p1066",
    level=1,
    cls="warlord",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p1066(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.str_mod)
        foe = c.target
        helpers = [a for a in c.within(5, side="ally") if a != c.me]
        if not helpers:
            return
        friend = c.choose(helpers, "who gets the opening")
        # Tactical Presence would make this 1 + Intelligence; no build to read.
        c.bonus("attack", 2, on=friend, when=lambda ctx: ctx.get("target") == foe)


@power(
    "p1412",
    level=1,
    cls="warlord",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=REF),
)
def p1412(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.str_mod)
        foe = c.target
        helpers = [a for a in c.within(1, of=foe, side="ally") if a != c.me]
        who = c.choose(helpers, "which ally strikes")
        name = f"ally {who}" if who is not None else "an ally"
        c.note(
            f"p1412: {name} would make a melee basic attack against {foe} as a free action, "
            f"with {c.cha_mod:+d} damage -- granting an ally an attack is not expressible"
        )


@power(
    "p1554",
    level=1,
    cls="warlord",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p1554(c: Cast) -> None:
    """Somebody trades places with the creature you just hit.

    The pool from `c.within(1, of=foe, side="ally")` already reads "you, only
    if you are adjacent to it, or an ally adjacent to it" -- the caster is in
    that list exactly when the printed proviso says so.

    A true swap cannot be written: `c.slide` has no destination argument, so
    the creature is slid a square and the swapper steps into the space it
    left, which is the same two squares of movement without the guarantee
    that they cross.
    """
    if c.strike():
        c.damage(c.w(2), c.str_mod)
        foe = c.target
        swappers = c.within(1, of=foe, side="ally")
        if not swappers:
            return
        who = c.choose(swappers, "who changes places with it")
        vacated = c.there
        if who is not None and c.slide(1, on=foe):
            c.shift(who=who, to=vacated)


# -- daily ------------------------------------------------------------------


@power(
    "p154",
    level=1,
    cls="warlord",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p154(c: Cast) -> None:
    landed = c.strike()
    if landed:
        c.damage(c.w(3), c.str_mod)
    for friend in [a for a in c.within(5, side="ally") if a != c.me]:
        if landed:
            for defence in (AC, FORT, REF, WILL):
                c.bonus(defence, 1, on=friend, until=When.ENCOUNTER)
        # The Effect line does not care whether the attack landed.
        c.temp_hp(5 + c.cha_mod, on=friend)


@power(
    "p239",
    level=1,
    cls="warlord",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p239(c: Cast) -> None:
    """Hit and miss differ only in the size of the bonus."""
    if c.strike():
        c.damage(c.w(3), c.str_mod)
        value = 1 + c.int_mod
    else:
        c.half_damage(c.w(3), c.str_mod)
        value = 1
    foe = c.target
    against = lambda ctx: ctx.get("target") == foe  # noqa: E731
    # "you and each ally within 5" is exactly what the ally pool holds.
    for friend in c.within(5, side="ally"):
        c.bonus("attack", value, on=friend, when=against)


@power(
    "p431",
    level=1,
    cls="warlord",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p431(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(3), c.str_mod)
    # "Cannot shift, while two of your allies flank it" is a conditional
    # veto on one kind of movement. Immobilised would stop everything, and
    # stop it unconditionally, so it is the wrong card.
    c.note(
        f"p431: for the rest of the encounter {c.target} could not shift while two of your "
        "allies were adjacent to it -- a conditional bar on shifting is not expressible"
    )


@power(
    "p1572",
    level=1,
    cls="warlord",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p1572(c: Cast) -> None:
    """A standing arrangement: every hit somebody lands nudges a friend.

    Hit and miss both leave the same trigger behind; they differ only in who
    gets to set it off, so one closure serves both with a different gate.
    """

    def nudge(ev: Hit) -> None:
        if not allowed(ev.attacker):
            return
        friends = [a for a in c.within(1, of=ev.attacker, side="ally") if a != ev.attacker]
        if friends:
            c.slide(1, on=c.choose(friends, "who is nudged a square"))

    if c.strike():
        c.damage(c.w(3), c.str_mod)
        beside_me = [a for a in c.within(1, side="ally") if a != c.me]
        if beside_me:
            c.slide(1, on=c.choose(beside_me, "who you shove a square"))
        squad = {c.me, *c.allies()}
        # "you or an ally within 10 squares of you" is asked when the hit
        # happens, not now -- people move.
        allowed = lambda who: who in squad and (who == c.me or c.distance(who) <= 10)  # noqa: E731
        c.watch(Hit, nudge, until=When.ENCOUNTER, label="p1572 (hit)")
    else:
        pool = [a for a in c.within(10, side="ally") if a != c.me]
        chosen = c.choose(pool, "who learns the trick") if pool else None
        if chosen is None:
            return
        allowed = lambda who: who == chosen  # noqa: E731
        c.watch(Hit, nudge, until=When.ENCOUNTER, label="p1572 (miss)")


# The class feature, p1590, is already written -- it is the same printed row
# as the cleric's heal and lives with it in `content/features/leaders.py`.
