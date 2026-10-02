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

from combat_engine.chargen import LONGSWORD
from combat_engine.engine import (
    AC,
    AT_WILL,
    ENCOUNTER,
    PERSONAL,
    SELF,
    ActionType,
    Cast,
    Condition,
    DamageType,
    Hit,
    Keyword,
    PowerUsed,
    SavingThrow,
    SurgeSpent,
    Trigger,
    When,
    power,
)
from combat_engine.engine.dsl import get
from combat_engine.engine.query import allies, line_of_effect, unseen_by

#: A class feature the benefit names in prose with no ref.
FEATURE = ("c.class_feature()",)
#: Nothing announces that a roll was a reroll.
REROLL = ("c.on_reroll()",)

#: The ref the prerequisite column gives for the heal three rows modify.
WORD = "p2339"


def _used(ref: str):  # noqa: ANN202
    def when(world, me: int, ev: Any) -> bool:  # noqa: ANN001
        return ev.actor == me and ev.power == ref

    return when


#: The virtue three rows here ride on, declared as a card of its own.
_VIRTUE = "cf:bard-f1s1"


def _virtue_pair(c: Cast) -> tuple[int | None, Any]:
    """The ally that card protected and the defence it was aimed at.

    Both are read off the `Hit` the card answered, exactly as the card
    reads them -- `PowerUsed.targets` is the card's own pick and `Hit`
    carries no `vs`, so the defence comes off the declared header.
    """
    hit = getattr(c.trigger, "trigger", None)
    ally = getattr(hit, "target", None)
    declared = get(getattr(hit, "power", "") or "")
    defence = declared.attack.vs if declared is not None and declared.attack else AC
    return ally, defence


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


@power("f1135", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use cf:bard-f1s1",
       on=Trigger(PowerUsed, _used(_VIRTUE), "you play that virtue"))
def f1135(c: Cast) -> None:
    """Lengthens the bonus `cf:bard-f1s1` grants an ally.

    Nothing moves an effect's clock, so the longer window is said as a
    second bonus of the same kind and size: two power bonuses do not
    add, the larger wins, and the card's own runs out first -- which
    leaves exactly this one standing for the rest of the ally's next
    turn. `EOTNT` because the printed clock is the *ally's*.

    The ally and the defence are read the way the card reads them, off
    the `Hit` it answered.
    """
    ally, defence = _virtue_pair(c)
    if ally is not None:
        c.bonus(defence, max(c.wis_mod, 1), kind="power",
                until=When.EOTNT, on=ally)


@power("f1152", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use cf:bard-f1s1",
       on=Trigger(PowerUsed, _used(_VIRTUE), "you play that virtue"))
def f1152(c: Cast) -> None:
    """Raises the same bonus by 2, which is one bigger bonus rather than
    a second one: two power bonuses do not add and the larger wins, so a
    +2 laid beside the card's would come to the card's."""
    ally, defence = _virtue_pair(c)
    if ally is not None:
        c.bonus(defence, max(c.wis_mod, 1) + 2, kind="power",
                until=When.EOT, on=ally)


@power("f2892", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use cf:bard-f1s1",
       on=Trigger(PowerUsed, _used(_VIRTUE), "you play that virtue"))
def f2892(c: Cast) -> None:
    """Psychic damage to whatever set the virtue off.

    Not `ev.targets`: the card targets the *ally* it protects, and the
    triggering enemy is the attacker on the `Hit` it answered."""
    hit = getattr(c.trigger, "trigger", None)
    foe = getattr(hit, "attacker", None)
    if foe is not None:
        c.flat(c.wis_mod, dtype=DamageType.PSYCHIC, on=foe)


# -- riders on the heal, which does have a ref -----------------------------


@power("f1719", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
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


@power("f2563", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
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
       todo=("c.moved_by_me()", "c.pre_empt(ref, clause)"))
def f2972(c: Cast) -> None:
    """A free step whenever you teleport an ally, and a teleport in place
    of the heal's slide.

    `Moved`, `MoveStart` and `MoveEnd` all carry `kind_`, so "an ally
    teleports" is sayable -- but none of them carries who did it, and
    `ForcedMove` (which does) covers pushes, pulls and slides only.

    The second clause is **re-aimed**: `p2339` is a ref and its slide is
    an ordinary printed clause inside its body, so what is wanted is the
    swap for half of what another row does -- the same operation thirty
    rows name, including the avenger's f1724 -- and not a verb of its own.
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


@power("f2298", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
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
       reach=PERSONAL, target=SELF)
def f2924(c: Cast) -> None:
    """The skill half stands and the rider lands with it.

    The rider was dropped on the reading that a death saving throw is
    rolled with `bonus=0` written in. It is not: `turns._death_saves`
    totals `save` modifiers against a context labelled `death`, so the
    gate is what keeps the +5 off every ordinary throw the ally makes --
    an ungated save bonus would be read by both.

    "Their next death saving throw" is spent by hand rather than with
    `once=True`: that branch of `c.bonus` ends a one-shot save bonus on
    the owner's next `SavingThrow` **whatever it was against**, and a
    dying ally rolls ordinary save-ends throws at the end of the same
    turn. A gated one-shot would be eaten by one of those.
    """
    me = c.me
    refs = ("p4987", "p1580")

    def on_hit(ev: Hit) -> None:
        if not _longsword(c, ev, refs):
            return
        for mate in allies(c.world, me):
            if mate == me or not c.adjacent(to=mate):
                continue
            if not c.is_(Condition.DYING, on=mate):
                continue
            given = c.bonus(
                "save", 5, on=mate, until=When.ENCOUNTER, kind="power",
                when=lambda ctx: ctx.get("label") == "death",
            )

            def rolled(ev: SavingThrow, who: int = mate, eff: Any = given) -> None:
                if ev.actor == who and ev.against == "death":
                    c.end_effect(eff)

            c.watch(
                SavingThrow, rolled, until=When.ENCOUNTER, on=me,
                label=f"{c.ref} spent",
            )
            return

    c.watch(Hit, on_hit, until=When.ENCOUNTER, on=me, label=f"{c.ref} riders")
    c.bonus("skill:nature", 2, on=me, until=When.ENCOUNTER, kind="feat")


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
       todo=("chargen.multiclass_powers()",))
def f1120(c: Cast) -> None:
    """Attacks with a borrowed power roll on Charisma instead.

    **One hold now, not two.** `c.rolls_with` exists, so rewriting which
    ability a row attacks with is no longer the problem -- but the verb takes
    a ref and this card names no rows at all. "Gained through a multiclass
    feat" is a provenance `Powers.known` does not keep: a row is in the list
    or it is not, and the list does not say how it got there.

    So the swap is one line the moment that provenance exists, and the marker
    names only the thing actually missing. Dropping the arrived symbol is not
    progress on the row and is not claimed as any.
    """


@power("f1144", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.bonus(clock=)",),
       trigger="you use p1628",
       on=Trigger(PowerUsed, _used("p1628"), "you use that racial power"))
def f1144(c: Cast) -> None:
    """An attack bonus for every ally who can see *you*, which is the
    opposite direction from `c.can_see` -- so the sight is asked with the
    ally as the watcher, the way `warlord/level_7_c.py` asks it.

    `PowerUsed` fires above the body, but the targets are chosen before
    it, so "the triggering enemy" is readable here.

    The window is dropped: the printed one is the *enemy's* next turn and
    an effect's clock is its owner or its source, so a bonus sitting on
    an ally cannot be timed by a third creature. `once=True` carries the
    substance -- it is spent by that ally's next attack on the enemy --
    and only an attack made out of turn late in the round would get it
    when the card says it should have lapsed.
    """
    foe = next(iter(c.trigger.targets), None)
    if foe is None:
        return
    me = c.me
    for friend in allies(c.world, me):
        if friend == me:
            continue
        if not line_of_effect(c.world, friend, me):
            continue
        if unseen_by(c.world, friend, me):
            continue
        c.bonus(
            "attack", 1, on=friend, until=When.EOTNT, kind="power", once=True,
            when=lambda ctx: ctx.get("target") == foe,
        )


@power("f1145", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=REROLL)
def f1145(c: Cast) -> None:
    """Combat advantage when `p1452`'s forced second attack roll misses.
    The power is a ref now; what is still missing is that nothing
    announces a roll was a reroll, which is the half f1524 also wants."""


@power("f1231", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.retype_damage(dtypes=)",))
def f1231(c: Cast) -> None:
    """**Re-aimed twice, and the marker is now the real gap.**

    The first two notes were about the ETL and both were wrong: the list
    resolves and the spec carries `<ref> : <clause>` with the clause intact,
    478 of 478. So `spec.associated_clause()` named nothing, and this row
    read as blocked on an instrument when it was blocked on an engine verb.

    What it actually wants, across all five of its riders identically: the
    damage the named power deals becomes a second type **as well**, and the
    power gains that keyword. Both halves are missing. `c.flat` and
    `c.damage` take `dtype`/`dtypes` where the damage is dealt, so a row can
    choose its own type -- but nothing retypes damage *another* row is about
    to deal, and `Power.keywords` is header data no trait can add to.

    One symbol for five riders, which is usually the trap `CLAUDE.md`
    warns about and here is not: the gap is the same sentence five times, so
    the marker goes red and green honestly for every one of them. #299."""


@power("f2091", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.retrigger(ref)",))
def f2091(c: Cast) -> None:
    """Widens another row's printed Trigger and adds a miss rider.
    `p1452` is a ref and its `on=Trigger(...)` is header data, read by
    the dispatcher before anything runs; nothing edits one for a
    character, so the miss clause has no window to live in either.

    Re-aimed only in spelling: the marker carried the ref inside the
    symbol, so it grouped with nothing and the next row wanting the same
    operation would have named it a third way."""


@power("f2973", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f2973(c: Cast) -> None:
    """A language and a reroll on four social skills against one sort of
    creature. No combat consequence at all: `c.reroll_check` answers a
    `SkillCheck` the board never rolls."""
