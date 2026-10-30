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

from . import BAND, SIDE, WORTH, budget, ceiling
from .module import DIFFICULTY, FoeSpec, Scene
from .reflavour import Dressed, Reflavour, Wave, themed

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


def _for_party_size(
    out: Dressed, scene: Scene, party_level: int,
    party_size: int, stated_size: int,
) -> None:
    """The adventure's own rule for a table that is not the size it assumes.

    **It is a rule, not a table, which is what #798 had wrong.** The issue
    is titled "adjusts each encounter for party size *by name*" and the
    page does nothing of the kind. Every chapter prints the same two
    paragraphs, and where an encounter does mention a specific creature it
    is illustrating the rule rather than specifying anything.

    Paraphrased below, deliberately -- those two paragraphs are the
    adventure's prose and belong in git-ignored `modules/`, and quoting
    them here is what `leaks.py --modules` caught me doing:

    * **short a character** (four where the module assumes five): take one
      creature off the field, picked from the weakest or the least
      consequential, and never a minion.
    * **one over** (six): add a creature, the least complicated of the
      kinds already fielded, preferring whichever sits nearest the
      encounter's own level.

    So it needs no authoring at all, which is why it is built now rather
    than waiting for the trigger the issue set: a general rule over the
    fielded list costs one function, where a per-encounter table would
    have cost a schema field and a pass over every converted scene.

    **One adjustment, not one per missing character.** The page says "a
    weak party" and "remove one", and says nothing about a party of three.
    Scaling it per head would be our curve again, which is the thing the
    stated XP figure is trusted over.

    **"Least important" is not modelled**, because nothing on a stat block
    says it. Lowest level is the half that is measurable and is what the
    page names first; the note says so rather than implying the pick was
    the adventure's.
    """
    if not out.refs or not scene.xp:
        return
    if int(party_size) == int(stated_size) or not stated_size:
        return

    # `_facts` already carries the rank, cached -- a second loader call
    # per ref would be the same answer at more cost.
    bulk = [(ref, _facts(ref)[1]) for ref in out.refs
            if _facts(ref)[4] != "minion"]
    if not bulk:
        out.notes.append(
            f"{scene.id}: the party is {int(party_size)} against the "
            f"module's {int(stated_size)}, and the adventure's rule only "
            "moves non-minions -- this fight is all minions, so it is "
            "fielded as printed"
        )
        return

    if int(party_size) < int(stated_size):
        drop = min(bulk, key=lambda pair: (pair[1], out.refs.index(pair[0])))
        if len(out.refs) <= 1:
            out.notes.append(
                f"{scene.id}: the party is {int(party_size)} against the "
                f"module's {int(stated_size)}, and the only creature in "
                "this fight is the one the rule would remove -- fielded "
                "as printed instead"
            )
            return
        # **By index, because `flavours` runs parallel to `refs`.** A bare
        # `refs.remove` leaves the two lists one apart and every creature
        # after the removed one is dressed as its neighbour.
        gone = out.refs.index(drop[0])
        del out.refs[gone]
        if gone < len(out.flavours):
            del out.flavours[gone]
        out.notes.append(
            f"{scene.id}: a weak party ({int(party_size)} against the "
            f"module's {int(stated_size)}), so the adventure's rule drops "
            f"one non-minion -- {drop[0]}, the lowest level at {drop[1]}. "
            "'Least important' is the page's other word for it and is not "
            "modelled"
        )
        return

    add = min(bulk, key=lambda pair: (abs(pair[1] - party_level), pair[1],
                                      out.refs.index(pair[0])))
    # The copy is dressed exactly as the creature it is a second of --
    # the page says "another guard drake", not a differently flavoured one.
    twin = out.refs.index(add[0])
    out.refs.append(add[0])
    if twin < len(out.flavours):
        out.flavours.append(out.flavours[twin])
    out.notes.append(
        f"{scene.id}: a strong party ({int(party_size)} against the "
        f"module's {int(stated_size)}), so the adventure's rule adds one "
        f"more of a non-minion already here -- {add[0]}, level {add[1]}, "
        f"nearest the party's {party_level}"
    )


def _stepped(scene: Scene) -> tuple[float, str]:
    """The scene's share of the budget, moved one band by its objective.

    An objective changes what a fight costs to build: a party that has to hold
    a line, or get something out, is doing two things at once and the printed
    advice everywhere is to ease the opposition back for it -- or to tighten it
    when the objective makes the fight shorter. One **band**, not a free
    multiplier, so an objective can only ever buy what a module could have
    asked for by writing a different `difficulty`.

    Returns the share and a note, because `CLAUDE.md` is explicit that a cap
    the reader is not told about *"reads as 'covered everything' when it did
    not"* -- and a budget that silently moved is the same fault. The note is
    empty when nothing moved.

    **A stated `xp` figure still wins**, which `resolve` enforces by never
    consulting the share in that branch. That is deliberate and is the same
    call `#798` made for party size: a module that prints its own number for
    its own encounter is more trustworthy than our curve, so an objective
    cannot quietly re-price a fight the page already priced. A scene that
    wants both says so by dropping the `xp`.
    """
    aim = scene.objective
    if aim is None or not (aim.harder or aim.easier):
        return scene.share, ""
    ladder = sorted(DIFFICULTY, key=lambda name: DIFFICULTY[name])
    try:
        at = ladder.index(scene.difficulty)
    except ValueError:                      # a band the loader would refuse
        return scene.share, ""
    to = at + 1 if aim.harder else at - 1
    if not 0 <= to < len(ladder):
        # Already at the end of the ladder. Reported rather than clamped
        # silently: an author who wrote `harder` on a `deadly` scene asked for
        # something the ladder cannot express and should hear so.
        return scene.share, (
            f"{scene.id}: the {aim.kind} objective asks for a "
            f"{'harder' if aim.harder else 'easier'} fight and "
            f"{scene.difficulty} is already the end of the ladder, so the "
            "budget is unchanged"
        )
    moved = ladder[to]
    return DIFFICULTY[moved], (
        f"{scene.id}: the {aim.kind} objective makes this "
        f"{'harder' if aim.harder else 'easier'}, so the budget is built "
        f"as {moved} rather than {scene.difficulty}"
    )


def _draw_for(
    spec: FoeSpec, scene: Scene, party_level: int, draw: Random | None,
    out: Dressed,
) -> tuple[list[str], Reflavour]:
    """Which rows one module line could be, and how to dress them.

    **Lifted out of the foes loop so an ally draws the same way a foe
    does.** #961 wants a module's printed ally roster on the PC side, and
    an ally resolved by a second, similar-looking path is a second set of
    tiers to keep in step -- which is the duplication `table.characters`
    already records as a cost it could not avoid. Here it could.

    Returns an empty pool when nothing fits, having said so in `notes`.
    """
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
        return [], Reflavour()

    # A reflavour is only mechanical when the shape tier had to dress
    # something; a creature found by name or theme already *is* the thing,
    # and bending it further would be inventing rules the module did not
    # ask for. All three tiers carry the module's own name for display.
    flavour = (
        themed(spec.words, party_level, name=spec.name)
        if tier == BY_SHAPE
        else Reflavour(name=spec.name)
    )
    return pool, flavour


def resolve(
    scene: Scene, *, party_level: int, draw: Random | None = None,
    party_size: int = SIDE, stated_size: int = SIDE,
    pitch: float = 1.0,
) -> Dressed:
    """The creatures a combat scene fields, and how each one is dressed.

    `party_size` scales the budget, because the printed rule is one standard
    monster **per character** and `story.budget` is hard-wired to `SIDE`. A
    module written for five and played by four was getting a fight built for
    four either way; now that `run.party_for` fields the five the module asked
    for, the fight has to be built for five too, or the extra character is a
    free win. A scene that states its own `xp` overrides all of this, which is
    what every fight in the module in `modules/` does.
    """
    out = Dressed()
    if scene.kind != "combat":
        return out

    per_head = max(1, int(party_size)) / SIDE
    share, stepped = _stepped(scene)
    if stepped:
        out.notes.append(stepped)
    # **The budget's own clamp, said out loud.** `story.budget` returned 0
    # above the database's ceiling and every division downstream guards
    # itself with `max(aim, 1.0)`, so a module validated for a paragon party
    # fielded nobody and raised nothing -- which reads as a `cast_list` bug.
    # The budget clamps now; this is the half that makes the clamp visible,
    # the same way a deferred creature and a cut count are already printed.
    # #963.
    top = ceiling()
    if party_level > top:
        out.notes.append(
            f"party_level {party_level} is above the highest level this "
            f"database can field a standard monster at ({top}), so the "
            f"budget is level {top}'s and the creatures will be too"
        )
    # **The reactive scale, and only where the module said nothing.** A
    # printed `xp` figure overrides the headcount already, so a dynamic
    # scale has to sit outside it or a published encounter stops being the
    # encounter the page describes. #977.
    want = (
        float(scene.xp) if scene.xp
        else budget(party_level) * share * per_head * pitch
    )
    # **A stated XP figure overrides the headcount, silently until now.**
    # When a scene prints its own number -- which every fight in the one
    # converted chapter does -- `per_head` is never consulted, so a party
    # of six walks into a fight built for the module's five and nothing
    # says so. The fielded creatures are byte-identical at 4, 5 and 6.
    #
    # That is the thing this component is told not to do: `CLAUDE.md` --
    # "a silent cap reads as 'covered everything' when it did not". The
    # approximation stays, because a module that prints a number for its
    # own party size is more trustworthy than our curve; what changes is
    # that the reader is told the number is not being adjusted. #798.
    # **Against the module's own stated size, not `SIDE`.** The first
    # version compared with the standard four, so on a module written for
    # five it warned a party of five -- which is exactly right for that
    # adventure -- and said nothing to a party of four, which is the one
    # playing a fight built for somebody else.
    if scene.xp and int(party_size) != int(stated_size):
        # **The budget is still not rescaled**, and that is deliberate: a
        # module that printed a figure for its own party is more
        # trustworthy than our curve. What changed is that the adventure's
        # own creature rule is applied afterwards, so this no longer says
        # the fight is unscaled -- `_for_party_size` reports what it did.
        out.notes.append(
            f"{scene.id}: the module states {scene.xp} XP for a party of "
            f"{int(stated_size)}, so the figure is used as printed rather "
            f"than rescaled for the {int(party_size)} playing it"
        )
    if want <= 0:
        out.notes.append(
            f"{scene.id}: no XP is written for level {party_level}, so the "
            "budget cannot be worked out -- fielding the module's own counts"
        )
        want = float("inf")
    # **The allies, before a penny of the budget is spent**, because the
    # printed rule is to build the encounter for the party *including*
    # them -- so their worth is added to what the opposition may cost. #961.
    helped = _allies(out, scene, party_level, draw)
    if helped and want != float("inf"):
        want += helped
        out.notes.append(
            f"{scene.id}: the opposition's budget is topped up by "
            f"{helped:.0f} XP for them, so the fight is built to challenge "
            "the party that includes them"
        )
    spent = 0.0

    for spec in scene.foes:
        pool, flavour = _draw_for(spec, scene, party_level, draw, out)
        if not pool:
            continue

        # **A line that walks on later is a wave, not part of the board.**
        # The module's wave encounter imported as a flat cast with every
        # reinforcement standing there at round 1, which is a different
        # fight: the party faces the whole roster at once with no reason
        # to hurry and no escalation. #962.
        if spec.arrives:
            picked = tuple(pool[i % len(pool)] for i in range(spec.count))
            out.waves.append(Wave(
                at=spec.at, every=spec.every, until=spec.until,
                refs=picked, flavour=flavour, worth=spec.worth,
                name=spec.name))
            unpaid = sum(float(_facts(r)[0]) for r in picked)
            if spec.worth:
                # A wave that earns XP is paid for out of the budget, the
                # same as anything else on the board.
                spent += unpaid
            else:
                # **Said out loud rather than quietly free.** This is
                # #958's finding in a second place: difficulty that costs
                # the budget nothing is difficulty nobody priced. The
                # module states the rule, so it is followed and reported
                # rather than overridden.
                out.notes.append(
                    f"{scene.id}: a wave of {spec.count} arrives from round "
                    f"{spec.at} and is worth no XP by the module's own rule, "
                    f"so {unpaid:.0f} XP of threat is unpriced (#958)"
                )
            out.notes.append(
                f"{scene.id}: {spec.count} arrive at the start of round "
                f"{spec.at}"
                + (f" and every {spec.every} round(s) to {spec.until}"
                   if spec.every else "")
            )
            continue

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

    _for_party_size(out, scene, party_level, party_size, stated_size)
    return out


def _allies(
    out: Dressed, scene: Scene, party_level: int, draw: Random | None,
) -> float:
    """Draw the module's own ally roster, on the party's side. #961.

    **After the foes and after the party-size scaling**, deliberately: an
    ally is not part of the opposition's budget and must not be able to
    push a creature off it. What it *does* do is make the fight easier, and
    the printed rule says to pay for that --

    > *When a nonplayer character participates in an encounter, that
    > character earns an equal share of experience points. You should build
    > encounters to challenge the party that includes the ally.*

    -- so the opposition is topped up by what the allies are worth. **Each
    ally's own XP, not a standard monster each**: the module's allies are
    minions, worth a quarter, and crediting each with a full standard
    monster would double a four-character fight for six guards who die to
    one hit. DMG2's exact *"add the experience value of a standard monster
    of the companion character's level"* is written for a **companion**,
    which is a full party member and is #1015.
    """
    if scene.kind != "combat" or not scene.allies:
        return 0.0
    paid = 0.0
    for spec in scene.allies:
        pool, flavour = _draw_for(spec, scene, party_level, draw, out)
        if not pool:
            continue
        for i in range(spec.count):
            ref = pool[i % len(pool)]
            out.allies.append(ref)
            out.ally_flavours.append(flavour)
            paid += float(_facts(ref)[0])
    if not out.allies:
        return 0.0
    out.notes.append(
        f"{scene.id}: {len(out.allies)} ally/allies fight alongside the "
        f"party, worth {paid:.0f} XP"
    )
    return paid
