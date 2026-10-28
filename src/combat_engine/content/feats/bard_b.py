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
    DamageRolled,
    DamageType,
    Hit,
    Keyword,
    Miss,
    PowerUsed,
    SavingThrow,
    SurgeSpent,
    Trigger,
    TurnEnd,
    When,
    Window,
    after_forced_reroll,
    power,
)
from combat_engine.engine.dsl import get
from combat_engine.engine.query import allies, line_of_effect, unseen_by

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
       dropped=("c.moved_by_me()",))
def f2972(c: Cast) -> None:
    """A free step whenever you teleport an ally, and a teleport in place
    of `p2339`'s slide.

    The second clause is written now: `p2339` reads `c.instead_of` at its
    own slide, so "you can teleport the target 1 square instead of sliding
    the target" is a menu entry on `p2339` rather than a thing that happened
    as well.

    The first clause is still held. `Moved`, `MoveStart` and `MoveEnd` all
    carry `kind_`, so "an ally teleports" is sayable -- but none of them
    carries *who did it*, and `ForcedMove`, which does, covers pushes,
    pulls and slides only. That is `c.moved_by_me()` and it is the marker
    this row keeps.
    """
    c.pre_empt("p2339", "slide",
               lambda using: using.teleport(1, who=using.target))
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
       reach=PERSONAL, target=SELF,
       trigger="you use p1628",
       on=Trigger(PowerUsed, _used("p1628"), "you use that racial power"))
def f1144(c: Cast) -> None:
    """An attack bonus for every ally who can see *you*, which is the
    opposite direction from `c.can_see` -- so the sight is asked with the
    ally as the watcher, the way `warlord/level_7_c.py` asks it.

    **"The triggering enemy" is on `p1628`'s own trigger, and this row
    was reading an empty list.** That power is `NO_TARGET` and aims itself
    at whoever hit its holder, so `PowerUsed.targets` is `[]` for it
    always -- the old body's first line therefore found `None` and
    returned, every time, which is why the row has been silent. `f827`,
    `f767` and `f1543` all read through `PowerUsed.trigger` instead and
    say so in their own notes; this is the fourth.

    **The window is written now, and it does not come from `until=`.**
    The old note was right about that half: `Effects.apply` sets
    `clock = owner if when in _TARGET_CLOCKED else source`, so an
    `EOTNT` hold sitting on an *ally* is timed by that ally and never by a
    third creature -- it said "the enemy's next turn" and meant the
    ally's. So the holds are kept in a local and ended from a
    `c.watch(TurnEnd, ...)`, which is the half `c.end_effect` exists for.

    **The latch is not optional here.** `p1628` answers a *hit* on its
    holder, so it fires on the attacking enemy's own turn far more often
    than not -- and the enemy's first `TurnEnd` after that is the end of
    *that* turn, not of its next one. `Effects.apply` writes exactly this
    latch for `EOTNT` (`world.turn == clock`); ending on the first
    turn-end without it would make the bonus shorter than the broken
    version it replaces.

    `once=True` still carries the other half of the sentence -- it is
    spent by that ally's next attack on the enemy -- and `c.end_effect` is
    idempotent, so a hold already spent that way is left alone.
    """
    foe = getattr(getattr(c.trigger, "trigger", None), "attacker", None)
    if foe is None:
        return
    me = c.me
    held: list[Any] = []
    for friend in allies(c.world, me):
        if friend == me:
            continue
        if not line_of_effect(c.world, friend, me):
            continue
        if unseen_by(c.world, friend, me):
            continue
        laid = c.bonus(
            "attack", 1, on=friend, until=When.ENCOUNTER, kind="power",
            once=True, when=lambda ctx: ctx.get("target") == foe,
        )
        if laid is not None:
            held.append(laid)
    if not held:
        return

    #: How many of the enemy's turn-ends to let past -- see the latch note.
    waiting = [2 if c.world.turn == foe else 1]

    def lapsed(ev: TurnEnd) -> None:
        if ev.actor != foe or not held:
            return
        waiting[0] -= 1
        if waiting[0] > 0:
            return
        for hold in held:
            c.end_effect(hold)
        held.clear()

    c.watch(TurnEnd, lapsed, until=When.ENCOUNTER)


@power("f1145", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="p1452 makes an enemy reroll its attack and the reroll misses "
               "you",
       on=Trigger(Miss, after_forced_reroll("p1452"),
                  "the attack you forced to be rerolled missed you"))
def f1145(c: Cast) -> None:
    """That enemy grants combat advantage to the next ally who attacks it.

    `to="ally"` leaves the holder out, which is what the card says -- "the
    next one of **your allies**" -- and `once=True` is the "next one": the
    relation is spent by the first ally to swing. The words are `c.within`'s
    and `"team"` would have included the bard, who the card does not. #496.
    """
    foe = getattr(c.trigger, "attacker", None)
    if foe is None:
        return
    c.grants_advantage(on=foe, to="ally", until=When.EONT, once=True)


#: The five powers the Associated Powers line names. Every one of them
#: prints the same sentence: the damage becomes that power's own type
#: **and** necrotic, and the power gains the necrotic keyword.
_NECROTIC_TOO = ("p1725", "p3705", "p1458", "p1167", "p2780")


@power("f1231", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1231(c: Cast) -> None:
    """**Written. The third note said "both halves are missing" and both
    halves were already here.**

    The damage half is `DamageRolled.dtypes`, which is documented writable
    and documented for exactly this -- "set this to say *and*, not
    *instead*". `f2847` and `f2855` in `general_l.py` are the same shape
    on a single power; this is five of them under one watcher, because the
    sentence is identical five times over. The keyword half is
    `c.counts_as_keyword`, which edits this creature's copy of a named row
    rather than the shared header tuple.

    **Laid from here rather than written into the five powers.** #550's
    convention is for a clause the power has to *ask* about; a listener on
    the blow needs no cooperation from the row that threw it, and `f1098`
    makes the same argument for the same reason.

    **A watcher rather than `c.deals(ref=, add=)`, which looks like the
    purpose-built verb and would be short of the card.** `c.deals` is read
    through `Cast._typed`, and only `c.damage` and `c.half_damage` call
    that -- `c.flat` goes straight to `deal_damage`. Two of these five deal
    part or all of their damage flat, so the tidier call would have
    recoloured the hit line and left the rider the card speaks about
    untouched. `DamageRolled` is emitted by every route.

    One symbol for five riders, which is usually the trap `CLAUDE.md`
    warns about and here was not: the gap was the same sentence five
    times, so it went red and green honestly for every one of them. #299."""
    me = c.me

    def rot(ev: DamageRolled) -> None:
        if ev.source != me or ev.detail not in _NECROTIC_TOO:
            return
        # `p1725` is the one rider with a condition in front of it -- the
        # target stepping away at the start of its own next turn -- and
        # that moment is a turn later than the weapon damage. The thunder
        # rider is the only blow dealt then, so it is the only blow the
        # clause can be about.
        if ev.detail == "p1725" and DamageType.THUNDER not in ev.types():
            return
        ev.dtypes = (*ev.types(), DamageType.NECROTIC)

    c.watch(DamageRolled, rot, until=When.ENCOUNTER, on=me,
            window=Window.BEFORE, label=c.ref)
    for ref in _NECROTIC_TOO:
        c.counts_as_keyword(ref, Keyword.NECROTIC, on=me,
                            until=When.ENCOUNTER)


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


#: The four the card lists.
_FEY_SOCIAL = ("bluff", "diplomacy", "intimidate", "streetwise")


@power("f2973", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2973(c: Cast) -> None:
    """Roll twice and keep the higher on four social checks against a fey
    creature.

    **"`c.reroll_check` answers a `SkillCheck` the board never rolls" was the
    reason and it is false** -- `bluff` is rolled 18 times in this tree and
    `diplomacy` four. #691.

    **Both halves of the printed gate are reads that already exist**, which
    is why this needed no new facility: `SkillCheck.target` is "who the check
    was made against", put there for "the seven rows whose printed line is
    about a creature rather than a number", and `c.is_kind` answers off the
    type line. A check about a fact leaves `target` None, and those are the
    ones this must not touch.

    "You **can** roll twice" is a choice, so it goes through `c.may` rather
    than firing itself.

    The language clause is narrative and stays unwritten: nothing in a fight
    asks what anybody speaks."""
    # Imported here rather than at the top of the file: this is the only row
    # in the batch that answers a check, and `general_i.py` keeps `Window`
    # the same way for the same reason.
    from combat_engine.engine.events import SkillCheck

    def twice(ev: Any) -> None:
        if getattr(ev, "actor", None) != c.me:
            return
        if getattr(ev, "skill", "") not in _FEY_SOCIAL:
            return
        who = getattr(ev, "target", None)
        if who is None or not c.is_kind("fey", on=who):
            return
        if c.may("roll twice and use the higher result"):
            c.reroll_check(keep="best", ev=ev)

    c.watch(SkillCheck, twice, until=When.ENCOUNTER)
