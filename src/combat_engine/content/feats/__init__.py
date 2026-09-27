"""Feats: the small every-other-level options.

Almost all of them are traits -- `action=ActionType.NONE` with no trigger,
armed once at the start of a fight -- and the rest answer something that
happens, usually another row being used. Either way a feat is an ordinary
`@power` row and needs no machinery of its own, which is why there is no
`Feat` type anywhere in the engine.

**The prerequisite is not written here.** It is a structured gate on the
`feat` table and `chargen.meets` enforces it when the character is built;
`Power.requires` is the wrong tool, because it is asked mid-fight of a
creature on a board and "you must be a fighter" does not change between
rounds. What is written here is the Benefit.

Filed by the class a feat's prerequisite names, mirroring
`content/powers/<class>/`, with `general.py` for the ungated ones and
`race.py` for those waiting on a race.
"""
