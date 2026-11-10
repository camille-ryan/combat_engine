"""Skill powers for one skill: `cls` is the skill, not a class.

Six rows, all Utility, at levels 2, 6 and 10. Every one of them is about
somebody else's hit point pool rather than the caster's -- a surge spent, a
second wind taken or handed back, a creature on the floor put back up -- so
the thing to get right in all six is **who**. Four print "one ally" or "you
or one ally", one prints "one dying creature", and none of them is the
caster by default, so every call here names its creature.

Four of the printed Effects read "the target **can** spend a healing surge",
which is `c.may` asked of the target: whose surge it is decides whether it
is worth spending.
"""

from __future__ import annotations

from combat_engine.engine import (
    ANY_CREATURE,
    ENCOUNTER,
    MINOR,
    ONE_ALLY,
    STANDARD,
    YOU_OR_ONE_ALLY,
    ActionType,
    Cast,
    Condition,
    Health,
    Keyword,
    Melee,
    Target,
    power,
)

#: The tally `c.second_wind` spends the use under, and so the ref
#: `c.restore_use` hands back.
SECOND_WIND = "second-wind"


def _ready_for_it(c: Cast, who: int) -> bool:
    """"Must be bloodied and have at least two healing surges remaining."

    The bloodied half is a `Target` field and the engine filters on it; the
    surge count is not, so it is asked here. Two, because the row spends
    one for nothing before any of them pays out.
    """
    health = c.world.get(who, Health)
    return health is not None and health.bloodied and health.surges >= 2


def _whoever_qualifies(c: Cast, reach: int) -> int | None:
    """The creature the printed target line allows, where the chooser's pick
    does not qualify.

    `Target` filters on side, count and the fields it has, so a row whose
    line narrows on something it has no field for may be handed somebody the
    card forbids. Redirecting rather than returning is the settled answer --
    returning throws the row away while somebody else in reach qualifies --
    and the pool here is the caster's own side, which is what the printed
    "you or one ally" reads.
    """
    who = c.target
    if who is not None and _ready_for_it(c, who) and c.distance(who) <= reach:
        return who
    return next(
        (
            f
            for f in (c.me, *c.allies())
            if _ready_for_it(c, f) and c.distance(f) <= reach
        ),
        None,
    )


@power(
    "p16520",
    level=2,
    cls="heal",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Melee(1),
    target=Target("team", 1, bloodied=True),
    keywords=[Keyword.HEALING],
)
def p16520(c: Cast) -> None:
    """Three surges at most and only the last two pay out: the first is lost
    for nothing, which is `c.spend_surge`, and then one or two are spent,
    which is `c.surge`.

    "One or two" is read as one and then an optional second rather than as
    two optional ones -- the printed line offers a count, not a refusal, and
    a target that spends none would be paying a surge for temporary hit
    points alone.

    The target line is "you or one ally", which is the `team` pool, with
    `bloodied=True` doing the half of the restriction the header can carry.
    The two-surge half has no field, so it is enforced in the body and the
    row redirects where the chooser's pick does not qualify.
    """
    who = _whoever_qualifies(c, 1)
    if who is None:
        return
    c.spend_surge(on=who)
    c.surge(on=who)
    if c.may("spend a second healing surge", who=who):
        c.surge(on=who)
    c.temp_hp(c.surge_value(of=who) // 2, on=who)


@power(
    "p9318",
    level=2,
    cls="heal",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=Target("any", 1, conditions=frozenset({Condition.DYING})),
    keywords=[Keyword.HEALING],
)
def p9318(c: Cast) -> None:
    """"One dying creature" is a `Target.conditions` line, so the engine
    filters the pool and the body has nobody to redirect to.

    `any` rather than `ally`: the printed word is "creature", and a dying
    enemy is a legal target of this however rarely anybody wants one.
    """
    if c.may("spend a healing surge", who=c.target):
        c.surge(on=c.target)


@power(
    "p11549",
    level=6,
    cls="heal",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Melee(1),
    target=ANY_CREATURE,
    todo=("c.immune(dtype=)",),
)
def p11549(c: Cast) -> None:
    """The whole printed Effect is an immunity nothing can be granted.

    **Re-pointed off `Defences.immune_keywords`, which names the wrong one
    of the two fields.** The printed word is *both* a `DamageType` and a
    `Keyword` here, and only one of the two is enforced: `Defences.immune`
    is read in `resolve.deal_damage`, twice, so damage of a type in that
    set does not land at all -- which is the bulk of what the printed
    sentence is for, the blow and the ongoing tick alike.
    `Defences.immune_keywords` is read only by `query.immune_to`, and
    nothing asks it when a keyword-tagged effect arrives, so a mod laid
    that way would refuse nothing while reporting the row finished.

    So the gap is a **door onto `Defences.immune`**, which is a bare
    `set[DamageType]` with no `Cast` verb either way: `c.immune` takes
    `Condition`s and `c.resist` writes the resistance dict next to it,
    undo and all, so the shape is already in the tree one field over.
    `c.ignore_resistance(immunity=)` is the attacker's side and not this.

    Still `todo=` rather than `dropped=`: the immunity *is* the whole
    Effect, so with no door the body does nothing. When one lands this
    becomes a `dropped=` row -- the non-damage half of "immune to poison",
    the conditions a poison power imposes, is `i3538p1`'s gap and is a
    second and smaller one. #1224.
    """


@power(
    "p11550",
    level=6,
    cls="heal",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=YOU_OR_ONE_ALLY,
    keywords=[Keyword.HEALING],
)
def p11550(c: Cast) -> None:
    """"You or one ally" is the `team` pool, which is the only honest way to
    declare a line printing both words."""
    if c.may("spend a healing surge", who=c.target):
        c.surge(on=c.target)


@power(
    "p9319",
    level=6,
    cls="heal",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Melee(1),
    target=ONE_ALLY,
)
def p9319(c: Cast) -> None:
    """"Without taking an action to do so" is `cost`, not a grant:
    `c.second_wind` is the one door to a second wind and carries what it was
    taken as, which printed feats read. `c.grant_action` would say the ally
    may take one later for a cheaper action, which is a different sentence.

    It returns False if the ally has already taken one this fight, which is
    the limit the printed rule carries rather than anything this row says.
    """
    if c.may("use its second wind", who=c.target):
        c.second_wind(on=c.target, cost=ActionType.NONE)


@power(
    "p9320",
    level=10,
    cls="heal",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Melee(1),
    target=ONE_ALLY,
)
def p9320(c: Cast) -> None:
    """"If he or she has already used it" is `c.restore_use`'s own return:
    it answers False when the row had not been spent, so the condition the
    card prints needs no gate of its own."""
    c.restore_use(SECOND_WIND, on=c.target)
