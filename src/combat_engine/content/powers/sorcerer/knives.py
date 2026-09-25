"""The one printed Requirement the sorcerer's weapon rows keep naming.

Six rows across five levels print "you must be wielding a dagger", and the
question is the same every time: what is in the main hand. Written once here
rather than six times, the way `fighter/grips.py` does it.

The chassis `chargen` derives for this class carries a mace, a crossbow and
an implement, so none of these six can be offered on the audit board -- they
report UNUSED, which is the requirement working rather than the row failing.
"""

from __future__ import annotations

from combat_engine.engine import Gear, World


def dagger(world: World, eid: int) -> bool:
    """"Requirement: You must be wielding a dagger"."""
    gear = world.get(eid, Gear)
    if gear is None or gear.main is None:
        return False
    return gear.main.group == "dagger" or gear.main.ref == "w:dagger"
