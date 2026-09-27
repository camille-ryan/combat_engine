"""Warlock: the two pact boons the later books print, and the tally one keeps.

Both carry a Prerequisite naming a pact, and `chargen.BUILDS["warlock"]`
now has a leg for each, so the prerequisite is a `requires=` gate the
interface refuses the row on rather than a sentence in a docstring.

**The dark pact's tally lives on `Mods`.** Nothing on a character holds a
number between uses of a row, and this one has to survive from the drop
that raises it to the interrupt that spends it. A stack of untyped +1
modifiers under one key is a counter with a duration already attached:
`c.total` reads it, and `When.ENCOUNTER` is exactly the printed "resets to
0 when you take a short rest". Raising it is the pact's payout and belongs
to `cf:warlock-f1`, which is where the other two pacts pay out; only the
spending is here.

**Two damage types at once** is one amount under the first of them, which
is the reading the rest of this class already uses.
"""

from __future__ import annotations

from combat_engine.content.features.builds import on_leg
from combat_engine.engine import (
    AT_WILL,
    INTERRUPT,
    NO_TARGET,
    PERSONAL,
    REACTION,
    SELF,
    AttackDeclared,
    Cast,
    DamageType,
    Dropped,
    Keyword,
    Trigger,
    When,
    World,
    cursed_by_me,
    get,
    power,
)
from combat_engine.engine.events import PowerUsed

#: The row that lays the curse, which both boons are clocked against.
CURSE = "cf:warlock-f4"

#: The key the dark pact's tally is kept under on `Mods`.
TALLY = "dark pact tally"


def tally(c: Cast) -> int:
    return c.total(TALLY)


def raise_tally(c: Cast, by: int = 1) -> None:
    c.bonus(TALLY, by, until=When.ENCOUNTER, on=c.me, kind="untyped")


def clear_tally(c: Cast) -> None:
    for effect in list(c.world.effects.of(c.me)):
        if effect.label.endswith(f"{TALLY}+1"):
            c.world.effects.end(effect, "the tally reset")


_A_CURSED_ENEMY_FALLS = "an enemy under your curse drops to 0 hit points"


@power(
    "p16254",
    level=1,
    cls="warlock",
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    requires=on_leg("elemental"),
    requires_text="needs the pact sworn to an element",
    trigger=_A_CURSED_ENEMY_FALLS,
    on=Trigger(Dropped, cursed_by_me, _A_CURSED_ENEMY_FALLS),
)
def p16254(c: Cast) -> None:
    """The payout lands on a creature that is not cursed yet, so the row
    arms a watch for the next curse instead of touching anybody now.

    `c.vulnerable` adds to whatever the creature already had, which is the
    printed "cumulative with the enemy's existing vulnerability"; and the
    curse lasts the encounter, so "until the curse ends" is that clock.
    """
    kind = c.element()
    if kind is None:
        return
    amount = 5 * (1 + (c.level >= 11) + (c.level >= 21))
    me = c.me

    def on_curse(ev: PowerUsed) -> None:
        if ev.actor != me or ev.power != CURSE:
            return
        for foe in ev.targets:
            c.vulnerable(amount, kind, on=foe, until=When.ENCOUNTER)

    # `once` is spent only when the handler actually did something, so an
    # unrelated power used in between does not burn the row's payout.
    c.watch(PowerUsed, on_curse, until=When.ENCOUNTER, on=me, once=True, label=c.ref)


_SWUNG_AT_ME = "an enemy makes a melee or a ranged attack against you"


def _melee_or_ranged_at_me(world: World, me: int, ev: AttackDeclared) -> bool:
    """Neither a burst nor a blast: the printed trigger names two reaches."""
    if ev.target != me or ev.attacker == me:
        return False
    declared = get(ev.power)
    reach = declared.reach if declared is not None else None
    return reach is not None and reach.kind in ("melee", "ranged")


@power(
    "p4311",
    level=1,
    cls="warlock",
    usage=AT_WILL,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.NECROTIC, Keyword.PSYCHIC],
    requires=on_leg("dark"),
    requires_text="needs the dark pact",
    trigger=_SWUNG_AT_ME,
    on=Trigger(AttackDeclared, _melee_or_ranged_at_me, _SWUNG_AT_ME),
)
def p4311(c: Cast) -> None:
    """No attack line is printed, so the damage simply lands; the `Hit:`
    heading on the card has nothing above it to roll.

    The header takes no target because the enemy is the one being answered
    and the dispatcher would aim the row at the warlock.
    """
    foe = getattr(c.trigger, "attacker", None)
    points = tally(c)
    if foe is None or points <= 0:
        return
    die = "d10" if c.level >= 21 else "d8" if c.level >= 11 else "d6"
    dealt = c.damage(f"{points}{die}", dtype=DamageType.NECROTIC, on=foe)
    clear_tally(c)
    if dealt >= 12:
        raise_tally(c)
        if c.may("weaken it for the attack", who=c.me):
            c.weakened(on=foe, until=When.EOT)
