"""The hunter, the ranger's third chassis and the last of `#642`'s
martial wave.

35 printed rows, and it shares eight of them almost word for word with the
scout: the knacks, the aspects of the wild, the Perception reroll and all
five of `-f20`'s abilities. Those are written out again rather than shared,
for `cf:rogue-thief-f1`'s reason -- a hunter is dealt no scout row, so if
these did not pay the clause nobody would -- and each says which scout row
it mirrors so the two files can be read side by side.

The shape:

    13  play
     4  a rung superseding a lower number -- `#1261`
     2  another use of `p13588` per encounter
     4  a knack or an aspect of the wild, chosen at creation
     5  rows a fight has no use for -- `out_of_combat=True`
     1  "two of the following abilities" -- a fork that deals TWO
     7  `defect=`: a list the import did not carry

## The one clause that had to go into another row

`-f11` reads *"when you hit with `p13588`, you can **blind** the target
until the end of your next turn, **instead of** immobilizing or dazing
it."* That is not a rider: `p13588`'s body already asks
`c.choose(["hold", "daze"], ...)` and this feature adds a third answer to
that question. No modifier can reach into another row's `c.choose`.

So the clause lives in `p13588`, gated on holding this feature -- which is
`content/CLAUDE.md`'s `#550` arrangement (*"a feat that names one power
writes its clause into that power"*) applied to a **class feature**, and
the reader is the same: `c.feat(ref)` asks whether a ref is in
`Powers.known`, and a class feature is an ordinary row there.

The row stays declared as the pointer, as `#550` says a feat-side row
does, and its weapon fork is what it pays itself.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.features.strikers import _weapon_attack
from combat_engine.engine import (
    ENCOUNTER,
    NO_TARGET,
    PERSONAL,
    ActionType,
    Cast,
    Condition,
    Gear,
    Keyword,
    When,
    get,
    power,
)
from combat_engine.engine.events import Hit

#: The row `-f11`'s fork answers and `-f3`/`-f8` would add a use of.
SHOT = "p13588"

#: The two ranged groups the chassis's forks key on.
CROSSBOW = "crossbow"
BOW = "bow"

#: The reaches `-f10` exempts. "Your ranged attacks" and nothing else --
#: an area attack is not a ranged one, which is the distinction
#: `features/bladesinger.py` draws from the other side by naming both.
_RANGED = ("ranged",)


def _a_weapon_attack(c: Cast) -> Any:
    """"Weapon attacks" -- the keyword on the row that is rolling."""
    me, world = c.me, c.world
    return lambda ctx: _weapon_attack(world, me, ctx) is not None


def _a_ranged_row(ctx: dict[str, Any]) -> bool:
    """"Your ranged attacks" -- off the row that is rolling."""
    rolling = get(ctx.get("power") or "")
    return rolling is not None and rolling.reach.kind in _RANGED


def _group_in_hand(c: Cast, group: str) -> bool:
    """Is the ranged weapon being used one of this group?

    `Gear.ranged` and not `Gear.main`: a hunter carries a bow and a blade,
    and every fork on this chassis is about *"your choice of ranged
    weapon"*. Reading the main hand would answer about the blade.
    """
    gear = c.world.get(c.me, Gear)
    shooter = gear.ranged if gear is not None else None
    return shooter is not None and shooter.group == group


# -- the thirteen rows that play ---------------------------------------------


def _grant(ref: str, got: str, why: str) -> Any:
    """One of the four "you gain <power or feat>" rows."""

    @power(
        ref,
        level=0,
        cls="ranger",
        usage=ENCOUNTER,
        action=ActionType.NONE,
        reach=PERSONAL,
        target=NO_TARGET,
        keywords=[Keyword.MARTIAL],
    )
    def row(c: Cast) -> None:
        c.grant_row(got, on=c.me, until=When.ENCOUNTER)

    row.__name__ = "hunter_grant_" + ref.rsplit("-f", 1)[-1]
    row.__doc__ = f'"You gain `{got}`."\n\n{why}'
    return row


hunter_grant_0 = _grant(
    "cf:ranger-hunter-f0", SHOT,
    "A no-op grant: a level-0 ranger row, so `chargen.loadout` has already "
    "dealt it. Written out because `-f3`, `-f8` and `-f11`'s whole fork "
    "are about that row. `#1259`.")
hunter_grant_5 = _grant(
    "cf:ranger-hunter-f5", "p13600",
    "**A real grant, and the level is why.** Level 5 is above a level-1 "
    "character, so the draw cannot reach it -- `cf:ranger-scout-f6` grants "
    "the same ref for the same reason.")


@power(
    "cf:ranger-hunter-f2",
    level=0,
    cls="ranger",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def hunter_accuracy(c: Cast) -> None:
    """"You gain a +1 bonus to the attack rolls of weapon attacks."

    `cf:fighter-slayer-f2`'s and `cf:fighter-knight-f5`'s sentence, on a
    third class. Untyped: a class feature stacks with everything.
    """
    c.bonus("attack", 1, on=c.me, until=When.ENCOUNTER, kind="untyped",
            when=_a_weapon_attack(c))


@power(
    "cf:ranger-hunter-f6",
    level=0,
    cls="ranger",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def hunter_damage(c: Cast) -> None:
    """"You gain a +1 bonus to the damage rolls of weapon attacks."

    **The ladder `-f12` and `-f15` climb is written here**: both print
    *"increases to"*, so they are pointers carrying `implemented_in=` and
    this body reads them. Rising order and plain `if`, so the highest held
    replaces rather than adds.
    """
    bonus = 1
    if c.feat("cf:ranger-hunter-f12"):
        bonus = 2
    if c.feat("cf:ranger-hunter-f15"):
        bonus = 3
    c.bonus("damage", bonus, on=c.me, until=When.ENCOUNTER, kind="untyped",
            when=_a_weapon_attack(c))


@power(
    "cf:ranger-hunter-f10",
    level=0,
    cls="ranger",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def hunter_unhindered(c: Cast) -> None:
    """"Your ranged attacks don't provoke opportunity attacks."

    `c.no_provoke(when=)` gated on the rolling row's `reach.kind`, which is
    where the printed line lives. **Ranged and not area**, unlike
    `cf:wizard-bladesinger-f6`, which names both -- the card here says one
    word and a close burst is neither.

    No weapon clause: the bladesinger's version requires a one-handed melee
    weapon in hand and this one requires nothing.
    """
    c.no_provoke(on=c.me, until=When.ENCOUNTER, when=_a_ranged_row)


@power(
    "cf:ranger-hunter-f11",
    level=0,
    cls="ranger",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def hunter_shot(c: Cast) -> None:
    """Two clauses, and the first one lives in another row.

    *"When you hit with `p13588`, you can blind the target until the end
    of your next turn, **instead of** immobilizing or dazing it."*
    `p13588`'s body already asks `c.choose(["hold", "daze"], ...)` and this
    adds a third answer -- no modifier can reach into another row's
    `c.choose`, so the clause is written **there**, gated on holding this
    feature.

    That is `content/CLAUDE.md`'s `#550` arrangement applied to a class
    feature rather than a feat, and the reader is the same verb:
    `c.feat(ref)` asks whether a ref is in `Powers.known`, and a class
    feature is an ordinary row there. This row stays declared as the
    pointer, which is what `#550` says the feat-side row does.

    The second clause is this row's own: a **parent** choosing between two
    benefits keyed to the ranged weapon. `chargen.BUILD_OPTIONS`, and both
    options are declared below.
    """
    chose = (c.chosen_option("cf:ranger-hunter-f11")
             or "cf:ranger-hunter-f11s0")
    c.grant_row(chose, on=c.me, until=When.ENCOUNTER)


def _shot_rider(ref: str, group: str, what: str) -> Any:
    """One of `-f11`'s two benefits: a rider on a `p13588` hit, keyed to a
    ranged weapon group.

    **`Hit` and not `PowerResolved`.** The slayer's and the knight's forks
    answer *"when you use `p12668`"*, which is a no-action row spent after
    a hit; this one answers *"when you **hit** with `p13588`"*, which is
    the hit itself. `p13588` is a standard-action attack, so `Hit` carries
    both the power and the victim and there is no second event to wait for.

    The group is read when the shot lands rather than when the trait arms,
    which is `cf:fighter-slayer-f21`'s reasoning: a hunter carries more
    than one weapon.
    """

    @power(
        ref,
        level=0,
        cls="ranger",
        usage=ENCOUNTER,
        action=ActionType.NONE,
        reach=PERSONAL,
        target=NO_TARGET,
        keywords=[Keyword.MARTIAL],
    )
    def row(c: Cast) -> None:
        me = c.me

        def rider(ev: Hit) -> None:
            if ev.attacker != me or ev.power != SHOT:
                return
            if not _group_in_hand(c, group):
                return
            if ref.endswith("s0"):
                c.push(3, on=ev.target)
                return
            amount = c.wis_mod
            if amount <= 0:
                return
            for foe in c.enemies():
                if foe != ev.target and c.adjacent_to(ev.target, foe):
                    c.flat(amount, on=foe)

        c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label=c.ref)

    row.__name__ = "hunter_shot_" + ref.rsplit("s", 1)[-1]
    row.__doc__ = (
        f"One benefit: with a {group}, {what}.\n\n"
        "The helper above has the argument for watching `Hit` rather than "
        "`PowerResolved`, which is the opposite call from the fighter's two "
        "chassis on their own strike row."
    )
    return row


hunter_shot_0 = _shot_rider(
    "cf:ranger-hunter-f11s0", CROSSBOW, "the target is pushed up to 3")
hunter_shot_1 = _shot_rider(
    "cf:ranger-hunter-f11s1", BOW,
    "every enemy adjacent to the target takes the hunter's Wisdom modifier")


@power(
    "cf:ranger-hunter-f16",
    level=0,
    cls="ranger",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def hunter_keen(c: Cast) -> None:
    """"You are immune to the blinded condition."

    `c.immune` takes conditions, and this is the mirror of `-f11`'s own
    first clause -- the chassis that learns to blind becomes unblindable.
    `cf:fighter-slayer-f14` is the same shape for `SLOWED`.
    """
    c.immune(Condition.BLINDED, until=When.ENCOUNTER, on=c.me)


@power(
    "cf:ranger-hunter-f17",
    level=0,
    cls="ranger",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def hunter_reach(c: Cast) -> None:
    """"Both the normal and the long range of any ranged weapon increases by
    10 when you make an attack with it."

    `c.weapon_range` writes the numbers onto the creature's **own copies**
    of its weapons -- `chargen.spawn` makes a `replace(w)` per character,
    so this needs no reader: `resolve._long_range` and `c.w` already read
    those fields for everybody.

    Both numbers move, which the card says twice.

    **`ref=` and not `mine=`**, which is the one thing here that reads
    wrong at a glance. `mine=True` selects weapons whose `item` is the
    **item block doing the asking** -- it is for a magic bow's own
    property, and a class feature owns no item, so it matched nothing and
    the row changed no range at all. Naming the weapon's own ref is what
    *"any ranged weapon"* comes to for a creature that has one.

    Read off the weapon at arming rather than per shot, which is what
    writing onto the weapon means -- and is right here, because the clause
    is about the weapon and not about the attack.
    """
    gear = c.world.get(c.me, Gear)
    shooter = gear.ranged if gear is not None else None
    if shooter is None or shooter.ranged is None:
        return
    near, far = shooter.ranged
    c.weapon_range(ranged=(near + 10, far + 10), ref=shooter.ref, on=c.me)


@power(
    "cf:ranger-hunter-f18",
    level=0,
    cls="ranger",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def hunter_mastery(c: Cast) -> None:
    """*"You gain one of the following features depending on your choice of
    ranged weapon."*

    A **parent**, and its two options each grant a **feat** --
    `c.grant_row` does that, because a feat is an ordinary row in
    `Powers.known`, which `cf:assassin-executioner-f5` established and
    `drivers.executioner_guild` asserts.
    """
    chose = (c.chosen_option("cf:ranger-hunter-f18")
             or "cf:ranger-hunter-f18s0")
    c.grant_row(chose, on=c.me, until=When.ENCOUNTER)


hunter_grant_18s0 = _grant(
    "cf:ranger-hunter-f18s0", "f3124",
    "**A real grant.** A feat, and `loadout` deals powers rather than "
    "feats, so nothing else puts it in reach.")


@power(
    "cf:ranger-hunter-f18s1",
    level=0,
    cls="ranger",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def hunter_mastery_crossbow(c: Cast) -> None:
    """The other option: a feat, and a crossbow reloaded as a free action.

    The feat is `c.grant_row`, as its sibling is. The reload **is**
    written: `c.loads_free` is the verb -- *"make reloading cost less than
    the printed minor action"* -- and the card's *"if a crossbow you wield
    has the load minor property"* is exactly what `only=` narrows to.

    So both clauses play and the row needs no marker, which makes it the
    one option of this pair that is more than a grant.
    """
    c.grant_row("f3126", on=c.me, until=When.ENCOUNTER)
    if _group_in_hand(c, CROSSBOW):
        c.loads_free(cost=ActionType.FREE, only="load minor", on=c.me,
                     until=When.ENCOUNTER)


# -- the four ladder rungs and the two extra uses ---------------------------


def _rung(ref: str, what: str, into: str) -> Any:
    """One rung refused for want of a level."""

    @power(
        ref,
        level=0,
        cls="ranger",
        usage=ENCOUNTER,
        action=ActionType.NONE,
        reach=PERSONAL,
        target=NO_TARGET,
        keywords=[Keyword.MARTIAL],
        implemented_in=(into,),
    )
    def row(c: Cast) -> None:
        pass

    row.__name__ = "hunter_rung_" + ref.rsplit("-f", 1)[-1]
    row.__doc__ = (
        f"{what}\n\n"
        f"**Written into `{into}`**, which is where a clause raising "
        "another row's number has to go -- no modifier can reach into "
        "that row's own `c.bonus` call. So this is a pointer and "
        "carries `implemented_in=`, exactly as a feat naming one power "
        "does.\n\n"
        "What made it unwritable was the level, not a verb: every "
        "class feature armed at the start of every fight because "
        "`class_feature` carries none, so this number reached a "
        "1st-level character. `combat_engine.levels` carries the "
        "printed levels now and `chargen.ladder_row` reads them. "
        "`#1261`."
    )
    return row


hunter_rung_12 = _rung("cf:ranger-hunter-f12",
                       "`-f6`'s damage bonus rises to +2.",
                       "cf:ranger-hunter-f6")
hunter_rung_15 = _rung("cf:ranger-hunter-f15",
                       "`-f6`'s damage bonus rises to +3.",
                       "cf:ranger-hunter-f6")


def _extra_use(ref: str) -> Any:
    """One of the two rows granting another use of `p13588` per
    encounter."""

    @power(
        ref,
        level=0,
        cls="ranger",
        usage=ENCOUNTER,
        action=ActionType.NONE,
        reach=PERSONAL,
        target=NO_TARGET,
        keywords=[Keyword.MARTIAL],
    )
    def row(c: Cast) -> None:
        c.more_uses("p13588", 1, on=c.me)

    row.__name__ = "hunter_extra_use_" + ref.rsplit("-f", 1)[-1]
    row.__doc__ = (
        "Another use of `p13588` per encounter, still only once a turn.\n\n"
        "The same two gaps five other chassis in this wave name, and the "
        "same two symbols."
    )
    return row


hunter_extra_use_3 = _extra_use("cf:ranger-hunter-f3")
hunter_extra_use_8 = _extra_use("cf:ranger-hunter-f8")


# -- the four choices at creation -------------------------------------------


def _pick(ref: str, what: str) -> Any:
    """One of the four "one additional knack / aspect" rows.

    The scout's `-f5`, `-f7`, `-f8` and `-f11` print these same four
    sentences, and these are written out again rather than shared for
    `cf:rogue-thief-f1`'s reason: a hunter is dealt no scout row.
    """

    @power(
        ref,
        level=0,
        cls="ranger",
        usage=ENCOUNTER,
        action=ActionType.NONE,
        reach=PERSONAL,
        target=NO_TARGET,
        keywords=[Keyword.MARTIAL],
        todo=("chargen.power_choice()",),
    )
    def row(c: Cast) -> None:
        pass

    row.__name__ = "hunter_pick_" + ref.rsplit("-f", 1)[-1]
    row.__doc__ = (
        f"{what}\n\n"
        "`chargen.power_choice()`'s gap, as the scout's four are. No level "
        "symbol: an extra choice at creation is not wrong early the way a "
        "superseding number is."
    )
    return row


hunter_pick_4 = _pick("cf:ranger-hunter-f4", "One more wilderness knack.")
hunter_pick_7 = _pick("cf:ranger-hunter-f7", "One more aspect of the wild.")
hunter_pick_9 = _pick("cf:ranger-hunter-f9",
                      "One more wilderness knack, from 1st level's options.")
hunter_pick_13 = _pick("cf:ranger-hunter-f13",
                       "One more aspect of the wild.")


@power(
    "cf:ranger-hunter-f14",
    level=0,
    cls="ranger",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def hunter_keen_eye(c: Cast) -> None:
    """"Whenever you make a Perception check, you can roll twice and use
    either result."

    `cf:ranger-scout-f13`'s sentence word for word, so it is the same
    call -- `c.roll_twice`, which `cf:rogue-thief-f20` defined. Written
    out again rather than shared for `cf:rogue-thief-f1`'s reason: a
    hunter is dealt no scout row.

    Not `narrative=`: a Perception check decides what a hunter notices
    before a fight and whether it is surprised, which is combat meaning.
    """
    c.roll_twice("perception", on=c.me)


@power(
    "cf:ranger-hunter-f20",
    level=0,
    cls="ranger",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
    todo=("chargen.BUILD_OPTIONS(pick=2)",),
)
def hunter_abilities(c: Cast) -> None:
    """*"You gain **two** of the following abilities of your choice."*

    `cf:ranger-scout-f17`'s gap exactly -- a fork that deals **two** where
    `chargen.BUILD_OPTIONS` deals one. Five options are declared below, so
    the content is here and what is missing is the arity.

    Not approximated by dealing one, which gives a hunter half its
    feature, and not by granting all five, which is stronger than print.
    """


def _ability(ref: str, what: str, why: str) -> Any:
    """One of `-f20`'s five abilities.

    Four are `out_of_combat=True` and the fifth takes a symbol, which is
    `cf:ranger-scout-f17s0`'s distinction: a Stealth check decides who is
    hidden, and that is combat meaning.

    **The decorator is applied by hand**, after `row.__doc__` is set --
    inherited from the scout's helper, where `narrative=`'s gate forced it.
    `out_of_combat` does not check the docstring, but the order is kept so
    the two files read alike.
    """

    def row(c: Cast) -> None:
        pass

    row.__name__ = "hunter_ability_" + ref.rsplit("s", 1)[-1]
    row.__doc__ = (
        f"One of `-f20`'s abilities: {why}\n\n"
        f"`out_of_combat=True`: the whole row is a {what} check and what "
        "it changes happens outside a fight. `cf:ranger-scout-f17s"
        f"{ref.rsplit('s', 1)[-1]}` is the same row on the sibling chassis."
    )
    return power(
        ref,
        level=0,
        cls="ranger",
        usage=ENCOUNTER,
        action=ActionType.NONE,
        reach=PERSONAL,
        target=NO_TARGET,
        keywords=[Keyword.MARTIAL],
        out_of_combat=True,
    )(row)


@power(
    "cf:ranger-hunter-f20s0",
    level=0,
    cls="ranger",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
    todo=("c.on_check(skill=)",),
)
def hunter_group_stealth(c: Cast) -> None:
    """"Whenever you make a Stealth check, each ally within 10 squares of
    you gains a +2 bonus to his or her next Stealth check."

    `cf:ranger-scout-f17s0`'s gap and the same symbol. The effect half is
    writable -- `c.bonus("skill:stealth", 2, on=ally, once=True)` -- and
    the **trigger** is not: nothing watches a skill check being made.
    `c._stealth_hide` rolls one and emits no event a row can answer.
    """


hunter_ability_1 = _ability(
    "cf:ranger-hunter-f20s1", "diplomacy",
    "a bonus to social checks against beasts, and simple commands they "
    "are under no compulsion to obey.")
hunter_ability_2 = _ability(
    "cf:ranger-hunter-f20s2", "athletics",
    "a climb the hunter succeeds at becomes easier for the allies who "
    "watched it.")
hunter_ability_3 = _ability(
    "cf:ranger-hunter-f20s3", "perception",
    "the party sleeps through an extended rest without the usual penalty.")
hunter_ability_4 = _ability(
    "cf:ranger-hunter-f20s4", "perception",
    "a short-rest sweep of the surrounding area.")


# -- the seven rows the import cannot supply ---------------------------------


def _defective(ref: str, why: str) -> Any:
    """A row whose printed text names a list the import did not carry."""

    @power(
        ref,
        level=0,
        cls="ranger",
        usage=ENCOUNTER,
        action=ActionType.NONE,
        reach=PERSONAL,
        target=NO_TARGET,
        keywords=[Keyword.MARTIAL],
        defect=why,
    )
    def row(c: Cast) -> None:
        pass

    row.__name__ = "hunter_defect_" + ref.rsplit("-f", 1)[-1]
    row.__doc__ = f"Refused: {why}"
    return row


_NO_LIST = ("the spec reads 'you gain {n} of the following powers of your "
            "choice' and then lists nothing, so there is no set to choose "
            "from")

hunter_defect_1 = _defective(
    "cf:ranger-hunter-f1",
    "the spec reads 'you gain the following three powers' and then lists "
    "none of them, so there is nothing to grant")
hunter_defect_19 = _defective("cf:ranger-hunter-f19", _NO_LIST.format(n="two"))
hunter_defect_21 = _defective("cf:ranger-hunter-f21", _NO_LIST.format(n="one"))
hunter_defect_22 = _defective("cf:ranger-hunter-f22", _NO_LIST.format(n="one"))
hunter_defect_23 = _defective("cf:ranger-hunter-f23", _NO_LIST.format(n="one"))
hunter_defect_24 = _defective("cf:ranger-hunter-f24", _NO_LIST.format(n="one"))
hunter_defect_25 = _defective("cf:ranger-hunter-f25", _NO_LIST.format(n="one"))
