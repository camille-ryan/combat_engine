"""Skill powers: utility powers a character takes for being trained.

One module per skill, which is also how they partition for authoring --
no two files share a ref.

**`cls` is the skill, not a class**, which is `#999`'s import decision and
the only thing that makes one of these identifiable at all: the compendium
gives them no category of their own and no empty class. `chargen.loadout`
selects them by exactly that, and `races/` already holds the precedent for a
`cls` that is not a class.

All 134 are **Utility** and print at level 2, 6 or 10, which is
`chargen.UTILITY_GAINS` exactly. A character may take one in place of the
class utility it would have gained, if it is trained in the skill and the
power is at or below that level -- the printed rule is quoted in full on
`#1162` and implemented in `loadout`. `#1163` is the block of rows.
"""

from __future__ import annotations
