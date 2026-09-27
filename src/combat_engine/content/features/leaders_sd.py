"""The later leaders' class-page features: the runepriest's rune states and
one of its traditions, and the artificer's bonus feat.

The runepriest had exactly one declared row before this file -- the heal --
and that row is only the *second* of the three things its class page prints.
The first is the pair of states the class is built around, and nothing in
the tree said it was missing: the heal simply paid out one state's rider
unconditionally, so the class read as finished and the choice it is named
for did not exist.

The shaman's page is the other shape and has nothing here: its five
companion spirits are five declared rows with two derived legs between them,
and the boon each one carries is not in the imported text at all. Both are
in `docs/blocked.json` rather than folded into a leg that cannot mean them.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    ENCOUNTER,
    FORT,
    NO_TARGET,
    PERSONAL,
    REF,
    WILL,
    ActionType,
    Cast,
    DamageApplied,
    Keyword,
    When,
    power,
)
from combat_engine.engine.query import adjacent, team

from .builds import on_leg

#: The two rune states, as the label of the hold that says which one this
#: runepriest is in. `p11353` reads them back: it prints a rider per state
#: and used to pay the first of the two whatever state the runepriest was
#: in, which is the whole feature decided by nothing.
DESTRUCTION = "cf:runepriest-rune destruction"
PROTECTION = "cf:runepriest-rune protection"


def rune_state(c: Cast) -> str:
    """Which state this runepriest stands in, or the empty string."""
    for held in c.world.effects.of(c.me):
        if held.label in (DESTRUCTION, PROTECTION):
            return held.label
    return ""


@power(
    "cf:runepriest-rune",
    level=0,
    cls="runepriest",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.DIVINE],
)
def runepriest_rune(c: Cast) -> None:
    """The state the runepriest fights in, and what its neighbours get for it.

    **The state is chosen once, when the fight begins.** The printed rule is
    that choosing a rune is part of using a power that carries the runic
    keyword, and that the state then stands until another is chosen or the
    encounter ends. `Keyword` has no member for runic and no row announces a
    rune, so there is nothing for a change of state to happen *on*; the
    switch is `cf:runepriest-rune-switch` in `docs/blocked.json`. What is
    written is the half that is real either way -- the runepriest is in one
    of the two states for the whole fight, and the benefit of being in it.

    The first option is the one `p11353` already paid out, so a fight nobody
    is steering plays exactly as it did: `World.decide` takes the head of
    the list.

    **A snapshot of who the allies are, not an aura**, for the reason
    `cf:warlord-senses` gives -- nothing re-arms a trait when somebody
    walks in. Where the printed line is geometric it stays geometric: both
    riders are gated modifiers that ask about adjacency at the moment the
    roll or the damage happens, so an ally that steps away from the
    runepriest loses the resistance and gets it back on stepping in.

    "Or to any other runepriests who are in this rune state" is dropped: one
    runepriest is what a party has, and reading the other half would mean
    hunting the board for creatures carrying this label -- a clause with no
    case on any board the tree can build.
    """
    me = c.me
    state = c.choose(
        [DESTRUCTION, PROTECTION], "cf:runepriest-rune: which state to stand in"
    )
    if state is None:
        return
    c.effect(state, until=When.ENCOUNTER, on=me)
    friends = c.allies()
    if not friends:
        return

    if state == DESTRUCTION:
        # "Allies gain a +1 bonus to attack rolls against enemies that are
        # adjacent to you." No bonus type is printed, so untyped.
        def beside_me(ctx: dict[str, Any]) -> bool:
            victim = ctx.get("target")
            return victim is not None and adjacent(c.world, me, victim)

        for friend in friends:
            c.bonus(
                "attack", 1, until=When.ENCOUNTER, on=friend,
                kind="untyped", when=beside_me,
            )
        return

    # "While adjacent to you, allies gain resist 2 to all damage", rising a
    # step at 11th and again at 21st. `c.resist` with a `when=` is a
    # modifier rather than a flat entry on `Defences`, which is what lets
    # the geometry be asked at the moment the damage lands.
    amount = 2 + 2 * sum(lv <= c.level for lv in (11, 21))
    for friend in friends:
        c.resist(
            amount, until=When.ENCOUNTER, on=friend,
            when=lambda ctx, who=friend: adjacent(c.world, me, who),
        )


@power(
    "cf:runepriest-tradition",
    level=0,
    cls="runepriest",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.DIVINE],
    requires=on_leg("second-con"),
    requires_text="needs the tradition this belongs to",
)
def runepriest_tradition(c: Cast) -> None:
    """Which of the three printed traditions this runepriest follows.

    One of the three is written, and it is the only one either derived leg
    can be *asked* about. The class has two secondaries, Constitution and
    Wisdom; one tradition pays a Constitution modifier and the other two
    both pay a Wisdom modifier, so `second-wis` cannot tell those two apart
    and neither can anything else -- the compendium prints no build section
    for this class. The Constitution one is here and the pair is
    `cf:runepriest-tradition-rest` in `docs/blocked.json`.

    The leg is asked in the header rather than in the body: a feature that
    is one of a printed choose-one belongs to its leg and nowhere else, and
    `requires=` is where the interface can see that. A body test would have
    armed a row for every runepriest and had it quietly do nothing on half
    of them.

    "Regardless of the number of times the enemy damages you in a round" is
    `stacks=False`: a second blow from the same enemy renews the bonus
    rather than doubling it. The gate is on the *enemy*, not on the round,
    because the printed duration is the runepriest's next turn and two
    different attackers each earn their own.

    The rest of the tradition is a weapon proficiency, which the engine does
    not model either way and which the chassis already carries the group
    for.
    """
    me = c.me
    if c.con_mod <= 0:
        return
    extra = c.con_mod

    def repaid(ev: DamageApplied) -> None:
        foe = ev.source
        if ev.target != me or ev.amount <= 0 or foe is None or foe == me:
            return
        if team(c.world, foe) is team(c.world, me):
            return
        c.bonus(
            "damage", extra, until=When.EONT, on=me, stacks=False,
            when=lambda ctx, f=foe: ctx.get("target") == f,
        )

    c.watch(
        DamageApplied, repaid, until=When.ENCOUNTER, on=me,
        label="cf:runepriest-tradition",
    )


@power(
    "cf:artificer-rituals",
    level=0,
    cls="artificer",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
    out_of_combat=True,
)
def artificer_rituals(c: Cast) -> None:
    """A bonus feat that lets the artificer perform rituals, and nothing else.

    Inert for the reason `cf:cleric-rituals` is. The artificer's other three
    class-page features are all about magic items -- empowering one,
    recharging one, and paying temporary hit points when an ally spends an
    item's daily power -- and the tree has no magic items at all; see
    `cf:artificer-items` in `docs/blocked.json`.
    """


#: What "a +1 bonus to all defenses" comes to, for `p11353`'s second rider.
#: Lives here beside the rune states rather than in that file, because the
#: rider it belongs to is the one this file decides.
ALL_DEFENCES = (AC, FORT, REF, WILL)
