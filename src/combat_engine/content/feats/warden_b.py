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

The gaps have narrowed. "While you are under the effect of your X
power" is no gap at all -- an effect's label is the ref of the row that
laid it, so `c.suffering(ref, include_self=True)` answers it, and three
of the four rows written against that hold are written now. "Instead
of" is not one either: `ForcedMove` is a cancellable `Decision` that
names the row shoving, so one feature's slide can be declined by ref
and replaced. What is left is the saving throw the class rolls at the
start of its turn -- nothing says which of a turn's two throws is being
rolled, or what the effect under it was.

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
    NO_TARGET,
    PERSONAL,
    SELF,
    ActionType,
    Cast,
    DamageType,
    Forced,
    Hit,
    Keyword,
    PowerUsed,
    Relation,
    SecondWind,
    Trigger,
    When,
    power,
)
from combat_engine.engine.dsl import get
from combat_engine.engine.events import (
    ActionPointSpent,
    Bloodied,
    ForcedMove,
    RelationSet,
    TurnStart,
)
from combat_engine.engine.query import holding
from combat_engine.engine.triggers import about_me

#: The two racial powers of `r1`, of which a character takes one.
R1 = ("p1448", "p12577")
#: The thirteen racial powers of `r33`, one per elemental
#: manifestation. A character takes one of them.
R33 = (
    "p1766", "p1767", "p1769", "p1770", "p1828",
    "p10043", "p10044", "p10045", "p10046",
    "p14073", "p14074", "p14075", "p14076",
)
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


def _used(ref: str):  # noqa: ANN202
    def when(world, me: int, ev: Any) -> bool:  # noqa: ANN001
        return ev.actor == me and ev.power == ref

    return when


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
       reach=PERSONAL, target=SELF,
       trigger="you use p1450 to reroll a weapon attack",
       on=Trigger(PowerUsed, _used("p1450"), "you use that racial power"))
def f1948(c: Cast) -> None:
    """A bonus to a racial reroll taken while in a guardian form.

    The old marker wanted an announcement that a roll was a reroll. The
    row does not need one: p1450 **is** the reroll, it is a declared ref,
    and `PowerUsed` carries the event it is answering -- so the attack
    being rerolled is `c.trigger.trigger`, and the roll it announces is
    still open.

    The +2 goes on the live `AttackResult` rather than being laid as a
    modifier, because a modifier is read when the roll is made and this
    one is printed for a roll that has already been made:
    `c.reroll_attack` shifts `total` by the difference between the faces
    and recomputes the hit from it, so two points added here survive the
    reroll and are read by the comparison that matters. `PowerUsed` is
    announced before the body runs, which is what puts this ahead of it.
    """
    used = c.trigger
    rolled = getattr(used, "trigger", None)
    result = getattr(rolled, "result", None)
    if result is None or not _in_guardian_form(c.world, c.me):
        return
    row = get(getattr(rolled, "power", ""))
    if row is None or Keyword.WEAPON not in row.keywords:
        return
    result.total += 2


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


def _my_crit(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.attacker == me and ev.critical


@power("f1842", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you score a critical hit with a heavy blade or a spear",
       on=Trigger(Hit, _my_crit, "you score a critical hit"))
def f1842(c: Cast) -> None:
    """Trades a critical hit for an ordinary one plus an immobilise.

    The marker read the damage as already rolled. It is not: `Hit` is
    announced by `resolve.attack` **before** the body rolls any damage,
    and `AttackResult.critical` -- which the event carries as `result` --
    is what `c.damage` reads to maximise it. So the demotion happens in
    time, and both the result and the announcement are set, because a
    rider watching the `Hit` reads the event rather than the result.

    Printed as "you can choose", so it is offered rather than taken.
    """
    ev = c.trigger
    if not _holding(c, "heavy blade", "spear"):
        return
    if not c.may("treat the critical hit as a normal hit"):
        return
    result = getattr(ev, "result", None)
    if result is not None:
        result.critical = False
    ev.critical = False
    c.immobilized(on=ev.target, until=When.SONT)


@power("f2796", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2796(c: Cast) -> None:
    """Swaps the slide in `p5094` -- the mark punishment that slides --
    for a longer pull, and slows two printed creature types.

    "Letting a named row's own forced movement not happen" is exactly
    what `ForcedMove` is: a `Decision`, cancellable, carrying the `power`
    that is doing the shoving. So the swap is a refusal of that row's
    slide and a pull of this row's own, at the same beat -- the shove is
    negotiated before the creature steps.

    A trait rather than a declared trigger, because the slide happens
    inside p5094's body and the watcher has to be standing before it
    runs.
    """
    me = c.me

    def instead(ev: ForcedMove) -> None:
        if ev.source != me or ev.power != "p5094" or ev.how is not Forced.SLIDE:
            return
        if not c.may("pull 3 squares instead of sliding"):
            return
        foe = ev.target
        ev.cancel("pulled instead")
        c.pull(3, on=foe)
        if c.is_kind("giant", on=foe) or c.is_kind("goblin", on=foe):
            c.slowed(on=foe, until=When.EOTNT)

    c.watch(ForcedMove, instead, until=When.ENCOUNTER, on=me, label=c.ref)


# -- second wind, which announces nothing -----------------------------------


@power("f1830", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use your second wind",
       on=Trigger(SecondWind, about_me, "you use your second wind"))
def f1830(c: Cast) -> None:
    """Heroic tier, so 2; the 11th- and 21st-level steps are paragon."""
    c.resist(2, on=c.me, until=When.EONT)


@power("f1846", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use your second wind",
       on=Trigger(SecondWind, about_me, "you use your second wind"))
def f1846(c: Cast) -> None:
    """A saving throw for a *second* ally when the second wind lands.

    Only the throw: the surge is `cf:warden-f1s1`'s half and that row is
    written. Which ally it chose is decided inside its own body and nothing
    announces it, so the pool offered here is every ally within 5 and the
    overlap is left standing rather than faked away.

    `side="ally"` already leaves the warden out; the explicit test is the
    one that row learned to keep.

    Printed as "you can", so it is offered and declining is an answer.
    """
    me = c.me
    near = sorted(
        (a for a in c.within(5, side="ally") if a != me),
        key=lambda a: -c.missing(on=a),
    )
    friend = c.choose(near, f"{c.ref}: who else makes a saving throw",
                      optional=True)
    if friend is not None:
        c.save(on=friend)


@power("f1886", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use your second wind",
       on=Trigger(SecondWind, about_me, "you use your second wind"))
def f1886(c: Cast) -> None:
    """One modifier gated on the damage context's `target` rather than a
    bonus laid per enemy, so an enemy marked later in the turn is covered
    too."""
    me = c.me
    c.bonus("damage", c.wis_mod, on=me, until=When.EONT,
            when=lambda ctx: ctx.get("target") is not None
            and c.marked(on=ctx["target"], by=me))


@power("f2556", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2556(c: Cast) -> None:
    """A shift *instead of* `cf:warden-f1s2` sliding your marked enemies.

    The alternative is sayable after all: `ForcedMove` is cancellable and
    names the row shoving, so the feature's slides can be declined by
    ref. Written as a trait that answers the **slide** rather than the
    second wind, which is what makes the choice ordering-proof -- both
    rows answer `SecondWind`, and a refusal armed from this row's own
    answer would arrive after the feature's if the feature is heard
    first. Asked at the first slide, remembered for the rest of them,
    because the card offers one choice and not one per enemy.
    """
    me = c.me
    taken: list[bool] = []

    def instead(ev: ForcedMove) -> None:
        if ev.source != me or ev.power != "cf:warden-f1s2":
            return
        if ev.how is not Forced.SLIDE:
            return
        if not taken:
            want = c.con_mod > 0 and c.may(
                "shift instead of sliding your marked enemies"
            )
            taken.append(want)
            if want:
                c.shift(c.con_mod)
        if taken[0]:
            ev.cancel("shifted instead")

    c.watch(ForcedMove, instead, until=When.ENCOUNTER, on=me, label=c.ref)


@power("f2558", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use your second wind",
       on=Trigger(SecondWind, about_me, "you use your second wind"))
def f2558(c: Cast) -> None:
    """Lightning, not the untyped default."""
    me = c.me
    for foe in c.enemies():
        if c.marked(on=foe, by=me):
            c.flat(c.con_mod, dtype=DamageType.LIGHTNING, on=foe)


@power("f1874", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1874(c: Cast) -> None:
    """Swaps a slide for a push inside `cf:warden-f1s2`.

    Something does take a forced movement back: `ForcedMove` is a
    `Decision` and carries the `power` shoving, so one row's slide can be
    refused by ref and replaced without touching the row that issued it.
    Same shape as f2796.
    """
    me = c.me

    def instead(ev: ForcedMove) -> None:
        if ev.source != me or ev.power != "cf:warden-f1s2":
            return
        if ev.how is not Forced.SLIDE or not c.may("push 2 squares instead"):
            return
        foe = ev.target
        ev.cancel("pushed instead")
        c.push(2, on=foe)

    c.watch(ForcedMove, instead, until=When.ENCOUNTER, on=me, label=c.ref)


# -- the saving throw the class gets at the start of its turn ---------------


@power("f1941", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=(*SAVE_KEYWORDS, "c.save_order()"))
def f1941(c: Cast) -> None:
    """Temporary hit points for shaking off one sort of effect.

    Two holds, and the second was unnamed. `cf:warden-f0` is the ref that
    rolls the throw and `SavingThrow` carries whether it succeeded --
    what is missing is which keywords the effect it was rolled against
    had. The save *modifier* context carries them, but this row answers
    the event, whose `against` is the effect's `__str__`: the label is
    inside that string and only inside it, so reading a ref back out
    would be parsing a repr, which is the sort of thing that breaks
    silently the day the repr changes.

    "At the start of your turn" is the second: nothing on the throw says
    which of the turn's two it is, the hold f2553 names."""


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
       reach=PERSONAL, target=SELF, todo=("c.save_order()",))
def f2554(c: Cast) -> None:
    """Pays out on succeeding at the throw `cf:warden-f0` grants.

    Re-aimed to the hold it shares with f2553 and f1941. The feature is a
    ref, but it is a trait that calls `c.save` from a `TurnStart` watch
    rather than a row anybody uses -- so there is no `PowerUsed` to
    bracket the throw with, and what would tell this one from the
    ordinary end-of-turn throw is the same missing thing: which of the
    turn's saves is being rolled."""


# -- rows that turn on a named power's hold standing on you -----------------


@power("f1949", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1949(c: Cast) -> None:
    """A further attack penalty on marked enemies while a racial power is
    running.

    The ref was the whole of it. The spec used to name the power as
    `x_m5139a3` -- a stat block's ability that happens to share the name,
    which is no id to ask about -- and now names `p6188`, so the row is the
    one gated `c.penalty` the old note promised.

    The gate is the printed clause: "attacks that don't include you as a
    target". `ctx["among"]` is the whole target set, which is the same test
    `resolve`'s own mark penalty makes a few hundred lines further down --
    not `ctx["target"]`, which would still penalise a blast that caught the
    warden along with everybody else.
    """
    if c.me not in c.suffering("p6188", include_self=True):
        return
    me = c.me

    def without_me(ctx: dict) -> bool:
        return me not in ctx.get("among", ())

    for foe in c.enemies():
        if c.marked(on=foe):
            c.penalty("attack", max(0, c.con_mod), on=foe,
                      until=When.EONT, when=without_me)


def _under(c: Cast, ref: str) -> bool:
    """Is this warden under the effect of its own `ref`?

    An effect's label is the ref of the row that laid it, so a power's
    own hold is found by label; `include_self` is what lets the caster
    find one it laid on itself, which is every racial buff here.
    """
    return c.me in c.suffering(ref, include_self=True)


@power("f1951", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1951(c: Cast) -> None:
    """Raises the damage bonus p2483 grants from +2 to +3, against marked
    targets only, so what is laid here is the one point of difference.

    The hold being up is readable: p2483 lays its bonus with `c.bonus`,
    which stamps the row's ref as the label, and `c.suffering` finds it.
    Both halves are asked per damage roll, because the racial power can
    go up mid-turn and the mark can land after the bonus does.
    """
    me = c.me
    c.bonus(
        "damage", 1, on=me, until=When.ENCOUNTER,
        when=lambda ctx: (
            _under(c, "p2483")
            and (v := ctx.get("target")) is not None
            and c.marked(on=v, by=me)
        ),
    )


@power("f1952", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you mark an enemy with cf:warden-f2 while p2484 is up",
       on=Trigger(RelationSet, _i_marked, "you mark an enemy"))
def f1952(c: Cast) -> None:
    """A shift around `cf:warden-f2`, which the marks it lays make
    readable, and p2484's hold is readable too -- `c.suffering` finds a
    self-laid effect by the ref of the row that laid it.

    The feature marks every adjacent enemy at once, so the shift is
    taken on the first mark of the turn and not once per enemy. "Before
    or after" is one square either way and the after is what a row
    answering the mark can take.
    """
    if not _under(c, "p2484"):
        return
    if _marks_this_turn(c.world, c.me) != 1:
        return
    c.shift(1)


@power("f2557", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit with an attack benefiting from p1769",
       on=Trigger(Hit, lambda world, me, ev: ev.attacker == me, "you hit"))
def f2557(c: Cast) -> None:
    """A slide and a slow whenever an attack "benefiting from" p1769
    lands.

    "Benefiting from" is two questions, and both are answerable: that
    power's hold is standing on the warden (`c.suffering`, by label), and
    the attack is one it actually pays out on -- p1769's own gate is the
    lightning-or-thunder keyword of the row rolling, so the same question
    is asked of the row that hit rather than assumed.
    """
    row = get(c.trigger.power)
    if row is None or not _under(c, "p1769"):
        return
    if not {Keyword.THUNDER, Keyword.LIGHTNING} & set(row.keywords):
        return
    me = c.me
    for foe in c.enemies():
        if c.marked(on=foe, by=me):
            c.slide(1, on=foe)
            c.slowed(on=foe, until=When.EONT)


# -- riders on a racial power, one a ref and two still prose ----------------


@power("f1853", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p1448",
       on=Trigger(PowerUsed, _used("p1448"), "you use that racial power"))
def f1853(c: Cast) -> None:
    """Marks every target of the racial power. `PowerUsed` fires before
    the body, but the targets are chosen before it too, so
    `PowerUsed.targets` is the set the card means -- and a mark lands on
    a creature the attack goes on to miss just the same."""
    for foe in c.trigger.targets:
        c.mark(on=foe, until=When.EONT)


@power("f1946", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1946(c: Cast) -> None:
    """The race's powers are declared, so the gate is a pair of refs.
    A standing modifier and not a trigger: the attack context carries
    `power` and `target`, which is the whole of "with that power against
    creatures marked by you"."""
    me = c.me

    def breath_at_my_mark(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        return (
            ctx.get("power") in R1
            and victim is not None
            and c.marked(on=victim, by=me)
        )

    c.bonus("attack", 1, on=me, until=When.ENCOUNTER, kind="feat",
            when=breath_at_my_mark)


@power("f1947", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you use a r33 racial power",
       on=Trigger(PowerUsed,
                  lambda world, me, ev: ev.actor == me and ev.power in R33,
                  "you use a r33 racial power"))
def f1947(c: Cast) -> None:
    """The race's thirteen powers are declared and a character takes one
    of them, so the build choice no longer stands between the row and
    its moment. The damage context carries `target`, so the mark is a
    gate it can answer. The 11th and 21st steps are out of scope."""
    me = c.me
    c.bonus("damage", 2, on=me, until=When.EONT,
            when=lambda ctx: (v := ctx.get("target")) is not None
            and c.marked(on=v, by=me))


@power("f1945", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("chargen.race_choice()",))
def f1945(c: Cast) -> None:
    """Marks whatever a racial trait's chosen power hits. The power is
    picked at build time out of another class's list and nothing records
    which one, the same gap f604 named."""
