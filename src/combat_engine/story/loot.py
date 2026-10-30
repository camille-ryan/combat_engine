"""What a scene hands over, and what the party is carrying afterwards.

A module hands things to the party in its own prose -- an NPC offers a
consumable, a chapter's treasure line lists one each -- and before this
there was nowhere for one to go. Camille, playing 2026-10-29:

> *"It looks like we were given healing poultices. I think this is likely
> prose only. When something like this happens it should be added to
> inventory."*

So a scene may state `grants`, and what it grants lands on the sheets and
survives into the next scene the way hit points and surges already do.

## A grant names the module's word or the ref, and both resolve

The same dual shape `Objective.foes` takes, for the same reason. A
converted module writes what the page printed -- a name -- and the
tracked fixture cannot, because **a name must not enter a tracked file**.
So `find` takes either:

* the printed name as the page writes it, with or without a leading
  *one*/*a*/*the* and in the plural, resolved through `localization/`;
* an item ref such as `"i1551"`, used as-is.

The fixture uses the second form, which is the same instruction every
content author gets: you are shown the name beside the ref and you write
the ref.

**No example of the first form is written here**, and that is the point
rather than coyness: the first draft of this docstring illustrated it with
a real item's name and quoted the module's own sentence around it, which
is two leaks in the file that exists to explain the rule. Fourth time on
this branch. `leaks.py --modules` and `--cited` are what catch it.

## What this deliberately does not do

**Nothing spends one.** `#935` is explicit that using an item is the
larger question -- a consumable is a power with a charge, and whether a
story-granted item is the same kind of object as one `chargen` dealt is a
design call that wants answering before it is written. The engine already
has two representations and a poultice is neither: `components.Item` is a
held one-shot that lives and dies with a board, and `Magic` is a worn slot
with an enhancement bonus.

So this makes the poultice **visible and durable** and stops the prose
lying, which is the whole of what was asked. A count that nothing can
spend is honest; a count that silently vanished was not.
"""

from __future__ import annotations

from functools import lru_cache

from combat_engine.db import game, localisation

# `_singulars` rather than a second copy of it. A module asks for four of
# something and the compendium prints the item once, singular -- exactly
# the problem `cast_list` already solved for creature names, including the
# `les` -> `l` fault that cost 45 of 400 names. A copied guard is the thing
# that goes wrong in the copy, so this imports the one that is measured.
from .cast_list import _singulars


@lru_cache(maxsize=1)
def _by_name() -> dict[str, str]:
    """Printed item name -> item ref, lower-cased. Items only.

    First writer wins on a collision, the same call `cast_list._by_name`
    makes: a module naming a thing printed twice should hand over one of
    them rather than nothing at all.
    """
    names = localisation()
    out: dict[str, str] = {}
    for (ref,) in game().execute("SELECT ref FROM item"):
        word = ((names.get(ref) or {}).get("name") or "").strip().lower()
        if word and word not in out:
            out[word] = ref
    return out


@lru_cache(maxsize=1)
def _refs() -> frozenset[str]:
    """Every item ref, so a grant written as a ref can be checked."""
    return frozenset(ref for (ref,) in game().execute("SELECT ref FROM item"))


def find(word: str) -> str:
    """The item ref a grant means, or `""`.

    A ref if it is one, then the name as written, the singular, and the
    three leading words a module actually writes -- *one*, *a*, *the*.
    """
    raw = word.strip()
    if raw in _refs():
        return raw
    table = _by_name()
    low = raw.lower()
    for stem in (low, low.removeprefix("one "), low.removeprefix("a "),
                 low.removeprefix("the ")):
        for candidate in _singulars(stem):
            ref = table.get(candidate)
            if ref:
                return ref
    return ""


def hand_over(sheets: list, grants: tuple) -> list[str]:
    """Put a scene's grants on the sheets. Returns what to print.

    **Round-robin from the first sheet, and the rule is printed rather than
    assumed.** One poultice for a party of four is one character carrying
    it, and nothing here can yet spend it, so choosing an owner is the
    least information this can invent: a stash on `Party` would need a new
    save key, and giving everybody a copy would mint three items the page
    never printed.

    An unresolvable word is **reported, not dropped**. That is the clamp
    rule this component already follows -- a silent cap reads as "covered
    everything" when it did not -- and it is the whole fault this issue was
    filed about, so swallowing it here would be the same bug one layer
    down.
    """
    notes: list[str] = []
    if not sheets:
        return notes
    at = 0
    for grant in grants:
        ref = find(grant.what)
        if not ref:
            notes.append(
                f"the scene hands over {grant.count}x {grant.what!r} and no "
                "item ref matches it, so nothing was carried away"
            )
            continue
        for _ in range(grant.count):
            sheet = sheets[at % len(sheets)]
            sheet.carried[ref] = sheet.carried.get(ref, 0) + 1
            at += 1
        notes.append(f"carried away: {grant.count}x {ref}")
    return notes
