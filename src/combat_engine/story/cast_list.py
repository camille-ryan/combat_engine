"""Turning *four of something goblin-ish* into refs that are written and play.

The module says what the fight is; this picks the creatures. Three tiers, and
which one answers is the whole story of how much work a module needs. #790.

## 1. The name, which for a 4e module is almost the whole answer

`localization/names.json` maps a ref to its printed name. Inverted and restricted
to the `monster` table it maps a name back to a ref, and a module written for
this edition names creatures this edition has.

Measured against the module now in `modules/`: **39 of its 39 high-confidence
creature names resolve to refs that pass `loader.usable` with no missing
abilities** -- every one fieldable today with no new content. 37 of the 39 are
heroic tier; the two paragon ones are deferred and said so out loud, because
the band does not cross a tier boundary.

So for a 4e module this tier does the work and the rest of the file is the
exception path. That is the opposite of how the component was first designed,
and the measurement is why.

## 2. The theme, for a creature we do not have

Matched on what the database already knows about each creature -- its
`keywords`, `kind` and `origin` columns -- against the words the module gave.
Ranked by how many words overlap, then by how close the XP is to one slot's
share, then by level distance.

## 3. The shape, dressed as the theme

Nothing matched, so take a creature of the right **role and rank** and bend it:
`story/reflavour.py` adds the words, retypes the damage and sets resistances.
This is the tier every module from every other edition lands in, and the reason
reflavouring exists at all.

## The budget binds in all three

A module can say *twenty goblins* and mean it narratively. Twenty standard
creatures against a level-2 party is not a fight, and `_compose` already learnt
this the hard way -- **11 of 24 level-10 draws came out over budget** when the
draw took four creatures whatever their rank. So the count is clamped to the
scene's share of `story.budget`, using the same fit rule, and **a clamp is
printed**: `scripts/CLAUDE.md` is explicit that a silent cap reads as
"covered everything" when it did not.

Minions are the case that makes this worth stating: they cost a quarter of a
standard, so a module asking for eight of them is asking for two standards'
worth and the clamp should not fire at all.
"""

from __future__ import annotations

import json
from functools import lru_cache
from random import Random

from combat_engine.content import loader
from combat_engine.db import game, localisation

from . import BAND, SIDE, WORTH, budget
from .module import FoeSpec, Scene
from .reflavour import Dressed, Reflavour, themed

#: How far past the budget a scene may go before a creature is skipped. The
#: same 10% `_compose` allows, for the same reason: the last creature taken is
#: always the one that breaks the ceiling, so some slack or nothing fits.
OVER = 1.1

#: The tiers, so a report can say which answered.
BY_NAME, BY_THEME, BY_SHAPE = "name", "theme", "shape"


@lru_cache(maxsize=1)
def _by_name() -> dict[str, str]:
    """Printed name -> monster ref, lower-cased.

    Monsters only. The localisation holds 37,058 entries across every
    namespace, and a module naming a creature must not resolve to a feat that
    happens to share the word.

    First writer wins on a collision, which is deliberate rather than lazy: the
    alternative is dropping both, and a module that names a creature printed
    twice should field one of them rather than fall through to the theme tier.
    Collisions are reported by `--validate`, not swallowed here.
    """
    names = localisation()
    out: dict[str, str] = {}
    for row in game().execute("SELECT ref FROM monster"):
        entry = names.get(row[0]) or {}
        word = (entry.get("name") or "").strip().lower()
        if word and word not in out:
            out[word] = row[0]
    return out


def _singulars(word: str) -> list[str]:
    """Every singular a plural might have come from, most likely first.

    Published adventures say *four goblin cutters*; the compendium prints the
    creature once, singular.

    **All the candidates, not the first rule that matches**, and that is a fix
    rather than a flourish. Taking the first match applied the `es` rule to
    anything ending in it, so a name ending in `le` pluralised to `les` came
    back as `...l` -- measured, 355 of 400 plurals resolved and the misses were
    that shape. Trying each and keeping whichever the table actually holds
    costs three dictionary lookups.
    """
    word = word.strip().lower()
    out = [word]
    if word.endswith("ies") and len(word) > 4:
        out.append(word[:-3] + "y")
    if word.endswith("es") and len(word) > 4:
        out.append(word[:-2])
    if word.endswith("s") and len(word) > 3:
        out.append(word[:-1])
    return out


def find_by_name(name: str) -> str:
    """The ref a module's own word for a creature means, or `""`.

    Tries the name as written, then the singular, then with a leading article
    stripped -- the three shapes a module actually writes.
    """
    table = _by_name()
    raw = name.strip().lower()
    for word in (raw, raw.removeprefix("the "), raw.removeprefix("a ")):
        for candidate in _singulars(word):
            ref = table.get(candidate)
            if ref:
                return ref
    return ""


@lru_cache(maxsize=4096)
def _facts(ref: str) -> tuple[int, int, frozenset[str], str, str]:
    """`(xp, level, words, role, rank)` for one creature."""
    row = game().execute(
        "SELECT xp, level, keywords, kind, origin, role, rank "
        "FROM monster WHERE ref = ?", (ref,),
    ).fetchone()
    if row is None:
        return 0, 0, frozenset(), "", ""
    words = {w.strip("() ").lower() for w in json.loads(row[2] or "[]")}
    words |= {(row[3] or "").strip("() ").lower(), (row[4] or "").strip().lower()}
    words.discard("")
    return (
        int(row[0] or 0), int(row[1] or 0), frozenset(words),
        (row[5] or "").strip().lower(), (row[6] or "standard").strip().lower(),
    )


def usable(ref: str) -> bool:
    """Written, offerable, and not defective. `loader.pick`'s own gate.

    `loader.spawn` does **not** check this -- the gate lives in `pick` -- so a
    tier that reaches past `pick` has to ask for itself or it will field a
    creature whose abilities do not exist.
    """
    try:
        return bool(loader.usable(ref) and not loader.load(ref).missing)
    except KeyError:
        return False


def in_tier(ref: str, party_level: int) -> bool:
    """Is this creature inside the party's tier?

    Camille's call, 2026-10-15, and `loader.pick` clamps its band the same way:
    heroic means monsters 1-10 and a paragon creature defers wholesale rather
    than being fielded three levels out of its depth.
    """
    level = _facts(ref)[1]
    floor_ = (max(party_level, 1) - 1) // 10 * 10 + 1
    return floor_ <= level <= floor_ + 9


def _pool(spec: FoeSpec, party_level: int) -> list[str]:
    """Every written creature of the right rank near the party's level.

    **The role is not passed to `loader.pick`**, and that is a correction
    rather than an oversight. Asking it to filter on one empties the pool for
    a whole rank: **253 of the 384 minions carry `role = 'minion'`** rather
    than a tactical role, so `pick(2, minion=True, role='skirmisher')` returns
    nothing at all while `role=None` returns 120. The fixture asked for four
    minion skirmishers and got the "nothing written fits" note.

    A module's role is a preference about how the fight should play, not a
    requirement, so it ranks in `_rank` instead -- where it costs nothing when
    the database cannot honour it.
    """
    return loader.pick(
        party_level, limit=0, band=BAND,
        rank=None if spec.rank == "minion" else spec.rank,
        minion=spec.rank == "minion",
    )


def _slot_cost(party_level: int, rank: str) -> float:
    """What one creature of a rank ought to cost, in XP.

    `budget` is `SIDE` standards, so one standard is `budget / SIDE` and
    `WORTH` prices the rest. The same arithmetic `_compose` settled on in #323,
    where centring the fit window on the *group's* share instead let a
    two-elite encounter field one creature.
    """
    return max((budget(party_level) / SIDE) * WORTH.get(rank, 1.0), 1.0)


def _rank(
    pool: list[str], spec: FoeSpec, party_level: int, draw: Random | None,
) -> list[str]:
    """Order a pool: theme first, then the role, then price, then level.

    Words before role because a module's words are what the *players* will see
    and the role is what the fight will feel like -- a goblin that fights like
    a brute still reads as a goblin, where a skirmisher that is not a goblin
    reads as the wrong monster. Both are preferences and neither can empty the
    pool.

    The shuffle survives every key for equal ranks, which is what stops two
    seeds meeting the same creature -- the fault `opposition` records, where
    every level-10 fight faced the same four creatures out of 41 written.
    """
    aim = _slot_cost(party_level, spec.rank)
    wanted = set(spec.words)
    ordered = list(pool)
    if draw is not None:
        ordered = draw.sample(ordered, len(ordered))

    def key(ref: str) -> tuple[int, int, float, int]:
        xp, level, words, role, _rank = _facts(ref)
        return (
            -len(wanted & words),            # most theme words first
            0 if (not spec.role or role == spec.role) else 1,
            abs(xp - aim) / max(aim, 1.0),   # then nearest a slot's price
            abs(level - party_level),        # then nearest the party
        )

    return sorted(ordered, key=key)


def resolve(
    scene: Scene, *, party_level: int, draw: Random | None = None,
) -> Dressed:
    """The creatures a combat scene fields, and how each one is dressed."""
    out = Dressed()
    if scene.kind != "combat":
        return out

    want = float(scene.xp) if scene.xp else budget(party_level) * scene.share
    if want <= 0:
        out.notes.append(
            f"{scene.id}: no XP is written for level {party_level}, so the "
            "budget cannot be worked out -- fielding the module's own counts"
        )
        want = float("inf")
    spent = 0.0

    for spec in scene.foes:
        named = find_by_name(spec.name) if spec.name else ""
        tier = ""
        pool: list[str] = []

        if named and usable(named) and in_tier(named, party_level):
            tier, pool = BY_NAME, [named]
        elif named and usable(named):
            out.notes.append(
                f"{scene.id}: the creature written for {spec.name!r} is level "
                f"{_facts(named)[1]}, outside the party's tier -- fielding "
                "something of the right shape instead"
            )
        elif named:
            out.notes.append(
                f"{scene.id}: {spec.name!r} resolves to {named}, which is not "
                "written yet -- fielding something of the right shape instead"
            )

        if not pool:
            candidates = _pool(spec, party_level)
            if spec.words:
                matching = [
                    r for r in candidates if set(spec.words) & _facts(r)[2]
                ]
                if matching:
                    tier, pool = BY_THEME, _rank(
                        matching, spec, party_level, draw)
            if not pool and candidates:
                tier, pool = BY_SHAPE, _rank(
                    candidates, spec, party_level, draw)

        if not pool:
            out.notes.append(
                f"{scene.id}: nothing written fits {spec.count}x "
                f"{spec.rank} {spec.role or 'any role'} near level "
                f"{party_level} -- that line is not fielded"
            )
            continue

        # A reflavour is only mechanical when the shape tier had to dress
        # something; a creature found by name or theme already *is* the thing,
        # and bending it further would be inventing rules the module did not
        # ask for. All three tiers carry the module's own name for display.
        flavour = (
            themed(spec.words, party_level, name=spec.name)
            if tier == BY_SHAPE
            else Reflavour(name=spec.name)
        )

        taken = 0
        for i in range(spec.count):
            ref = pool[i % len(pool)]
            cost = float(_facts(ref)[0])
            if (taken or out.refs) and spent + cost > want * OVER:
                break
            out.refs.append(ref)
            out.flavours.append(flavour)
            spent += cost
            taken += 1
        if taken < spec.count:
            out.notes.append(
                f"{scene.id}: the module asks for {spec.count}x "
                f"{spec.name or spec.rank} and the budget pays for {taken} "
                f"({spent:.0f} of {want:.0f} XP spent)"
            )

    return out
