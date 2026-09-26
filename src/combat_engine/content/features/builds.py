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
    Build,
    Cast,
    Keyword,
    When,
    World,
    get,
    power,
)


def on_leg(name: str):  # noqa: ANN201
    """A `requires=` gate reading one leg of a class's fork."""

    def check(world: World, eid: int) -> bool:
        held = world.get(eid, Build)
        return held is not None and name in held.choices

    return check


def _rattling_row(ctx: dict[str, Any]) -> bool:
    """"Attacks with the rattling keyword", as a modifier gate."""
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
    requires=on_leg("ruffian"),
    requires_text="needs the tactic trained in the heavier groups",
)
def rogue_tactic_club(c: Cast) -> None:
    """The fourth of the four printed tactics, and the only one that changes
    what the rogue may swing.

    Two of its three clauses are not here because they are not modifiers.
    The proficiency is the leg's own weapons in `chargen.BUILDS["rogue"]`,
    and letting those groups stand in for the light blade `cf:rogue-bonus`
    wants is in that row's `requires` gate, which is the one place the
    question is asked.

    What is left is the rider, and it is a damage rider: an attack modifier
    keyed off Strength on a Dexterity class would be a reading the rest of
    the page does not support. Untyped, because a class feature is.
    """
    if c.str_mod > 0:
        c.bonus(
            "damage",
            c.str_mod,
            until=When.ENCOUNTER,
            on=c.me,
            kind="untyped",
            when=_rattling_row,
        )


#: The row the shield leader feature hands over. It is a real level 0
#: warlord row, so every warlord `chargen` deals already knows it.
_RALLY = "p10887"


@power(
    "cf:warlord-shield",
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
        c.forbid(_RALLY, until=When.ENCOUNTER)
