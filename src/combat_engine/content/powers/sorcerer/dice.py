"""Reading a die somebody else rolled.

Two rows -- one at level 2, one at level 6 -- bet on the half of the d20 an
ally's attack will land in. Both are **free** actions, and a free action is
offered in the `Window.AFTER` of the event it triggers on, while the whole
attack resolves inside the `AttackDeclared` emit. So "before the ally makes
his or her first attack roll" cannot be honoured: by the time either body
runs the die is down. The choice is still taken blind; the face is read back
off the log here.
"""

from __future__ import annotations

from combat_engine.engine import AttackDeclared, AttackRolled, Cast


def face_of(c: Cast, swinger: int | None) -> int | None:
    """The die that creature just rolled, newest first.

    The search stops at that creature's own `AttackDeclared` so a roll from
    an earlier round is never mistaken for this one.
    """
    for ev in reversed(c.world.bus.log):
        if isinstance(ev, AttackRolled) and (swinger is None or ev.attacker == swinger):
            return ev.natural
        if isinstance(ev, AttackDeclared) and ev.attacker == swinger:
            return None
    return None
