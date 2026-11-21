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
    PERSONAL,
    SELF,
    STANDARD,
    WILL,
    WIS,
    YOU_OR_ONE_ALLY,
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
    allies = c.within(5, side="team")
    hurt = sorted((a for a in allies if c.wounded(a)), key=lambda a: -c.missing(a))
    return hurt or []


def _heal_an_ally(c: Cast) -> None:
    """You or an ally spends a surge and gets a little more besides.

    The printed text lets it land on the leader itself, so the pool is
    `side="team"` -- allies with the caster in it -- rather than `"ally"`.

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
    target=YOU_OR_ONE_ALLY,
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
    keywords=[Keyword.DIVINE, Keyword.CHANNEL_DIVINITY],
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
    keywords=[Keyword.DIVINE, Keyword.IMPLEMENT, Keyword.RADIANT, Keyword.CHANNEL_DIVINITY],
    attack=Attack(WIS, vs=WILL),
    group=CHANNEL_DIVINITY,
)
def p146(c: Cast) -> None:
    """Radiant light that only the undead feel.

    Its printed target line is "each undead creature in the burst", so
    everything else in the blast is simply not a target -- the body checks
    the creature's own type words rather than being handed a filtered list.
    """
    # **`i2775x1` is written here**, which is `#550`'s arrangement and the
    # one `i1461x1`/`p259` already uses: *"when you use your p146 power,
    # you can target creatures of the chosen kind instead of undead
    # creatures"*. The item names this row, so the clause lives in this
    # body gated on the holder, and the item stays declared as a pointer.
    #
    # **Not an `origin:undead` label on the chosen enemies**, which was
    # the tempting shortcut and is strictly stronger than print:
    # `query.kinds_of` would believe it, so they would be undead for
    # every other card in the fight.
    #
    # **The kind is chosen when the item is acquired, not per use**, which
    # is `chargen.BUILD_OPTIONS["i2775x1"]` and `c.chosen_option` the
    # reader. Written as a `c.choose` in this body first, and that was
    # stronger than print twice over: the holder could pick whichever
    # kind was standing in front of them, and this body runs once per
    # target so it could pick a different one for each. The card chooses
    # once, when the item changes hands.
    if not c.is_kind("undead"):
        if not c.feat("i2775x1"):
            return
        with c.credit("i2775x1"):
            if not c.is_kind(c.chosen_option("i2775x1") or ""):
                return
    if c.strike():
        c.damage("1d10", c.wis_mod, dtype=DamageType.RADIANT)
        c.push(3 + c.cha_mod)
        c.immobilized()
    else:
        c.half_damage("1d10", c.wis_mod, dtype=DamageType.RADIANT)


@power(
    "cf:cleric-templar-f1",
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

    **"By using a cleric power that has the healing keyword" is not asked.**
    `Healed` carries a source, a target and an amount and no power, so the
    only question available is whether this cleric sourced the heal. That
    is wider than the card by whatever a cleric restores hit points with
    that is not one of its own healing rows, which on the present tree is
    nothing.
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

    c.watch(SurgeSpent, spent, until=When.ENCOUNTER, on=me, label="cf:cleric-templar-f1")
    c.watch(
        Healed, more, until=When.ENCOUNTER, window=Window.BEFORE, on=me,
        label="cf:cleric-templar-f1",
    )


@power(
    "cf:cleric-templar-f3",
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
    "cf:warlord-marshal-f2",
    level=0,
    cls="warlord",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=CloseBurst(10),
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def warlord_senses(c: Cast) -> None:
    """A +2 to two skills, for the warlord and anybody who can see and hear it.

    The card names Insight and Perception, and `engine/skills.py` reads both
    off the `skill:<name>` modifier key -- the rogue's own hiding row asks
    `c.passive("perception")` of every enemy -- so the printed Effect does
    have somewhere to land. It was declared `out_of_combat` on the grounds
    that the engine had no skill checks, which stopped being true.

    Untyped: the card names no bonus type.

    **A snapshot, not an aura.** The ten squares are measured once, when
    `Encounter._arm_traits` runs this, exactly as the initiative leader
    feature measures its own; an ally that walks into range mid-fight does
    not pick the bonus up. A zone would follow the warlord, but nothing
    hangs modifiers on a zone's occupants, so the alternative is not a
    better reading, only a differently wrong one.

    Hearing is not modelled, so the printed "see and hear" is read as sight.

    **One of three, chosen by a fork rather than by a leg.** Camille's
    ruling on `#1296` was *"Do A"* -- two separate choices, one leader
    feature plus archer yes or no -- so `chargen.BUILD_OPTIONS` carries the
    three under `cf:warlord-marshal-f3`, the original, and each of them
    reads the answer. All four used to fire on every dealt marshal, which
    is `#1286`.

    The leg deliberately no longer decides it: that coupling made the
    leader feature a consequence of the presence choice, and a mapping for
    the other five legs would have had to be invented.

    This row's own note used to end *"`chargen.BUILDS["warlord"]` has a leg
    for only one of the three, so there is nothing to gate this on"*. That
    was true of the legs and is why the fork exists: it was the one of the
    three that fired for **every** marshal, on top of whichever other one
    the leg allowed.
    """
    if c.chosen_option("cf:warlord-marshal-f3") != "cf:warlord-marshal-f2":
        return
    # **`side="team"`, and the warlord was missing its own bonus.** The card
    # opens *"You and any ally within 10 squares of you"*, and `"ally"`
    # excludes the caster by design -- `Cast._side`'s own note: *"a card
    # that means you as well says 'you and each ally', and `team` is that
    # pool"*. So the `who != c.me` guard below could never fire and the
    # warlord got nothing from its own feature. `cf:warlord-marshal-f3`
    # beside it has always been right, by naming `on=c.me` outright.
    #
    # The sight test still only applies to somebody else: a creature can
    # always see itself, and asking `can_see` of the caster is what the
    # dead guard was for.
    for who in c.within(10, side="team"):
        if who != c.me and not c.can_see(who):
            continue
        c.bonus("skill:insight", 2, until=When.ENCOUNTER, on=who, kind="untyped")
        c.bonus("skill:perception", 2, until=When.ENCOUNTER, on=who, kind="untyped")
