"""Ranger feats.

The class's two halves split this list almost exactly in two.

**The quarry half is writable.** `cf:ranger-f1` is named by ref in every
one of their prerequisites, `c.quarry` lays the relation and
`world.relations.holds` reads it back, so "against the target of your
quarry" is a real question.

**The beast half is written now.** The class feature exists: the
fighting-style fork carries a leg for it, `cf:ranger-f0` calls the
creature with `c.call_beast`, and its numbers -- scores, defences, hit
points, attack bonus, damage die -- load out of the `companion` table
rather than being written down here. `c.beast()` is the reader.

**The racial half is written now too.** The four rows here that name a
racial power by ref -- `p1448`, `p2473`, `p1450`, `p1449` -- have one:
the races and their powers are declared, so a resistance keyed to one
reads its type off `c.element`, an exemption from one knows what the
effect is, and a rider on one is an ordinary `PowerUsed` trigger.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    ENCOUNTER,
    FORT,
    PERSONAL,
    REF,
    SELF,
    WILL,
    ActionType,
    AttackDeclared,
    Cast,
    Condition,
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
from combat_engine.engine.query import team


def _swings_at_beast(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    """A melee attack on this ranger's beast, by somebody standing next to
    one of them. The second clause is the card's own widening: "if you are
    adjacent to your beast companion, you can make this attack even if you
    can't reach the attacker"."""
    from combat_engine.engine.components import Companion
    from combat_engine.engine.query import adjacent

    mine = world.get(ev.target, Companion)
    p = get(ev.power)
    if mine is None or mine.owner != me or p is None or p.reach.kind != "melee":
        return False
    return adjacent(world, me, ev.attacker) or adjacent(world, me, ev.target)


def _is_my_quarry(c: Cast, who: int | None) -> bool:
    """Is that creature the one this ranger has marked as its quarry?

    `c.quarry` lays `Relation.QUARRY_OF` from the ranger to the target,
    and the relation table is the only thing that remembers it -- there
    is no condition and no effect label to match on.
    """
    return who is not None and c.world.relations.holds(
        Relation.QUARRY_OF, c.me, who
    )


def _crit_on_quarry(kind: str):  # noqa: ANN202
    def when(world, me: int, ev: Any) -> bool:  # noqa: ANN001
        p = get(ev.power)
        return (
            ev.attacker == me
            and ev.critical
            and p is not None
            and (p.reach.kind == kind or (kind == "ranged" and p.reach.alt))
            and world.relations.holds(Relation.QUARRY_OF, me, ev.target)
        )

    return when


@power("f280", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you crit your quarry with a melee attack",
       on=Trigger(Hit, _crit_on_quarry("melee"), "you crit your quarry"))
def f280(c: Cast) -> None:
    """A free shift and a penalty on that enemy's attacks **against
    you**, which the attack context reaches through `attacker`."""
    me = c.me
    c.shift(1)
    c.penalty(
        "attack", 2, on=c.trigger.target, until=When.EONT,
        when=lambda ctx: ctx.get("target") == me,
    )


@power("f301", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you crit your quarry with a ranged attack",
       on=Trigger(Hit, _crit_on_quarry("ranged"), "you crit your quarry"))
def f301(c: Cast) -> None:
    """Your **allies**, not you."""
    me = c.me
    foe = c.trigger.target
    for friend in [a for a in team(c.world, me) if a != me]:
        c.bonus(
            "attack", 1, on=friend, until=When.SONT,
            when=lambda ctx: ctx.get("target") == foe,
        )


@power("f783", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f783(c: Cast) -> None:
    """Allies deal more to whatever this ranger has marked. Read off the
    relation each time rather than fixed at arming, because the quarry
    moves from creature to creature over a fight."""
    me = c.me
    for friend in [a for a in team(c.world, me) if a != me]:
        c.bonus(
            "damage", 1, on=friend, until=When.ENCOUNTER,
            when=lambda ctx: _is_my_quarry(c, ctx.get("target")),
        )


@power("f761", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.on_reroll()",))
def f761(c: Cast) -> None:
    """Extra damage when a reroll granted by one racial power lands on
    the quarry. The quarry half is written as a standing damage bonus;
    what is dropped is the narrowing to *rerolled* attacks, because
    nothing announces that a roll was a reroll."""
    c.bonus(
        "damage", 0, dice="1d6", on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: _is_my_quarry(c, ctx.get("target")),
    )


@power("f273", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f273(c: Cast) -> None:
    """The class feature's extra damage rolls d8s instead of d6s.

    One die at every level this build imports, so "1d8" says the whole
    sentence -- see f185, which is the same row for the other striker and
    carries the note about what 11th level does to both.

    The gate names a second ref that is not declared, so there is nothing to
    change for it; `cf:ranger-f1` is the only quarry in the tree."""
    c.change_dice("cf:ranger-f1", "1d8")


@power("f786", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.extend_move()",))
def f786(c: Cast) -> None:
    """Adds two squares to the distance two named racial powers move you.
    Both are named by ref, so this is not a naming gap -- nothing adds to
    the distance a *particular* row moves."""


@power("f764", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f764(c: Cast) -> None:
    """A Stealth bonus with cover outdoors. The engine has no outdoors."""


@power("f777", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f777(c: Cast) -> None:
    """Finding and hiding tracks. Not a fight."""


# -- the beast companion ----------------------------------------------------
#
# `c.beast()` is read fresh inside every gate rather than captured at
# arming: the beast can be killed and called again, and a lambda holding
# the old id goes silently false the moment it is.


@power("f752", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f752(c: Cast) -> None:
    """A skill bonus for the beast and nothing else. Narrative-only, the
    way a cantrip that lights a torch is."""


@power("f753", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       dropped=("c.provoke(ignore_reach=)",),
       trigger="an adjacent enemy makes a melee attack against your beast",
       on=Trigger(AttackDeclared, _swings_at_beast,
                  "an enemy makes a melee attack against your beast"))
def f753(c: Cast) -> None:
    """The window, opened for the ranger against whoever swung at the beast.

    Dropped is the second sentence: standing next to the beast lets you
    attack a limb you could not otherwise reach, and the window checks
    reach like any other.
    """
    c.provoke(c.me, on=c.trigger.attacker, why=c.ref)


@power("f754", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f754(c: Cast) -> None:
    """Skill training for the beast. Not a fight."""


@power("f760", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f760(c: Cast) -> None:
    """`p1448` is declared and the damage type it deals is the build
    choice `c.element` records -- the same reader `p1448`'s own body
    uses. No element recorded is no resistance rather than resistance to
    everything, which is what `dtype=None` would have meant."""
    pet = c.beast()
    dtype = c.element(on=c.me)
    if pet is not None and dtype is not None:
        c.resist(5 + c.level // 2, dtype, on=pet, until=When.ENCOUNTER)


@power("f766", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f766(c: Cast) -> None:
    """A damage bonus on an opportunity attack the beast is standing beside.

    Both halves live in the damage context -- it carries `opportunity` and
    `target` -- which is the thin one, so this is a gate it can actually
    answer. Untyped: the card prints no word in front of "bonus".
    """
    def beside_the_beast(ctx: dict[str, Any]) -> bool:
        pet = c.beast()
        victim = ctx.get("target")
        return (
            bool(ctx.get("opportunity"))
            and pet is not None
            and victim is not None
            and c.adjacent_to(pet, victim)
        )

    c.bonus("damage", 2, on=c.me, until=When.ENCOUNTER, when=beside_the_beast)


@power("f773", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f773(c: Cast) -> None:
    """`p2473` is declared, so "the effect of that power" is a thing
    with a name: it blinds whoever is standing in the cloud as it forms.
    `PowerUsed` is announced above the body, which is the one window in
    which the immunity can be laid before the blinding lands.

    `c.immune` takes no gate, so the hold is kept to the turn the cloud
    goes up rather than the encounter -- wider than "that power" by any
    other blinding in the same turn, and narrower than a standing
    immunity would have been.
    """
    me = c.me

    def shelter(ev: Any) -> None:
        if ev.power != "p2473":
            return
        pet = c.beast()
        if pet is not None:
            c.immune(Condition.BLINDED, on=pet, until=When.EOT)

    c.watch(PowerUsed, shelter, on=me, until=When.ENCOUNTER,
            label=f"{c.ref} shelter")


@power("f776", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       dropped=("c.ignores_difficult(when=)", "c.reroll_attack(on=)"))
def f776(c: Cast) -> None:
    """The beast walks over rough ground.

    Two things dropped. The printed permission is only *while it shifts*
    and `c.ignores_difficult` takes a terrain kind rather than a gate, so
    the beast has it always -- wider than the card. And the reroll half
    is re-aimed: `p1450` is declared now, so the gap is no longer its
    name but that its reroll is of the caster's own roll and nothing
    turns it on somebody else's.
    """
    pet = c.beast()
    if pet is not None:
        c.ignores_difficult(on=pet, until=When.ENCOUNTER)


@power("f780", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f780(c: Cast) -> None:
    """An origin, a save bonus against charms, and the teleport rider.

    The saving-throw context carries the keywords of whatever is being
    saved against, so "against charm effects" is a real gate rather than a
    flat bonus that would be too good.

    The origin is printed as a swap and the companion's stat block prints
    one already, which is what `instead_of` is for.

    A trait with a `c.watch` rather than a declared trigger: the row
    holds standing modifiers as well, and declared `on=Trigger(...)`
    those would never be laid. "The same distance that you teleport" is
    `p1449`'s own 5, which is on the card rather than on the event.
    """
    pet = c.beast()
    if pet is None:
        return
    c.set_origin("fey", on=pet, until=When.ENCOUNTER, instead_of="natural")
    c.bonus(
        "save", 5, on=pet, until=When.ENCOUNTER,
        when=lambda ctx: Keyword.CHARM in ctx.get("keywords", ()),
    )

    def along(ev: Any) -> None:
        if ev.power != "p1449":
            return
        with_me = c.beast()
        if with_me is not None:
            c.teleport(5, who=with_me)

    c.watch(PowerUsed, along, on=c.me, until=When.ENCOUNTER,
            label=f"{c.ref} along")


@power("f781", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f781(c: Cast) -> None:
    """Fire resistance for the beast, scaling with the ranger's level."""
    pet = c.beast()
    if pet is not None:
        c.resist(5 + c.level // 2, DamageType.FIRE, on=pet, until=When.ENCOUNTER)


@power("f785", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f785(c: Cast) -> None:
    """A point of everything for the beast. No type word printed, so
    untyped, which is the one that stacks."""
    pet = c.beast()
    if pet is None:
        return
    for where in (AC, FORT, REF, WILL):
        c.bonus(where, 1, on=pet, until=When.ENCOUNTER)
