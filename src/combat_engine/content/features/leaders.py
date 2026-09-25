"""The leaders' features: healing a friend, and the divine channels.

A leader's job is that the party is better with it than without, and the
heal is most of that. Both the cleric's and the warlord's are the same
printed row with a different keyword on it, so they are the same function
twice rather than one shared one -- they are separate rows in the book and a
later errata to one should not silently move the other.

The cleric's two channelled rows share a budget rather than a use each:
`group=CHANNEL_DIVINITY` is the printed "only one of these per encounter",
and `dsl._group_spent` enforces it across every row carrying the name.
"""

from __future__ import annotations

from combat_engine.engine import (
    EACH_ENEMY,
    ENCOUNTER,
    FREE,
    MINOR,
    NO_TARGET,
    ONE_ALLY,
    PERSONAL,
    SELF,
    STANDARD,
    WILL,
    WIS,
    ActionType,
    Attack,
    Cast,
    CloseBurst,
    DamageType,
    Healed,
    Keyword,
    SurgeSpent,
    When,
    Window,
    power,
)

from . import CHANNEL_DIVINITY


def _worst_hurt(c: Cast) -> list[int]:
    """Who the heal offers, worst off first.

    Order is not cosmetic. `World.decide` takes the first option when
    nobody is playing, so the list *is* the decision for every headless
    fight -- and offering the whole party unsorted had the cleric healing
    whoever happened to be first, at full health, for nothing.

    Anybody untouched comes last, behind the option to keep the power.
    """
    allies = c.within(5, side="ally")
    hurt = sorted((a for a in allies if c.wounded(a)), key=lambda a: -c.missing(a))
    return hurt or []


def _heal_an_ally(c: Cast) -> None:
    """You or an ally spends a surge and gets a little more besides.

    The printed text lets it land on the leader itself, so `c.within(5,
    side="ally")` -- which includes the caster -- is exactly right here
    without filtering.

    Both halves are a printed **may**, and both are asked. Offering only the
    wounded meant that with nobody yet hurt the power fired, found an empty
    list, and was spent on nothing.
    """
    who = c.choose(_worst_hurt(c), "who is healed", optional=True,
                   decline="nobody -- keep the power")
    if who is None:
        return
    if not c.may("spend a healing surge", who=who):
        return
    if c.surge(on=who):
        c.heal(c.roll("1d6"), on=who)


@power(
    "p1590",
    level=0,
    cls="warlord",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    keywords=[Keyword.HEALING, Keyword.MARTIAL],
    uses=2,
    once_per_round=True,
)
def p1590(c: Cast) -> None:
    """Twice a fight, but not twice in one round -- the Special line."""
    _heal_an_ally(c)


@power(
    "p1589",
    level=0,
    cls="cleric",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.DIVINE],
    group=CHANNEL_DIVINITY,
)
def p1589(c: Cast) -> None:
    """A small bonus to the cleric's next attack roll or saving throw.

    Applied to both, and the first one used consumes it, which is what
    "your next attack roll **or** saving throw" means.
    """
    c.bonus("attack", 1, until=When.EONT, on=c.me, once=True)
    c.bonus("save", 1, until=When.EONT, on=c.me)


@power(
    "p146",
    level=0,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.DIVINE, Keyword.IMPLEMENT, Keyword.RADIANT],
    attack=Attack(WIS, vs=WILL),
    group=CHANNEL_DIVINITY,
)
def p146(c: Cast) -> None:
    """Radiant light that only the undead feel.

    Its printed target line is "each undead creature in the burst", so
    everything else in the blast is simply not a target -- the body checks
    the creature's own type words rather than being handed a filtered list.
    """
    if not c.is_kind("undead"):
        return
    if c.strike():
        c.damage("1d10", c.wis_mod, dtype=DamageType.RADIANT)
        c.push(3 + c.cha_mod)
        c.immobilized()


@power(
    "cf:cleric-surge",
    level=0,
    cls="cleric",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.DIVINE, Keyword.HEALING],
)
def cleric_surge(c: Cast) -> None:
    """The cleric's heals are worth more than they say on the card.

    `Healed` is announced before the hit points go on, so the amount is
    still negotiable -- the same seam `c.half_healing` uses from the other
    side.

    The printed condition is "only if the healing involves the creature
    spending a healing surge", and no event carries both facts at once. So
    the surge is remembered when it is spent and claimed by the **next**
    heal that lands on the same creature, whoever sourced it: that pairing
    is what "involves" means, and it disarms itself correctly on a second
    wind, where the creature spends its own surge and heals itself and this
    cleric had nothing to do with it.

    A heal with no surge before it -- the second half of the cleric's own
    twice-a-round word, which adds dice on top -- is left alone, which is
    the printed rule and not an oversight.
    """
    me, extra = c.me, c.wis_mod
    owed: set[int] = set()

    def spent(ev: SurgeSpent) -> None:
        owed.add(ev.actor)

    def more(ev: Healed) -> None:
        if ev.target not in owed:
            return
        owed.discard(ev.target)
        if ev.source == me:
            ev.amount += extra

    c.watch(SurgeSpent, spent, until=When.ENCOUNTER, on=me, label="cf:cleric-surge")
    c.watch(
        Healed, more, until=When.ENCOUNTER, window=Window.BEFORE, on=me,
        label="cf:cleric-surge",
    )


@power(
    "cf:cleric-rituals",
    level=0,
    cls="cleric",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.DIVINE],
    out_of_combat=True,
)
def cleric_rituals(c: Cast) -> None:
    """A bonus feat that lets the cleric perform rituals, and nothing else.

    Deliberately inert rather than unwritten: there is no ritual in a fight
    and no combat consequence to invent. The body is empty rather than a
    note, because `Encounter._arm_traits` runs a trait at the start of every
    fight and a line in the log saying so would be announcing a thing that
    is not happening.
    """


@power(
    "cf:warlord-senses",
    level=0,
    cls="warlord",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=CloseBurst(10),
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
    out_of_combat=True,
)
def warlord_senses(c: Cast) -> None:
    """A +2 to two skills, for the warlord and anybody who can see and hear it.

    The engine has no skill checks at all, so the whole printed Effect is
    outside a fight -- `out_of_combat=True` rather than an invented mechanic,
    which is what the flag is for.

    It is printed as one of three mutually exclusive leader features and
    `chargen.BUILDS["warlord"]` forks on an ability score rather than on
    this, so there is no leg to gate it on; the other two are in
    `docs/blocked.json`.
    """
