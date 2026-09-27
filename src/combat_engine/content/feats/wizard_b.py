"""Wizard feats, the second batch.

`wizard.py` holds the first and the same observation runs through this
one: a keyword gate is cheap and a class feature named in prose is not.
Four rows here turn on the fire keyword and are one lambda each; the
three that turn on a feature the spec never numbers carry a marker.

Two families are new.

**Preparation is writable.** `Powers.owned` is the book, `Powers.known`
is what is prepared and `c.prepare(ref, instead_of=)` moves a row
between them, so the two rows whose whole benefit is a swap are
ordinary rows with an action rather than narrative ones. Only the row
whose benefit is "your book is bigger" is `out_of_combat`, because that
number is settled by `chargen` and never in a fight.

**Ignoring a resistance has no verb.** `c.resist` grants one and
nothing reads past one, so three rows name `c.ignore_resistance()` --
two of them as a dropped clause on a row that otherwise plays.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AT_WILL,
    DAILY,
    ENCOUNTER,
    FORT,
    FREE,
    MINOR,
    NO_TARGET,
    PERSONAL,
    SELF,
    ActionType,
    AreaBurst,
    Cast,
    Dropped,
    Hit,
    Keyword,
    Trigger,
    Usage,
    When,
    power,
)
from combat_engine.engine.components import Health, Powers
from combat_engine.engine.dsl import get
from combat_engine.engine.events import PowerResolved, ZoneEntered

#: A class feature the benefit names in prose with no ref.
FEATURE = ("c.class_feature()",)
#: Nothing reads past a creature's resistance or immunity.
PIERCE = ("c.ignore_resistance()",)
#: A `SavingThrow` says who rolled and not what laid the effect.
ON_SAVE = ("c.on_save()",)


def _keyword(ref: str, *words: Keyword) -> bool:
    p = get(ref)
    return p is not None and any(w in p.keywords for w in words)


def _hit_with(*words: Keyword):  # noqa: ANN202
    def when(world, me: int, ev: Any) -> bool:  # noqa: ANN001
        return ev.attacker == me and _keyword(ev.power, *words)

    return when


def _wizard_hit_with(*words: Keyword):  # noqa: ANN202
    def when(world, me: int, ev: Any) -> bool:  # noqa: ANN001
        p = get(ev.power)
        return (
            ev.attacker == me
            and p is not None
            and p.cls == "wizard"
            and any(w in p.keywords for w in words)
        )

    return when


def _minion(world, eid: int) -> bool:  # noqa: ANN001
    """One hit point is what a minion is, and the number is a column.

    The same test `content/monsters/level_12/controllers.py` makes. The
    nine `c.is_minion()` markers in the item tree want it on `Cast`; a
    row that can read it here should not wait for that.
    """
    health = world.get(eid, Health)
    return health is not None and health.max_hp <= 1


# -- keyword gates ---------------------------------------------------------


@power("f1994", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit with a cold wizard power",
       on=Trigger(Hit, _wizard_hit_with(Keyword.COLD), "you hit with cold"))
def f1994(c: Cast) -> None:
    """`c.penalty` takes no `kind` and that is the rule, so the printed
    -2 is simply a -2."""
    c.penalty(FORT, 2, on=c.trigger.target, until=When.EONT)


@power("f1996", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit with a wizard illusion power",
       on=Trigger(Hit, _wizard_hit_with(Keyword.ILLUSION),
                  "you hit with an illusion"))
def f1996(c: Cast) -> None:
    """A skill bonus with a duration, which is an ordinary modifier --
    the flag that makes a row narrative is about the *whole* benefit,
    and this one is triggered by a hit in a fight."""
    c.bonus(
        "skill:stealth", c.int_mod, on=c.me, until=When.EONT, kind="feat",
    )


@power("f2133", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2133(c: Cast) -> None:
    """Both clauses land. `c.forces` is handed `how` and `power`, so
    "with a fear attack" is a gate on the shove rather than a standing
    two squares on everything. The tier steps are out of scope."""
    me = c.me
    c.bonus(
        "damage", 2, on=me, until=When.ENCOUNTER, kind="feat",
        when=lambda ctx: _keyword(ctx.get("power", ""), Keyword.FIRE),
    )
    c.forces(
        2, on=me, until=When.ENCOUNTER,
        when=lambda ctx: _keyword(ctx.get("power", ""), Keyword.FEAR),
    )


@power("f3069", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit with a fire attack",
       on=Trigger(Hit, _hit_with(Keyword.FIRE), "you hit with fire"))
def f3069(c: Cast) -> None:
    """"Your next damage roll against that target" -- so the bonus is
    gated on the creature as well as on the keyword, and `once=True`
    spends it on the first roll that qualifies."""
    foe = c.trigger.target
    c.bonus(
        "damage", 2, on=c.me, until=When.EONT, kind="power", once=True,
        when=lambda ctx: (
            ctx.get("target") == foe
            and _keyword(ctx.get("power", ""), Keyword.FIRE)
        ),
    )


@power("f1997", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1997(c: Cast) -> None:
    """Counted as they fall and paid once, on `PowerResolved`.

    Temporary hit points do not add -- the larger stands -- so paying a
    single point per minion as each dropped would have come to one for
    a power that killed six. `Dropped` carries `source`, so the count
    is this wizard's own, and `PowerResolved` is the end of the row that
    did it.
    """
    me, tally = c.me, {"n": 0}

    def fell(ev: Dropped) -> None:
        if ev.source == me and _minion(c.world, ev.actor):
            tally["n"] += 1

    def paid(ev: PowerResolved) -> None:
        if ev.actor != me:
            return
        p = get(ev.power)
        if tally["n"] and p is not None and p.cls == "wizard":
            c.temp_hp(tally["n"], on=me)
        tally["n"] = 0

    c.watch(Dropped, fell, until=When.ENCOUNTER, on=me, label=f"{c.ref} count")
    c.watch(PowerResolved, paid, until=When.ENCOUNTER, on=me, label=c.ref)


@power("f1995", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.reach_bonus()",))
def f1995(c: Cast) -> None:
    """Every wizard power reaches further, on a sliding scale, areas
    included. A row's range is header data -- `Range.size` and
    `Range.within` -- read by the targeting layer before the body runs
    so the interface can draw it, and nothing rewrites it for a
    creature. Same symbol f986 names for the melee side of it."""


# -- the racial fire family ------------------------------------------------


@power("f2134", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=ON_SAVE)
def f2134(c: Cast) -> None:
    """Fire damage when an enemy shakes off something a fire attack of
    yours laid. `SavingThrow` is announced and readable, but it carries
    `against=str(effect)` and the creature rolling -- not the effect,
    and not whoever applied it -- so "bestowed by *your* fire attack"
    cannot be asked. The same hold as f1088 and f1024."""


@power("f2135", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=ON_SAVE)
def f2135(c: Cast) -> None:
    """Same hold as f2134, knocking the saver prone instead."""


@power("f2136", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=PIERCE)
def f2136(c: Cast) -> None:
    """The row plays for its second clause and drops its first.

    "You replace your racial power with this one" is what `c.grant_row`
    says -- the replacement half is `chargen`'s and taking the old row
    away would need its ref, which the prose does not give. Ignoring a
    bloodied enemy's fire resistance is the dropped clause: `c.resist`
    lays one and `resolve` subtracts it, with nothing reading past it.
    """
    c.grant_row("f2136b", on=c.me, until=When.ENCOUNTER)


@power("f2136b", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=AreaBurst(1, within=10), target=NO_TARGET,
       keywords=[Keyword.ARCANE, Keyword.ZONE], dropped=PIERCE)
def f2136b(c: Cast) -> None:
    """The card of f2136: a zone that hands you combat advantage.

    `NO_TARGET` rather than `EACH_ENEMY` because the zone is the whole
    printed Effect and has to land on an empty patch of ground too.
    Combat advantage is granted to whoever is standing in the burst and
    to whoever walks in afterwards, which is the two halves of "targets
    in the zone" a one-shot pass over the squares would miss.

    Stripping immunities and resistances is dropped, as on f2136.
    """
    area = c.area()
    zone = c.zone(area, until=When.EONT, label=c.ref)
    for foe in c.in_squares(area, side="enemy"):
        c.grants_advantage(on=foe, until=When.EONT)

    def arrived(ev: ZoneEntered) -> None:
        if ev.zone == zone:
            c.grants_advantage(on=ev.actor, until=When.EONT)

    c.watch(
        ZoneEntered, arrived, until=When.EONT, on=c.me, label=f"{c.ref} entry"
    )


@power("f3068", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=PIERCE)
def f3068(c: Cast) -> None:
    """Ignores part of a creature's fire resistance, and treats immunity
    as a large resistance instead. Nothing reads past a resistance: it
    is subtracted inside `resolve` from a number the creature carries,
    and no modifier reduces it for one attacker. Same symbol f2136
    drops."""


# -- the spellbook ---------------------------------------------------------


def _dailies(refs: list[str], *, attack: bool, keywords: tuple = ()) -> list[str]:
    """Wizard dailies out of a list of refs, optionally keyword-filtered."""
    out = []
    for ref in refs:
        p = get(ref)
        if p is None or p.cls != "wizard" or p.usage is not Usage.DAILY:
            continue
        if (p.attack is not None) is not attack:
            continue
        if keywords and not any(w in p.keywords for w in keywords):
            continue
        out.append(ref)
    return out


def _prepared(c: Cast) -> list[str]:
    known = c.world.get(c.me, Powers)
    return list(known.known) if known is not None else []


@power("f1154", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f1154(c: Cast) -> None:
    """More rows in the book and none of them prepared, which is a
    build-time number: `chargen.spellbook` fills `Powers.owned` and the
    printed line says outright that the prepared count is unchanged.
    Same shape as f276."""


@power("f2047", level=1, cls="", usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF)
def f2047(c: Cast) -> None:
    """Two swaps -- an attack spell and a utility -- in one firing.

    The page prints them as two separate once-a-day allowances and the
    engine counts uses per row, so splitting them would want two refs.
    Doing both here is the compression: each is independent, each is
    refused when the book has nothing of that shape to offer, and the
    slot count never changes because `Powers.prepare` puts the outgoing
    row back.
    """
    book, prepared = c.spellbook(), _prepared(c)
    for attack in (True, False):
        fresh = _dailies(book, attack=attack)
        stale = _dailies(prepared, attack=attack)
        if not fresh or not stale:
            continue
        chosen = c.choose(fresh, "prepare which spell instead?")
        drop = c.choose(stale, "and put which one back?")
        if chosen is not None and drop is not None:
            c.prepare(chosen, instead_of=drop)


@power("f2292", level=1, cls="", usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def f2292(c: Cast) -> None:
    """The narrower swap: one chosen fire-or-fear daily, in place of an
    uncast one of at least its level.

    "Chosen at each extended rest" is not modelled -- there is no rest
    between fights here -- so the choice is made at the moment of the
    swap out of whatever the book holds, which is the same set the rest
    would have chosen from.
    """
    fresh = _dailies(
        c.spellbook(), attack=True, keywords=(Keyword.FIRE, Keyword.FEAR)
    )
    if not fresh:
        return
    chosen = c.choose(fresh, "swap which spell in?")
    if chosen is None:
        return
    level = getattr(get(chosen), "level", 0)
    spent = set(c.expended())
    stale = [
        ref
        for ref in _dailies(_prepared(c), attack=True)
        if ref not in spent and getattr(get(ref), "level", 0) >= level
    ]
    if stale:
        drop = c.choose(stale, "and which one out?")
        if drop is not None:
            c.prepare(chosen, instead_of=drop)


# -- the class feature with no ref -----------------------------------------


@power("f2030", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("cf:wizard-arcanist-f0c3", "c.use_power()"))
def f2030(c: Cast) -> None:
    """A free `f2023b` on a miss with one arcanist option. The option has
    a ref and no row, so nothing marks which misses it modified."""


@power("f2034", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("cf:wizard-arcanist-f0c1", "c.counts_as(kind=)"))
def f2034(c: Cast) -> None:
    """Treats `f2023b` as an at-will wizard spell for one arcanist option.
    That option has a ref and no row, and nothing makes a row count as a
    different sort."""
