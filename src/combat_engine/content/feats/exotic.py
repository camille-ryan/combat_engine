"""The exotic weapon chains: a proficiency feat and three powers each.

Every one of these is printed the same way. One feat grants proficiency
with a weapon and a rider on hitting with it; three more each "swap a
power you know" for a named card. The swap is 4e's retraining and means
"you have this power instead", so the parent is a plain `c.grant_row`
and the card beside it is an ordinary attack row.

**None of them carry a marker, and every one of them will report
UNUSED.** That is correct and is worth stating plainly, because the two
look alike from the summary line. The rows are complete: the attack, the
damage, the condition and the Requirement are all written. What is
missing is the *weapon* -- `chargen` deals sixteen and none of them is a
bola, a net or a whip -- so the Requirement is false for every character
the engine can currently build.

That is a chassis gap rather than a row gap, so it is tracked once as an
issue rather than marked on twelve rows. A `todo=` here would be a lie in
the other direction: it would say the engine cannot express these, and it
plainly can.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    EACH_OTHER,
    ENCOUNTER,
    FORT,
    FREE,
    MINOR,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    Ability,
    ActionType,
    Attack,
    Cast,
    CloseBurst,
    Condition,
    DamageRolled,
    Hit,
    Keyword,
    Melee,
    Ranged,
    Trigger,
    When,
    Window,
    power,
)
from combat_engine.engine.query import holding

WEAPON = [Keyword.WEAPON]


def _hit_with(what: str):  # noqa: ANN202
    """A hit landed with one named weapon, for a feat's own rider."""

    def when(world, me: int, ev) -> bool:  # noqa: ANN001
        return ev.attacker == me and bool(holding(world, me, what))

    return when


_hit_with_a_net = _hit_with("net")
_hit_with_a_whip = _hit_with("whip")


def _damaged_with(what: str):  # noqa: ANN202
    """My own attack damage, about to land, while one named weapon is held.

    The sibling of `_hit_with` for a card that trades the damage away
    rather than adding to it: the moment to answer is `DamageRolled` and
    not `Hit`, because that is the one a responder can refuse.

    `source` rather than `attacker` -- `DamageRolled` names the dealer that
    way -- and `from_attack` off the context, so the rider does not fire on
    ongoing damage or on a zone's burn.

    **"With your bola" is approximated by "holding one"**, exactly as
    `_hit_with` does for the whip and the net: the event carries the power
    that dealt it and not the weapon that swung, so holding is the nearest
    question the board can answer. A character wielding a bola and hitting
    with something else would get the offer wrongly; no dealt character
    holds two exotic weapons.
    """

    def when(world, me: int, ev) -> bool:  # noqa: ANN001
        ctx = getattr(ev, "ctx", None) or {}
        return (
            getattr(ev, "source", None) == me
            and getattr(ev, "amount", 0) > 0
            and bool(ctx.get("from_attack"))
            and bool(holding(world, me, what))
        )

    return when


_damaged_with_a_bola = _damaged_with("bola")


def _wielding(what: str):  # noqa: ANN202
    """A printed Requirement naming one weapon.

    False for every character `chargen` can build today, because it deals
    no such weapon -- which is why every row using this reports UNUSED
    rather than silent.
    """

    def gate(world, eid: int) -> bool:  # noqa: ANN001
        return bool(holding(world, eid, what))

    return gate


def _swap(ref: str, card: str):  # noqa: ANN202
    """"You can swap a power you know for X" -- you have X instead."""

    @power(ref, level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
           reach=PERSONAL, target=SELF)
    def parent(c: Cast) -> None:
        c.grant_row(card, on=c.me, until=When.ENCOUNTER)

    parent.__name__ = ref
    parent.__doc__ = f"Hands over {card} in place of a power of that level."
    return parent


# -- the bola ---------------------------------------------------------------


@power("f959", level=1, cls="", usage=AT_WILL, action=FREE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you hit with a weapon attack using your bola",
       on=Trigger(DamageRolled, _damaged_with_a_bola,
                  "you hit with a weapon attack using your bola",
                  window=Window.BEFORE),
       proficiency=("w3661",))
def f959(c: Cast) -> None:
    """Give the damage up to immobilise instead; a critical knocks prone too.

    **No verb was needed, and the marker said otherwise for a long time.**
    This carried `todo=("c.pre_empt(damage_of=)",)` on the premise that a
    row cannot decline its own damage. Two of the three rows that wore that
    symbol turned out to need nothing (#780): `c.strike()` rolls and does
    not pay, the body pays with `c.damage`, so declining is simply not
    calling it.

    This one is the exception `#780` then called the hard third, because the
    card names **a class of attacks** -- any weapon attack with the bola --
    rather than one power, so there is no body to write the clause into and
    `#550`'s convention does not reach it. The answer is not a registration
    keyed on the weapon: it is that `DamageRolled` is **refusable**, which
    `drivers.refusals` already asserts ("a refused blow takes no hit
    points"), and a free action may refuse one.

    So the trade is the event: answer the damage in `Window.BEFORE` and
    cancel it. `Trigger.window` exists for exactly this -- its own note says
    a handful of printed lines "cannot be said any other way".

    **The critical rides inside the same choice**, as the card prints, and
    is readable: `resolve` attaches the damage context to the event and
    `crit` is one of its keys, so the knockdown needs no second trigger and
    cannot fire without the trade.

    **`usage` was wrong and un-marking is what found it.** This was
    `ENCOUNTER`, and the card prints no limit at all -- which
    `content/CLAUDE.md` names as a real and silent narrowing for a row with
    a declared trigger, where `ENCOUNTER` means once a fight. `AT_WILL` is
    what the page says.

    `c.may` rather than `c.choose`, and `default=True` is deliberate: its
    docstring records that the order "is the answer for every fight run
    headless", so a `False` default would make this clause unreachable to
    every instrument. The consequence is that headless play always takes the
    trade, which is a scoring question for `policy/` rather than a rules
    one.
    """
    ev = c.trigger
    foe = getattr(ev, "target", None)
    if foe is None or not c.may("give up the damage to immobilise", who=c.me):
        return
    c.cancel()
    c.condition(Condition.IMMOBILIZED, until=When.EONT, on=foe)
    if (getattr(ev, "ctx", None) or {}).get("crit"):
        c.prone(on=foe)


_swap("f960", "f960b")


@power("f960b", level=1, cls="", usage=ENCOUNTER, action=STANDARD,
       reach=Ranged(10, by_weapon=True), target=ONE_CREATURE, keywords=WEAPON,
       attack=Attack(Ability.DEX, vs=REF),
       requires=_wielding("bola"), requires_text="you must be wielding a bola")
def f960b(c: Cast) -> None:
    """The 11th and 21st steps are out of scope."""
    if c.strike().hit:
        c.damage(c.w(2), c.dex_mod)
        c.condition(Condition.IMMOBILIZED, until=When.EONT)
        if c.crit:
            c.prone()


_swap("f961", "f961b")


@power("f961b", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=PERSONAL, target=SELF)
def f961b(c: Cast) -> None:
    """Regain the use of the other card in the chain."""
    c.restore_use("f960b")


_swap("f962", "f962b")


@power("f962b", level=1, cls="", usage=DAILY, action=STANDARD,
       reach=Ranged(10, by_weapon=True), target=ONE_CREATURE, keywords=WEAPON,
       attack=Attack(Ability.DEX, vs=REF),
       requires=_wielding("bola"), requires_text="you must be wielding a bola")
def f962b(c: Cast) -> None:
    """"Knocked prone and cannot stand" is prone plus the rooted-to-the-
    floor half, which is what `Condition.PINNED` says."""
    if c.strike().hit:
        c.damage(c.w(2), c.dex_mod + c.str_mod)
        c.prone()
        c.condition(Condition.PINNED, until=When.SAVE_ENDS)
    else:
        c.half_damage(c.w(2), c.dex_mod + c.str_mod)
        c.prone()
        c.condition(Condition.PINNED, until=When.EONT)


# -- the net ----------------------------------------------------------------


@power("f963", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you hit with a weapon attack using a net",
       on=Trigger(Hit, _hit_with_a_net, "you hit with a net"),
       proficiency=("w3660",))
def f963(c: Cast) -> None:
    """Both halves. `AT_WILL` because the card prints no limit, and an
    encounter budget on "when you hit" would spend the feat on the first
    blow of the fight."""
    c.condition(Condition.SLOWED, on=c.trigger.target, until=When.EONT)


_swap("f964", "f964b")


@power("f964b", level=1, cls="", usage=ENCOUNTER, action=STANDARD,
       reach=CloseBurst(1), target=EACH_OTHER, keywords=WEAPON,
       attack=Attack(Ability.STR, vs=FORT),
       requires=_wielding("net"), requires_text="you must be wielding a net")
def f964b(c: Cast) -> None:
    if c.strike().hit:
        c.damage(c.w(1), c.str_mod)
        c.condition(Condition.SLOWED, until=When.EONT)
        c.penalty("attack", 2, until=When.EONT)


_swap("f965", "f965b")


@power("f965b", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=WEAPON,
       requires=_wielding("net"), requires_text="you must be wielding a net")
def f965b(c: Cast) -> None:
    c.bonus(AC, 2, on=c.me, until=When.EONT, kind="power")
    c.bonus(REF, 2, on=c.me, until=When.EONT, kind="power")


_swap("f966", "f966b")


@power("f966b", level=1, cls="", usage=DAILY, action=STANDARD,
       reach=Melee(5), target=ONE_CREATURE, keywords=WEAPON,
       attack=Attack(Ability.STR, vs=REF),
       requires=_wielding("net"), requires_text="you must be wielding a net")
def f966b(c: Cast) -> None:
    """Reach 5 whatever the weapon says, which the header carries rather
    than the body -- `Melee(5)` is the printed Special line."""
    if c.strike().hit:
        c.damage(c.w(1), c.str_mod)
        c.grab()
        c.penalty("attack", 5)
    else:
        c.half_damage(c.w(1), c.str_mod)
        c.condition(Condition.IMMOBILIZED, until=When.EONT)


# -- the whip ---------------------------------------------------------------


@power("f967", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you hit a target with a whip",
       on=Trigger(Hit, _hit_with_a_whip, "you hit with a whip"),
       once_per_round=True,
       proficiency=("w3622",))
def f967(c: Cast) -> None:
    """The penalty, narrowed to the one creature it protects.

    **`proficiency=` was missing.** The card opens "You gain proficiency
    with the whip", and its two siblings -- `f959` for the bola, `f963` for
    the net -- both declare theirs. So a character taking this one was
    handed the rider and never the weapon, and `_hit_with_a_whip` could not
    be true of it. The first clause of the card was simply not written.

    "Against a target of your choice" was dropped for wanting an
    `against=` argument, and it does not need one. A penalty is a
    modifier laid on the creature that suffers it, and `c.penalty`
    passes `when=` through to `c.bonus`; the attack context carries the
    defender under `target`, so "only against that one" is the ordinary
    gate every "+2 against a creature you have cursed" row uses. Laid
    ungated this was the whip's victim's whole attack routine, which is
    much wider than the card.

    "Once per round" is the header's own field.
    """
    foe = c.trigger.target
    protected = c.choose(
        [c.me, *c.allies()], f"{c.ref}: whom the whip's victim cannot hit"
    )
    if protected is None:
        return
    c.penalty(
        "attack", 2, on=foe, until=When.EONT,
        when=lambda ctx: ctx.get("target") == protected,
    )


_swap("f968", "f968b")


@power("f968b", level=1, cls="", usage=ENCOUNTER, action=STANDARD,
       reach=Melee(2), target=ONE_CREATURE, keywords=WEAPON,
       attack=Attack(Ability.DEX, vs=REF),
       requires=_wielding("whip"), requires_text="you must be wielding a whip")
def f968b(c: Cast) -> None:
    """"Knock prone **or** pull 1" is a choice, and the scorer has no way
    to weigh one against the other -- prone is taken, because it costs the
    target its whole move to undo and a single square does not."""
    if c.strike().hit:
        c.damage(c.w(2), c.dex_mod)
        c.prone()
