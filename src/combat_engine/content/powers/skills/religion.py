"""Religion skill powers: seven utilities about surges, saves and undead.

`cls` is the skill, which is what makes a skill power identifiable at all --
see the package docstring. All seven are Utility at level 2, 6 or 10.

Two of them print a zone that stays centred on the caster, which is an aura
and gets no mechanism of its own; three of them are about a healing surge,
from three different ends -- spending somebody else's, spending your own for
no hit points, and answering an ally who spent one.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    ANY_CREATURE,
    DAILY,
    ENCOUNTER,
    FORT,
    INTERRUPT,
    MINOR,
    NO_TARGET,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    STANDARD,
    WILL,
    Cast,
    CloseBurst,
    DamageType,
    Hit,
    Keyword,
    Melee,
    SurgeSpent,
    Trigger,
    TurnEnd,
    When,
    World,
    ally_within,
    get,
    power,
)
from combat_engine.engine.dsl import keywords_of
from combat_engine.engine.query import holding

#: The implement a holy symbol is, by ref. `chargen` deals one to the two
#: classes whose pages print it, and `query.holding` matches a ref as well
#: as a group -- which is the only handle a row obeying the naming rule has.
SYMBOL = "w:holy-symbol"


@power(
    "p9335",
    level=2,
    cls="religion",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ANY_CREATURE,
    keywords=[Keyword.HEALING],
)
def p9335(c: Cast) -> None:
    """A printed "can", so the target is asked -- and asked of the target,
    because whose surge it is decides whether it is worth spending."""
    who = c.target
    if who is None:
        return
    if c.may("spend a healing surge", who=who):
        c.surge(on=who)


def _holds_a_symbol(world: World, eid: int) -> bool:
    """The printed Requirement, as much of it as is on the board.

    "Wearing or holding" -- holding is the half this engine carries, and
    the classes whose pages print this power are dealt the implement, so
    the gate is met rather than permanently false. Asked as a `requires=`
    and not in the body because this is an action rather than a trait: a
    trait gated here would be refused once at arming and never armed again.
    """
    return bool(holding(world, eid, SYMBOL))


@power(
    "p11591",
    level=6,
    cls="religion",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(1),
    target=NO_TARGET,
    keywords=[Keyword.ZONE],
    requires=_holds_a_symbol,
    requires_text="you must be wearing or holding a holy symbol",
)
def p11591(c: Cast) -> None:
    """"The zone moves with you, remaining centered on you" is an aura, and
    `Zones.refresh` redraws its footprint and diffs who is standing in it
    every time anybody moves -- so the arriving and leaving halves of the
    bonus are carried for free.

    `c.grants_in` is what makes the bonus belong to the geometry rather
    than to a clock: it ends when an ally leaves, which a plain
    `c.bonus(until=...)` cannot say. `side="ally"` leaves the caster out,
    which is the printed word.

    The gate reads `attacker` off the defence context, which is where
    "against undead creatures" lives: the defence is totalled per swing
    with the attacker in hand.
    """
    aura = c.aura(1, until=When.EONT)

    def undead_swing(ctx: dict[str, Any]) -> bool:
        swinging = ctx.get("attacker")
        return swinging is not None and c.is_kind("undead", on=swinging)

    for each in (AC, FORT, REF, WILL):
        c.grants_in(
            aura, each, 2, side="ally", kind="power", when=undead_swing
        )

    def shoved_at_the_end(ev: TurnEnd) -> None:
        if ev.actor == c.me or not c.is_kind("undead", on=ev.actor):
            return
        if c.in_my_aura(ev.actor, label=c.ref):
            c.push(1, on=ev.actor)

    c.watch(TurnEnd, shoved_at_the_end, until=When.EONT, label=c.ref)


@power(
    "p12166",
    level=6,
    cls="religion",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def p12166(c: Cast) -> None:
    """`c.spend_surge` is the verb for "spends a surge and gains nothing for
    it", so the no-hit-points half is the call rather than a subtraction.
    The worth is read before the spend, and the temporary hit points only
    land if there was a surge to pay with.
    """
    worth = c.surge_value()
    if c.spend_surge(on=c.me):
        c.temp_hp(worth, on=c.me)


_STRUCK = "you are hit by a necrotic or a radiant attack"


def _by_necrotic_or_radiant(world: World, me: int, ev: Hit) -> bool:
    """Which sort of attack landed, read off the row that swung.

    The damage has not been rolled when a `Hit` is announced, so the
    question is the attack's keywords and not a damage type on the event.
    `keywords_of` rather than the header tuple, because a feat may have
    granted one.
    """
    if getattr(ev, "target", None) != me:
        return False
    row = get(str(getattr(ev, "power", "")))
    if row is None:
        return False
    # Guarded rather than passed through: `keywords_of` wants an eid and a
    # `Hit` with no attacker would hand it `None`. The gate is "who swung",
    # so no attacker means there is nothing to ask about.
    swinging = getattr(ev, "attacker", None)
    if not isinstance(swinging, int):
        return False
    return bool(
        keywords_of(world, swinging, row)
        & {Keyword.NECROTIC, Keyword.RADIANT}
    )


@power(
    "p9336",
    level=6,
    cls="religion",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    trigger=_STRUCK,
    on=Trigger(Hit, _by_necrotic_or_radiant, _STRUCK),
)
def p9336(c: Cast) -> None:
    """An interrupt on the `Hit` is in place before the body that rolled it
    deals its damage, so the resistance covers the triggering attack as
    well as the rest of the window.

    Two types rather than one untyped resistance: an untyped one would
    shrug off every blow, which is a much larger sentence than the card.
    """
    shrugged = 5 + c.int_mod
    for dtype in (DamageType.NECROTIC, DamageType.RADIANT):
        c.resist(shrugged, dtype, on=c.me, until=When.EONT)


_ALLY_SURGED = "an ally within 5 squares of you spends a healing surge"


@power(
    "p12171",
    level=10,
    cls="religion",
    usage=ENCOUNTER,
    action=REACTION,
    reach=CloseBurst(5),
    target=NO_TARGET,
    trigger=_ALLY_SURGED,
    on=Trigger(SurgeSpent, ally_within(5), _ALLY_SURGED),
)
def p12171(c: Cast) -> None:
    """The triggering ally is read off the event rather than off a target
    line, which the card does not print: `SurgeSpent.actor` is whoever paid.

    `ally_within` leaves the caster out, which is the printed "an ally".
    The Level 21 line is paragon and out of scope.
    """
    who = getattr(c.trigger, "actor", None)
    if who is not None:
        c.temp_hp(c.roll("3d6"), on=who)


@power(
    "p3684",
    level=10,
    cls="religion",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(1),
    target=NO_TARGET,
    keywords=[Keyword.ZONE],
)
def p3684(c: Cast) -> None:
    """The same aura shape as `p11591`, with the printed sustain on it, and
    an ungated bonus: this one names no sort of enemy.
    """
    aura = c.aura(1, until=When.EONT, sustain=MINOR)
    c.grants_in(aura, "attack", 1, side="ally", kind="power")


@power(
    "p9337",
    level=10,
    cls="religion",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def p9337(c: Cast) -> None:
    """"The next saving throw" is `once=True`, which `c.bonus` spends on the
    `SavingThrow` it is read at rather than on the owner's next swing.

    A plain "+5 bonus" with no type word in front of it is untyped, so no
    `kind=`.
    """
    c.bonus("save", 5, on=c.me, until=When.SONT, once=True)
