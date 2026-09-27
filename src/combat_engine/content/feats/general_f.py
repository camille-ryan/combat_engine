"""General feats: the racial batch.

There is still no race, and none of that matters for the *benefit*. The
prerequisite is a column `chargen.meets` enforces at build time, and
`AUTHORING.md` says outright that a gate the engine cannot yet express
is not a reason to skip a feat. So these are written on their merits.

What decides each one is whether the racial power it rides on arrives
as a **ref** or as a **name**. `p1448`, `p1450`, `p1452`, `p1628`,
`p2473`, `p2485`, `p1831` and `p2339` are all refs in these
prerequisites, which makes a rider on one an ordinary trigger. The rest
-- infernal wrath, fade away, second chance called by name in the
benefit line rather than the gate -- are prose and carry
`c.on_racial_power()`.

Two smaller gaps come out of this batch and both are build-time rather
than in-fight. "You gain proficiency with all spears" changes what a
character may pick up, which is `chargen`'s business and not a `Cast`'s;
and "choose a new elemental manifestation" is a build choice that the
class feature does not record.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    ENCOUNTER,
    PERSONAL,
    REF,
    SELF,
    WILL,
    ActionPointSpent,
    ActionType,
    Cast,
    Hit,
    Keyword,
    PowerUsed,
    Size,
    Trigger,
    When,
    power,
)
from combat_engine.engine.components import Stats
from combat_engine.engine.dsl import get
from combat_engine.engine.query import allies, distance_between, enemies

#: A racial power the benefit line names in prose rather than by ref.
RACIAL = ("c.on_racial_power()",)
#: Nothing announces that a roll was a reroll, so a rider on one cannot
#: find its moment. The ranger's f761 dropped a clause for the same.
REROLL = ("c.on_reroll()",)
#: Which weapons a character may pick up is settled when it is built.
PROFICIENCY = ("chargen.proficiency()",)

_BIG = (Size.LARGE, Size.HUGE, Size.GARGANTUAN)


def _used(ref: str):  # noqa: ANN202
    def when(world, me: int, ev: Any) -> bool:  # noqa: ANN001
        return ev.actor == me and ev.power == ref

    return when


def _bigger_than_me(c: Cast, who: int) -> bool:
    """`Size.order`, not `>`: `Size` is a `StrEnum` and a bare
    comparison sorts the words alphabetically."""
    return c.size_of(who).order > c.size_of(c.me).order


# -- the ordinary standing bonuses ------------------------------------------


@power("f7", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f7(c: Cast) -> None:
    """Two larger enemies adjacent, counted per attack rather than at
    arming: a creature that is surrounded at the top of the round is
    not necessarily surrounded when the blow lands."""
    me = c.me
    c.bonus(
        AC, 2, on=me, until=When.ENCOUNTER,
        when=lambda ctx: sum(
            1 for f in enemies(c.world, me)
            if c.adjacent(to=f) and _bigger_than_me(c, f)
        ) >= 2,
    )


@power("f44", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f44(c: Cast) -> None:
    """Fire *or* fear, and both are real `Keyword` members -- the damage
    types are keywords on a card as well as types on a roll, which is
    why `Keyword.FIRE` exists beside `DamageType.FIRE`."""
    me = c.me
    wanted = (Keyword.FIRE, Keyword.FEAR)
    hot = lambda ctx: (  # noqa: E731
        (p := get(ctx.get("power", ""))) is not None
        and any(k in p.keywords for k in wanted)
    )
    c.bonus("attack", 1, on=me, until=When.ENCOUNTER, when=hot)
    c.bonus("damage", 1, on=me, until=When.ENCOUNTER, when=hot)


@power("f47", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f47(c: Cast) -> None:
    c.bonus("save", 1, on=c.me, until=When.ENCOUNTER, kind="feat")


@power("f77", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f77(c: Cast) -> None:
    """Asked per blow, because being bloodied is a state that arrives in
    the middle of a fight and this feat is printed for exactly that."""
    me = c.me
    c.bonus(
        "damage", 2, on=me, until=When.ENCOUNTER,
        when=lambda ctx: c.bloodied(on=me),
    )


@power("f193", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f193(c: Cast) -> None:
    """"Large or larger" is a fixed floor, not a comparison with your own
    size -- unlike `f7` a line above, which says "larger than you"."""
    me = c.me
    for defence in (AC, REF):
        c.bonus(
            defence, 1, on=me, until=When.ENCOUNTER,
            when=lambda ctx: (
                ctx.get("attacker") is not None
                and c.size_of(ctx["attacker"]) in _BIG
            ),
        )


@power("f215", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you spend an action point",
       on=Trigger(ActionPointSpent, lambda w, me, ev: ev.actor == me,
                  "you spend an action point"))
def f215(c: Cast) -> None:
    """"During any action you gain" -- so the bonus stands for the rest
    of the turn rather than being spent on one roll: a point can buy an
    action that attacks more than once."""
    c.bonus("attack", 3, on=c.me, until=When.EOT)


@power("f288", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f288(c: Cast) -> None:
    """The Insight half is a check rather than a fight. The initiative
    half is real and is handed out at arming -- `Initiative.bonus` is
    read before the d20, and a trait is armed after the opening rolls,
    so `c.initiative` is what moves an ally in the order."""
    me = c.me
    for friend in allies(c.world, me):
        if friend != me and distance_between(c.world, me, friend) <= 10:
            c.initiative(1, on=friend)


@power("f446", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f446(c: Cast) -> None:
    me = c.me
    c.bonus(
        "attack", 1, on=me, until=When.ENCOUNTER,
        when=lambda ctx: (
            not ctx.get("ranged", False)
            and ctx.get("target") is not None
            and any(
                a != me and c.adjacent_to(a, ctx["target"])
                for a in allies(c.world, me)
            )
        ),
    )


@power("f599", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f599(c: Cast) -> None:
    """The save bonus is narrowed to charm effects.

    When I wrote this the saving-throw context carried no `keywords`
    and the gate was silently false. It carries them now, derived from
    the row that laid the effect by `durations.keywords_of` -- so the
    narrowing is real rather than a sentence in a docstring.
    """
    me = c.me
    c.bonus(WILL, 1, on=me, until=When.ENCOUNTER, kind="feat")
    c.bonus(
        "save", 2, on=me, until=When.ENCOUNTER,
        when=lambda ctx: Keyword.CHARM in ctx.get("keywords", ()),
    )


@power("f596", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f596(c: Cast) -> None:
    """Three clauses about dragons, and the shape matters.

    A row may hold either a printed trigger or a standing modifier, not
    both -- if this were declared `on=Trigger(Hit, ...)` its body would
    run only on a critical hit, and the two attack bonuses would never
    be laid at all. So it is a trait, and the crit clause is a `c.watch`
    laid from inside it. That is what `c.watch` is for.

    `c.is_kind` reads the creature's printed type, which is what "a
    dragon" means here rather than anything about its name.
    """
    me = c.me
    is_dragon = lambda who: who is not None and c.is_kind("dragon", on=who)  # noqa: E731
    c.bonus(
        "attack", 1, on=me, until=When.ENCOUNTER,
        when=lambda ctx: is_dragon(ctx.get("target")),
    )
    # The second point while bloodied, as its own kind so `Mods.total`
    # keeps both rather than taking the larger of one type.
    c.bonus(
        "attack", 1, on=me, until=When.ENCOUNTER, kind=f"{c.ref}:bloodied",
        when=lambda ctx: c.bloodied(on=me) and is_dragon(ctx.get("target")),
    )

    def on_crit(ev: Any) -> None:
        p = get(ev.power)
        if (
            ev.attacker == me and ev.critical and is_dragon(ev.target)
            and p is not None
            and p.reach.kind in ("melee", "close_burst", "close_blast")
        ):
            stats = c.world.get(ev.target, Stats)
            c.temp_hp(stats.level if stats is not None else 1, on=me)

    c.watch(Hit, on_crit, on=me, until=When.ENCOUNTER)


@power("f609", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.on_revive()",))
def f609(c: Cast) -> None:
    """Pays out on coming back up in the same fight. `Dropped` announces
    going down and `Healed` announces the hit points, but nothing
    announces *regaining consciousness* -- the condition is cleared
    inside `Health` without a word, so the moment this row is printed
    for does not exist."""


# -- riders on a racial power that is a ref ---------------------------------


@power("f203", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p1628",
       on=Trigger(Hit, lambda w, me, ev: (
           ev.attacker == me and ev.power == "p1628"
       ), "you hit with that racial power"))
def f203(c: Cast) -> None:
    """Declared on the hit rather than on the use, because the printed
    line is "in addition to any damage you deal" -- a push handed out
    before the roll would land on a miss too."""
    c.push(1, on=c.trigger.target)


@power("f445", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p2485",
       on=Trigger(PowerUsed, _used("p2485"), "you use that racial power"))
def f445(c: Cast) -> None:
    c.temp_hp(5, on=c.me)


@power("f443", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.race_components()",))
def f443(c: Cast) -> None:
    """Scales a racial power's temporary hit points by how many of a
    race's components the character carries. The power is a ref; the
    components are a racial trait nothing models, and there is no race
    on a character to carry them."""


@power("f444", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p2485",
       on=Trigger(PowerUsed, _used("p2485"), "you use that racial power"))
def f444(c: Cast) -> None:
    """Widens what a racial power's saving throw may be made against,
    and adds to it.

    The widening is the power's own business -- it is the one that
    rolls the save, and this row cannot reach inside it. What this row
    *can* say is the +2, laid as a one-shot save bonus so it is spent
    on the throw the power is about to make. The widening is dropped.
    """
    c.bonus("save", 2, on=c.me, until=When.EOT, once=True, kind="feat")


@power("f471", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p2339",
       on=Trigger(PowerUsed, _used("p2339"), "you use that power"))
def f471(c: Cast) -> None:
    for who in c.trigger.targets:
        c.temp_hp(c.cha_mod, on=who)


@power("f216", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=REROLL)
def f216(c: Cast) -> None:
    """A penalty on the attack roll a racial power forces to be made
    again. `p1452` is a ref -- what is missing is that nothing announces
    a roll is a reroll, so there is no moment at which to penalise
    one."""


@power("f217", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=REROLL)
def f217(c: Cast) -> None:
    """A bonus on the roll `p1450` buys. Same gap as f216, from the
    other side."""


@power("f287", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.recast(reach=)",))
def f287(c: Cast) -> None:
    """Widens a named racial power's blast. Reach is header data the
    menu reads before anything runs, and nothing rewrites one."""


@power("f601", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.recast(reach=)",))
def f601(c: Cast) -> None:
    """Widens two named racial powers, a burst and a range. Same gap as
    f287, and both powers are refs, so it is not a naming one."""


@power("f387", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.deals(ref=)",))
def f387(c: Cast) -> None:
    """Changes what damage type one named power deals.

    `c.deals` exists and is the printed sentence for a *weapon* -- it
    overrides the type this creature's weapon attacks roll. This row
    overrides the type **one particular power** rolls, which is a
    different question: it must not touch anything else the character
    does, and `c.deals` has no way to name a row.
    """


@power("f602", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.on_granted_basic()", "c.class_feature()"))
def f602(c: Cast) -> None:
    """Damage of a type chosen by a racial manifestation, on a basic
    attack a class feature granted. Both halves are gaps and they are
    the two that turn up most often in this corpus."""


@power("f604", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("chargen.race_choice()",))
def f604(c: Cast) -> None:
    """Learns a second elemental manifestation and lets a rest switch
    between them. The manifestation is a racial choice, and there is no
    race on a character to hold one."""


# -- the bard's virtues, named in prose -------------------------------------


@power("f469", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.class_feature()",))
def f469(c: Cast) -> None:
    """Rides on a class feature that slides an ally. The feature is
    named in prose with no ref, which is the same gap eleven other rows
    carry."""


@power("f470", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.class_feature()",))
def f470(c: Cast) -> None:
    """Rides on a class feature that grants temporary hit points. Same
    gap as f469."""


@power("f472", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.on_second_wind()",))
def f472(c: Cast) -> None:
    """Temporary hit points when a nearby ally takes a second wind.
    Second wind is an action rather than a power and announces
    nothing."""


# -- proficiency, which is settled when the character is built --------------


@power("f64", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=PROFICIENCY)
def f64(c: Cast) -> None:
    """The damage half plays; the proficiency grant is dropped.

    Which weapon groups a character may pick up is settled by its
    chassis in `chargen`, and a `Cast` runs on a board with the gear
    already in hand. Writing the damage bonus without the grant is the
    right half to keep: a character that cannot hold a spear simply
    never meets the gate.
    """
    me = c.me
    c.bonus(
        "damage", 2, on=me, until=When.ENCOUNTER, kind="feat",
        # "spear" is a group; the card's other half is *longswords*, a
        # weapon rather than the whole heavy blade group. Widened here
        # rather than narrowed, and said so, because `chargen` hands out
        # exactly one heavy blade and it is the longsword.
        when=lambda ctx: _wielding_group(c, "spear", "heavy blade"),
    )


@power("f69", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       dropped=("chargen.proficiency()", "chargen.HAMMER"))
def f69(c: Cast) -> None:
    """Same shape as f64, for axes and hammers.

    **"hammer" is not one of this engine's weapon groups.** The set is
    axe, bow, crossbow, heavy blade, implement, light blade, mace,
    spear, staff and unarmed, so that arm of the gate was false in
    every fight and the row paid only on axes. `chargen` hands out no
    hammer at all, which is the gap rather than the group name -- the
    axe half plays and the hammer half is named.
    """
    me = c.me
    c.bonus(
        "damage", 2, on=me, until=When.ENCOUNTER, kind="feat",
        when=lambda ctx: _wielding_group(c, "axe"),
    )


def _wielding_group(c: Cast, *groups: str) -> bool:
    from combat_engine.engine.components import Gear

    gear = c.world.get(c.me, Gear)
    return gear is not None and any(w.group in groups for w in gear.melee)


# -- not a fight ------------------------------------------------------------


@power("f60", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f60(c: Cast) -> None:
    """Overland travel, tracks, and two skill bonuses. None of it is a
    fight."""


@power("f607", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f607(c: Cast) -> None:
    """A shared Perception check with a chosen ally. A check, not a
    fight."""
