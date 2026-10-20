"""The class-page features whose fork is a build leg rather than a score.

Three classes print a feature that is a *choice between named options* and
not a choice between abilities, so each needed a leg of its own in
`chargen.BUILDS` before `c.build(...)` had anything to answer. `on_leg` is
the same question asked of `requires=`, which gets `(world, eid)` and no
`Cast` -- and which is what makes `chargen.build_for` field the row on the
leg it belongs to instead of the class's first.

`chargen.loadout` hands a character **every** level 0 row its class has, so
a feature reading "you gain <power>" is a no-op: the character already has
it. Where the printed feature is one of a mutually exclusive set, the row
therefore takes the power *away* from the legs that did not choose it,
which is the only way the exclusivity can be true. The rangers' shared
`kind="class-option"` is the same trick in the modifier's language.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    ENCOUNTER,
    NO_TARGET,
    PERSONAL,
    ActionType,
    Cast,
    Gear,
    Keyword,
    Usage,
    When,
    World,
    get,
    power,
)
from combat_engine.engine.query import on_build


def on_leg(name: str):  # noqa: ANN201
    """A `requires=` gate reading one leg of a class's fork.

    **One line over `query.on_build`, which is the same question `c.build`
    asks.** It used to read `Build.choices` here, and that copy was the bug:
    six feats hand a character another class's option with `c.set_build`, and
    the five options gated in the *header* -- swordmage's three and invoker's
    two -- would have gone on refusing themselves while the nine gated in
    their bodies worked. A row that refuses itself after being handed over
    looks like the granting verb is broken.
    """

    def check(world: World, eid: int) -> bool:
        return on_build(world, eid, name)

    return check


# -- a feature's options, each beside the leg its own gate reads ------------
#
# **Written out rather than derived from the ref**, because the two halves
# of the tree disagree: nine options gate on their ref tail and five gate on
# a named leg. See `another_legs_option`.

#: `cf:ardent-f0`'s two, gating in their bodies.
ARDENT_F0_OPTIONS = {"cf:ardent-f0s1": "f0s1", "cf:ardent-f0s2": "f0s2"}

#: `cf:psion-f0`'s three, gating in their bodies.
PSION_F0_OPTIONS = {
    "cf:psion-f0s0": "f0s0",
    "cf:psion-f0s1": "f0s1",
    "cf:psion-f0s2": "f0s2",
}

#: `cf:battlemind-f2`'s four, gating in their bodies.
BATTLEMIND_F2_OPTIONS = {
    "cf:battlemind-f2s0": "f2s0",
    "cf:battlemind-f2s1": "f2s1",
    "cf:battlemind-f2s2": "f2s2",
    "cf:battlemind-f2s3": "f2s3",
}

#: `cf:swordmage-f1`'s three, gating in their **headers** on named legs.
SWORDMAGE_F1_OPTIONS = {
    "cf:swordmage-f1s0": "assault",
    "cf:swordmage-f1s1": "ensnarement",
    "cf:swordmage-f1s2": "shielding",
}

#: `cf:invoker-f1`'s two, also header-gated on named legs. The page prints
#: three covenants and `s1` is not declared, so this is the pair that is.
INVOKER_F1_OPTIONS = {
    "cf:invoker-f1s0": "malediction",
    "cf:invoker-f1s2": "wrath",
}


def another_legs_option(
    c: Cast, options: dict[str, str], *, usage: Usage, uses: int = 1
) -> str:
    """"Choose one of <a feature>'s options", for a character of another class.

    Three steps, and the middle one is the half that did not exist until
    `c.set_build`. `c.borrow_row(among=...)` picks one of the named set and
    hands it over; `c.set_build` stands the taker on that option's own leg,
    so the row it was just handed does not refuse itself on its first line;
    the option's body then does whatever its feature does.

    **The leg is written out per option rather than derived from the ref**,
    and that is not laziness. Nine of the fourteen options gate on their ref
    tail -- `cf:psion-f0s0` wants `"f0s0"` -- but swordmage's three and
    invoker's two gate on *named* legs, `assault`, `ensnarement`,
    `shielding`, `malediction`, `wrath`. A `ref.rsplit("-")[-1]` reads those
    five as `f1s0`/`f1s1`/`f1s2`, which is a leg nobody stands on, and the
    granted row would have gone on refusing itself while looking written.
    `drivers.another_legs_option` asserts every pair here against the
    option's own gate, so a drifted pair is red rather than silent.

    Scoped to the encounter, like the grant itself: an extra leg that
    outlasted the fight would hand the taker everything else printed on it,
    which is #548's trap.

    Returns the ref taken, or `""` when every option is already known --
    which is what happens if a member of the class takes the feat, and is
    the right answer rather than an error.
    """
    taken = c.borrow_row(
        among=tuple(options), usage=usage, attacks=False,
        uses=uses, until=When.ENCOUNTER,
    )
    if taken:
        c.set_build(options[taken], until=When.ENCOUNTER)
    return taken


def stand_on_another_leg(
    c: Cast, legs: dict[str, str], *, instead: bool = False
) -> str:
    """"Gain a second <option>", or "replace yours with another".

    The **own-class** half of `another_legs_option`, and it has to be a
    different verb rather than the same one. `c.borrow_row` drops any option
    the character already knows, and `chargen.loadout` deals a class *every*
    level 0 row it has -- so a psion knows all three focus rows and an
    invoker knows both covenants. Nothing is left to hand over, and both
    rows audited **SILENT** written the other way: they fired 48 times and
    did nothing, because the pool was empty every time. Measured, not
    guessed.

    Which is the right reading of the cards anyway. "Choose and gain a
    `cf:psion-f0` other than one you already possess" does not give a
    psion a row it lacks; it gives a *leg* it is not standing on, and the
    rows were always there. So the pick is over legs and the only thing that
    moves is the word `c.build` answers.

    `instead` is the replacing shape -- one covenant manifestation for
    another -- and displaces whichever leg the character is on now, found by
    asking, because nothing records it beyond the answer itself.

    **Idempotent within an encounter, which is not decoration.** These are
    `action=NONE` traits, so `turns.arm_traits` runs them once per fight --
    but run a second time, `instead` displaced the leg the *first* run had
    just granted and left the character on **no** covenant at all. Measured:
    `malediction -> wrath -> nothing`, four effects where there should be
    two. `audit.board` arms every such row and a driver calling the body
    then makes it twice, which is how it showed up; a once-per-encounter
    row that cannot survive being run twice is fragile either way.

    Returns the leg taken, `""` if there is nothing to move to or if this
    row has already moved it.
    """
    if any(f"{c.ref} build:" in e.label for e in c.world.effects.of(c.me)):
        return ""
    mine = [leg for leg in legs.values() if c.build(leg)]
    spare = [leg for leg in legs.values() if leg not in mine]
    if not spare:
        return ""
    taken = c.choose(sorted(spare), f"{c.ref}: which one")
    if not taken:
        return ""
    c.set_build(
        taken, until=When.ENCOUNTER,
        instead_of=(mine[0] if instead and mine else ""),
    )
    return taken


#: The two weapon groups the fourth rogue tactic trains in. Lives here
#: rather than beside the row that reads it in `features/strikers.py`,
#: because that file imports this one and not the other way round.
RUFFIAN_GROUPS = ("club", "mace")


def _rattling_row(ctx: dict[str, Any]) -> bool:
    """"An attack that has the rattling keyword", as a modifier gate."""
    declared = get(ctx.get("power") or "")
    return declared is not None and Keyword.RATTLING in declared.keywords


@power(
    "cf:rogue-tactic-club",
    level=0,
    cls="rogue",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
    requires=on_leg("cutthroat"),
    requires_text="needs the tactic trained in the heavier groups",
)
def rogue_tactic_club(c: Cast) -> None:
    """The fourth of the four printed tactics, and the only one that changes
    what the rogue may swing.

    Two of its three clauses are not here because they are not modifiers.
    The proficiency is the leg's own weapons in `chargen.BUILDS["rogue"]`,
    and letting those groups stand in for the light blade `cf:rogue-scoundrel-f4`
    wants is in that row's `requires` gate, which is the one place the
    question is asked.

    What is left is the rider. It is a damage rider -- "add your Strength
    modifier to the damage roll" -- and it is conditional on *delivering*
    the attack with one of the two groups, not merely on having the
    tactic: the printed line says "if you use a club or a mace to deliver
    an attack that has the rattling keyword". The keyword alone was the
    whole gate, which paid the rider off a light blade.
    """
    me, world = c.me, c.world

    def rider(ctx: dict[str, Any]) -> bool:
        if not _rattling_row(ctx):
            return False
        gear = world.get(me, Gear)
        held = gear.main if gear is not None else None
        return held is not None and held.group in RUFFIAN_GROUPS

    if c.str_mod > 0:
        c.bonus(
            "damage", c.str_mod, until=When.ENCOUNTER, on=me, kind="untyped", when=rider
        )


#: The row the shield leader feature hands over. It is a real level 0
#: warlord row, so every warlord `chargen` deals already knows it.
_RALLY = "p10887"


@power(
    "cf:warlord-marshal-f1",
    level=0,
    cls="warlord",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def warlord_shield(c: Cast) -> None:
    """One of the three mutually exclusive leader features, and the only one
    whose content is a power rather than prose.

    Its other half is proficiency with a shield. The warlord chassis already
    carries one -- `CLASSES["warlord"].shield` is a light shield -- so there
    is nothing for this to grant and nothing is invented; proficiency is not
    a thing the engine models either way.

    No `requires=`: the row runs for every warlord, because enforcing the
    exclusivity is the half that has to happen on the *other* legs. A
    warlord that did not take this one loses the row it hands out, which it
    was only holding because `loadout` deals a class every level 0 row it
    has.
    """
    if c.build("shielding"):
        c.grant_row(_RALLY)
    else:
        # `c.forbid` follows `c.target`, and a trait has none -- without
        # `on=` this took the row away from nobody, so every warlord kept
        # it whichever leg it was on and the exclusivity was never real.
        c.forbid(_RALLY, until=When.ENCOUNTER, on=c.me)
