"""Warden feats, the second batch.

`defenders.py` holds the first five and this one runs on the same three
rails.

The first is the mark. Nearly every row here pays out "against creatures
marked by you", which `c.marked` asks per attack because the set changes
inside a turn.

The second is the class's own marking feature, `cf:warden-f2`. It is a
ref and it is written -- it lays its marks at the start of the turn --
but it is a trait rather than a row anybody uses, so nothing announces
that it ran. What it leaves behind is a `RelationSet` per mark -- a mark
is a relation and emits no `ConditionApplied` at all -- and that is what
the two rows counting "three or more" watch. The same count is how the
row riding on an action point knows the feature has already gone off
this turn.

The third is the guardian form. `powers/warden/__init__.assume` writes
one as a stance labelled with the form's own ref -- there is no shared
word the way the druid's beast form has one -- so "while you are in
guardian form" is asked of the row the stance came from: all twenty-one
are warden polymorph powers and nothing else the class has is.

The gaps are the ones `defenders.py` already named. Second wind is an
action and announces nothing; a build's own second-wind rider has no ref
at all; and four rows turn on "while you are under the effect of" a
named power, which no hold records.

`usage=AT_WILL` throughout except `f1950`, which is the one card here
printing "the first time during an encounter". `triggers._answers` asks
`usable` every time it offers a row, so `ENCOUNTER` says that limit
exactly -- and would quietly impose it on the twenty-eight rows that do
not print it. The two rows counting three marks were each spent on the
first mark before this was noticed.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AT_WILL,
    ENCOUNTER,
    PERSONAL,
    SELF,
    ActionType,
    Cast,
    DamageType,
    Hit,
    Keyword,
    PowerUsed,
    Relation,
    Trigger,
    When,
    power,
)
from combat_engine.engine.dsl import get
from combat_engine.engine.events import (
    ActionPointSpent,
    Bloodied,
    RelationSet,
    TurnStart,
)
from combat_engine.engine.query import holding
from combat_engine.engine.triggers import about_me

#: Second wind is an action rather than a power, as `defenders.py` says.
SECOND_WIND = ("c.on_second_wind()",)
#: A class feature named in prose with no ref.
FEATURE = ("c.class_feature()",)
#: A racial power the benefit line names in prose rather than by ref.
RACIAL = ("c.on_racial_power()",)
#: "While you are under the effect of your <ref> power" -- the power is a
#: ref, but nothing records that one of its holds is standing on you.
BENEFIT = ("c.benefits_from()",)
#: Which effect a saving throw was rolled against.
SAVE_KEYWORDS = ("SavingThrow.keywords",)


def _holding(c: Cast, *groups: str) -> bool:
    return any(holding(c.world, c.me, g) for g in groups)


def _in_guardian_form(world, eid: int) -> bool:  # noqa: ANN001
    """A form is a stance wearing the form row's own ref as its label."""
    stance = world.effects.stance_of(eid)
    if stance is None:
        return False
    p = get(stance.label)
    return p is not None and p.cls == "warden" and Keyword.POLYMORPH in p.keywords


def _assumes_form(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    p = get(ev.power)
    return (
        ev.actor == me
        and p is not None
        and p.cls == "warden"
        and Keyword.POLYMORPH in p.keywords
    )


def _i_marked(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.kind_ is Relation.MARKED_BY and ev.source == me


def _marks_this_turn(world, me: int) -> int:  # noqa: ANN001
    """How many creatures this warden has marked since its turn began.

    `cf:warden-f2` marks every adjacent enemy at the start of the turn and
    says nothing else about itself, so the count of marks laid inside the
    turn is the only record that it ran and of how wide it went.

    A mark is a **relation**, not a condition: `c.mark` emits `RelationSet`
    and an `EffectApplied`, and no `ConditionApplied` at all -- which is
    what this counted first, and it counted nothing forever.
    """
    seen = 0
    for ev in reversed(world.bus.log):
        if isinstance(ev, TurnStart) and ev.actor == me:
            break
        if isinstance(ev, RelationSet) and _i_marked(world, me, ev):
            seen += 1
    return seen


def _my_marks(c: Cast) -> list[int]:
    return [foe for foe in c.enemies() if c.marked(on=foe)]


def _used(ref: str):  # noqa: ANN202
    def when(world, me: int, ev: Any) -> bool:  # noqa: ANN001
        return ev.actor == me and ev.power == ref

    return when


def _hit_with(ref: str):  # noqa: ANN202
    def when(world, me: int, ev: Any) -> bool:  # noqa: ANN001
        return ev.attacker == me and ev.power == ref

    return when


# -- the marking feature, counted off the marks it lays ---------------------


@power("f1942", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you mark three or more enemies with cf:warden-f2",
       on=Trigger(RelationSet, _i_marked, "you mark an enemy"))
def f1942(c: Cast) -> None:
    """The third mark is the one that pays, and only the third: the row
    fires again on the fourth and fifth, and an untyped bonus stacks, so
    the count is tested for equality rather than for "at least".

    "Weapon damage rolls" is the printed keyword, read off the row that
    is rolling, and "creatures you mark" is asked per roll because the
    mark can land after the bonus does.
    """
    me = c.me
    if _marks_this_turn(c.world, me) != 3:
        return
    c.bonus(
        "damage", 2, on=me, until=When.SONT,
        when=lambda ctx: (
            (p := get(ctx.get("power", ""))) is not None
            and Keyword.WEAPON in p.keywords
            and c.marked(on=ctx.get("target"))
        ),
    )


@power("f1953", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you spend an action point",
       on=Trigger(ActionPointSpent, about_me, "you spend an action point"))
def f1953(c: Cast) -> None:
    """A second use of `cf:warden-f2` inside one turn.

    The feature is a trait with a `TurnStart` watch rather than a row
    anybody uses, so there is nothing to run again -- what it *does* is
    mark every adjacent enemy, and that is what is done here. Having
    already gone off this turn is read the only way it is recorded, off
    the marks it laid.
    """
    me = c.me
    if _marks_this_turn(c.world, me) == 0:
        return
    for foe in c.enemies():
        if c.adjacent(foe):
            c.mark(on=foe, until=When.EONT)


@power("f2555", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you mark three or more creatures with cf:warden-f2",
       on=Trigger(RelationSet, _i_marked, "you mark an enemy"))
def f2555(c: Cast) -> None:
    """The same count as f1942, gated on a row still being unspent.
    `c.expended` lists what has gone, and a warden who does not know
    `p1770` has not spent it -- which the prerequisite settles rather
    than the body."""
    if _marks_this_turn(c.world, c.me) != 3:
        return
    if "p1770" in c.expended():
        return
    c.shift(1)


# -- the guardian form ------------------------------------------------------


@power("f1943", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1943(c: Cast) -> None:
    """Both halves are asked per damage roll: a form is taken mid-fight
    and a weapon can be dropped. No type word is printed, so untyped."""
    me = c.me
    c.bonus(
        "damage", 2, on=me, until=When.ENCOUNTER,
        when=lambda ctx: (
            _in_guardian_form(c.world, me) and _holding(c, "hammer", "mace")
        ),
    )


@power("f1944", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you assume a guardian form",
       on=Trigger(PowerUsed, _assumes_form, "you assume a guardian form"))
def f1944(c: Cast) -> None:
    """`PowerUsed` fires before the body, so the stance is not up yet --
    which is why the predicate reads the *row's* keywords rather than
    asking whether the warden is in a form."""
    c.shift(1)


@power("f1948", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.on_reroll()",))
def f1948(c: Cast) -> None:
    """A bonus to a racial reroll taken while in a guardian form. The
    power is a ref and the form is readable; what is missing is that
    nothing announces a roll was a reroll, the same gap the avenger's
    f1524 named."""


# -- riders on the class's own rows -----------------------------------------


@power("f2551", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p1828",
       on=Trigger(PowerUsed, _used("p1828"), "you use that power"))
def f2551(c: Cast) -> None:
    """Slides everything carrying this warden's mark, which is the whole
    board's worth rather than the triggering row's targets."""
    for foe in _my_marks(c):
        c.slide(c.con_mod, on=foe)


@power("f2552", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit with p1767",
       on=Trigger(Hit, _hit_with("p1767"), "you hit with that power"))
def f2552(c: Cast) -> None:
    c.slowed(on=c.trigger.target, until=When.SONT)


@power("f2559", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit an enemy with p1766",
       on=Trigger(Hit, _hit_with("p1766"), "you hit with that power"))
def f2559(c: Cast) -> None:
    """The burn is paid to the marked enemies rather than to the one that
    was hit, which may not be marked at all."""
    for foe in _my_marks(c):
        c.flat(c.str_mod, dtype=DamageType.FIRE, on=foe)


@power("f1950", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you are bloodied",
       on=Trigger(Bloodied, about_me, "you become bloodied"))
def f1950(c: Cast) -> None:
    """The one card here that prints "the first time during an
    encounter", and `usage=ENCOUNTER` is that sentence: the dispatcher
    asks `usable` before it offers a row, so a spent one is not offered
    again."""
    me = c.me
    for what in ("attack", "damage"):
        c.bonus(
            what, 2, on=me, until=When.EONT, kind="feat",
            when=lambda ctx: c.marked(on=ctx.get("target")),
        )


@power("f1842", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.uncrit()",))
def f1842(c: Cast) -> None:
    """Trades a critical hit for an ordinary one plus an immobilise.
    `Hit` carries `critical` and the immobilise is one line -- what is
    missing is taking the critical back after the damage it maxed has
    already been rolled and dealt."""


@power("f2796", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.forgo_push()",))
def f2796(c: Cast) -> None:
    """Swaps the slide in `p5094` -- the mark punishment that slides --
    for a longer pull, and slows two printed creature types. The row is a
    ref and `c.is_kind` reads the types; what is missing is letting a
    named row's own forced movement not happen, which is the symbol
    f984 named."""


# -- second wind, which announces nothing -----------------------------------


@power("f1830", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=SECOND_WIND)
def f1830(c: Cast) -> None:
    """Resistance to all damage after a second wind. Same gap as f583."""


@power("f1846", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=SECOND_WIND)
def f1846(c: Cast) -> None:
    """A saving throw for a second ally when the build's own second-wind
    rider grants one to the first. Both halves are the same gap: nothing
    announces the second wind, and the rider it widens has no ref -- see
    `cf:warden-f1-rest` in `docs/blocked.json`."""


@power("f1886", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=SECOND_WIND)
def f1886(c: Cast) -> None:
    """A damage bonus against marked enemies after a second wind."""


@power("f2556", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=SECOND_WIND)
def f2556(c: Cast) -> None:
    """A shift in place of the slide a build's second-wind rider makes.
    Same pair of gaps as f1846."""


@power("f2558", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=SECOND_WIND)
def f2558(c: Cast) -> None:
    """Lightning damage to every marked enemy after a second wind."""


@power("f1874", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=FEATURE)
def f1874(c: Cast) -> None:
    """Swaps a slide for a push inside a build's own rider. The build leg
    is named in prose with no ref, and even with one the forced movement
    is chosen inside it -- the same pair the avenger's f1724 named."""


# -- the saving throw the class gets at the start of its turn ---------------


@power("f1941", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=SAVE_KEYWORDS)
def f1941(c: Cast) -> None:
    """Temporary hit points for shaking off one sort of effect.
    `cf:warden-f0` is the ref that rolls the throw and `SavingThrow`
    carries whether it succeeded -- what is missing is which keywords the
    effect it was rolled against had. The save *modifier* context now
    carries them, but this row answers the event, whose `against` is the
    effect's `__str__` and not a ref `keywords_of` can read."""


_ELEMENTAL = (Keyword.ACID, Keyword.COLD, Keyword.FIRE,
              Keyword.LIGHTNING, Keyword.THUNDER)
_ELEMENTAL_DTYPES = (DamageType.ACID, DamageType.COLD, DamageType.FIRE,
                     DamageType.LIGHTNING, DamageType.THUNDER)


def _elemental_save(ctx: dict[str, Any]) -> bool:
    """The hold being saved against is one of the five elements -- by the
    keywords of the row that laid it, or by the type of its burn."""
    return bool(set(_ELEMENTAL) & set(ctx.get("keywords", ()))) or (
        ctx.get("dtype") in _ELEMENTAL_DTYPES
    )


@power("f2553", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.save_order()",))
def f2553(c: Cast) -> None:
    """The five keywords are exact. "Made at the start of your turn" is
    not: nothing in the save context says which of the turn's two throws
    this is, so the bonus also helps the ordinary end-of-turn one. No
    type word on the card, so untyped."""
    c.bonus("save", 2, on=c.me, until=When.ENCOUNTER, when=_elemental_save)


@power("f2554", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.on_save()",))
def f2554(c: Cast) -> None:
    """Pays out on succeeding at the throw `cf:warden-f0` grants. The
    feature is a ref, unlike f1024's -- what is missing there and here is
    knowing which feature a `SavingThrow` came from."""


# -- rows that turn on a named power's hold standing on you -----------------


@power("f1949", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=BENEFIT)
def f1949(c: Cast) -> None:
    """A further attack penalty on marked enemies while a racial power is
    running. The penalty itself is one gated `c.penalty` -- the attack
    context carries `target`, so "attacks that don't include you" is
    askable -- and what is missing is knowing the power is running."""


@power("f1951", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=BENEFIT)
def f1951(c: Cast) -> None:
    """Raises the damage bonus a racial power grants, against marked
    targets only. Written as the difference it comes to, it is still
    gated on that power's hold being up."""


@power("f1952", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=BENEFIT)
def f1952(c: Cast) -> None:
    """A shift around `cf:warden-f2`, which the marks it lays make
    readable -- so the whole of what is missing is whether the racial
    power's hold is standing."""


@power("f2557", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=BENEFIT)
def f2557(c: Cast) -> None:
    """A slide and a slow whenever an attack "benefiting from" a named
    power lands. `Hit` names the row that rolled; nothing records that a
    second row helped it."""


# -- racial powers named in prose -------------------------------------------


@power("f1853", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=RACIAL)
def f1853(c: Cast) -> None:
    """Marks every target of a racial power. `PowerUsed.targets` would
    carry them; the power is named in prose with no ref."""


@power("f1946", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=RACIAL)
def f1946(c: Cast) -> None:
    """An attack bonus for one named racial power against marked
    creatures. Same naming gap as f1853, and it is the gate rather than
    the bonus that wants the ref."""


@power("f1947", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=RACIAL)
def f1947(c: Cast) -> None:
    """A damage bonus against marked creatures after using the encounter
    power a racial build choice carries. Neither the choice nor the power
    it settles has a ref."""


@power("f1945", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("chargen.race_choice()",))
def f1945(c: Cast) -> None:
    """Marks whatever a racial trait's chosen power hits. The power is
    picked at build time out of another class's list and nothing records
    which one, the same gap f604 named."""
