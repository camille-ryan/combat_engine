"""Theme powers and wild talents.

A theme power is an ordinary row. `cls` is the theme's alias ref -- `x7_918`
-- or the literal `wild talent`, for the same reason a racial power is keyed
by the race's ref: a printed name in that column would leak, and a word
spelled like a class would be dealt to every character of it.

Nothing selects these yet. `chargen.loadout` gives a character none of them,
which is the normal state of a row before the thing that picks it exists.
"""
