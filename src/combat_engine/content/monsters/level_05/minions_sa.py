"""Monster abilities, level 5, minions.

Seventeen stat blocks, thirty rows. Three more level 5 minions print no
ability at all -- m2868, m811 and m3978's neighbours -- so there is nothing to
decorate for them and they are absent rather than skipped. (The blocks with no
row: m2868, m811.)

The conventions are the ones the level 1 to level 4 minion sweeps settled:

* a minion's damage is a flat number in the header, `Damage("", n,
  kind=MINION)`, and the body calls `c.hit()` -- so an MM1 block can be
  rescaled later. Its one hit point is in the database;
* a card printing **two** numbers for one blow -- "5 damage, or 6 if it has
  combat advantage" -- keeps the base in the header where a rescale can find it
  and adds the difference with `c.flat`. A gated `c.bonus` would survive the
  turn, and these are per-swing lines;
* "two others of its kind within 5 squares" counts by `Ident.ref`, because
  every creature in a fight may share a type word and the printed sentence is
  about this stat block;
* a card that prints no range at all is melee 1, and a printed band of "15/30"
  takes the normal range.

Six helpers are imported rather than copied, from the level 1 to level 4
sweeps.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_02.lurkers_sa import _triggering_enemy
from combat_engine.content.monsters.level_02.minions_sa import _closes_ranks, _kin_within
from combat_engine.content.monsters.level_02.soldiers_sa import _ref_of
from combat_engine.content.monsters.level_03.lurkers_sa import _restricted_to
from combat_engine.content.monsters.level_04.minions_sa import _extra_with_advantage
from combat_engine.engine import (
    AC,
    AT_WILL,
    ENCOUNTER,
    FREE,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    ActionType,
    Attack,
    Cast,
    CloseBurst,
    Condition,
    Damage,
    DamageType,
    Keyword,
    Melee,
    Ranged,
    Relation,
    Usage,
    When,
    World,
    power,
)
from combat_engine.engine.events import Bloodied, DamageRolled, Dropped
from combat_engine.engine.monster_math import MINION
from combat_engine.engine.query import distance_between, enemies, has_combat_advantage
from combat_engine.engine.triggers import Trigger, about_me, targets_me

# -- what these blocks share -----------------------------------------------


def _adjacent_enemy_bloodied(world: World, me: int, ev: Bloodied) -> bool:
    """"An enemy adjacent to it becomes bloodied."

    `Bloodied` is emitted once per creature, so "becomes" needs nothing said
    about it; `enemy_within` reads the event's actor, which is the right field
    here, but it does not also ask the side, so both are asked by hand.
    """
    if ev.actor == me or ev.actor not in enemies(world, me):
        return False
    return distance_between(world, me, ev.actor) <= 1


def _grabbing(c: Cast) -> list[int]:
    return c.grabbing()


def _holding_nobody(world: World, eid: int) -> bool:
    return not world.relations.targets(Relation.GRABBED_BY, eid)


def _grabbed_by_me_in_reach(world: World, eid: int) -> bool:
    """"One creature grabbed by it", as an entry gate. `Target` filters on side,
    count, size and what is in hand and on nothing a creature is *suffering*, so
    the narrowing cannot live there, and `dsl.usable` is handed `(world, eid)`
    and the caster is all it knows. #361."""
    targets = world.relations.targets(Relation.GRABBED_BY, eid)
    return any(distance_between(world, eid, foe) <= 1 for foe in targets)


def _edge_on_me(c: Cast) -> bool:
    """"If the target is granting combat advantage to it."

    Asked of the board rather than off `c.result`: this is the *second* half of
    two blocks' blows and the card phrases it as a standing circumstance of the
    victim, not as a property of the roll that just happened.
    """
    victim = c.target
    return victim is not None and has_combat_advantage(c.world, c.me, victim)


# --------------------------------------------------------------------------
# m1878
# --------------------------------------------------------------------------


@power(
    "m1878a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("", 5, dtype=DamageType.NECROTIC, kind=MINION),
)
def m1878a0(c: Cast) -> None:
    if c.strike():
        c.hit()


_M1878_SMELLS_BLOOD = "an enemy adjacent to it becomes bloodied"


@power(
    "m1878a1",
    level=5,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC],
    trigger=_M1878_SMELLS_BLOOD,
    on=Trigger(Bloodied, _adjacent_enemy_bloodied, _M1878_SMELLS_BLOOD),
)
def m1878a1(c: Cast) -> None:
    """The printed effect is a melee basic attack, so the row has no attack line
    of its own -- the compendium's "+10 vs AC; 1d10+4" is the basic leaking in,
    and `c.basic` reads whichever row this creature's actually is. The swing goes
    at the triggering creature and not at a target of this row, which an
    immediate action with `NO_TARGET` has none of."""
    foe = _triggering_enemy(c)
    if foe is not None and c.distance(foe) <= 1:
        c.basic(on=foe)


# --------------------------------------------------------------------------
# m2242
# --------------------------------------------------------------------------


@power(
    "m2242a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("", 6, kind=MINION),
)
def m2242a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2242a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("", 6, kind=MINION),
)
def m2242a1(c: Cast) -> None:
    """"15/30" takes the normal range; the long one is a penalty the engine works
    out from the same number."""
    if c.strike():
        c.hit()


# --------------------------------------------------------------------------
# m3978
# --------------------------------------------------------------------------


@power(
    "m3978a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("", 7, kind=MINION),
)
def m3978a0(c: Cast) -> None:
    """`c.mark` and never `c.condition(Condition.MARKED, ...)`: only the first
    sets `Relation.MARKED_BY`, which is what every "an enemy marked by it"
    trigger in the tree reads."""
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


# --------------------------------------------------------------------------
# m4642
# --------------------------------------------------------------------------


@power(
    "m4642a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("", 4, kind=MINION),
)
def m4642a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4642a1",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4642a1(c: Cast) -> None:
    """A trait and not the standard action the database files it as. Gated rather
    than laid, because who is standing within 5 squares changes every time
    anybody moves; "power bonus" is the word the card prints, so that is the
    `kind`. `_kin_within` counts with `side="team"`, which is why the printed
    "two **other**" is tested against three."""
    _closes_ranks(c, 1)
    c.bonus(
        "attack", 1, on=c.me, until=When.ENCOUNTER, kind="power",
        when=lambda _ctx: len(_kin_within(c, 5, c.me)) >= 3,
    )


# --------------------------------------------------------------------------
# m4746
# --------------------------------------------------------------------------


@power(
    "m4746a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("", 6, kind=MINION),
)
def m4746a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4746a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("", 6, kind=MINION),
)
def m4746a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4746a2",
    level=5,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m4746a2(c: Cast) -> None:
    c.shift(2)


# --------------------------------------------------------------------------
# m5403
# --------------------------------------------------------------------------


@power(
    "m5403a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("", 5, kind=MINION),
)
def m5403a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5403a1",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("", 6, kind=MINION),
)
def m5403a1(c: Cast) -> None:
    """"Recharges when it spends a minor action to reload" is the same minor this
    row already costs, so spending the action *is* the reload and the printed
    sentence adds nothing the header does not already say."""
    if c.strike():
        c.hit()


_M5403_FALLS = "it drops to 0 hit points"


@power(
    "m5403a2",
    level=5,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(3),
    target=NO_TARGET,
    keywords=[Keyword.FEAR],
    trigger=_M5403_FALLS,
    on=Trigger(Dropped, about_me, _M5403_FALLS),
)
def m5403a2(c: Cast) -> None:
    """"Ally minions in the burst" is a pool `Target` cannot name -- it filters
    on side, count and size and not on whether a creature is a minion -- so the
    row takes no target of its own and the set is read off the board. #361."""
    for mate in c.in_squares(c.area(), side="ally"):
        if c.is_minion(mate):
            c.shift(1, who=mate)


# --------------------------------------------------------------------------
# m5437
# --------------------------------------------------------------------------


@power(
    "m5437a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("", 6, dtype=DamageType.POISON, kind=MINION),
)
def m5437a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m5437a1",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=REF, printed=8),
    damage=Damage("", 6, dtype=DamageType.POISON, kind=MINION),
)
def m5437a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.blinded(until=When.SAVE_ENDS)


# --------------------------------------------------------------------------
# m5589
# --------------------------------------------------------------------------


@power(
    "m5589a0",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5589a0(c: Cast) -> None:
    """A gate and not a standing grant: who is beside the victim changes every
    time anybody walks, and `has_combat_advantage` is worked out from the board
    as the attack is rolled. "Two or more of its allies" counts every friend and
    not only its own sort, which is what the card says here and not on the
    blocks that name a kind."""

    def outnumbered(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        if not isinstance(victim, int):
            return False
        return len([a for a in c.within(1, of=victim, side="ally") if a != c.me]) >= 2

    c.gains_advantage(outnumbered, until=When.ENCOUNTER, on=c.me)


@power(
    "m5589a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("", 6, kind=MINION),
)
def m5589a1(c: Cast) -> None:
    """Two separate sentences, so two separate ifs: a prone target takes the
    extra points *and* a swing with the advantage knocks one down. The advantage
    is read off `c.result`, because a one-shot grant has already been spent by
    the time the board is asked again."""
    if not c.strike():
        return
    c.hit()
    if c.is_(Condition.PRONE):
        c.flat(2)
    if c.result is not None and c.result.advantage:
        c.prone()


# --------------------------------------------------------------------------
# m5590
# --------------------------------------------------------------------------


@power(
    "m5590a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("", 5, kind=MINION),
    requires_text="must be in its humanoid or hybrid shape",
    dropped=("c.in_form()",),
)
def m5590a0(c: Cast) -> None:
    """The shape Requirement is the named gap: `c.form` holds one but nothing
    asks which one is standing, so the gate cannot be written in the header or in
    the body. The blow is exact."""
    if c.strike():
        c.hit()
        _extra_with_advantage(c, 1)


@power(
    "m5590a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("", 3, kind=MINION),
    requires_text="must be in its beast or hybrid shape",
    dropped=("c.in_form()",),
)
def m5590a1(c: Cast) -> None:
    """"Save ends both" is one effect carrying the burn and the penalty to saving
    throws, which `save_mod` is -- written as two effects the victim would get two
    throws and shake off half of what the card calls one thing. No condition is
    printed, so none is passed: `c.condition` with none of them is an effect that
    is a burn and a penalty and nothing else."""
    if not c.strike():
        return
    c.hit()
    if _edge_on_me(c):
        c.condition(
            until=When.SAVE_ENDS,
            save_mod=-2,
            ongoing=(3, DamageType.UNTYPED),
        )


@power(
    "m5590a2",
    level=5,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    requires_text="must be in its beast shape",
    dropped=("c.in_form()",),
)
def m5590a2(c: Cast) -> None:
    c.shift(c.speed_of())


@power(
    "m5590a3",
    level=5,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
)
def m5590a3(c: Cast) -> None:
    """Three shapes, chosen once per use. The size change is the half that has a
    board consequence; "until it uses this again" is what `c.form`'s own
    replacement does, and dropping to 0 hit points ends every effect on a corpse
    anyway, so neither needs a watch."""
    from combat_engine.engine import Size

    which = c.choose(["tiny", "medium", "small"], f"{c.ref}: which shape") or "medium"
    size = {"tiny": Size.TINY, "medium": Size.MEDIUM, "small": Size.SMALL}[which]
    c.form(label=f"{c.ref} {which}", until=When.ENCOUNTER, revert=MINOR)
    c.resize(size, on=c.me, until=When.ENCOUNTER)


_M5590_STRUCK = "it takes damage from an attack"


@power(
    "m5590a4",
    level=5,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5590_STRUCK,
    on=Trigger(DamageRolled, targets_me, _M5590_STRUCK),
)
def m5590a4(c: Cast) -> None:
    """`DamageRolled` is the only window in which the blow can still be taken
    down to nothing -- by `DamageApplied` it has already come off hit points, and
    this creature has one. `bare`, because there is no save-ends effect to shake
    off; this is one of the handful of printed saves against nothing."""
    if not c.save(on=c.me, bare=True, against=c.ref):
        return
    blow = c.trigger
    c.reduce(max(0, getattr(blow, "amount", 0)), blow)


# --------------------------------------------------------------------------
# m5608
# --------------------------------------------------------------------------


@power(
    "m5608a0",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5608a0(c: Cast) -> None:
    """"Two extra damage for each **other** one of these adjacent to the target."

    A per-ally amount is not a number `c.bonus` can hold, so it is four +2s each
    gated on a different size of crowd -- untyped bonuses add, which is exactly
    what "for each" wants, and four is as many as can stand around one square.
    Counted by `Ident.ref`, because every creature in the fight may share a type
    word, and off the blow's own context, because who is beside the victim
    changes every time anybody walks.
    """
    mine = _ref_of(c, c.me)

    def crowd(ctx: dict[str, Any]) -> int:
        victim = ctx.get("target")
        if not isinstance(victim, int):
            return 0
        beside = c.within(1, of=victim, side="ally")
        return len([a for a in beside if a != c.me and _ref_of(c, a) == mine])

    for least in (1, 2, 3, 4):
        c.bonus(
            "damage", 2, on=c.me, until=When.ENCOUNTER,
            when=lambda ctx, n=least: crowd(ctx) >= n,
        )


@power(
    "m5608a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.DISEASE],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("", 5, kind=MINION),
    dropped=("c.contract(ref)",),
)
def m5608a1(c: Cast) -> None:
    """The blow and the step are exact. The disease the end-of-encounter save
    hands over is a block of its own and nothing carries one, which is the named
    gap."""
    if c.strike():
        c.hit()
        c.shift(1)


# --------------------------------------------------------------------------
# m5609
# --------------------------------------------------------------------------


@power(
    "m5609a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("", 5, kind=MINION),
    dropped=("c.grab(dc=)",),
)
def m5609a0(c: Cast) -> None:
    """"If it has no creature grabbed" is a condition on the grab and not on the
    row, so it is asked here rather than as an entry gate -- the damage lands
    either way. The printed escape DC has nowhere to go."""
    if c.strike():
        c.hit()
        if _holding_nobody(c.world, c.me):
            c.grab()


@power(
    "m5609a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.DISEASE],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("", 8, kind=MINION),
    requires=_grabbed_by_me_in_reach,
    requires_text="targets a creature it has grabbed",
    dropped=("Target.kind", "c.contract(ref)"),
)
def m5609a1(c: Cast) -> None:
    """Where the chooser handed it somebody it is not holding and it *is* holding
    somebody else in reach, the swing is redirected rather than thrown away."""
    foe = _restricted_to(c, 1, lambda f: f in _grabbing(c))
    if foe is None:
        return
    if c.strike(on=foe):
        c.hit(on=foe)


# --------------------------------------------------------------------------
# m6065
# --------------------------------------------------------------------------


@power(
    "m6065a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("", 4, kind=MINION),
)
def m6065a0(c: Cast) -> None:
    """The burn is gated on the advantage the blow actually had, read off
    `c.result`: asking the board again is too late, because a one-shot grant is
    already spent by then."""
    if not c.strike():
        return
    c.hit()
    if c.result is not None and c.result.advantage:
        c.ongoing(5, until=When.SAVE_ENDS)


# --------------------------------------------------------------------------
# m6153
# --------------------------------------------------------------------------


@power(
    "m6153a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("", 6, kind=MINION),
)
def m6153a0(c: Cast) -> None:
    """The shift is an Effect and not part of the Hit, so it happens whether the
    swing landed or not -- which is the whole point of a minion that does not
    want to be standing there afterwards."""
    if c.strike():
        c.hit()
    c.shift(1)


# --------------------------------------------------------------------------
# m820
# --------------------------------------------------------------------------


@power(
    "m820a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("", 5, dtype=DamageType.NECROTIC, kind=MINION),
)
def m820a0(c: Cast) -> None:
    """The base stays in the header where a rescale can find it and the extra
    point against a bloodied target is added here."""
    if c.strike():
        c.hit()
        if c.bloodied():
            c.flat(1, dtype=DamageType.NECROTIC)


@power(
    "m820a1",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.restrict_action()", "c.kill()"),
)
def m820a1(c: Cast) -> None:
    """Neither half can be said. Cutting a turn down to a single move action is a
    ceiling on the action budget rather than a grant, and `c.grant_action` only
    ever adds; and the creature burning to ash is a reduction to nothing that is
    not damage, so `c.flat` on its remaining hit point is the wrong reading as
    well as the only available one. The sunlight itself is readable --
    `c.terrain` carries the word -- which is why this is a `todo` on two verbs
    and not on a terrain gap."""
    if c.terrain("sunlight"):
        c.note(f"{c.ref}: it is standing in the light")
