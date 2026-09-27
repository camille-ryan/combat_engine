"""Bard feats, the second batch.

Three things decide almost every row here.

**The virtues are class features named in prose with no ref**, so the
three rows that modify one carry `c.class_feature()` -- the spelling
eleven other rows already use. Nothing can point at a feature the spec
never numbers.

**`p2339` is not a guess.** One row in this batch prints `has p2339` as
its prerequisite and then says "when you use majestic word" in its
benefit, so the ref and the prose name the same row. Three rows here
ride on it and all three point at the ref rather than at the words.

**"While using a longsword" is `chargen.LONGSWORD.ref`.** The base item
is a symbol the engine already owns, and `c.struck_with` hands back the
weapon the triggering blow was made with, so the clause is a comparison
rather than a marker.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.chargen import LONGSWORD
from combat_engine.engine import (
    ENCOUNTER,
    PERSONAL,
    SELF,
    ActionType,
    Cast,
    Hit,
    Keyword,
    PowerUsed,
    SurgeSpent,
    Trigger,
    When,
    power,
)
from combat_engine.engine.dsl import get
from combat_engine.engine.query import allies

#: A class feature the benefit names in prose with no ref.
FEATURE = ("c.class_feature()",)
#: A racial power the benefit names in prose rather than by ref.
RACIAL = ("c.on_racial_power()",)
#: Nothing announces that a roll was a reroll.
REROLL = ("c.on_reroll()",)

#: The ref the prerequisite column gives for the heal three rows modify.
WORD = "p2339"


def _used(ref: str):  # noqa: ANN202
    def when(world, me: int, ev: Any) -> bool:  # noqa: ANN001
        return ev.actor == me and ev.power == ref

    return when


def _keywords(ref: str, *words: Keyword) -> bool:
    p = get(ref)
    return p is not None and any(w in p.keywords for w in words)


def _longsword(c: Cast, ev: Any, refs: tuple[str, ...]) -> bool:
    """One of the named rows, hit, with the printed base weapon in hand."""
    if ev.attacker != c.me or ev.power not in refs:
        return False
    arm = c.struck_with(ev)
    return arm is not None and arm.ref == LONGSWORD.ref


# -- the virtues, which have no ref ----------------------------------------


@power("f1135", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=FEATURE)
def f1135(c: Cast) -> None:
    """Lengthens the defence bonus one virtue hands an ally. The virtue
    is named in prose with no ref, and even with one the duration is
    chosen inside its own body."""


@power("f1152", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=FEATURE)
def f1152(c: Cast) -> None:
    """Adds 2 to the same bonus. Same naming gap as f1135."""


@power("f2892", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=FEATURE)
def f2892(c: Cast) -> None:
    """Psychic damage to whatever set the virtue off. The virtue has no
    ref, so there is nothing to watch and no triggering enemy to read."""


# -- riders on the heal, which does have a ref -----------------------------


@power("f1719", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p2339",
       on=Trigger(PowerUsed, _used(WORD), "you use that power"))
def f1719(c: Cast) -> None:
    """"If the target is not bloodied" is asked here, before the heal.

    `PowerUsed` is announced above the body, which for once is what the
    clause wants: the row's own surge can lift a target out of bloodied,
    and the printed condition is about the ally you chose rather than
    the ally you left.
    """
    for who in c.trigger.targets:
        if not c.bloodied(on=who):
            c.bonus("attack", 1, on=who, until=When.EOTNT)


@power("f2563", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p2339",
       on=Trigger(PowerUsed, _used(WORD), "you use that power"))
def f2563(c: Cast) -> None:
    """"The next saving throw it makes" is `once=True`, not a duration:
    the bonus is spent by the first save and the window merely bounds
    how long it waits."""
    for who in c.trigger.targets:
        c.bonus("save", c.con_mod, on=who, until=When.EONT, once=True)


@power("f2972", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.moved_by_me()", "c.swap_forced()"))
def f2972(c: Cast) -> None:
    """A free step whenever you teleport an ally, and a teleport in place
    of the heal's slide.

    `Moved`, `MoveStart` and `MoveEnd` all carry `kind_`, so "an ally
    teleports" is sayable -- but none of them carries who did it, and
    `ForcedMove` (which does) covers pushes, pulls and slides only. The
    second clause reaches inside another row and swaps the movement it
    chose, which is the same hold as the avenger's f1724.
    """


# -- keyword gates, which are the cheap ones -------------------------------


@power("f1137", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1137(c: Cast) -> None:
    """Both keywords are asked of the *power*, not of the damage: a charm
    that happens to deal no arcane damage still counts. The later steps
    are out of scope."""
    me = c.me
    for what in ("attack", "damage"):
        c.bonus(
            what, 1, on=me, until=When.ENCOUNTER, kind="feat",
            when=lambda ctx: (
                _keywords(ctx.get("power", ""), Keyword.ARCANE)
                and _keywords(ctx.get("power", ""), Keyword.CHARM)
            ),
        )
    for skill in ("skill:bluff", "skill:diplomacy"):
        c.bonus(skill, 1, on=me, until=When.ENCOUNTER, kind="feat")


def _fire_or_fear(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    p = get(ev.power)
    return (
        ev.attacker == me
        and p is not None
        and p.cls == "bard"
        and (Keyword.FIRE in p.keywords or Keyword.FEAR in p.keywords)
    )


@power("f2298", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit with a bard fire or fear attack",
       on=Trigger(Hit, _fire_or_fear, "you hit with fire or fear"))
def f2298(c: Cast) -> None:
    """"One ally who can see you" is one ally, so the first visible one
    takes it rather than the whole party. The tier steps are out of
    scope."""
    me = c.me
    near = [a for a in allies(c.world, me) if a != me and c.can_see(a)]
    if near:
        c.temp_hp(1 + c.cha_mod, on=near[0])


# -- the longsword pair ----------------------------------------------------


@power("f2924", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.bonus('save:death')",))
def f2924(c: Cast) -> None:
    """The skill half stands; the rider is dropped.

    A death saving throw is rolled in `turns._death_saves` with
    `bonus=0` written into the event, so nothing a creature carries adds
    to one. A `c.bonus("save", ...)` here would look like the printed +5
    and never be read.
    """
    c.bonus("skill:nature", 2, on=c.me, until=When.ENCOUNTER, kind="feat")


@power("f2926", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2926(c: Cast) -> None:
    """A trait that arms a window, and the window arms the payout.

    Two nested watchers rather than one: the surge clause only listens
    for a turn after a qualifying hit, and `SurgeSpent` fires from every
    site that drains the pool, so a standing subscription would pay out
    all fight.
    """
    me = c.me
    refs = ("p7072", "p4988")

    def on_surge(ev: SurgeSpent) -> None:
        if ev.actor != me and not c.adjacent(to=ev.actor):
            return
        c.heal(1, on=me)
        for mate in allies(c.world, me):
            if mate != me and c.adjacent(to=mate):
                c.heal(1, on=mate)

    def on_hit(ev: Hit) -> None:
        if _longsword(c, ev, refs):
            c.watch(
                SurgeSpent, on_surge, until=When.EONT, on=me,
                label=f"{c.ref} surges",
            )

    c.watch(Hit, on_hit, until=When.ENCOUNTER, on=me, label=f"{c.ref} riders")


# -- the rest --------------------------------------------------------------


@power("f1120", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.attack_ability()", "chargen.multiclass_powers()"))
def f1120(c: Cast) -> None:
    """Attacks with a borrowed power roll on Charisma instead.

    Two holds. The ability a row attacks with is header data read before
    the body -- `Attack(ability=)` -- and nothing rewrites it for a
    creature. And "gained through a multiclass feat" is a provenance
    `Powers.known` does not keep: a row is in the list or it is not, and
    the list does not say how it got there.
    """


@power("f1144", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=RACIAL)
def f1144(c: Cast) -> None:
    """An attack bonus for every ally who can see you when a racial power
    goes off. The power is named in prose with no ref, so there is
    nothing to watch and no triggering enemy to aim at."""


@power("f1145", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=(*RACIAL, *REROLL))
def f1145(c: Cast) -> None:
    """Combat advantage when a racial power's forced second attack roll
    misses. Two holds: the power is prose, and nothing announces that a
    roll was a reroll, which is the half f1524 also wants."""


@power("f1231", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("feat.associated_powers",))
def f1231(c: Cast) -> None:
    """The preamble prints and the clause does not: "you gain a benefit"
    with one power listed and nothing said about it. Same shape as f974
    -- the list resolves and there is nothing to hang on it."""


@power("f2091", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.retrigger(p1452)",))
def f2091(c: Cast) -> None:
    """Widens another row's printed Trigger and adds a miss rider.
    `p1452` is a ref and its `on=Trigger(...)` is header data, read by
    the dispatcher before anything runs; nothing edits one for a
    character, so the miss clause has no window to live in either."""


@power("f2973", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f2973(c: Cast) -> None:
    """A language and a reroll on four social skills against one sort of
    creature. No combat consequence at all: `c.reroll_check` answers a
    `SkillCheck` the board never rolls."""
