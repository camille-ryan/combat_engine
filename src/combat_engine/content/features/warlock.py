"""Warlock: the sub-options printed inside the class features.

`cf:warlock-f0` through `cf:warlock-f4` are in `features/strikers.py`, and
nothing here is a feature of its own: each row hangs off one of those.

**The pact, as a choice.** `cf:warlock-f1` is one feature with seven legs
printed under it, and each leg is a `-f1sN` ref. A leg names an at-will
the character simply *knows* and a boon that pays when a cursed enemy
falls. Only the first half is written here: the boons are already paid,
two of them by `cf:warlock-f1`'s own watch and two by rows of their own
(`p4311`, `p16254`), so arming any of them again would pay the printed
sentence twice. Granting the at-will is the half nothing else says --
`chargen.loadout` samples at-wills, so a warlock built here usually does
not have the one its leg says it always has. `cf:warlock-f0` grants its
card for that same reason.

All seven legs have an entry in `chargen.BUILDS["warlock"]` now and gate
on it with `c.build`. Three of them were written behind a gate no leg
answered and marked `todo=("chargen.BUILDS",)`; the legs landed, so the
marker came off and the bodies were already right.

**Ten of the refs in this batch are not here.** The importer mints a ref
for every card printed on the class page, and most of those cards already
have a compendium entry that is written -- a pact's at-will is printed in
both places, and so is the curse. Declaring the second printing would put
the same card in the menu twice. The skipped refs and the rows that
already carry them are in the report.
"""

from __future__ import annotations

from combat_engine.content.features.builds import on_leg
from combat_engine.content.features.strikers import extra_damage
from combat_engine.engine import (
    AT_WILL,
    CON,
    ENCOUNTER,
    FREE,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    SELF,
    STANDARD,
    WILL,
    ActionType,
    Attack,
    Cast,
    DamageType,
    Dropped,
    Keyword,
    Ranged,
    Trigger,
    When,
    cursed_by_me,
    power,
)

ARCANE_IMPLEMENT = [Keyword.ARCANE, Keyword.IMPLEMENT]

#: The row that lays the curse, and the label its extra damage is filed
#: under. A curse from anywhere else has to use the same one.
CURSE = "cf:warlock-f4"

_A_CURSED_ENEMY_FALLS = "an enemy under your curse drops to 0 hit points"


# -- the pacts ----------------------------------------------------------


@power(
    "cf:warlock-f1s0",
    level=0,
    cls="warlock",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
)
def warlock_f1s0(c: Cast) -> None:
    """This leg's boon is spent through a row, so the row is granted along
    with the at-will. Raising the tally it spends is `cf:warlock-f1`'s, and
    is not armed again here."""
    if not c.build("dark"):
        return
    c.grant_row("p3403")
    c.grant_row("p4311")


@power(
    "cf:warlock-f1s1",
    level=0,
    cls="warlock",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.ELEMENTAL],
    dropped=("c.deals(ref=)",),
)
def warlock_f1s1(c: Cast) -> None:
    """The affinity itself is `Build.element`, rolled once at chargen rather
    than after each rest -- nothing on a character survives a rest to be
    re-rolled -- and `c.element` reads the one the leg carries. This leg's
    boon is a row too, so it is granted rather than armed.

    The dropped clause is the substitution: on your own turn an arcane
    power's force, necrotic, poison or psychic damage may be dealt as the
    affinity's type instead. `c.deals` changes every type a creature deals
    rather than four named ones on one named row, so taking it would
    recolour the whole character.
    """
    if not c.build("elemental"):
        return
    c.grant_row("p16256")
    c.grant_row("p16254")


@power(
    "cf:warlock-f1s2",
    level=0,
    cls="warlock",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
)
def warlock_f1s2(c: Cast) -> None:
    """The at-will is granted; this leg's boon is one of the two
    `cf:warlock-f1` pays off its own watch, so nothing is armed here."""
    if not c.build("fey"):
        return
    c.grant_row("p1456")


@power(
    "cf:warlock-f1s3",
    level=0,
    cls="warlock",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
)
def warlock_f1s3(c: Cast) -> None:
    """As the leg above: the at-will is granted and the boon stays with
    `cf:warlock-f1`."""
    if not c.build("infernal"):
        return
    c.grant_row("p1458")


@power(
    "cf:warlock-f1s4",
    level=0,
    cls="warlock",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
    dropped=("c.fell_might()",),
)
def warlock_f1s4(c: Cast) -> None:
    """The at-will is granted; the boon is the clause that is dropped.

    That boon is a once-per-encounter charge, declared before the attack
    roll of whatever power it enhances, and nothing holds a resource
    across uses or lets a power be augmented from outside its own card.
    """
    if not c.build("sorcerer-king"):
        return
    c.grant_row("p12887")


@power(
    "cf:warlock-f1s5",
    level=0,
    cls="warlock",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
)
def warlock_f1s5(c: Cast) -> None:
    """Both halves are rows and both are written -- the at-will has a
    compendium entry and the boon is below -- and the leg that says which
    warlock has them now exists."""
    if not c.build("star"):
        return
    c.grant_row("p1457")
    c.grant_row("cf:warlock-f1c10")


@power(
    "cf:warlock-f1s6",
    level=0,
    cls="warlock",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
    dropped=("c.active_vestige()",),
)
def warlock_f1s6(c: Cast) -> None:
    """The leg exists; the choice *within* the leg does not.

    Which of the two remnants this warlock bargained with is active is
    picked after a rest and changed mid-fight by certain dailies, and the
    at-will and the boon both read it. Nothing holds that state, so the
    two rows are handed over and neither can tell which remnant it is
    speaking for.
    """
    if not c.build("vestige"):
        return
    c.grant_row("cf:warlock-f1c11")
    c.grant_row("cf:warlock-f1c12")


# -- the cards only a pact above prints ---------------------------------


@power(
    "cf:warlock-f1c10",
    level=1,
    cls="warlock",
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE],
    trigger=_A_CURSED_ENEMY_FALLS,
    on=Trigger(Dropped, cursed_by_me, _A_CURSED_ENEMY_FALLS),
    requires=on_leg("star"),
    requires_text="needs the pact that prints it",
    dropped=("c.bonus('d20')",),
)
def warlock_f1c10(c: Cast) -> None:
    """A bonus to one roll, kept until it is spent: `once=True` is exactly
    "if you don't use this bonus by the end of your turn, it is lost", and
    an untyped one stacks, which is the printed "cumulative".

    The printed Prerequisite is the pact, and it is a leg now, so it is
    asked in the header like the other boons'.

    One thing is dropped. The bonus is printed for **any** d20 -- a save,
    a skill check, an ability check -- and a modifier is laid against one
    named roll, so the attack roll is the one it is laid against; three
    drops therefore buy three single attack rolls rather than one at +3.
    """
    c.bonus("attack", 1, until=When.EONT, on=c.me, once=True)


@power(
    "cf:warlock-f1c11",
    level=1,
    cls="warlock",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(CON, vs=WILL),
    dropped=("c.curse_damage()", "c.active_vestige()"),
)
def warlock_f1c11(c: Cast) -> None:
    """The one at-will that moves the curse around: it lands on the target
    or on somebody standing near it.

    "Within the target's line of sight" is the target's question and
    `c.can_see` asks the caster's, so distance is what is checked. Placing
    the curse has to lay its extra damage too -- `c.curse` only sets the
    state -- so the rider `cf:warlock-f4` arms is armed here under the same
    label, which is what a curse from any second source needs.

    Two clauses are dropped. A creature already cursed takes the curse's
    extra damage instead of the target, which wants that damage payable on
    demand rather than on the next hit; and the remnant the warlock is
    bargaining with adds a rider of its own to this card, which wants the
    active one to be readable.
    """
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.damage("1d6", c.con_mod, dtype=DamageType.PSYCHIC)
    near = [victim, *(e for e in c.within(3, of=victim, side="enemy") if e != victim)]
    pool = sorted(e for e in near if not c.cursed(on=e))
    pick = c.choose(pool, f"{c.ref}: who the curse settles on") if pool else None
    if pick is None:
        return
    c.curse(on=pick)
    extra_damage(c, "1d6", applies=lambda t: t == pick, label=CURSE)


@power(
    "cf:warlock-f1c12",
    level=1,
    cls="warlock",
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE],
    requires=on_leg("vestige"),
    requires_text="needs the pact that prints it",
    todo=("c.active_vestige()",),
)
def warlock_f1c12(c: Cast) -> None:
    """One row holding one boon per remnant, and which one pays is whichever
    is active. Both of the two printed here are sayable on their own -- an
    adjacent ally's defences, or the curse's attack bonus -- but nothing
    says which of them fires, and a row that paid both would be twice the
    card.
    """
