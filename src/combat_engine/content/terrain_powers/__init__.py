"""Terrain powers: rows the board owns, that any creature by them may use.

**A package rather than one module, since `#1123`.** It was a single
top-level file, and `content/__init__.py` carried an explicit import line
for it with a note saying *"inventing a `terrain_powers/` package for a
module would be the wrong shape"*. That was right for two rows and wrong
for twenty-four: all 24 printed rows in one file cannot be written in
parallel, and a tree-wide `ruff --fix` by one author has destroyed
another's work in this repo before. So the rows partition by file, which is
the unit this project's delegation rule is written in.

`batch_a` holds the two rows `#980` and `#1105`-`#1107` were built around
and keeps the full account of the mechanism -- read that file first. The
other batches are the remaining printed rows, split by ref only; there is
no meaning in which batch a row landed in.

`_load("terrain_powers")` walks this package now, so a new batch module
needs no line anywhere: it is found by being here. That is the thing the
old single-file arrangement could not do, and the reason the explicit
import is gone.
"""
