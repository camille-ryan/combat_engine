"""The three psionic class pages: battlemind, monk and psion.

Only the class-page rows. **The cards these pages print inline are already
in the tree under their own `p` refs** -- `powers/battlemind/level_0.py`,
`powers/monk/level_0.py` and `powers/psion/level_0.py` carry all fifteen of
them -- so nothing here re-declares one. A sub-option that reads "you gain
<card>" hands over the `p` ref that already exists.

Two of the three pages print the same power-point paragraph, and it is the
one thing on either page the engine cannot say.
`chargen.CLASSES[...].power_points` is already a column, so a character
*has* the points; what is missing is the spend -- `dsl.use(augment=)` --
which is the symbol eight earlier waves named and issue #170 tracks. Both
parent rows carry it as `todo=`, because without it there is nothing else in
them at all.

The other shape that recurs here is a **choice**, and it now has legs to
stand on. The monk prints five traditions, the psion three disciplines and
the battlemind four options; `chargen.BUILDS` carries one leg per option,
named for that option's own ref, so each sub-option row opens by asking
`c.build` whether this character took it. That is the *exclusivity* the
three pages print and that every one of these rows used to drop: taking
one option now takes the other four away.

The two parent rows are left holding nothing. Their whole printed content
was the word *one*, which the children's gates say between them, so both
are `out_of_combat=True` -- deliberately inert, in the sense
`docs/AUTHORING.md` gives the flag, rather than unwritten.

`chargen.loadout` deals a class every level 0 row it has, so `c.grant_row`
on a card the character already knows is a no-op in practice. It is still
what the printed sentence says, it adds no second copy to the menu, and it
is what will start mattering the day the legs exist.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    ENCOUNTER,
    NO_TARGET,
    PERSONAL,
    WILL,
    ActionType,
    Cast,
    DamageType,
    Keyword,
    Moved,
    When,
    power,
)
from combat_engine.engine.components import Defences

PSIONIC = [Keyword.PSIONIC]

#: The augment machinery, named the way the rest of the tree names it so
#: `todo.py` groups these two with the other fifty.
AUGMENT = ("dsl.use(augment=)",)

# -- battlemind -------------------------------------------------------------


@power(
    "cf:battlemind-f0",
    level=0,
    cls="battlemind",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=PSIONIC,
    todo=AUGMENT,
)
def battlemind_augment(c: Cast) -> None:
    """The whole feature is the power-point economy.

    The reservoir itself is data -- `chargen.CLASSES["battlemind"].power_points`
    is 2 -- and `c.points` and `c.spend_points` can read and drain it. What
    does not exist is the door a *use* goes through: nothing lets a player
    declare "this at-will, augmented by 2" before targets are chosen, which
    is the whole of the printed rule. Issue #170.
    """


@power(
    "cf:battlemind-f1",
    level=0,
    cls="battlemind",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=PSIONIC,
)
def battlemind_three_powers(c: Cast) -> None:
    """Three named level 0 rows, handed over.

    `chargen.loadout` already deals all three to every battlemind, so this
    is the printed sentence rather than the thing that makes it true. It is
    written anyway because the sentence is the feature: strip the class of
    its dealt rows and this is what puts them back.
    """
    for ref in ("p10438", "p10439", "p10440"):
        c.grant_row(ref, on=c.me, until=When.ENCOUNTER)


@power(
    "cf:battlemind-f2",
    level=0,
    cls="battlemind",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=PSIONIC,
    out_of_combat=True,
)
def battlemind_option(c: Cast) -> None:
    """The header of a four-way choice, and the choice is all it is.

    Its four children carry the content, and each of them now refuses
    itself on the three legs it is not for, which is the word *one* said
    where it can be read. Nothing is left for the parent to do.
    """


@power(
    "cf:battlemind-f2s0",
    level=0,
    cls="battlemind",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=PSIONIC,
)
def battlemind_option_resilience(c: Cast) -> None:
    """One of the four options, and its whole content is the card it names,
    which is already written in `powers/battlemind/level_0.py`."""
    if not c.build("f2s0"):
        return
    c.grant_row("p11155", on=c.me, until=When.ENCOUNTER)


@power(
    "cf:battlemind-f2s1",
    level=0,
    cls="battlemind",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=PSIONIC,
)
def battlemind_option_strike(c: Cast) -> None:
    if not c.build("f2s1"):
        return
    c.grant_row("p13024", on=c.me, until=When.ENCOUNTER)


@power(
    "cf:battlemind-f2s2",
    level=0,
    cls="battlemind",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=PSIONIC,
)
def battlemind_option_speed(c: Cast) -> None:
    if not c.build("f2s2"):
        return
    c.grant_row("p10441", on=c.me, until=When.ENCOUNTER)


@power(
    "cf:battlemind-f2s3",
    level=0,
    cls="battlemind",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=PSIONIC,
)
def battlemind_option_focus(c: Cast) -> None:
    if not c.build("f2s3"):
        return
    c.grant_row("p12418", on=c.me, until=When.ENCOUNTER)


# -- monk -------------------------------------------------------------------
#
# A tradition is one of the five level 0 cards plus one standing modifier.
# The cards are `FLURRIES` in `powers/monk/level_0.py` and are not touched
# here; only the modifier and the hand-over are.


@power(
    "cf:monk-f0s0",
    level=0,
    cls="monk",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=PSIONIC,
)
def monk_tradition_centred(c: Cast) -> None:
    """The hand-over, and only the hand-over.

    **The defence half belongs to `cf:monk-f0` and is not repeated here.**
    That row already lays this tradition's step of Fortitude -- it is the
    one tradition benefit the parent's page carries -- and an untyped bonus
    stacks, so writing it again is a silently doubled number rather than a
    visible duplicate. The parent carries what it carries; this row carries
    the card the parent explicitly does not assign.
    """
    if not c.build("f0s0"):
        return
    c.grant_row("p7448", on=c.me, until=When.ENCOUNTER)


@power(
    "cf:monk-f0s1",
    level=0,
    cls="monk",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ELEMENTAL, Keyword.FIRE, Keyword.PSIONIC],
)
def monk_tradition_wind(c: Cast) -> None:
    """"If you already have fire resistance equal to or higher than this,
    increase it by 2" is the printed collision rule, and it is written.

    **`c.resist` adds rather than taking the highest**, which is the
    opposite of the printed stacking rule for resistances -- so the delta
    is computed here and handed over, not the card's number. A monk already
    resisting 10 gains 2 and ends on 12; one resisting 3 gains 2 and ends
    on 5, which is "you gain resist 5" and not 8.
    """
    if not c.build("f0s1"):
        return
    held = c.world.get(c.me, Defences)
    standing = held.resist.get(DamageType.FIRE, 0) if held is not None else 0
    c.resist(2 if standing >= 5 else 5 - standing, DamageType.FIRE, on=c.me)
    c.grant_row("p16131", on=c.me, until=When.ENCOUNTER)


@power(
    "cf:monk-f0s2",
    level=0,
    cls="monk",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ELEMENTAL, Keyword.PSIONIC],
)
def monk_tradition_tide(c: Cast) -> None:
    """Two clauses about being shoved, and they need different tools.

    The first is a held modifier -- `c.resist_forced` shortens every push,
    pull and slide, wherever it comes from -- and the printed "an enemy" is
    not asked, because a forced move rides no attacker.

    The second waits for the move to finish, so it watches `Moved` and not
    `MoveStart`: the card says "after the forced movement is resolved", and
    on `MoveStart` nothing has happened yet. `Moved` carries `kind_` as a
    plain attribute, which is the only place the three forced kinds can be
    told from a walk.
    """
    if not c.build("f0s2"):
        return
    me = c.me
    c.grant_row("p16132", on=me, until=When.ENCOUNTER)
    c.resist_forced(1, on=me, until=When.ENCOUNTER)

    def shoved(ev: Moved) -> None:
        if ev.actor != me:
            return
        if getattr(ev, "kind_", "") not in ("push", "pull", "slide"):
            return
        c.shift(1)

    c.watch(Moved, shoved, until=When.ENCOUNTER, on=me, label="cf:monk-f0s2")


@power(
    "cf:monk-f0s3",
    level=0,
    cls="monk",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=PSIONIC,
)
def monk_tradition_iron(c: Cast) -> None:
    """`kind="shield"` because that is the word the card prints in front of
    "bonus", which also makes it not stack with a real shield -- the printed
    consequence, and the reason the word is not a guess.

    The gate is live rather than measured once: `c.wielding` is asked inside
    the modifier, so a monk that swaps to its fists loses the bonus for as
    long as they are what it is holding. That is what "while wielding"
    says, and it is normally *off* -- `chargen` arms a monk with
    `w:unarmed`, which is the one weapon this excludes.
    """
    if not c.build("f0s3"):
        return
    c.bonus(
        AC, 1, on=c.me, until=When.ENCOUNTER, kind="shield",
        when=lambda _ctx: not c.wielding("unarmed"),
    )
    c.grant_row("p13123", on=c.me, until=When.ENCOUNTER)


@power(
    "cf:monk-f0s4",
    level=0,
    cls="monk",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=PSIONIC,
)
def monk_tradition_stone(c: Cast) -> None:
    """Untyped: the card prints "+1 bonus" with no type word in front of it.
    The paragon steps are out of scope. `cf:monk-f0` lays a Fortitude step
    and no Will one, so unlike the first tradition this half is the child's
    to write."""
    if not c.build("f0s4"):
        return
    c.grant_row("p11207", on=c.me, until=When.ENCOUNTER)
    c.bonus(WILL, 1, on=c.me, until=When.ENCOUNTER)


@power(
    "cf:monk-f1",
    level=0,
    cls="monk",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=PSIONIC,
    todo=("spec.weapon_ref()",),
)
def monk_unarmed_strike(c: Cast) -> None:
    """The feature is a weapon, and a weapon is not something a body can
    make.

    Most of it is already true by data: `chargen.CLASSES["monk"].weapons`
    carries `w:unarmed`, a simple weapon in the unarmed group with a +3
    proficiency bonus and a d8, so every monk the tree deals is already
    swinging the printed thing. What is not there is the rest of the object
    -- the off-hand property, which `Weapon.properties` is empty for, and
    the free-hand requirement -- and the implement clause, which says a
    `i1775` enhances this weapon. None of those is a modifier: they are
    fields on a weapon row nothing declares.
    """


# -- psion ------------------------------------------------------------------


@power(
    "cf:psion-f0",
    level=0,
    cls="psion",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=PSIONIC,
    out_of_combat=True,
)
def psion_discipline(c: Cast) -> None:
    """"Choose one of these options", and the options are the children.
    Same shape as `cf:battlemind-f2`: the word *one* is the parent's whole
    content and each child says it now."""


@power(
    "cf:psion-f0s0",
    level=0,
    cls="psion",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.CONJURATION, Keyword.PSIONIC],
)
def psion_discipline_shaper(c: Cast) -> None:
    """One of the three disciplines; each hands over two cards, both of
    which are already written in `powers/psion/level_0.py`."""
    if not c.build("f0s0"):
        return
    for ref in ("p13300", "p13301"):
        c.grant_row(ref, on=c.me, until=When.ENCOUNTER)


@power(
    "cf:psion-f0s1",
    level=0,
    cls="psion",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=PSIONIC,
)
def psion_discipline_telekinetic(c: Cast) -> None:
    if not c.build("f0s1"):
        return
    for ref in ("p11267", "p11268"):
        c.grant_row(ref, on=c.me, until=When.ENCOUNTER)


@power(
    "cf:psion-f0s2",
    level=0,
    cls="psion",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=PSIONIC,
)
def psion_discipline_telepath(c: Cast) -> None:
    if not c.build("f0s2"):
        return
    for ref in ("p8224", "p8225"):
        c.grant_row(ref, on=c.me, until=When.ENCOUNTER)


@power(
    "cf:psion-f1",
    level=0,
    cls="psion",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=PSIONIC,
    todo=AUGMENT,
)
def psion_augment(c: Cast) -> None:
    """The same paragraph the battlemind prints, and the same gap.
    `chargen.CLASSES["psion"].power_points` is 2 and nothing can spend it on
    a use. Issue #170; see `cf:battlemind-f0`.
    """
