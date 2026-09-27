"""The bard's class page, and the ardent's mantle.

Neither class had a single `cf:` row before this file. The bard's page
prints seven features and the tree had the two that happen to carry a
compendium id of their own; the ardent's prints three and the tree had one.
Everything else was invisible: not written, not blocked, not counted.

Two of the bard's are deliberately inert -- a ritual feat and a feat-choice
permission, neither of which has a combat consequence to invent -- and they
are declared `out_of_combat=True` for the same reason `cf:cleric-templar-f3`
is: the flag is the difference between *decided* and *forgotten*.
"""

from __future__ import annotations

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
    CloseBurst,
    Keyword,
    When,
    power,
)
from combat_engine.engine.events import Bloodied, DamageApplied, Dropped, Miss

#: The four defences, for the mantle's one modifier laid four times.
_DEFENCES = (AC, FORT, REF, WILL)


@power(
    "cf:bard-f0",
    level=0,
    cls="bard",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
    out_of_combat=True,
)
def bard_rituals(c: Cast) -> None:
    """A bonus feat, a ritual book, and a daily ritual that costs no
    components. There is no ritual in a fight and nothing to invent, so this
    is inert on purpose rather than unwritten -- the same call, and the same
    empty body, as `cf:cleric-templar-f3`.
    """


@power(
    "cf:bard-f3",
    level=0,
    cls="bard",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
    out_of_combat=True,
)
def bard_versatility(c: Cast) -> None:
    """Permission to take multiclass feats from more than one class.

    Feats are not modelled at all -- `features/__init__` says so in its
    first paragraph -- so this is a rule about character building with no
    reading in a fight. Inert on purpose.
    """


@power(
    "cf:bard-f4",
    level=0,
    cls="bard",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
)
def bard_skills(c: Cast) -> None:
    """+1 to untrained skill checks.

    The blanket `skill` modifier key is read by `skills.modifier` on top of
    the per-skill one, so a bonus to every check is one line.

    **"Untrained" is not gated, and cannot be.** `engine/skills.py` has no
    training model -- it says so in its own first paragraph -- so every
    check in the game is an untrained one and the gate would have nothing
    to read. The number this lays is therefore exactly right today and
    becomes one skill too wide the moment a `Skills` component lands; that
    is the one place to come back to.
    """
    c.bonus("skill", 1, until=When.ENCOUNTER, on=c.me, kind="untyped")


@power(
    "cf:bard-f1",
    level=0,
    cls="bard",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=CloseBurst(5),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
)
def bard_virtue(c: Cast) -> None:
    """Whichever of the three printed virtues the leg took.

    `chargen.BUILDS["bard"]` is derived, so the two legs are `second-int`
    and `second-con` -- and two of the three virtues key off exactly those
    two abilities, which settles both without a guess. The third keys off
    Wisdom, the bard's dump stat, and has no leg; it is also the only one
    of the three that is an immediate interrupt rather than a free action,
    so it is recorded rather than folded into either of these.

    Both written legs are once per round and both are a printed "you can",
    which is asked.

    **The Constitution leg answers "bloodies an enemy" through the blow
    rather than through `Bloodied`.** That event carries an actor and no
    source, so it cannot say who did it; `resolve.damage` emits it in the
    same breath as the `DamageApplied` immediately before it, so the last
    blow landed on that creature is who bloodied it, exactly. The kill half
    reads `Dropped.source`, which carries one.
    """
    me = c.me
    last_hit: dict[int, int] = {}
    paid = {"round": 0}

    def once_this_round() -> bool:
        if paid["round"] == c.world.round:
            return False
        paid["round"] = c.world.round
        return True

    if c.build("f1s0"):
        reach = 5 + c.int_mod

        def on_miss(ev: Miss) -> None:
            who = ev.target
            if ev.attacker not in c.enemies() or who == me:
                return
            if who not in c.within(reach, side="ally"):
                return
            if not c.may("slide the ally a square", who=me) or not once_this_round():
                return
            c.slide(1, on=who)

        c.watch(Miss, on_miss, until=When.ENCOUNTER, on=me, label="cf:bard-f1")
        return

    if not c.build("f1s2"):
        return

    # 1 + Constitution modifier, rising by two at each of the two printed
    # tiers. Written as the card's arithmetic rather than as three numbers,
    # because the header cannot carry a tier and the body can.
    amount = 1 + 2 * sum(lv <= c.level for lv in (11, 21)) + c.con_mod

    def reward(ally: int) -> None:
        if ally == me or ally not in c.within(5, side="ally"):
            return
        if not c.may("take temporary hit points", who=ally) or not once_this_round():
            return
        c.temp_hp(amount, on=ally)

    def on_damage(ev: DamageApplied) -> None:
        last_hit[ev.target] = ev.source

    def on_bloodied(ev: Bloodied) -> None:
        if ev.actor in c.enemies():
            reward(last_hit.get(ev.actor, -1))

    def on_dropped(ev: Dropped) -> None:
        # `query.enemies` drops the dead, so the creature that just fell is
        # not in it -- compare sides directly, as `Dropped`'s own docstring
        # warns.
        from combat_engine.engine.query import team

        if ev.source is None or team(c.world, ev.actor) is team(c.world, me):
            return
        reward(ev.source)

    c.watch(DamageApplied, on_damage, until=When.ENCOUNTER, on=me, label="cf:bard-f1")
    c.watch(Bloodied, on_bloodied, until=When.ENCOUNTER, on=me, label="cf:bard-f1")
    c.watch(Dropped, on_dropped, until=When.ENCOUNTER, on=me, label="cf:bard-f1")


@power(
    "cf:ardent-f0",
    level=0,
    cls="ardent",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=CloseBurst(5),
    target=NO_TARGET,
    keywords=[Keyword.PSIONIC],
)
def ardent_mantle(c: Cast) -> None:
    """The first of the three mantles, on the first of the three legs.

    This row is the parent's ref carrying `cf:ardent-f0s0`'s content, which
    is where it was written before the class had legs. It used to be
    unconditional -- every ardent in the tree wore this mantle *and* the
    other two -- and `chargen.BUILDS["ardent"]` now has a leg per mantle,
    so it is gated like its two siblings in `features/primal_shadow.py`.

    `p10273`'s own rider is a different sentence and stays unconditional in
    its file: it is the surge power's, not this mantle's.

    `opportunity` is a key the attack context carries and `query.defence`
    is handed that context, so "a bonus to all defences against opportunity
    attacks" is four gated modifiers and nothing more.

    `stacks=False` buckets every one of them under this row's own ref,
    which is shared by every ardent that has it -- so the printed "if a
    character is in the radius of more than one of these, only the highest
    applies" is true across two ardents as well as within one.

    **A snapshot, not an aura**, exactly as `cf:warlord-marshal-f2` is: the
    five squares are measured once when `Encounter._arm_traits` runs this,
    and an ally that walks into range later does not pick it up. Nothing
    hangs modifiers on a zone's occupants, so an aura would be a
    differently wrong reading rather than a better one.
    """
    if not c.build("f0s0"):
        return

    def against_openings(ctx: dict) -> bool:
        return bool(ctx.get("opportunity"))

    nearby = c.within(5, side="ally")
    if c.wis_mod > 0:
        for who in nearby:
            for d in _DEFENCES:
                c.bonus(
                    d, c.wis_mod, until=When.ENCOUNTER, on=who,
                    stacks=False, when=against_openings,
                )
    for who in nearby:
        # The skill half is the allies' and not the ardent's own.
        if who == c.me:
            continue
        c.bonus("skill:insight", 2, until=When.ENCOUNTER, on=who, stacks=False)
        c.bonus("skill:perception", 2, until=When.ENCOUNTER, on=who, stacks=False)
