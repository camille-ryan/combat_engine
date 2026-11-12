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

    **"Feats are not modelled at all" was the reason and it is false.** A
    feat is an ordinary row in `Powers.known`; `c.feat` asks whether a
    character has one, `c.feats(category=)` counts them by printed
    category, and `feat.trains` reaches `Skills.trained` through `chargen`.
    74 heroic feats ask about another feat. #692, #688.

    Inert for a different and sturdier reason: the clause is a permission
    exercised **at character creation** -- which multiclass feats a
    character may take -- and nothing in a fight reads how a feat was
    qualified for. That is a claim about the card rather than about the
    engine, so it cannot go stale the way the old one did. #677.
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


# -- the skald, #642's wave ------------------------------------------------
#
# Six rows, and every one of them is a line the bard beside it already
# answers in some form -- which is what makes this the second-cheapest of
# the sixteen chassis and a good place to learn the shape.


@power(
    "cf:bard-skald-f0",
    level=0,
    cls="bard",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def skald_charisma(c: Cast) -> None:
    """*"When you make a melee basic attack with a one-handed weapon, you
    can use Charisma instead of Strength for the attack roll and the damage
    roll."*

    `c.rolls_with("mba", CHA, when=...)` says exactly that:
    `Attack.ability_for` reads the swap *before* the header, and `mba`'s
    body reads `c.attack_mod`, so **both** rolls move on one line. That is
    the mechanism `cf:warlord-marshal-f0`'s note records wanting for its
    own bow clause.

    The gate is `(world, eid)` rather than an attack context -- "with a
    one-handed weapon" is a fact about what the skald is holding, which
    `query.holding` answers off the printed `hands` field. Asked live, so
    putting a two-hander in hand mid-fight takes the swap away, which is
    better than the arming-time reads most gear gates here settle for.
    """
    from combat_engine.engine.components import Gear
    from combat_engine.engine.types import Ability

    def one_handed(world, eid) -> bool:  # noqa: ANN001
        gear = world.get(eid, Gear)
        return (gear is not None and gear.main is not None
                and gear.main.hands == "one-handed")

    c.rolls_with("mba", Ability.CHA, on=c.me, until=When.ENCOUNTER,
                 when=one_handed)


@power(
    "cf:bard-skald-f1",
    level=0,
    cls="bard",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
    dropped=("chargen.dailies_per_day()",),
)
def skald_dailies(c: Cast) -> None:
    """*"You gain two 1st-level bard daily attack powers of your choice, but
    each day you can use only one bard attack power."*

    **Two clauses and they pull opposite ways**: the skald is dealt an
    extra daily and may spend fewer of them than it holds. The first is
    `chargen.EXTRA_GAINS`' shape -- the table `#1112` landed -- and the
    second has no home at all.

    `Powers.per_day` counts uses **per ref**, which is the printed clock
    for a row that says "once a day". What this card prints is a budget
    *across* rows -- one bard daily a day whatever you know, rising to two
    at 5th and three at 9th, and no more than one of a particular level --
    and nothing holds a per-character allowance over a family of rows.
    `c.spend_per_day` keyed on a shared label is the nearest thing and is
    the artificer's answer for its three infusions
    (`cf:artificer-f2`), but that is one pool for three **named** rows,
    not a cap over everything a class knows.

    So the marker names the budget rather than the gain: granting the extra
    daily without the cap makes the skald strictly stronger than print,
    which is the wrong direction to ship half a card in. Both halves land
    together or neither.
    """


@power(
    "cf:bard-skald-f2",
    level=0,
    cls="bard",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
)
def skald_virtue(c: Cast) -> None:
    """*"You gain the `p15849` power."* Declared and unmarked, so granted.

    **Inert today for `#1259`'s reason**, like `cf:wizard-witch-f0`: a
    power a feature grants has no printed level, so it imports at
    `level = 0` and `loadout` hands it to every bard. The grant stays
    because it is what the card says and is what will work once the import
    carries a chassis.
    """
    c.grant_row("p15849", on=c.me, until=When.ENCOUNTER)


@power(
    "cf:bard-skald-f3",
    level=0,
    cls="bard",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
)
def skald_untrained(c: Cast) -> None:
    """*"You gain a +1 bonus to untrained skill checks."*

    The same line as `cf:bard-f4` beside it, and its note carries the
    reasoning this inherits: the blanket `skill` key is read by
    `skills.modifier` on top of the per-skill one, and *"untrained is not
    gated, and cannot be"* -- `engine/skills.py` has no training model, so
    every check is an untrained one and the gate would have nothing to
    read. Exactly right today, one skill too wide the day a `Skills`
    component lands, and that is the one place to come back to.
    """
    c.bonus("skill", 1, until=When.ENCOUNTER, on=c.me, kind="untyped")


@power(
    "cf:bard-skald-f4",
    level=0,
    cls="bard",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.HEALING],
    dropped=("turns.short_rest(surges=)",),
)
def skald_song_of_rest(c: Cast) -> None:
    """The skald's Song of Rest, which is `cf:bard-f5`'s card again.

    *"When an affected character spends healing surges at the end of the
    rest, that character regains additional hit points equal to your
    Charisma modifier with each healing surge."*

    **The same gap and the same symbol as `cf:bard-f5`**, deliberately:
    the two rows print one card between them and the hold is identical, so
    one symbol over both is the rule working rather than the collapse
    `content/CLAUDE.md` warns about -- two rows measured to want the same
    thing sharing one symbol is what that file asks for.

    What is missing is one layer out from the symbol's name, which `#1257`
    records: `events.ShortRested` exists, and `turns.short_rest`'s own
    docstring declines to spend surges -- *"that is `Cast.surge`, not
    this"*. **Nothing calls `Cast.surge` at a rest**, so there is no
    spending for this to add to. A party-level decision rather than a
    parameter.

    The one-at-a-time clause it ends with has nothing to arbitrate until
    then, which is `cf:bard-f5`'s note in the same words.
    """


@power(
    "cf:bard-skald-f5",
    level=0,
    cls="bard",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
)
def skald_aura(c: Cast) -> None:
    """*"You gain the `p2887` power."* Declared and unmarked, so granted.

    `cf:bard-f6` grants the same ref to the plain bard -- which is the one
    pair `chargen.superseded_for` **keeps** rather than replacing, its own
    measurement naming `cf:bard-f6` and `-f6c0` as the 2 of 144 blank rows
    a named chassis does not cover. So a skald reaches this power by its
    own row and the bard by its own, which is the arrangement that
    measurement describes.

    Inert today for `#1259`'s reason, as `-f2` above.
    """
    c.grant_row("p2887", on=c.me, until=When.ENCOUNTER)
