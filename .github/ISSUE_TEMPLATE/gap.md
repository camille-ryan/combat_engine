---
name: A gap the engine cannot express
about: A printed rule that no row can currently say
labels: engine
---

<!-- One gap, one component. If it spans two, file two. -->

## What cannot be said

The printed sentence, and the symbol a row would want for it —
`c.something(arg=)`. Symbols, never a name from the book.

## What it blocks

Which rows, **counted**. `uv run scripts/blocked.py --refs 'c.something()'`
gives the list; say how many and name two or three.

## Why it is not already there

What you checked. `grep -n "def something" src/combat_engine/engine/cast.py`
and `uv run scripts/vocab.py --brief` — about two thirds of gaps filed here
have turned out to already exist under a different name.

## Blast radius

What else would move if this landed. If you do not know, say so.
