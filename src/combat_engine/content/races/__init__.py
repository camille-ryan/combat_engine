"""Racial powers: the rows a race grants rather than a class.

They are ordinary `@power` rows and need no machinery of their own. What
marks them is `cls`, which holds a **race** ref -- `r1`, `r33` -- the way a
class power's holds `fighter`; the compendium files them in the same column.

Most are Personal, most are encounter, and a good half are the triggered
kind: `action=ActionType.NONE` with a declared `on=`, which is what "No
Action" prints as.
"""
